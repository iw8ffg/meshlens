"""Decodifica di tutte le varianti di Telemetry, condivisa da MQTT e radio."""
import math

from google.protobuf import json_format
from google.protobuf.descriptor import FieldDescriptor
from meshtastic.protobuf import telemetry_pb2

from .events import TelemetryData

# nome del campo oneof `variant` di Telemetry -> nome della variante salvata
VARIANTS = {
    "device_metrics": "device",
    "environment_metrics": "environment",
    "air_quality_metrics": "air_quality",
    "power_metrics": "power",
    "local_stats": "local_stats",
    "health_metrics": "health",
}

_NUMERIC = {
    FieldDescriptor.CPPTYPE_INT32, FieldDescriptor.CPPTYPE_INT64,
    FieldDescriptor.CPPTYPE_UINT32, FieldDescriptor.CPPTYPE_UINT64,
    FieldDescriptor.CPPTYPE_FLOAT, FieldDescriptor.CPPTYPE_DOUBLE,
}


class UnsupportedTelemetry(Exception):
    """Variante assente o non gestita."""


class EmptyTelemetry(Exception):
    """Variante gestita ma senza valori numerici finiti."""


def _opt(msg, field: str):
    """Valore di un campo, None se e' un optional non impostato."""
    try:
        if not msg.HasField(field):
            return None
    except ValueError:
        pass  # campo senza presenza esplicita: si usa il valore
    return getattr(msg, field)


def parse_telemetry_msg(tel: telemetry_pb2.Telemetry) -> TelemetryData:
    field = tel.WhichOneof("variant")
    variant = VARIANTS.get(field) if field else None
    if variant is None:
        raise UnsupportedTelemetry
    sub = getattr(tel, field)
    if variant == "device":
        return TelemetryData(
            battery_level=_opt(sub, "battery_level"),
            voltage=_opt(sub, "voltage"),
            channel_utilization=_opt(sub, "channel_utilization"),
            air_util_tx=_opt(sub, "air_util_tx"),
            uptime_seconds=_opt(sub, "uptime_seconds"),
        )
    metrics: dict[str, float] = {}
    for fd, value in sub.ListFields():
        if fd.cpp_type not in _NUMERIC or not isinstance(value, (int, float)):
            continue
        value = float(value)
        if math.isfinite(value):
            metrics[fd.name] = value
    if not metrics:
        raise EmptyTelemetry
    return TelemetryData(variant=variant, metrics=metrics)


def parse_telemetry(payload: bytes) -> TelemetryData:
    tel = telemetry_pb2.Telemetry()
    tel.ParseFromString(payload)
    return parse_telemetry_msg(tel)


def telemetry_from_dict(d: dict) -> TelemetryData:
    tel = telemetry_pb2.Telemetry()
    json_format.ParseDict(d, tel, ignore_unknown_fields=True)
    return parse_telemetry_msg(tel)
