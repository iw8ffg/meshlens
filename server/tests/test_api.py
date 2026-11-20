import contextlib
import time

import httpx
import pytest
from httpx import ASGITransport
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from meshlens.api import AppContext, create_app
from meshlens.auth import Auth
from meshlens.bus import Bus
from meshlens.db import connect
from meshlens.geo import CountryLocator
from meshlens.live import LiveState
from meshlens.store import Store


def make_ctx(static_dir=None):
    conn = connect(":memory:")
    live = LiveState()
    now = time.time()
    live.load([
        {"id": "!00000001", "num": 1, "long_name": "A", "country": "IT", "last_heard": now,
         "is_mine": True},
        {"id": "!00000002", "num": 2, "long_name": "B", "country": "IT", "last_heard": now - 7200 * 3},
        {"id": "!00000003", "num": 3, "long_name": "C", "country": "DE", "last_heard": now},
        {"id": "!00000004", "num": 4, "long_name": "D", "country": None, "last_heard": now},
    ])
    live.messages.append({"key": "1:1", "text": "ciao", "country": "IT", "time": now - 1})
    live.messages.append({"key": "1:2", "text": "hallo", "country": "DE", "time": now})
    live.messages.append({"key": "1:3", "text": "??", "country": None, "time": now})
    changed = []

    async def on_changed(s):
        changed.append(s)

    ctx = AppContext(live=live, store=Store(conn), auth=Auth(conn), bus=Bus(),
                     locator=CountryLocator(), conn=conn,
                     mqtt_status=lambda: {"connected": True, "msgs_per_s": 1.0, "undecodable": 0},
                     on_settings_changed=on_changed, static_dir=static_dir)
    ctx.changed = changed
    return ctx


@pytest.fixture
def ctx():
    return make_ctx()


def client(ctx, host="127.0.0.1"):
    return httpx.AsyncClient(transport=ASGITransport(app=create_app(ctx), client=(host, 1234)),
                             base_url="http://test")


@contextlib.asynccontextmanager
async def logged(ctx):
    async with client(ctx) as c:
        r = await c.post("/api/auth/setup", json={"pin": "1234"})
        assert r.status_code == 200
        yield c


async def test_requires_auth(ctx):
    async with client(ctx) as c:
        r = await c.get("/api/nodes")
        assert r.status_code == 401
        assert r.json() == {"detail": "Accesso richiesto"}
        r = await c.get("/api/auth/status")
        assert r.json() == {"pin_set": False, "authenticated": False, "is_local": True}


def test_ws_rejects_without_cookie(ctx):
    with TestClient(create_app(ctx)) as tc:
        with pytest.raises(WebSocketDisconnect) as e:
            with tc.websocket_connect("/ws") as ws:
                ws.receive_text()
        assert e.value.code == 4401


async def test_setup_rules(ctx):
    async with client(ctx, "192.168.1.50") as c:
        assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 403
        assert (await c.get("/api/auth/status")).json()["is_local"] is False
    async with client(ctx) as c:
        r = await c.post("/api/auth/setup", json={"pin": "1234"})
        assert r.status_code == 200
        sc = r.headers["set-cookie"]
        assert "meshlens_session=" in sc and "HttpOnly" in sc
        assert "samesite=strict" in sc.lower() and "Max-Age=31536000" in sc
        assert "Secure" not in sc
        assert (await c.get("/api/auth/status")).json()["authenticated"] is True
        assert (await c.post("/api/auth/setup", json={"pin": "5678"})).status_code == 403
        assert (await c.post("/api/auth/logout")).status_code == 200
        assert (await c.get("/api/nodes")).status_code == 401


async def test_setup_invalid_pin(ctx):
    async with client(ctx) as c:
        assert (await c.post("/api/auth/setup", json={"pin": "12"})).status_code == 400


async def test_login_wrong_then_locked(ctx):
    ctx.auth.set_pin("1234")
    async with client(ctx) as c:
        for _ in range(5):
            assert (await c.post("/api/auth/login", json={"pin": "0000"})).status_code == 401
        r = await c.post("/api/auth/login", json={"pin": "1234"})
        assert r.status_code == 429
        assert int(r.headers["Retry-After"]) > 0


async def test_login_ok(ctx):
    ctx.auth.set_pin("1234")
    async with client(ctx) as c:
        r = await c.post("/api/auth/login", json={"pin": "1234"})
        assert r.status_code == 200
        assert (await c.get("/api/nodes")).status_code == 200


async def test_nodes_and_filters(ctx):
    async with logged(ctx) as c:
        nodes = (await c.get("/api/nodes")).json()
        assert len(nodes) == 4 and all("is_mine" not in n for n in nodes)
        assert {n["num"] for n in (await c.get("/api/nodes?country=IT")).json()} == {1, 2}
        assert {n["num"] for n in (await c.get("/api/nodes?country=none")).json()} == {4}
        assert {n["num"] for n in (await c.get("/api/nodes?country=DE,none")).json()} == {3, 4}
        assert {n["num"] for n in (await c.get("/api/nodes?max_age_h=1")).json()} == {1, 3, 4}


async def test_node_detail(ctx):
    async with logged(ctx) as c:
        r = await c.get("/api/nodes/!00000001")
        assert r.status_code == 200
        assert r.json()["num"] == 1 and r.json()["telemetry"] == []
        assert (await c.get("/api/nodes/!000000ff")).status_code == 404
        assert (await c.get("/api/nodes/zzz")).status_code == 404
        assert (await c.get("/api/nodes/!00000001/positions?hours=2")).json() == []


async def test_messages(ctx):
    async with logged(ctx) as c:
        msgs = (await c.get("/api/messages")).json()
        assert [m["key"] for m in msgs] == ["1:3", "1:2", "1:1"]
        assert [m["key"] for m in (await c.get("/api/messages?country=IT")).json()] == ["1:1"]
        assert [m["key"] for m in (await c.get("/api/messages?country=none")).json()] == ["1:3"]
        assert len((await c.get("/api/messages?limit=2")).json()) == 2
        assert (await c.get("/api/messages/history?country=IT")).json() == []


async def test_countries(ctx):
    async with logged(ctx) as c:
        data = {x["code"]: x for x in (await c.get("/api/countries")).json()}
        assert data["IT"]["nodes"] == 2 and data["IT"]["name"]
        assert data["DE"]["nodes"] == 1
        assert data["none"] == {"code": "none", "name": "Sconosciuta", "nodes": 1}


async def test_settings(ctx):
    async with logged(ctx) as c:
        s = (await c.get("/api/settings")).json()
        assert s["mqtt"]["password"] == "••••"
        r = await c.put("/api/settings", json={"saved_countries": ["XX1"]})
        assert r.status_code == 400 and "saved_countries" in r.json()["detail"]
        assert ctx.changed == []
        r = await c.put("/api/settings", json={"saved_countries": ["IT", "DE"],
                                               "mqtt": {"host": "h.example", "password": "••••"}})
        assert r.status_code == 200
        assert r.json()["saved_countries"] == ["IT", "DE"]
        assert r.json()["mqtt"]["password"] == "••••"
        assert len(ctx.changed) == 1
        assert ctx.changed[0]["mqtt"]["password"] == "large4cats"
        assert ctx.changed[0]["mqtt"]["host"] == "h.example"
        assert (await c.get("/api/status")).json()["connected"] is True


def test_ws_receives_bus(ctx):
    ctx.auth.set_pin("1234")
    token = ctx.auth.login("1234", "127.0.0.1")
    with TestClient(create_app(ctx)) as tc:
        tc.cookies.set("meshlens_session", token)
        with tc.websocket_connect("/ws") as ws:
            ctx.bus.publish({"type": "message", "message": {"text": "x"}})
            assert ws.receive_json() == {"type": "message", "message": {"text": "x"}}


async def test_bus_drops_oldest():
    bus = Bus(maxsize=3)
    q = bus.subscribe()
    for i in range(5):
        bus.publish({"i": i})
    assert [q.get_nowait()["i"] for _ in range(3)] == [2, 3, 4]
    bus.unsubscribe(q)
    bus.publish({"i": 9})
    assert q.empty()


async def test_static_spa(tmp_path):
    (tmp_path / "index.html").write_text("<html>SPA</html>")
    (tmp_path / "a.js").write_text("x=1")
    ctx = make_ctx(static_dir=tmp_path)
    async with client(ctx) as c:
        assert "SPA" in (await c.get("/")).text
        assert (await c.get("/a.js")).text == "x=1"
        assert "SPA" in (await c.get("/some/route")).text
        r = await c.get("/api/unknown")
        assert r.status_code == 404 and "SPA" not in r.text


async def test_no_static_dir(tmp_path):
    ctx = make_ctx(static_dir=tmp_path / "missing")
    async with client(ctx) as c:
        assert (await c.get("/")).status_code == 404
