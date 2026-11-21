"""Connessione SQLite e schema."""
import logging
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes(
  num INTEGER PRIMARY KEY, id TEXT, long_name TEXT, short_name TEXT, hw_model TEXT, role TEXT,
  firmware TEXT, lat REAL, lon REAL, precision_bits INTEGER, position_source TEXT,
  position_time INTEGER, country TEXT, last_heard REAL, sources TEXT, battery INTEGER,
  voltage REAL, channel_util REAL, air_util_tx REAL, mqtt_gateways INTEGER, last_snr REAL,
  hops INTEGER, is_mine INTEGER DEFAULT 0, heard_by TEXT, is_favorite INTEGER DEFAULT 0,
  hops_min INTEGER);
CREATE TABLE IF NOT EXISTS positions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, node_num INTEGER, time REAL, lat REAL, lon REAL,
  precision_bits INTEGER, source TEXT);
CREATE TABLE IF NOT EXISTS messages(
  key TEXT PRIMARY KEY, from_num INTEGER, to_num INTEGER, channel TEXT, text TEXT,
  time REAL, country TEXT, source TEXT, direction TEXT DEFAULT 'in', radio_id TEXT,
  channel_index INTEGER, packet_id INTEGER, status TEXT, broker TEXT);
CREATE TABLE IF NOT EXISTS telemetry(
  id INTEGER PRIMARY KEY AUTOINCREMENT, node_num INTEGER, time REAL, battery INTEGER,
  voltage REAL, channel_util REAL, air_util_tx REAL, uptime INTEGER);
CREATE TABLE IF NOT EXISTS radios(
  id TEXT PRIMARY KEY, name TEXT, kind TEXT, address TEXT, auto_connect INTEGER DEFAULT 1,
  created REAL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS auth(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, created REAL, last_seen REAL, user_agent TEXT, ip TEXT);
CREATE TABLE IF NOT EXISTS links(
  from_num INTEGER, to_num INTEGER, source TEXT, snr REAL, time REAL,
  PRIMARY KEY(from_num, to_num, source));
CREATE TABLE IF NOT EXISTS traceroutes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, radio_id TEXT, target_num INTEGER, time REAL,
  status TEXT, error TEXT, forward TEXT, back TEXT);
CREATE TABLE IF NOT EXISTS coverage_sessions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, radio_id TEXT, mobile_num INTEGER,
  mode TEXT, channel_index INTEGER, interval_s INTEGER, started REAL, ended REAL,
  end_reason TEXT, base_lat REAL, base_lon REAL, notes TEXT);
CREATE TABLE IF NOT EXISTS coverage_points(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, segment INTEGER, seq INTEGER,
  time REAL, snr REAL, rssi INTEGER, hops INTEGER, lat REAL, lon REAL, precision_bits INTEGER);
CREATE TABLE IF NOT EXISTS coverage_track(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, time REAL, lat REAL, lon REAL,
  precision_bits INTEGER);
CREATE TABLE IF NOT EXISTS config_reads(
  id INTEGER PRIMARY KEY AUTOINCREMENT, node_num INTEGER, radio_id TEXT, time REAL,
  sections TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS config_backups(
  id INTEGER PRIMARY KEY AUTOINCREMENT, node_num INTEGER, time REAL, reason TEXT, label TEXT,
  sections TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS config_jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, node_num INTEGER, radio_id TEXT, kind TEXT,
  status TEXT, step TEXT, done INTEGER, total INTEGER, error TEXT, result_id INTEGER,
  verify TEXT, started REAL, ended REAL);
CREATE TABLE IF NOT EXISTS auth_failures(
  ip TEXT PRIMARY KEY, failures INTEGER NOT NULL, locked_until REAL, last_failure REAL);
CREATE TABLE IF NOT EXISTS auth_attempts(time REAL, ip TEXT);
CREATE TABLE IF NOT EXISTS coverage_prepare(
  id INTEGER PRIMARY KEY AUTOINCREMENT, radio_id TEXT, mobile_num INTEGER, created REAL,
  applied REAL, restored REAL, steps TEXT);
CREATE INDEX IF NOT EXISTS idx_config_reads_node ON config_reads(node_num, time);
CREATE INDEX IF NOT EXISTS idx_config_backups_node ON config_backups(node_num, time);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cov_points_seq
  ON coverage_points(session_id, segment, seq) WHERE seq IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cov_track_session ON coverage_track(session_id);
CREATE INDEX IF NOT EXISTS idx_links_time ON links(time);
CREATE INDEX IF NOT EXISTS idx_positions_node_time ON positions(node_num, time);
CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(time);
CREATE INDEX IF NOT EXISTS idx_telemetry_node_time ON telemetry(node_num, time);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_time ON auth_attempts(time);
"""

# indici della migrazione 2: alcuni poggiano su colonne create dalla migrazione 1
# (messages.radio_id), quindi si applicano solo dopo di essa
_INDEXES_V2 = (
    "CREATE INDEX IF NOT EXISTS idx_messages_country_time ON messages(country, time)",
    "CREATE INDEX IF NOT EXISTS idx_messages_radio_time ON messages(radio_id, time)"
    " WHERE radio_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_nodes_last_heard ON nodes(last_heard)",
    "CREATE INDEX IF NOT EXISTS idx_traceroutes_target_time ON traceroutes(target_num, time)",
    "CREATE INDEX IF NOT EXISTS idx_cov_points_session_time ON coverage_points(session_id, time)",
    "DROP INDEX IF EXISTS idx_cov_points_session",
    "CREATE INDEX IF NOT EXISTS idx_positions_time ON positions(time)",
    "CREATE INDEX IF NOT EXISTS idx_telemetry_time ON telemetry(time)",
)

# colonne aggiunte dopo la fase 1: (tabella, colonna, definizione)
_MIGRATIONS = (
    ("nodes", "heard_by", "TEXT"),
    ("messages", "direction", "TEXT DEFAULT 'in'"),
    ("messages", "radio_id", "TEXT"),
    ("messages", "channel_index", "INTEGER"),
    ("messages", "packet_id", "INTEGER"),
    ("messages", "status", "TEXT"),
    ("messages", "broker", "TEXT"),
    ("config_jobs", "error_code", "TEXT"),
    ("nodes", "is_favorite", "INTEGER DEFAULT 0"),
    ("nodes", "hops_min", "INTEGER"),
)


def _add_missing_columns(conn: sqlite3.Connection, columns) -> None:
    for table, column, definition in columns:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migration_1(conn: sqlite3.Connection) -> None:
    """Colonne aggiunte dopo la fase 1 e correzione una tantum (idempotenti)."""
    _add_missing_columns(conn, _MIGRATIONS)
    # 1.2.0: i salti dei nodi solo-MQTT erano calcolati da hop_start (privi di senso): si azzerano
    done = conn.execute("SELECT 1 FROM settings WHERE key='migr_hops_mqtt_v120'").fetchone()
    if not done:
        conn.execute("UPDATE nodes SET hops = NULL WHERE sources = '[\"mqtt\"]'")
        conn.execute("INSERT INTO settings(key, value) VALUES('migr_hops_mqtt_v120', '1')")


def _migration_2(conn: sqlite3.Connection) -> None:
    """sessions.ip e indici nuovi (le tabelle auth_* arrivano da SCHEMA)."""
    _add_missing_columns(conn, (("sessions", "ip", "TEXT"),))
    for stmt in _INDEXES_V2:
        conn.execute(stmt)


def _migration_3(conn: sqlite3.Connection) -> None:
    """messages.broker: id del broker MQTT da cui e' arrivato il messaggio."""
    _add_missing_columns(conn, (("messages", "broker", "TEXT"),))


def _migration_4(conn: sqlite3.Connection) -> None:
    """Risposte, reazioni, PKI, chiavi pubbliche, waypoint e letture delle conversazioni."""
    _add_missing_columns(conn, (
        ("messages", "reply_id", "INTEGER"),
        ("messages", "emoji", "INTEGER DEFAULT 0"),
        ("messages", "pki", "INTEGER DEFAULT 0"),
        ("messages", "error", "TEXT"),
        ("nodes", "public_key", "TEXT"),
        ("nodes", "key_changed", "REAL"),
    ))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS waypoints("
        "id INTEGER PRIMARY KEY, from_num INTEGER, lat REAL, lon REAL, name TEXT, "
        "description TEXT, icon INTEGER, expire INTEGER, locked_to INTEGER, time REAL, "
        "source TEXT, radio_id TEXT, channel TEXT, country TEXT, deleted INTEGER DEFAULT 0)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_waypoints_time ON waypoints(time)")
    conn.execute("CREATE TABLE IF NOT EXISTS conversation_reads("
                 "conv TEXT PRIMARY KEY, read_time REAL NOT NULL)")
    # lo storico esistente non diventa "non letto": conta solo cio' che arriva dopo
    conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES('conv_read_baseline', ?)",
                 (str(time.time()),))


_STEPS = {1: _migration_1, 2: _migration_2, 3: _migration_3, 4: _migration_4}


log = logging.getLogger(__name__)


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _run_migrations(conn: sqlite3.Connection, old_version: int) -> None:
    """Porta lo schema da old_version a SCHEMA_VERSION: una transazione per passo."""
    conn.commit()
    for version in range(old_version + 1, SCHEMA_VERSION + 1):
        conn.execute("BEGIN")
        try:
            _STEPS[version](conn)
            conn.execute(f"PRAGMA user_version={version}")
            conn.commit()
            log.info("Migrazione del database eseguita: schema %s", version)
        except BaseException:
            conn.rollback()
            raise


def connect(
    path: Path | str,
    before_migrate: Callable[[sqlite3.Connection, int, int], None] | None = None,
) -> sqlite3.Connection:
    """Apre il database (WAL, righe come Row), creando o migrando lo schema.

    before_migrate(conn, old, new) e' chiamata solo per un database gia' esistente
    da migrare, prima di qualsiasi modifica dello schema.
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    old = schema_version(conn)
    existing = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nodes'"
    ).fetchone() is not None
    if not existing:
        # va impostato prima di journal_mode=WAL (che scrive l'intestazione) e delle tabelle
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
    conn.execute("PRAGMA journal_mode=WAL")
    if existing and old < SCHEMA_VERSION and before_migrate is not None:
        before_migrate(conn, old, SCHEMA_VERSION)
    conn.executescript(SCHEMA)
    _run_migrations(conn, old)
    return conn
