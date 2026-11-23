from meshlens.live import LiveState


def test_evict_older_than_keeps_mine_and_fresh():
    live = LiveState()
    live.load([{"num": 1, "last_heard": 10}, {"num": 2, "last_heard": 10, "is_mine": True},
               {"num": 3, "last_heard": 100}, {"num": 4, "last_heard": None}])
    live.mark_changed(1)
    assert live.evict_older_than(50) == 2
    assert sorted(live.nodes) == [2, 3]
    assert live.take_changed() == []


def test_evict_null_last_heard_non_mine_only():
    live = LiveState()
    live.load([{"num": 1, "last_heard": None}, {"num": 2, "last_heard": None, "is_mine": True}])
    assert live.evict_older_than(50) == 1
    assert sorted(live.nodes) == [2]


def test_evict_keeps_favorites():
    live = LiveState()
    live.load([{"num": 1, "last_heard": 10}, {"num": 2, "last_heard": 10, "is_favorite": True}])
    assert live.evict_older_than(50) == 1
    assert sorted(live.nodes) == [2]


def test_default_node_cap():
    from meshlens.live import MAX_LIVE_NODES
    assert MAX_LIVE_NODES == 50_000
    assert LiveState().max_nodes == MAX_LIVE_NODES


def test_enforce_cap_keeps_mine_and_favorites():
    live = LiveState(max_nodes=100)
    nodes = [{"num": i, "last_heard": 1000 + i} for i in range(120)]
    for i in range(5):
        nodes[i]["is_mine"] = True
    for i in range(5, 10):
        nodes[i]["is_favorite"] = True
    nodes[50]["last_heard"] = None  # mai sentito: tra i primi a uscire
    live.load(nodes)
    live.mark_changed(10)
    assert live.enforce_cap() == 25
    assert len(live.nodes) == 95
    assert all(i in live.nodes for i in range(10))
    assert 50 not in live.nodes
    assert all(i not in live.nodes for i in range(10, 34))
    assert all(i in live.nodes for i in range(34, 120) if i != 50)
    assert live.take_changed() == []


def test_enforce_cap_below_limit_does_nothing():
    live = LiveState(max_nodes=100)
    live.load([{"num": i, "last_heard": i} for i in range(100)])
    assert live.enforce_cap() == 0 and len(live.nodes) == 100


def test_ignored_nodes_are_kept():
    live = LiveState(max_nodes=10)
    nodes = [{"num": i, "last_heard": 1000 + i} for i in range(20)]
    nodes[0]["is_ignored"] = True
    live.load(nodes)
    live.enforce_cap()
    assert 0 in live.nodes and 1 not in live.nodes
    assert live.evict_older_than(5000) >= 1 and 0 in live.nodes
