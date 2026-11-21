import pytest

from meshlens.events import NodeInfoData, PositionData, TelemetryData, TextData
from meshlens.rf_convert import nodedb_to_events, packet_to_event

NOW = 1000.0


def _pkt(decoded, **extra):
    p = {"from": 0x1234, "to": 0xFFFFFFFF, "id": 7, "rxTime": 5, "rxSnr": 6.5,
         "rxRssi": -90, "raw": b"x", "decoded": decoded}
    p.update(extra)
    return p


def test_text_with_emoji():
    ev = packet_to_event(
        _pkt({"portnum": "TEXT_MESSAGE_APP", "text": "ciao \U0001F600", "payload": b"z"}),
        "radio1", NOW)
    assert ev.kind == "text" and ev.payload == TextData(text="ciao \U0001F600")
    assert (ev.source, ev.radio_id, ev.gateway_id) == ("rf", "radio1", None)
    assert (ev.from_node, ev.to_node, ev.packet_id) == (0x1234, 0xFFFFFFFF, 7)
    assert (ev.snr, ev.rssi, ev.channel, ev.rx_time) == (6.5, -90, "0", NOW)


def test_channel_index():
    ev = packet_to_event(_pkt({"portnum": "TEXT_MESSAGE_APP", "text": "a"}, channel=2),
                         "r", NOW)
    assert ev.channel == "2"


def test_position_milan():
    ev = packet_to_event(_pkt({"portnum": "POSITION_APP", "position": {
        "latitude": 45.4642, "longitude": 9.19, "altitude": 120, "precisionBits": 32,
        "time": 99}}), "r", NOW)
    assert ev.kind == "position"
    assert ev.payload == PositionData(lat=45.4642, lon=9.19, alt=120,
                                      precision_bits=32, time=99)


def test_position_zero_or_missing_or_out_of_range():
    for pos in ({"latitude": 0, "longitude": 0}, {}, {"latitude": 95.0, "longitude": 9.0}):
        assert packet_to_event(_pkt({"portnum": "POSITION_APP", "position": pos}),
                               "r", NOW) is None


def test_nodeinfo_default_role():
    ev = packet_to_event(_pkt({"portnum": "NODEINFO_APP", "user": {
        "longName": "Nodo", "shortName": "N", "hwModel": "HELTEC_V3"}}), "r", NOW)
    assert ev.kind == "nodeinfo"
    assert ev.payload == NodeInfoData(long_name="Nodo", short_name="N",
                                      hw_model="HELTEC_V3", role="CLIENT")


def test_telemetry():
    ev = packet_to_event(_pkt({"portnum": "TELEMETRY_APP", "telemetry": {
        "deviceMetrics": {"batteryLevel": 80, "voltage": 4.1, "uptimeSeconds": 60}}}),
        "r", NOW)
    assert ev.payload.voltage == pytest.approx(4.1)  # float32 del protobuf
    ev.payload.voltage = 4.1
    assert ev.payload == TelemetryData(battery_level=80, voltage=4.1, uptime_seconds=60)


def test_telemetry_without_device_metrics():
    ev = packet_to_event(_pkt({"portnum": "TELEMETRY_APP", "telemetry": {
        "environmentMetrics": {"temperature": 20}}}), "r", NOW)
    assert ev.payload.variant == "environment" and ev.payload.metrics == {"temperature": 20.0}
    assert packet_to_event(_pkt({"portnum": "TELEMETRY_APP", "telemetry": {}}), "r", NOW) is None


def test_telemetry_from_payload_bytes():
    from meshtastic.protobuf import telemetry_pb2
    raw = telemetry_pb2.Telemetry(
        environment_metrics=telemetry_pb2.EnvironmentMetrics(temperature=18.5)).SerializeToString()
    ev = packet_to_event(_pkt({"portnum": "TELEMETRY_APP", "payload": raw}), "r", NOW)
    assert ev.payload.variant == "environment" and ev.payload.metrics == {"temperature": 18.5}
    assert packet_to_event(_pkt({"portnum": "TELEMETRY_APP", "payload": bytes([255, 255])}),
                           "r", NOW) is None


def test_no_decoded_and_other_port():
    p = _pkt(None)
    del p["decoded"]
    assert packet_to_event(p, "r", NOW) is None
    assert packet_to_event(_pkt({"portnum": "ROUTING_APP"}), "r", NOW) is None


def test_hops():
    d = {"portnum": "TEXT_MESSAGE_APP", "text": "a"}
    assert packet_to_event(_pkt(d, hopStart=3, hopLimit=1), "r", NOW).hops == 2
    assert packet_to_event(_pkt(d), "r", NOW).hops is None


def test_nodedb():
    nodes = {
        "!00000001": {
            "num": 1, "lastHeard": 500,
            "user": {"longName": "A", "shortName": "a", "hwModel": "TBEAM", "role": "ROUTER"},
            "position": {"latitude": 45.0, "longitude": 9.0, "time": 400},
            "deviceMetrics": {"batteryLevel": 50},
        },
        "!00000002": {
            "num": 2,
            "user": {"longName": "B", "shortName": "b", "hwModel": "HELTEC_V3"},
            "deviceMetrics": {"voltage": 3.9},
        },
    }
    evs = nodedb_to_events(nodes, "r", NOW)
    assert len(evs) == 5
    assert all(e.packet_id == 0 and e.source == "rf" for e in evs)
    first = [e for e in evs if e.from_node == 1]
    assert {e.kind for e in first} == {"nodeinfo", "position", "telemetry"}
    assert all(e.rx_time == 500 for e in first)
    assert all(e.rx_time == 0 for e in evs if e.from_node == 2)  # mai sentito
    pos = next(e for e in first if e.kind == "position")
    assert pos.payload.time == 400
    assert next(e for e in first if e.kind == "nodeinfo").payload.role == "ROUTER"


def test_rf_traceroute_and_neighbors_converted():
    ev = packet_to_event(_pkt({"portnum": "TRACEROUTE_APP", "requestId": 9, "traceroute": {
        "route": [11], "snrTowards": [24, -128], "routeBack": [], "snrBack": [-8]}}), "r", NOW)
    assert ev.kind == "traceroute"
    p = ev.payload
    assert (p.request_id, p.route, p.snr_towards, p.route_back, p.snr_back) == (
        9, [11], [6.0, None], [], [-2.0])
    ev = packet_to_event(_pkt({"portnum": "NEIGHBORINFO_APP", "neighborinfo": {
        "nodeId": 1, "neighbors": [{"nodeId": 5, "snr": 6.5}, {"nodeId": 6, "snr": -3.0}]}}),
        "r", NOW)
    assert ev.kind == "neighbors" and ev.payload.neighbors == [(5, 6.5), (6, -3.0)]


def test_rf_traceroute_falls_back_to_payload():
    from meshtastic.protobuf import mesh_pb2
    rd = mesh_pb2.RouteDiscovery(route=[2], snr_towards=[4])
    ev = packet_to_event(_pkt({"portnum": "TRACEROUTE_APP", "payload": rd.SerializeToString()}),
                         "r", NOW)
    assert ev.payload.route == [2] and ev.payload.snr_towards == [1.0]


def test_parse_seq():
    from meshlens.rf_convert import parse_seq
    assert parse_seq("seq 12") == 12
    assert parse_seq(" seq 0 ") == 0
    for bad in ("seq", "seq -1", "hello 3", "seq 1.5"):
        assert parse_seq(bad) is None


def test_rangetest_packet_converted():
    ev = packet_to_event(_pkt({"portnum": "RANGE_TEST_APP", "text": "seq 7"}), "r", NOW)
    assert ev.kind == "rangetest" and ev.payload.seq == 7
    ev = packet_to_event(_pkt({"portnum": "RANGE_TEST_APP", "payload": b"seq 8"}), "r", NOW)
    assert ev.payload.seq == 8
    ev = packet_to_event(_pkt({"portnum": "RANGE_TEST_APP", "payload": b"\xff\xfe"}), "r", NOW)
    assert ev.kind == "rangetest" and ev.payload.seq is None and ev.payload.text == ""


def test_text_reply_emoji_pki():
    ev = packet_to_event(
        _pkt({"portnum": "TEXT_MESSAGE_APP", "text": "ok", "replyId": 9, "emoji": 1},
             pkiEncrypted=True), "radio1", NOW)
    assert ev.payload.reply_id == 9 and ev.payload.emoji is True and ev.pki is True
    plain = packet_to_event(_pkt({"portnum": "TEXT_MESSAGE_APP", "text": "ok"}), "radio1", NOW)
    assert plain.payload.reply_id is None and plain.payload.emoji is False and plain.pki is False


def test_waypoint_converted():
    ev = packet_to_event(_pkt({"portnum": "WAYPOINT_APP", "waypoint": {
        "id": 5, "latitudeI": 451000000, "longitudeI": 92000000, "name": "Ritrovo",
        "description": "d", "icon": 128205, "expire": 99, "lockedTo": 4660}}), "radio1", NOW)
    assert ev.kind == "waypoint"
    p = ev.payload
    assert (p.id, p.name, p.description, p.icon, p.expire, p.locked_to) == (
        5, "Ritrovo", "d", 128205, 99, 4660)
    assert abs(p.lat - 45.1) < 1e-9 and abs(p.lon - 9.2) < 1e-9


def test_waypoint_zero_coords():
    ev = packet_to_event(_pkt({"portnum": "WAYPOINT_APP", "waypoint": {
        "id": 5, "latitudeI": 0, "longitudeI": 0, "expire": 1}}), "radio1", NOW)
    assert ev.kind == "waypoint" and ev.payload.lat is None and ev.payload.lon is None
    assert ev.payload.expire == 1


def test_packet_to_raw_and_meta():
    from meshlens.rf_convert import packet_to_raw
    p = _pkt({"portnum": "ADMIN_APP", "payload": b"zz"}, hopStart=3, hopLimit=1, wantAck=True)
    assert packet_to_event(p, "r1", NOW) is None
    raw = packet_to_raw(p, "r1", NOW)
    assert raw.status == "unsupported" and raw.source == "rf" and raw.radio_id == "r1"
    assert raw.meta.portnum == "ADMIN_APP" and raw.meta.raw == b"zz" and raw.meta.want_ack
    enc = packet_to_raw({"from": 1, "id": 2, "encrypted": b"abc"}, "r1", NOW)
    assert enc.status == "encrypted" and enc.meta.raw == b"abc" and enc.meta.encrypted
    t = packet_to_event(_pkt({"portnum": "TEXT_MESSAGE_APP", "text": "ciao",
                              "payload": b"ciao"}, hopStart=3, hopLimit=1), "r1", NOW)
    assert t.meta.raw == b"ciao" and t.meta.portnum == "TEXT_MESSAGE_APP"
    assert (t.meta.hop_start, t.meta.hop_limit) == (3, 1)
