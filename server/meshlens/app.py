"""Assemblaggio dell'applicazione: componenti, connettore MQTT e task periodici."""
import asyncio
import contextlib
import logging
import sqlite3
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI

from .api import AppContext, create_app
from .backup import BackupManager, apply_pending_restore, open_db, quick_check_file
from .auth import Auth
from .bus import Bus
from .config_service import ConfigService
from .coverage import CoverageRecorder
from .crypto import DEFAULT_KEY, expand_psk
from .dedup import Deduplicator
from .geo import CountryLocator
from .ingest import Ingestor
from .live import LiveState
from .paths import is_frozen, updates_dir
from .maps import MapsManager
from .mqtt_client import MqttConnector
from .mqtt_decode import EnvelopeDecoder
from .mqtt_publish import MqttSender
from .pubsub_hub import PubSubHub
from .radio import RadioConnector
from .radio_manager import RadioManager
from .settings import (CONNECT_KEYS, enabled_brokers, find_broker, load_settings,
                       migrate_brokers, migrate_secrets, scrub_text)
from .store import PURGE_CHUNK, Store
from .storeforward import StoreForwardService
from .updater import Updater

# installata: PyInstaller mette web/dist accanto alle librerie incluse (sys._MEIPASS)
if getattr(sys, "frozen", False):
    STATIC_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "web" / "dist"
else:
    STATIC_DIR = Path(__file__).parents[2] / "web" / "dist"
PURGE_INTERVAL_S = 3600
PURGE_FIRST_DELAY_S = 60
BACKUP_CHECK_S = 3600
MQTT_SILENT_S = 300  # connesso ma muto da tanto: ricollega
MQTT_WATCHDOG_EVERY_S = 30
MQTT_RETRY_START_S = 60  # connettore non partito: nuovo tentativo al massimo ogni 60 s
BACKUP_FIRST_DELAY_S = 300
LIVE_NODE_TTL_S = 7 * 24 * 3600
log = logging.getLogger(__name__)


def broker_keys(broker: dict) -> tuple[list[bytes], dict[str, bytes]]:
    """Chiavi del decoder di un broker: [DEFAULT_KEY] + PSK dei canali + extra_keys (senza
    vuoti ne' doppioni) e {nome: chiave} dei canali personalizzati."""
    custom = {ch["name"]: expand_psk(ch["psk"]) for ch in broker.get("channels", [])
              if ch.get("psk") != ""}  # "" = chiave persa: nessuna chiave da usare
    keys = [DEFAULT_KEY]
    extra = [expand_psk(k) for k in broker.get("extra_keys", []) if k.strip()]
    for k in [*custom.values(), *extra]:
        if k and k not in keys:
            keys.append(k)
    return keys, custom


def _connect_changed(old: dict, new: dict) -> bool:
    return any(old.get(k) != new.get(k) for k in CONNECT_KEYS)


# stato di un broker senza connettore (disattivato o non partito)
_IDLE_DROPS = ("empty", "unsupported_port", "undecodable", "json_topic", "not_protobuf")


def _idle_status() -> dict:
    return {"connected": False, "msgs_per_s": 0.0, "undecodable": 0,
            "connected_since": None, "last_msg_age_s": None, "reconnects": 0,
            "last_error": None, "last_error_at": None, "decoded": 0,
            "drops": {k: 0 for k in _IDLE_DROPS}, "queue_dropped": 0, "queue_size": 0}


_SUMMED = ("msgs_per_s", "undecodable", "decoded", "reconnects", "queue_size",
           "queue_dropped", "watchdog_restarts")


@dataclass
class Runtime:
    conn: object
    store: Store
    live: LiveState
    auth: Auth
    bus: Bus
    dedup: Deduplicator
    ingestor: Ingestor
    connector_factory: object
    coverage: CoverageRecorder | None = None
    on_event: object = None  # ingestor, poi registratore copertura
    loop: asyncio.AbstractEventLoop | None = None
    settings: dict = field(default_factory=dict)  # copia in cache: evita SQL a ogni pacchetto
    radios: RadioManager | None = None
    config: ConfigService | None = None
    maps: MapsManager | None = None
    updater: Updater | None = None
    auto_update: bool = False  # controllo automatico ogni 24 h (attivo solo nell'app reale)
    connectors: dict = field(default_factory=dict)  # id broker -> connettore
    learned_keys: dict = field(default_factory=dict)  # id broker -> canale -> chiave
    ctx: object = None  # AppContext
    tasks: list = field(default_factory=list)
    last_purge: dict | None = None
    db_path: Path | None = None
    backups: BackupManager | None = None
    db_health: str = "in corso"  # quick_check in un thread all'avvio
    watchdog_restarts: dict = field(default_factory=dict)  # id broker -> riavvii
    queue_dropped_retired: int = 0  # scarti della coda dei connettori gia' fermati
    _connector_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    monotonic: Callable[[], float] = time.monotonic
    _last_start_attempt: dict = field(default_factory=dict)  # id broker -> monotonic()
    _integrity_conn: object = None  # connessione del quick_check in corso (per interromperla)
    _stopping: bool = False
    _start_errors: dict = field(default_factory=dict)  # id broker -> (testo, time()) dell'avvio fallito
    storeforward: StoreForwardService | None = None

    def start_connector(self, broker: dict) -> None:
        bid = broker["id"]
        self._last_start_attempt[bid] = self.monotonic()
        keys, custom = broker_keys(broker)
        # le chiavi imparate sopravvivono al riavvio; le personalizzate vincono
        decoder = EnvelopeDecoder(keys, {**self.learned_keys.get(bid, {}), **custom}, broker=bid)
        connector = self.connector_factory(
            broker, decoder, self.loop, self.on_event or self.ingestor.handle)
        connector.start()
        self.connectors[bid] = connector
        self._start_errors.pop(bid, None)

    def _try_start(self, broker: dict, what: str) -> bool:
        try:
            self.start_connector(broker)
        except Exception as e:
            self.connectors.pop(broker["id"], None)
            # senza connettore l'errore va comunque mostrato su quel broker (senza credenziali)
            text = scrub_text(f"Avvio non riuscito: {e}", broker.get("password"), broker.get("username"))
            log.error("%s del connettore MQTT %s fallito: %s", what,
                      broker.get("name") or broker["id"], text)
            if log.isEnabledFor(logging.DEBUG):  # il traceback puo' contenere credenziali
                log.debug("Traceback dell'avvio MQTT %s: %s", broker["id"], scrub_text(
                    traceback.format_exc(), broker.get("password"), broker.get("username")))
            self._start_errors[broker["id"]] = (text, time.time())
            return False
        return True

    def start_connectors(self) -> None:
        """Avvia tutti i broker attivi: l'errore di uno non ferma gli altri (il watchdog ritenta)."""
        for b in enabled_brokers(self.settings):
            if b["id"] not in self.connectors:
                self._try_start(b, "Avvio")

    def mqtt_status(self) -> dict:
        entries = []
        for b in self.settings.get("mqtt_brokers", []):
            c = self.connectors.get(b["id"])
            st = {**_idle_status(), **(c.status() if c is not None else {})}
            failed = self._start_errors.get(b["id"])
            if c is None and failed is not None and b.get("enabled"):
                st["last_error"], st["last_error_at"] = failed
            entries.append({**st, "id": b["id"], "name": b.get("name"), "enabled": bool(b.get("enabled")),
                            "host": b.get("host"), "tls": bool(b.get("tls")),
                            "encryption": bool(b.get("encryption")),
                            "watchdog_restarts": self.watchdog_restarts.get(b["id"], 0)})
        total = {k: sum(e.get(k) or 0 for e in entries) for k in _SUMMED}
        total["msgs_per_s"] = float(total["msgs_per_s"])
        total["queue_dropped"] += self.queue_dropped_retired
        # anche i riavvii dei broker eliminati: il totale non torna indietro
        total["watchdog_restarts"] = sum(self.watchdog_restarts.values())
        drops: dict[str, int] = {k: 0 for k in _IDLE_DROPS}
        for e in entries:
            for k, v in (e.get("drops") or {}).items():
                drops[k] = drops.get(k, 0) + (v or 0)
        connected = [e for e in entries if e["enabled"] and e.get("connected")]
        since = [e["connected_since"] for e in connected if e.get("connected_since") is not None]
        ages = [e["last_msg_age_s"] for e in entries if e.get("last_msg_age_s") is not None]
        errors = [e for e in entries if e.get("last_error")]
        last = max(errors, key=lambda e: e.get("last_error_at") or 0, default=None)
        last_error = None
        if last is not None:
            many = len(enabled_brokers(self.settings)) > 1
            last_error = f"{last['name']}: {last['last_error']}" if many else last["last_error"]
        return {**total, "connected": bool(connected), "drops": drops,
                "connected_since": min(since, default=None),
                "last_msg_age_s": min(ages, default=None),
                "last_error": last_error,
                "last_error_at": None if last is None else last.get("last_error_at"),
                "filtered_channel": self.ingestor.filtered_channel,
                "brokers": entries}

    async def _retire_connector(self, broker_id: str) -> None:
        """Ferma un connettore tenendo le chiavi imparate e il totale degli scarti della coda."""
        old = self.connectors.pop(broker_id, None)
        if old is None:
            return
        learned = getattr(getattr(old, "decoder", None), "channel_keys", None)
        if learned:
            self.learned_keys[broker_id] = dict(learned)
        await asyncio.to_thread(old.stop)
        self.queue_dropped_retired += getattr(getattr(old, "inbox", None), "dropped", 0)

    async def restart_connector(self, broker_id: str, reason: str, expected=None) -> None:
        """`expected`: il connettore giudicato da riavviare; se nel frattempo e' cambiato
        (impostazioni salvate mentre si attendeva il lock) non si riavvia quello nuovo."""
        async with self._connector_lock:
            if expected is not None and self.connectors.get(broker_id) is not expected:
                return
            await self._restart_connector(broker_id, reason)

    async def _restart_connector(self, broker_id: str, reason: str) -> None:
        await self._retire_connector(broker_id)
        broker = find_broker(self.settings, broker_id)
        if broker is None or not broker.get("enabled"):
            return  # disattivato o eliminato nel frattempo
        self.watchdog_restarts[broker_id] = self.watchdog_restarts.get(broker_id, 0) + 1
        log.warning("MQTT %s: %s", broker.get("name") or broker_id, reason)
        if not self._try_start(broker, "Riavvio"):
            return
        note = getattr(self.connectors[broker_id], "set_error", None)
        if note is not None:
            note(reason)

    async def mqtt_watchdog(self) -> None:
        """Per ogni broker: se risulta connesso ma tace da troppo, ricollega da zero.

        Solo se su quel connettore i messaggi arrivavano: un broker tranquillo (o un
        filtro che non riceve nulla) non va ricollegato ogni 5 minuti. Per ogni broker
        attivo senza connettore ritenta l'avvio al massimo ogni MQTT_RETRY_START_S."""
        for bid, connector in list(self.connectors.items()):
            if self._is_silent(connector.status()):
                await self.restart_connector(
                    bid, f"Nessun messaggio da {MQTT_SILENT_S} s: ricollegamento", expected=connector)
        for b in enabled_brokers(self.settings):
            if b["id"] not in self.connectors:
                await self._retry_start_connector(b["id"])

    @staticmethod
    def _is_silent(st: dict) -> bool:
        if not st.get("connected"):
            return False
        if not st.get("decoded") and st.get("last_msg_age_s") is None:
            return False  # mai arrivato nulla da quando si e' connesso: niente da ricollegare
        ages = [a for a in (st.get("last_msg_age_s"),
                            None if st.get("connected_since") is None
                            else time.time() - st["connected_since"]) if a is not None]
        return bool(ages) and min(ages) > MQTT_SILENT_S

    async def _retry_start_connector(self, broker_id: str) -> None:
        async with self._connector_lock:
            broker = find_broker(self.settings, broker_id)
            if broker_id in self.connectors or broker is None or not broker.get("enabled"):
                return
            last = self._last_start_attempt.get(broker_id)
            if last is not None and self.monotonic() - last < MQTT_RETRY_START_S:
                return
            if self._try_start(broker, "Nuovo avvio"):
                log.info("MQTT %s: connettore avviato al nuovo tentativo",
                         broker.get("name") or broker_id)

    async def on_settings_changed(self, saved: dict) -> None:
        async with self._connector_lock:
            await self._on_settings_changed(saved)

    async def _on_settings_changed(self, saved: dict) -> None:
        if self._stopping:  # in chiusura: nessun connettore va (ri)avviato
            return
        self.settings = saved
        brokers = {b["id"]: b for b in saved.get("mqtt_brokers", [])}
        for bid in list(self.connectors):
            b = brokers.get(bid)
            if b is None or not b.get("enabled"):
                await self._retire_connector(bid)
        for bid in list(self.learned_keys):
            if bid not in brokers:  # broker eliminato: le sue chiavi si dimenticano
                del self.learned_keys[bid]
        for bid in list(self._last_start_attempt):
            if bid not in brokers:
                del self._last_start_attempt[bid]
        for bid in list(self._start_errors):
            b = brokers.get(bid)
            if b is None or not b.get("enabled"):
                del self._start_errors[bid]
        for b in enabled_brokers(saved):
            connector = self.connectors.get(b["id"])
            if connector is None:
                self._try_start(b, "Avvio")
                continue
            old = getattr(connector, "cfg", None) or {}
            if _connect_changed(old, b):
                await self._retire_connector(b["id"])
                self._try_start(b, "Avvio")
                continue
            new_keys = broker_keys(b)
            decoder = getattr(connector, "decoder", None)
            if decoder is not None and broker_keys(old) != new_keys:
                decoder.set_keys(*new_keys)  # senza ricollegarsi
            connector.cfg = b  # nome, crittografia: nient'altro da fare
            if hasattr(connector, "label"):
                connector.label = b.get("name") or b.get("host")  # nome nei log

    async def _every(self, seconds: float, fn, first_now: bool = False) -> None:
        if not first_now:
            await asyncio.sleep(seconds)
        while True:
            try:
                fn()
            except Exception:
                log.exception("Task periodico fallito")  # il task resta vivo
            await asyncio.sleep(seconds)

    async def _every_async(self, seconds: float, fn: Callable[[], Awaitable[None]],
                           first_delay: float) -> None:
        await asyncio.sleep(first_delay)
        while True:
            try:
                await fn()
            except Exception:
                log.exception("Task periodico fallito")  # il task resta vivo
            await asyncio.sleep(seconds)

    async def _backup_if_due(self) -> None:
        if self.backups is not None and self.backups.due(time.time()):
            await self.backups.create("settimanale")

    def _publish_changed(self) -> None:
        changed = self.live.take_changed()
        if changed:
            self.bus.publish({"type": "nodes", "nodes": [
                dict(n) for n in changed]})

    def _check_traceroutes(self) -> None:
        if self.radios is not None:
            self.radios.check_traceroutes()

    def _coverage_tick(self) -> None:
        if self.coverage is not None:
            self.coverage.tick()

    def prune_memory(self) -> None:
        """Ogni minuto: dimentica i pacchetti fuori finestra e tiene i nodi in memoria sotto il limite."""
        self.dedup.prune(time.time())
        removed = self.live.enforce_cap()
        if removed:
            log.info("Nodi in memoria oltre il limite: rimossi %d sentiti meno di recente", removed)

    def _publish_status(self) -> None:
        self.bus.publish({"type": "status", "mqtt": self.mqtt_status()})

    async def purge_once(self) -> dict:
        """Pulizia a blocchi: tra un blocco e l'altro il loop resta libero."""
        now = time.time()
        total: dict[str, int] = {}
        while True:
            step = self.store.purge_step(now, self.settings, limit=PURGE_CHUNK)
            self.store.commit()
            for k, v in step.deleted.items():
                total[k] = total.get(k, 0) + v
            if step.done:
                break
            await asyncio.sleep(0.05)
        self.store.incremental_vacuum()
        ttl = min(LIVE_NODE_TTL_S, self.settings["retention_positions_days"] * 86400)
        self.live.evict_older_than(now - ttl)
        self.last_purge = {"time": now, "deleted": total}
        log.info("Pulizia: %s", total)
        return total

    async def check_integrity(self) -> None:
        """PRAGMA quick_check fuori dal loop, con una connessione propria in sola lettura."""
        if self.db_path is None:
            self.db_health = "non controllata"
            return
        self.db_health = "in corso"
        try:
            result = await asyncio.to_thread(quick_check_file, self.db_path,
                                             on_open=self._integrity_opened)
        finally:
            self._integrity_conn = None
        self.db_health = result
        if result == "ok":
            log.info("Controllo d'integrità del database: ok")
        else:
            log.error("Controllo d'integrità del database fallito: %s", result)

    def _integrity_opened(self, conn) -> None:
        """(thread del controllo) Tiene la connessione per poterla interrompere in stop()."""
        if self._stopping:  # interrupt() prima di una query non avrebbe effetto
            raise sqlite3.OperationalError("interrupted")
        self._integrity_conn = conn
        if self._stopping:  # stop() arrivato tra il controllo e l'assegnazione
            self._integrity_conn = None
            raise sqlite3.OperationalError("interrupted")

    def _interrupt_integrity(self) -> None:
        self._stopping = True
        conn = self._integrity_conn
        if conn is not None:
            with contextlib.suppress(Exception):  # gia' chiusa: il controllo e' finito
                conn.interrupt()

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        if self.maps is not None:
            self.maps.cleanup_tmp()  # .tmp rimasti da un download interrotto
        if self.updater is not None:
            self.updater.cleanup_tmp()
        if self.coverage is not None:
            self.coverage.start()
        self.start_connectors()  # chi non parte viene ritentato dal watchdog
        if self.radios is not None:
            await self.radios.start()
        self.tasks = [
            asyncio.create_task(self.check_integrity()),
            asyncio.create_task(self._every(2, self._publish_changed)),
            asyncio.create_task(self._every(5, self._publish_status)),
            asyncio.create_task(self._every(1, self.store.commit)),
            asyncio.create_task(self._every_async(PURGE_INTERVAL_S, self.purge_once, PURGE_FIRST_DELAY_S)),
            asyncio.create_task(self._every(60, self.prune_memory)),
            asyncio.create_task(self._every(5, self._check_traceroutes)),
            asyncio.create_task(self._every(60, lambda: self.ctx.alerts())),
            asyncio.create_task(self._every(60, self._coverage_tick)),
            asyncio.create_task(self._every_async(MQTT_WATCHDOG_EVERY_S, self.mqtt_watchdog,
                                                  MQTT_WATCHDOG_EVERY_S)),
            asyncio.create_task(self._every_async(BACKUP_CHECK_S, self._backup_if_due,
                                                  BACKUP_FIRST_DELAY_S)),
        ]
        if self.storeforward is not None:
            self.tasks.append(asyncio.create_task(self._every(5, self.storeforward.check)))
        if self.updater is not None and self.auto_update:
            self.tasks.append(asyncio.create_task(self.updater.run()))

    async def stop(self) -> None:
        # un quick_check lungo su un database grande non deve bloccare la chiusura
        self._interrupt_integrity()
        if self.maps is not None:
            await self.maps.shutdown()  # uccide l'eventuale processo di ritaglio
        if self.config is not None:
            await self.config.stop()
        if self.radios is not None:
            await self.radios.stop()
        for t in self.tasks:  # prima i task: il watchdog non riavvia piu' nulla
            t.cancel()
        for t in self.tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        async with self._connector_lock:
            # tutti insieme e fuori dal loop: un broker lento non ritarda gli altri
            items = list(self.connectors.items())
            results = await asyncio.gather(*(asyncio.to_thread(c.stop) for _, c in items),
                                           return_exceptions=True)
            for (bid, _), r in zip(items, results):
                if isinstance(r, BaseException):
                    log.error("Arresto del connettore MQTT %s fallito", bid, exc_info=r)
            self.connectors.clear()
        with contextlib.suppress(Exception):
            self.store.commit()
            self.conn.close()


def build(data_dir: Path, connector_factory=MqttConnector,
          static_dir: Path | None = STATIC_DIR,
          radio_connector_factory=RadioConnector, update_http=None,
          auto_update: bool = False, log_dir: Path | None = None) -> tuple[FastAPI, Runtime]:
    db_path = Path(data_dir) / "meshlens.db"
    restored = apply_pending_restore(Path(data_dir))
    if restored:
        log.warning("Ripristino completato dal backup %s", restored)
    backups = BackupManager(db_path, Path(data_dir) / "backups")
    conn = open_db(Path(data_dir), backups)
    migrated = migrate_secrets(conn)
    if migrated:
        log.info("Segreti salvati in chiaro riscritti cifrati: %d", migrated)
    if migrate_brokers(conn):
        log.info("Impostazioni MQTT migrate a più broker")
    store = Store(conn)
    live = LiveState()
    live.load(store.load_nodes())
    bus = Bus()
    dedup = Deduplicator()
    locator = CountryLocator()
    auth = Auth(conn)
    if restored:
        # le sessioni e i blocchi del backup non valgono piu': il PIN torna quello di allora
        auth.forget_sessions_and_locks()
        log.warning("Dopo il ripristino: sessioni e blocchi dei tentativi azzerati, "
                    "ogni dispositivo deve accedere di nuovo")
    ingestor = Ingestor(live, store, dedup, locator, lambda: rt.settings,
                        lambda msg: bus.publish({"type": "message", "message": msg}),
                        lambda key, status: bus.publish(
                            {"type": "message_status", "key": key, "status": status}))
    rt = Runtime(conn, store, live, auth, bus, dedup, ingestor, connector_factory,
                 settings=load_settings(conn), db_path=db_path,
                 backups=backups)
    coverage = CoverageRecorder(store, live, bus,
                                radio_node=ingestor.radio_node)

    # i messaggi rigiocati dal router S&F rientrano da on_event come testi normali
    sf = StoreForwardService(store, live, lambda ev: on_event(ev), bus,
                             lambda rid: rt.radios.connector(rid))

    def on_event(ev) -> None:
        if ev.kind == "storeforward":
            sf.handle(ev)
            return
        if ev.kind == "text":
            sf.observe_text(ev)  # rifiuto di una richiesta S&F: il testo va comunque in chat
        # prima l'ingestor (aggiorna i nodi), poi il registratore delle prove di copertura
        ingestor.handle(ev)
        coverage.handle(ev)

    rt.coverage, rt.on_event, rt.storeforward = coverage, on_event, sf
    rt.radios = RadioManager(store, ingestor, bus, None, PubSubHub(None),
                              connector_factory=radio_connector_factory, on_event=on_event)
    rt.config = ConfigService(store, rt.radios, live, bus)
    rt.maps = MapsManager(data_dir, lambda: rt.settings, bus)
    rt.updater = Updater(lambda: rt.settings, bus, update_http, frozen=is_frozen(),
                         updates_dir=updates_dir(),
                         launcher_exit=lambda d: rt.ctx.request_exit(d),
                         before_install=lambda: rt.backups.create("pre-aggiornamento"))
    rt.auto_update = auto_update
    ctx = AppContext(live=live, store=store, auth=auth, bus=bus, locator=locator, conn=conn,
                     mqtt_status=rt.mqtt_status,
                     mqtt_channel_counts=ingestor.mqtt_channel_counts,
                     mqtt_channel_brokers=ingestor.mqtt_channel_brokers,
                     on_settings_changed=rt.on_settings_changed,
                     static_dir=static_dir, radios=rt.radios, coverage=coverage, storeforward=sf,
                     config=rt.config, maps=rt.maps, updater=rt.updater, data_dir=Path(data_dir),
                     db_path=rt.db_path, last_purge=lambda: rt.last_purge,
                     backups=backups, db_health=lambda: rt.db_health, log_dir=log_dir)
    rt.ctx = ctx
    def key_for(bid: str, channel: str) -> bytes | None:
        """Chiave del canale vista dal decoder del broker (personalizzata o imparata);
        altrimenti quella imparata prima dell'ultimo arresto del suo connettore."""
        decoder = getattr(rt.connectors.get(bid), "decoder", None)
        key = decoder.channel_keys.get(channel) if decoder is not None else None
        return key if key is not None else rt.learned_keys.get(bid, {}).get(channel)

    ctx.mqtt_sender = MqttSender(
        lambda bid: rt.connectors.get(bid), lambda: rt.settings, rt.radios.radios, time.time,
        ingestor.record_outgoing_mqtt, key_for)
    app = create_app(ctx)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        await rt.start()
        try:
            yield
        finally:
            await rt.stop()

    app.router.lifespan_context = lifespan
    return app, rt
