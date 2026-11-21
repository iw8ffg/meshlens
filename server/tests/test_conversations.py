from meshlens.conversations import BROADCAST_ID, conversation_key, summaries

LOCAL = {"!a1b2c3d4"}


def msg(**kw):
    base = {"radio_id": "r1a2b3c4", "from": "!00000042", "to": BROADCAST_ID,
            "channel_index": 0, "direction": "in", "time": 300, "text": "x", "emoji": False}
    return {**base, **kw}


def test_key_matches_web_rules():
    assert conversation_key(msg(radio_id=None), LOCAL) is None
    assert conversation_key(msg(channel_index=None), LOCAL) == "ch:r1a2b3c4:0"
    assert conversation_key(msg(channel_index=2), LOCAL) == "ch:r1a2b3c4:2"
    assert conversation_key(msg(to="!00000042", direction="out", **{"from": "!a1b2c3d4"}),
                            LOCAL) == "dm:r1a2b3c4:!00000042"
    assert conversation_key(msg(to="!00000099", **{"from": "!a1b2c3d4"}),
                            LOCAL) == "dm:r1a2b3c4:!00000099"
    assert conversation_key(msg(to="!a1b2c3d4"), LOCAL) == "dm:r1a2b3c4:!00000042"


def test_unread_rules():
    ch = "ch:r1a2b3c4:0"
    msgs = [msg(time=50), msg(time=150), msg(time=160, direction="out"),
            msg(time=170, **{"from": "!a1b2c3d4"}), msg(time=180, emoji=True),
            msg(time=250), msg(time=260, text="ultimo")]
    out = summaries(msgs, LOCAL, {}, 100)
    assert len(out) == 1 and out[0]["key"] == ch
    assert out[0]["unread"] == 3  # 150, 250, 260
    assert out[0]["last_time"] == 260 and out[0]["last_text"] == "ultimo"
    assert out[0]["last_from"] == "!00000042" and out[0]["last_emoji"] is False
    assert out[0]["read_time"] is None
    out = summaries(msgs, LOCAL, {ch: 200}, 100)
    assert out[0]["unread"] == 2 and out[0]["read_time"] == 200
    out = summaries(msgs, LOCAL, {ch: 255}, 100)
    assert out[0]["unread"] == 1


def test_summaries_sorted_by_last_time():
    msgs = [msg(time=10), msg(time=500, to="!a1b2c3d4")]
    assert [s["key"] for s in summaries(msgs, LOCAL, {}, 0)] == [
        "dm:r1a2b3c4:!00000042", "ch:r1a2b3c4:0"]
