"""Rotte di WP4 (radio e canali). Segnaposto di WP0 (contratto §5): il pacchetto proprietario lo riempie.

Prefissi riservati (contratto §5.3):
    /api/nodes/{node_id}/ignored, /api/nodes/{node_id}/radio-flags, /api/profiles,
    /api/config/{node_id}/channels/export, /api/config/{node_id}/admin, /api/config/{node_id}/canned, /api/privacy
"""

# percorsi GET (esattamente come registrati) leggibili dall'ospite: solo mappa, nodi, statistiche
GUEST_GET_PATHS: tuple[str, ...] = ()


def register(app, ctx, require_auth, require_json) -> None:
    """Registra le rotte del modulo (chiamata in coda a create_app, prima dei file statici)."""
    return None
