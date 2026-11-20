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
        self.close_block = None
        self.on_send = None

    def sendText(self, text, destinationId="^all", wantAck=False, channelIndex=0, **kw):
        self.send_thread = threading.current_thread()
        self.sent.append((text, destinationId, wantAck, channelIndex))
        self.next_id += 1
        if self.on_send:
            self.on_send(self.next_id)
        return SimpleNamespace(id=self.next_id)

    def close(self):
        self.closed += 1
        if self.close_block is not None:
            self.close_block.wait(5)


class FakePubSub:
    def __init__(self):
        self.subs = {}

    def subscribe(self, listener, topic):
        self.subs[topic] = listener

    def unsubscribe(self, listener, topic):
        assert self.subs.pop(topic) == listener


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


def test_hub_stop_unsubscribes_and_allows_restart():
    loop = asyncio.new_event_loop()
    try:
        ps = FakePubSub()
        hub = PubSubHub(loop, ps)
        hub.start()
        hub.stop()
        assert ps.subs == {}
        hub.stop()
        hub.start()
        assert len(ps.subs) == 3
    finally:
        loop.close()


async def test_ack_arriving_during_send_is_reconciled():
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    iface.on_send = lambda pid: h.loop.call_soon_threadsafe(
        h.conn.on_packet, ack_pkt(pid, 0x42))
    pid = await h.conn.send_text("m", 0, PEER)
    assert h.acks == [(CFG["id"], pid, True, None)]
    iface.on_send = lambda pid: h.loop.call_soon_threadsafe(
        h.conn.on_packet, ack_pkt(pid, 0x42, "NO_RESPONSE"))
    pid2 = await h.conn.send_text("m", 0, PEER)
    assert h.acks[-1] == (CFG["id"], pid2, False, "NO_RESPONSE")
    iface.on_send = lambda pid: h.loop.call_soon_threadsafe(
        h.conn.on_packet, ack_pkt(pid, MY_NUM))
    await h.conn.send_text("m", 0, PEER)
    assert len(h.acks) == 2  # ack locale: resta sent
    await h.conn.stop()


async def test_early_buffer_pruned():
    h = Harness(lambda cfg, n: FakeIface())
    h.conn.on_packet(ack_pkt(5, 0x42))
    assert 5 in h.conn._early
    h.now += 60
    h.conn.check_acks()
    assert not h.conn._early


async def test_blocking_close_times_out(monkeypatch):
    import meshlens.radio as radio
    monkeypatch.setattr(radio, "CLOSE_TIMEOUT", 0.1)
    iface = FakeIface()
    iface.close_block = threading.Event()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    await asyncio.wait_for(h.conn.stop(), 2.0)
    assert h.conn.state()["state"] == "disconnected"
    iface.close_block.set()


async def test_ble_error_codes():
    from meshlens.radio import describe_error

    class BLEError(Exception):  # come la libreria: solo il messaggio in args, codice in .kind
        def __init__(self, message, kind="unknown"):
            super().__init__(message)
            self.kind = kind

    class BleakError(Exception):
        pass
    assert describe_error(BLEError("x", "device_not_found")) ==         "Radio Bluetooth non trovata: è accesa e vicina?"
    assert describe_error(BLEError("x", "multiple_devices")) ==         "Più radio Bluetooth corrispondono: usa l'indirizzo esatto"
    assert describe_error(BLEError("x", "write_error")) ==         "Radio Bluetooth non abbinata: abbinala da Impostazioni Windows → Bluetooth "         "(PIN sullo schermo della radio)"
    connect_msg = "Connessione Bluetooth non riuscita: avvicina la radio e riprova"
    assert describe_error(BleakError("x")) == connect_msg
    assert describe_error(TimeoutError()) == connect_msg


async def test_close_runs_in_daemon_thread():
    iface = FakeIface()
    seen = []
    iface.close = lambda: seen.append(threading.current_thread())
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    await h.conn.stop()
    assert seen and seen[0].daemon and seen[0] is not threading.main_thread()


async def test_send_text_is_serialised(monkeypatch):
    iface = FakeIface()
    active, peak = [0], [0]
    orig = iface.sendText

    def slow(*a, **kw):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        import time as _t
        _t.sleep(0.05)
        active[0] -= 1
        return orig(*a, **kw)
    iface.sendText = slow
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    await asyncio.gather(*(h.conn.send_text(f"m{i}", 0, None) for i in range(3)))
    assert peak[0] == 1 and len(iface.sent) == 3
    await h.conn.stop()


async def test_send_text_timeout(monkeypatch):
    import meshlens.radio as radio
    monkeypatch.setattr(radio, "SEND_TIMEOUT", 0.1)
    iface = FakeIface()
    release = threading.Event()
    iface.sendText = lambda *a, **kw: release.wait(2)
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    with pytest.raises(RuntimeError, match="scaduto"):
        await h.conn.send_text("x", 0, PEER)
    release.set()
    await h.conn.stop()


async def test_start_wakes_backoff():
    def factory(cfg, n):
        if n == 1:
            raise PermissionError(13, "Access is denied")
        return FakeIface()
    h = Harness(factory)
    h.gate.clear()  # il backoff non scade da solo
    await h.conn.start()
    await h.until(lambda: h.conn.state()["state"] == "reconnecting")
    await h.conn.start()  # "Connetti"
    await h.until(lambda: h.conn.state()["state"] == "connected")
    assert h.factory_calls == 2
    await h.conn.stop()


async def test_not_connected_after_register_triggers_reconnect():
    first = FakeIface()
    first.isConnected = threading.Event()  # mai impostato: gia' persa
    second = FakeIface()
    h = Harness(lambda cfg, n: first if n == 1 else second)
    await connected(h)
    await h.until(lambda: h.factory_calls == 2)
    await h.until(lambda: first.closed == 1)
    await h.conn.stop()


async def test_nodedb_snapshot_retries_on_runtime_error():
    iface = FakeIface()
    real = iface.nodes
    calls = [0]

    from collections.abc import Mapping

    class Flaky(Mapping):
        def __getitem__(self, k):
            return real[k]

        def __len__(self):
            return len(real)

        def __iter__(self):
            calls[0] += 1
            if calls[0] < 3:
                raise RuntimeError("dictionary changed size during iteration")
            return iter(real)
    iface.nodes = Flaky()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    assert calls[0] >= 3
    assert {e.kind for e in h.events} == {"nodeinfo", "position"}
    await h.conn.stop()


async def test_real_pubsub_roundtrip():
    from pubsub import pub
    iface = FakeIface()
    loop = asyncio.get_running_loop()
    hub = PubSubHub(loop)  # pubsub reale
    hub.start()
    try:
        calls = []
        hub.register(iface, SimpleNamespace(
            on_packet=lambda p: calls.append(("pkt", p)),
            on_lost=lambda: calls.append(("lost",)),
            on_established=lambda: None))
        pub.sendMessage("meshtastic.receive", packet={"id": 1}, interface=iface)
        pub.sendMessage("meshtastic.connection.lost", interface=iface)
        pub.sendMessage("meshtastic.receive", packet={"id": 2}, interface=FakeIface())
        for _ in range(100):
            if len(calls) == 2:
                break
            await asyncio.sleep(0.01)
        assert calls == [("pkt", {"id": 1}), ("lost",)]
    finally:
        pub.unsubscribe(hub._on_receive, "meshtastic.receive")
        pub.unsubscribe(hub._on_lost, "meshtastic.connection.lost")
        pub.unsubscribe(hub._on_established, "meshtastic.connection.established")
