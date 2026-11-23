import pytest

from meshlens import conv_export, db
from meshlens.conv_export import EXPORT_MAX, export_conversation
from meshlens.store import Store

BCAST = "!ffffffff"
RADIO = "r1a2b3c4"
LOCAL = "!a1b2c3d4"
PEER = "!000000aa"


def add(store, key, text, t, frm=PEER, to=BCAST, radio=RADIO, ch=0, direction="in",
        emoji=False, broker=None):
    store.add_message({"key": key, "from": frm, "to": to, "text": text, "time": t,
                       "direction": direction, "radio_id": radio, "channel_index": ch,
                       "emoji": emoji, "broker": broker, "source": "rf" if radio else "mqtt"})


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_channel_export_chronological(conn):
    st = Store(conn)
    add(st, "a", "uno", 10)
    add(st, "c", "tre", 30)
    add(st, "b", "due", 20)
    add(st, "x", "altro canale", 25, ch=1)
    conn.commit()
    d = export_conversation(conn, f"ch:{RADIO}:0", {LOCAL})
    assert [m["key"] for m in d["messages"]] == ["a", "b", "c"]
    assert d["total"] == 3 and d["truncated"] is False and d["key"] == f"ch:{RADIO}:0"


def test_dm_export_includes_both_directions(conn):
    st = Store(conn)
    add(st, "in", "ciao", 10, frm=PEER, to=LOCAL)
    add(st, "out", "ciao a te", 20, frm=LOCAL, to=PEER, direction="out")
    add(st, "bc", "a tutti", 30, frm=PEER, to=BCAST)
    add(st, "other", "altro", 40, frm="!000000bb", to=LOCAL)
    conn.commit()
    d = export_conversation(conn, f"dm:{RADIO}:{PEER}", {LOCAL})
    assert [m["key"] for m in d["messages"]] == ["in", "out"]


def test_mqtt_exports(conn):
    st = Store(conn)
    add(st, "r", "radio", 10)
    add(st, "m1", "uno", 20, radio=None, broker="b1")
    add(st, "m2", "due", 30, radio=None, broker="b2")
    conn.commit()
    assert [m["key"] for m in export_conversation(conn, "mqtt", set())["messages"]] == ["m1", "m2"]
    assert [m["key"] for m in export_conversation(conn, "mqtt:b1", set())["messages"]] == ["m1"]


def test_period_filter_and_truncation(conn):
    st = Store(conn)
    for i in range(5):
        add(st, f"k{i}", f"m{i}", 10 + i)
    conn.commit()
    key = f"ch:{RADIO}:0"
    d = export_conversation(conn, key, set(), since=11, until=13)
    assert [m["key"] for m in d["messages"]] == ["k1", "k2", "k3"]
    d = export_conversation(conn, key, set(), limit=3)
    assert [m["key"] for m in d["messages"]] == ["k2", "k3", "k4"]
    assert d["total"] == 5 and d["truncated"] is True
    assert EXPORT_MAX == 20000


def test_names_resolved(conn):
    conn.execute("INSERT INTO nodes(num, id, long_name) VALUES(170, '!000000aa', 'Alice')")
    st = Store(conn)
    add(st, "a", "ciao", 10, frm=PEER, to=LOCAL)
    add(st, "b", "ehi", 20, frm="!000000bb", to="!000000cc", ch=0)
    conn.commit()
    m = export_conversation(conn, f"dm:{RADIO}:{PEER}", {LOCAL})["messages"][0]
    assert m["from_name"] == "Alice" and m["to_name"] is None


@pytest.mark.parametrize("key", ["x", "ch:r1:0", "mqtt:B!", "dm:r1a2b3c4:zz", "ch:r1a2b3c4:x"])
def test_invalid_key_raises(conn, key):
    with pytest.raises(ValueError):
        export_conversation(conn, key, set())


def test_no_secrets_in_rows(conn):
    add(Store(conn), "a", "ciao", 10)
    conn.commit()
    allowed = set(Store._message_row(conn.execute(
        "SELECT m.*, NULL AS from_name FROM messages m").fetchone())) | {"to_name"}
    m = export_conversation(conn, f"ch:{RADIO}:0", set())["messages"][0]
    assert set(m) <= allowed and "raw" not in m


def test_ignored_senders_hidden(conn):
    conn.execute("INSERT INTO nodes(num, id, long_name, is_ignored) VALUES(170, '!000000aa', 'X', 1)")
    st = Store(conn)
    add(st, "a", "nascosto", 10, frm=PEER)
    add(st, "b", "visibile", 20, frm="!000000bb")
    conn.commit()
    d = export_conversation(conn, f"ch:{RADIO}:0", set())
    assert [m["key"] for m in d["messages"]] == ["b"] and d["total"] == 1
    assert conv_export.MQTT_KEY_RE.match("mqtt:b1")
