"""Rotte di WP2 (avvisi su misura, sensori, salute della rete).

Prefissi riservati (contratto 5.3): /api/alert-rules, /api/nodes/{node_id}/sensor-events, /api/health
"""
import time

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from .alert_rules import MSG_RULE_UNKNOWN, MSG_RULES_UNAVAILABLE, validate_rule
from .api_storeforward import MSG_BAD_ID

# percorsi GET (esattamente come registrati) leggibili dall'ospite: nodi e statistiche
GUEST_GET_PATHS: tuple[str, ...] = ("/api/nodes/{node_id}/sensor-events",
                                    "/api/health/batteries")


class RuleBody(BaseModel):
    kind: str
    name: str = ""
    enabled: bool = True
    node_id: str | None = None
    channel: str | None = None
    threshold: float | None = None
    params: dict = Field(default_factory=dict)
    cooldown_min: int = 60


class RulePatchBody(BaseModel):
    kind: str | None = None
    name: str | None = None
    enabled: bool | None = None
    node_id: str | None = None
    channel: str | None = None
    threshold: float | None = None
    params: dict | None = None
    cooldown_min: int | None = None


class ConfirmBody(BaseModel):
    confirm: bool = False


def _node_num(node_id: str | None) -> int | None:
    if node_id is None:
        return None
    try:
        if not node_id.startswith("!"):
            raise ValueError
        return int(node_id[1:], 16)
    except ValueError:
        raise HTTPException(400, MSG_BAD_ID) from None


def register(app, ctx, require_auth, require_json) -> None:
    """Registra le rotte del modulo (chiamata in coda a create_app, prima dei file statici)."""
    write = [Depends(require_auth), Depends(require_json)]

    def engine():
        eng = ctx.ext.get("alert_rules")
        if eng is None:
            raise HTTPException(503, MSG_RULES_UNAVAILABLE)
        return eng

    def changed(eng) -> None:
        """Dopo una scrittura: motore aggiornato, commit, evento, avvisi ricalcolati."""
        eng.reload()
        ctx.conn.commit()
        ctx.bus.publish({"type": "alert_rules", "rules": [r.to_json() for r in eng.rules()]})
        ctx.alerts()

    @app.get("/api/alert-rules", dependencies=[Depends(require_auth)])
    async def list_rules():
        return [r.to_json() for r in engine().store.list()]

    @app.post("/api/alert-rules", dependencies=write)
    async def create_rule(body: RuleBody):
        eng = engine()
        data = body.model_dump()
        data["node_num"] = _node_num(data.pop("node_id"))
        try:
            rule = eng.store.create(validate_rule(data), time.time())
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        changed(eng)
        return rule.to_json()

    @app.patch("/api/alert-rules/{rule_id}", dependencies=write)
    async def patch_rule(rule_id: int, body: RulePatchBody):
        eng = engine()
        existing = eng.store.get(rule_id)
        if existing is None:
            raise HTTPException(404, MSG_RULE_UNKNOWN)
        data = {k: v for k, v in body.model_dump().items() if k in body.model_fields_set}
        if "node_id" in data:
            data["node_num"] = _node_num(data.pop("node_id"))
        for key in ("kind", "name", "enabled", "params", "cooldown_min"):
            if key in data and data[key] is None:
                del data[key]  # un null esplicito non azzera i campi obbligatori
        try:
            rule = eng.store.update(rule_id, validate_rule(data, existing), time.time())
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        if rule is None:
            raise HTTPException(404, MSG_RULE_UNKNOWN)
        changed(eng)
        return rule.to_json()

    @app.delete("/api/alert-rules/{rule_id}", dependencies=write)
    async def delete_rule(rule_id: int, body: ConfirmBody):
        eng = engine()
        if not body.confirm:
            raise HTTPException(400, "Conferma richiesta")
        if not eng.store.delete(rule_id):
            raise HTTPException(404, MSG_RULE_UNKNOWN)
        changed(eng)
        return {"ok": True}
