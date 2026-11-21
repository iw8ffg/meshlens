"""Backup del database (VACUUM INTO), ripristino differito e controllo d'integrità."""
import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Callable

BACKUP_KEEP = 5
BACKUP_WEEKLY_S = 7 * 86400
REASONS = ("pre-migrazione", "pre-aggiornamento", "settimanale", "manuale")
NAME_RE = re.compile(r"^meshlens-(\d{8}-\d{6})-([a-z-]+)\.db$")
RESTORE_FILE = "restore.json"
SAFETY_REASON = "prima-del-ripristino"
log = logging.getLogger(__name__)


def quick_check(conn: sqlite3.Connection) -> str:
    """'ok' oppure il primo errore di PRAGMA quick_check."""
    row = conn.execute("PRAGMA quick_check").fetchone()
    return str(row[0]) if row else "ok"


def _stamp(ts: float) -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(ts))


def _valid(name) -> bool:
    return isinstance(name, str) and NAME_RE.fullmatch(name) is not None


class BackupManager:
    def __init__(self, db_path: Path, backups_dir: Path, clock: Callable[[], float] = time.time,
                 keep: int = BACKUP_KEEP):
        self.db_path, self.dir = Path(db_path), Path(backups_dir)
        self.clock, self.keep = clock, keep

    # ---- creazione ----
    def _target(self, reason: str) -> Path:
        if reason not in REASONS:
            raise ValueError(f"Motivo di backup sconosciuto: {reason}")
        self.dir.mkdir(parents=True, exist_ok=True)
        ts = int(self.clock())
        while True:  # due backup nello stesso secondo non si sovrascrivono
            path = self.dir / f"meshlens-{_stamp(ts)}-{reason}.db"
            if not path.exists():
                return path
            ts += 1

    def _vacuum_into(self, conn: sqlite3.Connection, reason: str) -> dict:
        dest = self._target(reason)
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.unlink(missing_ok=True)
        try:
            conn.execute("VACUUM INTO ?", (str(tmp),))
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        self.prune()
        return self._info(dest)

    def create_sync(self, conn: sqlite3.Connection, reason: str) -> dict:
        """Sulla connessione data: solo prima della migrazione, quando e' ancora libera."""
        return self._vacuum_into(conn, reason)

    def _create_own(self, reason: str) -> dict:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        try:
            return self._vacuum_into(conn, reason)
        finally:
            conn.close()

    async def create(self, reason: str) -> dict:
        return await asyncio.to_thread(self._create_own, reason)

    # ---- elenco e pulizia ----
    def _info(self, path: Path) -> dict:
        m = NAME_RE.fullmatch(path.name)
        t = time.mktime(time.strptime(m.group(1), "%Y%m%d-%H%M%S"))
        return {"name": path.name, "time": t, "reason": m.group(2),
                "size_bytes": path.stat().st_size}

    def list(self) -> list[dict]:
        if not self.dir.is_dir():
            return []
        out = [self._info(p) for p in self.dir.iterdir() if p.is_file() and _valid(p.name)]
        out.sort(key=lambda b: (b["time"], b["name"]), reverse=True)
        return out

    def prune(self) -> None:
        for old in self.list()[self.keep:]:
            for suffix in ("", "-wal", "-shm"):
                (self.dir / (old["name"] + suffix)).unlink(missing_ok=True)

    def due(self, now: float) -> bool:
        items = self.list()
        return not items or now - items[0]["time"] >= BACKUP_WEEKLY_S

    # ---- ripristino (si completa al prossimo avvio) ----
    def schedule_restore(self, name: str) -> None:
        if not _valid(name):
            raise ValueError("Nome del backup non valido")
        if not (self.dir / name).is_file():
            raise FileNotFoundError(name)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        (self.db_path.parent / RESTORE_FILE).write_text(json.dumps({"name": name}), encoding="utf-8")


def apply_pending_restore(data_dir: Path) -> str | None:
    """Da chiamare prima di aprire il database: applica il ripristino richiesto, se c'e'."""
    data_dir = Path(data_dir)
    marker = data_dir / RESTORE_FILE
    if not marker.is_file():
        return None
    try:
        name = json.loads(marker.read_text(encoding="utf-8")).get("name")
    except (OSError, ValueError, AttributeError):
        name = None
    marker.unlink(missing_ok=True)  # un ripristino non si ripete ai prossimi avvii
    backups = data_dir / "backups"
    source = backups / name if _valid(name) else None
    if source is None or not source.is_file():
        log.error("Ripristino richiesto non applicabile: %r", name)
        return None
    db = data_dir / "meshlens.db"
    if db.exists():
        ts = time.time()
        safety = backups / f"meshlens-{_stamp(ts)}-{SAFETY_REASON}.db"
        while safety.exists():
            ts += 1
            safety = backups / f"meshlens-{_stamp(ts)}-{SAFETY_REASON}.db"
        backups.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            src = db.with_name(db.name + suffix)
            if src.exists():
                shutil.move(str(src), str(safety.with_name(safety.name + suffix)))
    tmp = db.with_name(db.name + ".restore")
    shutil.copy2(source, tmp)
    os.replace(tmp, db)
    log.warning("Database ripristinato dal backup %s", name)
    return name
