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
