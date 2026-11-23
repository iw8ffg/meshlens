import asyncio

import pytest

import meshlens.auth as auth_mod
from meshlens.auth import Auth, LockedError, lock_seconds
from meshlens.db import connect


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def auth(clock):
    return Auth(connect(":memory:"), clock)


def test_set_pin_validation(auth):
    for bad in ("12", "1234567890123", "12ab"):
        with pytest.raises(ValueError):
            auth.set_pin(bad)
    assert not auth.pin_is_set()


def test_login_and_check(auth):
    auth.set_pin("1234")
    assert auth.pin_is_set()
    token = auth.login("1234", "1.1.1.1", user_agent="ua")
    assert auth.check(token)
    assert not auth.check("x")
    assert not auth.check(None)
    auth.logout(token)
    assert not auth.check(token)


def test_token_stored_hashed(auth):
    auth.set_pin("1234")
    token = auth.login("1234", "1.1.1.1")
    rows = auth.conn.execute("SELECT token_hash FROM sessions").fetchall()
    assert len(rows) == 1 and rows[0][0] != token


def test_wrong_pin(auth):
    auth.set_pin("1234")
    with pytest.raises(PermissionError):
        auth.login("0000", "1.1.1.1")


def test_lockout_and_expiry(auth, clock):
    auth.set_pin("1234")
    for _ in range(5):
        with pytest.raises(PermissionError):
            auth.login("0000", "1.1.1.1")
    with pytest.raises(LockedError) as e:
        auth.login("1234", "1.1.1.1")
    assert 0 < e.value.retry_after <= 300
    # altro IP non bloccato
    assert auth.login("1234", "2.2.2.2")
    clock.t += 301
    assert auth.login("1234", "1.1.1.1")


def test_success_resets_failures(auth):
    auth.set_pin("1234")
    for _ in range(4):
        with pytest.raises(PermissionError):
            auth.login("0000", "1.1.1.1")
    auth.login("1234", "1.1.1.1")
    for _ in range(4):
        with pytest.raises(PermissionError):
            auth.login("0000", "1.1.1.1")


def test_reset(auth):
    auth.set_pin("1234")
    token = auth.login("1234", "1.1.1.1")
    auth.reset()
    assert not auth.pin_is_set()
    assert not auth.check(token)


# ---- blocco persistente e sessioni ----

def _fail(auth, ip, n=1):
    for _ in range(n):
        with pytest.raises(PermissionError):
            auth.login("0000", ip)


def test_backoff_grows_and_caps():
    assert lock_seconds(4) == 0
    assert lock_seconds(5) == 60
    assert lock_seconds(6) == 120
    assert lock_seconds(11) == 3600
    assert lock_seconds(20) == 3600
    assert lock_seconds(10_000) == 3600


def test_lock_survives_restart(auth, clock):
    auth.set_pin("1234")
    _fail(auth, "1.1.1.1", 5)
    again = Auth(auth.conn, clock)
    with pytest.raises(LockedError) as e:
        again.login("1234", "1.1.1.1")
    assert e.value.retry_after == 60


def test_backoff_after_lock_expires(auth, clock):
    auth.set_pin("1234")
    _fail(auth, "1.1.1.1", 5)
    clock.t += 61
    _fail(auth, "1.1.1.1")  # sesto errore: attesa raddoppiata
    with pytest.raises(LockedError) as e:
        auth.login("1234", "1.1.1.1")
    assert e.value.retry_after == 120


def test_global_lock_spares_loopback(auth, clock):
    auth.set_pin("1234")
    for i in range(30):
        _fail(auth, f"10.0.0.{i}")
    with pytest.raises(LockedError) as e:
        auth.login("1234", "10.0.0.99")
    assert e.value.retry_after == 900
    assert auth.check(auth.login("1234", "127.0.0.1"))
    assert auth.check(auth.login("1234", "::1"))
    # sopravvive al riavvio
    with pytest.raises(LockedError):
        Auth(auth.conn, clock).login("1234", "10.0.0.98")
    clock.t += 901
    assert auth.login("1234", "10.0.0.99")


def test_loopback_failures_do_not_count_globally(auth):
    auth.set_pin("1234")
    for _ in range(40):
        with pytest.raises((PermissionError, LockedError)):
            auth.login("0000", "127.0.0.1")
    assert auth.login("1234", "10.0.0.1")


def test_failures_reset_after_success_and_after_a_day(auth, clock):
    auth.set_pin("1234")
    _fail(auth, "1.1.1.1", 4)
    auth.login("1234", "1.1.1.1")
    _fail(auth, "1.1.1.1", 4)  # nessun blocco: contatore azzerato dal successo
    clock.t += 86400
    _fail(auth, "1.1.1.1", 4)  # nessun blocco: contatore scaduto dopo un giorno senza errori
    _fail(auth, "1.1.1.1")
    with pytest.raises(LockedError):
        auth.login("1234", "1.1.1.1")
    clock.t += 86400 + 1
    assert auth.login("1234", "1.1.1.1")


async def test_alogin_runs_verify_off_loop(auth, monkeypatch):
    auth.set_pin("1234")
    calls = []
    real = asyncio.to_thread

    async def spy(fn, *args, **kwargs):
        calls.append(fn)
        return await real(fn, *args, **kwargs)

    monkeypatch.setattr(auth_mod.asyncio, "to_thread", spy)
    token = await auth.alogin("1234", "1.1.1.1", "ua")
    assert auth.check(token)
    assert len(calls) == 1


async def test_parallel_attempts_same_ip_are_serialized(auth, monkeypatch):
    auth.set_pin("1234")
    verified = []
    real_verify = auth._verify

    def counting(stored, pin):
        verified.append(pin)
        return real_verify(stored, pin)

    monkeypatch.setattr(auth, "_verify", counting)
    results = await asyncio.gather(*(auth.alogin("0000", "1.1.1.1") for _ in range(10)),
                                   return_exceptions=True)
    assert len(verified) <= 5
    assert sum(isinstance(r, PermissionError) for r in results) == 5
    assert sum(isinstance(r, LockedError) for r in results) == 5


async def test_alogin_wrong_pin_and_lock(auth):
    auth.set_pin("1234")
    for _ in range(5):
        with pytest.raises(PermissionError):
            await auth.alogin("0000", "1.1.1.1")
    with pytest.raises(LockedError):
        await auth.alogin("1234", "1.1.1.1")


def test_session_expires_after_30_days_idle(auth, clock):
    auth.set_pin("1234")
    token = auth.login("1234", "1.1.1.1")
    clock.t += 29 * 86400
    assert auth.check(token)  # l'uso rinnova la sessione
    clock.t += 30 * 86400 - 1
    assert auth.check(token)
    clock.t += 30 * 86400 + 1
    assert not auth.check(token)
    assert auth.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_touch_is_throttled(auth, clock):
    auth.set_pin("1234")
    token = auth.login("1234", "1.1.1.1")
    stmts = []
    auth.conn.set_trace_callback(stmts.append)
    clock.t += 61
    assert auth.check(token)
    clock.t += 10
    assert auth.check(token)
    auth.conn.set_trace_callback(None)
    assert sum(s.lstrip().upper().startswith("UPDATE SESSIONS") for s in stmts) == 1


def test_sessions_list_and_revoke(auth, clock):
    auth.set_pin("1234")
    t1 = auth.login("1234", "1.1.1.1", user_agent="ua-1")
    clock.t += 5
    t2 = auth.login("1234", "2.2.2.2", user_agent="ua-2")
    rows = auth.sessions(t1)
    assert len(rows) == 2
    assert [r["current"] for r in rows if r["ip"] == "1.1.1.1"] == [True]
    assert sum(r["current"] for r in rows) == 1
    assert {r["user_agent"] for r in rows} == {"ua-1", "ua-2"}
    assert set(rows[0]) == {"id", "created", "last_seen", "user_agent", "ip", "current", "role"}
    assert {r["role"] for r in rows} == {"admin"}
    other = next(r for r in rows if not r["current"])
    assert len(other["id"]) == 16
    assert auth.revoke(other["id"])
    assert not auth.check(t2)
    assert auth.check(t1)
    assert not auth.revoke(other["id"])
    for bad in ("xyz", "", "' OR 1=1 --", "A" * 16, "0" * 17):
        assert not auth.revoke(bad)


def test_revoke_others(auth):
    auth.set_pin("1234")
    t1 = auth.login("1234", "1.1.1.1")
    t2 = auth.login("1234", "1.1.1.1")
    t3 = auth.login("1234", "1.1.1.1")
    assert auth.revoke_others(t1) == 2
    assert auth.check(t1) and not auth.check(t2) and not auth.check(t3)


def test_pin_length_and_min_len(auth):
    assert auth.pin_length() is None
    with pytest.raises(ValueError):
        auth.set_pin("1234", min_len=6)
    auth.set_pin("123456", min_len=6)
    assert auth.pin_length() == 6


def test_login_stores_missing_pin_len(auth):
    auth.set_pin("12345")
    auth.conn.execute("DELETE FROM auth WHERE key='pin_len'")  # PIN di una versione precedente
    assert auth.pin_length() is None
    auth.login("12345", "1.1.1.1")
    assert auth.pin_length() == 5


async def test_change_pin(auth):
    auth.set_pin("1234")
    t1 = auth.login("1234", "1.1.1.1")
    t2 = auth.login("1234", "2.2.2.2")
    with pytest.raises(PermissionError):
        await auth.change_pin(t1, "0000", "567890", 6)
    with pytest.raises(ValueError):
        await auth.change_pin(t1, "1234", "5678", 6)
    await auth.change_pin(t1, "1234", "567890", 6)
    assert auth.check(t1) and not auth.check(t2)
    assert auth.pin_length() == 6
    with pytest.raises(PermissionError):
        auth.login("1234", "3.3.3.3")
    assert auth.login("567890", "3.3.3.3")


async def test_change_pin_counts_failures(auth):
    auth.set_pin("1234")
    t1 = auth.login("1234", "1.1.1.1")
    for _ in range(5):
        with pytest.raises(PermissionError):
            await auth.change_pin(t1, "0000", "567890", 6)
    with pytest.raises(LockedError):
        await auth.change_pin(t1, "1234", "567890", 6)


async def test_change_pin_requires_valid_session(auth):
    auth.set_pin("1234")
    with pytest.raises(PermissionError):
        await auth.change_pin("nope", "1234", "567890", 6)


def test_reset_clears_locks(auth):
    auth.set_pin("1234")
    _fail(auth, "127.0.0.1", 5)
    for i in range(30):
        _fail(auth, f"10.0.0.{i}")
    auth.reset()
    assert auth.pin_length() is None
    auth.set_pin("1234")
    assert auth.login("1234", "127.0.0.1")
    assert auth.login("1234", "10.0.0.99")


def test_logs_never_contain_pin_or_token(auth, caplog):
    caplog.set_level("DEBUG", logger="meshlens.auth")
    auth.set_pin("982734")
    _fail(auth, "1.1.1.1", 5)
    token = auth.login("982734", "2.2.2.2")
    assert "982734" not in caplog.text and token not in caplog.text
    assert sum("bloccat" in r.getMessage() for r in caplog.records) == 1
