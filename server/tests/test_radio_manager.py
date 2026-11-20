import asyncio
import threading
from types import SimpleNamespace

import pytest

from meshlens.bus import Bus
from meshlens.db import connect
from meshlens.dedup import Deduplicator
from meshlens.geo import CountryLocator
from meshlens.ingest import Ingestor
from meshlens.live import LiveState
from meshlens.radio_manager import RadioManager
from meshlens.store import Store

MY_ID = "!a1b2c3d4"


class FakeConnector:
    instances = []

    def __init__(self, cfg, hub, on_event, on_state, on_ack, iface_factory):
        self.cfg, self.on_state, self.on_ack = cfg, on_state, on_ack
        self.state_name, self.starts, self.stops = "disconnected", 0, 0
        self.sent, self.next_id, self.fail = [], 500, None
        self.gate = None
        FakeConnector.instances.append(self)

    def state(self):
        up = self.state_name == "connected"
        return {"id": self.cfg["id"], "kind": self.cfg["kind"], "address": self.cfg["address"],
                "state": self.state_name, "error": None, "my_node_id": MY_ID if up else None,
                "my_node_name": "Heltec" if up else None,
                "channels": [{"index": 0, "name": "LongFast", "role": "PRIMARY"}] if up else []}

    async def start(self):
        self.starts += 1
        self.set("connected")

    async def stop(self):
        self.stops += 1
        self.set("disconnected")

    def set(self, name):
        self.state_name = name
        self.on_state(self.state())

    async def send_text(self, text, channel_index, dest):
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError(self.fail)
        self.sent.append((text, channel_index, dest))
        self.next_id += 1
        return self.next_id


class FakeHub:
    def __init__(self):
        self.loop = None

    def start(self, loop=None):
        self.loop = loop


class Env:
    def __init__(self):
        FakeConnector.instances = []
        self.conn = connect(":memory:")
        self.store = Store(self.conn)
        self.bus = Bus()
        self.q = self.bus.subscribe()
        self.live = LiveState()
        self.ingestor = Ingestor(
            self.live, self.store, Deduplicator(), CountryLocator(),
            lambda: {"saved_countries": []},
            lambda m: self.bus.publish({"type": "message", "message": m}),
            lambda k, s: self.bus.publish({"type": "message_status", "key": k, "status": s}))
        self.ports = [SimpleNamespace(device="COM5", description="CP210x", vid=0x10C4, pid=0xEA60),
                      SimpleNamespace(device="COM1", description="Porta", vid=None, pid=None)]
        self.scan_threads = []

        def scan():
            self.scan_threads.append(threading.current_thread())
            return [{"address": "AA:BB", "name": "Meshtastic_1a2b"}]

        self.mgr = RadioManager(self.store, self.ingestor, self.bus, None, FakeHub(),
                                connector_factory=FakeConnector, iface_factory=lambda c: None,
                                list_ports_fn=lambda: self.ports, ble_scan_fn=scan)

    def drain(self):
        out = []
        while not self.q.empty():
            out.append(self.q.get_nowait())
        return out


async def settle():
    for _ in range(50):
        await asyncio.sleep(0)


async def test_add_remove_and_duplicate():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "Heltec base")
    assert r["id"].startswith("r") and len(r["id"]) == 9
    assert (r["name"], r["kind"], r["address"], r["auto_connect"]) == (
        "Heltec base", "usb", "COM5", True)
    assert [x["id"] for x in e.store.list_radios()] == [r["id"]]
    with pytest.raises(ValueError, match="Radio già aggiunta"):
        await e.mgr.add("usb", "com5", "Altra")
    with pytest.raises(ValueError):
        await e.mgr.add("wifi", "x", "x")
    await e.mgr.remove(r["id"])
    assert e.mgr.radios() == [] and e.store.list_radios() == []
    assert FakeConnector.instances[0].stops == 1
    with pytest.raises(KeyError):
        await e.mgr.remove("rdeadbeef")


async def test_ports_marks_likely_and_in_use():
    e = Env()
    r = await e.mgr.add("usb", "COM5", None)
    ports = await e.mgr.ports()
    assert ports[0] == {"device": "COM5", "description": "CP210x", "vid": "10C4",
                        "pid": "EA60", "likely_meshtastic": True, "in_use_by": r["id"]}
    assert ports[1]["likely_meshtastic"] is False and ports[1]["in_use_by"] is None
    assert ports[1]["vid"] is None


async def test_ble_scan_runs_in_thread():
    e = Env()
    assert await e.mgr.ble_scan() == [{"address": "AA:BB", "name": "Meshtastic_1a2b"}]
    assert e.scan_threads[0] is not threading.current_thread()


async def test_ble_scan_failure_is_value_error():
    e = Env()

    def boom():
        raise SystemExit(1)

    e.mgr._ble_scan = boom
    with pytest.raises(ValueError, match="Bluetooth"):
        await e.mgr.ble_scan()


async def test_send_validation():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    with pytest.raises(ValueError, match="^Messaggio vuoto$"):
        await e.mgr.send(r["id"], "  ", 0, None)
    with pytest.raises(ValueError, match=r"^Messaggio troppo lungo \(max 200 byte\)$"):
        await e.mgr.send(r["id"], "è" * 101, 0, None)
    await e.mgr.send(r["id"], "è" * 100, 0, None)  # 200 byte esatti
    FakeConnector.instances[0].state_name = "reconnecting"
    with pytest.raises(ValueError, match="^Radio non connessa$"):
        await e.mgr.send(r["id"], "ciao", 0, None)
    FakeConnector.instances[0].state_name = "connected"
    with pytest.raises(ValueError, match="Destinatario"):
        await e.mgr.send(r["id"], "ciao", 0, "pippo")
    with pytest.raises(KeyError):
        await e.mgr.send("rnope", "ciao", 0, None)
    await settle()


async def test_send_provisional_then_definitive_then_ack():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    fc = FakeConnector.instances[0]
    fc.gate = asyncio.Event()
    e.drain()
    msg = await e.mgr.send(r["id"], "ciao", 0, "!00000042")
    assert msg["status"] == "sending" and msg["key"] == f"out:{r['id']}:pending-1"
    assert msg["to"] == "!00000042" and msg["direction"] == "out" and msg["radio_id"] == r["id"]
    assert [m["key"] for m in e.live.messages] == [msg["key"]]
    assert e.drain()[0]["message"]["status"] == "sending"
    fc.gate.set()
    await settle()
    (final,) = e.drain()
    final = final["message"]
    assert final["key"] == f"out:{r['id']}:501" and final["status"] == "sent"
    assert final["replaces"] == msg["key"] and final["packet_id"] == 501
    assert [m["key"] for m in e.live.messages] == [final["key"]]
    assert "replaces" not in e.live.messages[0]
    assert fc.sent == [("ciao", 0, "!00000042")]
    fc.on_ack(r["id"], 501, True, None)
    assert e.drain() == [{"type": "message_status", "key": final["key"], "status": "acked"}]
    assert e.live.messages[0]["status"] == "acked"
    fc.on_ack(r["id"], 501, False, "TIMEOUT")
    assert e.drain()[0]["status"] == "failed"


async def test_send_broadcast_stores_ffffffff_and_none_destination():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    msg = await e.mgr.send(r["id"], "tutti", 1, None)
    assert msg["to"] == "!ffffffff"
    await settle()
    assert FakeConnector.instances[0].sent == [("tutti", 1, None)]
    assert e.store.radio_messages(None, 10)[0]["to"] == "!ffffffff"


async def test_send_failure_marks_failed():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    FakeConnector.instances[0].fail = "Invio fallito: X"
    msg = await e.mgr.send(r["id"], "ciao", 0, None)
    e.drain()
    await settle()
    assert e.drain() == [{"type": "message_status", "key": msg["key"], "status": "failed"}]
    assert e.live.messages[0]["status"] == "failed"


async def test_state_change_publishes_radios_and_marks_local():
    e = Env()
    await e.mgr.add("usb", "COM5", "A")
    radios_events = [x for x in e.drain() if x["type"] == "radios"]
    assert radios_events and radios_events[-1]["radios"][0]["state"] == "connected"
    node = e.live.nodes[0xA1B2C3D4]
    assert node["is_local_radio"] is True and node["is_mine"] is True
    FakeConnector.instances[0].set("reconnecting")
    assert e.drain()[-1]["radios"][0]["state"] == "reconnecting"


async def test_start_connects_only_auto_connect_and_stop_stops_all():
    e = Env()
    e.store.save_radio({"id": "r00000001", "name": "A", "kind": "usb", "address": "COM5",
                        "auto_connect": True})
    e.store.save_radio({"id": "r00000002", "name": "B", "kind": "ble", "address": "AA:BB",
                        "auto_connect": False})
    mgr = RadioManager(e.store, e.ingestor, e.bus, None, FakeHub(),
                       connector_factory=FakeConnector)
    a, b = FakeConnector.instances[-2:]
    await mgr.start()
    assert (a.starts, b.starts) == (1, 0)
    await mgr.stop()
    assert (a.stops, b.stops) == (1, 1)


async def test_connect_disconnect_persist_auto_connect():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    await e.mgr.disconnect(r["id"])
    assert e.store.list_radios()[0]["auto_connect"] is False
    await e.mgr.connect(r["id"])
    assert e.store.list_radios()[0]["auto_connect"] is True
    assert FakeConnector.instances[0].starts == 2


async def test_radio_messages_store_filters_and_orders():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    e.store.add_message({"key": "1:1", "from": "!00000001", "to": "!ffffffff", "time": 5,
                         "text": "mqtt", "source": "mqtt"})
    e.ingestor.record_outgoing(r["id"], MY_ID, 1, "uno", 0, "!ffffffff", time_=100)
    e.ingestor.record_outgoing(r["id"], MY_ID, 2, "due", 0, "!ffffffff", time_=200)
    out = e.store.radio_messages(None, 10)
    assert sorted(m["text"] for m in out) == ["due", "uno"]
    assert [m["text"] for m in out] == ["due", "uno"]
    assert all(m["radio_id"] == r["id"] and m["direction"] == "out" for m in out)
    assert len(e.store.radio_messages(None, 1)) == 1
    assert e.store.radio_messages(0, 10) == []


async def test_early_ack_during_send_is_applied_to_definitive_message():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    fc = FakeConnector.instances[0]
    orig = fc.send_text

    async def send_with_early_ack(text, ch, dest):
        pid = await orig(text, ch, dest)
        fc.on_ack(r["id"], pid, True, None)
        return pid

    fc.send_text = send_with_early_ack
    msg = await e.mgr.send(r["id"], "ciao", 0, "!00000042")
    e.drain()
    await settle()
    events = e.drain()
    key = f"out:{r['id']}:501"
    assert {"type": "message_status", "key": key, "status": "acked"} in events
    assert e.live.messages[0]["status"] == "acked"
    assert e.store.radio_messages(None, 5)[0]["status"] == "acked"
    assert e.live.messages[0]["time"] == msg["time"]
    assert e.mgr._early_acks == {}


async def test_address_stored_as_typed_but_duplicates_case_insensitive():
    e = Env()
    r = await e.mgr.add("ble", "  aa:bb:cc  ", "x")
    assert r["address"] == "aa:bb:cc"
    with pytest.raises(ValueError, match="già aggiunta"):
        await e.mgr.add("ble", "AA:BB:CC", "y")
