"""Connessione SQLite e schema."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes(
  num INTEGER PRIMARY KEY, id TEXT, long_name TEXT, short_name TEXT, hw_model TEXT, role TEXT,
  firmware TEXT, lat REAL, lon REAL, precision_bits INTEGER, position_source TEXT,
  position_time INTEGER, country TEXT, last_heard REAL, sources TEXT, battery INTEGER,
  voltage REAL, channel_util REAL, air_util_tx REAL, mqtt_gateways INTEGER, last_snr REAL,
  hops INTEGER, is_mine INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS positions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, node_num INTEGER, time REAL, lat REAL, lon REAL,
  precision_bits INTEGER, source TEXT);
CREATE TABLE IF NOT EXISTS messages(
  key TEXT PRIMARY KEY, from_num INTEGER, to_num INTEGER, channel TEXT, text TEXT,
  time REAL, country TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS telemetry(
  id INTEGER PRIMARY KEY AUTOINCREMENT, node_num INTEGER, time REAL, battery INTEGER,
  voltage REAL, channel_util REAL, air_util_tx REAL, uptime INTEGER);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS auth(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, created REAL, last_seen REAL, user_agent TEXT);
CREATE INDEX IF NOT EXISTS idx_positions_node_time ON positions(node_num, time);
CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(time);
CREATE INDEX IF NOT EXISTS idx_telemetry_node_time ON telemetry(node_num, time);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    """Apre il database (WAL, righe come Row) creando lo schema se assente."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
