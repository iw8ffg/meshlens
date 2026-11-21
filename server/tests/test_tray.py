import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest

from meshlens import tray
from meshlens.app import build
from meshlens.serving import Bind


def _serve(body: bytes, status=200):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _free_port() -> int:
    srv = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = srv.server_port
    srv.server_close()
    return port


def test_single_instance_free():
    assert tray.single_instance(_free_port()) == "free"


def test_single_instance_meshlens():
    srv = _serve(json.dumps({"app": "meshlens", "version": "1.0.0"}).encode())
    try:
        assert tray.single_instance(srv.server_port) == "meshlens"
    finally:
        srv.shutdown()


@pytest.mark.parametrize("body,status", [(b"<html>ciao</html>", 200),
                                         (b'{"app":"altro"}', 200),
                                         (b'{"detail":"x"}', 404)])
def test_single_instance_other(body, status):
    srv = _serve(body, status)
    try:
        assert tray.single_instance(srv.server_port) == "other"
    finally:
        srv.shutdown()


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    KEY_READ = 1
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def OpenKey(self, root, path, reserved=0, access=0):
        assert root == "HKCU" and path.endswith(r"CurrentVersion\Run")
        return self

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def SetValueEx(self, key, name, _r, typ, value):
        self.values[name] = value

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], 1

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_autostart_roundtrip(monkeypatch):
    fake = FakeWinreg()
    monkeypatch.setattr(tray, "_winreg", lambda: fake)
    assert tray.get_autostart() is False
    tray.set_autostart(True, Path(r"C:\Prog\MeshLens.exe"))
    assert tray.get_autostart() is True
    assert fake.values["MeshLens"] == r'"C:\Prog\MeshLens.exe"'
    tray.set_autostart(False, Path(r"C:\Prog\MeshLens.exe"))
    assert tray.get_autostart() is False
    tray.set_autostart(False, Path("x.exe"))  # idempotente


def test_ensure_icon_generates(tmp_path):
    png = tray.ensure_icon(tmp_path / "m.png")
    assert png.is_file() and png.stat().st_size > 0


async def test_internal_shutdown_route_removed(tmp_path):
    app, rt = build(tmp_path, static_dir=None)
    async with await _client(app, "127.0.0.1") as c:
        r = await c.post("/api/internal/shutdown")
        assert r.status_code in (404, 405)
    assert not hasattr(rt.ctx, "shutdown_token")


async def _client(app, ip):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(ip, 1)),
                             base_url="http://127.0.0.1")


def test_server_config_ignores_proxy_headers(tmp_path):
    app, _ = build(tmp_path, static_dir=None)
    st = tray.ServerThread(app, [Bind("127.0.0.1", 0, False)], None)
    assert st.server.config.proxy_headers is False


def test_server_thread_stop_signals_every_server(monkeypatch):
    class T:
        def join(self, t):
            pass

        def is_alive(self):
            return False

    class S:
        should_exit = False

    st = tray.ServerThread.__new__(tray.ServerThread)
    st.servers = [S(), S()]
    st.server, st.thread = st.servers[0], T()
    st.stop(0.01)
    assert all(s.should_exit for s in st.servers)


def test_stop_timeout_logs_and_kills_children(caplog, monkeypatch):
    from meshlens import maps
    killed = []
    monkeypatch.setattr(maps, "kill_children", lambda: killed.append(1))

    class T:
        def join(self, t):
            pass

        def is_alive(self):
            return True

    class S:
        should_exit = False

    st = tray.ServerThread.__new__(tray.ServerThread)
    st.servers = [S()]
    st.server, st.thread = st.servers[0], T()
    with caplog.at_level("WARNING"):
        st.stop(0.01)
    assert killed == [1] and "non si è fermato" in caplog.text


def test_autostart_item_disabled_when_not_frozen():
    assert tray.autostart_enabled(False) is False
    assert tray.autostart_enabled(True) is True


def test_app_mutex_noop_off_windows(monkeypatch):
    from meshlens import tray
    monkeypatch.setattr(tray.sys, "platform", "linux")
    assert tray.create_app_mutex() == (None, False)


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="mutex con nome solo su Windows")
def test_app_mutex_detects_second_instance(monkeypatch):
    import ctypes
    monkeypatch.setattr(tray, "APP_MUTEX", f"MeshLensTestMutex-{__import__('os').getpid()}")
    first, existed = tray.create_app_mutex()
    try:
        assert first and existed is False
        second, existed2 = tray.create_app_mutex()
        assert existed2 is True
        ctypes.windll.kernel32.CloseHandle(second)
    finally:
        ctypes.windll.kernel32.CloseHandle(first)


def _no_build(*a, **k):
    raise AssertionError("build() non deve partire")


def test_second_instance_during_startup_opens_browser_without_build(tmp_path, monkeypatch):
    import meshlens.app as app_mod
    opened = []
    monkeypatch.setattr(tray, "single_instance", lambda port: "free")  # la prima sta migrando
    monkeypatch.setattr(tray, "create_app_mutex", lambda: (123, True))
    monkeypatch.setattr(tray.webbrowser, "open", opened.append)
    monkeypatch.setattr(app_mod, "build", _no_build)
    assert tray.run_tray(tmp_path, 8686) == 0
    assert opened == ["http://127.0.0.1:8686"]


def test_build_failure_shows_message_and_exits(tmp_path, monkeypatch, caplog):
    import meshlens.app as app_mod
    shown = []

    def broken(*a, **k):
        raise RuntimeError("database bloccato")

    monkeypatch.setattr(tray, "single_instance", lambda port: "free")
    monkeypatch.setattr(tray, "create_app_mutex", lambda: (123, False))
    monkeypatch.setattr(tray, "_message_box", shown.append)
    monkeypatch.setattr(app_mod, "build", broken)
    with caplog.at_level("ERROR"):
        assert tray.run_tray(tmp_path, 8686) == 1
    assert len(shown) == 1
    assert "non è riuscito ad avviarsi" in shown[0] and "database bloccato" in shown[0]
    assert "Avvio di MeshLens fallito" in caplog.text


def test_tray_sets_toast_on_context(tmp_path, monkeypatch):
    import sys
    import types
    import meshlens.app as app_mod

    class Icon:
        last = None

        def __init__(self, *a, **k):
            self.notified = []
            Icon.last = self

        def notify(self, message, title=None):
            self.notified.append((message, title))
            if message == "boom":
                raise OSError("Shell_NotifyIcon fallita")

        def run(self):
            # mentre l'icona e' attiva il server usa ctx.toast
            rt.ctx.toast("T", "B")
            rt.ctx.toast("X", "boom")  # l'errore non arriva al chiamante

        def stop(self):
            pass

    fake = types.SimpleNamespace(Icon=Icon, Menu=lambda *a: a, MenuItem=lambda *a, **k: a)
    monkeypatch.setitem(sys.modules, "pystray", fake)

    class Srv:
        def __init__(self, *a):
            self.errors = []
            self.thread = types.SimpleNamespace(join=lambda *a: None)

        def start(self): pass
        def wait_started(self): return True
        def stop(self, *a): pass

    ctx = types.SimpleNamespace(toast=None, tls=None, tls_errors=None, exit_callback=None)
    rt = types.SimpleNamespace(ctx=ctx, conn=None)
    monkeypatch.setattr(tray, "single_instance", lambda port: "free")
    monkeypatch.setattr(tray, "create_app_mutex", lambda: (123, False))
    monkeypatch.setattr(app_mod, "build", lambda *a, **k: (object(), rt))
    monkeypatch.setattr("meshlens.settings.load_settings",
                        lambda conn: {"lan_access": False, "lan_https": False})
    monkeypatch.setattr(tray, "prepare_serving", lambda *a: ([], None, {}))
    monkeypatch.setattr(tray, "ServerThread", Srv)
    monkeypatch.setattr(tray, "ensure_icon", lambda: tmp_path / "x.png")
    monkeypatch.setattr("PIL.Image.open", lambda p: object())
    assert tray.run_tray(tmp_path, 8686, open_browser=False) == 0
    assert Icon.last.notified == [("B", "T"), ("boom", "X")]
