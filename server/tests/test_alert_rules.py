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


# ---------------- RuleEngine ----------------
import logging  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from meshlens.events import PositionData  # noqa: E402

LIVE = SimpleNamespace(live=True)
NOT_LIVE = SimpleNamespace(live=False)


def nd(num, **kw):
    return {"num": num, "id": "!%08x" % num, "long_name": f"N{num}", "short_name": None,
            "battery": None, "last_heard": NOW, **kw}


class Harness:
    def __init__(self, nodes=None, ready=True):
        self.conn = connect(":memory:")
        self.store = RuleStore(self.conn)
        self.t = NOW
        self.nodes = {n["num"]: n for n in (nodes or [nd(9)])}
        self.local: set[str] = set()
        self.ready = ready
        self.sent: list = []
        self.recalc = 0
        self.published: list = []
        self.engine = ar.RuleEngine(
            self.store, get_nodes=lambda: self.nodes, get_local_ids=lambda: self.local,
            notify=lambda k, key, **f: self.sent.append((k, key, f)),
            notify_ready=lambda now: self.ready, clock=lambda: self.t,
            request_recalc=self._recalc, publish=self.published.append)

    def _recalc(self):
        self.recalc += 1

    def add(self, **data):
        rule = self.store.create(validate_rule(data), self.t)
        self.engine.reload()
        return rule

    def msg(self, text, **kw):
        m = {"from": "!00000009", "from_name": "Mio", "direction": "in", "text": text,
             "to": "!ffffffff", "radio_id": "r1", "channel_index": 0, "source": "rf"}
        m.update(kw)
        return m

    def alerts(self, previous=None):
        return self.engine.alert_source(self.t, {}, previous or {})

    def pos(self, lat, lon, num=9, **kw):
        ev = dict(from_node=num, source="rf", snr=None, replayed=False, kind="position",
                  payload=PositionData(lat, lon, precision_bits=kw.pop("bits", 32)))
        ev.update(kw)
        return SimpleNamespace(**ev)


def kwrule(h, **extra):
    return h.add(kind="keyword", params={"words": ["aiuto"]}, **extra)


def test_keyword_fires_alert_and_notification():
    h = Harness()
    rule = kwrule(h)
    h.engine.on_message(h.msg("Serve AIUTO subito"), LIVE)
    assert [(k, key) for k, key, _ in h.sent] == [("rule_keyword", f"rule:{rule.id}:!00000009")]
    assert h.sent[0][2] == {"word": "aiuto", "name": "N9", "text": "Serve AIUTO subito"}
    assert h.recalc == 1
    a = h.alerts()
    assert a == [{"key": f"rule:{rule.id}:!00000009", "kind": "rule_keyword",
                  "node_id": "!00000009", "node_name": "N9", "value": 0, "since": NOW,
                  "rule_id": rule.id, "detail": "aiuto"}]


def test_keyword_filters():
    h = Harness()
    rule = kwrule(h, channel="ch:r1:0", node_num=9)
    cases = [
        (h.msg("aiuto"), NOT_LIVE),
        (h.msg("aiuto", direction="out"), LIVE),
        (h.msg("aiuto", emoji=True), LIVE),
        (h.msg("aiuto", channel_index=3), LIVE),
        (h.msg("aiuto", to="!00000001"), LIVE),
        (h.msg("aiuto", **{"from": "!00000007"}), LIVE),
        (h.msg("niente"), LIVE),
        (h.msg(""), LIVE),
    ]
    for m, meta in cases:
        h.engine.on_message(m, meta)
    h.local = {"!00000009"}
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert h.sent == []
    h.local = set()
    h.nodes[9]["is_ignored"] = True  # nodo ignorato: nessuna reazione
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert h.sent == []
    h.nodes[9]["is_ignored"] = False
    h.store.update(rule.id, validate_rule({"enabled": False}, rule), h.t)
    h.engine.reload()
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert h.sent == []


def test_keyword_cooldown_per_rule_and_node():
    h = Harness([nd(9), nd(8)])
    rule = kwrule(h, cooldown_min=10)
    h.engine.on_message(h.msg("aiuto"), LIVE)
    h.t += 100
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert len(h.sent) == 1
    h.engine.on_message(h.msg("aiuto", **{"from": "!00000008"}), LIVE)
    assert len(h.sent) == 2
    h.t += 601
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert len(h.sent) == 3
    a = [x for x in h.alerts() if x["node_id"] == "!00000009"]
    assert len(a) == 1 and a[0]["since"] == h.t
    assert h.store.get(rule.id).last_fired == h.t


def test_keyword_cooldown_updates_last_fired():
    h = Harness()
    rule = kwrule(h)
    assert h.store.get(rule.id).last_fired is None
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert h.store.get(rule.id).last_fired == NOW
    assert h.engine.rules()[0].last_fired == NOW


def test_detection_rule_match():
    h = Harness()
    h.add(kind="detection", params={"match": "porta"}, node_num=9)
    h.engine.on_detection(9, "Finestra detected", 1.0)
    h.engine.on_detection(8, "Porta detected", 1.0)
    assert h.sent == []
    h.engine.on_detection(9, "Porta detected", 1.0)
    assert [(k, f) for k, _, f in h.sent] == [
        ("sensor_detection", {"name": "N9", "text": "Porta detected"})]
    a = h.alerts()[0]
    assert (a["kind"], a["value"], a["detail"]) == ("sensor_detection", 1.0, "Porta detected")
    h2 = Harness()
    h2.add(kind="detection")
    h2.engine.on_detection(9, "boh", None)
    assert len(h2.sent) == 1 and h2.alerts()[0]["value"] == 1.0


GEO_RULE = dict(kind="geofence", node_num=9, name="Casa", params={"polygon": SQUARE})


def test_geofence_first_observation_seeds_silently():
    h = Harness([nd(9)])
    h.add(**GEO_RULE)
    h.engine.on_event(h.pos(40.5, 10.5), "new")
    assert h.sent == [] and h.alerts() == []


def test_geofence_exit_and_enter():
    h = Harness()
    h.add(**GEO_RULE)
    h.engine.on_event(h.pos(40.5, 10.5), "new")  # seme: dentro
    h.engine.on_event(h.pos(45, 12), "new")  # esce
    assert [(k, f["zone"]) for k, _, f in h.sent] == [("rule_geofence_exit", "Casa")]
    assert h.sent[0][2]["lat"] == "45.00000"
    a = h.alerts()[0]
    assert (a["kind"], a["value"], a["detail"]) == ("rule_geofence", 0, "Casa")
    h.t += 4000
    h.engine.on_event(h.pos(40.5, 10.5), "new")  # rientra con trigger exit: nessuna notifica
    assert len(h.sent) == 1
    h2 = Harness()
    h2.add(**{**GEO_RULE, "params": {"polygon": SQUARE, "trigger": "both"}})
    h2.engine.on_event(h2.pos(45, 12), "new")
    h2.engine.on_event(h2.pos(40.5, 10.5), "new")
    assert [k for k, *_ in h2.sent] == ["rule_geofence_enter"]
    assert h2.alerts()[0]["value"] == 1


def test_geofence_ignores_imprecise_and_replayed_and_dup():
    h = Harness()
    h.add(**GEO_RULE)
    h.engine.on_event(h.pos(40.5, 10.5), "new")
    h.engine.on_event(h.pos(45, 12, bits=13), "new")
    h.engine.on_event(h.pos(45, 12, replayed=True), "new")
    h.engine.on_event(h.pos(45, 12), "dup")
    assert h.sent == []
    h.engine.on_event(h.pos(45, 12), "new")  # lo stato era rimasto "dentro"
    assert len(h.sent) == 1


def test_geofence_ignores_nodedb_replay_and_out_of_order_positions():
    h = Harness([nd(9, lat=45, lon=12, precision_bits=32, position_time=1000)])
    h.add(**{**GEO_RULE, "params": {"polygon": SQUARE, "trigger": "both"}})
    h.engine.on_event(h.pos(45, 12, rx_time=1000, packet_id=5), "new")  # seme: fuori
    # replay del node DB della radio (packet_id 0, orario vecchio): dentro
    h.engine.on_event(h.pos(40.5, 10.5, rx_time=500, packet_id=0), "new")
    # pacchetto fuori ordine, piu' vecchio della posizione corrente del nodo
    h.engine.on_event(h.pos(40.5, 10.5, rx_time=600, packet_id=7), "new")
    h.engine.on_event(h.pos(45, 12, rx_time=1100, packet_id=8), "new")
    assert h.sent == []
    h.engine.on_event(h.pos(40.5, 10.5, rx_time=1200, packet_id=9), "new")
    assert [k for k, *_ in h.sent] == ["rule_geofence_enter"]


def test_geofence_reload_seeds_from_live_nodes():
    h = Harness([nd(9, lat=40.5, lon=10.5, precision_bits=32)])
    h.add(**GEO_RULE)
    h.engine.on_event(h.pos(45, 12), "new")
    assert [k for k, *_ in h.sent] == ["rule_geofence_exit"]
    h2 = Harness([nd(9, lat=40.5, lon=10.5, precision_bits=10)])  # offuscata: niente seme
    h2.add(**GEO_RULE)
    h2.engine.on_event(h2.pos(45, 12), "new")
    assert h2.sent == []


def snr_ev(num=9, snr=-9.0, **kw):
    ev = dict(from_node=num, source="rf", snr=snr, replayed=False, kind="text",
              payload=None)
    ev.update(kw)
    return SimpleNamespace(**ev)


def test_snr_samples_only_for_watched_rf_new():
    h = Harness([nd(9), nd(8)])
    h.add(kind="snr_low", node_num=9, threshold=-5)
    for ev, out in [(snr_ev(num=8), "new"), (snr_ev(source="mqtt"), "new"), (snr_ev(), "dup"),
                    (snr_ev(replayed=True), "new"), (snr_ev(snr=None), "new")]:
        h.engine.on_event(ev, out)
    assert not h.engine._snr
    h.engine.on_event(snr_ev(), "new")
    assert len(h.engine._snr[9]) == 1


def test_snr_rule_state_and_notification():
    h = Harness()
    rule = h.add(kind="snr_low", node_num=9, threshold=-5)
    h.alerts()  # primo calcolo: semina
    for _ in range(3):
        h.engine.on_event(snr_ev(snr=-9.0), "new")
    a = h.alerts()
    assert [(x["kind"], x["value"]) for x in a] == [("rule_snr", -9.0)]
    assert [(k, f["snr"], f["thr"]) for k, _, f in h.sent] == [("rule_snr", -9.0, -5)]
    assert a[0]["key"] == f"rule:{rule.id}:!00000009"


def test_snr_clears_with_hysteresis():
    h = Harness()
    h.add(kind="snr_low", node_num=9, threshold=-5)
    h.alerts()
    for _ in range(3):
        h.engine.on_event(snr_ev(snr=-9.0), "new")
    prev = {a["key"]: a for a in h.alerts()}
    h.engine._snr[9].clear()
    for _ in range(3):
        h.engine.on_event(snr_ev(snr=-4.5), "new")
    assert h.alerts(prev)  # ancora attivo (soglia + 1)
    h.engine._snr[9].clear()
    for _ in range(3):
        h.engine.on_event(snr_ev(snr=-3.0), "new")
    assert h.alerts(prev) == []


def test_state_rules_battery_and_silent():
    h = Harness([nd(9, battery=10, last_heard=NOW - 5 * 3600), nd(8)])
    h.add(kind="battery", node_num=9, threshold=20)
    h.add(kind="silent", node_num=9, threshold=2)
    a = {x["kind"]: x for x in h.alerts()}
    assert a["rule_battery"]["value"] == 10 and a["rule_silent"]["value"] == 5.0


def test_first_call_seeds_without_notifying():
    h = Harness([nd(9, battery=10)])
    h.add(kind="battery", node_num=9, threshold=20)
    first = h.alerts()
    assert first and h.sent == []
    prev = {a["key"]: a for a in first}
    h.t += 60
    assert h.alerts(prev) and h.sent == []
    h.nodes[8] = nd(8, battery=5)
    h.add(kind="battery", node_num=8, threshold=20)  # regola nuova, subito vera
    h.alerts(prev)
    assert [(k, f["name"], f["pct"]) for k, _, f in h.sent] == [("rule_battery", "N8", 5)]


def test_state_notification_requires_ready_and_cooldown():
    h = Harness([nd(9, battery=50)], ready=False)
    h.add(kind="battery", node_num=9, threshold=20, cooldown_min=30)
    h.alerts()  # seme
    h.nodes[9]["battery"] = 10
    assert h.alerts() and h.sent == []  # non pronto: avviso visibile, nessuna notifica
    h.ready = True
    h.nodes[9]["battery"] = 50
    prev: dict = {}
    assert h.alerts(prev) == []
    h.nodes[9]["battery"] = 10
    assert h.alerts(prev) and len(h.sent) == 1
    h.nodes[9]["battery"] = 50
    h.alerts(prev)
    h.t += 60
    h.nodes[9]["battery"] = 10
    assert h.alerts(prev) and len(h.sent) == 1  # pausa non trascorsa
    h.nodes[9]["battery"] = 50
    h.alerts(prev)
    h.t += 1800
    h.nodes[9]["battery"] = 10
    h.alerts(prev)
    assert len(h.sent) == 2


def test_state_alert_since_preserved():
    h = Harness([nd(9, battery=10)])
    h.add(kind="battery", node_num=9, threshold=20)
    first = h.alerts()
    h.t += 500
    second = h.alerts({a["key"]: a for a in first})
    assert second[0]["since"] == first[0]["since"] == NOW


def test_event_alerts_expire_after_keep_window():
    h = Harness()
    kwrule(h)
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert len(h.alerts()) == 1
    h.t += ar.EVENT_KEEP_S + 1
    assert h.alerts() == []


def test_reload_drops_state_of_deleted_or_disabled_rules():
    h = Harness()
    rule = kwrule(h)
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert h.alerts()
    h.store.delete(rule.id)
    h.engine.reload()
    assert h.alerts() == [] and h.engine.rules() == []
    geo = h.add(**GEO_RULE)
    h.engine.on_event(h.pos(40.5, 10.5), "new")
    h.store.update(geo.id, validate_rule({"enabled": False}, geo), h.t + 1)
    h.engine.reload()
    assert h.engine._inside == {}


def test_disabled_rule_never_fires():
    h = Harness([nd(9, battery=1)])
    r = h.add(kind="battery", node_num=9, threshold=20, enabled=False)
    k = h.add(kind="keyword", params={"words": ["aiuto"]}, enabled=False)
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert h.alerts() == [] and h.sent == [] and r and k


def test_ignored_node_has_no_state_alerts():
    h = Harness([nd(9, battery=1, is_ignored=True)])
    h.add(kind="battery", node_num=9, threshold=20)
    assert h.alerts() == []


def test_restoring_an_ignored_node_is_not_news():
    h = Harness([nd(9, battery=10)])
    h.add(kind="battery", node_num=9, threshold=20)
    h.alerts()  # seme
    assert len(h.alerts()) == 1
    h.nodes[9]["is_ignored"] = True
    assert h.alerts() == []
    h.nodes[9]["is_ignored"] = False
    assert len(h.alerts()) == 1  # l'avviso ricompare, ma senza una nuova notifica
    assert h.sent == []


def test_engine_exceptions_in_one_rule_do_not_break_others(caplog):
    h = Harness([nd(9, battery=5)])
    h.add(kind="geofence", node_num=9, params={"polygon": SQUARE})
    h.add(kind="battery", node_num=9, threshold=20)
    bad = h.add(kind="keyword", params={"words": ["aiuto"]})
    h.engine._rules[bad.id] = replace_params(bad, {"words": 5})
    good = h.add(kind="keyword", params={"words": ["aiuto"]})
    h.engine._rules[bad.id] = replace_params(bad, {"words": 5})
    h.engine._rules[next(i for i, r in h.engine._rules.items() if r.kind == "geofence")] = \
        replace_params(h.engine.rules()[0], {})
    with caplog.at_level(logging.ERROR):
        h.engine.on_message(h.msg("aiuto segreto"), LIVE)
        h.engine.on_event(h.pos(45, 12), "new")
        out = h.alerts()
    kinds = sorted(a["kind"] for a in out)
    assert kinds == ["rule_battery", "rule_keyword"]
    assert any(k == "rule_keyword" for k, *_ in h.sent) and good
    assert str(bad.id) in caplog.text
    # testi e coordinate non finiscono nei messaggi di log (i traceback contengono percorsi:
    # si controllano solo i messaggi, non i nomi delle cartelle)
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "segreto" not in caplog.text and "45" not in msgs


def replace_params(rule, params):
    import dataclasses
    return dataclasses.replace(rule, params=params)


# ---------------- install (ext_monitor) ----------------
import asyncio  # noqa: E402
import time  # noqa: E402

from meshlens import ext_monitor  # noqa: E402
from meshlens.api import AppContext  # noqa: E402
from meshlens.auth import Auth  # noqa: E402
from meshlens.bus import Bus  # noqa: E402
from meshlens.geo import CountryLocator  # noqa: E402
from meshlens.live import LiveState  # noqa: E402
from meshlens.store import Store  # noqa: E402


class FakeNotifier:
    def __init__(self):
        self.sent = []
        self.ready = True

    def send(self, kind, key, **kw):
        self.sent.append((kind, key, kw))

    def rules_ready(self, now=None):
        return self.ready

    def on_alerts(self, old, new):
        pass


def make_ctx():
    conn = connect(":memory:")
    live = LiveState()
    live.load([{"id": "!00000009", "num": 9, "long_name": "Mio", "country": "IT",
                "last_heard": time.time(), "is_mine": False}])

    async def changed(_s):
        return None

    ctx = AppContext(live=live, store=Store(conn), auth=Auth(conn), bus=Bus(),
                     locator=CountryLocator(), conn=conn,
                     mqtt_status=lambda: {"connected": True, "msgs_per_s": 0.0, "undecodable": 0},
                     on_settings_changed=changed, static_dir=None)
    ctx.notifier = FakeNotifier()
    return ctx


def make_rt():
    rt = SimpleNamespace(ingestor=SimpleNamespace(persists=lambda n, s: True),
                         message_hooks=[], event_hooks=[])
    rt.add_message_hook = rt.message_hooks.append
    rt.add_event_hook = rt.event_hooks.append
    return rt


def test_install_registers_hooks_and_source():
    ctx, rt = make_ctx(), make_rt()
    ext_monitor.install(rt, ctx)
    assert ctx.ext["alert_rules"] is not None and ctx.ext["sensors"] is not None
    assert len(ctx.alert_sources) == 1
    assert len(rt.message_hooks) == 1
    assert rt.event_hooks == [ctx.ext["sensors"].on_event, ctx.ext["alert_rules"].on_event]


async def test_keyword_end_to_end():
    ctx, rt = make_ctx(), make_rt()
    ext_monitor.install(rt, ctx)
    rule = RuleStore(ctx.conn).create(
        validate_rule({"kind": "keyword", "params": {"words": ["aiuto"]}}), time.time())
    ctx.ext["alert_rules"].reload()
    calls = []
    real = ctx.alerts
    ctx.alerts = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    q = ctx.bus.subscribe()
    msg = {"from": "!00000009", "from_name": "Mio", "direction": "in", "text": "aiuto!",
           "to": "!ffffffff", "radio_id": "r1", "channel_index": 0, "source": "rf"}
    rt.message_hooks[0](msg, LIVE)
    rt.message_hooks[0](msg, LIVE)
    assert [(k, key) for k, key, _ in ctx.notifier.sent][0] == (
        "rule_keyword", f"rule:{rule.id}:!00000009")
    assert ctx.notifier.sent[0][2]["dedup"] is False
    assert calls == []
    await asyncio.sleep(0)
    assert calls == [1]  # un solo ricalcolo per piu' scatti
    assert [a["kind"] for a in ctx._alerts] == ["rule_keyword"]
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    assert any(e.get("type") == "alerts" for e in events)


def test_request_recalc_without_loop_is_noop():
    ctx, rt = make_ctx(), make_rt()
    ext_monitor.install(rt, ctx)
    RuleStore(ctx.conn).create(
        validate_rule({"kind": "keyword", "params": {"words": ["aiuto"]}}), time.time())
    ctx.ext["alert_rules"].reload()
    msg = {"from": "!00000009", "direction": "in", "text": "aiuto", "to": "!ffffffff",
           "radio_id": "r1", "channel_index": 0}
    rt.message_hooks[0](msg, LIVE)  # nessun loop in esecuzione: nessuna eccezione
    assert len(ctx.notifier.sent) == 1


def test_alerts_includes_rule_alerts_sorted():
    ctx, rt = make_ctx(), make_rt()
    ctx.live.nodes[9]["is_mine"] = True
    ctx.live.nodes[9]["last_heard"] = time.time() - 30 * 3600
    ctx.live.nodes[9]["battery"] = 5
    ext_monitor.install(rt, ctx)
    RuleStore(ctx.conn).create(
        validate_rule({"kind": "battery", "node_num": 9, "threshold": 20}), time.time())
    ctx.ext["alert_rules"].reload()
    kinds = [a["kind"] for a in ctx.alerts()]
    assert kinds == ["battery_low", "silent", "rule_battery"]


def test_install_survives_missing_radios():
    ctx, rt = make_ctx(), make_rt()
    ctx.radios = None
    ext_monitor.install(rt, ctx)
    assert ctx.ext["alert_rules"].get_local_ids() == set()


def test_build_installs_monitor_extension(tmp_path):
    from meshlens.app import build
    from test_app import FakeConnector
    app, rt = build(tmp_path, connector_factory=FakeConnector, static_dir=None)
    assert "alert_rules" in rt.ctx.ext and "sensors" in rt.ctx.ext


def test_cooldown_survives_edit_and_restart():
    h = Harness()
    rule = kwrule(h, node_num=9, cooldown_min=60)
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert len(h.sent) == 1
    # rinomina: lo stato resta, niente nuovo avviso
    h.store.update(rule.id, validate_rule({"name": "Altro nome"}, h.store.get(rule.id)), h.t + 1)
    h.engine.reload()
    h.t += 10
    h.engine.on_message(h.msg("aiuto"), LIVE)
    assert len(h.sent) == 1
    # riavvio: motore nuovo sulla stessa tabella, last_fired persistito
    from meshlens.alert_rules import RuleEngine
    e2 = RuleEngine(h.store, get_nodes=lambda: h.nodes, get_local_ids=lambda: set(),
                    notify=lambda kind, key, **f: h.sent.append((kind, key, f)),
                    notify_ready=lambda now: True, clock=lambda: h.t)
    e2.reload()
    e2.on_message(h.msg("aiuto"), LIVE)
    assert len(h.sent) == 1
    # cambio di parole chiave: la regola e' un'altra, il cooldown riparte
    h.store.update(rule.id, validate_rule({"params": {"words": ["soccorso"]}},
                                          h.store.get(rule.id)), h.t + 2)
    e2.reload()
    e2.on_message(h.msg("soccorso"), LIVE)
    assert len(h.sent) == 2


def test_empty_detection_text_does_not_fire_rule():
    h = Harness()
    h.add(kind="detection")
    h.engine.on_detection(9, "", None)
    assert h.sent == []
