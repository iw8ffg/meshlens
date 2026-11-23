"""Rotte di WP5b: note di versione, versione vista, anteprima conservazione, diagnosi radio."""
import time

import pytest

import meshlens
from meshlens import api_maintenance, release_notes
from meshlens.release_notes import Release
from meshlens.settings import load_settings, save_settings
from test_api import client, logged, make_ctx
from test_radio_diag import SENTINEL, FakeManager, FakeProbes, port, radio
from meshlens.radio_diag import RadioDiagnoser

RELEASES = [Release("1.6.0", "2026-12-01", "Novità", "News"),
            Release("1.5.1", "2026-11-23", "Correzioni", "Fixes")]


@pytest.fixture
def mctx(monkeypatch):
    monkeypatch.setattr(meshlens, "__version__", "1.6.0")
    monkeypatch.setattr(release_notes, "load_releases", lambda: list(RELEASES))
    return make_ctx()


async def test_update_notes_after_update(mctx):
    save_settings(mctx.conn, {"last_seen_version": "1.5.1", "onboarding_done": True})
    async with logged(mctx) as c:
        body = (await c.get("/api/update/notes")).json()
    assert body["show"] is True and body["version"] == "1.6.0"
    assert body["releases"][0]["version"] == "1.6.0"
    assert body["releases"][0]["it"] == "Novità" and body["releases"][0]["en"] == "News"


async def test_update_notes_fresh_install_hidden_and_force(mctx):
    async with logged(mctx) as c:
        assert (await c.get("/api/update/notes")).json()["show"] is False
        body = (await c.get("/api/update/notes?force=1")).json()
    assert body["show"] is True and [r["version"] for r in body["releases"]] == ["1.6.0"]


async def test_update_seen_sets_current_version_and_ignores_body(mctx):
    async with logged(mctx) as c:
        r = await c.post("/api/update/seen", json={"version": "9.9.9"})
        assert r.json() == {"last_seen_version": "1.6.0"}
        assert load_settings(mctx.conn)["last_seen_version"] == "1.6.0"
        assert mctx.changed[-1]["last_seen_version"] == "1.6.0"
        r = await c.post("/api/update/seen", content="x", headers={"content-type": "text/plain"})
        assert r.status_code == 415
    async with client(mctx) as c:
        assert (await c.post("/api/update/seen", json={})).status_code == 401


def _broker_settings(ctx, days=None):
    brokers = load_settings(ctx.conn)["mqtt_brokers"]
    b1 = {**brokers[0], "id": "b1", "name": "Privato", "host": "example.org"}
    changes = {"mqtt_brokers": [*brokers, b1], "retention_messages_days": 90}
    if days is not None:
        changes["retention_broker_days"] = {"b1": days}
    save_settings(ctx.conn, changes)


def _msg(ctx, key, age_days, broker="b1", source="mqtt"):
    ctx.conn.execute(
        "INSERT INTO messages(key, from_num, text, time, source, broker) VALUES(?,?,?,?,?,?)",
        (key, 5, "x", time.time() - age_days * 86400, source, broker))


async def test_retention_preview(mctx):
    _broker_settings(mctx, 7)
    _msg(mctx, "a", 10)
    _msg(mctx, "b", 0)
    _msg(mctx, "c", 200)  # gia' in scadenza per la regola generale: non contato
    _msg(mctx, "d", 10, broker="b2")
    mctx.conn.execute("INSERT INTO traceroutes(radio_id, target_num, time, status) "
                      "VALUES('r', 1, ?, 'ok')", (time.time() - 400 * 86400,))
    mctx.conn.execute("INSERT INTO traceroutes(radio_id, target_num, time, status) "
                      "VALUES('r', 1, ?, 'ok')", (time.time(),))
    mctx.conn.commit()
    before = mctx.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    async with logged(mctx) as c:
        body = (await c.get("/api/retention")).json()
        b = next(x for x in body["brokers"] if x["id"] == "b1")
        assert b["name"] == "Privato" and b["messages"] == 3 and b["days"] == 7
        assert b["would_delete"] == 1 and b["oldest"] is not None
        default = next(x for x in body["brokers"] if x["id"] != "b1")
        assert default["days"] is None and default["would_delete"] == 0
        assert body["traceroutes"] == {"rows": 2, "would_delete": 1, "days": 365}
        assert body["messages_days"] == 90
        assert mctx.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == before
        save_settings(mctx.conn, {"retention_broker_days": {"b1": 120}})
        body = (await c.get("/api/retention")).json()
    assert next(x for x in body["brokers"] if x["id"] == "b1")["would_delete"] == 0


def _diag_ctx(manager, probes):
    ctx = make_ctx()
    ctx.radios = manager
    ctx.ext["radio_diag"] = RadioDiagnoser(manager, probes=probes)
    return ctx


async def test_diagnose_saved_radio():
    m = FakeManager(radios=[radio("usb", "COM5", "error")], ports=[port()])
    ctx = _diag_ctx(m, FakeProbes())
    async with logged(ctx) as c:
        r = await c.post("/api/radios/r1/diagnose", json={})
        assert r.status_code == 200 and r.json()["checks"]
        r = await c.post("/api/radios/nope/diagnose", json={})
        assert r.status_code == 404 and r.json()["detail"] == "Radio non trovata"
        await ctx.ext["radio_diag"]._lock.acquire()
        r = await c.post("/api/radios/r1/diagnose", json={})
        assert r.status_code == 409 and r.json()["detail"] == "Diagnosi già in corso"
        ctx.ext["radio_diag"]._lock.release()


async def test_diagnose_unsaved_address():
    ctx = _diag_ctx(FakeManager(), FakeProbes())
    async with logged(ctx) as c:
        r = await c.post("/api/radios/diagnose", json={"kind": "tcp", "address": "192.0.2.1"})
        assert r.status_code == 200 and r.json()["kind"] == "tcp"
        r = await c.post("/api/radios/diagnose", json={"kind": "x", "address": "a"})
        assert r.status_code == 400 and r.json()["detail"] == "Tipo di radio non valido"
        r = await c.post("/api/radios/diagnose", json={"kind": "tcp", "address": " "})
        assert r.status_code == 400 and r.json()["detail"] == "Indirizzo mancante"


async def test_routes_require_auth_and_json():
    ctx = _diag_ctx(FakeManager(), FakeProbes())
    async with client(ctx) as c:
        for method, path in (("GET", "/api/update/notes"), ("POST", "/api/update/seen"),
                             ("GET", "/api/retention"), ("POST", "/api/radios/diagnose"),
                             ("POST", "/api/radios/r1/diagnose")):
            assert (await c.request(method, path, json={})).status_code == 401, path
    async with logged(ctx) as c:
        r = await c.post("/api/radios/diagnose", content="{}",
                         headers={"content-type": "text/plain"})
        assert r.status_code == 415


def test_no_guest_paths():
    assert api_maintenance.GUEST_GET_PATHS == ()


async def test_diagnose_response_has_no_secrets():
    m = FakeManager(radios=[radio("usb", "COM5", "error")], ports=[port()])
    ctx = _diag_ctx(m, FakeProbes())
    async with logged(ctx) as c:
        r = await c.post("/api/radios/r1/diagnose", json={})
    assert SENTINEL not in r.text and "security" not in r.text


async def test_diagnoser_created_on_demand():
    ctx = make_ctx()
    ctx.radios = FakeManager(radios=[radio("tcp", "bad host!", "error")])
    async with logged(ctx) as c:
        r = await c.post("/api/radios/r1/diagnose", json={})
    assert r.status_code == 200 and r.json()["advice"] == "tcp_bad_address"
