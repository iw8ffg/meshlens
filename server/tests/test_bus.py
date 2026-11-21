import asyncio

from meshlens.api import send_with_timeout
from meshlens.bus import RESYNC, Bus


def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_bus_overflow_replaces_backlog_with_single_resync():
    bus = Bus(maxsize=3)
    q = bus.subscribe()
    m = [{"type": "message", "n": i} for i in range(7)]
    for x in m[1:5]:
        bus.publish(x)
    assert q.qsize() == 2 and list(q._queue) == [RESYNC, m[4]]
    bus.publish(m[5])
    assert list(q._queue) == [RESYNC, m[4], m[5]]
    bus.publish(m[6])
    assert list(q._queue) == [RESYNC, m[6]]
    assert bus.resyncs == 2


def test_bus_other_subscribers_unaffected():
    bus = Bus(maxsize=3)
    slow = bus.subscribe()
    fast = bus.subscribe()
    got = []
    for i in range(1, 5):
        bus.publish({"n": i})
        got += _drain(fast)
    assert got == [{"n": i} for i in range(1, 5)]
    assert RESYNC not in got
    assert slow.get_nowait() == RESYNC


class _Stuck:
    async def send_json(self, msg):
        await asyncio.Event().wait()


class _Ok:
    async def send_json(self, msg):
        pass


def test_send_with_timeout_false_on_stuck_client():
    assert asyncio.run(send_with_timeout(_Stuck(), {"a": 1}, timeout=0.05)) is False
    assert asyncio.run(send_with_timeout(_Ok(), {"a": 1}, timeout=0.05)) is True
