"""Pipeline di ingestione: da MeshEvent a stato live e archivio."""
import time
from typing import Callable

from .dedup import Deduplicator
from .events import MeshEvent, TelemetryData, node_id
from .geo import CountryLocator
from .live import LiveState
from .store import Store

_DAY = 86400
_RF_BITS = 32
_RF_HOPS_TTL = 3600  # s: per quanto un hops RF non viene scavalcato da uno MQTT


def _bits(precision_bits: int | None) -> int:
    return _RF_BITS if precision_bits is None else precision_bits


def _channel_index(channel: str) -> int | None:
    """Indice canale di un evento RF (stringa numerica); None per i canali MQTT per nome."""
    try:
        return int(channel)
    except (TypeError, ValueError):
        return None


def _snr_at(snrs: list, i: int):
    return snrs[i] if i < len(snrs) else None


def traceroute_chains(ev: MeshEvent) -> tuple[list[tuple[int, float | None]],
                                              list[tuple[int, float | None]]]:
    """Catene (nodo, snr) di andata e ritorno; from_node e' il nodo raggiunto, to_node chi ha avviato."""
    p = ev.payload
    fwd_nodes = p.route + [ev.from_node]
    back_nodes = p.route_back + [ev.to_node]
    forward = [(ev.to_node, None)] + [(n, _snr_at(p.snr_towards, i)) for i, n in enumerate(fwd_nodes)]
    back = [(ev.from_node, None)] + [(n, _snr_at(p.snr_back, i)) for i, n in enumerate(back_nodes)]
    return forward, back


def revive_node(store, num: int) -> dict:
    """Nodo assente dalla memoria (nuovo o tolto dal limite dei nodi): se e' archiviato
    riparte dalla riga del database, altrimenti l'upsert cancellerebbe nome e posizione."""
    stored = store.get_node(num)
    return _new_node(num) if stored is None else {**_new_node(num), **stored}


def _new_node(num: int) -> dict:
    return {"id": node_id(num), "num": num, "long_name": None, "short_name": None,
            "hw_model": None, "role": None, "firmware": None, "lat": None, "lon": None,
            "precision_bits": None, "position_source": None, "position_time": None,
            "country": None, "last_heard": None, "sources": [], "battery": None,
            "voltage": None, "channel_util": None, "air_util_tx": None, "mqtt_gateways": 0,
            "last_snr": None, "hops": None, "heard_by": {}, "is_local_radio": False, "is_mine": False,
            "is_favorite": False, "hops_min": None}


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
        self._rf_hops_time: dict[int, float] = {}  # nodo -> istante dell'ultimo hops da RF
        self._radio_nodes: dict[str, int] = {}  # radio_id -> numero del nodo della radio
        # canali visti da MQTT (anche se scartati): (broker, canale) -> {minuto: conteggio}
        self._channel_buckets: dict[tuple[str, str], dict[int, int]] = {}
        self.filtered_channel = 0  # eventi MQTT scartati dal filtro mqtt_channels

    def _note_mqtt_channel(self, name: str, t: float, broker: str | None = None) -> None:
        buckets = self._channel_buckets.setdefault((broker or "", name), {})
        minute = int(t // 60)
        buckets[minute] = buckets.get(minute, 0) + 1
        for m in [m for m in buckets if m < minute - 61]:
            del buckets[m]

    def _channel_totals(self, now: float | None) -> dict[tuple[str, str], int]:
        minute = int((time.time() if now is None else now) // 60)
        out: dict[tuple[str, str], int] = {}
        for key, buckets in list(self._channel_buckets.items()):
            total = sum(c for m, c in buckets.items() if minute - 60 < m <= minute)
            if total:
                out[key] = total
            elif all(m <= minute - 60 for m in buckets):
                del self._channel_buckets[key]
        return out

    def mqtt_channel_counts(self, now: float | None = None,
                            broker: str | None = None) -> dict[str, int]:
        """Eventi MQTT per canale nell'ultima ora (compresi quelli scartati dal filtro).
        Senza broker e' la somma su tutti i broker."""
        out: dict[str, int] = {}
        for (b, name), total in self._channel_totals(now).items():
            if broker is None or b == broker:
                out[name] = out.get(name, 0) + total
        return out

    def mqtt_channel_brokers(self, now: float | None = None) -> dict[str, list[str]]:
        """Canale -> broker che l'hanno visto nell'ultima ora (ordine di primo arrivo)."""
        out: dict[str, list[str]] = {}
        for (b, name) in self._channel_totals(now):
            if b:
                out.setdefault(name, []).append(b)
        return out

    def handle(self, ev: MeshEvent) -> None:
        if ev.source == "mqtt" and ev.channel:
            self._note_mqtt_channel(ev.channel, ev.rx_time, ev.broker)
            wanted = self.get_settings().get("mqtt_channels") or []
            if wanted and ev.channel not in wanted:
                self.filtered_channel += 1
                return  # canale non ascoltato: ignorato del tutto
        num = ev.from_node
        node = self.live.nodes.get(num)
        if node is None:
            node = self.live.nodes[num] = self._revive_node(num)
        self.live.mark_changed(num)

        # i replay del database nodi della radio hanno rx_time vecchio: non fanno regredire lo stato
        previous_heard = node["last_heard"]
        stale = previous_heard is not None and ev.rx_time < previous_heard
        no_time = ev.rx_time <= 0  # nodo del database della radio senza lastHeard
        if not stale and not no_time:
            node["last_heard"] = ev.rx_time
        if ev.source not in node["sources"]:
            node["sources"].append(ev.source)
        is_dup = seen_mqtt = False
        if ev.source == "mqtt" or (ev.source == "rf" and ev.packet_id):
            # i pacchetti RF senza id (dal database nodi della radio) non si deduplicano;
            # seen_mqtt: copia gia' arrivata dal broker (serve a contare i gateway)
            is_new, seen_mqtt = self.dedup.observe(num, ev.packet_id, ev.rx_time, ev.source)
            is_dup = not is_new
        if ev.source == "rf" and ev.radio_id and not no_time:
            heard_by = node.setdefault("heard_by", {})
            old = heard_by.get(ev.radio_id)
            if old is None or int(ev.rx_time) >= old["time"]:
                heard_by[ev.radio_id] = {"snr": ev.snr, "rssi": ev.rssi, "hops": ev.hops,
                                         "time": int(ev.rx_time)}
        # copie dello stesso pacchetto: si tiene l'SNR migliore e il minor numero di hop
        if ev.snr is not None and not stale and not no_time:
            prev = node["last_snr"]
            node["last_snr"] = ev.snr if not is_dup or prev is None else max(prev, ev.snr)
        if not stale and not no_time:
            self._update_hops(node, ev, is_dup)

        self._record_links(ev)  # anche per i duplicati: l'upsert tiene l'ultima copia ricevuta

        if ev.source == "mqtt":
            if is_dup:
                if ev.gateway_id and not self.dedup.note_gateway(num, ev.packet_id, ev.gateway_id):
                    return  # stesso gateway gia' contato (es. su un altro broker)
                # copia MQTT di un pacchetto gia' visto: se prima c'era solo l'RF e' il primo gateway
                node["mqtt_gateways"] = 1 if not seen_mqtt else (node["mqtt_gateways"] or 0) + 1
                return
            node["mqtt_gateways"] = 1
            if ev.gateway_id:
                self.dedup.note_gateway(num, ev.packet_id, ev.gateway_id)
        elif is_dup:
            self.store.upsert_node(node)  # copia RF: aggiorna solo "sentito da"
            if ev.kind == "text" and ev.radio_id:
                self._adopt_rf_copy(ev)
            return

        ev_pos = None  # (lat, lon, precision_bits, source) della posizione nell'evento
        kind, p = ev.kind, ev.payload
        if kind == "position" and (self._older(ev, node["position_time"])
                                   or (no_time and node["lat"] is not None)):
            pass  # senza orario la posizione della radio riempie solo i vuoti
        elif kind == "telemetry" and no_time:
            if all(node[f] is None for f in ("battery", "voltage", "channel_util", "air_util_tx")):
                self._update_telemetry(node, p)
            kind = "stale"
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
                   or ev.source == "rf" or bool(node.get("is_mine"))
                   or bool(node.get("is_favorite")))

        message = self._build_message(node, ev) if kind == "text" else None
        if message is not None:
            self.live.messages.append(message)

        if persist:
            self.store.upsert_node(node)
            if ev_pos is not None and not no_time:
                self.store.add_position(num, ev.rx_time, *ev_pos[:3], ev_pos[3])
            if kind == "telemetry":
                self.store.add_telemetry(num, ev.rx_time, p)
            if message is not None:
                self.store.add_message(message)

        if message is not None:
            self.on_message(message)

    def _revive_node(self, num: int) -> dict:
        return revive_node(self.store, num)

    def _update_hops(self, node: dict, ev: MeshEvent, is_dup: bool) -> None:
        num = ev.from_node
        if ev.source == "rf":
            if ev.hops is not None:
                self._rf_hops_time[num] = ev.rx_time
                prev = node["hops"]
                node["hops"] = ev.hops if not is_dup or prev is None else min(prev, ev.hops)
                node["hops_min"] = None  # salti esatti: il minimo non serve piu'
            return
        rf_time = self._rf_hops_time.get(num)
        if rf_time is not None and ev.rx_time - rf_time < _RF_HOPS_TTL:
            return  # un hops recente da RF e' piu' affidabile di quello dedotto da MQTT
        if is_dup:
            # altra copia dello stesso pacchetto: si tiene il minimo, senza cancellare
            if ev.hops is not None:
                prev = node["hops"]
                node["hops"] = ev.hops if prev is None else min(prev, ev.hops)
                node["hops_min"] = None
            elif ev.hops_min is not None and node["hops"] is None:
                prev = node.get("hops_min")
                node["hops_min"] = ev.hops_min if prev is None else min(prev, ev.hops_min)
        else:
            # pacchetto MQTT nuovo: sostituisce l'informazione (azzera anche i valori vecchi)
            node["hops"] = ev.hops
            node["hops_min"] = ev.hops_min

    def _persisted(self, num: int) -> bool:
        """Nodo che si archivia: in una nazione salvata, "mio" o preferito. Sconosciuto: no."""
        node = self.live.nodes.get(num)
        return node is not None and (node["country"] in self.get_settings()["saved_countries"]
                                     or bool(node.get("is_mine"))
                                     or bool(node.get("is_favorite")))

    def _link(self, ev: MeshEvent, a: int, b: int, source: str, snr) -> None:
        # MQTT: si archivia solo se almeno un estremo e' archiviato; l'RF sempre
        if ev.source == "rf" or self._persisted(a) or self._persisted(b):
            self.store.upsert_link(a, b, source, snr, ev.rx_time)

    def _record_links(self, ev: MeshEvent) -> None:
        if ev.kind == "neighbors":
            for neighbor, snr in ev.payload.neighbors:
                self._link(ev, neighbor, ev.from_node, "neighborinfo", snr)
        elif ev.kind == "traceroute" and ev.payload.request_id:
            # le richieste in transito non hanno request_id: solo le risposte contano
            for chain in traceroute_chains(ev):
                for (a, _), (b, snr) in zip(chain, chain[1:]):
                    self._link(ev, a, b, "traceroute", snr)
        gw = ev.gateway_num
        if (ev.source == "mqtt" and gw is not None and gw != ev.from_node
                and ev.relay_node and ev.relay_node == (ev.from_node & 0xFF)):
            # ricezione diretta dal mittente: il gateway ha sentito il nodo via radio
            self._link(ev, ev.from_node, gw, "mqtt_gateway", ev.snr)
        if ev.source == "rf" and ev.hops == 0 and ev.rx_time > 0 and not ev.via_mqtt:
            radio_num = self._radio_nodes.get(ev.radio_id)
            # niente link via MQTT (non e' un collegamento radio) ne' verso se stessi
            if radio_num is not None and ev.from_node != radio_num:
                self.store.upsert_link(ev.from_node, radio_num, "rf_direct", ev.snr, ev.rx_time)

    def radio_node(self, radio_id: str) -> int | None:
        return self._radio_nodes.get(radio_id)

    def set_radio_node(self, radio_id: str, num: int) -> None:
        self._radio_nodes[radio_id] = num

    def _adopt_rf_copy(self, ev: MeshEvent) -> None:
        """Copia RF di un testo gia' creato da MQTT: il messaggio passa alla radio che l'ha sentito."""
        key = f"{ev.from_node}:{ev.packet_id}"
        for message in self.live.messages:
            if message["key"] == key and message.get("radio_id") is None:
                message.update(radio_id=ev.radio_id, channel_index=_channel_index(ev.channel),
                               source="rf")
                self.store.add_message(message)  # no-op se gia' presente
                self.store.update_message_radio(key, ev.radio_id, message["channel_index"])
                self.on_message(dict(message))
                return

    @staticmethod
    def _older(ev: MeshEvent, current: float | None) -> bool:
        return current is not None and ev.rx_time < current

    def mark_local_radio(self, node_num: int) -> None:
        """Il nodo e' una radio collegata a questo server: e' anche "mio"."""
        node = self.live.nodes.get(node_num)
        if node is None:
            node = self.live.nodes[node_num] = self._revive_node(node_num)
        node["is_local_radio"] = True
        node["is_mine"] = True
        self.live.mark_changed(node_num)
        self.store.upsert_node(node, is_mine=True)

    def record_outgoing(self, radio_id: str, my_node_id: str, packet_id: int, text: str,
                        channel_index: int, to: str, status: str = "sent",
                        replaces: str | None = None,
                        time_: int | None = None) -> dict:
        """Registra un messaggio inviato da una radio locale e lo pubblica."""
        mine = self.live.nodes.get(int(my_node_id[1:], 16))
        message = {"key": f"out:{radio_id}:{packet_id}", "from": my_node_id,
                   "from_name": mine["long_name"] if mine else None, "to": to,
                   "channel": str(channel_index), "text": text, "time": int(time.time()) if time_ is None else time_,
                   "country": mine["country"] if mine else None, "source": "rf",
                   "direction": "out", "radio_id": radio_id, "channel_index": channel_index,
                   "packet_id": packet_id, "status": status, "broker": None}
        self.live.messages.append(message)
        self.store.add_message(message)
        # "replaces": il client sostituisce il messaggio provvisorio con questa chiave
        self.on_message({**message, "replaces": replaces} if replaces else message)
        return message

    def record_outgoing_mqtt(self, from_num: int, to_num: int, packet_id: int, text: str,
                             channel: str, now: float | None = None,
                             broker: str | None = None) -> dict:
        """Registra un testo pubblicato via MQTT dal proprio nodo.
        (from, id) entra subito nel dedup: l'eco che il broker ci rimanda viene scartato
        e non genera un secondo messaggio."""
        t = time.time() if now is None else now
        self.dedup.is_new(from_num, packet_id, t)
        mine = self.live.nodes.get(from_num)
        message = {"key": f"{from_num}:{packet_id}", "from": node_id(from_num),
                   "from_name": mine["long_name"] if mine else None, "to": node_id(to_num),
                   "channel": channel, "text": text, "time": int(t),
                   "country": mine["country"] if mine else None, "source": "mqtt",
                   "direction": "out", "via": "mqtt", "radio_id": None, "channel_index": None,
                   "packet_id": packet_id, "status": "sent", "broker": broker}
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
                        position_source=source, position_time=int(ev.rx_time) or None,
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
                "packet_id": ev.packet_id, "status": None, "broker": ev.broker}
