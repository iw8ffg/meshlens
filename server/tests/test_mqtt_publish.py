"""Invio di testi via MQTT: pacchetto valido, limiti, conferma, nessuna pubblicazione accidentale."""
import pytest
from meshtastic.protobuf import mqtt_pb2

from helpers import channel_hash as helper_hash
from meshlens.api import AppContext
from meshlens.auth import Auth
from meshlens.bus import Bus
from meshlens.crypto import DEFAULT_KEY
from meshlens.db import connect
from meshlens.dedup import Deduplicator
from meshlens.geo import CountryLocator
from meshlens.ingest import Ingestor
from meshlens.live import LiveState
from meshlens.mqtt_decode import EnvelopeDecoder, channel_hash
from meshlens.mqtt_publish import (MqttSendError, MqttSender, build_envelope, confirm_text,
                                   region_from_topics)
from meshlens.settings import DEFAULTS, default_broker, load_settings, save_settings
from meshlens.store import Store
from test_api import client, logged

ME = "!a1b2c3d4"
NUM = 0xA1B2C3D4


class FakeConnector:
    def __init__(self, ok=True):
        self.ok = ok
        self.published = []
        self.callbacks = []

    def publish(self, topic, payload, on_result=None):
        if not self.ok:
            return False
        self.published.append((topic, payload))
        self.callbacks.append(on_result)
        return True


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make_sender(conn=None, settings=None, radios=None, clock=None, recorded=None,
                connectors=None):
    """connectors: id broker -> connettore; senza, ogni broker usa conn."""
    s = {**DEFAULTS, "mqtt_send_confirmed": True, "mqtt_node_id": ME}
    s.update(settings or {})
    if "mqtt_brokers" not in (settings or {}):  # broker predefinito migrato dal vecchio mqtt
        s["mqtt_brokers"] = [default_broker(s["mqtt"])]
    rec = [] if recorded is None else recorded

    def record(**kw):
        rec.append(kw)
        return {"key": "k", "text": kw["text"], "via": "mqtt"}

    get = (lambda bid: connectors.get(bid)) if connectors is not None else (lambda bid: conn)
    return MqttSender(get, lambda: s, lambda: radios or [], clock or Clock(), record)


SQUADRA_PSK = "ESIzRFVmd4iZqrvM3e7/ABEiM0RVZneImaq7zN3u/wA="  # 32 byte


def b1(**over):
    b = {"id": "b1", "name": "Broker uno", "enabled": True, "host": "broker.esempio.it",
         "port": 1883, "tls": False, "encryption": True, "username": "", "password": "",
         "topics": ["msh/EU_868/IT/#"], "channels": [{"name": "Squadra", "psk": SQUADRA_PSK}],
         "extra_keys": []}
    b.update(over)
    return b


def two_brokers(**over):
    """Broker predefinito + b1, con la conferma della prima volta gia' data per entrambi."""
    return {"mqtt_brokers": [default_broker(DEFAULTS["mqtt"]), b1(**over)],
            "mqtt_send_confirmed_brokers": ["b1"]}


def expect(status, code, fn):
    with pytest.raises(MqttSendError) as e:
        fn()
    assert e.value.status == status and e.value.code == code
    return e.value


def test_roundtrip_with_decoder():
    raw = build_envelope("Ciao àè", NUM, 0xFFFFFFFF, "LongFast", DEFAULT_KEY, 12345, ME)
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode("msh/EU_868/2/e/LongFast/" + ME, raw, 1.0)
    assert ev.kind == "text" and ev.payload.text == "Ciao àè"
    assert ev.from_node == NUM and ev.to_node == 0xFFFFFFFF and ev.packet_id == 12345
    assert ev.channel == "LongFast" and ev.gateway_id == ME


def test_packet_fields_and_channel_hash():
    raw = build_envelope("x", NUM, 0x11223344, "LongFast", DEFAULT_KEY, 7, ME)
    env = mqtt_pb2.ServiceEnvelope.FromString(raw)
    p = env.packet
    assert p.channel == channel_hash("LongFast", DEFAULT_KEY) == helper_hash("LongFast", DEFAULT_KEY)
    assert p.hop_limit == 3 and p.hop_start == 3 and not p.want_ack
    assert p.to == 0x11223344 and getattr(p, "from") == NUM and p.id == 7
    assert env.channel_id == "LongFast" and env.gateway_id == ME
    assert p.encrypted and p.WhichOneof("payload_variant") == "encrypted"


def test_region_from_topics():
    assert region_from_topics(["msh/US/#"]) == "US"
    assert region_from_topics(["msh/EU_868/IT/#", "msh/US/#"]) == "EU_868"
    assert region_from_topics([]) == "EU_868"
    assert region_from_topics(["altro/x"]) == "EU_868"


def test_send_publishes_on_expected_topic_and_records():
    conn, rec = FakeConnector(), []
    msg = make_sender(conn, recorded=rec).send("Ciao", "LongFast", None, False)
    topic, payload = conn.published[0]
    assert topic == f"msh/EU_868/2/e/LongFast/{ME}"
    assert msg["text"] == "Ciao"
    assert rec[0]["from_num"] == NUM and rec[0]["to_num"] == 0xFFFFFFFF
    assert rec[0]["channel"] == "LongFast"
    env = mqtt_pb2.ServiceEnvelope.FromString(payload)
    assert env.packet.id == rec[0]["packet_id"] != 0


def test_direct_message_target():
    conn, rec = FakeConnector(), []
    make_sender(conn, recorded=rec).send("Ciao", "LongFast", "!00000042", False)
    env = mqtt_pb2.ServiceEnvelope.FromString(conn.published[0][1])
    assert env.packet.to == 0x42 and rec[0]["to_num"] == 0x42


def test_text_limits_no_publish():
    conn = FakeConnector()
    s = make_sender(conn)
    expect(400, "invalid_text", lambda: s.send("", "LongFast", None, False))
    expect(400, "invalid_text", lambda: s.send("   ", "LongFast", None, False))
    expect(400, "invalid_text", lambda: s.send("a" * 201, "LongFast", None, False))
    expect(400, "invalid_text", lambda: s.send("è" * 101, "LongFast", None, False))  # 202 byte
    assert conn.published == []
    s.send("a" * 200, "LongFast", None, False)
    assert len(conn.published) == 1


def test_bad_target_and_channel_no_publish():
    conn = FakeConnector()
    s = make_sender(conn)
    expect(400, "invalid_target", lambda: s.send("x", "LongFast", "zz", False))
    expect(400, "invalid_channel", lambda: s.send("x", "", None, False))
    expect(400, "invalid_channel", lambda: s.send("x", "a/b", None, False))
    assert conn.published == []


def test_confirm_required_first_time_no_publish():
    conn, rec = FakeConnector(), []
    s = make_sender(conn, settings={"mqtt_send_confirmed": False}, recorded=rec)
    e = expect(409, "confirm_required", lambda: s.send("x", "LongFast", None, False))
    assert "pubblico" in e.message and "mqtt.meshtastic.org" in e.message
    assert conn.published == [] and rec == []
    s.send("x", "LongFast", None, True)
    assert len(conn.published) == 1


def test_rate_limit_10s_and_hourly():
    conn, clock = FakeConnector(), Clock()
    s = make_sender(conn, clock=clock)
    s.send("1", "LongFast", None, False)
    assert expect(429, "rate_limited", lambda: s.send("2", "LongFast", None, False)).message == "Attendi 10 s"
    clock.t += 4
    assert expect(429, "rate_limited", lambda: s.send("2", "LongFast", None, False)).message == "Attendi 6 s"
    assert len(conn.published) == 1
    clock.t += 6
    for _ in range(29):
        s.send("n", "LongFast", None, False)
        clock.t += 10
    assert len(conn.published) == 30
    # 30 messaggi nell'ultima ora: il successivo e' rifiutato anche oltre i 10 s
    e = expect(429, "rate_limited", lambda: s.send("n", "LongFast", None, False))
    assert e.message.startswith("Attendi ") and len(conn.published) == 30
    clock.t += 3600
    s.send("ok", "LongFast", None, False)
    assert len(conn.published) == 31


def test_disconnected_503_no_record_and_no_rate_consumed():
    conn, rec = FakeConnector(ok=False), []
    s = make_sender(conn, recorded=rec)
    expect(503, "mqtt_disconnected", lambda: s.send("x", "LongFast", None, False))
    assert rec == []
    conn.ok = True  # un publish rifiutato non consuma il limite di frequenza
    s.send("x", "LongFast", None, False)
    assert len(conn.published) == 1
    expect(503, "mqtt_disconnected", lambda: make_sender(None).send("x", "LongFast", None, False))


def test_unknown_own_node_400_no_publish():
    conn = FakeConnector()
    s = make_sender(conn, settings={"mqtt_node_id": ""},
                    radios=[{"state": "disconnected", "my_node_id": None}])
    e = expect(400, "unknown_node", lambda: s.send("x", "LongFast", None, False))
    assert "Collega una radio" in e.message
    assert conn.published == []


def test_own_node_from_first_connected_radio():
    conn, rec = FakeConnector(), []
    radios = [{"state": "connecting", "my_node_id": None},
              {"state": "connected", "my_node_id": "!00000099"}]
    make_sender(conn, settings={"mqtt_node_id": ""}, radios=radios, recorded=rec).send(
        "x", "LongFast", None, False)
    assert conn.published[0][0].endswith("/!00000099") and rec[0]["from_num"] == 0x99


def test_settings_node_id_beats_radio_and_region_from_topic():
    conn = FakeConnector()
    s = make_sender(conn, settings={"mqtt": {**DEFAULTS["mqtt"], "topics": ["msh/US/#"]}},
                    radios=[{"state": "connected", "my_node_id": "!00000099"}])
    s.send("x", "LongFast", None, False)
    assert conn.published[0][0] == f"msh/US/2/e/LongFast/{ME}"


def test_outgoing_mqtt_message_and_echo_not_duplicated():
    out = []
    ing = Ingestor(LiveState(), Store(connect(":memory:")), Deduplicator(), CountryLocator(),
                   lambda: dict(DEFAULTS), out.append)
    raw = build_envelope("Ciao", NUM, 0xFFFFFFFF, "LongFast", DEFAULT_KEY, 555, ME)
    m = ing.record_outgoing_mqtt(from_num=NUM, to_num=0xFFFFFFFF, packet_id=555, text="Ciao",
                                 channel="LongFast", now=100.0)
    assert m["direction"] == "out" and m["via"] == "mqtt" and m["status"] == "sending"
    assert m["source"] == "mqtt" and m["channel"] == "LongFast" and m["from"] == ME
    assert m["to"] == "!ffffffff"
    assert len(ing.live.messages) == 1 and len(out) == 1
    # l'eco dal broker (stesso from/id) non crea un secondo messaggio
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode("msh/EU_868/2/e/LongFast/" + ME, raw, 101.0)
    ing.handle(ev)
    assert len(ing.live.messages) == 1 and len(out) == 1


def make_ctx(conn, sender):
    async def on_changed(_s):
        return None
    return AppContext(live=LiveState(), store=Store(conn), auth=Auth(conn), bus=Bus(),
                      locator=CountryLocator(), conn=conn, mqtt_status=lambda: {},
                      on_settings_changed=on_changed, mqtt_sender=sender)


async def test_route_requires_auth():
    conn = connect(":memory:")
    async with client(make_ctx(conn, make_sender(FakeConnector()))) as c:
        assert (await c.post("/api/mqtt/send", json={"text": "x"})).status_code == 401


async def test_route_flow():
    db, conn = connect(":memory:"), FakeConnector()
    save_settings(db, {"mqtt_node_id": ME})
    s = MqttSender(lambda bid: conn, lambda: load_settings(db), lambda: [], Clock(),
                   lambda **kw: {"key": "k", "direction": "out", "via": "mqtt",
                                 "status": "sent", "text": kw["text"]})
    async with logged(make_ctx(db, s)) as c:
        r = await c.post("/api/mqtt/send", json={"text": "x", "channel": "LongFast"})
        assert r.status_code == 409 and r.json()["code"] == "confirm_required"
        assert conn.published == []
        r = await c.post("/api/mqtt/send", json={"text": "x", "confirm_public": True})
        assert r.status_code == 202 and r.json()["message"]["via"] == "mqtt"
        assert load_settings(db)["mqtt_send_confirmed"] is True
        # ricordata: niente piu' conferma, ma il limite di 10 s scatta
        r = await c.post("/api/mqtt/send", json={"text": "y"})
        assert r.status_code == 429 and r.json()["code"] == "rate_limited"
        assert (await c.post("/api/mqtt/send", json={"text": ""})).status_code == 400
        assert len(conn.published) == 1


def test_settings_validation():
    db = connect(":memory:")
    assert save_settings(db, {"mqtt_node_id": "!a1b2c3d4"})["mqtt_node_id"] == "!a1b2c3d4"
    assert save_settings(db, {"mqtt_node_id": ""})["mqtt_node_id"] == ""
    assert save_settings(db, {"mqtt_send_confirmed": True})["mqtt_send_confirmed"] is True
    for bad in ("a1b2c3d4", "!xyz", "!12345", 5):
        with pytest.raises(ValueError):
            save_settings(db, {"mqtt_node_id": bad})
    with pytest.raises(ValueError):
        save_settings(db, {"mqtt_send_confirmed": "si"})


async def test_connector_publish_qos1_and_false_when_disconnected():
    import asyncio

    from meshlens.mqtt_client import MqttConnector

    calls = []

    class Client:
        def username_pw_set(self, *a): pass
        def reconnect_delay_set(self, *a): pass
        def loop_start(self): pass
        def connect_async(self, *a, **k): pass
        def publish(self, topic, payload, qos=0):
            calls.append((topic, payload, qos))
            return type("I", (), {"rc": 0})()

    c = MqttConnector({"host": "h", "port": 1, "username": "", "password": "", "topics": []},
                      EnvelopeDecoder([DEFAULT_KEY]), asyncio.get_running_loop(), lambda e: None,
                      client_factory=lambda cid: Client())
    assert c.publish("t", b"x") is False  # non avviato
    c.start()
    assert c.publish("t", b"x") is False  # non connesso
    assert calls == []
    c._connected = True
    assert c.publish("t", b"x") is True and calls == [("t", b"x", 1)]


def test_learned_extra_key_used_for_sending():
    from meshlens.crypto import expand_psk
    extra = expand_psk("AQ==")[:-1] + b"\x77"
    dec = EnvelopeDecoder([DEFAULT_KEY, extra])
    from helpers import make_envelope
    from meshtastic.protobuf import mesh_pb2, portnums_pb2
    raw = make_envelope(portnums_pb2.TEXT_MESSAGE_APP, b"hi", channel_id="Privato", key=extra)
    assert dec.decode("msh/EU_868/2/e/Privato/!1", raw, 1.0) is not None
    conn = FakeConnector()
    s = make_sender(conn)
    s.key_for = lambda broker, channel: dec.channel_keys.get(channel)
    s.send("segreto", "Privato", None, False)
    ev = EnvelopeDecoder([extra]).decode("t", conn.published[0][1], 1.0)
    assert ev.payload.text == "segreto"


def test_unknown_custom_channel_refused_but_presets_ok():
    conn = FakeConnector()
    s = make_sender(conn)
    e = expect(400, "unknown_channel_key", lambda: s.send("x", "Privato", None, False))
    assert "Privato" in e.message and conn.published == []
    s.send("x", "ShortTurbo", None, False)
    assert len(conn.published) == 1


def test_control_chars_and_bad_radio_node():
    conn = FakeConnector()
    s = make_sender(conn)
    expect(400, "invalid_text", lambda: s.send("a\x00b", "LongFast", None, False))
    expect(400, "invalid_text", lambda: s.send("a\x1bb", "LongFast", None, False))
    s.send("a\nb\tc", "LongFast", None, False)
    s2 = make_sender(conn, settings={"mqtt_node_id": ""},
                     radios=[{"state": "connected", "my_node_id": "!zz"}])
    expect(400, "unknown_node", lambda: s2.send("x", "LongFast", None, False))
    assert len(conn.published) == 1


def test_root_from_topics_uses_subscribed_root():
    from meshlens.mqtt_publish import root_from_topics
    assert root_from_topics(["msh/EU_868/IT/#"]) == "msh/EU_868/IT"
    assert root_from_topics(["msh/EU_868/#"]) == "msh/EU_868"
    assert root_from_topics(["msh/EU_868/IT/2/e/LongFast/#"]) == "msh/EU_868/IT"
    assert root_from_topics(["msh/+/2/e/#"]) == "msh/EU_868"
    assert root_from_topics([]) == "msh/EU_868"


# ---- broker multipli ----

def test_send_on_custom_channel_without_traffic():
    from meshlens.crypto import expand_psk
    conn, rec = FakeConnector(), []
    s = make_sender(conn, settings=two_brokers(), recorded=rec)
    s.send("Ciao squadra", "Squadra", None, False, broker="b1")
    topic, payload = conn.published[0]
    assert topic == f"msh/EU_868/IT/2/e/Squadra/{ME}"
    k = expand_psk(SQUADRA_PSK)
    env = mqtt_pb2.ServiceEnvelope.FromString(payload)
    assert env.packet.WhichOneof("payload_variant") == "encrypted"
    assert env.packet.channel == channel_hash("Squadra", k)
    ev = EnvelopeDecoder([DEFAULT_KEY, k]).decode(topic, payload, 1.0)
    assert ev.payload.text == "Ciao squadra"
    assert rec[0]["broker"] == "b1" and rec[0]["channel"] == "Squadra"


def test_encryption_off_publishes_decoded():
    from meshlens.crypto import expand_psk
    conn = FakeConnector()
    make_sender(conn, settings=two_brokers(encryption=False)).send(
        "ciao", "Squadra", None, False, broker="b1")
    topic, payload = conn.published[0]
    p = mqtt_pb2.ServiceEnvelope.FromString(payload).packet
    assert p.WhichOneof("payload_variant") == "decoded"
    assert p.decoded.payload == b"ciao" and not p.encrypted
    assert p.channel == channel_hash("Squadra", expand_psk(SQUADRA_PSK))
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(topic, payload, 1.0)
    assert ev.payload.text == "ciao"


def test_envelope_with_empty_key_is_decoded():
    raw = build_envelope("x", NUM, 0xFFFFFFFF, "Aperto", b"", 9, ME)
    p = mqtt_pb2.ServiceEnvelope.FromString(raw).packet
    assert p.WhichOneof("payload_variant") == "decoded" and p.channel == channel_hash("Aperto", b"")


def test_default_broker_still_encrypted():
    conn, rec = FakeConnector(), []
    make_sender(conn, settings=two_brokers(), recorded=rec).send(
        "x", "LongFast", None, False, broker="default")
    p = mqtt_pb2.ServiceEnvelope.FromString(conn.published[0][1]).packet
    assert p.WhichOneof("payload_variant") == "encrypted"
    assert conn.published[0][0] == f"msh/EU_868/2/e/LongFast/{ME}"
    assert rec[0]["broker"] == "default"


def test_no_broker_uses_first_enabled():
    conn, rec = FakeConnector(), []
    st = two_brokers()
    st["mqtt_brokers"][0]["enabled"] = False
    make_sender(conn, settings={**st, "mqtt_send_confirmed_brokers": ["b1"]},
                recorded=rec).send("x", "LongFast", None, False)
    assert rec[0]["broker"] == "b1" and conn.published[0][0].startswith("msh/EU_868/IT/2/e/")


def test_unknown_or_disabled_broker_400():
    conn = FakeConnector()
    s = make_sender(conn, settings=two_brokers(enabled=False))
    e = expect(400, "unknown_broker", lambda: s.send("x", "LongFast", None, False, broker="b1"))
    assert e.message == "Broker non trovato o disattivato"
    expect(400, "unknown_broker", lambda: s.send("x", "LongFast", None, False, broker="nessuno"))
    st = {"mqtt_brokers": [{**default_broker(DEFAULTS["mqtt"]), "enabled": False}]}
    expect(400, "unknown_broker", lambda: make_sender(conn, settings=st).send(
        "x", "LongFast", None, False))
    assert conn.published == []


def test_unknown_channel_key_names_broker():
    s = make_sender(FakeConnector(), settings={**two_brokers(),
                                               "mqtt_send_confirmed_brokers": ["b1"]})
    e = expect(400, "unknown_channel_key",
               lambda: s.send("x", "Privato", None, False, broker="b1"))
    assert e.message == ("Non conosco la chiave del canale Privato su Broker uno: aggiungilo "
                         "ai canali del broker in Impostazioni")


def test_key_for_receives_broker_id():
    from meshlens.crypto import expand_psk
    k = expand_psk("Aw==")
    asked = []

    def key_for(broker, channel):
        asked.append((broker, channel))
        return k if (broker, channel) == ("b1", "Imparato") else None

    conn = FakeConnector()
    s = make_sender(conn, settings={**two_brokers(), "mqtt_send_confirmed_brokers": ["b1"]})
    s.key_for = key_for
    s.send("x", "Imparato", None, False, broker="b1")
    assert asked == [("b1", "Imparato")]
    assert EnvelopeDecoder([k]).decode("t", conn.published[0][1], 1.0).payload.text == "x"


def test_rate_limit_is_per_broker():
    conn = FakeConnector()
    s = make_sender(conn, settings={**two_brokers(), "mqtt_send_confirmed_brokers": ["b1"]})
    s.send("1", "LongFast", None, False, broker="default")
    s.send("2", "LongFast", None, False, broker="b1")
    expect(429, "rate_limited", lambda: s.send("3", "LongFast", None, False, broker="default"))
    assert len(conn.published) == 2


def test_disconnected_broker_does_not_consume_other_limits():
    conn, rec = FakeConnector(), []
    s = make_sender(settings={**two_brokers(), "mqtt_send_confirmed_brokers": ["b1"]},
                    recorded=rec, connectors={"default": conn, "b1": None})
    expect(503, "mqtt_disconnected", lambda: s.send("x", "LongFast", None, False, broker="b1"))
    s.send("x", "LongFast", None, False, broker="default")
    assert len(conn.published) == 1 and [r["broker"] for r in rec] == ["default"]


def test_confirmation_per_broker():
    conn = FakeConnector()
    s = make_sender(conn, settings={**two_brokers(), "mqtt_send_confirmed": True,
                                    "mqtt_send_confirmed_brokers": []})
    s.send("x", "LongFast", None, False, broker="default")
    e = expect(409, "confirm_required", lambda: s.send("x", "LongFast", None, False, broker="b1"))
    assert e.message == confirm_text("broker.esempio.it")
    assert "broker.esempio.it" in e.message and len(conn.published) == 1
    s2 = make_sender(conn, settings={**two_brokers(), "mqtt_send_confirmed": False,
                                     "mqtt_send_confirmed_brokers": ["b1"]})
    s2.send("x", "LongFast", None, False, broker="b1")
    expect(409, "confirm_required", lambda: s2.send("x", "LongFast", None, False, broker="default"))


def test_confirm_text_default_unchanged():
    from meshlens.mqtt_publish import CONFIRM_TEXT
    assert CONFIRM_TEXT == confirm_text("mqtt.meshtastic.org") == (
        "Il messaggio sarà pubblico sul broker mqtt.meshtastic.org e potrà essere "
        "ritrasmesso via radio dai gateway")


def test_root_from_selected_broker_topics():
    conn = FakeConnector()
    make_sender(conn, settings={**two_brokers(topics=["msh/US/#"]),
                                "mqtt_send_confirmed_brokers": ["b1"]}).send(
        "x", "LongFast", None, False, broker="b1")
    assert conn.published[0][0].startswith("msh/US/2/e/")


def test_send_with_lost_channel_psk_refused_never_clear():
    conn = FakeConnector()
    b = {**default_broker(DEFAULTS["mqtt"]), "channels": [{"name": "Privato", "psk": ""}]}
    s = make_sender(conn, settings={"mqtt_brokers": [b]})
    e = expect(400, "unknown_channel_key", lambda: s.send("x", "Privato", None, False))
    assert "non leggibile" in e.message and conn.published == []


def test_reply_roundtrip():
    raw = build_envelope("\U0001f44d", NUM, 0xFFFFFFFF, "LongFast", DEFAULT_KEY, 555, ME,
                         reply_id=99, emoji=True)
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode("msh/EU_868/2/e/LongFast/" + ME, raw, 1.0)
    assert ev.kind == "text" and ev.payload.text == "\U0001f44d"
    assert ev.payload.reply_id == 99 and ev.payload.emoji is True
    env = mqtt_pb2.ServiceEnvelope.FromString(
        build_envelope("ok", NUM, 0x42, "LongFast", b"", 556, ME, reply_id=99, emoji=True))
    from meshtastic.protobuf import portnums_pb2
    d = env.packet.decoded
    assert d.portnum == portnums_pb2.TEXT_MESSAGE_APP and d.reply_id == 99 and d.emoji == 1
    plain = mqtt_pb2.ServiceEnvelope.FromString(
        build_envelope("ok", NUM, 0x42, "LongFast", b"", 557, ME)).packet.decoded
    assert plain.reply_id == 0 and plain.emoji == 0


def test_reply_and_reaction_are_recorded():
    conn, rec = FakeConnector(), []
    s = make_sender(conn, recorded=rec, clock=Clock())
    s.send("risposta", "LongFast", "!00000042", False, reply_id=7)
    assert rec[0]["reply_id"] == 7 and rec[0]["emoji"] is False
    env = mqtt_pb2.ServiceEnvelope.FromString(conn.published[0][1])
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(conn.published[0][0], conn.published[0][1], 1.0)
    assert env.packet.encrypted and ev.payload.reply_id == 7 and ev.payload.emoji is False


def test_reaction_validation_no_publish():
    conn = FakeConnector()
    s = make_sender(conn)
    e = expect(400, "invalid_reaction", lambda: s.send("\U0001f44d", "LongFast", None, False,
                                                        emoji=True))
    assert e.message == "La reazione richiede il messaggio a cui reagire"
    e = expect(400, "invalid_reaction", lambda: s.send("ciao a tutti", "LongFast", None, False,
                                                        reply_id=5, emoji=True))
    assert e.message == "Reazione non valida"
    expect(400, "invalid_reaction", lambda: s.send("x" * 17, "LongFast", None, False,
                                                   reply_id=5, emoji=True))
    e = expect(400, "invalid_reaction", lambda: s.send("ok", "LongFast", None, False,
                                                        reply_id=2**32))
    assert e.message == "Messaggio di riferimento non valido"
    assert conn.published == []


def test_reaction_counts_for_rate_limit():
    conn, clock = FakeConnector(), Clock()
    s = make_sender(conn, clock=clock)
    s.send("\U0001f44d", "LongFast", None, False, reply_id=5, emoji=True)
    clock.t += 9
    e = expect(429, "rate_limited", lambda: s.send("testo", "LongFast", None, False))
    assert e.message == "Attendi 1 s" and len(conn.published) == 1


def test_reaction_needs_first_time_confirmation():
    conn = FakeConnector()
    s = make_sender(conn, settings={"mqtt_send_confirmed": False})
    expect(409, "confirm_required",
           lambda: s.send("\U0001f44d", "LongFast", None, False, reply_id=5, emoji=True))
    assert conn.published == []


async def test_route_forwards_reply_fields():
    db, conn, rec = connect(":memory:"), FakeConnector(), []
    save_settings(db, {"mqtt_node_id": ME, "mqtt_send_confirmed": True})

    def record(**kw):
        rec.append(kw)
        return {"key": "k", "text": kw["text"]}

    s = MqttSender(lambda bid: conn, lambda: load_settings(db), lambda: [], Clock(), record)
    async with logged(make_ctx(db, s)) as c:
        r = await c.post("/api/mqtt/send", json={"text": "x", "reply_id": 0})
        assert r.status_code == 422
        r = await c.post("/api/mqtt/send", json={"text": "x", "emoji": True})
        assert r.status_code == 400 and r.json()["code"] == "invalid_reaction"
        r = await c.post("/api/mqtt/send", json={"text": "\U0001f44d", "reply_id": 9,
                                                 "emoji": True})
        assert r.status_code == 202
        assert rec[0]["reply_id"] == 9 and rec[0]["emoji"] is True


def test_broker_result_is_routed_to_message_key():
    conn, results = FakeConnector(), []
    s = MqttSender(lambda bid: conn, lambda: {**DEFAULTS, "mqtt_send_confirmed": True,
                                              "mqtt_node_id": ME,
                                              "mqtt_brokers": [default_broker(DEFAULTS["mqtt"])]},
                   lambda: [], Clock(), lambda **kw: {"key": f"{kw['from_num']}:{kw['packet_id']}"},
                   on_result=lambda key, ok, err: results.append((key, ok, err)))
    m = s.send("ciao", "LongFast", None, False)
    conn.callbacks[0](False, "Il broker non ha confermato il messaggio")
    assert results == [(m["key"], False, "Il broker non ha confermato il messaggio")]
