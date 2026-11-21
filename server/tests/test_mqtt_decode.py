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
    assert d.decode(T, make_envelope(5, b""), now=1.0) is None and d.stats["unsupported_port"] == 1


def test_ok_is_counted():
    d = EnvelopeDecoder([DEFAULT_KEY])
    d.decode(T, make_envelope(1, b"x"), now=1.0)
    assert d.stats["ok"] == 1


def test_channel_hash_longfast_default_key_is_8():
    from helpers import channel_hash
    assert channel_hash("LongFast", DEFAULT_KEY) == 8
    env = mqtt_pb2.ServiceEnvelope.FromString(make_envelope(1, b"x"))
    assert env.packet.channel == 8


def test_wrong_key_wrong_hash_not_decoded_with_default_key():
    # con un testo qualsiasi: il hash del canale non coincide, la chiave non va nemmeno provata
    other = bytes(range(16))
    d = EnvelopeDecoder([DEFAULT_KEY])
    raw = make_envelope(1, b"x", key=other, channel_id="Privato")
    assert d.decode(T, raw, now=1.0) is None
    assert d.stats["undecodable"] == 1


def test_hash_mismatch_skips_key_even_if_plaintext_would_parse():
    d = EnvelopeDecoder([DEFAULT_KEY])
    raw = make_envelope(1, b"ciao", channel_hash_value=99)  # cifrato con la chiave giusta
    assert d.decode(T, raw, now=1.0) is None


def test_channel_zero_means_unknown_and_still_tries():
    d = EnvelopeDecoder([DEFAULT_KEY])
    ev = d.decode(T, make_envelope(1, b"ciao", channel_hash_value=0), now=1.0)
    assert ev is not None and ev.kind == "text"


@pytest.mark.parametrize("lat,lon", [(917000000, 0), (-917000000, 10), (10, 1801000000),
                                     (10, -1801000000)])
def test_out_of_range_position_is_empty(lat, lon):
    d = EnvelopeDecoder([DEFAULT_KEY])
    pos = mesh_pb2.Position(latitude_i=lat, longitude_i=lon)
    assert d.decode(T, make_envelope(3, pos), now=1.0) is None
    assert d.stats["empty"] == 1


def test_out_of_range_mapreport_position_is_empty():
    d = EnvelopeDecoder([DEFAULT_KEY])
    mr = mqtt_pb2.MapReport(latitude_i=917000000, longitude_i=1)
    ev = d.decode("msh/EU_868/2/map/", make_envelope(73, mr, encrypted=False), now=1.0)
    assert ev is None and d.stats["empty"] == 1


def test_invalid_utf8_text_is_undecodable():
    d = EnvelopeDecoder([DEFAULT_KEY])
    assert d.decode(T, make_envelope(1, b"\xff\xfe\xfa"), now=1.0) is None
    assert d.stats["undecodable"] == 1


def test_hops_never_negative():
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(
        T, make_envelope(1, b"x", hop_start=1, hop_limit=3), now=1.0)
    assert ev.hops == 0


def test_mqtt_neighborinfo_decoded():
    info = mesh_pb2.NeighborInfo(node_id=3, neighbors=[
        mesh_pb2.Neighbor(node_id=5, snr=6.5), mesh_pb2.Neighbor(node_id=6, snr=-3.0)])
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(71, info), now=1.0)
    assert ev.kind == "neighbors"
    assert ev.payload.neighbors == [(5, 6.5), (6, -3.0)]


def test_mqtt_traceroute_decoded_snr_scaled():
    from meshtastic.protobuf import portnums_pb2
    rd = mesh_pb2.RouteDiscovery(route=[0x0b], snr_towards=[24, -128], snr_back=[-8])
    data = mesh_pb2.Data(portnum=portnums_pb2.TRACEROUTE_APP, payload=rd.SerializeToString(),
                         request_id=77)
    from meshlens import mqtt_decode
    ev = mqtt_decode._parse_route(data)
    assert ev.snr_towards == [6.0, None] and ev.snr_back == [-2.0]
    assert ev.route == [0x0b] and ev.route_back == [] and ev.request_id == 77
    # e dalla busta completa
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(70, rd), now=1.0)
    assert ev.kind == "traceroute" and ev.payload.snr_towards == [6.0, None]
    assert ev.payload.request_id is None
