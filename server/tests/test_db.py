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
    assert schema_version(conn) == SCHEMA_VERSION == 5
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
    assert calls == [(0, 5, False)]
    assert "radio_id" in _cols(conn, "messages")
    assert conn.execute("SELECT text FROM messages WHERE key='k'").fetchone()[0] == "ciao"
    assert schema_version(conn) == 5


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
    assert [c[1:] for c in calls] == [(2, 5)]
    assert schema_version(conn) == 5
    assert "broker" in _cols(conn, "messages")
    row = conn.execute("SELECT text, broker FROM messages WHERE key='k'").fetchone()
    assert (row[0], row[1]) == ("ciao", None)


def test_migration_4_columns_and_tables(tmp_path):
    path = tmp_path / "v3.db"
    conn = connect(path)
    for table, col in (("messages", "reply_id"), ("messages", "emoji"), ("messages", "pki"),
                       ("messages", "error"), ("nodes", "public_key"), ("nodes", "key_changed")):
        conn.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
    conn.execute("DROP TABLE waypoints")
    conn.execute("DROP TABLE conversation_reads")
    conn.execute("DELETE FROM settings WHERE key='conv_read_baseline'")
    conn.execute("PRAGMA user_version=3")
    conn.commit()
    conn.close()
    calls = []
    conn = connect(path, lambda *a: calls.append(a))
    assert [c[1:] for c in calls] == [(3, 5)]
    assert schema_version(conn) == 5
    assert {"reply_id", "emoji", "pki", "error"} <= _cols(conn, "messages")
    assert {"public_key", "key_changed"} <= _cols(conn, "nodes")
    assert {"id", "from_num", "locked_to", "deleted"} <= _cols(conn, "waypoints")
    assert _cols(conn, "conversation_reads") == {"conv", "read_time"}
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='idx_waypoints_time'").fetchone()
    base = conn.execute("SELECT value FROM settings WHERE key='conv_read_baseline'").fetchone()
    assert float(base[0]) > 1_700_000_000
    conn.close()
    connect(path).close()  # idempotente: nessun errore e baseline invariata


def test_new_db_runs_migration_4():
    conn = connect(":memory:")
    assert schema_version(conn) == 5
    assert _cols(conn, "waypoints") and _cols(conn, "conversation_reads")


def test_new_db_is_v5_with_new_tables():
    conn = connect(":memory:")
    assert schema_version(conn) == 5
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {"metrics", "packets", "stats_hourly", "node_hourly"} <= names
    assert {"idx_metrics_node", "idx_metrics_time", "idx_packets_time", "idx_packets_from_time",
            "idx_packets_kind_time", "idx_node_hourly_node"} <= names


def test_v4_db_migrates_to_5_without_touching_telemetry(tmp_path):
    path = tmp_path / "v4.db"
    conn = connect(path)
    for table in ("metrics", "packets", "stats_hourly", "node_hourly"):
        conn.execute(f"DROP TABLE {table}")
    for i in range(3):
        conn.execute("INSERT INTO telemetry(node_num, time, battery) VALUES(1, ?, 50)", (float(i),))
    conn.execute("PRAGMA user_version=4")
    conn.commit()
    conn.close()
    calls = []
    conn = connect(path, lambda c, old, new: calls.append((old, new)))
    assert calls == [(4, 5)]
    assert conn.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0] == 3
    assert schema_version(conn) == 5
    assert _cols(conn, "metrics") == {"node_num", "time", "variant", "metric", "value"}
    conn.close()
    calls.clear()
    connect(path, lambda *a: calls.append(a)).close()
    assert calls == []
