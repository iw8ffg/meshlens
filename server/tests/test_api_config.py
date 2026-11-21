import asyncio
import json

from meshlens.config_model import MASK
from meshlens.config_service import ConfigService
from meshlens.radio import MSG_ADMIN_UNAUTH, AdminError
from test_api import client, logged
from test_api_radios import make_ctx
from test_config_service import MQTT, REMOTE, WIFI, CfgConnector, secrets_in
from test_radio_manager import MY_ID, Env, FakeConnector


async def make_env():
    e = Env()
    e.mgr._connector_factory = CfgConnector
    await e.mgr.add("usb", "COM5", "H")
    conn = FakeConnector.instances[0]
    conn.store = e.store

    async def nosleep(_s):
        await asyncio.sleep(0)

    ctx = make_ctx(e)
    ctx.config = ConfigService(e.store, e.mgr, e.live, e.bus, clock=lambda: e.now,
                               sleep=nosleep)
    return e, ctx, conn


async def finish(ctx, job):
    await ctx.config.join(job["id"])


async def test_requires_auth():
    e, ctx, conn = await make_env()
    async with client(ctx) as c:
        for path in ("/api/config/schema", f"/api/config/{MY_ID}",
                     f"/api/config/{MY_ID}/backups", "/api/config/jobs/1",
                     "/api/config/backups/1", "/api/radios/r1/admin-key"):
            assert (await c.get(path)).status_code == 401
        for path in (f"/api/config/{MY_ID}/read", f"/api/config/{MY_ID}/apply"):
            assert (await c.post(path, json={})).status_code == 401


async def test_schema_route():
    e, ctx, conn = await make_env()
    async with logged(ctx) as c:
        sch = (await c.get("/api/config/schema")).json()
        assert "lora" in sch["config"] and sch["config"]["lora"]["hop_limit"]["max"] > 0
        assert sch["config"]["security"]["private_key"]["secret"] is True


async def test_admin_key_route():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        r = await c.get(f"/api/radios/{rid}/admin-key")
        assert r.status_code == 200 and list(r.json()) == ["public_key_b64"]
        assert (await c.get("/api/radios/rnope/admin-key")).status_code == 404


async def test_error_statuses():
    e, ctx, conn = await make_env()
    async with logged(ctx) as c:
        assert (await c.get(f"/api/config/{MY_ID}")).status_code == 404
        assert (await c.get("/api/config/nodo")).status_code == 404
        r = await c.post(f"/api/config/{MY_ID}/preview",
                         json={"changes": {"config.lora.hop_limit": 4}})
        assert r.status_code == 409 and r.json()["detail"] == "Leggi prima la configurazione"
        r = await c.post(f"/api/config/{MY_ID}/apply", json={"preview_id": "x"})
        assert r.status_code == 400
        r = await c.post(f"/api/config/{MY_ID}/reboot", json={})
        assert r.status_code == 400 and r.json()["detail"] == "Conferma richiesta"
        assert (await c.get("/api/config/jobs/99")).status_code == 404
        assert (await c.get("/api/config/backups/99")).status_code == 404
        job = (await c.post(f"/api/config/{MY_ID}/read", json={})).json()
        await finish(ctx, job)
        r = await c.post(f"/api/config/{MY_ID}/preview",
                         json={"changes": {"config.lora.hop_limit": "tanti"}})
        assert r.status_code == 400
        r = await c.post(f"/api/config/{MY_ID}/read", json={"radio_id": "rnope"})
        assert r.status_code == 404


async def test_secrets_never_in_responses():
    """Review Focus 3: flusso completo, nessun segreto in risposte e messaggi del bus."""
    e, ctx, conn = await make_env()
    bodies = []
    async with logged(ctx) as c:
        async def call(method, path, **kw):
            r = await getattr(c, method)(path, **kw)
            bodies.append(r.text)
            return r

        r = await call("post", f"/api/config/{MY_ID}/read", json={})
        assert r.status_code == 202
        await finish(ctx, r.json())
        last = (await call("get", f"/api/config/{MY_ID}")).json()
        assert last["config"]["config"]["network"]["wifi_psk"] == MASK
        await call("get", "/api/config/schema")
        r = await call("post", f"/api/config/{MY_ID}/preview", json={"changes": {
            "config.network.wifi_psk": "NUOVASEGRETA-9", "config.lora.hop_limit": 4,
            "module_config.mqtt.password": "NUOVAMQTT-9", "channels.1.name": "x"}})
        pv = r.json()
        assert r.status_code == 200 and pv["risky"] is False
        r = await call("post", f"/api/config/{MY_ID}/apply",
                       json={"preview_id": pv["preview_id"]})
        assert r.status_code == 202
        await finish(ctx, r.json())
        job = (await call("get", f"/api/config/jobs/{r.json()['id']}")).json()
        assert job["status"] == "done" and job["verify"] == "verified"
        backups = (await call("get", f"/api/config/{MY_ID}/backups")).json()
        assert len(backups) == 1 and "config" not in backups[0]
        detail = (await call("get", f"/api/config/backups/{backups[0]['id']}")).json()
        assert detail["config"]["config"]["network"]["wifi_psk"] == MASK
        assert detail["config"]["module_config"]["mqtt"]["password"] == MASK
        r = await call("post", f"/api/config/backups/{backups[0]['id']}/preview-restore",
                       json={})
        assert r.status_code == 200
        r = await call("post", f"/api/config/{MY_ID}/apply",
                       json={"preview_id": r.json()["preview_id"]})
        await finish(ctx, r.json())
        # richiesta esplicita: l'unica risposta con una psk in chiaro
        r = await c.post(f"/api/config/{MY_ID}/channels/0/reveal-psk", json={})
        assert r.status_code == 200 and "psk" in r.json()
    everything = "\n".join(bodies) + json.dumps(e.drain())
    assert secrets_in(everything) == []
    assert "NUOVASEGRETA-9" not in everything and "NUOVAMQTT-9" not in everything
    assert conn.nodes[None]["config"].network.wifi_psk == WIFI  # ripristinato dalla copia
    assert conn.nodes[None]["module_config"].mqtt.password == MQTT


async def test_job_failure_carries_error_code():
    e, ctx, conn = await make_env()
    conn.read_error = AdminError("unauthorized", MSG_ADMIN_UNAUTH)
    async with logged(ctx) as c:
        r = await c.post(f"/api/config/{REMOTE}/read", json={"sections": ["lora"]})
        assert r.status_code == 202
        await finish(ctx, r.json())
        job = (await c.get(f"/api/config/jobs/{r.json()['id']}")).json()
        assert job["status"] == "failed" and job["error_code"] == "unauthorized"
        assert job["error"] == MSG_ADMIN_UNAUTH


async def test_reboot_and_fixed_position_routes():
    e, ctx, conn = await make_env()
    async with logged(ctx) as c:
        r = await c.post(f"/api/config/{MY_ID}/reboot", json={"confirm": True})
        assert r.status_code == 202 and r.json()["kind"] == "reboot"
        await finish(ctx, r.json())
        r = await c.post(f"/api/config/{MY_ID}/fixed-position",
                         json={"lat": 45.0, "lon": 9.0, "alt": 10, "confirm": True})
        assert r.status_code == 202
        await finish(ctx, r.json())
        r = await c.post(f"/api/config/{MY_ID}/fixed-position",
                         json={"remove": True, "confirm": True})
        await finish(ctx, r.json())
        assert conn.fixed == [(None, 45.0, 9.0, 10), (None, None)]
        r = await c.post(f"/api/config/{MY_ID}/fixed-position", json={"lat": 1, "lon": 1})
        assert r.status_code == 400
