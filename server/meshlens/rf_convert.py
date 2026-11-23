"""Conversione dei dict del pacchetto/nodo (libreria meshtastic) in MeshEvent."""
import base64

from meshtastic.protobuf import mesh_pb2

from .events import (
    MeshEvent, NeighborData, NodeInfoData, PacketMeta, PositionData, RAW_MAX, RangeTestData,
    RawPacket, RouteData, TelemetryData, TextData, WaypointData, scale_snr, APP_KINDS,
    APP_PORT_NAMES, AppData,
)
from .storeforward import parse_sf
from .telemetry_decode import parse_telemetry, telemetry_from_dict


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


def _neighbors(info: dict | None) -> NeighborData | None:
    if not info:
        return None
    return NeighborData([(n["nodeId"], n.get("snr")) for n in info.get("neighbors", [])
                         if n.get("nodeId")])


def _route(decoded: dict, packet: dict) -> RouteData | None:
    tr = decoded.get("traceroute")
    if tr is None and decoded.get("payload"):  # la libreria non l'ha decodificato
        try:
            rd = mesh_pb2.RouteDiscovery()
            rd.ParseFromString(bytes(decoded["payload"]))
            tr = {"route": list(rd.route), "snrTowards": list(rd.snr_towards),
                  "routeBack": list(rd.route_back), "snrBack": list(rd.snr_back)}
        except Exception:
            return None
    if tr is None:
        return None
    return RouteData(
        request_id=decoded.get("requestId") or packet.get("requestId") or None,
        route=list(tr.get("route", [])),
        snr_towards=[scale_snr(v) for v in tr.get("snrTowards", [])],
        route_back=list(tr.get("routeBack", [])),
        snr_back=[scale_snr(v) for v in tr.get("snrBack", [])],
    )


def parse_seq(text: str) -> int | None:
    """Numero di sequenza di un pacchetto Range Test: accetta solo "seq N" con N intero >= 0."""
    parts = (text or "").split()
    if len(parts) == 2 and parts[0] == "seq" and parts[1].isascii() and parts[1].isdigit():
        return int(parts[1])
    return None


def _rangetest(decoded: dict) -> RangeTestData:
    text = decoded.get("text")
    if text is None:
        try:
            text = bytes(decoded.get("payload") or b"").decode("utf-8")
        except UnicodeDecodeError:
            text = ""  # UTF-8 rotto: il pacchetto prova comunque che il modulo e' attivo
    return RangeTestData(seq=parse_seq(text), text=text)


def _waypoint(wp: dict | None) -> WaypointData | None:
    if not wp:
        return None
    lat_i, lon_i = wp.get("latitudeI"), wp.get("longitudeI")
    ok = (lat_i is not None and lon_i is not None and not (lat_i == 0 and lon_i == 0)
          and -900_000_000 <= lat_i <= 900_000_000 and -1_800_000_000 <= lon_i <= 1_800_000_000)
    return WaypointData(
        id=wp.get("id", 0),
        lat=lat_i * 1e-7 if ok else None, lon=lon_i * 1e-7 if ok else None,
        name=wp.get("name", ""), description=wp.get("description", ""),
        icon=wp.get("icon", 0), expire=wp.get("expire", 0), locked_to=wp.get("lockedTo", 0),
    )


def _event(kind, payload, *, from_node, to_node, packet_id, channel, rx_time,
           snr, rssi, hops, radio_id, via_mqtt=False, pki=False, meta=None) -> MeshEvent:
    return MeshEvent(
        source="rf", from_node=from_node, to_node=to_node, packet_id=packet_id,
        channel=channel, rx_time=rx_time, snr=snr, rssi=rssi, hops=hops,
        gateway_id=None, radio_id=radio_id, kind=kind, payload=payload, via_mqtt=via_mqtt,
        pki=pki, meta=meta,
    )


def _raw_bytes(value) -> bytes:
    """Byte di un payload della libreria (bytes o base64 se passato da MessageToDict)."""
    if not value:
        return b""
    if isinstance(value, str):
        try:
            return base64.b64decode(value)
        except Exception:
            return b""
    try:
        return bytes(value)
    except Exception:
        return b""


def _packet_meta(packet: dict, decoded: dict | None) -> PacketMeta:
    if decoded:
        raw, encrypted = _raw_bytes(decoded.get("payload")), bool(packet.get("pkiEncrypted"))
        portnum = decoded.get("portnum")
        portnum = None if portnum is None else str(portnum)
    else:
        raw, encrypted, portnum = _raw_bytes(packet.get("encrypted")), True, None
    return PacketMeta(
        portnum=portnum, hop_start=packet.get("hopStart") or None,
        hop_limit=packet.get("hopLimit"), want_ack=bool(packet.get("wantAck")),
        encrypted=encrypted, raw=raw[:RAW_MAX],
    )


def packet_to_raw(packet: dict, radio_id: str, now: float) -> RawPacket:
    """Pacchetto che la radio ha consegnato ma che non diventa un MeshEvent."""
    decoded = packet.get("decoded")
    return RawPacket(
        source="rf", from_node=packet.get("from", 0), to_node=packet.get("to", 0),
        packet_id=packet.get("id", 0), channel=str(packet.get("channel", 0)), rx_time=now,
        snr=packet.get("rxSnr"), rssi=packet.get("rxRssi"), gateway_id=None,
        radio_id=radio_id, broker=None, relay_node=packet.get("relayNode") or None,
        status="unsupported" if decoded else "encrypted", meta=_packet_meta(packet, decoded),
    )


def packet_to_event(packet: dict, radio_id: str, now: float) -> MeshEvent | None:
    decoded = packet.get("decoded")
    if not decoded:
        return None  # cifrato e non decifrabile dalla radio
    port = decoded.get("portnum")
    if port == "TEXT_MESSAGE_APP":
        text = decoded.get("text")
        kind = "text"
        payload = (TextData(text=text, reply_id=decoded.get("replyId") or None,
                            emoji=bool(decoded.get("emoji"))) if text is not None else None)
    elif port == "WAYPOINT_APP":
        kind, payload = "waypoint", _waypoint(decoded.get("waypoint"))
    elif port == "POSITION_APP":
        kind, payload = "position", _position(decoded.get("position"))
    elif port == "NODEINFO_APP":
        kind, payload = "nodeinfo", _nodeinfo(decoded.get("user"))
    elif port == "TELEMETRY_APP":
        kind = "telemetry"
        try:
            raw = decoded.get("payload")
            if isinstance(raw, (bytes, bytearray)):
                payload = parse_telemetry(bytes(raw))
            else:
                payload = telemetry_from_dict(decoded.get("telemetry") or {})
        except Exception:  # UnsupportedTelemetry, EmptyTelemetry, dict o bytes malformati
            payload = None
    elif port == "NEIGHBORINFO_APP":
        kind, payload = "neighbors", _neighbors(decoded.get("neighborinfo"))
    elif port == "TRACEROUTE_APP":
        kind, payload = "traceroute", _route(decoded, packet)
    elif port == "RANGE_TEST_APP":
        kind, payload = "rangetest", _rangetest(decoded)
    elif port == "STORE_FORWARD_APP":
        kind, payload = "storeforward", parse_sf(packet)
    elif port in APP_PORT_NAMES:
        # Detection Sensor, Paxcounter, ATAK: payload grezzo per le estensioni
        num, raw = APP_PORT_NAMES[port], decoded.get("payload")
        kind = APP_KINDS[num]
        payload = None
        if isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw)
            text = raw.decode("utf-8", errors="replace") if kind == "detection" else None
            payload = AppData(portnum=num, payload=raw, text=text)
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
        hops=hops, radio_id=radio_id, via_mqtt=bool(packet.get("viaMqtt")),
        pki=bool(packet.get("pkiEncrypted")),
        meta=_packet_meta(packet, decoded),
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
