from test_api import client, logged, make_ctx
from test_maps import FakeRunner, make_manager


async def test_requires_auth(tmp_path):
    ctx = make_ctx()
    ctx.maps = make_manager(tmp_path)
    async with client(ctx) as c:
        assert (await c.get("/api/maps")).status_code == 401
        assert (await c.post("/api/maps/estimate", json={"kind": "world"})).status_code == 401
        assert (await c.post("/api/maps/download", json={"kind": "world"})).status_code == 401
        assert (await c.post("/api/maps/jobs/x/cancel")).status_code == 401
        assert (await c.delete("/api/maps/world")).status_code == 401


async def test_status_estimate_download_delete(tmp_path):
    ctx = make_ctx()
    ctx.maps = make_manager(tmp_path, install_tool=True)
    async with logged(ctx) as c:
        s = (await c.get("/api/maps")).json()
        assert s["maps"] == [] and s["job"] is None and s["mode"] == "auto"
        assert s["tool"]["installed"] is True and s["disk_free_bytes"] > 0
        r = await c.post("/api/maps/estimate", json={"kind": "world"})
        assert r.status_code == 200 and r.json()["estimate_bytes"] == 200_000_000
        r = await c.post("/api/maps/download", json={"kind": "world"})
        assert r.status_code == 202 and r.json()["status"] == "running"
        await ctx.maps._task
        assert [m["id"] for m in (await c.get("/api/maps")).json()["maps"]] == ["world"]
        assert (await c.delete("/api/maps/world")).status_code == 200
        assert (await c.delete("/api/maps/world")).status_code == 404


async def test_errors_mapped(tmp_path):
    ctx = make_ctx()
    ctx.maps = make_manager(tmp_path, install_tool=True, disk_free=lambda p: 0)
    async with logged(ctx) as c:
        r = await c.post("/api/maps/download", json={"kind": "area", "bbox": [5, 5, 1, 1]})
        assert r.status_code == 400
        r = await c.post("/api/maps/download", json={"kind": "area"})
        assert r.status_code == 400
        r = await c.post("/api/maps/download", json={"kind": "world"})
        assert r.status_code == 409 and "Spazio su disco insufficiente" in r.json()["detail"]
        assert (await c.post("/api/maps/download", json={"kind": "boh"})).status_code == 422
        assert (await c.post("/api/maps/jobs/zzz/cancel")).status_code == 404
        ctx.maps.head = lambda u: 404
        r = await c.post("/api/maps/estimate", json={"kind": "world"})
        assert r.status_code == 502
        assert r.json()["detail"] == "Nessuna mappa Protomaps disponibile negli ultimi 7 giorni"


async def test_cancel_route_and_settings(tmp_path):
    runner = FakeRunner(hang=True)
    ctx = make_ctx()
    ctx.maps = make_manager(tmp_path, runner=runner, install_tool=True)
    async with logged(ctx) as c:
        job = (await c.post("/api/maps/download", json={"kind": "italy"})).json()
        await runner.started.wait()
        r = await c.post("/api/maps/download", json={"kind": "world"})
        assert r.status_code == 409
        r = await c.post(f"/api/maps/jobs/{job['id']}/cancel")
        assert r.status_code == 200 and r.json()["status"] == "cancelled"
        r = await c.put("/api/settings", json={"map_mode": "offline",
                                               "maps_source_url": "https://a.b/c.pmtiles"})
        assert r.status_code == 200 and r.json()["map_mode"] == "offline"
        assert (await c.put("/api/settings", json={"map_mode": "x"})).status_code == 400
