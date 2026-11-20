"""BLEInterface della libreria meshtastic, reso sicuro per un processo di lunga durata.

Problemi della versione 2.7.11 che qui si evitano:
- bleak chiama il callback "disconnected" nel thread del loop del BLEClient e la libreria lo
  collega a close(): close() scrive sul GATT aspettando quello stesso loop (deadlock);
- se la costruzione fallisce (timeout, errori di scrittura/connessione) il thread di
  ricezione e il collegamento restano vivi;
- tutte le attese sul loop BLE sono senza limite.
"""
import atexit
import logging
import threading

from meshtastic.ble_interface import BLEClient, BLEInterface
from meshtastic.mesh_interface import MeshInterface

log = logging.getLogger(__name__)

OP_TIMEOUT = 30.0      # operazioni GATT in esercizio
CLOSE_TIMEOUT = 5.0    # operazioni durante la chiusura


class SafeBLEClient(BLEClient):
    """BLEClient con attese limitate (default: nessun limite durante la connessione)."""

    default_timeout: float | None = None

    def async_await(self, coro, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        future = self.async_run(coro)
        try:
            return future.result(timeout)
        except BaseException:
            future.cancel()
            raise

    def close(self):
        try:
            self.async_run(self._stop_event_loop())
        except BaseException:
            pass
        self._eventThread.join(timeout=CLOSE_TIMEOUT)


class SafeBLEInterface(BLEInterface):
    def __init__(self, *args, **kwargs):
        self._init_safe_state()
        try:
            super().__init__(*args, **kwargs)
        except BaseException:
            # pulizia best-effort fuori dal thread chiamante, poi si rilancia l'errore
            threading.Thread(target=self._safe_close, name="BLEAbortClose",
                             daemon=True).start()
            raise

    def _init_safe_state(self) -> None:
        self._close_lock = threading.Lock()
        self._close_started = False

    def _safe_close(self) -> None:
        try:
            self.close()
        except BaseException:
            pass

    # ---- connessione ---------------------------------------------------
    def connect(self, address=None):
        device = self.find_device(address)
        client = SafeBLEClient(device.address, disconnected_callback=self._on_ble_disconnected)
        try:
            client.connect()
            client.discover()
        except BaseException:
            try:
                client.close()
            except BaseException:
                pass
            raise
        client.default_timeout = OP_TIMEOUT
        return client

    def _on_ble_disconnected(self, _client) -> None:
        """Callback di bleak (thread del loop BLE): solo pubblicare la perdita, mai close()."""
        if self._close_started:
            return
        threading.Thread(target=self._publish_lost, name="BLELost", daemon=True).start()

    def _publish_lost(self) -> None:
        try:
            self._disconnected()
        except BaseException:
            log.debug("pubblicazione connection.lost fallita", exc_info=True)

    # ---- chiusura ------------------------------------------------------
    def close(self) -> None:
        with self._close_lock:
            if self._close_started:
                return
            self._close_started = True
        client = getattr(self, "client", None)
        if client is not None:
            client.default_timeout = CLOSE_TIMEOUT
        try:
            MeshInterface.close(self)
        except BaseException as exc:
            log.debug("chiusura MeshInterface: %r", exc)

        if getattr(self, "_want_receive", False):
            self._want_receive = False
            thread = getattr(self, "_receiveThread", None)
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=2)
            self._receiveThread = None

        if client is not None:
            handler = getattr(self, "_exit_handler", None)
            if handler is not None:
                atexit.unregister(handler)
            for step in (client.disconnect, client.close):
                try:
                    step()
                except BaseException as exc:
                    log.debug("chiusura client BLE: %r", exc)
            self.client = None
        self._publish_lost()
