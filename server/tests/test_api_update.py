from test_api import client, logged, make_ctx
from test_updater import FakeHttp, TOKEN, make


async def test_requires_auth():
    ctx = make_ctx()
    async with client(ctx) as c:
        assert (await c.get("/api/update/status")).status_code == 401
        assert (await c.post("/api/update/check", json={})).status_code == 401
        assert (await c.post("/api/update/download", json={})).status_code == 401
        assert (await c.post("/api/update/install", json={"confirm": True})).status_code == 401


async def test_flow(tmp_path):
    ctx = make_ctx()
    ctx.updater = make(tmp_path)
    async with logged(ctx) as c:
        s = (await c.get("/api/update/status")).json()
        assert s["latest"] is None and s["job"] is None and s["can_install"] is False
        s = (await c.post("/api/update/check", json={})).json()
        assert s["available"] and s["latest"] == "1.0.1"
        r = await c.post("/api/update/download", json={})
        assert r.status_code == 202 and r.json()["status"] == "running"
        await ctx.updater._task
        assert (await c.get("/api/update/status")).json()["can_install"] is True
        assert (await c.post("/api/update/install", json={})).status_code == 400
        r = await c.post("/api/update/install", json={"confirm": True})
        assert r.status_code == 202 and r.json() == {"ok": True}
        assert ctx.updater.exits == [2.0]


async def test_dev_install_409_and_download_without_update(tmp_path):
    ctx = make_ctx()
    ctx.updater = make(tmp_path, frozen=False)
    async with logged(ctx) as c:
        assert (await c.post("/api/update/download", json={})).status_code == 409
        await c.post("/api/update/check", json={})
        r = await c.post("/api/update/install", json={"confirm": True})
        assert r.status_code == 409
        assert r.json()["detail"] == "Disponibile solo nella versione installata"


async def test_check_error_in_status(tmp_path):
    ctx = make_ctx()
    ctx.updater = make(tmp_path, FakeHttp(status=404), token="")
    async with logged(ctx) as c:
        r = await c.post("/api/update/check", json={})
        assert r.status_code == 200 and "Repository privato" in r.json()["error"]


async def test_get_settings_still_masks_token():
    ctx = make_ctx()
    async with logged(ctx) as c:
        await c.put("/api/settings", json={"update_token": TOKEN})
        r = await c.get("/api/settings")
        assert r.json()["update_token"] == "••••" and TOKEN not in r.text
        stored = ctx.conn.execute("SELECT value FROM settings WHERE key='update_token'").fetchone()[0]
        assert TOKEN not in stored


async def test_token_masked_in_settings():
    ctx = make_ctx()
    async with logged(ctx) as c:
        s = (await c.get("/api/settings")).json()
        assert s["update_token"] == "" and s["update_repo"] == "iw8ffg/meshlens"
        assert s["update_auto_check"] is True
        r = await c.put("/api/settings", json={"update_token": TOKEN})
        assert r.json()["update_token"] == "••••" and TOKEN not in r.text
        assert TOKEN not in (await c.get("/api/settings")).text
        r = await c.put("/api/settings", json={"update_token": "••••", "update_auto_check": False})
        assert r.json()["update_auto_check"] is False
        from meshlens.settings import load_settings
        assert load_settings(ctx.conn)["update_token"] == TOKEN  # invariato
        assert (await c.put("/api/settings", json={"update_repo": "senza-slash"})).status_code == 400
        assert (await c.put("/api/settings", json={"update_auto_check": "si"})).status_code == 400
        assert (await c.put("/api/settings", json={"update_token": 5})).status_code == 400
