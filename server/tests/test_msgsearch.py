import pytest

from meshlens import db, msgsearch, queries
from meshlens.msgsearch import (InvalidCursor, SNIP_CLOSE, SNIP_OPEN, fts_query, like_pattern,
                                parse_cursor, search_messages, search_nodes)
from meshlens.store import Store

BCAST = "!ffffffff"
RADIO = "r1a2b3c4"
LOCAL = "!a1b2c3d4"
PEER = "!000000aa"


@pytest.fixture(params=["fts5", "like"])
def engine(request, monkeypatch):
    if request.param == "like":
        monkeypatch.setattr(db, "fts5_available", lambda c: False)
    conn = db.connect(":memory:")
    if request.param == "like":
        db.ensure_search_index(conn)
    expected = "fts5" if request.param == "fts5" else "like"
    assert db.search_engine(conn) == expected
    return conn, expected


def add(store, key, text, t, frm=PEER, to=BCAST, radio=RADIO, ch=0, direction="in",
        emoji=False, broker=None):
    store.add_message({"key": key, "from": frm, "to": to, "text": text, "time": t,
                       "direction": direction, "radio_id": radio, "channel_index": ch,
                       "emoji": emoji, "broker": broker, "source": "rf" if radio else "mqtt"})


def add_node(conn, num, long_name, short_name="XX", ignored=0, heard=1.0, mine=0):
    conn.execute(
        "INSERT INTO nodes(num, id, long_name, short_name, hw_model, last_heard, is_mine, "
        "is_favorite, is_ignored) VALUES(?,?,?,?,?,?,?,0,?)",
        (num, f"!{num:08x}", long_name, short_name, "TBEAM", heard, mine, ignored))


def test_fts_query_builder():
    assert fts_query("ciao mondo") == '"ciao"* "mondo"*'
    assert fts_query('a"b') == '"a""b"*'
    assert fts_query("  ") is None
    assert fts_query("--- ...") is None
    assert fts_query(" ".join(f"w{i}" for i in range(10))).count('"*') == 8
    assert fts_query("x" * 65) is None


def test_like_pattern_escapes():
    assert like_pattern("50%_a\\") == "%50\\%\\_a\\\\%"


def test_basic_search_both_engines(engine):
    conn, eng = engine
    st = Store(conn)
    add(st, "k1", "Ciao a tutti", 10)
    add(st, "k2", "niente da dire", 20)
    add(st, "k3", "ciao di nuovo", 30)
    conn.commit()
    res = search_messages(conn, "ciao")
    assert res["engine"] == eng
    assert [h["message"]["key"] for h in res["hits"]] == ["k3", "k1"]
    for k in ("key", "from", "from_name", "to", "text", "time", "direction", "radio_id",
              "channel_index", "status", "broker", "emoji"):
        assert k in res["hits"][0]["message"]


def test_prefix_and_diacritics_fts_only(engine):
    conn, eng = engine
    st = Store(conn)
    add(st, "k1", "perché no", 10)
    add(st, "k2", "che città", 20)
    conn.commit()
    assert [h["message"]["key"] for h in search_messages(conn, "perch")["hits"]] == ["k1"]
    found = [h["message"]["key"] for h in search_messages(conn, "citta")["hits"]]
    assert found == (["k2"] if eng == "fts5" else [])


def test_percent_and_underscore_are_literal(engine):
    conn, _ = engine
    st = Store(conn)
    add(st, "k1", "100% sicuro", 10)
    add(st, "k2", "a_b", 20)
    conn.commit()
    assert [h["message"]["key"] for h in search_messages(conn, "%")["hits"]] == ["k1"]
    assert [h["message"]["key"] for h in search_messages(conn, "_")["hits"]] == ["k2"]


@pytest.mark.parametrize("q", ['"', "*", "NEAR(a b)", "a OR", '"unbalanced', "((", "\\"])
def test_special_characters_never_raise(engine, q):
    conn, _ = engine
    add(Store(conn), "k1", "NEAR a b OR c", 10)
    conn.commit()
    assert isinstance(search_messages(conn, q)["hits"], list)


def test_filters(engine):
    conn, _ = engine
    st = Store(conn)
    add(st, "c0", "ciao zero", 10, ch=0)
    add(st, "c1", "ciao uno", 20, ch=1)
    add(st, "d_in", "ciao dm in", 30, frm=PEER, to=LOCAL)
    add(st, "d_out", "ciao dm out", 40, frm=LOCAL, to=PEER, direction="out")
    add(st, "d_other", "ciao altro", 45, frm="!000000bb", to=LOCAL)
    add(st, "m1", "ciao mqtt", 50, radio=None, broker="broker1", to=BCAST)
    add(st, "m2", "ciao mqtt due", 60, radio=None, broker="broker2", to=BCAST)
    conn.commit()

    def keys(**kw):
        return [h["message"]["key"] for h in search_messages(conn, "ciao", **kw)["hits"]]

    assert keys(conv=f"ch:{RADIO}:0") == ["c0"]
    assert keys(conv=f"ch:{RADIO}:1") == ["c1"]
    assert keys(conv=f"dm:{RADIO}:{PEER}", local_ids={LOCAL}) == ["d_out", "d_in"]
    assert keys(conv="mqtt") == ["m2", "m1"]
    assert keys(conv="mqtt:broker1") == ["m1"]
    assert keys(sender=0xaa) == ["m2", "m1", "d_in", "c1", "c0"]
    assert keys(since=20, until=40) == ["d_out", "d_in", "c1"]
    with pytest.raises(ValueError):
        keys(conv="boh")


def test_reactions_and_empty_text_excluded(engine):
    conn, _ = engine
    st = Store(conn)
    add(st, "r1", "👍", 10, emoji=True)
    add(st, "e1", "", 20)
    add(st, "t1", "👍 ok", 30)
    conn.commit()
    # la reazione (emoji=1) e il testo vuoto non compaiono mai; "👍 ok" si trova per "ok"
    assert all(h["message"]["key"] == "t1" for h in search_messages(conn, "👍")["hits"])
    assert search_messages(conn, "ok")["hits"][0]["message"]["key"] == "t1"


def test_ignored_senders_excluded(engine):
    conn, _ = engine
    add_node(conn, 0xaa, "Ignorato", ignored=1)
    add_node(conn, 0xbb, "Visibile")
    st = Store(conn)
    add(st, "i1", "ciao da ignorato", 10, frm="!000000aa")
    add(st, "v1", "ciao da visibile", 20, frm="!000000bb")
    conn.commit()
    assert [h["message"]["key"] for h in search_messages(conn, "ciao")["hits"]] == ["v1"]


def test_cursor_pagination_no_gaps_no_dupes(engine):
    conn, _ = engine
    st = Store(conn)
    for i in range(25):
        add(st, f"k:{i:02d}", f"ciao {i}", 100 + (i // 5))
    conn.commit()
    seen, cur = [], None
    while True:
        res = search_messages(conn, "ciao", limit=7, cursor=cur)
        seen += [h["message"]["key"] for h in res["hits"]]
        cur = res["next"]
        if cur is None:
            break
    assert len(seen) == 25 and len(set(seen)) == 25
    rows = conn.execute("SELECT key FROM messages ORDER BY time DESC, key DESC").fetchall()
    assert seen == [r["key"] for r in rows]
    exact = search_messages(conn, "ciao 1", limit=7)  # 11 corrispondenze circa: non esatto
    assert exact["next"] is not None
    st2 = search_messages(conn, "ciao", limit=25)
    assert st2["next"] is None and len(st2["hits"]) == 25


def test_invalid_cursor():
    for bad in ("abc", "nan:k", ":k", "inf:k"):
        with pytest.raises(InvalidCursor):
            parse_cursor(bad)
    assert parse_cursor("12.5:k:1") == (12.5, "k:1")


def test_empty_cursor_is_no_cursor(engine):
    conn, _ = engine
    add(Store(conn), "k1", "ciao", 10)
    conn.commit()
    assert len(search_messages(conn, "ciao", cursor="")["hits"]) == 1


def test_limit_clamped(engine):
    conn, _ = engine
    st = Store(conn)
    for i in range(3):
        add(st, f"k{i}", "ciao", i)
    conn.commit()
    assert len(search_messages(conn, "ciao", limit=0)["hits"]) == 1
    assert len(search_messages(conn, "ciao", limit=10_000)["hits"]) == 3
    assert msgsearch.LIMIT_MAX == 100


def test_empty_query(engine):
    conn, eng = engine
    assert search_messages(conn, "   ") == {"hits": [], "next": None, "engine": eng}


def test_snippet_markers(engine):
    conn, eng = engine
    st = Store(conn)
    add(st, "k1", "Arrivo alle 18 al rifugio", 10)
    add(st, "k2", ("x" * 300) + " rifugio", 20)
    conn.commit()
    hits = {h["message"]["key"]: h["snippet"] for h in search_messages(conn, "rifugio")["hits"]}
    assert f"{SNIP_OPEN}rifugio{SNIP_CLOSE}" in hits["k1"]
    assert "<" not in hits["k1"]
    if eng == "like":
        assert len(hits["k2"]) <= 80 and hits["k2"].startswith("…")
    else:
        assert SNIP_OPEN in hits["k2"]


def test_conv_in_hit(engine):
    conn, _ = engine
    st = Store(conn)
    add(st, "k1", "ciao", 10)
    add(st, "k2", "ciao", 20, radio=None, broker="b1")
    conn.commit()
    convs = {h["message"]["key"]: h["conv"] for h in search_messages(conn, "ciao")["hits"]}
    assert convs == {"k1": f"ch:{RADIO}:0", "k2": None}


def test_search_nodes():
    conn = db.connect(":memory:")
    add_node(conn, 0xa1b2c3d4, "Rifugio Alpe", "RIFA", heard=50)
    add_node(conn, 0x11, "Garifa", "GAR", heard=10)
    add_node(conn, 0x22, "Rifugio Ignorato", "RIGN", ignored=1)
    add_node(conn, 0x33, "100% node", "PCT")
    conn.commit()
    assert [n["long_name"] for n in search_nodes(conn, "rif")] == ["Rifugio Alpe", "Garifa"]
    assert search_nodes(conn, "RIFA")[0]["id"] == "!a1b2c3d4"
    assert search_nodes(conn, "a1b2")[0]["id"] == "!a1b2c3d4"
    assert search_nodes(conn, "!a1b2")[0]["id"] == "!a1b2c3d4"
    assert search_nodes(conn, "r") == []
    assert len(search_nodes(conn, "rif", limit=1)) == 1
    assert [n["long_name"] for n in search_nodes(conn, "0%")] == ["100% node"]
    assert set(search_nodes(conn, "rifugio")[0]) == {
        "id", "long_name", "short_name", "hw_model", "last_heard", "is_mine", "is_favorite"}


def test_uses_ro_connection(tmp_path):
    path = tmp_path / "m.db"
    conn = db.connect(path)
    add(Store(conn), "k1", "ciao ro", 10)
    conn.commit()
    conn.close()
    ro = queries.ro_connect(path)
    try:
        res = search_messages(ro, "ciao")
        assert len(res["hits"]) == 1
        assert search_nodes(ro, "zz") == []
    finally:
        ro.close()


def test_fts_non_alnum_term_still_required(engine):
    conn, _ = engine
    store = Store(conn)
    add(store, "k1", "hello \U0001F600", 1.0)
    add(store, "k2", "hello world", 2.0)
    r = search_messages(conn, "hello \U0001F600")
    assert [h["message"]["key"] for h in r["hits"]] == ["k1"]


def test_snippet_only_for_returned_page_prefix_and_accents(engine):
    conn, kind = engine
    store = Store(conn)
    for i in range(5):
        add(store, f"k{i}", f"Perche' ciao a tutti {i}", float(i))
    add(store, "k9", "Perch\u00e9 ci vediamo", 9.0)
    r = search_messages(conn, "perche", limit=2)
    assert len(r["hits"]) == 2 and r["next"] is not None
    if kind == "fts5":  # LIKE non ignora gli accenti
        assert SNIP_OPEN + "Perch\u00e9" + SNIP_CLOSE in r["hits"][0]["snippet"]
    r = search_messages(conn, "a", limit=50)
    sn = [h["snippet"] for h in r["hits"] if h["message"]["key"] == "k0"][0]
    assert SNIP_OPEN + "a" + SNIP_CLOSE in sn
