"""Statistiche e compattazione del database."""
from .db import rebuild_search_index
import sqlite3
import time
from pathlib import Path

TABLES = ("nodes", "positions", "messages", "telemetry", "links", "traceroutes",
          "coverage_points", "sessions", "metrics", "packets", "stats_hourly", "node_hourly",
          "waypoints", "alert_rules", "sensor_events", "tak_contacts", "trace_targets",
          "config_profiles")
# byte stimati per riga quando dbstat non e' compilato (ripartizione proporzionale)
ROW_WEIGHTS = {"packets": 300, "messages": 200, "positions": 60, "telemetry": 80,
               "metrics": 50, "links": 50, "traceroutes": 150}
DEFAULT_WEIGHT = 100
TABLE_BYTES_CACHE_S = 120
FTS_TABLE = "messages_fts"

_clock = time.monotonic
_table_bytes_cache: dict[str, tuple[float, dict[str, int], str]] = {}


def _size(conn: sqlite3.Connection) -> int:
    pages = conn.execute("PRAGMA page_count").fetchone()[0]
    return pages * conn.execute("PRAGMA page_size").fetchone()[0]


def _present_tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    present = _present_tables(conn)
    # i nomi vengono da TABLES (costanti del codice), mai da input esterno
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in TABLES if t in present}


def _dbstat_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1 FROM dbstat LIMIT 1").fetchall()
        return True
    except sqlite3.Error:
        return False


def _owner(name: str) -> str:
    return FTS_TABLE if name.startswith(FTS_TABLE + "_") else name


def _bytes_dbstat(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for tbl, size in conn.execute(
            "SELECT m.tbl_name, SUM(d.pgsize) FROM dbstat d "
            "JOIN sqlite_master m ON m.name = d.name GROUP BY m.tbl_name"):
        if tbl.startswith("sqlite_"):
            continue
        key = _owner(tbl)
        out[key] = out.get(key, 0) + int(size or 0)
    return out


def _bytes_estimate(conn: sqlite3.Connection, rows: dict[str, int]) -> dict[str, int]:
    """(size - free) ripartito per righe x peso, con resti assegnati ai piu' grandi: la somma
    e' esatta."""
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    used = max(0, _size(conn) - conn.execute("PRAGMA freelist_count").fetchone()[0] * page_size)
    weights = {t: n * ROW_WEIGHTS.get(t, DEFAULT_WEIGHT) for t, n in rows.items()}
    total = sum(weights.values())
    if total <= 0:
        return {t: 0 for t in rows}
    exact = {t: used * w / total for t, w in weights.items()}
    out = {t: int(v) for t, v in exact.items()}
    rest = used - sum(out.values())
    for t in sorted(exact, key=lambda t: exact[t] - out[t], reverse=True)[:rest]:
        out[t] += 1
    return out


def table_bytes(conn: sqlite3.Connection, rows: dict[str, int] | None = None
                ) -> tuple[dict[str, int], str]:
    """Byte occupati da ogni tabella (indici compresi): dbstat se compilato, altrimenti stima."""
    if _dbstat_available(conn):
        return _bytes_dbstat(conn), "dbstat"
    return _bytes_estimate(conn, rows if rows is not None else _row_counts(conn)), "estimate"


def read_db_stats(db_path: Path) -> dict:
    """Statistiche con una connessione propria in sola lettura (adatta a to_thread)."""
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    try:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        rows = _row_counts(conn)
        key = str(Path(db_path).resolve())
        cached = _table_bytes_cache.get(key)
        now = _clock()
        if cached is None or now - cached[0] > TABLE_BYTES_CACHE_S:
            sizes, method = table_bytes(conn, rows)
            _table_bytes_cache[key] = (now, sizes, method)
        else:
            sizes, method = cached[1], cached[2]
        return {
            "size_bytes": _size(conn),
            "free_bytes": conn.execute("PRAGMA freelist_count").fetchone()[0] * page_size,
            "schema_version": conn.execute("PRAGMA user_version").fetchone()[0],
            "rows": rows,
            "table_bytes": dict(sizes),
            "table_bytes_method": method,
        }
    finally:
        conn.close()


def compact(conn: sqlite3.Connection) -> tuple[int, int]:
    """VACUUM (bloccante). Passa il database ad auto_vacuum=INCREMENTAL. Ritorna byte prima/dopo."""
    conn.commit()
    _table_bytes_cache.clear()  # lo spazio per tabella cambia: niente valori vecchi
    before = _size(conn)
    conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
    conn.execute("VACUUM")
    # VACUUM puo' rinumerare i rowid impliciti di messages: l'indice di ricerca si ricostruisce
    if rebuild_search_index(conn):
        conn.commit()
        conn.execute("PRAGMA incremental_vacuum").fetchall()  # pagine liberate dalla ricostruzione
    return before, _size(conn)
