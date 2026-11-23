"""Connessione SQLite e schema."""
import logging
import secrets
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

SCHEMA_VERSION = 7

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
CREATE TABLE IF NOT EXISTS sf_routers(
  num INTEGER PRIMARY KEY, radio_id TEXT, last_seen REAL, heartbeat_period INTEGER,
  secondary INTEGER, stats TEXT, last_request REAL);
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


_SCHEMA_V5 = """
CREATE TABLE IF NOT EXISTS metrics(
    node_num INTEGER NOT NULL, time REAL NOT NULL, variant TEXT NOT NULL,
    metric TEXT NOT NULL, value REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_metrics_node ON metrics(node_num, variant, metric, time);
CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics(time);
CREATE TABLE IF NOT EXISTS packets(
    id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL NOT NULL, from_num INTEGER,
    to_num INTEGER, packet_id INTEGER, source TEXT, broker TEXT, radio_id TEXT,
    channel TEXT, portnum TEXT, kind TEXT, status TEXT NOT NULL, snr REAL, rssi INTEGER,
    hops INTEGER, hop_start INTEGER, hop_limit INTEGER, relay_node INTEGER, gateway TEXT,
    copies INTEGER NOT NULL DEFAULT 1, receptions TEXT, summary TEXT, raw BLOB, size INTEGER);
CREATE INDEX IF NOT EXISTS idx_packets_time ON packets(time);
CREATE INDEX IF NOT EXISTS idx_packets_from_time ON packets(from_num, time);
CREATE INDEX IF NOT EXISTS idx_packets_kind_time ON packets(kind, time);
CREATE TABLE IF NOT EXISTS stats_hourly(
    time INTEGER NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL,
    packets INTEGER NOT NULL, receptions INTEGER NOT NULL, UNIQUE(time, source, kind));
CREATE TABLE IF NOT EXISTS node_hourly(
    time INTEGER NOT NULL, node_num INTEGER NOT NULL, source TEXT NOT NULL,
    packets INTEGER NOT NULL, snr_sum REAL NOT NULL DEFAULT 0,
    snr_n INTEGER NOT NULL DEFAULT 0, snr_max REAL, UNIQUE(time, node_num, source));
CREATE INDEX IF NOT EXISTS idx_node_hourly_node ON node_hourly(node_num, time);
"""


def _migration_5(conn: sqlite3.Connection) -> None:
    """Metriche generiche, ispettore dei pacchetti e aggregati orari: solo tabelle e indici
    nuovi, i dati esistenti non si toccano. Niente executescript (farebbe commit)."""
    for stmt in _SCHEMA_V5.split(";"):
        if stmt.strip():
            conn.execute(stmt)


def _migration_6(conn: sqlite3.Connection) -> None:
    """messages.heard_by: chi ha sentito in radio un messaggio inviato via MQTT (lista JSON)."""
    _add_missing_columns(conn, (("messages", "heard_by", "TEXT"),))


_COLUMNS_V7 = (
    # from_num c'e' dalla fase 1: solo per database molto vecchi/parziali, serve all'indice sotto
    ("messages", "from_num", "INTEGER"),
    ("nodes", "is_ignored", "INTEGER DEFAULT 0"),
    ("sessions", "role", "TEXT NOT NULL DEFAULT 'admin'"),
    ("traceroutes", "auto", "INTEGER DEFAULT 0"),
    ("traceroutes", "route", "TEXT"),
)

# una istruzione per elemento: niente split(";") (i corpi dei trigger contengono ";")
_SCHEMA_V7: tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS alert_rules("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', "
    "enabled INTEGER NOT NULL DEFAULT 1, node_num INTEGER, channel TEXT, threshold REAL, "
    "params TEXT NOT NULL DEFAULT '{}', cooldown_min INTEGER NOT NULL DEFAULT 60, "
    "created REAL NOT NULL, updated REAL NOT NULL, last_fired REAL)",
    "CREATE INDEX IF NOT EXISTS idx_alert_rules_kind ON alert_rules(kind, enabled)",
    "CREATE TABLE IF NOT EXISTS config_profiles("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created REAL NOT NULL, "
    "updated REAL NOT NULL, source_node_num INTEGER, source_hw TEXT, firmware TEXT, "
    "sections TEXT NOT NULL, data TEXT NOT NULL, notes TEXT)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_config_profiles_name ON config_profiles(name)",
    "CREATE TABLE IF NOT EXISTS sensor_events("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, node_num INTEGER NOT NULL, time REAL NOT NULL, "
    "kind TEXT NOT NULL, text TEXT, value REAL, source TEXT NOT NULL, radio_id TEXT, "
    "broker TEXT, packet_id INTEGER)",
    "CREATE INDEX IF NOT EXISTS idx_sensor_events_node_time ON sensor_events(node_num, time)",
    "CREATE INDEX IF NOT EXISTS idx_sensor_events_time ON sensor_events(time)",
    "CREATE TABLE IF NOT EXISTS trace_targets("
    "node_num INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1, "
    "interval_min INTEGER NOT NULL DEFAULT 180, radio_id TEXT, created REAL NOT NULL, "
    "last_run REAL, last_status TEXT, last_traceroute_id INTEGER, "
    "fail_count INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS tak_contacts("
    "node_num INTEGER PRIMARY KEY, callsign TEXT, device_callsign TEXT, team TEXT, role TEXT, "
    "battery INTEGER, lat REAL, lon REAL, altitude INTEGER, speed INTEGER, course INTEGER, "
    "compressed INTEGER NOT NULL DEFAULT 0, time REAL NOT NULL, source TEXT NOT NULL, "
    "radio_id TEXT, broker TEXT)",
    "CREATE INDEX IF NOT EXISTS idx_tak_contacts_time ON tak_contacts(time)",
    "CREATE INDEX IF NOT EXISTS idx_traceroutes_time ON traceroutes(time)",
    "CREATE INDEX IF NOT EXISTS idx_messages_from_time ON messages(from_num, time)",
)

SEARCH_TRIGGERS: tuple[str, ...] = ("messages_fts_ai", "messages_fts_ad", "messages_fts_au")

# opzioni del tokenizer: la prova di fts5_available usa le stesse (remove_diacritics 2 vuole
# SQLite >= 3.27: con uno piu' vecchio si ripiega su LIKE)
FTS_TOKENIZE = "unicode61 remove_diacritics 2"
_SEARCH_TABLE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
    "text, content='messages', content_rowid='rowid', "
    f"tokenize='{FTS_TOKENIZE}')"
)
_SEARCH_TRIGGER_SQL: dict[str, str] = {
    "messages_fts_ai":
        "CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN "
        "INSERT INTO messages_fts(rowid, text) VALUES (new.rowid, new.text); END",
    "messages_fts_ad":
        "CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN "
        "INSERT INTO messages_fts(messages_fts, rowid, text) "
        "VALUES('delete', old.rowid, old.text); END",
    "messages_fts_au":
        "CREATE TRIGGER IF NOT EXISTS messages_fts_au AFTER UPDATE OF text ON messages BEGIN "
        "INSERT INTO messages_fts(messages_fts, rowid, text) "
        "VALUES('delete', old.rowid, old.text); "
        "INSERT INTO messages_fts(rowid, text) VALUES (new.rowid, new.text); END",
}


def fts5_available(conn: sqlite3.Connection) -> bool:
    """True se il SQLite in uso ha FTS5 con il tokenizer dell'indice (prova su una tabella
    temporanea con le stesse opzioni)."""
    name = f"fts5_probe_{secrets.token_hex(4)}"
    try:
        conn.execute(f"CREATE VIRTUAL TABLE temp.{name} USING fts5(x, tokenize='{FTS_TOKENIZE}')")
    except sqlite3.DatabaseError:
        return False
    conn.execute(f"DROP TABLE temp.{name}")
    return True


def _drop_search_triggers(conn: sqlite3.Connection) -> None:
    for trig in SEARCH_TRIGGERS:
        conn.execute(f"DROP TRIGGER IF EXISTS {trig}")


def _master_names(conn: sqlite3.Connection, kind: str) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type=?", (kind,))}


def ensure_search_index(conn: sqlite3.Connection) -> str:
    """Indice di ricerca dei messaggi: "fts5" se il modulo c'e' (crea tabella e trigger
    mancanti e, se ha creato qualcosa, ricostruisce l'indice), altrimenti "like" (toglie i
    trigger, che farebbero fallire ogni INSERT su messages). Un errore dell'indice non solleva:
    i trigger si tolgono e si ripiega su "like" (i messaggi si salvano sempre). Non fa commit."""
    if not fts5_available(conn):
        _drop_search_triggers(conn)
        return "like"
    try:
        created = "messages_fts" not in _master_names(conn, "table")
        if created:
            conn.execute(_SEARCH_TABLE)
        triggers = _master_names(conn, "trigger")
        for trig in SEARCH_TRIGGERS:
            if trig not in triggers:
                conn.execute(_SEARCH_TRIGGER_SQL[trig])
                created = True
        if created:
            conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
    except sqlite3.DatabaseError as e:
        log.warning("Indice di ricerca dei messaggi non creato (%s): si usa LIKE", e)
        _drop_search_triggers(conn)
        return "like"
    return "fts5"


def rebuild_search_index(conn: sqlite3.Connection) -> bool:
    """Ricostruisce l'indice dai messaggi (dopo VACUUM o ripristino: i rowid impliciti di
    messages possono cambiare). False se l'indice non c'e' o non si puo' ricostruire (in quel
    caso i trigger si tolgono: la ricerca ripiega su LIKE). Non fa commit."""
    if search_engine(conn) != "fts5":
        return False
    try:
        conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
    except sqlite3.DatabaseError as e:
        log.warning("Indice di ricerca dei messaggi non ricostruito (%s): si usa LIKE", e)
        _drop_search_triggers(conn)
        return False
    return True


def search_engine(conn: sqlite3.Connection) -> str:
    """"fts5" se indice e trigger esistono e il modulo e' disponibile, altrimenti "like".
    Usabile anche su una connessione in sola lettura."""
    if "messages_fts" not in _master_names(conn, "table"):
        return "like"
    if not set(SEARCH_TRIGGERS) <= _master_names(conn, "trigger"):
        return "like"
    return "fts5" if fts5_available(conn) else "like"


def _migration_7(conn: sqlite3.Connection) -> None:
    """1.6: nodi ignorati, ruolo delle sessioni, traceroute automatici, tabelle di regole di
    avviso, profili, sensori, bersagli dei traceroute, contatti ATAK; indice di ricerca."""
    _add_missing_columns(conn, _COLUMNS_V7)
    for stmt in _SCHEMA_V7:
        conn.execute(stmt)
    # chi aggiorna un database con dati non vede l'avvio guidato
    conn.execute(
        "INSERT OR IGNORE INTO settings(key, value) SELECT 'onboarding_done', 'true' "
        "WHERE EXISTS(SELECT 1 FROM nodes) OR EXISTS(SELECT 1 FROM radios) "
        "OR EXISTS(SELECT 1 FROM settings WHERE key='mqtt_brokers')")
    ensure_search_index(conn)


_STEPS = {1: _migration_1, 2: _migration_2, 3: _migration_3, 4: _migration_4, 5: _migration_5,
          6: _migration_6, 7: _migration_7}


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
    _refresh_search_index(conn)
    return conn


def _refresh_search_index(conn: sqlite3.Connection) -> None:
    """A ogni apertura: indice creato se FTS5 e' tornato, trigger tolti se manca."""
    conn.execute("BEGIN")
    try:
        engine = ensure_search_index(conn)
        conn.commit()
    except Exception as e:  # noqa: BLE001 - l'indice non deve mai impedire l'avvio
        conn.rollback()
        log.warning("Indice di ricerca dei messaggi non utilizzabile (%s): si usa LIKE", e)
        engine = "like"
        try:
            _drop_search_triggers(conn)
            conn.commit()
        except sqlite3.DatabaseError:
            conn.rollback()
            log.exception("Indice di ricerca: impossibile togliere i trigger")
    global _like_logged
    if engine == "like" and not _like_logged:
        _like_logged = True
        log.info("Ricerca nei messaggi senza FTS5: si usa LIKE")


_like_logged = False
