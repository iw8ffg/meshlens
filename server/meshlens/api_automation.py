"""Rotte di WP5 (automazioni): traceroute periodici, bot, webhook.

Prefissi riservati (contratto §5.3):
    /api/trace-targets, /api/bot, /api/webhook, /api/retention,
    /api/radios/diagnose, /api/radios/{radio_id}/diagnose, /api/update/notes, /api/update/seen
Le rotte di manutenzione stanno in api_maintenance (registrato da qui).
"""
from fastapi import HTTPException

from . import api_maintenance

EXT_UNAVAILABLE_MSG = "Automazioni non disponibili"

# percorsi GET (esattamente come registrati) leggibili dall'ospite: nessuno
GUEST_GET_PATHS: tuple[str, ...] = (*api_maintenance.GUEST_GET_PATHS,)


def _ext(ctx, key: str):
    """Servizio dell'estensione (ctx.ext[key]) o 503 se l'estensione non e' installata."""
    ext = ctx if isinstance(ctx, dict) else getattr(ctx, "ext", None) or {}
    service = ext.get(key)
    if service is None:
        raise HTTPException(503, EXT_UNAVAILABLE_MSG)
    return service


def register(app, ctx, require_auth, require_json) -> None:
    """Registra le rotte del modulo (chiamata in coda a create_app, prima dei file statici)."""
    api_maintenance.register(app, ctx, require_auth, require_json)
