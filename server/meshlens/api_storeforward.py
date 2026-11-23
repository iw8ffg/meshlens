"""Rotte Store & Forward: router noti, richiesta dello storico, verifica del router, lavori."""
import re

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .storeforward import SfError

_NODE_ID = re.compile(r"![0-9a-fA-F]{8}")
MSG_BAD_ID = "Identificativo del nodo non valido"
MSG_UNAVAILABLE = "Store & Forward non disponibile"
GUEST_GET_PATHS: tuple[str, ...] = ()  # E19: niente per l'ospite (messaggi conservati)


class RequestBody(BaseModel):
    radio_id: str
    router_id: str
    window_min: int = Field(ge=5, le=1440)
    channel_index: int = Field(ge=0, le=7)


class ProbeBody(BaseModel):
    radio_id: str
    router_id: str
    channel_index: int = Field(ge=0, le=7)


def _router_num(router_id: str) -> int:
    if not _NODE_ID.fullmatch(router_id):
        raise HTTPException(400, MSG_BAD_ID)
    return int(router_id[1:], 16)


def register(app, ctx, require_auth, require_json) -> None:
    def service():
        if ctx.storeforward is None:
            raise HTTPException(503, MSG_UNAVAILABLE)
        return ctx.storeforward

    def error_response(err: SfError) -> JSONResponse:
        headers = {"Retry-After": str(err.retry_after)} if err.retry_after is not None else None
        return JSONResponse({"detail": str(err)}, status_code=err.status, headers=headers)

    @app.get("/api/storeforward/routers", dependencies=[Depends(require_auth)])
    async def sf_routers():
        return service().routers()

    @app.get("/api/storeforward/jobs", dependencies=[Depends(require_auth)])
    async def sf_jobs():
        return service().jobs()

    @app.post("/api/storeforward/request", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def sf_request(body: RequestBody):
        num = _router_num(body.router_id)
        try:
            return await service().request(body.radio_id, num, body.window_min,
                                           body.channel_index)
        except SfError as err:
            return error_response(err)

    @app.post("/api/storeforward/probe", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def sf_probe(body: ProbeBody):
        num = _router_num(body.router_id)
        try:
            await service().probe(body.radio_id, num, body.channel_index)
        except SfError as err:
            return error_response(err)
        return {}
