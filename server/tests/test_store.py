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
                     "source": "mqtt"}
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
