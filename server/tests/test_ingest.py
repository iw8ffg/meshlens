import pytest

from meshlens.db import connect
from meshlens.dedup import Deduplicator
from meshlens.events import MeshEvent, NodeInfoData, PositionData, TelemetryData, TextData
from meshlens.geo import CountryLocator
from meshlens.ingest import Ingestor, _new_node
from meshlens.live import LiveState
from meshlens.store import Store

NOW = 1_800_000_000.0
HOUR = 3600
MILAN = (45.46, 9.19)
BERLIN = (52.52, 13.40)
SETTINGS = {"saved_countries": ["IT"]}


@pytest.fixture(scope="module")
def locator():
    return CountryLocator()


@pytest.fixture
def env(locator):
    conn = connect(":memory:")
    store = Store(conn)
    live = LiveState()
    got = []
    ing = Ingestor(live, store, Deduplicator(), locator, lambda: SETTINGS, got.append)
    return ing, live, store, conn, got


def ev(kind, payload, num=1, pid=1, t=NOW, source="mqtt", **kw):
    d = dict(source=source, from_node=num, to_node=0xFFFFFFFF, packet_id=pid, channel="LongFast",
             rx_time=t, snr=-7.5, rssi=None, hops=2, gateway_id="!gw", radio_id=None)
    d.update(kw)
    return MeshEvent(kind=kind, payload=payload, **d)


def pos(coords, bits=13):
    return PositionData(lat=coords[0], lon=coords[1], precision_bits=bits)


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_saved_country_position(env):
    ing, live, store, conn, _ = env
    ing.handle(ev("position", pos(MILAN)))
    n = live.nodes[1]
    assert n["country"] == "IT" and n["id"] == "!00000001"
    assert n["position_source"] == "mqtt" and n["last_snr"] == -7.5 and n["hops"] == 2
    assert [x["num"] for x in store.load_nodes()] == [1]
    assert count(conn, "positions") == 1


def test_unsaved_country_stays_live_only(env):
    ing, live, store, conn, _ = env
    ing.handle(ev("position", pos(BERLIN)))
    assert live.nodes[1]["country"] == "DE"
    assert store.load_nodes() == [] and count(conn, "positions") == 0


def test_text_from_italian_node(env):
    ing, live, store, conn, got = env
    ing.handle(ev("nodeinfo", NodeInfoData("Mario", "MA", "HELTEC_V3", "CLIENT"), pid=1))
    ing.handle(ev("position", pos(MILAN), pid=2))
    ing.handle(ev("text", TextData("ciao <b>mondo</b>"), pid=3))
    assert len(got) == 1 and got[0]["country"] == "IT"
    assert got[0]["text"] == "ciao <b>mondo</b>" and got[0]["from_name"] == "Mario"
    assert got[0]["key"] == "1:3" and got[0]["to"] == "!ffffffff"
    assert list(live.messages) == got and count(conn, "messages") == 1


def test_text_from_unknown_country_not_stored(env):
    ing, live, _, conn, got = env
    ing.handle(ev("text", TextData("hi")))
    assert got[0]["country"] is None and got[0]["from_name"] is None
    assert count(conn, "messages") == 0


def test_duplicate_mqtt_packet(env):
    ing, live, _, _, got = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    e = ev("text", TextData("ciao"), pid=2)
    ing.handle(e)
    ing.handle(e)
    assert len(got) == 1 and len(live.messages) == 1
    assert live.nodes[1]["mqtt_gateways"] == 2


def test_precision_rule(env):
    ing, live, _, _, _ = env
    ing.handle(ev("position", pos(MILAN, 13), pid=1))
    ing.handle(ev("position", pos(BERLIN, 10), pid=2, t=NOW + HOUR))
    assert live.nodes[1]["precision_bits"] == 13 and live.nodes[1]["country"] == "IT"
    ing.handle(ev("position", pos(BERLIN, 10), pid=3, t=NOW + 25 * HOUR))
    assert live.nodes[1]["precision_bits"] == 10 and live.nodes[1]["country"] == "DE"


def test_rf_position_counts_as_32_bits_and_is_stored(env):
    ing, live, store, _, _ = env
    ing.handle(ev("position", pos(BERLIN, None), source="rf", radio_id="r"))
    assert live.nodes[1]["position_source"] == "rf"
    assert [n["num"] for n in store.load_nodes()] == [1]
    ing.handle(ev("position", pos(MILAN, 20), pid=9, t=NOW + HOUR))
    assert live.nodes[1]["country"] == "DE"


def test_nodeinfo_only(env):
    ing, live, store, _, _ = env
    ing.handle(ev("nodeinfo", NodeInfoData("Mario", "MA", "HELTEC_V3", "CLIENT")))
    n = live.nodes[1]
    assert n["long_name"] == "Mario" and n["lat"] is None and n["country"] is None
    assert store.load_nodes() == []


def test_telemetry_updates_and_persists(env):
    ing, live, _, conn, _ = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    ing.handle(ev("telemetry", TelemetryData(87, 4.01, 12.5, 1.2), pid=2))
    n = live.nodes[1]
    assert (n["battery"], n["voltage"], n["channel_util"], n["air_util_tx"]) == (87, 4.01, 12.5, 1.2)
    assert count(conn, "telemetry") == 1


def test_mine_node_outside_saved_countries_is_persisted(env):
    ing, live, store, conn, _ = env
    live.nodes[1] = {**_new_node(1), "is_mine": True}
    ing.handle(ev("telemetry", TelemetryData(50, 3.9, 5.0, 1.0), pid=2))
    assert count(conn, "telemetry") == 1
    assert [n["num"] for n in store.load_nodes()] == [1]


def test_new_node_has_is_mine_false(env):
    ing, live, _, _, _ = env
    ing.handle(ev("position", pos(MILAN)))
    assert live.nodes[1]["is_mine"] is False


def test_unmarked_node_outside_saved_countries_not_persisted(env):
    ing, live, _, conn, _ = env
    ing.handle(ev("telemetry", TelemetryData(50, 3.9, 5.0, 1.0), pid=2))
    assert count(conn, "telemetry") == 0


def test_take_changed(env):
    ing, live, _, _, _ = env
    ing.handle(ev("position", pos(MILAN), num=1))
    ing.handle(ev("position", pos(BERLIN), num=2))
    assert {n["num"] for n in live.take_changed()} == {1, 2}
    assert live.take_changed() == []


def test_duplicate_copies_keep_best_snr_and_min_hops(env):
    ing, live, _, _, _ = env
    ing.handle(ev("position", pos(MILAN), pid=5, snr=-10.0, hops=3))
    ing.handle(ev("position", pos(MILAN), pid=5, snr=-3.0, hops=1))
    ing.handle(ev("position", pos(MILAN), pid=5, snr=-12.0, hops=5))
    assert live.nodes[1]["last_snr"] == -3.0 and live.nodes[1]["hops"] == 1
    ing.handle(ev("position", pos(MILAN), pid=6, snr=-9.0, hops=4))  # nuovo pacchetto
    assert live.nodes[1]["last_snr"] == -9.0 and live.nodes[1]["hops"] == 4
