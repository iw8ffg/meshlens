import time

from meshlens.db import connect
from meshlens.queries import (PacketFilter, bucket_rows, metric_series, network_stats,
                              packet_detail, packet_list, ro_connect, snr_series, track,
                              telemetry_series)
from meshlens.store import Store


def test_bucket_rows_average_and_nulls():
    rows = [{"time": float(i), "battery": i, "voltage": None} for i in range(10)]
    out = bucket_rows(rows, ("battery", "voltage"), 5)
    assert len(out) == 5
    assert out[0]["battery"] == 0.5
    assert out[0]["voltage"] is None


def test_bucket_rows_passthrough():
    rows = [{"time": 1.0, "battery": 3}, {"time": 2.0, "battery": 4}]
    assert bucket_rows(rows, ("battery",), 5) is rows
    assert bucket_rows(rows, ("battery",), 2) is rows


def test_track_decimates_keeping_ends():
    conn = connect(":memory:")
    n = 260_000
    conn.executemany(
        "INSERT INTO positions(node_num, time, lat, lon, precision_bits, source) "
        "VALUES(1,?,?,?,?,?)", [(1000.0 + i, 45.0, 9.0, 32, "rf") for i in range(n)])
    out = track(conn, 1, 0.0, max_points=5000)
    assert len(out) <= 5001
    assert out[0]["time"] == 1000.0 and out[-1]["time"] == 1000.0 + n - 1


def test_metric_series_latest_all_time():
    conn = connect(":memory:")
    store = Store(conn)
    now = time.time()
    store.add_metrics(1, now - 200 * 86400, "environment", {"temperature": 11.0})
    store.add_metrics(1, now - 3600, "environment", {"humidity": 50.0})
    res = metric_series(conn, 1, now - 7 * 86400)
    assert res["latest"]["environment.temperature"]["value"] == 11.0
    assert "environment.temperature" not in res["series"]
    assert res["latest"]["environment.humidity"]["value"] == 50.0
    assert [v for _, v in res["series"]["environment.humidity"]] == [50.0]


def test_snr_series_avg():
    conn = connect(":memory:")
    store = Store(conn)
    store.upsert_node_hourly([(3600, 1, "rf", 3, -12.0, 3, -2.0), (3600, 1, "mqtt", 2, 0.0, 0, None)])
    out = snr_series(conn, 1, 0.0)
    assert out[0]["source"] == "mqtt" and out[0]["snr_avg"] is None
    assert out[1] == {"time": 3600, "source": "rf", "snr_avg": -4.0, "snr_max": -2.0,
                      "packets": 3}


def test_telemetry_series_and_ro_connect(tmp_path):
    path = tmp_path / "t.db"
    conn = connect(path)
    conn.execute("INSERT INTO telemetry(node_num, time, battery) VALUES(1, 100.0, 80)")
    conn.commit()
    ro = ro_connect(path)
    try:
        assert telemetry_series(ro, 1, 0.0)[0]["battery"] == 80
    finally:
        ro.close()
    conn.close()


def _stats_db():
    conn = connect(":memory:")
    H0, H1 = 100 * 3600, 101 * 3600
    for num, name in ((1, "Uno"), (2, None), (3, "Tre")):
        conn.execute("INSERT INTO nodes(num, id, long_name, hw_model, role, last_heard, hops) "
                     "VALUES(?,?,?,?,?,?,?)",
                     (num, f"!{num:08x}", name, "TBEAM", "CLIENT", H1 + 10, num))
    store = Store(conn)
    store.upsert_node_hourly([
        (H0, 1, "rf", 5, -10.0, 2, -4.0), (H0, 2, "rf", 3, 0.0, 0, None),
        (H1, 1, "rf", 4, -6.0, 2, -2.0), (H1, 2, "mqtt", 2, -60.0, 2, -30.0),
        (H1, 3, "rf", 1, 12.0, 1, 12.0)])
    store.upsert_stats_hourly([(H0, "rf", "text", 6, 6), (H0, "rf", "position", 2, 3),
                               (H1, "mqtt", "text", 7, 9)])
    return conn, H0, H1


def test_network_stats_shapes():
    conn, H0, H1 = _stats_db()
    res = network_stats(conn, H1 + 100, 24)
    assert res["online"] == [{"time": H0, "nodes": 2}, {"time": H1, "nodes": 3}]
    assert res["top"][0]["id"] == "!00000001" and res["top"][0]["packets"] == 9
    assert res["top"][0]["per_hour"] == 9 / 24 and res["top"][1]["name"] == "!00000002"
    assert sum(res["snr"]["rf"]) == 2 and sum(res["snr"]["mqtt"]) == 1
    assert res["snr"]["mqtt"][0] == 1          # -30 dB goes to the first bin
    assert res["snr"]["bins"][0] == -20 and res["snr"]["bins"][-1] == 15
    assert res["snr"]["rf"][-1] == 0            # 12 dB is below the last bin edge
    assert res["totals"] == {"nodes": 3, "packets": 15}
    assert {(p["time"], p["kind"]) for p in res["packets"]} == {
        (H0, "text"), (H0, "position"), (H1, "text")}
    assert [h["hops"] for h in res["hops"]] == [0, 1, 2, 3, 4, 5, 6, 7, None]
    assert res["hardware"] == [{"value": "TBEAM", "nodes": 3}] and res["other_hardware"] == 0
    assert res["roles"] == [{"value": "CLIENT", "nodes": 3}]


def test_network_stats_window():
    conn, H0, H1 = _stats_db()
    res = network_stats(conn, H1 + 100, 1)
    assert [o["time"] for o in res["online"]] == [H1]
    assert res["totals"] == {"nodes": 3, "packets": 7}


def _packet_db(n=250):
    conn = connect(":memory:")
    conn.execute("INSERT INTO nodes(num, id, long_name) VALUES(1, '!00000001', 'Uno')")
    rows = [(1000.0 + i, 1 if i % 2 == 0 else 2, 3 if i % 5 else 1,
             "text" if i % 2 else "position", "rf" if i % 3 else "mqtt", "ok",
             float(i % 10) - 8, b"\x01\xff") for i in range(n)]
    conn.executemany("INSERT INTO packets(time, from_num, to_num, kind, source, status, snr, raw) "
                     "VALUES(?,?,?,?,?,?,?,?)", rows)
    return conn


def test_packet_list_filters_and_cursor():
    conn = _packet_db()
    page = packet_list(conn, PacketFilter(), 100, None)
    assert len(page["items"]) == 100 and page["items"][0]["id"] == 250
    assert page["next_before_id"] == page["items"][-1]["id"] == 151
    last = packet_list(conn, PacketFilter(), 100, 51)
    assert len(last["items"]) == 50 and last["next_before_id"] is None
    assert len(packet_list(conn, PacketFilter(), 5000, None)["items"]) == 200

    def items(**kw):
        return packet_list(conn, PacketFilter(**kw), 200, None)["items"]
    assert items(kind="text") and all(p["kind"] == "text" for p in items(kind="text"))
    assert items(source="rf") and all(p["source"] == "rf" for p in items(source="rf"))
    assert items(min_snr=-5) and all(p["snr"] >= -5 for p in items(min_snr=-5))
    both = items(node=2)
    assert both and all("!00000002" in (p["from"], p["to"]) for p in both)
    one = items(node=1)
    assert any(p["from"] == "!00000002" and p["to"] == "!00000001" for p in one)
    assert any(p["from"] == "!00000001" for p in one)
    assert one[0]["from_name"] in (None, "Uno")
    since = items(since=1240.0)
    assert len(since) == 10 and min(p["time"] for p in since) == 1240.0
    assert len(items(until=1009.0)) == 10


def test_packet_filter_values_are_parameterized():
    conn = _packet_db(5)
    hostile = PacketFilter(kind="x' OR '1'='1")
    assert packet_list(conn, hostile, 10, None)["items"] == []


def test_packet_detail_hex_and_json():
    conn = _packet_db(3)
    conn.execute("UPDATE packets SET receptions='[{\"source\": \"rf\"}]', "
                 "summary='{\"a\": 1}' WHERE id=1")
    d = packet_detail(conn, 1)
    assert d["raw_hex"] == "01ff" and d["receptions"] == [{"source": "rf"}]
    assert d["summary"] == {"a": 1}
    d2 = packet_detail(conn, 2)
    assert d2["receptions"] == [] and d2["summary"] is None
    conn.execute("UPDATE packets SET raw=NULL WHERE id=3")
    assert packet_detail(conn, 3)["raw_hex"] == ""
    assert packet_detail(conn, 99) is None
