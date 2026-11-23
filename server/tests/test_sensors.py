import pytest
from meshtastic.protobuf import paxcount_pb2

from meshlens import queries
from meshlens.db import connect
from meshlens.events import AppData, MeshEvent
from meshlens.sensors import (SensorService, clean_detection_text, detection_value, list_events,
                              parse_paxcount)
from meshlens.store import Store

NOW = 1_800_000_000.0


def ev(kind, payload, num=10, t=NOW, source="rf", **kw):
    d = dict(source=source, from_node=num, to_node=0xFFFFFFFF, packet_id=77, channel="Primary",
             rx_time=t, snr=-7.5, rssi=None, hops=2, gateway_id=None, radio_id="r1",
             broker="b1")
    d.update(kw)
    return MeshEvent(kind=kind, payload=payload, **d)


def det(text="Porta detected\x07", **kw):
    return ev("detection", AppData(10, text.encode(), text), **kw)


def pax(wifi=3, ble=5, uptime=60, **kw):
    raw = paxcount_pb2.Paxcount(wifi=wifi, ble=ble, uptime=uptime).SerializeToString()
    return ev("paxcounter", AppData(34, raw), **kw)


class Env:
    def __init__(self, persists=True):
        self.conn = connect(":memory:")
        self.store = Store(self.conn)
        self.published: list = []
        self.detected: list = []
        self.svc = SensorService(
            self.conn, self.store, self.published.append, lambda n: {"num": n, "id": "!%08x" % n},
            lambda node, source: persists,
            on_detection=lambda *a: self.detected.append(a))


def test_clean_detection_text():
    assert clean_detection_text("Porta detected\x07") == "Porta detected"
    assert clean_detection_text("\x07") == ""
    assert len(clean_detection_text("x" * 300)) == 200
    assert clean_detection_text("a\nb\x00c") == "abc"
    assert clean_detection_text(None) == ""


def test_detection_value():
    assert detection_value("Porta detected") == 1.0
    assert detection_value("Porta cleared") == 0.0
    assert detection_value("boh") is None
    assert detection_value("PORTA DETECTED") == 1.0
    assert detection_value("Rilevato") == 1.0
    assert detection_value("Ripristinato") == 0.0


def test_parse_paxcount():
    raw = paxcount_pb2.Paxcount(wifi=3, ble=5, uptime=60).SerializeToString()
    assert parse_paxcount(raw) == {"wifi": 3.0, "ble": 5.0, "uptime": 60.0}
    assert parse_paxcount(b"\xff\xff") == {}
    assert parse_paxcount(b"") == {"wifi": 0.0, "ble": 0.0, "uptime": 0.0}


def test_detection_event_persisted_and_published():
    e = Env()
    e.svc.on_event(det(), "new")
    row = e.conn.execute("SELECT * FROM sensor_events").fetchone()
    assert (row["kind"], row["text"], row["value"], row["source"], row["radio_id"],
            row["broker"], row["packet_id"], row["node_num"], row["time"]) == (
        "detection", "Porta detected", 1.0, "rf", "r1", "b1", 77, 10, NOW)
    assert len(e.published) == 1
    pub = e.published[0]
    assert pub["type"] == "sensor_event" and pub["event"]["node_id"] == "!0000000a"
    assert pub["event"]["text"] == "Porta detected"
    assert list_events(e.conn, 10, 0) == [pub["event"]]
    assert set(pub["event"]) == {"id", "node_id", "time", "kind", "text", "value", "source"}
    assert e.detected == [(10, "Porta detected", 1.0)]


def test_detection_not_persisted_but_rules_notified():
    e = Env(persists=False)
    e.svc.on_event(det(), "new")
    assert e.conn.execute("SELECT COUNT(*) FROM sensor_events").fetchone()[0] == 0
    assert e.published == []
    assert e.detected == [(10, "Porta detected", 1.0)]


def test_ignored_cases():
    e = Env()
    e.svc.on_event(det(), "dup")
    e.svc.on_event(det(replayed=True), "new")
    e.svc.on_event(ev("text", AppData(10, b"x", "x")), "new")
    e.svc.on_event(pax(), "dup")
    assert e.detected == [] and e.published == []
    assert e.conn.execute("SELECT COUNT(*) FROM sensor_events").fetchone()[0] == 0
    assert e.conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 0


def test_paxcounter_metrics():
    e = Env()
    e.svc.on_event(pax(), "new")
    rows = e.conn.execute("SELECT variant, metric, value, time FROM metrics").fetchall()
    assert sorted((r["variant"], r["metric"], r["value"], r["time"]) for r in rows) == [
        ("paxcounter", "ble", 5.0, NOW), ("paxcounter", "uptime", 60.0, NOW),
        ("paxcounter", "wifi", 3.0, NOW)]
    assert queries.metric_series(e.conn, 10, 0)["latest"]["paxcounter.wifi"]["value"] == 3.0
    n = Env(persists=False)
    n.svc.on_event(pax(), "new")
    assert n.conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 0
    bad = Env()
    bad.svc.on_event(ev("paxcounter", AppData(34, b"\xff\xff")), "new")
    assert bad.conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 0


def test_paxcounter_garbage_never_raises():
    e = Env()
    import os
    for _ in range(50):
        e.svc.on_event(ev("paxcounter", AppData(34, os.urandom(12))), "new")


def test_rule_failure_does_not_stop_saving():
    e = Env()

    def boom(*a):
        raise RuntimeError("x")
    e.svc.on_detection = boom
    e.svc.on_event(det(), "new")
    assert e.conn.execute("SELECT COUNT(*) FROM sensor_events").fetchone()[0] == 1


def test_list_events_order_and_limit():
    e = Env()
    for i, t in enumerate([NOW - 300, NOW, NOW - 100]):
        e.svc.on_event(det(f"p{i} detected", t=t), "new")
    assert [x["text"] for x in list_events(e.conn, 10, 0)] == [
        "p1 detected", "p2 detected", "p0 detected"]
    assert len(list_events(e.conn, 10, 0, limit=2)) == 2
    assert [x["text"] for x in list_events(e.conn, 10, NOW - 150)] == [
        "p1 detected", "p2 detected"]
    assert list_events(e.conn, 11, 0) == []


def test_detection_value_words_and_negations():
    assert detection_value("Not detected") == 0.0
    assert detection_value("Non rilevato") == 0.0
    assert detection_value("nuclear") is None
    assert detection_value("Porta clear") == 0.0
    assert detection_value("not cleared") == 1.0


def test_empty_detection_text_fires_nothing():
    e = Env()
    e.svc.on_event(det("\x07\x01"), "new")
    assert e.detected == [] and e.published == []
    assert e.conn.execute("SELECT COUNT(*) FROM sensor_events").fetchone()[0] == 0


def test_ignored_node_detection_saved_but_hidden():
    e = Env()
    e.svc.is_ignored = lambda n: True
    e.svc.on_event(det(), "new")
    assert e.published == []
    assert e.conn.execute("SELECT COUNT(*) FROM sensor_events").fetchone()[0] == 1
    e.conn.execute("INSERT INTO nodes(num, id, is_ignored) VALUES(10, '!0000000a', 1)")
    assert list_events(e.conn, 10, 0) == []
    e.conn.execute("UPDATE nodes SET is_ignored = 0 WHERE num = 10")
    assert len(list_events(e.conn, 10, 0)) == 1
