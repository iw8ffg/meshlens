"""Estensioni della 1.6: ogni pacchetto di lavoro registra i propri agganci da un modulo
ext_*.py, installato da build() prima di create_app. Un'estensione che fallisce non ferma
l'avvio."""
import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # solo per i tipi: app importa questo modulo
    from .api import AppContext
    from .app import Runtime

log = logging.getLogger(__name__)

EXTENSIONS: tuple[str, ...] = ("ext_messages", "ext_monitor", "ext_map", "ext_radio",
                               "ext_automation")


def install(rt: "Runtime", ctx: "AppContext") -> None:
    """Importa ogni modulo meshlens.<nome> e chiama mod.install(rt, ctx)."""
    for name in EXTENSIONS:
        try:
            mod = importlib.import_module(f"{__package__}.{name}")
            mod.install(rt, ctx)
        except Exception:
            log.exception("Estensione %s non avviata", name)
