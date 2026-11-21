import pytest

from meshlens.bus import Bus
from meshlens.coverage import (CoverageRecorder, SessionActive, haversine_m, interpolate_position,
                               missing_points, precision_m, summarize)
from meshlens.db import connect
from meshlens.events import MeshEvent, PositionData, RangeTestData
from meshlens.live import LiveState
from meshlens.store import Store

MOBILE = 0xA1B2C3D4
T0 = 1_800_000_000.0


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def rt(seq, t, node=MOBILE, radio="r1", source="rf", snr=-5.0, text=None):
    return MeshEvent(source, node, 0xFFFFFFFF, 1, "LongFast", t, snr, -90, 1, None, radio,
                     "rangetest", RangeTestData(seq, text or f"seq {seq}"))


def pos(t, lat=45.0, lon=11.0, node=MOBILE, radio="r1", source="rf", bits=32):
    return MeshEvent(source, node, 0xFFFFFFFF, 2, "LongFast", t, None, None, 0, None, radio,
                     "position", PositionData(lat, lon, None, bits, None))


@pytest.fixture
def env():
    store = Store(connect(":memory:"))
    live = LiveState()
    bus = Bus()
    q = bus.subscribe()
    clock = Clock()
    rec = CoverageRecorder(store, live, bus, clock)
    rec.start()
    return rec, store, live, q, clock


def begin(rec, mode="rangetest", **kw):
    return rec.start_session("r1", MOBILE, mode, 30, "T", kw.get("base_lat", 45.0),
                             kw.get("base_lon", 11.0), None)


def test_precision_and_haversine():
    assert precision_m(None) is None and precision_m(32) is None
    assert precision_m(16) == round(2 ** 16 * 1e-7 * 111320 / 2)
    assert haversine_m(45.0, 11.0, 45.0, 11.0) == 0
    assert haversine_m(45.0, 11.0, 46.0, 11.0) == pytest.approx(111195, rel=1e-3)


def test_interpolate_between_and_nearest_and_none():
    track = [{"time": 0, "lat": 45.0, "lon": 11.0, "precision_bits": 32},
             {"time": 100, "lat": 45.1, "lon": 11.0, "precision_bits": 16}]
    lat, lon, bits = interpolate_position(track, 50)
    assert (lat, lon, bits) == (pytest.approx(45.05), pytest.approx(11.0), 16)
    one = track[:1]
    assert interpolate_position(one, 90)[:2] == (45.0, 11.0)
    assert interpolate_position(one, 500) is None
    assert interpolate_position([], 5) is None


def test_missing_points_per_segment():
    pts = [{"segment": 0, "seq": s, "time": t} for s, t in [(0, 0), (1, 30), (4, 120)]]
    pts += [{"segment": 1, "seq": s, "time": 1000 + s * 30} for s in (0, 1)]
    track = [{"time": 0, "lat": 45.0, "lon": 11.0, "precision_bits": None}]
    miss = missing_points(pts, 30, track)
    assert [(m["seq"], m["time"]) for m in miss] == [(2, 60), (3, 90)]
    assert miss[0]["lat"] == 45.0
    session = {"mode": "rangetest", "mobile_num": MOBILE, "base_lat": None, "base_lon": None}
    s = summarize(session, [p | {"snr": None, "lat": None, "lon": None, "precision_bits": None}
                            for p in pts[:3]], miss)
    assert (s["received"], s["missing"], s["expected"], s["loss_pct"]) == (3, 2, 5, 40.0)
    assert s["max_distance_m"] is None and s["mobile_id"] == "!a1b2c3d4"


def test_summarize_position_mode_has_no_loss():
    session = {"mode": "position", "mobile_num": MOBILE, "base_lat": 45.0, "base_lon": 11.0}
    pts = [{"segment": 0, "seq": None, "time": 1, "snr": -3.0, "lat": 45.0, "lon": 11.1,
            "precision_bits": 16}]
    s = summarize(session, pts, [])
    assert s["expected"] is None and s["missing"] is None and s["loss_pct"] is None
    assert s["max_distance_m"] > 7000 and s["approx_precision_m"] == precision_m(16)
    assert s["best_snr"] == s["worst_snr"] == -3.0


def test_recorder_ignores_other_nodes_and_radios(env):
    rec, store, *_ = env
    sid = begin(rec)["id"]
    rec.handle(pos(T0))
    rec.handle(rt(0, T0 + 1, node=0x1234))
    rec.handle(rt(0, T0 + 1, radio="r2"))
    rec.handle(rt(0, T0 + 1, source="mqtt"))
    rec.handle(rt(None, T0 + 1, text="boh"))
    assert store.points(sid) == []
    rec.handle(rt(0, T0 + 2))
    assert len(store.points(sid)) == 1


def test_recorder_duplicate_seq_keeps_best_snr_and_publishes_once(env):
    rec, store, _, q, _ = env
    sid = begin(rec)["id"]
    rec.handle(pos(T0))
    rec.handle(rt(0, T0 + 1, snr=-8.0))
    rec.handle(rt(0, T0 + 2, snr=-2.0))
    pts = store.points(sid)
    assert len(pts) == 1 and pts[0]["snr"] == -2.0
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    assert sum(1 for m in msgs if m["type"] == "coverage" and m["point"]) == 1


def test_recorder_new_segment_on_seq_drop(env):
    rec, store, *_ = env
    sid = begin(rec)["id"]
    for i, s in enumerate((0, 1, 2, 0, 1)):
        rec.handle(rt(s, T0 + i))
    assert [(p["segment"], p["seq"]) for p in store.points(sid)] == [
        (0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]
    d = rec.detail(sid)
    assert d["missing"] == 0 and d["loss_pct"] == 0.0


def test_point_without_position_then_backfilled(env):
    rec, store, _, q, _ = env
    sid = begin(rec)["id"]
    rec.handle(rt(0, T0 + 100))
    assert store.points(sid)[0]["lat"] is None
    while not q.empty():
        q.get_nowait()
    rec.handle(pos(T0 + 110, 45.2, 11.2))
    p = store.points(sid)[0]
    assert (p["lat"], p["lon"]) == (45.2, 11.2)
    msg = q.get_nowait()
    assert msg["type"] == "coverage" and msg["point"]["id"] == p["id"]
    assert msg["point"]["segment"] == 0 and msg["point"]["lat"] == 45.2
    assert msg["point"]["distance_m"] > 0 and msg["session"]["id"] == sid
    assert rec.detail(sid)["points"][0]["id"] == p["id"]


def test_backfill_refines_nearest_to_interpolated_and_dedups_track(env):
    rec, store, *_ = env
    sid = begin(rec)["id"]
    rec.handle(pos(T0, 45.0, 11.0))
    rec.handle(rt(0, T0 + 50))
    assert store.points(sid)[0]["lat"] == 45.0  # solo la piu' vicina
    rec.handle(pos(T0 + 100, 45.1, 11.0))
    rec.handle(pos(T0 + 100, 45.1, 11.0, source="mqtt"))
    assert store.points(sid)[0]["lat"] == pytest.approx(45.05)
    assert len(store.track(sid)) == 2


def test_point_without_any_position_counts_but_null(env):
    rec, _, *_ = env
    sid = begin(rec)["id"]
    rec.handle(rt(0, T0 + 100))
    d = rec.detail(sid)
    assert d["received"] == 1 and d["points"][0]["lat"] is None
    assert d["points"][0]["distance_m"] is None


def test_position_mode_records_positions_as_points(env):
    rec, store, *_ = env
    sid = begin(rec, "position")["id"]
    rec.handle(pos(T0, 45.0, 11.0))
    rec.handle(pos(T0 + 5, 45.0, 11.0, source="mqtt"))  # solo percorso
    assert len(store.points(sid)) == 1 and len(store.track(sid)) == 2
    assert rec.detail(sid)["missing_points"] == []


def test_session_auto_stops_after_8h(env):
    rec, store, _, _, clock = env
    sid = begin(rec)["id"]
    clock.t += 8 * 3600 - 1
    rec.tick()
    assert store.get_session(sid)["ended"] is None
    clock.t += 2
    rec.tick()
    s = store.get_session(sid)
    assert s["end_reason"] == "timeout" and s["ended"] is not None
    assert rec.stop_session() is None


def test_active_session_resumes_after_restart(env):
    rec, store, live, _, clock = env
    sid = begin(rec)["id"]
    rec.handle(pos(T0))
    for i, s in enumerate((0, 1, 0, 1)):
        rec.handle(rt(s, T0 + i))
    rec2 = CoverageRecorder(store, live, Bus(), clock)
    rec2.start()
    rec2.handle(rt(2, T0 + 10))
    assert [(p["segment"], p["seq"]) for p in store.points(sid)][-1] == (1, 2)
    assert rec2.detail(sid)["points"][-1]["lat"] == 45.0


def test_start_session_base_from_radio_node_and_single_active(env):
    rec, store, live, *_ = env
    rec = CoverageRecorder(store, live, Bus(), radio_node=lambda rid: 0x99)
    live.nodes[0x99] = {"lat": 44.0, "lon": 10.0}
    s = rec.start_session("r1", MOBILE, "rangetest", 30, None, None, None, 0)
    assert (s["base_lat"], s["base_lon"]) == (44.0, 10.0) and s["name"].startswith("Prova ")
    with pytest.raises(SessionActive):
        begin(rec)
    assert rec.stop_session()["end_reason"] == "manual"


def test_rangetest_age_tracked_outside_session(env):
    rec, _, _, _, clock = env
    assert rec.rangetest_age("r1", MOBILE) is None
    rec.handle(rt(None, T0 - 30, text="rotto"))
    assert rec.rangetest_age("r1", MOBILE) == 30
    assert rec.rangetest_age("r2", MOBILE) is None
