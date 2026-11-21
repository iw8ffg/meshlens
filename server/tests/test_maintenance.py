from meshlens.db import connect
from meshlens.maintenance import compact, read_db_stats


def _fill(conn, n=20000):
    conn.executemany(
        "INSERT INTO messages(key, from_num, text, time, source) VALUES(?, 1, ?, ?, 'mqtt')",
        [(f"1:{i}", "x" * 200, float(i)) for i in range(n)])
    conn.commit()


def test_read_db_stats_counts_rows(tmp_path):
    path = tmp_path / "m.db"
    conn = connect(path)
    _fill(conn, 50)
    stats = read_db_stats(path)
    assert stats["rows"]["messages"] == 50 and stats["rows"]["nodes"] == 0
    assert stats["size_bytes"] > 0 and stats["free_bytes"] >= 0
    assert stats["schema_version"] >= 2
    assert set(stats["rows"]) == {"nodes", "positions", "messages", "telemetry", "links",
                                  "traceroutes", "coverage_points", "sessions"}
    conn.close()


def test_compact_reduces_free_pages(tmp_path):
    conn = connect(tmp_path / "m.db")
    _fill(conn)
    conn.execute("DELETE FROM messages")
    conn.commit()
    before, after = compact(conn)
    assert after < before
    assert conn.execute("PRAGMA freelist_count").fetchone()[0] == 0
    conn.close()
