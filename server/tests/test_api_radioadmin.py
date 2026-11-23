import time

from meshtastic.protobuf import config_pb2

from meshlens import api_channels, api_nodeflags, api_profiles, api_radioadmin, ext_radio
from test_api import client, logged
from test_api_config import finish, make_env
from test_config_service import REMOTE, secrets_in
from test_radio_manager import MY_ID

PEER = "!00000042"
PEER_NUM = 0x42
BODIES: list[str] = []  # corpi di tutte le risposte (nessun segreto)


def _keep(r):
    BODIES.append(r.text)
    return r


async def env_with_peer():
    e, ctx, conn = await make_env()
    e.live.nodes[PEER_NUM] = {"id": PEER, "num": PEER_NUM, "long_name": "Altro",
                              "short_name": "AL", "last_heard": time.time(), "is_ignored": False}
    e.store.upsert_node(e.live.nodes[PEER_NUM])
    e.store.commit()
    return e, ctx, conn


GETS = [f"/api/nodes/{PEER}/radio-flags", f"/api/config/{MY_ID}/admin",
        f"/api/config/{MY_ID}/canned", "/api/privacy", "/api/nodes/ignored"]
WRITES = [("PUT", f"/api/nodes/{PEER}/ignored"), ("PUT", f"/api/nodes/{PEER}/radio-flags"),
          ("POST", f"/api/config/{MY_ID}/admin"), ("PUT", f"/api/config/{MY_ID}/canned"),
          ("POST", f"/api/privacy/{MY_ID}/preview")]


async def test_routes_require_auth_and_json():
    e, ctx, conn = await env_with_peer()
    async with client(ctx) as c:
        for path in GETS:
            assert (await c.get(path)).status_code == 401, path
        for method, path in WRITES:
            assert (await c.request(method, path, json={})).status_code == 401, path
    async with logged(ctx) as c:
        for method, path in WRITES:
            r = await c.request(method, path, content=b"{}",
                                headers={"Content-Type": "text/plain"})
            assert r.status_code == 415, path


async def test_ignore_node_hides_and_syncs_radio():
    e, ctx, conn = await env_with_peer()
    rid = e.mgr.radios()[0]["id"]
    q = ctx.bus.subscribe()
    async with logged(ctx) as c:
        r = _keep(await c.put(f"/api/nodes/{PEER}/ignored", json={"ignored": True}))
        assert r.status_code == 200
        body = r.json()
        assert body["node"]["is_ignored"] is True
        assert body["radios"] == [{"radio_id": rid, "ok": True, "error": None}]
        assert e.store.get_node(PEER_NUM)["is_ignored"] is True
        assert conn.flag_calls == [(PEER_NUM, "ignored", True)]
        assert PEER_NUM in [n["num"] for n in ctx.live.take_changed()]
        msgs = []
        while not q.empty():
            msgs.append(q.get_nowait())
        assert {"type": "resync"} in msgs
        lst = _keep(await c.get("/api/nodes/ignored"))
        assert lst.status_code == 200 and [n["id"] for n in lst.json()] == [PEER]
        r = await c.put(f"/api/nodes/{PEER}/ignored", json={"ignored": False, "radio": False})
        assert r.status_code == 200 and r.json()["radios"] == []
        assert conn.flag_calls == [(PEER_NUM, "ignored", True)]
        assert (await c.get("/api/nodes/ignored")).json() == []
        assert (await c.put("/api/nodes/!00000999/ignored",
                            json={"ignored": True})).status_code == 404


async def test_ignored_list_includes_nodes_not_in_memory():
    e, ctx, conn = await env_with_peer()
    async with logged(ctx) as c:
        await c.put(f"/api/nodes/{PEER}/ignored", json={"ignored": True, "radio": False})
        del e.live.nodes[PEER_NUM]
        r = await c.get("/api/nodes/ignored")
        assert [n["id"] for n in r.json()] == [PEER] and r.json()[0]["is_ignored"] is True


async def test_ignore_own_radio_node_refused():
    e, ctx, conn = await env_with_peer()
    async with logged(ctx) as c:
        r = _keep(await c.put(f"/api/nodes/{MY_ID}/ignored", json={"ignored": True}))
        assert r.status_code == 400
        assert r.json()["detail"] == "Non puoi ignorare il nodo di una tua radio"


async def test_ignore_radio_error_keeps_local_flag():
    e, ctx, conn = await env_with_peer()
    conn.busy = True
    async with logged(ctx) as c:
        r = _keep(await c.put(f"/api/nodes/{PEER}/ignored", json={"ignored": True}))
        assert r.status_code == 200 and r.json()["node"]["is_ignored"] is True
        assert r.json()["radios"][0]["ok"] is False
        assert r.json()["radios"][0]["error"] == "Radio occupata, riprova tra poco"


async def test_radio_flags_get_and_put():
    e, ctx, conn = await env_with_peer()
    conn.flags = {PEER_NUM: {"favorite": True, "ignored": False, "muted": None}}
    async with logged(ctx) as c:
        r = _keep(await c.get(f"/api/nodes/{PEER}/radio-flags"))
        assert r.status_code == 200 and r.json()["radios"][0]["favorite"] is True
        r = _keep(await c.put(f"/api/nodes/{PEER}/radio-flags", json={"favorite": False}))
        assert r.status_code == 200 and r.json()["radios"][0]["ok"] is True
        assert (PEER_NUM, "favorite", False) in conn.flag_calls
        r = await c.put(f"/api/nodes/{PEER}/radio-flags", json={})
        assert r.status_code == 400 and r.json()["detail"] == "Nessun flag indicato"
        r = await c.put(f"/api/nodes/{PEER}/radio-flags", json={"favorite": True, "boh": 1})
        assert r.status_code == 422


async def test_admin_status_and_command_routes():
    e, ctx, conn = await env_with_peer()
    async with logged(ctx) as c:
        r = _keep(await c.get(f"/api/config/{MY_ID}/admin"))
        assert r.status_code == 200 and r.json()["local"] is True
        r = await c.post(f"/api/config/{MY_ID}/admin", json={"command": "set_time"})
        assert r.status_code == 400 and r.json()["detail"] == "Conferma richiesta"
        r = await c.post(f"/api/config/{MY_ID}/admin",
                         json={"command": "set_time", "confirm": "true"})
        assert r.status_code == 422  # conferma solo booleana
        r = _keep(await c.post(f"/api/config/{MY_ID}/admin",
                               json={"command": "set_time", "confirm": True}))
        assert r.status_code == 202 and r.json()["kind"] == "set_time"
        await finish(ctx, r.json())
        r = _keep(await c.post(f"/api/config/{REMOTE}/admin",
                               json={"command": "reboot", "confirm": True}))
        assert r.status_code == 409


async def test_canned_routes():
    e, ctx, conn = await env_with_peer()
    conn.canned = "Ciao|OK"
    async with logged(ctx) as c:
        r = _keep(await c.get(f"/api/config/{MY_ID}/canned"))
        assert r.status_code == 200 and r.json()["messages"] == ["Ciao", "OK"]
        r = _keep(await c.put(f"/api/config/{MY_ID}/canned", json={"messages": ["è" * 101]}))
        assert r.status_code == 400
        assert r.json()["detail"] == "Troppo lunghi: 202 byte su 200 (separatori compresi)"
        r = _keep(await c.put(f"/api/config/{MY_ID}/canned", json={"messages": ["A", "B"]}))
        assert r.status_code == 200 and conn.canned_calls == [(None, "A|B")]
        r = await c.put(f"/api/config/{MY_ID}/canned", json={"messages": ["x"] * 51})
        assert r.status_code == 422
        conn.busy = True
        r = _keep(await c.put(f"/api/config/{MY_ID}/canned", json={"messages": ["A"]}))
        assert r.status_code == 409


async def test_privacy_routes():
    e, ctx, conn = await env_with_peer()
    p = conn.nodes[None]
    p["channels"][0].settings.psk = b"\x01"
    p["channels"][0].settings.module_settings.position_precision = 32
    p["config"].position.gps_mode = config_pb2.Config.PositionConfig.ENABLED
    async with logged(ctx) as c:
        r = _keep(await c.get("/api/privacy"))
        assert r.status_code == 200 and r.json()["radios"][0]["risks"]
        r = _keep(await c.post(f"/api/privacy/{MY_ID}/preview", json={"bits": 14}))
        assert r.status_code == 409 and r.json()["detail"] == "Leggi prima la configurazione"
        job = (await c.post(f"/api/config/{MY_ID}/read", json={})).json()
        await finish(ctx, job)
        r = _keep(await c.post(f"/api/privacy/{MY_ID}/preview",
                               json={"bits": 14, "channels": None}))
        assert r.status_code == 200
        assert r.json()["changes"][0]["path"] == "channels.0.position_precision"


async def test_missing_services_503():
    e, ctx, conn = await env_with_peer()
    ctx.config = None
    async with logged(ctx) as c:
        r = await c.get("/api/privacy")
        assert r.status_code == 503 and r.json()["detail"] == "Configurazione radio non disponibile"
        assert (await c.get(f"/api/config/{MY_ID}/canned")).status_code == 503
        # "Ignora" funziona anche senza servizio radio
        r = await c.put(f"/api/nodes/{PEER}/ignored", json={"ignored": True})
        assert r.status_code == 200 and r.json()["radios"] == []


def test_guest_paths_empty():
    for mod in (api_radioadmin, api_nodeflags, api_profiles, api_channels):
        assert mod.GUEST_GET_PATHS == ()


def test_ext_radio_installs_profiles():
    from types import SimpleNamespace
    from meshlens.db import connect
    from meshlens.profiles import ProfileStore
    ctx = SimpleNamespace(conn=connect(":memory:"), ext={})
    ext_radio.install(None, ctx)
    assert isinstance(ctx.ext["profiles"], ProfileStore)


def test_no_secret_in_any_response():
    assert BODIES
    assert secrets_in("\n".join(BODIES)) == []
