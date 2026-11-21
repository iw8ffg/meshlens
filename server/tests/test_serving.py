import asyncio
import socket
import ssl

import httpx
from fastapi import FastAPI

from meshlens import serving, tls
from meshlens.serving import Bind


def test_plan_binds_cases():
    assert serving.plan_binds(False, False, 8686) == [Bind("127.0.0.1", 8686, False)]
    assert serving.plan_binds(False, True, 8686) == [Bind("127.0.0.1", 8686, False)]
    assert serving.plan_binds(True, False, 8686) == [Bind("0.0.0.0", 8686, False)]
    assert serving.plan_binds(True, True, 8686) == [Bind("127.0.0.1", 8686, False),
                                                    Bind("0.0.0.0", 8687, True)]


def test_prepare_without_https_has_no_cert(tmp_path):
    binds, cert, info = serving.prepare_serving(tmp_path, True, False, 8686)
    assert binds == [Bind("0.0.0.0", 8686, False)] and cert is None
    assert info == {"enabled": False, "port": None, "fingerprint_sha256": None,
                    "not_after": None, "error": None}
    assert not (tmp_path / "tls").exists()


def test_prepare_with_https_creates_cert(tmp_path):
    binds, cert, info = serving.prepare_serving(tmp_path, True, True, 8686, ips=["192.168.1.10"])
    assert binds == [Bind("127.0.0.1", 8686, False), Bind("0.0.0.0", 8687, True)]
    assert cert.cert_path == tmp_path / "tls" / "cert.pem"
    assert info == {"enabled": True, "port": 8687, "fingerprint_sha256": cert.fingerprint_sha256,
                    "not_after": cert.not_after, "error": None}


def test_cert_failure_serves_loopback_only(tmp_path, monkeypatch, caplog):
    def boom(*a, **k):
        raise OSError("disco pieno")

    monkeypatch.setattr(serving, "ensure_cert", boom)
    with caplog.at_level("ERROR"):
        binds, cert, info = serving.prepare_serving(tmp_path, True, True, 8686, ips=[])
    assert binds == [Bind("127.0.0.1", 8686, False)] and cert is None
    assert info["enabled"] is False and "certificato" in info["error"]
    assert "http://127.0.0.1:8686" in info["error"]
    assert "disco pieno" in caplog.text


def test_make_servers_only_first_has_lifespan(tmp_path):
    cert = tls.ensure_cert(tmp_path / "tls", [])
    binds = [Bind("127.0.0.1", 8686, False), Bind("0.0.0.0", 8687, True)]
    servers = serving.make_servers(FastAPI(), binds, cert, None)
    assert [s.config.lifespan for s in servers] == ["on", "off"]
    assert [(s.config.host, s.config.port) for s in servers] == [("127.0.0.1", 8686),
                                                                ("0.0.0.0", 8687)]
    assert servers[0].config.ssl_certfile is None
    assert servers[1].config.ssl_certfile == str(cert.cert_path)
    assert servers[1].config.ssl_keyfile == str(cert.key_path)
    assert all(s.config.proxy_headers is False for s in servers)


class _FakeServer:
    def __init__(self, port, fail=None, log=None):
        self.config = type("C", (), {"port": port})()
        self.fail, self.log = fail, log if log is not None else []
        self.started = False
        self.should_exit = False

    async def serve(self):
        if self.fail is not None:
            raise self.fail
        self.started = True
        self.log.append(("start", self.config.port))
        while not self.should_exit:
            await asyncio.sleep(0.01)
        self.log.append(("stop", self.config.port))


async def test_secondary_bind_failure_keeps_primary():
    log: list = []
    primary = _FakeServer(8686, log=log)
    secondary = _FakeServer(8687, fail=SystemExit(1))
    errors: list[str] = []
    task = asyncio.create_task(serving.serve_all([primary, secondary], errors))
    for _ in range(200):
        if errors:
            break
        await asyncio.sleep(0.01)
    assert len(errors) == 1 and "8687" in errors[0]
    assert not task.done() and primary.started
    primary.should_exit = True
    await asyncio.wait_for(task, 2)
    assert log == [("start", 8686), ("stop", 8686)]


async def test_secondary_starts_after_primary_and_stops_with_it():
    log: list = []
    primary = _FakeServer(8686, log=log)
    secondary = _FakeServer(8687, log=log)
    errors: list[str] = []
    task = asyncio.create_task(serving.serve_all([primary, secondary], errors))
    for _ in range(200):
        if secondary.started:
            break
        await asyncio.sleep(0.01)
    primary.should_exit = True
    await asyncio.wait_for(task, 2)
    assert log[0] == ("start", 8686) and ("stop", 8687) in log and errors == []


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _tiny_app() -> FastAPI:
    app = FastAPI()

    @app.get("/x")
    async def x():
        return {"ok": True}

    return app


def test_real_https_listener_and_busy_port(tmp_path):
    """Un HTTPS vero risponde col certificato creato; con la porta occupata resta l'HTTP."""
    from meshlens.tray import ServerThread
    cert = tls.ensure_cert(tmp_path / "tls", [])
    http_port, https_port = _free_port(), _free_port()
    st = ServerThread(_tiny_app(), [Bind("127.0.0.1", http_port, False),
                                    Bind("127.0.0.1", https_port, True)], cert)
    st.start()
    try:
        assert st.wait_started()
        for _ in range(100):
            if st.servers[1].started:
                break
            st.thread.join(0.05)
        assert httpx.get(f"http://127.0.0.1:{http_port}/x").json() == {"ok": True}
        r = httpx.get(f"https://127.0.0.1:{https_port}/x", verify=ssl.create_default_context(cafile=str(cert.cert_path)))
        assert r.json() == {"ok": True}
    finally:
        st.stop(5)

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        st = ServerThread(_tiny_app(), [Bind("127.0.0.1", http_port, False),
                                        Bind("127.0.0.1", busy.getsockname()[1], True)], cert)
        st.start()
        try:
            assert st.wait_started()
            for _ in range(100):
                if st.errors:
                    break
                st.thread.join(0.05)
            assert st.errors and str(busy.getsockname()[1]) in st.errors[0]
            assert httpx.get(f"http://127.0.0.1:{http_port}/x").json() == {"ok": True}
        finally:
            st.stop(5)
