"""Invio di messaggi di testo via MQTT a nome del proprio nodo.
Si pubblica SOLO TEXT_MESSAGE_APP: mai posizioni, nodeinfo o altro.
Chiave: quella che il decoder ha visto decifrare quel canale (extra_keys e' una lista
piatta, non per canale); se ignota, la predefinita (AQ==) solo per i nomi dei preset."""
import math
import re
import secrets
from collections import deque
from typing import Callable

from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2

from .crypto import DEFAULT_KEY, decrypt
from .mqtt_decode import channel_hash

MAX_TEXT_BYTES = 200
MIN_INTERVAL_S = 10
MAX_PER_HOUR = 30
HOUR_S = 3600
BROADCAST = 0xFFFFFFFF
HOP_LIMIT = 3
DEFAULT_REGION = "EU_868"
CONFIRM_TEXT = ("Il messaggio sarà pubblico sul broker mqtt.meshtastic.org e potrà essere "
                "ritrasmesso via radio dai gateway")
UNKNOWN_NODE_TEXT = "Collega una radio o imposta il tuo id nodo in Impostazioni → MQTT"
PRESET_CHANNELS = frozenset({"LongFast", "MediumFast", "MediumSlow", "ShortFast", "ShortSlow",
                             "LongModerate", "LongSlow", "ShortTurbo"})
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_NODE_ID = re.compile(r"!([0-9a-fA-F]{8})")


class MqttSendError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def build_envelope(text: str, from_num: int, to_num: int, channel_name: str, key: bytes,
                   packet_id: int, gateway_id: str) -> bytes:
    """ServiceEnvelope con un TEXT_MESSAGE_APP cifrato (AES-CTR e' simmetrico)."""
    data = mesh_pb2.Data(portnum=portnums_pb2.TEXT_MESSAGE_APP, payload=text.encode("utf-8"))
    packet = mesh_pb2.MeshPacket(**{"from": from_num}, to=to_num, id=packet_id,
                                 channel=channel_hash(channel_name, key),
                                 hop_limit=HOP_LIMIT, hop_start=HOP_LIMIT, want_ack=False)
    packet.encrypted = decrypt(key, packet_id, from_num, data.SerializeToString())
    return mqtt_pb2.ServiceEnvelope(packet=packet, channel_id=channel_name,
                                    gateway_id=gateway_id).SerializeToString()


def region_from_topics(topics: list[str]) -> str:
    """Regione dal primo argomento sottoscritto msh/<REGIONE>/..."""
    if topics:
        parts = topics[0].split("/")
        if len(parts) >= 2 and parts[0] == "msh" and parts[1] not in ("", "#", "+"):
            return parts[1]
    return DEFAULT_REGION


class MqttSender:
    """Connettore, impostazioni e radio sono funzioni: il connettore cambia a ogni modifica
    delle impostazioni MQTT."""

    def __init__(self, get_connector: Callable[[], object], get_settings: Callable[[], dict],
                 get_radios: Callable[[], list], clock: Callable[[], float],
                 record: Callable[..., dict],
                 key_for: Callable[[str], bytes | None] = lambda channel: None):
        self.get_connector, self.settings, self.radios = get_connector, get_settings, get_radios
        self.clock, self.record, self.key_for = clock, record, key_for
        self._sent: deque[float] = deque()

    def _own_node(self, settings: dict) -> str:
        configured = (settings.get("mqtt_node_id") or "").strip()
        if configured:
            return "!" + configured[1:].lower()
        for r in self.radios():
            if r.get("state") == "connected" and _NODE_ID.fullmatch(r.get("my_node_id") or ""):
                return r["my_node_id"].lower()
        raise MqttSendError(400, "unknown_node", UNKNOWN_NODE_TEXT)

    def _check_rate(self) -> None:
        now = self.clock()
        while self._sent and now - self._sent[0] >= HOUR_S:
            self._sent.popleft()
        wait = 0.0
        if self._sent:
            wait = self._sent[-1] + MIN_INTERVAL_S - now
        if len(self._sent) >= MAX_PER_HOUR:
            wait = max(wait, self._sent[0] + HOUR_S - now)
        if wait > 0:
            raise MqttSendError(429, "rate_limited", f"Attendi {math.ceil(wait)} s")

    def send(self, text: str, channel: str, to: str | None, confirm_public: bool) -> dict:
        settings = self.settings()
        if not text.strip() or _CONTROL.search(text) or len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise MqttSendError(400, "invalid_text",
                                f"Il testo deve essere non vuoto e di al massimo {MAX_TEXT_BYTES} byte")
        if not channel or len(channel) > 32 or any(c in channel for c in "/#+"):
            raise MqttSendError(400, "invalid_channel", "Nome del canale non valido")
        to_num = BROADCAST
        if to:
            m = _NODE_ID.fullmatch(to)
            if not m:
                raise MqttSendError(400, "invalid_target", "Destinatario non valido")
            to_num = int(m.group(1), 16)
        if not settings.get("mqtt_send_confirmed") and not confirm_public:
            raise MqttSendError(409, "confirm_required", CONFIRM_TEXT)
        key = self.key_for(channel)  # chiave imparata dal traffico; altrimenti solo i preset
        if key is None:
            if channel not in PRESET_CHANNELS:
                raise MqttSendError(400, "unknown_channel_key",
                                    f"Non conosco la chiave del canale {channel}: aspetta di "
                                    "ricevere almeno un messaggio su quel canale")
            key = DEFAULT_KEY
        own = self._own_node(settings)
        connector = self.get_connector()
        if connector is None:
            raise MqttSendError(503, "mqtt_disconnected", "MQTT non connesso")
        self._check_rate()
        from_num = int(own[1:], 16)
        packet_id = secrets.randbelow(2**32 - 1) + 1  # 32 bit, mai 0
        region = region_from_topics(settings["mqtt"].get("topics", []))
        topic = f"msh/{region}/2/e/{channel}/{own}"
        payload = build_envelope(text, from_num, to_num, channel, key, packet_id, own)
        if not connector.publish(topic, payload):
            raise MqttSendError(503, "mqtt_disconnected", "MQTT non connesso")
        self._sent.append(self.clock())
        return self.record(from_num=from_num, to_num=to_num, packet_id=packet_id, text=text,
                           channel=channel)
