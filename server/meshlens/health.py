"""Salute della rete (E11): stima dell'autonomia della batteria e tendenza dei nodi solari.

Le funzioni di analisi sono pure; solo `battery_overview` legge il database (connessione in sola
lettura, fuori dal loop). La web mostra soltanto il risultato: la stima e' solo qui."""
import math
from collections import defaultdict

WINDOW_H = 72
BUCKET_S = 3600
MIN_BUCKETS = 6
MIN_SPAN_H = 24
CHARGING_SLOPE_PER_DAY = 2.0
STABLE_SLOPE_PER_DAY = 1.0
MIN_TOTAL_DROP = 2.0
MAX_DAYS = 60
PAIR_MIN_DX_H = 0.5
SOLAR_RISE_PTS = 5.0
SOLAR_MIN_WINDOWS = 2
SOLAR_MIN_BUCKETS = 4
SOLAR_DELTA = 2.0
BATTERY_EXTERNAL = 101


def median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def hourly_buckets(samples: list[tuple[float, int | None]], now: float,
                   hours: float = WINDOW_H) -> list[tuple[float, float]]:
    """(tempo medio, mediana) per ora; scarta None, 101 (esterna) e i campioni fuori finestra."""
    cutoff = now - hours * 3600
    groups: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for t, b in samples:
        if b is None or b > 100 or t < cutoff or t > now:
            continue
        groups[math.floor(t / BUCKET_S)].append((t, b))
    return [(sum(t for t, _ in g) / len(g), median([b for _, b in g]))
            for _, g in sorted(groups.items())]


def theil_sen(points: list[tuple[float, float]]) -> tuple[float, float]:
    """(pendenza per ora, livello a x = 0); x = ore rispetto a now (<= 0)."""
    slopes = [(points[j][1] - points[i][1]) / (points[j][0] - points[i][0])
              for i in range(len(points)) for j in range(i + 1, len(points))
              if points[j][0] - points[i][0] >= PAIR_MIN_DX_H]
    slope = median(slopes) if slopes else 0.0
    level = median([y - slope * x for x, y in points])
    return slope, min(100.0, max(0.0, level))


def _empty(status: str) -> dict:
    return {"status": status, "level": None, "slope_per_day": None, "days_left": None,
            "solar": False, "solar_trend": None, "solar_peak": None}


def _has_cycle(window: list[float]) -> bool:
    """Una finestra da 24 h con un ciclo giorno/notte: sale e scende di almeno SOLAR_RISE_PTS.

    La sola salita (D5) scambierebbe una ricarica continua per un nodo solare: serve anche
    una discesa nella stessa finestra."""
    if len(window) < SOLAR_MIN_BUCKETS:
        return False
    rise = drop = False
    low = high = window[0]
    for v in window[1:]:
        rise = rise or v - low >= SOLAR_RISE_PTS
        drop = drop or high - v >= SOLAR_RISE_PTS
        low, high = min(low, v), max(high, v)
    return rise and drop


def analyze_battery(samples: list[tuple[float, int | None]], now: float) -> dict:
    """Algoritmo D5 del piano WP2: {status, level, slope_per_day, days_left, solar, solar_trend,
    solar_peak}. `status`: falling | charging | stable | insufficient | external | solar."""
    recent = [(t, b) for t, b in samples if now - WINDOW_H * 3600 <= t <= now and b is not None]
    if recent and max(recent, key=lambda s: s[0])[1] > 100:
        return _empty("external")
    buckets = hourly_buckets(samples, now)
    if len(buckets) < MIN_BUCKETS or buckets[-1][0] - buckets[0][0] < MIN_SPAN_H * 3600:
        return _empty("insufficient")
    wins: list[list[float]] = [[], [], []]
    for t, v in buckets:
        age = (now - t) / 3600
        wins[0 if age > 48 else 1 if age > 24 else 2].append(v)
    if sum(_has_cycle(w) for w in wins) >= SOLAR_MIN_WINDOWS:
        trend = None
        if len(wins[1]) >= SOLAR_MIN_BUCKETS and len(wins[2]) >= SOLAR_MIN_BUCKETS:
            delta = max(wins[2]) - max(wins[1])
            trend = ("charging" if delta >= SOLAR_DELTA
                     else "falling" if delta <= -SOLAR_DELTA else "stable")
        return {"status": "solar", "level": round(buckets[-1][1], 1), "slope_per_day": None,
                "days_left": None, "solar": True, "solar_trend": trend,
                "solar_peak": max(wins[2]) if wins[2] else None}
    slope_h, level = theil_sen([((t - now) / 3600, v) for t, v in buckets])
    slope_day = slope_h * 24
    drop = -slope_h * (buckets[-1][0] - buckets[0][0]) / 3600
    out = {**_empty("stable"), "level": round(level, 1), "slope_per_day": round(slope_day, 1)}
    if slope_day >= CHARGING_SLOPE_PER_DAY:
        out["status"] = "charging"
    elif slope_day > -STABLE_SLOPE_PER_DAY or drop < MIN_TOTAL_DROP:
        pass
    else:
        days = 0.0 if level <= 0 else level / -slope_day
        if days <= MAX_DAYS:
            out["status"] = "falling"
            out["days_left"] = round(days, 1)
    return out


def power_stats(rows: list[tuple[float, float | None, int | None]]) -> dict:
    """Da (tempo, tensione, uptime) ordinati: ultimi valori non nulli e numero di riavvii."""
    voltage = uptime = None
    reboots = 0
    prev = None
    for _t, v, up in rows:
        if v is not None:
            voltage = v
        if up is not None:
            uptime = up
            if prev is not None and up < prev:
                reboots += 1
            prev = up
    return {"voltage": voltage, "uptime_s": uptime, "reboots": reboots}


def _name(n: dict) -> str:
    return n.get("long_name") or n.get("short_name") or n.get("id") or ""


def _priority(h: dict) -> tuple:
    if h["status"] == "falling":
        return (0, h["days_left"], h["name"])
    if h["status"] == "solar" and h["solar_trend"] == "falling":
        return (1, 0.0, h["name"])
    return (2, 0.0, h["name"])


def battery_overview(conn, nodes: dict[int, dict], scope: str, now: float,
                     hours: float = WINDOW_H, limit: int = 200) -> dict:
    """Stato delle batterie per "miei e preferiti" (scope "mine") o per tutti i nodi con dati."""
    since = now - hours * 3600
    visible = {n: node for n, node in nodes.items() if not node.get("is_ignored")}
    if scope == "mine":
        visible = {n: node for n, node in visible.items()
                   if node.get("is_mine") or node.get("is_favorite")}
    rows_by_node: dict[int, list] = defaultdict(list)
    for r in conn.execute(
            "SELECT node_num, time, battery, voltage, uptime FROM telemetry "
            "WHERE time >= ? ORDER BY node_num, time", (since,)):
        if r["node_num"] in visible:
            rows_by_node[r["node_num"]].append(r)
    current: dict[int, dict[str, float]] = defaultdict(dict)
    for r in conn.execute(
            "SELECT node_num, variant, value FROM metrics WHERE time >= ? AND "
            "((variant = 'power' AND metric = 'ch1_current') "
            " OR (variant = 'environment' AND metric = 'current')) ORDER BY time", (since,)):
        if r["node_num"] in visible and r["value"] is not None:
            current[r["node_num"]][r["variant"]] = r["value"]
    out = []
    for num, node in visible.items():
        rows = rows_by_node.get(num, [])
        bat = [(r["time"], r["battery"]) for r in rows if r["battery"] is not None]
        if scope != "mine" and not bat:
            continue
        stats = power_stats([(r["time"], r["voltage"], r["uptime"]) for r in rows])
        cur = current.get(num, {})
        out.append({
            "node_id": node.get("id") or "!%08x" % num, "name": _name(node),
            "is_mine": bool(node.get("is_mine")), "is_favorite": bool(node.get("is_favorite")),
            "battery": bat[-1][1] if bat else node.get("battery"),
            "samples": len(bat), "last_sample": bat[-1][0] if bat else None,
            "voltage": stats["voltage"],
            "current_ma": cur.get("power", cur.get("environment")),
            "uptime_s": stats["uptime_s"], "reboots": stats["reboots"],
            **analyze_battery(bat, now)})
    out.sort(key=_priority)
    return {"generated": now, "window_h": hours, "scope": scope,
            "truncated": len(out) > limit, "nodes": out[:limit]}
