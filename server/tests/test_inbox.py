import asyncio
import threading

from meshlens.inbox import INBOX_BATCH, INBOX_MAX, EventInbox


class FakeLoop:
    """Registra i callback invece di eseguirli: il test decide quando farli girare."""

    def __init__(self):
        self.threadsafe: list = []
        self.soon: list = []

    def call_soon_threadsafe(self, fn, *args):
        self.threadsafe.append(fn)

    def call_soon(self, fn, *args):
        self.soon.append(fn)

    def run_all(self) -> int:
        runs = 0
        pending = self.threadsafe + self.soon
        self.threadsafe, self.soon = [], []
        while pending:
            pending.pop(0)()
            runs += 1
            pending += self.threadsafe + self.soon
            self.threadsafe, self.soon = [], []
        return runs


def test_defaults():
    assert INBOX_MAX == 5000 and INBOX_BATCH == 200


def test_inbox_drops_oldest_and_counts():
    loop, got = FakeLoop(), []
    inbox = EventInbox(loop, got.append, maxsize=5000)

    def produce():
        for i in range(10_000):
            inbox.put(i)

    t = threading.Thread(target=produce)
    t.start()
    t.join()
    assert inbox.dropped == 5000
    assert inbox.size() == 5000 and inbox.high_water == 5000
    assert len(loop.threadsafe) == 1  # un solo callback per l'intera raffica
    loop.run_all()
    assert got == list(range(5000, 10_000))
    assert inbox.size() == 0


def test_inbox_drains_in_batches():
    loop, got = FakeLoop(), []
    inbox = EventInbox(loop, got.append, batch=200)
    for i in range(450):
        inbox.put(i)
    assert len(loop.threadsafe) == 1
    runs = 0
    rescheduled = 0
    pending = loop.threadsafe
    loop.threadsafe = []
    while pending:
        pending.pop(0)()
        runs += 1
        rescheduled += len(loop.soon)
        pending += loop.soon
        loop.soon = []
    assert runs == 3 and rescheduled == 2
    assert loop.threadsafe == []
    assert got == list(range(450))
    # coda vuota: il put successivo rischedula di nuovo
    inbox.put(999)
    assert len(loop.threadsafe) == 1


def test_inbox_handler_exception_does_not_stop_batch(caplog):
    loop, got = FakeLoop(), []

    def handler(item):
        if item == 1:
            raise ValueError("evento difettoso")
        got.append(item)

    inbox = EventInbox(loop, handler)
    for i in range(3):
        inbox.put(i)
    loop.run_all()
    assert got == [0, 2]
    assert "Evento MQTT non elaborato" in caplog.text


def test_inbox_put_on_closed_loop_is_ignored():
    class ClosedLoop(FakeLoop):
        def call_soon_threadsafe(self, fn, *args):
            raise RuntimeError("Event loop is closed")

    inbox = EventInbox(ClosedLoop(), lambda item: None)
    inbox.put(1)  # nessuna eccezione
    assert inbox.size() == 1


async def test_inbox_no_orphan_after_drain():
    loop = asyncio.get_running_loop()
    got = []
    total = 20_000
    inbox = EventInbox(loop, got.append, maxsize=total, batch=50)

    def produce():
        for i in range(total):
            inbox.put(i)
            if i % 97 == 0:
                threading.Event().wait(0.0005)  # lascia chiudere i drain a meta' raffica

    t = threading.Thread(target=produce)
    t.start()
    while t.is_alive():
        await asyncio.sleep(0.001)
    t.join()
    for _ in range(2000):
        if len(got) == total:
            break
        await asyncio.sleep(0.005)
    assert got == list(range(total))
    assert inbox.size() == 0 and inbox.dropped == 0


def test_inbox_closed_loop_clears_scheduled_flag():
    class FlakyLoop(FakeLoop):
        closed = True

        def call_soon_threadsafe(self, fn, *args):
            if self.closed:
                raise RuntimeError("Event loop is closed")
            super().call_soon_threadsafe(fn, *args)

    loop, got = FlakyLoop(), []
    inbox = EventInbox(loop, got.append)
    inbox.put(1)
    loop.closed = False
    inbox.put(2)  # il flag non e' rimasto incastrato: si rischedula
    assert len(loop.threadsafe) == 1
    loop.run_all()
    assert got == [1, 2]


def test_inbox_base_exception_from_handler_does_not_wedge():
    loop, got = FakeLoop(), []

    def handler(item):
        if item == 0:
            raise KeyboardInterrupt
        got.append(item)

    inbox = EventInbox(loop, handler)
    inbox.put(0)
    try:
        loop.run_all()
    except KeyboardInterrupt:
        pass
    inbox.put(1)
    assert len(loop.threadsafe) == 1  # rischedulato: _scheduled non e' rimasto vero
    loop.run_all()
    assert got == [1]


def test_inbox_drops_raw_packets_before_events():
    from meshlens.events import PacketMeta, RawPacket
    raw = RawPacket(source="mqtt", from_node=1, to_node=2, packet_id=1, channel="c", rx_time=1.0,
                    snr=None, rssi=None, gateway_id=None, radio_id=None, broker=None,
                    relay_node=None, status="encrypted", meta=PacketMeta(None, None, None))
    loop, got = FakeLoop(), []
    inbox = EventInbox(loop, got.append, maxsize=8)
    for i in range(4):
        inbox.put(i)
    for _ in range(10):  # raffica di grezzi: tolgono solo grezzi
        inbox.put(raw)
    for i in range(4, 8):  # eventi a coda piena: partono i grezzi, non gli eventi
        inbox.put(i)
    loop.run_all()
    assert [x for x in got if not isinstance(x, RawPacket)] == list(range(8))
    assert inbox.size() == 0
