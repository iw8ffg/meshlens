import numpy as np
from test_api import client, logged, make_ctx
from test_prediction_service import PARAMS, TILES, FakeCache, make

from meshlens.prediction import Grid, SiteParams


def ctx_with(tmp_path, cache=None):
    ctx = make_ctx()
    ctx.prediction, _ = make(tmp_path, cache)
    return ctx


def put_result(m):
    g = np.full((10, 10), -5, dtype=np.int8)
    g[:, :5] = 5
    return m._save(SiteParams.from_dict({"lat": 40.5, "lon": 10.5, "radius_km": 3}), "T",
                   Grid(bbox=[10.0, 40.0, 11.0, 41.0], width=10, height=10, values=g))


async def test_requires_auth(tmp_path):
    ctx = ctx_with(tmp_path)
    async with client(ctx) as c:
        assert (await c.post("/api/prediction/estimate", json=PARAMS)).status_code == 401
        assert (await c.post("/api/prediction/jobs", json={"params": PARAMS})).status_code == 401
        assert (await c.post("/api/prediction/jobs/x/cancel", json={})).status_code == 401
        assert (await c.get("/api/predictions")).status_code == 401
        assert (await c.get("/api/predictions/p1-abcdef")).status_code == 401
        assert (await c.request("DELETE", "/api/predictions/p1-abcdef", json={})).status_code == 401
        assert (await c.get("/api/predictions/p1-abcdef/compare?session_id=1")).status_code == 401


async def test_estimate_and_validation(tmp_path):
    ctx = ctx_with(tmp_path, FakeCache(TILES[:1]))
    async with logged(ctx) as c:
        r = await c.post("/api/prediction/estimate", json=PARAMS)
        assert r.status_code == 200
        assert r.json()["tiles_missing"] == len(TILES) - 1 and len(r.json()["bbox"]) == 4
        r = await c.post("/api/prediction/estimate", json={**PARAMS, "tx_power_dbm": 31})
        assert r.status_code == 400 and "tx_power_dbm" in r.json()["detail"]
        r = await c.post("/api/prediction/jobs", json={"params": {**PARAMS, "radius_km": 0}})
        assert r.status_code == 400 and "radius_km" in r.json()["detail"]


async def test_jobs_errors_and_lifecycle(tmp_path):
    ctx = ctx_with(tmp_path, FakeCache(TILES[:1]))
    async with logged(ctx) as c:
        r = await c.post("/api/prediction/jobs", json={"params": PARAMS, "name": "X"})
        assert r.status_code == 409
        assert r.json()["code"] == "elevation_missing" and "Mancano" in r.json()["detail"]
        r = await c.post("/api/prediction/jobs", json={"params": PARAMS, "download": True})
        assert r.status_code == 202 and r.json()["status"] == "running"
        r2 = await c.post("/api/prediction/jobs", json={"params": PARAMS, "download": True})
        assert r2.status_code == 409 and r2.json()["detail"] == "C'è già un calcolo in corso"
        await ctx.prediction._task
        items = (await c.get("/api/predictions")).json()
        assert len(items) == 1 and items[0]["id"] == ctx.prediction.job["result_id"]
        assert (await c.post("/api/prediction/jobs/zzz/cancel", json={})).status_code == 404
        cancel = await c.post(f"/api/prediction/jobs/{r.json()['id']}/cancel", json={})
        assert cancel.status_code == 200 and cancel.json()["status"] == "done"


async def test_get_delete_404(tmp_path):
    ctx = ctx_with(tmp_path)
    pid = put_result(ctx.prediction)
    async with logged(ctx) as c:
        assert (await c.get("/api/predictions/p1-abcdef")).status_code == 404
        assert (await c.get("/api/predictions/..%2Fx")).status_code == 404
        r = await c.get(f"/api/predictions/{pid}")
        assert r.status_code == 200 and r.json()["nodata"] == -128 and r.json()["width"] == 10
        assert (await c.request("DELETE", f"/api/predictions/{pid}", json={})).status_code == 204
        assert (await c.request("DELETE", f"/api/predictions/{pid}", json={})).status_code == 404
        assert (await c.get("/api/predictions")).json() == []


async def test_compare(tmp_path):
    ctx = ctx_with(tmp_path)
    pid = put_result(ctx.prediction)
    s = ctx.store
    sid = s.create_session(name="p", radio_id="r", mobile_num=1, mode="rangetest",
                           interval_s=30, started=100)
    for seq, t, lon, rssi in ((1, 100, 10.2, -120), (2, 110, 10.3, -120), (4, 130, 10.8, -130)):
        s.add_point(sid, 0, seq, t, 5.0, rssi, 0, 40.5, lon, 32)
        s.add_track(sid, t, 40.5, 10.2 + (t - 100) * 0.02, 32)
    async with logged(ctx) as c:
        r = await c.get(f"/api/predictions/{pid}/compare", params={"session_id": sid})
        assert r.status_code == 200
        b = r.json()
        assert (b["received"], b["missing"]) == (3, 1)
        assert (b["received_covered"], b["received_uncovered"], b["missing_uncovered"]) == (2, 1, 1)
        assert b["agreement_pct"] == 75.0 and b["rssi_bias_db"] == -6.5
        assert set(b) >= {"missing_covered", "outside", "rssi_rmse_db", "points"}
        r = await c.get(f"/api/predictions/{pid}/compare", params={"session_id": 999})
        assert r.status_code == 404
        r = await c.get("/api/predictions/p1-abcdef/compare", params={"session_id": sid})
        assert r.status_code == 404


async def test_unavailable(tmp_path):
    ctx = make_ctx()
    async with logged(ctx) as c:
        assert (await c.get("/api/predictions")).status_code == 503
