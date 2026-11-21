import sqlite3

from meshlens.db import connect
from meshlens.events import TextData
from meshlens.store import Store
from test_ingest import BERLIN, HOUR, NOW, count, env, ev, locator, pos  # noqa: F401


def rf(kind, payload, radio, **kw):
    return ev(kind, payload, source="rf", radio_id=radio, gateway_id=None, channel="0", **kw)


def test_same_text_from_two_radios_and_mqtt_is_one_message(env):
    ing, live, store, conn, got = env
    ing.handle(rf("text", TextData("ciao"), "rA", pid=7, snr=-5.0, rssi=-100, hops=0))
    ing.handle(rf("text", TextData("ciao"), "rB", pid=7, snr=-9.0, rssi=-120, hops=1, t=NOW + 1))
    ing.handle(ev("text", TextData("ciao"), pid=7))
    assert len(got) == 1 and count(conn, "messages") == 1
    m = got[0]
    assert m["direction"] == "in" and m["radio_id"] == "rA" and m["channel_index"] == 0
    assert m["packet_id"] == 7 and m["status"] is None
    hb = live.nodes[1]["heard_by"]
    assert hb["rA"] == {"snr": -5.0, "rssi": -100, "hops": 0, "time": int(NOW)}
    assert hb["rB"] == {"snr": -9.0, "rssi": -120, "hops": 1, "time": int(NOW + 1)}
    assert "rf" in live.nodes[1]["sources"]
    assert store.load_nodes()[0]["heard_by"]["rB"]["snr"] == -9.0


def test_rf_node_in_unsaved_country_is_persisted(env):
    ing, live, store, conn, _ = env
    ing.handle(rf("position", pos(BERLIN), "rA"))
    assert live.nodes[1]["country"] == "DE"
    assert [n["num"] for n in store.load_nodes()] == [1]


def test_record_outgoing_and_status(env):
    ing, live, store, conn, got = env
    statuses = []
    ing.on_status = lambda k, s, e=None: statuses.append((k, s))
    m = ing.record_outgoing("rA", "!00000001", 55, "ciao", 2, "!ffffffff")
    assert m["key"] == "out:rA:55" and m["direction"] == "out" and m["status"] == "sent"
    assert got == [m]
    ing.set_status("out:rA:55", "acked")
    assert statuses == [("out:rA:55", "acked")]
    saved = store.messages(None, None, 10)[0]
    assert saved["status"] == "acked" and saved["direction"] == "out"
    assert saved["radio_id"] == "rA" and saved["channel_index"] == 2 and saved["packet_id"] == 55
    assert m["status"] == "acked"


def test_set_status_without_callback(env):
    ing, *_ = env
    ing.record_outgoing("rA", "!00000001", 1, "x", 0, "!ffffffff")
    ing.set_status("out:rA:1", "failed")


def test_mark_local_radio(env):
    ing, live, store, conn, _ = env
    ing.mark_local_radio(0xA1)
    n = live.nodes[0xA1]
    assert n["is_local_radio"] and n["is_mine"]
    assert store.load_nodes()[0]["is_mine"] is True


def test_migration_from_phase1_db(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
    CREATE TABLE nodes(num INTEGER PRIMARY KEY, id TEXT, long_name TEXT, short_name TEXT,
      hw_model TEXT, role TEXT, firmware TEXT, lat REAL, lon REAL, precision_bits INTEGER,
      position_source TEXT, position_time INTEGER, country TEXT, last_heard REAL, sources TEXT,
      battery INTEGER, voltage REAL, channel_util REAL, air_util_tx REAL, mqtt_gateways INTEGER,
      last_snr REAL, hops INTEGER, is_mine INTEGER DEFAULT 0);
    CREATE TABLE messages(key TEXT PRIMARY KEY, from_num INTEGER, to_num INTEGER, channel TEXT,
      text TEXT, time REAL, country TEXT, source TEXT);
    INSERT INTO nodes(num, id, sources, last_heard) VALUES(1, '!00000001', '["mqtt"]', 5);
    INSERT INTO messages VALUES('1:1', 1, 4294967295, 'LongFast', 'ciao', 5, 'IT', 'mqtt');
    """)
    old.commit()
    old.close()
    conn = connect(path)
    store = Store(conn)
    assert count(conn, "nodes") == 1
    assert store.load_nodes()[0]["heard_by"] == {}
    m = store.messages(None, None, 10)[0]
    assert m["direction"] == "in" and m["radio_id"] is None and m["status"] is None
    connect(path).close()  # seconda apertura: migrazione idempotente


def test_nodedb_replay_does_not_regress_fresh_state(env):
    ing, live, store, conn, _ = env
    from meshlens.events import NodeInfoData, TelemetryData
    ing.handle(ev("position", pos((45.46, 9.19)), t=NOW))
    ing.handle(ev("telemetry", TelemetryData(battery_level=90, voltage=4.1), t=NOW, pid=2))
    ing.handle(rf("position", pos((45.0, 9.0), bits=None), "rA", pid=9, t=NOW, snr=-3.0, hops=1))
    n = live.nodes[1]
    before = {k: v for k, v in n.items() if k not in ("heard_by", "sources")}
    old = NOW - 5 * HOUR
    for kind, payload in (("position", pos((50.0, 10.0), bits=None)),
                          ("telemetry", TelemetryData(battery_level=10, voltage=3.0)),
                          ("nodeinfo", NodeInfoData("Nome", "NM", "HELTEC", "CLIENT"))):
        ing.handle(rf(kind, payload, "rA", pid=0, t=old, snr=-20.0, rssi=-130, hops=7))
    after = {k: v for k, v in n.items() if k not in ("heard_by", "sources")}
    assert after.pop("long_name") == "Nome" and before.pop("long_name") is None
    after.pop("short_name"), before.pop("short_name")
    after.pop("hw_model"), before.pop("hw_model")
    after.pop("role"), before.pop("role")
    assert after == before
    assert n["heard_by"]["rA"]["time"] == int(NOW) and n["last_heard"] == NOW
    assert count(conn, "positions") == 2 and count(conn, "telemetry") == 1


def test_rf_first_then_mqtt_counts_one_gateway(env):
    ing, live, *_ = env
    ing.handle(rf("text", TextData("x"), "rA", pid=3))
    assert live.nodes[1]["mqtt_gateways"] == 0
    ing.handle(ev("text", TextData("x"), pid=3))
    assert live.nodes[1]["mqtt_gateways"] == 1
    ing.handle(ev("text", TextData("x"), pid=3, gateway_id="!g2"))
    assert live.nodes[1]["mqtt_gateways"] == 2


def test_rf_copy_of_mqtt_text_adopts_radio(env):
    ing, live, store, conn, got = env
    ing.handle(ev("text", TextData("ciao"), pid=11))
    assert got[0]["radio_id"] is None and got[0]["source"] == "mqtt"
    ing.handle(rf("text", TextData("ciao"), "rA", pid=11, t=NOW + 1))
    assert len(live.messages) == 1 and count(conn, "messages") == 1
    m = live.messages[0]
    assert (m["radio_id"], m["channel_index"], m["source"]) == ("rA", 0, "rf")
    assert len(got) == 2 and got[1]["radio_id"] == "rA" and got[1]["key"] == m["key"]
    row = store.messages(None, None, 10)[0]
    assert (row["radio_id"], row["channel_index"], row["source"]) == ("rA", 0, "rf")
    ing.handle(rf("text", TextData("ciao"), "rB", pid=11, t=NOW + 2))  # gia' assegnato
    assert len(got) == 2 and live.messages[0]["radio_id"] == "rA"


def test_nodedb_entry_without_lastheard_does_not_look_fresh(env):
    from meshlens.events import NodeInfoData
    ing, live, store, conn, _ = env
    ing.handle(rf("nodeinfo", NodeInfoData("Nome", "NM", "HELTEC", "CLIENT"), "rA",
                  pid=0, t=0, snr=None))
    ing.handle(rf("position", pos((45.46, 9.19)), "rA", pid=0, t=0, snr=None))
    n = live.nodes[1]
    assert n["last_heard"] is None and n["heard_by"] == {}
    assert n["long_name"] == "Nome" and n["lat"] == 45.46 and n["position_time"] is None
    assert count(conn, "positions") == 0
    ing.handle(rf("position", pos((50.0, 10.0)), "rA", pid=0, t=0, snr=None))
    assert n["lat"] == 45.46  # solo i vuoti


def test_rf_direct_link_only_with_zero_hops(env):
    ing, live, store, conn, _ = env
    ing.set_radio_node("rA", 99)
    ing.handle(rf("text", TextData("a"), "rA", num=1, pid=1, hops=0))
    ing.handle(rf("text", TextData("b"), "rA", num=2, pid=2, hops=2))
    ing.handle(rf("text", TextData("c"), "rA", num=3, pid=3, hops=0, t=0))
    ing.handle(rf("text", TextData("d"), "rZ", num=4, pid=4, hops=0))
    assert [(r["from_id"], r["to_id"], r["source"]) for r in store.links(0)] == [
        ("!00000001", "!00000063", "rf_direct")]


def test_rf_direct_link_skips_mqtt_relayed_and_own_node(env):
    ing, live, store, conn, _ = env
    ing.set_radio_node("rA", 99)
    ing.handle(rf("text", TextData("a"), "rA", num=1, pid=1, hops=0, via_mqtt=True))
    ing.handle(rf("text", TextData("b"), "rA", num=99, pid=2, hops=0))
    assert store.links(0) == []


def test_rangetest_updates_only_last_heard(env):
    from meshlens.events import RangeTestData
    ing, live, store, conn, got = env
    ing.handle(rf("rangetest", RangeTestData(3, "seq 3"), "rA", hops=0))
    n = live.nodes[1]
    assert n["last_heard"] == NOW and "rf" in n["sources"] and n["heard_by"]["rA"]["snr"] == -7.5
    assert n["lat"] is None and n["battery"] is None and not got
    assert count(conn, "positions") == 0 and count(conn, "messages") == 0
    assert count(conn, "telemetry") == 0


def test_rf_reaction_dedup_keeps_fields(env):
    ing, live, store, conn, got = env
    ing.handle(ev("text", TextData("\U0001F44D", reply_id=9, emoji=True), pid=12))
    ing.handle(rf("text", TextData("\U0001F44D", reply_id=9, emoji=True), "rA", pid=12,
                  t=NOW + 1))
    m = live.messages[0]
    assert m["radio_id"] == "rA" and m["reply_id"] == 9 and m["emoji"] is True
    assert got[-1]["reply_id"] == 9 and got[-1]["emoji"] is True
    row = store.messages(None, None, 10)[0]
    assert row["reply_id"] == 9 and row["emoji"] is True and row["radio_id"] == "rA"
