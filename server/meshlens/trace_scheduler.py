"""Traceroute periodici verso nodi scelti (E14).

Un giro ogni 60 s, al piu' un traceroute trasmesso per giro, solo tramite
RadioManager.traceroute(..., auto=True) (che applica il limite firmware di 30 s per radio).
Regole: >= 60 min fra due traceroute trasmessi verso lo stesso nodo (moltiplicato dopo i
fallimenti), >= 60 s fra due automatici sulla stessa radio, tetto orario globale
(traceroute_auto_max_per_hour). Gli esiti "non trasmesso" (throttled/busy/no_radio) non
consumano l'intervallo. Tutte le scritture SQL avvengono sul loop con la connessione principale.
"""
import logging
import time
from typing import Callable

from .radio import RadioBusy
from .radio_manager import NoRadioConnected, TracerouteThrottled

log = logging.getLogger(__name__)

TICK_S = 60
MIN_INTERVAL_MIN = 60
MAX_INTERVAL_MIN = 10080
RADIO_GAP_S = 60
DEFER_NOT_SENT_S = 300
MAX_TRACE_TARGETS = 20
THROTTLE_MARGIN_S = 5

INTERVAL_MSG = "Intervallo non valido: da 60 minuti a 7 giorni"
OWN_NODE_MSG = "Non si può programmare un traceroute verso un tuo nodo"
NODE_NOT_FOUND_MSG = "Nodo non trovato"
BAD_RADIO_MSG = "Radio non valida"
TOO_MANY_MSG = "Troppi nodi con traceroute periodico: massimo 20"

_COLUMNS = ("enabled", "interval_min", "radio_id", "last_run", "last_status",
            "last_traceroute_id", "fail_count")


def mult(fail_count: int) -> int:
    """Moltiplicatore dell'intervallo dopo fallimenti consecutivi."""
    if fail_count < 3:
        return 1
    if fail_count < 6:
        return 2
    return 4


def _node_id(num: int) -> str:
    return f"!{num:08x}"


def _num(node_id: str) -> int:
    if not isinstance(node_id, str) or len(node_id) != 9 or not node_id.startswith("!"):
        raise ValueError(NODE_NOT_FOUND_MSG)
    try:
        return int(node_id[1:], 16)
    except ValueError:
        raise ValueError(NODE_NOT_FOUND_MSG) from None


def _target_json(r) -> dict:
    return {"node_id": _node_id(r["node_num"]), "enabled": bool(r["enabled"]),
            "interval_min": r["interval_min"], "radio_id": r["radio_id"],
            "created": r["created"], "last_run": r["last_run"],
            "last_status": r["last_status"], "last_traceroute_id": r["last_traceroute_id"],
            "fail_count": r["fail_count"]}


def _update(conn, num: int, **fields) -> None:
    cols = [k for k in fields if k in _COLUMNS]  # nomi di colonna: costanti del modulo
    if not cols:
        return
    conn.execute(f"UPDATE trace_targets SET {', '.join(c + '=?' for c in cols)} "
                 "WHERE node_num=?", (*(fields[c] for c in cols), num))


class TraceScheduler:
    def __init__(self, conn, store, manager, live, bus, get_settings: Callable[[], dict],
                 clock: Callable[[], float] = time.time):
        self.conn, self.store, self.manager, self.live = conn, store, manager, live
        self.bus, self.get_settings, self.clock = bus, get_settings, clock
        self._defer: dict[int, float] = {}  # nodo -> non prima di
        self._last_auto: dict[str, float] = {}  # radio -> ultimo automatico trasmesso

    # ---- bersagli ----------------------------------------------------
    def _rows(self):
        return self.conn.execute(
            "SELECT * FROM trace_targets ORDER BY created, node_num").fetchall()

    def list_targets(self) -> list[dict]:
        return [_target_json(r) for r in self._rows()]

    def get(self, node_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM trace_targets WHERE node_num=?",
                              (_num(node_id),)).fetchone()
        return _target_json(r) if r else None

    def _publish(self) -> None:
        self.bus.publish({"type": "trace_targets", "targets": self.list_targets()})

    def _radio_ids(self) -> set[str]:
        try:
            return {r["id"] for r in self.manager.radios()}
        except Exception:  # noqa: BLE001 - nessun gestore: nessuna radio nota
            return set()

    def upsert(self, node_id: str, *, enabled: bool = True, interval_min: int,
               radio_id: str | None = None) -> dict:
        num = _num(node_id)
        if (not isinstance(interval_min, int) or isinstance(interval_min, bool)
                or not MIN_INTERVAL_MIN <= interval_min <= MAX_INTERVAL_MIN):
            raise ValueError(INTERVAL_MSG)
        node = self.live.nodes.get(num)
        existing = self.conn.execute("SELECT created FROM trace_targets WHERE node_num=?",
                                     (num,)).fetchone()
        if node is None and existing is None:
            raise ValueError(NODE_NOT_FOUND_MSG)
        if node is not None and node.get("is_mine"):
            raise ValueError(OWN_NODE_MSG)
        if radio_id is not None and radio_id not in self._radio_ids():
            raise ValueError(BAD_RADIO_MSG)
        if existing is None:
            count = self.conn.execute("SELECT COUNT(*) FROM trace_targets").fetchone()[0]
            if count >= MAX_TRACE_TARGETS:
                raise ValueError(TOO_MANY_MSG)
            # Ultimo automatico gia' trasmesso verso il nodo: rimuovere e riaggiungere
            # il bersaglio non azzera l'intervallo.
            last = self.conn.execute(
                "SELECT MAX(time) FROM traceroutes WHERE target_num=? AND auto=1",
                (num,)).fetchone()[0]
            self.conn.execute(
                "INSERT INTO trace_targets(node_num, enabled, interval_min, radio_id, created, "
                "last_run) VALUES(?,?,?,?,?,?)", (num, 1 if enabled else 0, interval_min,
                                                   radio_id, self.clock(), last))
        else:
            _update(self.conn, num, enabled=1 if enabled else 0, interval_min=interval_min,
                    radio_id=radio_id)
        self.conn.commit()
        self._defer.pop(num, None)
        self._publish()
        return self.get(node_id)

    def remove(self, node_id: str) -> bool:
        num = _num(node_id)
        cur = self.conn.execute("DELETE FROM trace_targets WHERE node_num=?", (num,))
        self.conn.commit()
        self._defer.pop(num, None)
        if cur.rowcount:
            self._publish()
        return bool(cur.rowcount)

    def status(self) -> dict:
        s = self.get_settings()
        return {"enabled": bool(s.get("traceroute_auto_enabled")),
                "max_per_hour": s.get("traceroute_auto_max_per_hour", 6),
                "targets": self.list_targets()}

    # ---- giro --------------------------------------------------------
    def _sent_last_hour(self, now: float) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM traceroutes WHERE auto=1 AND time >= ?",
                                 (now - 3600,)).fetchone()[0]

    def _candidates(self, now: float) -> list:
        due = []
        for r in self.conn.execute(
                "SELECT * FROM trace_targets WHERE enabled=1 "
                "ORDER BY (last_run IS NOT NULL), last_run, created, node_num"):
            eff = r["interval_min"] * 60 * mult(r["fail_count"])
            if r["last_run"] is not None and now - r["last_run"] < eff:
                continue
            if now < self._defer.get(r["node_num"], 0):
                continue
            due.append(r)
        return due

    async def tick(self) -> str | None:
        """Un giro: al piu' un traceroute trasmesso. Restituisce l'esito (per i test)."""
        s = self.get_settings()
        if not s.get("traceroute_auto_enabled"):
            return "disabled"
        now = self.clock()
        if self._sent_last_hour(now) >= s.get("traceroute_auto_max_per_hour", 6):
            return "cap"
        for r in self._candidates(now):
            num = r["node_num"]
            node = self.live.nodes.get(num)
            if node is None or node.get("is_mine") or node.get("is_ignored"):
                continue
            rid = r["radio_id"]
            if rid is not None and now - self._last_auto.get(rid, float("-inf")) < RADIO_GAP_S:
                self._defer[num] = self._last_auto[rid] + RADIO_GAP_S
                continue
            return await self._run(num, rid, now, r["interval_min"])
        return None

    async def _run(self, num: int, rid: str | None, now: float,
                   interval_min: int = MIN_INTERVAL_MIN) -> str:
        r_interval = interval_min
        try:
            result = await self.manager.traceroute(_node_id(num), rid, auto=True)
        except TracerouteThrottled as e:
            outcome = "throttled"
            _update(self.conn, num, last_status=outcome)
            self._defer[num] = now + e.wait_s + THROTTLE_MARGIN_S
        except RadioBusy:
            outcome = "busy"
            _update(self.conn, num, last_status=outcome)
            self._defer[num] = now + DEFER_NOT_SENT_S
        except (NoRadioConnected, KeyError):  # KeyError: radio scelta eliminata
            outcome = "no_radio"
            _update(self.conn, num, last_status=outcome)
            self._defer[num] = now + DEFER_NOT_SENT_S
        except ValueError:
            outcome = "failed"
            self.conn.execute(
                "UPDATE trace_targets SET last_run=?, last_status='failed', "
                "fail_count=fail_count+1 WHERE node_num=?", (now, num))
        except Exception:  # noqa: BLE001 - es. DB in errore dopo l'invio
            # Il pacchetto potrebbe essere partito: mai ritrasmettere al giro dopo.
            # Rinvio in memoria (vale anche se il DB non accetta scritture).
            log.exception("Traceroute automatico verso %s: errore inatteso", _node_id(num))
            self._defer[num] = now + max(r_interval * 60, DEFER_NOT_SENT_S)
            if rid:
                self._last_auto[rid] = now
            try:
                _update(self.conn, num, last_run=now, last_status="error")
                self.conn.commit()
            except Exception:  # noqa: BLE001 - best-effort
                log.warning("Traceroute automatico: stato del nodo non salvato")
            return "error"
        else:
            outcome = "sent"
            _update(self.conn, num, last_run=now, last_status="pending",
                    last_traceroute_id=result["id"])
            used = result.get("radio_id") or rid
            if used:
                self._last_auto[used] = now
        self.conn.commit()
        self._publish()
        return outcome

    # ---- esiti -------------------------------------------------------
    def _finalize(self, num: int, status: str) -> None:
        if status == "ok":
            _update(self.conn, num, last_status=status, fail_count=0)
        else:
            self.conn.execute("UPDATE trace_targets SET last_status=?, fail_count=fail_count+1 "
                              "WHERE node_num=?", (status, num))

    def on_bus(self, msg: dict) -> None:
        if msg.get("type") != "traceroute":
            return
        result = msg.get("result") or {}
        tid, status = result.get("id"), result.get("status")
        if tid is None or not status or status == "pending":
            return
        rows = self.conn.execute(
            "SELECT node_num FROM trace_targets WHERE last_traceroute_id=?", (tid,)).fetchall()
        if not rows:
            return
        for r in rows:
            self._finalize(r["node_num"], status)
        self.conn.commit()
        self._publish()

    def reconcile(self) -> None:
        """All'avvio: i bersagli ancora "pending" adottano l'esito della riga traceroutes
        (gia' chiusa da expire_pending_traceroutes)."""
        rows = self.conn.execute(
            "SELECT t.node_num, r.status FROM trace_targets t JOIN traceroutes r "
            "ON r.id = t.last_traceroute_id WHERE t.last_status='pending'").fetchall()
        changed = False
        for r in rows:
            if r["status"] and r["status"] != "pending":
                self._finalize(r["node_num"], r["status"])
                changed = True
        if changed:
            self.conn.commit()
