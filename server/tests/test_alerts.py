from meshlens.alerts import compute_alerts, parse_firmware

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


def test_chutil_high_only_for_mine_and_threshold():
    nodes = [node(1), node(2, is_mine=False)]
    out = compute_alerts(nodes, SET, NOW, {}, chutil={"!00000001": 31.26, "!00000002": 40})
    assert [(a["key"], a["kind"], a["value"]) for a in out] ==         [("chutil:!00000001", "chutil_high", 31.3)]
    assert "detail" not in out[0]
    assert compute_alerts(nodes, SET, NOW, {}, chutil={"!00000001": 24.9}) == []


def test_firmware_old():
    out = compute_alerts([node(1, firmware="2.3.2.63df972")], SET, NOW, {})
    assert [(a["key"], a["kind"], a["value"], a["detail"]) for a in out] ==         [("firmware:!00000001", "firmware_old", 0, "2.3.2.63df972")]
    assert compute_alerts([node(1, firmware="2.5.0.abc")], SET, NOW, {}) == []
    assert compute_alerts([node(1, firmware=None)], SET, NOW, {}) == []
    assert compute_alerts([node(1, firmware="boh")], SET, NOW, {}) == []


def test_parse_firmware():
    assert parse_firmware("2.6.11.60ec05e") == (2, 6, 11)
    assert parse_firmware("2.5") is None
    assert parse_firmware(None) is None
    assert parse_firmware("2.3².1") is None
    assert parse_firmware("v2.3.2") == (2, 3, 2)
    assert parse_firmware("2.5.0-rc1") == (2, 5, 0)


def test_raising_silent_hours_no_false_back_online():
    first = compute_alerts([node(1, last_heard=NOW - 7 * 3600)], SET, NOW, {})
    assert [a["kind"] for a in first] == ["silent"]
    relaxed = dict(SET, silent_alert_hours=12)
    second = compute_alerts([node(1, last_heard=NOW - 7 * 3600)], relaxed, NOW + 60,
                            {a["key"]: a for a in first})
    assert second == []


def test_back_online_after_silent():
    first = compute_alerts([node(1, last_heard=NOW - 7 * 3600)], SET, NOW, {})
    assert [a["kind"] for a in first] == ["silent"]
    t1 = NOW + 120
    second = compute_alerts([node(1, last_heard=NOW + 60)], SET, t1, {a["key"]: a for a in first})
    assert [(a["key"], a["kind"], a["value"], a["since"]) for a in second] ==         [("online:!00000001", "back_online", 7, t1)]
    third = compute_alerts([node(1, last_heard=NOW + 60)], SET, t1 + 3599,
                           {a["key"]: a for a in second})
    assert [(a["kind"], a["value"], a["since"]) for a in third] == [("back_online", 7, t1)]
    fourth = compute_alerts([node(1, last_heard=NOW + 60)], SET, t1 + 3601,
                            {a["key"]: a for a in third})
    assert fourth == []


def test_back_online_dropped_when_silent_again():
    prev = {"online:!00000001": {"key": "online:!00000001", "since": NOW, "value": 7}}
    out = compute_alerts([node(1, last_heard=NOW - 8 * 3600)], SET, NOW + 10, prev)
    assert [a["kind"] for a in out] == ["silent"]


def test_back_online_not_without_previous_silent():
    assert compute_alerts([node(1)], SET, NOW, {}) == []


def test_kind_order():
    nodes = [node(4, firmware="2.3.0.x", long_name="D"),
             node(3, long_name="C"),
             node(2, last_heard=NOW - 8 * 3600, long_name="B"),
             node(1, battery=5, long_name="A")]
    out = compute_alerts(nodes, SET, NOW, {}, chutil={"!00000003": 50.0})
    assert [a["kind"] for a in out] == ["battery_low", "silent", "chutil_high", "firmware_old"]


def test_key_changed_for_mine_and_favorite():
    fav = node(5, is_mine=False, is_favorite=True, key_changed=NOW - 3600, battery=5,
               last_heard=NOW - 9 * 3600)
    out = compute_alerts([fav], SET, NOW, {})
    assert out == [{"key": "pki:!00000005", "kind": "key_changed", "node_id": "!00000005",
                    "node_name": "N5", "value": 0, "since": NOW - 3600}]
    assert compute_alerts([{**fav, "key_changed": NOW - 8 * 86400}], SET, NOW, {}) == []
    assert compute_alerts([node(6, is_mine=False, key_changed=NOW - 60)], SET, NOW, {}) == []
    nodes = [node(1, key_changed=NOW - 60, long_name="A"),
             node(2, last_heard=NOW - 8 * 3600, long_name="B"),
             node(3, long_name="C")]
    out = compute_alerts(nodes, SET, NOW, {}, chutil={"!00000003": 50.0})
    assert [a["kind"] for a in out] == ["silent", "key_changed", "chutil_high"]


def test_sort_key_unknown_kind_last():
    from meshlens.alerts import KIND_ORDER, sort_key
    assert sort_key({"kind": "zzz", "node_name": "a"}) > sort_key({"kind": "autonomy_low", "node_name": "a"})
    assert set(KIND_ORDER) == {
        "battery_low", "silent", "key_changed", "chutil_high", "firmware_old", "back_online",
        "rule_keyword", "rule_snr", "rule_geofence", "rule_battery", "rule_silent",
        "sensor_detection", "autonomy_low"}
