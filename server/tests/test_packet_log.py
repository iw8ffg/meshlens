import json

import pytest

from meshlens import packet_log as pl
from meshlens.db import connect
from meshlens.events import MeshEvent, NodeInfoData, PacketMeta, RawPacket, TextData
from meshlens.packet_log import PacketLog, summarize
from meshlens.store import Store

NOW = 1_800_000_000.0


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t


def _meta(raw=b"\x01\x02\x03"):
    return PacketMeta(portnum="TEXT_MESSAGE_APP", hop_start=3, hop_limit=1, raw=raw)


def ev(pid=1, num=0xA1, gateway="!gw1", snr=-5.0, t=NOW, **kw):
    d = dict(source="mqtt", from_node=num, to_node=0xFFFFFFFF, packet_id=pid, channel="LongFast",
             rx_time=t, snr=snr, rssi=None, hops=2, gateway_id=gateway, radio_id=None,
             kind="text", payload=TextData("ciao"), broker="b1", meta=_meta())
    d.update(kw)
    return MeshEvent(**d)


def raw_packet(pid=7, num=0xB2, status="encrypted", raw=b"\xff" * 256, t=NOW):
    return RawPacket(source="mqtt", from_node=num, to_node=0xFFFFFFFF, packet_id=pid,
                     channel="LongFast", rx_time=t, snr=-9.0, rssi=None, gateway_id="!gw",
                     radio_id=None, broker="b1", relay_node=None, status=status,
                     meta=PacketMeta(portnum=None, hop_start=3, hop_limit=2, encrypted=True,
                                     raw=raw))


@pytest.fixture
def env():
    conn = connect(":memory:")
    store = Store(conn)
    mode = {"v": "all"}
    clock = Clock()
    log = PacketLog(store, lambda: mode["v"], clock=clock)
    return log, conn, mode, clock


def rows(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM packets ORDER BY id")]


def test_new_and_dup_merge_into_one_row(env):
    log, conn, _, _ = env
    log.observe(ev(gateway="!gw1"), "new", True)
    log.observe(ev(gateway="!gw2", snr=-7.0), "dup", True)
    log.observe(ev(gateway="!gw3", snr=None), "dup", True)
    assert log.flush(NOW + 6) == 1
    (r,) = rows(conn)
    assert r["copies"] == 3
    recs = json.loads(r["receptions"])
    assert [x["gateway"] for x in recs] == ["!gw1", "!gw2", "!gw3"]
    assert r["status"] == "ok" and r["kind"] == "text"
    assert r["portnum"] == "TEXT_MESSAGE_APP" and r["hop_start"] == 3 and r["hop_limit"] == 1
    assert r["raw"] == b"\x01\x02\x03" and r["size"] == 3
    assert json.loads(r["summary"]) == {"text": "ciao", "reply_id": None, "emoji": False}
    assert r["from_num"] == 0xA1 and r["gateway"] == "!gw1" and r["snr"] == -5.0


def test_late_dup_ignored(env):
    log, conn, _, _ = env
    log.observe(ev(), "new", True)
    log.flush(NOW + 6)
    log.observe(ev(gateway="!late"), "dup", True)
    assert log.flush(NOW + 60, force=True) == 0
    assert len(rows(conn)) == 1


def test_hold_window(env):
    log, conn, _, _ = env
    log.observe(ev(), "new", True)
    assert log.flush(NOW + 1) == 0
    assert rows(conn) == []
    assert log.flush(NOW + 6) == 1


def test_modes(env):
    log, conn, mode, _ = env
    mode["v"] = "off"
    log.observe(ev(pid=1), "new", True)
    mode["v"] = "archived"
    log.observe(ev(pid=2), "new", False)
    assert log.flush(force=True) == 0
    mode["v"] = "all"
    log.observe(ev(pid=3), "new", False)
    assert log.flush(force=True) == 1
    assert [r["packet_id"] for r in rows(conn)] == [3]


def test_ignored_outcome_and_replayed_skipped(env):
    log, conn, _, _ = env
    log.observe(ev(pid=1), "ignored", True)
    log.observe(ev(pid=2, replayed=True), "new", True)
    assert log.flush(force=True) == 0


def test_raw_packet_row(env):
    log, conn, _, _ = env
    log.observe_raw(raw_packet(raw=b"\xff" * 300), True)
    log.observe_raw(raw_packet(), True)  # stessa chiave: solo una ricezione in piu'
    assert log.flush(force=True) == 1
    (r,) = rows(conn)
    assert r["status"] == "encrypted" and r["kind"] is None
    assert len(r["raw"]) <= 256 and r["size"] == len(r["raw"])
    assert r["hops"] is None and r["summary"] is None  # MQTT: hop_limit non attendibile
    assert len(json.loads(r["receptions"])) == 2


def test_flush_max_per_call(env):
    log, conn, _, _ = env
    for i in range(2500):
        log.observe(ev(pid=i + 1), "new", True)
    assert log.flush(NOW + 6) == 2000
    assert log.flush(NOW + 6) == 500
    assert len(rows(conn)) == 2500


def test_force_flush_writes_everything(env):
    log, conn, _, _ = env
    for i in range(2500):
        log.observe(ev(pid=i + 1), "new", True)
    assert log.flush(force=True) == 2500


def test_buffer_overflow_drops_oldest(env, monkeypatch):
    monkeypatch.setattr(pl, "BUFFER_MAX", 10)
    log, conn, _, _ = env
    for i in range(12):
        log.observe(ev(pid=i + 1), "new", True)
    assert log.dropped == 2
    log.flush(force=True)
    assert [r["packet_id"] for r in rows(conn)] == list(range(3, 13))


def test_receptions_capped(env):
    log, conn, _, _ = env
    log.observe(ev(), "new", True)
    for i in range(20):
        log.observe(ev(gateway=f"!g{i}"), "dup", True)
    log.flush(force=True)
    (r,) = rows(conn)
    assert r["copies"] == 21
    assert len(json.loads(r["receptions"])) == pl.MAX_RECEPTIONS


def test_skips_nodedb_replay(env):
    log, conn, _, _ = env
    log.observe(ev(pid=0), "new", True)
    log.observe(ev(pid=5, t=0), "new", True)
    log.observe_raw(raw_packet(pid=0), True)
    assert log.flush(force=True) == 0
    assert rows(conn) == []


def test_summarize_hex_bytes_and_cut_text():
    s = summarize(ev(payload=TextData("x" * 500)))
    assert len(s["text"]) == 200
    n = summarize(ev(kind="nodeinfo", payload=NodeInfoData("L", "S", "HW", "CLIENT", b"\x0a\xff")))
    assert n["public_key"] == "0aff"
    json.dumps(n)


def test_raw_mqtt_hops_follow_relay_rule(env):
    log, conn, _, _ = env
    direct = raw_packet(pid=1, num=0xB2)
    direct.relay_node = 0xB2  # relay == from & 0xFF: ricezione diretta
    log.observe_raw(direct, True)
    relayed = raw_packet(pid=2, num=0xB2)  # hop_start 3, hop_limit 2: ma il broker li azzera
    relayed.relay_node = 0x11
    log.observe_raw(relayed, True)
    log.observe_raw(raw_packet(pid=3), True)  # relay sconosciuto
    rf = raw_packet(pid=4)
    rf.source = "rf"
    log.observe_raw(rf, True)
    log.flush(force=True)
    assert [r["hops"] for r in rows(conn)] == [0, None, None, 1]
    assert json.loads(rows(conn)[0]["receptions"])[0]["hops"] == 0
