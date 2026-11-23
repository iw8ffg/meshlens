import sqlite3

from meshlens import db
from meshlens.db import SCHEMA_VERSION, connect, ensure_search_index, schema_version, search_engine

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
    assert schema_version(conn) == SCHEMA_VERSION == 7
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
    assert calls == [(0, 7, False)]
    assert "radio_id" in _cols(conn, "messages")
    assert conn.execute("SELECT text FROM messages WHERE key='k'").fetchone()[0] == "ciao"
    assert schema_version(conn) == SCHEMA_VERSION == 7


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
    assert [c[1:] for c in calls] == [(2, 7)]
    assert schema_version(conn) == SCHEMA_VERSION == 7
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
    assert [c[1:] for c in calls] == [(3, 7)]
    assert schema_version(conn) == SCHEMA_VERSION == 7
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
    assert schema_version(conn) == SCHEMA_VERSION == 7
    assert _cols(conn, "waypoints") and _cols(conn, "conversation_reads")


def test_new_db_is_v5_with_new_tables():
    conn = connect(":memory:")
    assert schema_version(conn) == SCHEMA_VERSION == 7
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
    assert calls == [(4, 7)]
    assert conn.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0] == 3
    assert schema_version(conn) == SCHEMA_VERSION == 7
    assert _cols(conn, "metrics") == {"node_num", "time", "variant", "metric", "value"}
    conn.close()
    calls.clear()
    connect(path, lambda *a: calls.append(a)).close()
    assert calls == []


def test_v5_db_migrates_to_6_with_heard_by(tmp_path):
    path = tmp_path / "v5.db"
    conn = connect(path)
    conn.execute("ALTER TABLE messages DROP COLUMN heard_by")
    conn.execute("INSERT INTO messages(key, text, time, status) VALUES('k', 'ciao', 1.0, 'sent')")
    conn.execute("PRAGMA user_version=5")
    conn.commit()
    conn.close()
    calls = []
    conn = connect(path, lambda c, old, new: calls.append((old, new)))
    assert calls == [(5, 7)] and schema_version(conn) == SCHEMA_VERSION == 7
    assert "heard_by" in _cols(conn, "messages")
    assert conn.execute("SELECT status, heard_by FROM messages WHERE key='k'").fetchone()[:] == ("sent", None)


# ---- schema 7 (1.6) ----

V7_TABLES = {"alert_rules", "config_profiles", "sensor_events", "trace_targets", "tak_contacts"}
V7_INDEXES = {
    "idx_alert_rules_kind", "idx_config_profiles_name", "idx_sensor_events_node_time",
    "idx_sensor_events_time", "idx_tak_contacts_time", "idx_traceroutes_time",
    "idx_messages_from_time",
}


def _names(conn, kind):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type=?", (kind,))}


def _match(conn, word):
    return [r[0] for r in conn.execute(
        "SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?", (word,))]


def test_v7_tables_columns_indexes(tmp_path):
    conn = connect(tmp_path / "v7.db")
    assert V7_TABLES <= _names(conn, "table")
    assert "is_ignored" in _cols(conn, "nodes")
    assert "role" in _cols(conn, "sessions")
    assert {"auto", "route"} <= _cols(conn, "traceroutes")
    assert V7_INDEXES <= _names(conn, "index")
    unique = {r[1]: r[2] for r in conn.execute("PRAGMA index_list(config_profiles)")}
    assert unique["idx_config_profiles_name"] == 1


def test_v7_migration_is_idempotent(tmp_path):
    conn = connect(tmp_path / "v7.db")
    before = conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
    conn.execute("BEGIN")
    db._migration_7(conn)
    conn.execute("COMMIT")
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == before


def _drop_search_index(conn):
    """Toglie gli oggetti FTS: un vero database 1.5.1 non li ha."""
    for trig in db.SEARCH_TRIGGERS:
        conn.execute(f"DROP TRIGGER IF EXISTS {trig}")
    conn.execute("DROP TABLE IF EXISTS messages_fts")


def test_upgrade_from_v6_keeps_data(tmp_path, monkeypatch):
    path = tmp_path / "v6.db"
    monkeypatch.setattr(db, "SCHEMA_VERSION", 6)
    conn = connect(path)
    assert schema_version(conn) == 6
    _drop_search_index(conn)
    conn.execute("INSERT INTO sessions(token_hash, created, last_seen) VALUES('h', 1, 1)")
    conn.execute("INSERT INTO nodes(num, id, last_heard) VALUES(1, '!00000001', 1)")
    conn.execute("INSERT INTO messages(key, text, time) VALUES('a', 'Ciao a tutti', 1)")
    conn.execute("INSERT INTO messages(key, text, time) VALUES('b', 'altro testo', 2)")
    conn.commit()
    conn.close()
    monkeypatch.undo()
    calls = []

    def hook(c, old, new):
        calls.append((old, new, "role" in _cols(c, "sessions")))

    conn = connect(path, hook)
    assert calls == [(6, 7, False)]
    assert schema_version(conn) == 7
    assert conn.execute("SELECT role FROM sessions").fetchone()[0] == "admin"
    flag = conn.execute("SELECT value FROM settings WHERE key='onboarding_done'").fetchone()
    assert flag[0] == "true"
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
    rowid = conn.execute("SELECT rowid FROM messages WHERE key='a'").fetchone()[0]
    assert _match(conn, "ciao") == [rowid]
    conn.close()
    calls.clear()
    connect(path, lambda *a: calls.append(a)).close()
    assert calls == []


def test_fresh_db_has_no_onboarding_flag(tmp_path):
    conn = connect(tmp_path / "f.db")
    assert conn.execute("SELECT 1 FROM settings WHERE key='onboarding_done'").fetchone() is None


def test_fts_triggers_follow_inserts_and_deletes(tmp_path):
    conn = connect(tmp_path / "f.db")
    conn.execute("INSERT INTO messages(key, text, time) VALUES('k', 'perché città', 1)")
    assert len(_match(conn, "perche")) == 1
    conn.execute("INSERT OR IGNORE INTO messages(key, text, time) VALUES('k', 'perché città', 1)")
    assert conn.execute("SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH 'citta'"
                        ).fetchone()[0] == 1
    conn.execute("DELETE FROM messages")
    assert _match(conn, "perche") == []


def test_search_engine_reports_fts5(tmp_path):
    conn = connect(tmp_path / "f.db")
    assert search_engine(conn) == "fts5"


def _db_without_fts(path, monkeypatch):
    """Database con indice aperto da un SQLite senza FTS5 e un messaggio inserito senza trigger."""
    conn = connect(path)
    monkeypatch.setattr(db, "fts5_available", lambda conn: False)
    assert ensure_search_index(conn) == "like"
    conn.commit()
    conn.execute("INSERT INTO messages(key, text, time) VALUES('k', 'x', 1)")
    conn.commit()
    return conn


def test_without_fts5_triggers_dropped_and_inserts_work(tmp_path, monkeypatch):
    conn = _db_without_fts(tmp_path / "nofts.db", monkeypatch)
    assert not set(db.SEARCH_TRIGGERS) & _names(conn, "trigger")
    assert conn.execute("SELECT text FROM messages WHERE key='k'").fetchone()[0] == "x"
    assert search_engine(conn) == "like"


def test_fts5_back_rebuilds_index(tmp_path, monkeypatch):
    path = tmp_path / "nofts.db"
    _db_without_fts(path, monkeypatch).close()
    monkeypatch.undo()
    conn = connect(path)
    assert search_engine(conn) == "fts5"
    assert set(db.SEARCH_TRIGGERS) <= _names(conn, "trigger")
    rowid = conn.execute("SELECT rowid FROM messages WHERE key='k'").fetchone()[0]
    assert _match(conn, "x") == [rowid]


def test_new_db_without_fts5_migrates(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "fts5_available", lambda conn: False)
    conn = connect(tmp_path / "nofts.db")
    assert schema_version(conn) == 7
    assert "messages_fts" not in _names(conn, "table")
    conn.execute("INSERT INTO messages(key, text, time) VALUES('k', 'x', 1)")
    assert search_engine(conn) == "like"



# ---- correzioni della revisione di WP0 ----

def test_probe_uses_the_real_tokenizer(tmp_path, monkeypatch):
    conn = connect(tmp_path / "p.db")
    assert db.fts5_available(conn)
    monkeypatch.setattr(db, "FTS_TOKENIZE", "inesistente")
    assert db.fts5_available(conn) is False


def test_index_creation_error_falls_back_to_like(tmp_path, monkeypatch):
    path = tmp_path / "e.db"
    monkeypatch.setattr(db, "fts5_available", lambda conn: True)
    monkeypatch.setattr(db, "_SEARCH_TABLE", "CREATE VIRTUAL TABLE messages_fts USING nessuno(x)")
    conn = connect(path)
    assert schema_version(conn) == 7
    assert not set(db.SEARCH_TRIGGERS) & _names(conn, "trigger")
    conn.execute("INSERT INTO messages(key, text, time) VALUES('k', 'x', 1)")
    assert search_engine(conn) == "like"


def test_broken_index_never_blocks_startup(tmp_path, monkeypatch, caplog):
    path = tmp_path / "b.db"
    connect(path).close()

    def boom(conn):
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(db, "ensure_search_index", boom)
    conn = connect(path)  # si apre lo stesso
    assert not set(db.SEARCH_TRIGGERS) & _names(conn, "trigger")
    conn.execute("INSERT INTO messages(key, text, time) VALUES('k', 'x', 1)")
    assert "Indice di ricerca" in caplog.text


def test_rebuild_after_compact_keeps_search_consistent(tmp_path):
    from meshlens.maintenance import compact
    conn = connect(tmp_path / "c.db")
    for i in range(50):
        conn.execute("INSERT INTO messages(key, text, time) VALUES(?, ?, ?)",
                     (f"k{i}", f"parola{i} comune", i))
    conn.execute("DELETE FROM messages WHERE time < 25")
    conn.commit()
    compact(conn)
    rows = conn.execute("SELECT m.key FROM messages_fts f JOIN messages m ON m.rowid = f.rowid "
                        "WHERE messages_fts MATCH 'parola30'").fetchall()
    assert [r[0] for r in rows] == ["k30"]
    assert db.rebuild_search_index(conn) is True
