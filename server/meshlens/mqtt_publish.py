"""Invio di messaggi di testo via MQTT a nome del proprio nodo, sul broker scelto.
Si pubblica SOLO TEXT_MESSAGE_APP: mai posizioni, nodeinfo o altro.
Chiave: quella del canale personalizzato del broker; poi quella che il decoder del broker
ha visto decifrare quel canale; se ignota, la predefinita (AQ==) solo per i nomi dei preset.
Con la crittografia del broker spenta il pacchetto esce in chiaro (decoded)."""
import math
import re
import secrets
from collections import deque
from typing import Callable

from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2

from .crypto import DEFAULT_KEY, decrypt, expand_psk
from .mqtt_decode import channel_hash
from .settings import DEFAULT_BROKER_ID, enabled_brokers, find_broker

MAX_TEXT_BYTES = 200
MIN_INTERVAL_S = 10
MAX_PER_HOUR = 30
HOUR_S = 3600
BROADCAST = 0xFFFFFFFF
HOP_LIMIT = 3
DEFAULT_REGION = "EU_868"


def confirm_text(host: str) -> str:
    return (f"Il messaggio sarà pubblico sul broker {host} e potrà essere "
            "ritrasmesso via radio dai gateway")


CONFIRM_TEXT = confirm_text("mqtt.meshtastic.org")
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
                   packet_id: int, gateway_id: str, encrypted: bool = True) -> bytes:
    """ServiceEnvelope con un TEXT_MESSAGE_APP cifrato (AES-CTR e' simmetrico), oppure in
    chiaro (decoded) se encrypted e' falso o il canale non ha chiave."""
    data = mesh_pb2.Data(portnum=portnums_pb2.TEXT_MESSAGE_APP, payload=text.encode("utf-8"))
    packet = mesh_pb2.MeshPacket(**{"from": from_num}, to=to_num, id=packet_id,
                                 channel=channel_hash(channel_name, key),
                                 hop_limit=HOP_LIMIT, hop_start=HOP_LIMIT, want_ack=False)
    if encrypted and key:
        packet.encrypted = decrypt(key, packet_id, from_num, data.SerializeToString())
    else:
        packet.decoded.CopyFrom(data)
    return mqtt_pb2.ServiceEnvelope(packet=packet, channel_id=channel_name,
                                    gateway_id=gateway_id).SerializeToString()


def root_from_topics(topics: list[str]) -> str:
    """Radice per l'invio, presa dal primo argomento sottoscritto: "msh/EU_868/IT/#" ->
    "msh/EU_868/IT". I gateway con downlink ascoltano <radice>/2/e/<canale>/#: pubblicare
    sotto la stessa radice che si ascolta e' cio' che fa arrivare il messaggio via radio."""
    if topics:
        t = topics[0].strip()
        if "/2/" in t:
            t = t.split("/2/", 1)[0]
        t = t.rstrip("#").rstrip("/")
        parts = t.split("/")
        if len(parts) >= 2 and parts[0] == "msh" and all(p and p not in ("#", "+") for p in parts):
            return t
    return f"msh/{DEFAULT_REGION}"


def region_from_topics(topics: list[str]) -> str:
    """Regione dal primo argomento sottoscritto msh/<REGIONE>/..."""
    if topics:
        parts = topics[0].split("/")
        if len(parts) >= 2 and parts[0] == "msh" and parts[1] not in ("", "#", "+"):
            return parts[1]
    return DEFAULT_REGION


def pick_broker(settings: dict, broker_id: str | None) -> dict:
    """Il broker su cui inviare: quello indicato se esiste ed e' attivo, altrimenti
    (None) il primo attivo."""
    if broker_id is None:
        active = enabled_brokers(settings)
        broker = active[0] if active else None
    else:
        broker = find_broker(settings, broker_id)
    if broker is None or not broker.get("enabled"):
        raise MqttSendError(400, "unknown_broker", "Broker non trovato o disattivato")
    return broker


def is_confirmed(settings: dict, broker_id: str) -> bool:
    """Conferma della prima volta gia' data per questo broker (mqtt_send_confirmed vale per
    il predefinito, come nelle versioni con un solo broker)."""
    return (broker_id in (settings.get("mqtt_send_confirmed_brokers") or [])
            or (broker_id == DEFAULT_BROKER_ID and bool(settings.get("mqtt_send_confirmed"))))


class MqttSender:
    """Connettore, impostazioni e radio sono funzioni: i connettori cambiano a ogni modifica
    delle impostazioni MQTT. get_connector(id broker) -> connettore o None;
    key_for(id broker, canale) -> chiave imparata dal decoder di quel broker o None."""

    def __init__(self, get_connector: Callable[[str], object | None],
                 get_settings: Callable[[], dict],
                 get_radios: Callable[[], list], clock: Callable[[], float],
                 record: Callable[..., dict],
                 key_for: Callable[[str, str], bytes | None] = lambda broker, channel: None):
        self.get_connector, self.settings, self.radios = get_connector, get_settings, get_radios
        self.clock, self.record, self.key_for = clock, record, key_for
        self._sent: dict[str, deque[float]] = {}  # id broker -> istanti degli invii

    def _own_node(self, settings: dict) -> str:
        configured = (settings.get("mqtt_node_id") or "").strip()
        if configured:
            return "!" + configured[1:].lower()
        for r in self.radios():
            if r.get("state") == "connected" and _NODE_ID.fullmatch(r.get("my_node_id") or ""):
                return r["my_node_id"].lower()
        raise MqttSendError(400, "unknown_node", UNKNOWN_NODE_TEXT)

    def _check_rate(self, broker_id: str) -> None:
        now = self.clock()
        sent = self._sent.setdefault(broker_id, deque())
        while sent and now - sent[0] >= HOUR_S:
            sent.popleft()
        wait = 0.0
        if sent:
            wait = sent[-1] + MIN_INTERVAL_S - now
        if len(sent) >= MAX_PER_HOUR:
            wait = max(wait, sent[0] + HOUR_S - now)
        if wait > 0:
            raise MqttSendError(429, "rate_limited", f"Attendi {math.ceil(wait)} s")

    def _channel_key(self, broker: dict, channel: str) -> bytes:
        for ch in broker.get("channels", []):
            if ch.get("name") == channel:
                return expand_psk(ch["psk"])
        key = self.key_for(broker["id"], channel)  # imparata dal traffico di quel broker
        if key is not None:
            return key
        if channel in PRESET_CHANNELS:
            return DEFAULT_KEY
        raise MqttSendError(400, "unknown_channel_key",
                            f"Non conosco la chiave del canale {channel} su {broker['name']}: "
                            "aggiungilo ai canali del broker in Impostazioni")

    def send(self, text: str, channel: str, to: str | None, confirm_public: bool,
             broker: str | None = None) -> dict:
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
        b = pick_broker(settings, broker)
        bid = b["id"]
        if not is_confirmed(settings, bid) and not confirm_public:
            raise MqttSendError(409, "confirm_required", confirm_text(b["host"]))
        key = self._channel_key(b, channel)
        own = self._own_node(settings)
        connector = self.get_connector(bid)
        if connector is None:
            raise MqttSendError(503, "mqtt_disconnected", "MQTT non connesso")
        self._check_rate(bid)
        from_num = int(own[1:], 16)
        packet_id = secrets.randbelow(2**32 - 1) + 1  # 32 bit, mai 0
        root = root_from_topics(b.get("topics", []))
        topic = f"{root}/2/e/{channel}/{own}"
        payload = build_envelope(text, from_num, to_num, channel, key, packet_id, own,
                                 encrypted=b.get("encryption", True))
        if not connector.publish(topic, payload):
            raise MqttSendError(503, "mqtt_disconnected", "MQTT non connesso")
        self._sent[bid].append(self.clock())
        return self.record(from_num=from_num, to_num=to_num, packet_id=packet_id, text=text,
                           channel=channel, broker=bid)
