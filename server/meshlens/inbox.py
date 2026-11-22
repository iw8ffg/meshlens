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

from .events import RawPacket

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
        # i RawPacket (solo ispettore) hanno una coda a parte: in una raffica si scartano per primi
        self._raws: collections.deque = collections.deque()
        self._lock = threading.Lock()
        self._scheduled = False

    def size(self) -> int:
        with self._lock:
            return len(self._items) + len(self._raws)

    def put(self, item: object) -> None:
        """Da qualsiasi thread. Se la coda e' piena si scarta l'elemento piu' vecchio,
        ma prima i pacchetti grezzi: gli eventi dei nodi hanno la precedenza."""
        with self._lock:
            is_raw = isinstance(item, RawPacket)
            total = len(self._items) + len(self._raws)
            if is_raw and len(self._raws) >= max(1, self.maxsize // 4):
                self._raws.popleft()
                self.dropped += 1
                total -= 1
            if total >= self.maxsize:
                (self._raws if self._raws else self._items).popleft()
                self.dropped += 1
            (self._raws if is_raw else self._items).append(item)
            size = len(self._items) + len(self._raws)
            if size > self.high_water:
                self.high_water = size
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
            taken = []
            for q in (self._items, self._raws):
                while q and len(taken) < self.batch:
                    taken.append(q.popleft())
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
            if not self._items and not self._raws:
                # azzerato sotto lock a coda vuota: un put successivo rischedula da se'
                self._scheduled = False
                return
        try:
            self.loop.call_soon(self._drain)
        except RuntimeError:  # loop chiuso: il prossimo put riprova
            with self._lock:
                self._scheduled = False
