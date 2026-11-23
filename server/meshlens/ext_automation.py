"""Estensione di WP5: automazioni (traceroute periodici, bot, webhook) - contratto §4.3.

Registra:
- task periodico `trace_scheduler` (60 s): al piu' un traceroute automatico per giro;
- task periodico `automation_bus` (1 s): svuota una coda del bus e la smista ai servizi
  (nessun task di lunga durata da gestire);
- ctx.ext["trace_scheduler"].
"""
import logging

from .trace_scheduler import TICK_S, TraceScheduler

log = logging.getLogger(__name__)

BUS_TICK_S = 1.0
BUS_SERVICES = ("trace_scheduler", "bot", "webhook")


def drain_bus(q, ext: dict) -> int:
    """Smista ai servizi gli eventi accumulati nella coda; restituisce quanti ne ha letti."""
    n = 0
    while not q.empty():
        msg = q.get_nowait()
        n += 1
        if msg.get("type") == "resync":
            continue
        for name in BUS_SERVICES:
            service = ext.get(name)
            if service is None:
                continue
            try:
                service.on_bus(msg)
            except Exception:
                log.exception("Automazioni: evento %s non gestito da %s", msg.get("type"), name)
    return n


def install(rt, ctx) -> None:
    """Registra task periodici, agganci e servizi in ctx.ext."""
    settings = lambda: rt.settings  # noqa: E731 - copia in cache aggiornata dal Runtime
    sched = TraceScheduler(ctx.conn, rt.store, rt.radios, rt.live, rt.bus, settings)
    try:
        sched.reconcile()
    except Exception:
        log.exception("Traceroute periodici: riallineamento all'avvio non riuscito")
    rt.add_periodic("trace_scheduler", TICK_S, sched.tick, first_delay_s=TICK_S)
    ctx.ext["trace_scheduler"] = sched

    q = rt.bus.subscribe()
    rt.add_periodic("automation_bus", BUS_TICK_S, lambda: drain_bus(q, ctx.ext),
                    first_delay_s=BUS_TICK_S)
    rt.add_shutdown(lambda: rt.bus.unsubscribe(q))
