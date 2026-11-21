import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest

from meshlens import tray
from meshlens.app import build


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


async def _client(app, ip):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(ip, 1)),
                             base_url="http://127.0.0.1")


async def test_shutdown_endpoint(tmp_path):
    app, rt = build(tmp_path, static_dir=None)
    calls = []
    rt.ctx.exit_callback = lambda: calls.append(1)
    tok = rt.ctx.shutdown_token
    assert len(tok) >= 32
    async with app.router.lifespan_context(app):
        async with await _client(app, "127.0.0.1") as c:
            assert (await c.post("/api/internal/shutdown")).status_code == 403
            r = await c.post("/api/internal/shutdown", headers={"X-Shutdown-Token": "sbagliato"})
            assert r.status_code == 403
            assert not calls
        async with await _client(app, "192.168.1.9") as c:
            r = await c.post("/api/internal/shutdown", headers={"X-Shutdown-Token": tok})
            assert r.status_code == 403
            assert not calls
        async with await _client(app, "127.0.0.1") as c:
            r = await c.post("/api/internal/shutdown", headers={"X-Shutdown-Token": tok})
            assert r.status_code == 200
        for _ in range(50):
            if calls:
                break
            import asyncio
            await asyncio.sleep(0.02)
        assert calls == [1]


async def test_ping_unauthenticated(tmp_path):
    from meshlens import __version__
    app, rt = build(tmp_path, static_dir=None)
    async with app.router.lifespan_context(app):
        async with await _client(app, "127.0.0.1") as c:
            r = await c.get("/api/ping")
            assert r.status_code == 200
            assert r.json() == {"app": "meshlens", "version": __version__}


def test_request_exit_delay_zero_calls_callback(tmp_path):
    app, rt = build(tmp_path, static_dir=None)
    ev = threading.Event()
    rt.ctx.exit_callback = ev.set
    rt.ctx.request_exit(0)
    assert ev.wait(2)
    rt.conn.close()
