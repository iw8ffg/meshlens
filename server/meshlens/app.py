"""Assemblaggio dell'applicazione: componenti, connettore MQTT e task periodici."""
import asyncio
import contextlib
import logging
import sys
import time
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
from .settings import load_settings, migrate_brokers, migrate_secrets
from .store import PURGE_CHUNK, Store
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


def _make_decoder(mqtt_cfg: dict) -> EnvelopeDecoder:
    keys = [DEFAULT_KEY] + [expand_psk(k) for k in mqtt_cfg.get("extra_keys", []) if k.strip()]
    return EnvelopeDecoder(keys)


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
    connector: object = None
    learned_keys: dict = field(default_factory=dict)  # canale -> chiave vista decifrare
    ctx: object = None  # AppContext
    tasks: list = field(default_factory=list)
    last_purge: dict | None = None
    db_path: Path | None = None
    backups: BackupManager | None = None
    db_health: str = "in corso"  # quick_check in un thread all'avvio
    watchdog_restarts: int = 0
    queue_dropped_retired: int = 0  # scarti della coda dei connettori gia' fermati
    _connector_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    monotonic: Callable[[], float] = time.monotonic
    _last_start_attempt: float = 0.0  # monotonic() dell'ultimo avvio del connettore

    def start_connector(self) -> None:
        self._last_start_attempt = self.monotonic()
        cfg = self.settings["mqtt"]
        decoder = _make_decoder(cfg)
        decoder.channel_keys.update(self.learned_keys)  # sopravvivono al riavvio del connettore
        self.connector = self.connector_factory(
            cfg, decoder, self.loop, self.on_event or self.ingestor.handle)
        self.connector.start()

    def mqtt_status(self) -> dict:
        base = self.connector.status() if self.connector else {
            "connected": False, "msgs_per_s": 0.0, "undecodable": 0,
            "connected_since": None, "last_msg_age_s": None, "reconnects": 0,
            "last_error": None, "last_error_at": None, "decoded": 0,
            "drops": {"empty": 0, "unsupported_port": 0, "undecodable": 0,
                      "json_topic": 0, "not_protobuf": 0},
            "queue_dropped": 0, "queue_size": 0}
        return {**base, "filtered_channel": self.ingestor.filtered_channel,
                "watchdog_restarts": self.watchdog_restarts,
                "queue_dropped": base.get("queue_dropped", 0) + self.queue_dropped_retired}

    async def _retire_connector(self, old) -> None:
        """Ferma un connettore tenendo le chiavi imparate e il totale degli scarti della coda."""
        self.learned_keys.update(getattr(getattr(old, "decoder", None), "channel_keys", {}))
        await asyncio.to_thread(old.stop)
        self.queue_dropped_retired += getattr(getattr(old, "inbox", None), "dropped", 0)

    async def restart_connector(self, reason: str) -> None:
        async with self._connector_lock:
            await self._restart_connector(reason)

    async def _restart_connector(self, reason: str) -> None:
        old, self.connector = self.connector, None
        if old is not None:
            await self._retire_connector(old)
        self.watchdog_restarts += 1
        log.warning("MQTT: %s", reason)
        try:
            self.start_connector()
        except Exception:
            log.exception("Riavvio del connettore MQTT fallito")
            self.connector = None
            return
        note = getattr(self.connector, "set_error", None)
        if note is not None:
            note(reason)

    async def mqtt_watchdog(self) -> None:
        """Se il broker risulta connesso ma tace da troppo, ricollega da zero.

        Solo se su questo connettore i messaggi arrivavano: un broker tranquillo (o un
        filtro che non riceve nulla) non va ricollegato ogni 5 minuti. Se il connettore
        non e' partito, ritenta l'avvio al massimo ogni MQTT_RETRY_START_S."""
        if self.connector is None:
            await self._retry_start_connector()
            return
        st = self.connector.status()
        if not st.get("connected"):
            return
        if not st.get("decoded") and st.get("last_msg_age_s") is None:
            return  # mai arrivato nulla da quando si e' connesso: niente da ricollegare
        ages = [a for a in (st.get("last_msg_age_s"),
                            None if st.get("connected_since") is None
                            else time.time() - st["connected_since"]) if a is not None]
        if ages and min(ages) > MQTT_SILENT_S:
            await self.restart_connector(f"Nessun messaggio da {MQTT_SILENT_S} s: ricollegamento")

    async def _retry_start_connector(self) -> None:
        async with self._connector_lock:
            if self.connector is not None:
                return
            if self.monotonic() - self._last_start_attempt < MQTT_RETRY_START_S:
                return
            try:
                self.start_connector()
            except Exception:
                log.exception("Nuovo avvio del connettore MQTT fallito")
                self.connector = None
                return
            log.info("MQTT: connettore avviato al nuovo tentativo")

    async def on_settings_changed(self, saved: dict) -> None:
        async with self._connector_lock:
            await self._on_settings_changed(saved)

    async def _on_settings_changed(self, saved: dict) -> None:
        self.settings = saved
        if self.connector is not None and getattr(self.connector, "cfg", None) == saved["mqtt"]:
            return
        if self.connector is not None:
            old, self.connector = self.connector, None
            await self._retire_connector(old)
        try:
            self.start_connector()
        except Exception:
            log.exception("Avvio del connettore MQTT fallito")
            self.connector = None

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
        result = await asyncio.to_thread(quick_check_file, self.db_path)
        self.db_health = result
        if result == "ok":
            log.info("Controllo d'integrità del database: ok")
        else:
            log.error("Controllo d'integrità del database fallito: %s", result)

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        if self.maps is not None:
            self.maps.cleanup_tmp()  # .tmp rimasti da un download interrotto
        if self.updater is not None:
            self.updater.cleanup_tmp()
        if self.coverage is not None:
            self.coverage.start()
        try:
            self.start_connector()
        except Exception:  # il watchdog ritenta l'avvio
            log.exception("Avvio del connettore MQTT fallito")
            self.connector = None
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
        if self.updater is not None and self.auto_update:
            self.tasks.append(asyncio.create_task(self.updater.run()))

    async def stop(self) -> None:
        if self.maps is not None:
            await self.maps.shutdown()  # uccide l'eventuale processo di ritaglio
        if self.config is not None:
            await self.config.stop()
        if self.radios is not None:
            await self.radios.stop()
        if self.connector is not None:
            self.connector.stop()
        for t in self.tasks:
            t.cancel()
        for t in self.tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
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

    def on_event(ev) -> None:
        # prima l'ingestor (aggiorna i nodi), poi il registratore delle prove di copertura
        ingestor.handle(ev)
        coverage.handle(ev)

    rt.coverage, rt.on_event = coverage, on_event
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
                     on_settings_changed=rt.on_settings_changed,
                     static_dir=static_dir, radios=rt.radios, coverage=coverage,
                     config=rt.config, maps=rt.maps, updater=rt.updater, data_dir=Path(data_dir),
                     db_path=rt.db_path, last_purge=lambda: rt.last_purge,
                     backups=backups, db_health=lambda: rt.db_health, log_dir=log_dir)
    rt.ctx = ctx
    ctx.mqtt_sender = MqttSender(
        lambda: rt.connector, lambda: rt.settings, rt.radios.radios, time.time,
        ingestor.record_outgoing_mqtt,
        lambda ch: getattr(getattr(rt.connector, "decoder", None), "channel_keys", {}).get(ch))
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
