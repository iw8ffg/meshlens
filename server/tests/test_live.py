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
