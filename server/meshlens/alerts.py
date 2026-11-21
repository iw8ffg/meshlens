"""Avvisi sui nodi "miei": funzione pura, ricalcolata periodicamente (non si salvano)."""
from typing import Iterable

BATTERY_EXTERNAL = 101  # alimentazione esterna: nessun avviso


def _name(n: dict) -> str:
    return n.get("long_name") or n.get("short_name") or n["id"]


def compute_alerts(nodes: Iterable[dict], settings: dict, now: float,
                   previous: dict[str, dict]) -> list[dict]:
    out = []
    for n in nodes:
        if not n.get("is_mine"):
            continue
        found = []
        battery = n.get("battery")
        if battery is not None and battery < BATTERY_EXTERNAL \
                and battery < settings["battery_alert_pct"]:
            found.append(("battery:" + n["id"], "battery_low", battery))
        heard = n.get("last_heard")
        if heard is not None:
            hours = (now - heard) / 3600
            if hours > settings["silent_alert_hours"]:
                found.append(("silent:" + n["id"], "silent", int(hours)))
        for key, kind, value in found:
            since = previous[key]["since"] if key in previous else now
            out.append({"key": key, "kind": kind, "node_id": n["id"],
                        "node_name": _name(n), "value": value, "since": since})
    out.sort(key=lambda a: (a["kind"] != "battery_low", a["node_name"]))
    return out
