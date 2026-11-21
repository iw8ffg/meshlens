"""Decodifica dei ServiceEnvelope MQTT di Meshtastic in MeshEvent."""
import collections

from meshtastic.protobuf import config_pb2, mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

from .crypto import decrypt
from .events import (
    MapReportData, MeshEvent, NeighborData, NodeInfoData, PositionData, RouteData,
    TelemetryData, TextData, scale_snr,
)


class _Empty(Exception):
    """Messaggio valido ma senza contenuto utile."""


class _Unsupported(Exception):
    pass


def _enum_name(enum_type, value: int) -> str:
    try:
        return enum_type.Name(value)
    except Exception:
        return str(value)


def _opt(msg, field: str):
    """Valore di un campo, None se e' un optional non impostato."""
    try:
        if not msg.HasField(field):
            return None
    except ValueError:
        pass  # campo senza presenza esplicita: si usa il valore
    return getattr(msg, field)


def _valid_coords(lat_i: int, lon_i: int) -> bool:
    return -900_000_000 <= lat_i <= 900_000_000 and -1_800_000_000 <= lon_i <= 1_800_000_000


def _xor_bytes(data: bytes) -> int:
    h = 0
    for b in data:
        h ^= b
    return h


def channel_hash(name: str, key: bytes) -> int:
    """Hash di canale di Meshtastic: XOR dei byte del nome e di quelli della chiave."""
    return _xor_bytes(name.encode("utf-8")) ^ _xor_bytes(key)


def _parse_position(payload: bytes) -> PositionData:
    pos = mesh_pb2.Position()
    pos.ParseFromString(payload)
    if (pos.latitude_i == 0 and pos.longitude_i == 0) or not _valid_coords(
            pos.latitude_i, pos.longitude_i):
        raise _Empty
    return PositionData(
        lat=pos.latitude_i * 1e-7,
        lon=pos.longitude_i * 1e-7,
        alt=_opt(pos, "altitude"),
        precision_bits=pos.precision_bits or None,
        time=pos.time or None,
    )


def _parse_nodeinfo(payload: bytes) -> NodeInfoData:
    user = mesh_pb2.User()
    user.ParseFromString(payload)
    return NodeInfoData(
        long_name=user.long_name,
        short_name=user.short_name,
        hw_model=_enum_name(mesh_pb2.HardwareModel, user.hw_model),
        role=_enum_name(config_pb2.Config.DeviceConfig.Role, user.role),
        public_key=user.public_key or None,
    )


def _parse_telemetry(payload: bytes) -> TelemetryData:
    tel = telemetry_pb2.Telemetry()
    tel.ParseFromString(payload)
    if not tel.HasField("device_metrics"):
        raise _Unsupported
    dm = tel.device_metrics
    return TelemetryData(
        battery_level=_opt(dm, "battery_level"),
        voltage=_opt(dm, "voltage"),
        channel_utilization=_opt(dm, "channel_utilization"),
        air_util_tx=_opt(dm, "air_util_tx"),
        uptime_seconds=_opt(dm, "uptime_seconds"),
    )


def _parse_mapreport(payload: bytes) -> MapReportData:
    mr = mqtt_pb2.MapReport()
    mr.ParseFromString(payload)
    has_pos = not (mr.latitude_i == 0 and mr.longitude_i == 0)
    if has_pos and not _valid_coords(mr.latitude_i, mr.longitude_i):
        raise _Empty
    return MapReportData(
        long_name=mr.long_name,
        short_name=mr.short_name,
        hw_model=_enum_name(mesh_pb2.HardwareModel, mr.hw_model),
        role=_enum_name(config_pb2.Config.DeviceConfig.Role, mr.role),
        firmware_version=mr.firmware_version,
        region=_enum_name(config_pb2.Config.LoRaConfig.RegionCode, mr.region),
        modem_preset=_enum_name(config_pb2.Config.LoRaConfig.ModemPreset, mr.modem_preset),
        lat=mr.latitude_i * 1e-7 if has_pos else None,
        lon=mr.longitude_i * 1e-7 if has_pos else None,
        precision_bits=mr.position_precision or None,
        num_online_local_nodes=mr.num_online_local_nodes or None,
    )


def _parse_neighbors(payload: bytes) -> NeighborData:
    info = mesh_pb2.NeighborInfo()
    info.ParseFromString(payload)
    return NeighborData([(n.node_id, n.snr) for n in info.neighbors if n.node_id])


def _parse_route(data: mesh_pb2.Data) -> RouteData:
    rd = mesh_pb2.RouteDiscovery()
    rd.ParseFromString(data.payload)
    return RouteData(
        request_id=data.request_id or None,
        route=list(rd.route), snr_towards=[scale_snr(v) for v in rd.snr_towards],
        route_back=list(rd.route_back), snr_back=[scale_snr(v) for v in rd.snr_back],
    )


def _parse_payload(data: mesh_pb2.Data):
    port = data.portnum
    if port == portnums_pb2.TEXT_MESSAGE_APP:
        return "text", TextData(text=data.payload.decode("utf-8"))  # strict: UnicodeDecodeError = undecodable
    if port == portnums_pb2.POSITION_APP:
        return "position", _parse_position(data.payload)
    if port == portnums_pb2.NODEINFO_APP:
        return "nodeinfo", _parse_nodeinfo(data.payload)
    if port == portnums_pb2.TELEMETRY_APP:
        return "telemetry", _parse_telemetry(data.payload)
    if port == portnums_pb2.MAP_REPORT_APP:
        return "mapreport", _parse_mapreport(data.payload)
    if port == portnums_pb2.NEIGHBORINFO_APP:
        return "neighbors", _parse_neighbors(data.payload)
    if port == portnums_pb2.TRACEROUTE_APP:
        return "traceroute", _parse_route(data)
    raise _Unsupported


class EnvelopeDecoder:
    def __init__(self, keys: list[bytes]):
        self.keys = list(keys)
        self.stats: collections.Counter = collections.Counter()

    def decode(self, topic: str, payload: bytes, now: float) -> MeshEvent | None:
        """Non solleva mai: ogni scarto viene contato in `stats`."""
        try:
            return self._decode(topic, payload, now)
        except _Empty:
            self.stats["empty"] += 1
        except _Unsupported:
            self.stats["unsupported_port"] += 1
        except Exception:
            self.stats["undecodable"] += 1
        return None

    def _decode(self, topic: str, payload: bytes, now: float) -> MeshEvent | None:
        if "json" in topic.split("/"):
            self.stats["json_topic"] += 1
            return None
        env = mqtt_pb2.ServiceEnvelope()
        try:
            env.ParseFromString(payload)
        except Exception:
            self.stats["not_protobuf"] += 1
            return None
        if not env.HasField("packet"):
            self.stats["not_protobuf"] += 1
            return None
        packet = env.packet
        from_node = getattr(packet, "from")
        data = self._extract_data(packet, from_node, env.channel_id or None)
        if data is None:
            self.stats["undecodable"] += 1
            return None
        kind, body = _parse_payload(data)
        self.stats["ok"] += 1
        return MeshEvent(
            source="mqtt",
            from_node=from_node,
            to_node=packet.to,
            packet_id=packet.id,
            channel=env.channel_id,
            rx_time=now,
            snr=packet.rx_snr or None,
            rssi=packet.rx_rssi or None,
            hops=max(0, packet.hop_start - packet.hop_limit) if packet.hop_start > 0 else None,
            gateway_id=env.gateway_id or None,
            radio_id=None,
            kind=kind,
            payload=body,
        )

    def _extract_data(self, packet: mesh_pb2.MeshPacket, from_node: int,
                      channel_name: str | None) -> mesh_pb2.Data | None:
        if packet.WhichOneof("payload_variant") == "decoded":
            return packet.decoded if packet.decoded.portnum != 0 else None
        if not packet.encrypted:
            return None
        for key in self.keys:
            if not key:  # b"" = nessuna cifratura: niente da provare
                continue
            # packet.channel == 0: hash sconosciuto, si prova comunque
            if packet.channel and channel_name is not None and                     packet.channel != channel_hash(channel_name, key):
                continue
            try:
                plain = decrypt(key, packet.id, from_node, packet.encrypted)
                data = mesh_pb2.Data()
                data.ParseFromString(plain)
            except Exception:
                continue
            if data.portnum != 0:
                return data
        return None
