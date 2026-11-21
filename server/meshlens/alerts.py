"""Avvisi sui nodi "miei": funzione pura, ricalcolata periodicamente (non si salvano)."""
from typing import Iterable

BATTERY_EXTERNAL = 101  # alimentazione esterna: nessun avviso
CHUTIL_ALERT_PCT = 25.0  # canale saturo: media di channel_util a partire da questa soglia
CHUTIL_WINDOW_S = 1800
CHUTIL_MIN_SAMPLES = 2
BACK_ONLINE_KEEP_S = 3600
FIRMWARE_MIN = (2, 5, 0)
KIND_ORDER = {"battery_low": 0, "silent": 1, "chutil_high": 2, "firmware_old": 3, "back_online": 4}


def _name(n: dict) -> str:
    return n.get("long_name") or n.get("short_name") or n["id"]


def parse_firmware(v: str | None) -> tuple[int, int, int] | None:
    """Le prime tre parti numeriche di "2.3.2.63df972"; None se manca o non si legge."""
    if not v:
        return None
    parts = str(v).split(".")[:3]
    if len(parts) < 3 or not all(p.isdigit() for p in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def compute_alerts(nodes: Iterable[dict], settings: dict, now: float,
                   previous: dict[str, dict],
                   chutil: dict[str, float] | None = None) -> list[dict]:
    out = []
    for n in nodes:
        if not n.get("is_mine"):
            continue
        found = []
        battery = n.get("battery")
        if battery is not None and battery < BATTERY_EXTERNAL \
                and battery < settings["battery_alert_pct"]:
            found.append(("battery:" + n["id"], "battery_low", battery, None))
        heard = n.get("last_heard")
        silent = False
        if heard is not None:
            hours = (now - heard) / 3600
            if hours > settings["silent_alert_hours"]:
                silent = True
                found.append(("silent:" + n["id"], "silent", int(hours), None))
        avg = (chutil or {}).get(n["id"])
        if avg is not None and avg >= CHUTIL_ALERT_PCT:
            found.append(("chutil:" + n["id"], "chutil_high", round(avg, 1), None))
        fw = n.get("firmware")
        parsed = parse_firmware(fw)
        if parsed is not None and parsed < FIRMWARE_MIN:
            found.append(("firmware:" + n["id"], "firmware_old", 0, fw))
        if not silent:
            okey, skey = "online:" + n["id"], "silent:" + n["id"]
            if skey in previous:
                found.append((okey, "back_online", previous[skey]["value"], None))
            elif okey in previous and now - previous[okey]["since"] < BACK_ONLINE_KEEP_S:
                found.append((okey, "back_online", previous[okey]["value"], None))
        for key, kind, value, detail in found:
            # back_online nato ora: since = now (la chiave online non e' in previous)
            since = previous[key]["since"] if key in previous else now
            alert = {"key": key, "kind": kind, "node_id": n["id"],
                     "node_name": _name(n), "value": value, "since": since}
            if detail is not None:
                alert["detail"] = detail
            out.append(alert)
    out.sort(key=lambda a: (KIND_ORDER[a["kind"]], a["node_name"]))
    return out
