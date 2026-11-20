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
