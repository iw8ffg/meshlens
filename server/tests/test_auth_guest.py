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
