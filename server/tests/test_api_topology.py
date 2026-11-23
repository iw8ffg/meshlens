import json
import time
from pathlib import Path

from test_api import client, logged, make_ctx  # noqa: F401

from meshlens import api_topology
from meshlens.topology import SOURCES

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
        assert p in routes


def test_wp3_catalog_has_message():
    f = Path(__file__).parents[2] / "web" / "src" / "lib" / "i18n" / "server-en" / "wp3.json"
    exact = json.loads(f.read_text("utf-8"))["exact"]
    for k in ("Periodo non valido: da 1 a 720 ore", "Sorgenti dei collegamenti non valide",
              "Filtro nazioni non valido", "Limite di nodi non valido: da 10 a 1000"):
        assert k in exact


# ---- /api/topology ----
def seed_graph(ctx):
    for n, country in ((1, "IT"), (2, "IT"), (3, "DE")):
        ctx.conn.execute("INSERT OR REPLACE INTO nodes(num, id, long_name, last_heard, country) "
                         "VALUES(?,?,?,?,?)", (n, "!%08x" % n, f"N{n}", NOW - 5, country))
    for a, b, s, t in ((1, 2, "traceroute", NOW - 5), (2, 3, "neighborinfo", NOW - 5),
                       (1, 3, "rf_direct", NOW - 2 * 3600)):
        ctx.conn.execute("INSERT INTO links(from_num, to_num, source, snr, time) VALUES(?,?,?,?,?)",
                         (a, b, s, 1.0, t))
    ctx.conn.commit()


async def test_topology_requires_auth():
    async with client(make_ctx()) as c:
        assert (await c.get("/api/topology")).status_code == 401


async def test_topology_default_shape():
    ctx = make_ctx()
    seed_graph(ctx)
    async with logged(ctx) as c:
        j = (await c.get("/api/topology")).json()
    assert set(j) == {"since", "hours", "nodes", "edges", "isolated", "components", "stats",
                      "truncated", "sources"}
    assert j["hours"] == 168 and j["sources"] == list(SOURCES)


async def test_topology_params_applied():
    ctx = make_ctx()
    seed_graph(ctx)
    async with logged(ctx) as c:
        assert len((await c.get("/api/topology?hours=1")).json()["edges"]) == 2
        j = (await c.get("/api/topology?sources=traceroute")).json()
        assert [e["sources"] for e in j["edges"]] == [["traceroute"]]
        j = (await c.get("/api/topology?countries=IT")).json()
        assert {n["id"] for n in j["nodes"]} == {"!00000001", "!00000002"}
        assert (await c.get("/api/topology?limit=10")).status_code == 200


async def test_topology_validation_errors():
    ctx = make_ctx()
    hours = "Periodo non valido: da 1 a 720 ore"
    srcs = "Sorgenti dei collegamenti non valide"
    lim = "Limite di nodi non valido: da 10 a 1000"
    cases = {"hours=0": hours, "hours=721": hours, "hours=x": hours,
             "sources=boh": srcs, "sources=": srcs, "sources=traceroute,traceroute": srcs,
             "countries=ITA": "Filtro nazioni non valido",
             "countries=it,": "Filtro nazioni non valido",
             "limit=9": lim, "limit=1001": lim, "limit=x": lim}
    async with logged(ctx) as c:
        for q, msg in cases.items():
            r = await c.get(f"/api/topology?{q}")
            assert r.status_code == 400, q
            assert r.json()["detail"] == msg, q


async def test_topology_works_without_ext():
    ctx = make_ctx()
    assert ctx.ext == {}
    async with logged(ctx) as c:
        assert (await c.get("/api/topology")).status_code == 200


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


async def test_topology_no_secrets_or_addresses():
    ctx = make_ctx()
    seed_graph(ctx)
    async with logged(ctx) as c:
        keys = set(_keys((await c.get("/api/topology")).json()))
    assert not keys & {"public_key", "ip", "address", "psk"}
