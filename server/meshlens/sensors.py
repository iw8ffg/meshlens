"""Detection Sensor e Paxcounter (E9): eventi dei sensori salvati e metriche per i grafici.

I payload arrivano da pacchetti non fidati (un messaggio MQTT decifrato con la chiave sbagliata
puo' cadere su queste porte con byte qualsiasi): ogni errore di lettura scarta l'evento."""
import logging
import re
from typing import Callable

from .notify import fold

log = logging.getLogger(__name__)

DETECTION_TEXT_MAX = 200

_DETECTED = ("detected", "rilevat", "triggered")
_CLEARED = ("cleared", "clear", "ripristinat")
_NEGATIONS = ("not", "no", "non", "nessun", "nessuna", "never")
_WORD_RE = re.compile(r"[^\W_]+")


def clean_detection_text(text: str | None) -> str:
    """Toglie BEL (0x07) e gli altri caratteri di controllo (spazio escluso), poi strip e taglio."""
    if not text:
        return ""
    return "".join(c for c in text if ord(c) >= 32).strip()[:DETECTION_TEXT_MAX]


def detection_value(text: str) -> float | None:
    """1.0 rilevato, 0.0 cessato, None se il testo non lo dice."""
    words = _WORD_RE.findall(fold(text))
    value = None
    for i, w in enumerate(words):  # decide l'ultima parola chiave (la coda inviata dal firmware)
        if w.startswith(_DETECTED):
            v = 1.0
        elif w in _CLEARED or w.startswith("ripristinat"):
            v = 0.0
        else:
            continue
        if i > 0 and words[i - 1] in _NEGATIONS:
            v = 1.0 - v  # "not detected" = cessato
        value = v
    return value


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
        "WHERE node_num = ? AND time >= ? "
        "AND COALESCE((SELECT is_ignored FROM nodes WHERE num = ?), 0) = 0 "  # ignorato: nascosto
        "ORDER BY time DESC, id DESC LIMIT ?",
        (num, since, num, limit))]


class SensorService:
    def __init__(self, conn, store, publish: Callable[[dict], None],
                 get_node: Callable[[int], dict | None],
                 persists: Callable[[dict, str], bool],
                 on_detection: Callable[[int, str, float | None], None] = lambda *a: None,
                 is_ignored: Callable[[int], bool] | None = None) -> None:
        self.conn = conn
        self.store = store
        self.publish = publish
        self.get_node = get_node
        self.persists = persists
        self.on_detection = on_detection
        self.is_ignored = is_ignored

    def on_event(self, ev, outcome: str) -> None:
        if ev.kind not in ("detection", "paxcounter") or outcome != "new" or ev.replayed:
            return
        if ev.kind == "detection":
            self._detection(ev)
        else:
            self._paxcounter(ev)

    def _detection(self, ev) -> None:
        text = clean_detection_text(getattr(ev.payload, "text", None))
        if not text:
            return  # solo caratteri di controllo: niente evento, niente regole
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
        if self.is_ignored is not None and self.is_ignored(ev.from_node):
            return  # salvato ma nascosto (contratto 4.6)
        self.publish({"type": "sensor_event",
                      "event": sensor_event_json(row, "!%08x" % ev.from_node)})

    def _paxcounter(self, ev) -> None:
        node = self.get_node(ev.from_node)
        if node is None or not self.persists(node, ev.source):
            return
        metrics = parse_paxcount(getattr(ev.payload, "payload", b""))
        if metrics:
            self.store.add_metrics(ev.from_node, ev.rx_time, "paxcounter", metrics)
