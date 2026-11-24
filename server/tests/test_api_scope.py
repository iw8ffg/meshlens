"""Ambito di bot e webhook bloccato dalla rete con la funzione accesa; /docs spenti."""
from test_api import ctx, client_from, logged  # noqa: F401 - fixture
from meshlens.settings import load_settings, save_settings

SCOPE_CHANGES = [
    {"bot_targets": [{"kind": "rf", "channel": 3}]},
    {"bot_replies": {"ping": "ciao"}},
    {"bot_commands": ["ping"]},
    {"bot_min_interval_s": 99},
    {"bot_max_per_hour": 7},
    {"bot_node_cooldown_s": 999},
    {"bot_weather_node": 123},
    {"webhook_url": "https://example.com/hook"},
    {"webhook_events": ["message"]},
]


async def test_docs_and_openapi_are_disabled(ctx):
    async with logged(ctx) as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await c.get(path)).status_code == 404, path


async def test_scope_locked_from_lan_while_enabled(ctx):
    ctx.auth.set_pin("123456")
    save_settings(ctx.conn, {"lan_access": True})
    save_settings(ctx.conn, {"bot_enabled": True, "webhook_enabled": True})
    async with client_from(ctx, "192.168.1.20") as c:
        assert (await c.post("/api/auth/login", json={"pin": "123456"})).status_code == 200
        for changes in SCOPE_CHANGES:
            r = await c.put("/api/settings", json=changes)
            assert r.status_code == 403, changes
            assert "questo PC" in r.json()["detail"]
        doc = {"format": 1, "settings": {"bot_max_per_hour": 7}}
        assert (await c.post("/api/settings/import", json=doc)).status_code == 403
        # un valore invariato (o una chiave estranea) passa
        r = await c.put("/api/settings", json={
            "bot_max_per_hour": load_settings(ctx.conn)["bot_max_per_hour"],
            "retention_messages_days": 30})
        assert r.status_code == 200
    async with client_from(ctx, "127.0.0.1") as c:
        assert (await c.post("/api/auth/login", json={"pin": "123456"})).status_code == 200
        r = await c.put("/api/settings", json={"bot_max_per_hour": 7})
        assert r.status_code == 200


async def test_scope_free_from_lan_while_disabled(ctx):
    ctx.auth.set_pin("123456")
    save_settings(ctx.conn, {"lan_access": True})
    async with client_from(ctx, "192.168.1.20") as c:
        assert (await c.post("/api/auth/login", json={"pin": "123456"})).status_code == 200
        r = await c.put("/api/settings", json={"bot_max_per_hour": 7})
        assert r.status_code == 200
