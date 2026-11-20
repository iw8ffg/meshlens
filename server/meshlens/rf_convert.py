"""Conversione dei dict del pacchetto/nodo (libreria meshtastic) in MeshEvent."""
import base64

from .events import (
    MeshEvent, NodeInfoData, PositionData, TelemetryData, TextData,
)


def _coord(d: dict, name: str):
    v = d.get(name)
    if v is None and d.get(name + "I") is not None:
        v = d[name + "I"] * 1e-7
    return v


def _position(pos: dict | None) -> PositionData | None:
    if not pos:
        return None
    lat, lon = _coord(pos, "latitude"), _coord(pos, "longitude")
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return PositionData(
        lat=lat, lon=lon, alt=pos.get("altitude"),
        precision_bits=pos.get("precisionBits") or None,
        time=pos.get("time") or None,
    )


def _public_key(value) -> bytes | None:
    if not value:
        return None
    if isinstance(value, str):  # MessageToDict codifica i bytes in base64
        try:
            return base64.b64decode(value)
        except Exception:
            return None
    return bytes(value)


def _nodeinfo(user: dict | None) -> NodeInfoData | None:
    if not user:
        return None
    return NodeInfoData(
        long_name=user.get("longName", ""),
        short_name=user.get("shortName", ""),
        hw_model=str(user.get("hwModel", "UNSET")),
        role=str(user.get("role", "CLIENT")),
        public_key=_public_key(user.get("publicKey")),
    )


def _telemetry(dm: dict | None) -> TelemetryData | None:
    if not dm:
        return None
    return TelemetryData(
        battery_level=dm.get("batteryLevel"),
        voltage=dm.get("voltage"),
        channel_utilization=dm.get("channelUtilization"),
        air_util_tx=dm.get("airUtilTx"),
        uptime_seconds=dm.get("uptimeSeconds"),
    )


def _event(kind, payload, *, from_node, to_node, packet_id, channel, rx_time,
           snr, rssi, hops, radio_id) -> MeshEvent:
    return MeshEvent(
        source="rf", from_node=from_node, to_node=to_node, packet_id=packet_id,
        channel=channel, rx_time=rx_time, snr=snr, rssi=rssi, hops=hops,
        gateway_id=None, radio_id=radio_id, kind=kind, payload=payload,
    )


def packet_to_event(packet: dict, radio_id: str, now: float) -> MeshEvent | None:
    decoded = packet.get("decoded")
    if not decoded:
        return None  # cifrato e non decifrabile dalla radio
    port = decoded.get("portnum")
    if port == "TEXT_MESSAGE_APP":
        text = decoded.get("text")
        kind, payload = "text", TextData(text=text) if text is not None else None
    elif port == "POSITION_APP":
        kind, payload = "position", _position(decoded.get("position"))
    elif port == "NODEINFO_APP":
        kind, payload = "nodeinfo", _nodeinfo(decoded.get("user"))
    elif port == "TELEMETRY_APP":
        kind = "telemetry"
        payload = _telemetry((decoded.get("telemetry") or {}).get("deviceMetrics"))
    else:
        return None
    if payload is None:
        return None
    hop_start = packet.get("hopStart")
    hops = max(0, hop_start - packet.get("hopLimit", 0)) if hop_start else None
    return _event(
        kind, payload,
        from_node=packet.get("from", 0), to_node=packet.get("to", 0),
        packet_id=packet.get("id", 0), channel=str(packet.get("channel", 0)),
        rx_time=now, snr=packet.get("rxSnr"), rssi=packet.get("rxRssi"),
        hops=hops, radio_id=radio_id,
    )


# rx_time 0 = nodo mai sentito: l'ingestione non lo tratta come "appena sentito"
def nodedb_to_events(nodes: dict, radio_id: str, now: float) -> list[MeshEvent]:
    events: list[MeshEvent] = []
    for node in nodes.values():
        num = node.get("num")
        if num is None:
            continue
        common = dict(from_node=num, to_node=0, packet_id=0, channel="0",
                      rx_time=node.get("lastHeard") or 0, snr=None, rssi=None,
                      hops=None, radio_id=radio_id)
        for kind, payload in (
            ("nodeinfo", _nodeinfo(node.get("user"))),
            ("position", _position(node.get("position"))),
            ("telemetry", _telemetry(node.get("deviceMetrics"))),
        ):
            if payload is not None:
                events.append(_event(kind, payload, **common))
    return events
