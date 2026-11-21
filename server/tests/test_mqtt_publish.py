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
from meshlens.mqtt_publish import MqttSendError, MqttSender, build_envelope, region_from_topics
from meshlens.settings import DEFAULTS, load_settings, save_settings
from meshlens.store import Store
from test_api import client, logged

ME = "!a1b2c3d4"
NUM = 0xA1B2C3D4


class FakeConnector:
    def __init__(self, ok=True):
        self.ok = ok
        self.published = []

    def publish(self, topic, payload):
        if not self.ok:
            return False
        self.published.append((topic, payload))
        return True


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make_sender(conn=None, settings=None, radios=None, clock=None, recorded=None):
    s = {**DEFAULTS, "mqtt_send_confirmed": True, "mqtt_node_id": ME}
    s.update(settings or {})
    rec = [] if recorded is None else recorded

    def record(**kw):
        rec.append(kw)
        return {"key": "k", "text": kw["text"], "via": "mqtt"}

    return MqttSender(lambda: conn, lambda: s, lambda: radios or [], clock or Clock(), record)


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
    assert m["direction"] == "out" and m["via"] == "mqtt" and m["status"] == "sent"
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
    s = MqttSender(lambda: conn, lambda: load_settings(db), lambda: [], Clock(),
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


async def test_connector_publish_qos0_and_false_when_disconnected():
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
    assert c.publish("t", b"x") is True and calls == [("t", b"x", 0)]


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
    s.key_for = dec.channel_keys.get
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
