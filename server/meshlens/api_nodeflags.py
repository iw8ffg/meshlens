"""Rotte di WP4 per i nodi ignorati e i preferiti/ignorati nel NodeDB delle radio collegate.

"Ignora" scrive sempre in MeshLens (AppContext.set_node_ignored) e prova sulle radio locali;
un errore radio non annulla l'ignorato locale (esito per radio).
"""
import logging

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .store import ignored_nums

log = logging.getLogger(__name__)

GUEST_GET_PATHS: tuple[str, ...] = ()

MSG_OWN_RADIO = "Non puoi ignorare il nodo di una tua radio"
MSG_NO_FLAG = "Nessun flag indicato"
MSG_NO_CONFIG = "Configurazione radio non disponibile"


class IgnoredBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ignored: StrictBool
    radio: StrictBool = True


class RadioFlagsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    favorite: StrictBool | None = None
    ignored: StrictBool | None = None
    radio_id: str | None = Field(None, max_length=64)


def _move_before(app, path: str, before: str) -> None:
    """Sposta la rotta `path` prima di `before` (rotte con parametro registrate prima)."""
    routes = app.router.routes
    mine = [r for r in routes if getattr(r, "path", None) == path]
    for r in mine:
        routes.remove(r)
    idx = next((i for i, r in enumerate(routes) if getattr(r, "path", None) == before),
               len(routes))
    routes[idx:idx] = mine


def register(app, ctx, require_auth, require_json) -> None:
    from .api import _num_from_id, _public  # qui: api.py importa api_radioadmin

    def config():
        if ctx.config is None or ctx.radios is None:
            raise HTTPException(503, MSG_NO_CONFIG)
        return ctx.config

    def own_radio_ids() -> set[str]:
        ids = set()
        if ctx.radios is not None:
            ids |= set(ctx.radios.local_ids())
            ids |= {r.get("my_node_id") for r in ctx.radios.radios() if r.get("my_node_id")}
        return ids

    @app.get("/api/nodes/ignored", dependencies=[Depends(require_auth)])
    async def ignored_nodes():
        # anche i nodi ignorati non in memoria (servono all'elenco per ripristinarli)
        out = []
        for num in sorted(ignored_nums(ctx.conn)):
            node = ctx.live.nodes.get(num) or ctx.store.get_node(num)
            if node is not None:
                out.append(_public(node))
        out.sort(key=lambda n: ((n.get("long_name") or n.get("short_name") or n.get("id")
                                 or "").lower(), n.get("num") or 0))
        return out

    # /api/nodes/{node_id} (api.py) e' registrata prima: "ignored" va confrontata prima
    _move_before(app, "/api/nodes/ignored", "/api/nodes/{node_id}")

    @app.put("/api/nodes/{node_id}/ignored",
             dependencies=[Depends(require_auth), Depends(require_json)])
    async def set_ignored(node_id: str, body: IgnoredBody):
        num = _num_from_id(node_id)
        nid = f"!{num:08x}"
        if body.ignored and nid in own_radio_ids():
            raise HTTPException(400, MSG_OWN_RADIO)
        node = ctx.set_node_ignored(num, body.ignored)
        if node is None:
            raise HTTPException(404, "Nodo non trovato")
        radios: list[dict] = []
        if body.radio and ctx.config is not None and ctx.radios is not None:
            try:
                radios = await ctx.config.set_radio_flags(nid, ignored=body.ignored)
            except Exception as exc:  # mai 500 per la radio: l'ignorato locale resta
                log.warning("flag ignorato sulle radio non scritto: %s", type(exc).__name__)
        return {"node": _public(node), "radios": radios}

    @app.get("/api/nodes/{node_id}/radio-flags", dependencies=[Depends(require_auth)])
    async def get_radio_flags(node_id: str):
        nid = f"!{_num_from_id(node_id):08x}"
        return {"radios": config().radio_flags(nid)}

    @app.put("/api/nodes/{node_id}/radio-flags",
             dependencies=[Depends(require_auth), Depends(require_json)])
    async def put_radio_flags(node_id: str, body: RadioFlagsBody):
        nid = f"!{_num_from_id(node_id):08x}"
        if body.favorite is None and body.ignored is None:
            raise HTTPException(400, MSG_NO_FLAG)
        svc = config()
        radios = await svc.set_radio_flags(
            nid, favorite=body.favorite, ignored=body.ignored,
            radio_ids=[body.radio_id] if body.radio_id else None)
        return {"radios": radios}
