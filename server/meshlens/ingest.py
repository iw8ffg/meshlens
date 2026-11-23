"""Pipeline di ingestione: da MeshEvent a stato live e archivio."""
import base64
import time
from typing import Callable

from .dedup import Deduplicator
from .events import MeshEvent, TelemetryData, node_id
from .geo import CountryLocator
from .live import LiveState
from .store import Store

_DAY = 86400
_RF_BITS = 32
_RF_HOPS_TTL = 3600
MAX_HEARD_BY = 20  # gateway/radio ricordati per un messaggio inviato via MQTT  # s: per quanto un hops RF non viene scavalcato da uno MQTT


def _bits(precision_bits: int | None) -> int:
    return _RF_BITS if precision_bits is None else precision_bits


def _channel_index(channel: str) -> int | None:
    """Indice canale di un evento RF (stringa numerica); None per i canali MQTT per nome."""
    try:
        return int(channel)
    except (TypeError, ValueError):
        return None


def icon_char(codepoint: int) -> str:
    """Carattere dell'icona di un waypoint; "" se manca o non e' un codepoint valido."""
    if codepoint < 0x20 or 0xD800 <= codepoint <= 0xDFFF or codepoint > 0x10FFFF:
        return ""
    return chr(codepoint)


def _snr_at(snrs: list, i: int):
    return snrs[i] if i < len(snrs) else None


UNKNOWN_HOPS = (0, 0xFFFFFFFF)


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
            "is_favorite": False, "is_ignored": False, "hops_min": None, "public_key": None,
            "key_changed": None}


class Ingestor:
    def __init__(self, live: LiveState, store: Store, dedup: Deduplicator,
                 locator: CountryLocator, get_settings: Callable[[], dict],
                 on_message: Callable[[dict], None],
                 on_status: Callable[[str, str, str | None], None] | None = None,
                 on_waypoint: Callable[[dict], None] | None = None):
        self.live = live
        self.store = store
        self.dedup = dedup
        self.locator = locator
        self.get_settings = get_settings
        self.on_message = on_message
        self.on_status = on_status
        self.on_waypoint = on_waypoint
        self._telemetry_time: dict[tuple[int, str], float] = {}
        self._rf_hops_time: dict[int, float] = {}  # nodo -> istante dell'ultimo hops da RF
        self._radio_nodes: dict[str, int] = {}  # radio_id -> numero del nodo della radio
        # canali visti da MQTT (anche se scartati): (broker, canale) -> {minuto: conteggio}
        self._channel_buckets: dict[tuple[str, str], dict[int, int]] = {}
        self.filtered_channel = 0  # eventi MQTT scartati dal filtro mqtt_channels
        self.last_outcome = "ignored"  # esito dell'ultimo handle: ignored | dup | new
        # testi inviati via MQTT di recente: (from, id) -> (chiave, istante dell'invio);
        # una copia sentita da un altro gateway o da una radio locale li segna "heard"
        self._outgoing_mqtt: dict[tuple[int, int], tuple[str, float]] = {}

    def _note_mqtt_channel(self, name: str, t: float, broker: str | None = None) -> None:
        buckets = self._channel_buckets.setdefault((broker or "", name), {})
        minute = int(t // 60)
        buckets[minute] = buckets.get(minute, 0) + 1
        for m in [m for m in buckets if m < minute - 61]:
            del buckets[m]

    def prune(self, now: float | None = None) -> None:
        """Pota le mappe interne: nodi usciti da live e canali non piu' visti nell'ultima ora."""
        t = time.time() if now is None else now
        nodes = self.live.nodes
        for k in [k for k in list(self._telemetry_time) if k[0] not in nodes]:
            self._telemetry_time.pop(k, None)
        for n in [n for n, t0 in list(self._rf_hops_time.items())
                  if n not in nodes or t - t0 >= _RF_HOPS_TTL]:
            self._rf_hops_time.pop(n, None)
        minute = int(t // 60)
        for k in [k for k, b in list(self._channel_buckets.items())
                  if all(m <= minute - 60 for m in b)]:
            self._channel_buckets.pop(k, None)

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
        if not isinstance(ev, MeshEvent):
            self.last_outcome = "ignored"
            return
        self.last_outcome = "ignored"
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
        if ev.packet_id:
            # i pacchetti senza id (RF dal database nodi della radio, MQTT di bridge che
            # omettono l'id) non si deduplicano;
            # seen_mqtt: copia gia' arrivata dal broker (serve a contare i gateway)
            is_new, seen_mqtt = self.dedup.observe(num, ev.packet_id, ev.rx_time, ev.source)
            is_dup = not is_new
            if is_dup:
                self._note_heard(ev)
        self.last_outcome = "dup" if is_dup else "new"
        # rigioco S&F: non e' una ricezione radio, niente statistiche RF ne' collegamenti
        if ev.source == "rf" and ev.radio_id and not no_time and not ev.replayed:
            heard_by = node.setdefault("heard_by", {})
            old = heard_by.get(ev.radio_id)
            if old is None or int(ev.rx_time) >= old["time"]:
                heard_by[ev.radio_id] = {"snr": ev.snr, "rssi": ev.rssi, "hops": ev.hops,
                                         "time": int(ev.rx_time)}
        # copie dello stesso pacchetto: si tiene l'SNR migliore e il minor numero di hop
        if ev.snr is not None and not stale and not no_time and not ev.replayed:
            prev = node["last_snr"]
            node["last_snr"] = ev.snr if not is_dup or prev is None else max(prev, ev.snr)
        if not stale and not no_time and not ev.replayed:
            self._update_hops(node, ev, is_dup)

        if not ev.replayed:
            self._record_links(ev)  # anche per i duplicati: l'upsert tiene l'ultima copia ricevuta

        if ev.source == "mqtt":
            if is_dup:
                if ev.gateway_id and not self.dedup.note_gateway(num, ev.packet_id, ev.gateway_id):
                    return  # stesso gateway gia' contato (es. su un altro broker)
                # copia MQTT di un pacchetto gia' visto: se prima c'era solo l'RF e' il primo gateway
                node["mqtt_gateways"] = 1 if not seen_mqtt else (node["mqtt_gateways"] or 0) + 1
                return
            node["mqtt_gateways"] = 1
            if ev.gateway_id and ev.packet_id:
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
            if p.variant == "device" and all(
                    node[f] is None for f in ("battery", "voltage", "channel_util", "air_util_tx")):
                self._update_telemetry(node, p)
            kind = "stale"
        elif kind == "telemetry" and self._older(ev, self._telemetry_time.get((num, p.variant))):
            kind = "stale"
        elif kind == "position":
            ev_pos = (p.lat, p.lon, p.precision_bits, ev.source)
            self._update_position(node, ev, *ev_pos)
        elif kind == "nodeinfo":
            self._update_identity(node, p, ev.rx_time or time.time(), replay=stale or no_time,
                                  rf=ev.source == "rf")
        elif kind == "mapreport":
            self._update_identity(node, p, ev.rx_time or time.time(), replay=stale or no_time)
            if p.firmware_version:
                node["firmware"] = p.firmware_version
            if (p.lat is not None and p.lon is not None
                    and not self._older(ev, node["position_time"])):
                ev_pos = (p.lat, p.lon, p.precision_bits, "mqtt_map")
                self._update_position(node, ev, *ev_pos)
        elif kind == "telemetry":
            self._telemetry_time[(num, p.variant)] = ev.rx_time
            if p.variant == "device":
                self._update_telemetry(node, p)
        elif kind == "waypoint":
            self._handle_waypoint(node, ev)

        persist = self.persists(node, ev.source)

        message = self._build_message(node, ev) if kind == "text" else None
        if message is not None:
            self.live.messages.append(message)

        if persist:
            self.store.upsert_node(node)
            if ev_pos is not None and not no_time:
                self.store.add_position(num, ev.rx_time, *ev_pos[:3], ev_pos[3])
            if kind == "telemetry":
                if p.variant == "device":
                    self.store.add_telemetry(num, ev.rx_time, p)
                else:
                    self.store.add_metrics(num, ev.rx_time, p.variant, p.metrics)
            if message is not None:
                self.store.add_message(message)

        if message is not None:
            self.on_message(message)

    def persists(self, node: dict, source: str) -> bool:
        """Il nodo (e cio' che porta) si archivia: in una nazione salvata, arrivato in radio,
        "mio" o preferito."""
        return (node["country"] in self.get_settings()["saved_countries"]
                or source == "rf" or bool(node.get("is_mine"))
                or bool(node.get("is_favorite")))

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
        return self.is_archived(num)

    def is_archived(self, num: int) -> bool:
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
                # un hop ignoto (0 o 0xFFFFFFFF) spezza la catena: niente nodi o link inventati
                segment: list[tuple[int, float | None]] = []
                for hop in chain + [(0, None)]:
                    if hop[0] in UNKNOWN_HOPS:
                        for (a, _), (b, snr) in zip(segment, segment[1:]):
                            self._link(ev, a, b, "traceroute", snr)
                        segment = []
                    else:
                        segment.append(hop)
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
            # un nostro invio MQTT resta tale: la copia RF lo segna solo come "sentito"
            if (message["key"] == key and message.get("radio_id") is None
                    and message.get("direction") != "out"):
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
                        time_: int | None = None, reply_id: int | None = None,
                        emoji: bool = False) -> dict:
        """Registra un messaggio inviato da una radio locale e lo pubblica."""
        mine = self.live.nodes.get(int(my_node_id[1:], 16))
        message = {"key": f"out:{radio_id}:{packet_id}", "from": my_node_id,
                   "from_name": mine["long_name"] if mine else None, "to": to,
                   "channel": str(channel_index), "text": text, "time": int(time.time()) if time_ is None else time_,
                   "country": mine["country"] if mine else None, "source": "rf",
                   "direction": "out", "radio_id": radio_id, "channel_index": channel_index,
                   "packet_id": packet_id, "status": status, "broker": None,
                   "reply_id": reply_id, "emoji": emoji, "pki": False, "error": None}
        self.live.messages.append(message)
        self.store.add_message(message)
        # "replaces": il client sostituisce il messaggio provvisorio con questa chiave
        self.on_message({**message, "replaces": replaces} if replaces else message)
        return message

    def record_outgoing_mqtt(self, from_num: int, to_num: int, packet_id: int, text: str,
                             channel: str, now: float | None = None,
                             broker: str | None = None, reply_id: int | None = None,
                             emoji: bool = False, status: str = "sending") -> dict:
        """Registra un testo pubblicato via MQTT dal proprio nodo ("sending" fino al PUBACK).
        (from, id) entra subito nel dedup: l'eco che il broker ci rimanda viene scartato
        e non genera un secondo messaggio."""
        t = time.time() if now is None else now
        self.dedup.is_new(from_num, packet_id, t)
        self._track_outgoing_mqtt((from_num, packet_id), f"{from_num}:{packet_id}", t)
        mine = self.live.nodes.get(from_num)
        message = {"key": f"{from_num}:{packet_id}", "from": node_id(from_num),
                   "from_name": mine["long_name"] if mine else None, "to": node_id(to_num),
                   "channel": channel, "text": text, "time": int(t),
                   "country": mine["country"] if mine else None, "source": "mqtt",
                   "direction": "out", "via": "mqtt", "radio_id": None, "channel_index": None,
                   "packet_id": packet_id, "status": status, "broker": broker,
                   "reply_id": reply_id, "emoji": emoji, "pki": False, "error": None,
                   "heard_by": None}
        self.live.messages.append(message)
        self.store.add_message(message)
        self.on_message(message)
        return message

    def _track_outgoing_mqtt(self, key: tuple[int, int], msg_key: str, t: float) -> None:
        window = self.dedup.window_s
        for k in [k for k, (_, t0) in self._outgoing_mqtt.items() if t - t0 >= window]:
            del self._outgoing_mqtt[k]
        self._outgoing_mqtt[key] = (msg_key, t)

    def _live_message(self, key: str) -> dict | None:
        for message in reversed(self.live.messages):
            if message["key"] == key:
                return message
        return None

    def mqtt_publish_result(self, key: str, ok: bool, error: str | None) -> None:
        """Esito del broker per un invio MQTT (PUBACK o timeout): "sent" o "failed".
        Un messaggio gia' sentito in radio non torna indietro."""
        message = self._live_message(key)
        if message is not None:
            status = message.get("status")
        else:  # non piu' in memoria: lo stato corrente e' nel database
            state = self.store.message_state(key)
            status = state[0] if state is not None else None
        if status != "sending":
            return
        if ok:
            self.set_status(key, "sent")
        else:
            self.set_status(key, "failed", error)

    def _note_heard(self, ev: MeshEvent) -> None:
        """Copia di un nostro invio MQTT: se l'ha sentita un gateway diverso dal nostro nodo
        (non l'eco del nostro publish) o una radio locale, il messaggio e' andato in onda."""
        entry = self._outgoing_mqtt.get((ev.from_node, ev.packet_id))
        if entry is None:
            return
        key, t0 = entry
        if ev.rx_time - t0 >= self.dedup.window_s:
            del self._outgoing_mqtt[(ev.from_node, ev.packet_id)]
            return
        if ev.source == "mqtt":
            gw = (ev.gateway_id or "").lower()
            if not gw or gw == node_id(ev.from_node):
                return  # eco del nostro publish
            who = gw
        elif ev.source == "rf" and ev.radio_id and not ev.via_mqtt and not ev.replayed:
            radio_num = self._radio_nodes.get(ev.radio_id)
            who = node_id(radio_num) if radio_num is not None else f"radio:{ev.radio_id}"
        else:
            return
        message = self._live_message(key)
        if message is not None:
            heard = list(message.get("heard_by") or [])
        else:  # non piu' in memoria: si parte da quanto e' gia' nel database
            state = self.store.message_state(key)
            heard = list(state[1]) if state is not None else []
        if who in heard or len(heard) >= MAX_HEARD_BY:
            return
        heard.append(who)
        self.store.update_message_heard(key, heard)
        if message is not None:
            message.update(status="heard", error=None, heard_by=heard)
        if self.on_status is not None:
            self.on_status(key, "heard", None, heard_by=heard)

    def set_status(self, key: str, status: str, error: str | None = None) -> None:
        self.store.update_message_status(key, status, error)
        for message in self.live.messages:
            if message["key"] == key:
                message["status"] = status
                message["error"] = error
        if self.on_status is not None:
            self.on_status(key, status, error)

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
    def _update_identity(node: dict, p, t: float, replay: bool = False, rf: bool = False) -> None:
        for field in ("long_name", "short_name", "hw_model", "role"):
            value = getattr(p, field)
            if value:
                node[field] = value
        key = getattr(p, "public_key", None)  # mapreport non porta la chiave
        if key:  # vuota o assente (firmware vecchio): non e' un cambio
            b64 = base64.b64encode(key).decode()
            if replay:
                # replay del database nodi (orario vecchio o assente): riempie solo il vuoto,
                # non scavalca una chiave piu' recente e non e' mai un cambio
                if node.get("public_key") is None:
                    node["public_key"] = b64
                return
            if node.get("public_key") and node["public_key"] != b64:
                if not rf:
                    return  # MQTT non e' autorevole: riempie solo una chiave mancante
                node["key_changed"] = t
            node["public_key"] = b64

    def _handle_waypoint(self, node: dict, ev: MeshEvent) -> None:
        """Waypoint ricevuto: scaduto o senza coordinate vale come eliminazione."""
        p = ev.payload
        now = ev.rx_time or time.time()
        if (p.expire and p.expire <= now) or p.lat is None or p.lon is None:
            stored = self.store.get_waypoint(p.id)
            if stored is not None and stored["from_num"] != ev.from_node:
                return  # solo chi l'ha creato puo' eliminarlo
            self.store.delete_waypoint(p.id)
            if self.on_waypoint is not None:
                self.on_waypoint({"deleted": p.id})
            return
        wp = {"id": p.id, "from": node_id(ev.from_node), "from_name": node["long_name"],
              "lat": p.lat, "lon": p.lon, "name": p.name, "description": p.description,
              "icon": icon_char(p.icon), "expire": p.expire or None,
              "locked_to": node_id(p.locked_to) if p.locked_to else None,
              "time": int(ev.rx_time), "source": ev.source, "radio_id": ev.radio_id,
              "channel": ev.channel, "mine": ev.from_node in self._radio_nodes.values()}
        stored = self.store.get_waypoint(p.id)
        if (stored is not None and stored["from_num"] != ev.from_node
                and (stored["locked_to"] or stored["from_num"] in self._radio_nodes.values())):
            return  # waypoint bloccato o di una radio locale: un altro nodo non lo sostituisce
        country = self.locator.locate(p.lat, p.lon)
        if ev.source == "rf" or country in self.get_settings()["saved_countries"]:
            self.store.upsert_waypoint(
                {**wp, "from_num": ev.from_node, "icon": p.icon if wp["icon"] else 0,
                 "locked_to": p.locked_to or None, "country": country})
            if self.on_waypoint is not None:
                self.on_waypoint(wp)

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
                "packet_id": ev.packet_id, "status": None, "broker": ev.broker,
                "reply_id": ev.payload.reply_id, "emoji": ev.payload.emoji, "pki": ev.pki,
                "error": None}
