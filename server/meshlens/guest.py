"""Accesso ospite (E19): un secondo PIN apre una sessione in sola lettura che vede solo mappa,
nodi e statistiche.

Il controllo e' sul server e nega per impostazione predefinita:
- HTTP: `require_auth` (api.py) richiede l'admin per ogni rotta, salvo GET con il percorso
  (template della rotta) in `guest_get_paths()`;
- WebSocket: all'ospite passano solo gli eventi di `guest_event()`.
"""
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
# stato MQTT per l'ospite: niente host dei broker, errori, topic rifiutati
_MQTT_KEYS = ("connected", "msgs_per_s", "connected_since", "last_msg_age_s")


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
    """Avvisi dei nodi senza quelli delle regole (`rule_*`: testi dei messaggi, nomi e
    configurazione delle regole) e senza `rule_id`."""
    out = []
    for a in alerts:
        if str(a.get("kind") or "").startswith("rule_"):
            continue
        out.append({k: v for k, v in a.items() if k != "rule_id"})
    return out


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
    return msg
