import asyncio

import pytest

from meshlens.api import AppContext
from meshlens.auth import Auth
from meshlens.geo import CountryLocator
from test_api import client, logged
from test_radio_manager import Env, FakeConnector, settle


def make_ctx(env):
    async def noop(_s):
        return None

    return AppContext(live=env.live, store=env.store, auth=Auth(env.conn), bus=env.bus,
                      locator=CountryLocator(), conn=env.conn, mqtt_status=lambda: {},
                      on_settings_changed=noop, radios=env.mgr)


@pytest.fixture
def env():
    return Env()


async def test_requires_auth(env):
    async with client(make_ctx(env)) as c:
        assert (await c.get("/api/radios")).status_code == 401
        assert (await c.post("/api/radios/ble-scan")).status_code == 401
        assert (await c.get("/api/messages/radio")).status_code == 401


async def test_add_list_duplicate_delete(env):
    async with logged(make_ctx(env)) as c:
        r = await c.post("/api/radios", json={"kind": "usb", "address": "COM5", "name": "H"})
        assert r.status_code == 200
        rid = r.json()["id"]
        assert (await c.get("/api/radios")).json()[0]["id"] == rid
        dup = await c.post("/api/radios", json={"kind": "usb", "address": "COM5", "name": "H"})
        assert dup.status_code == 400 and dup.json()["detail"] == "Radio già aggiunta"
        bad = await c.post("/api/radios", json={"kind": "wifi", "address": "x", "name": "H"})
        assert bad.status_code == 400
        assert (await c.post(f"/api/radios/{rid}/disconnect")).status_code == 200
        assert (await c.post(f"/api/radios/{rid}/connect")).status_code == 200
        assert (await c.delete(f"/api/radios/{rid}")).status_code == 200
        assert (await c.get("/api/radios")).json() == []
        assert (await c.delete(f"/api/radios/{rid}")).status_code == 404


async def test_ports_and_ble_scan(env):
    async with logged(make_ctx(env)) as c:
        ports = (await c.get("/api/radios/ports")).json()
        assert ports[0]["device"] == "COM5" and ports[0]["likely_meshtastic"] is True
        scan = await c.post("/api/radios/ble-scan")
        assert scan.json() == [{"address": "AA:BB", "name": "Meshtastic_1a2b"}]


async def test_send_endpoint(env):
    async with logged(make_ctx(env)) as c:
        rid = (await c.post("/api/radios", json={"kind": "usb", "address": "COM5",
                                                 "name": "H"})).json()["id"]
        url = f"/api/radios/{rid}/send"
        r = await c.post(url, json={"text": "", "channel_index": 0, "to": None})
        assert r.status_code == 400 and r.json()["detail"] == "Messaggio vuoto"
        r = await c.post(url, json={"text": "x" * 201})
        assert r.status_code == 400 and "troppo lungo" in r.json()["detail"]
        FakeConnector.instances[0].state_name = "error"
        r = await c.post(url, json={"text": "ciao"})
        assert r.status_code == 400 and r.json()["detail"] == "Radio non connessa"
        FakeConnector.instances[0].state_name = "connected"
        env.drain()
        r = await c.post(url, json={"text": "ciao", "channel_index": 0, "to": None})
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "sending" and body["key"].endswith("pending-1")
        assert body["radio_id"] == rid and body["to"] == "!ffffffff"
        await settle()
        msgs = [m["message"] for m in env.drain() if m["type"] == "message"]
        assert msgs[-1]["replaces"] == body["key"] and msgs[-1]["status"] == "sent"
        assert (await c.post("/api/radios/rnope/send", json={"text": "a"})).status_code == 404


async def test_send_body_reply_fields(env):
    async with logged(make_ctx(env)) as c:
        rid = (await c.post("/api/radios", json={"kind": "usb", "address": "COM5",
                                                 "name": "H"})).json()["id"]
        url = f"/api/radios/{rid}/send"
        assert (await c.post(url, json={"text": "ok", "reply_id": 0})).status_code == 422
        assert (await c.post(url, json={"text": "ok",
                                        "reply_id": 4294967296})).status_code == 422
        r = await c.post(url, json={"text": "👍", "emoji": True})
        assert r.status_code == 400
        assert r.json()["detail"] == "La reazione richiede il messaggio a cui reagire"
        r = await c.post(url, json={"text": "👍", "to": "!00000042", "reply_id": 42,
                                    "emoji": True})
        assert r.status_code == 202
        body = r.json()
        assert body["reply_id"] == 42 and body["emoji"] is True and body["pki"] is False
        await settle()
        assert FakeConnector.instances[0].sent_reply == [(42, True)]


async def test_radio_messages_endpoint(env):
    async with logged(make_ctx(env)) as c:
        rid = (await c.post("/api/radios", json={"kind": "usb", "address": "COM5",
                                                 "name": "H"})).json()["id"]
        env.store.add_message({"key": "9:9", "from": "!00000009", "to": "!ffffffff",
                               "time": 1, "text": "mqtt", "source": "mqtt"})
        env.ingestor.record_outgoing(rid, "!a1b2c3d4", 1, "uscita", 0, "!ffffffff")
        r = await c.get("/api/messages/radio")
        assert r.status_code == 200
        (m,) = r.json()
        assert (m["text"], m["direction"], m["radio_id"], m["channel_index"], m["packet_id"],
                m["status"]) == ("uscita", "out", rid, 0, 1, "sent")
        assert (await c.get("/api/messages/radio?before=1")).json() == []
        assert (await c.get("/api/messages/radio?limit=0")).status_code == 422


async def test_traceroute_endpoints(env):
    async with logged(make_ctx(env)) as c:
        assert (await c.post("/api/nodes/!00000042/traceroute", json={})).status_code == 409
        rid = (await c.post("/api/radios", json={"kind": "usb", "address": "COM5",
                                                 "name": "H"})).json()["id"]
        r = await c.post("/api/nodes/!00000042/traceroute", json={})
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "pending" and body["radio_id"] == rid
        assert body["target_id"] == "!00000042"
        env.now += 10
        r = await c.post("/api/nodes/!00000042/traceroute", json={"radio_id": rid})
        assert r.status_code == 429 and r.json()["detail"] == "Attendi 20 s"
        env.now += 100
        assert (await c.post("/api/nodes/!00000042/traceroute",
                             json={"radio_id": "rnope"})).status_code == 404
        assert (await c.post("/api/nodes/zzz/traceroute", json={})).status_code == 404
        r = await c.get("/api/nodes/!00000042/traceroutes")
        assert r.status_code == 200 and [t["id"] for t in r.json()] == [body["id"]]
        assert (await c.get("/api/nodes/zzz/traceroutes")).status_code == 404


async def test_traceroute_requires_auth(env):
    async with client(make_ctx(env)) as c:
        assert (await c.post("/api/nodes/!00000042/traceroute", json={})).status_code == 401
        assert (await c.get("/api/nodes/!00000042/traceroutes")).status_code == 401
