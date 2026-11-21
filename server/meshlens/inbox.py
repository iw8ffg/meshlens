"""Coda limitata tra un thread produttore (callback di paho) e il loop asyncio.

Con una raffica dal broker la coda non cresce senza limite: oltre `maxsize` si scartano
gli elementi piu' vecchi e si contano. Il loop riceve un solo callback per raffica e
consuma a blocchi di `batch`, cedendo il controllo tra un blocco e l'altro.
Ogni connettore ha la propria coda: piu' connettori possono alimentare lo stesso gestore."""
import asyncio
import collections
import logging
import threading
from typing import Callable

INBOX_MAX = 5000
INBOX_BATCH = 200
log = logging.getLogger(__name__)


class EventInbox:
    def __init__(self, loop: asyncio.AbstractEventLoop, handler: Callable[[object], None],
                 maxsize: int = INBOX_MAX, batch: int = INBOX_BATCH):
        self.loop = loop
        self.handler = handler
        self.maxsize = maxsize
        self.batch = batch
        self.dropped = 0
        self.high_water = 0
        self._items: collections.deque = collections.deque()
        self._lock = threading.Lock()
        self._scheduled = False

    def size(self) -> int:
        with self._lock:
            return len(self._items)

    def put(self, item: object) -> None:
        """Da qualsiasi thread. Se la coda e' piena si scarta l'elemento piu' vecchio."""
        with self._lock:
            if len(self._items) >= self.maxsize:
                self._items.popleft()
                self.dropped += 1
            self._items.append(item)
            if len(self._items) > self.high_water:
                self.high_water = len(self._items)
            if self._scheduled:
                return
            self._scheduled = True
        try:
            self.loop.call_soon_threadsafe(self._drain)
        except RuntimeError:  # loop chiuso durante lo spegnimento
            with self._lock:
                self._scheduled = False

    def _drain(self) -> None:
        """Sul loop: consegna al massimo `batch` elementi, poi si rischedula se ne restano."""
        with self._lock:
            n = min(self.batch, len(self._items))
            taken = [self._items.popleft() for _ in range(n)]
        try:
            for item in taken:
                try:
                    self.handler(item)
                except Exception:
                    log.exception("Evento MQTT non elaborato")  # gli altri proseguono
        finally:
            # anche con una BaseException dal gestore la coda non resta bloccata
            self._finish_drain()

    def _finish_drain(self) -> None:
        with self._lock:
            if not self._items:
                # azzerato sotto lock a coda vuota: un put successivo rischedula da se'
                self._scheduled = False
                return
        try:
            self.loop.call_soon(self._drain)
        except RuntimeError:  # loop chiuso: il prossimo put riprova
            with self._lock:
                self._scheduled = False
