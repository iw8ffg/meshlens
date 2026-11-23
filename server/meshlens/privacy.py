"""Privacy della posizione: canali pubblici o inoltrati a MQTT con posizione troppo precisa.

Funzioni pure sui protobuf della radio (mai restituiti: le voci non contengono chiavi).
"""
from meshtastic.protobuf import channel_pb2, config_pb2

from .channel_link import preset_name
from .config_model import psk_kind
from .coverage import precision_m

PRIVACY_MAX_BITS = 14  # 14 bit ~ 1,46 km: oltre (>= 15, ~730 m) e' "troppo precisa"
FIX_CHOICES = (0, 10, 11, 12, 13, 14)  # 0 = non inviare la posizione su quel canale
MSG_BAD_PRECISION = "Precisione non ammessa"
MSG_NOTHING_TO_FIX = "Nessun canale da correggere"


def _channel_name(ch, protos: dict) -> str:
    name = ch.settings.name
    if not name and ch.role == channel_pb2.Channel.PRIMARY:
        return preset_name(protos["config"].lora.modem_preset)
    return name


def position_risks(protos: dict, has_position: bool) -> list[dict]:
    """Rischi per la posizione della radio (protobuf come current_protos)."""
    if not has_position:
        return []
    mqtt = protos["module_config"].mqtt
    out = []
    for ch in sorted(protos.get("channels") or [], key=lambda c: c.index):
        if ch.role == channel_pb2.Channel.DISABLED:
            continue
        bits = ch.settings.module_settings.position_precision
        if bits < PRIVACY_MAX_BITS + 1:
            continue  # 0 = non inviata; <= 14 = abbastanza approssimata
        kind = psk_kind(ch.settings.psk)
        reasons = []
        if kind == "none":
            reasons.append("no_key")
        elif kind == "default":
            reasons.append("public_key")
        if mqtt.enabled and ch.settings.uplink_enabled:
            reasons.append("mqtt_uplink")
        if not reasons:
            continue
        out.append({"kind": "channel", "channel_index": ch.index,
                    "channel_name": _channel_name(ch, protos), "precision_bits": bits,
                    "precision_m": precision_m(bits), "reasons": reasons,
                    "suggested_bits": PRIVACY_MAX_BITS})
    map_bits = mqtt.map_report_settings.position_precision
    if mqtt.enabled and mqtt.map_reporting_enabled and map_bits > PRIVACY_MAX_BITS:
        out.append({"kind": "map_report", "precision_bits": map_bits,
                    "precision_m": precision_m(map_bits), "reasons": ["mqtt_map"],
                    "suggested_bits": None})
    return out


def has_position(protos: dict, live_node: dict | None) -> bool:
    """La radio ha una posizione da proteggere: fissa, GPS attivo o nota in memoria."""
    pos = protos["config"].position
    if pos.fixed_position or pos.gps_mode == config_pb2.Config.PositionConfig.ENABLED:
        return True
    node = live_node or {}
    return node.get("lat") is not None and node.get("lon") is not None


def fix_changes(risks: list[dict], bits: int, channels: list[int] | None = None) -> dict:
    """Cambi per l'anteprima che portano i canali a rischio alla precisione scelta."""
    if isinstance(bits, bool) or bits not in FIX_CHOICES:
        raise ValueError(MSG_BAD_PRECISION)
    wanted = None if channels is None else set(channels)
    out = {}
    for r in risks:
        if r.get("kind") != "channel":
            continue
        idx = r["channel_index"]
        if wanted is not None and idx not in wanted:
            continue
        out[f"channels.{idx}.position_precision"] = bits
    if not out:
        raise ValueError(MSG_NOTHING_TO_FIX)
    return out
