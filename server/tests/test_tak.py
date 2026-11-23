import random

import pytest
from meshtastic.protobuf import atak_pb2

from meshlens.tak import _wire_fields, parse_tak


def make_packet(**kw) -> bytes:
    p = atak_pb2.TAKPacket()
    if kw.get("compressed"):
        p.is_compressed = True
    if "callsign" in kw or "device" in kw:
        p.contact.callsign = kw.get("callsign", "")
        p.contact.device_callsign = kw.get("device", "")
    if "role" in kw or "team" in kw:
        p.group.role = kw.get("role", 0)
        p.group.team = kw.get("team", 0)
    if "battery" in kw:
        p.status.battery = kw["battery"]
    if "lat" in kw or "lon" in kw or "alt" in kw:
        p.pli.latitude_i = kw.get("lat", 0)
        p.pli.longitude_i = kw.get("lon", 0)
        p.pli.altitude = kw.get("alt", 0)
        p.pli.speed = kw.get("speed", 0)
        p.pli.course = kw.get("course", 0)
    if kw.get("chat"):
        p.chat.message = "ciao"
    return p.SerializeToString()


FULL = dict(callsign="ALPHA-1", device="dev", role=2, team=10, battery=87,
            lat=457000000, lon=95000000, alt=120, speed=3, course=270)


def test_parse_pli_uncompressed():
    r = parse_tak(make_packet(**FULL))
    assert (r.compressed, r.callsign, r.device_callsign, r.team, r.role, r.battery) == \
        (False, "ALPHA-1", "dev", "Cyan", "TeamLead", 87)
    assert r.lat == pytest.approx(45.7) and r.lon == pytest.approx(9.5)
    assert (r.altitude, r.speed, r.course, r.has_pli, r.fallback) == (120, 3, 270, True, False)


def test_compressed_hides_texts():
    r = parse_tak(make_packet(compressed=True, **FULL))
    assert r.compressed and r.callsign is None and r.device_callsign is None
    assert r.team == "Cyan" and r.battery == 87 and r.lat == pytest.approx(45.7)


def test_compressed_invalid_utf8_uses_fallback():
    ref = atak_pb2.TAKPacket()
    ref.group.role, ref.group.team = 2, 10
    ref.status.battery = 87
    ref.pli.latitude_i, ref.pli.longitude_i = 457000000, 95000000
    group, status, pli = (m.SerializeToString() for m in (ref.group, ref.status, ref.pli))
    data = (b"\x08\x01" + b"\x12\x04\x0a\x02\xff\xfe"
            + b"\x1a" + bytes([len(group)]) + group
            + b"\x22" + bytes([len(status)]) + status
            + b"\x2a" + bytes([len(pli)]) + pli)
    with pytest.raises(Exception):
        atak_pb2.TAKPacket.FromString(data)
    r = parse_tak(data)
    assert r.fallback is True and r.compressed is True and r.callsign is None
    assert r.lat == pytest.approx(45.7) and r.team == "Cyan" and r.battery == 87


def test_unspecified_enums_become_none():
    r = parse_tak(make_packet(role=0, team=0, lat=1, lon=1))
    assert r.role is None and r.team is None


def test_zero_position_has_no_fix():
    r = parse_tak(make_packet(lat=0, lon=0, alt=55))
    assert r.has_pli and r.lat is None and r.lon is None and r.altitude is None


def test_out_of_range_position():
    assert parse_tak(make_packet(lat=950000000, lon=1)).lat is None


def test_battery_out_of_range_is_none():
    assert parse_tak(make_packet(battery=250, lat=1, lon=1)).battery is None


def test_chat_only_returns_none():
    assert parse_tak(make_packet(chat=True)) is None


def test_garbage_returns_none_without_raising():
    for blob in (b"", b"\xff\xff\xff", random.Random(1).randbytes(64), b"\x01" * 5000):
        assert parse_tak(blob) is None


def test_callsign_cleaned():
    assert parse_tak(make_packet(callsign="  A\x07B  ", lat=1, lon=1)).callsign == "AB"
    assert len(parse_tak(make_packet(callsign="x" * 200, lat=1, lon=1)).callsign) == 64


def test_wire_fields_stops_on_truncated_data():
    assert list(_wire_fields(b"\x0a\x05ab")) == []
    assert list(_wire_fields(b"\x08\x01")) == [(1, 0, 1)]
