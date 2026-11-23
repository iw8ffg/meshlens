"""Rotte di WP5a: traceroute periodici, bot, webhook."""
import json
import time

import pytest
from fastapi import HTTPException

from meshlens import api_automation, api_maintenance
from meshlens.api import create_app
from meshlens.bot import Bot
from meshlens.settings import load_settings, save_settings
from meshlens.trace_scheduler import TraceScheduler
from meshlens.webhook import WebhookService
from test_api import client, logged, make_ctx
from test_webhook import server  # noqa: F401 - fixture


class FakeRadios:
    def __init__(self):
        self.sent = []

    def radios(self):
        return [{"id": "r1", "name": "Heltec", "state": "connected", "channels": []}]

    def local_ids(self):
        return {"!00000001"}

    async def send(self, *a, **kw):
        self.sent.append((a, kw))
        return {"key": "out:r1:pending-1"}

    async def traceroute(self, *a, **kw):
        raise AssertionError("nessun traceroute nei test delle rotte")


class _LocalOpener:
    """Opener di prova: manda la richiesta https al server http locale dei test."""

    def __init__(self, port):
        import urllib.request
        self.port, self.inner = port, urllib.request.build_opener()

    def open(self, req, timeout=None):
        import urllib.request
        local = urllib.request.Request(f"http://127.0.0.1:{self.port}/h", data=req.data,
                                       headers=dict(req.header_items()), method="POST")
        return self.inner.open(local, timeout=timeout)


def auto_ctx():
    ctx = make_ctx()
    ctx.radios = FakeRadios()
    settings = lambda: load_settings(ctx.conn)  # noqa: E731
    ctx.ext["trace_scheduler"] = TraceScheduler(
        ctx.conn, ctx.store, ctx.radios, ctx.live, ctx.bus, settings)
    ctx.ext["bot"] = Bot(settings, time.time, ctx.radios, None, ctx.live, ctx.radios.local_ids,
                         lambda: set(), lambda num: {}, ctx.bus.publish, "1.6.0")
    ctx.ext["webhook"] = WebhookService(settings, time.time, version="1.6.0")
    return ctx


@pytest.fixture
def actx():
    return auto_ctx()


def test_routes_answer_503_without_install():
    with pytest.raises(HTTPException) as e:
        api_automation._ext({}, "bot")
    assert e.value.status_code == 503
    assert e.value.detail == "Automazioni non disponibili"


def test_ext_helper_returns_service():
    class Ctx:
        ext = {"bot": object()}
    assert api_automation._ext(Ctx(), "bot") is Ctx.ext["bot"]


def test_app_imports_without_cycles():
    import subprocess
    import sys
    from pathlib import Path
    server = Path(__file__).parents[1]
    r = subprocess.run([sys.executable, "-c", "import meshlens.app"], cwd=server,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


def test_guest_get_paths_empty():
    assert api_automation.GUEST_GET_PATHS == ()
    assert api_maintenance.GUEST_GET_PATHS == ()


def test_maintenance_registered(monkeypatch):
    calls = []
    monkeypatch.setattr(api_maintenance, "register", lambda *a: calls.append(a))
    create_app(make_ctx())
    assert len(calls) == 1


# ---- traceroute periodici ------------------------------------------------
def add_node(ctx, num, **kw):
    ctx.live.nodes[num] = {"id": f"!{num:08x}", "num": num, "long_name": f"N{num}",
                           "country": "IT", "last_heard": 0, "is_mine": False, **kw}


async def test_put_get_delete_target(actx):
    add_node(actx, 0xaabbccdd)
    async with logged(actx) as c:
        r = await c.put("/api/trace-targets/!aabbccdd", json={"interval_min": 180})
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["node_id"] == "!aabbccdd" and t["enabled"] is True and t["interval_min"] == 180
        r = await c.get("/api/trace-targets")
        body = r.json()
        assert body["enabled"] is False and body["max_per_hour"] == 6
        assert [x["node_id"] for x in body["targets"]] == ["!aabbccdd"]
        r = await c.request("DELETE", "/api/trace-targets/!aabbccdd")
        assert r.status_code in (400, 415)
        r = await c.request("DELETE", "/api/trace-targets/!aabbccdd", json={})
        assert r.json() == {"ok": True}
        assert (await c.get("/api/trace-targets")).json()["targets"] == []


async def test_put_validation_errors(actx):
    add_node(actx, 0x10)
    async with logged(actx) as c:
        r = await c.put("/api/trace-targets/!00000010", json={"interval_min": 30})
        assert r.status_code == 400 and "Intervallo" in r.json()["detail"]
        r = await c.put("/api/trace-targets/!00000001", json={"interval_min": 60})
        assert r.status_code == 400  # nodo proprio
        r = await c.put("/api/trace-targets/!00000010", json={"interval_min": 60,
                                                               "radio_id": "zz"})
        assert r.status_code == 400 and r.json()["detail"] == "Radio non valida"
        r = await c.put("/api/trace-targets/xyz", json={"interval_min": 60})
        assert r.status_code == 400
        assert r.json()["detail"] == "Identificativo del nodo non valido"
        for i in range(20):
            add_node(actx, 0x100 + i)
            r = await c.put(f"/api/trace-targets/!{0x100 + i:08x}", json={"interval_min": 60})
            assert r.status_code == 200
        r = await c.put("/api/trace-targets/!00000010", json={"interval_min": 60})
        assert r.status_code == 400 and "massimo 20" in r.json()["detail"]


async def test_enable_route_turns_on_auto_traceroutes(actx):
    async with logged(actx) as c:
        r = await c.put("/api/settings", json={"traceroute_auto_enabled": True})
        assert r.status_code == 400  # interruttore dedicato
        r = await c.post("/api/trace-targets/enable", json={"enabled": True})
        assert r.status_code == 200 and r.json()["enabled"] is True
        assert load_settings(actx.conn)["traceroute_auto_enabled"] is True
        assert actx.changed[-1]["traceroute_auto_enabled"] is True
        r = await c.post("/api/trace-targets/enable", json={"enabled": False})
        assert r.json()["enabled"] is False
        assert load_settings(actx.conn)["traceroute_auto_enabled"] is False
        r = await c.post("/api/trace-targets/enable", content="x",
                         headers={"content-type": "text/plain"})
        assert r.status_code == 415


async def test_requires_auth(actx):
    async with client(actx) as c:
        for method, path in [("GET", "/api/trace-targets"),
                             ("PUT", "/api/trace-targets/!00000010"),
                             ("DELETE", "/api/trace-targets/!00000010"),
                             ("POST", "/api/trace-targets/enable"),
                             ("GET", "/api/trace-targets/!00000010/history"),
                             ("GET", "/api/bot"), ("POST", "/api/bot/enable"),
                             ("POST", "/api/bot/preview"), ("GET", "/api/webhook"),
                             ("POST", "/api/webhook/test"), ("POST", "/api/webhook/enable")]:
            r = await c.request(method, path, json={})
            assert r.status_code == 401, (method, path)


async def test_routes_503_without_extension():
    ctx = make_ctx()
    async with logged(ctx) as c:
        assert (await c.get("/api/trace-targets")).status_code == 503
        assert (await c.get("/api/bot")).status_code == 503
        assert (await c.get("/api/webhook")).status_code == 503


def insert_trace(ctx, num, t, status, route, auto=False):
    cur = ctx.conn.execute(
        "INSERT INTO traceroutes(radio_id, target_num, time, status, forward, back, auto, route)"
        " VALUES('r1',?,?,?,?,?,?,?)",
        (num, t, status, json.dumps([{"id": "!00000001", "snr": None}]), "[]",
         1 if auto else 0, route))
    return cur.lastrowid


async def test_history_marks_route_changes(actx):
    insert_trace(actx, 0x10, 100, "ok", "!aa")
    insert_trace(actx, 0x10, 200, "ok", "!aa")
    insert_trace(actx, 0x10, 300, "ok", "!aa>!bb")
    insert_trace(actx, 0x10, 400, "failed", None)
    insert_trace(actx, 0x10, 500, "ok", "")
    async with logged(actx) as c:
        r = await c.get("/api/trace-targets/!00000010/history")
        items = r.json()
    got = [(i["time"], i["route_changed"], i["prev_route"]) for i in items]
    assert got == [(500, True, "!aa>!bb"), (400, False, None), (300, True, "!aa"),
                   (200, False, "!aa"), (100, False, None)]


async def test_history_pagination_and_predecessor_beyond_page(actx):
    for i, route in enumerate(["!a", "!b", "!b", "!c", "!c"]):
        insert_trace(actx, 0x10, 100 * (i + 1), "ok", route)
    async with logged(actx) as c:
        items = (await c.get("/api/trace-targets/!00000010/history?limit=2")).json()
        assert [(i["time"], i["route_changed"], i["prev_route"]) for i in items] == [
            (500, False, "!c"), (400, True, "!b")]
        items = (await c.get("/api/trace-targets/!00000010/history?limit=2&before=400")).json()
        assert [(i["time"], i["route_changed"]) for i in items] == [(300, False), (200, True)]
        for bad in (0, 101):
            r = await c.get(f"/api/trace-targets/!00000010/history?limit={bad}")
            assert r.status_code == 400


async def test_history_includes_auto_flag(actx):
    insert_trace(actx, 0x10, 100, "ok", "", auto=True)
    insert_trace(actx, 0x10, 200, "timeout", None)
    async with logged(actx) as c:
        items = (await c.get("/api/trace-targets/!00000010/history")).json()
    assert [i["auto"] for i in items] == [False, True]
    assert all("forward" in i and "back" in i for i in items)
    assert items[0]["route_changed"] is False and items[0]["prev_route"] is None


def test_annotate_history_same_time_uses_id(actx):
    a = insert_trace(actx, 0x10, 100, "ok", "!a")
    b = insert_trace(actx, 0x10, 100, "ok", "!b")
    rows = actx.store.traceroutes(0x10, 1)
    assert rows[0]["id"] == b
    out = api_automation.annotate_history(actx.conn, rows)
    assert out[0]["prev_route"] == "!a" and out[0]["route_changed"] is True and a < b


# ---- bot -------------------------------------------------------------------
RF_T = {"kind": "radio", "radio_id": "r1", "channel_index": 0}
MQ_T = {"kind": "mqtt", "broker": "b1", "channel": "LongFast"}


async def test_bot_status_route(actx):
    async with logged(actx) as c:
        body = (await c.get("/api/bot")).json()
    assert set(body["status"]) == {"enabled", "queued", "sent_last_hour", "paused_until",
                                   "last_error", "dropped"}
    assert body["commands"] == ["ping", "info", "nodes", "time", "weather"]


async def test_enable_requires_confirm_and_json(actx):
    save_settings(actx.conn, {"bot_targets": [RF_T]})
    async with logged(actx) as c:
        r = await c.post("/api/bot/enable", json={"enabled": True})
        assert r.status_code == 400 and r.json()["detail"] == "Conferma richiesta"
        r = await c.post("/api/bot/enable", content="{}", headers={"content-type": "text/plain"})
        assert r.status_code == 415
        assert load_settings(actx.conn)["bot_enabled"] is False


async def test_enable_requires_target(actx):
    async with logged(actx) as c:
        r = await c.post("/api/bot/enable", json={"enabled": True, "confirm": True})
    assert r.status_code == 400
    assert r.json()["detail"] == "Per attivare il bot scegli almeno un canale"


async def test_enable_requires_loopback(actx, monkeypatch):
    save_settings(actx.conn, {"bot_targets": [RF_T]})
    async with logged(actx) as c:
        monkeypatch.setattr(api_automation, "is_loopback_request", lambda request: False)
        r = await c.post("/api/bot/enable", json={"enabled": True, "confirm": True})
        assert r.status_code == 403
        r = await c.post("/api/bot/enable", json={"enabled": False})
        assert r.status_code == 200 and r.json()["status"]["enabled"] is False


async def test_enable_rejects_unconfirmed_mqtt_broker(actx):
    brokers = load_settings(actx.conn)["mqtt_brokers"]
    brokers = [*brokers, {**brokers[0], "id": "b1", "name": "Privato", "host": "example.org"}]
    save_settings(actx.conn, {"mqtt_brokers": brokers, "bot_targets": [RF_T, MQ_T]})
    async with logged(actx) as c:
        r = await c.post("/api/bot/enable", json={"enabled": True, "confirm": True})
        assert r.status_code == 400 and "b1" in r.json()["detail"]
        save_settings(actx.conn, {"mqtt_send_confirmed_brokers": ["b1"]})
        n = len(actx.changed)
        r = await c.post("/api/bot/enable", json={"enabled": True, "confirm": True})
        assert r.status_code == 200 and r.json()["status"]["enabled"] is True
    assert load_settings(actx.conn)["bot_enabled"] is True
    assert len(actx.changed) == n + 1


async def test_enable_off_clears_state(actx):
    save_settings(actx.conn, {"bot_targets": [RF_T]})
    bot = actx.ext["bot"]
    async with logged(actx) as c:
        await c.post("/api/bot/enable", json={"enabled": True, "confirm": True})
        from meshlens.bot import Job
        bot._queue.append(Job(RF_T, "[bot] x", 1, "!000000aa", time.time()))
        r = await c.post("/api/bot/enable", json={"enabled": False})
    assert load_settings(actx.conn)["bot_enabled"] is False
    assert bot.status()["queued"] == 0 and r.json()["status"]["queued"] == 0


async def test_preview_does_not_send(actx):
    save_settings(actx.conn, {"bot_replies": [{"trigger": "orari", "text": "Bus alle 8"}]})
    async with logged(actx) as c:
        r = (await c.post("/api/bot/preview", json={"text": "!ora"})).json()
        assert r["command"] == "time" and r["reply"].startswith("[bot] Ora:")
        r = (await c.post("/api/bot/preview", json={"text": "ciao"})).json()
        assert r["command"] is None and r["reply"] is None
        r = (await c.post("/api/bot/preview", json={"text": "!ping"})).json()
        assert r["sample"] is True and r["reply"].startswith("[bot] pong!")
        r = (await c.post("/api/bot/preview", json={"text": "Orari?"})).json()
        assert r["trigger"] == "orari" and r["reply"] == "[bot] Bus alle 8"
        r = await c.post("/api/bot/preview", json={"text": "x" * 201})
        assert r.status_code == 422
    assert actx.radios.sent == []


# ---- webhook ---------------------------------------------------------------
async def test_webhook_status_never_exposes_url(actx):
    save_settings(actx.conn, {"webhook_url": "https://example.org/hook?token=SEGRETO1"})
    async with logged(actx) as c:
        w = await c.get("/api/webhook")
        s = await c.get("/api/settings")
    assert w.json()["configured"] is True and "SEGRETO1" not in w.text
    assert "SEGRETO1" not in s.text and "example.org" not in w.text


async def test_webhook_test_route(actx, server):  # noqa: F811
    from meshlens import webhook as webhook_mod
    svc = actx.ext["webhook"]
    async with logged(actx) as c:
        r = await c.post("/api/webhook/test", json={})
        assert r.status_code == 400 and r.json()["detail"] == "Webhook non configurato"
        save_settings(actx.conn, {"webhook_url": f"https://hook.example:{server.server_port}/h"})
        # M1: la prova applica lo stesso controllo dei bersagli (qui risolto verso il PC)
        svc.check_target = lambda u: webhook_mod.check_url(
            u, lambda h, p, *a, **k: [(2, 1, 6, "", ("127.0.0.1", p))])
        r = await c.post("/api/webhook/test", json={})
        assert r.json() == {"ok": False, "code": "blocked_target"} and server.hits == []


async def test_webhook_test_route_delivers(actx, server):  # noqa: F811
    svc = actx.ext["webhook"]
    async with logged(actx) as c:
        save_settings(actx.conn, {"webhook_url": f"https://hook.example:{server.server_port}/h"})
        svc.check_target = lambda u: None
        svc.opener = _LocalOpener(server.server_port)
        r = await c.post("/api/webhook/test", json={})
        assert r.json() == {"ok": True, "code": "ok"}
        assert json.loads(server.hits[0]["body"])["event"] == "test"
        r = await c.post("/api/webhook/test", json={})
        assert r.status_code == 429
        assert r.json()["detail"] == "Attendi qualche secondo prima di un'altra prova"


async def test_webhook_enable_route(actx, monkeypatch):
    async with logged(actx) as c:
        r = await c.put("/api/settings", json={"webhook_enabled": True})
        assert r.status_code == 400  # interruttore dedicato
        r = await c.post("/api/webhook/enable", json={"enabled": True})
        assert r.status_code == 400 and r.json()["detail"] == "Webhook non configurato"
        save_settings(actx.conn, {"webhook_url": "https://example.org/hook"})
        monkeypatch.setattr(api_automation, "is_loopback_request", lambda request: False)
        r = await c.post("/api/webhook/enable", json={"enabled": True})
        assert r.status_code == 403
        monkeypatch.undo()
        r = await c.post("/api/webhook/enable", json={"enabled": True})
        assert r.status_code == 200 and r.json()["enabled"] is True
        assert "example.org" not in r.text
        assert load_settings(actx.conn)["webhook_enabled"] is True
        r = await c.post("/api/webhook/enable", json={"enabled": False})
        assert r.json()["enabled"] is False
