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


# ---- servizio ----
import time  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from meshlens import db  # noqa: E402
from meshlens.events import AppData, MeshEvent  # noqa: E402
from meshlens.ext_map import install  # noqa: E402
from meshlens.tak import TakService  # noqa: E402

NUM = 0xAABBCCDD


def make_ev(payload=None, rx=1000.0, kind="tak", source="rf", replayed=False, port=72):
    pl = make_packet(**FULL) if payload is None else payload
    return MeshEvent(source=source, from_node=NUM, to_node=0xFFFFFFFF, packet_id=1, channel="c",
                     rx_time=rx, snr=None, rssi=None, hops=None, gateway_id=None, radio_id="r1",
                     kind=kind, payload=AppData(portnum=port, payload=pl), replayed=replayed)


class Env:
    def __init__(self, persists=True, node=True):
        self.conn = db.connect(":memory:")
        self.events = []
        self.svc = TakService(self.conn, self.events.append, lambda n, s: persists,
                              (lambda num: {"country": "IT"} if node else None),
                              now=lambda: 5000.0)

    def rows(self):
        return self.conn.execute("SELECT * FROM tak_contacts").fetchall()


def test_new_pli_creates_contact_and_publishes():
    e = Env()
    e.svc.on_event(make_ev(), "new")
    rows = e.rows()
    assert len(rows) == 1
    r = e.conn.execute("SELECT callsign, compressed, time FROM tak_contacts").fetchone()
    assert tuple(r) == ("ALPHA-1", 0, 1000.0)
    assert len(e.events) == 1 and e.events[0]["type"] == "tak_contact"
    c = e.events[0]["contact"]
    assert c["node_id"] == "!aabbccdd" and c["compressed"] is False


def test_dup_or_replayed_or_ignored_outcome_not_stored():
    e = Env()
    e.svc.on_event(make_ev(), "dup")
    e.svc.on_event(make_ev(), "ignored")
    e.svc.on_event(make_ev(replayed=True), "new")
    assert e.rows() == [] and e.events == []


def test_not_persisted_node_skipped():
    e = Env(persists=False)
    e.svc.on_event(make_ev(), "new")
    assert e.rows() == []


def test_unknown_node_skipped():
    e = Env(node=False)
    e.svc.on_event(make_ev(), "new")
    assert e.rows() == []


def test_older_pli_does_not_overwrite():
    e = Env()
    e.svc.on_event(make_ev(rx=2000.0), "new")
    e.svc.on_event(make_ev(make_packet(**{**FULL, "callsign": "OLD"}), rx=1000.0), "new")
    assert e.conn.execute("SELECT callsign, time FROM tak_contacts").fetchone()[:] == ("ALPHA-1", 2000.0)
    assert len(e.events) == 1


def test_compressed_packet_keeps_previous_callsign():
    e = Env()
    e.svc.on_event(make_ev(rx=1000.0), "new")
    e.svc.on_event(make_ev(make_packet(compressed=True, **{k: v for k, v in FULL.items()
                                                           if k not in ("callsign", "device")}),
                           rx=2000.0), "new")
    r = e.conn.execute("SELECT callsign, compressed, time FROM tak_contacts").fetchone()
    assert tuple(r) == ("ALPHA-1", 1, 2000.0)


def test_non_pli_ignored():
    e = Env()
    e.svc.on_event(make_ev(make_packet(chat=True)), "new")
    assert e.rows() == []


def test_future_time_is_clamped():
    e = Env()
    e.svc.on_event(make_ev(rx=5000.0 + 10 ** 6), "new")
    assert e.conn.execute("SELECT time FROM tak_contacts").fetchone()[0] <= 5300.0


def test_garbage_payload_does_not_raise():
    e = Env()
    e.svc.on_event(make_ev(b"\xff\xff"), "new")
    assert e.rows() == []


def test_non_tak_event_ignored():
    e = Env()
    e.svc.on_event(make_ev(kind="text"), "new")
    assert e.rows() == []


def test_contacts_orders_by_time_desc_and_filters_since():
    e = Env()
    for num, t in ((1, 100.0), (2, 300.0), (3, 200.0)):
        e.conn.execute("INSERT INTO tak_contacts(node_num, time, source) VALUES(?,?,'rf')", (num, t))
    got = e.svc.contacts(since=150.0)
    assert [c["time"] for c in got] == [300.0, 200.0]


def test_install_registers_hook_and_ext():
    hooks = []
    conn = db.connect(":memory:")
    rt = SimpleNamespace(add_event_hook=hooks.append,
                         ingestor=SimpleNamespace(persists=lambda n, s: True))
    ctx = SimpleNamespace(store=SimpleNamespace(conn=conn), bus=SimpleNamespace(publish=print),
                          live=SimpleNamespace(nodes={}, is_ignored=lambda n: False), ext={})
    install(rt, ctx)
    assert isinstance(ctx.ext["tak"], TakService)
    assert hooks == [ctx.ext["tak"].on_event]
    assert time.time() > 0


def test_ignored_node_contact_saved_but_not_broadcast():
    e = Env()
    e.svc.is_ignored = lambda n: True
    e.svc.on_event(make_ev(), "new")
    assert len(e.rows()) == 1 and e.events == []


def test_pli_without_fix_keeps_old_time():
    e = Env()
    e.svc.on_event(make_ev(rx=1000.0), "new")
    nofix = {k: v for k, v in FULL.items() if k not in ("lat", "lon")}
    e.svc.on_event(make_ev(make_packet(**nofix), rx=3000.0), "new")
    r = e.conn.execute("SELECT lat, time FROM tak_contacts").fetchone()
    assert r["lat"] is not None and r["time"] == 1000.0
