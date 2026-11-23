"""Rotte di WP5 (automazioni): traceroute periodici, bot, webhook.

Prefissi riservati (contratto §5.3):
    /api/trace-targets, /api/bot, /api/webhook, /api/retention,
    /api/radios/diagnose, /api/radios/{radio_id}/diagnose, /api/update/notes, /api/update/seen
Le rotte di manutenzione stanno in api_maintenance (registrato da qui).
Gli interruttori dedicati (traceroute_auto_enabled, bot_enabled, webhook_enabled) si accendono
solo da qui: PUT /api/settings puo' soltanto spegnerli (contratto §2).
"""
import re

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import api_maintenance
from .api_data import run_read
from .settings import load_settings, save_settings
from .store import Store

EXT_UNAVAILABLE_MSG = "Automazioni non disponibili"
BAD_NODE_ID_MSG = "Identificativo del nodo non valido"
BAD_LIMIT_MSG = "Numero di risultati non valido: da 1 a 100"
HISTORY_DEFAULT = 20
HISTORY_MAX = 100
_NODE_ID = re.compile(r"![0-9a-fA-F]{8}")

# percorsi GET (esattamente come registrati) leggibili dall'ospite: nessuno
GUEST_GET_PATHS: tuple[str, ...] = (*api_maintenance.GUEST_GET_PATHS,)


def _ext(ctx, key: str):
    """Servizio dell'estensione (ctx.ext[key]) o 503 se l'estensione non e' installata."""
    ext = ctx if isinstance(ctx, dict) else getattr(ctx, "ext", None) or {}
    service = ext.get(key)
    if service is None:
        raise HTTPException(503, EXT_UNAVAILABLE_MSG)
    return service


def _node_num(node_id: str) -> int:
    if not _NODE_ID.fullmatch(node_id or ""):
        raise HTTPException(400, BAD_NODE_ID_MSG)
    return int(node_id[1:], 16)


def annotate_history(conn, rows: list[dict]) -> list[dict]:
    """Aggiunge route_changed/prev_route alle righe (ordine tempo decrescente): per ogni riga
    ok il percorso dell'ok precedente (anche oltre la pagina); le altre righe mai cambiate."""
    out = [dict(r, route_changed=False, prev_route=None) for r in rows]
    prev: str | None = None
    found = False  # trovato un ok piu' vecchio dentro la pagina
    for i in range(len(out) - 1, -1, -1):  # dal piu' vecchio al piu' recente
        item = out[i]
        if item["status"] != "ok" or item.get("route") is None:
            continue
        if not found:
            num = int(item["target_id"][1:], 16)
            row = conn.execute(
                "SELECT route FROM traceroutes WHERE target_num=? AND status='ok' "
                "AND route IS NOT NULL AND (time < ? OR (time = ? AND id < ?)) "
                "ORDER BY time DESC, id DESC LIMIT 1",
                (num, item["time"], item["time"], item["id"])).fetchone()
            prev = row[0] if row else None
            found = True
        item["prev_route"] = prev
        item["route_changed"] = prev is not None and prev != item["route"]
        prev = item["route"]
    return out


class TraceTargetBody(BaseModel):
    enabled: bool = True
    interval_min: int
    radio_id: str | None = Field(None, max_length=64)


class SwitchBody(BaseModel):
    enabled: bool


def register(app, ctx, require_auth, require_json) -> None:
    """Registra le rotte del modulo (chiamata in coda a create_app, prima dei file statici)."""
    auth = [Depends(require_auth)]
    write = [Depends(require_auth), Depends(require_json)]

    async def save(changes: dict) -> dict:
        try:
            saved = save_settings(ctx.conn, changes)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await ctx.on_settings_changed(saved)
        return saved

    # ---- traceroute periodici ----------------------------------------------
    @app.get("/api/trace-targets", dependencies=auth)
    async def trace_targets():
        sched = _ext(ctx, "trace_scheduler")
        return sched.status()

    @app.post("/api/trace-targets/enable", dependencies=write)
    async def trace_targets_enable(body: SwitchBody):
        sched = _ext(ctx, "trace_scheduler")
        await save({"traceroute_auto_enabled": body.enabled})
        return sched.status()

    @app.put("/api/trace-targets/{node_id}", dependencies=write)
    async def trace_target_put(node_id: str, body: TraceTargetBody):
        sched = _ext(ctx, "trace_scheduler")
        _node_num(node_id)
        try:
            return sched.upsert(node_id.lower(), enabled=body.enabled,
                                interval_min=body.interval_min, radio_id=body.radio_id)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/trace-targets/{node_id}", dependencies=write)
    async def trace_target_delete(node_id: str):
        sched = _ext(ctx, "trace_scheduler")
        _node_num(node_id)
        sched.remove(node_id.lower())
        return {"ok": True}

    @app.get("/api/trace-targets/{node_id}/history", dependencies=auth)
    async def trace_target_history(node_id: str, limit: int = Query(HISTORY_DEFAULT),
                                   before: float | None = None):
        num = _node_num(node_id)
        if not 1 <= limit <= HISTORY_MAX:
            raise HTTPException(400, BAD_LIMIT_MSG)

        def read(conn):
            return annotate_history(conn, Store(conn).traceroutes(num, limit, before))
        return await run_read(ctx, read)

    api_maintenance.register(app, ctx, require_auth, require_json)
