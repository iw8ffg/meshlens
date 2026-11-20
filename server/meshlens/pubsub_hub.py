"""Hub unico verso il pubsub globale della libreria meshtastic.

La libreria pubblica da un solo thread per tutte le radio: i listener qui non
fanno lavoro, inoltrano al loop asyncio e smistano per identita' dell'interfaccia.
"""
import logging

log = logging.getLogger(__name__)

TOPIC_RECEIVE = "meshtastic.receive"
TOPIC_LOST = "meshtastic.connection.lost"
TOPIC_ESTABLISHED = "meshtastic.connection.established"


class PubSubHub:
    def __init__(self, loop, pubsub_module=None):
        self._loop = loop
        self._pubsub = pubsub_module
        self._connectors: dict[int, tuple[object, object]] = {}
        self._started = False

    def register(self, iface, connector) -> None:
        # riferimento forte all'interfaccia: id() resta valido finche' registrata
        self._connectors[id(iface)] = (iface, connector)

    def unregister(self, iface) -> None:
        self._connectors.pop(id(iface), None)

    def start(self, loop=None) -> None:
        if loop is not None:
            self._loop = loop  # hub creato prima che il loop esistesse
        if self._started:
            return
        if self._pubsub is None:
            from pubsub import pub
            self._pubsub = pub
        # riferimenti forti: pubsub tiene solo riferimenti deboli
        self._listeners = (self._on_receive, self._on_lost, self._on_established)
        self._pubsub.subscribe(self._on_receive, TOPIC_RECEIVE)
        self._pubsub.subscribe(self._on_lost, TOPIC_LOST)
        self._pubsub.subscribe(self._on_established, TOPIC_ESTABLISHED)
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        for listener, topic in zip(self._listeners,
                                   (TOPIC_RECEIVE, TOPIC_LOST, TOPIC_ESTABLISHED)):
            try:
                self._pubsub.unsubscribe(listener, topic)
            except Exception:
                log.debug("unsubscribe %s fallita", topic)
        self._started = False

    def _dispatch(self, interface, method: str, *args) -> None:
        entry = self._connectors.get(id(interface))
        if entry is None or entry[0] is not interface:
            return
        try:
            self._loop.call_soon_threadsafe(getattr(entry[1], method), *args)
        except RuntimeError:  # loop chiuso (spegnimento)
            log.debug("loop chiuso, evento %s scartato", method)

    def _on_receive(self, packet, interface):
        self._dispatch(interface, "on_packet", packet)

    def _on_lost(self, interface):
        self._dispatch(interface, "on_lost")

    def _on_established(self, interface):
        self._dispatch(interface, "on_established")
