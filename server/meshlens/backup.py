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

from .db import connect

BACKUP_WEEKLY_S = 7 * 86400
REASONS = ("pre-migrazione", "pre-aggiornamento", "settimanale", "manuale")
NAME_RE = re.compile(r"^meshlens-(\d{8}-\d{6})-([a-z-]+)\.db$")
RESTORE_FILE = "restore.json"
SAFETY_REASON = "prima-del-ripristino"
# copie tenute per motivo, ognuno potato per conto suo (le piu' recenti restano)
KEEP_BY_REASON = {"manuale": 2, "pre-aggiornamento": 2, "settimanale": 3,
                  "pre-migrazione": 3, SAFETY_REASON: 3}
log = logging.getLogger(__name__)


def quick_check(conn: sqlite3.Connection) -> str:
    """'ok' oppure il primo errore di PRAGMA quick_check."""
    row = conn.execute("PRAGMA quick_check").fetchone()
    return str(row[0]) if row else "ok"


def _open_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, timeout=30)


def quick_check_file(path: Path) -> str:
    """quick_check con una connessione propria in sola lettura (adatta a to_thread)."""
    try:
        conn = _open_ro(path)
        try:
            return quick_check(conn)
        finally:
            conn.close()
    except sqlite3.Error as e:
        return f"non leggibile ({e})"


class BackupUnusable(Exception):
    """Il backup scelto e' illeggibile o danneggiato."""


def verify_backup(path: Path) -> None:
    """Controlla un backup con una connessione propria; solleva BackupUnusable se non e' sano."""
    try:
        conn = _open_ro(path)
        try:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='nodes'").fetchone() is None:
                raise BackupUnusable("il backup e' vuoto o non e' un database MeshLens")
            result = quick_check(conn)
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise BackupUnusable(f"il backup non e' leggibile ({e})") from e
    if result != "ok":
        raise BackupUnusable(f"il backup e' danneggiato ({result})")


def _stamp(ts: float) -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(ts))


def _valid(name) -> bool:
    return isinstance(name, str) and NAME_RE.fullmatch(name) is not None


class BackupManager:
    def __init__(self, db_path: Path, backups_dir: Path, clock: Callable[[], float] = time.time):
        self.db_path, self.dir = Path(db_path), Path(backups_dir)
        self.clock = clock

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
        log.info("Backup creato: %s", dest.name)
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

    def _info_or_none(self, path: Path) -> dict | None:
        try:
            return self._info(path)
        except OSError:  # sparito tra iterdir e stat
            return None

    def list(self) -> list[dict]:
        if not self.dir.is_dir():
            return []
        out = [i for p in self.dir.iterdir() if _valid(p.name)
               if (i := self._info_or_none(p)) is not None]
        out.sort(key=lambda b: (b["time"], b["name"]), reverse=True)
        return out

    def prune(self) -> None:
        items = self.list()  # dal piu' recente
        doomed = []
        for reason, keep in KEEP_BY_REASON.items():
            doomed += [b for b in items if b["reason"] == reason][keep:]
        for old in doomed:
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
        verify_backup(self.dir / name)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        (self.db_path.parent / RESTORE_FILE).write_text(json.dumps({"name": name}), encoding="utf-8")


def open_db(data_dir: Path, backups: BackupManager | None = None) -> sqlite3.Connection:
    """Apre (e se serve migra) il database di data_dir: prima di migrare un database
    esistente ne fa il backup "pre-migrazione". Usata dall'app e da `meshlens reset-pin`."""
    db_path = Path(data_dir) / "meshlens.db"
    if backups is None:
        backups = BackupManager(db_path, Path(data_dir) / "backups")
    return connect(db_path,
                   before_migrate=lambda c, old, new: backups.create_sync(c, "pre-migrazione"))


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
    suffixes = ("", "-wal", "-shm")
    moved: list[tuple[Path, Path]] = []  # (originale, copia di salvataggio)
    tmp = db.with_name(db.name + ".restore")
    try:
        verify_backup(source)
        if db.exists():
            ts = time.time()
            safety = backups / f"meshlens-{_stamp(ts)}-{SAFETY_REASON}.db"
            while safety.exists():
                ts += 1
                safety = backups / f"meshlens-{_stamp(ts)}-{SAFETY_REASON}.db"
            backups.mkdir(parents=True, exist_ok=True)
            for suffix in suffixes:
                src = db.with_name(db.name + suffix)
                if src.exists():
                    dst = safety.with_name(safety.name + suffix)
                    shutil.move(str(src), str(dst))
                    moved.append((src, dst))
        shutil.copy2(source, tmp)
        os.replace(tmp, db)
    except Exception:
        log.exception("Ripristino fallito: si riparte dal database originale")
        tmp.unlink(missing_ok=True)
        for src, _ in moved:  # solo i file davvero spostati: qui puo' esserci un resto a meta'
            src.unlink(missing_ok=True)
        for src, dst in moved:
            try:
                shutil.move(str(dst), str(src))
            except OSError:
                log.exception("Impossibile rimettere %s al suo posto", src)
        return None
    log.warning("Database ripristinato dal backup %s", name)
    return name
