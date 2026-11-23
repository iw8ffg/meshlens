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


# ---- motore --------------------------------------------------------------
from pathlib import Path  # noqa: E402

from meshlens import bot as bot_mod  # noqa: E402
from meshlens.app import MessageMeta  # noqa: E402
from meshlens.bot import (BACKOFF_RESET_S, BOT_NODE_TTL_S, INFLIGHT_TTL_S, JOB_TTL_S,  # noqa: E402
                          Bot)
from meshlens.bus import Bus  # noqa: E402
from meshlens.events import MeshEvent, TextData  # noqa: E402
from meshlens.live import LiveState  # noqa: E402
from meshlens.mqtt_publish import MqttSendError  # noqa: E402
from meshlens.radio import RadioBusy  # noqa: E402

T0 = 1_800_000_000.0
RF_T = {"kind": "radio", "radio_id": "r1", "channel_index": 0}
MQ_T = {"kind": "mqtt", "broker": "b1", "channel": "LongFast"}


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


class FakeRadios:
    def __init__(self):
        self.calls, self.raise_, self.n = [], None, 0

    def local_ids(self):
        return {"!00000001"}

    async def send(self, radio_id, text, channel_index=0, to=None, reply_id=None, emoji=False,
                   **kw):
        self.calls.append({"radio_id": radio_id, "text": text, "channel_index": channel_index,
                           "to": to, "reply_id": reply_id, **kw})
        if self.raise_ is not None:
            raise self.raise_
        self.n += 1
        return {"key": f"out:{radio_id}:pending-{self.n}"}


class FakeMqtt:
    def __init__(self):
        self.calls, self.raise_ = [], []

    def send(self, text, channel, to, confirm_public, broker=None, reply_id=None, emoji=False):
        self.calls.append({"text": text, "channel": channel, "to": to,
                           "confirm_public": confirm_public, "broker": broker,
                           "reply_id": reply_id})
        if self.raise_:
            raise self.raise_.pop(0)
        return {"key": f"out:mqtt:{len(self.calls)}"}


class BotEnv:
    def __init__(self, **settings):
        self.clock = Clock()
        self.radios = FakeRadios()
        self.mqtt = FakeMqtt()
        self.live = LiveState()
        self.bus = Bus()
        self.q = self.bus.subscribe()
        self.weather = {}
        self.settings = {"bot_enabled": True, "bot_targets": [RF_T, MQ_T],
                         "bot_commands": ["ping", "info", "nodes", "time", "weather"],
                         "bot_weather_node": "", "bot_replies": [], "bot_min_interval_s": 30,
                         "bot_max_per_hour": 20, "bot_node_cooldown_s": 300,
                         "mqtt_node_id": "!0000beef", "mqtt_send_confirmed_brokers": ["b1"],
                         **settings}
        self.bot = Bot(lambda: self.settings, self.clock, self.radios, self.mqtt, self.live,
                       self.radios.local_ids, lambda: set(), self.lookup, self.bus.publish,
                       "1.6.0")

    def lookup(self, num):
        return self.weather

    def node(self, num, **kw):
        self.live.nodes[num] = {"id": f"!{num:08x}", "num": num, "long_name": "X",
                                "is_mine": False, "is_ignored": False,
                                "last_heard": self.clock.t, **kw}

    def msg(self, text="!ping", sender="!000000aa", source="rf", outcome="new", replayed=False,
            with_event=True, **kw):
        num = int(sender[1:], 16)
        if num not in self.live.nodes:
            self.node(num)
        m = {"key": f"{sender}:77", "from": sender, "from_name": "X", "to": "!ffffffff",
             "channel": "0" if source == "rf" else "LongFast", "text": text,
             "time": int(self.clock.t), "country": "IT", "source": source, "direction": "in",
             "radio_id": "r1" if source == "rf" else None,
             "channel_index": 0 if source == "rf" else None, "packet_id": 77, "status": None,
             "broker": None if source == "rf" else "b1", "reply_id": None, "emoji": False,
             "pki": False, "error": None}
        m.update(kw)
        ev = None
        if with_event:
            ev = MeshEvent(source=source, from_node=num, to_node=0xFFFFFFFF, packet_id=77,
                           channel=m["channel"], rx_time=self.clock.t, snr=5.5, rssi=-92,
                           hops=2, gateway_id=None, radio_id=m["radio_id"], kind="text",
                           payload=TextData(text), broker=m["broker"], replayed=replayed)
        return m, MessageMeta(ev, outcome)

    def feed(self, *a, **kw):
        m, meta = self.msg(*a, **kw)
        self.bot.on_message(m, meta)
        return m

    def bot_events(self):
        out = []
        while not self.q.empty():
            m = self.q.get_nowait()
            if m["type"] == "bot":
                out.append(m)
        return out


def queued(e):
    return e.bot.status()["queued"]


def test_ignores_when_disabled_or_no_targets():
    e = BotEnv(bot_enabled=False)
    e.feed()
    assert queued(e) == 0 and e.bot.status()["dropped"]["disabled"] == 1
    e = BotEnv(bot_targets=[])
    e.feed()
    assert queued(e) == 0 and e.bot.status()["dropped"]["disabled"] == 1


def test_ignores_non_live_and_outgoing():
    e = BotEnv()
    e.feed(outcome="dup")
    e.feed(replayed=True)
    e.feed(direction="out")
    e.feed(with_event=False)
    assert queued(e) == 0
    assert e.bot.status()["dropped"]["not_live"] == 4


def test_ignores_dm_reactions_and_old():
    e = BotEnv()
    e.feed(to="!00000002")
    e.feed(emoji=True)
    e.feed(time=int(T0) - 121)
    e.feed(text="")
    assert queued(e) == 0


def test_ignores_non_target_channel():
    e = BotEnv()
    e.feed(channel_index=1)
    e.feed(radio_id="r2")
    e.feed(source="mqtt", broker="b2")
    e.feed(source="mqtt", channel="Altro")
    assert queued(e) == 0 and e.bot.status()["dropped"]["no_target"] == 4


def test_never_replies_to_self_or_own_nodes():
    e = BotEnv()
    e.feed(sender="!00000001")  # radio locale
    e.node(0x22, is_mine=True)
    e.feed(sender="!00000022")
    e.feed(sender="!0000beef", source="mqtt")  # mqtt_node_id
    assert queued(e) == 0 and e.bot.status()["dropped"]["own"] == 3


def test_never_replies_to_ignored_node():
    e = BotEnv()
    e.node(0x33, is_ignored=True)
    e.feed(sender="!00000033")
    assert queued(e) == 0


def test_never_replies_to_marked_text_and_flags_bot_node():
    e = BotEnv()
    e.feed(text="[bot] pong!")
    assert queued(e) == 0 and "!000000aa" in e.bot._bot_nodes
    e.feed(text="!ping")
    assert queued(e) == 0
    e.clock.t += BOT_NODE_TTL_S + 1
    e.feed(text="!ping")
    assert queued(e) == 1


def test_bot_nodes_capacity_bounded():
    e = BotEnv()
    for i in range(300):
        e.feed(text="[bot] ciao", sender=f"!{0x1000 + i:08x}")
    assert len(e.bot._bot_nodes) <= 256


def test_requires_explicit_request():
    e = BotEnv()
    e.feed(text="ciao !ping")
    assert queued(e) == 0 and e.bot.status()["dropped"]["no_request"] == 1


def test_per_node_cooldown():
    e = BotEnv()
    e.feed()
    e.feed()
    assert queued(e) == 1
    e.feed(sender="!000000bb")
    assert queued(e) == 2
    e.bot._queue.clear()
    e.clock.t += 301
    e.feed()
    assert queued(e) == 1


def test_cooldown_restored_when_no_reply_built():
    e = BotEnv(bot_weather_node="!00000099")
    e.node(0x99, is_mine=False)
    e.feed(text="!meteo")
    assert queued(e) == 0 and e.bot.status()["dropped"]["no_reply"] == 1
    e.feed(text="!ping")
    assert queued(e) == 1


def test_weather_from_own_node():
    e = BotEnv(bot_weather_node="!00000099")
    e.node(0x99, is_mine=True)
    e.weather = {"temperature": 20.0}
    e.feed(text="!meteo")
    assert e.bot._queue[0].text == "[bot] Meteo: 20.0 °C"


def test_one_pending_job_per_sender_and_queue_cap():
    e = BotEnv(bot_node_cooldown_s=30)
    for i in range(11):
        e.feed(sender=f"!{0x100 + i:08x}")
    assert queued(e) == 10
    e2 = BotEnv(bot_node_cooldown_s=30)
    e2.feed()
    e2.clock.t += 31
    e2.feed()
    assert queued(e2) == 1


async def test_pump_sends_one_per_call_and_respects_min_interval():
    e = BotEnv()
    for s in ("!000000a1", "!000000a2", "!000000a3"):
        e.feed(sender=s)
    await e.bot.pump()
    assert len(e.radios.calls) == 1
    e.clock.t += 2
    await e.bot.pump()
    assert len(e.radios.calls) == 1
    e.clock.t = T0 + 30
    await e.bot.pump()
    assert len(e.radios.calls) == 2


async def test_hourly_cap():
    e = BotEnv(bot_max_per_hour=2, bot_min_interval_s=15)
    e.feed(sender="!000000a1")
    await e.bot.pump()
    e.clock.t += 20
    e.feed(sender="!000000a2")
    await e.bot.pump()
    e.clock.t += 20
    e.feed(sender="!000000a3")
    await e.bot.pump()
    assert len(e.radios.calls) == 2 and queued(e) == 1
    e.clock.t = T0 + 3600  # il primo invio esce dalla finestra, ma il job e' scaduto
    await e.bot.pump()
    assert len(e.radios.calls) == 2 and queued(e) == 0
    e.feed(sender="!000000a4")
    await e.bot.pump()
    assert len(e.radios.calls) == 3


async def test_job_expires_after_ttl():
    e = BotEnv()
    e.feed()
    e.clock.t += JOB_TTL_S + 1
    await e.bot.pump()
    assert e.radios.calls == [] and queued(e) == 0


async def test_reply_goes_to_same_target_with_reply_id():
    e = BotEnv()
    e.feed()
    await e.bot.pump()
    assert e.radios.calls == [{"radio_id": "r1", "text": "[bot] pong! SNR +5.5 dB, RSSI -92 dBm, "
                               "2 salti", "channel_index": 0, "to": None, "reply_id": 77}]
    assert e.mqtt.calls == []
    e2 = BotEnv()
    e2.feed(source="mqtt")
    await e2.bot.pump()
    assert e2.radios.calls == []
    assert e2.mqtt.calls == [{"text": "[bot] pong! via MQTT, 2 salti", "channel": "LongFast",
                              "to": None, "confirm_public": False, "broker": "b1",
                              "reply_id": 77}]


async def test_never_passes_confirm_public_true():
    e = BotEnv(bot_min_interval_s=15)
    for i in range(5):
        e.feed(source="mqtt", sender=f"!{0x200 + i:08x}")
        await e.bot.pump()
        e.clock.t += 16
    assert e.mqtt.calls and all(c["confirm_public"] is False for c in e.mqtt.calls)


async def test_unconfirmed_broker_not_admitted():
    e = BotEnv(mqtt_send_confirmed_brokers=[])
    e.feed(source="mqtt")
    assert queued(e) == 0
    assert e.bot.status()["dropped"]["broker_not_confirmed"] == 1


async def test_target_removed_after_enqueue_drops_job():
    e = BotEnv()
    e.feed()
    e.settings["bot_targets"] = [MQ_T]
    await e.bot.pump()
    assert e.radios.calls == [] and queued(e) == 0


async def test_disabling_clears_queue():
    e = BotEnv()
    e.feed()
    e.settings["bot_enabled"] = False
    await e.bot.pump()
    assert e.radios.calls == [] and queued(e) == 0


async def test_mqtt_rate_limited_requeues_once():
    e = BotEnv()
    e.feed(source="mqtt")
    e.mqtt.raise_ = [MqttSendError(429, "rate_limited", "Attendi 5 s"),
                     MqttSendError(429, "rate_limited", "Attendi 5 s")]
    await e.bot.pump()
    assert len(e.mqtt.calls) == 1
    job = e.bot._queue[0]
    assert job.attempts == 1 and job.not_before == T0 + 30
    await e.bot.pump()  # non prima di not_before
    assert len(e.mqtt.calls) == 1
    e.clock.t = T0 + 30
    await e.bot.pump()
    assert len(e.mqtt.calls) == 2 and queued(e) == 0
    assert e.bot.status()["last_error"] == "busy"


async def test_mqtt_confirm_required_blocks_broker():
    e = BotEnv(bot_node_cooldown_s=30)
    e.feed(source="mqtt", sender="!000000a1")
    e.feed(source="mqtt", sender="!000000a2")
    e.mqtt.raise_ = [MqttSendError(409, "confirm_required", "conferma")]
    await e.bot.pump()
    assert queued(e) == 0 and e.bot.status()["last_error"] == "broker_not_confirmed"
    e.feed(source="mqtt", sender="!000000a3")
    assert queued(e) == 0
    e.settings = {**e.settings}  # impostazioni salvate di nuovo
    e.feed(source="mqtt", sender="!000000a4")
    assert queued(e) == 1


async def test_mqtt_other_errors_drop_job():
    e = BotEnv()
    e.feed(source="mqtt")
    e.mqtt.raise_ = [MqttSendError(503, "mqtt_disconnected", "MQTT non connesso")]
    await e.bot.pump()
    assert queued(e) == 0 and e.bot.status()["last_error"] == "mqtt_disconnected"
    e.clock.t += 400
    e.feed(source="mqtt")
    e.mqtt.raise_ = [MqttSendError(400, "invalid_text", "testo")]
    await e.bot.pump()
    assert e.bot.status()["last_error"] == "invalid"


async def test_radio_errors_drop_job():
    e = BotEnv()
    e.feed()
    e.radios.raise_ = ValueError("Radio non connessa")
    await e.bot.pump()
    assert queued(e) == 0 and e.bot.status()["last_error"] == "radio_not_connected"
    e.clock.t += 400
    e.feed()
    e.radios.raise_ = RadioBusy()
    await e.bot.pump()
    assert queued(e) == 1 and len(e.radios.calls) == 2
    e.clock.t += 30
    await e.bot.pump()
    assert queued(e) == 0 and len(e.radios.calls) == 3
    assert e.bot.status()["last_error"] == "busy"


async def nak(e, error):
    e.feed(sender=f"!{0x300 + len(e.radios.calls):08x}")
    await e.bot.pump()
    n = e.radios.n
    e.bot.on_bus({"type": "message", "message": {"key": f"out:r1:{900 + n}",
                                                  "replaces": f"out:r1:pending-{n}"}})
    e.bot.on_bus({"type": "message_status", "key": f"out:r1:{900 + n}", "status": "failed",
                  "error": error})


async def test_nak_duty_cycle_backs_off():
    e = BotEnv()
    await nak(e, "DUTY_CYCLE_LIMIT")
    st = e.bot.status()
    assert st["paused_until"] == T0 + 300 and st["last_error"] == "duty_cycle_limit"
    e.clock.t += 60
    e.feed(sender="!000000c2")
    assert queued(e) == 0  # in pausa: nessuna nuova richiesta
    assert e.bot.status()["dropped"]["paused"] == 1
    await e.bot.pump()
    assert len(e.radios.calls) == 1
    e.clock.t = T0 + 300
    e.feed(sender="!000000c3")
    await e.bot.pump()
    assert len(e.radios.calls) == 2


async def test_backoff_doubles_and_caps_and_resets():
    e = BotEnv(bot_min_interval_s=15, bot_node_cooldown_s=30)
    await nak(e, "DUTY_CYCLE_LIMIT")
    assert e.bot.status()["paused_until"] == e.clock.t + 300
    e.clock.t = e.bot.paused_until
    await nak(e, "RATE_LIMIT_EXCEEDED")
    assert e.bot.paused_until == e.clock.t + 600
    assert e.bot.status()["last_error"] == "rate_limit_exceeded"
    for _ in range(4):
        e.clock.t = e.bot.paused_until
        await nak(e, "DUTY_CYCLE_LIMIT")
        assert e.bot.paused_until - e.clock.t <= 3600
    assert e.bot.paused_until - e.clock.t == 3600
    e.clock.t = e.bot.paused_until + BACKOFF_RESET_S
    await nak(e, "DUTY_CYCLE_LIMIT")
    assert e.bot.paused_until == e.clock.t + 300


async def test_backoff_clears_queue():
    e = BotEnv()
    e.feed(sender="!000000d1")
    e.feed(sender="!000000d2")
    await e.bot.pump()
    assert queued(e) == 1
    # invio fallito prima di avere l'id definitivo: stato sulla chiave provvisoria
    e.bot.on_bus({"type": "message_status", "key": "out:r1:pending-1", "status": "failed",
                  "error": "DUTY_CYCLE_LIMIT"})
    assert queued(e) == 0 and e.bot.status()["paused_until"] == T0 + 300
    # la stessa chiave non conta due volte
    e.bot.on_bus({"type": "message_status", "key": "out:r1:pending-1", "status": "failed",
                  "error": "DUTY_CYCLE_LIMIT"})
    assert e.bot.paused_until == T0 + 300 and e.bot._strikes == 1


async def test_nak_for_foreign_message_ignored():
    e = BotEnv()
    e.bot.on_bus({"type": "message_status", "key": "out:r1:12345", "status": "failed",
                  "error": "DUTY_CYCLE_LIMIT"})
    assert e.bot.status()["paused_until"] is None


async def test_other_failures_only_record_error():
    e = BotEnv()
    await nak(e, "SEND_FAILED")
    st = e.bot.status()
    assert st["last_error"] == "send_failed" and st["paused_until"] is None
    e2 = BotEnv()
    await nak(e2, "MAX_RETRANSMIT")
    assert e2.bot.status()["last_error"] == "max_retransmit"


async def test_inflight_pruned():
    e = BotEnv()
    e.feed()
    await e.bot.pump()
    assert len(e.bot._inflight) == 1
    e.clock.t += INFLIGHT_TTL_S + 1
    await e.bot.pump()
    assert e.bot._inflight == {}


def test_no_override_duty_cycle_anywhere():
    src = Path(bot_mod.__file__).read_text(encoding="utf-8")
    for bad in ("override_duty_cycle", "sendText", "sendData", "paho", "publish(", "iface",
                "confirm_public=True"):
        assert bad not in src.replace("self.publish(", "").replace("_publish(", ""), bad


async def test_status_fields_and_bus_event():
    e = BotEnv()
    assert set(e.bot.status()) == {"enabled", "queued", "sent_last_hour", "paused_until",
                                   "last_error", "dropped"}
    e.feed()
    e.feed(sender="!000000bb")
    await e.bot.pump()
    ev = e.bot_events()
    assert len(ev) == 1 and ev[0]["status"]["queued"] == 1
    assert ev[0]["status"]["sent_last_hour"] == 1
    await e.bot.pump()  # nulla di cambiato
    assert e.bot_events() == []
    e.feed(text="niente", sender="!000000cc")  # solo "dropped" cambia: nessun evento
    await e.bot.pump()
    assert e.bot_events() == []


def test_reset_clears_queue():
    e = BotEnv()
    e.feed()
    e.bot.reset()
    assert queued(e) == 0


def test_installed_hook_and_periodic():
    from test_trace_scheduler import Env as TEnv, make_installed
    t = TEnv()
    rt, ctx = make_installed(t)
    assert isinstance(ctx.ext["bot"], Bot)
    assert ctx.ext["bot"].on_message in rt.message_hooks
    names = {p[0]: p for p in rt.periodic}
    assert names["bot_pump"][1] == 2.0 and names["bot_pump"][3] == 2.0
    assert "automation_bus" in names


def test_weather_lookup_reads_recent_environment_metrics():
    from meshlens.bot import weather_lookup
    from meshlens.db import connect
    from meshlens.store import Store
    conn = connect(":memory:")
    st = Store(conn)
    st.add_metrics(0x99, T0 - 8000, "environment", {"temperature": 10.0})
    st.add_metrics(0x99, T0 - 100, "environment", {"temperature": 18.5,
                                                    "relative_humidity": 60.0})
    st.add_metrics(0x99, T0 - 50, "environment", {"temperature": 19.0})
    st.add_metrics(0x99, T0 - 10, "device", {"voltage": 4.0})
    assert weather_lookup(conn, 0x99, T0) == {"temperature": 19.0, "relative_humidity": 60.0}
    assert weather_lookup(conn, 0x98, T0) == {}
