"""Rotte di WP1 (messaggi e avvio): ricerca nel testo dei messaggi, ricerca globale (Ctrl+K) ed
esportazione di una conversazione. Solo GET, in sola lettura (`api_data.run_read`).

Prefissi riservati (contratto §5.3):
    /api/messages/search, /api/conversations/{key}/export, /api/search
"""
from fastapi import Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from .api_data import run_read
from .conv_export import export_conversation
from .msgsearch import (InvalidCursor, LIMIT_MAX, MAX_QUERY_CHARS, search_messages,
                        search_nodes)

# percorsi GET (esattamente come registrati) leggibili dall'ospite: nessuno (niente messaggi)
GUEST_GET_PATHS: tuple[str, ...] = ()

GLOBAL_NODES = 8
GLOBAL_MESSAGES = 5
_NODE_ID = r"^![0-9a-fA-F]{8}$"


def _local_ids(ctx) -> set[str]:
    """Id dei nodi locali (come `local_nodes` di api.py, che e' una closure)."""
    ids = {n["id"] for n in ctx.live.nodes.values() if n.get("is_local_radio")}
    if ctx.radios is not None:
        ids |= ctx.radios.local_ids()
    return ids


def register(app, ctx, require_auth, require_json) -> None:
    """Registra le rotte del modulo (chiamata in coda a create_app, prima dei file statici)."""
    from .api import _num_from_id

    @app.get("/api/messages/search", dependencies=[Depends(require_auth)])
    async def messages_search(q: str = Query(..., min_length=1, max_length=MAX_QUERY_CHARS),
                              conv: str | None = Query(None, max_length=64),
                              sender: str | None = Query(None, pattern=_NODE_ID),
                              since: float | None = None, until: float | None = None,
                              cursor: str | None = Query(None, max_length=128),
                              limit: int = Query(50, ge=1, le=LIMIT_MAX)):
        num = _num_from_id(sender.lower()) if sender else None
        local = _local_ids(ctx)
        try:
            return await run_read(ctx, lambda c: search_messages(
                c, q, conv=conv, sender=num, since=since, until=until, cursor=cursor,
                limit=limit, local_ids=local))
        except InvalidCursor:
            raise HTTPException(400, "Cursore di ricerca non valido")
        except ValueError:
            raise HTTPException(400, "Conversazione non valida")

    @app.get("/api/conversations/{key}/export", dependencies=[Depends(require_auth)])
    async def conversation_export(key: str, since: float | None = None,
                                  until: float | None = None):
        local = _local_ids(ctx)
        try:
            data = await run_read(ctx, lambda c: export_conversation(
                c, key, local, since=since, until=until))
        except ValueError:
            raise HTTPException(400, "Conversazione non valida")
        return JSONResponse(data, headers={"Cache-Control": "no-store"})

    @app.get("/api/search", dependencies=[Depends(require_auth)])
    async def global_search(q: str = Query(..., min_length=1, max_length=MAX_QUERY_CHARS),
                            limit: int = Query(GLOBAL_NODES, ge=1, le=GLOBAL_NODES)):
        local = _local_ids(ctx)

        def job(c):
            res = search_messages(c, q, limit=GLOBAL_MESSAGES, local_ids=local)
            return {"nodes": search_nodes(c, q, limit), "messages": res["hits"],
                    "engine": res["engine"]}
        return await run_read(ctx, job)
