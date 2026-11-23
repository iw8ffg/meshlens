import ast
import inspect
import sqlite3

import pytest

from meshlens import maintenance
from meshlens.db import connect
from meshlens.maintenance import TABLES, compact, read_db_stats


@pytest.fixture(autouse=True)
def _fresh_cache():
    maintenance._table_bytes_cache.clear()
    yield
    maintenance._table_bytes_cache.clear()


def _fill(conn, n=20000):
    conn.executemany(
        "INSERT INTO messages(key, from_num, text, time, source) VALUES(?, 1, ?, ?, 'mqtt')",
        [(f"1:{i}", "x" * 200, float(i)) for i in range(n)])
    conn.commit()


def _nodes(conn, n):
    conn.executemany("INSERT INTO nodes(num, long_name) VALUES(?, ?)",
                     [(i, f"n{i}") for i in range(1, n + 1)])
    conn.commit()


def test_read_db_stats_counts_rows(tmp_path):
    path = tmp_path / "m.db"
    conn = connect(path)
    _fill(conn, 50)
    stats = read_db_stats(path)
    assert stats["rows"]["messages"] == 50 and stats["rows"]["nodes"] == 0
    assert stats["size_bytes"] > 0 and stats["free_bytes"] >= 0
    assert stats["schema_version"] >= 2
    assert set(stats["rows"]) == set(TABLES)
    conn.close()


def test_rows_include_new_tables_when_present(tmp_path):
    path = tmp_path / "m.db"
    connect(path).close()
    assert set(read_db_stats(path)["rows"]) == set(TABLES)
    old = tmp_path / "old.db"
    c = sqlite3.connect(old)
    c.execute("CREATE TABLE nodes(num INTEGER PRIMARY KEY)")
    c.execute("CREATE TABLE messages(key TEXT, time REAL)")
    c.execute("PRAGMA user_version=6")
    c.commit()
    c.close()
    stats = read_db_stats(old)
    assert set(stats["rows"]) == {"nodes", "messages"}
    assert stats["table_bytes_method"] in ("dbstat", "estimate")


def _dbstat_compiled() -> bool:
    c = sqlite3.connect(":memory:")
    try:
        return maintenance._dbstat_available(c)
    finally:
        c.close()


@pytest.mark.skipif(not _dbstat_compiled(), reason="dbstat non compilato in questo SQLite")
def test_table_bytes_dbstat(tmp_path):
    path = tmp_path / "m.db"
    conn = connect(path)
    _fill(conn, 2000)
    _nodes(conn, 50)
    stats = read_db_stats(path)
    tb = stats["table_bytes"]
    assert stats["table_bytes_method"] == "dbstat"
    assert tb["messages"] > tb["nodes"] > 0
    assert sum(tb.values()) <= stats["size_bytes"]
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='messages_fts'").fetchone():
        assert "messages_fts" in tb and not any(k.startswith("messages_fts_") for k in tb)
    conn.close()


def test_table_bytes_estimate_when_dbstat_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, "_dbstat_available", lambda c: False)
    path = tmp_path / "m.db"
    conn = connect(path)
    _fill(conn, 500)
    _nodes(conn, 10)
    conn.executemany("INSERT INTO packets(time, from_num, status) VALUES(?, 1, 'ok')",
                     [(float(i),) for i in range(100)])
    conn.commit()
    stats = read_db_stats(path)
    tb = stats["table_bytes"]
    assert stats["table_bytes_method"] == "estimate"
    assert all(v >= 0 for v in tb.values())
    assert abs(sum(tb.values()) - (stats["size_bytes"] - stats["free_bytes"])) <= 1
    assert tb["packets"] > tb["nodes"] and tb["messages"] > tb["packets"]
    conn.close()


def test_table_bytes_empty_database(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, "_dbstat_available", lambda c: False)
    path = tmp_path / "m.db"
    connect(path).close()
    stats = read_db_stats(path)
    assert all(v == 0 for v in stats["table_bytes"].values())


def test_cache_120s(tmp_path, monkeypatch):
    path = tmp_path / "m.db"
    connect(path).close()
    calls = []
    real = maintenance.table_bytes
    monkeypatch.setattr(maintenance, "table_bytes",
                        lambda conn, rows=None: calls.append(1) or real(conn, rows))
    now = [1000.0]
    monkeypatch.setattr(maintenance, "_clock", lambda: now[0])
    read_db_stats(path)
    now[0] += 60
    read_db_stats(path)
    assert len(calls) == 1
    now[0] += 61
    read_db_stats(path)
    assert len(calls) == 2


def test_table_names_are_never_user_input():
    for fn in (maintenance.read_db_stats, maintenance._row_counts, maintenance.table_bytes,
               maintenance._bytes_dbstat, maintenance._bytes_estimate):
        tree = ast.parse(inspect.getsource(fn).lstrip())
        func = tree.body[0]
        params = {a.arg for a in func.args.args}
        for node in ast.walk(func):  # solo l'SQL: f-string passate a execute()
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "execute" and node.args
                    and isinstance(node.args[0], ast.JoinedStr)):
                names = {n.id for n in ast.walk(node.args[0]) if isinstance(n, ast.Name)}
                assert not names & params, (fn.__name__, names & params)


def test_compact_reduces_free_pages(tmp_path):
    conn = connect(tmp_path / "m.db")
    _fill(conn)
    conn.execute("DELETE FROM messages")
    conn.commit()
    before, after = compact(conn)
    assert after < before
    assert conn.execute("PRAGMA freelist_count").fetchone()[0] == 0
    conn.close()


def test_compact_clears_table_bytes_cache(tmp_path):
    path = tmp_path / "m.db"
    conn = connect(path)
    read_db_stats(path)
    assert maintenance._table_bytes_cache
    compact(conn)
    assert not maintenance._table_bytes_cache
    conn.close()
