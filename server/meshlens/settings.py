"""Impostazioni persistenti (tabella settings, valori JSON)."""
import base64
import copy
import json
import logging
import re
import secrets
import sqlite3
from datetime import datetime, timezone

from urllib.parse import urlsplit

from . import __version__
from .crypto import expand_psk
from .secretbox import SECRET_KEYS, SecretError, get_protector

log = logging.getLogger(__name__)
MASK = "••••"
EXPORT_FORMAT = 1

DEFAULTS: dict = {
    "saved_countries": ["IT"],
    "retention_messages_days": 90,
    "retention_positions_days": 90,
    "retention_telemetry_days": 365,
    "storage_cap_mb": 2048,
    "packet_log_mode": "archived",  # ispettore dei pacchetti: off | archived | all
    "retention_packets_hours": 48,
    "backup_retention_days": 0,  # elimina i backup piu' vecchi di N giorni (0 = mai)
    "battery_alert_pct": 20,
    "silent_alert_hours": 6,
    "lan_access": False,
    "lan_https": False,  # HTTPS sulla porta successiva per l'accesso dalla rete
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
    "mqtt_send_confirmed_brokers": [],  # broker per cui la conferma e' gia' data
    # notifiche esterne (toast di Windows dall'icona, bot Telegram)
    "notify_toast": True,
    "notify_telegram": False,
    "telegram_token": "",  # segreto (SECRET_KEYS)
    "telegram_chat_id": "",
    "notify_mine_status": True,
    "notify_new_node": False,
    "notify_keywords": [],
    # ---- 1.6 ----
    "onboarding_done": False,
    "quick_replies": [],
    "favorites_to_radio": False,
    "traceroute_auto_enabled": False,
    "traceroute_auto_max_per_hour": 6,
    "bot_enabled": False,
    "bot_targets": [],
    "bot_commands": ["ping", "info", "time"],
    "bot_weather_node": "",
    "bot_replies": [],
    "bot_min_interval_s": 30,
    "bot_max_per_hour": 20,
    "bot_node_cooldown_s": 300,
    "webhook_enabled": False,
    "webhook_url": "",  # segreto (SECRET_KEYS)
    "webhook_events": ["alert"],
    "update_channel": "stable",
    "last_seen_version": "",
    "guest_enabled": False,
    "retention_traceroutes_days": 365,
    "retention_broker_days": {},
}

BOT_COMMANDS = ("ping", "info", "nodes", "time", "weather")
WEBHOOK_EVENTS = ("message", "alert", "sensor", "traceroute", "node_new")
MAX_QUICK_REPLIES = 20
QUICK_REPLY_MAX_BYTES = 200
MAX_BOT_TARGETS = 16
MAX_BOT_REPLIES = 20
# scelte di questo PC: un file di impostazioni importato non le cambia mai
LOCAL_ONLY_KEYS = ("onboarding_done", "last_seen_version", "guest_enabled", "bot_enabled",
                   "webhook_enabled")

DEFAULT_BROKER_ID = "default"
DEFAULT_BROKER_NAME = "mqtt.meshtastic.org (predefinito)"
MAX_BROKERS = 8
MAX_BROKER_CHANNELS = 16
MAX_CHANNEL_NAME_BYTES = 11
MAX_BROKER_NAME = 40
BROKER_KEYS = ("id", "name", "enabled", "host", "port", "tls", "encryption", "username",
               "password", "topics", "channels", "extra_keys")
# parametri che richiedono di ricollegarsi al broker
CONNECT_KEYS = ("host", "port", "tls", "username", "password", "topics")
_BROKER_DEFAULTS = {"enabled": True, "tls": False, "encryption": False, "port": 1883,
                    "username": "", "password": "", "channels": [], "extra_keys": []}
_BROKER_ID_RE = re.compile(r"[a-z0-9-]{1,24}")
_CHANNEL_KEYS = ("name", "psk")


def _clean_topics(topics) -> list[str]:
    return [t for t in (normalize_topic(x) for x in topics) if t]


def default_broker(mqtt: dict | None = None) -> dict:
    """Il broker predefinito ricavato dal vecchio oggetto mqtt (fuso con i valori predefiniti)."""
    m = {**DEFAULTS["mqtt"], **{k: v for k, v in (mqtt or {}).items() if k in DEFAULTS["mqtt"]}}
    return {
        "id": DEFAULT_BROKER_ID,
        "name": DEFAULT_BROKER_NAME,
        "enabled": True,
        "host": m["host"],
        "port": m["port"],
        "tls": False,
        "encryption": True,
        "username": m["username"],
        "password": m["password"],
        # argomenti salvati da versioni precedenti senza "/#" (non ricevevano nulla)
        "topics": _clean_topics(m["topics"]) or list(DEFAULTS["mqtt"]["topics"]),
        "channels": [],
        "extra_keys": list(m["extra_keys"]),
    }


def find_broker(settings: dict, broker_id: str) -> dict | None:
    return next((b for b in settings.get("mqtt_brokers", []) if b.get("id") == broker_id), None)


def enabled_brokers(settings: dict) -> list[dict]:
    return [b for b in settings.get("mqtt_brokers", []) if b.get("enabled")]


def mqtt_view(brokers: list[dict]) -> dict:
    """Vista di compatibilita' (vecchia chiave mqtt): i parametri del broker predefinito."""
    d = next((b for b in brokers if b.get("id") == DEFAULT_BROKER_ID), None) or default_broker()
    return {k: copy.deepcopy(d[k]) for k in DEFAULTS["mqtt"]}

_INT_KEYS = ("retention_messages_days", "retention_positions_days",
             "retention_telemetry_days", "storage_cap_mb")
# interi con intervallo ammesso (min, max)
_RANGE_KEYS = {"battery_alert_pct": (1, 99), "silent_alert_hours": (1, 168),
               "retention_packets_hours": (1, 168), "backup_retention_days": (0, 3650),
               "traceroute_auto_max_per_hour": (1, 30), "bot_min_interval_s": (15, 3600),
               "bot_max_per_hour": (1, 120), "bot_node_cooldown_s": (30, 86400),
               "retention_traceroutes_days": (1, 3650)}
_MQTT_STR = ("host", "username", "password")
_BOOL_KEYS = ("lan_access", "lan_https", "notify_toast", "notify_telegram",
              "notify_mine_status", "notify_new_node", "onboarding_done", "favorites_to_radio",
              "traceroute_auto_enabled", "bot_enabled", "webhook_enabled", "guest_enabled")
MAX_NOTIFY_KEYWORDS = 20
_CHAT_ID_RE = re.compile(r"-?[0-9]{1,20}")
_TELEGRAM_TOKEN_RE = re.compile(r"\d{5,12}:[A-Za-z0-9_-]{30,50}")


def normalize_topic(topic: str) -> str:
    """Un'iscrizione senza jolly ("msh/EU_868/IT") riceverebbe solo quell'argomento esatto,
    cioe' niente: si aggiunge "/#" per ricevere tutto cio' che sta sotto."""
    t = topic.strip()
    if not t or t.endswith("#") or "+" in t:
        return t
    return t.rstrip("/") + "/#"


DEFAULTS["mqtt_brokers"] = [default_broker()]


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


NO_CRYPTO_PSK = "AA=="  # nessuna cifratura; "" resta solo "chiave persa dopo un errore di decifratura"


def strict_psk(psk) -> bytes:
    """Chiave effettiva di una PSK base64 rigorosa (niente caratteri estranei ignorati)."""
    if not isinstance(psk, str):
        raise ValueError("deve essere una stringa base64")
    try:
        base64.b64decode(psk, validate=True)
    except ValueError:
        raise ValueError("base64 non valido") from None
    return expand_psk(psk)


def _validate_channels(name: str, channels) -> None:
    if not isinstance(channels, list):
        raise ValueError(f"Broker {name}: channels deve essere una lista")
    if len(channels) > MAX_BROKER_CHANNELS:
        raise ValueError(f"Broker {name}: al massimo {MAX_BROKER_CHANNELS} canali")
    seen = set()
    for ch in channels:
        if not isinstance(ch, dict):
            raise ValueError(f"Broker {name}: ogni canale deve essere un oggetto")
        unknown = set(ch) - set(_CHANNEL_KEYS)
        if unknown:
            raise ValueError(f"Broker {name}: impostazione del canale sconosciuta: "
                             f"{sorted(unknown)[0]}")
        if isinstance(ch.get("name"), str):
            ch["name"] = ch["name"].strip()
        if isinstance(ch.get("psk"), str):
            ch["psk"] = ch["psk"].strip()  # "" resta: chiave persa, mai "nessuna cifratura"
        cname = ch.get("name")
        if not (isinstance(cname, str)
                and 1 <= len(cname.encode("utf-8")) <= MAX_CHANNEL_NAME_BYTES):
            raise ValueError(f"Canale {cname}: il nome deve avere da 1 a "
                             f"{MAX_CHANNEL_NAME_BYTES} caratteri")
        if any(c in cname for c in "/#+"):
            raise ValueError(f"Canale {cname}: il nome non può contenere / # +")
        if cname in seen:
            raise ValueError(f"Canale {cname}: nome già usato in questo broker")
        seen.add(cname)
        psk = ch.get("psk")
        try:
            strict_psk(psk)
        except ValueError as e:
            raise ValueError(f"Canale {cname}: chiave PSK non valida ({e})") from e


def merge_channels(broker: dict, entries: list[dict]) -> tuple[list[str], list[dict]]:
    """Aggiunge in coda al broker i canali nuovi (modifica `broker`). Restituisce i nomi
    aggiunti e i saltati con il motivo."""
    from .crypto import DEFAULT_KEY
    from .mqtt_publish import PRESET_CHANNELS  # import locale: mqtt_publish importa settings
    channels = broker.setdefault("channels", [])
    added: list[str] = []
    skipped: list[dict] = []
    for e in entries:
        name, psk = e.get("name"), e.get("psk")
        if isinstance(name, str):
            name = name.strip()
        if isinstance(psk, str):
            psk = psk.strip() or NO_CRYPTO_PSK
        reason = None
        key = None
        if (not isinstance(name, str) or not 1 <= len(name.encode("utf-8")) <= MAX_CHANNEL_NAME_BYTES
                or any(c in name for c in "/#+")):
            reason = "nome non valido" if (
                isinstance(name, str) and (not name or any(c in name for c in "/#+"))
                or not isinstance(name, str)) else "nome troppo lungo"
        else:
            try:
                key = strict_psk(psk)
            except ValueError:
                key = None
            if key is None:
                reason = "chiave non valida"
            elif any(c["name"] == name for c in channels):
                reason = "già presente"
            elif name in PRESET_CHANNELS and key == DEFAULT_KEY:
                reason = "canale pubblico predefinito"
            elif len(channels) >= MAX_BROKER_CHANNELS:
                reason = f"limite di {MAX_BROKER_CHANNELS} canali"
        if reason:
            skipped.append({"name": name if isinstance(name, str) else "", "reason": reason})
            continue
        channels.append({"name": name, "psk": base64.b64encode(base64.b64decode(psk)).decode()})
        added.append(name)
    return added, skipped


def _validate_broker(b) -> None:
    if not isinstance(b, dict):
        raise ValueError("Ogni broker deve essere un oggetto")
    unknown = set(b) - set(BROKER_KEYS)
    if unknown:
        raise ValueError(f"Impostazione del broker sconosciuta: {sorted(unknown)[0]}")
    name = b.get("name")
    if not (isinstance(name, str) and 1 <= len(name.strip()) <= MAX_BROKER_NAME):
        raise ValueError(f"Il nome del broker deve avere da 1 a {MAX_BROKER_NAME} caratteri")
    b["name"] = name = name.strip()
    for k, v in _BROKER_DEFAULTS.items():
        if b.get(k) is None:
            b[k] = copy.deepcopy(v)
    for k in ("enabled", "tls", "encryption"):
        if not isinstance(b[k], bool):
            raise ValueError(f"Broker {name}: {k} deve essere vero o falso")
    for k in ("username", "password"):
        if not isinstance(b[k], str):
            raise ValueError(f"Broker {name}: {k} deve essere una stringa")
    host = b.get("host")
    if not isinstance(host, str) or not host.strip():
        raise ValueError(f"Broker {name}: host vuoto")
    b["host"] = host.strip()
    if not (_is_int(b["port"]) and 1 <= b["port"] <= 65535):
        raise ValueError(f"Broker {name}: porta non valida")
    topics = b.get("topics")
    if isinstance(topics, list) and all(isinstance(t, str) for t in topics):
        b["topics"] = _clean_topics(topics)
    if not (isinstance(b.get("topics"), list) and b["topics"]):
        raise ValueError(f"Broker {name}: indica almeno un topic")
    _validate_channels(name, b["channels"])
    keys = b["extra_keys"]
    if not (isinstance(keys, list) and all(isinstance(k, str) for k in keys)):
        raise ValueError(f"Broker {name}: extra_keys deve essere una lista di stringhe")
    for key in keys:
        try:
            expand_psk(key)
        except ValueError as e:
            raise ValueError(f"Broker {name}: chiave PSK non valida ({e})") from e


def _validate_brokers(value) -> None:
    """Valida la lista dei broker completandone le voci (modifica la lista sul posto)."""
    if not isinstance(value, list):
        raise ValueError("mqtt_brokers deve essere una lista")
    if len(value) > MAX_BROKERS:
        raise ValueError(f"Al massimo {MAX_BROKERS} broker")
    for b in value:
        _validate_broker(b)
    ids: set[str] = set()
    for b in value:
        bid = b.get("id")
        if bid in (None, ""):
            bid = "b" + secrets.token_hex(3)
            while bid in ids or any(x.get("id") == bid for x in value):
                bid = "b" + secrets.token_hex(3)
            b["id"] = bid
        if not (isinstance(bid, str) and _BROKER_ID_RE.fullmatch(bid)):
            raise ValueError(f"Broker {b['name']}: id non valido")
        if bid in ids:
            raise ValueError(f"Broker {b['name']}: id già usato da un altro broker")
        ids.add(bid)
    if DEFAULT_BROKER_ID not in ids:
        raise ValueError("Il broker predefinito non si può eliminare: puoi disattivarlo")
    for i, b in enumerate(value):
        value[i] = {k: b[k] for k in BROKER_KEYS}


_NODE_ID_RE = re.compile(r"![0-9a-fA-F]{8}")
_VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.-]+)?")
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
# testi costanti (non f-string): il test del catalogo li trova e ne controlla la traduzione
_QUICK_REPLIES_ERR = ("quick_replies deve essere una lista di al massimo 20 testi (da 1 a 200 "
                      "byte, senza caratteri di controllo né doppioni)")
_BOT_TARGETS_ERR = ("bot_targets deve essere una lista di al massimo 16 bersagli radio o MQTT "
                    "validi, senza doppioni")
_BOT_REPLIES_ERR = ("bot_replies deve essere una lista di al massimo 20 risposte (parola da 2 a "
                    "32 caratteri, testo da 1 a 200 byte, parole diverse)")
_WEBHOOK_URL_ERR = "webhook_url deve essere un URL https (http solo verso questo PC)"


def _short_text(t, max_bytes: int) -> bool:
    """Testo senza spazi agli estremi, da 1 a max_bytes byte UTF-8, senza caratteri di controllo."""
    return (isinstance(t, str) and t == t.strip() and 1 <= len(t.encode("utf-8")) <= max_bytes
            and not any(ord(c) < 32 for c in t))


def _validate_quick_replies(value) -> None:
    if not (isinstance(value, list) and len(value) <= MAX_QUICK_REPLIES
            and all(_short_text(t, QUICK_REPLY_MAX_BYTES) for t in value)
            and len(set(value)) == len(value)):
        raise ValueError(_QUICK_REPLIES_ERR)


def _bot_target(t) -> dict:
    """Bersaglio del bot normalizzato alle sole chiavi del suo tipo (ValueError se non valido)."""
    if not isinstance(t, dict):
        raise ValueError(_BOT_TARGETS_ERR)
    if t.get("kind") == "radio":
        rid, idx = t.get("radio_id"), t.get("channel_index")
        if (set(t) == {"kind", "radio_id", "channel_index"} and isinstance(rid, str)
                and 1 <= len(rid) <= 64 and _is_int(idx) and 0 <= idx <= 7):
            return {"kind": "radio", "radio_id": rid, "channel_index": idx}
    elif t.get("kind") == "mqtt":
        broker, ch = t.get("broker"), t.get("channel")
        if (set(t) == {"kind", "broker", "channel"} and isinstance(broker, str)
                and _BROKER_ID_RE.fullmatch(broker) and isinstance(ch, str)
                and 1 <= len(ch.encode("utf-8")) <= MAX_CHANNEL_NAME_BYTES
                and not any(c in ch for c in "/#+")):
            return {"kind": "mqtt", "broker": broker, "channel": ch}
    raise ValueError(_BOT_TARGETS_ERR)


def _validate_bot_targets(value) -> None:
    if not (isinstance(value, list) and len(value) <= MAX_BOT_TARGETS):
        raise ValueError(_BOT_TARGETS_ERR)
    seen = set()
    for i, t in enumerate(value):
        value[i] = norm = _bot_target(t)
        key = tuple(norm.values())
        if key in seen:
            raise ValueError(_BOT_TARGETS_ERR)
        seen.add(key)


def _validate_bot_replies(value) -> None:
    if not (isinstance(value, list) and len(value) <= MAX_BOT_REPLIES):
        raise ValueError(_BOT_REPLIES_ERR)
    seen = set()
    for r in value:
        if not (isinstance(r, dict) and set(r) == {"trigger", "text"}):
            raise ValueError(_BOT_REPLIES_ERR)
        trig = r["trigger"]
        if not (isinstance(trig, str) and 2 <= len(trig) <= 32 and trig == trig.strip()
                and _short_text(r["text"], 200)):
            raise ValueError(_BOT_REPLIES_ERR)
        if trig.casefold() in seen:
            raise ValueError(_BOT_REPLIES_ERR)
        seen.add(trig.casefold())


def _validate_webhook_url(value) -> None:
    if not isinstance(value, str):
        raise ValueError(_WEBHOOK_URL_ERR)
    if value in ("", MASK):
        return
    try:
        u = urlsplit(value)
        host = u.hostname
    except ValueError:
        raise ValueError(_WEBHOOK_URL_ERR) from None
    ok = (len(value) <= 2048 and "#" not in value and host
          and (u.scheme == "https" or (u.scheme == "http" and host in _LOOPBACK_HOSTS)))
    if not ok:
        raise ValueError(_WEBHOOK_URL_ERR)


def _unique_subset(value, allowed: tuple) -> bool:
    return (isinstance(value, list) and all(isinstance(x, str) and x in allowed for x in value)
            and len(set(value)) == len(value))


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
    elif key in _BOOL_KEYS:
        if not isinstance(value, bool):
            raise ValueError(f"{key} deve essere vero o falso")
    elif key == "map_mode":
        if value not in ("auto", "online", "offline"):
            raise ValueError("map_mode deve essere auto, online oppure offline")
    elif key == "packet_log_mode":
        if value not in ("off", "archived", "all"):
            raise ValueError("packet_log_mode deve essere off, archived oppure all")
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
            raise ValueError(f"{key} deve essere una stringa")
    elif key == "telegram_token":
        if not (isinstance(value, str) and (value in ("", MASK) or _TELEGRAM_TOKEN_RE.fullmatch(value))):
            raise ValueError("telegram_token non ha il formato di un token di BotFather")
    elif key == "telegram_chat_id":
        if not (isinstance(value, str) and (value == "" or _CHAT_ID_RE.fullmatch(value))):
            raise ValueError("telegram_chat_id deve essere vuoto oppure un numero intero")
    elif key == "notify_keywords":
        if not (isinstance(value, list) and len(value) <= MAX_NOTIFY_KEYWORDS and all(
                isinstance(w, str) and 2 <= len(w) <= 32 and w == w.strip() for w in value)):
            raise ValueError(f"notify_keywords deve essere una lista di al massimo "
                             f"{MAX_NOTIFY_KEYWORDS} parole (da 2 a 32 caratteri, senza spazi "
                             f"agli estremi)")
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
    elif key == "mqtt_brokers":
        _validate_brokers(value)
    elif key == "mqtt_send_confirmed_brokers":
        if not (isinstance(value, list) and all(
                isinstance(x, str) and _BROKER_ID_RE.fullmatch(x) for x in value)):
            raise ValueError("mqtt_send_confirmed_brokers deve essere una lista di id di broker")
    elif key == "quick_replies":
        _validate_quick_replies(value)
    elif key == "bot_targets":
        _validate_bot_targets(value)
    elif key == "bot_commands":
        if not _unique_subset(value, BOT_COMMANDS):
            raise ValueError("bot_commands deve contenere solo comandi tra ping, info, nodes, "
                             "time, weather, senza doppioni")
    elif key == "bot_weather_node":
        if not (isinstance(value, str) and (value == "" or _NODE_ID_RE.fullmatch(value))):
            raise ValueError("bot_weather_node deve essere vuoto oppure nel formato !xxxxxxxx")
    elif key == "bot_replies":
        _validate_bot_replies(value)
    elif key == "webhook_url":
        _validate_webhook_url(value)
    elif key == "webhook_events":
        if not _unique_subset(value, WEBHOOK_EVENTS):
            raise ValueError("webhook_events deve contenere solo eventi tra message, alert, "
                             "sensor, traceroute, node_new, senza doppioni")
    elif key == "update_channel":
        if value not in ("stable", "beta"):
            raise ValueError("update_channel deve essere stable oppure beta")
    elif key == "last_seen_version":
        if not (isinstance(value, str) and (value == "" or (
                len(value) <= 32 and _VERSION_RE.fullmatch(value)))):
            raise ValueError("last_seen_version deve essere vuoto oppure un numero di versione")
    elif key == "retention_broker_days":
        if not (isinstance(value, dict) and len(value) <= MAX_BROKERS and all(
                isinstance(k, str) and _BROKER_ID_RE.fullmatch(k) and _is_int(v)
                and 1 <= v <= 3650 for k, v in value.items())):
            raise ValueError("retention_broker_days deve associare a ogni id di broker un "
                             "numero di giorni tra 1 e 3650")


_DECRYPT_CACHE: dict = {}  # (protector, valore salvato) -> chiaro, oppure None se non decifrabile
_DECRYPT_CACHE_MAX = 256


def _decrypt_cached(key: str, stored: str) -> str:
    """Ogni valore salvato si decifra una volta sola: un valore non decifrabile avvisa una volta."""
    protector = get_protector()
    ck = (id(protector), stored)
    if ck in _DECRYPT_CACHE:
        plain = _DECRYPT_CACHE[ck]
    else:
        try:
            plain = protector.unprotect(stored)
        except SecretError:
            log.warning("Impossibile decifrare %s: reimpostalo", key)
            plain = None
        if len(_DECRYPT_CACHE) >= _DECRYPT_CACHE_MAX:
            _DECRYPT_CACHE.pop(next(iter(_DECRYPT_CACHE)))
        _DECRYPT_CACHE[ck] = plain
    return "" if plain is None else plain


def _map_broker_secrets(brokers: list, fn) -> list:
    """Copia dei broker con fn(etichetta, valore) applicata a password, PSK e chiavi extra
    non vuote."""
    out = copy.deepcopy(brokers)
    for b in out:
        if not isinstance(b, dict):
            continue
        label = f"mqtt_brokers.{b.get('id')}"
        if isinstance(b.get("password"), str) and b["password"]:
            b["password"] = fn(f"{label}.password", b["password"])
        for ch in b.get("channels") or []:
            if isinstance(ch, dict) and isinstance(ch.get("psk"), str) and ch["psk"]:
                ch["psk"] = fn(f"{label}.channels.{ch.get('name')}", ch["psk"])
        b["extra_keys"] = [fn(f"{label}.extra_keys", k) if isinstance(k, str) and k else k
                           for k in b.get("extra_keys") or []]
    return out


def _protect_brokers(brokers: list) -> list:
    protector = get_protector()
    try:
        return _map_broker_secrets(brokers, lambda _label, v: protector.protect(v))
    except SecretError as e:
        raise ValueError(f"Impossibile cifrare mqtt_brokers: {e}") from e


def load_settings(conn: sqlite3.Connection) -> dict:
    """Default sovrascritti dai valori salvati."""
    result = copy.deepcopy(DEFAULTS)
    legacy_mqtt = None
    brokers = None
    for row in conn.execute("SELECT key, value FROM settings"):
        if row["key"] not in DEFAULTS:
            continue
        value = json.loads(row["value"])
        if row["key"] in SECRET_KEYS and isinstance(value, str) and value:
            value = _decrypt_cached(row["key"], value)
        if row["key"] == "mqtt":
            legacy_mqtt = value
        elif row["key"] == "mqtt_brokers":
            brokers = _map_broker_secrets(value, _decrypt_cached)
        else:
            result[row["key"]] = value
    if brokers is None:  # database di una versione con un solo broker, non ancora migrato
        brokers = [default_broker(legacy_mqtt)]
    result["mqtt_brokers"] = brokers
    result["mqtt"] = mqtt_view(brokers)
    return result


def save_settings(conn: sqlite3.Connection, changes: dict) -> dict:
    """Valida e salva le modifiche. Con mqtt_brokers la vecchia chiave mqtt e' ignorata;
    con la sola mqtt si aggiorna il broker predefinito."""
    changes = dict(changes)
    if "mqtt_brokers" in changes:
        changes.pop("mqtt", None)
    for key, value in changes.items():
        _validate(key, value)
    current = load_settings(conn)
    if "mqtt" in changes:
        brokers = copy.deepcopy(current["mqtt_brokers"])
        d = next(b for b in brokers if b["id"] == DEFAULT_BROKER_ID)
        d.update(changes.pop("mqtt"))
        # come le versioni con un solo broker: senza argomenti valgono quelli predefiniti
        d["topics"] = _clean_topics(d["topics"]) or list(DEFAULTS["mqtt"]["topics"])
        _validate_brokers(brokers)
        changes["mqtt_brokers"] = brokers
    stored = {}
    for key, value in changes.items():  # prima si cifra tutto: un errore non salva nulla
        if key == "mqtt_brokers":
            value = _protect_brokers(value)
        elif key in SECRET_KEYS and isinstance(value, str) and value:
            try:
                value = get_protector().protect(value)
            except SecretError as e:
                raise ValueError(f"Impossibile cifrare {key}: {e}") from e
        stored[key] = value
    for key, value in stored.items():
        conn.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, json.dumps(value)))
    if "mqtt_brokers" in stored:
        conn.execute("DELETE FROM settings WHERE key='mqtt'")
    conn.commit()
    return load_settings(conn)


def migrate_brokers(conn: sqlite3.Connection) -> bool:
    """Database di una versione con un solo broker: scrive mqtt_brokers dal vecchio mqtt
    (il broker predefinito, con Crittografia accesa) e toglie la vecchia riga."""
    if conn.execute("SELECT 1 FROM settings WHERE key='mqtt_brokers'").fetchone():
        return False
    row = conn.execute("SELECT value FROM settings WHERE key='mqtt'").fetchone()
    if row is None:
        return False  # installazione nuova: valgono i predefiniti
    try:
        brokers = _protect_brokers([default_broker(json.loads(row["value"]))])
    except ValueError as e:
        log.warning("Migrazione dei broker MQTT rimandata: %s", e)
        return False
    conn.execute("INSERT INTO settings(key, value) VALUES('mqtt_brokers', ?)",
                 (json.dumps(brokers),))
    conn.execute("DELETE FROM settings WHERE key='mqtt'")
    conn.commit()
    return True


def migrate_secrets(conn: sqlite3.Connection) -> int:
    """Riscrive cifrati i segreti ancora salvati in chiaro (database delle versioni precedenti)."""
    protector = get_protector()
    n = 0
    row = conn.execute("SELECT value FROM settings WHERE key='mqtt_brokers'").fetchone()
    if row is not None:
        plain = []

        def protect_plain(label, v):
            if protector.is_protected(v):
                return v
            plain.append(label)
            return protector.protect(v)
        try:
            brokers = _map_broker_secrets(json.loads(row["value"]), protect_plain)
        except SecretError as e:
            log.warning("Impossibile cifrare mqtt_brokers, resta in chiaro: %s", e)
        else:
            if plain:
                conn.execute("UPDATE settings SET value=? WHERE key='mqtt_brokers'",
                             (json.dumps(brokers),))
                n += 1
    for key in SECRET_KEYS:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            continue
        value = json.loads(row["value"])
        if isinstance(value, str) and value and not protector.is_protected(value):
            try:
                stored = protector.protect(value)
            except SecretError as e:
                log.warning("Impossibile cifrare %s, resta in chiaro: %s", key, e)
                continue
            conn.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(stored), key))
            n += 1
    if n:
        conn.commit()
    return n


def mask_secrets(s: dict) -> dict:
    """Copia senza segreti in chiaro: password MQTT, token (SECRET_KEYS), chiavi PSK extra,
    PSK dei canali dei broker."""
    out = copy.deepcopy(s)
    mqtt = out.get("mqtt")
    if isinstance(mqtt, dict):
        if mqtt.get("password"):
            mqtt["password"] = MASK
        mqtt["extra_keys"] = [MASK for _ in mqtt.get("extra_keys", [])]
    if isinstance(out.get("mqtt_brokers"), list):
        out["mqtt_brokers"] = _map_broker_secrets(out["mqtt_brokers"], lambda _label, _v: MASK)
    for key in SECRET_KEYS:
        if out.get(key):
            out[key] = MASK
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


def prepare_import(data: dict, current: dict | None = None) -> tuple[dict, list[str]]:
    """Da un documento esportato ricava le modifiche da salvare e le chiavi scartate.
    I segreti mascherati dei broker si risolvono contro le impostazioni attuali (current)."""
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
    if "mqtt_send_confirmed_brokers" in changes:
        del changes["mqtt_send_confirmed_brokers"]
        skipped.append("mqtt_send_confirmed_brokers")
    for key in LOCAL_ONLY_KEYS:  # mai invii automatici o accesso ospite da un file importato
        if key in changes:
            del changes[key]
            skipped.append(key)
    for key in SECRET_KEYS:
        if changes.get(key) == MASK:
            del changes[key]
            skipped.append(key)
    if "mqtt_brokers" in changes:
        changes.pop("mqtt", None)  # vista di compatibilita': vale la lista dei broker
        if isinstance(changes["mqtt_brokers"], list):
            existing = (current or {}).get("mqtt_brokers") or []
            changes["mqtt_brokers"] = _resolve_brokers(changes["mqtt_brokers"], existing,
                                                       skipped)
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
            raise ValueError(_NO_MATCH)
    return out


_NO_MATCH = "Chiave mascherata senza corrispondenza: reinseriscila"


def _mask_ref(value, position: int) -> int | None:
    """Indice della voce salvata a cui rimanda un valore mascherato ("••••" = stessa
    posizione, "••••#n" = n-esima); None se il valore non e' mascherato."""
    if value == MASK:
        return position
    if isinstance(value, str) and (m := _MASK_REF.match(value)):
        return int(m.group(1))
    return None


def _resolve_brokers(new, existing: list, skipped: list[str] | None) -> list:
    """Sostituisce i segreti mascherati con quelli salvati del broker con lo stesso id.
    skipped None: un valore senza corrispondenza solleva ValueError; altrimenti la password
    diventa "", il canale e la chiave extra si scartano e finiscono in skipped."""
    out = copy.deepcopy(new)
    by_id = {b.get("id"): b for b in existing if isinstance(b, dict)}
    for nb in out:
        if not isinstance(nb, dict):
            continue
        bid = nb.get("id")
        ob = by_id.get(bid) if isinstance(bid, str) and bid else None

        def missing(what: str) -> None:
            if skipped is None:
                raise ValueError(_NO_MATCH)
            skipped.append(f"mqtt_brokers.{bid}.{what}")

        if _mask_ref(nb.get("password"), 0) is not None:
            if ob is not None:
                nb["password"] = ob.get("password", "")
            else:
                missing("password")
                nb["password"] = ""
        if isinstance(nb.get("channels"), list):
            saved = (ob or {}).get("channels") or []
            channels = []
            for ch in nb["channels"]:
                if isinstance(ch, dict) and ch.get("psk") == MASK:
                    match = next((c for c in saved if c.get("name") == ch.get("name")), None)
                    psk = None if match is None else match.get("psk")
                elif isinstance(ch, dict) and (ref := _mask_ref(ch.get("psk"), -1)) is not None:
                    psk = saved[ref].get("psk") if ref < len(saved) else None
                else:
                    channels.append(ch)
                    continue
                if psk is None:
                    missing(f"channels.{ch.get('name')}")
                else:
                    channels.append({**ch, "psk": psk})
            nb["channels"] = channels
        if isinstance(nb.get("extra_keys"), list):
            saved_keys = (ob or {}).get("extra_keys") or []
            keys, lost = [], False
            for i, k in enumerate(nb["extra_keys"]):
                ref = _mask_ref(k, i)
                if ref is None:
                    keys.append(k)
                elif ref < len(saved_keys):
                    keys.append(saved_keys[ref])
                else:
                    lost = True
            if lost:
                missing("extra_keys")
            nb["extra_keys"] = keys
    return out


def resolve_broker_secrets(new: list, existing: list) -> list:
    """Per PUT /api/settings: i segreti mascherati tornano quelli salvati (stesso id di broker;
    PSK per nome del canale con "••••" o per posizione con "••••#n"). Un valore mascherato
    senza corrispondenza solleva ValueError."""
    if not isinstance(new, list):
        return new
    return _resolve_brokers(new, existing, None)


def scrub_text(text: str, *secrets) -> str:
    """Sostituisce con MASK i segreti dati. Sotto i 4 caratteri solo come parola intera
    (evita di rovinare il testo); da 4 in su come sottostringa."""
    for secret in secrets:
        if not secret or not isinstance(secret, str):
            continue
        if len(secret) >= 4:
            text = text.replace(secret, MASK)
        else:
            text = re.sub(rf"(?<!\w){re.escape(secret)}(?!\w)", MASK, text)
    return text
