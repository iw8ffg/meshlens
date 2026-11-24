"""Lanciatore con icona di notifica: istanza singola, avvio automatico, server in un thread."""
import asyncio
import json
import logging
import os
import queue
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__, watchdog
from .paths import app_dir, is_frozen, logs_dir
from .serving import Bind, make_servers, prepare_serving, serve_all
from .tls import CertInfo

PORT = 8686
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "MeshLens"
log = logging.getLogger(__name__)
ASSETS = Path(__file__).parent / "assets"


# ---------- istanza singola ----------

def single_instance(port: int) -> str:
    """'free' se la porta è libera, 'meshlens' se risponde MeshLens, 'other' altrimenti."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            pass
    except OSError:
        return "free"
    try:
        # senza proxy: il loopback non deve mai passare dal proxy di sistema
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/api/ping", timeout=2.0) as r:
            data = json.loads(r.read(4096).decode("utf-8", "replace"))
        if isinstance(data, dict) and data.get("app") == "meshlens":
            return "meshlens"
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return "other"


# ---------- avvio automatico (HKCU Run) ----------

def _winreg():
    import winreg  # solo Windows; i test lo sostituiscono con un finto modulo
    return winreg


def autostart_enabled(frozen: bool) -> bool:
    """La voce di avvio automatico ha senso solo per l'eseguibile installato."""
    return frozen


def get_autostart() -> bool:
    w = _winreg()
    try:
        with w.OpenKey(w.HKEY_CURRENT_USER, RUN_KEY, 0, w.KEY_READ) as k:
            w.QueryValueEx(k, RUN_NAME)
        return True
    except OSError:
        return False


def set_autostart(enabled: bool, exe: Path) -> None:
    w = _winreg()
    with w.OpenKey(w.HKEY_CURRENT_USER, RUN_KEY, 0, w.KEY_SET_VALUE) as k:
        if enabled:
            w.SetValueEx(k, RUN_NAME, 0, w.REG_SZ, f'"{exe}"')
        else:
            try:
                w.DeleteValue(k, RUN_NAME)
            except OSError:
                pass  # già assente


# ---------- icona ----------

def draw_icon(size: int = 256):
    """Prima versione semplice: lente sopra una maglia di nodi (sarà sostituita dal logo)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256
    d.rounded_rectangle([8 * s, 8 * s, 248 * s, 248 * s], radius=48 * s, fill=(15, 23, 42, 255))
    pts = [(60, 70), (130, 50), (200, 90), (80, 150), (170, 170), (110, 215)]
    edges = [(0, 1), (1, 2), (0, 3), (1, 3), (1, 4), (2, 4), (3, 4), (3, 5), (4, 5)]
    for a, b in edges:
        d.line([pts[a][0] * s, pts[a][1] * s, pts[b][0] * s, pts[b][1] * s],
               fill=(56, 189, 248, 170), width=max(1, round(4 * s)))
    for x, y in pts:
        r = 9 * s
        d.ellipse([x * s - r, y * s - r, x * s + r, y * s + r], fill=(56, 189, 248, 255))
    cx, cy, r = 118 * s, 118 * s, 62 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(248, 250, 252, 255),
              width=max(1, round(14 * s)))
    d.line([cx + r * 0.72, cy + r * 0.72, 214 * s, 214 * s], fill=(248, 250, 252, 255),
           width=max(1, round(22 * s)))
    return img


def ensure_icon(png: Path = ASSETS / "meshlens.png") -> Path:
    """Restituisce il PNG dell'icona, generandolo con Pillow se manca."""
    if not png.is_file():
        png.parent.mkdir(parents=True, exist_ok=True)
        draw_icon(256).save(png)
    return png


# ---------- server in un thread ----------

class ServerThread:
    """Gli ascolti di MeshLens (loopback HTTP ed eventuale HTTPS per la rete) in un thread."""

    def __init__(self, app, binds: list[Bind], cert: CertInfo | None):
        from uvicorn.config import LOGGING_CONFIG
        # senza console (eseguibile installato) stdout è None: niente configurazione di log
        self.servers = make_servers(app, binds, cert, None if is_frozen() else LOGGING_CONFIG)
        self.server = self.servers[0]  # quello col lifespan: il suo avvio è l'avvio dell'app
        self.errors: list[str] = []  # ascolti secondari non partiti (es. porta HTTPS occupata)
        self.thread = threading.Thread(target=self._run, name="meshlens-server", daemon=True)
        self.error: BaseException | None = None

    def _run(self) -> None:
        try:
            # su Windows i sottoprocessi asyncio (go-pmtiles) richiedono il Proactor
            loop = (asyncio.ProactorEventLoop() if sys.platform == "win32"
                    else asyncio.new_event_loop())
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(serve_all(self.servers, self.errors))
            finally:
                loop.close()
        except BaseException as e:  # noqa: BLE001 - riportato al thread principale
            self.error = e

    def start(self) -> None:
        self.thread.start()

    def wait_started(self, timeout: float = 20.0) -> bool:
        pause = threading.Event()
        for _ in range(int(timeout / 0.1)):
            if self.server.started:
                return True
            if not self.thread.is_alive():
                return False
            pause.wait(0.1)
        return False

    def stop(self, timeout: float = 20.0) -> None:
        for srv in self.servers:
            srv.should_exit = True
        self.thread.join(timeout)
        if self.thread.is_alive():
            from . import maps
            log.warning("Il server non si è fermato entro %s s: chiusura forzata", timeout)
            maps.kill_children()  # niente go-pmtiles orfano


class ToastQueue:
    """Toast su un thread dedicato: Shell_NotifyIcon puo' bloccarsi e non deve fermare il loop."""

    def __init__(self, notify):
        self._notify = notify
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._run, name="meshlens-toast", daemon=True)
        self._thread.start()

    def post(self, title: str, body: str) -> None:
        self._q.put((title, body))  # non blocca mai

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            try:
                self._notify(*item)
            except Exception as e:  # noqa: BLE001 - un errore della shell non arriva mai al server
                log.warning("Notifica di Windows non riuscita: %s", e)

    def close(self, timeout: float = 2.0) -> None:
        """Ferma il thread dopo aver mostrato i toast gia' in coda (al massimo `timeout` s:
        una shell bloccata non trattiene l'uscita)."""
        self._q.put(None)
        self._thread.join(timeout)


APP_MUTEX = "MeshLensAppMutex"
ERROR_ALREADY_EXISTS = 183


def create_app_mutex() -> tuple[object, bool]:
    """Mutex con nome: l'installer (AppMutex) aspetta che MeshLens sia chiuso, e una seconda
    istanza capisce che la prima sta gia' partendo (anche prima che la porta sia in ascolto).

    Restituisce (handle, gia_esistente); (None, False) se non Windows."""
    if sys.platform != "win32":
        return None, False
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateMutexW(None, False, APP_MUTEX)  # handle tenuto finche' si vive
    return handle, ctypes.get_last_error() == ERROR_ALREADY_EXISTS


def _message_box(text: str) -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "MeshLens", 0x10)
    else:
        print(text, file=sys.stderr)


def run_tray(data_dir: Path, port: int = PORT, open_browser: bool = True) -> int:
    url = f"http://127.0.0.1:{port}"
    state = single_instance(port)
    if state == "meshlens":
        webbrowser.open(url)
        return 0
    if state == "other":
        _message_box(f"La porta {port} è occupata da un altro programma: "
                     "chiudilo e riavvia MeshLens.")
        return 1

    # prima di build(): una migrazione o un backup lunghi tengono la porta libera a lungo
    _mutex, already = create_app_mutex()  # noqa: F841 - resta aperto fino all'uscita del processo
    if already:
        log.info("MeshLens è già in esecuzione: si apre il browser sull'istanza attiva")
        webbrowser.open(url)
        return 0

    import pystray
    from PIL import Image

    from .app import build
    from .settings import load_settings

    data_dir = Path(data_dir)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        app, rt = build(data_dir, auto_update=True, log_dir=logs_dir())
        settings = load_settings(rt.conn)
        binds, cert, rt.ctx.tls = prepare_serving(data_dir, settings["lan_access"],
                                                  settings["lan_https"], port)
    except Exception as e:  # noqa: BLE001 - mostrato all'utente: senza console non lo vedrebbe
        log.exception("Avvio di MeshLens fallito")
        _message_box(f"MeshLens non è riuscito ad avviarsi: {e}\n\n"
                     f"I dettagli sono nel file di log in {logs_dir()}.")
        return 1
    watchdog.start(logs_dir())
    srv = ServerThread(app, binds, cert)
    rt.ctx.tls_errors = srv.errors  # GET /api/tls mostra anche la porta HTTPS occupata
    srv.start()
    if not srv.wait_started():
        _message_box(f"MeshLens non è riuscito ad avviarsi: {srv.error or 'errore sconosciuto'}")
        srv.stop(5)
        return 1

    icon_img = Image.open(ensure_icon())
    exe = Path(sys.executable) if is_frozen() else app_dir() / "MeshLens.exe"

    def open_ui(*_):
        webbrowser.open(url)

    def open_data(*_):
        os.startfile(str(data_dir))  # noqa: S606

    def toggle_autostart(icon, _item):
        set_autostart(not get_autostart(), exe)
        icon.update_menu()

    def quit_app(icon, _item=None):
        icon.stop()

    icon = pystray.Icon(
        "MeshLens", icon_img, f"MeshLens {__version__}",
        pystray.Menu(
            pystray.MenuItem("Apri MeshLens", open_ui, default=True),
            pystray.MenuItem("Apri cartella dati", open_data),
            pystray.MenuItem("Avvia all'accesso", toggle_autostart,
                             checked=lambda _i: get_autostart(),
                             enabled=autostart_enabled(is_frozen())),
            pystray.MenuItem("Esci", quit_app),
        ))
    # l'aggiornamento chiude tutto passando da qui
    rt.ctx.exit_callback = icon.stop

    toaster = ToastQueue(lambda title, body: icon.notify(body, title))
    rt.ctx.toast = toaster.post

    def watch() -> None:  # se il server muore da solo, chiudi anche l'icona
        srv.thread.join()
        icon.stop()

    threading.Thread(target=watch, daemon=True).start()
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        icon.run()
    finally:
        toaster.close()
        srv.stop()
        watchdog.stop()  # il lifespan ferma radio, connettore MQTT e processi figli
    return 0
