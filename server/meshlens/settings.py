"""Impostazioni persistenti (tabella settings, valori JSON)."""
import copy
import json
import re
import sqlite3
from datetime import datetime, timezone

from urllib.parse import urlsplit

from . import __version__
from .crypto import expand_psk

MASK = "••••"
EXPORT_FORMAT = 1

DEFAULTS: dict = {
    "saved_countries": ["IT"],
    "retention_messages_days": 90,
    "retention_positions_days": 90,
    "retention_telemetry_days": 365,
    "storage_cap_mb": 2048,
    "battery_alert_pct": 20,
    "silent_alert_hours": 6,
    "lan_access": False,
    "map_mode": "auto",
    "maps_source_url": "",
    "update_repo": "iw8ffg/meshlens",
    "update_token": "",
    "update_auto_check": True,
    "mqtt_channels": [],
    "mqtt_node_id": "",  # "" = id della prima radio collegata; altrimenti "!xxxxxxxx"
    "mqtt_send_confirmed": False,  # conferma "messaggio pubblico" gia' data
    "mqtt": {
        "host": "mqtt.meshtastic.org",
        "port": 1883,
        "username": "meshdev",
        "password": "large4cats",
        "topics": ["msh/EU_868/#"],
        "extra_keys": [],
    },
}

_INT_KEYS = ("retention_messages_days", "retention_positions_days",
             "retention_telemetry_days", "storage_cap_mb")
# interi con intervallo ammesso (min, max)
_RANGE_KEYS = {"battery_alert_pct": (1, 99), "silent_alert_hours": (1, 168)}
_MQTT_STR = ("host", "username", "password")


def normalize_topic(topic: str) -> str:
    """Un'iscrizione senza jolly ("msh/EU_868/IT") riceverebbe solo quell'argomento esatto,
    cioe' niente: si aggiunge "/#" per ricevere tutto cio' che sta sotto."""
    t = topic.strip()
    if not t or t.endswith("#") or "+" in t:
        return t
    return t.rstrip("/") + "/#"


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _validate_mqtt(m) -> None:
    if not isinstance(m, dict):
        raise ValueError("mqtt deve essere un oggetto")
    unknown = set(m) - set(DEFAULTS["mqtt"])
    if unknown:
        raise ValueError(f"Impostazione mqtt sconosciuta: {sorted(unknown)[0]}")
    for k in _MQTT_STR:
        if k in m and not isinstance(m[k], str):
            raise ValueError(f"mqtt.{k} deve essere una stringa")
    if "host" in m and not m["host"].strip():
        raise ValueError("mqtt.host non può essere vuoto")
    if "port" in m and not (_is_int(m["port"]) and 1 <= m["port"] <= 65535):
        raise ValueError("mqtt.port deve essere un numero tra 1 e 65535")
    for k in ("topics", "extra_keys"):
        if k in m and not (isinstance(m[k], list) and all(isinstance(x, str) for x in m[k])):
            raise ValueError(f"mqtt.{k} deve essere una lista di stringhe")
    if "topics" in m:
        m["topics"] = [t for t in (normalize_topic(x) for x in m["topics"]) if t]
    for key in m.get("extra_keys", []):
        try:
            expand_psk(key)
        except ValueError as e:
            raise ValueError(f"Chiave PSK non valida ({key}): {e}") from e


def _validate(key: str, value) -> None:
    if key not in DEFAULTS:
        raise ValueError(f"Impostazione sconosciuta: {key}")
    if key == "saved_countries":
        if not (isinstance(value, list) and all(
                isinstance(c, str) and re.fullmatch(r"[A-Z]{2}", c) for c in value)):
            raise ValueError("saved_countries deve essere una lista di codici di 2 lettere maiuscole")
    elif key in _INT_KEYS:
        if not (_is_int(value) and value > 0):
            raise ValueError(f"{key} deve essere un numero intero positivo")
    elif key in _RANGE_KEYS:
        lo, hi = _RANGE_KEYS[key]
        if not (_is_int(value) and lo <= value <= hi):
            raise ValueError(f"{key} deve essere un numero intero tra {lo} e {hi}")
    elif key == "lan_access":
        if not isinstance(value, bool):
            raise ValueError("lan_access deve essere vero o falso")
    elif key == "map_mode":
        if value not in ("auto", "online", "offline"):
            raise ValueError("map_mode deve essere auto, online oppure offline")
    elif key == "maps_source_url":
        if not isinstance(value, str):
            raise ValueError("maps_source_url deve essere una stringa")
        if value:
            u = urlsplit(value)
            if u.scheme != "https" or not u.netloc or not u.path.endswith(".pmtiles"):
                raise ValueError("maps_source_url deve essere un URL https che termina con .pmtiles")
    elif key == "update_repo":
        if not (isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value)):
            raise ValueError("update_repo deve avere il formato owner/nome")
    elif key == "update_token":
        if not isinstance(value, str):
            raise ValueError("update_token deve essere una stringa")
    elif key == "update_auto_check":
        if not isinstance(value, bool):
            raise ValueError("update_auto_check deve essere vero o falso")
    elif key == "mqtt_channels":
        if not (isinstance(value, list) and len(value) <= 20 and all(
                isinstance(c, str) and 0 < len(c) <= 32 for c in value)):
            raise ValueError("mqtt_channels deve essere una lista di al massimo 20 nomi "
                             "(da 1 a 32 caratteri)")
    elif key == "mqtt_node_id":
        if not (isinstance(value, str) and (value == "" or re.fullmatch(r"![0-9a-fA-F]{8}", value))):
            raise ValueError("mqtt_node_id deve essere vuoto oppure nel formato !xxxxxxxx")
    elif key == "mqtt_send_confirmed":
        if not isinstance(value, bool):
            raise ValueError("mqtt_send_confirmed deve essere vero o falso")
    elif key == "mqtt":
        _validate_mqtt(value)


def load_settings(conn: sqlite3.Connection) -> dict:
    """Default sovrascritti dai valori salvati."""
    result = copy.deepcopy(DEFAULTS)
    for row in conn.execute("SELECT key, value FROM settings"):
        if row["key"] not in DEFAULTS:
            continue
        value = json.loads(row["value"])
        if row["key"] == "mqtt":
            result["mqtt"].update(value)
        else:
            result[row["key"]] = value
    # argomenti salvati da versioni precedenti senza "/#" (non ricevevano nulla)
    result["mqtt"]["topics"] = [t for t in (normalize_topic(x) for x in result["mqtt"].get("topics", []))
                                if t] or list(DEFAULTS["mqtt"]["topics"])
    return result


def save_settings(conn: sqlite3.Connection, changes: dict) -> dict:
    """Valida e salva le modifiche (mqtt e' fuso con i valori esistenti)."""
    for key, value in changes.items():
        _validate(key, value)
    current = load_settings(conn)
    for key, value in changes.items():
        if key == "mqtt":
            current["mqtt"].update(value)
            value = current["mqtt"]
        conn.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, json.dumps(value)))
    conn.commit()
    return load_settings(conn)


def mask_secrets(s: dict) -> dict:
    """Copia senza segreti in chiaro: password MQTT, token di aggiornamento, chiavi PSK extra."""
    out = copy.deepcopy(s)
    mqtt = out.get("mqtt")
    if isinstance(mqtt, dict):
        if mqtt.get("password"):
            mqtt["password"] = MASK
        mqtt["extra_keys"] = [MASK for _ in mqtt.get("extra_keys", [])]
    if out.get("update_token"):
        out["update_token"] = MASK
    return out


def export_settings(s: dict, include_secrets: bool) -> dict:
    """Documento di esportazione (format 1)."""
    return {
        "app": "meshlens",
        "format": EXPORT_FORMAT,
        "version": __version__,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settings": copy.deepcopy(s) if include_secrets else mask_secrets(s),
    }


def prepare_import(data: dict) -> tuple[dict, list[str]]:
    """Da un documento esportato ricava le modifiche da salvare e le chiavi scartate."""
    if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
        raise ValueError("Formato del file di impostazioni non supportato")
    settings = data.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("Il file non contiene le impostazioni")
    changes = copy.deepcopy(settings)
    skipped: list[str] = []
    if "mqtt_send_confirmed" in changes:
        del changes["mqtt_send_confirmed"]  # la conferma resta una scelta di questo PC
        skipped.append("mqtt_send_confirmed")
    if changes.get("update_token") == MASK:
        del changes["update_token"]
        skipped.append("update_token")
    mqtt = changes.get("mqtt")
    if isinstance(mqtt, dict):
        if mqtt.get("password") == MASK:
            del mqtt["password"]
            skipped.append("mqtt.password")
        keys = mqtt.get("extra_keys")
        if isinstance(keys, list) and MASK in keys:
            del mqtt["extra_keys"]
            skipped.append("mqtt.extra_keys")
    return changes, skipped


_MASK_REF = re.compile("^" + re.escape(MASK) + r"#(\d+)$")


def resolve_extra_keys(entries, existing: list[str]):
    """Sostituisce le voci mascherate con le chiavi salvate: "••••#n" e' la n-esima chiave
    esistente, "••••" da solo e' quella nella stessa posizione. Le altre voci restano com'e'."""
    if not isinstance(entries, list):
        return entries
    out = []
    for i, e in enumerate(entries):
        ref = None
        if e == MASK:
            ref = i
        elif isinstance(e, str) and (m := _MASK_REF.match(e)):
            ref = int(m.group(1))
        if ref is None:
            out.append(e)
        elif ref < len(existing):
            out.append(existing[ref])
        else:
            raise ValueError("Chiave mascherata senza corrispondenza: reinseriscila")
    return out


def scrub_text(text: str, *secrets) -> str:
    """Sostituisce con MASK le occorrenze (come parola intera) dei segreti dati."""
    import re
    for secret in secrets:
        if secret and isinstance(secret, str):
            text = re.sub(rf"(?<!\w){re.escape(secret)}(?!\w)", MASK, text)
    return text
