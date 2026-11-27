"""Avvisi chiudibili e "accetta la nuova chiave": ciclo di vita, persistenza, notifiche, ospite."""
import time

from meshlens.api import AppContext
from meshlens.auth import Auth
from meshlens.bus import Bus
from meshlens.live import LiveState
from meshlens.settings import export_settings, load_settings, save_settings
from meshlens.store import Store
from test_api import logged, make_ctx
from test_api_guest import ADMIN_PIN, GUEST_PIN, client_with, guest_token

import pytest


@pytest.fixture
def ctx():
    c = make_ctx()
    c.live.nodes[1]["battery"] = 10  # nodo mio con la batteria scarica
    c.live.nodes[1]["num"] = 1
    return c


def keys(alerts):
    return [a["key"] for a in alerts]


async def test_dismiss_hides_while_condition_lasts(ctx):
    ctx.alerts()
    async with logged(ctx) as c:
        assert keys((await c.get("/api/alerts")).json()) == ["battery:!00000001"]
        r = await c.post("/api/alerts/battery:!00000001/dismiss", json={})
        assert r.status_code == 200 and r.json() == {"hidden": 1}
        assert (await c.get("/api/alerts")).json() == []
        assert (await c.get("/api/alerts/hidden")).json() == {"count": 1}
        # la condizione dura (anche con un valore diverso): resta nascosto
        ctx.live.nodes[1]["battery"] = 9
        assert ctx.alerts() == []
        assert load_settings(ctx.conn)["dismissed_alerts"] == ["battery:!00000001"]


async def test_dismissal_dropped_when_condition_ends_then_reappears(ctx):
    ctx.alerts()
    assert ctx.dismiss_alert("battery:!00000001")
    assert ctx.alerts() == []
    ctx.live.nodes[1]["battery"] = 80  # condizione finita
    assert ctx.alerts() == []
    assert load_settings(ctx.conn)["dismissed_alerts"] == []  # chiusura scordata
    assert ctx.alerts_hidden() == 0
    ctx.live.nodes[1]["battery"] = 5  # ritorna: si rivede
    assert keys(ctx.alerts()) == ["battery:!00000001"]


async def test_dismiss_unknown_key_404_and_needs_json(ctx):
    async with logged(ctx) as c:
        r = await c.post("/api/alerts/silent:!00000001/dismiss", json={})
        assert r.status_code == 404
        r = await c.post("/api/alerts/battery:!00000001/dismiss", content=b"{}")
        assert r.status_code == 415


async def test_restore_shows_all_again(ctx):
    ctx.alerts()
    async with logged(ctx) as c:
        await c.post("/api/alerts/battery:!00000001/dismiss", json={})
        r = await c.post("/api/alerts/dismissed/restore", json={})
        assert r.status_code == 200 and r.json() == {"hidden": 0}
        assert keys((await c.get("/api/alerts")).json()) == ["battery:!00000001"]
        assert load_settings(ctx.conn)["dismissed_alerts"] == []


def test_ws_event_carries_hidden_and_active_keys(ctx):
    ctx.alerts()
    q = ctx.bus.subscribe()
    ctx.dismiss_alert("battery:!00000001")
    msg = q.get_nowait()
    assert msg["type"] == "alerts" and msg["alerts"] == [] and msg["hidden"] == 1
    assert msg["active_keys"] == ["battery:!00000001"]


def test_dismissal_persists_across_restart(ctx):
    ctx.alerts()
    ctx.dismiss_alert("battery:!00000001")
    fresh = AppContext(live=ctx.live, store=Store(ctx.conn), auth=Auth(ctx.conn), bus=Bus(),
                       locator=ctx.locator, conn=ctx.conn,
                       mqtt_status=ctx.mqtt_status, on_settings_changed=ctx.on_settings_changed)
    assert fresh.alerts() == []  # il primo calcolo dopo l'avvio non scorda e non mostra
    assert fresh.alerts_hidden() == 1


def test_dismissed_not_exported_and_validated(ctx):
    save_settings(ctx.conn, {"dismissed_alerts": ["a", "b"]})
    assert "dismissed_alerts" not in export_settings(load_settings(ctx.conn), True)["settings"]
    for bad in ("x", [1], ["a", "a"], [""], ["a" * 201], [f"k{i}" for i in range(501)]):
        with pytest.raises(ValueError):
            save_settings(ctx.conn, {"dismissed_alerts": bad})


def test_notifications_not_resent_for_dismissed_or_restored(ctx):
    ctx.live.nodes[1]["battery"] = None
    ctx.live.nodes[1]["last_heard"] = time.time() - 10 * 3600  # nodo muto: "silent"
    ctx.alerts()
    seen = []
    ctx.notifier.on_alerts = lambda old, new: seen.append(({a["key"] for a in old},
                                                           {a["key"] for a in new}))
    ctx.dismiss_alert("silent:!00000001")
    ctx.alerts()
    ctx.restore_dismissed()
    assert seen
    for old, new in seen:  # mai "nuovo" rispetto a prima: nessuna notifica
        assert "silent:!00000001" in old and "silent:!00000001" in new


def test_key_changed_alert_order_kept_and_accept_key(ctx):
    now = time.time()
    ctx.live.nodes[1]["key_changed"] = now - 60
    ctx.live.nodes[1]["public_key"] = "x"
    ctx.store.upsert_node(ctx.live.nodes[1])
    ctx.store.commit()
    out = ctx.alerts()
    assert [a["kind"] for a in out] == ["battery_low", "key_changed"]
    q = ctx.bus.subscribe()
    node = ctx.accept_key(1)
    assert node["key_changed"] is None and ctx.live.nodes[1]["key_changed"] is None
    assert ctx.store.get_node(1)["key_changed"] is None
    assert [a["kind"] for a in ctx._alerts] == ["battery_low"]
    assert q.get_nowait()["type"] == "alerts"
    assert 1 in [n["num"] for n in ctx.live.take_changed()]  # nodo da ripubblicare ai client


async def test_accept_key_route_and_key_changes_again(ctx):
    ctx.live.nodes[1]["key_changed"] = time.time() - 60
    async with logged(ctx) as c:
        assert "pki:!00000001" in keys((await c.get("/api/alerts")).json())
        r = await c.post("/api/nodes/!00000001/accept-key", json={})
        assert r.status_code == 200 and r.json()["key_changed"] is None
        assert "pki:!00000001" not in keys((await c.get("/api/alerts")).json())
        assert (await c.post("/api/nodes/!000000ff/accept-key", json={})).status_code == 404
        assert (await c.post("/api/nodes/!00000001/accept-key", content=b"{}")).status_code == 415
        ctx.live.nodes[1]["key_changed"] = time.time()  # l'ingest la rimette se cambia ancora
        assert "pki:!00000001" in keys((await c.get("/api/alerts")).json())


async def test_guest_cannot_dismiss_restore_or_accept(ctx):
    ctx.auth.set_pin(ADMIN_PIN)
    ctx.auth.set_guest_pin(GUEST_PIN)
    save_settings(ctx.conn, {"guest_enabled": True})
    token = guest_token(ctx)
    async with client_with(ctx, token) as g:
        for path in ("/api/alerts/battery:!00000001/dismiss", "/api/alerts/dismissed/restore",
                     "/api/nodes/!00000001/accept-key"):
            assert (await g.post(path, json={})).status_code == 403
        assert (await g.get("/api/alerts/hidden")).status_code == 403
    assert ctx.live.nodes[1].get("key_changed") is None
