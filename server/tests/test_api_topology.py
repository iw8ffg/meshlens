import json
import time
from pathlib import Path

from test_api import client, logged, make_ctx  # noqa: F401

from meshlens import api_topology

NOW = time.time()
KEYS = {"node_id", "callsign", "device_callsign", "team", "role", "battery", "lat", "lon",
        "altitude", "speed", "course", "compressed", "time", "source"}


def add_contact(ctx, num, t, callsign="X", compressed=0, **kw):
    ctx.conn.execute(
        "INSERT INTO tak_contacts(node_num, callsign, team, lat, lon, compressed, time, source) "
        "VALUES(?,?,?,?,?,?,?,'rf')", (num, callsign, kw.get("team"), 45.0, 9.0, compressed, t))
    ctx.conn.commit()


async def test_tak_requires_auth():
    ctx = make_ctx()
    async with client(ctx) as c:
        assert (await c.get("/api/tak/contacts")).status_code == 401
        assert (await c.get("/api/tak/summary")).status_code == 401


async def test_tak_contacts_shape_and_order():
    ctx = make_ctx()
    add_contact(ctx, 1, NOW - 100, "A")
    add_contact(ctx, 2, NOW - 10, None, compressed=1)
    async with logged(ctx) as c:
        r = await c.get("/api/tak/contacts")
    data = r.json()
    assert [d["node_id"] for d in data] == ["!00000002", "!00000001"]
    assert all(set(d) == KEYS for d in data)
    assert data[0]["compressed"] is True and data[1]["compressed"] is False


async def test_tak_contacts_window_and_validation():
    ctx = make_ctx()
    add_contact(ctx, 1, NOW - 3 * 86400)
    async with logged(ctx) as c:
        assert (await c.get("/api/tak/contacts?hours=24")).json() == []
        assert len((await c.get("/api/tak/contacts?hours=96")).json()) == 1
        for bad in ("0", "721", "abc"):
            r = await c.get(f"/api/tak/contacts?hours={bad}")
            assert r.status_code == 400
            assert r.json()["detail"] == "Periodo non valido: da 1 a 720 ore"


async def test_tak_hides_ignored_nodes():
    ctx = make_ctx()
    ctx.conn.execute("INSERT INTO nodes(num, id, is_ignored) VALUES(1, '!00000001', 1)")
    add_contact(ctx, 1, NOW - 10)
    add_contact(ctx, 2, NOW - 10)
    async with logged(ctx) as c:
        assert [d["node_id"] for d in (await c.get("/api/tak/contacts")).json()] == ["!00000002"]
        assert (await c.get("/api/tak/summary")).json()["contacts"] == 1


async def test_tak_summary_counts():
    ctx = make_ctx()
    add_contact(ctx, 1, NOW - 10, None, compressed=1)
    add_contact(ctx, 2, NOW - 10, "B", compressed=1)
    add_contact(ctx, 3, NOW - 10, "C")
    for i in range(2):
        ctx.conn.execute("INSERT INTO packets(time, portnum, status) VALUES(?, 'ATAK_PLUGIN_V2', 'unsupported')",
                         (NOW - 5,))
    ctx.conn.commit()
    async with logged(ctx) as c:
        assert (await c.get("/api/tak/summary")).json() == {"contacts": 3, "compressed": 1,
                                                            "unsupported_v2": 2}


async def test_guest_paths_declared():
    ctx = make_ctx()
    from meshlens.api import create_app
    app = create_app(ctx)
    routes = {r.path for r in app.routes if "GET" in getattr(r, "methods", ())}
    assert set(api_topology.GUEST_GET_PATHS) == {"/api/tak/contacts", "/api/tak/summary",
                                                 "/api/topology"}
    for p in api_topology.GUEST_GET_PATHS:
        if p != "/api/topology":  # la rotta del grafo arriva col Task 5
            assert p in routes


def test_wp3_catalog_has_message():
    f = Path(__file__).parents[2] / "web" / "src" / "lib" / "i18n" / "server-en" / "wp3.json"
    assert "Periodo non valido: da 1 a 720 ore" in json.loads(f.read_text("utf-8"))["exact"]
