"""Statistiche e compattazione del database."""
import sqlite3
from pathlib import Path

TABLES = ("nodes", "positions", "messages", "telemetry", "links", "traceroutes",
          "coverage_points", "sessions", "metrics", "packets")


def _size(conn: sqlite3.Connection) -> int:
    pages = conn.execute("PRAGMA page_count").fetchone()[0]
    return pages * conn.execute("PRAGMA page_size").fetchone()[0]


def read_db_stats(db_path: Path) -> dict:
    """Statistiche con una connessione propria in sola lettura (adatta a to_thread)."""
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    try:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        return {
            "size_bytes": _size(conn),
            "free_bytes": conn.execute("PRAGMA freelist_count").fetchone()[0] * page_size,
            "schema_version": conn.execute("PRAGMA user_version").fetchone()[0],
            "rows": {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES},
        }
    finally:
        conn.close()


def compact(conn: sqlite3.Connection) -> tuple[int, int]:
    """VACUUM (bloccante). Passa il database ad auto_vacuum=INCREMENTAL. Ritorna byte prima/dopo."""
    conn.commit()
    before = _size(conn)
    conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
    conn.execute("VACUUM")
    return before, _size(conn)
