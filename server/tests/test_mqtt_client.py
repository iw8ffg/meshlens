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
