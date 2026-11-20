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


async def test_periodic_task_logs_exception_and_keeps_running(tmp_path, caplog):
    import asyncio
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("guasto")

    with caplog.at_level("ERROR"):
        t = asyncio.create_task(rt._every(0.01, boom, first_now=True))
        await asyncio.sleep(0.1)
        t.cancel()
    assert len(calls) > 1
    assert "Task periodico fallito" in caplog.text


async def test_failed_connector_restart_reports_disconnected(tmp_path):
    state = {"fail": False}

    class Flaky(FakeConnector):
        def __init__(self, *a):
            if state["fail"]:
                raise RuntimeError("no")
            super().__init__(*a)

    import asyncio
    _, rt = build(tmp_path, connector_factory=Flaky, static_dir=None)
    rt.loop = asyncio.get_running_loop()
    rt.start_connector()
    assert rt.mqtt_status()["connected"] is True
    state["fail"] = True
    await rt.on_settings_changed({"mqtt": {"host": "x"}})
    assert rt.mqtt_status()["connected"] is False


async def test_periodic_status_payload_uses_mqtt_key(tmp_path):
    import asyncio
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt.loop = asyncio.get_running_loop()
    rt.start_connector()
    q = rt.bus.subscribe()
    rt._publish_status()
    assert q.get_nowait() == {
        "type": "status",
        "mqtt": {"connected": True, "msgs_per_s": 1.0, "undecodable": 0}}
