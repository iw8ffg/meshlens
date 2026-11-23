"""Rotte di WP1 (messaggi e avvio). Segnaposto di WP0 (contratto §5): il pacchetto proprietario lo riempie.

Prefissi riservati (contratto §5.3):
    /api/messages/search, /api/conversations/{key}/export, /api/search
"""

# percorsi GET (esattamente come registrati) leggibili dall'ospite: solo mappa, nodi, statistiche
GUEST_GET_PATHS: tuple[str, ...] = ()


def register(app, ctx, require_auth, require_json) -> None:
    """Registra le rotte del modulo (chiamata in coda a create_app, prima dei file statici)."""
    return None
