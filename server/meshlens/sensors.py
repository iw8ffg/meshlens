"""Detection Sensor e Paxcounter (E9): eventi dei sensori salvati e metriche per i grafici.

I payload arrivano da pacchetti non fidati (un messaggio MQTT decifrato con la chiave sbagliata
puo' cadere su queste porte con byte qualsiasi): ogni errore di lettura scarta l'evento."""
import logging
from typing import Callable

from .notify import fold

log = logging.getLogger(__name__)

DETECTION_TEXT_MAX = 200

_DETECTED = ("detected", "rilevat", "triggered")
_CLEARED = ("cleared", "clear", "ripristinat")


def clean_detection_text(text: str | None) -> str:
    """Toglie BEL (0x07) e gli altri caratteri di controllo (spazio escluso), poi strip e taglio."""
    if not text:
        return ""
    return "".join(c for c in text if ord(c) >= 32).strip()[:DETECTION_TEXT_MAX]


def detection_value(text: str) -> float | None:
    """1.0 rilevato, 0.0 cessato, None se il testo non lo dice."""
    f = fold(text)
    if any(w in f for w in _DETECTED):
        return 1.0
    if any(w in f for w in _CLEARED):
        return 0.0
    return None


def parse_paxcount(payload: bytes) -> dict[str, float]:
    """Paxcount -> {"wifi", "ble", "uptime"}; {} se i byte non sono un Paxcount valido.

    Un payload vuoto e' un Paxcount valido di proto3 con tutti i campi a zero."""
    try:
        from meshtastic.protobuf import paxcount_pb2
        p = paxcount_pb2.Paxcount.FromString(bytes(payload))
        return {"wifi": float(p.wifi), "ble": float(p.ble), "uptime": float(p.uptime)}
    except Exception:  # noqa: BLE001 - DecodeError e qualunque altro errore di lettura
        return {}


def sensor_event_json(row, node_id: str) -> dict:
    return {"id": row["id"], "node_id": node_id, "time": row["time"], "kind": row["kind"],
            "text": row["text"], "value": row["value"], "source": row["source"]}


def list_events(conn, num: int, since: float, limit: int = 200) -> list[dict]:
    node_id = "!%08x" % num
    return [sensor_event_json(r, node_id) for r in conn.execute(
        "SELECT id, time, kind, text, value, source FROM sensor_events "
        "WHERE node_num = ? AND time >= ? ORDER BY time DESC, id DESC LIMIT ?",
        (num, since, limit))]


class SensorService:
    def __init__(self, conn, store, publish: Callable[[dict], None],
                 get_node: Callable[[int], dict | None],
                 persists: Callable[[dict, str], bool],
                 on_detection: Callable[[int, str, float | None], None] = lambda *a: None) -> None:
        self.conn = conn
        self.store = store
        self.publish = publish
        self.get_node = get_node
        self.persists = persists
        self.on_detection = on_detection

    def on_event(self, ev, outcome: str) -> None:
        if ev.kind not in ("detection", "paxcounter") or outcome != "new" or ev.replayed:
            return
        if ev.kind == "detection":
            self._detection(ev)
        else:
            self._paxcounter(ev)

    def _detection(self, ev) -> None:
        text = clean_detection_text(getattr(ev.payload, "text", None))
        value = detection_value(text)
        try:
            self.on_detection(ev.from_node, text, value)  # le regole non richiedono il nodo salvato
        except Exception:  # noqa: BLE001 - le regole non devono fermare il salvataggio
            log.exception("Regole del sensore non valutate")
        node = self.get_node(ev.from_node)
        if node is None or not self.persists(node, ev.source):
            return
        cur = self.conn.execute(
            "INSERT INTO sensor_events(node_num, time, kind, text, value, source, radio_id,"
            " broker, packet_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (ev.from_node, ev.rx_time, "detection", text, value, ev.source, ev.radio_id,
             ev.broker, ev.packet_id))
        row = {"id": cur.lastrowid, "time": ev.rx_time, "kind": "detection", "text": text,
               "value": value, "source": ev.source}
        self.publish({"type": "sensor_event",
                      "event": sensor_event_json(row, "!%08x" % ev.from_node)})

    def _paxcounter(self, ev) -> None:
        node = self.get_node(ev.from_node)
        if node is None or not self.persists(node, ev.source):
            return
        metrics = parse_paxcount(getattr(ev.payload, "payload", b""))
        if metrics:
            self.store.add_metrics(ev.from_node, ev.rx_time, "paxcounter", metrics)
