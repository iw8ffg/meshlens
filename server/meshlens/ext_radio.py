"""Estensione di WP4: radio e canali (contratto §4.3).

Mette in ctx.ext["profiles"] l'archivio dei profili di configurazione (connessione del loop).
"""
from .profiles import ProfileStore


def install(rt, ctx) -> None:
    ctx.ext["profiles"] = ProfileStore(ctx.conn)
