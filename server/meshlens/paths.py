"""Percorsi dell'applicazione: sviluppo (repository) o versione installata (PyInstaller)."""
import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Cartella dell'eseguibile (installata) oppure radice del repository (sviluppo)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _local_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "MeshLens"


def default_data_dir() -> Path:
    if is_frozen():
        return _local_root() / "data"
    return app_dir() / "data"


def logs_dir() -> Path:
    """File di log: installata in %LOCALAPPDATA%/MeshLens/logs, sviluppo in data/logs."""
    if is_frozen():
        return _local_root() / "logs"
    return app_dir() / "data" / "logs"


def updates_dir() -> Path:
    """Dove finiscono gli installer scaricati (solo versione installata)."""
    return _local_root() / "updates"


def bundled_tool() -> Path | None:
    """go-pmtiles incluso nell'installer, se presente."""
    p = app_dir() / "tools" / "pmtiles.exe"
    return p if p.is_file() else None
