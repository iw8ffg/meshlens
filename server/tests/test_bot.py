"""Bot (E15): riconoscimento dei comandi, testi delle risposte, motore con coda e limiti."""
import time

import pytest

from meshlens.bot import (BOT_MARK, ReplyContext, Request, build_reply, clamp_utf8,
                          match_target, parse_request)

ALL = ["ping", "info", "nodes", "time", "weather"]


def ctx(**kw):
    base = dict(snr=5.5, rssi=-92, hops=2, via_mqtt=False, version="1.6.0", now=1_800_000_000.0,
                nodes_active_1h=7, nodes_total=42, heard_1h=5, heard_24h=12, weather=None)
    base.update(kw)
    return ReplyContext(**base)


# ---- parte pura ----------------------------------------------------------
def test_parse_command_words():
    for text in ("!ping", "!PING", "  !ping  test"):
        assert parse_request(text, ALL, []) == Request("command", "ping", None)
    for text, name in (("!nodi", "nodes"), ("!nodes", "nodes"), ("!ora", "time"),
                       ("!time", "time"), ("!meteo", "weather"), ("!weather", "weather"),
                       ("!info", "info")):
        assert parse_request(text, ALL, []).name == name


def test_command_must_start_the_text():
    for text in ("ciao !ping", "ping", "!pingpong", "!ping2", "", "   "):
        assert parse_request(text, ALL, []) is None


def test_disabled_command_ignored():
    assert parse_request("!info", ["ping"], []) is None


def test_custom_reply_matching():
    replies = [{"trigger": "Orari", "text": "Bus alle 8"},
               {"trigger": "buon giorno", "text": "Ciao"}]
    for text in ("orari", "Orari?", "orari del bus"):
        r = parse_request(text, ALL, replies)
        assert r == Request("reply", "Orari", "Bus alle 8")
    assert parse_request("orarietto", ALL, replies) is None
    assert parse_request("Buon giorno a tutti", ALL, replies).reply_text == "Ciao"
    assert parse_request("dico orari", ALL, replies) is None


def test_builtin_has_precedence_over_trigger():
    r = parse_request("!ping", ["ping"], [{"trigger": "!ping", "text": "altro"}])
    assert r.kind == "command" and r.name == "ping"
    # comando spento: vale la risposta personalizzata
    r = parse_request("!ping", [], [{"trigger": "!ping", "text": "altro"}])
    assert r.kind == "reply"


def test_never_matches_bot_marked_text():
    replies = [{"trigger": "[bot]", "text": "x"}]
    assert parse_request("[bot] pong! SNR +5.5 dB", ALL, replies) is None
    assert parse_request("  [bot] !ping", ALL, replies) is None
    assert parse_request("[BOT] !ping", ALL, replies) is None


def test_ping_reply_texts():
    assert build_reply(Request("command", "ping", None), ctx()) == \
        "[bot] pong! SNR +5.5 dB, RSSI -92 dBm, 2 salti"
    assert "diretto" in build_reply(Request("command", "ping", None), ctx(hops=0))
    assert build_reply(Request("command", "ping", None), ctx(hops=1)).endswith("1 salto")
    t = build_reply(Request("command", "ping", None), ctx(snr=None, rssi=None))
    assert t == "[bot] pong! SNR n/d, RSSI n/d, 2 salti"
    assert build_reply(Request("command", "ping", None), ctx(via_mqtt=True)) == \
        "[bot] pong! via MQTT, 2 salti"
    assert build_reply(Request("command", "ping", None), ctx(snr=-3.25)).startswith(
        "[bot] pong! SNR -3.2 dB")


def test_info_nodes_time_replies():
    c = ctx()
    assert build_reply(Request("command", "info", None), c) == \
        "[bot] MeshLens 1.6.0: 7 nodi attivi nell'ultima ora, 42 noti"
    assert build_reply(Request("command", "nodes", None), c) == \
        "[bot] Nodi sentiti: 5 nell'ultima ora, 12 nelle ultime 24 h"
    expected = time.strftime("[bot] Ora: %H:%M del %d/%m/%Y", time.localtime(c.now))
    assert build_reply(Request("command", "time", None), c) == expected


def test_weather_reply():
    w = {"temperature": 18.5, "relative_humidity": 62.0, "barometric_pressure": 1013.2}
    req = Request("command", "weather", None)
    assert build_reply(req, ctx(weather=w)) == "[bot] Meteo: 18.5 °C, UR 62%, 1013 hPa"
    assert build_reply(req, ctx(weather={"temperature": 18.5})) == "[bot] Meteo: 18.5 °C"
    assert build_reply(req, ctx(weather={})) == "[bot] Meteo non disponibile"
    assert build_reply(req, ctx(weather=None)) is None


def test_custom_reply_text():
    assert build_reply(Request("reply", "Orari", "Bus alle 8"), ctx()) == "[bot] Bus alle 8"


def test_replies_never_contain_node_names_or_input_text():
    req = parse_request("!ping <script>", ALL, [])
    out = build_reply(req, ctx())
    assert "<script>" not in out and out.startswith(BOT_MARK + " ")


def test_clamp_utf8():
    text = "è" * 150  # 300 byte
    out = clamp_utf8(text)
    assert len(out.encode("utf-8")) <= 200
    out.encode("utf-8").decode("utf-8")
    assert out == "è" * 100
    assert clamp_utf8("aè", 2) == "a"
    long = "x" * 200
    assert len(build_reply(Request("reply", "t", long), ctx()).encode("utf-8")) <= 200


def test_match_target_radio_and_mqtt():
    targets = [{"kind": "radio", "radio_id": "r1", "channel_index": 0},
               {"kind": "mqtt", "broker": "b1", "channel": "LongFast"}]
    rf = {"source": "rf", "radio_id": "r1", "channel_index": 0, "broker": None,
          "channel": "0"}
    assert match_target(rf, targets) == targets[0]
    assert match_target({**rf, "channel_index": 1}, targets) is None
    assert match_target({**rf, "radio_id": "r2"}, targets) is None
    mq = {"source": "mqtt", "radio_id": None, "channel_index": None, "broker": "b1",
          "channel": "LongFast"}
    assert match_target(mq, targets) == targets[1]
    assert match_target({**mq, "broker": "b2"}, targets) is None
    assert match_target({**mq, "channel": "Altro"}, targets) is None
    # sorgente incoerente: messaggio RF con i campi di un bersaglio MQTT
    assert match_target({**mq, "source": "rf"}, targets) is None
    assert match_target(rf, []) is None
