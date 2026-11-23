import pytest
from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

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
    assert ev.payload.precision_bits == 13 and ev.gateway_id == "!00000001"
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


def test_environment_telemetry_decoded():
    tel = telemetry_pb2.Telemetry(
        environment_metrics=telemetry_pb2.EnvironmentMetrics(temperature=21.5))
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(67, tel), now=1.0)
    assert ev.kind == "telemetry" and ev.payload.variant == "environment"
    assert ev.payload.metrics == {"temperature": 21.5}


def test_host_metrics_counted_unsupported():
    tel = telemetry_pb2.Telemetry(host_metrics=telemetry_pb2.HostMetrics(uptime_seconds=5))
    d = EnvelopeDecoder([DEFAULT_KEY])
    assert d.decode(T, make_envelope(67, tel), now=1.0) is None
    assert d.stats["unsupported_port"] == 1


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


def _hops_ev(relay_node, from_node=0xa1b2c3d4):
    env = mqtt_pb2.ServiceEnvelope()
    env.ParseFromString(make_envelope(1, b"x", from_node=from_node))
    env.packet.relay_node = relay_node
    return EnvelopeDecoder([DEFAULT_KEY]).decode(T, env.SerializeToString(), now=1.0)


def test_mqtt_hops_direct_when_relay_is_sender_byte():
    # hop_start/hop_limit si ignorano: il broker azzera hop_limit
    ev = _hops_ev(0xd4)
    assert ev.hops == 0 and ev.hops_min is None and ev.relay_node == 0xd4
    assert ev.gateway_num == 1


def test_mqtt_hops_relayed_gives_lower_bound():
    ev = _hops_ev(0x11)
    assert ev.hops is None and ev.hops_min == 1


def test_mqtt_hops_unknown_relay():
    ev = _hops_ev(0)
    assert ev.hops is None and ev.hops_min is None and ev.relay_node == 0


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


def test_custom_channel_key_decodes_and_preloads():
    k = bytes(range(32))
    dec = EnvelopeDecoder([DEFAULT_KEY, k], channel_keys={"Squadra": k})
    assert dec.channel_keys["Squadra"] == k
    raw = make_envelope(portnums_pb2.TEXT_MESSAGE_APP, b"ciao", channel_id="Squadra", key=k)
    ev = dec.decode("msh/EU_868/2/e/Squadra/!00000001", raw, 1.0)
    assert ev is not None and ev.kind == "text" and ev.payload.text == "ciao"
    assert dec.channel_keys["Squadra"] == k


def test_decoded_packet_has_broker():
    dec = EnvelopeDecoder([DEFAULT_KEY], broker="b1")
    raw = make_envelope(portnums_pb2.TEXT_MESSAGE_APP, b"ciao", encrypted=False)
    ev = dec.decode(T, raw, 1.0)
    assert ev is not None and ev.broker == "b1"


def test_set_keys_keeps_learned_and_custom_wins():
    dec = EnvelopeDecoder([DEFAULT_KEY])
    dec.channel_keys["A"], dec.channel_keys["B"] = b"a" * 16, b"b" * 16
    k2 = b"c" * 16
    dec.set_keys([DEFAULT_KEY, k2], {"A": k2})
    assert dec.keys == [DEFAULT_KEY, k2]
    assert dict(dec.channel_keys) == {"A": k2, "B": b"b" * 16}


def test_custom_key_not_in_keys_still_decodes():
    k = bytes(range(1, 33))
    dec = EnvelopeDecoder([DEFAULT_KEY], channel_keys={"Squadra": k})
    raw = make_envelope(portnums_pb2.TEXT_MESSAGE_APP, b"x", channel_id="Squadra", key=k)
    assert dec.decode("msh/EU_868/2/e/Squadra/!00000001", raw, 1.0) is not None


def test_learned_key_never_overwrites_custom():
    k = bytes(range(1, 33))
    dec = EnvelopeDecoder([DEFAULT_KEY], channel_keys={"Squadra": k})
    # pacchetto sul canale personalizzato cifrato con un'altra chiave (hash non verificabile: 0)
    raw = make_envelope(portnums_pb2.TEXT_MESSAGE_APP, b"x", channel_id="Squadra",
                        channel_hash_value=0)
    assert dec.decode("msh/EU_868/2/e/Squadra/!00000001", raw, 1.0) is not None
    assert dec.channel_keys["Squadra"] == k


def test_set_keys_removing_custom_channel_stops_using_its_key():
    k = bytes(range(1, 33))
    dec = EnvelopeDecoder([DEFAULT_KEY], channel_keys={"Squadra": k})
    dec.set_keys([DEFAULT_KEY], {})
    assert "Squadra" not in dec.channel_keys
    raw = make_envelope(portnums_pb2.TEXT_MESSAGE_APP, b"x", channel_id="Squadra", key=k)
    assert dec.decode("msh/EU_868/2/e/Squadra/!00000001", raw, 1.0) is None


def test_text_reply_and_emoji():
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(
        T, make_envelope(1, "👍".encode(), reply_id=42, emoji=1), now=1.0)
    assert ev.kind == "text" and ev.payload.reply_id == 42 and ev.payload.emoji is True
    plain = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(1, b"ciao"), now=1.0)
    assert plain.payload.reply_id is None and plain.payload.emoji is False


def test_waypoint_decoded():
    wp = mesh_pb2.Waypoint(id=7, latitude_i=451000000, longitude_i=92000000,
                           name="Ritrovo", icon=0x1F4CD, expire=0)
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(8, wp), now=1.0)
    assert ev.kind == "waypoint"
    assert ev.payload.id == 7 and ev.payload.name == "Ritrovo"
    assert ev.payload.lat == pytest.approx(45.1) and ev.payload.lon == pytest.approx(9.2)
    assert ev.payload.icon == 0x1F4CD and ev.payload.expire == 0


def test_pki_flag_and_stat():
    dec = EnvelopeDecoder([DEFAULT_KEY])
    ev = dec.decode(T, make_envelope(1, b"dm", encrypted=False, pki=True), now=1.0)
    assert ev.pki is True
    plain = dec.decode(T, make_envelope(1, b"dm", encrypted=False), now=1.0)
    assert plain.pki is False
    # cifrato con una chiave che non abbiamo: non decifrabile
    other = bytes(range(16))
    raw = make_envelope(1, b"dm", key=other, pki=True)
    assert dec.decode(T, raw, now=1.0) is None
    assert dec.stats["pki_encrypted"] == 1 and dec.stats["undecodable"] == 0


def test_meta_filled_for_decrypted_packet():
    d = EnvelopeDecoder([DEFAULT_KEY])
    ev = d.decode(T, make_envelope(1, b"ciao", hop_start=5, hop_limit=2), now=1.0)
    assert ev.meta.portnum == "TEXT_MESSAGE_APP" and ev.meta.encrypted is True
    assert ev.meta.raw == b"ciao" and ev.meta.hop_start == 5 and ev.meta.hop_limit == 2


def test_decode_any_raw_only_with_filter():
    from meshlens.events import RawPacket
    d = EnvelopeDecoder([DEFAULT_KEY])
    payload = make_envelope(1, b"x" * 400, key=bytes(range(16)))
    assert d.decode_any(T, payload, now=1.0) is None
    d.raw_filter = lambda n: True
    raw = d.decode_any(T, payload, now=1.0)
    assert isinstance(raw, RawPacket) and raw.status == "encrypted"
    assert raw.source == "mqtt" and raw.meta.encrypted is True and raw.meta.portnum is None
    assert 0 < len(raw.meta.raw) <= 256
    assert d.stats["undecodable"] == 2
    assert d.decode(T, payload, now=1.0) is None
    d.raw_filter = lambda n: False
    assert d.decode_any(T, payload, now=1.0) is None
    assert d.decode_any("msh/json/x", b"{}", now=1.0) is None
    d.raw_filter = lambda n: True
    assert d.decode_any(T, b"\xff\xff garbage", now=1.0) is None


def test_decode_any_unsupported_has_portnum():
    d = EnvelopeDecoder([DEFAULT_KEY])
    d.raw_filter = lambda n: True
    raw = d.decode_any(T, make_envelope(5, b""), now=1.0)
    assert raw.status == "unsupported" and raw.meta.portnum == "ROUTING_APP"
    assert d.stats["unsupported_port"] == 1
    assert d.decode(T, make_envelope(5, b""), now=1.0) is None


def test_build_raw_does_not_decrypt_twice(monkeypatch):
    calls = []
    d = EnvelopeDecoder([DEFAULT_KEY])
    real = d._extract_data
    monkeypatch.setattr(d, "_extract_data", lambda *a: (calls.append(1), real(*a))[1])
    d.raw_filter = lambda n: True
    payload = make_envelope(1, b"x" * 40, key=bytes(range(16)))
    assert d.decode_any(T, payload, now=1.0).status == "encrypted"
    assert len(calls) == 1  # il pacchetto grezzo riusa l'estrazione di _decode


def test_app_portnums_become_events():
    from meshtastic.protobuf import atak_pb2, paxcount_pb2
    from meshlens.events import AppData, MeshEvent
    pax = paxcount_pb2.Paxcount(wifi=3, ble=5, uptime=60).SerializeToString()
    tak = atak_pb2.TAKPacket(pli=atak_pb2.PLI(latitude_i=450000000, longitude_i=90000000)
                             ).SerializeToString()
    for port, raw, kind in ((10, b"Porta detected", "detection"), (34, pax, "paxcounter"),
                            (72, tak, "tak")):
        ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(port, raw), now=1.0)
        assert isinstance(ev, MeshEvent) and ev.kind == kind
        assert isinstance(ev.payload, AppData)
        assert ev.payload.portnum == port and ev.payload.payload == raw
        assert ev.payload.text == ("Porta detected" if port == 10 else None)


def test_atak_v2_still_unsupported():
    d = EnvelopeDecoder([DEFAULT_KEY])
    assert d.decode(T, make_envelope(78, b"x"), now=1.0) is None
    assert d.stats["unsupported_port"] == 1
    d.raw_filter = lambda n: True
    raw = d.decode_any(T, make_envelope(78, b"x"), now=1.0)
    assert raw.status == "unsupported"



def test_garbage_app_payloads_decode_without_errors():
    for port in (10, 34, 72):
        ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(port, b"\xff\xfe\x00\x80"),
                                                   now=1.0)
        assert ev is not None and ev.payload.payload == b"\xff\xfe\x00\x80"
        if port == 10:
            assert "\ufffd" in ev.payload.text
