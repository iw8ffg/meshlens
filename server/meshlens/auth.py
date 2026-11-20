"""PIN (argon2), sessioni e blocco tentativi per IP."""
import hashlib
import math
import secrets
import sqlite3
import time
from typing import Callable

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

MAX_FAILURES = 5
LOCK_SECONDS = 300


class LockedError(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"troppi tentativi, riprova tra {retry_after}s")
        self.retry_after = retry_after


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], float] = time.time):
        self.conn = conn
        self.clock = clock
        self._ph = PasswordHasher()
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def pin_is_set(self) -> bool:
        row = self.conn.execute("SELECT 1 FROM auth WHERE key='pin_hash'").fetchone()
        return row is not None

    def set_pin(self, pin: str) -> None:
        if not (pin.isascii() and pin.isdigit() and 4 <= len(pin) <= 12):
            raise ValueError("il PIN deve essere di 4-12 cifre")
        self.conn.execute(
            "INSERT OR REPLACE INTO auth(key, value) VALUES('pin_hash', ?)",
            (self._ph.hash(pin),),
        )
        self.conn.commit()

    def login(self, pin: str, client_ip: str, user_agent: str | None = None) -> str:
        now = self.clock()
        until = self._locked_until.get(client_ip)
        if until is not None:
            if now < until:
                raise LockedError(math.ceil(until - now))
            del self._locked_until[client_ip]
            self._failures.pop(client_ip, None)
        row = self.conn.execute("SELECT value FROM auth WHERE key='pin_hash'").fetchone()
        ok = False
        if row is not None:
            try:
                ok = self._ph.verify(row[0], pin)
            except VerifyMismatchError:
                ok = False
        if not ok:
            n = self._failures.get(client_ip, 0) + 1
            self._failures[client_ip] = n
            if n >= MAX_FAILURES:
                self._locked_until[client_ip] = now + LOCK_SECONDS
            raise PermissionError("PIN errato")
        self._failures.pop(client_ip, None)
        token = secrets.token_urlsafe(32)
        self.conn.execute(
            "INSERT INTO sessions(token_hash, created, last_seen, user_agent) VALUES(?,?,?,?)",
            (_hash(token), now, now, user_agent),
        )
        self.conn.commit()
        return token

    def check(self, token: str | None) -> bool:
        if not token:
            return False
        cur = self.conn.execute(
            "UPDATE sessions SET last_seen=? WHERE token_hash=?", (self.clock(), _hash(token))
        )
        self.conn.commit()
        return cur.rowcount > 0

    def logout(self, token: str) -> None:
        self.conn.execute("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))
        self.conn.commit()

    def reset(self) -> None:
        self.conn.execute("DELETE FROM auth WHERE key='pin_hash'")
        self.conn.execute("DELETE FROM sessions")
        self.conn.commit()
        self._failures.clear()
        self._locked_until.clear()
