import asyncio
import sys
import threading
import time
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
        self.sent_data = []
        self.sent_data_ack = []
        self.sent_kw = []
        self.packets = []
        self.closed = 0
        self.send_thread = None
        self.next_id = 1000
        self.close_block = None
        self.on_send = None

    def sendText(self, text, destinationId="^all", wantAck=False, channelIndex=0, **kw):
        self.send_thread = threading.current_thread()
        self.sent.append((text, destinationId, wantAck, channelIndex))
        self.sent_kw.append(kw)
        self.next_id += 1
        if self.on_send:
            self.on_send(self.next_id)
        return SimpleNamespace(id=self.next_id)

    def sendData(self, data, destinationId="^all", portNum=None, wantAck=False,
                 wantResponse=False, channelIndex=0, **kw):
        self.send_thread = threading.current_thread()
        self.sent_data.append((data, destinationId, portNum, wantResponse, channelIndex))
        self.sent_data_ack.append(wantAck)
        self.next_id += 1
        if self.on_send:
            self.on_send(self.next_id)
        return SimpleNamespace(id=self.next_id)

    def _generatePacketId(self):
        self.next_id += 1
        return self.next_id

    def _sendPacket(self, meshPacket, destinationId="^all", wantAck=False, **kw):
        self.send_thread = threading.current_thread()
        self.packets.append((meshPacket, destinationId, wantAck))
        if self.on_send:
            self.on_send(meshPacket.id)
        return meshPacket

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
        self.traces = []
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
            clock=lambda: self.now, sleep=sleep,
            on_traceroute=lambda *a: self.traces.append(a))

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


async def test_send_text_reply_uses_reply_id():
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    pid = await h.conn.send_text("ok", 0, "!0000abcd", reply_id=42)
    assert iface.sent == [("ok", "!0000abcd", True, 0)]
    assert iface.sent_kw == [{"replyId": 42}]
    assert pid == 1001 and iface.packets == []
    await h.conn.send_text("senza", 0, None)
    assert iface.sent_kw[-1] == {"replyId": None}
    await h.conn.stop()


async def test_send_reaction_builds_emoji_packet():
    from meshtastic.protobuf import portnums_pb2
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    pid = await h.conn.send_text("👍", 1, None, reply_id=42, emoji=True)
    assert iface.sent == []
    ((pkt, dest, want_ack),) = iface.packets
    assert pkt.decoded.emoji == 1 and pkt.decoded.reply_id == 42 and pkt.channel == 1
    from meshtastic.protobuf import mesh_pb2
    assert pkt.priority == mesh_pb2.MeshPacket.Priority.RELIABLE
    assert pkt.decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP
    assert pkt.decoded.payload == "👍".encode()
    assert dest == "^all" and want_ack is True
    assert pid == pkt.id == 1001
    assert iface.send_thread is not threading.main_thread()
    pid2 = await h.conn.send_text("👍", 0, PEER, reply_id=7, emoji=True)
    assert iface.packets[-1][1] == PEER
    h.now += 100
    h.conn.check_acks()
    assert [a[1] for a in h.acks] == [pid2]  # la reazione in DM attende l'ack
    await h.conn.stop()


async def test_send_waypoint_uses_waypoint_port():
    from meshtastic.protobuf import mesh_pb2, portnums_pb2
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    wp = mesh_pb2.Waypoint(id=7, latitude_i=451000000, longitude_i=92000000, locked_to=MY_NUM,
                           name="Ritrovo")
    pid = await h.conn.send_waypoint(wp, 1)
    assert pid == 1001
    ((data, dest, port, want_response, channel),) = iface.sent_data
    assert data.locked_to == MY_NUM and data.name == "Ritrovo"
    assert port == portnums_pb2.WAYPOINT_APP and dest == "^all" and channel == 1
    assert iface.sent_data_ack == [False]
    assert iface.send_thread is not threading.main_thread()
    await h.conn.stop()
    with pytest.raises(RuntimeError):
        await h.conn.send_waypoint(wp, 0)


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


async def test_send_traceroute_calls_senddata():
    from meshtastic.protobuf import mesh_pb2, portnums_pb2
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    pid = await h.conn.send_traceroute(0x42, 2)
    assert pid == 1001
    data, dest, port, want, ch = iface.sent_data[0]
    assert isinstance(data, mesh_pb2.RouteDiscovery)
    assert (dest, port, want, ch) == (0x42, portnums_pb2.TRACEROUTE_APP, True, 2)
    assert iface.send_thread is not threading.main_thread()
    await h.conn.stop()


async def test_send_traceroute_not_connected():
    h = Harness(lambda cfg, n: FakeIface())
    with pytest.raises(RuntimeError, match="non connessa"):
        await h.conn.send_traceroute(0x42)


async def test_traceroute_reply_calls_callback_and_still_reaches_ingest():
    h = Harness(lambda cfg, n: FakeIface())
    await connected(h)
    pkt = {"from": 0x42, "to": MY_NUM, "id": 7, "decoded": {
        "portnum": "TRACEROUTE_APP", "requestId": 55,
        "traceroute": {"route": [], "snrTowards": [20], "routeBack": [], "snrBack": [8]}}}
    h.conn.on_packet(pkt)
    assert [(t[0], t[1], t[2].kind) for t in h.traces] == [(CFG["id"], 55, "traceroute")]
    assert h.events[-1].kind == "traceroute"
    # senza requestId (richiesta di altri): nessuna callback
    del pkt["decoded"]["requestId"]
    h.conn.on_packet(pkt)
    assert len(h.traces) == 1
    await h.conn.stop()


async def test_traceroute_routing_error_is_forwarded_as_ack_failure():
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    pid = await h.conn.send_traceroute(0x42)
    h.conn.on_packet(ack_pkt(pid, MY_NUM))  # ack locale ok: ignorato
    assert h.acks == []
    h.conn.on_packet(ack_pkt(pid, 0x42, "NO_RESPONSE"))
    assert h.acks == [(CFG["id"], pid, False, "NO_RESPONSE")]
    await h.conn.stop()


async def test_traceroute_early_error_during_send_is_reported():
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    iface.on_send = lambda pid: h.loop.call_soon_threadsafe(
        h.conn.on_packet, ack_pkt(pid, 0x42, "NO_ROUTE"))
    pid = await h.conn.send_traceroute(0x42)
    assert h.acks == [(CFG["id"], pid, False, "NO_ROUTE")]
    await h.conn.stop()


# ---- operazioni admin (fase 5) -------------------------------------------------
import base64  # noqa: E402
import copy  # noqa: E402

from meshtastic.protobuf import channel_pb2, localonly_pb2  # noqa: E402

from meshlens.radio import AdminError  # noqa: E402

REMOTE_NUM = 0x42


class FakeNode:
    """Registra le chiamate admin (inviando davvero un pacchetto); i protobuf sono reali."""

    def __init__(self, iface, calls, remote=False):
        self.iface, self.calls, self.remote = iface, calls, remote
        self.localConfig = localonly_pb2.LocalConfig()
        self.moduleConfig = localonly_pb2.LocalModuleConfig()
        self.channels = [channel_pb2.Channel(index=i) for i in range(3)]
        self.channels[0].role = channel_pb2.Channel.PRIMARY
        self.request_hook = None  # funzione(configType) chiamata da requestConfig
        self.write_hook = None  # funzione() chiamata da writeConfig
        self.channel_error = None
        # messaggi predefiniti (come la libreria: cache, attesa attiva, sys.exit oltre 200)
        self.canned_available = True
        self.cannedPluginMessage = None
        self.cannedPluginMessageMessages = None  # testo dell'ultima risposta (cache)
        self.canned_no_reply_early = False  # la libreria esce senza risposta (es. errore)
        self.gotResponse = None
        self.canned_reply = None
        self.canned_event = None
        self.canned_seen = "non chiamato"
        self.canned_thread_done = threading.Event()

    def _rec(self, *a):
        self.calls.append(a)
        self.iface.sendData(None)

    def beginSettingsTransaction(self):
        self._rec("begin")

    def commitSettingsTransaction(self):
        self._rec("commit")

    def writeConfig(self, name):
        self._rec("writeConfig", name, self.localConfig.lora.hop_limit)
        if self.write_hook:
            self.write_hook()

    def writeChannel(self, i):
        if self.channel_error:
            raise self.channel_error
        self._rec("writeChannel", i)

    def setOwner(self, long_name=None, short_name=None, is_licensed=False):
        self._rec("setOwner", long_name, short_name, is_licensed)

    def ensureSessionKey(self):
        self._rec("ensureSessionKey")

    def requestConfig(self, cfg):
        self._rec("requestConfig", getattr(cfg, "name", cfg))
        if self.request_hook:
            self.request_hook(cfg)
        if self.remote:
            self.iface.waitForAckNak()  # come la libreria, che poi azzera l'ack

    def reboot(self, secs=10):
        self._rec("reboot", secs)

    def setFixedPosition(self, lat, lon, alt):
        self._rec("setFixedPosition", lat, lon, alt)

    def removeFixedPosition(self):
        self._rec("removeFixedPosition")

    def setFavorite(self, num):
        self._rec("setFavorite", num)

    def removeFavorite(self, num):
        self._rec("removeFavorite", num)

    def setIgnored(self, num):
        self._rec("setIgnored", num)

    def removeIgnored(self, num):
        self._rec("removeIgnored", num)

    def setTime(self, t=0):
        self._rec("setTime", t)

    def resetNodeDb(self):
        self._rec("resetNodeDb")

    def shutdown(self, secs=10):
        self._rec("shutdown", secs)

    def module_available(self, bit):
        return self.canned_available

    def get_canned_message(self):
        self.canned_seen = self.cannedPluginMessage
        self.calls.append(("get_canned_message",))
        try:
            if self.canned_event is not None:
                self.canned_event.wait(5)
            if self.canned_no_reply_early:  # come la libreria: usa la cache dei messaggi
                return self.cannedPluginMessageMessages or ""
            if self.canned_reply is not None:
                self.cannedPluginMessageMessages = self.canned_reply  # risposta arrivata
            if self.canned_reply is None:
                self.gotResponse = False  # come la libreria, prima dell'attesa attiva
                while self.gotResponse is False:
                    time.sleep(0.01)
                return ""
            return self.canned_reply
        finally:
            self.canned_thread_done.set()

    def set_canned_message(self, message):
        if len(message) > 200:
            sys.exit(1)  # come our_exit della libreria
        self._rec("set_canned_message", message)


class AdminIface(FakeIface):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.local = FakeNode(self, self.calls)
        self.localNode = self.local
        self.local.localConfig.security.public_key = bytes(range(32))
        self.local.localConfig.security.private_key = b"segretissimo"
        self.remote = FakeNode(self, self.calls, remote=True)
        self.nodesByNum = {}
        self._timeout = SimpleNamespace(expireTimeout=300)
        self.timeouts_seen = []
        self.get_node_hook = None
        self.ack_mode = "ack"  # "ack" | "nak" | "none": cosa risponde ogni invio
        self._acknowledgment = SimpleNamespace(
            receivedAck=False, receivedNak=False, receivedImplAck=False, reset=self._reset_ack)

    def _reset_ack(self):
        self.calls.append(("ack_reset",))
        a = self._acknowledgment
        a.receivedAck = a.receivedNak = a.receivedImplAck = False

    def sendData(self, *a, **kw):
        pkt = super().sendData(*a, **kw)
        if self.ack_mode == "ack":
            self._acknowledgment.receivedAck = True
        elif self.ack_mode == "nak":
            self._acknowledgment.receivedNak = True
        return pkt

    def getNode(self, nid, requestChannels=True, requestChannelAttempts=3, timeout=300):
        self.calls.append(("getNode", nid, requestChannels, timeout))
        self.timeouts_seen.append(self._timeout.expireTimeout)
        self.sendData(None)
        if self.get_node_hook:
            self.get_node_hook()
        return self.remote


async def admin_connected():
    iface = AdminIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    return h, iface


def routing_from_thread(h, iface, reason, sender=REMOTE_NUM):
    """Come il hub: il pacchetto ROUTING arriva nel loop per l'ultimo pacchetto inviato."""
    h.loop.call_soon_threadsafe(h.conn.on_packet, ack_pkt(iface.next_id, sender, reason))


def changed(iface, hop=4, channel1="prova", owner="Nuovo", node=None):
    node = node or iface.local
    protos = {"config": copy.deepcopy(node.localConfig),
              "module_config": copy.deepcopy(node.moduleConfig),
              "channels": [copy.deepcopy(c) for c in node.channels],
              "owner": {"long_name": owner, "short_name": "HB", "is_licensed": False}}
    protos["config"].lora.hop_limit = hop
    protos["channels"][1].settings.name = channel1
    return protos


async def test_read_local_returns_masked_dict():
    h, iface = await admin_connected()
    cfg = await h.conn.read_local()
    assert cfg["config"]["security"]["private_key"] == "••••"
    assert cfg["owner"]["long_name"] == "Heltec base"
    assert len(cfg["channels"]) == 3
    assert "segretissimo" not in str(cfg)
    assert await h.conn.admin_public_key() == base64.b64encode(bytes(range(32))).decode()
    assert iface._timeout.expireTimeout == 300 and iface.timeouts_seen == []
    await h.conn.stop()


async def test_current_protos_local_is_unmasked_copy():
    h, iface = await admin_connected()
    protos = await h.conn.current_protos(None)
    assert protos["config"] is not iface.localNode.localConfig
    assert protos["config"].security.private_key  # in chiaro: serve a copie e scritture
    assert protos["owner"]["long_name"] == "Heltec base" and len(protos["channels"]) == 3
    await h.conn.stop()


async def test_read_remote_unauthorized_fails_fast():
    h, iface = await admin_connected()

    def deny():  # il nodo risponde ROUTING 37 e la libreria uscirebbe con SystemExit
        routing_from_thread(h, iface, "ADMIN_PUBLIC_KEY_UNAUTHORIZED")
        raise SystemExit(1)
    iface.get_node_hook = deny
    t0 = asyncio.get_running_loop().time()
    with pytest.raises(AdminError) as ei:
        await h.conn.read_remote(REMOTE_NUM, None, lambda *a: None)
    assert ei.value.code == "unauthorized"
    assert "chiave admin" in ei.value.message
    assert asyncio.get_running_loop().time() - t0 < 1
    assert iface._timeout.expireTimeout == 300  # ripristinato
    await h.conn.stop()


async def test_read_remote_unauthorized_on_request_config():
    h, iface = await admin_connected()
    iface.remote.request_hook = lambda cfg: routing_from_thread(h, iface, "NOT_AUTHORIZED")
    with pytest.raises(AdminError) as ei:
        await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    assert ei.value.code == "unauthorized"
    await h.conn.stop()


async def test_unrelated_routing_error_does_not_abort():
    h, iface = await admin_connected()
    iface.remote.request_hook = lambda cfg: h.loop.call_soon_threadsafe(
        h.conn.on_packet, ack_pkt(9999, REMOTE_NUM, "NO_ROUTE"))  # ack di una chat, non nostro
    cfg = await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    assert "lora" in cfg["config"]
    await h.conn.stop()


async def test_read_remote_nak_without_reason_is_error():
    h, iface = await admin_connected()
    iface.ack_mode = "nak"  # la libreria azzera l'ack e torna come se nulla fosse
    with pytest.raises(AdminError) as ei:
        await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    assert ei.value.code == "error"
    await h.conn.stop()


async def test_read_remote_nak_with_unauthorized_reason():
    h, iface = await admin_connected()
    iface.ack_mode = "nak"
    iface.remote.request_hook = lambda cfg: routing_from_thread(h, iface, "ADMIN_PUBLIC_KEY_UNAUTHORIZED")
    iface.get_node_hook = None
    with pytest.raises(AdminError) as ei:
        await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    assert ei.value.code == "unauthorized"
    await h.conn.stop()


async def test_read_remote_ok_steps_and_timeout_60():
    h, iface = await admin_connected()
    steps = []
    cfg = await h.conn.read_remote(REMOTE_NUM, ["lora", "telemetry"], lambda *a: steps.append(a))
    assert iface.timeouts_seen == [60]
    assert ("getNode", "!00000042", True, 60) in iface.calls
    assert [c[1] for c in iface.calls if c[0] == "requestConfig"] == ["lora", "telemetry"]
    assert steps[0][1:] == (0, 3) and steps[-1][1:] == (3, 3)
    assert "lora" in cfg["config"]
    await h.conn.stop()


async def test_read_remote_timeout():
    h, iface = await admin_connected()

    def boom(cfg):
        raise RuntimeError("Timed out waiting for an acknowledgment")
    iface.remote.request_hook = boom
    with pytest.raises(AdminError) as ei:
        await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    assert ei.value.code == "timeout"
    assert ei.value.message == "Nessuna risposta dal nodo entro 60 s"
    await h.conn.stop()


async def test_busy_while_abandoned_thread_still_runs():
    h, iface = await admin_connected()
    gate = threading.Event()
    first = [True]

    def deny():
        if first[0]:
            first[0] = False
            routing_from_thread(h, iface, "ADMIN_PUBLIC_KEY_UNAUTHORIZED")
            gate.wait(5)  # il thread della libreria resta bloccato
            raise SystemExit(1)
    iface.get_node_hook = deny
    with pytest.raises(AdminError) as ei:
        await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    assert ei.value.code == "unauthorized"
    with pytest.raises(AdminError) as ei:
        await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    assert ei.value.code == "busy"
    assert "ancora in corso" in ei.value.message
    gate.set()
    await h.until(lambda: h.conn._admin_task.done())
    cfg = await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    assert "lora" in cfg["config"]
    await h.conn.stop()


async def test_other_thread_stdout_not_swallowed(capsys):
    h, iface = await admin_connected()

    def hook(cfg):
        print("dal-thread-admin")  # scartato
        t = threading.Thread(target=lambda: print("da-altro-thread"))
        t.start()
        t.join()
    iface.remote.request_hook = hook
    await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    out = capsys.readouterr().out
    assert "da-altro-thread" in out and "dal-thread-admin" not in out
    await h.conn.stop()


async def test_write_uses_single_transaction():
    h, iface = await admin_connected()
    steps = []
    await h.conn.write(None, changed(iface), lambda *a: steps.append(a))
    seq = [c for c in iface.calls if c[0] not in ("ack_reset", "getNode")]
    assert seq == [("begin",), ("writeConfig", "lora", 4), ("writeChannel", 1),
                   ("setOwner", "Nuovo", "HB", False), ("commit",)]
    assert iface.local.localConfig.lora.hop_limit == 4  # copiato nel Node prima di scrivere
    assert steps[-1][1] == steps[-1][2]
    await h.conn.stop()


async def test_failed_write_restores_node():
    h, iface = await admin_connected()
    iface.local.channel_error = RuntimeError("boom")
    with pytest.raises(AdminError):
        await h.conn.write(None, changed(iface), lambda *a: None)
    assert iface.local.localConfig.lora.hop_limit == 0
    assert iface.local.channels[1].settings.name == ""
    await h.conn.stop()


async def test_write_remote_calls_ensure_session_key_and_waits_ack():
    h, iface = await admin_connected()
    await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    iface.calls.clear()
    await h.conn.write(REMOTE_NUM, changed(iface, node=iface.remote), lambda *a: None)
    names = [c[0] for c in iface.calls]
    assert names[0] == "ensureSessionKey"
    assert names.index("ack_reset") < names.index("commit")
    assert names[names.index("commit"):].count("ack_reset") == 1  # ack consumato dopo il commit
    assert iface._timeout.expireTimeout == 300
    await h.conn.stop()


async def test_write_remote_without_prior_read_fails():
    h, iface = await admin_connected()
    with pytest.raises(AdminError) as ei:
        await h.conn.write(REMOTE_NUM, changed(iface), lambda *a: None)
    assert ei.value.code == "error"
    await h.conn.stop()


async def test_remote_cache_cleared_on_close_and_expires():
    h, iface = await admin_connected()
    await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    assert REMOTE_NUM in h.conn._remote_nodes
    h.now += 241  # lettura troppo vecchia: serve una nuova (e una nuova chiave di sessione)
    with pytest.raises(AdminError) as ei:
        await h.conn.write(REMOTE_NUM, changed(iface, node=iface.remote), lambda *a: None)
    assert ei.value.code == "error" and REMOTE_NUM not in h.conn._remote_nodes
    await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    await h.conn._close_iface()
    assert h.conn._remote_nodes == {}
    await h.conn.stop()


async def test_write_remote_retries_once_on_bad_session_key():
    h, iface = await admin_connected()
    await h.conn.read_remote(REMOTE_NUM, ["lora"], lambda *a: None)
    iface.calls.clear()
    iface.nodesByNum[REMOTE_NUM] = {"adminSessionPassKey": b"vecchia"}
    first = [True]

    def bad():
        if first[0]:
            first[0] = False
            routing_from_thread(h, iface, "ADMIN_BAD_SESSION_KEY")
            iface._acknowledgment.receivedNak = True
    iface.remote.write_hook = bad
    await h.conn.write(REMOTE_NUM, changed(iface, node=iface.remote), lambda *a: None)
    names = [c[0] for c in iface.calls]
    assert names.count("ensureSessionKey") == 2 and names.count("commit") == 1
    assert "adminSessionPassKey" not in iface.nodesByNum[REMOTE_NUM]
    await h.conn.stop()


async def test_admin_ops_hold_send_lock():
    h, iface = await admin_connected()
    gate = threading.Event()
    orig = iface.local.beginSettingsTransaction
    iface.local.beginSettingsTransaction = lambda: (gate.wait(3), orig())
    w = asyncio.create_task(h.conn.write(None, changed(iface), lambda *a: None))
    await h.until(lambda: h.conn._send_lock.locked())
    s = asyncio.create_task(h.conn.send_text("ciao", 0, None))
    await asyncio.sleep(0.1)
    assert iface.sent == [] and not s.done()
    gate.set()
    await w
    await s
    assert len(iface.sent) == 1
    await h.conn.stop()


async def test_reboot_and_fixed_position_local():
    h, iface = await admin_connected()
    await h.conn.reboot(None, 7)
    await h.conn.set_fixed_position(None, 45.5, 9.25, 120)
    await h.conn.remove_fixed_position(None)
    assert ("reboot", 7) in iface.calls
    assert ("setFixedPosition", 45.5, 9.25, 120) in iface.calls
    assert ("removeFixedPosition",) in iface.calls
    await h.conn.stop()


async def test_remote_reboot_does_not_wait_for_ack():
    h, iface = await admin_connected()
    iface.ack_mode = "none"  # il nodo che si riavvia non conferma
    await asyncio.wait_for(h.conn.reboot(REMOTE_NUM, 5), 5)
    assert ("reboot", 5) in iface.calls
    await h.conn.stop()


async def test_wait_reconnected_ok_after_reboot():
    h, iface = await admin_connected()
    await h.conn.write(None, changed(iface), lambda *a: None)
    waiter = asyncio.create_task(h.conn.wait_reconnected(5))
    await asyncio.sleep(0.05)
    assert not waiter.done()
    h.conn.on_established()  # la libreria ripubblica established dopo il riavvio
    assert await waiter is True
    await h.conn.stop()


async def test_wait_reconnected_times_out():
    h, iface = await admin_connected()
    await h.conn.write(None, changed(iface), lambda *a: None)

    async def fake_sleep(d):
        h.now += d
        await asyncio.sleep(0)
    h.conn._sleep = fake_sleep
    assert await h.conn.wait_reconnected(90) is False
    assert h.now >= 1000.0 + 90
    await h.conn.stop()


def test_library_prints_are_silenced_on_any_thread(capsys):
    import threading
    from meshtastic import node as mnode
    secret = "WIFISECRET-xyz"
    t = threading.Thread(target=lambda: mnode.print(f"Preferences: {secret}"))
    t.start()
    t.join()
    out = capsys.readouterr()
    assert secret not in out.out + out.err


async def test_unhandled_packet_emits_raw():
    from meshlens.events import RawPacket
    h = Harness(lambda cfg, n: FakeIface())
    await connected(h)
    h.events.clear()
    h.conn.on_packet({"from": 0x42, "id": 5, "decoded": {"portnum": "ADMIN_APP", "payload": b"q"}})
    h.conn.on_packet(ack_pkt(999, 0x42))  # ROUTING_APP: gestito, ma emesso comunque
    assert [type(e) for e in h.events] == [RawPacket, RawPacket]
    assert h.events[0].status == "unsupported" and h.events[0].meta.portnum == "ADMIN_APP"
    await h.conn.stop()


def test_describe_error_tcp():
    import socket
    from meshlens.radio import describe_error
    assert "non trovato" in describe_error(socket.gaierror(11001, "x"), "tcp")
    assert "rifiutata" in describe_error(ConnectionRefusedError(), "tcp")
    assert "non raggiungibile" in describe_error(TimeoutError(), "tcp")
    assert "non raggiungibile" in describe_error(OSError(10065, "x"), "tcp")
    assert describe_error(TimeoutError()).startswith("Connessione Bluetooth")


def test_describe_error_tcp_not_meshtastic():
    from meshlens.radio import MSG_TCP_NO_REPLY, describe_error

    class MeshInterfaceError(Exception):
        pass
    msg = describe_error(MeshInterfaceError("Timed out waiting for connection completion"), "tcp")
    assert msg == MSG_TCP_NO_REPLY
    assert "Meshtastic" in msg and "un altro collegamento" in msg
    # un timeout di rete resta "non raggiungibile"
    assert "non raggiungibile" in describe_error(TimeoutError(), "tcp")
    # per le altre radio il testo non cambia
    assert describe_error(MeshInterfaceError("x"), "usb") == "Errore di connessione: MeshInterfaceError"


async def test_factory_runs_in_daemon_thread_not_pool():
    seen = {}

    def factory(cfg, n):
        import threading
        t = threading.current_thread()
        seen.update(daemon=t.daemon, name=t.name)
        return FakeIface()
    h = Harness(factory)
    await connected(h)
    assert seen["daemon"] is True and not seen["name"].startswith("asyncio_")
    await h.conn.stop()


async def test_stop_during_blocked_connect_returns_and_closes_late():
    import threading
    release, entered = threading.Event(), threading.Event()
    iface = FakeIface()

    def factory(cfg, n):
        entered.set()
        release.wait(5)
        return iface
    h = Harness(factory)
    await h.conn.start()
    await h.until(entered.is_set)
    await asyncio.wait_for(h.conn.stop(), 2)  # non attende il thread bloccato
    release.set()
    await h.until(lambda: iface.closed == 1)


async def test_send_fails_fast_when_radio_lock_is_held(monkeypatch):
    import meshlens.radio as radio_mod
    from meshlens.radio import RadioBusy
    monkeypatch.setattr(radio_mod, "SEND_LOCK_TIMEOUT", 0.1)
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    await h.conn._send_lock.acquire()  # come un'operazione admin in corso
    try:
        for coro in (h.conn.send_text("ciao", 0, None), h.conn.send_traceroute(0x42)):
            with pytest.raises(RadioBusy, match="occupata, riprova tra poco"):
                await asyncio.wait_for(coro, 2)
        assert iface.sent == [] and iface.sent_data == []
    finally:
        h.conn._send_lock.release()
    await h.conn.stop()


# ---- WP4: preferiti/ignorati, ora, reset NodeDB, spegnimento, canned -------------

async def test_admin_op_wait_raises_radio_busy(monkeypatch):
    import meshlens.radio as radio_mod
    from meshlens.radio import RadioBusy
    monkeypatch.setattr(radio_mod, "SEND_LOCK_TIMEOUT", 0.1)
    h, iface = await admin_connected()
    await h.conn._send_lock.acquire()
    try:
        with pytest.raises(RadioBusy):
            await asyncio.wait_for(h.conn.set_node_flag(0x42, "favorite", True, wait=0.1), 2)
        assert not any(c[0] == "setFavorite" for c in iface.calls)
    finally:
        h.conn._send_lock.release()
    await h.conn.stop()


async def test_set_node_flag_local_calls_library_and_updates_memory():
    h, iface = await admin_connected()
    iface.nodesByNum[0x42] = {"num": 0x42}
    await h.conn.set_node_flag(0x42, "favorite", True)
    assert ("setFavorite", 0x42) in iface.calls
    assert h.conn.node_flags(0x42) == {"favorite": True, "ignored": False, "muted": None}
    await h.conn.set_node_flag(0x42, "ignored", True)
    assert ("setIgnored", 0x42) in iface.calls
    await h.conn.set_node_flag(0x42, "favorite", False)
    assert ("removeFavorite", 0x42) in iface.calls
    assert h.conn.node_flags(0x42) == {"favorite": False, "ignored": True, "muted": None}
    await h.conn.set_node_flag(0x42, "ignored", False)
    assert ("removeIgnored", 0x42) in iface.calls
    await h.conn.stop()


async def test_set_node_flag_rejects_bad_flag_and_own_node():
    h, iface = await admin_connected()
    with pytest.raises(ValueError):
        await h.conn.set_node_flag(0x42, "muted", True)
    with pytest.raises(ValueError):
        await h.conn.set_node_flag(MY_NUM, "favorite", True)
    assert iface.calls == []
    await h.conn.stop()


async def test_node_flags_reads_camelcase_and_unknown():
    h, iface = await admin_connected()
    iface.nodesByNum[0x77] = {"num": 0x77, "isFavorite": True, "isIgnored": True,
                              "isMuted": False}
    assert h.conn.node_flags(0x77) == {"favorite": True, "ignored": True, "muted": False}
    assert h.conn.node_flags(0x99) is None
    await h.conn.stop()
    assert h.conn.node_flags(0x77) is None


async def test_set_time_reset_shutdown_local():
    h, iface = await admin_connected()
    await h.conn.set_time(None, 1_700_000_000)
    await h.conn.reset_nodedb(None)
    assert h.conn._reboot_mark is not None
    h.conn._reboot_mark = None
    await h.conn.shutdown(None, 5)
    assert h.conn._reboot_mark is None
    assert ("setTime", 1700000000) in iface.calls
    assert ("resetNodeDb",) in iface.calls
    assert ("shutdown", 5) in iface.calls
    await h.conn.stop()


async def test_remote_shutdown_does_not_wait_ack_and_set_time_does():
    h, iface = await admin_connected()
    iface.ack_mode = "none"
    await asyncio.wait_for(h.conn.shutdown(REMOTE_NUM, 5), 5)
    assert ("shutdown", 5) in iface.calls
    iface.ack_mode = "ack"
    iface.calls.clear()
    await h.conn.set_time(REMOTE_NUM, 1)
    i = iface.calls.index(("setTime", 1))
    assert ("ack_reset",) in iface.calls[i + 1:]  # waitForAckNak ha consumato l'ACK
    await h.conn.stop()


async def test_get_canned_resets_cache_and_returns_text():
    h, iface = await admin_connected()
    iface.local.cannedPluginMessage = "vecchio"
    iface.local.canned_reply = "Ciao|Arrivo|OK"
    assert await h.conn.get_canned(None) == "Ciao|Arrivo|OK"
    assert iface.local.canned_seen is None  # cache azzerata prima della chiamata
    await h.conn.stop()


async def test_get_canned_without_reply_never_returns_stale_text():
    """M9: una lettura senza risposta non restituisce mai il testo della lettura precedente."""
    h, iface = await admin_connected()
    iface.local.cannedPluginMessageMessages = "Vecchio|Testo"
    iface.local.canned_no_reply_early = True
    with pytest.raises(AdminError):
        await h.conn.get_canned(None)
    iface.local.canned_no_reply_early = False
    iface.local.canned_reply = ""  # risposta vera: elenco vuoto
    assert await h.conn.get_canned(None) == ""
    await h.conn.stop()


async def test_get_canned_timeout_releases_busy_wait(monkeypatch):
    import meshlens.radio as radio_mod
    monkeypatch.setattr(radio_mod, "CANNED_TIMEOUT", 0.2)
    h, iface = await admin_connected()
    iface.local.canned_reply = None  # nessuna risposta: attesa attiva della libreria
    with pytest.raises(AdminError) as ei:
        await h.conn.get_canned(None)
    assert ei.value.code == "timeout"
    await h.until(lambda: iface.local.canned_thread_done.is_set(), 1.0)
    await h.until(lambda: h.conn._admin_task.done(), 1.0)
    iface.nodesByNum[0x42] = {"num": 0x42}
    await h.conn.set_node_flag(0x42, "favorite", True)  # nessun MSG_ADMIN_BUSY
    assert ("setFavorite", 0x42) in iface.calls
    await h.conn.stop()


async def test_canned_module_missing():
    from meshlens.radio import MSG_NO_CANNED
    h, iface = await admin_connected()
    iface.local.canned_available = False
    with pytest.raises(AdminError, match=MSG_NO_CANNED):
        await h.conn.get_canned(None)
    with pytest.raises(AdminError, match=MSG_NO_CANNED):
        await h.conn.set_canned(None, "a")
    assert not any(c[0] in ("get_canned_message", "set_canned_message") for c in iface.calls)
    await h.conn.stop()


async def test_set_canned_validates_before_library():
    h, iface = await admin_connected()
    with pytest.raises(ValueError):
        await h.conn.set_canned(None, "è" * 101)  # 202 byte
    with pytest.raises(ValueError):
        await h.conn.set_canned(None, "")
    assert not any(c[0] == "set_canned_message" for c in iface.calls)
    await h.conn.set_canned(None, "Ciao|OK")
    assert ("set_canned_message", "Ciao|OK") in iface.calls
    await h.conn.stop()


async def test_library_system_exit_becomes_admin_error():
    h, iface = await admin_connected()
    with pytest.raises(AdminError) as ei:
        await h.conn._simple_admin(None, lambda n: sys.exit(1))
    assert ei.value.message == "Operazione fallita: SystemExit"
    await h.conn.stop()


async def test_has_admin_session_follows_remote_cache_age():
    """M4: sessione admin aperta = lettura remota recente (chiave di sessione valida)."""
    from meshlens.radio import SESSION_MAX_AGE
    h = Harness(lambda cfg, n: FakeIface())
    assert h.conn.has_admin_session(0x42) is False
    h.conn._remote_nodes[0x42] = (object(), h.now)
    assert h.conn.has_admin_session(0x42) is True
    h.now += SESSION_MAX_AGE + 1
    assert h.conn.has_admin_session(0x42) is False


async def test_running_true_between_retries_false_after_stop():
    """M7: tra due tentativi (stato error/reconnecting) il connettore possiede ancora la porta."""
    h = Harness(lambda cfg, n: (_ for _ in ()).throw(OSError("porta occupata")))
    h.gate.clear()  # il backoff resta in attesa
    assert h.conn.running is False
    await h.conn.start()
    await h.until(lambda: h.conn.state()["state"] in ("error", "reconnecting"))
    assert h.conn.running is True
    h.gate.set()
    await h.conn.stop()
    assert h.conn.running is False
