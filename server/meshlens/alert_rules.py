"""Regole di avviso scelte dall'utente (E6): validazione, archivio SQL e valutatori puri.

Il motore (RuleEngine) sta in coda al file. Nessun invio in radio/MQTT: gli avvisi diventano
voci della lista avvisi e notifiche (toast / Telegram) tramite Notifier."""
import json
import math
import re
from collections import deque
from dataclasses import dataclass
from typing import Iterable

from .notify import fold

RULE_KINDS = ("keyword", "snr_low", "geofence", "battery", "silent", "detection")
MAX_RULES = 100
NAME_MAX = 60
COOLDOWN_RANGE = (1, 1440)
SNR_HYSTERESIS_DB = 1.0
BATTERY_HYSTERESIS = 2
EVENT_KEEP_S = 3600
GEOFENCE_MIN_PRECISION_BITS = 20
SNR_MAX_SAMPLES = 300

MSG_RULE_KIND = "Tipo di avviso non valido"
MSG_RULE_NAME = "Il nome può avere al massimo 60 caratteri"
MSG_RULE_COOLDOWN = "La pausa deve essere tra 1 e 1440 minuti"
MSG_RULE_NODE_REQUIRED = "Scegli il nodo a cui si applica l'avviso"
MSG_RULE_CHANNEL = "Canale non valido"
MSG_RULE_WORDS = "Servono da 1 a 10 parole di almeno 2 e al massimo 32 caratteri"
MSG_RULE_SNR = "La soglia dell'SNR deve essere tra -30 e 20 dB"
MSG_RULE_WINDOW = "La finestra deve essere tra 15 e 1440 minuti"
MSG_RULE_SAMPLES = "I campioni minimi devono essere tra 1 e 50"
MSG_RULE_BATTERY = "La soglia della batteria deve essere un intero tra 1 e 99%"
MSG_RULE_SILENT = "La soglia del silenzio deve essere tra 0,25 e 168 ore"
MSG_RULE_POLYGON = "La zona deve avere da 3 a 64 punti con coordinate valide"
MSG_RULE_POLYGON_SHAPE = "La zona non deve avere lati che si incrociano né area nulla"
MSG_RULE_TRIGGER = "Il tipo di scatto deve essere uscita, entrata o entrambi"
MSG_RULE_MATCH = "Il testo da cercare può avere al massimo 32 caratteri"
MSG_RULE_PARAMS = "Parametri dell'avviso non validi"
MSG_RULES_MAX = "Hai raggiunto il limite di 100 avvisi su misura"
MSG_RULE_UNKNOWN = "Avviso su misura non trovato"
MSG_RULES_UNAVAILABLE = "Gli avvisi su misura non sono disponibili"

ERROR_MESSAGES: tuple[str, ...] = (
    MSG_RULE_KIND, MSG_RULE_NAME, MSG_RULE_COOLDOWN, MSG_RULE_NODE_REQUIRED, MSG_RULE_CHANNEL,
    MSG_RULE_WORDS, MSG_RULE_SNR, MSG_RULE_WINDOW, MSG_RULE_SAMPLES, MSG_RULE_BATTERY,
    MSG_RULE_SILENT, MSG_RULE_POLYGON, MSG_RULE_POLYGON_SHAPE, MSG_RULE_TRIGGER, MSG_RULE_MATCH,
    MSG_RULE_PARAMS, MSG_RULES_MAX, MSG_RULE_UNKNOWN, MSG_RULES_UNAVAILABLE)

NODE_REQUIRED_KINDS = ("snr_low", "geofence", "battery", "silent")
_CH_RE = re.compile(r"^ch:[^:\s]{1,64}:[0-7]$")
_MQTT_RE = re.compile(r"^mqtt:[^\x00-\x1f]{1,32}$")
_PARAM_KEYS = {"keyword": {"words", "whole_word"}, "snr_low": {"window_min", "min_samples"},
               "geofence": {"polygon", "trigger"}, "battery": set(), "silent": set(),
               "detection": {"match"}}
_PARAM_DEFAULTS = {"keyword": {"whole_word": False}, "snr_low": {"window_min": 60, "min_samples": 3},
                   "geofence": {"trigger": "exit"}, "battery": {}, "silent": {},
                   "detection": {"match": ""}}


@dataclass(frozen=True)
class Rule:
    id: int
    kind: str
    name: str
    enabled: bool
    node_num: int | None
    channel: str | None
    threshold: float | None
    params: dict
    cooldown_min: int
    created: float
    updated: float
    last_fired: float | None

    @classmethod
    def from_row(cls, row) -> "Rule":
        try:
            params = json.loads(row["params"] or "{}")
        except (TypeError, ValueError):
            params = {}
        if not isinstance(params, dict):
            params = {}
        return cls(row["id"], row["kind"], row["name"] or "", bool(row["enabled"]),
                   row["node_num"], row["channel"], row["threshold"], params,
                   row["cooldown_min"], row["created"], row["updated"], row["last_fired"])

    def to_json(self) -> dict:
        return {"id": self.id, "kind": self.kind, "name": self.name, "enabled": self.enabled,
                "node_id": None if self.node_num is None else "!%08x" % self.node_num,
                "channel": self.channel, "threshold": self.threshold, "params": self.params,
                "cooldown_min": self.cooldown_min, "created": self.created,
                "updated": self.updated, "last_fired": self.last_fired}


# ---- validazione ----
def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def _int_in(v, lo: int, hi: int) -> int | None:
    n = _num(v)
    if n is None or n != int(n) or not lo <= n <= hi:
        return None
    return int(n)


def _validate_words(raw) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError(MSG_RULE_WORDS)
    out: list[str] = []
    seen: set[str] = set()
    for w in raw:
        if not isinstance(w, str):
            raise ValueError(MSG_RULE_WORDS)
        w = w.strip()
        if not 2 <= len(w) <= 32:
            raise ValueError(MSG_RULE_WORDS)
        f = fold(w)
        if f not in seen:
            seen.add(f)
            out.append(w)
    if not 1 <= len(out) <= 10:
        raise ValueError(MSG_RULE_WORDS)
    return out


def _validate_params(kind: str, raw) -> dict:
    if not isinstance(raw, dict) or set(raw) - _PARAM_KEYS[kind]:
        raise ValueError(MSG_RULE_PARAMS)
    p = {**_PARAM_DEFAULTS[kind], **raw}
    if kind == "keyword":
        if "words" not in raw:
            raise ValueError(MSG_RULE_WORDS)
        if not isinstance(p["whole_word"], bool):
            raise ValueError(MSG_RULE_PARAMS)
        return {"words": _validate_words(raw["words"]), "whole_word": p["whole_word"]}
    if kind == "snr_low":
        window = _int_in(p["window_min"], 15, 1440)
        if window is None:
            raise ValueError(MSG_RULE_WINDOW)
        samples = _int_in(p["min_samples"], 1, 50)
        if samples is None:
            raise ValueError(MSG_RULE_SAMPLES)
        return {"window_min": window, "min_samples": samples}
    if kind == "geofence":
        if p["trigger"] not in ("exit", "enter", "both"):
            raise ValueError(MSG_RULE_TRIGGER)
        poly = normalize_polygon(raw.get("polygon"))
        err = polygon_error(poly)
        if err:
            raise ValueError(err)
        return {"polygon": poly, "trigger": p["trigger"]}
    if kind == "detection":
        m = p["match"]
        if not isinstance(m, str):
            raise ValueError(MSG_RULE_MATCH)
        m = m.strip()
        if len(m) > 32:
            raise ValueError(MSG_RULE_MATCH)
        return {"match": m}
    return {}


def validate_rule(data: dict, existing: Rule | None = None) -> dict:
    """Normalizza i campi "piatti" di una regola; con `existing` i campi mancanti si ereditano."""
    base: dict = {}
    if existing is not None:
        base = {"kind": existing.kind, "name": existing.name, "enabled": existing.enabled,
                "node_num": existing.node_num, "channel": existing.channel,
                "threshold": existing.threshold, "params": existing.params,
                "cooldown_min": existing.cooldown_min}
    d = {**base, **data}
    kind = d.get("kind")
    if kind not in RULE_KINDS:
        raise ValueError(MSG_RULE_KIND)
    name = d.get("name", "")
    if not isinstance(name, str) or len(name.strip()) > NAME_MAX:
        raise ValueError(MSG_RULE_NAME)
    enabled = d.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(MSG_RULE_PARAMS)
    cooldown = _int_in(d.get("cooldown_min", 60), *COOLDOWN_RANGE)
    if cooldown is None:
        raise ValueError(MSG_RULE_COOLDOWN)
    node = d.get("node_num")
    if node is not None and (not _is_int(node) or node < 0):
        raise ValueError(MSG_RULE_NODE_REQUIRED)
    if kind in NODE_REQUIRED_KINDS and node is None:
        raise ValueError(MSG_RULE_NODE_REQUIRED)
    channel = d.get("channel")
    if kind == "keyword" and channel is not None:
        if not isinstance(channel, str) or not (_CH_RE.match(channel) or _MQTT_RE.match(channel)):
            raise ValueError(MSG_RULE_CHANNEL)
    else:
        channel = None
    threshold = None
    if kind == "snr_low":
        t = _num(d.get("threshold"))
        if t is None or not -30 <= t <= 20:
            raise ValueError(MSG_RULE_SNR)
        threshold = t
    elif kind == "battery":
        t = _int_in(d.get("threshold"), 1, 99)
        if t is None:
            raise ValueError(MSG_RULE_BATTERY)
        threshold = float(t)
    elif kind == "silent":
        t = _num(d.get("threshold"))
        if t is None or not 0.25 <= t <= 168:
            raise ValueError(MSG_RULE_SILENT)
        threshold = t
    params_in = d.get("params", {})
    if existing is not None and existing.kind != kind and "params" not in data:
        params_in = {}
    return {"kind": kind, "name": name.strip(), "enabled": enabled, "node_num": node,
            "channel": channel, "threshold": threshold,
            "params": _validate_params(kind, params_in), "cooldown_min": cooldown}


# ---- geometria ----
def normalize_polygon(polygon) -> list[list[float]]:
    """Coppie [lon, lat] come liste di float; toglie il punto di chiusura uguale al primo."""
    if not isinstance(polygon, (list, tuple)):
        raise ValueError(MSG_RULE_POLYGON)
    out: list[list[float]] = []
    for p in polygon:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError(MSG_RULE_POLYGON)
        lon, lat = _num(p[0]), _num(p[1])
        if lon is None or lat is None or not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError(MSG_RULE_POLYGON)
        out.append([lon, lat])
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    if not 3 <= len(out) <= 64:
        raise ValueError(MSG_RULE_POLYGON)
    return out


def _cross(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _on_segment(p, a, b) -> bool:
    return (min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def _segments_intersect(a, b, c, d) -> bool:
    o1, o2, o3, o4 = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    if ((o1 > 0 > o2) or (o1 < 0 < o2)) and ((o3 > 0 > o4) or (o3 < 0 < o4)):
        return True
    return ((o1 == 0 and _on_segment(c, a, b)) or (o2 == 0 and _on_segment(d, a, b))
            or (o3 == 0 and _on_segment(a, c, d)) or (o4 == 0 and _on_segment(b, c, d)))


def polygon_error(polygon) -> str | None:
    """MSG_RULE_POLYGON (forma dei dati), MSG_RULE_POLYGON_SHAPE (geometria) o None."""
    try:
        pts = normalize_polygon(polygon)
    except ValueError as e:
        return str(e)
    n = len(pts)
    if max(p[0] for p in pts) - min(p[0] for p in pts) > 180:
        return MSG_RULE_POLYGON_SHAPE
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
               for i in range(n)) / 2
    if abs(area) < 1e-12 or any(pts[i] == pts[(i + 1) % n] for i in range(n)):
        return MSG_RULE_POLYGON_SHAPE
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue  # lati adiacenti
            if _segments_intersect(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n]):
                return MSG_RULE_POLYGON_SHAPE
    return None


def point_in_polygon(lon: float, lat: float, polygon: list[list[float]]) -> bool:
    """Ray casting piano su [lon, lat]; il bordo conta come dentro."""
    pt = (lon, lat)
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        if _cross(a, b, pt) == 0 and _on_segment(pt, a, b):
            return True
    inside = False
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        if (a[1] > lat) != (b[1] > lat):
            x = a[0] + (lat - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if lon < x:
                inside = not inside
    return inside


# ---- valutatori puri ----
def channel_selector(msg: dict) -> str | None:
    """Selettore del canale di un messaggio in broadcast; None per i messaggi diretti."""
    if msg.get("to") != "!ffffffff":
        return None
    radio = msg.get("radio_id")
    if radio:
        return f"ch:{radio}:{msg.get('channel_index') or 0}"
    if msg.get("source") == "mqtt" and msg.get("channel"):
        return f"mqtt:{msg['channel']}"
    return None


def keyword_match(rule: Rule, text: str) -> str | None:
    """La prima parola della regola trovata nel testo (come scritta nella regola)."""
    folded = fold(text)
    whole = bool(rule.params.get("whole_word"))
    for w in rule.params.get("words") or []:
        fw = fold(w)
        if not fw:
            continue
        if whole:
            if re.search(rf"(?<!\w){re.escape(fw)}(?!\w)", folded):
                return w
        elif fw in folded:
            return w
    return None


def snr_state(samples: Iterable[tuple[float, float]], now: float, rule: Rule,
              active: bool) -> float | None:
    """Media SNR nella finestra se la condizione e' attiva (con isteresi), altrimenti None."""
    window = rule.params.get("window_min", 60) * 60
    vals = [s for t, s in samples if now - window <= t <= now]
    if len(vals) < rule.params.get("min_samples", 3) or rule.threshold is None:
        return None
    mean = sum(vals) / len(vals)
    limit = rule.threshold + (SNR_HYSTERESIS_DB if active else 0)
    return round(mean, 1) if mean < limit else None


def battery_state(node: dict, rule: Rule, active: bool) -> int | None:
    b = node.get("battery")
    if b is None or b > 100 or rule.threshold is None:
        return None
    limit = rule.threshold + (BATTERY_HYSTERESIS if active else 0)
    return b if b < limit else None


def silent_state(node: dict, rule: Rule, now: float) -> float | None:
    heard = node.get("last_heard")
    if heard is None or rule.threshold is None:
        return None
    hours = (now - heard) / 3600
    return round(hours, 1) if hours > rule.threshold else None


def geofence_transition(trigger: str, was_inside: bool | None, inside: bool) -> str | None:
    if was_inside is None or was_inside == inside:
        return None
    kind = "enter" if inside else "exit"
    return kind if trigger in (kind, "both") else None


# ---- archivio ----
class RuleStore:
    """Tabella alert_rules sulla connessione principale (solo dal loop)."""

    def __init__(self, conn):
        self.conn = conn

    def list(self) -> list[Rule]:
        return [Rule.from_row(r) for r in self.conn.execute("SELECT * FROM alert_rules ORDER BY id")]

    def get(self, rule_id: int) -> Rule | None:
        r = self.conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
        return Rule.from_row(r) if r else None

    def create(self, fields: dict, now: float) -> Rule:
        count = self.conn.execute("SELECT COUNT(*) FROM alert_rules").fetchone()[0]
        if count >= MAX_RULES:
            raise ValueError(MSG_RULES_MAX)
        cur = self.conn.execute(
            "INSERT INTO alert_rules(kind, name, enabled, node_num, channel, threshold, params,"
            " cooldown_min, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (fields["kind"], fields["name"], int(fields["enabled"]), fields["node_num"],
             fields["channel"], fields["threshold"], json.dumps(fields["params"]),
             fields["cooldown_min"], now, now))
        return self.get(cur.lastrowid)

    def update(self, rule_id: int, fields: dict, now: float) -> Rule | None:
        cur = self.conn.execute(
            "UPDATE alert_rules SET kind=?, name=?, enabled=?, node_num=?, channel=?, threshold=?,"
            " params=?, cooldown_min=?, updated=? WHERE id=?",
            (fields["kind"], fields["name"], int(fields["enabled"]), fields["node_num"],
             fields["channel"], fields["threshold"], json.dumps(fields["params"]),
             fields["cooldown_min"], now, rule_id))
        return self.get(rule_id) if cur.rowcount else None

    def delete(self, rule_id: int) -> bool:
        return self.conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,)).rowcount > 0

    def touch_fired(self, rule_id: int, when: float) -> None:
        self.conn.execute("UPDATE alert_rules SET last_fired = ? WHERE id = ?", (when, rule_id))
