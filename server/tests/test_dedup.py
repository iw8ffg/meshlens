from meshlens.dedup import Deduplicator


def test_first_sighting_is_new():
    d = Deduplicator()
    assert d.is_new(1, 5, 0) is True


def test_duplicate_inside_window_is_not_new():
    d = Deduplicator()
    d.is_new(1, 5, 0)
    assert d.is_new(1, 5, 10) is False


def test_same_packet_id_from_other_node_is_new():
    d = Deduplicator()
    d.is_new(1, 5, 0)
    assert d.is_new(2, 5, 10) is True


def test_expired_window_is_new_again():
    d = Deduplicator()
    d.is_new(1, 5, 0)
    assert d.is_new(1, 5, 700) is True


def test_prune_forgets_expired_keys():
    d = Deduplicator(window_s=600)
    d.is_new(1, 5, 0)
    d.is_new(2, 7, 300)
    d.prune(650)
    assert d.is_new(1, 5, 650) is True
    assert d.is_new(2, 7, 650) is False


def test_memory_limit_evicts_oldest_key():
    d = Deduplicator()
    for i in range(200_001):
        assert d.is_new(1, i, 0) is True
    # la chiave 0 e' stata scartata per far posto alla 200 000
    assert d.is_new(1, 0, 0) is True
    # la chiave piu' recente e' ancora ricordata
    assert d.is_new(1, 200_000, 0) is False


def test_observe_tracks_sources():
    d = Deduplicator(window_s=600)
    assert d.observe(1, 5, 0, "rf") == (True, False)
    assert d.observe(1, 5, 10, "mqtt") == (False, False)
    assert d.observe(1, 5, 20, "mqtt") == (False, True)
    assert d.observe(1, 5, 30, "rf") == (False, True)
    assert d.observe(1, 5, 600, "mqtt") == (True, False)


def test_observe_without_source_marks_nothing():
    d = Deduplicator()
    assert d.observe(1, 5, 0) == (True, False)
    assert d.observe(1, 5, 1, "mqtt") == (False, False)
    assert d.is_new(1, 5, 2) is False


def test_note_gateway():
    d = Deduplicator(window_s=10)
    d.observe(1, 5, 100.0, "mqtt")
    assert d.note_gateway(1, 5, "!a") is True
    assert d.note_gateway(1, 5, "!a") is False
    assert d.note_gateway(1, 5, "!b") is True
    d.prune(200.0)
    d.observe(1, 5, 200.0, "mqtt")
    assert d.note_gateway(1, 5, "!a") is True
