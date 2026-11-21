"""Ciclo di vita di una radio: connessione, riconnessione, invio testo, ACK."""
import asyncio
import base64
import contextlib
import io
import logging
import threading
import time
from typing import Any, Callable

from .config_model import CONFIG_SECTIONS, node_to_dict
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
MSG_BLE_PAIR = ("Radio Bluetooth non abbinata: abbinala da Impostazioni Windows → Bluetooth "
                "(PIN sullo schermo della radio)")
MSG_BLE_CONNECT = "Connessione Bluetooth non riuscita: avvicina la radio e riprova"
CLOSE_TIMEOUT = 12.0
SEND_TIMEOUT = 30.0

# operazioni admin: 60 s per richiesta (mai i 300 s di default della libreria)
ADMIN_TIMEOUT = 60
SESSION_MAX_AGE = 240.0  # la chiave di sessione dura 300 s: oltre 240 se ne chiede una nuova
SETTLE = 0.05  # attesa per dare tempo al pacchetto ROUTING di arrivare dal hub
MSG_ADMIN_UNAUTH = ("Il nodo non ha la chiave admin di questa radio: aggiungila seguendo la "
                    "guida")
MSG_ADMIN_TIMEOUT = "Nessuna risposta dal nodo entro 60 s"
UNAUTH_REASONS = {"ADMIN_PUBLIC_KEY_UNAUTHORIZED", "NOT_AUTHORIZED", "37", "33"}
TIMEOUT_REASONS = {"MAX_RETRANSMIT", "TIMEOUT", "NO_RESPONSE"}
# moduli leggibili/scrivibili con Node.writeConfig della libreria
MODULE_SECTIONS = ("mqtt", "serial", "external_notification", "store_forward", "range_test",
                   "telemetry", "canned_message", "audio", "remote_hardware", "neighbor_info",
                   "detection_sensor", "ambient_lighting", "paxcounter", "traffic_management")


class AdminError(Exception):
    """Errore di un'operazione admin: code = "unauthorized" | "timeout" | "error"."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def describe_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if (isinstance(exc, PermissionError) or "Access is denied" in text
            or "PermissionError(13" in text):
        return MSG_PORT_BUSY
    if isinstance(exc, FileNotFoundError) or "could not open port" in text:
        return MSG_PORT_MISSING
    if type(exc).__name__ == "BLEError":
        code = getattr(exc, "kind", None)  # la libreria tiene il codice in .kind
        if code == "multiple_devices":
            return MSG_BLE_MULTIPLE
        if code == "device_not_found" or "No Meshtastic BLE peripheral" in text:
            return MSG_BLE_MISSING
        if code == "write_error":
            return MSG_BLE_PAIR
    if type(exc).__name__ in ("BleakError", "TimeoutError") or isinstance(exc, TimeoutError):
        return MSG_BLE_CONNECT
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
                 sleep=asyncio.sleep,
                 on_traceroute: Callable[[str, int, MeshEvent], None] | None = None):
        self._cfg = cfg
        self._hub = hub
        self._on_event = on_event
        self._on_state = on_state
        self._on_ack = on_ack
        self._on_traceroute = on_traceroute
        self._factory = iface_factory
        self._clock = clock
        self._sleep = sleep
        self._iface = None
        self._task: asyncio.Task | None = None
        self._lost = asyncio.Event()
        self._wake = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._pending: dict[int, float] = {}
        self._traces: dict[int, float] = {}  # traceroute inviati: id pacchetto -> istante
        self._early: dict[int, tuple[float, int | None, bool, str | None]] = {}
        self._state = "disconnected"
        self._error: str | None = None
        self._my_node_id: str | None = None
        self._my_node_num: int | None = None
        self._my_node_name: str | None = None
        self._channels: list[dict] = []
        # operazioni admin
        self._connected_count = 0  # quante volte lo stato e' diventato "connected"
        self._reboot_mark: int | None = None
        self._admin_target: int | None = None  # nodo remoto di cui ascoltiamo gli errori
        self._admin_abort = asyncio.Event()
        self._admin_reason: str | None = None
        self._remote_nodes: dict[int, tuple[Any, float]] = {}

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
        if state == "connected":
            self._connected_count += 1
        self._emit(self._on_state, self.state())

    def _emit(self, fn, *args) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("callback del connettore %s fallita", self._cfg.get("id"))

    # ---- ciclo di vita ----------------------------------------------
    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            if self._state in ("error", "reconnecting"):
                self._wake.set()  # "Connetti": riprova subito, senza attendere il backoff
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
        self._traces.clear()
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
            await self._backoff(BACKOFF[min(attempt, len(BACKOFF) - 1)])
            attempt += 1

    async def _backoff(self, delay: float) -> None:
        self._wake.clear()
        sleeper = asyncio.ensure_future(self._sleep(delay))
        waker = asyncio.ensure_future(self._wake.wait())
        try:
            await asyncio.wait({sleeper, waker}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in (sleeper, waker):
                t.cancel()

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
        connected_flag = getattr(iface, "isConnected", None)
        if connected_flag is not None and hasattr(connected_flag, "is_set")                 and not connected_flag.is_set():
            self._lost.set()  # persa tra la creazione e la registrazione
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
            nodes = None
            for _ in range(3):  # il thread della libreria puo' modificare il dict
                try:
                    nodes = dict(self._iface.nodes or {})
                    break
                except RuntimeError:
                    continue
            if nodes is None:
                return
            events = nodedb_to_events(nodes, self.radio_id, self._clock())
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
        # thread daemon: un close() bloccato non deve impedire l'uscita del processo
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()

        def finish(exc):
            if not fut.done():
                fut.set_result(exc)

        def run():
            err = None
            try:
                iface.close()
            except BaseException as exc:
                err = exc
            try:
                loop.call_soon_threadsafe(finish, err)
            except RuntimeError:
                pass  # loop gia' chiuso
        threading.Thread(target=run, name="RadioClose", daemon=True).start()
        try:
            err = await asyncio.wait_for(fut, CLOSE_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("close() radio %s: timeout, procedo comunque", self.radio_id)
            return
        if err is not None:
            log.warning("close() radio %s: %r", self.radio_id, err)

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
            if (ev.kind == "traceroute" and ev.payload is not None
                    and ev.payload.request_id and self._on_traceroute is not None):
                self._traces.pop(ev.payload.request_id, None)
                self._emit(self._on_traceroute, self.radio_id, ev.payload.request_id, ev)
            self._emit(self._on_event, ev)  # l'ingest registra comunque i collegamenti

    # ---- invio e conferme -------------------------------------------
    async def send_text(self, text: str, channel_index: int, dest: str | None) -> int:
        iface = self._iface
        if iface is None or self._state != "connected":
            raise RuntimeError("Radio non connessa")
        async with self._send_lock:  # un invio alla volta per radio
            try:
                packet = await asyncio.wait_for(self._call(
                    lambda: iface.sendText(
                        text, destinationId=dest or BROADCAST, wantAck=True,
                        channelIndex=channel_index)), SEND_TIMEOUT)
            except asyncio.TimeoutError:
                raise RuntimeError("Invio scaduto") from None
            except _LibraryError as err:
                raise RuntimeError(f"Invio fallito: {type(err.original).__name__}") from err
        packet_id = packet.id
        if dest is not None:  # per i broadcast nessun ack atteso
            self._pending[packet_id] = self._clock()
            early = self._early.pop(packet_id, None)
            if early is not None:  # ack arrivato mentre sendText era ancora in thread
                self._resolve(packet_id, early[1], early[2], early[3])
        return packet_id

    async def send_traceroute(self, dest_num: int, channel_index: int = 0) -> int:
        from meshtastic.protobuf import mesh_pb2, portnums_pb2
        iface = self._iface
        if iface is None or self._state != "connected":
            raise RuntimeError("Radio non connessa")
        async with self._send_lock:  # un invio alla volta per radio
            try:
                packet = await asyncio.wait_for(self._call(
                    lambda: iface.sendData(
                        mesh_pb2.RouteDiscovery(), destinationId=dest_num,
                        portNum=portnums_pb2.TRACEROUTE_APP, wantResponse=True,
                        channelIndex=channel_index)), SEND_TIMEOUT)
            except asyncio.TimeoutError:
                raise RuntimeError("Invio scaduto") from None
            except _LibraryError as err:
                raise RuntimeError(f"Invio fallito: {type(err.original).__name__}") from err
        packet_id = packet.id
        self._traces[packet_id] = self._clock()
        early = self._early.pop(packet_id, None)
        if early is not None:  # errore arrivato mentre sendData era ancora in thread
            self._handle_trace_routing(packet_id, early[2], early[3])
        return packet_id

    def _handle_trace_routing(self, rid: int, ok: bool, reason) -> None:
        # solo gli errori contano: l'ack del nodo locale non e' la risposta
        if not ok:
            self._traces.pop(rid, None)
            self._emit(self._on_ack, self.radio_id, rid, False, reason)

    def _handle_routing(self, packet: dict, decoded: dict) -> None:
        rid = decoded.get("requestId")
        if rid is None:
            return
        reason = (decoded.get("routing") or {}).get("errorReason")
        ok = reason in (None, "NONE")
        if (not ok and self._admin_target is not None
                and packet.get("from") in (self._admin_target, self._my_node_num)):
            self._admin_fail(str(reason))  # errore per un'operazione admin in corso
        if rid in self._traces:
            self._handle_trace_routing(rid, ok, reason)
            return
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
        for rid in [r for r, t in self._traces.items() if now - t >= ACK_TIMEOUT]:
            del self._traces[rid]
        for pid in [p for p, t in self._pending.items() if now - t >= ACK_TIMEOUT]:
            del self._pending[pid]
            self._emit(self._on_ack, self.radio_id, pid, False, "TIMEOUT")

    # ---- operazioni admin --------------------------------------------
    def _admin_fail(self, reason: str) -> None:
        if self._admin_reason is None:
            self._admin_reason = reason
            self._admin_abort.set()

    @staticmethod
    def _error_for_reason(reason: str) -> AdminError:
        if reason in UNAUTH_REASONS:
            return AdminError("unauthorized", MSG_ADMIN_UNAUTH)
        if reason in TIMEOUT_REASONS:
            return AdminError("timeout", MSG_ADMIN_TIMEOUT)
        return AdminError("error", f"Il nodo ha rifiutato la richiesta ({reason})")

    @staticmethod
    def _error_for_exception(exc: BaseException) -> AdminError:
        if "imed out" in str(exc):
            return AdminError("timeout", MSG_ADMIN_TIMEOUT)
        return AdminError("error", f"Operazione fallita: {type(exc).__name__}")

    @contextlib.asynccontextmanager
    async def _admin_op(self, node_num: int | None):
        """Sezione esclusiva: lock di invio, timeout a 60 s, ascolto errori del nodo remoto."""
        async with self._send_lock:
            iface = self._iface
            if iface is None or self._state != "connected":
                raise AdminError("error", "Radio non connessa")
            old = iface._timeout.expireTimeout
            iface._timeout.expireTimeout = ADMIN_TIMEOUT
            self._admin_reason = None
            self._admin_abort.clear()
            self._admin_target = node_num
            try:
                yield iface
            finally:
                self._admin_target = None
                iface._timeout.expireTimeout = old

    async def _admin_call(self, fn, *, watch: bool, timeout: float = ADMIN_TIMEOUT + 15):
        """Esegue fn in thread. Con watch esce subito se arriva un errore ROUTING dal nodo."""
        def quiet():  # la libreria stampa anche le config (segreti compresi)
            with contextlib.redirect_stdout(io.StringIO()):
                return fn()
        task = asyncio.ensure_future(self._call(quiet))
        task.add_done_callback(lambda t: t.cancelled() or t.exception())
        waiters = {task}
        abort = None
        if watch:
            abort = asyncio.ensure_future(self._admin_abort.wait())
            waiters.add(abort)
        try:
            done, _ = await asyncio.wait(waiters, timeout=timeout,
                                         return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            if abort is not None:
                abort.cancel()
        if watch and task in done:
            await asyncio.sleep(SETTLE)  # il ROUTING puo' arrivare poco dopo l'uscita del thread
        if watch and self._admin_reason is not None:
            raise self._error_for_reason(self._admin_reason)
        if task not in done:
            raise AdminError("timeout", MSG_ADMIN_TIMEOUT)
        try:
            return task.result()
        except _LibraryError as err:
            raise self._error_for_exception(err.original) from err

    def _owner_of(self, node_num: int | None) -> dict:
        nid = self._my_node_id if node_num is None else node_id(node_num)
        user = ((self._iface.nodes or {}).get(nid) or {}).get("user") or {}
        return {"long_name": user.get("longName", ""), "short_name": user.get("shortName", ""),
                "is_licensed": bool(user.get("isLicensed", False))}

    async def admin_public_key(self) -> str | None:
        """Chiave pubblica della radio locale in base64 (per il campo "Admin key" dei nodi)."""
        async with self._admin_op(None) as iface:
            def work():
                key = iface.localNode.localConfig.security.public_key
                return base64.b64encode(key).decode() if key else None
            return await self._admin_call(work, watch=False)

    async def read_local(self) -> dict:
        async with self._admin_op(None) as iface:
            def work():
                n = iface.localNode
                return node_to_dict(n.localConfig, n.moduleConfig, n.channels or [],
                                    self._owner_of(None))
            return await self._admin_call(work, watch=False)

    @staticmethod
    def _step(on_step, text: str, done: int, total: int) -> None:
        if on_step is not None:
            try:
                on_step(text, done, total)
            except Exception:
                log.exception("on_step fallita")

    async def read_remote(self, node_num: int, sections: list[str] | None, on_step) -> dict:
        nid = node_id(node_num)
        names = list(sections) if sections else list(CONFIG_SECTIONS) + list(MODULE_SECTIONS)
        total = 1 + len(names)  # canali + una richiesta per sezione
        async with self._admin_op(node_num) as iface:
            self._step(on_step, "Contatto il nodo", 0, total)
            node = await self._admin_call(
                lambda: iface.getNode(nid, requestChannels=True, timeout=ADMIN_TIMEOUT),
                watch=True, timeout=3 * ADMIN_TIMEOUT + 15)
            self._step(on_step, "Canali letti", 1, total)
            for i, name in enumerate(names):
                field = (node.localConfig.DESCRIPTOR.fields_by_name.get(name)
                         or node.moduleConfig.DESCRIPTOR.fields_by_name.get(name))
                if field is None:
                    raise AdminError("error", f"Sezione sconosciuta: {name}")
                await self._admin_call(lambda f=field: node.requestConfig(f), watch=True)
                self._step(on_step, f"Letta la sezione {name}", i + 2, total)
            self._remote_nodes[node_num] = (node, self._clock())
            return node_to_dict(node.localConfig, node.moduleConfig, node.channels or [],
                                self._owner_of(node_num))

    @staticmethod
    def _ser(msg) -> bytes:
        return msg.SerializeToString(deterministic=True)

    def _plan_write(self, node, protos: dict, owner_now: dict):
        """Sezioni cambiate rispetto al Node; copia i protobuf modificati nel Node."""
        cfg = [n for n in CONFIG_SECTIONS
               if self._ser(getattr(protos["config"], n)) != self._ser(getattr(node.localConfig, n))]
        mods = [n for n in MODULE_SECTIONS
                if n in protos["module_config"].DESCRIPTOR.fields_by_name
                and self._ser(getattr(protos["module_config"], n))
                != self._ser(getattr(node.moduleConfig, n))]
        chans = []
        for c in protos.get("channels", []):
            cur = next((x for x in (node.channels or []) if x.index == c.index), None)
            if cur is None or self._ser(c) != self._ser(cur):
                chans.append(c.index)
        owner = protos.get("owner") or {}
        owner_changed = bool(owner) and any(
            owner.get(k, owner_now[k]) != owner_now[k] for k in owner_now)
        for n in cfg:
            getattr(node.localConfig, n).CopyFrom(getattr(protos["config"], n))
        for n in mods:
            getattr(node.moduleConfig, n).CopyFrom(getattr(protos["module_config"], n))
        for i in chans:
            c = next(x for x in protos["channels"] if x.index == i)
            if node.channels is None:
                node.channels = []
            cur = next((x for x in node.channels if x.index == i), None)
            if cur is None:
                node.channels.append(c)
            else:
                cur.CopyFrom(c)
        return cfg, mods, chans, owner_changed

    def _node_for(self, node_num: int | None, *, need_read: bool):
        """Node della libreria: locale, oppure il remoto restituito da getNode in lettura."""
        iface = self._iface
        if node_num is None:
            return iface.localNode
        cached = self._remote_nodes.get(node_num)
        if cached is not None:
            return cached[0]
        if need_read:
            raise AdminError("error", "Leggi prima la configurazione del nodo")
        return iface.getNode(node_id(node_num), requestChannels=False)

    def _renew_session_if_old(self, node_num: int) -> None:
        cached = self._remote_nodes.get(node_num)
        if cached is not None and self._clock() - cached[1] > SESSION_MAX_AGE:
            entry = (getattr(self._iface, "nodesByNum", None) or {}).get(node_num)
            if entry is not None:
                entry.pop("adminSessionPassKey", None)

    async def write(self, node_num: int | None, protos_changed: dict, on_step) -> None:
        """Scrive le sezioni cambiate in un'unica transazione (la radio si riavvia una volta)."""
        remote = node_num is not None
        async with self._admin_op(node_num) as iface:
            node = self._node_for(node_num, need_read=True)
            cfg, mods, chans, owner = self._plan_write(
                node, protos_changed, self._owner_of(node_num))
            todo = ([("writeConfig", n) for n in cfg + mods]
                    + [("writeChannel", i) for i in chans])
            if owner:
                todo.append(("setOwner", None))
            if not todo:
                return
            total = len(todo) + 2
            done = 0

            async def step(text, fn):
                nonlocal done
                await self._admin_call(fn, watch=remote)
                done += 1
                self._step(on_step, text, done, total)

            if remote:
                self._renew_session_if_old(node_num)
                await self._admin_call(node.ensureSessionKey, watch=True)
            await step("Apro la transazione", node.beginSettingsTransaction)
            for kind, arg in todo:
                if kind == "writeConfig":
                    await step(f"Scrivo {arg}", lambda a=arg: node.writeConfig(a))
                elif kind == "writeChannel":
                    await step(f"Scrivo il canale {arg}", lambda a=arg: node.writeChannel(a))
                else:
                    o = protos_changed["owner"]
                    await step("Scrivo il nome", lambda: node.setOwner(
                        o.get("long_name"), o.get("short_name"), bool(o.get("is_licensed"))))
            if remote:
                await self._admin_call(lambda: iface._acknowledgment.reset(), watch=False)
            await step("Confermo le modifiche", node.commitSettingsTransaction)
            if remote:
                await self._admin_call(iface.waitForAckNak, watch=True)
                # la chiave di sessione del nodo si azzera al riavvio
                self._remote_nodes.pop(node_num, None)
            else:
                self._reboot_mark = self._connected_count

    async def _simple_admin(self, node_num: int | None, call, reboots: bool = False) -> None:
        remote = node_num is not None
        async with self._admin_op(node_num) as iface:
            node = self._node_for(node_num, need_read=False)
            if remote:
                await self._admin_call(lambda: iface._acknowledgment.reset(), watch=False)
            await self._admin_call(lambda: call(node), watch=remote)
            if remote:
                await self._admin_call(iface.waitForAckNak, watch=True)
            elif reboots:
                self._reboot_mark = self._connected_count

    async def reboot(self, node_num: int | None, secs: int = 5) -> None:
        await self._simple_admin(node_num, lambda n: n.reboot(secs), reboots=True)

    async def set_fixed_position(self, node_num: int | None, lat: float, lon: float,
                                 alt: int = 0) -> None:
        # float in gradi: un int sarebbe interpretato come gia' in unita' di 1e-7
        await self._simple_admin(
            node_num, lambda n: n.setFixedPosition(float(lat), float(lon), int(alt)))

    async def remove_fixed_position(self, node_num: int | None) -> None:
        await self._simple_admin(node_num, lambda n: n.removeFixedPosition())

    async def wait_reconnected(self, timeout: float = 90) -> bool:
        """Attende che la radio torni "connected" dopo un riavvio (anche con interfaccia nuova)."""
        mark = self._reboot_mark if self._reboot_mark is not None else self._connected_count
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            if self._connected_count > mark and self._state == "connected":
                self._reboot_mark = None
                return True
            await self._sleep(0.5)
        self._reboot_mark = None
        return False
