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
    assert ev.payload == TelemetryData(battery_level=80, voltage=4.1, uptime_seconds=60)


def test_telemetry_without_device_metrics():
    assert packet_to_event(_pkt({"portnum": "TELEMETRY_APP", "telemetry": {
        "environmentMetrics": {"temperature": 20}}}), "r", NOW) is None


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
    assert all(e.rx_time == NOW for e in evs if e.from_node == 2)
    pos = next(e for e in first if e.kind == "position")
    assert pos.payload.time == 400
    assert next(e for e in first if e.kind == "nodeinfo").payload.role == "ROUTER"
