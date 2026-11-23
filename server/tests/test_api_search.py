import contextlib
import urllib.parse
from types import SimpleNamespace

import httpx
from httpx import ASGITransport

from meshlens import api_search, db, ext_messages
from meshlens.api import create_app
from test_api import make_ctx

BCAST = "!ffffffff"
RADIO = "r1a2b3c4"
LOCAL = "!a1b2c3d4"
PEER = "!000000aa"


def add(ctx, key, text, t, frm=PEER, to=BCAST, radio=RADIO, ch=0, direction="in", broker=None):
    ctx.store.add_message({"key": key, "from": frm, "to": to, "text": text, "time": t,
                           "direction": direction, "radio_id": radio, "channel_index": ch,
                           "broker": broker, "source": "rf" if radio else "mqtt"})
    ctx.conn.commit()


def add_node(ctx, num, name, ignored=0):
    ctx.conn.execute("INSERT INTO nodes(num, id, long_name, short_name, last_heard, is_ignored) "
                     "VALUES(?,?,?,?,?,?)", (num, f"!{num:08x}", name, "SN", 1.0, ignored))
    ctx.conn.commit()


@contextlib.asynccontextmanager
async def logged(ctx):
    app = create_app(ctx)
    async with httpx.AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 1234)),
                                 base_url="http://127.0.0.1") as c:
        assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
        yield c


async def test_search_requires_auth():
    ctx = make_ctx()
    app = create_app(ctx)
    async with httpx.AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 1234)),
                                 base_url="http://127.0.0.1") as c:
        for url in ("/api/messages/search?q=a", "/api/conversations/mqtt/export",
                    "/api/search?q=ab"):
            assert (await c.get(url)).status_code == 401


async def test_message_search_endpoint():
    ctx = make_ctx()
    add(ctx, "k1", "ciao uno", 10)
    add(ctx, "k2", "ciao due", 20)
    async with logged(ctx) as c:
        r = await c.get("/api/messages/search", params={"q": "ciao"})
        assert r.status_code == 200
        body = r.json()
        assert body["hits"][0]["message"]["text"] == "ciao due"
        assert body["engine"] in ("fts5", "like")
        r1 = (await c.get("/api/messages/search", params={"q": "ciao", "limit": 1})).json()
        assert r1["next"] is not None and r1["hits"][0]["message"]["key"] == "k2"
        r2 = (await c.get("/api/messages/search",
                          params={"q": "ciao", "limit": 1, "cursor": r1["next"]})).json()
        assert [h["message"]["key"] for h in r2["hits"]] == ["k1"] and r2["next"] is None


async def test_message_search_validation():
    ctx = make_ctx()
    async with logged(ctx) as c:
        g = c.get
        assert (await g("/api/messages/search", params={"q": ""})).json()["detail"] == (
            "Testo da cercare mancante")
        r = await g("/api/messages/search", params={"q": "x" * 201})
        assert r.status_code == 400 and r.json()["detail"] == "Testo da cercare troppo lungo"
        r = await g("/api/messages/search", params={"q": "a", "sender": "zz"})
        assert r.status_code == 400 and r.json()["detail"] == "Mittente non valido"
        assert (await g("/api/search", params={"q": ""})).status_code == 400
        assert (await g("/api/search", params={"q": "a", "limit": 9})).status_code == 400
        r = await g("/api/messages/search", params={"q": "a", "cursor": "abc"})
        assert r.status_code == 400 and r.json()["detail"] == "Cursore di ricerca non valido"
        r = await g("/api/messages/search", params={"q": "a", "conv": "boh"})
        assert r.status_code == 400 and r.json()["detail"] == "Conversazione non valida"
        assert (await g("/api/messages/search", params={"q": "a", "limit": 101})).json()["detail"] == (
            "Limite non valido")
        assert (await g("/api/messages/search", params={"q": "a", "limit": 0})).status_code == 400


async def test_search_dm_both_directions_with_local_ids():
    ctx = make_ctx()
    ctx.radios = SimpleNamespace(local_ids=lambda: {LOCAL})
    add(ctx, "in", "ciao in", 10, frm=PEER, to=LOCAL)
    add(ctx, "out", "ciao out", 20, frm=LOCAL, to=PEER, direction="out")
    add(ctx, "other", "ciao altro", 30, frm="!000000bb", to=LOCAL)
    async with logged(ctx) as c:
        r = await c.get("/api/messages/search",
                        params={"q": "ciao", "conv": f"dm:{RADIO}:{PEER}"})
        assert [h["message"]["key"] for h in r.json()["hits"]] == ["out", "in"]
        assert all(h["conv"] == f"dm:{RADIO}:{PEER}" for h in r.json()["hits"])


async def test_search_excludes_ignored_senders():
    ctx = make_ctx()
    add_node(ctx, 0xaa, "Ignorato", ignored=1)
    add(ctx, "a", "ciao nascosto", 10, frm=PEER)
    add(ctx, "b", "ciao visibile", 20, frm="!000000bb")
    async with logged(ctx) as c:
        r = await c.get("/api/messages/search", params={"q": "ciao"})
        assert [h["message"]["key"] for h in r.json()["hits"]] == ["b"]
        r = await c.get("/api/conversations/ch%3A" + RADIO + "%3A0/export")
        assert [m["key"] for m in r.json()["messages"]] == ["b"]


async def test_export_endpoint():
    ctx = make_ctx()
    ctx.radios = SimpleNamespace(local_ids=lambda: {LOCAL})
    add(ctx, "a", "uno", 10, frm=PEER, to=LOCAL)
    add(ctx, "b", "due", 20, frm=LOCAL, to=PEER, direction="out")
    add(ctx, "m", "mqtt", 30, radio=None, broker="b1")
    async with logged(ctx) as c:
        key = urllib.parse.quote(f"dm:{RADIO}:{PEER}", safe="")
        assert key == "dm%3Ar1a2b3c4%3A%21000000aa"
        r = await c.get(f"/api/conversations/{key}/export")
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-store"
        d = r.json()
        assert [m["key"] for m in d["messages"]] == ["a", "b"]
        assert d["total"] == 2 and d["truncated"] is False
        assert (await c.get("/api/conversations/mqtt/export")).status_code == 200
        r = await c.get("/api/conversations/mqtt:b1/export")
        assert [m["key"] for m in r.json()["messages"]] == ["m"]
        r = await c.get("/api/conversations/dm:r1:zz/export")
        assert r.status_code == 400 and r.json()["detail"] == "Conversazione non valida"


async def test_global_search_endpoint():
    ctx = make_ctx()
    add_node(ctx, 0x77, "Rifugio Alpe")
    add_node(ctx, 0x78, "Rifugio Ignorato", ignored=1)
    for i in range(7):
        add(ctx, f"k{i}", f"ci vediamo al rifugio {i}", 10 + i)
    async with logged(ctx) as c:
        r = await c.get("/api/search", params={"q": "rif"})
        assert r.status_code == 200
        d = r.json()
        assert [n["long_name"] for n in d["nodes"]] == ["Rifugio Alpe"]
        assert len(d["messages"]) == 5 and d["engine"] in ("fts5", "like")


async def test_search_runs_on_ro_connection(tmp_path):
    ctx = make_ctx()
    path = tmp_path / "s.db"
    disk = db.connect(path)
    from meshlens.store import Store
    Store(disk).add_message({"key": "k", "from": PEER, "to": BCAST, "text": "ciao disco",
                             "time": 5, "radio_id": RADIO, "channel_index": 0})
    disk.commit()
    disk.close()
    ctx.db_path = path
    async with logged(ctx) as c:
        r = await c.get("/api/messages/search", params={"q": "disco"})
        assert r.status_code == 200 and len(r.json()["hits"]) == 1
        assert (await c.get("/api/search", params={"q": "disco"})).json()["messages"]
        assert (await c.get(f"/api/conversations/ch:{RADIO}:0/export")).json()["total"] == 1


def test_ext_install_records_engine():
    ctx = make_ctx()
    ext_messages.install(None, ctx)
    assert ctx.ext["search"]["engine"] == db.search_engine(ctx.conn)
    assert api_search.GUEST_GET_PATHS == ()
