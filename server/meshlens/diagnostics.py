"""Pacchetto diagnostico: zip con versione, impostazioni senza segreti e coda dei log."""
import io
import json
import zipfile
from pathlib import Path

from .logsetup import LOG_FILE, tail_file
from .settings import mask_secrets, scrub_text

# (nome nel file zip, byte finali da includere)
LOG_PARTS = ((LOG_FILE, 512 * 1024), (f"{LOG_FILE}.1", 256 * 1024), ("console.log", 128 * 1024))


def _scrub_mqtt(info: dict, settings: dict) -> dict:
    """Difesa in profondita': nessun testo dello stato MQTT contiene utente o password."""
    mqtt = info.get("mqtt")
    if not isinstance(mqtt, dict) or not isinstance(mqtt.get("last_error"), str):
        return info
    cfg = settings.get("mqtt") or {}
    text = scrub_text(mqtt["last_error"], cfg.get("password"), cfg.get("username"))
    return {**info, "mqtt": {**mqtt, "last_error": text}}


def build_bundle(info: dict, settings: dict, log_dir: Path | None) -> bytes:
    info = _scrub_mqtt(info, settings)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.json", json.dumps(info, indent=2, ensure_ascii=False, default=str))
        z.writestr("settings.json", json.dumps(mask_secrets(settings), indent=2, ensure_ascii=False))
        if log_dir is not None:
            for name, limit in LOG_PARTS:
                p = Path(log_dir) / name
                if p.is_file():
                    z.writestr(name, tail_file(p, limit))
    return buf.getvalue()
