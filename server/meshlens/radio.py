"""Ciclo di vita di una radio: connessione, riconnessione, invio testo, ACK."""
import asyncio
import logging
import threading
import time
from typing import Any, Callable

from .events import MeshEvent, node_id
from .rf_convert import nodedb_to_events, packet_to_event

log = logging.getLogger(__name__)

BACKOFF = (2, 5, 10, 30, 60)
ACK_TIMEOUT = 60.0
ACK_CHECK_INTERVAL = 5.0
BROADCAST = "^all"

MSG_PORT_BUSY = "Porta in uso da un altro programma (chiudi l'app o la CLI Meshtastic)"
MSG_PORT_MISSING = "Porta non trovata: radio scollegata?"
MSG_BLE_MISSING = "Radio Bluetooth non trovata: è accesa e vicina?"
MSG_BLE_MULTIPLE = "Più radio Bluetooth corrispondono: usa l'indirizzo esatto"
CLOSE_TIMEOUT = 12.0


def describe_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if (isinstance(exc, PermissionError) or "Access is denied" in text
            or "PermissionError(13" in text):
        return MSG_PORT_BUSY
    if isinstance(exc, FileNotFoundError) or "could not open port" in text:
        return MSG_PORT_MISSING
    if type(exc).__name__ == "BLEError":
        code = exc.args[1] if len(exc.args) > 1 else None
        if code == "multiple_devices":
            return MSG_BLE_MULTIPLE
        if code == "device_not_found" or "No Meshtastic BLE peripheral" in text:
            return MSG_BLE_MISSING
    return f"Errore di connessione: {type(exc).__name__}"


def _enum_name(obj, field: str, value) -> str:
    if isinstance(value, str):
        return value
    try:
        return obj.DESCRIPTOR.fields_by_name[field].enum_type.values_by_number[value].name
    except Exception:
        return str(value)


def _camel(name: str) -> str:
    return "".join(p.capitalize() for p in name.split("_"))


def read_channels(iface) -> list[dict]:
    """Canali attivi (ruolo != DISABLED) dalla radio locale."""
    node = iface.localNode
    preset = None
    try:
        lora = node.localConfig.lora
        preset = _camel(_enum_name(lora, "modem_preset", lora.modem_preset))
    except Exception:
        pass
    out = []
    for ch in node.channels or []:
        role = _enum_name(ch, "role", ch.role)
        if role == "DISABLED":
            continue
        name = ch.settings.name
        if not name and role == "PRIMARY":
            name = preset or "Primario"
        out.append({"index": ch.index, "name": name, "role": role})
    return out


class _LibraryError(Exception):
    def __init__(self, original: BaseException):
        super().__init__(repr(original))
        self.original = original


def _close_late(fut: asyncio.Future) -> None:
    """Interfaccia creata dopo uno stop(): chiuderla in un thread, senza bloccare il loop."""
    if fut.cancelled() or fut.exception() is not None:
        return
    iface = fut.result()

    def close():
        try:
            iface.close()
        except BaseException:
            pass
    threading.Thread(target=close, daemon=True).start()


class RadioConnector:
    def __init__(self, cfg: dict, hub, on_event: Callable[[MeshEvent], None],
                 on_state: Callable[[dict], None],
                 on_ack: Callable[[str, int, bool, str | None], None],
                 iface_factory: Callable[[dict], Any], clock=time.time, *,
                 sleep=asyncio.sleep):
        self._cfg = cfg
        self._hub = hub
        self._on_event = on_event
        self._on_state = on_state
        self._on_ack = on_ack
        self._factory = iface_factory
        self._clock = clock
        self._sleep = sleep
        self._iface = None
        self._task: asyncio.Task | None = None
        self._lost = asyncio.Event()
        self._pending: dict[int, float] = {}
        self._early: dict[int, tuple[float, int | None, bool, str | None]] = {}
        self._state = "disconnected"
        self._error: str | None = None
        self._my_node_id: str | None = None
        self._my_node_num: int | None = None
        self._my_node_name: str | None = None
        self._channels: list[dict] = []

    # ---- stato -------------------------------------------------------
    @property
    def radio_id(self) -> str:
        return self._cfg["id"]

    def state(self) -> dict:
        return {
            "id": self._cfg["id"], "kind": self._cfg["kind"],
            "address": self._cfg["address"], "state": self._state,
            "error": self._error, "my_node_id": self._my_node_id,
            "my_node_name": self._my_node_name, "channels": list(self._channels),
        }

    def _set_state(self, state: str, error: str | None = None) -> None:
        self._state, self._error = state, error
        self._emit(self._on_state, self.state())

    def _emit(self, fn, *args) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("callback del connettore %s fallita", self._cfg.get("id"))

    # ---- ciclo di vita ----------------------------------------------
    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._set_state("connecting")
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self._close_iface()
        self._pending.clear()
        self._set_state("disconnected")

    async def _call(self, fn, *args):
        """Chiamata bloccante della libreria in thread; la libreria puo' fare sys.exit."""
        try:
            return await asyncio.to_thread(fn, *args)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            raise _LibraryError(exc) from exc

    async def _run(self) -> None:
        attempt = 0
        while True:
            if self._state != "connecting":
                self._set_state("connecting", self._error)
            if await self._connect():
                attempt = 0
                await self._until_lost()
                await self._close_iface()
                self._set_state("reconnecting")
            else:
                self._set_state("reconnecting", self._error)
            await self._sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
            attempt += 1

    async def _connect(self) -> bool:
        self._lost.clear()
        fut = asyncio.ensure_future(self._call(self._factory, self._cfg))
        try:
            iface = await asyncio.shield(fut)
        except asyncio.CancelledError:
            fut.add_done_callback(_close_late)
            raise
        except _LibraryError as err:
            log.warning("connessione radio %s fallita: %r", self.radio_id, err.original)
            self._set_state("error", describe_error(err.original))
            return False
        self._iface = iface
        self._hub.register(iface, self)
        try:
            self._read_info(iface)
        except Exception as exc:
            log.warning("lettura info radio %s fallita: %r", self.radio_id, exc)
            await self._close_iface()
            self._set_state("error", f"Errore di connessione: {type(exc).__name__}")
            return False
        self._set_state("connected")
        self._emit_nodedb()
        return True

    def _read_info(self, iface) -> None:
        num = iface.myInfo.my_node_num
        self._my_node_num, self._my_node_id = num, node_id(num)
        user = (iface.nodes or {}).get(self._my_node_id, {}).get("user") or {}
        self._my_node_name = user.get("longName") or None
        self._channels = read_channels(iface)

    def _emit_nodedb(self) -> None:
        try:
            events = nodedb_to_events(self._iface.nodes or {}, self.radio_id, self._clock())
        except Exception:
            log.exception("nodedb radio %s non convertibile", self.radio_id)
            return
        for ev in events:
            self._emit(self._on_event, ev)

    async def _until_lost(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._lost.wait(), ACK_CHECK_INTERVAL)
                return
            except asyncio.TimeoutError:
                self.check_acks()

    async def _close_iface(self) -> None:
        iface, self._iface = self._iface, None
        if iface is None:
            return
        self._hub.unregister(iface)
        try:
            await asyncio.wait_for(asyncio.shield(self._call(iface.close)), CLOSE_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("close() radio %s: timeout, procedo comunque", self.radio_id)
        except _LibraryError as err:
            log.warning("close() radio %s: %r", self.radio_id, err.original)

    # ---- eventi dal hub (nel thread del loop) -------------------------
    def on_lost(self) -> None:
        self._lost.set()

    def on_established(self) -> None:
        # riavvio firmware: la libreria ripubblica established senza ricreare
        if self._state == "connected" and self._iface is not None:
            try:
                self._read_info(self._iface)
            except Exception:
                return
            self._set_state("connected")

    def on_packet(self, packet: dict) -> None:
        decoded = packet.get("decoded") or {}
        if decoded.get("portnum") == "ROUTING_APP":
            self._handle_routing(packet, decoded)
            return
        ev = packet_to_event(packet, self.radio_id, self._clock())
        if ev is not None:
            self._emit(self._on_event, ev)

    # ---- invio e conferme -------------------------------------------
    async def send_text(self, text: str, channel_index: int, dest: str | None) -> int:
        iface = self._iface
        if iface is None or self._state != "connected":
            raise RuntimeError("Radio non connessa")
        try:
            packet = await self._call(
                lambda: iface.sendText(
                    text, destinationId=dest or BROADCAST, wantAck=True,
                    channelIndex=channel_index))
        except _LibraryError as err:
            raise RuntimeError(f"Invio fallito: {type(err.original).__name__}") from err
        packet_id = packet.id
        if dest is not None:  # per i broadcast nessun ack atteso
            self._pending[packet_id] = self._clock()
            early = self._early.pop(packet_id, None)
            if early is not None:  # ack arrivato mentre sendText era ancora in thread
                self._resolve(packet_id, early[1], early[2], early[3])
        return packet_id

    def _handle_routing(self, packet: dict, decoded: dict) -> None:
        rid = decoded.get("requestId")
        if rid is None:
            return
        reason = (decoded.get("routing") or {}).get("errorReason")
        ok = reason in (None, "NONE")
        if rid not in self._pending:
            self._early[rid] = (self._clock(), packet.get("from"), ok, reason)
            return
        self._resolve(rid, packet.get("from"), ok, reason)

    def _resolve(self, rid: int, sender, ok: bool, reason) -> None:
        if ok and sender == self._my_node_num:
            return  # ack dal nodo locale: la radio l'ha solo accodato (resta "sent")
        self._pending.pop(rid, None)
        self._emit(self._on_ack, self.radio_id, rid, ok, None if ok else reason)

    def check_acks(self) -> None:
        now = self._clock()
        for rid in [r for r, e in self._early.items() if now - e[0] >= ACK_TIMEOUT]:
            del self._early[rid]
        for pid in [p for p, t in self._pending.items() if now - t >= ACK_TIMEOUT]:
            del self._pending[pid]
            self._emit(self._on_ack, self.radio_id, pid, False, "TIMEOUT")
