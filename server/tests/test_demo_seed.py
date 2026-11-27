import importlib.util
from pathlib import Path

from meshlens.db import connect
from meshlens.settings import load_settings
from meshlens.store import Store

SEED = Path(__file__).resolve().parents[2] / "tools" / "demo_seed.py"


def load_seed():
    spec = importlib.util.spec_from_file_location("demo_seed", SEED)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_seed_creates_only_fake_data(tmp_path):
    seed = load_seed()
    info = seed.build(tmp_path)
    conn = connect(tmp_path / "meshlens.db")
    store = Store(conn)
    nodes = store.load_nodes()
    assert len(nodes) >= 30 and len(nodes) == info["nodes"]
    assert {n["long_name"] for n in nodes} <= set(seed.NAMES)
    assert any(n["is_mine"] for n in nodes)
    assert store.telemetry(nodes[0]["num"], 0)
    assert store.links(0)
    sess = store.sessions()
    assert len(sess) == 1 and sess[0]["ended"] is not None and store.points(sess[0]["id"])
    # MQTT non puo' collegarsi a nulla di reale
    m = load_settings(conn)["mqtt"]
    assert m["host"] == "127.0.0.1" and m["port"] == 1
    # nessun dato reale: nessuna radio, nessun PIN
    assert store.list_radios() == []
    assert conn.execute("SELECT COUNT(*) FROM auth").fetchone()[0] == 0


def test_demo_seed_exercises_1_6_features(tmp_path):
    import json

    from meshlens.health import battery_overview
    from meshlens.topology import build_topology
    seed = load_seed()
    now = 1_800_000_000.0
    info = seed.build(tmp_path, now=now)
    conn = connect(tmp_path / "meshlens.db")

    def n(q):
        return conn.execute(q).fetchone()[0]
    nodes = {r["num"]: {**dict(r), "is_ignored": bool(r["is_ignored"])}
             for r in conn.execute("SELECT * FROM nodes")}
    drain, solar, charge = info["battery_nodes"]
    out = {x["node_id"]: x for x in battery_overview(conn, nodes, "mine", now)["nodes"]}
    d, s_, c = out["!%08x" % drain], out["!%08x" % solar], out["!%08x" % charge]
    assert d["status"] == "falling" and 2 <= d["days_left"] <= 4
    assert s_["status"] == "solar" and c["status"] in ("external", "charging")
    assert c["current_ma"] and d["voltage"] and d["reboots"] >= 1
    assert n("SELECT COUNT(*) FROM sensor_events") >= 3
    assert n("SELECT COUNT(*) FROM metrics WHERE variant='paxcounter'") > 0
    assert {r[0] for r in conn.execute("SELECT kind FROM alert_rules")} >= {
        "keyword", "snr_low", "geofence", "battery"}
    assert n("SELECT COUNT(*) FROM trace_targets") == 2
    # un bersaglio ha due percorsi diversi (cambio di percorso)
    assert conn.execute(
        "SELECT MAX(c) FROM (SELECT COUNT(DISTINCT route) c FROM traceroutes "
        "WHERE status='ok' GROUP BY target_num)").fetchone()[0] == 2
    assert n("SELECT COUNT(*) FROM tak_contacts") == 2
    topo = build_topology(conn, now, 24)
    assert topo["stats"]["cut"] == 1 and topo["stats"]["isolated"] >= 1
    assert nodes[info["ignored"]]["is_ignored"]
    assert n("SELECT COUNT(*) FROM messages WHERE from_num=%d" % info["ignored"]) == 1
    assert n("SELECT COUNT(*) FROM config_profiles") == 1
    st = load_settings(conn)
    assert st["onboarding_done"] is True and len(st["quick_replies"]) == 2
    assert any("{batteria}" in q for q in st["quick_replies"])
    assert not (st["bot_enabled"] or st["webhook_enabled"] or st["guest_enabled"]
                or st["traceroute_auto_enabled"])
    assert st["bot_targets"] and st["webhook_events"]
    assert st["mqtt"]["host"] == "127.0.0.1" and st["mqtt"]["port"] == 1
    assert json.loads(conn.execute("SELECT data FROM config_profiles").fetchone()[0])["config"]


def test_demo_seed_has_battery_and_key_changed_alerts(tmp_path):
    from meshlens.alerts import compute_alerts
    seed = load_seed()
    now = 1_800_000_000.0
    info = seed.build(tmp_path, now=now)
    conn = connect(tmp_path / "meshlens.db")
    nodes = [n for n in Store(conn).load_nodes() if n["is_mine"]]
    out = compute_alerts(nodes, load_settings(conn), now, {})
    kinds = {(a["kind"], a["node_id"]) for a in out}
    assert ("battery_low", f"!{info['low_battery']:08x}") in kinds
    assert ("key_changed", f"!{info['key_changed']:08x}") in kinds
