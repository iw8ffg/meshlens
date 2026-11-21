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
from meshlens.events import MeshEvent, RouteData
from meshlens.radio_manager import NoRadioConnected, RadioManager, TracerouteThrottled
from meshlens.store import Store

MY_ID = "!a1b2c3d4"


class FakeConnector:
    instances = []

    def __init__(self, cfg, hub, on_event, on_state, on_ack, iface_factory, on_traceroute=None):
        self.cfg, self.on_state, self.on_ack = cfg, on_state, on_ack
        self.on_traceroute, self.traces = on_traceroute, []
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


    async def send_traceroute(self, dest_num, channel_index=0):
        if self.fail:
            raise RuntimeError(self.fail)
        self.traces.append((dest_num, channel_index))
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
            lambda k, s, e=None: self.bus.publish(
                {"type": "message_status", "key": k, "status": s}))
        self.now = 1000.0
        self.ports = [SimpleNamespace(device="COM5", description="CP210x", vid=0x10C4, pid=0xEA60),
                      SimpleNamespace(device="COM1", description="Porta", vid=None, pid=None)]
        self.scan_threads = []

        def scan():
            self.scan_threads.append(threading.current_thread())
            return [{"address": "AA:BB", "name": "Meshtastic_1a2b"}]

        self.mgr = RadioManager(self.store, self.ingestor, self.bus, None, FakeHub(),
                                connector_factory=FakeConnector, iface_factory=lambda c: None,
                                list_ports_fn=lambda: self.ports, ble_scan_fn=scan,
                                clock=lambda: self.now)

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


async def test_stop_stops_connectors_concurrently():
    e = Env()
    await e.mgr.add("usb", "COM5", "A")
    await e.mgr.add("usb", "COM6", "B")
    running = [0]
    peak = [0]

    def slow(conn):
        async def stop():
            running[0] += 1
            peak[0] = max(peak[0], running[0])
            await asyncio.sleep(0.05)
            running[0] -= 1
        conn.stop = stop
    for c in FakeConnector.instances[-2:]:
        slow(c)
    await e.mgr.stop()
    assert peak[0] == 2


TARGET = "!00000042"


def route_event(radio_node=0xA1B2C3D4, target=0x42, request_id=501):
    payload = RouteData(request_id, [0x77], [5.0, 2.25], [], [-3.0])
    return MeshEvent(source="rf", from_node=target, to_node=radio_node, packet_id=9,
                     channel="0", rx_time=1000, snr=None, rssi=None, hops=None,
                     gateway_id=None, radio_id="r", kind="traceroute", payload=payload)


async def test_traceroute_response_resolves_pending():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    fc = FakeConnector.instances[0]
    e.drain()
    res = await e.mgr.traceroute(TARGET, None)
    assert fc.traces == [(0x42, 0)]
    assert res["status"] == "pending" and res["radio_id"] == r["id"]
    assert res["target_id"] == TARGET and res["forward"] == [] and res["time"] == 1000.0
    assert e.drain() == [{"type": "traceroute", "result": res}]
    fc.on_traceroute(r["id"], 501, route_event())
    out = e.drain()
    assert len(out) == 1 and out[0]["type"] == "traceroute"
    done = out[0]["result"]
    assert done["id"] == res["id"] and done["status"] == "ok" and done["error"] is None
    assert done["forward"] == [{"id": MY_ID, "snr": None}, {"id": "!00000077", "snr": 5.0},
                               {"id": TARGET, "snr": 2.25}]
    assert done["back"] == [{"id": TARGET, "snr": None}, {"id": MY_ID, "snr": -3.0}]
    assert e.store.traceroutes(0x42)[0] == done
    e.now += 100
    e.mgr.check_traceroutes()  # gia' risolto: non scade
    assert e.drain() == [] and e.store.traceroutes(0x42)[0]["status"] == "ok"
    fc.on_traceroute(r["id"], 501, route_event())  # risposta doppia o sconosciuta: ignorata
    assert e.drain() == []


async def test_traceroute_routing_error_fails_and_is_not_a_chat_ack():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    fc = FakeConnector.instances[0]
    await e.mgr.traceroute(TARGET, None)
    e.drain()
    fc.on_ack(r["id"], 501, True, None)  # ack implicito: ignorato
    assert e.drain() == [] and e.mgr._early_acks == {}
    fc.on_ack(r["id"], 501, False, "NO_RESPONSE")
    out = e.drain()
    assert e.mgr._early_acks == {}
    res = out[0]["result"]
    assert res["status"] == "failed" and res["error"] == "Nessuna risposta dal nodo"
    assert e.store.traceroutes(0x42)[0]["status"] == "failed"


async def test_traceroute_timeout_after_60s():
    e = Env()
    await e.mgr.add("usb", "COM5", "A")
    await e.mgr.traceroute(TARGET, None)
    e.drain()
    e.now += 59
    e.mgr.check_traceroutes()
    assert e.drain() == []
    e.now += 2
    e.mgr.check_traceroutes()
    out = e.drain()
    assert out[0]["result"]["status"] == "timeout"
    assert e.store.traceroutes(0x42)[0]["status"] == "timeout"
    e.mgr.check_traceroutes()
    assert e.drain() == []


async def test_traceroute_throttled_per_radio():
    e = Env()
    r1 = await e.mgr.add("usb", "COM5", "A")
    r2 = await e.mgr.add("usb", "COM6", "B")
    await e.mgr.traceroute(TARGET, r1["id"])
    e.now += 10
    with pytest.raises(TracerouteThrottled) as exc:
        await e.mgr.traceroute(TARGET, r1["id"])
    assert exc.value.wait_s == 20
    await e.mgr.traceroute(TARGET, r2["id"])  # l'altra radio ha il suo limite
    e.now += 20
    await e.mgr.traceroute(TARGET, r1["id"])


async def test_traceroute_send_failure_does_not_consume_the_slot():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    FakeConnector.instances[0].fail = "Invio scaduto"
    with pytest.raises(ValueError, match="Invio scaduto"):
        await e.mgr.traceroute(TARGET, r["id"])
    FakeConnector.instances[0].fail = None
    await e.mgr.traceroute(TARGET, r["id"])
    assert len(e.store.traceroutes(0x42)) == 1


async def test_traceroute_picks_radio_with_fewest_hops():
    e = Env()
    r1 = await e.mgr.add("usb", "COM5", "A")
    r2 = await e.mgr.add("usb", "COM6", "B")
    r3 = await e.mgr.add("usb", "COM7", "C")
    FakeConnector.instances[2].set("disconnected")
    e.live.nodes[0x42] = {"heard_by": {r1["id"]: {"hops": 3}, r2["id"]: {"hops": 1},
                                       r3["id"]: {"hops": 0}}}
    res = await e.mgr.traceroute(TARGET, None)
    assert res["radio_id"] == r2["id"]  # r3 e' scollegata
    e.live.nodes.pop(0x42)
    e.now += 100
    res = await e.mgr.traceroute(TARGET, None)  # nessuno lo sente: la prima collegata
    assert res["radio_id"] == r1["id"]


async def test_traceroute_no_radio_connected():
    e = Env()
    with pytest.raises(NoRadioConnected):
        await e.mgr.traceroute(TARGET, None)
    r = await e.mgr.add("usb", "COM5", "A")
    FakeConnector.instances[0].set("disconnected")
    with pytest.raises(NoRadioConnected):
        await e.mgr.traceroute(TARGET, None)
    with pytest.raises(NoRadioConnected):
        await e.mgr.traceroute(TARGET, r["id"])
    with pytest.raises(KeyError):
        await e.mgr.traceroute(TARGET, "rnope")
    with pytest.raises(ValueError):
        await e.mgr.traceroute("xyz", None)


async def test_stale_pending_traceroutes_become_timeout_at_startup():
    e = Env()
    tid = e.store.add_traceroute("r1", 0x42, 900.0)
    e.store.commit()
    assert e.store.traceroutes(0x42)[0]["status"] == "pending"
    RadioManager(e.store, e.ingestor, e.bus, None, FakeHub(), connector_factory=FakeConnector,
                 clock=lambda: e.now)
    row = e.store.traceroutes(0x42)[0]
    assert row["id"] == tid and row["status"] == "timeout"


async def test_traceroute_early_reply_during_send_resolves_ok():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    fc = FakeConnector.instances[0]
    orig = fc.send_traceroute

    async def send_with_early_reply(dest, ch=0):
        pid = await orig(dest, ch)
        fc.on_traceroute(r["id"], pid, route_event(request_id=pid))
        return pid

    fc.send_traceroute = send_with_early_reply
    await e.mgr.traceroute(TARGET, None)
    row = e.store.traceroutes(0x42)[0]
    assert row["status"] == "ok" and row["forward"][1] == {"id": "!00000077", "snr": 5.0}
    assert e.mgr._early_acks == {} and e.mgr._early_traces == {}


async def test_traceroute_early_routing_error_keeps_reason_and_skips_chat_buffer():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    fc = FakeConnector.instances[0]
    orig = fc.send_traceroute

    async def send_with_early_error(dest, ch=0):
        pid = await orig(dest, ch)
        fc.on_ack(r["id"], pid, False, "NO_ROUTE")
        return pid

    fc.send_traceroute = send_with_early_error
    await e.mgr.traceroute(TARGET, None)
    row = e.store.traceroutes(0x42)[0]
    assert row["status"] == "failed" and row["error"] == "Nessun percorso verso il nodo"
    assert e.mgr._early_acks == {} and e.mgr._early_traces == {}


async def test_chat_ack_during_traceroute_send_reaches_message():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    fc = FakeConnector.instances[0]
    await e.mgr.send(r["id"], "ciao", 0, "!00000042")
    await settle()
    chat_key = e.live.messages[0]["key"]
    chat_pid = int(chat_key.rsplit(":", 1)[1])
    orig = fc.send_traceroute

    async def send_with_chat_ack(dest, ch=0):
        pid = await orig(dest, ch)
        fc.on_ack(r["id"], chat_pid, True, None)  # ack del messaggio precedente
        return pid

    fc.send_traceroute = send_with_chat_ack
    await e.mgr.traceroute(TARGET, None)
    assert e.live.messages[0]["status"] == "acked"
    assert e.store.traceroutes(0x42)[0]["status"] == "pending"


async def test_traceroute_slot_released_if_store_fails():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")

    def boom(*a):
        raise RuntimeError("db")

    e.store.add_traceroute = boom
    with pytest.raises(RuntimeError):
        await e.mgr.traceroute(TARGET, r["id"])
    assert r["id"] not in e.mgr._last_trace and e.mgr._tracing == set()


async def test_traceroute_early_reply_returns_final_state_and_canonical_target():
    e = Env()
    r = await e.mgr.add("usb", "COM5", "A")
    fc = FakeConnector.instances[0]
    orig = fc.send_traceroute

    async def send_with_early_reply(dest, ch=0):
        pid = await orig(dest, ch)
        fc.on_traceroute(r["id"], pid, route_event(request_id=pid))
        return pid

    fc.send_traceroute = send_with_early_reply
    res = await e.mgr.traceroute("!0000004A", None)
    assert res["status"] == "ok" and res["target_id"] == "!0000004a"
