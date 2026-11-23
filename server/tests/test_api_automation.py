"""Rotte di WP5a: traceroute periodici, bot, webhook."""
import json

import pytest
from fastapi import HTTPException

from meshlens import api_automation, api_maintenance
from meshlens.api import create_app
from meshlens.settings import load_settings, save_settings
from meshlens.trace_scheduler import TraceScheduler
from test_api import client, logged, make_ctx


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


def auto_ctx():
    ctx = make_ctx()
    ctx.radios = FakeRadios()
    ctx.ext["trace_scheduler"] = TraceScheduler(
        ctx.conn, ctx.store, ctx.radios, ctx.live, ctx.bus, lambda: load_settings(ctx.conn))
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
                             ("GET", "/api/trace-targets/!00000010/history")]:
            r = await c.request(method, path, json={})
            assert r.status_code == 401, (method, path)


async def test_routes_503_without_extension():
    ctx = make_ctx()
    async with logged(ctx) as c:
        assert (await c.get("/api/trace-targets")).status_code == 503


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
