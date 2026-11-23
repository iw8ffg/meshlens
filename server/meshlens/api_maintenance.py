"""Rotte di WP5b (manutenzione): note di versione, conservazione, diagnosi radio.
Registrate da api_automation.register."""

# percorsi GET leggibili dall'ospite: nessuno
GUEST_GET_PATHS: tuple[str, ...] = ()


def register(app, ctx, require_auth, require_json) -> None:
    return None
