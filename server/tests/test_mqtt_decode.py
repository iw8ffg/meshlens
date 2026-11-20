import pytest
from meshtastic.protobuf import mesh_pb2, mqtt_pb2, telemetry_pb2

from helpers import make_envelope
from meshlens.crypto import DEFAULT_KEY
from meshlens.events import node_id
from meshlens.mqtt_decode import EnvelopeDecoder

T = "msh/EU_868/2/e/LongFast/!00000001"


def test_position_decoded():
    pos = mesh_pb2.Position(latitude_i=454642000, longitude_i=91900000, precision_bits=13)
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(3, pos), now=1000.0)
    assert ev.kind == "position" and ev.source == "mqtt"
    assert ev.payload.lat == pytest.approx(45.4642) and ev.payload.lon == pytest.approx(9.19)
    assert ev.payload.precision_bits == 13 and ev.hops == 2 and ev.gateway_id == "!00000001"
    assert node_id(ev.from_node) == "!a1b2c3d4"
    assert ev.rx_time == 1000.0 and ev.channel == "LongFast" and ev.snr == -5.0


def test_zero_position_has_no_coordinates():
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(3, mesh_pb2.Position()), now=1.0)
    assert ev is None  # posizione vuota = nessun evento


def test_text_is_not_transformed():
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(1, b"ciao <b>x</b>"), now=1.0)
    assert ev.kind == "text" and ev.payload.text == "ciao <b>x</b>"


def test_nodeinfo_decoded():
    user = mesh_pb2.User(long_name="Base", short_name="BS", hw_model=mesh_pb2.HardwareModel.HELTEC_V3)
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(4, user), now=1.0)
    assert ev.kind == "nodeinfo"
    assert ev.payload.long_name == "Base" and ev.payload.short_name == "BS"
    assert ev.payload.hw_model == "HELTEC_V3" and ev.payload.role == "CLIENT"


def test_telemetry_decoded():
    tel = telemetry_pb2.Telemetry(
        device_metrics=telemetry_pb2.DeviceMetrics(battery_level=87, voltage=4.01))
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(67, tel), now=1.0)
    assert ev.kind == "telemetry"
    assert ev.payload.battery_level == 87 and ev.payload.voltage == pytest.approx(4.01)
    assert ev.payload.air_util_tx is None


def test_mapreport_decoded_from_plain_packet():
    mr = mqtt_pb2.MapReport(long_name="Mappa", short_name="MP", firmware_version="2.5.0",
                            latitude_i=454642000, longitude_i=91900000, position_precision=14,
                            num_online_local_nodes=4)
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(
        "msh/EU_868/2/map/", make_envelope(73, mr, encrypted=False), now=1.0)
    assert ev.kind == "mapreport"
    assert ev.payload.lat == pytest.approx(45.4642) and ev.payload.lon == pytest.approx(9.19)
    assert ev.payload.firmware_version == "2.5.0" and ev.payload.precision_bits == 14
    assert ev.payload.num_online_local_nodes == 4


def test_mapreport_without_position_has_none_coordinates():
    mr = mqtt_pb2.MapReport(long_name="Mappa", firmware_version="2.5.0")
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(
        "msh/EU_868/2/map/", make_envelope(73, mr, encrypted=False), now=1.0)
    assert ev.payload.lat is None and ev.payload.lon is None


def test_second_key_is_tried():
    k2 = bytes(range(16))
    ev = EnvelopeDecoder([DEFAULT_KEY, k2]).decode(T, make_envelope(1, b"x", key=k2), now=1.0)
    assert ev.kind == "text"


def test_empty_key_is_skipped_not_raised():
    ev = EnvelopeDecoder([b"", DEFAULT_KEY]).decode(T, make_envelope(1, b"x"), now=1.0)
    assert ev.kind == "text"


@pytest.mark.parametrize("topic,payload,stat", [
    ("msh/EU_868/2/json/LongFast/!1", b'{"a":1}', "json_topic"),
    ("msh/EU_868/2/stat/!1", b"online", "not_protobuf"),
    (T, b"\xff\xff\xff", "not_protobuf"),
])
def test_garbage_is_counted_not_raised(topic, payload, stat):
    d = EnvelopeDecoder([DEFAULT_KEY])
    assert d.decode(topic, payload, now=1.0) is None and d.stats[stat] == 1


def test_unknown_key_counted_undecodable():
    d = EnvelopeDecoder([DEFAULT_KEY])
    assert d.decode(T, make_envelope(1, b"x", key=bytes(range(16))), now=1.0) is None
    assert d.stats["undecodable"] == 1


def test_unsupported_port_counted():
    d = EnvelopeDecoder([DEFAULT_KEY])
    assert d.decode(T, make_envelope(70, b""), now=1.0) is None and d.stats["unsupported_port"] == 1


def test_ok_is_counted():
    d = EnvelopeDecoder([DEFAULT_KEY])
    d.decode(T, make_envelope(1, b"x"), now=1.0)
    assert d.stats["ok"] == 1
