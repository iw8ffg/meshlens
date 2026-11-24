"""Modello della configurazione del nodo: dict, schema, validazione, diff, rischio, segreti.

Funzioni pure sui protobuf di Meshtastic (nessun I/O). I percorsi sono puntati:
"config.lora.hop_limit", "module_config.mqtt.enabled", "channels.1.name", "owner.long_name".
"""
import base64
import binascii
import copy

from google.protobuf.descriptor import FieldDescriptor as FD
from google.protobuf.json_format import MessageToDict
from meshtastic.protobuf import channel_pb2, localonly_pb2

from .crypto import DEFAULT_KEY

MASK = "••••"

CONFIG_SECTIONS = ("device", "position", "power", "network", "display", "lora", "bluetooth",
                   "security")
OWNER_FIELDS = {"long_name": "string", "short_name": "string", "is_licensed": "bool"}
# campi del canale appiattiti: nome -> (tipo, enum, segreto)
CHANNEL_FIELDS = ("role", "name", "psk", "position_precision", "uplink_enabled",
                  "downlink_enabled")
MAX_CHANNELS = 8

# segreti: (sezione, campo); le psk dei canali sono gestite a parte
_SECRET_FIELDS = {("config", "security", "private_key"), ("config", "network", "wifi_psk"),
                  ("module_config", "mqtt", "password"), ("config", "bluetooth", "fixed_pin")}

_LORA_RISKY = {"region", "modem_preset", "use_preset", "bandwidth", "spread_factor",
               "coding_rate", "channel_num", "override_frequency", "tx_enabled",
               "frequency_offset"}
_NET_KINDS = ("net", "tcp", "wifi")

_TYPES = {
    FD.CPPTYPE_BOOL: "bool", FD.CPPTYPE_STRING: "string", FD.CPPTYPE_ENUM: "enum",
    FD.CPPTYPE_FLOAT: "float", FD.CPPTYPE_DOUBLE: "float",
    FD.CPPTYPE_INT32: "int", FD.CPPTYPE_INT64: "int", FD.CPPTYPE_UINT32: "int",
    FD.CPPTYPE_UINT64: "int",
}
_BITS = {FD.CPPTYPE_INT32: (-2**31, 2**31 - 1), FD.CPPTYPE_UINT32: (0, 2**32 - 1),
         FD.CPPTYPE_INT64: (-2**63, 2**63 - 1), FD.CPPTYPE_UINT64: (0, 2**64 - 1)}


def _to_dict(msg) -> dict:
    return MessageToDict(msg, preserving_proto_field_name=True,
                         always_print_fields_with_no_presence=True)


def _field_type(f) -> str:
    if f.type == FD.TYPE_BYTES:
        return "bytes"
    return _TYPES.get(f.cpp_type, "message")


def _describe(f, secret: bool = False) -> dict | None:
    """Descrive un campo per lo schema; None se è un messaggio annidato (non modificabile)."""
    t = _field_type(f)
    if t == "message":
        return None
    out: dict = {"type": "repeated" if f.is_repeated else t}
    if f.is_repeated:
        out["item"] = t
    if t == "enum":
        out["enum"] = [v.name for v in f.enum_type.values]
    if t == "int":
        out["min"], out["max"] = _BITS[f.cpp_type]
    if secret:
        out["secret"] = True
    return out


def _msg_schema(desc, prefix: tuple) -> dict:
    out = {}
    for f in desc.fields:
        d = _describe(f, prefix + (f.name,) in _SECRET_FIELDS)
        if d is not None:
            out[f.name] = d
    return out


def schema() -> dict:
    """Schema dei campi modificabili, ricavato dai descrittori protobuf."""
    cfg_desc = localonly_pb2.LocalConfig.DESCRIPTOR
    mod_desc = localonly_pb2.LocalModuleConfig.DESCRIPTOR
    config = {n: _msg_schema(cfg_desc.fields_by_name[n].message_type, ("config", n))
              for n in CONFIG_SECTIONS}
    module = {f.name: _msg_schema(f.message_type, ("module_config", f.name))
              for f in mod_desc.fields if f.message_type is not None}
    chan_desc = channel_pb2.Channel.DESCRIPTOR
    channel = {
        "role": {"type": "enum", "enum": [v.name for v in chan_desc.fields_by_name["role"]
                                          .enum_type.values]},
        "name": {"type": "string"},
        "psk": {"type": "bytes", "secret": True},
        "position_precision": {"type": "int", "min": 0, "max": 2**32 - 1},
        "uplink_enabled": {"type": "bool"},
        "downlink_enabled": {"type": "bool"},
    }
    return {"config": config, "module_config": module, "channel": channel,
            "owner": {k: {"type": v} for k, v in OWNER_FIELDS.items()}}


# --- tipo di chiave dei canali ---

KEY_KINDS = ("none", "default", "custom")


def psk_kind(psk: bytes) -> str:
    """"none" (nessuna cifratura), "default" (chiave pubblica nota e varianti), "custom".

    Non rivela nulla della chiave: serve all'avviso "chiave debole".
    """
    psk = bytes(psk or b"")
    if psk in (b"", b"\x00"):
        return "none"
    if len(psk) == 1:
        return "default"  # 1..255: chiave predefinita e sue varianti "semplici"
    if psk == DEFAULT_KEY:
        return "default"
    return "custom"


# --- messaggi predefiniti (canned) ---

CANNED_SEP = "|"
CANNED_MAX_BYTES = 200


def split_canned(text: str) -> list[str]:
    """"a|b" -> ["a", "b"]; voci vuote tolte."""
    return [p for p in (text or "").split(CANNED_SEP) if p.strip()]


def join_canned(messages: list[str]) -> str:
    """Unisce i messaggi con "|" dopo averli validati (la libreria fa sys.exit oltre 200)."""
    if not isinstance(messages, list) or not all(isinstance(m, str) for m in messages):
        raise ValueError("Serve almeno un messaggio")
    if not messages:
        raise ValueError("Serve almeno un messaggio")
    items = [m.strip() for m in messages]
    if any(not m for m in items):
        raise ValueError("I messaggi non possono essere vuoti")
    if any(CANNED_SEP in m for m in items):
        raise ValueError("I messaggi non possono contenere il carattere |")
    if any(ord(c) < 32 for m in items for c in m):
        raise ValueError("I messaggi non possono contenere caratteri di controllo")
    text = CANNED_SEP.join(items)
    n = len(text.encode("utf-8"))
    if n > CANNED_MAX_BYTES:
        raise ValueError(f"Troppo lunghi: {n} byte su 200 (separatori compresi)")
    return text


# --- costruzione del dict di configurazione ---

def channel_to_dict(ch, mask: bool = True) -> dict:
    psk = ch.settings.psk
    return {
        "index": ch.index,
        "role": channel_pb2.Channel.Role.Name(ch.role),
        "name": ch.settings.name,
        "psk": MASK if mask else base64.b64encode(psk).decode(),
        # calcolato prima della maschera; additivo, non modificabile (non e' in CHANNEL_FIELDS)
        "key_kind": psk_kind(psk),
        "position_precision": ch.settings.module_settings.position_precision,
        "uplink_enabled": ch.settings.uplink_enabled,
        "downlink_enabled": ch.settings.downlink_enabled,
    }


def node_to_dict(local_config, module_config, channels, owner: dict, mask: bool = True) -> dict:
    """Config del contratto. Con mask=False i segreti restano in chiaro (solo per le copie)."""
    config = {n: _to_dict(getattr(local_config, n)) for n in CONFIG_SECTIONS}
    mod_desc = localonly_pb2.LocalModuleConfig.DESCRIPTOR
    module = {f.name: _to_dict(getattr(module_config, f.name))
              for f in mod_desc.fields if f.message_type is not None}
    out = {
        "owner": {"long_name": owner.get("long_name", ""),
                  "short_name": owner.get("short_name", ""),
                  "is_licensed": bool(owner.get("is_licensed", False))},
        "config": config, "module_config": module,
        "channels": [channel_to_dict(c, mask=mask) for c in channels],
    }
    return mask_config(out) if mask else out


def mask_config(cfg: dict) -> dict:
    """Copia di un Config con tutti i segreti mascherati."""
    out = copy.deepcopy(cfg)
    for kind, section, field in _SECRET_FIELDS:
        if field in out.get(kind, {}).get(section, {}):
            out[kind][section][field] = MASK
    for ch in out.get("channels", []):
        ch["psk"] = MASK
    return out


# --- validazione dei cambi ---

def _split(path: str):
    """Restituisce (kind, section, field) o solleva ValueError."""
    parts = path.split(".")
    if parts[0] == "owner" and len(parts) == 2:
        return "owner", None, parts[1]
    if parts[0] in ("config", "module_config") and len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if parts[0] == "channels" and len(parts) == 3:
        try:
            idx = int(parts[1])
        except ValueError:
            raise ValueError(f"Indice di canale non valido: {parts[1]}") from None
        if not 0 <= idx < MAX_CHANNELS:
            raise ValueError(f"Indice di canale fuori intervallo (0-{MAX_CHANNELS - 1}): {idx}")
        return "channels", idx, parts[2]
    raise ValueError(f"Percorso sconosciuto: {path}")


def _spec(sch: dict, kind: str, section, field: str, path: str) -> dict:
    if kind == "owner":
        spec = sch["owner"].get(field)
    elif kind == "channels":
        spec = sch["channel"].get(field)
    else:
        spec = sch[kind].get(section, {}).get(field)
    if spec is None:
        raise ValueError(f"Percorso sconosciuto: {path}")
    return spec


def _coerce_one(path: str, v, t: str, spec: dict):
    if t == "bool":
        if not isinstance(v, bool):
            raise ValueError(f"{path}: atteso vero/falso")
        return v
    if t == "int":
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"{path}: atteso un numero intero")
        if not spec["min"] <= v <= spec["max"]:
            raise ValueError(f"{path}: valore fuori intervallo ({spec['min']}..{spec['max']})")
        return v
    if t == "float":
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{path}: atteso un numero")
        return float(v)
    if t == "string":
        if not isinstance(v, str):
            raise ValueError(f"{path}: atteso un testo")
        return v
    if t == "enum":
        if not isinstance(v, str) or v not in spec["enum"]:
            raise ValueError(f"{path}: valore non valido, ammessi: {', '.join(spec['enum'])}")
        return v
    if t == "bytes":
        if not isinstance(v, str):
            raise ValueError(f"{path}: atteso un testo base64")
        try:
            return base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError(f"{path}: base64 non valido") from None
    raise ValueError(f"{path}: tipo non supportato")


def _is_secret(kind, section, field) -> bool:
    if kind == "channels":
        return field == "psk"
    return (kind, section, field) in _SECRET_FIELDS


def parse_changes(changes: dict, sch: dict | None = None) -> list[tuple[str, object]]:
    """Valida percorsi e tipi. Solleva ValueError con messaggio in italiano."""
    sch = sch or schema()
    out = []
    for path, raw in changes.items():
        kind, section, field = _split(path)
        spec = _spec(sch, kind, section, field, path)
        if raw == MASK and _is_secret(kind, section, field):
            out.append((path, MASK))
            continue
        if spec["type"] == "repeated":
            if not isinstance(raw, list):
                raise ValueError(f"{path}: atteso un elenco")
            val = [_coerce_one(path, x, spec["item"], spec) for x in raw]
        else:
            val = _coerce_one(path, raw, spec["type"], spec)
            if kind == "channels" and field == "psk" and len(val) not in (0, 1, 16, 32):
                raise ValueError(f"{path}: la chiave deve essere di 0, 1, 16 o 32 byte")
        out.append((path, val))
    return out


# --- diff e rischio ---

def _current(current: dict, kind, section, field):
    if kind == "owner":
        return current.get("owner", {}).get(field)
    if kind == "channels":
        for ch in current.get("channels", []):
            if ch.get("index") == section:
                return ch.get(field)
        return None
    return current.get(kind, {}).get(section, {}).get(field)


def _to_json(v):
    """Valore parsato -> valore del dict (bytes in base64)."""
    if isinstance(v, bytes):
        return base64.b64encode(v).decode()
    if isinstance(v, list):
        return [_to_json(x) for x in v]
    return v


def _risk(kind, section, field, new, context: dict) -> str | None:
    kind_radio = context.get("radio_kind")
    if kind == "config":
        if section == "lora" and field in _LORA_RISKY:
            return "Un parametro radio sbagliato può isolare il nodo dalla rete"
        if section == "security":
            return "Le chiavi di sicurezza sbagliate possono bloccare l'accesso al nodo"
        if (section == "bluetooth" and field == "enabled" and new is False
                and kind_radio == "ble" and context.get("is_local")):
            return "Disattivare il Bluetooth su una radio collegata via Bluetooth la scollega"
        if section == "device" and field == "role" and new == "REPEATER":
            return "Il ruolo REPEATER nasconde il nodo e cambia il comportamento della rete"
        if (section == "network" and kind_radio in _NET_KINDS and context.get("is_local")):
            return "Cambiare la rete su una radio collegata via rete può scollegarla"
        if section == "power" and field == "is_power_saving":
            return "Il risparmio energetico può spegnere USB e Bluetooth tra un pacchetto e l'altro"
        if section == "lora" and field == "ignore_incoming":
            return "La radio scarterà ogni pacchetto dei nodi in elenco"
        if section == "lora" and field == "serial_hal_only":
            return "Con questa opzione la radio può smettere di trasmettere via LoRa"
    if (kind == "module_config" and section == "serial"
            and field == "override_console_serial_port"):
        return "Cedere la console seriale al modulo seriale può scollegare la radio via USB"
    if kind == "channels" and section == 0:
        return "Modificare il canale 0 può isolare il nodo dagli altri"
    return None


def diff(current: dict, changes: list[tuple[str, object]], context: dict) -> list[dict]:
    """Differenze rispetto al Config attuale. Ignora valori uguali e mascherati."""
    out = []
    for path, new in changes:
        kind, section, field = _split(path)
        if new == MASK and _is_secret(kind, section, field):
            continue
        old = _current(current, kind, section, field)
        new_json = _to_json(new)
        secret = _is_secret(kind, section, field)
        if not secret:
            same = old == new_json
            if not same and isinstance(new, int) and not isinstance(new, bool):
                try:
                    same = int(old) == new
                except (TypeError, ValueError):
                    same = False
            if not same and isinstance(new, float):
                try:
                    same = float(old) == new
                except (TypeError, ValueError):
                    same = False
            if same:
                continue
        reason = _risk(kind, section, field, new, context)
        out.append({"path": path,
                    "old": MASK if secret else old,
                    "new": MASK if secret else new_json,
                    "risky": reason is not None, "reason": reason})
    return out


# --- applicazione ai protobuf ---

def _set_attr(msg, field: str, value) -> None:
    f = msg.DESCRIPTOR.fields_by_name[field]
    if f.is_repeated:
        container = getattr(msg, field)
        del container[:]
        if f.type == FD.TYPE_ENUM:
            container.extend(f.enum_type.values_by_name[x].number for x in value)
        else:
            container.extend(value)
    elif f.cpp_type == FD.CPPTYPE_ENUM:
        setattr(msg, field, f.enum_type.values_by_name[value].number)
    else:
        setattr(msg, field, value)


def apply_to_protos(protos: dict, changes: list[tuple[str, object]]) -> dict:
    """Applica i cambi a copie dei protobuf.

    protos = {"config": LocalConfig, "module_config": LocalModuleConfig,
              "channels": [Channel], "owner": dict}. I segreti mascherati restano invariati.
    """
    out = {"config": copy.deepcopy(protos["config"]),
           "module_config": copy.deepcopy(protos["module_config"]),
           "channels": [copy.deepcopy(c) for c in protos.get("channels", [])],
           "owner": dict(protos.get("owner", {}))}
    for path, value in changes:
        kind, section, field = _split(path)
        if value == MASK and _is_secret(kind, section, field):
            continue
        if kind == "owner":
            out["owner"][field] = value
        elif kind == "channels":
            ch = next((c for c in out["channels"] if c.index == section), None)
            if ch is None:
                ch = channel_pb2.Channel(index=section)
                out["channels"].append(ch)
            if field == "role":
                ch.role = channel_pb2.Channel.Role.Value(value)
            elif field == "position_precision":
                ch.settings.module_settings.position_precision = value
            else:
                setattr(ch.settings, field, value)
        else:
            _set_attr(getattr(out[kind], section), field, value)
    return out


def touched_sections(changes: list[tuple[str, object]]) -> list[str]:
    """Sezioni toccate, nell'ordine di prima comparsa: ["config.lora", "channels.1", "owner"]."""
    seen: list[str] = []
    for path, _ in changes:
        kind, section, _f = _split(path)
        name = "owner" if kind == "owner" else f"{kind}.{section}"
        if name not in seen:
            seen.append(name)
    return seen
