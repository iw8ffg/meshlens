import time

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
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as c:
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
    msg = q.get_nowait()
    assert msg["type"] == "status"
    assert msg["mqtt"] == {"connected": True, "msgs_per_s": 1.0, "undecodable": 0,
                           "filtered_channel": 0, "watchdog_restarts": 0}


async def test_purge_evicts_live_nodes_not_heard_for_7_days(tmp_path):
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    now = time.time()
    rt.live.nodes[1] = {"num": 1, "last_heard": now - 8 * 86400}
    rt.live.nodes[2] = {"num": 2, "last_heard": now - 3600}
    await rt.purge_once()
    assert list(rt.live.nodes) == [2]


async def test_settings_cached_and_old_connector_stopped_in_thread(tmp_path, monkeypatch):
    import threading
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    async with app.router.lifespan_context(app):
        assert rt.settings["mqtt"]["host"]
        main_thread = threading.get_ident()
        seen = []
        old = rt.connector
        old.stop = lambda: seen.append(threading.get_ident())
        saved = {**rt.settings, "mqtt": {**rt.settings["mqtt"], "host": "x.example"}}
        await rt.on_settings_changed(saved)
        assert seen and seen[0] != main_thread
        assert rt.settings is saved


async def test_auto_radio_connected_at_start_and_stopped_at_shutdown(tmp_path):
    from meshlens.store import Store
    from test_radio_manager import FakeConnector as FakeRadio

    pre = connect(tmp_path / "meshlens.db")
    Store(pre).save_radio({"id": "r0000abcd", "name": "H", "kind": "usb", "address": "COM5",
                           "auto_connect": True})
    pre.commit()
    pre.close()
    FakeRadio.instances = []
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None,
                    radio_connector_factory=FakeRadio)
    (radio,) = FakeRadio.instances
    async with app.router.lifespan_context(app):
        assert radio.starts == 1 and radio.state()["state"] == "connected"
    assert radio.stops == 1


async def test_events_reach_coverage_recorder_from_mqtt_connector(tmp_path):
    from meshlens.events import MeshEvent, RangeTestData
    FakeConnector.instances.clear()
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt.start_connector()
    assert rt.ctx.coverage is rt.coverage
    ev = MeshEvent("rf", 5, 0, 1, "", 1.0, None, None, None, None, "r1", "rangetest",
                   RangeTestData(0, "seq 0"))
    rt.on_event(ev)
    assert rt.coverage.rangetest_age("r1", 5) is not None


async def test_purge_once_yields_to_loop(tmp_path, monkeypatch):
    import asyncio
    import meshlens.app as appmod
    monkeypatch.setattr(appmod, "PURGE_CHUNK", 1000)
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    old = time.time() - 400 * 86400
    rt.conn.executemany(
        "INSERT INTO positions(node_num, time, lat, lon, source) VALUES(1, ?, 45, 9, 'mqtt')",
        [(old - i,) for i in range(5000)])
    rt.conn.commit()
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)

    t = asyncio.create_task(ticker())
    before = ticks
    deleted = await rt.purge_once()
    t.cancel()
    assert deleted["positions"] == 5000
    assert ticks - before >= 4
    assert rt.last_purge["deleted"]["positions"] == 5000


async def test_first_purge_is_delayed(tmp_path, monkeypatch):
    import asyncio
    import meshlens.app as appmod
    monkeypatch.setattr(appmod, "PURGE_FIRST_DELAY_S", 0.2)
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    old = time.time() - 400 * 86400
    rt.conn.execute(
        "INSERT INTO positions(node_num, time, lat, lon, source) VALUES(1, ?, 45, 9, 'mqtt')", (old,))
    rt.conn.commit()
    async with app.router.lifespan_context(app):
        assert rt.conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 1
        await asyncio.sleep(0.5)
        assert rt.conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 0


async def _watchdog_rt(tmp_path, status):
    import asyncio

    class Silent(FakeConnector):
        def status(self):
            return status

    _, rt = build(tmp_path, connector_factory=Silent, static_dir=None)
    rt.loop = asyncio.get_running_loop()
    rt.start_connector()
    return rt


async def test_watchdog_restarts_silent_connector(tmp_path):
    rt = await _watchdog_rt(tmp_path, {"connected": True, "last_msg_age_s": 301.0,
                                       "connected_since": None})
    old = rt.connector
    await rt.mqtt_watchdog()
    assert rt.connector is not old and rt.connector.started and old.stopped
    assert rt.mqtt_status()["watchdog_restarts"] == 1


async def test_watchdog_leaves_healthy_or_disconnected_alone(tmp_path):
    import time
    for st in ({"connected": True, "last_msg_age_s": 10.0, "connected_since": None},
               {"connected": False, "last_msg_age_s": 999.0, "connected_since": None},
               {"connected": True, "last_msg_age_s": 999.0, "connected_since": time.time() - 5}):
        rt = await _watchdog_rt(tmp_path, st)
        old = rt.connector
        await rt.mqtt_watchdog()
        assert rt.connector is old and not old.stopped
        assert rt.mqtt_status()["watchdog_restarts"] == 0


async def test_mqtt_status_route_has_new_fields(tmp_path):
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as c:
            await c.post("/api/auth/setup", json={"pin": "123456"})
            body = (await c.get("/api/mqtt/status")).json()
    assert body["filtered_channel"] == 0 and body["watchdog_restarts"] == 0
    assert body["connected"] is True


async def test_settings_change_during_watchdog_restart_leaves_one_connector(tmp_path):
    import asyncio

    class Slow(FakeConnector):
        def stop(self):
            import time
            time.sleep(0.1)
            super().stop()

    _, rt = build(tmp_path, connector_factory=Slow, static_dir=None)
    rt.loop = asyncio.get_running_loop()
    rt.start_connector()
    FakeConnector.instances.clear()
    await asyncio.gather(rt.restart_connector("test"),
                         rt.on_settings_changed({**rt.settings, "mqtt": {**rt.settings["mqtt"], "host": "nuovo"}}))
    live = [c for c in FakeConnector.instances if c.started and not c.stopped]
    assert live == [rt.connector]
