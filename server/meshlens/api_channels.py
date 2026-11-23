"""Rotta di WP4 per il link di condivisione dei canali (contiene le PSK in chiaro).

Risponde solo al loopback, controllato prima di toccare la radio; nessun log, niente cache.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .config_service import ConfigError

GUEST_GET_PATHS: tuple[str, ...] = ()

MSG_LOCAL_ONLY = "Il link dei canali si mostra solo da questo PC"
MSG_NO_CONFIG = "Configurazione radio non disponibile"


class ChannelExportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channels: list[Annotated[int, Field(ge=0, le=7)]] | None = Field(None, max_length=8)
    add: StrictBool = False


def register(app, ctx, require_auth, require_json) -> None:
    from .api import is_loopback_request  # qui: api.py importa api_radioadmin

    @app.post("/api/config/{node_id}/channels/export",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def export_channels(node_id: str, body: ChannelExportBody, request: Request):
        if not is_loopback_request(request):
            raise HTTPException(403, MSG_LOCAL_ONLY)
        if ctx.config is None or ctx.radios is None:
            raise HTTPException(503, MSG_NO_CONFIG)
        try:
            out = await ctx.config.export_channels(node_id, body.channels, body.add)
        except ConfigError as e:
            raise HTTPException(e.status, e.message) from None
        return JSONResponse(out, headers={"Cache-Control": "no-store"})
