"""Estensione di WP3: mappa e topologia (aggancio eventi tak, ctx.ext["tak"]) (contratto §4.3)."""
from .tak import TakService


def install(rt, ctx) -> None:
    svc = TakService(ctx.store.conn, ctx.bus.publish, rt.ingestor.persists, ctx.live.nodes.get)
    rt.add_event_hook(svc.on_event)
    ctx.ext["tak"] = svc
