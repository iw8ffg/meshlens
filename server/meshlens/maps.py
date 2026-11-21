"""Mappe offline: strumento go-pmtiles, ritaglio degli archivi PMTiles, elenco e cancellazione.

Un solo lavoro alla volta. Il ritaglio scrive su un file .tmp rinominato solo a fine riuscita;
annullamento e chiusura del server uccidono il processo figlio e cancellano il .tmp.
"""
import asyncio
import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

GB = 1_000_000_000

# Strumento ufficiale protomaps/go-pmtiles: versione, asset Windows x86_64 e SHA-256 fissati qui.
# Verificato il 2026-11-21 sulla release v1.31.2 (stabile, non bozza) di GitHub: l'impronta e'
# il digest sha256 pubblicato da GitHub per l'asset (la release non ha un file checksums.txt).
TOOL_VERSION = "1.31.2"
TOOL_ASSET = "go-pmtiles_1.31.2_Windows_x86_64.zip"
TOOL_URL = ("https://github.com/protomaps/go-pmtiles/releases/download/v1.31.2/"
            "go-pmtiles_1.31.2_Windows_x86_64.zip")
TOOL_SHA256 = "a658baa4d7e55020aef6ca17bd9ff9faa1582671266b36f58c52db0ac8e785a1"
TOOL_SIZE = 17_842_310  # byte dello zip
TOOL_EXE = "pmtiles.exe"

SOURCE_TEMPLATE = "https://build.protomaps.com/{}.pmtiles"
SOURCE_DAYS_BACK = 7
ITALY_BBOX = [6.6, 36.6, 18.6, 47.1]
MAXZOOM = {"world": 6, "italy": 14, "area": 14}
ESTIMATE_WORLD = 200_000_000
ESTIMATE_ITALY = 2 * GB
ESTIMATE_MIN = 50_000_000
MAX_SPAN_DEG = 40
BAD_HASH_MSG = "Impronta del file non valida: download annullato"
_PCT = re.compile(r"(\d{1,3})\s*%")


class MapsError(Exception):
    """Errore di dominio con codice HTTP suggerito."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class _Cancelled(Exception):
    pass


def _bbox_area(b) -> float:
    return (b[2] - b[0]) * (b[3] - b[1])


def validate_bbox(bbox) -> list[float]:
    if (not isinstance(bbox, (list, tuple)) or len(bbox) != 4
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(v) for v in bbox)):
        raise MapsError("Area non valida: servono 4 coordinate")
    b = [float(v) for v in bbox]
    if not (-180 <= b[0] <= 180 and -180 <= b[2] <= 180):
        raise MapsError("Area non valida: longitudine fuori da -180..180")
    if not (-85 <= b[1] <= 85 and -85 <= b[3] <= 85):
        raise MapsError("Area non valida: latitudine fuori da -85..85")
    if b[0] >= b[2] or b[1] >= b[3]:
        raise MapsError("Area non valida: il minimo deve essere minore del massimo")
    if b[2] - b[0] > MAX_SPAN_DEG or b[3] - b[1] > MAX_SPAN_DEG:
        raise MapsError("Area troppo grande: massimo 40° x 40°")
    return b


def estimate_bytes(kind: str, bbox) -> int:
    if kind == "world":
        return ESTIMATE_WORLD
    if kind == "italy":
        return ESTIMATE_ITALY
    b = validate_bbox(bbox)
    return max(ESTIMATE_MIN, int(ESTIMATE_ITALY * _bbox_area(b) / _bbox_area(ITALY_BBOX)))


def find_source(head: Callable[[str], int], today: date,
                custom: str | None) -> tuple[str, str | None]:
    """URL della build Protomaps piu' recente (oggi e fino a 7 giorni indietro) e la sua data."""
    if custom and custom.strip():
        return custom.strip(), None
    for back in range(SOURCE_DAYS_BACK + 1):
        d = (today - timedelta(days=back)).strftime("%Y%m%d")
        url = SOURCE_TEMPLATE.format(d)
        try:
            if head(url) == 200:
                return url, d
        except Exception:
            continue  # rete assente o errore: prova il giorno prima
    raise MapsError("Nessuna mappa Protomaps disponibile negli ultimi 7 giorni", 502)


def default_head(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def default_downloader(url: str, dest: Path, progress: Callable[[int, int | None], None]) -> None:
    """Download a blocchi (da eseguire in un thread); progress puo' sollevare per interrompere."""
    if urlsplit(url).scheme != "https":
        raise MapsError("Sono ammessi solo download https")
    with urllib.request.urlopen(url, timeout=30) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0) or None
        done = 0
        while chunk := r.read(256 * 1024):
            f.write(chunk)
            done += len(chunk)
            progress(done, total)


async def default_runner(argv: list[str], on_output: Callable[[str], None]) -> int:
    """Lancia il processo; all'annullamento (o chiusura) lo uccide prima di rilanciare."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL)
    try:
        while chunk := await proc.stdout.read(4096):
            for part in re.split(r"[\r\n]+", chunk.decode("utf-8", "replace")):
                if part.strip():
                    on_output(part.strip())
        return await proc.wait()
    finally:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await asyncio.shield(proc.wait())


def default_disk_free(path: Path) -> int:
    return shutil.disk_usage(path).free


class MapsManager:
    def __init__(self, data_dir, store_settings: Callable[[], dict], bus, runner=None,
                 downloader=None, clock=time.time, head=None, disk_free=None,
                 tool_sha256: str = TOOL_SHA256, progress_interval: float = 2.0):
        self.data_dir = Path(data_dir)
        self.maps_dir = self.data_dir / "maps"
        self.tools_dir = self.data_dir / "tools"
        self.maps_dir.mkdir(parents=True, exist_ok=True)
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self.store_settings, self.bus = store_settings, bus
        self.runner = runner or default_runner
        self.downloader = downloader or default_downloader
        self.clock = clock
        self.head = head or default_head
        self.disk_free = disk_free or default_disk_free
        self.tool_sha256 = tool_sha256
        self.progress_interval = progress_interval
        self.job: dict | None = None
        self._task: asyncio.Task | None = None
        self._tool_cancel = threading.Event()

    # ---- stato ----
    @property
    def tool_path(self) -> Path:
        return self.tools_dir / TOOL_EXE

    def _read_maps(self) -> list[dict]:
        try:
            data = json.loads((self.maps_dir / "maps.json").read_text("utf-8"))
        except (OSError, ValueError):
            return []
        return [m for m in data.get("maps", []) if (self.maps_dir / f"{m['id']}.pmtiles").exists()]

    def _write_maps(self, items: list[dict]) -> None:
        path = self.maps_dir / "maps.json"
        tmp = self.maps_dir / "maps.json.tmp"
        tmp.write_text(json.dumps({"maps": items}, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, path)  # scrittura atomica

    def status(self) -> dict:
        installed = self.tool_path.exists()
        return {"maps": self._read_maps(),
                "tool": {"installed": installed, "version": TOOL_VERSION,
                         "size_bytes": self.tool_path.stat().st_size if installed else TOOL_SIZE},
                "job": dict(self.job) if self.job else None,
                "disk_free_bytes": self.disk_free(self.maps_dir),
                "mode": self.store_settings().get("map_mode", "auto")}

    def _today(self) -> date:
        return datetime.fromtimestamp(self.clock(), timezone.utc).date()

    async def _source(self) -> tuple[str, str | None]:
        custom = self.store_settings().get("maps_source_url") or None
        return await asyncio.to_thread(find_source, self.head, self._today(), custom)

    async def estimate(self, kind: str, bbox) -> dict:
        size = estimate_bytes(kind, ITALY_BBOX if kind == "italy" else bbox)
        url, d = await self._source()
        return {"estimate_bytes": size, "source_url": url, "source_date": d,
                "needs_tool": not self.tool_path.exists(), "tool_size_bytes": TOOL_SIZE}

    # ---- lavoro ----
    def _publish(self) -> None:
        if self.job:
            self.bus.publish({"type": "map_job", "job": dict(self.job)})

    def _set(self, **kw) -> None:
        self.job.update(kw)
        self._publish()

    def _running(self) -> bool:
        return self.job is not None and self.job["status"] == "running"

    async def start(self, kind: str, bbox, name: str | None) -> dict:
        if self._running():
            raise MapsError("C'è già un download in corso", 409)
        need_tool = not self.tool_path.exists()
        if kind == "tool":
            if not need_tool:
                raise MapsError("Strumento già installato", 409)
            size, url, sdate = TOOL_SIZE, None, None
        else:
            if kind == "area":
                bbox = validate_bbox(bbox)
            elif kind == "italy":
                bbox = list(ITALY_BBOX)
            else:
                bbox = None
            size = estimate_bytes(kind, bbox)
        need = int(size * 1.5 + GB)
        if self.disk_free(self.maps_dir) < need:
            raise MapsError("Spazio su disco insufficiente: servono circa "
                            f"{math.ceil(need / GB)} GB", 409)
        if kind != "tool":
            url, sdate = await self._source()
        now = self.clock()
        self.job = {"id": uuid.uuid4().hex[:12], "kind": "tool" if need_tool else kind,
                    "name": name or {"world": "Mondo", "italy": "Italia",
                                     "tool": "Strumento go-pmtiles"}.get(kind, "Area"),
                    "status": "running", "step": "In coda", "bytes_done": 0,
                    "bytes_total": TOOL_SIZE if need_tool else size, "error": None,
                    "started": now, "ended": None}
        self._task = asyncio.create_task(
            self._run(kind, bbox, url, sdate, size, self.job["name"]))
        self._publish()
        return dict(self.job)

    async def _ticker(self, tmp_path: Path) -> None:
        while True:
            await asyncio.sleep(self.progress_interval)
            with contextlib.suppress(OSError):
                if self.job["step"] == "Ritaglio della mappa" and tmp_path.exists():
                    self.job["bytes_done"] = max(self.job["bytes_done"], tmp_path.stat().st_size)
            self._publish()

    async def _run(self, kind, bbox, url, sdate, size, name) -> None:
        map_id = kind if kind in ("world", "italy") else f"area-{int(self.clock())}"
        tmp = self.maps_dir / f"{map_id}.pmtiles.tmp"
        ticker = asyncio.create_task(self._ticker(tmp))
        try:
            if not self.tool_path.exists():
                await self._install_tool()
            if kind != "tool":
                self._set(kind=kind, step="Ritaglio della mappa", bytes_done=0,
                          bytes_total=size)
                await self._extract(kind, bbox, url, tmp, size)
                self._register(map_id, kind, name, bbox, tmp, sdate)
            self._set(status="done", step="Completato", ended=self.clock())
        except asyncio.CancelledError:
            self._set(status="cancelled", step="Annullato", ended=self.clock())
        except _Cancelled:
            self._set(status="cancelled", step="Annullato", ended=self.clock())
        except MapsError as e:
            self._set(status="failed", error=str(e), ended=self.clock())
        except Exception as e:
            self._set(status="failed", error=f"Errore imprevisto: {e}", ended=self.clock())
        finally:
            ticker.cancel()
            for p in (tmp, self.tools_dir / "pmtiles.zip.tmp"):
                with contextlib.suppress(OSError):
                    p.unlink()

    async def _install_tool(self) -> None:
        zip_tmp = self.tools_dir / "pmtiles.zip.tmp"
        exe_tmp = self.tools_dir / f"{TOOL_EXE}.tmp"
        self._tool_cancel.clear()
        self._set(kind="tool", step="Scarico lo strumento go-pmtiles", bytes_done=0,
                  bytes_total=TOOL_SIZE)

        def progress(done: int, total: int | None) -> None:
            if self._tool_cancel.is_set():
                raise _Cancelled()
            self.job["bytes_done"] = done  # solo campi semplici: la pubblicazione e' del ticker
            if total:
                self.job["bytes_total"] = total

        fut = asyncio.ensure_future(
            asyncio.to_thread(self.downloader, TOOL_URL, zip_tmp, progress))
        try:
            await asyncio.shield(fut)
        except asyncio.CancelledError:
            self._tool_cancel.set()
            with contextlib.suppress(BaseException):
                await fut  # attende il thread, cosi' il file si puo' cancellare
            raise
        try:
            self._set(step="Verifica dell'impronta")
            digest = await asyncio.to_thread(_sha256, zip_tmp)
            if digest != self.tool_sha256:
                raise MapsError(BAD_HASH_MSG)
            await asyncio.to_thread(_extract_exe, zip_tmp, exe_tmp)
            os.replace(exe_tmp, self.tool_path)  # compare solo dopo la verifica
        finally:
            for p in (zip_tmp, exe_tmp):
                with contextlib.suppress(OSError):
                    p.unlink()

    async def _extract(self, kind, bbox, url, tmp: Path, size: int) -> None:
        argv = [str(self.tool_path), "extract", url, str(tmp)]
        if bbox:
            argv.append("--bbox=" + ",".join(f"{v:g}" for v in bbox))
        argv += [f"--maxzoom={MAXZOOM[kind]}", "--download-threads=4"]

        def on_output(line: str) -> None:
            m = _PCT.search(line)
            if m:
                pct = min(100, int(m.group(1)))
                self.job["bytes_done"] = max(self.job["bytes_done"],
                                             int((self.job["bytes_total"] or size) * pct / 100))

        with contextlib.suppress(OSError):
            tmp.unlink()
        rc = await self.runner(argv, on_output)
        if rc != 0:
            raise MapsError(f"Ritaglio non riuscito (codice {rc})")
        if not tmp.exists():
            raise MapsError("Ritaglio non riuscito: file non creato")

    def _register(self, map_id, kind, name, bbox, tmp: Path, sdate) -> None:
        final = self.maps_dir / f"{map_id}.pmtiles"
        os.replace(tmp, final)  # rinomina solo a fine riuscita
        entry = {"id": map_id, "name": name, "kind": kind, "bbox": bbox,
                 "maxzoom": MAXZOOM[kind], "size_bytes": final.stat().st_size,
                 "created": self.clock(), "source_date": sdate}
        items = [m for m in self._read_maps() if m["id"] != map_id] + [entry]
        self._write_maps(items)
        self.job["bytes_done"] = entry["size_bytes"]

    async def cancel(self, job_id: str) -> dict:
        if not self.job or self.job["id"] != job_id:
            raise MapsError("Lavoro non trovato", 404)
        if self._running() and self._task is not None:
            self._task.cancel()
            await asyncio.wait({self._task})
        return dict(self.job)

    async def shutdown(self) -> None:
        """Chiusura del server: termina il lavoro in corso (uccide il figlio, cancella i .tmp)."""
        if self._running() and self._task is not None:
            self._task.cancel()
            await asyncio.wait({self._task})
        self.cleanup_tmp()

    async def delete(self, map_id: str) -> None:
        if self._running():
            raise MapsError("Attendi la fine del download in corso", 409)
        items = self._read_maps()
        if not any(m["id"] == map_id for m in items):
            raise MapsError("Mappa non trovata", 404)
        with contextlib.suppress(FileNotFoundError):
            (self.maps_dir / f"{map_id}.pmtiles").unlink()
        self._write_maps([m for m in items if m["id"] != map_id])

    def cleanup_tmp(self) -> None:
        """Cancella i file temporanei rimasti (da avvio o chiusura interrotti)."""
        for d in (self.maps_dir, self.tools_dir):
            for p in d.glob("*.tmp"):
                with contextlib.suppress(OSError):
                    p.unlink()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _extract_exe(zip_path: Path, out: Path) -> None:
    """Estrae solo pmtiles.exe (nome scelto da noi: nessun percorso dallo zip)."""
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.filename.rsplit("/", 1)[-1].lower() == TOOL_EXE and not info.is_dir():
                with z.open(info) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                return
    raise MapsError("Archivio dello strumento non valido")
