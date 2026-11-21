import time

import pytest

from meshlens.api import AppContext
from meshlens.auth import Auth
from meshlens.coverage import CoverageRecorder
from meshlens.geo import CountryLocator
from test_api import client, logged
from test_radio_manager import Env, FakeConnector, MY_ID

MOBILE = 0x1234ABCD
MOBILE_ID = "!1234abcd"


@pytest.fixture
def env():
    return Env()


def make_ctx(env):
    async def noop(_s):
        return None

    env.coverage = CoverageRecorder(env.store, env.live, env.bus,
                                    radio_node=lambda rid: int(MY_ID[1:], 16))
    return AppContext(live=env.live, store=env.store, auth=Auth(env.conn), bus=env.bus,
                      locator=CountryLocator(), conn=env.conn, mqtt_status=lambda: {},
                      on_settings_changed=noop, radios=env.mgr, coverage=env.coverage)


def put_mobile(env, age_s=300, bits=32):
    env.live.nodes[MOBILE] = {"num": MOBILE, "id": MOBILE_ID, "lat": 45.0, "lon": 11.0,
                              "position_time": int(time.time() - age_s),
                              "precision_bits": bits, "position_source": "rf"}


async def add_radio(c, env, connected=True):
    rid = (await c.post("/api/radios", json={"kind": "usb", "address": "COM5",
                                             "name": "H"})).json()["id"]
    FakeConnector.instances[0].state_name = "connected" if connected else "error"
    return rid


async def test_requires_auth(env):
    async with client(make_ctx(env)) as c:
        assert (await c.get("/api/coverage/sessions")).status_code == 401
        assert (await c.get("/api/coverage/check")).status_code == 401
        assert (await c.post("/api/coverage/sessions", json={})).status_code == 401


async def test_check_reports_gps_and_precision(env):
    async with logged(make_ctx(env)) as c:
        rid = await add_radio(c, env)
        put_mobile(env, 300, 13)
        r = (await c.get("/api/coverage/check",
                         params={"radio_id": rid, "mobile_id": MOBILE_ID.upper()})).json()
        assert r["radio_connected"] and r["mobile_known"] and r["gps_ok"]
        assert r["radio_channels"] == [{"index": 0, "name": "LongFast"}]
        assert r["precision_bits"] == 13 and abs(r["precision_m"] - 2900) < 290
        assert 295 < r["position_age_s"] < 310 and r["rangetest_age_s"] is None
        assert r["base_position"] is None
        put_mobile(env, 1200, 13)
        r = (await c.get("/api/coverage/check",
                         params={"radio_id": rid, "mobile_id": MOBILE_ID})).json()
        assert r["gps_ok"] is False
        env.live.nodes.pop(MOBILE)
        r = (await c.get("/api/coverage/check",
                         params={"radio_id": rid, "mobile_id": MOBILE_ID})).json()
        assert r["mobile_known"] is False and r["gps_ok"] is False


async def test_start_requires_connected_radio_and_gps(env):
    async with logged(make_ctx(env)) as c:
        rid = await add_radio(c, env, connected=False)
        put_mobile(env)
        body = {"radio_id": rid, "mobile_id": MOBILE_ID}
        r = await c.post("/api/coverage/sessions", json=body)
        assert r.status_code == 400 and "collegata" in r.json()["detail"]
        FakeConnector.instances[0].state_name = "connected"
        put_mobile(env, 1200)
        r = await c.post("/api/coverage/sessions", json=body)
        assert r.status_code == 400
        assert r.json()["detail"] == ("Il nodo mobile non ha inviato una posizione negli ultimi "
                                      "10 minuti: serve il GPS acceso e la posizione attiva.")
        r = await c.post("/api/coverage/sessions",
                         json={"radio_id": "rnope", "mobile_id": MOBILE_ID})
        assert r.status_code == 404
        r = await c.post("/api/coverage/sessions", json={"radio_id": rid, "mobile_id": "xx"})
        assert r.status_code == 400


async def test_start_validation(env):
    async with logged(make_ctx(env)) as c:
        rid = await add_radio(c, env)
        put_mobile(env)
        base = {"radio_id": rid, "mobile_id": MOBILE_ID}
        for extra in ({"interval_s": 5}, {"interval_s": 601}, {"mode": "x"}, {"base_lat": 45.0}):
            r = await c.post("/api/coverage/sessions", json=base | extra)
            assert r.status_code in (400, 422), extra


async def test_start_approx_needs_accept(env):
    async with logged(make_ctx(env)) as c:
        rid = await add_radio(c, env)
        put_mobile(env, 60, 13)
        body = {"radio_id": rid, "mobile_id": MOBILE_ID}
        r = await c.post("/api/coverage/sessions", json=body)
        assert r.status_code == 400 and r.json()["code"] == "approx_position"
        assert "±2" in r.json()["detail"] or "±3" in r.json()["detail"]
        r = await c.post("/api/coverage/sessions", json=body | {"accept_approx": True})
        assert r.status_code == 201 and r.json()["mobile_id"] == MOBILE_ID


async def test_start_conflict_when_active(env):
    async with logged(make_ctx(env)) as c:
        rid = await add_radio(c, env)
        put_mobile(env)
        body = {"radio_id": rid, "mobile_id": MOBILE_ID}
        assert (await c.post("/api/coverage/sessions", json=body)).status_code == 201
        r = await c.post("/api/coverage/sessions", json=body)
        assert r.status_code == 409 and r.json()["detail"] == "C'è già una sessione in corso"


async def test_stop_patch_delete(env):
    async with logged(make_ctx(env)) as c:
        rid = await add_radio(c, env)
        put_mobile(env)
        s = (await c.post("/api/coverage/sessions",
                          json={"radio_id": rid, "mobile_id": MOBILE_ID})).json()
        url = f"/api/coverage/sessions/{s['id']}"
        assert (await c.delete(url)).status_code == 409
        r = await c.patch(url, json={"name": "Nuovo", "notes": "n", "base_lat": 44.0,
                                     "base_lon": 10.0})
        assert r.status_code == 200 and r.json()["name"] == "Nuovo" and r.json()["base_lat"] == 44.0
        assert (await c.patch(url, json={"base_lat": 44.0})).status_code == 400
        assert (await c.patch("/api/coverage/sessions/999", json={"name": "x"})).status_code == 404
        r = await c.post(url + "/stop")
        assert r.status_code == 200 and r.json()["end_reason"] == "manual"
        assert (await c.post(url + "/stop")).status_code == 409
        assert (await c.delete(url)).status_code in (200, 204)
        assert (await c.get(url)).status_code == 404
        assert (await c.get("/api/coverage/sessions")).json() == []


async def test_list_and_detail_shape(env):
    async with logged(make_ctx(env)) as c:
        rid = await add_radio(c, env)
        put_mobile(env)
        s = (await c.post("/api/coverage/sessions",
                          json={"radio_id": rid, "mobile_id": MOBILE_ID.upper()})).json()
        assert (await c.get("/api/coverage/sessions")).json()[0]["id"] == s["id"]
        d = (await c.get(f"/api/coverage/sessions/{s['id']}")).json()
        for k in ("id", "name", "radio_id", "mobile_id", "mode", "received", "expected",
                  "missing", "loss_pct", "best_snr", "worst_snr", "max_distance_m",
                  "approx_precision_m", "points", "missing_points", "track"):
            assert k in d
        assert (await c.get("/api/coverage/sessions/999")).status_code == 404


async def test_default_name(env):
    async with logged(make_ctx(env)) as c:
        rid = await add_radio(c, env)
        put_mobile(env)
        s = (await c.post("/api/coverage/sessions",
                          json={"radio_id": rid, "mobile_id": MOBILE_ID})).json()
        assert s["name"].startswith("Prova ")


def real_pos(t, bits):
    from meshlens.events import MeshEvent, PositionData
    return MeshEvent("rf", MOBILE, 0xFFFFFFFF, 7, "0", t, None, None, 0, None, "r1", "position",
                     PositionData(45.0, 11.0, None, bits, None))


async def test_check_and_start_use_latest_position_not_best(env):
    async with logged(make_ctx(env)) as c:
        rid = await add_radio(c, env)
        put_mobile(env, 3000, 32)  # la migliore, vecchia
        env.coverage.handle(real_pos(time.time() - 30, 13))  # l'ultima, approssimata
        r = (await c.get("/api/coverage/check",
                         params={"radio_id": rid, "mobile_id": MOBILE_ID})).json()
        assert r["precision_bits"] == 13 and r["gps_ok"] and r["position_age_s"] < 60
        r = await c.post("/api/coverage/sessions", json={"radio_id": rid, "mobile_id": MOBILE_ID})
        assert r.status_code == 400 and r.json()["code"] == "approx_position"
        assert "km" in r.json()["detail"] and "," in r.json()["detail"]


async def test_mobile_id_strict_and_name_and_coords(env):
    async with logged(make_ctx(env)) as c:
        rid = await add_radio(c, env)
        put_mobile(env)
        for bad in ("!-1234abc", "!1234abc", "!1234abcde", "!1234abcg"):
            r = await c.post("/api/coverage/sessions", json={"radio_id": rid, "mobile_id": bad})
            assert r.status_code == 400, bad
        body = {"radio_id": rid, "mobile_id": MOBILE_ID}
        r = await c.post("/api/coverage/sessions", json=body | {"base_lat": 91, "base_lon": 0})
        assert r.status_code == 400
        r = await c.post("/api/coverage/sessions", json=body | {"name": "   "})
        assert r.status_code == 201 and r.json()["name"].startswith("Prova ")
        url = f"/api/coverage/sessions/{r.json()['id']}"
        assert (await c.patch(url, json={"name": " "})).status_code == 400
        assert (await c.patch(url, json={"base_lat": 10, "base_lon": 181})).status_code == 400
        q = env.bus.subscribe()
        assert (await c.patch(url, json={"notes": "x"})).status_code == 200
        assert q.get_nowait()["type"] == "coverage"
