import pytest

from meshlens import alert_rules as ar
from meshlens.alert_rules import (Rule, RuleStore, battery_state, channel_selector,
                                  geofence_transition, keyword_match, point_in_polygon,
                                  polygon_error, silent_state, snr_state, validate_rule)
from meshlens.db import connect

NOW = 1_000_000.0
SQUARE = [[10, 40], [11, 40], [11, 41], [10, 41]]


def mk(kind="keyword", **kw):
    base = dict(id=1, kind=kind, name="", enabled=True, node_num=None, channel=None,
                threshold=None, params={}, cooldown_min=60, created=0.0, updated=0.0,
                last_fired=None)
    return Rule(**{**base, **kw})


def test_validate_ok_per_kind():
    r = validate_rule({"kind": "keyword", "name": " Aiuto ", "threshold": 5, "channel": "ch:r1:2",
                       "params": {"words": [" Aiuto", "SOS", "aiuto", "sos "]}})
    assert r == {"kind": "keyword", "name": "Aiuto", "enabled": True, "node_num": None,
                 "channel": "ch:r1:2", "threshold": None,
                 "params": {"words": ["Aiuto", "SOS"], "whole_word": False}, "cooldown_min": 60}
    r = validate_rule({"kind": "snr_low", "node_num": 9, "threshold": -7.5, "channel": "ch:r1:2"})
    assert r["channel"] is None and r["threshold"] == -7.5
    assert r["params"] == {"window_min": 60, "min_samples": 3}
    r = validate_rule({"kind": "geofence", "node_num": 9,
                       "params": {"polygon": SQUARE + [SQUARE[0]], "trigger": "both"}})
    assert r["params"] == {"polygon": [[10.0, 40.0], [11.0, 40.0], [11.0, 41.0], [10.0, 41.0]],
                           "trigger": "both"}
    assert validate_rule({"kind": "geofence", "node_num": 9,
                          "params": {"polygon": SQUARE}})["params"]["trigger"] == "exit"
    r = validate_rule({"kind": "battery", "node_num": 9, "threshold": 20, "cooldown_min": 5})
    assert r["threshold"] == 20.0 and r["params"] == {} and r["cooldown_min"] == 5
    r = validate_rule({"kind": "silent", "node_num": 9, "threshold": 0.25})
    assert r["threshold"] == 0.25
    r = validate_rule({"kind": "detection", "threshold": 3, "params": {"match": " porta "}})
    assert r["threshold"] is None and r["params"] == {"match": "porta"} and r["node_num"] is None
    assert validate_rule({"kind": "detection"})["params"] == {"match": ""}


KW = {"kind": "keyword", "params": {"words": ["aiuto"]}}
BAT = {"kind": "battery", "node_num": 9, "threshold": 20}
SNR = {"kind": "snr_low", "node_num": 9, "threshold": -5}
SIL = {"kind": "silent", "node_num": 9, "threshold": 2}
GEO = {"kind": "geofence", "node_num": 9, "params": {"polygon": SQUARE}}
DET = {"kind": "detection"}


def with_(base, **kw):
    return {**base, **kw}


def with_params(base, **params):
    return {**base, "params": {**base.get("params", {}), **params}}


@pytest.mark.parametrize("data,msg", [
    (with_(BAT, threshold=0), ar.MSG_RULE_BATTERY),
    (with_(BAT, threshold=100), ar.MSG_RULE_BATTERY),
    (with_(SNR, threshold=-31), ar.MSG_RULE_SNR),
    (with_(SNR, threshold=21), ar.MSG_RULE_SNR),
    (with_(SIL, threshold=0.2), ar.MSG_RULE_SILENT),
    (with_(SIL, threshold=169), ar.MSG_RULE_SILENT),
    (with_params(SNR, window_min=14), ar.MSG_RULE_WINDOW),
    (with_params(SNR, min_samples=0), ar.MSG_RULE_SAMPLES),
    (with_params(SNR, min_samples=51), ar.MSG_RULE_SAMPLES),
    (with_params(KW, words=[f"parola{i}" for i in range(11)]), ar.MSG_RULE_WORDS),
    (with_params(KW, words=["a"]), ar.MSG_RULE_WORDS),
    (with_params(KW, words=["a" * 33]), ar.MSG_RULE_WORDS),
    (with_params(KW, words=[]), ar.MSG_RULE_WORDS),
    (with_params(GEO, trigger="x"), ar.MSG_RULE_TRIGGER),
    (with_params(DET, match="m" * 33), ar.MSG_RULE_MATCH),
    (with_params(BAT, boh=1), ar.MSG_RULE_PARAMS),
    (with_params(KW, boh=1), ar.MSG_RULE_PARAMS),
    (with_(KW, channel="ch:r1:8"), ar.MSG_RULE_CHANNEL),
    (with_(KW, channel="foo"), ar.MSG_RULE_CHANNEL),
    (with_(KW, channel="mqtt:"), ar.MSG_RULE_CHANNEL),
    (with_(BAT, cooldown_min=0), ar.MSG_RULE_COOLDOWN),
    (with_(BAT, cooldown_min=1441), ar.MSG_RULE_COOLDOWN),
    (with_(BAT, name="n" * 61), ar.MSG_RULE_NAME),
    ({"kind": "battery", "threshold": 20}, ar.MSG_RULE_NODE_REQUIRED),
    (with_(BAT, kind="x"), ar.MSG_RULE_KIND),
    (with_params(GEO, polygon=[[0, 0], [1, 1]]), ar.MSG_RULE_POLYGON),
])
def test_validate_errors(data, msg):
    with pytest.raises(ValueError) as e:
        validate_rule(data)
    assert str(e.value) == msg


def test_validate_patch_inherits():
    rule = mk("battery", node_num=9, threshold=20.0)
    out = validate_rule({"enabled": False}, existing=rule)
    assert out["kind"] == "battery" and out["threshold"] == 20.0 and out["enabled"] is False
    assert out["node_num"] == 9
    kw = mk("keyword", params={"words": ["aiuto"], "whole_word": False})
    out = validate_rule({"threshold": 5}, existing=kw)
    assert out["threshold"] is None and out["params"]["words"] == ["aiuto"]


def test_polygon_rules():
    assert polygon_error([[0, 0], [1, 0], [0, 1]]) is None
    for bad in ([[0, 0], [1, 1]], [[i / 100, (i % 7) / 100] for i in range(65)],
                [[0, 91], [1, 0], [0, 1]], [[181, 0], [1, 0], [0, 1]],
                [[float("nan"), 0], [1, 0], [0, 1]]):
        assert polygon_error(bad) == ar.MSG_RULE_POLYGON
    for bad in ([[0, 0], [1, 1], [1, 0], [0, 1]], [[0, 0], [1, 1], [2, 2]],
                [[-100, 0], [100, 0], [0, 10]]):
        assert polygon_error(bad) == ar.MSG_RULE_POLYGON_SHAPE
    assert ar.normalize_polygon([[0, 0], [1, 0], [0, 1], [0, 0]]) == [[0, 0], [1, 0], [0, 1]]


def test_point_in_polygon():
    assert point_in_polygon(10.5, 40.5, SQUARE)
    assert not point_in_polygon(12, 40.5, SQUARE)
    assert not point_in_polygon(10.5, 42, SQUARE)
    assert point_in_polygon(10, 40, SQUARE)  # vertice
    assert point_in_polygon(10.5, 40, SQUARE)  # lato
    ell = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]]
    assert point_in_polygon(0.5, 3, ell)
    assert not point_in_polygon(3, 3, ell)  # nella tacca


def test_channel_selector():
    m = {"to": "!ffffffff", "radio_id": "r1", "channel_index": 2, "source": "rf"}
    assert channel_selector(m) == "ch:r1:2"
    assert channel_selector({**m, "channel_index": None}) == "ch:r1:0"
    assert channel_selector({"to": "!ffffffff", "source": "mqtt", "channel": "Meteo",
                             "radio_id": None}) == "mqtt:Meteo"
    assert channel_selector({**m, "to": "!00000009"}) is None


def test_keyword_match():
    r = mk(params={"words": ["aiuto", "SOS"], "whole_word": False})
    assert keyword_match(r, "Serve AIUTO!") == "aiuto"
    assert keyword_match(mk(params={"words": ["perche"]}), "perché no") == "perche"
    w = mk(params={"words": ["aiuto"], "whole_word": True})
    assert keyword_match(w, "aiutorella") is None
    assert keyword_match(w, "ho bisogno d'aiuto.") == "aiuto"
    for whole in (True, False):
        dot = mk(params={"words": ["a.b"], "whole_word": whole})
        assert keyword_match(dot, "axb") is None
        assert keyword_match(dot, "a.b") == "a.b"


def test_snr_state():
    r = mk("snr_low", threshold=-5.0, params={"window_min": 60, "min_samples": 3})
    s = lambda *v: [(NOW - 10 * (i + 1), x) for i, x in enumerate(v)]  # noqa: E731
    assert snr_state(s(-7, -7), NOW, r, False) is None
    assert snr_state(s(-7, -7, -7), NOW, r, False) == -7.0
    old = [(NOW - 7200, -20)] * 5
    assert snr_state(old + s(-7, -7, -7), NOW, r, False) == -7.0
    assert snr_state(s(-4.5, -4.5, -4.5), NOW, r, True) == -4.5
    assert snr_state(s(-3.9, -3.9, -3.9), NOW, r, True) is None
    assert snr_state(s(-4.5, -4.5, -4.5), NOW, r, False) is None


def test_battery_state():
    r = mk("battery", threshold=20.0)
    assert battery_state({"battery": 15}, r, False) == 15
    assert battery_state({"battery": None}, r, False) is None
    assert battery_state({"battery": 101}, r, False) is None
    assert battery_state({"battery": 21}, r, True) == 21
    assert battery_state({"battery": 22}, r, True) is None
    assert battery_state({"battery": 21}, r, False) is None


def test_silent_state():
    r = mk("silent", threshold=2.0)
    assert silent_state({"last_heard": NOW - 3 * 3600}, r, NOW) == 3.0
    assert silent_state({"last_heard": NOW - 1.5 * 3600}, r, NOW) is None
    assert silent_state({"last_heard": None}, r, NOW) is None
    assert silent_state({"last_heard": NOW - 7500}, r, NOW) == 2.1


def test_geofence_transition():
    assert geofence_transition("exit", True, False) == "exit"
    assert geofence_transition("exit", False, True) is None
    assert geofence_transition("enter", False, True) == "enter"
    assert geofence_transition("both", True, False) == "exit"
    assert geofence_transition("both", None, True) is None
    assert geofence_transition("both", True, True) is None


def test_rule_store_crud():
    conn = connect(":memory:")
    st = RuleStore(conn)
    f = validate_rule({"kind": "battery", "node_num": 9, "threshold": 20})
    r = st.create(f, 100.0)
    assert r.id and r.created == r.updated == 100.0 and r.last_fired is None
    assert r.to_json()["node_id"] == "!00000009"
    r2 = st.create(validate_rule(KW), 101.0)
    assert [x.id for x in st.list()] == [r.id, r2.id]
    up = st.update(r.id, validate_rule({"enabled": False}, r), 200.0)
    assert up.updated == 200.0 and up.enabled is False and up.created == 100.0
    assert st.update(999, f, 1.0) is None
    st.touch_fired(r.id, 300.0)
    assert st.get(r.id).last_fired == 300.0
    assert st.delete(r.id) is True and st.delete(r.id) is False
    for _ in range(ar.MAX_RULES - 1):
        st.create(f, 1.0)
    with pytest.raises(ValueError) as e:
        st.create(f, 1.0)
    assert str(e.value) == ar.MSG_RULES_MAX


def test_error_messages_are_constants_and_listed():
    consts = [v for k, v in vars(ar).items() if k.startswith("MSG_")]
    assert set(ar.ERROR_MESSAGES) == set(consts)
    assert len(ar.ERROR_MESSAGES) == len(set(ar.ERROR_MESSAGES))
