"""Pipeline di ingestione: da MeshEvent a stato live e archivio."""
import time
from collections import OrderedDict
from typing import Callable

from .dedup import Deduplicator
from .events import MeshEvent, TelemetryData, node_id
from .geo import CountryLocator
from .live import LiveState
from .store import Store

_DAY = 86400
_RF_BITS = 32


def _bits(precision_bits: int | None) -> int:
    return _RF_BITS if precision_bits is None else precision_bits


def _channel_index(channel: str) -> int | None:
    """Indice canale di un evento RF (stringa numerica); None per i canali MQTT per nome."""
    try:
        return int(channel)
    except (TypeError, ValueError):
        return None


def _new_node(num: int) -> dict:
    return {"id": node_id(num), "num": num, "long_name": None, "short_name": None,
            "hw_model": None, "role": None, "firmware": None, "lat": None, "lon": None,
            "precision_bits": None, "position_source": None, "position_time": None,
            "country": None, "last_heard": None, "sources": [], "battery": None,
            "voltage": None, "channel_util": None, "air_util_tx": None, "mqtt_gateways": 0,
            "last_snr": None, "hops": None, "heard_by": {}, "is_local_radio": False}


class Ingestor:
    def __init__(self, live: LiveState, store: Store, dedup: Deduplicator,
                 locator: CountryLocator, get_settings: Callable[[], dict],
                 on_message: Callable[[dict], None],
                 on_status: Callable[[str, str], None] | None = None):
        self.live = live
        self.store = store
        self.dedup = dedup
        self.locator = locator
        self.get_settings = get_settings
        self.on_message = on_message
        self.on_status = on_status
        self._telemetry_time: dict[int, float] = {}
        # (nodo, packet id) gia' visti da MQTT: serve a contare i gateway anche se l'RF e' arrivato prima
        self._mqtt_seen: OrderedDict[tuple[int, int], None] = OrderedDict()

    def handle(self, ev: MeshEvent) -> None:
        num = ev.from_node
        node = self.live.nodes.get(num)
        if node is None:
            node = self.live.nodes[num] = _new_node(num)
        self.live.mark_changed(num)

        # i replay del database nodi della radio hanno rx_time vecchio: non fanno regredire lo stato
        previous_heard = node["last_heard"]
        stale = previous_heard is not None and ev.rx_time < previous_heard
        if not stale:
            node["last_heard"] = ev.rx_time
        if ev.source not in node["sources"]:
            node["sources"].append(ev.source)
        is_dup = False
        if ev.source == "mqtt" or (ev.source == "rf" and ev.packet_id):
            # i pacchetti RF senza id (dal database nodi della radio) non si deduplicano
            is_dup = not self.dedup.is_new(num, ev.packet_id, ev.rx_time)
        if ev.source == "rf" and ev.radio_id:
            heard_by = node.setdefault("heard_by", {})
            old = heard_by.get(ev.radio_id)
            if old is None or int(ev.rx_time) >= old["time"]:
                heard_by[ev.radio_id] = {"snr": ev.snr, "rssi": ev.rssi, "hops": ev.hops,
                                         "time": int(ev.rx_time)}
        # copie dello stesso pacchetto: si tiene l'SNR migliore e il minor numero di hop
        if ev.snr is not None and not stale:
            prev = node["last_snr"]
            node["last_snr"] = ev.snr if not is_dup or prev is None else max(prev, ev.snr)
        if ev.hops is not None and not stale:
            prev = node["hops"]
            node["hops"] = ev.hops if not is_dup or prev is None else min(prev, ev.hops)

        if ev.source == "mqtt":
            key = (num, ev.packet_id)
            seen = key in self._mqtt_seen
            if not seen:
                if len(self._mqtt_seen) >= 200_000:
                    self._mqtt_seen.popitem(last=False)
                self._mqtt_seen[key] = None
            if is_dup:
                # copia MQTT di un pacchetto gia' visto: se prima c'era solo l'RF e' il primo gateway
                node["mqtt_gateways"] = 1 if not seen else (node["mqtt_gateways"] or 0) + 1
                return
            node["mqtt_gateways"] = 1
        elif is_dup:
            self.store.upsert_node(node)  # copia RF: aggiorna solo "sentito da"
            return

        ev_pos = None  # (lat, lon, precision_bits, source) della posizione nell'evento
        kind, p = ev.kind, ev.payload
        if kind == "position" and self._older(ev, node["position_time"]):
            pass
        elif kind == "telemetry" and self._older(ev, self._telemetry_time.get(num)):
            kind = "stale"
        elif kind == "position":
            ev_pos = (p.lat, p.lon, p.precision_bits, ev.source)
            self._update_position(node, ev, *ev_pos)
        elif kind == "nodeinfo":
            self._update_identity(node, p)
        elif kind == "mapreport":
            self._update_identity(node, p)
            if p.firmware_version:
                node["firmware"] = p.firmware_version
            if (p.lat is not None and p.lon is not None
                    and not self._older(ev, node["position_time"])):
                ev_pos = (p.lat, p.lon, p.precision_bits, "mqtt_map")
                self._update_position(node, ev, *ev_pos)
        elif kind == "telemetry":
            self._telemetry_time[num] = ev.rx_time
            self._update_telemetry(node, p)

        persist = (node["country"] in self.get_settings()["saved_countries"]
                   or ev.source == "rf" or bool(node.get("is_mine")))

        message = self._build_message(node, ev) if kind == "text" else None
        if message is not None:
            self.live.messages.append(message)

        if persist:
            self.store.upsert_node(node)
            if ev_pos is not None:
                self.store.add_position(num, ev.rx_time, *ev_pos[:3], ev_pos[3])
            if kind == "telemetry":
                self.store.add_telemetry(num, ev.rx_time, p)
            if message is not None:
                self.store.add_message(message)

        if message is not None:
            self.on_message(message)

    @staticmethod
    def _older(ev: MeshEvent, current: float | None) -> bool:
        return current is not None and ev.rx_time < current

    def mark_local_radio(self, node_num: int) -> None:
        """Il nodo e' una radio collegata a questo server: e' anche "mio"."""
        node = self.live.nodes.get(node_num)
        if node is None:
            node = self.live.nodes[node_num] = _new_node(node_num)
        node["is_local_radio"] = True
        node["is_mine"] = True
        self.live.mark_changed(node_num)
        self.store.upsert_node(node, is_mine=True)

    def record_outgoing(self, radio_id: str, my_node_id: str, packet_id: int, text: str,
                        channel_index: int, to: str, status: str = "sent") -> dict:
        """Registra un messaggio inviato da una radio locale e lo pubblica."""
        mine = self.live.nodes.get(int(my_node_id[1:], 16))
        message = {"key": f"out:{radio_id}:{packet_id}", "from": my_node_id,
                   "from_name": mine["long_name"] if mine else None, "to": to,
                   "channel": str(channel_index), "text": text, "time": int(time.time()),
                   "country": mine["country"] if mine else None, "source": "rf",
                   "direction": "out", "radio_id": radio_id, "channel_index": channel_index,
                   "packet_id": packet_id, "status": status}
        self.live.messages.append(message)
        self.store.add_message(message)
        self.on_message(message)
        return message

    def set_status(self, key: str, status: str) -> None:
        self.store.update_message_status(key, status)
        for message in self.live.messages:
            if message["key"] == key:
                message["status"] = status
        if self.on_status is not None:
            self.on_status(key, status)

    def _update_position(self, node: dict, ev: MeshEvent, lat: float, lon: float,
                         precision_bits: int | None, source: str) -> None:
        """Regola della posizione migliore (a parita' di precisione vince la piu' recente)."""
        current_time = node["position_time"]
        replace = (node["lat"] is None
                   or _bits(precision_bits) >= _bits(node["precision_bits"])
                   or current_time is None
                   or ev.rx_time - current_time > _DAY)
        if replace:
            node.update(lat=lat, lon=lon, precision_bits=precision_bits,
                        position_source=source, position_time=int(ev.rx_time),
                        country=self.locator.locate(lat, lon))

    @staticmethod
    def _update_identity(node: dict, p) -> None:
        for field in ("long_name", "short_name", "hw_model", "role"):
            value = getattr(p, field)
            if value:
                node[field] = value

    @staticmethod
    def _update_telemetry(node: dict, t: TelemetryData) -> None:
        for field, value in (("battery", t.battery_level), ("voltage", t.voltage),
                             ("channel_util", t.channel_utilization),
                             ("air_util_tx", t.air_util_tx)):
            if value is not None:
                node[field] = value

    def _build_message(self, node: dict, ev: MeshEvent) -> dict:
        return {"key": f"{ev.from_node}:{ev.packet_id}", "from": node_id(ev.from_node),
                "from_name": node["long_name"], "to": node_id(ev.to_node),
                "channel": ev.channel, "text": ev.payload.text, "time": int(ev.rx_time),
                "country": node["country"], "source": ev.source, "direction": "in",
                "radio_id": ev.radio_id, "channel_index": _channel_index(ev.channel),
                "packet_id": ev.packet_id, "status": None}
