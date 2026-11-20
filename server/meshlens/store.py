"""Accesso ai dati: nodi, posizioni, messaggi, telemetria."""
import json
import sqlite3

from .events import TelemetryData

_NODE_FIELDS = ("id", "long_name", "short_name", "hw_model", "role", "firmware", "lat", "lon",
                "precision_bits", "position_source", "position_time", "country", "last_heard",
                "battery", "voltage", "channel_util", "air_util_tx", "mqtt_gateways",
                "last_snr", "hops")
_DAY = 86400


def _id_to_num(node_id: str) -> int:
    return int(node_id[1:], 16)


def _num_to_id(num: int | None) -> str | None:
    return None if num is None else f"!{num:08x}"


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def commit(self) -> None:
        self.conn.commit()

    def upsert_node(self, node: dict, is_mine: bool | None = None) -> None:
        cols = ["num", "sources", *_NODE_FIELDS]
        values = [node["num"], json.dumps(node.get("sources") or [])]
        values += [node.get(f) for f in _NODE_FIELDS]
        if node.get("id") is None:
            values[cols.index("id")] = _num_to_id(node["num"])
        if is_mine is not None:
            cols.append("is_mine")
            values.append(1 if is_mine else 0)
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
            "(key, from_num, to_num, channel, text, time, country, source) VALUES(?,?,?,?,?,?,?,?)",
            (msg["key"], _id_to_num(msg["from"]), _id_to_num(to) if to else None,
             msg.get("channel"), msg.get("text"), msg["time"], msg.get("country"),
             msg.get("source")))

    def add_telemetry(self, num: int, time: float, t: TelemetryData) -> None:
        self.conn.execute(
            "INSERT INTO telemetry(node_num, time, battery, voltage, channel_util, air_util_tx, uptime) "
            "VALUES(?,?,?,?,?,?,?)",
            (num, time, t.battery_level, t.voltage, t.channel_utilization,
             t.air_util_tx, t.uptime_seconds))

    def load_nodes(self) -> list[dict]:
        out = []
        for row in self.conn.execute("SELECT * FROM nodes"):
            d = dict(row)
            d["sources"] = json.loads(d["sources"]) if d["sources"] else []
            d["is_mine"] = bool(d["is_mine"])
            out.append(d)
        return out

    def positions(self, num: int, since: float) -> list[dict]:
        rows = self.conn.execute(
            "SELECT time, lat, lon, precision_bits, source FROM positions "
            "WHERE node_num=? AND time>=? ORDER BY time", (num, since))
        return [dict(r) for r in rows]

    def messages(self, countries: list[str] | None, before: float | None, limit: int) -> list[dict]:
        sql = ("SELECT m.*, n.long_name AS from_name FROM messages m "
               "LEFT JOIN nodes n ON n.num = m.from_num WHERE 1=1")
        params: list = []
        if countries is not None:
            sql += f" AND m.country IN ({','.join('?' * len(countries))})"
            params += countries
        if before is not None:
            sql += " AND m.time < ?"
            params.append(before)
        sql += " ORDER BY m.time DESC LIMIT ?"
        params.append(limit)
        return [{"key": r["key"], "from": _num_to_id(r["from_num"]), "from_name": r["from_name"],
                 "to": _num_to_id(r["to_num"]), "channel": r["channel"], "text": r["text"],
                 "time": r["time"], "country": r["country"], "source": r["source"]}
                for r in self.conn.execute(sql, params)]

    def telemetry(self, num: int, since: float) -> list[dict]:
        rows = self.conn.execute(
            "SELECT time, battery, voltage, channel_util, air_util_tx, uptime FROM telemetry "
            "WHERE node_num=? AND time>=? ORDER BY time", (num, since))
        return [dict(r) for r in rows]

    def _used_bytes(self) -> int:
        pages = self.conn.execute("PRAGMA page_count").fetchone()[0]
        free = self.conn.execute("PRAGMA freelist_count").fetchone()[0]
        page_size = self.conn.execute("PRAGMA page_size").fetchone()[0]
        return (pages - free) * page_size

    def purge(self, now: float, settings: dict) -> dict[str, int]:
        """Applica la retention, poi riduce positions/messages se si supera il limite spazio."""
        deleted = {}
        for table, key in (("messages", "retention_messages_days"),
                           ("positions", "retention_positions_days"),
                           ("telemetry", "retention_telemetry_days")):
            cutoff = now - settings[key] * _DAY
            deleted[table] = self.conn.execute(
                f"DELETE FROM {table} WHERE time < ?", (cutoff,)).rowcount
        cap = settings["storage_cap_mb"] * 1024 * 1024
        while self._used_bytes() > cap:
            removed_round = 0
            for table in ("positions", "messages"):
                n = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if n == 0:
                    continue
                removed = self.conn.execute(
                    f"DELETE FROM {table} WHERE rowid IN "
                    f"(SELECT rowid FROM {table} ORDER BY time LIMIT ?)",
                    (max(1, n // 10),)).rowcount
                deleted[table] += removed
                removed_round += removed
            if removed_round == 0:
                break
        self.conn.commit()
        return deleted
