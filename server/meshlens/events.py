"""Eventi di rete normalizzati (contratto MeshEvent)."""
from dataclasses import dataclass


def node_id(num: int) -> str:
    return f"!{num:08x}"


@dataclass
class PositionData:
    lat: float
    lon: float
    alt: int | None = None
    precision_bits: int | None = None
    time: int | None = None


@dataclass
class NodeInfoData:
    long_name: str
    short_name: str
    hw_model: str
    role: str
    public_key: bytes | None = None


@dataclass
class TextData:
    text: str


@dataclass
class TelemetryData:
    battery_level: int | None = None
    voltage: float | None = None
    channel_utilization: float | None = None
    air_util_tx: float | None = None
    uptime_seconds: int | None = None


@dataclass
class MapReportData:
    long_name: str
    short_name: str
    hw_model: str
    role: str
    firmware_version: str
    region: str
    modem_preset: str
    lat: float | None
    lon: float | None
    precision_bits: int | None
    num_online_local_nodes: int | None


@dataclass
class NeighborData:
    # (node_id del vicino, snr); il nodo che riferisce e' ev.from_node
    neighbors: list[tuple[int, float | None]]


@dataclass
class RouteData:
    request_id: int | None
    route: list[int]
    snr_towards: list[float | None]
    route_back: list[int]
    snr_back: list[float | None]


def scale_snr(v: int) -> float | None:
    """SNR dei protobuf di traceroute: quarti di dB, -128 = sconosciuto."""
    return None if v == -128 else v / 4


@dataclass
class MeshEvent:
    source: str
    from_node: int
    to_node: int
    packet_id: int
    channel: str
    rx_time: float
    snr: float | None
    rssi: int | None
    hops: int | None
    gateway_id: str | None
    radio_id: str | None
    kind: str
    payload: (PositionData | NodeInfoData | TextData | TelemetryData | MapReportData
               | NeighborData | RouteData)
