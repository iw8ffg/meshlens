import math

import pytest

from meshlens import health
from meshlens.db import connect
from meshlens.health import (analyze_battery, battery_overview, hourly_buckets, median,
                             power_stats, theil_sen)

NOW = 1_000_000 * 3600.0


def hourly(fn, n=73):
    """Campioni orari (t, valore) per i = 0..n-1 che finiscono a NOW."""
    return [(NOW - (n - 1 - i) * 3600, fn(i)) for i in range(n)]


def test_median_and_buckets():
    assert median([3, 1, 2]) == 2
    assert median([4, 1, 2, 3]) == 2.5
    samples = [(NOW - 100, 50), (NOW - 300, 70), (NOW - 4000, None), (NOW - 5000, 101),
               (NOW - 80 * 3600, 90), (NOW - 7300, 60)]
    b = hourly_buckets(samples, NOW)
    assert b == [(NOW - 7300, 60.0), (NOW - 200, 60.0)]


def test_theil_sen_exact_line():
    pts = [(-72 + i, 90 - 30 * i / 72) for i in range(73)]
    slope, level = theil_sen(pts)
    assert slope == pytest.approx(-0.416667, abs=1e-5)
    assert level == pytest.approx(60.0, abs=1e-6)
    # due campioni a 10 minuti di distanza non producono pendenze enormi
    slope, _ = theil_sen([(-2.0, 50.0), (-1.9, 0.0), (-1.0, 50.0), (0.0, 50.0)])
    assert slope == 0.0  # la coppia a 6 minuti (-2.0, -1.9) e' ignorata


def test_falling_node():
    r = analyze_battery(hourly(lambda i: 90 - 30 * i / 72), NOW)
    assert r["status"] == "falling" and r["level"] == 60.0
    assert r["slope_per_day"] == -10.0 and r["days_left"] == 6.0 and r["solar"] is False


def test_falling_is_robust_to_charge_blip():
    r = analyze_battery(hourly(lambda i: 90 - 30 * i / 72 + (25 if 40 <= i <= 45 else 0)), NOW)
    assert r["status"] == "falling"
    assert abs(r["slope_per_day"] + 10) < 1.5
    assert 5.0 <= r["days_left"] <= 7.0 and r["solar"] is False


def test_charging():
    r = analyze_battery(hourly(lambda i: 50 + 30 * i / 72), NOW)
    assert r["status"] == "charging" and r["days_left"] is None and r["solar"] is False


def test_stable_cases():
    wobble = analyze_battery(hourly(lambda i: 70 + (0.5 if i % 2 else -0.5)), NOW)
    assert wobble["status"] == "stable"
    assert analyze_battery(hourly(lambda i: 70 - 1.5 * i / 72), NOW)["status"] == "stable"
    short = analyze_battery(hourly(lambda i: 70 - 1.2 * i / 24, n=25), NOW)
    assert short["status"] == "stable"  # drop 1.2 < 2
    far = analyze_battery(hourly(lambda i: 90 - 3.6 * i / 72), NOW)
    assert far["status"] == "stable" and far["days_left"] is None  # 72 giorni > 60


def test_insufficient():
    assert analyze_battery(hourly(lambda i: 80 - i, n=5), NOW)["status"] == "insufficient"
    assert analyze_battery(hourly(lambda i: 80 - i, n=13), NOW)["status"] == "insufficient"
    r = analyze_battery([], NOW)
    assert r["status"] == "insufficient" and r["level"] is None


def test_external_power():
    s = hourly(lambda i: 80 - i)[:-1] + [(NOW, 101)]
    r = analyze_battery(s, NOW)
    assert r == {"status": "external", "level": None, "slope_per_day": None, "days_left": None,
                 "solar": False, "solar_trend": None, "solar_peak": None}


def test_level_zero():
    r = analyze_battery(hourly(lambda i: max(0.0, 60 - 2.5 * i)), NOW)
    assert r["status"] == "falling" and r["days_left"] == 0.0


def diurnal(peaks, n=73):
    def v(h):
        k = 0 if h < 24 else 1 if h < 48 else 2
        return 40 + (peaks[k] - 40) * max(0.0, math.sin(math.pi * ((h % 24) - 6) / 12))
    return hourly(v, n)


def test_solar_detection_and_trend():
    r = analyze_battery(diurnal([70, 70, 78]), NOW)
    assert r["solar"] is True and r["status"] == "solar" and r["solar_trend"] == "charging"
    assert r["solar_peak"] == 78.0 and r["days_left"] is None
    assert analyze_battery(diurnal([70, 70, 70]), NOW)["solar_trend"] == "stable"
    assert analyze_battery(diurnal([78, 70, 62]), NOW)["solar_trend"] == "falling"
    short = analyze_battery(diurnal([70, 70, 78])[-30:], NOW)
    assert short["solar"] is False
    short = analyze_battery(diurnal([70, 70, 78])[:30], NOW)
    assert short["solar"] is False
    # due finestre buone e una con buchi: solare, ma senza tendenza
    gappy = [(t, v) for (t, v), h in zip(diurnal([70, 70, 78]), range(73))
             if not (24 <= h < 48) or h in (30, 40)]
    r = analyze_battery(gappy, NOW)
    assert r["solar"] is True and r["solar_trend"] is None


def test_nonsolar_not_flagged():
    assert analyze_battery(hourly(lambda i: 90 - 30 * i / 72), NOW)["solar"] is False
    assert analyze_battery(hourly(lambda i: 50 + 30 * i / 72), NOW)["solar"] is False


def test_power_stats():
    rows = [(1, 3.9, 100), (2, 3.8, 200), (3, 3.8, 50), (4, None, 80)]
    assert power_stats(rows) == {"voltage": 3.8, "uptime_s": 80, "reboots": 1}
    assert power_stats([(1, None, None)]) == {"voltage": None, "uptime_s": None, "reboots": 0}


def seed(conn, num, fn, n=73, voltage=None, uptime=None):
    for i in range(n):
        conn.execute("INSERT INTO telemetry(node_num, time, battery, voltage, uptime) "
                     "VALUES (?,?,?,?,?)", (num, NOW - (n - 1 - i) * 3600, fn(i), voltage, uptime))


def test_battery_overview_mine_and_all():
    conn = connect(":memory:")
    nodes = {1: {"id": "!00000001", "long_name": "Mio", "is_mine": True},
             2: {"id": "!00000002", "long_name": "Pref", "is_favorite": True},
             3: {"id": "!00000003", "long_name": "Altro", "battery": 40},
             4: {"id": "!00000004", "long_name": "Ign", "is_mine": True, "is_ignored": True}}
    seed(conn, 1, lambda i: 90 - 30 * i / 72, voltage=3.7, uptime=500)
    seed(conn, 3, lambda i: 90 - 60 * i / 72)
    seed(conn, 4, lambda i: 50)
    seed(conn, 99, lambda i: 50)  # nodo non in memoria
    conn.execute("INSERT INTO metrics(node_num, time, variant, metric, value) VALUES "
                 "(1, ?, 'environment', 'current', 11), (1, ?, 'power', 'ch1_current', 120)",
                 (NOW - 10, NOW - 20))
    mine = battery_overview(conn, nodes, "mine", NOW)
    assert [n["node_id"] for n in mine["nodes"]] == ["!00000001", "!00000002"]
    first, pref = mine["nodes"]
    assert first["status"] == "falling" and first["days_left"] == pytest.approx(6.0, abs=0.1)
    assert first["current_ma"] == 120 and first["voltage"] == 3.7 and first["uptime_s"] == 500
    assert first["is_mine"] is True and first["samples"] == 73 and first["battery"] == 60
    assert pref["status"] == "insufficient" and pref["samples"] == 0 and pref["is_favorite"]
    assert mine["window_h"] == 72 and mine["truncated"] is False and mine["scope"] == "mine"
    allr = battery_overview(conn, nodes, "all", NOW)
    assert [n["node_id"] for n in allr["nodes"]] == ["!00000003", "!00000001"]  # meno giorni prima
    limited = battery_overview(conn, nodes, "all", NOW, limit=1)
    assert limited["truncated"] is True and limited["nodes"][0]["node_id"] == "!00000003"
    assert set(first) == {
        "node_id", "name", "is_mine", "is_favorite", "battery", "samples", "last_sample",
        "voltage", "current_ma", "uptime_s", "reboots", "status", "level", "slope_per_day",
        "days_left", "solar", "solar_trend", "solar_peak"}


def test_constants_match_plan():
    assert (health.WINDOW_H, health.MIN_BUCKETS, health.MIN_SPAN_H, health.MAX_DAYS) == (
        72, 6, 24, 60)
