"""Estensione di WP1: messaggi e avvio. Registra il motore di ricerca nei messaggi in
`ctx.ext["search"]` (contratto §4.3); la ricerca stessa e' in `msgsearch.py`/`api_search.py`."""
import logging

from . import db

log = logging.getLogger(__name__)


def install(rt, ctx) -> None:
    engine = db.search_engine(ctx.conn)
    ctx.ext["search"] = {"engine": engine}
    log.info("Ricerca nei messaggi: %s", engine)
