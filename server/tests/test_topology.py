import random
import time

from meshlens import db
from meshlens.topology import SOURCES, analyze, build_topology

NOW = 1_700_000_000.0


def an(edges, nodes=None):
    if nodes is None:
        nodes = {x for e in edges for x in e}
    return analyze(nodes, edges)


def test_path_middle_is_cut():
    a = an([(1, 2), (2, 3)])
    assert a.cut == {2: 1}
    assert a.degree == {1: 1, 2: 2, 3: 1}
    assert a.components == [3]


def test_star_center_is_cut_with_impact():
    a = an([(1, 2), (1, 3), (1, 4), (1, 5)])
    assert a.cut == {1: 3}


def test_cycle_has_no_cut():
    assert an([(1, 2), (2, 3), (3, 4), (4, 1)]).cut == {}


def test_barbell():
    a = an([(1, 2), (2, 3), (1, 3), (4, 5), (5, 6), (4, 6), (3, 4)])
    assert a.cut == {3: 2, 4: 2}


def test_root_with_two_children_is_cut_and_with_one_is_not():
    assert an([(1, 2), (2, 3)]).cut == {2: 1}  # radice 1 con un figlio: non cerniera
    assert 1 in an([(1, 2), (1, 3)]).cut      # radice con due figli: cerniera


def test_two_components_and_isolated():
    a = an([(1, 2), (2, 3), (10, 11)], nodes={1, 2, 3, 10, 11, 99})
    assert a.components == [3, 2]
    assert a.component[1] == 0 and a.component[10] == 1
    assert 99 not in a.component and a.degree.get(99, 0) == 0


def test_self_loops_and_duplicates_ignored():
    a = an([(1, 1), (1, 2), (2, 1), (1, 2)])
    assert a.degree == {1: 1, 2: 1}


def test_edges_with_unknown_endpoint_dropped():
    a = analyze({1, 2}, [(1, 2), (2, 77)])
    assert a.degree == {1: 1, 2: 1}


def test_invariant_under_node_order():
    base = [(1, 2), (2, 3), (3, 1), (3, 4), (4, 5), (5, 6), (6, 4), (6, 7), (7, 8), (8, 9),
            (9, 7), (2, 10), (10, 11), (11, 12)]
    ref = an(base)
    rnd = random.Random(7)
    for _ in range(20):
        perm = list(range(1, 13))
        rnd.shuffle(perm)
        m = dict(zip(range(1, 13), perm))
        inv = {v: k for k, v in m.items()}
        edges = [(m[a], m[b]) for a, b in base]
        rnd.shuffle(edges)
        a = an(edges)
        assert sorted(a.cut.values()) == sorted(ref.cut.values())
        assert {inv[k]: v for k, v in a.cut.items()} == ref.cut


def test_long_chain_no_recursion_error():
    t0 = time.time()
    a = an([(i, i + 1) for i in range(1, 5000)])
    assert len(a.cut) == 4998
    assert time.time() - t0 < 2


def test_hubs_threshold():
    star = [(100, i) for i in range(1, 13)] + [(200 + i, 300 + i) for i in range(1, 6)]
    a = analyze({x for e in star for x in e}, star)
    assert 100 in a.hubs and len(a.hubs) == 1
    assert an([(1, 2), (2, 3), (3, 4), (4, 1)]).hubs == frozenset()


# ---- build_topology ----

def make_db():
    conn = db.connect(":memory:")
    return conn


def add_node(conn, num, last=NOW - 10, country="IT", mine=0, ignored=0, name=None):
    conn.execute("INSERT INTO nodes(num, id, long_name, role, last_heard, country, is_mine, is_ignored) "
                 "VALUES(?,?,?,?,?,?,?,?)",
                 (num, "!%08x" % num, name, "ROUTER", last, country, mine, ignored))


def add_link(conn, a, b, source, snr=None, t=NOW - 10):
    conn.execute("INSERT INTO links(from_num, to_num, source, snr, time) VALUES(?,?,?,?,?)",
                 (a, b, source, snr, t))


def test_build_topology_shape_and_merge():
    c = make_db()
    for n in (1, 2, 3):
        add_node(c, n)
    add_link(c, 1, 2, "neighborinfo", 4)
    add_link(c, 2, 1, "traceroute", 6)
    add_link(c, 2, 3, "rf_direct")
    r = build_topology(c, NOW, 168, SOURCES, ())
    assert r["edges"][0] == {"a": "!00000001", "b": "!00000002",
                             "sources": ["neighborinfo", "traceroute"], "snr": 6.0, "time": NOW - 10}
    assert r["stats"]["by_source"] == {"neighborinfo": 1, "traceroute": 1, "mqtt_gateway": 0,
                                       "rf_direct": 1}
    assert r["stats"]["cut"] == 1
    assert [n["id"] for n in r["nodes"] if n["cut"]] == ["!00000002"]


def test_build_topology_window_sources_and_countries():
    c = make_db()
    add_node(c, 1)
    add_node(c, 2)
    add_node(c, 3, country="DE")
    add_node(c, 4, country="DE", mine=1)
    add_link(c, 1, 2, "traceroute")
    add_link(c, 1, 3, "traceroute")
    add_link(c, 1, 4, "traceroute")
    add_link(c, 2, 1, "neighborinfo", t=NOW - 3 * 86400)
    r = build_topology(c, NOW, 24, SOURCES, ("IT",))
    assert {(e["a"], e["b"]) for e in r["edges"]} == {("!00000001", "!00000002"),
                                                       ("!00000001", "!00000004")}
    r = build_topology(c, NOW, 168, ("traceroute",), ())
    assert r["stats"]["by_source"]["neighborinfo"] == 0 and r["stats"]["edges"] == 3
    r = build_topology(c, NOW, 24, SOURCES, ())
    assert "!00000003" in {n["id"] for n in r["nodes"]}


def test_placeholder_nodes_follow_none_country():
    c = make_db()
    add_node(c, 1)
    add_link(c, 1, 99, "traceroute")
    assert build_topology(c, NOW, 24, SOURCES, ("IT",))["edges"] == []
    r = build_topology(c, NOW, 24, SOURCES, ("IT", "none"))
    assert len(r["edges"]) == 1
    assert [n for n in r["nodes"] if n["id"] == "!00000063"][0]["name"] == "!00000063"


def test_isolated_listed_not_drawn():
    c = make_db()
    add_node(c, 1)
    add_node(c, 2)
    add_node(c, 5)                       # isolato recente
    add_node(c, 6, ignored=1)            # ignorato: mai presente
    add_node(c, 7, last=NOW - 30 * 86400)  # scaduto
    add_link(c, 1, 2, "traceroute")
    add_link(c, 1, 6, "traceroute")
    r = build_topology(c, NOW, 168, SOURCES, ())
    assert [i["id"] for i in r["isolated"]] == ["!00000005"]
    assert "!00000005" not in {n["id"] for n in r["nodes"]}
    ids = {n["id"] for n in r["nodes"]} | {i["id"] for i in r["isolated"]}
    assert "!00000006" not in ids and "!00000007" not in ids
    assert r["stats"]["isolated"] == 1


def test_truncation_keeps_cuts_first():
    c = make_db()
    for n in range(1, 31):
        add_node(c, n)
    for n in range(1, 30):
        add_link(c, n, n + 1, "traceroute")
    r = build_topology(c, NOW, 168, SOURCES, (), limit=10)
    assert r["truncated"] is True and len(r["nodes"]) == 10
    kept = {n["id"] for n in r["nodes"]}
    assert all(e["a"] in kept and e["b"] in kept for e in r["edges"])
    assert r["stats"]["cut"] == 28
    assert max(n["impact"] for n in r["nodes"]) == 14
