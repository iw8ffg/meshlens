"""Accesso ai dati: nodi, posizioni, messaggi, telemetria."""
import json
import sqlite3
import time
from dataclasses import dataclass

from .events import TelemetryData

_NODE_FIELDS = ("id", "long_name", "short_name", "hw_model", "role", "firmware", "lat", "lon",
                "precision_bits", "position_source", "position_time", "country", "last_heard",
                "battery", "voltage", "channel_util", "air_util_tx", "mqtt_gateways",
                "last_snr", "hops", "hops_min", "public_key", "key_changed")
_DAY = 86400
PURGE_CHUNK = 2000


@dataclass
class PurgeStep:
    deleted: dict[str, int]
    done: bool


def _id_to_num(node_id: str) -> int:
    return int(node_id[1:], 16)


def _num_to_id(num: int | None) -> str | None:
    return None if num is None else f"!{num:08x}"


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def commit(self) -> None:
        self.conn.commit()

    def upsert_node(self, node: dict, is_mine: bool | None = None,
                    is_favorite: bool | None = None) -> None:
        cols = ["num", "sources", "heard_by", *_NODE_FIELDS]
        values = [node["num"], json.dumps(node.get("sources") or []),
                  json.dumps(node.get("heard_by") or {})]
        values += [node.get(f) for f in _NODE_FIELDS]
        if node.get("id") is None:
            values[cols.index("id")] = _num_to_id(node["num"])
        if is_mine is not None:
            cols.append("is_mine")
            values.append(1 if is_mine else 0)
        if is_favorite is not None:
            cols.append("is_favorite")
            values.append(1 if is_favorite else 0)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols[1:])
        self.conn.execute(
            f"INSERT INTO nodes({', '.join(cols)}) VALUES({', '.join('?' * len(cols))}) "
            f"ON CONFLICT(num) DO UPDATE SET {updates}", values)

    def add_position(self, num: int, time: float, lat: float, lon: float,
                     precision_bits: int | None, source: str) -> None:
        self.conn.execute(
            "INSERT INTO positions(node_num, time, lat, lon, precision_bits, source) "
            "VALUES(?,?,?,?,?,?)", (num, time, lat, lon, precision_bits, source))

    def add_message(self, msg: dict) -> None:
        to = msg.get("to")
        self.conn.execute(
            "INSERT OR IGNORE INTO messages"
            "(key, from_num, to_num, channel, text, time, country, source, direction, radio_id, "
            "channel_index, packet_id, status, broker, reply_id, emoji, pki, error, heard_by) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (msg["key"], _id_to_num(msg["from"]), _id_to_num(to) if to else None,
             msg.get("channel"), msg.get("text"), msg["time"], msg.get("country"),
             msg.get("source"), msg.get("direction") or "in", msg.get("radio_id"),
             msg.get("channel_index"), msg.get("packet_id"), msg.get("status"),
             msg.get("broker"), msg.get("reply_id"), 1 if msg.get("emoji") else 0,
             1 if msg.get("pki") else 0, msg.get("error"),
             json.dumps(msg["heard_by"]) if msg.get("heard_by") else None))

    def update_message_heard(self, key: str, heard_by: list[str]) -> None:
        """Messaggio inviato via MQTT sentito in radio: stato "heard" e chi l'ha sentito."""
        self.conn.execute("UPDATE messages SET status='heard', error=NULL, heard_by=? WHERE key=?",
                          (json.dumps(heard_by), key))

    def message_state(self, key: str) -> tuple[str | None, list[str]] | None:
        """(stato, heard_by) di un messaggio archiviato; None se non esiste."""
        r = self.conn.execute("SELECT status, heard_by FROM messages WHERE key=?", (key,)).fetchone()
        if r is None:
            return None
        return r["status"], (json.loads(r["heard_by"]) if r["heard_by"] else [])

    def update_message_status(self, key: str, status: str, error: str | None = None) -> None:
        self.conn.execute("UPDATE messages SET status=?, error=? WHERE key=?",
                          (status, error, key))

    def update_message_radio(self, key: str, radio_id: str, channel_index: int | None) -> None:
        self.conn.execute("UPDATE messages SET radio_id=?, channel_index=?, source='rf' "
                          "WHERE key=?", (radio_id, channel_index, key))

    def list_radios(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, kind, address, auto_connect, created FROM radios "
            "ORDER BY created, id")
        return [{**dict(r), "auto_connect": bool(r["auto_connect"])} for r in rows]

    def save_radio(self, r: dict) -> None:
        created = r.get("created")
        self.conn.execute(
            "INSERT INTO radios(id, name, kind, address, auto_connect, created) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "kind=excluded.kind, address=excluded.address, auto_connect=excluded.auto_connect",
            (r["id"], r.get("name"), r.get("kind"), r.get("address"),
             1 if r.get("auto_connect", True) else 0, time.time() if created is None else created))

    def delete_radio(self, radio_id: str) -> None:
        self.conn.execute("DELETE FROM radios WHERE id=?", (radio_id,))

    def add_telemetry(self, num: int, time: float, t: TelemetryData) -> None:
        self.conn.execute(
            "INSERT INTO telemetry(node_num, time, battery, voltage, channel_util, air_util_tx, uptime) "
            "VALUES(?,?,?,?,?,?,?)",
            (num, time, t.battery_level, t.voltage, t.channel_utilization,
             t.air_util_tx, t.uptime_seconds))

    def add_metrics(self, num: int, time: float, variant: str, metrics: dict[str, float]) -> None:
        if not metrics:
            return
        self.conn.executemany(
            "INSERT INTO metrics(node_num, time, variant, metric, value) VALUES(?,?,?,?,?)",
            [(num, time, variant, name, value) for name, value in metrics.items()])

    _PACKET_COLS = ("time", "from_num", "to_num", "packet_id", "source", "broker", "radio_id",
                    "channel", "portnum", "kind", "status", "snr", "rssi", "hops", "hop_start",
                    "hop_limit", "relay_node", "gateway", "copies", "receptions", "summary",
                    "raw", "size")

    def insert_packets(self, rows: list[dict]) -> None:
        if not rows:
            return
        self.conn.executemany(
            f"INSERT INTO packets({', '.join(self._PACKET_COLS)}) "
            f"VALUES({', '.join('?' * len(self._PACKET_COLS))})",
            [tuple(r.get(c, 1 if c == "copies" else None) for c in self._PACKET_COLS)
             for r in rows])

    def upsert_stats_hourly(self, rows: list[tuple[int, str, str, int, int]]) -> None:
        if not rows:
            return
        self.conn.executemany(
            "INSERT INTO stats_hourly(time, source, kind, packets, receptions) VALUES(?,?,?,?,?) "
            "ON CONFLICT(time, source, kind) DO UPDATE SET "
            "packets=packets+excluded.packets, receptions=receptions+excluded.receptions", rows)

    def upsert_node_hourly(
            self, rows: list[tuple[int, int, str, int, float, int, float | None]]) -> None:
        if not rows:
            return
        self.conn.executemany(
            "INSERT INTO node_hourly(time, node_num, source, packets, snr_sum, snr_n, snr_max) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(time, node_num, source) DO UPDATE SET "
            "packets=packets+excluded.packets, snr_sum=snr_sum+excluded.snr_sum, "
            "snr_n=snr_n+excluded.snr_n, "
            "snr_max=CASE WHEN snr_max IS NULL THEN excluded.snr_max "
            "WHEN excluded.snr_max IS NULL THEN snr_max "
            "ELSE MAX(snr_max, excluded.snr_max) END", rows)

    def packets_cutoff(self, max_rows: int) -> int | None:
        """Id oltre il quale i pacchetti vanno tolti per restare entro `max_rows` (None se basta)."""
        top = self.conn.execute("SELECT MAX(id) FROM packets").fetchone()[0]
        if top is None or top - max_rows <= 0:
            return None
        return top - max_rows

    def trim_packets(self, cutoff: int, limit: int) -> int:
        """Cancella al massimo `limit` pacchetti con id <= `cutoff` (dal piu' vecchio)."""
        return self.conn.execute(
            "DELETE FROM packets WHERE id IN "
            "(SELECT id FROM packets WHERE id <= ? ORDER BY id LIMIT ?)",
            (cutoff, limit)).rowcount

    @staticmethod
    def _node_from_row(row) -> dict:
        d = dict(row)
        d["sources"] = json.loads(d["sources"]) if d["sources"] else []
        d["heard_by"] = json.loads(d["heard_by"]) if d["heard_by"] else {}
        d["is_mine"] = bool(d["is_mine"])
        d["is_favorite"] = bool(d["is_favorite"])
        return d

    def load_nodes(self) -> list[dict]:
        return [self._node_from_row(row) for row in self.conn.execute("SELECT * FROM nodes")]

    def get_node(self, num: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM nodes WHERE num=?", (num,)).fetchone()
        return None if row is None else self._node_from_row(row)

    def set_mine(self, num: int, mine: bool) -> None:
        self.conn.execute("UPDATE nodes SET is_mine=? WHERE num=?", (1 if mine else 0, num))

    def set_favorite(self, num: int, favorite: bool) -> None:
        self.conn.execute("UPDATE nodes SET is_favorite=? WHERE num=?", (1 if favorite else 0, num))

    def upsert_link(self, from_num: int, to_num: int, source: str, snr: float | None,
                    time: float) -> None:
        """Tiene la riga piu' recente per (from, to, source)."""
        self.conn.execute(
            "INSERT INTO links(from_num, to_num, source, snr, time) VALUES(?,?,?,?,?) "
            "ON CONFLICT(from_num, to_num, source) DO UPDATE SET snr=excluded.snr, "
            "time=excluded.time WHERE excluded.time >= links.time",
            (from_num, to_num, source, snr, time))

    def links(self, since: float) -> list[dict]:
        rows = self.conn.execute(
            "SELECT from_num, to_num, source, snr, time FROM links WHERE time>=? ORDER BY time",
            (since,))
        return [{"from_id": _num_to_id(r["from_num"]), "to_id": _num_to_id(r["to_num"]),
                 "source": r["source"], "snr": r["snr"], "time": r["time"]} for r in rows]

    # --- prove di copertura (non scadono: purge non le tocca) ---
    _SESSION_FIELDS = ("name", "radio_id", "mobile_num", "mode", "channel_index", "interval_s",
                       "started", "ended", "end_reason", "base_lat", "base_lon", "notes")

    def _check_fields(self, fields: dict) -> None:
        bad = set(fields) - set(self._SESSION_FIELDS)
        if bad:
            raise ValueError(f"campi sessione sconosciuti: {sorted(bad)}")

    def create_session(self, **fields) -> int:
        self._check_fields(fields)
        cols = ", ".join(fields)
        cur = self.conn.execute(
            f"INSERT INTO coverage_sessions({cols}) VALUES({', '.join('?' * len(fields))})",
            tuple(fields.values()))
        return cur.lastrowid

    def update_session(self, sid: int, **fields) -> None:
        self._check_fields(fields)
        if fields:
            self.conn.execute(
                f"UPDATE coverage_sessions SET {', '.join(k + '=?' for k in fields)} WHERE id=?",
                (*fields.values(), sid))

    def get_session(self, sid: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM coverage_sessions WHERE id=?", (sid,)).fetchone()
        return dict(row) if row else None

    def sessions(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM coverage_sessions ORDER BY started DESC, id DESC")
        return [dict(r) for r in rows]

    def active_session(self) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM coverage_sessions WHERE ended IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def delete_session(self, sid: int) -> None:
        for table in ("coverage_points", "coverage_track"):
            self.conn.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
        self.conn.execute("DELETE FROM coverage_sessions WHERE id=?", (sid,))

    def add_point(self, session_id: int, segment: int, seq: int | None, time: float,
                  snr: float | None, rssi: int | None, hops: int | None, lat: float | None,
                  lon: float | None, precision_bits: int | None) -> bool:
        """Registra un punto; stesso (sessione, tratto, seq): tiene l'SNR migliore, False."""
        if seq is not None:
            row = self.conn.execute(
                "SELECT id, snr FROM coverage_points WHERE session_id=? AND segment=? AND seq=?",
                (session_id, segment, seq)).fetchone()
            if row is not None:
                if snr is not None and (row["snr"] is None or snr > row["snr"]):
                    self.conn.execute("UPDATE coverage_points SET snr=?, rssi=?, hops=? "
                                      "WHERE id=?", (snr, rssi, hops, row["id"]))
                return False
        self.conn.execute(
            "INSERT INTO coverage_points(session_id, segment, seq, time, snr, rssi, hops, lat, "
            "lon, precision_bits) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (session_id, segment, seq, time, snr, rssi, hops, lat, lon, precision_bits))
        return True

    def points(self, session_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM coverage_points WHERE session_id=? ORDER BY time, id", (session_id,))
        return [dict(r) for r in rows]

    def points_since(self, session_id: int, since: float) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM coverage_points WHERE session_id=? AND time>=? ORDER BY time, id",
            (session_id, since))
        return [dict(r) for r in rows]

    def add_track(self, session_id: int, time: float, lat: float, lon: float,
                  precision_bits: int | None) -> None:
        self.conn.execute(
            "INSERT INTO coverage_track(session_id, time, lat, lon, precision_bits) "
            "VALUES(?,?,?,?,?)", (session_id, time, lat, lon, precision_bits))

    def track(self, session_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM coverage_track WHERE session_id=? ORDER BY time, id", (session_id,))
        return [dict(r) for r in rows]

    def update_point_position(self, point_id: int, lat: float, lon: float,
                              precision_bits: int | None) -> None:
        self.conn.execute(
            "UPDATE coverage_points SET lat=?, lon=?, precision_bits=? WHERE id=?",
            (lat, lon, precision_bits, point_id))

    def add_traceroute(self, radio_id: str, target_num: int, time: float) -> int:
        cur = self.conn.execute(
            "INSERT INTO traceroutes(radio_id, target_num, time, status, forward, back) "
            "VALUES(?,?,?,'pending','[]','[]')", (radio_id, target_num, time))
        return cur.lastrowid

    def update_traceroute(self, tid: int, status: str, error: str | None,
                          forward: list, back: list) -> None:
        self.conn.execute(
            "UPDATE traceroutes SET status=?, error=?, forward=?, back=? WHERE id=?",
            (status, error, json.dumps(forward), json.dumps(back), tid))

    def expire_pending_traceroutes(self, error: str) -> None:
        self.conn.execute("UPDATE traceroutes SET status='timeout', error=? WHERE status='pending'",
                          (error,))

    def traceroutes(self, target_num: int, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM traceroutes WHERE target_num=? ORDER BY time DESC, id DESC LIMIT ?",
            (target_num, limit))
        return [{"id": r["id"], "radio_id": r["radio_id"],
                 "target_id": _num_to_id(r["target_num"]), "time": r["time"],
                 "status": r["status"], "error": r["error"],
                 "forward": json.loads(r["forward"] or "[]"),
                 "back": json.loads(r["back"] or "[]")} for r in rows]

    # --- configurazione del nodo (letture, copie di sicurezza, lavori): non scadono ---
    def add_read(self, node_num: int, radio_id: str | None, time: float, sections: list,
                 data: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO config_reads(node_num, radio_id, time, sections, data) VALUES(?,?,?,?,?)",
            (node_num, radio_id, time, json.dumps(sections), json.dumps(data)))
        return cur.lastrowid

    def last_read(self, node_num: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM config_reads WHERE node_num=? ORDER BY time DESC, id DESC LIMIT 1",
            (node_num,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "node_num": row["node_num"], "radio_id": row["radio_id"],
                "time": row["time"], "sections": json.loads(row["sections"] or "[]"),
                "data": json.loads(row["data"] or "{}")}

    def add_backup(self, node_num: int, time: float, reason: str, label: str | None,
                   sections: list, data: dict) -> int:
        # data contiene i segreti in chiaro: serve a ripristinare, non esce mai senza maschera
        cur = self.conn.execute(
            "INSERT INTO config_backups(node_num, time, reason, label, sections, data) "
            "VALUES(?,?,?,?,?,?)",
            (node_num, time, reason, label, json.dumps(sections), json.dumps(data)))
        return cur.lastrowid

    @staticmethod
    def _backup_row(r, with_data: bool) -> dict:
        d = {"id": r["id"], "node_num": r["node_num"], "time": r["time"], "reason": r["reason"],
             "label": r["label"], "sections": json.loads(r["sections"] or "[]")}
        if with_data:
            d["data"] = json.loads(r["data"] or "{}")
        return d

    def backups(self, node_num: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM config_backups WHERE node_num=? ORDER BY time DESC, id DESC",
            (node_num,))
        return [self._backup_row(r, False) for r in rows]

    def get_backup(self, backup_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM config_backups WHERE id=?",
                                (backup_id,)).fetchone()
        return self._backup_row(row, True) if row else None

    # --- piani "Prepara le radio" (steps: JSON con le copie e i lavori per nodo) ---
    def add_plan(self, radio_id: str, mobile_num: int, created: float, steps: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO coverage_prepare(radio_id, mobile_num, created, steps) VALUES(?,?,?,?)",
            (radio_id, mobile_num, created, json.dumps(steps)))
        return cur.lastrowid

    @staticmethod
    def _plan_row(r) -> dict:
        return {"id": r["id"], "radio_id": r["radio_id"], "mobile_num": r["mobile_num"],
                "created": r["created"], "applied": r["applied"], "restored": r["restored"],
                "steps": json.loads(r["steps"] or "{}")}

    def get_plan(self, plan_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM coverage_prepare WHERE id=?",
                                (plan_id,)).fetchone()
        return self._plan_row(row) if row else None

    def update_plan(self, plan_id: int, **fields) -> None:
        if "steps" in fields:
            fields["steps"] = json.dumps(fields["steps"])
        self.conn.execute(
            f"UPDATE coverage_prepare SET {', '.join(k + '=?' for k in fields)} WHERE id=?",
            (*fields.values(), plan_id))

    def applied_plans(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM coverage_prepare WHERE applied IS NOT NULL AND restored IS NULL "
            "ORDER BY id DESC")
        return [self._plan_row(r) for r in rows]

    _JOB_FIELDS = ("node_num", "radio_id", "kind", "status", "step", "done", "total", "error",
                   "result_id", "verify", "started", "ended", "error_code")

    def _check_job(self, fields: dict) -> None:
        bad = set(fields) - set(self._JOB_FIELDS)
        if bad:
            raise ValueError(f"campi lavoro sconosciuti: {sorted(bad)}")

    def add_job(self, **fields) -> int:
        self._check_job(fields)
        cur = self.conn.execute(
            f"INSERT INTO config_jobs({', '.join(fields)}) VALUES({', '.join('?' * len(fields))})",
            tuple(fields.values()))
        return cur.lastrowid

    def update_job(self, job_id: int, **fields) -> None:
        self._check_job(fields)
        if fields:
            self.conn.execute(
                f"UPDATE config_jobs SET {', '.join(k + '=?' for k in fields)} WHERE id=?",
                (*fields.values(), job_id))

    def fail_running_jobs(self, error: str, ended: float) -> None:
        """Lavori rimasti "running" da un avvio precedente: non finiranno piu'."""
        self.conn.execute(
            "UPDATE config_jobs SET status='failed', error=?, ended=?, error_code='error' "
            "WHERE status='running'",
            (error, ended))

    def get_job(self, job_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM config_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def positions(self, num: int, since: float) -> list[dict]:
        rows = self.conn.execute(
            "SELECT time, lat, lon, precision_bits, source FROM positions "
            "WHERE node_num=? AND time>=? ORDER BY time", (num, since))
        return [dict(r) for r in rows]

    def radio_messages(self, before: float | None, limit: int) -> list[dict]:
        """Messaggi passati da una radio locale (entrata e uscita), i piu' recenti prima."""
        return self.messages(None, before, limit, radio_only=True)

    def messages(self, countries: list[str] | None, before: float | None, limit: int,
                 radio_only: bool = False, broker: str | None = None) -> list[dict]:
        sql = ("SELECT m.*, n.long_name AS from_name FROM messages m "
               "LEFT JOIN nodes n ON n.num = m.from_num WHERE 1=1")
        params: list = []
        if radio_only:
            sql += " AND m.radio_id IS NOT NULL"
        if countries is not None:
            sql += f" AND m.country IN ({','.join('?' * len(countries))})"
            params += countries
        if broker is not None:
            sql += " AND m.broker = ?"
            params.append(broker)
        if before is not None:
            sql += " AND m.time < ?"
            params.append(before)
        sql += " ORDER BY m.time DESC LIMIT ?"
        params.append(limit)
        return [self._message_row(r) for r in self.conn.execute(sql, params)]

    @staticmethod
    def _message_row(r: sqlite3.Row) -> dict:
        return {"key": r["key"], "from": _num_to_id(r["from_num"]), "from_name": r["from_name"],
                "to": _num_to_id(r["to_num"]), "channel": r["channel"], "text": r["text"],
                "time": r["time"], "country": r["country"], "source": r["source"],
                "direction": r["direction"] or "in", "radio_id": r["radio_id"],
                "channel_index": r["channel_index"], "packet_id": r["packet_id"],
                "status": r["status"], "broker": r["broker"],
                "reply_id": r["reply_id"], "emoji": bool(r["emoji"]), "pki": bool(r["pki"]),
                "error": r["error"],
                "heard_by": json.loads(r["heard_by"]) if r["heard_by"] else None,
                # "via" non e' una colonna: si ricava (uscita su MQTT = inviato via MQTT)
                **({"via": "mqtt"} if r["direction"] == "out" and r["source"] == "mqtt" else {})}

    def recent_radio_messages(self, limit: int = 5000) -> list[dict]:
        """Ultimi messaggi passati da una radio locale (per il conteggio dei non letti)."""
        return self.messages(None, None, limit, radio_only=True)

    _WP_COLS = ("id", "from_num", "lat", "lon", "name", "description", "icon", "expire",
                "locked_to", "time", "source", "radio_id", "channel", "country")

    def upsert_waypoint(self, wp: dict) -> None:
        cols = self._WP_COLS
        # from_num non cambia mai: chi ha creato il waypoint resta il suo proprietario
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("id", "from_num"))
        # un nuovo arrivo ripristina anche un waypoint eliminato prima
        self.conn.execute(
            f"INSERT INTO waypoints({', '.join(cols)}, deleted) "
            f"VALUES({', '.join('?' * len(cols))}, 0) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}, deleted=0",
            [wp.get(c) for c in cols])

    def delete_waypoint(self, wid: int) -> None:
        self.conn.execute("UPDATE waypoints SET deleted=1 WHERE id=?", (wid,))

    def get_waypoint(self, wid: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM waypoints WHERE id=?", (wid,)).fetchone()
        return dict(row) if row else None

    def active_waypoints(self, now: float, limit: int = 500) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM waypoints WHERE deleted=0 AND (expire IS NULL OR expire=0 OR expire>?) "
            "ORDER BY time DESC LIMIT ?", (now, limit))
        return [dict(r) for r in rows]

    def mark_read(self, conv: str, t: float) -> float:
        self.conn.execute(
            "INSERT INTO conversation_reads(conv, read_time) VALUES(?,?) "
            "ON CONFLICT(conv) DO UPDATE SET read_time=MAX(read_time, excluded.read_time)",
            (conv, t))
        return self.conn.execute("SELECT read_time FROM conversation_reads WHERE conv=?",
                                 (conv,)).fetchone()[0]

    def read_times(self) -> dict[str, float]:
        return {r["conv"]: r["read_time"]
                for r in self.conn.execute("SELECT conv, read_time FROM conversation_reads")}

    def read_baseline(self) -> float:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key='conv_read_baseline'").fetchone()
        try:
            return float(json.loads(row["value"])) if row else 0.0
        except (TypeError, ValueError):
            return 0.0

    def telemetry(self, num: int, since: float) -> list[dict]:
        rows = self.conn.execute(
            "SELECT time, battery, voltage, channel_util, air_util_tx, uptime FROM telemetry "
            "WHERE node_num=? AND time>=? ORDER BY time", (num, since))
        return [dict(r) for r in rows]

    def channel_util_stats(self, nums: list[int], since: float) -> dict[int, tuple[float, int]]:
        """Media e numero di campioni di channel_util per nodo dopo `since` (una sola query)."""
        if not nums:
            return {}
        marks = ",".join("?" * len(nums))
        rows = self.conn.execute(
            "SELECT node_num, AVG(channel_util), COUNT(channel_util) FROM telemetry "
            f"WHERE node_num IN ({marks}) AND time>=? AND channel_util IS NOT NULL "
            "GROUP BY node_num", (*nums, since))
        return {r[0]: (r[1], r[2]) for r in rows}

    def _used_bytes(self) -> int:
        pages = self.conn.execute("PRAGMA page_count").fetchone()[0]
        free = self.conn.execute("PRAGMA freelist_count").fetchone()[0]
        page_size = self.conn.execute("PRAGMA page_size").fetchone()[0]
        return (pages - free) * page_size

    def purge_step(self, now: float, settings: dict, limit: int = PURGE_CHUNK) -> PurgeStep:
        """Un passo di pulizia: al massimo `limit` righe per tabella. `done` quando non resta
        nulla di scaduto e lo spazio e' entro il limite. Non fa commit."""
        deleted: dict[str, int] = {}
        full = False  # una tabella ha cancellato `limit` righe: potrebbe averne ancora
        pos_cutoff = now - settings["retention_positions_days"] * _DAY
        for table, cutoff in (("messages", now - settings["retention_messages_days"] * _DAY),
                              ("positions", pos_cutoff),
                              ("telemetry", now - settings["retention_telemetry_days"] * _DAY),
                              ("links", pos_cutoff),
                              ("metrics", now - settings["retention_telemetry_days"] * _DAY),
                              ("stats_hourly", now - settings["retention_telemetry_days"] * _DAY),
                              ("node_hourly", pos_cutoff),
                              ("packets", now - settings["retention_packets_hours"] * 3600)):
            n = self.conn.execute(
                f"DELETE FROM {table} WHERE rowid IN "
                f"(SELECT rowid FROM {table} WHERE time < ? LIMIT ?)", (cutoff, limit)).rowcount
            full = full or n >= limit
            if table not in ("links", "stats_hourly", "node_hourly"):  # non nel conteggio
                deleted[table] = n
        n = self.conn.execute(
            "DELETE FROM nodes WHERE rowid IN (SELECT rowid FROM nodes WHERE "
            "(last_heard < ? OR last_heard IS NULL) AND is_mine = 0 AND is_favorite = 0 LIMIT ?)",
            (pos_cutoff, limit)).rowcount
        deleted["nodes"] = n
        full = full or n >= limit
        n = self.conn.execute(
            "DELETE FROM waypoints WHERE rowid IN (SELECT rowid FROM waypoints WHERE "
            "(expire > 0 AND expire < ?) OR time < ? LIMIT ?)", (now, pos_cutoff, limit)).rowcount
        full = full or n >= limit  # i waypoint non entrano nel conteggio restituito
        self.conn.execute(
            "DELETE FROM conversation_reads WHERE conv IN (SELECT conv FROM conversation_reads "
            "WHERE read_time < ? LIMIT ?)",
            (now - settings["retention_messages_days"] * _DAY, limit))
        if not full and self._used_bytes() > settings["storage_cap_mb"] * 1024 * 1024:
            for table in ("packets", "positions", "messages"):
                removed = self.conn.execute(
                    f"DELETE FROM {table} WHERE rowid IN "
                    f"(SELECT rowid FROM {table} ORDER BY time LIMIT ?)", (limit,)).rowcount
                deleted[table] += removed
                full = full or removed > 0
        return PurgeStep(deleted, not full)

    def purge(self, now: float, settings: dict) -> dict[str, int]:
        """Applica la retention e il limite spazio, ripetendo `purge_step` fino a `done`."""
        total: dict[str, int] = {"messages": 0, "positions": 0, "telemetry": 0, "nodes": 0,
                                 "metrics": 0, "packets": 0}
        while True:
            step = self.purge_step(now, settings)
            for k, v in step.deleted.items():
                total[k] = total.get(k, 0) + v
            if step.done:
                break
        self.conn.commit()
        return total

    def incremental_vacuum(self, pages: int = 1000) -> None:
        """Restituisce al disco le pagine libere (solo con auto_vacuum=INCREMENTAL)."""
        if self.conn.execute("PRAGMA auto_vacuum").fetchone()[0] != 2:
            return
        self.conn.commit()
        self.conn.execute(f"PRAGMA incremental_vacuum({int(pages)})").fetchall()
