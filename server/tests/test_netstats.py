from meshlens.db import connect
from meshlens.events import MeshEvent, TextData
from meshlens.netstats import NetStats
from meshlens.store import Store

NOW = 1_800_000_000.0  # multiplo di 3600
HOUR = 3600


def ev(pid=1, num=0xA1, snr=-5.0, t=NOW + 10, source="mqtt", **kw):
    d = dict(source=source, from_node=num, to_node=0xFFFFFFFF, packet_id=pid, channel="LongFast",
             rx_time=t, snr=snr, rssi=None, hops=2, gateway_id="!gw", radio_id=None,
             kind="text", payload=TextData("ciao"))
    d.update(kw)
    return MeshEvent(**d)


def _env():
    conn = connect(":memory:")
    return NetStats(Store(conn)), conn


def test_hourly_counts():
    ns, conn = _env()
    ns.observe(ev(pid=1), "new", False)
    ns.observe(ev(pid=2), "new", False)
    ns.observe(ev(pid=2), "dup", False)
    ns.observe(ev(pid=3), "ignored", False)
    ns.observe(ev(pid=0), "new", False)  # database nodi della radio
    ns.observe(ev(pid=4, replayed=True), "new", False)  # rigioco S&F: non e' traffico
    assert ns.flush() == 1
    rows = [dict(r) for r in conn.execute("SELECT * FROM stats_hourly")]
    assert rows == [{"time": int(NOW), "source": "mqtt", "kind": "text",
                     "packets": 2, "receptions": 3}]


def test_node_hourly_only_archived_and_snr():
    ns, conn = _env()
    ns.observe(ev(pid=1, num=1, snr=-5.0), "new", True)
    ns.observe(ev(pid=1, num=1, snr=-3.0), "dup", True)
    ns.observe(ev(pid=2, num=1, snr=None), "new", True)
    ns.observe(ev(pid=1, num=2, snr=1.0), "new", False)
    ns.flush()
    rows = [dict(r) for r in conn.execute("SELECT * FROM node_hourly")]
    assert len(rows) == 1
    r = rows[0]
    assert r["node_num"] == 1 and r["packets"] == 2
    assert r["snr_n"] == 2 and r["snr_max"] == -3.0 and r["snr_sum"] == -8.0


def test_flush_resets():
    ns, conn = _env()
    ns.observe(ev(), "new", True)
    assert ns.flush() == 2
    assert ns.flush() == 0
    ns.observe(ev(pid=9), "new", True)
    ns.flush()
    assert conn.execute("SELECT packets FROM stats_hourly").fetchone()[0] == 2
