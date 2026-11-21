"""Aggiornamento da GitHub Releases: controllo, download verificato (SHA-256) e installazione."""
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from . import __version__

log = logging.getLogger(__name__)

API_HOST = "api.github.com"
CHECK_INTERVAL_S = 24 * 3600
MAX_REDIRECTS = 5
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024
RETRY_AFTER_ERROR_S = 3600
PRIVATE_MSG = "Repository privato: inserisci un token valido in Impostazioni → Aggiornamenti"
OFFLINE_MSG = "Nessuna connessione"
BAD_HASH_MSG = "Impronta SHA-256 non corrispondente: file scartato"
DEV_MSG = "Disponibile solo nella versione installata"
INSTALLER_ARGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
_VER = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


class UpdateError(Exception):
    """Errore con messaggio per l'utente e codice HTTP associato."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class NetworkError(Exception):
    """Rete non raggiungibile (il messaggio non contiene mai URL o intestazioni)."""


def parse_version(s) -> tuple | None:
    """'v1.2.3' -> (1, 2, 3); None per pre-release (-beta) o formati non semver."""
    if not isinstance(s, str):
        return None
    m = _VER.fullmatch(s.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(latest, current) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _unlink(p: Path) -> None:
    with contextlib.suppress(OSError):
        p.unlink()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None  # i redirect li gestiamo noi, a mano


class UrllibHttp:
    """HTTP minimo con urllib. Redirect manuali: massimo 5, solo https, e l'intestazione
    Authorization viene tolta quando l'host cambia (i download GitHub vanno su CDN esterne)."""

    def __init__(self, timeout: float = 30):
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)

    def _open_once(self, url: str, headers: dict):
        """Una richiesta senza redirect: restituisce una risposta (anche 3xx/4xx)."""
        from .maps import user_agent
        req = urllib.request.Request(url, headers={"User-Agent": user_agent(), **headers})
        try:
            return self._opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            return e  # ha status/headers/read come una risposta
        except (urllib.error.URLError, OSError, TimeoutError):
            raise NetworkError(OFFLINE_MSG) from None

    def _follow(self, url: str, headers: dict):
        headers = dict(headers)
        for _ in range(MAX_REDIRECTS + 1):
            if urlsplit(url).scheme != "https":
                raise UpdateError("Sono ammessi solo download https", 502)
            r = self._open_once(url, headers)
            if r.status in (301, 302, 303, 307, 308):
                loc = r.headers.get("Location")
                r.close()
                if not loc:
                    raise UpdateError("Risposta di reindirizzamento non valida", 502)
                new = urljoin(url, loc)
                if urlsplit(new).hostname != urlsplit(url).hostname:
                    headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
                url = new
                continue
            return r
        raise UpdateError("Troppi reindirizzamenti", 502)

    def get(self, url: str, headers: dict, max_bytes: int = 5_000_000) -> tuple[int, bytes]:
        r = self._follow(url, headers)
        try:
            return r.status, r.read(max_bytes)
        finally:
            r.close()

    def download(self, url: str, headers: dict, dest: Path,
                 progress: Callable[[int, int | None], None]) -> int:
        r = self._follow(url, headers)
        try:
            if r.status != 200:
                return r.status
            total = int(r.headers.get("Content-Length") or 0) or None
            done = 0
            with open(dest, "wb") as f:
                while chunk := r.read(256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    progress(done, total)
            return 200
        finally:
            r.close()


def _ps_quote(s: str) -> str:
    """Stringa PowerShell tra apici singoli (l'apice si raddoppia)."""
    return "'" + s.replace("'", "''") + "'"


def wait_then_run_command(pid: int, argv: list[str], timeout_s: int = 60) -> list[str]:
    """Comando che aspetta la fine del processo `pid` e poi avvia l'installer.

    L'installer controlla subito se MeshLens e' aperto (AppMutex): in modalita' silenziosa,
    se lo trova, rinuncia senza dire nulla. Per questo parte solo dopo la nostra uscita.
    """
    exe, args = argv[0], argv[1:]
    arglist = ",".join(_ps_quote(a) for a in args) if args else "@()"
    script = (f"Wait-Process -Id {int(pid)} -Timeout {int(timeout_s)} -ErrorAction SilentlyContinue; "
              f"Start-Process -FilePath {_ps_quote(exe)} -ArgumentList {arglist}")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden", "-Command", script]


def default_launcher(argv: list[str]) -> None:
    """Avvia l'installer, staccato, solo dopo l'uscita di questo processo."""
    # niente DETACHED_PROCESS: PowerShell senza console non esegue nulla (provato).
    # CREATE_NO_WINDOW nasconde la finestra; BREAKAWAY_FROM_JOB evita che un job lo chiuda con noi.
    base = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    cmd = wait_then_run_command(os.getpid(), argv)
    io = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              close_fds=True)
    try:
        subprocess.Popen(cmd, creationflags=base | 0x01000000, **io)  # CREATE_BREAKAWAY_FROM_JOB
    except OSError:  # job che non consente l'uscita: si avvia senza
        subprocess.Popen(cmd, creationflags=base, **io)


class Updater:
    def __init__(self, settings: Callable[[], dict], bus, http=None, clock=time.time,
                 frozen: bool = False, updates_dir=None, launcher_exit=None,
                 launcher=default_launcher, current: str = __version__,
                 progress_interval: float = 0.5):
        self.settings, self.bus = settings, bus
        self.http = http or UrllibHttp()
        self.clock, self.frozen = clock, frozen
        self.updates_dir = Path(updates_dir) if updates_dir else None
        self.launcher_exit, self.launcher = launcher_exit, launcher
        self.current = current
        self.progress_interval = progress_interval
        self.latest: str | None = None
        self.notes: str | None = None
        self.published_at: str | None = None
        self.checked_at: float | None = None
        self.error: str | None = None
        self.job: dict | None = None
        self._assets: dict[str, dict] = {}  # nome -> {url, size}, solo host api.github.com
        self._dl: dict | None = None  # copia fissata all'avvio del download
        self._expected: dict[str, str] = {}  # nome -> SHA-256 atteso (in memoria)
        self._installing = False
        self._task: asyncio.Task | None = None
        self._next_auto: float | None = None
        self._job_seq = 0

    # ---- stato ----
    def _installer_name(self) -> str | None:
        return f"MeshLens-Setup-{self.latest}.exe" if self.latest else None

    def _paths(self) -> tuple[Path, Path] | None:
        name = self._installer_name()
        if not name or self.updates_dir is None:
            return None
        return self.updates_dir / name, self.updates_dir / (name + ".sha256")

    def _ready(self) -> bool:
        p = self._paths()
        return bool(p and p[0].is_file() and p[1].is_file())

    def available(self) -> bool:
        return self.latest is not None and is_newer(self.latest, self.current)

    def status(self) -> dict:
        return {"current": self.current, "latest": self.latest, "available": self.available(),
                "notes": self.notes, "published_at": self.published_at,
                "checked_at": self.checked_at, "error": self.error,
                "job": dict(self.job) if self.job else None,
                "frozen": bool(self.frozen),
                "can_install": bool(self.frozen and self.available() and self._ready())}

    def _headers(self, accept: str) -> dict:
        h = {"Accept": accept, "User-Agent": "MeshLens-Updater",
             "X-GitHub-Api-Version": "2022-11-28"}
        token = (self.settings().get("update_token") or "").strip()
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    # ---- controllo ----
    async def check(self) -> dict:
        self.checked_at = self.clock()
        self._next_auto = self.checked_at + RETRY_AFTER_ERROR_S  # in errore si ritenta presto
        try:
            await asyncio.to_thread(self._check_blocking)
            self.error = None
            self._next_auto = self.checked_at + CHECK_INTERVAL_S  # solo se riuscito
        except UpdateError as e:
            self.error = str(e)
        except NetworkError:
            self.error = OFFLINE_MSG
        except Exception:
            log.exception("Controllo aggiornamenti fallito")
            self.error = "Controllo aggiornamenti non riuscito"
        return self.status()

    def _check_blocking(self) -> None:
        repo = self.settings().get("update_repo") or ""
        url = f"https://{API_HOST}/repos/{repo}/releases/latest"
        status, body = self.http.get(url, self._headers("application/vnd.github+json"))
        if status in (401, 403, 404):
            raise UpdateError(PRIVATE_MSG, status)
        if status != 200:
            raise UpdateError(f"GitHub ha risposto con errore {status}", 502)
        try:
            data = json.loads(body)
            tag = data["tag_name"]
        except (ValueError, KeyError, TypeError):
            raise UpdateError("Risposta di GitHub non valida", 502) from None
        ver = parse_version(tag)
        if ver is None:  # pre-release o tag non semver: ignorata
            self.latest = self.notes = self.published_at = None
            self._assets = {}
            return
        self.latest = ".".join(str(x) for x in ver)
        self.notes = data.get("body") or None
        self.published_at = data.get("published_at")
        # il token parte solo verso api.github.com: scarta gli asset con URL di altri host
        self._assets = {}
        for a in data.get("assets", []):
            if not (isinstance(a, dict) and isinstance(a.get("name"), str)
                    and isinstance(a.get("url"), str)):
                continue
            u = urlsplit(a["url"])
            if u.scheme == "https" and u.hostname == API_HOST:
                size = a.get("size")
                self._assets[a["name"]] = {
                    "url": a["url"], "size": size if isinstance(size, int) else None}

    async def tick(self) -> None:
        """Controllo automatico: al massimo uno ogni 24 h, se abilitato."""
        if not self.settings().get("update_auto_check", True):
            return
        if self._next_auto is None or self.clock() >= self._next_auto:
            await self.check()

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Controllo automatico fallito")
            await asyncio.sleep(3600)

    # ---- download ----
    def _publish(self) -> None:
        if self.job is not None:
            self.bus.publish({"type": "update_job", "job": dict(self.job)})

    def _running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start_download(self) -> dict:
        if self._running():
            raise UpdateError("Download già in corso", 409)
        if not self.available():
            raise UpdateError("Nessun aggiornamento disponibile", 409)
        if self.updates_dir is None:
            raise UpdateError(DEV_MSG, 409)
        name = self._installer_name()
        if name not in self._assets or name + ".sha256" not in self._assets:
            raise UpdateError("La release non contiene l'installer o il file SHA-256", 502)
        size = self._assets[name]["size"]
        if size is not None and size > MAX_DOWNLOAD_BYTES:
            raise UpdateError("Installer troppo grande", 502)
        # copia: il thread di download non legge _assets, che un controllo puo' sostituire
        self._dl = {"name": name, "url": self._assets[name]["url"], "size": size,
                    "sha_url": self._assets[name + ".sha256"]["url"]}
        self._job_seq += 1
        self.job = {"id": f"u{self._job_seq}", "status": "running",
                    "bytes_done": 0, "bytes_total": None, "error": None}
        self._publish()
        self._task = asyncio.create_task(self._run())
        return dict(self.job)

    async def _ticker(self) -> None:
        while True:
            await asyncio.sleep(self.progress_interval)
            self._publish()

    async def _run(self) -> None:
        ticker = asyncio.create_task(self._ticker())
        try:
            await asyncio.to_thread(self._download_blocking)
            self.job.update(status="done")
        except UpdateError as e:
            self.job.update(status="failed", error=str(e))
        except NetworkError:
            self.job.update(status="failed", error=OFFLINE_MSG)
        except Exception:
            log.exception("Download aggiornamento fallito")
            self.job.update(status="failed", error="Download non riuscito")
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker
            self._publish()

    def _fetch_sha(self, sha_url: str) -> str:
        status, body = self.http.get(sha_url,
                                     self._headers("application/octet-stream"), 4096)
        if status != 200:
            raise UpdateError("File SHA-256 non scaricabile", 502)
        line = body.decode("utf-8", "replace").strip().split()
        if not line or not re.fullmatch(r"[0-9a-fA-F]{64}", line[0]):
            raise UpdateError("File SHA-256 non valido", 502)
        return line[0].lower()

    def _download_blocking(self) -> None:
        dl = self._dl
        name = dl["name"]
        final, sidecar = self.updates_dir / name, self.updates_dir / (name + ".sha256")
        self._expected.pop(name, None)
        self.updates_dir.mkdir(parents=True, exist_ok=True)
        tmp = final.with_name(name + ".tmp")
        _unlink(final)  # niente file "pronto" finché non è verificato
        _unlink(sidecar)
        expected = self._fetch_sha(dl["sha_url"])

        def progress(done: int, total: int | None) -> None:
            if done > MAX_DOWNLOAD_BYTES or (total and total > MAX_DOWNLOAD_BYTES):
                raise UpdateError("Installer troppo grande", 502)
            self.job["bytes_done"] = done  # solo campi semplici: pubblica il ticker
            if total:
                self.job["bytes_total"] = total

        try:
            status = self.http.download(dl["url"],
                                        self._headers("application/octet-stream"), tmp, progress)
            if status != 200:
                raise UpdateError(f"Download non riuscito (errore {status})", 502)
            if dl["size"] is not None and tmp.stat().st_size != dl["size"]:
                raise UpdateError("Dimensione dell'installer inattesa", 502)
            if _sha256(tmp) != expected:
                raise UpdateError(BAD_HASH_MSG, 502)
            sidecar.write_text(f"{expected}  {name}\n", encoding="utf-8")
            tmp.replace(final)  # compare solo dopo la verifica
            self._expected[name] = expected
        except BaseException:
            _unlink(tmp)
            _unlink(final)
            _unlink(sidecar)
            raise

    def cleanup_tmp(self) -> None:
        if self.updates_dir and self.updates_dir.is_dir():
            for p in self.updates_dir.glob("*.tmp"):
                _unlink(p)
            # installer gia' applicati (o piu' vecchi): versione <= quella in esecuzione
            for p in self.updates_dir.glob("MeshLens-Setup-*.exe*"):
                m = re.fullmatch(r"MeshLens-Setup-(\d+\.\d+\.\d+)\.exe(\.sha256)?", p.name)
                if m and not is_newer(m.group(1), self.current):
                    _unlink(p)

    # ---- installazione ----
    async def install(self, confirm) -> dict:
        if confirm is not True:
            raise UpdateError("Conferma richiesta", 400)
        if not self.frozen:
            raise UpdateError(DEV_MSG, 409)
        if self._installing:
            raise UpdateError("Installazione già in corso", 409)
        if self._running():
            raise UpdateError("Download in corso", 409)
        if not self.available() or not self._ready():
            raise UpdateError("Aggiornamento non scaricato", 409)
        self._installing = True
        try:
            final, sidecar = self._paths()
            expected = self._expected.get(final.name)
            try:
                parts = sidecar.read_text(encoding="utf-8").split()
                on_disk = parts[0].lower() if parts else ""
            except (OSError, ValueError):
                on_disk = ""
            # impronta in memoria (dal download) + sidecar + file riverificato prima di eseguire
            ok = (expected is not None and on_disk == expected
                  and await asyncio.to_thread(_sha256, final) == expected)
            if not ok:
                _unlink(final)
                _unlink(sidecar)
                raise UpdateError(BAD_HASH_MSG, 409)
            await asyncio.to_thread(self.launcher, [str(final), *INSTALLER_ARGS])
        except BaseException:
            self._installing = False  # a lancio riuscito resta True: un secondo install e' 409
            raise
        if self.launcher_exit:
            self.launcher_exit(2.0)
        return {"ok": True}
