import time

from meshlens.db import connect
from meshlens.queries import (bucket_rows, metric_series, ro_connect, snr_series, track,
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
