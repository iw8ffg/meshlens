import pytest

from meshlens.db import connect
from meshlens.dedup import Deduplicator
from meshlens.events import MeshEvent, NodeInfoData, PositionData, TelemetryData, TextData
from meshlens.events import WaypointData
from meshlens.events import node_id
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
    ing.handle(ev("text", TextData("ciao"), pid=2, gateway_id="!gw2"))
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


def test_environment_telemetry_stored_as_metrics(env):
    ing, live, _, conn, _ = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    ing.handle(ev("telemetry", TelemetryData(87, 4.01), pid=2))
    ing.handle(ev("telemetry", TelemetryData(variant="environment", metrics={
        "temperature": 21.5, "relative_humidity": 40.0}), pid=3, t=NOW + 10))
    assert count(conn, "telemetry") == 1 and count(conn, "metrics") == 2
    assert (live.nodes[1]["battery"], live.nodes[1]["voltage"]) == (87, 4.01)


def test_device_after_environment_not_stale(env):
    ing, live, _, conn, _ = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    ing.handle(ev("telemetry", TelemetryData(variant="environment",
                                             metrics={"temperature": 20.0}), pid=2, t=NOW + 10))
    ing.handle(ev("telemetry", TelemetryData(55, 3.8), pid=3, t=NOW + 5))
    assert live.nodes[1]["battery"] == 55
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


def test_traceroute_chains():
    from meshlens.events import RouteData
    from meshlens.ingest import traceroute_chains
    e = ev("traceroute", RouteData(5, [2], [6.0, -1.0], [], [4.0]), num=3, to_node=1)
    assert traceroute_chains(e) == ([(1, None), (2, 6.0), (3, -1.0)], [(3, None), (1, 4.0)])


def test_ingest_records_links(env):
    from meshlens.events import NeighborData, RouteData
    ing, live, store, conn, got = env
    for n in (1, 2, 3, 5, 6):
        ing.live.nodes[n] = _new_node(n)
        ing.live.nodes[n]["is_mine"] = True
    ing.handle(ev("neighbors", NeighborData([(5, 6.5), (6, None)]), num=3, pid=1))
    ing.handle(ev("traceroute", RouteData(5, [2], [6.0, -1.0], [], [4.0]), num=3, pid=2,
                  to_node=1))
    rows = {(r["from_id"], r["to_id"], r["source"]): r["snr"] for r in store.links(0)}
    assert rows == {(node_id(5), node_id(3), "neighborinfo"): 6.5,
                    (node_id(6), node_id(3), "neighborinfo"): None,
                    (node_id(1), node_id(2), "traceroute"): 6.0,
                    (node_id(2), node_id(3), "traceroute"): -1.0,
                    (node_id(3), node_id(1), "traceroute"): 4.0}
    assert live.nodes[3]["last_heard"] == NOW and live.nodes[3]["lat"] is None
    assert not got


def test_traceroute_unknown_hops_split_chain_without_links(env):
    from meshlens.events import RouteData
    ing, live, store, conn, got = env
    for n in (1, 2, 3, 4):
        live.nodes[n] = _new_node(n)
        live.nodes[n]["is_mine"] = True
    # andata 1 -> 2 -> ignoto -> 4 -> 3; ritorno diretto con un hop 0
    ing.handle(ev("traceroute", RouteData(5, [2, 0xFFFFFFFF, 4], [1.0, 2.0, 3.0, 4.0],
                                          [0], [5.0, 6.0]), num=3, pid=2, to_node=1))
    rows = {(r["from_id"], r["to_id"]) for r in store.links(0)}
    assert rows == {(node_id(1), node_id(2)), (node_id(4), node_id(3))}
    assert all(0xFFFFFFFF not in (r["from_id"], r["to_id"]) for r in store.links(0))
    assert node_id(0) not in {x for pair in rows for x in pair}
    assert 0xFFFFFFFF not in live.nodes and 0 not in live.nodes


def test_mqtt_links_only_for_persisted_endpoints(env):
    from meshlens.events import NeighborData, RouteData
    ing, live, store, conn, got = env
    for n, c in ((3, "DE"), (4, "DE"), (5, "IT")):
        live.nodes[n] = _new_node(n)
        live.nodes[n]["country"] = c
    ing.handle(ev("neighbors", NeighborData([(4, 1.0), (9, 2.0)]), num=3, pid=1))
    assert store.links(0) == []
    ing.handle(ev("neighbors", NeighborData([(5, 1.0)]), num=3, pid=2))
    assert len(store.links(0)) == 1


def test_traceroute_request_without_id_makes_no_links(env):
    from meshlens.events import RouteData
    ing, live, store, conn, got = env
    live.nodes[1] = _new_node(1)
    live.nodes[1]["is_mine"] = True
    ing.handle(ev("traceroute", RouteData(None, [], [], [], []), num=3, to_node=1))
    assert store.links(0) == []


# ---- filtro canali MQTT ----
def make_env(locator, settings):
    conn = connect(":memory:")
    live = LiveState()
    got = []
    ing = Ingestor(live, Store(conn), Deduplicator(), locator, lambda: settings, got.append)
    return ing, live, got


def test_mqtt_channels_empty_accepts_all(locator):
    ing, live, got = make_env(locator, {"saved_countries": ["IT"], "mqtt_channels": []})
    ing.handle(ev("text", TextData("a"), num=1, pid=1, channel="MediumFast"))
    assert 1 in live.nodes and len(got) == 1


def test_mqtt_channels_filter_ignores_other_mqtt_but_counts(locator):
    ing, live, got = make_env(locator, {"saved_countries": ["IT"], "mqtt_channels": ["LongFast"]})
    ing.handle(ev("text", TextData("a"), num=1, pid=1, channel="MediumFast"))
    ing.handle(ev("text", TextData("b"), num=2, pid=2, channel="LongFast"))
    assert 1 not in live.nodes and got and [m["text"] for m in got] == ["b"]
    assert 2 in live.nodes
    counts = ing.mqtt_channel_counts(now=NOW + 10)
    assert counts == {"MediumFast": 1, "LongFast": 1}


def test_mqtt_channels_filter_never_applies_to_rf(locator):
    ing, live, got = make_env(locator, {"saved_countries": ["IT"], "mqtt_channels": ["LongFast"]})
    ing.handle(ev("text", TextData("a"), num=1, pid=1, source="rf", channel="0", radio_id="r"))
    assert 1 in live.nodes and len(got) == 1
    assert ing.mqtt_channel_counts(now=NOW) == {}


def test_mqtt_channel_counts_window_one_hour(locator):
    ing, _, _ = make_env(locator, {"saved_countries": ["IT"]})
    ing.handle(ev("text", TextData("a"), num=1, pid=1, t=NOW, channel="LongFast"))
    ing.handle(ev("text", TextData("b"), num=1, pid=2, t=NOW + 3000, channel="LongFast"))
    assert ing.mqtt_channel_counts(now=NOW + 3100) == {"LongFast": 2}
    assert ing.mqtt_channel_counts(now=NOW + 3700) == {"LongFast": 1}
    assert ing.mqtt_channel_counts(now=NOW + 7000) == {}


def test_new_node_has_favorite_false_and_hops_min_none(env):
    ing, live, _, _, _ = env
    ing.handle(ev("position", pos(MILAN)))
    assert live.nodes[1]["is_favorite"] is False and live.nodes[1]["hops_min"] is None


def test_favorite_node_outside_saved_countries_is_persisted(env):
    ing, live, store, conn, _ = env
    live.nodes[1] = {**_new_node(1), "is_favorite": True}
    ing.handle(ev("telemetry", TelemetryData(50, 3.9, 5.0, 1.0), pid=2))
    assert count(conn, "telemetry") == 1


def _links(store):
    return [(l["from_id"], l["to_id"], l["source"], l["snr"]) for l in store.links(0)]


def test_mqtt_gateway_link_on_direct_reception(env):
    ing, live, store, conn, _ = env
    ing.handle(ev("position", pos(MILAN), num=0x1234abcd, pid=90))  # il nodo e' gia' localizzato
    ing.handle(ev("position", pos(MILAN), num=0x1234abcd, gateway_id="!00000077",
                  relay_node=0xcd, hops=0))
    assert _links(store) == [("!1234abcd", "!00000077", "mqtt_gateway", -7.5)]


def test_mqtt_gateway_link_skipped_cases(env):
    ing, live, store, conn, _ = env
    ing.handle(ev("position", pos(MILAN), num=0x1234abcd, gateway_id="!00000077",
                  relay_node=0x11, pid=1))  # ritrasmesso
    ing.handle(ev("position", pos(MILAN), num=0x1234abcd, gateway_id="!00000077",
                  relay_node=0, pid=2))  # sconosciuto
    ing.handle(ev("position", pos(MILAN), num=0x1234abcd, gateway_id="!1234abcd",
                  relay_node=0xcd, pid=3))  # gateway == mittente
    ing.handle(ev("position", pos(MILAN), num=0x1234abcd, gateway_id="!gw",
                  relay_node=0xcd, pid=4))  # gateway non valido
    assert _links(store) == []


def test_mqtt_gateway_link_not_persisted_outside_saved_countries(env):
    ing, live, store, conn, _ = env
    ing.handle(ev("position", pos(BERLIN), num=0x1234abcd, gateway_id="!00000077", relay_node=0xcd))
    assert _links(store) == []


def test_mqtt_gateway_link_persisted_for_favorite(env):
    ing, live, store, conn, _ = env
    live.nodes[0x1234abcd] = {**_new_node(0x1234abcd), "is_favorite": True}
    ing.handle(ev("position", pos(BERLIN), num=0x1234abcd, gateway_id="!00000077", relay_node=0xcd))
    assert len(_links(store)) == 1


def test_mqtt_gateway_links_one_per_gateway_even_for_duplicates(env):
    ing, live, store, conn, _ = env
    ing.handle(ev("position", pos(MILAN), num=0x1234abcd, pid=90))
    for gw in ("!00000077", "!00000088"):
        ing.handle(ev("position", pos(MILAN), num=0x1234abcd, pid=5, gateway_id=gw,
                      relay_node=0xcd))
    assert sorted(l[1] for l in _links(store)) == ["!00000077", "!00000088"]


def test_hops_min_set_from_relayed_mqtt(env):
    ing, live, _, _, _ = env
    ing.handle(ev("position", pos(MILAN), hops=None, hops_min=1, relay_node=0x11))
    n = live.nodes[1]
    assert n["hops"] is None and n["hops_min"] == 1
    ing.handle(ev("position", pos(MILAN), pid=2, hops=0, relay_node=1))
    assert n["hops"] == 0 and n["hops_min"] is None


def test_mqtt_hops_do_not_overwrite_recent_rf_hops(env):
    ing, live, _, _, _ = env
    ing.handle(ev("position", pos(MILAN), source="rf", radio_id="rA", pid=1, hops=3, t=NOW))
    ing.handle(ev("position", pos(MILAN), pid=2, hops=0, relay_node=1, t=NOW + 10))
    assert live.nodes[1]["hops"] == 3
    ing.handle(ev("position", pos(MILAN), source="rf", radio_id="rA", pid=3, hops=2, t=NOW + 20))
    assert live.nodes[1]["hops"] == 2


def test_mqtt_relayed_event_clears_stale_hops(env):
    ing, live, _, _, _ = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    live.nodes[1]["hops"] = 7  # valore vecchio calcolato da hop_start
    ing.handle(ev("position", pos(MILAN), pid=2, hops=None, hops_min=1, relay_node=0x11))
    assert live.nodes[1]["hops"] is None and live.nodes[1]["hops_min"] == 1


def test_mqtt_duplicate_copies_do_not_clear_direct_hops(env):
    ing, live, _, _, _ = env
    ing.handle(ev("position", pos(MILAN), pid=5, hops=0, relay_node=1, gateway_id="!00000077"))
    ing.handle(ev("position", pos(MILAN), pid=5, hops=None, hops_min=1, relay_node=0x11,
                  gateway_id="!00000088"))
    assert live.nodes[1]["hops"] == 0


def test_filtered_channel_counted(locator):
    ing, live, got = make_env(locator, {"saved_countries": ["IT"], "mqtt_channels": ["LongFast"]})
    assert ing.filtered_channel == 0
    ing.handle(ev("text", TextData("a"), num=1, pid=1, channel="MediumFast"))
    ing.handle(ev("text", TextData("b"), num=2, pid=2, channel="LongFast"))
    assert ing.filtered_channel == 1


def test_ingestor_has_no_private_mqtt_seen(env):
    ing = env[0]
    assert not hasattr(ing, "_mqtt_seen")


def test_mqtt_gateways_after_rf_copy_use_shared_dedup(env):
    ing, live, _, _, _ = env
    rf = ev("text", TextData("ciao"), pid=9, source="rf", radio_id="r1", channel="0")
    ing.handle(rf)
    ing.handle(ev("text", TextData("ciao"), pid=9))  # prima copia MQTT: primo gateway
    assert live.nodes[1]["mqtt_gateways"] == 1
    ing.handle(ev("text", TextData("ciao"), pid=9, gateway_id="!gw2"))  # seconda copia MQTT
    assert live.nodes[1]["mqtt_gateways"] == 2


def test_node_evicted_by_cap_is_revived_from_db(env):
    ing, live, store, conn, _ = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    ing.handle(ev("nodeinfo", NodeInfoData("Mario", "MA", "HELTEC_V3", "CLIENT"), pid=2))
    ing.handle(ev("telemetry", TelemetryData(87, 4.01), pid=3))
    live.max_nodes = 0
    assert live.enforce_cap() == 1 and 1 not in live.nodes
    ing.handle(ev("text", TextData("di nuovo qui"), pid=4, t=NOW + HOUR))
    node = live.nodes[1]
    assert node["long_name"] == "Mario" and node["hw_model"] == "HELTEC_V3"
    assert node["lat"] == pytest.approx(MILAN[0]) and node["country"] == "IT"
    assert node["battery"] == 87 and node["last_heard"] == NOW + HOUR
    row = store.get_node(1)
    assert row["long_name"] == "Mario" and row["lat"] == pytest.approx(MILAN[0])
    assert row["battery"] == 87 and row["country"] == "IT"


def test_unknown_node_starts_blank(env):
    ing, live, store, _, _ = env
    assert store.get_node(42) is None
    ing.handle(ev("text", TextData("ciao"), num=42, pid=1))
    assert live.nodes[42]["long_name"] is None and live.nodes[42]["mqtt_gateways"] == 1


def test_message_carries_broker(env):
    ing, live, store, conn, got = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    ing.handle(ev("text", TextData("ciao"), pid=2, broker="b1a2b3c"))
    assert got[0]["broker"] == "b1a2b3c"
    assert conn.execute("SELECT broker FROM messages").fetchone()[0] == "b1a2b3c"
    m = ing.record_outgoing_mqtt(1, 0xFFFFFFFF, 99, "x", "LongFast", broker="default")
    assert m["broker"] == "default"
    assert conn.execute("SELECT broker FROM messages WHERE key='1:99'").fetchone()[0] == "default"
    assert {m["key"]: m["broker"] for m in store.messages(None, None, 10)}["1:99"] == "default"


def test_same_packet_two_brokers_one_message(env):
    ing, live, _, conn, got = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    ing.handle(ev("text", TextData("ciao"), pid=2, broker="default"))
    ing.handle(ev("text", TextData("ciao"), pid=2, broker="b1"))
    assert len(got) == 1 and got[0]["broker"] == "default"
    assert conn.execute("SELECT broker FROM messages").fetchone()[0] == "default"
    assert live.nodes[1]["mqtt_gateways"] == 1
    ing.handle(ev("text", TextData("ciao"), pid=2, broker="b1", gateway_id="!other"))
    assert live.nodes[1]["mqtt_gateways"] == 2


def test_channel_counts_per_broker(env):
    ing, *_ = env
    ing.handle(ev("text", TextData("a"), pid=1, broker="default"))
    ing.handle(ev("text", TextData("b"), pid=2, broker="default"))
    ing.handle(ev("text", TextData("c"), pid=3, broker="b1"))
    assert ing.mqtt_channel_counts(now=NOW) == {"LongFast": 3}
    assert ing.mqtt_channel_counts(now=NOW, broker="b1") == {"LongFast": 1}
    assert ing.mqtt_channel_brokers(now=NOW)["LongFast"] == ["default", "b1"]


def test_message_carries_reply_emoji_pki(env):
    ing, live, store, conn, got = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    ing.handle(ev("text", TextData("\U0001F44D", reply_id=5, emoji=True), pid=2, pki=True))
    m = got[0]
    assert m["reply_id"] == 5 and m["emoji"] is True and m["pki"] is True and m["error"] is None
    saved = store.messages(None, None, 10)[0]
    assert saved["reply_id"] == 5 and saved["emoji"] is True and saved["pki"] is True
    ing.handle(ev("text", TextData("ciao"), pid=3))
    assert got[1]["reply_id"] is None and got[1]["emoji"] is False and got[1]["pki"] is False


def test_outgoing_carries_reply_and_emoji(env):
    ing, live, store, conn, got = env
    m = ing.record_outgoing("rA", "!00000001", 55, "\U0001F44D", 0, "!ffffffff",
                            reply_id=7, emoji=True)
    assert (m["reply_id"], m["emoji"], m["pki"]) == (7, True, False)
    q = ing.record_outgoing_mqtt(1, 0xFFFFFFFF, 99, "ok", "LongFast", reply_id=8)
    assert (q["reply_id"], q["emoji"], q["pki"]) == (8, False, False)
    saved = {x["key"]: x for x in store.messages(None, None, 10)}
    assert saved["out:rA:55"]["reply_id"] == 7 and saved["out:rA:55"]["emoji"] is True
    assert saved["1:99"]["reply_id"] == 8 and saved["1:99"]["emoji"] is False


def _ni(key):
    return NodeInfoData("Mario", "MA", "HELTEC_V3", "CLIENT", public_key=key)


def test_public_key_change_detection(env):
    import base64
    ing, live, store, conn, _ = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    ing.handle(ev("nodeinfo", _ni(b"A" * 32), pid=2))
    n = live.nodes[1]
    a64 = base64.b64encode(b"A" * 32).decode()
    assert n["public_key"] == a64 and n["key_changed"] is None
    ing.handle(ev("nodeinfo", _ni(b"A" * 32), pid=3, source="rf", radio_id="rA",
                  gateway_id=None, channel="0"))
    assert n["key_changed"] is None
    ing.handle(ev("nodeinfo", _ni(None), pid=4))
    ing.handle(ev("nodeinfo", _ni(b""), pid=5))
    assert n["public_key"] == a64 and n["key_changed"] is None
    ing.handle(ev("nodeinfo", _ni(b"B" * 32), pid=6, t=NOW + 1000, source="rf",
                  radio_id="rA", gateway_id=None, channel="0"))
    b64 = base64.b64encode(b"B" * 32).decode()
    assert n["key_changed"] == NOW + 1000 and n["public_key"] == b64
    saved = store.get_node(1)
    assert saved["public_key"] == b64 and saved["key_changed"] == NOW + 1000


def test_mqtt_key_never_replaces_or_flags(env):
    import base64
    ing, live, store, conn, _ = env
    ing.handle(ev("position", pos(MILAN), pid=1))
    ing.handle(ev("nodeinfo", _ni(b"A" * 32), pid=2))  # chiave mancante: la riempie
    n = live.nodes[1]
    a64 = base64.b64encode(b"A" * 32).decode()
    assert n["public_key"] == a64
    ing.handle(ev("nodeinfo", _ni(b"B" * 32), pid=3, t=NOW + 10))  # MQTT diversa: ignorata
    assert n["public_key"] == a64 and n["key_changed"] is None


def test_new_node_has_no_public_key():
    n = _new_node(9)
    assert n["public_key"] is None and n["key_changed"] is None


def _wp(wid=42, lat=MILAN[0], lon=MILAN[1], icon=0x1F4CD, expire=0, locked_to=0):
    return WaypointData(id=wid, lat=lat, lon=lon, name="Ritrovo", description="qui",
                        icon=icon, expire=expire, locked_to=locked_to)


def _rfwp(payload, pid):
    return ev("waypoint", payload, pid=pid, source="rf", radio_id="rA", gateway_id=None,
              channel="0")


def test_waypoint_store_and_delete(env):
    ing, live, store, conn, _ = env
    wps = []
    ing.on_waypoint = wps.append
    ing.set_radio_node("rA", 1)
    ing.handle(_rfwp(_wp(locked_to=1), 1))
    assert wps[-1] == {"id": 42, "from": "!00000001", "from_name": None, "lat": MILAN[0],
                       "lon": MILAN[1], "name": "Ritrovo", "description": "qui",
                       "icon": "\U0001F4CD", "expire": None, "locked_to": "!00000001",
                       "time": int(NOW), "source": "rf", "radio_id": "rA", "channel": "0",
                       "mine": True}
    (row,) = store.active_waypoints(NOW)
    assert row["id"] == 42 and row["icon"] == 0x1F4CD and row["country"] == "IT"
    assert row["from_num"] == 1 and row["locked_to"] == 1
    # stesso id con expire=1: l'eliminazione delle app ufficiali
    ing.handle(_rfwp(_wp(expire=1), 2))
    assert wps[-1] == {"deleted": 42} and store.active_waypoints(NOW) == []
    # coordinate non valide: eliminazione
    ing.handle(ev("waypoint", _wp(wid=43, lat=None, lon=None), pid=3))
    assert wps[-1] == {"deleted": 43}
    # MQTT fuori dalle nazioni salvate: ne' salvato ne' pubblicato
    n_before = len(wps)
    ing.handle(ev("waypoint", _wp(wid=44, lat=48.85, lon=2.35, expire=int(NOW) + 3600),
                  num=2, pid=4))
    assert len(wps) == n_before and store.active_waypoints(NOW) == []
    # MQTT in una nazione salvata: si salva e si pubblica
    ing.handle(ev("waypoint", _wp(wid=45, expire=int(NOW) + 3600), num=2, pid=5))
    assert [r["id"] for r in store.active_waypoints(NOW)] == [45]
    assert wps[-1]["id"] == 45 and wps[-1]["mine"] is False
    assert wps[-1]["expire"] == int(NOW) + 3600 and wps[-1]["locked_to"] is None
    # icona non valida (surrogato) o assente
    ing.handle(ev("waypoint", _wp(wid=46, icon=0xD800), num=2, pid=6))
    assert wps[-1]["icon"] == ""
    ing.handle(ev("waypoint", _wp(wid=47, icon=0), num=2, pid=7))
    assert wps[-1]["icon"] == ""


def test_waypoint_without_callback(env):
    ing, live, store, *_ = env
    ing.handle(ev("waypoint", _wp(), pid=1))
    assert [r["id"] for r in store.active_waypoints(NOW)] == [42]


def test_set_status_with_error(env):
    ing, live, store, *_ = env
    calls = []
    ing.on_status = lambda *a: calls.append(a)
    ing.record_outgoing("rA", "!00000001", 5, "x", 0, "!00000002")
    ing.set_status("out:rA:5", "failed", "NO_ROUTE")
    assert calls == [("out:rA:5", "failed", "NO_ROUTE")]
    assert live.messages[-1]["status"] == "failed" and live.messages[-1]["error"] == "NO_ROUTE"
    assert store.messages(None, None, 10)[0]["error"] == "NO_ROUTE"


def test_nodedb_replay_never_changes_key(env):
    import base64
    ing, live, store, *_ = env

    def replay(key, t, pid=0):
        return ev("nodeinfo", _ni(key), pid=pid, t=t, source="rf", radio_id="rA",
                  gateway_id=None, channel="0", snr=None)

    a64 = base64.b64encode(b"A" * 32).decode()
    # replay senza orario su un nodo senza chiave: riempie il vuoto
    ing.handle(replay(b"A" * 32, 0))
    n = live.nodes[1]
    assert n["public_key"] == a64 and n["key_changed"] is None
    ing.handle(ev("nodeinfo", _ni(b"A" * 32), pid=2))  # chiave viva, uguale
    # replay con chiave diversa: senza orario o con orario vecchio non cambia nulla
    ing.handle(replay(b"B" * 32, 0))
    ing.handle(replay(b"B" * 32, NOW - HOUR))
    assert n["public_key"] == a64 and n["key_changed"] is None
    ing.handle(ev("nodeinfo", _ni(b"A" * 32), pid=3, t=NOW + 1))
    assert n["public_key"] == a64 and n["key_changed"] is None
    assert store.get_node(1)["key_changed"] is None


def test_waypoint_deleted_only_by_its_sender(env):
    ing, live, store, *_ = env
    wps = []
    ing.on_waypoint = wps.append
    ing.handle(ev("waypoint", _wp(), num=1, pid=1))
    ing.handle(ev("waypoint", _wp(expire=1), num=2, pid=2))
    assert [r["id"] for r in store.active_waypoints(NOW)] == [42]
    assert wps[-1]["id"] == 42 and len(wps) == 1
    ing.handle(ev("waypoint", _wp(expire=1), num=1, pid=3))
    assert wps[-1] == {"deleted": 42} and store.active_waypoints(NOW) == []
    # sconosciuto: l'eliminazione passa comunque
    ing.handle(ev("waypoint", _wp(wid=50, expire=1), num=3, pid=4))
    assert wps[-1] == {"deleted": 50}


def test_waypoint_expiry_without_rx_time(env, monkeypatch):
    import meshlens.ingest as ingmod
    ing, live, store, *_ = env
    wps = []
    ing.on_waypoint = wps.append
    monkeypatch.setattr(ingmod.time, "time", lambda: NOW)
    ing.handle(ev("waypoint", _wp(expire=int(NOW) - 10), pid=1, t=0, source="rf",
                  radio_id="rA", gateway_id=None, channel="0"))
    assert wps == [{"deleted": 42}]


def test_waypoint_takeover_refused(env):
    ing, live, store, *_ = env
    wps = []
    ing.on_waypoint = wps.append
    ing.set_radio_node("rA", 1)
    ing.handle(ev("waypoint", _wp(), num=1, pid=1))  # di una radio locale
    assert len(wps) == 1
    ing.handle(ev("waypoint", _wp(lat=41.9, lon=12.5), num=2, pid=2))
    assert len(wps) == 1 and store.get_waypoint(42)["from_num"] == 1
    assert store.get_waypoint(42)["lat"] == MILAN[0]
    # bloccato verso un nodo: nessun altro lo sostituisce
    ing.handle(ev("waypoint", _wp(wid=60, locked_to=5), num=7, pid=3))
    ing.handle(ev("waypoint", _wp(wid=60, lat=41.9, lon=12.5), num=8, pid=4))
    assert len(wps) == 2 and store.get_waypoint(60)["from_num"] == 7
    # non bloccato e non locale: il nuovo arrivo lo aggiorna ma il proprietario resta
    ing.handle(ev("waypoint", _wp(wid=61), num=9, pid=5))
    ing.handle(ev("waypoint", _wp(wid=61, lat=41.9, lon=12.5), num=10, pid=6))
    assert store.get_waypoint(61)["from_num"] == 9 and store.get_waypoint(61)["lat"] == 41.9


def test_waypoint_callback_only_when_stored(env):
    ing, live, store, *_ = env
    wps = []
    ing.on_waypoint = wps.append
    ing.handle(ev("waypoint", _wp(lat=-33.9, lon=151.2), num=1, pid=1))  # nazione non salvata
    assert wps == [] and store.active_waypoints(NOW) == []


def test_last_outcome_and_raw_guard(env):
    from meshlens.events import PacketMeta, RawPacket
    ing, live, _, _, _ = env
    ing.handle(ev("text", TextData("a"), pid=9))
    assert ing.last_outcome == "new"
    ing.handle(ev("text", TextData("a"), pid=9, gateway_id="!gw2"))
    assert ing.last_outcome == "dup"
    live.nodes.clear()
    raw = RawPacket("mqtt", 5, 0, 1, "LongFast", NOW, None, None, None, None, None, None,
                    "encrypted", PacketMeta(None, None, None))
    ing.handle(raw)
    assert ing.last_outcome == "ignored" and 5 not in live.nodes
    global SETTINGS
    old = SETTINGS
    try:
        SETTINGS = {"saved_countries": ["IT"], "mqtt_channels": ["Altro"]}
        ing.handle(ev("text", TextData("b"), pid=10))
        assert ing.last_outcome == "ignored"
    finally:
        SETTINGS = old


# ---- invii MQTT: esito del broker e "sentito in radio" ----
ME_NUM = 0xA1B2C3D4


def _sent(env, statuses=None):
    ing, live, store, conn, got = env
    if statuses is not None:
        ing.on_status = lambda key, status, error=None, heard_by=None: statuses.append(
            (key, status, error, heard_by))
    return ing.record_outgoing_mqtt(ME_NUM, 0xFFFFFFFF, 77, "ciao", "LongFast", now=NOW,
                                    broker="default")


def test_outgoing_mqtt_starts_sending_then_broker_accepts(env):
    ing, live, store, conn, got = env
    st = []
    m = _sent(env, st)
    assert m["status"] == "sending" and m["heard_by"] is None
    ing.mqtt_publish_result(m["key"], True, None)
    assert st == [(m["key"], "sent", None, None)]
    assert conn.execute("SELECT status FROM messages WHERE key=?", (m["key"],)).fetchone()[0] == "sent"


def test_outgoing_mqtt_broker_timeout_fails(env):
    ing, live, store, conn, got = env
    st = []
    m = _sent(env, st)
    ing.mqtt_publish_result(m["key"], False, "Il broker non ha confermato il messaggio")
    assert st[-1][:3] == (m["key"], "failed", "Il broker non ha confermato il messaggio")
    row = store.messages(None, None, 10)[0]
    assert row["status"] == "failed" and row["error"] == "Il broker non ha confermato il messaggio"


def test_own_echo_is_not_heard(env):
    ing, live, store, conn, got = env
    st = []
    _sent(env, st)
    ing.handle(ev("text", TextData("ciao"), num=ME_NUM, pid=77, t=NOW + 1,
                  gateway_id=node_id(ME_NUM)))
    assert st == [] and live.messages[-1]["status"] == "sending"


def test_other_gateway_marks_heard(env):
    ing, live, store, conn, got = env
    st = []
    m = _sent(env, st)
    ing.mqtt_publish_result(m["key"], True, None)
    ing.handle(ev("text", TextData("ciao"), num=ME_NUM, pid=77, t=NOW + 2,
                  gateway_id="!0badcafe"))
    assert st[-1] == (m["key"], "heard", None, ["!0badcafe"])
    assert len(live.messages) == 1 and live.messages[0]["status"] == "heard"
    assert live.messages[0]["heard_by"] == ["!0badcafe"]
    row = store.messages(None, None, 10)[0]
    assert row["status"] == "heard" and row["heard_by"] == ["!0badcafe"]
    # il PUBACK in ritardo (o il timeout) non fa tornare indietro lo stato
    ing.mqtt_publish_result(m["key"], False, "Il broker non ha confermato il messaggio")
    assert live.messages[0]["status"] == "heard"
    # un secondo gateway si aggiunge all'elenco
    ing.handle(ev("text", TextData("ciao"), num=ME_NUM, pid=77, t=NOW + 3,
                  gateway_id="!0000beef"))
    assert store.messages(None, None, 10)[0]["heard_by"] == ["!0badcafe", "!0000beef"]


def test_local_rf_copy_marks_heard(env):
    ing, live, store, conn, got = env
    st = []
    ing.set_radio_node("rA", 0x11223344)
    m = _sent(env, st)
    ing.handle(ev("text", TextData("ciao"), num=ME_NUM, pid=77, t=NOW + 2, source="rf",
                  radio_id="rA", gateway_id=None))
    assert st[-1] == (m["key"], "heard", None, ["!11223344"])
    # resta un messaggio MQTT in uscita: non diventa un messaggio della radio
    assert live.messages[0]["source"] == "mqtt" and live.messages[0]["radio_id"] is None


def test_rf_copy_via_mqtt_is_not_heard(env):
    ing, live, store, conn, got = env
    st = []
    _sent(env, st)
    ing.handle(ev("text", TextData("ciao"), num=ME_NUM, pid=77, t=NOW + 2, source="rf",
                  radio_id="rA", gateway_id=None, via_mqtt=True))
    assert st == []


def test_heard_by_merges_from_db_when_message_not_in_live(env):
    ing, live, store, conn, got = env
    m = _sent(env)
    ing.mqtt_publish_result(m["key"], True, None)
    ing.handle(ev("text", TextData("ciao"), num=ME_NUM, pid=77, t=NOW + 2, gateway_id="!0badcafe"))
    live.messages.clear()  # il messaggio non e' piu' in memoria
    ing.handle(ev("text", TextData("ciao"), num=ME_NUM, pid=77, t=NOW + 3, gateway_id="!0000beef"))
    assert store.messages(None, None, 10)[0]["heard_by"] == ["!0badcafe", "!0000beef"]


def test_publish_result_does_not_regress_heard_when_not_in_live(env):
    ing, live, store, conn, got = env
    m = _sent(env)
    ing.handle(ev("text", TextData("ciao"), num=ME_NUM, pid=77, t=NOW + 2, gateway_id="!0badcafe"))
    live.messages.clear()
    ing.mqtt_publish_result(m["key"], False, "timeout")
    row = store.messages(None, None, 10)[0]
    assert row["status"] == "heard" and row["heard_by"] == ["!0badcafe"]


def test_prune_drops_maps_of_departed_nodes_and_old_channels(env):
    ing, live, store, conn, got = env
    ing._telemetry_time[(7, "device")] = NOW
    ing._telemetry_time[(8, "device")] = NOW
    ing._rf_hops_time[7] = NOW
    ing._rf_hops_time[8] = NOW
    live.nodes[8] = {"num": 8}
    ing._note_mqtt_channel("Vecchio", NOW, "b")
    ing._note_mqtt_channel("Nuovo", NOW + 7200, "b")
    ing.prune(NOW + 7200)
    assert list(ing._telemetry_time) == [(8, "device")]
    assert list(ing._rf_hops_time) == []  # 8 presente ma l'hops RF e' scaduto
    assert list(ing._channel_buckets) == [("b", "Nuovo")]


def test_mqtt_packets_with_id_zero_are_not_deduplicated(env):
    ing, live, store, conn, got = env
    ing.handle(ev("text", TextData("uno"), pid=0))
    assert ing.last_outcome == "new"
    ing.handle(ev("text", TextData("due"), pid=0, t=NOW + 1))
    assert ing.last_outcome == "new"
    assert [m["text"] for m in live.messages] == ["uno", "due"]


def test_heard_outside_window_ignored(env):
    ing, live, store, conn, got = env
    st = []
    _sent(env, st)
    ing.handle(ev("text", TextData("ciao"), num=ME_NUM, pid=77, t=NOW + 700,
                  gateway_id="!0badcafe"))
    assert all(s[1] != "heard" for s in st)


def test_app_event_updates_node_without_payload_handling(env):
    from meshlens.events import AppData
    ing, live, store, conn, _ = env
    ing.handle(ev("paxcounter", AppData(34, b""), num=9, source="rf", radio_id="r1"))
    assert live.nodes[9]["last_heard"] == NOW
    assert ing.last_outcome == "new"
    assert count(conn, "telemetry") == 0 and count(conn, "metrics") == 0
    assert store.get_node(9) is not None


def test_persists_helper(env):
    ing = env[0]
    base = _new_node(5)
    assert ing.persists({**base, "country": "DE"}, "rf")
    assert ing.persists({**base, "country": "DE", "is_mine": True}, "mqtt")
    assert ing.persists({**base, "country": "DE", "is_favorite": True}, "mqtt")
    assert ing.persists({**base, "country": "IT"}, "mqtt")
    assert not ing.persists({**base, "country": "DE"}, "mqtt")


def test_new_node_has_is_ignored_false(env):
    ing, live, *_ = env
    ing.handle(ev("position", pos(MILAN), num=3))
    assert live.nodes[3]["is_ignored"] is False
    assert _new_node(4)["is_ignored"] is False
