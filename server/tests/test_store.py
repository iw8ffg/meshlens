import pytest

from meshlens.db import connect
from meshlens.events import TelemetryData
from meshlens.settings import DEFAULTS
from meshlens import store as store_mod
from meshlens.store import (BUILTIN_RETENTION_RULES, NOT_IGNORED_SENDER_SQL, RetentionRule, Store,
                            ignored_nums,
                            register_retention_rule,
                            retention_rules, route_signature, time_rule)

DAY = 86400
NOW = 1_800_000_000.0


@pytest.fixture
def store():
    return Store(connect(":memory:"))


def node(num=0xA1B2C3D4, **kw):
    d = {"id": f"!{num:08x}", "num": num, "long_name": "Nodo", "short_name": "ND",
         "hw_model": "HELTEC_V3", "role": "CLIENT", "firmware": None, "lat": 45.46, "lon": 9.19,
         "precision_bits": 13, "position_source": "mqtt", "position_time": 1763660000,
         "country": "IT", "last_heard": 1763660123, "sources": ["mqtt", "rf"], "battery": 87,
         "voltage": 4.01, "channel_util": 12.5, "air_util_tx": 1.2, "mqtt_gateways": 3,
         "last_snr": -7.5, "hops": 2}
    d.update(kw)
    return d


def msg(key, time, country="IT", frm="!a1b2c3d4"):
    return {"key": key, "from": frm, "to": "!ffffffff", "channel": "LongFast",
            "text": "ciao", "time": time, "country": country, "source": "mqtt"}


def test_upsert_and_reload_node(store):
    store.upsert_node(node())
    store.upsert_node(node(long_name="Nuovo"), is_mine=True)
    store.upsert_node(node(long_name="Ancora"))  # is_mine preservato
    nodes = store.load_nodes()
    assert len(nodes) == 1
    n = nodes[0]
    assert n["sources"] == ["mqtt", "rf"]
    assert n["long_name"] == "Ancora"
    assert n["id"] == "!a1b2c3d4"
    assert n["is_mine"] is True


def test_duplicate_message_ignored(store):
    store.add_message(msg("1:1", NOW))
    store.add_message(msg("1:1", NOW))
    assert len(store.messages(None, None, 50)) == 1


def test_messages_filter_and_shape(store):
    store.upsert_node(node())
    store.add_message(msg("1:1", NOW, "IT"))
    store.add_message(msg("1:2", NOW + 1, "SE", frm="!00000009"))
    store.add_message(msg("1:3", NOW + 2, "IT"))
    it = store.messages(["IT"], None, 50)
    assert [m["key"] for m in it] == ["1:3", "1:1"]
    assert it[0] == {"key": "1:3", "from": "!a1b2c3d4", "from_name": "Nodo", "to": "!ffffffff",
                     "channel": "LongFast", "text": "ciao", "time": NOW + 2, "country": "IT",
                     "source": "mqtt", "direction": "in", "radio_id": None,
                     "channel_index": None, "packet_id": None, "status": None,
                     "broker": None, "reply_id": None, "emoji": False, "pki": False,
                     "error": None, "heard_by": None}
    assert store.messages(["SE"], None, 50)[0]["from_name"] is None
    assert [m["key"] for m in store.messages(None, NOW + 1, 50)] == ["1:2", "1:1"]  # before incluso
    assert len(store.messages(None, None, 1)) == 1


def test_messages_before_is_inclusive_and_stable_within_a_second(store):
    for i in range(4):
        store.add_message(msg(f"1:{i}", NOW, "IT"))
    page1 = store.messages(None, None, 2)
    page2 = store.messages(None, page1[-1]["time"], 4)
    assert [m["key"] for m in page1] == ["1:3", "1:2"]
    assert {m["key"] for m in page2} >= {"1:1", "1:0"}  # stesso secondo: non saltati


def test_positions_and_telemetry_since(store):
    store.add_position(1, NOW - 10, 45.0, 9.0, 13, "mqtt")
    store.add_position(1, NOW - 1000, 44.0, 8.0, None, "mqtt")
    assert len(store.positions(1, NOW - 100)) == 1
    store.add_telemetry(1, NOW, TelemetryData(battery_level=80, voltage=4.0, uptime_seconds=5))
    t = store.telemetry(1, NOW - 1)
    assert t[0]["battery"] == 80 and t[0]["uptime"] == 5


def test_channel_util_stats(store):
    store.add_telemetry(1, NOW - 10, TelemetryData(channel_utilization=10.0))
    store.add_telemetry(1, NOW - 20, TelemetryData(channel_utilization=20.0))
    store.add_telemetry(1, NOW - 30, TelemetryData(battery_level=50))  # channel_util NULL
    store.add_telemetry(1, NOW - 5000, TelemetryData(channel_utilization=90.0))  # fuori finestra
    assert store.channel_util_stats([1], NOW - 1800) == {1: (15.0, 2)}
    assert store.channel_util_stats([], NOW - 1800) == {}


def test_purge_retention(store):
    store.add_position(1, NOW - 91 * DAY, 45.0, 9.0, 13, "mqtt")
    store.add_position(1, NOW - 89 * DAY, 45.0, 9.0, 13, "mqtt")
    store.add_message(msg("1:1", NOW - 91 * DAY))
    store.add_telemetry(1, NOW - 100 * DAY, TelemetryData())
    res = store.purge(NOW, DEFAULTS)
    assert res == {"messages": 1, "positions": 1, "telemetry": 0, "nodes": 0,
                   "metrics": 0, "packets": 0}
    assert len(store.positions(1, 0)) == 1


def test_purge_storage_cap(store):
    for i in range(3000):
        store.add_position(1, NOW - i, 45.0, 9.0, 13, "mqtt")
        store.add_message(msg(f"1:{i}", NOW - i))
    store.commit()
    assert store._used_bytes() > 0.5 * 1024 * 1024
    res = store.purge(NOW, {**DEFAULTS, "storage_cap_mb": 0.5})
    assert store._used_bytes() <= 0.5 * 1024 * 1024
    assert res["positions"] > 0 and res["messages"] > 0


def test_purge_deletes_stale_nodes_but_not_mine(store):
    old = NOW - 91 * DAY
    store.upsert_node(node(1, last_heard=old))
    store.upsert_node(node(2, last_heard=old), is_mine=True)
    store.upsert_node(node(3, last_heard=NOW - 89 * DAY))
    res = store.purge(NOW, DEFAULTS)
    assert res["nodes"] == 1
    assert sorted(n["num"] for n in store.load_nodes()) == [2, 3]


def test_purge_deletes_null_last_heard_non_mine(store):
    store.upsert_node(node(1, last_heard=None))
    store.upsert_node(node(2, last_heard=None), is_mine=True)
    res = store.purge(NOW, DEFAULTS)
    assert res["nodes"] == 1
    assert [n["num"] for n in store.load_nodes()] == [2]


def test_radios_crud(store):
    store.save_radio({"id": "r1", "name": "Heltec", "kind": "usb", "address": "COM5",
                      "auto_connect": True, "created": 1.0})
    store.save_radio({"id": "r2", "name": "Ble", "kind": "ble", "address": "AA:BB",
                      "auto_connect": False, "created": 2.0})
    store.save_radio({"id": "r1", "name": "Nuovo", "kind": "usb", "address": "COM6",
                      "auto_connect": False})
    radios = store.list_radios()
    assert [r["id"] for r in radios] == ["r1", "r2"]
    assert radios[0]["name"] == "Nuovo" and radios[0]["auto_connect"] is False
    assert radios[0]["created"] == 1.0
    store.delete_radio("r1")
    assert [r["id"] for r in store.list_radios()] == ["r2"]


def test_message_new_fields_and_status(store):
    store.add_message({**msg("out:r1:9", NOW), "direction": "out", "radio_id": "r1",
                       "channel_index": 1, "packet_id": 9, "status": "sending"})
    store.update_message_status("out:r1:9", "acked")
    m = store.messages(None, None, 10)[0]
    assert (m["direction"], m["radio_id"], m["channel_index"], m["packet_id"], m["status"]) == \
        ("out", "r1", 1, 9, "acked")


def test_heard_by_roundtrip(store):
    store.upsert_node(node(heard_by={"r1": {"snr": -7.5, "rssi": -110, "hops": 0, "time": 5}}))
    assert store.load_nodes()[0]["heard_by"]["r1"]["rssi"] == -110


def test_upsert_link_keeps_latest(store):
    store.upsert_link(10, 20, "rf_direct", -5.0, 100)
    store.upsert_link(10, 20, "rf_direct", -9.0, 200)
    rows = store.conn.execute("SELECT * FROM links").fetchall()
    assert len(rows) == 1 and rows[0]["time"] == 200 and rows[0]["snr"] == -9.0


def test_links_since_filters_and_formats(store):
    store.upsert_link(10, 20, "neighborinfo", None, 50)
    store.upsert_link(10, 20, "traceroute", 4.5, 150)
    assert store.links(100) == [{"from_id": "!0000000a", "to_id": "!00000014",
                                 "source": "traceroute", "snr": 4.5, "time": 150}]


def test_purge_drops_old_links(store):
    store.upsert_link(1, 2, "rf_direct", 1.0, NOW - 100 * DAY)
    store.upsert_link(1, 3, "rf_direct", 1.0, NOW - DAY)
    store.purge(NOW, dict(DEFAULTS))
    assert [lk["to_id"] for lk in store.links(0)] == ["!00000003"]


def test_set_mine_roundtrip(store):
    store.upsert_node(node(10))
    store.set_mine(10, True)
    assert store.load_nodes()[0]["is_mine"] is True
    store.set_mine(10, False)
    assert store.load_nodes()[0]["is_mine"] is False


def test_traceroute_roundtrip(store):
    tid = store.add_traceroute("r1", 10, 100.0)
    assert store.traceroutes(10)[0]["status"] == "pending"
    fwd = [{"id": "!0000000a", "snr": None}]
    store.update_traceroute(tid, "ok", None, fwd, [])
    t = store.traceroutes(10)[0]
    assert t == {"id": tid, "radio_id": "r1", "target_id": "!0000000a", "time": 100.0,
                 "status": "ok", "error": None, "forward": fwd, "back": [],
                 "auto": False, "route": "!0000000a"}
    assert store.traceroutes(11) == []


def _pt(store, sid, seq, snr, seg=0):
    return store.add_point(sid, seg, seq, NOW, snr, -100, 0, 45.0, 9.0, 32)


def test_add_point_dedup_keeps_best_snr(store):
    sid = store.create_session(name="p", radio_id="r", mobile_num=1, mode="rangetest",
                               started=NOW)
    assert _pt(store, sid, 5, -5.0) is True
    assert _pt(store, sid, 5, -2.0) is False
    pts = store.points(sid)
    assert len(pts) == 1 and pts[0]["snr"] == -2.0
    assert _pt(store, sid, 5, -9.0) is False and store.points(sid)[0]["snr"] == -2.0
    assert _pt(store, sid, 5, -1.0, seg=1) is True  # altro tratto
    assert store.add_point(sid, 0, None, NOW, 1.0, -90, 0, None, None, None) is True
    assert store.add_point(sid, 0, None, NOW, 1.0, -90, 0, None, None, None) is True


def test_session_crud_and_active(store):
    sid = store.create_session(name="p", radio_id="r", mobile_num=1, mode="rangetest",
                               channel_index=1, interval_s=30, started=NOW)
    assert store.active_session()["id"] == sid
    assert store.get_session(sid)["name"] == "p" and store.get_session(99) is None
    store.add_track(sid, NOW, 45.0, 9.0, 32)
    _pt(store, sid, 1, 0.0)
    store.update_point_position(store.points(sid)[0]["id"], 46.0, 10.0, 13)
    p = store.points(sid)[0]
    assert (p["lat"], p["lon"], p["precision_bits"]) == (46.0, 10.0, 13)
    assert len(store.track(sid)) == 1
    store.update_session(sid, ended=NOW + 5, end_reason="manual")
    assert store.active_session() is None
    assert [s["id"] for s in store.sessions()] == [sid]
    store.delete_session(sid)
    assert store.get_session(sid) is None and store.points(sid) == [] and store.track(sid) == []


def test_purge_keeps_coverage(store):
    sid = store.create_session(name="p", radio_id="r", mobile_num=1, mode="rangetest",
                               started=NOW - 365 * DAY)
    _pt(store, sid, 1, 0.0)
    store.add_track(sid, NOW - 365 * DAY, 45.0, 9.0, 32)
    store.purge(NOW, {**DEFAULTS, "storage_cap_mb": 0.0001})
    assert len(store.sessions()) == 1 and len(store.points(sid)) == 1
    assert len(store.track(sid)) == 1


def test_store_config_tables_roundtrip(store):
    num = 0xA1B2C3D4
    assert store.last_read(num) is None
    store.add_read(num, "r1", 100.0, ["config.lora"], {"a": 1})
    rid = store.add_read(num, "r1", 200.0, ["config.lora", "owner"], {"a": 2})
    last = store.last_read(num)
    assert last["id"] == rid and last["data"] == {"a": 2}
    assert last["sections"] == ["config.lora", "owner"] and last["radio_id"] == "r1"

    bid = store.add_backup(num, 150.0, "before_apply", "prima", ["config.lora"],
                           {"config": {"security": {"private_key": "SEGRETO"}}})
    store.add_backup(99, 160.0, "manual", None, [], {})
    lst = store.backups(num)
    assert [b["id"] for b in lst] == [bid] and "data" not in lst[0]
    got = store.get_backup(bid)
    assert got["data"]["config"]["security"]["private_key"] == "SEGRETO"
    assert got["reason"] == "before_apply" and store.get_backup(999) is None

    jid = store.add_job(node_num=num, radio_id="r1", kind="apply", status="running",
                        step="avvio", done=0, total=3, started=1.0)
    store.update_job(jid, status="done", done=3, verify="verified", ended=2.0)
    job = store.get_job(jid)
    assert job["status"] == "done" and job["verify"] == "verified" and job["total"] == 3
    with pytest.raises(ValueError):
        store.update_job(jid, bogus=1)
    assert store.get_job(999) is None


def test_purge_never_touches_config_tables(store):
    # letture, copie e lavori di configurazione non scadono mai, nemmeno se vecchissimi
    store.add_read(1, "r1", 1.0, ["lora"], {"a": 1})
    store.add_backup(1, 1.0, "before_apply", None, ["config.lora"], {"a": 1})
    jid = store.add_job(node_num=1, radio_id="r1", kind="read", status="done", started=1.0)
    store.commit()
    store.purge(NOW, {**DEFAULTS, "storage_cap_mb": 0})
    assert store.last_read(1) is not None and len(store.backups(1)) == 1
    assert store.get_job(jid) is not None


def test_fail_running_jobs_sets_error_code(store):
    st = store
    jid = st.add_job(node_num=1, radio_id="r", kind="read", status="running", started=1.0)
    st.fail_running_jobs("Interrotto", 2.0)
    job = st.get_job(jid)
    assert job["status"] == "failed" and job["error_code"] == "error"


def test_favorite_roundtrip_and_preserved_by_upsert(store):
    store.upsert_node(node(), is_favorite=True)
    store.upsert_node(node(long_name="Altro"))  # is_favorite preservato
    n = store.load_nodes()[0]
    assert n["is_favorite"] is True and n["is_mine"] is False
    store.set_favorite(0xA1B2C3D4, False)
    assert store.load_nodes()[0]["is_favorite"] is False


def test_hops_min_persisted(store):
    store.upsert_node(node(hops=None, hops_min=1))
    assert store.load_nodes()[0]["hops_min"] == 1


def test_purge_keeps_favorites(store):
    old = NOW - 91 * DAY
    store.upsert_node(node(1, last_heard=old))
    store.upsert_node(node(2, last_heard=old), is_favorite=True)
    store.upsert_node(node(3, last_heard=None), is_favorite=True)
    assert store.purge(NOW, DEFAULTS)["nodes"] == 1
    assert sorted(n["num"] for n in store.load_nodes()) == [2, 3]


def test_migration_clears_stale_mqtt_only_hops(tmp_path):
    from meshlens.db import connect
    path = tmp_path / "m.db"
    conn = connect(path)
    st = Store(conn)
    st.upsert_node(node(1, sources=["mqtt"], hops=7))
    st.upsert_node(node(2, sources=["rf"], hops=2))
    st.upsert_node(node(3, sources=["mqtt", "rf"], hops=1))
    conn.execute("DELETE FROM settings WHERE key='migr_hops_mqtt_v120'")  # come un DB 1.1.0
    conn.execute("PRAGMA user_version=0")
    conn.commit()
    conn.close()
    conn = connect(path)
    got = {n["num"]: n["hops"] for n in Store(conn).load_nodes()}
    assert got == {1: None, 2: 2, 3: 1}
    conn.execute("UPDATE nodes SET hops=5 WHERE num=1")
    conn.commit()
    conn.close()
    got = {n["num"]: n["hops"] for n in Store(connect(path)).load_nodes()}
    assert got[1] == 5  # eseguita una volta sola


def test_purge_step_deletes_at_most_limit(store):
    store.conn.executemany(
        "INSERT INTO messages(key, from_num, text, time, source) VALUES(?, 1, 'x', ?, 'mqtt')",
        [(f"1:{i}", NOW - 100 * DAY - i) for i in range(5000)])
    store.commit()
    step = store.purge_step(NOW, DEFAULTS, limit=2000)
    assert step.deleted["messages"] == 2000 and step.done is False
    store.purge_step(NOW, DEFAULTS, limit=2000)
    step = store.purge_step(NOW, DEFAULTS, limit=2000)
    assert step.deleted["messages"] == 1000 and step.done is True
    assert store.conn.execute("SELECT COUNT(*) FROM messages WHERE time < ?",
                              (NOW - 90 * DAY,)).fetchone()[0] == 0


def test_message_reply_emoji_pki_roundtrip(store):
    store.add_message({**msg("k1", NOW), "reply_id": 77, "emoji": True, "pki": True})
    m = store.messages(None, None, 10)[0]
    assert m["reply_id"] == 77 and m["emoji"] is True and m["pki"] is True and m["error"] is None
    store.update_message_status("k1", "failed", "NO_ROUTE")
    m = store.messages(None, None, 10)[0]
    assert m["status"] == "failed" and m["error"] == "NO_ROUTE"


def test_recent_radio_messages_only_radio(store):
    store.add_message(msg("a", NOW))
    store.add_message({**msg("b", NOW + 1), "radio_id": "r1"})
    assert [m["key"] for m in store.recent_radio_messages()] == ["b"]


def test_waypoints_active_and_purge(store):
    def wp(i, expire, t):
        return {"id": i, "from_num": 0xA1B2C3D4, "lat": 45.0, "lon": 9.0, "name": f"w{i}",
                "description": "", "icon": 128205, "expire": expire, "locked_to": None,
                "time": t, "source": "rf", "radio_id": "r1", "channel": "0", "country": "IT"}
    store.upsert_waypoint(wp(1, None, NOW - 3))
    store.upsert_waypoint(wp(2, int(NOW) - 10, NOW - 2))
    store.upsert_waypoint(wp(3, 0, NOW - 1))
    store.delete_waypoint(3)
    assert [w["id"] for w in store.active_waypoints(NOW)] == [1]
    assert store.get_waypoint(3)["deleted"] == 1 and store.get_waypoint(99) is None
    store.upsert_waypoint(wp(1, None, NOW))  # aggiornamento, non duplicato
    assert store.active_waypoints(NOW)[0]["time"] == NOW
    store.purge_step(NOW, DEFAULTS)
    assert store.get_waypoint(2) is None and store.get_waypoint(1) is not None


def test_mark_read_keeps_max(store):
    assert store.mark_read("ch:r1:0", 100) == 100
    assert store.mark_read("ch:r1:0", 50) == 100
    assert store.read_times() == {"ch:r1:0": 100}


def test_read_baseline_and_purge_reads(store):
    assert store.read_baseline() > 1_700_000_000
    store.conn.execute("DELETE FROM settings WHERE key='conv_read_baseline'")
    assert store.read_baseline() == 0
    store.mark_read("old", NOW - 400 * DAY)
    store.mark_read("new", NOW)
    store.purge_step(NOW, DEFAULTS)
    assert set(store.read_times()) == {"new"}


def _pkt(time, **kw):
    return {"time": time, "from_num": 1, "status": "ok", "kind": "text", **kw}


def test_add_metrics_and_empty_noop(store):
    store.add_metrics(1, 10.0, "environment", {"temperature": 21.5, "relative_humidity": 40.0})
    assert store.conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 2
    store.add_metrics(1, 11.0, "environment", {})
    assert store.conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 2


def test_upsert_hourly_sums_and_max(store):
    store.upsert_node_hourly([(3600, 1, "mqtt", 2, -10.0, 2, -4.0)])
    store.upsert_node_hourly([(3600, 1, "mqtt", 1, -2.0, 1, None)])
    row = store.conn.execute("SELECT packets, snr_sum, snr_n, snr_max FROM node_hourly").fetchone()
    assert tuple(row) == (3, -12.0, 3, -4.0)
    store.upsert_stats_hourly([(3600, "rf", "text", 2, 5)])
    store.upsert_stats_hourly([(3600, "rf", "text", 1, 2)])
    row = store.conn.execute("SELECT packets, receptions FROM stats_hourly").fetchone()
    assert tuple(row) == (3, 7)


def test_trim_packets_respects_cap(store):
    store.insert_packets([_pkt(float(i)) for i in range(25)])
    cutoff = store.packets_cutoff(10)
    assert cutoff == 15
    assert store.trim_packets(cutoff, 4) == 4
    ids = [r[0] for r in store.conn.execute("SELECT id FROM packets ORDER BY id")]
    assert ids == list(range(5, 26))
    while store.trim_packets(cutoff, 4):
        pass
    ids = [r[0] for r in store.conn.execute("SELECT id FROM packets ORDER BY id")]
    assert ids == list(range(16, 26))


def test_packets_cutoff_none_when_within_cap(store):
    assert store.packets_cutoff(10) is None
    store.insert_packets([_pkt(float(i)) for i in range(10)])
    assert store.packets_cutoff(10) is None


def test_purge_covers_new_tables(store):
    old_h = NOW - 49 * 3600
    store.insert_packets([_pkt(old_h), _pkt(NOW - 3600)])
    store.add_metrics(1, NOW - 366 * DAY, "environment", {"temperature": 1.0})
    store.add_metrics(1, NOW - DAY, "environment", {"temperature": 2.0})
    store.upsert_stats_hourly([(int(NOW - 366 * DAY), "rf", "text", 1, 1),
                               (int(NOW - DAY), "rf", "text", 1, 1)])
    store.upsert_node_hourly([(int(NOW - 91 * DAY), 1, "rf", 1, 0.0, 0, None),
                              (int(NOW - DAY), 1, "rf", 1, 0.0, 0, None)])
    res = store.purge(NOW, DEFAULTS)
    assert res["metrics"] == 1 and res["packets"] == 1
    assert "stats_hourly" not in res and "node_hourly" not in res
    for table in ("metrics", "packets", "stats_hourly", "node_hourly"):
        assert store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1, table


# ---- 1.6: registro delle regole di conservazione, nodi ignorati, traceroute ----

RULE_NAMES = ["messages", "positions", "telemetry", "links", "metrics", "stats_hourly",
              "node_hourly", "packets", "nodes", "waypoints", "conversation_reads",
              "messages_broker", "traceroutes", "sensor_events", "tak_contacts"]


@pytest.fixture
def clean_rules():
    yield
    store_mod._EXTRA_RULES.clear()


def test_builtin_rules_order_and_names():
    assert [r.name for r in BUILTIN_RETENTION_RULES] == RULE_NAMES


def test_purge_deleted_keys_unchanged(store):
    assert set(store.purge(NOW, DEFAULTS)) == {
        "messages", "positions", "telemetry", "metrics", "packets", "nodes"}
    assert set(store.purge_step(NOW, DEFAULTS).deleted) == {
        "messages", "positions", "telemetry", "metrics", "packets", "nodes"}


def test_purge_keeps_ignored_nodes(store):
    old = NOW - 100 * DAY
    store.upsert_node(node(num=1, last_heard=old), is_ignored=True)
    store.upsert_node(node(num=2, last_heard=old))
    assert store.purge(NOW, DEFAULTS)["nodes"] == 1
    assert [n["num"] for n in store.load_nodes()] == [1]


def _trace_count(store):
    return store.conn.execute("SELECT COUNT(*) FROM traceroutes").fetchone()[0]


def test_purge_traceroutes_by_setting(store):
    store.add_traceroute("r1", 5, NOW - 400 * DAY)
    store.add_traceroute("r1", 5, NOW - 10 * DAY)
    store.purge(NOW, DEFAULTS)
    assert _trace_count(store) == 1
    store.purge(NOW, {**DEFAULTS, "retention_traceroutes_days": 5})
    assert _trace_count(store) == 0


def test_purge_sensor_events_and_tak(store):
    c = store.conn
    for t in (NOW - 366 * DAY, NOW - DAY):
        c.execute("INSERT INTO sensor_events(node_num, time, kind, source) "
                  "VALUES(1, ?, 'detection', 'rf')", (t,))
    c.execute("INSERT INTO tak_contacts(node_num, time, source) VALUES(1, ?, 'rf')",
              (NOW - 91 * DAY,))
    c.execute("INSERT INTO tak_contacts(node_num, time, source) VALUES(2, ?, 'rf')", (NOW - DAY,))
    store.purge(NOW, DEFAULTS)
    assert [r[0] for r in c.execute("SELECT time FROM sensor_events")] == [NOW - DAY]
    assert [r[0] for r in c.execute("SELECT node_num FROM tak_contacts")] == [2]


def _bmsg(key, t, source="mqtt", broker="b1"):
    return {**msg(key, t), "source": source, "broker": broker}


def _keys(store):
    return {r[0] for r in store.conn.execute("SELECT key FROM messages")}


def test_purge_broker_retention_shorter_only(store):
    for m in (_bmsg("old_b1", NOW - 10 * DAY), _bmsg("new_b1", NOW - 60),
              _bmsg("old_rf", NOW - 10 * DAY, source="rf", broker=None),
              _bmsg("old_def", NOW - 10 * DAY, broker="default")):
        store.add_message(m)
    res = store.purge(NOW, {**DEFAULTS, "retention_broker_days": {"b1": 120}})
    assert res["messages"] == 0 and len(_keys(store)) == 4
    res = store.purge(NOW, {**DEFAULTS, "retention_broker_days": {"b1": 7}})
    assert res["messages"] == 1
    assert _keys(store) == {"new_b1", "old_rf", "old_def"}


def test_purge_without_new_settings_keys(store):
    """Impostazioni di prima della 1.6 (senza le chiavi nuove): nessun errore."""
    old = {k: v for k, v in DEFAULTS.items()
           if k not in ("retention_traceroutes_days", "retention_broker_days")}
    store.add_traceroute("r1", 5, NOW - 400 * DAY)
    store.purge(NOW, old)
    assert _trace_count(store) == 0


def test_register_retention_rule(store, clean_rules):
    store.conn.execute("CREATE TABLE extra(time REAL)")
    store.conn.execute("INSERT INTO extra(time) VALUES(?)", (NOW - 400 * DAY,))
    rule = time_rule("extra", "extra", "retention_telemetry_days")
    register_retention_rule(rule)
    register_retention_rule(rule)  # stessa regola: nessun effetto
    assert [r.name for r in retention_rules()].count("extra") == 1
    store.purge(NOW, DEFAULTS)
    assert store.conn.execute("SELECT COUNT(*) FROM extra").fetchone()[0] == 0
    with pytest.raises(ValueError):
        register_retention_rule(time_rule("extra", "extra", "retention_positions_days"))
    with pytest.raises(ValueError):
        register_retention_rule(RetentionRule("messages", "messages", lambda s, now: []))


def test_purge_sql_uses_parameters(store):
    store.add_message(_bmsg("x", NOW - 2 * DAY, broker="x-1"))
    store.purge(NOW, {**DEFAULTS, "retention_broker_days": {"x-1": 1}})
    assert _keys(store) == set()


def test_set_ignored_roundtrip(store):
    store.upsert_node(node(num=7), is_ignored=True)
    assert store.get_node(7)["is_ignored"] is True
    store.upsert_node(node(num=7, long_name="Altro"))  # flag preservato
    assert store.get_node(7)["is_ignored"] is True
    store.set_ignored(7, False)
    assert store.get_node(7)["is_ignored"] is False
    store.upsert_node(node(num=8))
    assert all("is_ignored" in n for n in store.load_nodes())
    assert store.get_node(8)["is_ignored"] is False


def test_traceroute_auto_and_route(store):
    tid = store.add_traceroute("r1", 5, NOW, auto=True)
    fwd = [{"id": "!0000000a", "snr": 1.0}, {"id": "!0000000b", "snr": 2.0}]
    store.update_traceroute(tid, "ok", None, fwd, [])
    t = store.traceroutes(5)[0]
    assert t["auto"] is True and t["route"] == "!0000000a>!0000000b"
    assert route_signature([]) == ""
    tid2 = store.add_traceroute("r1", 5, NOW + 10)
    store.update_traceroute(tid2, "failed", "x", [], [])
    latest = store.traceroutes(5)[0]
    assert latest["id"] == tid2 and latest["route"] is None and latest["auto"] is False
    assert [x["id"] for x in store.traceroutes(5, before=NOW + 5)] == [tid]



def test_messages_of_ignored_senders_kept_but_hidden(store):
    store.upsert_node(node(num=0xA1B2C3D4), is_ignored=True)
    store.add_message({**msg("1:1", NOW), "radio_id": "r1"})
    store.add_message({**msg("1:2", NOW, frm="!00000009"), "radio_id": "r1"})
    assert store.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
    assert [m["key"] for m in store.messages(None, None, 10)] == ["1:2"]
    assert [m["key"] for m in store.radio_messages(None, 10)] == ["1:2"]
    assert ignored_nums(store.conn) == {0xA1B2C3D4}
    store.set_ignored(0xA1B2C3D4, False)  # reversibile: tutto torna
    assert len(store.messages(None, None, 10)) == 2
    assert ignored_nums(store.conn) == set()



def test_not_ignored_sender_sql_with_alias(store):
    from meshlens.store import not_ignored_sender_sql
    assert not_ignored_sender_sql() == NOT_IGNORED_SENDER_SQL
    assert not_ignored_sender_sql("m").startswith("m.from_num NOT IN")
    with pytest.raises(ValueError):
        not_ignored_sender_sql("m; DROP")
    store.upsert_node(node(num=0xA1B2C3D4), is_ignored=True)
    store.add_message(msg("1:1", NOW))
    store.add_message(msg("1:2", NOW, frm="!00000009"))
    store.insert_packets([{"time": NOW, "from_num": 9, "status": "ok"}])
    rows = store.conn.execute(
        "SELECT m.key FROM messages m JOIN packets p ON p.from_num = m.from_num WHERE "
        + not_ignored_sender_sql("m")).fetchall()
    assert [r[0] for r in rows] == ["1:2"]
