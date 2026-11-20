import httpx

from meshlens.__main__ import main
from meshlens.app import build
from meshlens.auth import Auth
from meshlens.db import connect


class FakeConnector:
    instances = []

    def __init__(self, cfg, decoder, loop, on_event):
        self.cfg, self.started, self.stopped = cfg, False, False
        FakeConnector.instances.append(self)

    def start(self): self.started = True
    def stop(self): self.stopped = True
    def status(self): return {"connected": True, "msgs_per_s": 1.0, "undecodable": 0}


async def test_build_serves_auth_status_and_reset_pin(tmp_path, capsys):
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    async with app.router.lifespan_context(app):
        assert FakeConnector.instances[-1].started
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/auth/status")
            assert r.status_code == 200 and r.json()["pin_set"] is False
            assert (await c.post("/api/auth/setup", json={"pin": "123456"})).status_code == 200
            assert (await c.get("/api/auth/status")).json()["pin_set"] is True
            await c.put("/api/settings", json={"mqtt": {"host": "altro.example"}})
            assert FakeConnector.instances[-2].stopped
            assert FakeConnector.instances[-1].cfg["host"] == "altro.example"
    assert FakeConnector.instances[-1].stopped

    assert main(["reset-pin", "--data-dir", str(tmp_path)]) == 0
    assert "PIN azzerato" in capsys.readouterr().out
    assert Auth(connect(tmp_path / "meshlens.db")).pin_is_set() is False
