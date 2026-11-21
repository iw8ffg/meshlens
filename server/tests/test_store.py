import pytest

from meshlens.db import connect
from meshlens.events import TelemetryData
from meshlens.settings import DEFAULTS
from meshlens.store import Store

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
                     "channel_index": None, "packet_id": None, "status": None}
    assert store.messages(["SE"], None, 50)[0]["from_name"] is None
    assert [m["key"] for m in store.messages(None, NOW + 2, 50)] == ["1:2", "1:1"]
    assert len(store.messages(None, None, 1)) == 1


def test_positions_and_telemetry_since(store):
    store.add_position(1, NOW - 10, 45.0, 9.0, 13, "mqtt")
    store.add_position(1, NOW - 1000, 44.0, 8.0, None, "mqtt")
    assert len(store.positions(1, NOW - 100)) == 1
    store.add_telemetry(1, NOW, TelemetryData(battery_level=80, voltage=4.0, uptime_seconds=5))
    t = store.telemetry(1, NOW - 1)
    assert t[0]["battery"] == 80 and t[0]["uptime"] == 5


def test_purge_retention(store):
    store.add_position(1, NOW - 91 * DAY, 45.0, 9.0, 13, "mqtt")
    store.add_position(1, NOW - 89 * DAY, 45.0, 9.0, 13, "mqtt")
    store.add_message(msg("1:1", NOW - 91 * DAY))
    store.add_telemetry(1, NOW - 100 * DAY, TelemetryData())
    res = store.purge(NOW, DEFAULTS)
    assert res == {"messages": 1, "positions": 1, "telemetry": 0, "nodes": 0}
    assert len(store.positions(1, 0)) == 1


def test_purge_storage_cap(store):
    for i in range(3000):
        store.add_position(1, NOW - i, 45.0, 9.0, 13, "mqtt")
        store.add_message(msg(f"1:{i}", NOW - i))
    store.commit()
    assert store._used_bytes() > 100_000
    res = store.purge(NOW, {**DEFAULTS, "storage_cap_mb": 0.1})
    assert store._used_bytes() <= 0.1 * 1024 * 1024
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
                 "status": "ok", "error": None, "forward": fwd, "back": []}
    assert store.traceroutes(11) == []
