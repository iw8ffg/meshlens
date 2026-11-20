import asyncio
import threading
from types import SimpleNamespace

import pytest

from meshlens.pubsub_hub import PubSubHub
from meshlens.radio import RadioConnector

CFG = {"id": "r1a2b3c4d", "kind": "usb", "address": "COM5"}
MY_NUM = 0xA1B2C3D4
PEER = "!00000042"


class FakeIface:
    def __init__(self, channels=None):
        self.nodes = {
            "!a1b2c3d4": {"num": MY_NUM, "user": {"longName": "Heltec base",
                                                    "shortName": "HB", "hwModel": "HELTEC_V3"}},
            PEER: {"num": 0x42, "user": {"longName": "Altro", "shortName": "AL"},
                   "position": {"latitude": 45.46, "longitude": 9.19}},
        }
        self.myInfo = SimpleNamespace(my_node_num=MY_NUM)
        self.localNode = SimpleNamespace(channels=channels if channels is not None else [
            SimpleNamespace(index=0, role="PRIMARY", settings=SimpleNamespace(name="")),
            SimpleNamespace(index=1, role="SECONDARY", settings=SimpleNamespace(name="Amici")),
            SimpleNamespace(index=2, role="DISABLED", settings=SimpleNamespace(name="")),
        ])
        self.sent = []
        self.closed = 0
        self.send_thread = None
        self.next_id = 1000

    def sendText(self, text, destinationId="^all", wantAck=False, channelIndex=0, **kw):
        self.send_thread = threading.current_thread()
        self.sent.append((text, destinationId, wantAck, channelIndex))
        self.next_id += 1
        return SimpleNamespace(id=self.next_id)

    def close(self):
        self.closed += 1


class FakePubSub:
    def __init__(self):
        self.subs = {}

    def subscribe(self, listener, topic):
        self.subs[topic] = listener


class Harness:
    def __init__(self, factory):
        self.loop = asyncio.get_running_loop()
        self.pubsub = FakePubSub()
        self.hub = PubSubHub(self.loop, self.pubsub)
        self.hub.start()
        self.events, self.states, self.acks, self.sleeps = [], [], [], []
        self.now = 1000.0
        self.gate = asyncio.Event()  # se non impostato blocca lo sleep
        self.gate.set()
        self.factory_calls = 0
        self._factory = factory

        async def sleep(delay):
            self.sleeps.append(delay)
            await self.gate.wait()
            await asyncio.sleep(0)

        def factory_wrapper(cfg):
            self.factory_calls += 1
            return self._factory(cfg, self.factory_calls)

        self.conn = RadioConnector(
            CFG, self.hub, self.events.append, lambda s: self.states.append(s["state"]),
            lambda *a: self.acks.append(a), factory_wrapper,
            clock=lambda: self.now, sleep=sleep)

    async def until(self, cond, timeout=3.0):
        async def poll():
            while not cond():
                await asyncio.sleep(0.005)
        await asyncio.wait_for(poll(), timeout)


def ack_pkt(rid, sender, reason="NONE"):
    return {"from": sender, "decoded": {"portnum": "ROUTING_APP", "requestId": rid,
                                         "routing": {"errorReason": reason}}}


async def connected(h):
    await h.conn.start()
    await h.until(lambda: h.conn.state()["state"] == "connected")


async def test_connect_ok_reads_info_and_emits_nodedb():
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    st = h.conn.state()
    assert h.states[:2] == ["connecting", "connected"]
    assert (st["my_node_id"], st["my_node_name"]) == ("!a1b2c3d4", "Heltec base")
    assert st["channels"] == [{"index": 0, "name": "Primario", "role": "PRIMARY"},
                              {"index": 1, "name": "Amici", "role": "SECONDARY"}]
    assert {e.kind for e in h.events} == {"nodeinfo", "position"}
    assert all(e.radio_id == CFG["id"] and e.source == "rf" for e in h.events)
    await h.conn.stop()
    assert iface.closed == 1 and h.conn.state()["state"] == "disconnected"


async def test_connect_error_then_reconnecting_with_backoff():
    def factory(cfg, n):
        if n <= 6:
            raise PermissionError(13, "Access is denied")
        return FakeIface()
    h = Harness(factory)
    await connected(h)
    assert h.sleeps == [2, 5, 10, 30, 60, 60]
    assert h.states[:3] == ["connecting", "error", "reconnecting"]
    await h.conn.stop()


async def test_error_messages():
    cases = [
        (PermissionError(13, "x"), "Porta in uso da un altro programma (chiudi l'app o la CLI Meshtastic)"),
        (FileNotFoundError("x"), "Porta non trovata: radio scollegata?"),
        (SystemExit(1), "Errore di connessione: SystemExit"),
        (ValueError("boh"), "Errore di connessione: ValueError"),
    ]
    for exc, msg in cases:
        def factory(cfg, n, exc=exc):
            raise exc
        h = Harness(factory)
        h.gate.clear()
        await h.conn.start()
        await h.until(lambda: h.conn.state()["state"] == "reconnecting")
        assert h.conn.state()["error"] == msg
        await h.conn.stop()

    class BLEError(Exception):
        pass

    def ble(cfg, n):
        raise BLEError("No Meshtastic BLE peripheral with identifier found")
    h = Harness(ble)
    h.gate.clear()
    await h.conn.start()
    await h.until(lambda: h.conn.state()["state"] == "reconnecting")
    assert h.conn.state()["error"] == "Radio Bluetooth non trovata: è accesa e vicina?"
    await h.conn.stop()


async def test_lost_closes_and_recreates():
    ifaces = []

    def factory(cfg, n):
        ifaces.append(FakeIface())
        return ifaces[-1]
    h = Harness(factory)
    await connected(h)
    h.hub._on_lost(ifaces[0])
    await h.until(lambda: h.factory_calls == 2 and h.conn.state()["state"] == "connected")
    assert ifaces[0].closed == 1 and h.sleeps == [2]
    assert "reconnecting" in h.states
    await h.conn.stop()


async def test_packet_from_other_interface_ignored():
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    n = len(h.events)
    pkt = {"from": 0x42, "to": 0xFFFFFFFF, "id": 5, "decoded": {
        "portnum": "TEXT_MESSAGE_APP", "text": "ciao"}}
    h.pubsub.subs["meshtastic.receive"](pkt, FakeIface())
    await asyncio.sleep(0.05)
    assert len(h.events) == n
    h.pubsub.subs["meshtastic.receive"](pkt, iface)
    await h.until(lambda: len(h.events) == n + 1)
    assert h.events[-1].kind == "text"
    await h.conn.stop()
    h.pubsub.subs["meshtastic.receive"](pkt, iface)  # annullata la registrazione
    await asyncio.sleep(0.05)
    assert len(h.events) == n + 1


async def test_send_text_runs_in_thread_and_returns_id():
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    pid = await h.conn.send_text("ciao", 1, PEER)
    assert pid == 1001
    assert iface.sent == [("ciao", PEER, True, 1)]
    assert iface.send_thread is not threading.main_thread()
    pid2 = await h.conn.send_text("a tutti", 0, None)
    assert iface.sent[-1] == ("a tutti", "^all", True, 0)
    h.now += 100
    h.conn.check_acks()
    assert [a[1] for a in h.acks] == [pid]  # il broadcast non scade
    assert pid2 not in [a[1] for a in h.acks]
    await h.conn.stop()


async def test_send_text_not_connected():
    h = Harness(lambda cfg, n: FakeIface())
    with pytest.raises(RuntimeError, match="non connessa"):
        await h.conn.send_text("x", 0, None)


async def test_acks():
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    a, b, c, d = [await h.conn.send_text("m", 0, PEER) for _ in range(4)]
    h.conn.on_packet(ack_pkt(a, 0x42))
    h.conn.on_packet(ack_pkt(b, 0x42, "NO_RESPONSE"))
    h.conn.on_packet(ack_pkt(c, MY_NUM))  # ack dal nodo locale: ignorato
    h.conn.on_packet(ack_pkt(999, 0x42))  # id sconosciuto
    assert h.acks == [(CFG["id"], a, True, None), (CFG["id"], b, False, "NO_RESPONSE")]
    h.now += 59
    h.conn.check_acks()
    assert len(h.acks) == 2
    h.now += 1
    h.conn.check_acks()
    assert h.acks[2:] == [(CFG["id"], c, False, "TIMEOUT"), (CFG["id"], d, False, "TIMEOUT")]
    h.conn.check_acks()
    assert len(h.acks) == 4
    await h.conn.stop()


async def test_stop_during_reconnecting_is_immediate():
    def factory(cfg, n):
        raise FileNotFoundError("COM5")
    h = Harness(factory)
    h.gate.clear()  # lo sleep non termina mai
    await h.conn.start()
    await h.until(lambda: h.conn.state()["state"] == "reconnecting")
    await asyncio.wait_for(h.conn.stop(), 1.0)
    assert h.conn.state()["state"] == "disconnected"


def test_hub_start_subscribes_once():
    loop = asyncio.new_event_loop()
    try:
        ps = FakePubSub()
        hub = PubSubHub(loop, ps)
        hub.start()
        hub.start()
        assert set(ps.subs) == {"meshtastic.receive", "meshtastic.connection.lost",
                                "meshtastic.connection.established"}
    finally:
        loop.close()
