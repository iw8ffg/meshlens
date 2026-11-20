"""Bus di messaggi in memoria verso i client WebSocket."""
import asyncio

QUEUE_SIZE = 1000


class Bus:
    def __init__(self, maxsize: int = QUEUE_SIZE):
        self._maxsize = maxsize
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, msg: dict) -> None:
        for q in self._subs:
            if q.full():
                q.get_nowait()  # scarta il piu vecchio
            q.put_nowait(msg)
