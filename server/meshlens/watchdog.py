"""Diagnostica dei blocchi: un thread controlla che il loop asyncio batta il cuore ogni secondo.

Se il battito e' piu' vecchio di STALL_AFTER_S scrive UN dump di tutti i thread (faulthandler +
traceback leggibile) in logs/stall-AAAAMMGG-HHMMSS.txt e un WARNING nel log; si riarma quando
il loop riprende a battere. Il dump comprende anche il MainThread (loop dell'icona)."""
import faulthandler
import logging
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable

STALL_AFTER_S = 15.0
CHECK_EVERY_S = 1.0
log = logging.getLogger(__name__)


def format_threads() -> str:
    """Stack Python di tutti i thread, in forma leggibile."""
    names = {t.ident: t.name for t in threading.enumerate()}
    out = []
    for ident, frame in sys._current_frames().items():
        out.append(f"--- Thread {names.get(ident, '?')} (id {ident}) ---")
        out.append("".join(traceback.format_stack(frame)))
    return "\n".join(out)


class Watchdog:
    def __init__(self, log_dir: Path | None, stall_after: float = STALL_AFTER_S,
                 clock: Callable[[], float] = time.monotonic,
                 dump: Callable[[float], Path | None] | None = None):
        self.log_dir = Path(log_dir) if log_dir is not None else None
        self.stall_after = stall_after
        self.clock = clock
        self._dump = dump or self._write_dump
        self.last_beat = clock()
        self.dumped = False
        self.dumps = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def beat(self) -> None:
        self.last_beat = self.clock()

    def check(self) -> bool:
        """Un controllo; True se in questo giro ha scritto il dump."""
        age = self.clock() - self.last_beat
        if age < self.stall_after:
            self.dumped = False  # il loop e' vivo: riarma
            return False
        if self.dumped:
            return False
        self.dumped = True
        self.dumps += 1
        try:
            path = self._dump(age)
        except Exception as e:  # noqa: BLE001 - la diagnostica non deve mai disturbare
            path = None
            log.warning("Dump del blocco non riuscito: %s", e)
        log.warning("Loop asyncio fermo da %d s (dump: %s)", int(age), path or "non scritto")
        return True

    def _write_dump(self, age: float) -> Path | None:
        if self.log_dir is None:
            return None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / f"stall-{datetime.now():%Y%m%d-%H%M%S}.txt"
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            f.write(f"Loop asyncio fermo da {age:.0f} s\n\n=== traceback ===\n")
            f.write(format_threads())
            f.write("\n=== faulthandler ===\n")
            f.flush()
            faulthandler.dump_traceback(file=f, all_threads=True)
        return path

    def _run(self) -> None:
        while not self._stop.wait(CHECK_EVERY_S):
            self.check()

    def start(self) -> None:
        if self._thread is None:
            self.beat()
            self._thread = threading.Thread(target=self._run, name="meshlens-watchdog", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2)
            self._thread = None


_current: Watchdog | None = None


def start(log_dir: Path | None) -> Watchdog:
    """Avvia (una sola volta) il watchdog del processo."""
    global _current
    if _current is None:
        _current = Watchdog(log_dir)
        _current.start()
    return _current


def stop() -> None:
    global _current
    if _current is not None:
        _current.stop()
        _current = None


def beat() -> None:
    """Chiamata dal loop asyncio ogni secondo."""
    if _current is not None:
        _current.beat()
