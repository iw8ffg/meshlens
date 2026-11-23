import time
from types import SimpleNamespace

from meshlens import alert_rules as ar
from meshlens import ext_monitor
from meshlens.alert_rules import RuleStore, validate_rule
from meshlens.api import AppContext
from meshlens.auth import Auth
from meshlens.bus import Bus
from meshlens.db import connect
from meshlens.geo import CountryLocator
from meshlens.live import LiveState
from meshlens.store import Store
from test_api import client, logged

SQUARE = [[10, 40], [11, 40], [11, 41], [10, 41]]
BATTERY = {"kind": "battery", "node_id": "!00000001", "threshold": 20}


def make_ctx(install=True):
    conn = connect(":memory:")
    live = LiveState()
    now = time.time()
    live.load([{"id": "!00000001", "num": 1, "long_name": "A", "country": "IT",
                "last_heard": now, "is_mine": True, "battery": 8},
               {"id": "!00000002", "num": 2, "long_name": "B", "country": "IT",
                "last_heard": now, "battery": 50}])

    async def noop(_s):
        return None

    ctx = AppContext(live=live, store=Store(conn), auth=Auth(conn), bus=Bus(),
                     locator=CountryLocator(), conn=conn,
                     mqtt_status=lambda: {"connected": True, "msgs_per_s": 0.0, "undecodable": 0},
                     on_settings_changed=noop, static_dir=None)
    if install:
        rt = SimpleNamespace(ingestor=SimpleNamespace(persists=lambda n, s: True),
                             add_message_hook=lambda f: None, add_event_hook=lambda f: None)
        ext_monitor.install(rt, ctx)
    return ctx


async def test_requires_auth_and_json():
    ctx = make_ctx()
    async with client(ctx) as c:
        assert (await c.get("/api/alert-rules")).status_code == 401
        assert (await c.post("/api/alert-rules", json=BATTERY)).status_code == 401
        assert (await c.patch("/api/alert-rules/1", json={})).status_code == 401
        assert (await c.request("DELETE", "/api/alert-rules/1",
                                json={"confirm": True})).status_code == 401
    async with logged(ctx) as c:
        r = await c.post("/api/alert-rules", content="{}", headers={"content-type": "text/plain"})
        assert r.status_code == 415


async def test_503_without_extension():
    async with logged(make_ctx(install=False)) as c:
        for r in (await c.get("/api/alert-rules"), await c.post("/api/alert-rules", json=BATTERY)):
            assert r.status_code == 503
            assert r.json()["detail"] == ar.MSG_RULES_UNAVAILABLE


async def test_create_list_patch_delete():
    async with logged(make_ctx()) as c:
        r = await c.post("/api/alert-rules", json=BATTERY)
        assert r.status_code == 200
        rule = r.json()
        assert rule["id"] and rule["node_id"] == "!00000001" and rule["created"]
        assert rule["threshold"] == 20 and rule["enabled"] is True
        assert [x["id"] for x in (await c.get("/api/alert-rules")).json()] == [rule["id"]]
        url = f"/api/alert-rules/{rule['id']}"
        p = await c.patch(url, json={"enabled": False})
        assert p.status_code == 200 and p.json()["enabled"] is False
        assert p.json()["threshold"] == 20 and p.json()["node_id"] == "!00000001"
        assert (await c.patch(url, json={"threshold": 99})).status_code == 200
        bad = await c.patch(url, json={"threshold": 100})
        assert bad.status_code == 400 and bad.json()["detail"] == ar.MSG_RULE_BATTERY
        assert (await c.request("DELETE", url, json={})).status_code == 400
        d = await c.request("DELETE", url, json={"confirm": True})
        assert d.status_code == 200 and d.json() == {"ok": True}
        assert (await c.get("/api/alert-rules")).json() == []
        assert (await c.patch("/api/alert-rules/999", json={"enabled": True})).status_code == 404
        assert (await c.request("DELETE", "/api/alert-rules/999",
                                json={"confirm": True})).status_code == 404


async def test_patch_node_null_and_bad_id():
    async with logged(make_ctx()) as c:
        kw = (await c.post("/api/alert-rules", json={
            "kind": "keyword", "node_id": "!00000002", "params": {"words": ["aiuto"]}})).json()
        assert kw["node_id"] == "!00000002"
        r = await c.patch(f"/api/alert-rules/{kw['id']}", json={"node_id": None})
        assert r.json()["node_id"] is None
        r = await c.post("/api/alert-rules", json={**BATTERY, "node_id": "zzz"})
        assert r.status_code == 400


async def test_validation_errors_are_400_with_italian_message():
    async with logged(make_ctx()) as c:
        cases = [
            ({"kind": "geofence", "node_id": "!00000001",
              "params": {"polygon": [[0, 0], [1, 1], [1, 0], [0, 1]]}}, ar.MSG_RULE_POLYGON_SHAPE),
            ({"kind": "keyword", "params": {"words": ["a"]}}, ar.MSG_RULE_WORDS),
            ({"kind": "keyword", "channel": "foo", "params": {"words": ["aiuto"]}},
             ar.MSG_RULE_CHANNEL),
            ({"kind": "nope"}, ar.MSG_RULE_KIND),
        ]
        for body, msg in cases:
            r = await c.post("/api/alert-rules", json=body)
            assert r.status_code == 400 and r.json()["detail"] == msg


async def test_limit_100_rules():
    ctx = make_ctx()
    store = RuleStore(ctx.conn)
    for _ in range(ar.MAX_RULES):
        store.create(validate_rule({"kind": "detection"}), 1.0)
    async with logged(ctx) as c:
        r = await c.post("/api/alert-rules", json={"kind": "detection"})
        assert r.status_code == 400 and r.json()["detail"] == ar.MSG_RULES_MAX


async def test_ws_event_and_alerts_recomputed():
    ctx = make_ctx()
    q = ctx.bus.subscribe()
    async with logged(ctx) as c:
        rule = (await c.post("/api/alert-rules", json=BATTERY)).json()
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        ev = [e for e in events if e.get("type") == "alert_rules"]
        assert ev and ev[0]["rules"][0]["id"] == rule["id"]
        alerts = (await c.get("/api/alerts")).json()
        a = [x for x in alerts if x["kind"] == "rule_battery"]
        assert a and a[0]["rule_id"] == rule["id"] and a[0]["value"] == 8


async def test_rule_json_has_no_internal_fields():
    async with logged(make_ctx()) as c:
        rule = (await c.post("/api/alert-rules", json=BATTERY)).json()
        assert set(rule) == {"id", "kind", "name", "enabled", "node_id", "channel", "threshold",
                             "params", "cooldown_min", "created", "updated", "last_fired"}
