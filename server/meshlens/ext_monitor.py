"""Estensione di WP2: avvisi su misura, sensori (Detection, Paxcounter) e salute della rete.

Collega il motore delle regole e il servizio dei sensori agli agganci del Runtime (contratto 4.2-4.4)."""
import asyncio
import logging

from .alert_rules import RuleEngine, RuleStore
from .sensors import SensorService

log = logging.getLogger(__name__)


def install(rt, ctx) -> None:
    store = RuleStore(ctx.conn)
    state = {"pending": False}

    def run() -> None:
        state["pending"] = False
        try:
            ctx.alerts()
        except Exception:  # noqa: BLE001 - un ricalcolo fallito non ferma l'ingestione
            log.exception("Ricalcolo degli avvisi fallito")

    def request_recalc() -> None:
        """Ricalcolo degli avvisi accorpato: piu' scatti nello stesso giro del loop = uno solo."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if state["pending"]:
            return
        state["pending"] = True
        loop.call_soon(run)

    def local_ids() -> set[str]:
        return ctx.radios.local_ids() if ctx.radios is not None else set()

    engine = RuleEngine(
        store, get_nodes=lambda: ctx.live.nodes, get_local_ids=local_ids,
        notify=lambda kind, key, **fmt: ctx.notifier.send(kind, key, dedup=False, **fmt),
        notify_ready=lambda now: ctx.notifier.rules_ready(now),
        request_recalc=request_recalc, publish=ctx.bus.publish, is_ignored=ctx.live.is_ignored)
    engine.reload()
    sensors = SensorService(ctx.conn, ctx.store, ctx.bus.publish,
                            lambda num: ctx.live.nodes.get(num), rt.ingestor.persists,
                            on_detection=engine.on_detection)
    ctx.ext["alert_rules"] = engine
    ctx.ext["sensors"] = sensors
    ctx.alert_sources.append(engine.alert_source)
    rt.add_message_hook(engine.on_message)
    rt.add_event_hook(sensors.on_event)  # prima i sensori, poi il motore
    rt.add_event_hook(engine.on_event)
