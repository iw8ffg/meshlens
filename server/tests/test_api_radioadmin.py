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


# ---- profili e canali (Task 7) ----

async def profile_env():
    e, ctx, conn = await env_with_peer()
    ext_radio.install(None, ctx)
    return e, ctx, conn


async def read(c, ctx, node_id, sections=None):
    body = {} if sections is None else {"sections": sections}
    job = (await c.post(f"/api/config/{node_id}/read", json=body)).json()
    await finish(ctx, job)


async def test_profile_save_list_get_without_secrets():
    e, ctx, conn = await profile_env()
    e.live.nodes[int(MY_ID[1:], 16)] = {"id": MY_ID, "num": int(MY_ID[1:], 16),
                                        "hw_model": "HELTEC_V3", "firmware": "2.7.11"}
    async with logged(ctx) as c:
        await read(c, ctx, MY_ID)
        r = _keep(await c.post("/api/profiles", json={"node_id": MY_ID, "name": "Base"}))
        assert r.status_code == 201
        prof = r.json()
        assert prof["source_node_id"] == MY_ID and prof["source_hw"] == "HELTEC_V3"
        assert prof["firmware"] == "2.7.11" and "config.lora" in prof["sections"]
        lst = _keep(await c.get("/api/profiles"))
        assert lst.status_code == 200 and len(lst.json()) == 1 and "data" not in lst.json()[0]
        det = _keep(await c.get(f"/api/profiles/{prof['id']}"))
        data = det.json()["data"]
        assert "security" not in data["config"] and "region" not in data["config"]["lora"]
        assert "wifi_psk" not in data["config"]["network"]
        assert "wifi_ssid" not in data["config"]["network"]
        assert "password" not in data["module_config"]["mqtt"]
    dump = "\n".join(row["data"] for row in ctx.conn.execute("SELECT data FROM config_profiles"))
    assert secrets_in(dump) == []


async def test_profile_save_errors():
    e, ctx, conn = await profile_env()
    async with logged(ctx) as c:
        r = await c.post("/api/profiles", json={"node_id": MY_ID, "name": "Base"})
        assert r.status_code == 404
        assert r.json()["detail"] == "Nessuna configurazione letta per questo nodo"
        await read(c, ctx, MY_ID)
        r = await c.post("/api/profiles", json={"node_id": MY_ID, "name": "Base",
                                                "sections": ["config.security"]})
        assert r.status_code == 400 and r.json()["detail"] == "Sezione non copiabile: config.security"
        assert (await c.post("/api/profiles", json={"node_id": MY_ID,
                                                    "name": "Base"})).status_code == 201
        r = await c.post("/api/profiles", json={"node_id": MY_ID, "name": "Base"})
        assert r.status_code == 409
        r = await c.post("/api/profiles", json={"node_id": MY_ID, "name": "  "})
        assert r.status_code == 400


async def test_profile_saved_from_partial_remote_read_keeps_read_sections_only():
    e, ctx, conn = await profile_env()
    async with logged(ctx) as c:
        await read(c, ctx, REMOTE, ["config.lora"])
        r = await c.post("/api/profiles", json={"node_id": REMOTE, "name": "Parziale"})
        assert r.status_code == 201 and r.json()["sections"] == ["config.lora"]
        assert r.json()["source_node_id"] == REMOTE


async def test_profile_preview_and_apply_on_other_node():
    from test_config_service import PRIV, REMOTE_NUM
    e, ctx, conn = await profile_env()
    async with logged(ctx) as c:
        await read(c, ctx, MY_ID)
        pid = (await c.post("/api/profiles", json={"node_id": MY_ID, "name": "Base"})).json()["id"]
        conn.nodes[REMOTE_NUM]["config"].lora.hop_limit = 6
        conn.nodes[REMOTE_NUM]["config"].lora.region = config_pb2.Config.LoRaConfig.US
        await read(c, ctx, REMOTE)
        r = _keep(await c.post(f"/api/profiles/{pid}/preview", json={"node_id": REMOTE}))
        assert r.status_code == 200, r.text
        changes = r.json()["preview"]["changes"]
        assert {"path": "config.lora.hop_limit", "old": 6, "new": 3} == {
            k: changes[0][k] for k in ("path", "old", "new")}
        assert all(not ch["path"].startswith("config.security") for ch in changes)
        assert all(ch["path"] != "config.lora.region" for ch in changes)
        r = await c.post(f"/api/config/{REMOTE}/apply",
                         json={"preview_id": r.json()["preview"]["preview_id"],
                               "confirm_risky": True})
        assert r.status_code == 202
        await finish(ctx, r.json())
        assert ctx.config.job(r.json()["id"])["status"] == "done"
        written = conn.writes[-1][1]
        assert written["config"].lora.hop_limit == 3
        assert written["config"].security.private_key == PRIV
        assert written["config"].lora.region == config_pb2.Config.LoRaConfig.US


async def test_profile_preview_nothing_to_change_and_needs_read():
    e, ctx, conn = await profile_env()
    async with logged(ctx) as c:
        await read(c, ctx, MY_ID)
        pid = (await c.post("/api/profiles", json={"node_id": MY_ID, "name": "Base"})).json()["id"]
        r = await c.post(f"/api/profiles/{pid}/preview", json={"node_id": MY_ID})
        assert r.status_code == 400
        assert r.json()["detail"] == "Il profilo non cambia nulla su questa radio"
        r = await c.post(f"/api/profiles/{pid}/preview", json={"node_id": REMOTE})
        assert r.status_code == 409 and r.json()["detail"] == "Leggi prima la configurazione"
        r = await c.post("/api/profiles/999/preview", json={"node_id": MY_ID})
        assert r.status_code == 404


async def test_profile_preview_skips_tampered_fields():
    import json as _json
    e, ctx, conn = await profile_env()
    async with logged(ctx) as c:
        await read(c, ctx, MY_ID)
        pid = (await c.post("/api/profiles", json={"node_id": MY_ID, "name": "Base"})).json()["id"]
        data = _json.loads(ctx.conn.execute("SELECT data FROM config_profiles WHERE id=?",
                                            (pid,)).fetchone()[0])
        data["config"]["lora"]["region"] = "US"
        data["config"]["lora"]["hop_limit"] = 5
        data["config"]["security"] = {"private_key": "QUJD"}
        ctx.conn.execute("UPDATE config_profiles SET data=? WHERE id=?", (_json.dumps(data), pid))
        ctx.conn.commit()
        r = _keep(await c.post(f"/api/profiles/{pid}/preview", json={"node_id": MY_ID}))
        assert r.status_code == 200
        paths = [ch["path"] for ch in r.json()["preview"]["changes"]]
        assert paths == ["config.lora.hop_limit"]
        assert {"config.lora.region", "config.security.private_key"} <= set(r.json()["skipped"])


async def test_profile_compare_nodes_and_profile():
    from test_config_service import REMOTE_NUM
    e, ctx, conn = await profile_env()
    async with logged(ctx) as c:
        await read(c, ctx, MY_ID)
        conn.nodes[REMOTE_NUM]["config"].lora.hop_limit = 6
        r = _keep(await c.get(f"/api/profiles/compare?a={MY_ID}&b={REMOTE}"))
        assert r.status_code == 404
        await read(c, ctx, REMOTE)
        r = _keep(await c.get(f"/api/profiles/compare?a={MY_ID}&b={REMOTE}"))
        assert r.status_code == 200
        body = r.json()
        assert body["rows"] == [{"path": "config.lora.hop_limit", "a": 3, "b": 6,
                                 "excluded": False}]
        assert body["a"]["time"] and body["b"]["label"]
        pid = (await c.post("/api/profiles", json={"node_id": MY_ID, "name": "Base"})).json()["id"]
        r = _keep(await c.get(f"/api/profiles/compare?profile={pid}&b={REMOTE}"
                              "&sections=config.lora,config.device"))
        assert r.status_code == 200 and r.json()["a"]["label"] == "Base"
        assert [x["path"] for x in r.json()["rows"]] == ["config.lora.hop_limit"]
        assert r.json()["sections"] == ["config.device", "config.lora"]
        r = await c.get(f"/api/profiles/compare?a={MY_ID}")
        assert r.status_code in (400, 422)


async def test_profile_rename_delete_export_import():
    e, ctx, conn = await profile_env()
    async with logged(ctx) as c:
        await read(c, ctx, MY_ID)
        pid = (await c.post("/api/profiles", json={"node_id": MY_ID, "name": "Base",
                                                   "notes": "nota"})).json()["id"]
        r = _keep(await c.put(f"/api/profiles/{pid}", json={"name": "Nuovo"}))
        assert r.status_code == 200 and r.json()["name"] == "Nuovo" and r.json()["notes"] == "nota"
        r = await c.put(f"/api/profiles/{pid}", json={"notes": None})
        assert r.json()["notes"] is None and r.json()["name"] == "Nuovo"
        r = _keep(await c.get(f"/api/profiles/{pid}/export"))
        assert r.status_code == 200 and r.json()["format"] == "meshlens-profile"
        assert "attachment" in r.headers["content-disposition"]
        assert f"profilo-{pid}.json" in r.headers["content-disposition"]
        doc = r.json()
        r = _keep(await c.post("/api/profiles/import", json={"profile": doc, "name": "Copia"}))
        assert r.status_code == 201 and r.json()["source_node_id"] is None
        assert r.json()["name"] == "Copia"
        r = await c.post("/api/profiles/import", json={"profile": {"format": "x"}})
        assert r.status_code == 400
        r = await c.request("DELETE", f"/api/profiles/{pid}", json={})
        assert r.status_code == 400 and r.json()["detail"] == "Conferma richiesta"
        r = await c.request("DELETE", f"/api/profiles/{pid}", json={"confirm": True})
        assert r.status_code == 200 and r.json() == {"ok": True}
        assert (await c.get(f"/api/profiles/{pid}")).status_code == 404


async def test_profile_routes_503_without_ext():
    e, ctx, conn = await env_with_peer()
    async with logged(ctx) as c:
        r = await c.get("/api/profiles")
        assert r.status_code == 503 and r.json()["detail"] == "Profili non disponibili"


async def test_profile_routes_require_auth():
    e, ctx, conn = await profile_env()
    async with client(ctx) as c:
        for path in ("/api/profiles", "/api/profiles/1", "/api/profiles/compare?a=x&b=y",
                     "/api/profiles/1/export"):
            assert (await c.get(path)).status_code == 401, path
        for method, path in (("POST", "/api/profiles"), ("PUT", "/api/profiles/1"),
                             ("DELETE", "/api/profiles/1"), ("POST", "/api/profiles/1/preview"),
                             ("POST", "/api/profiles/import"),
                             ("POST", f"/api/config/{MY_ID}/channels/export")):
            assert (await c.request(method, path, json={})).status_code == 401, path
    async with logged(ctx) as c:
        r = await c.post("/api/profiles", content=b"{}", headers={"Content-Type": "text/plain"})
        assert r.status_code == 415


async def test_channel_export_loopback_only():
    e, ctx, conn = await profile_env()
    ctx.auth.set_pin("1234")
    async with client(ctx, host="192.168.1.20") as c:
        assert (await c.post("/api/auth/login", json={"pin": "1234"})).status_code == 200
        r = _keep(await c.post(f"/api/config/{MY_ID}/channels/export", json={}))
        assert r.status_code == 403
        assert r.json()["detail"] == "Il link dei canali si mostra solo da questo PC"
    async with client(ctx) as c:
        assert (await c.post("/api/auth/login", json={"pin": "1234"})).status_code == 200
        r = await c.post(f"/api/config/{MY_ID}/channels/export", json={})
        assert r.status_code == 200 and r.json()["url"].startswith("https://meshtastic.org/e/#")
        assert r.headers.get("cache-control") == "no-store"
        r = await c.post(f"/api/config/{MY_ID}/channels/export",
                         json={"channels": [1], "add": True})
        assert r.json()["url"].startswith("https://meshtastic.org/e/?add=true#")
        r = await c.post(f"/api/config/{MY_ID}/channels/export", json={"channels": [7]})
        assert r.status_code == 400


async def test_channel_export_not_logged(caplog):
    import base64
    import logging
    from test_config_service import CHAN_PSK
    caplog.set_level(logging.DEBUG)
    e, ctx, conn = await profile_env()
    async with logged(ctx) as c:
        r = await c.post(f"/api/config/{MY_ID}/channels/export", json={})
        assert r.status_code == 200
    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "meshtastic.org/e/" not in text
    assert base64.b64encode(CHAN_PSK).decode() not in text


async def test_ignore_node_with_open_admin_session_refused():
    """M4: un nodo che stai amministrando da remoto non si puo' ignorare."""
    e, ctx, conn = await env_with_peer()
    conn.fresh_remote.add(PEER_NUM)
    async with logged(ctx) as c:
        r = _keep(await c.put(f"/api/nodes/{PEER}/ignored", json={"ignored": True}))
        assert r.status_code == 409
        assert r.json()["detail"] == api_nodeflags.MSG_ADMIN_SESSION
        assert e.store.get_node(PEER_NUM)["is_ignored"] is False
        assert conn.flag_calls == []
        r = await c.put(f"/api/nodes/{PEER}/ignored", json={"ignored": False})
        assert r.status_code == 200  # togliere l'ignorato resta sempre possibile


async def test_ignore_own_remote_node_only_in_meshlens():
    """M4: un tuo nodo remoto viene ignorato solo in MeshLens, mai sulle radio."""
    e, ctx, conn = await env_with_peer()
    e.live.nodes[PEER_NUM]["is_mine"] = True
    async with logged(ctx) as c:
        r = _keep(await c.put(f"/api/nodes/{PEER}/ignored", json={"ignored": True}))
        assert r.status_code == 200 and r.json()["node"]["is_ignored"] is True
        assert r.json()["radios"] == [] and conn.flag_calls == []
        assert r.json()["warning"] == api_nodeflags.MSG_MINE_LOCAL_ONLY


def test_no_secret_in_any_response():
    assert BODIES
    assert secrets_in("\n".join(BODIES)) == []
