"""Letture di serie storiche per le rotte dei dati: girano su una connessione a sola lettura
propria (thread a parte), mai sulla connessione principale del loop."""
import math
import sqlite3
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
