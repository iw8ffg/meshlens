"""Estensione di WP5: automazioni (traceroute periodici, bot, webhook) - contratto §4.3."""
import logging

log = logging.getLogger(__name__)


def install(rt, ctx) -> None:
    """Registra task periodici, agganci e servizi in ctx.ext."""
    return None
