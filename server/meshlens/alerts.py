"""Avvisi sui nodi "miei": funzione pura, ricalcolata periodicamente (non si salvano)."""
import re
from typing import Iterable

BATTERY_EXTERNAL = 101  # alimentazione esterna: nessun avviso
CHUTIL_ALERT_PCT = 25.0  # canale saturo: media di channel_util a partire da questa soglia
CHUTIL_WINDOW_S = 1800
CHUTIL_MIN_SAMPLES = 2
BACK_ONLINE_KEEP_S = 3600
FIRMWARE_MIN = (2, 5, 0)
KEY_CHANGED_KEEP_S = 7 * 86400
KIND_ORDER = {"battery_low": 0, "silent": 1, "key_changed": 2, "chutil_high": 3,
              "firmware_old": 4, "back_online": 5,
              # 1.6: avvisi delle regole (WP2) e autonomia
              "rule_keyword": 6, "rule_snr": 7, "rule_geofence": 8, "rule_battery": 9,
              "rule_silent": 10, "sensor_detection": 11, "autonomy_low": 12}


# 1.6: tipo di regola (alert_rules.kind) -> tipo di avviso
RULE_ALERT_KIND = {"keyword": "rule_keyword", "snr_low": "rule_snr", "geofence": "rule_geofence",
                   "battery": "rule_battery", "silent": "rule_silent",
                   "detection": "sensor_detection"}


def sort_key(a: dict) -> tuple:
    """Ordine degli avvisi: per tipo (gli sconosciuti in fondo), poi per nome del nodo."""
    return (KIND_ORDER.get(a.get("kind"), 99), a.get("node_name") or "")


_FW_RE = re.compile(r"\D*([0-9]+)\.([0-9]+)\.([0-9]+)", re.ASCII)


def _name(n: dict) -> str:
    return n.get("long_name") or n.get("short_name") or n["id"]


def rule_alert(rule_kind: str, rule_id: int, node: dict, since: float, value: float,
               detail: str | None = None) -> dict:
    """Avviso di una regola utente (chiave `rule:<id>:<nodo>`), stesso formato di compute_alerts."""
    alert = {"key": f"rule:{rule_id}:{node['id']}", "kind": RULE_ALERT_KIND[rule_kind],
             "node_id": node["id"], "node_name": _name(node), "value": value, "since": since,
             "rule_id": rule_id}
    if detail is not None:
        alert["detail"] = detail
    return alert


def parse_firmware(v: str | None) -> tuple[int, int, int] | None:
    """Le prime tre parti numeriche di "2.3.2.63df972"; None se manca o non si legge."""
    if not v:
        return None
    m = _FW_RE.match(str(v))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def compute_alerts(nodes: Iterable[dict], settings: dict, now: float,
                   previous: dict[str, dict],
                   chutil: dict[str, float] | None = None) -> list[dict]:
    out = []
    for n in nodes:
        if n.get("is_ignored"):
            continue  # nodo ignorato: nessun avviso
        mine = bool(n.get("is_mine"))
        if not mine and not n.get("is_favorite"):
            continue
        found = []
        changed = n.get("key_changed")
        if changed is not None and now - changed < KEY_CHANGED_KEEP_S:
            found.append(("pki:" + n["id"], "key_changed", 0, None))
        if not mine:  # i preferiti non miei ricevono solo l'avviso di chiave cambiata
            out.extend(_alerts(n, found, now, previous))
            continue
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
            if skey in previous and heard is not None and heard >= previous[skey]["since"]:
                found.append((okey, "back_online", previous[skey]["value"], None))
            elif okey in previous and now - previous[okey]["since"] < BACK_ONLINE_KEEP_S:
                found.append((okey, "back_online", previous[okey]["value"], None))
        out.extend(_alerts(n, found, now, previous))
    out.sort(key=sort_key)
    return out


def _alerts(n: dict, found: list, now: float, previous: dict[str, dict]) -> list[dict]:
    out = []
    for key, kind, value, detail in found:
        if kind == "key_changed":
            since = n["key_changed"]
        else:
            # back_online nato ora: since = now (la chiave online non e' in previous)
            since = previous[key]["since"] if key in previous else now
        alert = {"key": key, "kind": kind, "node_id": n["id"],
                 "node_name": _name(n), "value": value, "since": since}
        if detail is not None:
            alert["detail"] = detail
        out.append(alert)
    return out
