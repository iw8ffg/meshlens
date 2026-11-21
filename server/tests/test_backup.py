import asyncio
import sqlite3

import pytest

from meshlens.app import build
from meshlens.backup import (BACKUP_WEEKLY_S, BackupManager, apply_pending_restore,
                             KEEP_BY_REASON, quick_check, quick_check_file)
from meshlens.db import connect


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def mgr(tmp_path, clock=None):
    db = tmp_path / "meshlens.db"
    conn = connect(db)
    return conn, BackupManager(db, tmp_path / "backups", clock or Clock(1_700_000_000))


def test_create_and_list_and_prune(tmp_path):
    clock = Clock(1_700_000_000)
    conn, m = mgr(tmp_path, clock)
    for i in range(7):
        clock.t += 100
        m.create_sync(conn, "manuale" if i % 2 else "settimanale")
    items = m.list()
    assert len(items) == 5  # 2 manuali + 3 settimanali
    assert [b["time"] for b in items] == sorted((b["time"] for b in items), reverse=True)
    assert items[0]["time"] > items[-1]["time"]
    assert {b["reason"] for b in items} == {"manuale", "settimanale"}
    assert all(b["size_bytes"] > 0 for b in items)
    conn.close()


async def test_async_backup_while_writer_open(tmp_path):
    conn, m = mgr(tmp_path)
    conn.execute("INSERT INTO settings(key, value) VALUES('a', '1')")
    conn.commit()
    conn.execute("INSERT INTO settings(key, value) VALUES('b', '2')")  # transazione aperta
    info = await m.create("manuale")
    assert info["reason"] == "manuale"
    copy = sqlite3.connect(m.dir / info["name"])
    keys = {r[0] for r in copy.execute("SELECT key FROM settings")}
    copy.close()
    assert "a" in keys and "b" not in keys
    conn.rollback()
    conn.close()


def test_due_weekly(tmp_path):
    clock = Clock(1_700_000_000)
    conn, m = mgr(tmp_path, clock)
    assert m.due(clock.t)
    m.create_sync(conn, "manuale")
    assert not m.due(clock.t + 6 * 86400)
    assert m.due(clock.t + 8 * 86400)
    assert m.due(clock.t + BACKUP_WEEKLY_S)
    conn.close()


def test_premigration_backup_from_legacy_db(tmp_path):
    legacy = sqlite3.connect(tmp_path / "meshlens.db")
    legacy.executescript(
        "CREATE TABLE nodes(num INTEGER PRIMARY KEY, id TEXT, long_name TEXT, hops INTEGER, sources TEXT, last_heard REAL, is_mine INTEGER DEFAULT 0);"
        "CREATE TABLE messages(key TEXT PRIMARY KEY, text TEXT, time REAL, country TEXT);"
        "CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);"
        "INSERT INTO nodes(num, id, long_name) VALUES(7, '!00000007', 'Vecchio');")
    legacy.commit()
    assert legacy.execute("PRAGMA user_version").fetchone()[0] == 0
    legacy.close()

    _, rt = build(tmp_path, static_dir=None)
    rt.conn.close()
    found = sorted((tmp_path / "backups").glob("*-pre-migrazione.db"))
    assert len(found) == 1
    old = sqlite3.connect(found[0])
    assert old.execute("PRAGMA user_version").fetchone()[0] == 0  # schema non migrato
    cols = {r[1] for r in old.execute("PRAGMA table_info(nodes)")}
    assert "heard_by" not in cols and "hops_min" not in cols
    assert old.execute("SELECT long_name FROM nodes WHERE num=7").fetchone()[0] == "Vecchio"
    old.close()
    assert rt.db_health == "in corso"  # il controllo gira in un thread all'avvio
    asyncio.run(rt.check_integrity())
    assert rt.db_health == "ok"

    _, rt2 = build(tmp_path, static_dir=None)  # gia' migrato: niente altro backup
    rt2.conn.close()
    assert len(list((tmp_path / "backups").glob("*-pre-migrazione.db"))) == 1


def test_restore_roundtrip(tmp_path):
    conn, m = mgr(tmp_path)
    conn.execute("INSERT INTO settings(key, value) VALUES('marker', '\"vecchio\"')")
    conn.commit()
    name = m.create_sync(conn, "manuale")["name"]
    conn.execute("UPDATE settings SET value='\"nuovo\"' WHERE key='marker'")
    conn.commit()
    conn.close()
    m.schedule_restore(name)
    assert (tmp_path / "restore.json").exists()
    assert apply_pending_restore(tmp_path) == name
    assert not (tmp_path / "restore.json").exists()
    cur = sqlite3.connect(tmp_path / "meshlens.db")
    assert cur.execute("SELECT value FROM settings WHERE key='marker'").fetchone()[0] == '"vecchio"'
    cur.close()
    safety = list((tmp_path / "backups").glob("*-prima-del-ripristino.db"))
    assert len(safety) == 1
    s = sqlite3.connect(safety[0])
    assert s.execute("SELECT value FROM settings WHERE key='marker'").fetchone()[0] == '"nuovo"'
    s.close()
    assert apply_pending_restore(tmp_path) is None


@pytest.mark.parametrize("name", ["../meshlens.db", "x.db", "meshlens-20240101-000000-a/b.db"])
def test_restore_rejects_bad_names(tmp_path, name):
    _, m = mgr(tmp_path)
    with pytest.raises(ValueError):
        m.schedule_restore(name)


def test_pending_restore_with_bad_name_is_ignored(tmp_path):
    (tmp_path / "restore.json").write_text('{"name": "../x.db"}')
    assert apply_pending_restore(tmp_path) is None
    assert not (tmp_path / "restore.json").exists()


def test_quick_check_ok(tmp_path):
    conn, _ = mgr(tmp_path)
    assert quick_check(conn) == "ok"
    conn.close()


def test_zero_byte_and_corrupt_backup_refused(tmp_path):
    from meshlens.backup import BackupUnusable
    conn, m = mgr(tmp_path)
    conn.close()
    m.dir.mkdir(exist_ok=True)
    (m.dir / "meshlens-20240101-000000-manuale.db").write_bytes(b"")
    (m.dir / "meshlens-20240101-000001-manuale.db").write_bytes(b"questo non e' sqlite" * 500)
    for n in ("meshlens-20240101-000000-manuale.db", "meshlens-20240101-000001-manuale.db"):
        with pytest.raises(BackupUnusable):
            m.schedule_restore(n)
    assert not (tmp_path / "restore.json").exists()


def test_copy_failure_midway_restores_original(tmp_path, monkeypatch):
    import meshlens.backup as bk
    conn, m = mgr(tmp_path)
    conn.execute("INSERT INTO settings(key, value) VALUES('marker', '\"originale\"')")
    conn.commit()
    name = m.create_sync(conn, "manuale")["name"]
    conn.close()
    m.schedule_restore(name)

    def boom(src, dst, *a, **k):
        raise OSError("disco pieno")

    monkeypatch.setattr(bk.shutil, "copy2", boom)
    assert apply_pending_restore(tmp_path) is None
    cur = sqlite3.connect(tmp_path / "meshlens.db")
    assert cur.execute("SELECT value FROM settings WHERE key='marker'").fetchone()[0] == '"originale"'
    cur.close()
    assert not list((tmp_path / "backups").glob("*-prima-del-ripristino.db*"))
    assert not (tmp_path / "meshlens.db.restore").exists()
    _, rt = build(tmp_path, static_dir=None)  # l'app parte sul database originale
    rt.conn.close()


def test_prune_keeps_special_backups_and_tolerates_vanishing(tmp_path):
    clock = Clock(1_700_000_000)
    conn, m = mgr(tmp_path, clock)
    m.create_sync(conn, "pre-migrazione")
    for _ in range(8):
        clock.t += 100
        m.create_sync(conn, "manuale")
    names = [b["reason"] for b in m.list()]
    assert names.count("pre-migrazione") == 1 and names.count("manuale") == 2
    for _ in range(5):
        clock.t += 100
        m.create_sync(conn, "pre-migrazione")
    assert [b["reason"] for b in m.list()].count("pre-migrazione") == 3
    victim = m.list()[0]["name"]
    (m.dir / victim).unlink()  # sparito: list non solleva
    assert all(b["name"] != victim for b in m.list())
    conn.close()


def test_wal_move_failure_keeps_original_db_and_wal(tmp_path, monkeypatch):
    import meshlens.backup as bk
    conn, m = mgr(tmp_path)
    conn.execute("INSERT INTO settings(key, value) VALUES('marker', '\"originale\"')")
    conn.commit()
    name = m.create_sync(conn, "manuale")["name"]
    conn.close()
    wal = tmp_path / "meshlens.db-wal"
    wal.write_bytes(b"wal non ancora trasferito")
    m.schedule_restore(name)
    real_move = bk.shutil.move

    def flaky(src, dst, *a, **k):
        if str(src).endswith("-wal"):
            raise OSError("file bloccato")
        return real_move(src, dst, *a, **k)

    monkeypatch.setattr(bk.shutil, "move", flaky)
    assert apply_pending_restore(tmp_path) is None
    assert wal.read_bytes() == b"wal non ancora trasferito"
    cur = sqlite3.connect(tmp_path / "meshlens.db")
    assert cur.execute("SELECT value FROM settings WHERE key='marker'").fetchone()[0] == '"originale"'
    cur.close()
    assert not list((tmp_path / "backups").glob("*-prima-del-ripristino.db*"))


def test_retention_is_per_reason(tmp_path):
    clock = Clock(1_700_000_000)
    conn, m = mgr(tmp_path, clock)
    for reason in ("pre-migrazione", "pre-aggiornamento", "settimanale", "manuale"):
        for _ in range(6):
            clock.t += 100
            m.create_sync(conn, reason)
    items = m.list()
    counts = {r: [b["reason"] for b in items].count(r) for r in KEEP_BY_REASON}
    assert counts == {"manuale": 2, "pre-aggiornamento": 2, "settimanale": 3,
                      "pre-migrazione": 3, "prima-del-ripristino": 0}
    # restano le piu' recenti di ogni motivo
    newest_manual = max(b["time"] for b in items if b["reason"] == "manuale")
    assert newest_manual == clock.t
    # tanti manuali non spingono fuori i settimanali
    for _ in range(10):
        clock.t += 100
        m.create_sync(conn, "manuale")
    assert [b["reason"] for b in m.list()].count("settimanale") == 3
    conn.close()


def _legacy_db(path):
    legacy = sqlite3.connect(path)
    legacy.executescript(
        "CREATE TABLE nodes(num INTEGER PRIMARY KEY, id TEXT, long_name TEXT, hops INTEGER, sources TEXT, last_heard REAL, is_mine INTEGER DEFAULT 0);"
        "CREATE TABLE messages(key TEXT PRIMARY KEY, text TEXT, time REAL, country TEXT);"
        "CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);")
    legacy.commit()
    legacy.close()


def test_reset_pin_on_legacy_db_makes_premigration_backup(tmp_path, capsys):
    from meshlens.__main__ import main
    _legacy_db(tmp_path / "meshlens.db")
    assert main(["reset-pin", "--data-dir", str(tmp_path)]) == 0
    found = list((tmp_path / "backups").glob("*-pre-migrazione.db"))
    assert len(found) == 1
    old = sqlite3.connect(found[0])
    assert old.execute("PRAGMA user_version").fetchone()[0] == 0
    old.close()


def test_restore_drops_sessions_and_locks_but_keeps_backup_pin(tmp_path, caplog):
    from meshlens.auth import Auth
    conn, m = mgr(tmp_path)
    auth = Auth(conn)
    auth.set_pin("111111")
    token = auth.login("111111", "192.168.1.5")
    conn.execute("INSERT INTO auth_failures(ip, failures, locked_until, last_failure) "
                 "VALUES('10.0.0.9', 7, 9e12, 9e12)")
    conn.execute("INSERT INTO auth_attempts(time, ip) VALUES(9e12, '10.0.0.9')")
    conn.execute("INSERT INTO auth(key, value) VALUES('global_lock_until', '9e12')")
    conn.commit()
    name = m.create_sync(conn, "manuale")["name"]  # il backup contiene sessione e blocchi
    auth.set_pin("222222")  # PIN cambiato dopo il backup
    conn.close()
    m.schedule_restore(name)
    with caplog.at_level("WARNING"):
        _, rt = build(tmp_path, static_dir=None)
    try:
        assert rt.auth.check(token) is False
        assert rt.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert rt.conn.execute("SELECT COUNT(*) FROM auth_failures").fetchone()[0] == 0
        assert rt.conn.execute("SELECT COUNT(*) FROM auth_attempts").fetchone()[0] == 0
        assert rt.auth._get("global_lock_until") is None
        assert rt.auth.pin_is_set()
        rt.auth.login("111111", "127.0.0.1")  # il PIN e' quello del momento del backup
        assert "sessioni e blocchi" in caplog.text
    finally:
        rt.conn.close()


def test_build_without_restore_keeps_sessions(tmp_path):
    _, rt = build(tmp_path, static_dir=None)
    rt.auth.set_pin("111111")
    token = rt.auth.login("111111", "127.0.0.1")
    rt.conn.close()
    _, rt2 = build(tmp_path, static_dir=None)
    try:
        assert rt2.auth.check(token) is True
    finally:
        rt2.conn.close()


def test_quick_check_file_reports_unreadable(tmp_path):
    db = tmp_path / "meshlens.db"
    connect(db).close()
    assert quick_check_file(db) == "ok"
    bad = tmp_path / "rotto.db"
    bad.write_bytes(b"non un database" * 100)
    assert quick_check_file(bad) != "ok"


def test_quick_check_file_can_be_interrupted_through_on_open(tmp_path):
    db = tmp_path / "x.db"
    connect(db).close()
    seen = []

    def on_open(c):  # interrompe a meta' del quick_check, come fa Runtime.stop()
        seen.append(c)
        c.set_progress_handler(lambda: c.interrupt() or 0, 1)

    assert quick_check_file(db, on_open=on_open) == "non leggibile (interrupted)"
    assert isinstance(seen[0], sqlite3.Connection)
