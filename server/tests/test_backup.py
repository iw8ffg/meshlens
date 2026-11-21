import sqlite3

import pytest

from meshlens.app import build
from meshlens.backup import (BACKUP_WEEKLY_S, BackupManager, apply_pending_restore,
                             quick_check)
from meshlens.db import connect


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def mgr(tmp_path, clock=None, keep=5):
    db = tmp_path / "meshlens.db"
    conn = connect(db)
    return conn, BackupManager(db, tmp_path / "backups", clock or Clock(1_700_000_000), keep)


def test_create_and_list_and_prune(tmp_path):
    clock = Clock(1_700_000_000)
    conn, m = mgr(tmp_path, clock)
    for i in range(7):
        clock.t += 100
        m.create_sync(conn, "manuale" if i % 2 else "settimanale")
    items = m.list()
    assert len(items) == 5
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
    assert names.count("pre-migrazione") == 1 and names.count("manuale") == 5
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
