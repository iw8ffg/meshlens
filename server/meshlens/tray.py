"""Lanciatore con icona di notifica: istanza singola, avvio automatico, server in un thread."""
import asyncio
import json
import logging
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__
from .paths import app_dir, is_frozen, logs_dir

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
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2.0) as r:
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
    def __init__(self, app, host: str, port: int):
        import uvicorn
        from uvicorn.config import LOGGING_CONFIG
        # senza console (eseguibile installato) stdout è None: niente configurazione di log
        cfg = uvicorn.Config(app, host=host, port=port,
                             log_config=None if is_frozen() else LOGGING_CONFIG,
                             proxy_headers=False, forwarded_allow_ips=None, use_colors=False)
        self.server = uvicorn.Server(cfg)
        self.thread = threading.Thread(target=self._run, name="meshlens-server", daemon=True)
        self.error: BaseException | None = None

    def _run(self) -> None:
        try:
            # su Windows i sottoprocessi asyncio (go-pmtiles) richiedono il Proactor
            loop = (asyncio.ProactorEventLoop() if sys.platform == "win32"
                    else asyncio.new_event_loop())
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.server.serve())
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
        self.server.should_exit = True
        self.thread.join(timeout)
        if self.thread.is_alive():
            from . import maps
            log.warning("Il server non si è fermato entro %s s: chiusura forzata", timeout)
            maps.kill_children()  # niente go-pmtiles orfano


APP_MUTEX = "MeshLensAppMutex"


def create_app_mutex():
    """Mutex con nome: l'installer (AppMutex) aspetta che MeshLens sia chiuso. None se non Windows."""
    if sys.platform != "win32":
        return None
    import ctypes
    return ctypes.windll.kernel32.CreateMutexW(None, False, APP_MUTEX)  # handle tenuto finche' si vive


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

    import pystray
    from PIL import Image

    _mutex = create_app_mutex()  # noqa: F841 - resta aperto fino all'uscita del processo

    from .app import build
    from .settings import load_settings

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    app, rt = build(data_dir, auto_update=True, log_dir=logs_dir())
    host = "0.0.0.0" if load_settings(rt.conn)["lan_access"] else "127.0.0.1"
    srv = ServerThread(app, host, port)
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

    def watch() -> None:  # se il server muore da solo, chiudi anche l'icona
        srv.thread.join()
        icon.stop()

    threading.Thread(target=watch, daemon=True).start()
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        icon.run()
    finally:
        srv.stop()  # il lifespan ferma radio, connettore MQTT e processi figli
    return 0
