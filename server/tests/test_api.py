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
from meshlens.events import TelemetryData
from meshlens.geo import CountryLocator
from meshlens.live import LiveState
from meshlens.settings import save_settings
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
                             base_url="http://127.0.0.1")


@contextlib.asynccontextmanager
async def logged_existing(ctx, pin="1234"):
    async with client(ctx) as c:
        r = await c.post("/api/auth/login", json={"pin": pin})
        assert r.status_code == 200
        yield c


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
        assert r.json() == {"pin_set": False, "authenticated": False, "is_local": True,
                            "pin_short": None, "pin_min": 4}


def test_ws_rejects_without_cookie(ctx):
    with TestClient(create_app(ctx), base_url="http://127.0.0.1") as tc:
        with pytest.raises(WebSocketDisconnect) as e:
            with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
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


async def test_login_lock_returns_429_with_retry_after(ctx):
    ctx.auth.set_pin("1234")
    async with client(ctx, host="10.0.0.5") as c:
        for _ in range(5):
            assert (await c.post("/api/auth/login", json={"pin": "0000"})).status_code == 401
        r = await c.post("/api/auth/login", json={"pin": "1234"})
        assert r.status_code == 429
        assert r.headers["Retry-After"] == "60"
    # dal PC si entra ancora
    async with client(ctx) as c:
        assert (await c.post("/api/auth/login", json={"pin": "1234"})).status_code == 200


async def test_setup_requires_6_digits_with_lan(ctx):
    save_settings(ctx.conn, {"lan_access": True})
    async with client(ctx) as c:
        r = await c.post("/api/auth/setup", json={"pin": "1234"})
        assert r.status_code == 400
        assert not ctx.auth.pin_is_set()
        assert (await c.post("/api/auth/setup", json={"pin": "123456"})).status_code == 200
        st = (await c.get("/api/auth/status")).json()
        assert st["authenticated"] is True and st["pin_short"] is False
        assert st["pin_min"] == 6


async def test_short_pin_keeps_working_with_lan(ctx):
    async with logged(ctx) as c:
        assert (await c.get("/api/auth/status")).json()["pin_short"] is False
        save_settings(ctx.conn, {"lan_access": True})
        assert (await c.get("/api/auth/status")).json()["pin_short"] is True
    async with client(ctx, host="192.168.1.20") as c:
        assert (await c.post("/api/auth/login", json={"pin": "1234"})).status_code == 200
        assert (await c.get("/api/auth/status")).json()["pin_short"] is True


async def test_pin_short_null_when_length_unknown(ctx):
    ctx.auth.set_pin("1234")
    ctx.conn.execute("DELETE FROM auth WHERE key='pin_len'")
    save_settings(ctx.conn, {"lan_access": True})
    async with client(ctx) as c:
        assert (await c.get("/api/auth/status")).json()["pin_short"] is None


async def test_change_pin_requires_current_and_revokes_others(ctx):
    ctx.auth.set_pin("1234")
    async with client(ctx, host="192.168.1.20") as other:
        assert (await other.post("/api/auth/login", json={"pin": "1234"})).status_code == 200
        async with logged_existing(ctx) as c:
            r = await c.post("/api/auth/pin", json={"current_pin": "0000", "new_pin": "5678"})
            assert r.status_code == 403
            r = await c.post("/api/auth/pin", json={"current_pin": "1234", "new_pin": "56"})
            assert r.status_code == 400
            r = await c.post("/api/auth/pin", json={"current_pin": "1234", "new_pin": "5678"})
            assert r.status_code == 200 and r.json() == {"ok": True}
            assert (await c.get("/api/nodes")).status_code == 200
        assert (await other.get("/api/nodes")).status_code == 401
    async with client(ctx) as c:
        assert (await c.post("/api/auth/login", json={"pin": "5678"})).status_code == 200


async def test_change_pin_needs_6_digits_with_lan(ctx):
    async with logged(ctx) as c:
        save_settings(ctx.conn, {"lan_access": True})
        r = await c.post("/api/auth/pin", json={"current_pin": "1234", "new_pin": "5678"})
        assert r.status_code == 400
        r = await c.post("/api/auth/pin", json={"current_pin": "1234", "new_pin": "567890"})
        assert r.status_code == 200


async def test_change_pin_requires_auth(ctx):
    ctx.auth.set_pin("1234")
    async with client(ctx) as c:
        r = await c.post("/api/auth/pin", json={"current_pin": "1234", "new_pin": "5678"})
        assert r.status_code == 401


async def test_sessions_api(ctx):
    ctx.auth.set_pin("1234")
    async with client(ctx, host="192.168.1.20") as other:
        await other.post("/api/auth/login", json={"pin": "1234"},
                         headers={"user-agent": "Telefono"})
        async with client(ctx, host="192.168.1.21") as third:
            await third.post("/api/auth/login", json={"pin": "1234"})
            async with logged_existing(ctx) as c:
                rows = (await c.get("/api/auth/sessions")).json()
                assert len(rows) == 3
                me = [r for r in rows if r["current"]]
                assert len(me) == 1 and me[0]["ip"] == "127.0.0.1"
                assert set(me[0]) == {"id", "created", "last_seen", "user_agent", "ip", "current"}
                phone = next(r for r in rows if r["user_agent"] == "Telefono")
                assert (await c.delete(f"/api/auth/sessions/{phone['id']}")).status_code == 200
                assert (await c.delete(f"/api/auth/sessions/{phone['id']}")).status_code == 404
                assert (await c.delete("/api/auth/sessions/zz")).status_code == 404
                assert (await other.get("/api/nodes")).status_code == 401
                r = await c.post("/api/auth/sessions/revoke-others")
                assert r.json() == {"ok": True, "revoked": 1}
                assert len((await c.get("/api/auth/sessions")).json()) == 1
            assert (await third.get("/api/nodes")).status_code == 401
    async with client(ctx) as c:
        assert (await c.get("/api/auth/sessions")).status_code == 401


async def test_login_ok(ctx):
    ctx.auth.set_pin("1234")
    async with client(ctx) as c:
        r = await c.post("/api/auth/login", json={"pin": "1234"})
        assert r.status_code == 200
        assert (await c.get("/api/nodes")).status_code == 200


async def test_nodes_and_filters(ctx):
    async with logged(ctx) as c:
        nodes = (await c.get("/api/nodes")).json()
        assert len(nodes) == 4 and nodes[0]["is_mine"] is True
        assert {n["num"] for n in (await c.get("/api/nodes?country=IT")).json()} == {1, 2}
        assert {n["num"] for n in (await c.get("/api/nodes?country=none")).json()} == {4}
        assert {n["num"] for n in (await c.get("/api/nodes?country=DE,none")).json()} == {3, 4}
        assert {n["num"] for n in (await c.get("/api/nodes?max_age_h=1")).json()} == {1, 3, 4}


async def test_node_json_exposes_is_mine(ctx):
    async with logged(ctx) as c:
        assert (await c.get("/api/nodes/!00000001")).json()["is_mine"] is True


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
    with TestClient(create_app(ctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token)
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
            ctx.bus.publish({"type": "message", "message": {"text": "x"}})
            assert ws.receive_json() == {"type": "message", "message": {"text": "x"}}


def _ws_closed_code(ws) -> int:
    with pytest.raises(WebSocketDisconnect) as e:
        ws.receive_json()
    return e.value.code


def test_ws_closed_when_session_revoked(ctx):
    ctx.auth.set_pin("1234")
    token_a = ctx.auth.login("1234", "127.0.0.1")
    token_b = ctx.auth.login("1234", "192.168.1.20", "Telefono")
    with TestClient(create_app(ctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token_b)
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
            tc.cookies.set("meshlens_session", token_a)
            rows = tc.get("/api/auth/sessions").json()
            b = next(r for r in rows if r["user_agent"] == "Telefono")
            assert tc.delete(f"/api/auth/sessions/{b['id']}").status_code == 200
            assert _ws_closed_code(ws) == 4401


def test_ws_closed_on_revoke_others_and_logout(ctx):
    ctx.auth.set_pin("1234")
    token_a = ctx.auth.login("1234", "127.0.0.1")
    token_b = ctx.auth.login("1234", "192.168.1.20")
    with TestClient(create_app(ctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token_b)
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws_b:
            tc.cookies.set("meshlens_session", token_a)
            with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws_a:
                assert tc.post("/api/auth/sessions/revoke-others").json()["revoked"] == 1
                assert _ws_closed_code(ws_b) == 4401
                # il proprio socket resta aperto
                ctx.bus.publish({"type": "x"})
                assert ws_a.receive_json() == {"type": "x"}
                assert tc.post("/api/auth/logout").status_code == 200
                assert _ws_closed_code(ws_a) == 4401
    assert ctx.auth._watchers == {}


def test_ws_closed_on_pin_change(ctx):
    ctx.auth.set_pin("1234")
    token_a = ctx.auth.login("1234", "127.0.0.1")
    token_b = ctx.auth.login("1234", "192.168.1.20")
    with TestClient(create_app(ctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token_b)
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
            tc.cookies.set("meshlens_session", token_a)
            r = tc.post("/api/auth/pin", json={"current_pin": "1234", "new_pin": "5678"})
            assert r.status_code == 200
            assert _ws_closed_code(ws) == 4401


def test_ws_recheck_closes_expired_session(ctx, monkeypatch):
    import meshlens.api as api_mod
    monkeypatch.setattr(api_mod, "WS_RECHECK_S", 0.05)
    ctx.auth.set_pin("1234")
    token = ctx.auth.login("1234", "127.0.0.1")
    with TestClient(create_app(ctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token)
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
            ctx.auth.clock = lambda: time.time() + 31 * 86400  # 31 giorni dopo
            assert _ws_closed_code(ws) == 4401


async def test_change_pin_failures_count_on_request_ip(ctx):
    ctx.auth.set_pin("1234")
    token = ctx.auth.login("1234", "127.0.0.1")  # sessione aperta dal PC
    async with client(ctx, host="192.168.1.30") as c:
        c.cookies.set("meshlens_session", token)
        for _ in range(5):
            r = await c.post("/api/auth/pin", json={"current_pin": "0000", "new_pin": "5678"})
            assert r.status_code == 403
        r = await c.post("/api/auth/pin", json={"current_pin": "1234", "new_pin": "5678"})
        assert r.status_code == 429
    # il PC non è bloccato
    async with client(ctx) as c:
        assert (await c.post("/api/auth/login", json={"pin": "1234"})).status_code == 200


async def test_setup_hashes_off_loop(ctx, monkeypatch):
    import meshlens.auth as auth_mod
    calls = []
    real = auth_mod.asyncio.to_thread

    async def spy(fn, *args, **kwargs):
        calls.append(getattr(fn, "__name__", repr(fn)))
        return await real(fn, *args, **kwargs)

    monkeypatch.setattr(auth_mod.asyncio, "to_thread", spy)
    async with client(ctx) as c:
        assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
    assert calls == ["hash", "_verify"]


async def test_bus_overflow_sends_resync():
    bus = Bus(maxsize=3)
    q = bus.subscribe()
    for i in range(5):
        bus.publish({"i": i})
    assert [q.get_nowait() for _ in range(3)] == [{"type": "resync"}, {"i": 3}, {"i": 4}]
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
        for u in ("/map-assets/nope.json", "/tiles/x/y.mvt"):
            r = await c.get(u)
            assert r.status_code == 404 and "SPA" not in r.text


async def test_no_static_dir(tmp_path):
    ctx = make_ctx(static_dir=tmp_path / "missing")
    async with client(ctx) as c:
        r = await c.get("/")
        assert r.status_code == 200 and "Interfaccia non compilata" in r.text
        assert "npm run build" in r.text
        assert (await c.get("/api/auth/status")).status_code == 200  # API invariata
        assert (await c.get("/api/unknown")).status_code == 404


async def test_auth_requires_json_content_type(ctx):
    async with client(ctx) as c:
        r = await c.post("/api/auth/setup", content="pin=1234",
                         headers={"content-type": "application/x-www-form-urlencoded"})
        assert r.status_code == 415
        r = await c.post("/api/auth/setup", content='{"pin":"1234"}',
                         headers={"content-type": "text/plain"})
        assert r.status_code == 415
        assert not ctx.auth.pin_is_set()
        ctx.auth.set_pin("1234")
        r = await c.post("/api/auth/login", content="pin=1234",
                         headers={"content-type": "application/x-www-form-urlencoded"})
        assert r.status_code == 415


def test_ws_survives_client_frame(ctx):
    ctx.auth.set_pin("1234")
    token = ctx.auth.login("1234", "127.0.0.1")
    with TestClient(create_app(ctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token)
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
            ws.send_text("ping")
            ctx.bus.publish({"type": "message", "message": {"text": "y"}})
            assert ws.receive_json()["message"]["text"] == "y"
            ws.send_text("again")
            ctx.bus.publish({"type": "message", "message": {"text": "z"}})
            assert ws.receive_json()["message"]["text"] == "z"


async def test_limit_clamped(ctx):
    async with logged(ctx) as c:
        for path in ("/api/messages", "/api/messages/history"):
            assert (await c.get(f"{path}?limit=0")).status_code == 422
            assert (await c.get(f"{path}?limit=1001")).status_code == 422
            assert (await c.get(f"{path}?limit=1000")).status_code == 200


async def test_history_shape(ctx):
    ctx.store.upsert_node({"num": 0xa1b2c3d4, "long_name": "Zed"})
    msg = {"key": "1:9", "from": "!a1b2c3d4", "to": "!ffffffff", "channel": "LongFast",
           "text": "ciao", "time": 1763660123.0, "country": "IT", "source": "mqtt"}
    ctx.store.add_message(msg)
    ctx.store.commit()
    async with logged(ctx) as c:
        rows = (await c.get("/api/messages/history?country=IT")).json()
        assert rows == [{**msg, "from_name": "Zed", "direction": "in", "radio_id": None,
                         "channel_index": None, "packet_id": None, "status": None,
                         "broker": None, "reply_id": None, "emoji": False, "pki": False,
                         "error": None}]
        assert set(rows[0]) == {"key", "from", "from_name", "to", "channel", "text",
                                "time", "country", "source", "direction", "radio_id",
                                "channel_index", "packet_id", "status", "broker", "reply_id",
                                "emoji", "pki", "error"}
        assert (await c.get("/api/messages/history?country=IT&before=1")).json() == []


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8686", "localhost.evil.example"])
async def test_host_header_rejected(ctx, host):
    async with client(ctx) as c:
        r = await c.get("/api/auth/status", headers={"host": host})
        assert r.status_code == 400 and r.json() == {"detail": "Host non consentito"}


@pytest.mark.parametrize("host", ["127.0.0.1:8686", "localhost", "localhost:8686", "[::1]:8686",
                                  "192.168.1.5:8686"])
async def test_host_header_allowed(ctx, host):
    async with client(ctx) as c:
        assert (await c.get("/api/auth/status", headers={"host": host})).status_code == 200


def test_ws_rejects_foreign_origin(ctx):
    ctx.auth.set_pin("1234")
    token = ctx.auth.login("1234", "127.0.0.1")
    with TestClient(create_app(ctx), base_url="http://127.0.0.1:8686") as tc:
        tc.cookies.set("meshlens_session", token)
        with pytest.raises(WebSocketDisconnect) as e:
            with tc.websocket_connect("/ws", headers={"host": "127.0.0.1:8686", "origin": "http://evil.example"}) as ws:
                ws.receive_text()
        assert e.value.code == 4403
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1:8686", "origin": "http://127.0.0.1:8686"}) as ws:
            ctx.bus.publish({"type": "x"})
            assert ws.receive_json() == {"type": "x"}


async def test_put_mine_and_get_alerts(ctx):
    ctx.live.nodes[3]["battery"] = 10
    async with logged(ctx) as c:
        r = await c.put("/api/nodes/!00000003/mine", json={"mine": True})
        assert r.status_code == 200 and r.json()["is_mine"] is True
        alerts = (await c.get("/api/alerts")).json()
        assert [(a["key"], a["value"]) for a in alerts] == [("battery:!00000003", 10)]
        assert ctx.store.load_nodes()  # nodo persistito anche se non c'era nel database
        assert (await c.put("/api/nodes/!000000ff/mine", json={"mine": True})).status_code == 404


async def test_put_favorite_no_alerts_and_persists(ctx):
    ctx.live.nodes[3]["battery"] = 10
    async with logged(ctx) as c:
        r = await c.put("/api/nodes/!00000003/favorite", json={"favorite": True})
        assert r.status_code == 200
        assert r.json()["is_favorite"] is True and not r.json().get("is_mine")
        assert (await c.get("/api/alerts")).json() == []  # nessun avviso per i preferiti
        assert [n for n in ctx.store.load_nodes() if n["num"] == 3][0]["is_favorite"] is True
        assert (await c.put("/api/nodes/!000000ff/favorite",
                            json={"favorite": True})).status_code == 404
        r = await c.put("/api/nodes/!00000003/favorite", json={"favorite": False})
        assert r.json()["is_favorite"] is False


async def test_alerts_publish_only_on_change(ctx):
    ctx.live.nodes[1]["battery"] = 10
    q = ctx.bus.subscribe()
    ctx.alerts()
    ctx.alerts()
    assert q.qsize() == 1 and q.get_nowait()["type"] == "alerts"
    ctx.live.nodes[1]["battery"] = 9
    ctx.alerts()
    assert q.qsize() == 1


async def test_alerts_include_chutil_for_mine(ctx):
    now = time.time()
    ctx.store.add_telemetry(1, now - 300, TelemetryData(channel_utilization=30.0))
    ctx.store.add_telemetry(1, now - 600, TelemetryData(channel_utilization=34.0))
    async with logged(ctx) as c:
        alerts = (await c.get("/api/alerts")).json()
        assert [(a["kind"], a["value"]) for a in alerts if a["kind"] == "chutil_high"]             == [("chutil_high", 32.0)]


async def test_telemetry_route(ctx):
    now = time.time()
    ctx.store.add_telemetry(1, now - 60, TelemetryData(50, 3.9, 1.0, 0.5, 5))
    async with logged(ctx) as c:
        r = await c.get("/api/nodes/!00000001/telemetry")
        assert r.json() == [{"time": r.json()[0]["time"], "battery": 50, "voltage": 3.9,
                             "channel_util": 1.0, "air_util_tx": 0.5}]
        assert (await c.get("/api/nodes/!000000ff/telemetry")).status_code == 404


async def test_positions_route_max_points(ctx):
    now = time.time()
    for i in range(50):
        ctx.store.add_position(1, now - 3000 + i, 45.0 + i / 1000, 9.0, 32, "rf")
    async with logged(ctx) as c:
        r = await c.get("/api/nodes/!00000001/positions?hours=24&max_points=10")
        body = r.json()
        assert r.status_code == 200 and 2 <= len(body) <= 11
        assert set(body[0]) == {"time", "lat", "lon", "precision_bits", "source"}
        assert body[-1]["lat"] == pytest.approx(45.049)
        assert len((await c.get("/api/nodes/!00000001/positions")).json()) == 50


async def test_metrics_and_snr_routes(ctx):
    now = time.time()
    ctx.store.add_metrics(1, now - 60, "environment", {"temperature": 21.5})
    async with logged(ctx) as c:
        body = (await c.get("/api/nodes/!00000001/metrics?hours=24")).json()
        assert body["latest"]["environment.temperature"]["value"] == 21.5
        assert [v for _, v in body["series"]["environment.temperature"]] == [21.5]
        assert (await c.get("/api/nodes/!00000001/snr")).json() == []
        ctx.store.upsert_node_hourly([(int(now // 3600) * 3600, 1, "rf", 2, -6.0, 2, -2.0)])
        snr = (await c.get("/api/nodes/!00000001/snr")).json()
        assert snr[0]["snr_avg"] == -3.0 and snr[0]["packets"] == 2


async def test_data_routes_use_thread_with_db_path(tmp_path, monkeypatch):
    import asyncio
    from meshlens.app import build
    app, rt = build(tmp_path, static_dir=None)
    calls = []
    real = asyncio.to_thread

    async def spy(fn, *a, **kw):
        calls.append(fn)
        return await real(fn, *a, **kw)
    monkeypatch.setattr(asyncio, "to_thread", spy)
    try:
        rt.conn.execute("INSERT INTO metrics(node_num, time, variant, metric, value) "
                        "VALUES(5, ?, 'environment', 'temperature', 19.0)", (time.time(),))
        rt.conn.commit()
        async with client_for_app(app) as c:
            assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
            calls.clear()
            r = await c.get("/api/nodes/!00000005/metrics")
            assert r.json()["latest"]["environment.temperature"]["value"] == 19.0
            assert calls
    finally:
        rt.conn.close()


async def test_stats_route_cached(tmp_path, monkeypatch):
    from meshlens import queries
    from meshlens.app import build
    app, rt = build(tmp_path, static_dir=None)
    calls = []
    real = queries.network_stats

    def spy(conn, now, hours):
        calls.append(hours)
        return real(conn, now, hours)
    monkeypatch.setattr(queries, "network_stats", spy)
    try:
        async with client_for_app(app) as c:
            assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
            a = await c.get("/api/stats?hours=24")
            b = await c.get("/api/stats?hours=24")
            assert a.status_code == 200 and a.json() == b.json() and calls == [24]
            await c.get("/api/stats?hours=48")
            assert calls == [24, 48]
    finally:
        rt.conn.close()


async def test_stats_hours_bounds(ctx):
    async with logged(ctx) as c:
        assert (await c.get("/api/stats?hours=0")).status_code == 422
        assert (await c.get("/api/stats?hours=2161")).status_code == 422
        assert (await c.get("/api/stats?hours=2160")).status_code == 200


async def test_packets_routes(ctx):
    ctx.conn.executemany(
        "INSERT INTO packets(time, from_num, kind, source, status) VALUES(?,?,?,?,?)",
        [(1000.0 + i, 1, "text", "rf", "ok") for i in range(300)])
    ctx.conn.commit()
    async with logged(ctx) as c:
        body = (await c.get("/api/packets?limit=500")).json()
        assert len(body["items"]) == 200 and body["next_before_id"] == body["items"][-1]["id"]
        assert body["items"][0]["from"] == "!00000001"
        assert len((await c.get("/api/packets")).json()["items"]) == 100
        r = await c.get("/api/packets?node=!00000001&kind=text&source=rf")
        assert len(r.json()["items"]) == 100
        assert (await c.get("/api/packets?source=bogus")).status_code == 422
        assert (await c.get("/api/packets?node=zz")).status_code == 422
        d = await c.get("/api/packets/5")
        assert d.status_code == 200 and d.json()["raw_hex"] == "" and d.json()["receptions"] == []
        assert (await c.get("/api/packets/99999")).status_code == 404
        assert (await c.get("/api/packets/99999999999999999999")).status_code == 422
        assert (await c.get("/api/packets/-1")).status_code == 422
        live = (await c.get("/api/packets?after_id=290&limit=5")).json()
        assert [p["id"] for p in live["items"]] == [291, 292, 293, 294, 295]


@pytest.mark.parametrize("path", ["telemetry", "positions", "metrics", "snr"])
async def test_data_routes_reject_zero_hours(ctx, path):
    async with logged(ctx) as c:
        assert (await c.get(f"/api/nodes/!00000001/{path}?hours=0")).status_code == 422


async def test_links_route(ctx):
    ctx.store.upsert_link(1, 2, "rf_direct", 4.5, time.time())
    async with logged(ctx) as c:
        r = await c.get("/api/links")
        assert r.json()[0]["from_id"] == "!00000001" and r.json()[0]["snr"] == 4.5
        ctx.store.upsert_link(2, 3, "rf_direct", None, time.time() - 48 * 3600)
        assert len((await c.get("/api/links")).json()) == 1
        assert len((await c.get("/api/links?hours=72")).json()) == 2


async def test_put_settings_republishes_alerts(ctx):
    ctx.live.nodes[3]["battery"] = 30
    q = ctx.bus.subscribe()
    ctx.live.nodes[3]["is_mine"] = True
    ctx.alerts()
    while not q.empty():
        q.get_nowait()
    async with logged(ctx) as c:
        r = await c.put("/api/settings", json={"battery_alert_pct": 50})
        assert r.status_code == 200
    assert q.qsize() == 1 and q.get_nowait()["type"] == "alerts"


async def test_mqtt_channels_endpoint(ctx):
    ctx.mqtt_channel_counts = lambda: {"LongFast": 5, "MediumFast": 9, "Zed": 1}
    async with client(ctx) as c:
        assert (await c.get("/api/mqtt/channels")).status_code == 401
    async with logged(ctx) as c:
        allon = (await c.get("/api/mqtt/channels")).json()
        assert [x["enabled"] for x in allon] == [True, True, True]  # lista vuota = tutti
        r = await c.put("/api/settings", json={"mqtt_channels": ["LongFast", "Gone"]})
        assert r.status_code == 200 and r.json()["mqtt_channels"] == ["LongFast", "Gone"]
        got = (await c.get("/api/mqtt/channels")).json()
        assert got == [
            {"name": "MediumFast", "count_1h": 9, "enabled": False, "custom": False, "brokers": []},
            {"name": "LongFast", "count_1h": 5, "enabled": True, "custom": False, "brokers": []},
            {"name": "Zed", "count_1h": 1, "enabled": False, "custom": False, "brokers": []}]


_B1 = {"id": "b1", "name": "Broker uno", "enabled": True, "host": "broker.esempio.it",
       "port": 1883, "topics": ["msh/EU_868/IT/#"],
       "channels": [{"name": "Squadra", "psk": "ESIzRFVmd4iZqrvM3e7/ABEiM0RVZneImaq7zN3u/wA="}]}


def _with_b1(conn):
    from meshlens.settings import load_settings
    default = load_settings(conn)["mqtt_brokers"][0]
    return save_settings(conn, {"mqtt_brokers": [default, dict(_B1)]})


async def test_send_route_with_broker_and_confirmation_saved(ctx):
    from meshlens.mqtt_publish import MqttSender
    from meshlens.settings import load_settings

    class Conn:
        def __init__(self):
            self.published = []

        def publish(self, topic, payload):
            self.published.append(topic)
            return True

    conns = {"default": Conn(), "b1": Conn()}
    save_settings(ctx.conn, {"mqtt_node_id": "!a1b2c3d4"})
    _with_b1(ctx.conn)
    recorded = []
    ctx.mqtt_sender = MqttSender(
        conns.get, lambda: load_settings(ctx.conn), lambda: [], lambda: 1000.0,
        lambda **kw: recorded.append(kw) or {"key": "k", "text": kw["text"],
                                             "broker": kw["broker"]})
    async with logged(ctx) as c:
        body = {"text": "ciao", "channel": "Squadra", "broker": "b1"}
        r = await c.post("/api/mqtt/send", json=body)
        assert r.status_code == 409 and "broker.esempio.it" in r.json()["detail"]
        r = await c.post("/api/mqtt/send", json={**body, "confirm_public": True})
        assert r.status_code == 202 and r.json()["message"]["broker"] == "b1"
        saved = load_settings(ctx.conn)
        assert saved["mqtt_send_confirmed_brokers"] == ["b1"]
        assert saved["mqtt_send_confirmed"] is False  # vale solo per il predefinito
        assert conns["b1"].published == ["msh/EU_868/IT/2/e/Squadra/!a1b2c3d4"]
        r = await c.post("/api/mqtt/send", json={**body, "broker": "x" * 25})
        assert r.status_code == 422
        r = await c.post("/api/mqtt/send", json={**body, "broker": "nessuno"})
        assert r.status_code == 400 and r.json()["code"] == "unknown_broker"
        # sul predefinito la conferma imposta anche mqtt_send_confirmed
        r = await c.post("/api/mqtt/send", json={"text": "x", "broker": "default",
                                                 "confirm_public": True})
        assert r.status_code == 202
        saved = load_settings(ctx.conn)
        assert saved["mqtt_send_confirmed_brokers"] == ["b1", "default"]
        assert saved["mqtt_send_confirmed"] is True
    assert [kw["broker"] for kw in recorded] == ["b1", "default"]


async def test_channels_route_includes_custom_with_zero_count(ctx):
    _with_b1(ctx.conn)
    seen = {"default": {"LongFast": 4, "Squadra": 2}, "b1": {"LongFast": 3}}

    def counts(broker=None):
        if broker is None:
            return {"LongFast": 7, "Squadra": 2}
        return seen.get(broker, {})

    ctx.mqtt_channel_counts = counts
    ctx.mqtt_channel_brokers = lambda: {"LongFast": ["default", "b1"], "Squadra": ["default"]}
    async with logged(ctx) as c:
        got = (await c.get("/api/mqtt/channels?broker=b1")).json()
        assert got == [
            {"name": "LongFast", "count_1h": 3, "enabled": True, "custom": False,
             "brokers": ["default", "b1"]},
            {"name": "Squadra", "count_1h": 0, "enabled": True, "custom": True,
             "brokers": ["default", "b1"]}]
        allb = (await c.get("/api/mqtt/channels")).json()
        assert allb == [
            {"name": "LongFast", "count_1h": 7, "enabled": True, "custom": False,
             "brokers": ["default", "b1"]},
            {"name": "Squadra", "count_1h": 2, "enabled": True, "custom": True,
             "brokers": ["default", "b1"]}]
        dflt = (await c.get("/api/mqtt/channels?broker=default")).json()
        assert [(r["name"], r["count_1h"], r["custom"]) for r in dflt] == [
            ("LongFast", 4, False), ("Squadra", 2, False)]
        assert (await c.get("/api/mqtt/channels?broker=nessuno")).status_code == 404


async def test_db_endpoint_and_compact_requires_confirm(tmp_path):
    from meshlens.app import build
    app, rt = build(tmp_path, static_dir=None)
    await rt.check_integrity()
    try:
        async with client_for_app(app) as c:
            assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
            r = await c.get("/api/db")
            assert r.status_code == 200
            body = r.json()
            assert "messages" in body["rows"] and body["integrity"] == "ok"
            assert body["last_purge"] is None
            assert (await c.post("/api/db/compact", json={})).status_code == 400
            r = await c.post("/api/db/compact", json={"confirm": True})
            assert r.status_code == 200 and "before_bytes" in r.json()
    finally:
        rt.conn.close()


def client_for_app(app):
    return httpx.AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 1234)),
                             base_url="http://127.0.0.1")


def client_from(ctx, host):
    return httpx.AsyncClient(transport=ASGITransport(app=create_app(ctx), client=(host, 1234)),
                             base_url="http://127.0.0.1")


async def _setup_secrets(c):
    r = await c.put("/api/settings", json={
        "update_token": "ghp_SECRETTOKEN",
        "mqtt": {"password": "hunter2pw", "extra_keys": ["AQ=="]}})
    assert r.status_code == 200


async def test_settings_export_masks_secrets_by_default(ctx):
    async with logged(ctx) as c:
        await _setup_secrets(c)
        r = await c.get("/api/settings/export")
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
        assert ".json" in r.headers["content-disposition"]
        doc = r.json()
        assert doc["app"] == "meshlens" and doc["format"] == 1 and doc["settings"]
        for secret in ("hunter2pw", "ghp_SECRETTOKEN", "AQ=="):
            assert secret not in r.text
        assert doc["settings"]["update_token"] == "••••"
        assert doc["settings"]["mqtt"]["password"] == "••••"
        r = await c.get("/api/settings/export?secrets=1")
        assert r.json()["settings"]["mqtt"]["password"] == "hunter2pw"


async def test_settings_export_with_secrets_only_local(ctx):
    async with logged(ctx) as c:
        await _setup_secrets(c)
        cookie = c.cookies.get("meshlens_session")
    async with client_from(ctx, "192.168.1.5") as lan:
        lan.cookies.set("meshlens_session", cookie)
        assert (await lan.get("/api/settings/export?secrets=1")).status_code == 403
        r = await lan.get("/api/settings/export")
        assert r.status_code == 200 and "hunter2pw" not in r.text


async def test_settings_import_skips_masked(ctx):
    async with logged(ctx) as c:
        await _setup_secrets(c)
        doc = (await c.get("/api/settings/export")).json()
        doc["settings"]["retention_messages_days"] = 30
        doc["settings"]["mqtt_send_confirmed"] = True
        r = await c.post("/api/settings/import", json=doc)
        assert r.status_code == 200, r.text
        body = r.json()
        # i segreti mascherati dei broker si risolvono con quelli salvati (stesso id)
        assert set(body["skipped"]) == {"update_token", "mqtt_send_confirmed",
                                        "mqtt_send_confirmed_brokers"}
        assert "hunter2pw" not in r.text and "AQ==" not in r.text
        assert body["settings"]["retention_messages_days"] == 30
        from meshlens.settings import load_settings
        s = load_settings(ctx.conn)
        assert s["mqtt"]["password"] == "hunter2pw" and s["update_token"] == "ghp_SECRETTOKEN"
        assert s["mqtt"]["extra_keys"] == ["AQ=="] and s["mqtt_send_confirmed"] is False
        assert ctx.changed  # on_settings_changed chiamata
        # chiave sconosciuta: 400 e nulla salvato
        bad = {"format": 1, "settings": {"retention_messages_days": 11, "nope": 1}}
        assert (await c.post("/api/settings/import", json=bad)).status_code == 400
        assert load_settings(ctx.conn)["retention_messages_days"] == 30
        assert (await c.post("/api/settings/import",
                             json={"format": 2, "settings": {}})).status_code == 400


async def test_backup_routes(tmp_path):
    from meshlens.app import build
    app, rt = build(tmp_path, static_dir=None)
    try:
        async with client_for_app(app) as c:
            assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
            assert (await c.get("/api/backups")).json() == []
            r = await c.post("/api/backups")
            assert r.status_code == 200 and r.json()["reason"] == "manuale"
            name = r.json()["name"]
            lst = (await c.get("/api/backups")).json()
            assert [b["name"] for b in lst] == [name] and lst[0]["size_bytes"] > 0
            assert (await c.post(f"/api/backups/{name}/restore", json={})).status_code == 400
            assert (await c.post("/api/backups/x.db/restore",
                                 json={"confirm": True})).status_code == 404
            assert (await c.post("/api/backups/meshlens-20200101-000000-manuale.db/restore",
                                 json={"confirm": True})).status_code == 404
            r = await c.post(f"/api/backups/{name}/restore", json={"confirm": True})
            assert r.status_code == 200
            assert r.json() == {"ok": True, "restart_required": True}
            assert (tmp_path / "restore.json").exists()
    finally:
        rt.conn.close()


async def test_extra_keys_never_returned_and_mask_preserved(ctx):
    from meshlens.settings import load_settings
    k1, k2, k3 = "AQ==", "Ag==", "Aw=="
    async with logged(ctx) as c:
        r = await c.put("/api/settings", json={"mqtt": {"extra_keys": [k1, k2]}})
        assert r.status_code == 200 and r.json()["mqtt"]["extra_keys"] == ["••••", "••••"]
        assert k1 not in r.text and k2 not in r.text
        g = await c.get("/api/settings")
        assert g.json()["mqtt"]["extra_keys"] == ["••••", "••••"] and k1 not in g.text
        # invariate (maschere posizionali)
        r = await c.put("/api/settings", json={"mqtt": {"extra_keys": ["••••", "••••"]}})
        assert load_settings(ctx.conn)["mqtt"]["extra_keys"] == [k1, k2]
        # aggiunta di una nuova chiave
        r = await c.put("/api/settings", json={"mqtt": {"extra_keys": ["••••#0", "••••#1", k3]}})
        assert r.status_code == 200 and r.json()["mqtt"]["extra_keys"] == ["••••"] * 3
        assert load_settings(ctx.conn)["mqtt"]["extra_keys"] == [k1, k2, k3]
        # rimozione della prima: la seconda resta riconoscibile
        r = await c.put("/api/settings", json={"mqtt": {"extra_keys": ["••••#1", "••••#2"]}})
        assert load_settings(ctx.conn)["mqtt"]["extra_keys"] == [k2, k3]
        # riferimento fuori intervallo: 400, nulla cambia
        r = await c.put("/api/settings", json={"mqtt": {"extra_keys": ["••••#9"]}})
        assert r.status_code == 400
        assert load_settings(ctx.conn)["mqtt"]["extra_keys"] == [k2, k3]


async def test_backup_restore_refuses_corrupt(tmp_path):
    from meshlens.app import build
    app, rt = build(tmp_path, static_dir=None)
    try:
        async with client_for_app(app) as c:
            assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
            (tmp_path / "backups").mkdir(exist_ok=True)
            (tmp_path / "backups" / "meshlens-20240101-000000-manuale.db").write_bytes(b"")
            r = await c.post("/api/backups/meshlens-20240101-000000-manuale.db/restore",
                             json={"confirm": True})
            assert r.status_code == 409 and "rifiutato" in r.json()["detail"]
            assert not (tmp_path / "restore.json").exists()
    finally:
        rt.conn.close()


async def test_mine_and_favorite_revive_cap_evicted_node(ctx):
    ctx.store.upsert_node({"id": "!000000aa", "num": 0xaa, "long_name": "Evicted"})
    ctx.store.commit()
    assert 0xaa not in ctx.live.nodes
    async with logged(ctx) as c:
        r = await c.put("/api/nodes/!000000aa/mine", json={"mine": True})
        assert r.status_code == 200 and r.json()["long_name"] == "Evicted"
        assert ctx.live.nodes[0xaa]["is_mine"] is True
        del ctx.live.nodes[0xaa]
        r = await c.put("/api/nodes/!000000aa/favorite", json={"favorite": True})
        assert r.status_code == 200 and r.json()["long_name"] == "Evicted"
        assert ctx.store.get_node(0xaa)["is_mine"]


async def test_cookie_secure_on_https_from_lan(ctx):
    ctx.auth.set_pin("1234")
    save_settings(ctx.conn, {"lan_access": True})
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(ctx),
                                                         client=("192.168.1.20", 1234)),
                                 base_url="https://192.168.1.10") as c:
        r = await c.post("/api/auth/login", json={"pin": "1234"})
        assert r.status_code == 200
        sc = r.headers["set-cookie"]
        assert sc.startswith("meshlens_session_s=")
        assert "Secure" in sc and "HttpOnly" in sc and "samesite=strict" in sc.lower()
        # da HTTPS il cookie torna indietro e la sessione vale
        assert (await c.get("/api/auth/status")).json()["authenticated"] is True
        # il cookie HTTP con lo stesso valore non basta su HTTPS (e viceversa)
        token = c.cookies.get("meshlens_session_s")
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(ctx),
                                                         client=("192.168.1.20", 1234)),
                                 base_url="https://192.168.1.10") as c:
        c.cookies.set("meshlens_session", token)
        assert (await c.get("/api/auth/status")).json()["authenticated"] is False
    async with client(ctx) as c:  # su http (loopback) niente Secure: il login funziona
        r = await c.post("/api/auth/login", json={"pin": "1234"})
        sc = r.headers["set-cookie"]
        assert r.status_code == 200 and "Secure" not in sc
        assert sc.startswith("meshlens_session=")
        assert (await c.get("/api/auth/status")).json()["authenticated"] is True


async def test_cookie_never_secure_for_loopback_even_on_https(ctx):
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(ctx),
                                                         client=("127.0.0.1", 1234)),
                                 base_url="https://127.0.0.1") as c:
        r = await c.post("/api/auth/setup", json={"pin": "1234"})
        assert r.status_code == 200
        sc = r.headers["set-cookie"]
        assert sc.startswith("meshlens_session_s=") and "Secure" not in sc
        assert (await c.get("/api/auth/status")).json()["authenticated"] is True
        r = await c.post("/api/auth/logout")
        assert 'meshlens_session_s=""' in r.headers["set-cookie"]


def test_ws_over_https_reads_https_cookie(ctx):
    ctx.auth.set_pin("1234")
    token = ctx.auth.login("1234", "127.0.0.1")
    with TestClient(create_app(ctx), base_url="https://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token)  # cookie HTTP: non vale su wss
        with pytest.raises(WebSocketDisconnect) as exc:
            with tc.websocket_connect("wss://127.0.0.1/ws", headers={"host": "127.0.0.1"}) as ws:
                ws.receive_json()
        assert exc.value.code == 4401
        tc.cookies.clear()
        tc.cookies.set("meshlens_session_s", token)
        with tc.websocket_connect("wss://127.0.0.1/ws", headers={"host": "127.0.0.1"}) as ws:
            ctx.bus.publish({"type": "message", "message": {"text": "y"}})
            assert ws.receive_json() == {"type": "message", "message": {"text": "y"}}


async def test_compact_busy_database_returns_409(tmp_path, monkeypatch):
    import sqlite3
    import meshlens.api as api_mod
    from meshlens.app import build

    def busy(conn):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(api_mod, "compact", busy)
    app, rt = build(tmp_path, static_dir=None)
    try:
        async with client_for_app(app) as c:
            assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
            r = await c.post("/api/db/compact", json={"confirm": True})
            assert r.status_code == 409 and "riprova" in r.json()["detail"]
    finally:
        rt.conn.close()


async def test_tls_route(ctx):
    async with client(ctx) as c:
        assert (await c.get("/api/tls")).status_code == 401
    async with logged(ctx) as c:
        assert (await c.get("/api/tls")).json() == {
            "enabled": False, "port": None, "fingerprint_sha256": None,
            "not_after": None, "error": None}
        ctx.tls = {"enabled": True, "port": 8687, "fingerprint_sha256": "AB:CD",
                   "not_after": 1.5, "error": None}
        ctx.tls_errors.append("HTTPS non avviato sulla porta 8687")
        assert (await c.get("/api/tls")).json() == {
            "enabled": True, "port": 8687, "fingerprint_sha256": "AB:CD",
            "not_after": 1.5, "error": "HTTPS non avviato sulla porta 8687"}


async def test_put_settings_brokers_masked_roundtrip(ctx):
    from meshlens.settings import load_settings
    async with logged(ctx) as c:
        s = (await c.get("/api/settings")).json()
        s["mqtt_brokers"][0]["password"] = "pw-default"
        s["mqtt_brokers"].append({"id": "casa", "name": "Casa", "host": "casa.example",
                                  "topics": ["msh/#"], "password": "pw-casa",
                                  "channels": [{"name": "A", "psk": "AAECAwQFBgcICQoLDA0ODw=="},
                                               {"name": "B", "psk": "Ag=="}],
                                  "extra_keys": ["Aw=="]})
        r = await c.put("/api/settings", json=s)
        assert r.status_code == 200, r.text
        saved = load_settings(ctx.conn)["mqtt_brokers"]
        body = (await c.get("/api/settings")).json()
        for secret in ("pw-default", "pw-casa", "AAECAwQFBgcICQoLDA0ODw==", "Ag==", "Aw=="):
            assert secret not in r.text
        r = await c.put("/api/settings", json=body)
        assert r.status_code == 200, r.text
        assert load_settings(ctx.conn)["mqtt_brokers"] == saved
        casa = r.json()["mqtt_brokers"][1]
        assert casa["password"] == "••••" and [ch["psk"] for ch in casa["channels"]] == ["••••"] * 2
        assert r.json()["mqtt"]["password"] == "••••"


async def test_put_settings_bad_mask_400_and_nothing_saved(ctx):
    from meshlens.settings import load_settings
    async with logged(ctx) as c:
        s = (await c.get("/api/settings")).json()
        before = load_settings(ctx.conn)
        s["retention_messages_days"] = 33
        s["mqtt_brokers"][0]["channels"] = [{"name": "A", "psk": "••••#3"}]
        r = await c.put("/api/settings", json=s)
        assert r.status_code == 400 and "senza corrispondenza" in r.json()["detail"]
        s["mqtt_brokers"][0]["channels"] = []
        s["mqtt_brokers"].append({"name": "Nuovo", "host": "n.example", "topics": ["msh/#"],
                                  "password": "••••"})
        r = await c.put("/api/settings", json=s)
        assert r.status_code == 400
        assert load_settings(ctx.conn) == before


# ---- importazione dei canali e "mostra PSK" ----------------------------------------
KEY32_B64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="  # 32 byte 00..1f


def _squadra_link() -> str:
    import base64
    from meshtastic.protobuf import apponly_pb2
    cs = apponly_pb2.ChannelSet()
    cs.settings.add().psk = b"\x01"  # primario senza nome: LongFast con la chiave pubblica
    s = cs.settings.add()
    s.name, s.psk = "Squadra", bytes(range(32))
    return "https://meshtastic.org/e/#" + base64.urlsafe_b64encode(
        cs.SerializeToString()).decode().rstrip("=")


async def test_import_link_route_saves_and_masks(tmp_path):
    from meshlens.settings import find_broker, load_settings
    from test_app import KeyedConnector, _broker, _multi_rt
    rt = await _multi_rt(tmp_path, KeyedConnector, _broker("b1"))
    save_settings(rt.conn, {"mqtt_brokers": rt.settings["mqtt_brokers"]})
    b1 = rt.connectors["b1"]
    app = create_app(rt.ctx)
    try:
        async with client_for_app(app) as c:
            assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
            r = await c.post("/api/mqtt/brokers/b1/channels/import-link",
                             json={"url": _squadra_link()})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["added"] == ["Squadra"]
            assert body["skipped"] == [{"name": "LongFast", "reason": "canale pubblico predefinito"}]
            masked = find_broker(body["settings"], "b1")["channels"]
            assert masked == [{"name": "Squadra", "psk": "••••"}]
            assert KEY32_B64 not in r.text
            assert find_broker(load_settings(rt.conn), "b1")["channels"] == [
                {"name": "Squadra", "psk": KEY32_B64}]
            assert b1.decoder.channel_keys["Squadra"] == bytes(range(32))
            # di nuovo: tutto gia' presente, nulla da salvare
            r = await c.post("/api/mqtt/brokers/b1/channels/import-link",
                             json={"url": _squadra_link()})
            assert r.json()["added"] == [] and r.json()["skipped"][1]["reason"] == "già presente"
            bad = await c.post("/api/mqtt/brokers/b1/channels/import-link",
                               json={"url": "https://example.com/e/#abc"})
            assert bad.status_code == 400 and "Link non valido" in bad.json()["detail"]
            nob = await c.post("/api/mqtt/brokers/zz/channels/import-link",
                               json={"url": _squadra_link()})
            assert nob.status_code == 404
    finally:
        rt.conn.close()


async def test_import_routes_require_auth(ctx):
    async with client(ctx) as c:
        for path in ("import-link", "import-radio"):
            assert (await c.post(f"/api/mqtt/brokers/default/channels/{path}",
                                 json={})).status_code == 401
        assert (await c.post("/api/mqtt/brokers/default/channels/0/reveal", json={})).status_code == 401


async def test_import_radio_route_409_without_radio():
    from test_api_config import make_env
    e, ctx, conn = await make_env()
    conn.state_name = "reconnecting"
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        r = await c.post("/api/mqtt/brokers/default/channels/import-radio", json={"radio_id": rid})
        assert r.status_code == 409 and r.json()["detail"] == "Radio non collegata"
        r = await c.post("/api/mqtt/brokers/default/channels/import-radio",
                         json={"radio_id": "rnope"})
        assert r.status_code == 404
        r = await c.post("/api/mqtt/brokers/zz/channels/import-radio", json={"radio_id": rid})
        assert r.status_code == 404


async def test_import_radio_route_adds_channels():
    import base64
    from test_api_config import make_env
    from meshlens.settings import find_broker, load_settings
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    psk = bytes(range(32))
    conn.nodes[None]["channels"][0].settings.psk = psk  # (la PSK di prova non e' valida)
    async with logged(ctx) as c:
        r = await c.post("/api/mqtt/brokers/default/channels/import-radio", json={"radio_id": rid})
        assert r.status_code == 200, r.text
        assert r.json()["added"] == ["LongFast", "uno"]
        assert base64.b64encode(psk).decode() not in r.text
        chans = find_broker(load_settings(ctx.conn), "default")["channels"]
        assert chans[0] == {"name": "LongFast", "psk": base64.b64encode(psk).decode()}


async def test_reveal_psk_route(ctx):
    from meshlens.settings import load_settings
    changes = {"mqtt_brokers": [{**load_settings(ctx.conn)["mqtt_brokers"][0],
                                 "channels": [{"name": "Squadra", "psk": KEY32_B64}]}]}
    save_settings(ctx.conn, changes)
    async with logged(ctx) as c:
        r = await c.post("/api/mqtt/brokers/default/channels/0/reveal", json={})
        assert r.status_code == 200 and r.json() == {"psk": KEY32_B64}
        assert (await c.post("/api/mqtt/brokers/default/channels/99/reveal", json={})).status_code == 404
        assert (await c.post("/api/mqtt/brokers/zz/channels/0/reveal", json={})).status_code == 404
        cookie = c.cookies.get("meshlens_session")
    async with client_from(ctx, "192.168.1.5") as lan:
        lan.cookies.set("meshlens_session", cookie)
        r = await lan.post("/api/mqtt/brokers/default/channels/0/reveal", json={})
        assert r.status_code == 403 and KEY32_B64 not in r.text


async def test_import_does_not_lose_concurrent_save(ctx):
    """Un salvataggio arrivato mentre si aspetta la radio non va perso."""
    import asyncio
    from meshlens.settings import load_settings
    entered, release = asyncio.Event(), asyncio.Event()

    class SlowConfig:
        async def channel_secrets(self, radio_id):
            entered.set()
            await release.wait()
            return [{"name": "Squadra", "psk": KEY32_B64}]
    ctx.config = SlowConfig()
    async with logged(ctx) as c:
        task = asyncio.create_task(c.post("/api/mqtt/brokers/default/channels/import-radio",
                                          json={"radio_id": "r1"}))
        await entered.wait()
        r = await c.put("/api/settings", json={"retention_messages_days": 33})
        assert r.status_code == 200
        release.set()
        r = await task
        assert r.status_code == 200 and r.json()["added"] == ["Squadra"]
        assert load_settings(ctx.conn)["retention_messages_days"] == 33
        assert r.json()["settings"]["retention_messages_days"] == 33


async def test_manual_channel_psk_must_be_strict_base64(ctx):
    async with logged(ctx) as c:
        cur = (await c.get("/api/settings")).json()["mqtt_brokers"]
        for bad in ("***", "!!"):
            body = [{**cur[0], "channels": [{"name": "X", "psk": bad}]}]
            r = await c.put("/api/settings", json={"mqtt_brokers": body})
            assert r.status_code == 400, bad


# ---- waypoint e conversazioni (fase 12) ----
def _ws_ctx_with_radio():
    from test_radio_manager import Env, FakeConnector
    env = Env()
    env.ingestor.on_waypoint = lambda wp: env.bus.publish(
        {"type": "waypoint_deleted", "id": wp["deleted"]} if "deleted" in wp
        else {"type": "waypoint", "waypoint": wp})
    sent = []

    async def send_waypoint(self, wp, channel_index):
        sent.append((wp, channel_index))
        return 900 + len(sent)

    FakeConnector.send_waypoint = send_waypoint
    ctx = AppContext(live=env.live, store=env.store, auth=Auth(env.conn), bus=env.bus,
                     locator=CountryLocator(), conn=env.conn, mqtt_status=lambda: {},
                     on_settings_changed=None, radios=env.mgr)
    return env, ctx, sent


def _ws_login(ctx):
    ctx.auth.set_pin("1234")
    return ctx.auth.login("1234", "127.0.0.1")


def test_waypoint_routes():
    import asyncio
    from test_radio_manager import MY_ID
    env, ctx, sent = _ws_ctx_with_radio()
    token = _ws_login(ctx)
    wp_body = {"name": "Ritrovo", "lat": 45.1, "lon": 9.2, "expire_h": 2}
    with TestClient(create_app(ctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token)
        rid = tc.post("/api/radios", json={"kind": "usb", "address": "COM5"}).json()["id"]
        url = f"/api/radios/{rid}/waypoint"
        tc.post(f"/api/radios/{rid}/disconnect")
        assert tc.post(url, json=wp_body).status_code == 400  # radio non connessa
        tc.post(f"/api/radios/{rid}/connect")
        env.ingestor.set_radio_node(rid, int(MY_ID[1:], 16))
        assert tc.post(url, json={**wp_body, "name": "x" * 31}).status_code == 400
        assert tc.post(url, json={**wp_body, "icon": "ab"}).status_code == 400
        assert tc.post(url, json={**wp_body, "expire_h": 0}).status_code == 400
        assert tc.post(url, json={**wp_body, "lat": 0, "lon": 0}).status_code == 400
        assert sent == []
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
            r = tc.post(url, json=wp_body)
            assert r.status_code == 202
            wp = r.json()
            assert wp["name"] == "Ritrovo" and wp["icon"] == "📍" and wp["mine"] is True
            assert wp["from"] == MY_ID and wp["locked_to"] == MY_ID and wp["expire"]
            assert sent[0][0].locked_to == int(MY_ID[1:], 16) and sent[0][0].id == wp["id"]
            got = ws.receive_json()
            assert got["type"] == "waypoint" and got["waypoint"]["id"] == wp["id"]
            assert [w["id"] for w in tc.get("/api/waypoints").json()] == [wp["id"]]
            # un waypoint di un altro nodo non si elimina
            env.store.upsert_waypoint({"id": 5, "from_num": 0x42, "lat": 45.0, "lon": 9.0,
                                       "name": "Altrui", "time": time.time(), "source": "rf",
                                       "radio_id": rid, "channel": "0"})
            r = tc.delete("/api/waypoints/5")
            assert r.status_code == 403
            assert r.json()["detail"] == "Puoi eliminare solo i tuoi waypoint"
            assert tc.delete("/api/waypoints/123").status_code == 404
            r = tc.delete(f"/api/waypoints/{wp['id']}")
            assert r.status_code == 200 and r.json() == {"ok": True}
            assert sent[1][0].expire == 1 and sent[1][0].id == wp["id"]
            assert ws.receive_json() == {"type": "waypoint_deleted", "id": wp["id"]}
        assert [w["id"] for w in tc.get("/api/waypoints").json()] == [5]
        # mio ma con la radio scollegata: 409, non 403
        env.store.upsert_waypoint({"id": 6, "from_num": int(MY_ID[1:], 16), "lat": 45.0,
                                   "lon": 9.0, "name": "Mio", "time": time.time(),
                                   "source": "rf", "radio_id": rid, "channel": "0"})
        tc.post(f"/api/radios/{rid}/disconnect")
        r = tc.delete("/api/waypoints/6")
        assert r.status_code == 409 and r.json()["detail"] == "Radio non connessa"


def test_conversations_read_broadcasts(ctx):
    token = _ws_login(ctx)
    key = "ch:r1a2b3c4d:0"
    base = time.time()
    for i, (t, d, frm) in enumerate([(base - 30, "in", 0x42), (base - 20, "in", 0x42),
                                     (base - 10, "out", 1)]):
        ctx.store.add_message({"key": f"k{i}", "from": f"!{frm:08x}", "to": "!ffffffff",
                               "channel": "0", "text": f"m{i}", "time": t, "country": "IT",
                               "source": "rf", "direction": d, "radio_id": "r1a2b3c4d",
                               "channel_index": 0, "packet_id": i, "status": "sent"})
    ctx.conn.execute("UPDATE settings SET value='0' WHERE key='conv_read_baseline'")
    ctx.store.commit()
    with TestClient(create_app(ctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token)
        conv = tc.get("/api/conversations").json()
        assert [c["key"] for c in conv] == [key] and conv[0]["unread"] == 2
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
            r = tc.post("/api/conversations/read", json={"key": key, "time": base - 15})
            assert r.status_code == 200 and r.json() == {"key": key, "read_time": base - 15}
            assert ws.receive_json() == {"type": "conv_read", "key": key, "time": base - 15}
        conv = tc.get("/api/conversations").json()
        assert conv[0]["read_time"] == base - 15 and conv[0]["unread"] == 0
        assert tc.post("/api/conversations/read",
                       json={"key": "boh", "time": 1}).status_code == 400
        assert tc.post("/api/conversations/read",
                       json={"key": "dm:r1a2b3c4d:!00000042", "time": 1}).status_code == 200
        assert tc.post("/api/conversations/read",
                       json={"key": key, "time": time.time() + 3600}).status_code == 400


async def test_put_settings_keeps_masked_telegram_token(ctx):
    from meshlens.settings import load_settings
    save_settings(ctx.conn, {"telegram_token": "123456:SEGRETO_abcdefghijklmnopqrstuvwxyz0123", "telegram_chat_id": "42"})
    async with logged(ctx) as c:
        s = (await c.get("/api/settings")).json()
        assert s["telegram_token"] == "••••" and "SEGRETO" not in str(s)
        r = await c.put("/api/settings", json={"telegram_token": "••••", "notify_telegram": True})
        assert r.status_code == 200 and r.json()["telegram_token"] == "••••"
        assert load_settings(ctx.conn)["telegram_token"] == "123456:SEGRETO_abcdefghijklmnopqrstuvwxyz0123"
        assert load_settings(ctx.conn)["notify_telegram"] is True


async def test_notify_test_without_config(ctx):
    from meshlens.notify import TOAST_UNAVAILABLE
    async with logged(ctx) as c:
        r = await c.post("/api/notify/test", json={"channel": "telegram"})
        assert r.status_code == 400
        r = await c.post("/api/notify/test", json={"channel": "toast"})
        assert r.status_code == 400 and r.json()["detail"] == TOAST_UNAVAILABLE
        r = await c.post("/api/notify/test", json={"channel": "sms"})
        assert r.status_code == 422
        r = await c.post("/api/notify/telegram/chat")
        assert r.status_code == 400
        st = (await c.get("/api/notify/status")).json()
        assert st == {"toast_available": False, "telegram_last_ok": None,
                      "telegram_last_error": None}
        shown = []
        ctx.toast = lambda t, b: shown.append((t, b))
        r = await c.post("/api/notify/test", json={"channel": "toast"})
        assert r.status_code == 200 and r.json() == {"ok": True}
        assert shown == [("Prova di MeshLens", "Le notifiche funzionano")]
        assert (await c.get("/api/notify/status")).json()["toast_available"] is True


async def test_notify_telegram_failure_502_without_token(ctx, monkeypatch):
    from meshlens import notify
    token = "123456:SEGRETISSIMO_abcdefghijklmnopqrstuvwxyz"
    save_settings(ctx.conn, {"telegram_token": token, "telegram_chat_id": "42"})

    def fail(tok, chat, text, **_k):
        raise notify.NotifyError(notify.scrub_text(f"rete giù per bot{tok}", tok))

    def no_chat(tok, **_k):
        raise notify.NotifyError(notify.TELEGRAM_NO_CHAT)

    ctx.notifier.send_telegram = fail
    monkeypatch.setattr(notify, "telegram_find_chat", no_chat)
    async with logged(ctx) as c:
        r = await c.post("/api/notify/test", json={"channel": "telegram"})
        assert r.status_code == 502 and "SEGRETISSIMO" not in r.text
        st = (await c.get("/api/notify/status")).json()
        assert st["telegram_last_error"] and "SEGRETISSIMO" not in st["telegram_last_error"]
        r = await c.post("/api/notify/telegram/chat")
        assert r.status_code == 404 and r.json()["detail"] == notify.TELEGRAM_NO_CHAT
        monkeypatch.setattr(notify, "telegram_find_chat", lambda tok, **_k: ("-100", "Gruppo"))
        r = await c.post("/api/notify/telegram/chat")
        assert r.json() == {"chat_id": "-100", "title": "Gruppo"}


def test_alerts_feed_notifier(ctx):
    calls = []
    ctx.notifier.on_alerts = lambda old, new: calls.append((old, new))
    ctx.alerts()  # primo calcolo all'avvio: nessuna notifica per gli avvisi gia' presenti
    ctx.alerts()
    assert len(calls) == 1


async def test_backup_delete_and_cleanup_routes(tmp_path):
    from meshlens.app import build
    app, rt = build(tmp_path, static_dir=None)
    try:
        async with client_for_app(app) as anon:
            assert (await anon.delete("/api/backups/x.db")).status_code == 401
            assert (await anon.post("/api/backups/cleanup", json={"days": 5})).status_code == 401
        async with client_for_app(app) as c:
            assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
            d = tmp_path / "backups"
            d.mkdir(exist_ok=True)
            names = ["meshlens-20200101-000000-manuale.db", "meshlens-20200102-000000-manuale.db",
                     "meshlens-20200103-000000-manuale.db"]
            for n in names:
                (d / n).write_bytes(b"x")
            hdr = {"content-type": "application/json"}
            assert (await c.delete("/api/backups/x.db", headers=hdr)).status_code == 404
            assert (await c.delete("/api/backups/meshlens-19990101-000000-manuale.db",
                                   headers=hdr)).status_code == 404
            assert (await c.delete(f"/api/backups/{names[0]}")).status_code == 415
            (tmp_path / "restore.json").write_text('{"name": "%s"}' % names[1])
            assert (await c.delete(f"/api/backups/{names[1]}", headers=hdr)).status_code == 409
            r = await c.delete(f"/api/backups/{names[0]}", headers=hdr)
            assert r.status_code == 200 and not (d / names[0]).exists()
            assert (await c.post("/api/backups/cleanup", json={"days": 0})).status_code == 400
            r = await c.post("/api/backups/cleanup", json={"days": 30})
            # il piu' recente e quello da ripristinare restano
            assert r.status_code == 200 and r.json() == {"deleted": []}
            assert (d / names[1]).exists() and (d / names[2]).exists()
            (d / "meshlens-20200104-000000-manuale.db").write_bytes(b"x")
            r = await c.post("/api/backups/cleanup", json={"days": 30})
            assert r.json() == {"deleted": [names[2]]}
    finally:
        rt.conn.close()


async def test_messages_filtered_by_broker(ctx):
    for key, broker, t in (("7:1", "default", 100.0), ("7:2", "sos", 200.0), ("7:3", None, 300.0)):
        m = {"key": key, "from": "!00000007", "to": "!ffffffff", "channel": "LongFast",
             "text": key, "time": t, "country": "IT", "source": "mqtt", "broker": broker}
        ctx.store.add_message(m)
        ctx.live.messages.append(m)
    ctx.store.commit()
    async with logged(ctx) as c:
        live = [m["key"] for m in (await c.get("/api/messages?broker=sos")).json()]
        assert live == ["7:2"]
        hist = [m["key"] for m in (await c.get("/api/messages/history?broker=default")).json()]
        assert hist == ["7:1"]
        assert "7:3" in [m["key"] for m in (await c.get("/api/messages/history")).json()]
        assert (await c.get("/api/messages?broker=" + "x" * 25)).status_code == 422
