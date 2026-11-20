"""Assemblaggio dell'applicazione: componenti, connettore MQTT e task periodici."""
import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI

from .api import AppContext, create_app
from .auth import Auth
from .bus import Bus
from .crypto import DEFAULT_KEY, expand_psk
from .db import connect
from .dedup import Deduplicator
from .geo import CountryLocator
from .ingest import Ingestor
from .live import LiveState
from .mqtt_client import MqttConnector
from .mqtt_decode import EnvelopeDecoder
from .settings import load_settings
from .store import Store

STATIC_DIR = Path(__file__).parents[2] / "web" / "dist"
PURGE_INTERVAL_S = 24 * 3600


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
    loop: asyncio.AbstractEventLoop | None = None
    connector: object = None
    tasks: list = field(default_factory=list)

    def start_connector(self) -> None:
        cfg = load_settings(self.conn)["mqtt"]
        self.connector = self.connector_factory(
            cfg, _make_decoder(cfg), self.loop, self.ingestor.handle)
        self.connector.start()

    def mqtt_status(self) -> dict:
        return self.connector.status() if self.connector else {
            "connected": False, "msgs_per_s": 0.0, "undecodable": 0}

    async def on_settings_changed(self, saved: dict) -> None:
        if self.connector is not None and getattr(self.connector, "cfg", None) == saved["mqtt"]:
            return
        if self.connector is not None:
            self.connector.stop()
        self.start_connector()

    async def _every(self, seconds: float, fn, first_now: bool = False) -> None:
        if not first_now:
            await asyncio.sleep(seconds)
        while True:
            try:
                fn()
            except Exception:
                pass  # un task periodico non deve mai morire
            await asyncio.sleep(seconds)

    def _publish_changed(self) -> None:
        changed = self.live.take_changed()
        if changed:
            self.bus.publish({"type": "nodes", "nodes": [
                {k: v for k, v in n.items() if k != "is_mine"} for n in changed]})

    def _purge(self) -> None:
        self.store.purge(time.time(), load_settings(self.conn))

    def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.start_connector()
        self.tasks = [
            asyncio.create_task(self._every(2, self._publish_changed)),
            asyncio.create_task(self._every(5, lambda: self.bus.publish(
                {"type": "status", "status": self.mqtt_status()}))),
            asyncio.create_task(self._every(1, self.store.commit)),
            asyncio.create_task(self._every(PURGE_INTERVAL_S, self._purge, first_now=True)),
            asyncio.create_task(self._every(60, lambda: self.dedup.prune(time.time()))),
        ]

    async def stop(self) -> None:
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
          static_dir: Path | None = STATIC_DIR) -> tuple[FastAPI, Runtime]:
    conn = connect(Path(data_dir) / "meshlens.db")
    store = Store(conn)
    live = LiveState()
    live.load(store.load_nodes())
    bus = Bus()
    dedup = Deduplicator()
    locator = CountryLocator()
    auth = Auth(conn)
    ingestor = Ingestor(live, store, dedup, locator, lambda: load_settings(conn),
                        lambda msg: bus.publish({"type": "message", "message": msg}))
    rt = Runtime(conn, store, live, auth, bus, dedup, ingestor, connector_factory)
    ctx = AppContext(live=live, store=store, auth=auth, bus=bus, locator=locator, conn=conn,
                     mqtt_status=rt.mqtt_status, on_settings_changed=rt.on_settings_changed,
                     static_dir=static_dir)
    app = create_app(ctx)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        rt.start()
        try:
            yield
        finally:
            await rt.stop()

    app.router.lifespan_context = lifespan
    return app, rt
