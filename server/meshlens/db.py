"""Connessione SQLite e schema."""
import sqlite3
from pathlib import Path

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
  channel_index INTEGER, packet_id INTEGER, status TEXT);
CREATE TABLE IF NOT EXISTS telemetry(
  id INTEGER PRIMARY KEY AUTOINCREMENT, node_num INTEGER, time REAL, battery INTEGER,
  voltage REAL, channel_util REAL, air_util_tx REAL, uptime INTEGER);
CREATE TABLE IF NOT EXISTS radios(
  id TEXT PRIMARY KEY, name TEXT, kind TEXT, address TEXT, auto_connect INTEGER DEFAULT 1,
  created REAL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS auth(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, created REAL, last_seen REAL, user_agent TEXT);
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
CREATE TABLE IF NOT EXISTS coverage_prepare(
  id INTEGER PRIMARY KEY AUTOINCREMENT, radio_id TEXT, mobile_num INTEGER, created REAL,
  applied REAL, restored REAL, steps TEXT);
CREATE INDEX IF NOT EXISTS idx_config_reads_node ON config_reads(node_num, time);
CREATE INDEX IF NOT EXISTS idx_config_backups_node ON config_backups(node_num, time);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cov_points_seq
  ON coverage_points(session_id, segment, seq) WHERE seq IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cov_points_session ON coverage_points(session_id);
CREATE INDEX IF NOT EXISTS idx_cov_track_session ON coverage_track(session_id);
CREATE INDEX IF NOT EXISTS idx_links_time ON links(time);
CREATE INDEX IF NOT EXISTS idx_positions_node_time ON positions(node_num, time);
CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(time);
CREATE INDEX IF NOT EXISTS idx_telemetry_node_time ON telemetry(node_num, time);
"""

# colonne aggiunte dopo la fase 1: (tabella, colonna, definizione)
_MIGRATIONS = (
    ("nodes", "heard_by", "TEXT"),
    ("messages", "direction", "TEXT DEFAULT 'in'"),
    ("messages", "radio_id", "TEXT"),
    ("messages", "channel_index", "INTEGER"),
    ("messages", "packet_id", "INTEGER"),
    ("messages", "status", "TEXT"),
    ("config_jobs", "error_code", "TEXT"),
    ("nodes", "is_favorite", "INTEGER DEFAULT 0"),
    ("nodes", "hops_min", "INTEGER"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, definition in _MIGRATIONS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    # 1.2.0: i salti dei nodi solo-MQTT erano calcolati da hop_start (privi di senso): si azzerano
    done = conn.execute("SELECT 1 FROM settings WHERE key='migr_hops_mqtt_v120'").fetchone()
    if not done:
        conn.execute("UPDATE nodes SET hops = NULL WHERE sources = '[\"mqtt\"]'")
        conn.execute("INSERT INTO settings(key, value) VALUES('migr_hops_mqtt_v120', '1')")


def connect(path: Path | str) -> sqlite3.Connection:
    """Apre il database (WAL, righe come Row) creando lo schema se assente."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn
