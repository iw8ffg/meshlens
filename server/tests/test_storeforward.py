import base64
import json

import pytest
from google.protobuf.json_format import MessageToDict
from meshtastic.protobuf.storeforward_pb2 import StoreAndForward

from meshlens.db import connect
from meshlens.events import MeshEvent, TextData
from meshlens.live import LiveState
from meshlens.rf_convert import packet_to_event
from meshlens.store import Store
from meshlens.storeforward import (
    REFUSED_PUBLIC, SfError, StoreForwardService, parse_sf,
)

NOW = 1_800_000_000.0
ROUTER = 0xA1
ME = 0xB2
RR = StoreAndForward.RequestResponse


class Clock:
    def __init__(self):
        self.t = NOW

    def __call__(self):
        return self.t


class FakeBus:
    def __init__(self):
        self.msgs = []

    def publish(self, msg):
        self.msgs.append(msg)

    def last(self, kind):
        return [m for m in self.msgs if m["type"] == kind][-1]


class FakeConnector:
    def __init__(self, calls):
        self.calls = calls
        self.status = "connected"

    def state(self):
        return {"state": self.status}

    async def send_storeforward(self, dest_num, rr, window_min, channel_index):
        self.calls.append(("send_storeforward", dest_num, rr, window_min, channel_index))
        return 77


@pytest.fixture
def env():
    conn = connect(":memory:")
    store = Store(conn)
    live = LiveState()
    bus = FakeBus()
    clock = Clock()
    calls, events = [], []
    radios = {"r1": FakeConnector(calls)}

    def connector(rid):
        return radios[rid]

    sf = StoreForwardService(store, live, events.append, bus, connector, clock=clock)
    return sf, store, live, bus, clock, radios, calls, events


def sf_packet(msg: StoreAndForward, *, frm=ROUTER, to=ME, pid=500, channel=1, rx_time=None,
              payload=True):
    decoded = {"portnum": "STORE_FORWARD_APP"}
    if payload is True:
        decoded["payload"] = msg.SerializeToString()
    elif payload is not None:
        decoded["payload"] = payload
    pkt = {"from": frm, "to": to, "id": pid, "channel": channel, "decoded": decoded,
           "rxSnr": 5.0, "rxRssi": -90, "hopStart": 3, "hopLimit": 3}
    if rx_time is not None:
        pkt["rxTime"] = rx_time
    return pkt


def sf_event(msg, clock, **kw):
    ev = packet_to_event(sf_packet(msg, **kw), "r1", clock())
    assert ev is not None
    return ev


def heartbeat(period=900):
    return StoreAndForward(rr=RR.Value("ROUTER_HEARTBEAT"),
                           heartbeat=StoreAndForward.Heartbeat(period=period))


def test_parse_sf():
    p = parse_sf(sf_packet(heartbeat(), rx_time=0))
    assert p.rr == "ROUTER_HEARTBEAT"
    assert p.heartbeat == {"period": 900, "secondary": False}
    assert p.stats is None and p.history is None and p.text is None and p.rx_time is None
    assert parse_sf(sf_packet(heartbeat(), payload=b"\xff\xff\xff")) is None
    # ricaduta sul dict della libreria (MessageToDict: camelCase, bytes in base64)
    text_msg = StoreAndForward(rr=RR.Value("ROUTER_TEXT_BROADCAST"), text="ciao".encode())
    pkt = sf_packet(text_msg, payload=b"\xff\xff\xff", rx_time=NOW - 10)
    pkt["decoded"]["storeforward"] = MessageToDict(text_msg)
    assert pkt["decoded"]["storeforward"]["text"] == base64.b64encode(b"ciao").decode()
    p = parse_sf(pkt)
    assert p.rr == "ROUTER_TEXT_BROADCAST" and p.text == b"ciao" and p.rx_time == NOW - 10
    stats = StoreAndForward(rr=RR.Value("ROUTER_STATS"), stats=StoreAndForward.Statistics(
        messages_saved=120, messages_max=3000, return_max=100, return_window=240))
    p = parse_sf(sf_packet(stats))
    assert p.stats["messages_saved"] == 120 and p.stats["return_window"] == 240


def test_rf_convert_branch():
    ev = packet_to_event(sf_packet(heartbeat()), "r1", NOW)
    assert ev.kind == "storeforward" and ev.payload.rr == "ROUTER_HEARTBEAT"
    assert ev.from_node == ROUTER and ev.radio_id == "r1"
    assert ev.replayed is False


def test_heartbeat_registers_router(env):
    sf, store, live, bus, clock, *_ = env
    live.nodes[ROUTER] = {"long_name": "Router Vesuvio"}
    sf.handle(sf_event(heartbeat(), clock))
    row = store.conn.execute("SELECT * FROM sf_routers WHERE num=?", (ROUTER,)).fetchone()
    assert row is not None and row["radio_id"] == "r1" and row["heartbeat_period"] == 900
    routers = bus.last("sf_routers")["routers"]
    assert routers == [{"id": "!000000a1", "name": "Router Vesuvio", "radio_id": "r1",
                        "last_seen": NOW, "heartbeat_period": 900, "secondary": False,
                        "stats": None, "last_request": None}]
    clock.t += 900
    sf.handle(sf_event(heartbeat(), clock))
    assert sf.routers()[0]["last_seen"] == NOW + 900
    # le statistiche si aggiungono senza perdere il periodo del heartbeat
    stats = StoreAndForward(rr=RR.Value("ROUTER_STATS"), stats=StoreAndForward.Statistics(
        messages_saved=120, messages_max=3000, return_max=100, return_window=240))
    sf.handle(sf_event(stats, clock))
    r = sf.routers()[0]
    assert r["heartbeat_period"] == 900 and r["stats"]["messages_max"] == 3000
    assert json.loads(store.conn.execute("SELECT stats FROM sf_routers").fetchone()[0])


async def test_request_flow(env):
    sf, store, live, bus, clock, radios, calls, events = env
    job = await sf.request("r1", ROUTER, 240, 1)
    assert calls == [("send_storeforward", ROUTER, "CLIENT_HISTORY", 240, 1)]
    assert job["status"] == "waiting" and job["router_id"] == "!000000a1"
    assert job["window_min"] == 240 and job["channel_index"] == 1 and job["received"] == 0
    assert bus.last("sf_job")["job"]["id"] == job["id"]
    hist = StoreAndForward(rr=RR.Value("ROUTER_HISTORY"),
                           history=StoreAndForward.History(history_messages=3, window=240))
    clock.t += 2
    sf.handle(sf_event(hist, clock))
    j = sf.jobs()[0]
    assert j["status"] == "receiving" and j["expected"] == 3
    orig = NOW - 3600
    for i in range(3):
        clock.t += 1
        msg = StoreAndForward(rr=RR.Value("ROUTER_TEXT_BROADCAST"), text=f"msg {i}".encode())
        sf.handle(sf_event(msg, clock, frm=0x10 + i, pid=900 + i, rx_time=orig))
    assert len(events) == 3
    for i, e in enumerate(events):
        assert isinstance(e, MeshEvent) and e.kind == "text" and e.replayed is True
        assert e.to_node == 0xFFFFFFFF and e.rx_time == orig
        assert e.payload == TextData(f"msg {i}")
        assert e.from_node == 0x10 + i and e.packet_id == 900 + i
        assert e.channel == "1" and e.radio_id == "r1" and e.source == "rf"
        assert e.snr is None and e.rssi is None and e.hops is None
    assert sf.jobs()[0]["received"] == 3
    sf.check()
    j = sf.jobs()[0]
    assert j["status"] == "done" and j["received"] == 3 and j["ended"] == clock.t
    assert bus.last("sf_job")["job"]["status"] == "done"


async def test_direct_replay_keeps_destination(env):
    sf, *_, clock, radios, calls, events = env
    msg = StoreAndForward(rr=RR.Value("ROUTER_TEXT_DIRECT"), text=b"privato")
    sf.handle(sf_event(msg, clock, frm=0x10, to=ME, pid=42))
    assert events[0].to_node == ME and events[0].rx_time == NOW  # senza rxTime: ora attuale


async def test_replay_dedup(env):
    sf, store, live, bus, clock, radios, calls, events = env
    await sf.request("r1", ROUTER, 60, 1)
    store.add_message({"key": "16:1", "from": "!00000010", "to": "!ffffffff", "channel": "1",
                       "text": "a", "time": int(NOW), "country": None, "source": "rf",
                       "direction": "in", "radio_id": "r1", "channel_index": 1,
                       "packet_id": 1, "status": None, "broker": None})
    live.messages.append({"key": "17:2", "text": "b"})
    for frm, pid in ((0x10, 1), (0x11, 2)):
        msg = StoreAndForward(rr=RR.Value("ROUTER_TEXT_BROADCAST"), text=b"x")
        sf.handle(sf_event(msg, clock, frm=frm, pid=pid, rx_time=NOW - 60))
    assert events == []
    j = sf.jobs()[0]
    assert j["duplicates"] == 2 and j["received"] == 0 and j["status"] == "receiving"


async def test_refused_public(env):
    sf, store, live, bus, clock, radios, calls, events = env
    await sf.request("r1", ROUTER, 60, 0)
    text = MeshEvent(source="rf", from_node=ROUTER, to_node=ME, packet_id=5, channel="0",
                     rx_time=NOW, snr=1.0, rssi=-80, hops=0, gateway_id=None, radio_id="r1",
                     kind="text", payload=TextData(REFUSED_PUBLIC))
    sf.observe_text(text)
    j = sf.jobs()[0]
    assert j["status"] == "failed"
    assert j["error"] == ("Il router rifiuta le richieste sul canale pubblico: scegli un "
                          "canale privato condiviso con il router")


async def test_refused_busy(env):
    from meshlens.storeforward import REFUSED_BUSY
    sf, *_, clock, radios, calls, events = env
    await sf.request("r1", ROUTER, 60, 1)
    sf.observe_text(MeshEvent(source="rf", from_node=ROUTER, to_node=ME, packet_id=5,
                              channel="1", rx_time=NOW, snr=None, rssi=None, hops=0,
                              gateway_id=None, radio_id="r1", kind="text",
                              payload=TextData(REFUSED_BUSY)))
    j = sf.jobs()[0]
    assert j["status"] == "failed" and j["error"] == "Router occupato: riprova tra poco"


async def test_timeouts(env):
    sf, store, live, bus, clock, radios, calls, events = env
    await sf.request("r1", ROUTER, 60, 1)
    clock.t += 60
    sf.check()
    assert sf.jobs()[0]["status"] == "waiting"
    clock.t += 1
    sf.check()
    j = sf.jobs()[0]
    assert j["status"] == "failed" and j["error"] == "Nessuna risposta dal router"
    clock.t += 300  # oltre il limite di frequenza
    job = await sf.request("r1", ROUTER, 60, 1)
    radios["r1"].status = "disconnected"
    sf.check()
    j = [x for x in sf.jobs() if x["id"] == job["id"]][0]
    assert j["status"] == "failed" and j["error"] == "Radio scollegata durante il recupero"


async def test_receiving_idle_timeout(env):
    sf, *_, clock, radios, calls, events = env
    await sf.request("r1", ROUTER, 60, 1)
    hist = StoreAndForward(rr=RR.Value("ROUTER_HISTORY"),
                           history=StoreAndForward.History(history_messages=5))
    sf.handle(sf_event(hist, clock))
    clock.t += 29
    sf.check()
    assert sf.jobs()[0]["status"] == "receiving"
    clock.t += 1
    sf.check()
    assert sf.jobs()[0]["status"] == "done"


async def test_request_errors(env):
    sf, *_, clock, radios, calls, events = env
    radios["r1"].status = "connecting"
    with pytest.raises(SfError) as e:
        await sf.request("r1", ROUTER, 60, 1)
    assert e.value.status == 409 and str(e.value) == "Radio non connessa"
    radios["r1"].status = "connected"
    await sf.request("r1", ROUTER, 60, 1)
    with pytest.raises(SfError) as e:
        await sf.request("r1", 0xC3, 60, 1)
    assert e.value.status == 409
    assert str(e.value) == "C'è già un recupero in corso su questa radio"


async def test_rate_limit(env):
    sf, store, live, bus, clock, radios, calls, events = env
    await sf.request("r1", ROUTER, 60, 1)
    sf.handle(sf_event(StoreAndForward(rr=RR.Value("ROUTER_BUSY")), clock))
    assert sf.jobs()[0]["status"] == "failed"
    clock.t += 10
    with pytest.raises(SfError) as e:
        await sf.request("r1", ROUTER, 60, 1)
    assert e.value.status == 429 and e.value.retry_after == 290
    assert str(e.value) == "Attendi 290 s prima di una nuova richiesta a questo router"
    assert len(calls) == 1


async def test_probe(env):
    sf, *_, clock, radios, calls, events = env
    await sf.probe("r1", ROUTER, 1)
    assert calls == [("send_storeforward", ROUTER, "CLIENT_STATS", None, 1)]
    assert sf.jobs() == []


async def test_radio_send_storeforward():
    from test_radio import FakeIface, Harness, connected
    iface = FakeIface()
    h = Harness(lambda cfg, n: iface)
    await connected(h)
    pid = await h.conn.send_storeforward(ROUTER, "CLIENT_HISTORY", 240, 1)
    data, dest, port, want_response, channel = iface.sent_data[-1]
    assert pid == iface.next_id and dest == ROUTER and port == 65
    assert want_response is False and channel == 1
    msg = StoreAndForward.FromString(data.SerializeToString())
    assert msg.rr == RR.Value("CLIENT_HISTORY") and msg.history.window == 240
    await h.conn.send_storeforward(ROUTER, "CLIENT_STATS", None, 0)
    msg = StoreAndForward.FromString(iface.sent_data[-1][0].SerializeToString())
    assert msg.rr == RR.Value("CLIENT_STATS") and not msg.HasField("history")
    await h.conn.stop()


async def test_concurrent_radios_rate_limited(env):
    import asyncio
    sf, store, live, bus, clock, radios, calls, events = env

    class Slow(FakeConnector):
        async def send_storeforward(self, *a):
            await asyncio.sleep(0.01)
            return await super().send_storeforward(*a)

    radios["r1"] = Slow(calls)
    radios["r2"] = Slow(calls)
    res = await asyncio.gather(sf.request("r1", ROUTER, 60, 1), sf.request("r2", ROUTER, 60, 1),
                               return_exceptions=True)
    errs = [r for r in res if isinstance(r, SfError)]
    assert len(errs) == 1 and errs[0].status == 429 and len(calls) == 2 - 1


async def test_failed_send_releases_rate_limit(env):
    sf, store, live, bus, clock, radios, calls, events = env

    async def boom(*a):
        raise RuntimeError("giu")

    radios["r1"].send_storeforward = boom
    with pytest.raises(SfError):
        await sf.request("r1", ROUTER, 60, 1)
    assert ROUTER not in sf._last_request


async def test_history_from_other_router_ignored(env):
    sf, *_, clock, radios, calls, events = env
    await sf.request("r1", ROUTER, 60, 1)
    hist = StoreAndForward(rr=RR.Value("ROUTER_HISTORY"),
                           history=StoreAndForward.History(history_messages=3))
    sf.handle(sf_event(hist, clock, frm=0xC3))
    assert sf.jobs()[0]["status"] == "waiting"


async def test_last_request_persisted_for_unknown_router(env):
    sf, store, live, bus, clock, radios, calls, events = env
    await sf.request("r1", ROUTER, 60, 1)
    row = store.conn.execute("SELECT last_request FROM sf_routers WHERE num=?",
                             (ROUTER,)).fetchone()
    assert row[0] == NOW and sf.routers() == []  # persistito, ma non elencato senza heartbeat


async def test_replay_skips_own_outgoing(env):
    sf, store, live, bus, clock, radios, calls, events = env
    store.add_message({"key": "99:7", "from": "!00000099", "to": "!ffffffff", "channel": "1",
                       "text": "mio", "time": int(NOW), "country": None, "source": "rf",
                       "direction": "out", "radio_id": "r2", "channel_index": 1,
                       "packet_id": 7, "status": None, "broker": None})
    msg = StoreAndForward(rr=RR.Value("ROUTER_TEXT_BROADCAST"), text=b"mio")
    sf.handle(sf_event(msg, clock, frm=0x99, pid=7, rx_time=NOW - 60))
    assert events == []


async def test_replay_keeps_reply_and_emoji(env):
    sf, *_, clock, radios, calls, events = env
    pkt = sf_packet(StoreAndForward(rr=RR.Value("ROUTER_TEXT_BROADCAST"), text="\U0001F44D".encode()),
                    frm=0x10, pid=77, rx_time=NOW - 60)
    pkt["decoded"].update({"replyId": 9, "emoji": 1})
    ev = packet_to_event(pkt, "r1", clock())
    sf.handle(ev)
    assert events[0].payload == TextData("\U0001F44D", reply_id=9, emoji=True)
    # senza replyId/emoji restano i valori predefiniti
    sf.handle(sf_event(StoreAndForward(rr=RR.Value("ROUTER_TEXT_BROADCAST"), text=b"x"),
                       clock, frm=0x11, pid=78, rx_time=NOW - 60))
    assert events[1].payload == TextData("x") and events[1].payload.reply_id is None


async def test_old_replay_does_not_notify(env):
    from meshlens.notify import Notifier
    sf, *_, clock, radios, calls, events = env
    toasts = []
    n = Notifier(lambda: {"notify_toast": True, "notify_keywords": ["aiuto"]},
                 lambda: (lambda t, b: toasts.append((t, b))), lambda: [], clock,
                 send_telegram=lambda *a: None, run_bg=lambda f: f())
    sf.handle(sf_event(StoreAndForward(rr=RR.Value("ROUTER_TEXT_BROADCAST"), text=b"aiuto"),
                       clock, frm=0x10, pid=90, rx_time=NOW - 3600))
    e = events[0]
    assert e.replayed and e.rx_time == NOW - 3600
    m = {"key": f"{e.from_node}:{e.packet_id}", "from": "!00000010", "text": e.payload.text,
         "direction": "in", "emoji": False, "time": int(e.rx_time)}
    assert n.on_message(m) is None and toasts == []
