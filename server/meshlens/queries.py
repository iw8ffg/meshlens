"""Letture di serie storiche per le rotte dei dati: girano su una connessione a sola lettura
propria (thread a parte), mai sulla connessione principale del loop."""
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path


def ro_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def bucket_rows(rows: list[dict], keys: tuple[str, ...], max_points: int,
                tkey: str = "time") -> list[dict]:
    """Oltre `max_points` righe: medie su intervalli di tempo uguali (None se mancano tutti
    i valori di una chiave nell'intervallo)."""
    if len(rows) <= max_points:
        return rows
    t0, t1 = rows[0][tkey], rows[-1][tkey]
    width = (t1 - t0) / max_points
    groups: dict[int, list[dict]] = {}
    for r in rows:
        i = min(int((r[tkey] - t0) / width), max_points - 1) if width > 0 else 0
        groups.setdefault(i, []).append(r)
    out = []
    for i in sorted(groups):
        g = groups[i]
        row = {tkey: sum(r[tkey] for r in g) / len(g)}
        for k in keys:
            vals = [r[k] for r in g if r[k] is not None]
            row[k] = sum(vals) / len(vals) if vals else None
        out.append(row)
    return out


def telemetry_series(conn: sqlite3.Connection, num: int, since: float,
                     max_points: int = 800) -> list[dict]:
    keys = ("battery", "voltage", "channel_util", "air_util_tx")
    rows = [dict(r) for r in conn.execute(
        "SELECT time, battery, voltage, channel_util, air_util_tx FROM telemetry "
        "WHERE node_num=? AND time>=? ORDER BY time", (num, since))]
    return bucket_rows(rows, keys, max_points)


def metric_series(conn: sqlite3.Connection, num: int, since: float,
                  max_points: int = 800) -> dict:
    latest = {f"{r['variant']}.{r['metric']}": {"value": r["value"], "time": r["time"]}
              for r in conn.execute(
                  "SELECT variant, metric, value, MAX(time) AS time FROM metrics "
                  "WHERE node_num=? GROUP BY variant, metric", (num,))}
    grouped: dict[str, list[dict]] = {}
    for r in conn.execute(
            "SELECT variant, metric, time, value FROM metrics WHERE node_num=? AND time>=? "
            "ORDER BY variant, metric, time", (num, since)):
        grouped.setdefault(f"{r['variant']}.{r['metric']}", []).append(
            {"time": r["time"], "value": r["value"]})
    series = {key: [[p["time"], p["value"]] for p in bucket_rows(rows, ("value",), max_points)]
              for key, rows in grouped.items()}
    return {"latest": latest, "series": series}


def snr_series(conn: sqlite3.Connection, num: int, since: float) -> list[dict]:
    return [{"time": r["time"], "source": r["source"],
             "snr_avg": r["snr_sum"] / r["snr_n"] if r["snr_n"] else None,
             "snr_max": r["snr_max"], "packets": r["packets"]}
            for r in conn.execute(
                "SELECT time, source, packets, snr_sum, snr_n, snr_max FROM node_hourly "
                "WHERE node_num=? AND time>=? ORDER BY time, source", (num, since))]


def track(conn: sqlite3.Connection, num: int, since: float, max_points: int = 5000) -> list[dict]:
    """Un punto ogni k, piu' sempre l'ultimo."""
    rows = [dict(r) for r in conn.execute(
        "SELECT time, lat, lon, precision_bits, source FROM positions "
        "WHERE node_num=? AND time>=? ORDER BY time", (num, since))]
    n = len(rows)
    if n <= max_points:
        return rows
    k = math.ceil(n / max_points)
    out = rows[::k]
    if (n - 1) % k:
        out.append(rows[-1])
    return out


SNR_BINS = [-20 + 2.5 * i for i in range(15)]
PACKET_LIMIT_MAX = 200
HARDWARE_TOP = 12


def _node_id(num: int | None) -> str | None:
    return None if num is None else f"!{num:08x}"


def _snr_bin(v: float) -> int:
    return max(0, min(len(SNR_BINS) - 1, int((v - SNR_BINS[0]) // 2.5)))


def network_stats(conn: sqlite3.Connection, now: float, hours: int) -> dict:
    since = math.ceil((now - hours * 3600) / 3600) * 3600  # first whole hour inside the window
    online = [{"time": r["time"], "nodes": r["n"]} for r in conn.execute(
        "SELECT time, COUNT(DISTINCT node_num) AS n FROM node_hourly WHERE time>=? "
        "GROUP BY time ORDER BY time", (since,))]
    packets = [{"time": r["time"], "kind": r["kind"], "packets": r["p"], "receptions": r["r"]}
               for r in conn.execute(
                   "SELECT time, kind, SUM(packets) AS p, SUM(receptions) AS r FROM stats_hourly "
                   "WHERE time>=? GROUP BY time, kind ORDER BY time, kind", (since,))]
    snr = {"bins": list(SNR_BINS), "rf": [0] * len(SNR_BINS), "mqtt": [0] * len(SNR_BINS)}
    for r in conn.execute(
            "SELECT source, SUM(snr_sum) * 1.0 / SUM(snr_n) AS v FROM node_hourly "
            "WHERE time>=? AND source IN ('rf','mqtt') GROUP BY node_num, source "
            "HAVING SUM(snr_n) > 0", (since,)):
        snr[r["source"]][_snr_bin(r["v"])] += 1
    hop_counts: dict[int | None, int] = {i: 0 for i in range(8)}
    hop_counts[None] = 0
    for r in conn.execute("SELECT hops, COUNT(*) AS n FROM nodes WHERE last_heard>=? "
                          "GROUP BY hops", (since,)):
        hop_counts[r["hops"] if r["hops"] in hop_counts else None] += r["n"]
    hops = [{"hops": h, "nodes": n} for h, n in hop_counts.items()]
    hw = [(r["hw_model"], r["n"]) for r in conn.execute(
        "SELECT hw_model, COUNT(*) AS n FROM nodes WHERE last_heard>=? AND hw_model IS NOT NULL "
        "AND hw_model<>'' GROUP BY hw_model ORDER BY n DESC, hw_model", (since,))]
    hardware = [{"value": v, "nodes": n} for v, n in hw[:HARDWARE_TOP]]
    other_hardware = sum(n for _, n in hw[HARDWARE_TOP:])
    roles = [{"value": r["role"], "nodes": r["n"]} for r in conn.execute(
        "SELECT role, COUNT(*) AS n FROM nodes WHERE last_heard>=? AND role IS NOT NULL "
        "AND role<>'' GROUP BY role ORDER BY n DESC, role", (since,))]
    top = [{"id": _node_id(r["node_num"]), "name": r["long_name"] or _node_id(r["node_num"]),
            "packets": r["p"], "per_hour": r["p"] / hours} for r in conn.execute(
        "SELECT h.node_num, SUM(h.packets) AS p, n.long_name FROM node_hourly h "
        "LEFT JOIN nodes n ON n.num=h.node_num WHERE h.time>=? "
        "GROUP BY h.node_num ORDER BY p DESC, h.node_num LIMIT 10", (since,))]
    total_nodes = conn.execute("SELECT COUNT(DISTINCT node_num) FROM node_hourly WHERE time>=?",
                               (since,)).fetchone()[0]
    total_packets = conn.execute("SELECT COALESCE(SUM(packets), 0) FROM stats_hourly "
                                 "WHERE time>=?", (since,)).fetchone()[0]
    return {"hours": hours, "since": since,
            "totals": {"nodes": total_nodes, "packets": total_packets},
            "online": online, "packets": packets, "snr": snr, "hops": hops, "top": top,
            "hardware": hardware, "roles": roles, "other_hardware": other_hardware}


@dataclass
class PacketFilter:
    node: int | None = None
    kind: str | None = None
    source: str | None = None
    status: str | None = None
    min_snr: float | None = None
    since: float | None = None
    until: float | None = None


_PACKET_ROW_SQL = (
    "SELECT p.id, p.time, p.from_num, n.long_name AS from_name, p.to_num, p.packet_id, p.source, "
    "p.broker, p.radio_id, p.channel, p.portnum, p.kind, p.status, p.snr, p.rssi, p.hops, "
    "p.hop_start, p.hop_limit, p.relay_node, p.gateway, p.copies, p.size")


def _packet_row(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "time": r["time"], "from": _node_id(r["from_num"]),
            "from_name": r["from_name"], "to": _node_id(r["to_num"]),
            "packet_id": r["packet_id"], "source": r["source"], "broker": r["broker"],
            "radio_id": r["radio_id"], "channel": r["channel"], "portnum": r["portnum"],
            "kind": r["kind"], "status": r["status"], "snr": r["snr"], "rssi": r["rssi"],
            "hops": r["hops"], "hop_start": r["hop_start"], "hop_limit": r["hop_limit"],
            "relay_node": r["relay_node"], "gateway": r["gateway"], "copies": r["copies"],
            "size": r["size"]}


def packet_list(conn: sqlite3.Connection, f: PacketFilter, limit: int,
                before_id: int | None) -> dict:
    limit = max(1, min(limit, PACKET_LIMIT_MAX))
    where, args = [], []
    if f.node is not None:
        where.append("(p.from_num=? OR p.to_num=?)")
        args += [f.node, f.node]
    for col, val in (("kind", f.kind), ("source", f.source), ("status", f.status)):
        if val is not None:
            where.append(f"p.{col}=?")
            args.append(val)
    if f.min_snr is not None:
        where.append("p.snr>=?")
        args.append(f.min_snr)
    if f.since is not None:
        where.append("p.time>=?")
        args.append(f.since)
    if f.until is not None:
        where.append("p.time<=?")
        args.append(f.until)
    if before_id is not None:
        where.append("p.id<?")
        args.append(before_id)
    sql = (_PACKET_ROW_SQL + " FROM packets p LEFT JOIN nodes n ON n.num=p.from_num"
           + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY p.id DESC LIMIT ?")
    items = [_packet_row(r) for r in conn.execute(sql, (*args, limit))]
    return {"items": items,
            "next_before_id": items[-1]["id"] if len(items) == limit else None}


def _loads(text: str | None):
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def packet_detail(conn: sqlite3.Connection, pid: int) -> dict | None:
    r = conn.execute(
        _PACKET_ROW_SQL + ", p.receptions, p.summary, p.raw FROM packets p "
        "LEFT JOIN nodes n ON n.num=p.from_num WHERE p.id=?", (pid,)).fetchone()
    if r is None:
        return None
    out = _packet_row(r)
    out["receptions"] = _loads(r["receptions"]) or []
    out["summary"] = _loads(r["summary"])
    out["raw_hex"] = bytes(r["raw"]).hex() if r["raw"] is not None else ""
    return out
