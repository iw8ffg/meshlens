"""Gestione delle radio collegate: persistenza, connettori, invio e stato."""
import asyncio
import contextlib
import logging
import math
import secrets
import time
from typing import Any

from .events import MeshEvent, WaypointData, node_id
from .conversations import waypoint_json
from .ingest import traceroute_chains
from .mqtt_publish import reply_problem
from .radio import RadioConnector

log = logging.getLogger(__name__)

KINDS = ("usb", "ble")
MAX_TEXT_BYTES = 200
BLE_SCAN_TIMEOUT = 12.0
LIKELY_VIDS = {"239A", "303A", "10C4", "1A86", "2886"}
BROADCAST_ID = "!ffffffff"
MAX_EARLY_ACKS = 100
TRACEROUTE_INTERVAL = 30.0  # il firmware scarta i traceroute piu' frequenti
TRACEROUTE_TIMEOUT = 60.0
MSG_TRACE_TIMEOUT = "Nessuna risposta entro 60 s"
# testi dei codici di mesh_pb2.Routing.Error (gli stessi in web/src/lib/strings/messaggi.ts)
ROUTING_ERRORS = {
    "NO_ROUTE": "Nessun percorso verso il nodo",
    "GOT_NAK": "Rifiutato da un nodo lungo il percorso",
    "TIMEOUT": MSG_TRACE_TIMEOUT,  # testo dei traceroute; per i messaggi lo da' l'interfaccia
    "NO_INTERFACE": "Nessuna interfaccia disponibile per l'invio",
    "MAX_RETRANSMIT": "Nessuna conferma dopo i tentativi",
    "NO_CHANNEL": "Canale non disponibile sul destinatario",
    "TOO_LARGE": "Messaggio troppo grande",
    "NO_RESPONSE": "Nessuna risposta dal nodo",
    "DUTY_CYCLE_LIMIT": "Limite di tempo di trasmissione raggiunto: riprova più tardi",
    "BAD_REQUEST": "Richiesta non valida",
    "NOT_AUTHORIZED": "Non autorizzato",
    "PKI_FAILED": "Cifratura a chiave pubblica non riuscita",
    "PKI_UNKNOWN_PUBKEY": "Il destinatario non conosce ancora la tua chiave pubblica: "
                          "attendi che riceva le info del tuo nodo",
    "ADMIN_BAD_SESSION_KEY": "Sessione di amministrazione scaduta",
    "ADMIN_PUBLIC_KEY_UNAUTHORIZED": "Chiave admin non autorizzata sul nodo",
    "RATE_LIMIT_EXCEEDED": "Troppi messaggi: il nodo ha applicato un limite, riprova più tardi",
    "PKI_SEND_FAIL_PUBLIC_KEY": "La tua radio non conosce la chiave pubblica del destinatario",
    "SEND_FAILED": "Invio alla radio non riuscito",
}
SEND_FAILED = "SEND_FAILED"  # errore del messaggio quando la radio rifiuta l'invio


def _routing_text(reason: str | None) -> str:
    return ROUTING_ERRORS.get(reason or "", f"Errore di consegna ({reason})")


class NoRadioConnected(Exception):
    pass


class TracerouteThrottled(Exception):
    def __init__(self, wait_s: int):
        super().__init__(f"Attendi {wait_s} s")
        self.wait_s = wait_s


def default_iface_factory(cfg: dict):
    if cfg["kind"] == "usb":
        from meshtastic.serial_interface import SerialInterface
        return SerialInterface(devPath=cfg["address"])
    from .ble_safe import SafeBLEInterface
    return SafeBLEInterface(cfg["address"])


def default_ble_scan() -> list[dict]:
    from meshtastic.ble_interface import BLEInterface
    return [{"address": d.address, "name": d.name or ""} for d in BLEInterface.scan()]


def default_list_ports():
    from serial.tools import list_ports
    return list_ports.comports()


def _norm_address(address: str) -> str:
    return address.strip().upper()


def _is_node_id(value: str) -> bool:
    if not value.startswith("!") or len(value) != 9:
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


class RadioManager:
    def __init__(self, store, ingestor, bus, loop, hub, connector_factory=RadioConnector,
                 iface_factory=default_iface_factory, list_ports_fn=default_list_ports,
                 ble_scan_fn=default_ble_scan, clock=time.time, on_event=None):
        self.store = store
        self.ingestor = ingestor
        self.on_event = on_event or ingestor.handle
        self.bus = bus
        self.loop = loop
        self.hub = hub
        self._connector_factory = connector_factory
        self._iface_factory = iface_factory
        self._list_ports = list_ports_fn
        self._ble_scan = ble_scan_fn
        self._cfgs: dict[str, dict] = {}
        self._connectors: dict[str, Any] = {}
        self._tasks: set[asyncio.Task] = set()
        self._pending_seq = 0
        # esiti arrivati durante send_text: (radio, id) -> (stato, motivo dell'errore)
        self._early_acks: dict[tuple[str, int], tuple[str, str | None]] = {}
        self._clock = clock
        # traceroute in attesa: (radio, id pacchetto) -> risultato parziale
        self._traces: dict[tuple[str, int], dict] = {}
        self._last_trace: dict[str, float] = {}
        # esiti arrivati prima della registrazione (sendData dorme nel suo thread):
        # (radio, id) -> (istante, evento di risposta | None, motivo dell'errore)
        self._early_traces: dict[tuple[str, int], tuple[float, MeshEvent | None, str | None]] = {}
        self._tracing: set[str] = set()  # radio con un traceroute in invio
        # dopo un riavvio nessuna risposta puo' piu' arrivare ai pending rimasti nel DB
        store.expire_pending_traceroutes(MSG_TRACE_TIMEOUT)
        store.commit()
        for cfg in store.list_radios():
            self._register(cfg)

    # ---- ciclo di vita ------------------------------------------------
    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.hub.start(self.loop)
        for rid, cfg in list(self._cfgs.items()):
            if cfg["auto_connect"]:
                await self._connectors[rid].start()

    async def stop(self) -> None:
        tasks = list(self._tasks)
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        async def stop_one(conn):
            try:
                await conn.stop()
            except Exception:
                log.exception("stop radio fallito")
        await asyncio.gather(*(stop_one(c) for c in list(self._connectors.values())))
        stop_hub = getattr(self.hub, "stop", None)
        if stop_hub is not None:
            stop_hub()

    def _register(self, cfg: dict) -> None:
        cfg = dict(cfg)
        self._cfgs[cfg["id"]] = cfg
        self._connectors[cfg["id"]] = self._connector_factory(
            {"id": cfg["id"], "kind": cfg["kind"], "address": cfg["address"]}, self.hub,
            self.on_event, self._on_state, self._on_ack, self._iface_factory,
            on_traceroute=self._on_traceroute)

    # ---- callback dei connettori (thread del loop) --------------------
    def _on_state(self, state: dict) -> None:
        if state.get("state") == "connected" and state.get("my_node_id"):
            num = int(state["my_node_id"][1:], 16)
            self.ingestor.mark_local_radio(num)
            self.ingestor.set_radio_node(state["id"], num)
        self._publish_radios()

    def _on_ack(self, radio_id: str, packet_id: int, ok: bool, reason: str | None) -> None:
        key = (radio_id, packet_id)
        if key in self._traces:  # errore di un traceroute: non e' una chat
            if not ok:
                self._finish_trace(key, "failed", _routing_text(reason))
            return
        status = "acked" if ok else "failed"
        error = None if ok else (reason or "TIMEOUT")
        msg_key = f"out:{radio_id}:{packet_id}"
        if any(m["key"] == msg_key for m in self.ingestor.live.messages):
            # ack di un messaggio gia' registrato, anche se arriva durante un traceroute
            self.ingestor.set_status(msg_key, status, error)
            return
        if radio_id in self._tracing:
            # id sconosciuto durante l'invio di un traceroute (il lock esclude invii chat
            # contemporanei sulla stessa radio): e' l'esito in anticipo del traceroute
            if not ok:
                self._buffer_early_trace(key, None, reason)
            return
        # ack arrivato durante send_text: il messaggio definitivo non esiste ancora
        self._early_acks[(radio_id, packet_id)] = (status, error)
        while len(self._early_acks) > MAX_EARLY_ACKS:
            del self._early_acks[next(iter(self._early_acks))]

    def _on_traceroute(self, radio_id: str, request_id: int, ev: MeshEvent) -> None:
        key = (radio_id, request_id)
        if key not in self._traces:
            self._buffer_early_trace(key, ev, None)
            return
        self._finish_ok(key, ev)

    def _buffer_early_trace(self, key, ev: MeshEvent | None, reason: str | None) -> None:
        now = self._clock()
        for k in [k for k, e in self._early_traces.items() if now - e[0] >= TRACEROUTE_TIMEOUT]:
            del self._early_traces[k]
        self._early_traces[key] = (now, ev, reason)
        while len(self._early_traces) > MAX_EARLY_ACKS:
            del self._early_traces[next(iter(self._early_traces))]

    def _finish_ok(self, key: tuple[str, int], ev: MeshEvent) -> None:
        forward, back = traceroute_chains(ev)
        self._finish_trace(key, "ok", None,
                           [{"id": node_id(n), "snr": snr} for n, snr in forward],
                           [{"id": node_id(n), "snr": snr} for n, snr in back])

    def _finish_trace(self, key: tuple[str, int], status: str, error: str | None,
                      forward: list | None = None, back: list | None = None) -> None:
        result = self._traces.pop(key)
        result.update(status=status, error=error, forward=forward or [], back=back or [])
        self.store.update_traceroute(result["id"], status, error, result["forward"],
                                     result["back"])
        self.store.commit()
        self.bus.publish({"type": "traceroute", "result": dict(result)})

    def check_traceroutes(self) -> None:
        """Porta a timeout i traceroute senza risposta dopo 60 s."""
        now = self._clock()
        for key in [k for k, r in self._traces.items()
                    if now - r["time"] >= TRACEROUTE_TIMEOUT]:
            self._finish_trace(key, "timeout", MSG_TRACE_TIMEOUT)

    def _publish_radios(self) -> None:
        self.bus.publish({"type": "radios", "radios": self.radios()})

    # ---- elenco -------------------------------------------------------
    def _radio_json(self, rid: str) -> dict:
        cfg, st = self._cfgs[rid], self._connectors[rid].state()
        return {"id": rid, "name": cfg["name"], "kind": cfg["kind"], "address": cfg["address"],
                "auto_connect": cfg["auto_connect"], "state": st["state"], "error": st["error"],
                "my_node_id": st["my_node_id"], "my_node_name": st["my_node_name"],
                "channels": st["channels"]}

    def radios(self) -> list[dict]:
        return [self._radio_json(rid) for rid in self._cfgs]

    def _get(self, radio_id: str) -> dict:
        if radio_id not in self._cfgs:
            raise KeyError(radio_id)
        return self._cfgs[radio_id]

    # ---- gestione -----------------------------------------------------
    async def add(self, kind: str, address: str, name: str | None) -> dict:
        if kind not in KINDS:
            raise ValueError("Tipo di radio non valido")
        address = (address or "").strip()
        if not address:
            raise ValueError("Indirizzo mancante")
        if any(_norm_address(c["address"]) == _norm_address(address)
               for c in self._cfgs.values()):
            raise ValueError("Radio già aggiunta")
        rid = "r" + secrets.token_hex(4)
        while rid in self._cfgs:
            rid = "r" + secrets.token_hex(4)
        cfg = {"id": rid, "name": (name or "").strip() or address, "kind": kind,
               "address": address, "auto_connect": True}
        self.store.save_radio(cfg)
        self.store.commit()
        self._register(cfg)
        await self._connectors[rid].start()
        self._publish_radios()
        return self._radio_json(rid)

    async def remove(self, radio_id: str) -> None:
        self._get(radio_id)
        await self._connectors[radio_id].stop()
        self.store.delete_radio(radio_id)
        self.store.commit()
        self._cfgs.pop(radio_id, None)
        self._connectors.pop(radio_id, None)
        self._publish_radios()

    def _set_auto(self, radio_id: str, value: bool) -> None:
        cfg = self._get(radio_id)
        cfg["auto_connect"] = value
        self.store.save_radio(cfg)
        self.store.commit()

    async def connect(self, radio_id: str) -> None:
        self._set_auto(radio_id, True)
        await self._connectors[radio_id].start()
        self._publish_radios()

    async def disconnect(self, radio_id: str) -> None:
        self._set_auto(radio_id, False)
        await self._connectors[radio_id].stop()
        self._publish_radios()

    # ---- porte e scansione --------------------------------------------
    async def ports(self) -> list[dict]:
        try:
            found = await asyncio.to_thread(lambda: list(self._list_ports()))
        except Exception as exc:
            log.warning("elenco porte fallito: %r", exc)
            raise ValueError("Impossibile leggere le porte seriali")
        in_use = {_norm_address(c["address"]): rid for rid, c in self._cfgs.items()
                  if c["kind"] == "usb"}
        out = []
        for p in found:
            vid = f"{p.vid:04X}" if p.vid is not None else None
            pid = f"{p.pid:04X}" if p.pid is not None else None
            out.append({"device": p.device, "description": p.description, "vid": vid,
                        "pid": pid, "likely_meshtastic": vid in LIKELY_VIDS,
                        "in_use_by": in_use.get(_norm_address(p.device))})
        return out

    async def ble_scan(self) -> list[dict]:
        try:
            return await asyncio.wait_for(asyncio.to_thread(self._ble_scan), BLE_SCAN_TIMEOUT)
        except asyncio.TimeoutError:
            raise ValueError("Scansione Bluetooth scaduta")
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # la libreria puo' chiamare sys.exit
            log.warning("scansione BLE fallita: %r", exc)
            raise ValueError("Scansione Bluetooth non riuscita: il Bluetooth è acceso?")

    # ---- invio --------------------------------------------------------
    async def send(self, radio_id: str, text: str, channel_index: int = 0,
                   to: str | None = None, reply_id: int | None = None,
                   emoji: bool = False) -> dict:
        self._get(radio_id)
        if not text or not text.strip():
            raise ValueError("Messaggio vuoto")
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("Messaggio troppo lungo (max 200 byte)")
        if to is not None and not _is_node_id(to):
            raise ValueError("Destinatario non valido")
        if not isinstance(channel_index, int) or not 0 <= channel_index <= 7:
            raise ValueError("Canale non valido")
        problem = reply_problem(text, reply_id, emoji)
        if problem is not None:
            raise ValueError(problem)
        conn = self._connectors[radio_id]
        st = conn.state()
        if st["state"] != "connected" or not st["my_node_id"]:
            raise ValueError("Radio non connessa")
        my_id = st["my_node_id"]
        self._pending_seq += 1
        mine = self.ingestor.live.nodes.get(int(my_id[1:], 16))
        message = {"key": f"out:{radio_id}:pending-{self._pending_seq}", "from": my_id,
                   "from_name": mine["long_name"] if mine else None,
                   "to": to or BROADCAST_ID, "channel": str(channel_index), "text": text,
                   "time": int(time.time()), "country": mine["country"] if mine else None,
                   "source": "rf", "direction": "out", "radio_id": radio_id,
                   "channel_index": channel_index, "packet_id": None, "status": "sending",
                   "reply_id": reply_id, "emoji": emoji, "pki": False, "error": None}
        self.ingestor.live.messages.append(message)
        self.ingestor.on_message(dict(message))
        task = asyncio.create_task(
            self._finish_send(conn, message, my_id, text, channel_index, to, reply_id, emoji))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return dict(message)

    async def _finish_send(self, conn, message: dict, my_id: str, text: str,
                           channel_index: int, to: str | None, reply_id: int | None = None,
                           emoji: bool = False) -> None:
        try:
            packet_id = await conn.send_text(text, channel_index, to, reply_id=reply_id,
                                             emoji=emoji)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("invio radio %s fallito: %r", message["radio_id"], exc)
            message["status"], message["error"] = "failed", SEND_FAILED
            if self.ingestor.on_status is not None:
                self.ingestor.on_status(message["key"], "failed", SEND_FAILED)
            return
        with contextlib.suppress(ValueError):
            self.ingestor.live.messages.remove(message)
        self.ingestor.record_outgoing(message["radio_id"], my_id, packet_id, text,
                                      channel_index, to or BROADCAST_ID, status="sent",
                                      replaces=message["key"], time_=message["time"],
                                      reply_id=reply_id, emoji=emoji)
        early = self._early_acks.pop((message["radio_id"], packet_id), None)
        if early is not None:
            self.ingestor.set_status(f"out:{message['radio_id']}:{packet_id}", *early)

    # ---- waypoint -----------------------------------------------------
    def local_ids(self) -> set[str]:
        """Id dei nodi delle radio configurate (quelli noti)."""
        nums = (self.ingestor.radio_node(rid) for rid in self._cfgs)
        return {node_id(n) for n in nums if n is not None}

    async def send_waypoint(self, radio_id: str, name: str, description: str, icon: str,
                            lat: float, lon: float, expire_h: int | None,
                            channel_index: int) -> dict:
        from meshtastic.protobuf import mesh_pb2
        self._get(radio_id)
        if not name or len(name.encode("utf-8")) > 30:
            raise ValueError("Nome non valido (1-30 byte)")
        if len(description.encode("utf-8")) > 100:
            raise ValueError("Descrizione troppo lunga (max 100 byte)")
        if len(icon) != 1 or ord(icon) < 0x20 or 0xD800 <= ord(icon) <= 0xDFFF:
            raise ValueError("Icona non valida")
        if (not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lat, lon))
                or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0)):
            raise ValueError("Coordinate non valide")
        if expire_h is not None and (not isinstance(expire_h, int) or isinstance(expire_h, bool)
                                     or not 1 <= expire_h <= 720):
            raise ValueError("Scadenza non valida (1-720 ore)")
        if not isinstance(channel_index, int) or not 0 <= channel_index <= 7:
            raise ValueError("Canale non valido")
        conn = self._connectors[radio_id]
        st = conn.state()
        if st["state"] != "connected" or not st["my_node_id"]:
            raise ValueError("Radio non connessa")
        my_num = int(st["my_node_id"][1:], 16)
        wid = 0
        while wid == 0:
            wid = secrets.randbits(32)
        expire = int(time.time()) + expire_h * 3600 if expire_h else 0
        lat_i, lon_i = round(lat * 1e7), round(lon * 1e7)
        wp = mesh_pb2.Waypoint(id=wid, latitude_i=lat_i, longitude_i=lon_i, expire=expire,
                               locked_to=my_num, name=name, description=description,
                               icon=ord(icon))
        packet_id = await conn.send_waypoint(wp, channel_index)
        # lo stesso percorso di un waypoint ricevuto: compare subito
        self.ingestor.handle(MeshEvent(
            source="rf", from_node=my_num, to_node=0xFFFFFFFF, packet_id=packet_id,
            channel=str(channel_index), rx_time=time.time(), snr=None, rssi=None, hops=None,
            gateway_id=None, radio_id=radio_id, kind="waypoint",
            payload=WaypointData(id=wid, lat=lat_i * 1e-7, lon=lon_i * 1e-7, name=name,
                                 description=description, icon=ord(icon), expire=expire,
                                 locked_to=my_num)))
        row = self.store.get_waypoint(wid)
        return waypoint_json(row, self.ingestor.live.nodes,
                             {self.ingestor.radio_node(r) for r in self._cfgs} - {None})

    async def delete_waypoint(self, wid: int) -> None:
        """Elimina un proprio waypoint: lo ri-invia con expire=1 (come le app ufficiali)."""
        from meshtastic.protobuf import mesh_pb2
        row = self.store.get_waypoint(wid)
        if row is None or row["deleted"]:
            raise KeyError(wid)
        owner = self.local_radio_for(row["from_num"])
        if owner is None:
            raise PermissionError(wid)
        try:
            channel_index = int(row["channel"])
        except (TypeError, ValueError):
            channel_index = 0
        wp = mesh_pb2.Waypoint(
            id=wid, latitude_i=round(row["lat"] * 1e7), longitude_i=round(row["lon"] * 1e7),
            expire=1, locked_to=row["locked_to"] or 0, name=row["name"] or "",
            description=row["description"] or "", icon=row["icon"] or 0)
        await self._connectors[owner].send_waypoint(wp, channel_index)
        self.store.delete_waypoint(wid)
        self.store.commit()
        if self.ingestor.on_waypoint is not None:
            self.ingestor.on_waypoint({"deleted": wid})

    # ---- accesso per la configurazione ---------------------------------
    def connector(self, radio_id: str):
        """Connettore della radio (KeyError se sconosciuta)."""
        self._get(radio_id)
        return self._connectors[radio_id]

    def radio_kind(self, radio_id: str) -> str:
        return self._get(radio_id)["kind"]

    def local_radio_for(self, num: int) -> str | None:
        """Radio collegata il cui nodo e' `num`, se c'e'."""
        mine = node_id(num)
        for rid in self._cfgs:
            st = self._connectors[rid].state()
            if st["state"] == "connected" and st.get("my_node_id") == mine:
                return rid
        return None

    def pick_radio(self, num: int) -> str:
        """Radio collegata che sente il nodo con meno hop (come il traceroute)."""
        return self._pick_radio(num)

    # ---- traceroute ---------------------------------------------------
    def _pick_radio(self, num: int) -> str:
        connected = [rid for rid in self._cfgs
                     if self._connectors[rid].state()["state"] == "connected"]
        if not connected:
            raise NoRadioConnected("Nessuna radio collegata")
        heard = (self.ingestor.live.nodes.get(num) or {}).get("heard_by") or {}
        hops = {rid: heard[rid]["hops"] for rid in connected
                if rid in heard and heard[rid].get("hops") is not None}
        return min(hops, key=hops.get) if hops else connected[0]

    async def traceroute(self, target_id: str, radio_id: str | None) -> dict:
        if not _is_node_id(target_id):
            raise ValueError("Nodo non valido")
        num = int(target_id[1:], 16)
        if radio_id is None:
            radio_id = self._pick_radio(num)
        else:
            self._get(radio_id)
            if self._connectors[radio_id].state()["state"] != "connected":
                raise NoRadioConnected("Radio non connessa")
        conn, now = self._connectors[radio_id], self._clock()
        last = self._last_trace.get(radio_id)
        if last is not None and now - last < TRACEROUTE_INTERVAL:
            raise TracerouteThrottled(math.ceil(TRACEROUTE_INTERVAL - (now - last)))
        self._last_trace[radio_id] = now  # prenota subito: un solo invio alla volta
        self._tracing.add(radio_id)
        try:
            try:
                packet_id = await conn.send_traceroute(num)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise ValueError(str(exc)) from exc
            tid = self.store.add_traceroute(radio_id, num, now)
            self.store.commit()
        except BaseException:
            self._last_trace.pop(radio_id, None)  # niente invio utile: libera il limite
            raise
        finally:
            self._tracing.discard(radio_id)
        result = {"id": tid, "radio_id": radio_id, "target_id": node_id(num), "time": now,
                  "status": "pending", "error": None, "forward": [], "back": []}
        key = (radio_id, packet_id)
        self._traces[key] = result
        self.bus.publish({"type": "traceroute", "result": dict(result)})
        early = self._early_traces.pop(key, None)  # esito arrivato durante l'invio
        if early is not None and self._clock() - early[0] < TRACEROUTE_TIMEOUT:
            if early[1] is not None:
                self._finish_ok(key, early[1])
            else:
                self._finish_trace(key, "failed", _routing_text(early[2]))
        return dict(result)  # stato attuale: un esito arrivato durante l'invio e' gia' applicato
