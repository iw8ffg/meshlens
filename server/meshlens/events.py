"""Eventi di rete normalizzati (contratto MeshEvent)."""
from dataclasses import dataclass, field


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
    reply_id: int | None = None  # packet_id del messaggio a cui risponde o reagisce
    emoji: bool = False  # reazione: il testo e' l'emoji


@dataclass
class WaypointData:
    id: int
    lat: float | None  # None se (0,0) o fuori intervallo (serve per le eliminazioni)
    lon: float | None
    name: str
    description: str
    icon: int  # codepoint Unicode, 0 = nessuno
    expire: int  # secondi epoch, 0 = mai
    locked_to: int  # numero nodo, 0 = nessuno


@dataclass
class TelemetryData:
    battery_level: int | None = None
    voltage: float | None = None
    channel_utilization: float | None = None
    air_util_tx: float | None = None
    uptime_seconds: int | None = None
    variant: str = "device"
    metrics: dict[str, float] = field(default_factory=dict)


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


@dataclass
class RangeTestData:
    seq: int | None  # None se il testo non e' "seq N"
    text: str


def scale_snr(v: int) -> float | None:
    """SNR dei protobuf di traceroute: quarti di dB, -128 = sconosciuto."""
    return None if v == -128 else v / 4


RAW_MAX = 256


@dataclass
class PacketMeta:
    portnum: str | None  # "TEXT_MESSAGE_APP"; None se non decifrato
    hop_start: int | None
    hop_limit: int | None
    want_ack: bool = False
    encrypted: bool = False  # arrivato cifrato
    raw: bytes = b""  # Data.payload decifrato, altrimenti i byte cifrati; max RAW_MAX


@dataclass
class RawPacket:
    """Pacchetto ricevuto ma non trasformato in MeshEvent."""
    source: str
    from_node: int
    to_node: int
    packet_id: int
    channel: str
    rx_time: float
    snr: float | None
    rssi: int | None
    gateway_id: str | None
    radio_id: str | None
    broker: str | None
    relay_node: int | None
    status: str  # "encrypted" | "unsupported" | "undecodable" | "empty"
    meta: PacketMeta


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
               | NeighborData | RouteData | RangeTestData | WaypointData)
    via_mqtt: bool = False  # pacchetto RF arrivato alla radio tramite un gateway MQTT
    # MQTT: ultimo byte dell'ultimo ritrasmettitore (0 = sconosciuto) e minimo dei salti noto
    relay_node: int | None = None
    hops_min: int | None = None
    broker: str | None = None  # MQTT: id del broker che ha consegnato il pacchetto
    pki: bool = False  # DM cifrato con la chiave pubblica del destinatario
    replayed: bool = False  # S&F: messaggio rigiocato da un router (ora originale)
    meta: PacketMeta | None = None

    @property
    def gateway_num(self) -> int | None:
        """Numero del nodo gateway ricavato da gateway_id ("!hex"); None se non valido."""
        g = self.gateway_id
        if not g or not g.startswith("!"):
            return None
        try:
            return int(g[1:], 16)
        except ValueError:
            return None
