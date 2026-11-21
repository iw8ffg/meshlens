"""Assemblaggio dell'applicazione: componenti, connettore MQTT e task periodici."""
import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI

from .api import AppContext, create_app
from .auth import Auth
from .bus import Bus
from .config_service import ConfigService
from .coverage import CoverageRecorder
from .crypto import DEFAULT_KEY, expand_psk
from .db import connect
from .dedup import Deduplicator
from .geo import CountryLocator
from .ingest import Ingestor
from .live import LiveState
from .paths import is_frozen, updates_dir
from .maps import MapsManager
from .mqtt_client import MqttConnector
from .mqtt_decode import EnvelopeDecoder
from .pubsub_hub import PubSubHub
from .radio import RadioConnector
from .radio_manager import RadioManager
from .settings import load_settings
from .store import Store
from .updater import Updater

STATIC_DIR = Path(__file__).parents[2] / "web" / "dist"
PURGE_INTERVAL_S = 24 * 3600
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
    ctx: object = None  # AppContext
    tasks: list = field(default_factory=list)

    def start_connector(self) -> None:
        cfg = self.settings["mqtt"]
        self.connector = self.connector_factory(
            cfg, _make_decoder(cfg), self.loop, self.on_event or self.ingestor.handle)
        self.connector.start()

    def mqtt_status(self) -> dict:
        return self.connector.status() if self.connector else {
            "connected": False, "msgs_per_s": 0.0, "undecodable": 0}

    async def on_settings_changed(self, saved: dict) -> None:
        self.settings = saved
        if self.connector is not None and getattr(self.connector, "cfg", None) == saved["mqtt"]:
            return
        if self.connector is not None:
            old, self.connector = self.connector, None
            await asyncio.to_thread(old.stop)
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

    def _publish_status(self) -> None:
        self.bus.publish({"type": "status", "mqtt": self.mqtt_status()})

    def _purge(self) -> None:
        now = time.time()
        self.store.purge(now, self.settings)
        ttl = min(LIVE_NODE_TTL_S, self.settings["retention_positions_days"] * 86400)
        self.live.evict_older_than(now - ttl)

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        if self.maps is not None:
            self.maps.cleanup_tmp()  # .tmp rimasti da un download interrotto
        if self.updater is not None:
            self.updater.cleanup_tmp()
        if self.coverage is not None:
            self.coverage.start()
        self.start_connector()
        if self.radios is not None:
            await self.radios.start()
        self.tasks = [
            asyncio.create_task(self._every(2, self._publish_changed)),
            asyncio.create_task(self._every(5, self._publish_status)),
            asyncio.create_task(self._every(1, self.store.commit)),
            asyncio.create_task(self._every(PURGE_INTERVAL_S, self._purge, first_now=True)),
            asyncio.create_task(self._every(60, lambda: self.dedup.prune(time.time()))),
            asyncio.create_task(self._every(5, self._check_traceroutes)),
            asyncio.create_task(self._every(60, lambda: self.ctx.alerts())),
            asyncio.create_task(self._every(60, self._coverage_tick)),
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
          auto_update: bool = False) -> tuple[FastAPI, Runtime]:
    conn = connect(Path(data_dir) / "meshlens.db")
    store = Store(conn)
    live = LiveState()
    live.load(store.load_nodes())
    bus = Bus()
    dedup = Deduplicator()
    locator = CountryLocator()
    auth = Auth(conn)
    ingestor = Ingestor(live, store, dedup, locator, lambda: rt.settings,
                        lambda msg: bus.publish({"type": "message", "message": msg}),
                        lambda key, status: bus.publish(
                            {"type": "message_status", "key": key, "status": status}))
    rt = Runtime(conn, store, live, auth, bus, dedup, ingestor, connector_factory,
                 settings=load_settings(conn))
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
                         launcher_exit=lambda d: rt.ctx.request_exit(d))
    rt.auto_update = auto_update
    ctx = AppContext(live=live, store=store, auth=auth, bus=bus, locator=locator, conn=conn,
                     mqtt_status=rt.mqtt_status, on_settings_changed=rt.on_settings_changed,
                     static_dir=static_dir, radios=rt.radios, coverage=coverage,
                     config=rt.config, maps=rt.maps, updater=rt.updater, data_dir=Path(data_dir))
    rt.ctx = ctx
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
