import sqlite3

from meshlens.db import SCHEMA_VERSION, connect, schema_version

EXPECTED_INDEXES = {
    "idx_messages_country_time", "idx_messages_radio_time", "idx_nodes_last_heard",
    "idx_traceroutes_target_time", "idx_cov_points_session_time", "idx_positions_time",
    "idx_telemetry_time",
}


def _legacy(path):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE nodes(num INTEGER PRIMARY KEY, id TEXT, hops INTEGER, sources TEXT, last_heard REAL)")
    c.execute("CREATE TABLE messages(key TEXT PRIMARY KEY, text TEXT, time REAL, country TEXT)")
    c.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, created REAL)")
    c.execute("CREATE TABLE coverage_points(id INTEGER PRIMARY KEY, session_id INTEGER, segment INTEGER, seq INTEGER, time REAL)")
    c.execute("CREATE INDEX idx_cov_points_session ON coverage_points(session_id)")
    c.execute("INSERT INTO messages(key, text, time) VALUES('k', 'ciao', 1.0)")
    c.commit()
    c.close()


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_new_db_has_current_version_and_incremental_vacuum(tmp_path):
    calls = []
    conn = connect(tmp_path / "n.db", lambda *a: calls.append(a))
    assert schema_version(conn) == SCHEMA_VERSION == 3
    assert conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
    assert calls == []
    assert "ip" in _cols(conn, "sessions")


def test_legacy_db_is_migrated_after_hook(tmp_path):
    path = tmp_path / "l.db"
    _legacy(path)
    calls = []

    def hook(conn, old, new):
        calls.append((old, new, "radio_id" in _cols(conn, "messages")))

    conn = connect(path, hook)
    assert calls == [(0, 3, False)]
    assert "radio_id" in _cols(conn, "messages")
    assert conn.execute("SELECT text FROM messages WHERE key='k'").fetchone()[0] == "ciao"
    assert schema_version(conn) == 3


def test_reopen_does_not_migrate_again(tmp_path):
    path = tmp_path / "l.db"
    _legacy(path)
    connect(path).close()
    calls = []
    connect(path, lambda *a: calls.append(a))
    assert calls == []


def test_indexes_exist(tmp_path):
    conn = connect(tmp_path / "i.db")
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert EXPECTED_INDEXES <= names
    assert "idx_cov_points_session" not in names


def test_legacy_db_gets_indexes(tmp_path):
    path = tmp_path / "l.db"
    _legacy(path)
    conn = connect(path)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert EXPECTED_INDEXES <= names
    assert "idx_cov_points_session" not in names


def test_query_plans_use_indexes(tmp_path):
    conn = connect(tmp_path / "q.db")
    plan = " ".join(
        r[3] for r in conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM messages WHERE country=? "
            "ORDER BY time DESC LIMIT 50", ("IT",)))
    assert "idx_messages_country_time" in plan


def test_migration_3_adds_broker_column(tmp_path):
    path = tmp_path / "v2.db"
    conn = connect(path)
    conn.execute("ALTER TABLE messages DROP COLUMN broker")
    conn.execute("INSERT INTO messages(key, text, time) VALUES('k', 'ciao', 1.0)")
    conn.execute("PRAGMA user_version=2")
    conn.commit()
    conn.close()
    assert "broker" not in _cols(sqlite3.connect(path), "messages")
    calls = []
    conn = connect(path, lambda *a: calls.append(a))
    assert [c[1:] for c in calls] == [(2, 3)]
    assert schema_version(conn) == 3
    assert "broker" in _cols(conn, "messages")
    row = conn.execute("SELECT text, broker FROM messages WHERE key='k'").fetchone()
    assert (row[0], row[1]) == ("ciao", None)
