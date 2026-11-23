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


class KeyedConnector(FakeConnector):
    """Come FakeConnector, ma tiene il decoder (per i test sulle chiavi)."""

    def __init__(self, cfg, decoder, loop, on_event):
        super().__init__(cfg, decoder, loop, on_event)
        self.decoder = decoder


PSK_A = "AAECAwQFBgcICQoLDA0ODw=="  # 16 byte 00..0f
KEY_A = bytes(range(16))


def _broker(bid, **kw):
    return {"id": bid, "name": f"Broker {bid}", "enabled": True, "host": f"{bid}.example",
            "port": 1883, "tls": False, "encryption": False, "username": "", "password": "",
            "topics": ["msh/#"], "channels": [], "extra_keys": [], **kw}


def _with(settings, bid, **changes):
    """Copia delle impostazioni con il broker `bid` modificato."""
    return {**settings, "mqtt_brokers": [{**b, **changes} if b["id"] == bid else b
                                         for b in settings["mqtt_brokers"]]}


def _plus(settings, *brokers):
    return {**settings, "mqtt_brokers": [*settings["mqtt_brokers"], *brokers]}


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
    rt.start_connectors()
    assert rt.mqtt_status()["connected"] is True
    state["fail"] = True
    await rt.on_settings_changed(_with(rt.settings, "default", host="x"))
    assert rt.mqtt_status()["connected"] is False


async def test_periodic_status_payload_uses_mqtt_key(tmp_path):
    import asyncio
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt.loop = asyncio.get_running_loop()
    rt.start_connectors()
    q = rt.bus.subscribe()
    rt._publish_status()
    msg = q.get_nowait()
    assert msg["type"] == "status"
    st = msg["mqtt"]
    assert st["connected"] is True and st["msgs_per_s"] == 1.0 and st["undecodable"] == 0
    assert st["filtered_channel"] == 0 and st["watchdog_restarts"] == 0
    assert st["queue_dropped"] == 0
    assert [b["id"] for b in st["brokers"]] == ["default"]


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
        old = rt.connectors["default"]
        old.stop = lambda: seen.append(threading.get_ident())
        saved = _with(rt.settings, "default", host="x.example")
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
    rt.start_connectors()
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
    rt.start_connectors()
    return rt


async def test_watchdog_restarts_silent_connector(tmp_path):
    rt = await _watchdog_rt(tmp_path, {"connected": True, "last_msg_age_s": 301.0,
                                       "connected_since": None})
    old = rt.connectors.get("default")
    await rt.mqtt_watchdog()
    assert rt.connectors.get("default") is not old and rt.connectors.get("default").started and old.stopped
    assert rt.mqtt_status()["watchdog_restarts"] == 1


async def test_watchdog_leaves_healthy_or_disconnected_alone(tmp_path):
    import time
    for st in ({"connected": True, "last_msg_age_s": 10.0, "connected_since": None},
               {"connected": False, "last_msg_age_s": 999.0, "connected_since": None},
               {"connected": True, "last_msg_age_s": 999.0, "connected_since": time.time() - 5}):
        rt = await _watchdog_rt(tmp_path, st)
        old = rt.connectors.get("default")
        await rt.mqtt_watchdog()
        assert rt.connectors.get("default") is old and not old.stopped
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
    rt.start_connectors()
    FakeConnector.instances.clear()
    await asyncio.gather(rt.restart_connector("default", "test"),
                         rt.on_settings_changed(_with(rt.settings, "default", host="nuovo")))
    live = [c for c in FakeConnector.instances if c.started and not c.stopped]
    assert live == [rt.connectors["default"]]


async def test_memory_prune_caps_live_nodes_and_prunes_dedup(tmp_path):
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt.live.max_nodes = 10
    for i in range(12):
        rt.live.nodes[i] = {"num": i, "last_heard": 1000 + i}
    rt.dedup.is_new(1, 1, time.time() - 10_000)
    rt.prune_memory()
    assert len(rt.live.nodes) == 9 and 0 not in rt.live.nodes
    assert rt.dedup.is_new(1, 1, time.time()) is True


async def test_mqtt_status_has_queue_fields_without_connector(tmp_path):
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt.connectors.clear()
    st = rt.mqtt_status()
    assert st["queue_dropped"] == 0 and st["queue_size"] == 0


async def test_queue_dropped_accumulates_across_connector_restarts(tmp_path):
    class Inbox:
        dropped = 0

    class DroppingConnector(FakeConnector):
        def __init__(self, *a):
            super().__init__(*a)
            self.inbox = Inbox()

        def status(self):
            return {**super().status(), "queue_dropped": self.inbox.dropped, "queue_size": 0}

    app, rt = build(tmp_path, connector_factory=DroppingConnector, static_dir=None)
    async with app.router.lifespan_context(app):
        rt.connectors["default"].inbox.dropped = 7
        await rt.restart_connector("default", "prova")
        rt.connectors["default"].inbox.dropped = 3
        assert rt.mqtt_status()["queue_dropped"] == 10
        saved = _with(rt.settings, "default", host="altro")
        await rt.on_settings_changed(saved)
        assert rt.mqtt_status()["queue_dropped"] == 10


async def test_watchdog_leaves_quiet_broker_alone(tmp_path):
    import time
    # connesso da 10 minuti senza un solo messaggio: ricollegare non serve a nulla
    rt = await _watchdog_rt(tmp_path, {"connected": True, "last_msg_age_s": None,
                                       "decoded": 0, "connected_since": time.time() - 600})
    old = rt.connectors.get("default")
    await rt.mqtt_watchdog()
    assert rt.connectors.get("default") is old and not old.stopped
    assert rt.mqtt_status()["watchdog_restarts"] == 0


async def test_watchdog_restarts_when_flowing_messages_stop(tmp_path):
    import time
    rt = await _watchdog_rt(tmp_path, {"connected": True, "last_msg_age_s": 400.0,
                                       "decoded": 12, "connected_since": time.time() - 900})
    old = rt.connectors.get("default")
    await rt.mqtt_watchdog()
    assert rt.connectors.get("default") is not old and old.stopped
    assert rt.mqtt_status()["watchdog_restarts"] == 1


async def test_watchdog_retries_failed_connector_start_every_60s(tmp_path):
    import asyncio
    state = {"fail": True, "attempts": 0}

    class Flaky(FakeConnector):
        def __init__(self, *a):
            state["attempts"] += 1
            if state["fail"]:
                raise RuntimeError("no")
            super().__init__(*a)

    clock = {"t": 1000.0}
    app, rt = build(tmp_path, connector_factory=Flaky, static_dir=None)
    rt.monotonic = lambda: clock["t"]
    async with app.router.lifespan_context(app):  # l'avvio fallito non ferma l'app
        assert "default" not in rt.connectors and state["attempts"] == 1
        clock["t"] += 30
        await rt.mqtt_watchdog()
        assert state["attempts"] == 1  # troppo presto
        clock["t"] += 31
        await rt.mqtt_watchdog()
        assert state["attempts"] == 2 and "default" not in rt.connectors  # fallito di nuovo
        state["fail"] = False
        clock["t"] += 10
        await rt.mqtt_watchdog()
        assert state["attempts"] == 2
        clock["t"] += 60
        await asyncio.gather(rt.mqtt_watchdog(), rt.mqtt_watchdog())  # col lock: un solo avvio
        assert state["attempts"] == 3 and rt.connectors["default"].started


async def test_integrity_check_runs_off_loop_at_start(tmp_path, monkeypatch):
    import asyncio
    import threading
    import meshlens.app as app_mod
    seen = {}

    def fake_check(path, on_open=None):
        seen["thread"] = threading.current_thread() is not threading.main_thread()
        seen["path"] = path
        return "ok"

    monkeypatch.setattr(app_mod, "quick_check_file", fake_check)
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    assert rt.db_health == "in corso"
    async with app.router.lifespan_context(app):
        for _ in range(50):
            if rt.db_health != "in corso":
                break
            await asyncio.sleep(0.01)
        assert rt.db_health == "ok"
    assert seen == {"thread": True, "path": tmp_path / "meshlens.db"}


async def test_integrity_check_failure_is_logged(tmp_path, monkeypatch, caplog):
    import meshlens.app as app_mod
    monkeypatch.setattr(app_mod, "quick_check_file", lambda p, on_open=None: "*** in database main ***")
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    with caplog.at_level("ERROR"):
        await rt.check_integrity()
    assert rt.db_health == "*** in database main ***"
    assert "integrità" in caplog.text
    rt.conn.close()


async def _multi_rt(tmp_path, factory=FakeConnector, *brokers):
    import asyncio
    _, rt = build(tmp_path, connector_factory=factory, static_dir=None)
    rt.loop = asyncio.get_running_loop()
    rt.settings = _plus(rt.settings, *brokers)
    FakeConnector.instances.clear()
    rt.start_connectors()
    return rt


async def test_one_connector_per_enabled_broker(tmp_path):
    rt = await _multi_rt(tmp_path, FakeConnector, _broker("b1"), _broker("b2", enabled=False))
    started = [c for c in FakeConnector.instances if c.started]
    assert sorted(c.cfg["id"] for c in started) == ["b1", "default"]
    assert sorted(rt.connectors) == ["b1", "default"]
    assert rt.connectors["b1"].cfg["host"] == "b1.example"


async def test_settings_change_restarts_only_changed_broker(tmp_path):
    rt = await _multi_rt(tmp_path, FakeConnector, _broker("b1"))
    d, b1 = rt.connectors["default"], rt.connectors["b1"]
    await rt.on_settings_changed(_with(rt.settings, "b1", host="nuovo.example"))
    assert b1.stopped and rt.connectors["b1"] is not b1
    assert rt.connectors["b1"].started and rt.connectors["b1"].cfg["host"] == "nuovo.example"
    assert rt.connectors["default"] is d and not d.stopped


async def test_channel_change_updates_keys_without_reconnect(tmp_path):
    from meshlens.crypto import DEFAULT_KEY
    rt = await _multi_rt(tmp_path, KeyedConnector, _broker("b1"))
    b1 = rt.connectors["b1"]
    saved = _with(rt.settings, "b1", channels=[{"name": "Squadra", "psk": PSK_A}])
    await rt.on_settings_changed(saved)
    assert rt.connectors["b1"] is b1 and not b1.stopped
    assert b1.decoder.channel_keys["Squadra"] == KEY_A
    assert KEY_A in b1.decoder.keys and DEFAULT_KEY in b1.decoder.keys
    assert b1.cfg["channels"] == [{"name": "Squadra", "psk": PSK_A}]
    assert "Squadra" not in rt.connectors["default"].decoder.channel_keys
    # solo il nome cambia: niente nuova connessione, cfg aggiornata
    await rt.on_settings_changed(_with(rt.settings, "b1", name="Rinominato"))
    assert rt.connectors["b1"] is b1 and b1.cfg["name"] == "Rinominato" and not b1.stopped


async def test_disable_and_remove_broker_stops_connector(tmp_path):
    rt = await _multi_rt(tmp_path, KeyedConnector, _broker("b1"), _broker("b2"))
    b1, b2, d = rt.connectors["b1"], rt.connectors["b2"], rt.connectors["default"]
    b2.decoder.channel_keys["Imparato"] = KEY_A
    saved = _with(rt.settings, "b1", enabled=False)
    saved = {**saved, "mqtt_brokers": [b for b in saved["mqtt_brokers"] if b["id"] != "b2"]}
    await rt.on_settings_changed(saved)
    assert b1.stopped and b2.stopped and not d.stopped
    assert sorted(rt.connectors) == ["default"]
    assert "b2" not in rt.learned_keys  # broker eliminato: chiavi dimenticate
    st = rt.mqtt_status()
    assert [(b["id"], b["enabled"], b["connected"]) for b in st["brokers"]] == [
        ("default", True, True), ("b1", False, False)]
    # riattivato: riparte
    await rt.on_settings_changed(_with(rt.settings, "b1", enabled=True))
    assert rt.connectors["b1"].started and rt.connectors["b1"] is not b1


async def test_failed_start_of_one_broker_keeps_others(tmp_path):
    attempts = []

    class FailB1(FakeConnector):
        def __init__(self, cfg, *a):
            attempts.append(cfg["id"])
            if cfg["id"] == "b1":
                raise RuntimeError("TLS non valido")
            super().__init__(cfg, *a)

    import asyncio
    clock = {"t": 1000.0}
    _, rt = build(tmp_path, connector_factory=FailB1, static_dir=None)
    rt.loop = asyncio.get_running_loop()
    rt.monotonic = lambda: clock["t"]
    rt.settings = _plus(rt.settings, _broker("b1"))
    rt.start_connectors()
    assert sorted(attempts) == ["b1", "default"] and sorted(rt.connectors) == ["default"]
    d = rt.connectors["default"]
    attempts.clear()
    clock["t"] += 30
    await rt.mqtt_watchdog()
    assert attempts == []
    clock["t"] += 31
    await rt.mqtt_watchdog()
    assert attempts == ["b1"] and rt.connectors["default"] is d


async def test_watchdog_restarts_only_silent_broker(tmp_path):
    import time as _t

    class PerBroker(FakeConnector):
        def status(self):
            if self.cfg["id"] == "b1":
                return {"connected": True, "last_msg_age_s": 301.0, "decoded": 5,
                        "connected_since": _t.time() - 900}
            return {"connected": True, "last_msg_age_s": 2.0, "decoded": 9,
                    "connected_since": _t.time() - 900}

    rt = await _multi_rt(tmp_path, PerBroker, _broker("b1"))
    d, b1 = rt.connectors["default"], rt.connectors["b1"]
    await rt.mqtt_watchdog()
    assert b1.stopped and rt.connectors["b1"] is not b1 and rt.connectors["b1"].started
    assert rt.connectors["default"] is d and not d.stopped
    st = rt.mqtt_status()
    per = {b["id"]: b for b in st["brokers"]}
    assert per["b1"]["watchdog_restarts"] == 1 and per["default"]["watchdog_restarts"] == 0
    assert st["watchdog_restarts"] == 1


async def test_learned_keys_survive_restart_per_broker(tmp_path):
    rt = await _multi_rt(tmp_path, KeyedConnector, _broker("b1"))
    rt.connectors["b1"].decoder.channel_keys["Locale"] = KEY_A
    await rt.restart_connector("b1", "prova")
    assert rt.connectors["b1"].decoder.channel_keys["Locale"] == KEY_A
    assert rt.connectors["b1"].decoder.broker == "b1"
    assert "Locale" not in rt.connectors["default"].decoder.channel_keys
    await rt.restart_connector("default", "prova")
    assert "Locale" not in rt.connectors["default"].decoder.channel_keys


async def test_status_totals_and_brokers(tmp_path):
    import time as _t
    now = _t.time()

    class Stat(FakeConnector):
        def status(self):
            base = {"undecodable": 1, "reconnects": 1, "decoded": 10,
                    "drops": {"empty": 1, "unsupported_port": 0, "undecodable": 1,
                              "json_topic": 0, "not_protobuf": 0},
                    "queue_dropped": 2, "queue_size": 3}
            if self.cfg["id"] == "default":
                return {**base, "connected": True, "msgs_per_s": 1.0,
                        "connected_since": now - 100, "last_msg_age_s": 4.0,
                        "last_error": "vecchio", "last_error_at": now - 500}
            return {**base, "connected": False, "msgs_per_s": 2.5, "connected_since": None,
                    "last_msg_age_s": 1.5, "last_error": "Connessione rifiutata",
                    "last_error_at": now - 5}

    rt = await _multi_rt(tmp_path, Stat, _broker("b1"), _broker("b2", enabled=False))
    st = rt.mqtt_status()
    for k in ("connected", "msgs_per_s", "undecodable", "connected_since", "last_msg_age_s",
              "reconnects", "last_error", "last_error_at", "decoded", "drops", "queue_dropped",
              "queue_size", "filtered_channel", "watchdog_restarts"):
        assert k in st, k
    assert st["connected"] is True and st["msgs_per_s"] == 3.5
    assert st["undecodable"] == 2 and st["decoded"] == 20 and st["reconnects"] == 2
    assert st["queue_dropped"] == 4 and st["queue_size"] == 6
    assert st["drops"]["empty"] == 2 and st["drops"]["undecodable"] == 2
    assert st["connected_since"] == now - 100 and st["last_msg_age_s"] == 1.5
    assert st["last_error"] == "Broker b1: Connessione rifiutata"
    assert st["last_error_at"] == now - 5
    assert [b["id"] for b in st["brokers"]] == ["default", "b1", "b2"]
    b2 = st["brokers"][2]
    assert b2["connected"] is False and b2["enabled"] is False and b2["msgs_per_s"] == 0.0
    for k in ("id", "name", "enabled", "host", "tls", "encryption", "connected", "msgs_per_s",
              "undecodable", "connected_since", "last_msg_age_s", "reconnects",
              "watchdog_restarts", "last_error", "last_error_at", "decoded", "drops",
              "queue_dropped", "queue_size"):
        assert all(k in b for b in st["brokers"]), k
    assert st["brokers"][1]["last_error"] == "Connessione rifiutata"  # senza prefisso
    assert st["brokers"][1]["host"] == "b1.example"


async def test_status_last_error_without_prefix_with_one_active_broker(tmp_path):
    class Err(FakeConnector):
        def status(self):
            return {"connected": False, "last_error": "rifiutato", "last_error_at": 1.0}

    rt = await _multi_rt(tmp_path, Err, _broker("b1", enabled=False))
    st = rt.mqtt_status()
    assert st["last_error"] == "rifiutato" and st["connected"] is False


async def test_stop_stops_all_connectors(tmp_path):
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt.settings = _plus(rt.settings, _broker("b1"))
    async with app.router.lifespan_context(app):
        conns = list(rt.connectors.values())
        assert len(conns) == 2 and all(c.started for c in conns)
    assert all(c.stopped for c in conns)


async def test_mqtt_sender_uses_connector_and_keys_of_each_broker(tmp_path):
    rt = await _multi_rt(tmp_path, KeyedConnector, _broker("b1"))
    sender = rt.ctx.mqtt_sender
    assert sender.get_connector("default") is rt.connectors["default"]
    assert sender.get_connector("b1") is rt.connectors["b1"]
    assert sender.get_connector("nessuno") is None
    rt.connectors["default"].decoder.channel_keys["X"] = KEY_A
    assert sender.key_for("default", "X") == KEY_A
    assert sender.key_for("b1", "X") is None  # le chiavi non passano da un broker all'altro
    # broker senza connettore: la chiave imparata prima dell'arresto
    rt.learned_keys["spento"] = {"Y": KEY_A}
    assert sender.key_for("spento", "Y") == KEY_A and sender.key_for("spento", "Z") is None


async def test_stop_interrupts_running_integrity_check(tmp_path, monkeypatch):
    import asyncio
    import threading
    import time as _t
    import meshlens.app as app_mod
    interrupted = threading.Event()
    opened = threading.Event()

    class SlowConn:
        def interrupt(self):
            interrupted.set()

    def slow_check(path, on_open=None):
        on_open(SlowConn())
        opened.set()
        interrupted.wait(10)  # un quick_check lungo che finisce solo se interrotto
        return "non leggibile (interrupted)"

    monkeypatch.setattr(app_mod, "quick_check_file", slow_check)
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    t0 = _t.monotonic()
    async with app.router.lifespan_context(app):
        await asyncio.to_thread(opened.wait, 5)
    assert interrupted.is_set()
    assert _t.monotonic() - t0 < 5


async def test_integrity_check_started_after_stop_request_aborts(tmp_path):
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt._interrupt_integrity()  # stop() gia' chiesto: il controllo non parte nemmeno
    await rt.check_integrity()
    assert rt.db_health == "non leggibile (interrupted)" and rt._integrity_conn is None
    rt.conn.close()


async def test_stop_stops_connectors_concurrently_off_loop(tmp_path):
    import asyncio
    import time as _t

    class SlowStop(FakeConnector):
        def stop(self):
            _t.sleep(0.4)
            super().stop()

    app, rt = build(tmp_path, connector_factory=SlowStop, static_dir=None)
    rt.settings = _plus(rt.settings, _broker("b1"), _broker("b2"))
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    async with app.router.lifespan_context(app):
        conns = list(rt.connectors.values())
        assert len(conns) == 3
        t = asyncio.create_task(ticker())
        t0 = _t.monotonic()
    elapsed = _t.monotonic() - t0
    t.cancel()
    assert all(c.stopped for c in conns)
    assert elapsed < 1.0  # in parallelo: ~0.4 s, non 1.2 s
    assert ticks >= 10  # il loop resta libero durante gli arresti


async def test_stop_logs_failing_connector_and_stops_others(tmp_path, caplog):
    class Boom(FakeConnector):
        def stop(self):
            if self.cfg["id"] == "b1":
                raise RuntimeError("guasto")
            super().stop()

    app, rt = build(tmp_path, connector_factory=Boom, static_dir=None)
    rt.settings = _plus(rt.settings, _broker("b1"))
    with caplog.at_level("ERROR"):
        async with app.router.lifespan_context(app):
            d = rt.connectors["default"]
    assert d.stopped and "b1" in caplog.text


async def test_watchdog_restart_skipped_if_connector_changed(tmp_path):
    rt = await _multi_rt(tmp_path, FakeConnector, _broker("b1"))
    b1 = rt.connectors["b1"]
    await rt.restart_connector("b1", "vecchio giudizio", expected=object())
    assert rt.connectors["b1"] is b1 and not b1.stopped
    assert rt.watchdog_restarts.get("b1", 0) == 0
    await rt.restart_connector("b1", "giusto", expected=b1)
    assert rt.connectors["b1"] is not b1 and b1.stopped


async def test_failed_start_error_shown_on_that_broker(tmp_path):
    import asyncio
    state = {"fail": True}

    class FailB1(FakeConnector):
        def __init__(self, cfg, *a):
            if cfg["id"] == "b1" and state["fail"]:
                raise RuntimeError("certificato non valido per utente-x con pw-segreta")
            super().__init__(cfg, *a)

    clock = {"t": 1000.0}
    _, rt = build(tmp_path, connector_factory=FailB1, static_dir=None)
    rt.loop = asyncio.get_running_loop()
    rt.monotonic = lambda: clock["t"]
    rt.settings = _plus(rt.settings, _broker("b1", username="utente-x", password="pw-segreta"))
    rt.start_connectors()
    per = {b["id"]: b for b in rt.mqtt_status()["brokers"]}
    err = per["b1"]["last_error"]
    assert "certificato non valido" in err and "pw-segreta" not in err and "utente-x" not in err
    assert per["b1"]["last_error_at"] is not None and per["default"]["last_error"] is None
    assert rt.mqtt_status()["last_error"].startswith("Broker b1: ")
    state["fail"] = False
    clock["t"] += 61
    await rt.mqtt_watchdog()
    per = {b["id"]: b for b in rt.mqtt_status()["brokers"]}
    assert per["b1"]["last_error"] is None  # riuscito: errore dimenticato


async def test_rename_updates_connector_label(tmp_path):
    class Labeled(FakeConnector):
        def __init__(self, cfg, *a):
            super().__init__(cfg, *a)
            self.label = cfg["name"]

    rt = await _multi_rt(tmp_path, Labeled, _broker("b1"))
    b1 = rt.connectors["b1"]
    await rt.on_settings_changed(_with(rt.settings, "b1", name="Nuovo nome"))
    assert rt.connectors["b1"] is b1 and b1.label == "Nuovo nome"


async def test_integrity_stop_between_check_and_store_aborts(tmp_path):
    import sqlite3
    import pytest
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)

    class Racy(type(rt)):
        pass

    # stop() arriva proprio mentre la connessione viene registrata
    class Conn:
        def interrupt(self):
            pass

    real_setattr = object.__setattr__

    def on_store(self, name, value):
        real_setattr(self, name, value)
        if name == "_integrity_conn" and value is not None:
            real_setattr(self, "_stopping", True)

    rt.__class__ = Racy
    Racy.__setattr__ = on_store
    with pytest.raises(sqlite3.OperationalError):
        rt._integrity_opened(Conn())
    assert rt._integrity_conn is None
    rt.conn.close()


async def test_ingestor_status_and_waypoint_reach_bus(tmp_path):
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    q = rt.bus.subscribe()
    rt.ingestor.set_status("out:r1:5", "failed", "NO_ROUTE")
    rt.ingestor.on_waypoint({"id": 7, "name": "W"})
    rt.ingestor.on_waypoint({"deleted": 7})
    assert [q.get_nowait() for _ in range(3)] == [
        {"type": "message_status", "key": "out:r1:5", "status": "failed", "error": "NO_ROUTE"},
        {"type": "waypoint", "waypoint": {"id": 7, "name": "W"}},
        {"type": "waypoint_deleted", "id": 7}]


def test_notifier_wired_into_runtime(tmp_path):
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    assert rt.notifier is rt.ctx.notifier
    nodes, msgs = [], []
    rt.notifier.on_nodes = nodes.append
    rt.notifier.on_message = msgs.append
    rt._publish_changed()  # anche senza nodi cambiati (segue le radio connesse)
    assert nodes == [[]]
    rt.ingestor.on_message({"key": "1:1", "direction": "in", "text": "ciao"})
    assert msgs and msgs[0]["key"] == "1:1"
    assert rt.notifier.status()["toast_available"] is False
    rt.ctx.toast = lambda t, b: None
    assert rt.notifier.status()["toast_available"] is True


async def test_trim_packets_chunks_and_yields(tmp_path, monkeypatch):
    import asyncio
    import meshlens.app as appmod
    import meshlens.packet_log as plmod
    monkeypatch.setattr(plmod, "PACKETS_MAX_ROWS", 100)
    monkeypatch.setattr(appmod, "PURGE_CHUNK", 50)
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt.conn.executemany("INSERT INTO packets(time, packet_id, status) VALUES(?, ?, 'ok')",
                        [(time.time(), i) for i in range(400)])
    rt.conn.commit()
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)

    t = asyncio.create_task(ticker())
    before = ticks
    deleted = await rt.trim_packets()
    t.cancel()
    assert deleted == 300
    assert ticks - before >= 5
    assert rt.conn.execute("SELECT COUNT(*) FROM packets").fetchone()[0] == 100
    # restano i piu' recenti
    assert rt.conn.execute("SELECT MIN(packet_id) FROM packets").fetchone()[0] == 300


async def test_on_event_routes_raw_packets(tmp_path):
    from meshlens.events import PacketMeta, RawPacket
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt.settings = {**rt.settings, "packet_log_mode": "all"}
    seen = []
    orig = rt.ingestor.handle
    rt.ingestor.handle = lambda ev: (seen.append(ev), orig(ev))
    raw = RawPacket(source="mqtt", from_node=0xB2, to_node=0xFFFFFFFF, packet_id=9,
                    channel="LongFast", rx_time=time.time(), snr=-9.0, rssi=None,
                    gateway_id="!gw", radio_id=None, broker="b1", relay_node=None,
                    status="encrypted", meta=PacketMeta(None, 3, 2, encrypted=True, raw=b"\x01"))
    rt.on_event(raw)
    assert seen == []
    assert 0xB2 not in rt.live.nodes
    assert rt.packet_log.flush(force=True) == 1
    row = rt.conn.execute("SELECT status, kind FROM packets").fetchone()
    assert tuple(row) == ("encrypted", None)


async def test_on_event_feeds_netstats_and_packet_log(tmp_path):
    from meshlens.events import MeshEvent, PacketMeta, TextData
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt.settings = {**rt.settings, "packet_log_mode": "all"}
    now = time.time()

    def text(pid, replayed=False):
        return MeshEvent("rf", 5, 0xFFFFFFFF, pid, "0", now, -4.0, -90, 0, None, "r1", "text",
                         TextData("ciao"), replayed=replayed,
                         meta=PacketMeta("TEXT_MESSAGE_APP", 3, 3, raw=b"ciao"))

    rt.on_event(text(11))
    rt.on_event(text(11))  # copia
    rt.on_event(text(12, replayed=True))  # rigioco S&F: non e' traffico dal vivo
    assert rt.netstats.flush() == 2
    assert rt.packet_log.flush(force=True) == 1
    st = rt.conn.execute("SELECT packets, receptions FROM stats_hourly").fetchone()
    assert tuple(st) == (1, 2)
    assert rt.conn.execute("SELECT copies FROM packets").fetchone()[0] == 2


async def test_raw_filter_follows_mode(tmp_path):
    from meshlens.ingest import _new_node
    FakeConnector.instances.clear()
    _, rt = build(tmp_path, connector_factory=KeyedConnector, static_dir=None)
    mine = {**_new_node(0x10), "is_mine": True}
    rt.live.nodes[0x10] = mine
    rt.live.nodes[0x20] = _new_node(0x20)
    rt.settings = {**rt.settings, "packet_log_mode": "off"}
    assert rt.raw_filter(0x10) is False
    rt.settings = {**rt.settings, "packet_log_mode": "all"}
    assert rt.raw_filter(0x20) is True
    rt.settings = {**rt.settings, "packet_log_mode": "archived"}
    assert rt.raw_filter(0x10) is False  # insieme non ancora calcolato
    rt.refresh_archived()
    assert rt.raw_filter(0x10) is True and rt.raw_filter(0x20) is False
    rt.settings = _plus(rt.settings, _broker("x"))
    rt.start_connectors()
    assert rt.connectors["x"].decoder.raw_filter == rt.raw_filter


async def test_stop_flushes_packet_log_and_netstats(tmp_path):
    from meshlens.db import connect as dbconnect
    from meshlens.events import MeshEvent, PacketMeta, TextData
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    rt.settings = {**rt.settings, "packet_log_mode": "all"}
    async with app.router.lifespan_context(app):
        rt.on_event(MeshEvent("rf", 5, 0xFFFFFFFF, 3, "0", time.time(), -4.0, -90, 0, None,
                              "r1", "text", TextData("ciao"),
                              meta=PacketMeta("TEXT_MESSAGE_APP", 3, 3, raw=b"ciao")))
    conn = dbconnect(tmp_path / "meshlens.db")
    assert conn.execute("SELECT COUNT(*) FROM packets").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM stats_hourly").fetchone()[0] == 1
    conn.close()


async def test_mqtt_status_exposes_packet_log_dropped(tmp_path):
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    assert rt.mqtt_status()["packet_log_dropped"] == 0 and rt.mqtt_status()["raw_dropped"] == 0
    rt.packet_log.dropped = 7
    assert rt.mqtt_status()["packet_log_dropped"] == 7


async def test_netstats_failure_does_not_stop_packet_log(tmp_path):
    from meshlens.events import MeshEvent, TextData
    _, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    seen = []
    rt.netstats.observe = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
    rt.packet_log.observe = lambda *a: seen.append(a)
    rt.on_event(MeshEvent(source="mqtt", from_node=1, to_node=2, packet_id=5, channel="c",
                          rx_time=time.time(), snr=None, rssi=None, hops=None, gateway_id=None,
                          radio_id=None, kind="text", payload=TextData("x")))
    assert len(seen) == 1


async def test_restart_keeps_learned_separate_from_custom(tmp_path):
    rt = await _multi_rt(tmp_path, KeyedConnector, _broker(
        "b1", channels=[{"name": "Squadra", "psk": PSK_A}]))
    rt.connectors["b1"].decoder.channel_keys["Locale"] = KEY_A  # imparata
    await rt.restart_connector("b1", "prova")
    dec = rt.connectors["b1"].decoder
    assert dec._learned == {"Locale": KEY_A} and set(dec._custom) == {"Squadra"}
    assert rt.learned_keys["b1"] == {"Locale": KEY_A}  # solo le imparate


async def test_removed_custom_channel_stops_decrypting_after_restart(tmp_path):
    rt = await _multi_rt(tmp_path, KeyedConnector, _broker(
        "b1", channels=[{"name": "Squadra", "psk": PSK_A}]))
    await rt.on_settings_changed(_with(rt.settings, "b1", host="nuovo.example", channels=[]))
    assert "Squadra" not in rt.connectors["b1"].decoder.channel_keys


async def test_stop_delivers_queued_inbox_events_before_closing_db(tmp_path):
    from meshlens.inbox import EventInbox
    seen = []

    class InboxConnector(FakeConnector):
        def __init__(self, cfg, decoder, loop, on_event):
            super().__init__(cfg, decoder, loop, on_event)
            self.inbox = EventInbox(loop, lambda ev: seen.append((ev, rt.conn.execute("SELECT 1").fetchone()[0])))

    rt = await _multi_rt(tmp_path, InboxConnector)
    inbox = rt.connectors["default"].inbox
    inbox.put("a")
    inbox.put("b")  # in coda, drain non ancora girato
    await rt.stop()
    assert seen == [("a", 1), ("b", 1)]  # elaborati a database aperto, senza errori


# ---- 1.6: agganci del Runtime, estensioni ----

def _text_ev(pid=7, source="mqtt", radio_id=None, replayed=False, text="ciao", num=0x0A):
    from meshlens.events import MeshEvent, TextData
    return MeshEvent(source=source, from_node=num, to_node=0xFFFFFFFF, packet_id=pid,
                     channel="LongFast" if source == "mqtt" else "0", rx_time=time.time(),
                     snr=-5.0, rssi=None, hops=1, gateway_id="!00000001" if source == "mqtt" else None,
                     radio_id=radio_id, kind="text", payload=TextData(text=text), replayed=replayed)


def _hooked(tmp_path):
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    calls = []
    rt.add_message_hook(lambda msg, meta: calls.append((msg, meta)))
    return rt, calls


def test_message_hook_receives_live_meta(tmp_path):
    rt, calls = _hooked(tmp_path)
    rt.on_event(_text_ev())
    assert len(calls) == 1
    msg, meta = calls[0]
    assert meta.outcome == "new" and meta.live is True and meta.event.packet_id == 7
    assert msg["direction"] == "in"


def test_message_hook_dup_and_replayed_not_live(tmp_path):
    rt, calls = _hooked(tmp_path)
    rt.on_event(_text_ev())
    rt.on_event(_text_ev(source="rf", radio_id="r1"))
    assert len(calls) == 2
    assert calls[1][1].outcome == "dup" and calls[1][1].live is False
    rt.on_event(_text_ev(pid=99, replayed=True, num=0x0B))
    assert calls[-1][1].event.replayed and calls[-1][1].live is False


def test_message_hook_local_for_outgoing(tmp_path):
    rt, calls = _hooked(tmp_path)
    rt.ingestor.record_outgoing_mqtt(0x0C, 0xFFFFFFFF, 5, "uscita", "LongFast")
    assert len(calls) == 1
    msg, meta = calls[0]
    assert meta.event is None and meta.outcome == "local" and meta.live is False
    assert msg["direction"] == "out"


def test_failing_hooks_do_not_stop_ingestion(tmp_path, caplog):
    rt, calls = _hooked(tmp_path)
    seen = []

    def boom(*a):
        raise RuntimeError("x")

    rt.message_hooks.insert(0, boom)
    rt.add_event_hook(boom)
    rt.add_event_hook(lambda ev, outcome: seen.append(outcome))
    rt.on_event(_text_ev())
    assert 0x0A in rt.live.nodes
    assert len(calls) == 1 and seen == ["new"]
    assert "Aggancio" in caplog.text


def test_event_hook_called_for_mesh_events_only(tmp_path):
    from meshlens.events import MeshEvent, PacketMeta, PositionData, RawPacket
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    seen = []
    rt.add_event_hook(lambda ev, outcome: seen.append((ev.kind, outcome)))
    rt.on_event(MeshEvent(source="mqtt", from_node=0x0D, to_node=0xFFFFFFFF, packet_id=3,
                          channel="LongFast", rx_time=time.time(), snr=None, rssi=None, hops=1,
                          gateway_id="!00000001", radio_id=None, kind="position",
                          payload=PositionData(lat=45.0, lon=9.0)))
    assert seen == [("position", "new")]
    rt.on_event(RawPacket(source="mqtt", from_node=0x0D, to_node=0, packet_id=4, channel="x",
                          rx_time=time.time(), snr=None, rssi=None, gateway_id=None,
                          radio_id=None, broker=None, relay_node=None, status="encrypted",
                          meta=PacketMeta(portnum=None, hop_start=None, hop_limit=None)))
    assert len(seen) == 1


async def test_periodic_task_runs_and_late_registration_fails(tmp_path):
    import asyncio
    import pytest
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    runs = {"a": 0, "s": 0}

    async def tick():
        runs["a"] += 1

    def tick_sync():
        runs["s"] += 1

    rt.add_periodic("t", 0.05, tick, first_delay_s=0)
    rt.add_periodic("s", 0.05, tick_sync, first_delay_s=0)
    await rt.start()
    try:
        await asyncio.sleep(0.2)
        assert runs["a"] >= 1 and runs["s"] >= 1
        with pytest.raises(RuntimeError):
            rt.add_periodic("late", 1, tick)
    finally:
        await rt.stop()
    assert all(t.done() for t in rt.tasks)


def test_extensions_installed_before_app_and_errors_logged(tmp_path, monkeypatch, caplog):
    import meshlens.ext_map
    import meshlens.ext_monitor

    def fail(rt, ctx):
        raise RuntimeError("rotta")

    def ok(rt, ctx):
        ctx.ext["x"] = 1

    monkeypatch.setattr(meshlens.ext_map, "install", fail)
    monkeypatch.setattr(meshlens.ext_monitor, "install", ok)
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    assert rt.ctx.ext["x"] == 1
    assert "Estensione ext_map non avviata" in caplog.text
