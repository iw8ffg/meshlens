import asyncio

from meshtastic.protobuf import portnums_pb2

from helpers import make_envelope
from meshlens.crypto import DEFAULT_KEY
from meshlens.mqtt_client import MqttConnector
from meshlens.mqtt_decode import EnvelopeDecoder

CFG = {"host": "h", "port": 1883, "username": "u", "password": "p",
       "topics": ["msh/EU_868/#"], "extra_keys": []}


class FakeClient:
    def __init__(self, client_id=None, fail=False):
        self.client_id = client_id
        self.fail = fail
        self.subscribed = []

    def username_pw_set(self, *a): pass
    def reconnect_delay_set(self, *a): pass
    def loop_start(self): pass
    def loop_stop(self): pass
    def disconnect(self): pass

    def connect_async(self, *a, **k):
        if self.fail:
            raise OSError("rete assente")

    def subscribe(self, topic, qos=0):
        self.subscribed.append((topic, qos))

    def publish(self, *a, **k):
        raise AssertionError("MeshLens non deve mai pubblicare")


async def test_subscribes_on_connect():
    clients = []

    def factory(cid):
        clients.append(FakeClient(cid))
        return clients[-1]

    c = MqttConnector(CFG, EnvelopeDecoder([DEFAULT_KEY]), asyncio.get_running_loop(),
                      lambda ev: None, client_factory=factory)
    c.start()
    assert clients[0].client_id.startswith("meshlens-")
    c._on_connect(clients[0], None, None, 0, None)
    assert clients[0].subscribed == [("msh/EU_868/#", 0)]
    assert c.status()["connected"] is True


async def test_on_message_delivers_event_on_loop():
    got = asyncio.Queue()
    c = MqttConnector(CFG, EnvelopeDecoder([DEFAULT_KEY]), asyncio.get_running_loop(),
                      got.put_nowait, client_factory=FakeClient)
    c.start()

    class Msg:
        topic = "msh/EU_868/2/e/LongFast/!00000001"
        payload = make_envelope(portnums_pb2.TEXT_MESSAGE_APP, b"ciao")

    await asyncio.get_running_loop().run_in_executor(None, c._on_message, None, None, Msg)
    ev = await asyncio.wait_for(got.get(), 2)
    assert ev.from_node == 0xa1b2c3d4
    assert c.status()["msgs_per_s"] > 0


async def test_start_without_network_does_not_raise():
    c = MqttConnector(CFG, EnvelopeDecoder([DEFAULT_KEY]), asyncio.get_running_loop(),
                      lambda ev: None, client_factory=lambda cid: FakeClient(cid, fail=True))
    c.start()
    assert c.status()["connected"] is False


async def test_refused_connack_does_not_connect_or_subscribe():
    from paho.mqtt.reasoncodes import ReasonCode
    from paho.mqtt.packettypes import PacketTypes
    client = FakeClient()
    c = MqttConnector(CFG, EnvelopeDecoder([DEFAULT_KEY]), asyncio.get_running_loop(),
                      lambda ev: None, client_factory=lambda cid: client)
    c.start()
    c._on_connect(client, None, None, ReasonCode(PacketTypes.CONNACK, "Bad user name or password"), None)
    assert c.status()["connected"] is False
    assert client.subscribed == []


def _connector(cfg=CFG, factory=FakeClient):
    c = MqttConnector(cfg, EnvelopeDecoder([DEFAULT_KEY]), asyncio.get_running_loop(),
                      lambda ev: None, client_factory=factory)
    c.start()
    return c


async def test_status_reports_connected_since_and_reconnects(monkeypatch):
    from meshlens import mqtt_client
    c = _connector()
    assert c.status()["connected_since"] is None and c.status()["reconnects"] == 0
    clock = iter([1000.0, 2000.0])
    monkeypatch.setattr(mqtt_client.time, "time", lambda: next(clock))
    c._on_connect(c._client, None, None, 0, None)
    c._on_connect(c._client, None, None, 0, None)
    monkeypatch.undo()
    st = c.status()
    assert st["connected_since"] == 2000.0 and st["reconnects"] == 1


async def test_refused_connack_sets_last_error():
    from paho.mqtt.reasoncodes import ReasonCode
    from paho.mqtt.packettypes import PacketTypes
    c = _connector()
    c._on_connect(c._client, None, None, ReasonCode(PacketTypes.CONNACK, "Bad user name or password"), None)
    st = c.status()
    assert st["last_error"] == "Utente o password MQTT rifiutati" and st["last_error_at"] > 0
    c._on_connect(c._client, None, None, ReasonCode(PacketTypes.CONNACK, "Server unavailable"), None)
    assert c.status()["last_error"].startswith("Connessione rifiutata dal broker:")


async def test_network_error_sets_last_error():
    c = _connector(factory=lambda cid: FakeClient(cid, fail=True))
    assert c.status()["last_error"].startswith("Broker non raggiungibile")


async def test_unexpected_disconnect_sets_last_error():
    c = _connector()
    c._on_connect(c._client, None, None, 0, None)
    c._on_disconnect(c._client, None, None, 7, None)
    assert c.status()["last_error"] == "Connessione persa: 7"


async def test_last_error_never_contains_credentials():
    cfg = {**CFG, "username": "mario-rossi", "password": "s3gr3t0-xyz"}

    class Leaky(FakeClient):
        def connect_async(self, *a, **k):
            raise OSError("fallito con mario-rossi:s3gr3t0-xyz@broker")

    c = _connector(cfg, Leaky)
    err = c.status()["last_error"]
    assert "s3gr3t0-xyz" not in err and "mario-rossi" not in err and "Broker non raggiungibile" in err
    c._on_disconnect(c._client, None, None, "perso s3gr3t0-xyz", None)
    c._connected = True
    c._on_disconnect(c._client, None, None, "perso s3gr3t0-xyz", None)
    assert "s3gr3t0-xyz" not in c.status()["last_error"]
    import json
    assert "s3gr3t0-xyz" not in json.dumps(c.status())


async def test_last_msg_age_and_drop_reasons():
    c = _connector()
    assert c.status()["last_msg_age_s"] is None

    class Bad:
        topic = "msh/EU_868/2/e/LongFast/!00000001"
        payload = b"\x00\x01 non protobuf"

    class Good:
        topic = "msh/EU_868/2/e/LongFast/!00000001"
        payload = make_envelope(portnums_pb2.TEXT_MESSAGE_APP, b"ciao")

    c._on_message(None, None, Bad)
    c._on_message(None, None, Good)
    st = c.status()
    assert st["drops"]["not_protobuf"] == 1 and st["decoded"] == 1
    assert st["last_msg_age_s"] >= 0
    assert set(st["drops"]) == {"empty", "unsupported_port", "undecodable", "json_topic", "not_protobuf"}


async def test_status_reports_queue_counters():
    from meshlens.inbox import EventInbox
    loop = asyncio.get_running_loop()
    got = []
    c = MqttConnector(CFG, EnvelopeDecoder([DEFAULT_KEY]), loop, got.append,
                      client_factory=FakeClient)
    st = c.status()
    assert st["queue_dropped"] == 0 and st["queue_size"] == 0
    c.inbox = EventInbox(loop, got.append, maxsize=2)
    for i in range(3):
        c.inbox.put(i)
    st = c.status()
    assert st["queue_dropped"] == 1 and st["queue_size"] == 2
    await asyncio.sleep(0)
    assert got == [1, 2] and c.status()["queue_size"] == 0


class TlsClient(FakeClient):
    def __init__(self, client_id=None, fail=False):
        super().__init__(client_id, fail)
        self.calls = []

    def tls_set_context(self, ctx):
        self.calls.append("tls")

    def connect_async(self, *a, **k):
        self.calls.append("connect")
        super().connect_async(*a, **k)


async def _start(cfg, client):
    c = MqttConnector(cfg, EnvelopeDecoder([DEFAULT_KEY]), asyncio.get_running_loop(),
                      lambda ev: None, client_factory=lambda cid: client)
    c.start()
    return c


async def test_tls_context_set_only_when_enabled():
    on = TlsClient()
    await _start({**CFG, "tls": True}, on)
    assert on.calls == ["tls", "connect"]
    off = TlsClient()
    await _start({**CFG, "tls": False}, off)
    assert off.calls == ["connect"]


async def test_connect_fail_sets_error_without_secrets():
    cfg = {**CFG, "password": "segreta", "username": "mario"}
    client = TlsClient()
    c = await _start(cfg, client)
    client.on_connect_fail(client, None)
    err = c.status()["last_error"]
    assert err == "Connessione non riuscita: controlla host, porta e TLS"
    assert "segreta" not in err
    c.set_error("boom segreta mario")  # il segreto del broker stesso viene tolto
    assert "segreta" not in c.status()["last_error"] and "mario" not in c.status()["last_error"]


async def test_log_lines_use_broker_label(caplog):
    caplog.set_level("INFO")
    c = await _start({**CFG, "name": "Mio broker"}, FakeClient())
    c._on_connect(c._client, None, None, 0, None)
    assert any("Mio broker" in r.getMessage() and "connesso" in r.getMessage()
               for r in caplog.records)
