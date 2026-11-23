"""Rotte di WP4 (radio e canali): comandi admin, messaggi predefiniti, privacy della posizione.

Registra anche le rotte dei moduli propri di WP4 (nodi ignorati e flag radio, profili,
esportazione dei canali). Prefissi riservati (contratto §5.3):
    /api/nodes/{node_id}/ignored, /api/nodes/{node_id}/radio-flags, /api/profiles,
    /api/config/{node_id}/channels/export, /api/config/{node_id}/admin, /api/config/{node_id}/canned, /api/privacy
(piu' GET /api/nodes/ignored, decisione R4.1).
"""
from typing import Annotated

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from . import api_channels, api_nodeflags, api_profiles
from .config_service import ConfigError

# nessuna rotta di configurazione per l'ospite
GUEST_GET_PATHS: tuple[str, ...] = (
    api_nodeflags.GUEST_GET_PATHS + api_profiles.GUEST_GET_PATHS + api_channels.GUEST_GET_PATHS)

MSG_NO_CONFIG = "Configurazione radio non disponibile"


class AdminCommandBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(max_length=32)
    confirm: StrictBool = False
    radio_id: str | None = Field(None, max_length=64)


class CannedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # la regola vera (200 byte con i separatori) e' in config_model.join_canned
    messages: list[Annotated[str, Field(max_length=200)]] = Field(max_length=50)
    radio_id: str | None = Field(None, max_length=64)


class PrivacyPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bits: int
    channels: list[Annotated[int, Field(ge=0, le=7)]] | None = Field(None, max_length=8)


async def service_call(result):
    """Attende una chiamata al servizio: ConfigError -> HTTP."""
    try:
        if hasattr(result, "__await__"):
            return await result
        return result
    except ConfigError as e:
        raise HTTPException(e.status, e.message) from None


def register(app, ctx, require_auth, require_json) -> None:
    """Registra le rotte del modulo (chiamata in coda a create_app, prima dei file statici)."""

    def config():
        if ctx.config is None or ctx.radios is None:
            raise HTTPException(503, MSG_NO_CONFIG)
        return ctx.config

    # ---- comandi admin (E13) ----
    @app.get("/api/config/{node_id}/admin", dependencies=[Depends(require_auth)])
    async def admin_status(node_id: str, radio_id: str | None = None):
        return await service_call(config().admin_status(node_id, radio_id))

    @app.post("/api/config/{node_id}/admin", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def admin_command(node_id: str, body: AdminCommandBody):
        return await service_call(config().admin_command(node_id, body.radio_id, body.command,
                                                         body.confirm))

    # ---- messaggi predefiniti (E10) ----
    @app.get("/api/config/{node_id}/canned", dependencies=[Depends(require_auth)])
    async def get_canned(node_id: str, radio_id: str | None = None):
        return await service_call(config().get_canned(node_id, radio_id))

    @app.put("/api/config/{node_id}/canned",
             dependencies=[Depends(require_auth), Depends(require_json)])
    async def put_canned(node_id: str, body: CannedBody):
        return await service_call(config().set_canned(node_id, body.radio_id, body.messages))

    # ---- privacy della posizione (E12) ----
    @app.get("/api/privacy", dependencies=[Depends(require_auth)])
    async def privacy():
        return {"radios": await service_call(config().privacy_report())}

    @app.post("/api/privacy/{node_id}/preview",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def privacy_preview(node_id: str, body: PrivacyPreviewBody):
        return await service_call(config().privacy_preview(node_id, body.bits, body.channels))

    api_nodeflags.register(app, ctx, require_auth, require_json)
    api_profiles.register(app, ctx, require_auth, require_json)
    api_channels.register(app, ctx, require_auth, require_json)
