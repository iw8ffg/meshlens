"""Bus di messaggi in memoria verso i client WebSocket."""
import asyncio

QUEUE_SIZE = 1000
RESYNC = {"type": "resync"}


class Bus:
    def __init__(self, maxsize: int = QUEUE_SIZE):
        self._maxsize = maxsize
        self._subs: set[asyncio.Queue] = set()
        self.resyncs = 0

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, msg: dict) -> None:
        for q in self._subs:
            if q.full():
                # coda piena: il client e' troppo lento. Si svuota e si avvisa con un solo
                # "resync" (il client ricarica i dati) invece di perdere eventi in silenzio.
                while not q.empty():
                    q.get_nowait()
                q.put_nowait(RESYNC)
                self.resyncs += 1
            q.put_nowait(msg)
