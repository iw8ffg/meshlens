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
MIN_PIN_GUEST = 6  # l'ospite implica l'accesso dalla rete
MAX_PIN = 12
ROLE_ADMIN = "admin"
ROLE_GUEST = "guest"  # E19: sola lettura di mappa, nodi e statistiche
VERIFY_CONCURRENCY = 2  # ogni verifica argon2 usa 64 MiB
LOOPBACK = ("127.0.0.1", "::1")
SAME_PIN_MSG = "Il PIN ospite deve essere diverso dal PIN principale"
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
        # token_hash -> eventi dei WebSocket aperti con quella sessione (chiusi alla revoca)
        self._watchers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Event]]] = {}

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
        # il PIN principale non puo' coincidere con quello ospite: il login darebbe l'admin
        # a chi conosce il PIN ospite
        if self._verify(self._get("guest_pin_hash"), pin):
            raise ValueError(SAME_PIN_MSG)
        self._store_pin(self._ph.hash(pin), len(pin))

    async def aset_pin(self, pin: str, min_len: int = MIN_PIN) -> None:
        """Come `set_pin`, con l'hash argon2 fuori dal loop (per l'API)."""
        self._validate_pin(pin, min_len)
        if await self._averify(self._get("guest_pin_hash"), pin):
            raise ValueError(SAME_PIN_MSG)
        self._store_pin(await asyncio.to_thread(self._ph.hash, pin), len(pin))

    def _store_pin(self, pin_hash: str, length: int) -> None:
        self.conn.executemany("INSERT OR REPLACE INTO auth(key, value) VALUES(?, ?)",
                              (("pin_hash", pin_hash), ("pin_len", str(length))))
        self.conn.commit()

    # ---- PIN ospite (E19) ----
    def guest_pin_is_set(self) -> bool:
        return self._get("guest_pin_hash") is not None

    def set_guest_pin(self, pin: str) -> None:
        self._validate_pin(pin, MIN_PIN_GUEST)
        if self._verify(self._get("pin_hash"), pin):
            raise ValueError(SAME_PIN_MSG)
        self._store_guest_pin(self._ph.hash(pin))

    async def aset_guest_pin(self, pin: str) -> None:
        """PIN ospite (6-12 cifre, diverso dal principale); revoca le sessioni ospite aperte."""
        self._validate_pin(pin, MIN_PIN_GUEST)
        if await self._averify(self._get("pin_hash"), pin):
            raise ValueError(SAME_PIN_MSG)
        self._store_guest_pin(await asyncio.to_thread(self._ph.hash, pin))

    def _store_guest_pin(self, pin_hash: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO auth(key, value) VALUES('guest_pin_hash', ?)",
                          (pin_hash,))
        self.conn.commit()
        self.revoke_role(ROLE_GUEST)
        log.info("PIN ospite impostato: sessioni ospite revocate")

    def clear_guest_pin(self) -> None:
        self.conn.execute("DELETE FROM auth WHERE key='guest_pin_hash'")
        self.conn.commit()
        self.revoke_role(ROLE_GUEST)
        log.info("PIN ospite tolto: sessioni ospite revocate")

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
    def _issue_token(self, ip: str, user_agent: str | None, now: float,
                     role: str = ROLE_ADMIN) -> str:
        token = secrets.token_urlsafe(32)
        self.conn.execute("DELETE FROM auth_failures WHERE ip=?", (ip,))
        self.conn.execute(
            "INSERT INTO sessions(token_hash, created, last_seen, user_agent, ip, role) "
            "VALUES(?,?,?,?,?,?)", (_hash(token), now, now, user_agent, ip, role))
        self.conn.commit()
        if role == ROLE_GUEST:
            log.info("Accesso ospite riuscito da %s", ip)
        else:
            log.info("Accesso riuscito da %s", ip)
        return token

    def _finish(self, role: str | None, pin: str, ip: str, user_agent: str | None) -> str:
        now = self.clock()
        if role is None:
            self._record_failure(ip, now)
            raise PermissionError("PIN errato")
        if role == ROLE_ADMIN and self.pin_length() is None:  # PIN di una versione precedente
            self.conn.execute("INSERT OR REPLACE INTO auth(key, value) VALUES('pin_len', ?)",
                              (str(len(pin)),))
        return self._issue_token(ip, user_agent, now, role)

    def login(self, pin: str, client_ip: str, user_agent: str | None = None,
              guest_ok: bool = False) -> str:
        """Versione sincrona (CLI e test): verifica argon2 sul thread chiamante.
        guest_ok: anche il PIN ospite apre una sessione (accesso ospite attivo)."""
        self._precheck(client_ip, self.clock())
        role = ROLE_ADMIN if self._verify(self._get("pin_hash"), pin) else None
        if role is None and guest_ok and self._verify(self._get("guest_pin_hash"), pin):
            role = ROLE_GUEST
        return self._finish(role, pin, client_ip, user_agent)

    async def alogin(self, pin: str, client_ip: str, user_agent: str | None = None,
                     guest_ok: bool = False) -> str:
        # stesso lucchetto per IP e stessi blocchi per il PIN principale e per quello ospite
        async with self._ip_lock(client_ip):
            self._precheck(client_ip, self.clock())
            role = ROLE_ADMIN if await self._averify(self._get("pin_hash"), pin) else None
            if (role is None and guest_ok
                    and await self._averify(self._get("guest_pin_hash"), pin)):
                role = ROLE_GUEST
            return self._finish(role, pin, client_ip, user_agent)

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

    async def change_pin(self, token: str, current: str, new: str, min_len: int,
                         client_ip: str | None = None) -> None:
        """Verifica il PIN attuale (gli errori contano come al login, sull'IP della richiesta),
        poi revoca le altre sessioni."""
        row = self.conn.execute("SELECT ip FROM sessions WHERE token_hash=?",
                                (_hash(token or ""),)).fetchone()
        if row is None or self.check_role(token) != ROLE_ADMIN:
            raise PermissionError("sessione non valida")
        ip = client_ip or row[0] or "unknown"
        self._validate_pin(new, min_len)
        async with self._ip_lock(ip):
            self._precheck(ip, self.clock())
            ok = await self._averify(self._get("pin_hash"), current)
            if not ok:
                self._record_failure(ip, self.clock())
                raise PermissionError("PIN attuale errato")
            if await self._averify(self._get("guest_pin_hash"), new):
                raise ValueError(SAME_PIN_MSG)
            new_hash = await asyncio.to_thread(self._ph.hash, new)
            self.conn.execute("DELETE FROM auth_failures WHERE ip=?", (ip,))
            self._store_pin(new_hash, len(new))
            self.revoke_others(token)
        log.info("PIN cambiato da %s: altre sessioni revocate", ip)

    # ---- sessioni ----
    def check(self, token: str | None) -> bool:
        return self.check_role(token) is not None

    def check_role(self, token: str | None) -> str | None:
        """Ruolo della sessione valida ('admin' | 'guest'), None se assente o scaduta."""
        if not token:
            return None
        h = _hash(token)
        row = self.conn.execute("SELECT last_seen, role FROM sessions WHERE token_hash=?",
                                (h,)).fetchone()
        if row is None:
            return None
        now = self.clock()
        last_seen = row[0] or 0
        if now - last_seen > SESSION_IDLE_S:
            self._drop("token_hash=?", (h,))
            return None
        if now - last_seen >= TOUCH_INTERVAL_S:
            self.conn.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, h))
            self.conn.commit()
        # qualunque valore diverso da 'admin' vale come ospite: mai privilegi per errore
        return ROLE_ADMIN if row[1] == ROLE_ADMIN else ROLE_GUEST

    def sessions(self, current_token: str | None) -> list[dict]:
        self._drop("last_seen < ?", (self.clock() - SESSION_IDLE_S,))
        current = _hash(current_token) if current_token else None
        rows = self.conn.execute(
            "SELECT token_hash, created, last_seen, user_agent, ip, role FROM sessions "
            "ORDER BY last_seen DESC").fetchall()
        return [{"id": h[:16], "created": created, "last_seen": last_seen,
                 "user_agent": ua, "ip": ip, "current": h == current,
                 "role": ROLE_ADMIN if role == ROLE_ADMIN else ROLE_GUEST}
                for h, created, last_seen, ua, ip, role in rows]

    def count_guests(self) -> int:
        self._drop("last_seen < ?", (self.clock() - SESSION_IDLE_S,))
        return self.conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE role != 'admin'").fetchone()[0]

    def revoke_role(self, role: str) -> int:
        """Revoca tutte le sessioni di un ruolo (es. gli ospiti quando l'accesso si spegne)."""
        if role == ROLE_ADMIN:
            return self._drop("role = 'admin'", ())
        return self._drop("role != 'admin'", ())

    def revoke(self, session_id: str) -> bool:
        if not isinstance(session_id, str) or not _SESSION_ID.match(session_id):
            return False
        return self._drop("substr(token_hash, 1, 16)=?", (session_id,)) > 0

    def revoke_others(self, current_token: str) -> int:
        return self._drop("token_hash != ?", (_hash(current_token),))

    def _drop(self, where: str, params: tuple) -> int:
        """Cancella le sessioni che soddisfano `where` e chiude i loro WebSocket."""
        gone = [r[0] for r in self.conn.execute(
            f"SELECT token_hash FROM sessions WHERE {where}", params)]
        if gone:
            self.conn.executemany("DELETE FROM sessions WHERE token_hash=?", [(h,) for h in gone])
            self.conn.commit()
        for h in gone:
            for loop, event in self._watchers.get(h, ()):
                with contextlib.suppress(RuntimeError):  # loop già chiuso
                    loop.call_soon_threadsafe(event.set)
        return len(gone)

    def watch(self, token: str) -> tuple[str, asyncio.Event]:
        """Per un WebSocket: evento che scatta quando la sessione viene revocata o scade."""
        h = _hash(token)
        event = asyncio.Event()
        self._watchers.setdefault(h, set()).add((asyncio.get_running_loop(), event))
        return h, event

    def unwatch(self, token_hash: str, event: asyncio.Event) -> None:
        entries = self._watchers.get(token_hash)
        if entries is None:
            return
        entries.difference_update({e for e in entries if e[1] is event})
        if not entries:
            del self._watchers[token_hash]

    def logout(self, token: str) -> None:
        self._drop("token_hash=?", (_hash(token),))

    def reset(self) -> None:
        """`meshlens reset-pin`: toglie PIN, sessioni e ogni blocco."""
        # anche il PIN ospite: un nuovo PIN principale potrebbe coincidere con lui
        self.conn.execute("DELETE FROM auth WHERE key IN ('pin_hash', 'pin_len', 'guest_pin_hash')")
        self.forget_sessions_and_locks()

    def forget_sessions_and_locks(self) -> None:
        """Toglie sessioni e blocchi, non il PIN (dopo un ripristino: le sessioni del backup
        potrebbero essere state revocate nel frattempo)."""
        self.conn.execute("DELETE FROM auth WHERE key='global_lock_until'")
        self._drop("1", ())
        self.conn.execute("DELETE FROM auth_failures")
        self.conn.execute("DELETE FROM auth_attempts")
        self.conn.commit()
