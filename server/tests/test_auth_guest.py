"""E19: PIN ospite e ruolo della sessione (auth.py)."""
import asyncio

import pytest

from meshlens.auth import Auth, LockedError
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
    a = Auth(connect(":memory:"), clock)
    a.set_pin("1234")
    return a


def test_guest_pin_validation(auth):
    assert auth.guest_pin_is_set() is False
    for bad in ("12345", "abcdef", "1234567890123", "١٢٣٤٥٦"):
        with pytest.raises(ValueError):
            auth.set_guest_pin(bad)
    auth.set_guest_pin("123456")
    assert auth.guest_pin_is_set() is True


def test_guest_pin_must_differ_from_admin(clock):
    a = Auth(connect(":memory:"), clock)
    a.set_pin("123456")
    with pytest.raises(ValueError):
        a.set_guest_pin("123456")
    assert a.guest_pin_is_set() is False


def test_guest_login_gives_guest_role(auth):
    auth.set_guest_pin("654321")
    token = auth.login("654321", "192.168.1.5", "Telefono", guest_ok=True)
    assert auth.check_role(token) == "guest"
    assert auth.check(token) is True
    admin = auth.login("1234", "192.168.1.5", guest_ok=True)
    assert auth.check_role(admin) == "admin"
    assert auth.check_role(None) is None
    assert auth.check_role("nope") is None


def test_guest_pin_refused_when_guest_not_allowed(auth):
    auth.set_guest_pin("654321")
    with pytest.raises(PermissionError):
        auth.login("654321", "192.168.1.5", guest_ok=False)
    row = auth.conn.execute("SELECT failures FROM auth_failures WHERE ip='192.168.1.5'").fetchone()
    assert row[0] == 1


def test_lockout_shared_between_admin_and_guest(auth):
    auth.set_guest_pin("654321")
    ip = "192.168.1.9"
    for i in range(5):
        with pytest.raises(PermissionError):
            auth.login("000000" if i % 2 else "9999", ip, guest_ok=True)
    with pytest.raises(LockedError):
        auth.login("654321", ip, guest_ok=True)
    with pytest.raises(LockedError):
        auth.login("1234", ip, guest_ok=True)


async def test_alogin_guest(auth):
    await auth.aset_guest_pin("654321")
    token = await auth.alogin("654321", "10.0.0.2", None, guest_ok=True)
    assert auth.check_role(token) == "guest"
    with pytest.raises(PermissionError):
        await auth.alogin("654321", "10.0.0.3", None)


def test_sessions_expose_role_and_revoke_role(auth):
    auth.set_guest_pin("654321")
    admin = auth.login("1234", "127.0.0.1")
    guest = auth.login("654321", "192.168.1.5", guest_ok=True)
    rows = auth.sessions(admin)
    assert sorted(r["role"] for r in rows) == ["admin", "guest"]
    assert auth.revoke_role("guest") == 1
    assert auth.check(guest) is False
    assert auth.check(admin) is True


async def test_revoke_role_closes_watchers(auth):
    auth.set_guest_pin("654321")
    guest = auth.login("654321", "192.168.1.5", guest_ok=True)
    h, event = auth.watch(guest)
    auth.revoke_role("guest")
    await asyncio.wait_for(event.wait(), 1)
    auth.unwatch(h, event)


def test_clear_guest_pin_drops_guest_sessions(auth):
    auth.set_guest_pin("654321")
    guest = auth.login("654321", "192.168.1.5", guest_ok=True)
    admin = auth.login("1234", "127.0.0.1")
    auth.clear_guest_pin()
    assert auth.guest_pin_is_set() is False
    assert auth.check(guest) is False
    assert auth.check(admin) is True
    with pytest.raises(PermissionError):
        auth.login("654321", "192.168.1.6", guest_ok=True)


def test_reset_removes_guest_pin(auth):
    auth.set_guest_pin("654321")
    auth.reset()
    assert auth.guest_pin_is_set() is False


async def test_change_pin_cannot_equal_guest_pin(auth):
    auth.set_guest_pin("654321")
    token = auth.login("1234", "127.0.0.1")
    with pytest.raises(ValueError):
        await auth.change_pin(token, "1234", "654321", 4, "127.0.0.1")
    # il PIN principale resta quello di prima
    assert auth.check_role(auth.login("1234", "127.0.0.1")) == "admin"


async def test_aset_pin_cannot_equal_guest_pin(clock):
    a = Auth(connect(":memory:"), clock)
    a.set_pin("1234")
    a.set_guest_pin("654321")
    a.conn.execute("DELETE FROM auth WHERE key IN ('pin_hash', 'pin_len')")
    with pytest.raises(ValueError):
        await a.aset_pin("654321", 4)


# ---- revisione di sicurezza WP6 ----

def test_guest_login_does_not_reset_ip_failures(auth, clock):
    """I1: un accesso ospite riuscito non azzera il contatore per IP (altrimenti chi conosce
    il PIN ospite prova il PIN principale senza mai essere bloccato)."""
    auth.set_pin("13579246")
    auth.set_guest_pin("654321")
    ip = "192.168.1.50"
    tries = locked = 0
    for cycle in range(10):
        for i in range(4):
            try:
                auth.login("%08d" % (cycle * 4 + i), ip, guest_ok=True)
            except PermissionError:
                tries += 1
            except LockedError:
                locked += 1
            clock.t += 25
        try:
            auth.login("654321", ip, guest_ok=True)
        except LockedError:
            locked += 1
        clock.t += 1
    assert locked > 0
    assert tries < 12
    # l'accesso admin invece azzera
    clock.t += 7200
    auth.login("13579246", ip, guest_ok=True)
    assert auth.conn.execute("SELECT COUNT(*) FROM auth_failures WHERE ip=?", (ip,)).fetchone()[0] == 0


async def test_guest_login_in_flight_refused_after_pin_rotation(auth, monkeypatch):
    """I2: un login con il PIN ospite vecchio, ancora in corso quando il PIN cambia, non
    ottiene una sessione."""
    import time as _time
    auth.set_pin("13579246")
    auth.set_guest_pin("654321")
    orig = auth._verify
    slow = {"on": True}

    def verify(stored, pin):
        if slow["on"]:
            _time.sleep(0.3)
        return orig(stored, pin)
    monkeypatch.setattr(auth, "_verify", verify)
    login = asyncio.create_task(auth.alogin("654321", "192.168.1.50", guest_ok=True))
    await asyncio.sleep(0.45)  # verifica admin finita, verifica ospite in corso
    slow["on"] = False
    await auth.aset_guest_pin("111222")
    with pytest.raises(PermissionError):
        await login
    assert auth.count_guests() == 0
    # il cambio di PIN non e' un errore dell'utente: nessun tentativo contato
    assert auth.conn.execute("SELECT COUNT(*) FROM auth_failures").fetchone()[0] == 0


async def test_guest_login_in_flight_refused_after_pin_clear(auth, monkeypatch):
    import time as _time
    auth.set_pin("13579246")
    auth.set_guest_pin("654321")
    orig = auth._verify
    slow = {"on": True}

    def verify(stored, pin):
        if slow["on"]:
            _time.sleep(0.3)
        return orig(stored, pin)
    monkeypatch.setattr(auth, "_verify", verify)
    login = asyncio.create_task(auth.alogin("654321", "192.168.1.50", guest_ok=True))
    await asyncio.sleep(0.45)
    slow["on"] = False
    auth.clear_guest_pin()
    with pytest.raises(PermissionError):
        await login
    assert auth.count_guests() == 0


async def test_concurrent_admin_and_guest_pin_cannot_be_equal(auth):
    """M1: PIN principale e ospite impostati insieme allo stesso valore: uno dei due fallisce."""
    auth.set_pin("13579246")
    auth.set_guest_pin("654321")
    res = await asyncio.gather(auth.aset_pin("99887766"), auth.aset_guest_pin("99887766"),
                               return_exceptions=True)
    assert sum(isinstance(r, ValueError) for r in res) == 1
    token = auth.login("99887766", "1.2.3.4", guest_ok=True)
    role = auth.check_role(token)
    # vale solo quello impostato per primo
    assert (role == "admin") == (res[0] is None)


async def test_concurrent_change_pin_and_guest_pin_cannot_be_equal(auth):
    auth.set_pin("13579246")
    auth.set_guest_pin("654321")
    token = auth.login("13579246", "127.0.0.1")
    res = await asyncio.gather(auth.change_pin(token, "13579246", "99887766", 4, "127.0.0.1"),
                               auth.aset_guest_pin("99887766"), return_exceptions=True)
    assert sum(isinstance(r, ValueError) for r in res) == 1


def test_guest_sessions_capped(auth, clock):
    """M6: al massimo MAX_GUEST_SESSIONS sessioni ospite; si revocano le piu' vecchie."""
    from meshlens.auth import MAX_GUEST_SESSIONS
    auth.set_guest_pin("654321")
    admin = auth.login("1234", "127.0.0.1")
    tokens = []
    for _ in range(MAX_GUEST_SESSIONS + 5):
        tokens.append(auth.login("654321", "192.168.1.5", guest_ok=True))
        clock.t += 1
    assert auth.count_guests() == MAX_GUEST_SESSIONS
    assert all(auth.check(t) is False for t in tokens[:5])
    assert all(auth.check(t) is True for t in tokens[5:])
    assert auth.check(admin) is True
