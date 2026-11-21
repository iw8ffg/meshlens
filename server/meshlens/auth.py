"""PIN (argon2), sessioni e blocco dei tentativi (per IP e globale), salvati nel database.

Il database si usa solo dal thread del loop: `alogin`/`change_pin` controllano i blocchi e
registrano l'esito sul loop, e mandano in `asyncio.to_thread` solo la verifica argon2.
"""
import asyncio
import contextlib
import hashlib
import logging
import math
import re
import secrets
import sqlite3
import time
from typing import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MAX_FAILURES = 5
FAILURE_RESET_S = 86400
MAX_LOCK_S = 3600
GLOBAL_MAX_FAILURES = 30
GLOBAL_WINDOW_S = 600
GLOBAL_LOCK_S = 900
SESSION_IDLE_S = 30 * 86400
TOUCH_INTERVAL_S = 60
MIN_PIN = 4
MIN_PIN_LAN = 6
MAX_PIN = 12
VERIFY_CONCURRENCY = 2  # ogni verifica argon2 usa 64 MiB
LOOPBACK = ("127.0.0.1", "::1")
_SESSION_ID = re.compile(r"^[0-9a-f]{16}$")
log = logging.getLogger(__name__)


class LockedError(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"troppi tentativi, riprova tra {retry_after}s")
        self.retry_after = retry_after


def lock_seconds(failures: int) -> int:
    """Attesa dopo `failures` errori consecutivi: 60 s al quinto, poi raddoppia fino a un'ora."""
    if failures < MAX_FAILURES:
        return 0
    return min(60 * 2 ** min(failures - MAX_FAILURES, 6), MAX_LOCK_S)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], float] = time.time):
        self.conn = conn
        self.clock = clock
        self._ph = PasswordHasher()
        self._ip_locks: dict[str, list] = {}  # ip -> [asyncio.Lock, utenti in attesa]
        self._sem: tuple[asyncio.AbstractEventLoop, asyncio.Semaphore] | None = None

    # ---- PIN ----
    def pin_is_set(self) -> bool:
        return self._get("pin_hash") is not None

    def pin_length(self) -> int | None:
        v = self._get("pin_len")
        return int(v) if v is not None and v.isdigit() else None

    @staticmethod
    def _validate_pin(pin: str, min_len: int) -> None:
        if not (pin.isascii() and pin.isdigit() and min_len <= len(pin) <= MAX_PIN):
            raise ValueError(f"il PIN deve essere di {min_len}-{MAX_PIN} cifre")

    def set_pin(self, pin: str, min_len: int = MIN_PIN) -> None:
        self._validate_pin(pin, min_len)
        self._store_pin(self._ph.hash(pin), len(pin))

    def _store_pin(self, pin_hash: str, length: int) -> None:
        self.conn.executemany("INSERT OR REPLACE INTO auth(key, value) VALUES(?, ?)",
                              (("pin_hash", pin_hash), ("pin_len", str(length))))
        self.conn.commit()

    def _get(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM auth WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _verify(self, stored: str | None, pin: str) -> bool:
        """Solo CPU, nessun accesso al database: sicura in un thread."""
        if stored is None:
            return False
        try:
            return self._ph.verify(stored, pin)
        except (VerificationError, InvalidHashError):
            return False

    # ---- blocchi ----
    def _precheck(self, ip: str, now: float) -> None:
        if ip not in LOOPBACK:
            until = float(self._get("global_lock_until") or 0)
            if now < until:
                log.debug("Tentativo da %s rifiutato: blocco globale attivo", ip)
                raise LockedError(math.ceil(until - now))
        row = self.conn.execute(
            "SELECT locked_until, last_failure FROM auth_failures WHERE ip=?", (ip,)).fetchone()
        if row is None:
            return
        locked_until, last_failure = row
        if now - (last_failure or 0) >= FAILURE_RESET_S:
            self.conn.execute("DELETE FROM auth_failures WHERE ip=?", (ip,))
            self.conn.commit()
            return
        if locked_until is not None and now < locked_until:
            log.debug("Tentativo da %s rifiutato: IP bloccato", ip)
            raise LockedError(math.ceil(locked_until - now))

    def _record_failure(self, ip: str, now: float) -> None:
        row = self.conn.execute("SELECT failures FROM auth_failures WHERE ip=?", (ip,)).fetchone()
        n = (row[0] if row else 0) + 1
        wait = lock_seconds(n)
        self.conn.execute(
            "INSERT OR REPLACE INTO auth_failures(ip, failures, locked_until, last_failure) "
            "VALUES(?,?,?,?)", (ip, n, now + wait if wait else None, now))
        if wait:
            log.info("Accesso fallito da %s (tentativo %d): bloccato per %d s", ip, n, wait)
        else:
            log.info("Accesso fallito da %s (tentativo %d)", ip, n)
        if ip not in LOOPBACK:
            self.conn.execute("INSERT INTO auth_attempts(time, ip) VALUES(?, ?)", (now, ip))
            self.conn.execute("DELETE FROM auth_attempts WHERE time <= ?", (now - GLOBAL_WINDOW_S,))
            count = self.conn.execute("SELECT COUNT(*) FROM auth_attempts").fetchone()[0]
            if count >= GLOBAL_MAX_FAILURES:
                self.conn.execute("INSERT OR REPLACE INTO auth(key, value) VALUES(?, ?)",
                                  ("global_lock_until", str(now + GLOBAL_LOCK_S)))
                self.conn.execute("DELETE FROM auth_attempts")
                log.warning("%d PIN errati dalla rete in %d s: accesso dalla rete bloccato "
                            "per %d s (dal PC si entra ancora)",
                            count, GLOBAL_WINDOW_S, GLOBAL_LOCK_S)
        self.conn.commit()

    # ---- login ----
    def _issue_token(self, ip: str, user_agent: str | None, now: float) -> str:
        token = secrets.token_urlsafe(32)
        self.conn.execute("DELETE FROM auth_failures WHERE ip=?", (ip,))
        self.conn.execute(
            "INSERT INTO sessions(token_hash, created, last_seen, user_agent, ip) "
            "VALUES(?,?,?,?,?)", (_hash(token), now, now, user_agent, ip))
        self.conn.commit()
        log.info("Accesso riuscito da %s", ip)
        return token

    def _finish(self, ok: bool, pin: str, ip: str, user_agent: str | None) -> str:
        now = self.clock()
        if not ok:
            self._record_failure(ip, now)
            raise PermissionError("PIN errato")
        if self.pin_length() is None:  # PIN impostato da una versione precedente
            self.conn.execute("INSERT OR REPLACE INTO auth(key, value) VALUES('pin_len', ?)",
                              (str(len(pin)),))
        return self._issue_token(ip, user_agent, now)

    def login(self, pin: str, client_ip: str, user_agent: str | None = None) -> str:
        """Versione sincrona (CLI e test): verifica argon2 sul thread chiamante."""
        self._precheck(client_ip, self.clock())
        ok = self._verify(self._get("pin_hash"), pin)
        return self._finish(ok, pin, client_ip, user_agent)

    async def alogin(self, pin: str, client_ip: str, user_agent: str | None = None) -> str:
        async with self._ip_lock(client_ip):
            self._precheck(client_ip, self.clock())
            ok = await self._averify(self._get("pin_hash"), pin)
            return self._finish(ok, pin, client_ip, user_agent)

    async def _averify(self, stored: str | None, pin: str) -> bool:
        async with self._verify_sem():
            return await asyncio.to_thread(self._verify, stored, pin)

    def _verify_sem(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self._sem is None or self._sem[0] is not loop:
            self._sem = (loop, asyncio.Semaphore(VERIFY_CONCURRENCY))
        return self._sem[1]

    @contextlib.asynccontextmanager
    async def _ip_lock(self, ip: str):
        """Tentativi dallo stesso IP in fila: nessuno sfugge al contatore."""
        entry = self._ip_locks.get(ip)
        if entry is None:
            entry = self._ip_locks[ip] = [asyncio.Lock(), 0]
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if entry[1] == 0:
                self._ip_locks.pop(ip, None)

    async def change_pin(self, token: str, current: str, new: str, min_len: int) -> None:
        """Verifica il PIN attuale (gli errori contano come al login), poi revoca le altre sessioni."""
        row = self.conn.execute("SELECT ip FROM sessions WHERE token_hash=?",
                                (_hash(token or ""),)).fetchone()
        if row is None or not self.check(token):
            raise PermissionError("sessione non valida")
        ip = row[0] or "unknown"
        self._validate_pin(new, min_len)
        async with self._ip_lock(ip):
            self._precheck(ip, self.clock())
            ok = await self._averify(self._get("pin_hash"), current)
            if not ok:
                self._record_failure(ip, self.clock())
                raise PermissionError("PIN attuale errato")
            new_hash = await asyncio.to_thread(self._ph.hash, new)
            self.conn.execute("DELETE FROM auth_failures WHERE ip=?", (ip,))
            self._store_pin(new_hash, len(new))
            self.revoke_others(token)
        log.info("PIN cambiato da %s: altre sessioni revocate", ip)

    # ---- sessioni ----
    def check(self, token: str | None) -> bool:
        if not token:
            return False
        h = _hash(token)
        row = self.conn.execute("SELECT last_seen FROM sessions WHERE token_hash=?", (h,)).fetchone()
        if row is None:
            return False
        now = self.clock()
        last_seen = row[0] or 0
        if now - last_seen > SESSION_IDLE_S:
            self.conn.execute("DELETE FROM sessions WHERE token_hash=?", (h,))
            self.conn.commit()
            return False
        if now - last_seen >= TOUCH_INTERVAL_S:
            self.conn.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, h))
            self.conn.commit()
        return True

    def sessions(self, current_token: str | None) -> list[dict]:
        self.conn.execute("DELETE FROM sessions WHERE last_seen < ?",
                          (self.clock() - SESSION_IDLE_S,))
        self.conn.commit()
        current = _hash(current_token) if current_token else None
        rows = self.conn.execute(
            "SELECT token_hash, created, last_seen, user_agent, ip FROM sessions "
            "ORDER BY last_seen DESC").fetchall()
        return [{"id": h[:16], "created": created, "last_seen": last_seen,
                 "user_agent": ua, "ip": ip, "current": h == current}
                for h, created, last_seen, ua, ip in rows]

    def revoke(self, session_id: str) -> bool:
        if not isinstance(session_id, str) or not _SESSION_ID.match(session_id):
            return False
        cur = self.conn.execute("DELETE FROM sessions WHERE substr(token_hash, 1, 16)=?",
                                (session_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def revoke_others(self, current_token: str) -> int:
        cur = self.conn.execute("DELETE FROM sessions WHERE token_hash != ?",
                                (_hash(current_token),))
        self.conn.commit()
        return cur.rowcount

    def logout(self, token: str) -> None:
        self.conn.execute("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))
        self.conn.commit()

    def reset(self) -> None:
        """`meshlens reset-pin`: toglie PIN, sessioni e ogni blocco."""
        self.conn.execute("DELETE FROM auth WHERE key IN ('pin_hash', 'pin_len', 'global_lock_until')")
        self.conn.execute("DELETE FROM sessions")
        self.conn.execute("DELETE FROM auth_failures")
        self.conn.execute("DELETE FROM auth_attempts")
        self.conn.commit()
