from meshlens.alerts import compute_alerts

SET = {"battery_alert_pct": 20, "silent_alert_hours": 6}
NOW = 1_000_000.0


def node(num, **kw):
    base = {"num": num, "id": f"!{num:08x}", "long_name": f"N{num}", "short_name": None,
            "is_mine": True, "battery": None, "last_heard": NOW}
    return {**base, **kw}


def test_battery_low_only_for_mine():
    out = compute_alerts([node(1, battery=15), node(2, battery=5, is_mine=False)], SET, NOW, {})
    assert out == [{"key": "battery:!00000001", "kind": "battery_low", "node_id": "!00000001",
                    "node_name": "N1", "value": 15, "since": NOW}]


def test_battery_101_and_none_ignored():
    out = compute_alerts([node(1, battery=101), node(2, battery=None)], SET, NOW, {})
    assert out == []


def test_silent_after_threshold():
    out = compute_alerts([node(1, last_heard=NOW - 7 * 3600)], SET, NOW, {})
    assert [(a["kind"], a["value"]) for a in out] == [("silent", 7)]
    assert compute_alerts([node(1, last_heard=NOW - 5 * 3600)], SET, NOW, {}) == []
    assert compute_alerts([node(1, last_heard=None)], SET, NOW, {}) == []


def test_order_and_name_fallback():
    nodes = [node(3, last_heard=NOW - 8 * 3600, long_name=None, short_name="ZZ"),
             node(2, last_heard=NOW - 8 * 3600, long_name="Alfa"),
             node(1, battery=10, long_name="Omega")]
    out = compute_alerts(nodes, SET, NOW, {})
    assert [a["node_name"] for a in out] == ["Omega", "Alfa", "ZZ"]


def test_since_preserved():
    first = compute_alerts([node(1, battery=10)], SET, NOW, {})
    second = compute_alerts([node(1, battery=9)], SET, NOW + 60, {a["key"]: a for a in first})
    assert second[0]["since"] == NOW and second[0]["value"] == 9
