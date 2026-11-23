"""E19: accesso ospite. Allowlist, filtro degli eventi, matrice su tutte le rotte, WebSocket,
rotte dedicate."""
import re

import httpx
import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from meshlens import guest
from meshlens.api import create_app
from meshlens.settings import load_settings, save_settings
from test_api import make_ctx


# ---- parte pura ----

def test_guest_paths_union_of_core_and_modules():
    from meshlens import api_data, api_monitor, api_topology
    paths = guest.guest_get_paths()
    assert set(guest.CORE_GUEST_GET_PATHS) <= paths
    assert set(api_data.GUEST_GET_PATHS) <= paths
    assert set(api_monitor.GUEST_GET_PATHS) <= paths
    assert set(api_topology.GUEST_GET_PATHS) <= paths
    # mai messaggi, radio, impostazioni, registro pacchetti
    for bad in ("/api/messages", "/api/messages/history", "/api/conversations", "/api/radios",
                "/api/settings", "/api/packets", "/api/waypoints", "/api/status",
                "/api/version", "/api/messages/search", "/api/search"):
        assert bad not in paths


def test_guest_alerts_drop_rules():
    alerts = [
        {"key": "a", "kind": "battery_low", "node_id": "!00000001", "value": 10},
        {"key": "b", "kind": "rule_keyword", "node_id": "!00000002", "rule_id": 3,
         "detail": {"word": "sos", "text": "aiuto sos"}},
        {"key": "c", "kind": "rule_snr", "node_id": "!00000002", "rule_id": 4},
        {"key": "d", "kind": "sensor_detection", "node_id": "!00000003", "rule_id": None},
    ]
    out = guest.guest_alerts(alerts)
    assert [a["key"] for a in out] == ["a", "d"]
    assert all("rule_id" not in a for a in out)
    assert alerts[3]["rule_id"] is None  # l'originale non cambia


def test_guest_mqtt_status_is_reduced():
    st = {"connected": True, "msgs_per_s": 2.5, "connected_since": 10.0, "last_msg_age_s": 3,
          "last_error": "host.example: rifiutato", "brokers": [{"host": "h.example"}],
          "decoded": 5, "undecodable": 1}
    out = guest.guest_mqtt_status(st)
    assert out == {"connected": True, "msgs_per_s": 2.5, "connected_since": 10.0,
                   "last_msg_age_s": 3, "undecodable": 0}
    assert guest.guest_mqtt_status(None) is None


def test_guest_event_filter():
    ok = [{"type": "nodes", "nodes": []}, {"type": "resync"},
          {"type": "sensor_event", "event": {}}, {"type": "tak_contact", "contact": {}},
          {"type": "traceroute", "result": {"forward": []}}]
    for m in ok:
        assert guest.guest_event(m) == m
    denied = ["message", "message_status", "conv_read", "radios", "config_job", "bot",
              "alert_rules", "trace_targets", "waypoint", "waypoint_deleted", "coverage",
              "update_job", "map_job", "prediction_job", "sf_job", "sf_routers", "x", None]
    for t in denied:
        assert guest.guest_event({"type": t, "message": {"text": "segreto"}}) is None
    st = guest.guest_event({"type": "status", "mqtt": {"connected": False, "msgs_per_s": 0,
                                                      "brokers": [{"host": "h"}]}})
    assert st == {"type": "status", "mqtt": {"connected": False, "msgs_per_s": 0,
                                             "connected_since": None, "last_msg_age_s": None,
                                             "undecodable": 0}}
    al = guest.guest_event({"type": "alerts", "alerts": [
        {"key": "a", "kind": "silent"}, {"key": "b", "kind": "rule_keyword", "detail": {}}]})
    assert al == {"type": "alerts", "alerts": [{"key": "a", "kind": "silent"}]}


# ---- API: nega per impostazione predefinita ----

ADMIN_PIN = "1234"
GUEST_PIN = "654321"
# rotte senza require_auth: solo queste (una nuova rotta pubblica fa fallire la matrice)
PUBLIC = {("GET", "/api/ping"), ("GET", "/api/auth/status"), ("POST", "/api/auth/setup"),
          ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("GET", "/")}


@pytest.fixture
def gctx():
    ctx = make_ctx()
    ctx.auth.set_pin(ADMIN_PIN)
    ctx.auth.set_guest_pin(GUEST_PIN)
    save_settings(ctx.conn, {"guest_enabled": True})
    return ctx


def guest_token(ctx, ip="127.0.0.1"):
    return ctx.auth.login(GUEST_PIN, ip, "Ospite", guest_ok=True)


def admin_token(ctx, ip="127.0.0.1"):
    return ctx.auth.login(ADMIN_PIN, ip, "Admin")


def client_with(ctx, token, host="127.0.0.1", app=None):
    c = httpx.AsyncClient(
        transport=ASGITransport(app=app or create_app(ctx), client=(host, 1234),
                                raise_app_exceptions=False),
        base_url="http://127.0.0.1")
    if token:
        c.cookies.set("meshlens_session", token)
    return c


def fill(path: str) -> str:
    def value(m):
        return "!00000001" if m.group(1) == "node_id" else "1"
    return re.sub(r"\{(\w+)(?::[^}]*)?\}", value, path)


def api_routes(app):
    for r in app.routes:
        if isinstance(r, APIRoute):
            for method in sorted(r.methods):
                yield method, r.path


async def test_matrix_guest_denied_everywhere_but_allowlist(gctx):
    app = create_app(gctx)
    allowed = guest.guest_get_paths()
    token = guest_token(gctx)
    checked = denied = 0
    failures = []
    async with client_with(gctx, token, app=app) as c:
        for method, path in api_routes(app):
            if (method, path) in PUBLIC:
                continue
            kw = {} if method == "GET" else {"json": {}}
            r = await c.request(method, fill(path), **kw)
            checked += 1
            if method == "GET" and path in allowed:
                if r.status_code in (401, 403):
                    failures.append(f"{method} {path}: {r.status_code} (in allowlist)")
            else:
                denied += 1
                if r.status_code != 403 or r.json().get("detail") != guest.GUEST_FORBIDDEN:
                    failures.append(f"{method} {path}: {r.status_code} {r.text[:80]}")
    assert not failures, "\n".join(failures)
    assert checked > 100 and denied > 80


async def test_matrix_guest_denied_from_network_too(gctx):
    app = create_app(gctx)
    allowed = guest.guest_get_paths()
    token = guest_token(gctx, "192.168.1.50")
    async with client_with(gctx, token, host="192.168.1.50", app=app) as c:
        for method, path in api_routes(app):
            if (method, path) in PUBLIC or (method == "GET" and path in allowed):
                continue
            r = await c.request(method, fill(path), **({} if method == "GET" else {"json": {}}))
            assert r.status_code == 403, f"{method} {path}: {r.status_code}"


def test_allowlist_only_existing_get_routes(gctx):
    app = create_app(gctx)
    by_path: dict[str, set[str]] = {}
    for method, path in api_routes(app):
        by_path.setdefault(path, set()).add(method)
    for path in guest.guest_get_paths():
        assert path in by_path, f"{path} non e' una rotta registrata"
        assert by_path[path] == {"GET"}, f"{path} non e' solo GET: {by_path[path]}"


def test_every_non_public_route_uses_require_auth(gctx):
    app = create_app(gctx)
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        if all((m, r.path) in PUBLIC for m in r.methods):
            continue
        names = {getattr(d.call, "__name__", "") for d in r.dependant.dependencies}
        assert "require_auth" in names, f"{r.path} senza require_auth"


async def test_matrix_admin_never_forbidden_for_role(gctx):
    app = create_app(gctx)
    async with client_with(gctx, admin_token(gctx), app=app) as c:
        for method, path in api_routes(app):
            if method != "GET" or (method, path) in PUBLIC:
                continue
            r = await c.get(fill(path))
            assert r.status_code != 401, path
            if r.status_code == 403:
                assert r.json().get("detail") != guest.GUEST_FORBIDDEN, path


async def test_guest_reads_allowed_routes(gctx):
    async with client_with(gctx, guest_token(gctx)) as c:
        r = await c.get("/api/nodes")
        assert r.status_code == 200 and len(r.json()) == 4
        assert (await c.get("/api/nodes/!00000001")).status_code == 200
        assert (await c.get("/api/links")).status_code == 200
        assert (await c.get("/api/countries")).status_code == 200
        assert (await c.get("/api/messages")).status_code == 403
        r = await c.put("/api/nodes/!00000001/favorite", json={"favorite": True})
        assert r.status_code == 403


async def test_auth_status_role(gctx):
    async with client_with(gctx, guest_token(gctx, "192.168.1.5"), host="192.168.1.5") as c:
        st = (await c.get("/api/auth/status")).json()
        assert st["authenticated"] is True and st["role"] == "guest"
        assert "pin_short" not in st and "pin_min" not in st
    async with client_with(gctx, admin_token(gctx)) as c:
        st = (await c.get("/api/auth/status")).json()
        assert st["role"] == "admin" and "pin_min" in st


async def test_guest_alerts_filtered(gctx):
    gctx.alert_sources.append(lambda now, s, prev: [
        {"key": "rule:1:!00000001", "kind": "rule_keyword", "node_id": "!00000001",
         "value": 1, "rule_id": 1, "detail": {"text": "messaggio privato"}}])
    async with client_with(gctx, guest_token(gctx)) as c:
        alerts = (await c.get("/api/alerts")).json()
        assert all(not a["kind"].startswith("rule_") for a in alerts)
        assert "messaggio privato" not in str(alerts)
    async with client_with(gctx, admin_token(gctx)) as c:
        assert any(a["kind"] == "rule_keyword" for a in (await c.get("/api/alerts")).json())


async def test_login_with_guest_pin_only_when_enabled(gctx):
    async with client_with(gctx, "") as c:
        r = await c.post("/api/auth/login", json={"pin": GUEST_PIN})
        assert r.status_code == 200
        assert (await c.get("/api/auth/status")).json()["role"] == "guest"
    save_settings(gctx.conn, {"guest_enabled": False})
    async with client_with(gctx, "", host="192.168.1.7") as c:
        r = await c.post("/api/auth/login", json={"pin": GUEST_PIN})
        assert r.status_code == 401


async def test_guest_session_invalid_when_guest_disabled(gctx):
    token = guest_token(gctx)
    save_settings(gctx.conn, {"guest_enabled": False})  # es. ripristino: nessuna revoca
    async with client_with(gctx, token) as c:
        assert (await c.get("/api/nodes")).status_code == 401
        assert (await c.get("/api/auth/status")).json()["authenticated"] is False
    assert gctx.auth.check(token) is False


async def test_put_settings_guest_off_revokes_guests(gctx):
    token = guest_token(gctx)
    async with client_with(gctx, admin_token(gctx)) as c:
        r = await c.put("/api/settings", json={"guest_enabled": False})
        assert r.status_code == 200
    assert gctx.auth.check(token) is False
    assert load_settings(gctx.conn)["guest_enabled"] is False


async def test_change_admin_pin_equal_to_guest_refused(gctx):
    async with client_with(gctx, admin_token(gctx)) as c:
        r = await c.post("/api/auth/pin", json={"current_pin": ADMIN_PIN, "new_pin": GUEST_PIN})
        assert r.status_code == 400


# ---- WebSocket ----

ADMIN_ONLY_EVENTS = [
    {"type": "message", "message": {"text": "segreto"}},
    {"type": "message_status", "key": "k", "status": "acked"},
    {"type": "conv_read", "key": "ch:r00000001:0", "time": 1},
    {"type": "radios", "radios": [{"address": "COM3"}]},
    {"type": "config_job", "job": {}},
    {"type": "bot", "status": {}},
    {"type": "alert_rules", "rules": []},
    {"type": "trace_targets", "targets": []},
    {"type": "waypoint", "waypoint": {}},
    {"type": "coverage", "session": {}},
    {"type": "update_job", "job": {}},
    {"type": "futuro", "x": 1},
]


def test_ws_guest_receives_only_public_events(gctx):
    token = guest_token(gctx)
    with TestClient(create_app(gctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token)
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
            for ev in ADMIN_ONLY_EVENTS:
                gctx.bus.publish(ev)
            gctx.bus.publish({"type": "alerts", "alerts": [
                {"key": "a", "kind": "rule_keyword", "detail": {"text": "segreto"}},
                {"key": "b", "kind": "silent", "node_id": "!00000001"}]})
            gctx.bus.publish({"type": "status", "mqtt": {"connected": True, "msgs_per_s": 1,
                                                        "brokers": [{"host": "h.example"}],
                                                        "last_error": "x"}})
            gctx.bus.publish({"type": "nodes", "nodes": [{"id": "!00000001"}]})
            gctx.bus.publish({"type": "resync"})
            got = [ws.receive_json() for _ in range(4)]
    assert [m["type"] for m in got] == ["alerts", "status", "nodes", "resync"]
    assert got[0]["alerts"] == [{"key": "b", "kind": "silent", "node_id": "!00000001"}]
    assert "brokers" not in got[1]["mqtt"] and "last_error" not in got[1]["mqtt"]
    assert "segreto" not in str(got)


def test_ws_admin_receives_everything(gctx):
    token = admin_token(gctx)
    with TestClient(create_app(gctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token)
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
            for ev in ADMIN_ONLY_EVENTS:
                gctx.bus.publish(ev)
            got = [ws.receive_json() for _ in ADMIN_ONLY_EVENTS]
    assert got == ADMIN_ONLY_EVENTS


def test_ws_guest_closed_when_guest_disabled(gctx):
    token = guest_token(gctx)
    admin = admin_token(gctx)
    with TestClient(create_app(gctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token)
        with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
            tc.cookies.set("meshlens_session", admin)
            assert tc.put("/api/settings", json={"guest_enabled": False}).status_code == 200
            with pytest.raises(WebSocketDisconnect) as e:
                ws.receive_json()
            assert e.value.code == 4401


def test_ws_guest_refused_when_guest_disabled(gctx):
    token = guest_token(gctx)
    save_settings(gctx.conn, {"guest_enabled": False})
    with TestClient(create_app(gctx), base_url="http://127.0.0.1") as tc:
        tc.cookies.set("meshlens_session", token)
        with pytest.raises(WebSocketDisconnect) as e:
            with tc.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
                ws.receive_json()
        assert e.value.code == 4401
