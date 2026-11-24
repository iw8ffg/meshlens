"""Accesso ospite (E19): un secondo PIN apre una sessione in sola lettura che vede solo mappa,
nodi e statistiche.

Il controllo e' sul server e nega per impostazione predefinita:
- HTTP: `require_auth` (api.py) richiede l'admin per ogni rotta, salvo GET con il percorso
  (template della rotta) in `guest_get_paths()`;
- WebSocket: all'ospite passano solo gli eventi di `guest_event()`.
"""
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field, StrictBool

from .auth import LOOPBACK, MIN_PIN_GUEST, ROLE_GUEST
from .settings import load_settings, save_settings

GUEST_FORBIDDEN = "Non disponibile con l'accesso ospite"
GUEST_LOCAL_ONLY = "L'accesso ospite si gestisce solo da questo PC"
GUEST_NO_PIN = "Imposta prima il PIN ospite"

# GET del nucleo (api.py) leggibili dall'ospite: nodi, collegamenti, avvisi dei nodi (filtrati),
# stile e tasselli della mappa. Mai messaggi, waypoint, radio, impostazioni, stato dei broker.
CORE_GUEST_GET_PATHS: tuple[str, ...] = (
    "/api/nodes",
    "/api/nodes/{node_id}",
    "/api/links",
    "/api/countries",
    "/api/alerts",
    "/api/nodes/{node_id}/traceroutes",
    "/api/maps/style-info",
    "/tiles/{z}/{x}/{y}.mvt",
)

# eventi del WebSocket per l'ospite; `status` e `alerts` passano ridotti (vedi guest_event)
GUEST_WS_TYPES = frozenset({"nodes", "traceroute", "sensor_event", "tak_contact", "resync",
                            "status", "alerts"})
# avvisi per l'ospite (allowlist): stato dei nodi, mai regole (rule_*) ne' sensor_detection
GUEST_ALERT_KINDS = frozenset({"battery_low", "silent", "chutil_high", "back_online",
                               "firmware_old", "autonomy_low"})
_ALERT_FIELDS = ("key", "kind", "node_id", "node_name", "value", "since", "detail")
# stato MQTT per l'ospite: niente host dei broker, errori, topic rifiutati
_MQTT_KEYS = ("connected", "msgs_per_s", "connected_since", "last_msg_age_s")


class GuestPinBody(BaseModel):
    pin: str = Field(max_length=32)


class GuestEnableBody(BaseModel):
    enabled: StrictBool


def register_guest_routes(app, ctx, require_auth, require_json) -> None:
    """Rotte dedicate (contratto §5.3: prefisso /api/auth/guest). Tutte solo admin (require_auth
    nega l'ospite); PIN e accensione solo da questo PC."""

    def local(request: Request) -> bool:
        return request.client is not None and request.client.host in LOOPBACK

    def need_local(request: Request) -> None:
        if not local(request):
            raise HTTPException(403, GUEST_LOCAL_ONLY)

    def status(request: Request) -> dict:
        s = load_settings(ctx.conn)
        return {"enabled": s.get("guest_enabled") is True, "pin_set": ctx.auth.guest_pin_is_set(),
                "local": local(request), "lan_access": bool(s.get("lan_access")),
                "sessions": ctx.auth.count_guests(), "pin_min": MIN_PIN_GUEST}

    async def set_enabled(enabled: bool) -> None:
        saved = save_settings(ctx.conn, {"guest_enabled": enabled})
        if not enabled:
            ctx.auth.revoke_role(ROLE_GUEST)
        await ctx.on_settings_changed(saved)

    @app.get("/api/auth/guest", dependencies=[Depends(require_auth)])
    async def guest_status(request: Request):
        return status(request)

    @app.put("/api/auth/guest/pin", dependencies=[Depends(require_auth), Depends(require_json)])
    async def guest_set_pin(body: GuestPinBody, request: Request):
        need_local(request)
        try:
            await ctx.auth.aset_guest_pin(body.pin)  # revoca gli ospiti con il PIN vecchio
        except ValueError as e:
            raise HTTPException(400, str(e))
        return status(request)

    @app.delete("/api/auth/guest/pin", dependencies=[Depends(require_auth), Depends(require_json)])
    async def guest_clear_pin(request: Request):
        need_local(request)
        ctx.auth.clear_guest_pin()
        if load_settings(ctx.conn).get("guest_enabled") is True:
            await set_enabled(False)
        return status(request)

    @app.put("/api/auth/guest", dependencies=[Depends(require_auth), Depends(require_json)])
    async def guest_enable(body: GuestEnableBody, request: Request):
        if body.enabled:
            # accendere solo da questo PC e con un PIN ospite; spegnere da ovunque
            need_local(request)
            if not ctx.auth.guest_pin_is_set():
                raise HTTPException(400, GUEST_NO_PIN)
        await set_enabled(body.enabled)
        return status(request)


def guest_get_paths() -> frozenset[str]:
    """Allowlist completa: nucleo + `GUEST_GET_PATHS` di ogni modulo di rotte.
    Import qui dentro: i moduli importano a loro volta da api.py."""
    from . import (api_automation, api_data, api_monitor, api_prediction, api_radioadmin,
                   api_search, api_storeforward, api_topology)
    paths = set(CORE_GUEST_GET_PATHS)
    for mod in (api_data, api_storeforward, api_prediction, api_search, api_monitor,
                api_topology, api_radioadmin, api_automation):
        paths.update(mod.GUEST_GET_PATHS)
    return frozenset(paths)


def guest_alerts(alerts: list[dict]) -> list[dict]:
    """Solo gli avvisi di `GUEST_ALERT_KINDS` (allowlist: mai le regole, con testi dei messaggi
    e configurazione, ne' i rilevamenti dei sensori, ne' i tipi futuri), con i soli campi di
    `_ALERT_FIELDS` e una chiave senza id di regola."""
    out = []
    for a in alerts:
        kind = a.get("kind")
        if kind not in GUEST_ALERT_KINDS:
            continue
        b = {k: a[k] for k in _ALERT_FIELDS if k in a}
        if str(b.get("key") or "").startswith("rule:"):
            b["key"] = f"{kind}:{a.get('node_id')}"
        out.append(b)
    return out


def guest_sensor_event(ev: dict) -> dict:
    """Evento del sensore per l'ospite: nodo, ora e rilevato/cessato, senza il testo libero
    del dispositivo (l'interfaccia mostra allora "Rilevato"/"Cessato")."""
    return {"id": ev.get("id"), "node_id": ev.get("node_id"), "time": ev.get("time"),
            "kind": ev.get("kind"), "text": None, "value": ev.get("value")}


def guest_mqtt_status(status: dict | None) -> dict | None:
    if status is None:
        return None
    out = {k: status.get(k) for k in _MQTT_KEYS}
    out["connected"] = bool(out["connected"])
    out["msgs_per_s"] = out["msgs_per_s"] or 0
    out["undecodable"] = 0
    return out


def guest_event(msg: dict) -> dict | None:
    """L'evento come lo vede l'ospite, None se non deve riceverlo (anche i tipi futuri)."""
    kind = msg.get("type") if isinstance(msg, dict) else None
    if kind not in GUEST_WS_TYPES:
        return None
    if kind == "status":
        return {"type": "status", "mqtt": guest_mqtt_status(msg.get("mqtt"))}
    if kind == "alerts":
        return {"type": "alerts", "alerts": guest_alerts(msg.get("alerts") or [])}
    if kind == "sensor_event":
        return {"type": "sensor_event", "event": guest_sensor_event(msg.get("event") or {})}
    return msg
