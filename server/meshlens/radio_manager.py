"""Gestione delle radio collegate: persistenza, connettori, invio e stato."""
import asyncio
import contextlib
import logging
import secrets
import time
from typing import Any

from .radio import RadioConnector

log = logging.getLogger(__name__)

KINDS = ("usb", "ble")
MAX_TEXT_BYTES = 200
BLE_SCAN_TIMEOUT = 12.0
LIKELY_VIDS = {"239A", "303A", "10C4", "1A86", "2886"}
BROADCAST_ID = "!ffffffff"
MAX_EARLY_ACKS = 100


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
                 ble_scan_fn=default_ble_scan):
        self.store = store
        self.ingestor = ingestor
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
        self._early_acks: dict[tuple[str, int], str] = {}
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
            self.ingestor.handle, self._on_state, self._on_ack, self._iface_factory)

    # ---- callback dei connettori (thread del loop) --------------------
    def _on_state(self, state: dict) -> None:
        if state.get("state") == "connected" and state.get("my_node_id"):
            num = int(state["my_node_id"][1:], 16)
            self.ingestor.mark_local_radio(num)
            self.ingestor.set_radio_node(state["id"], num)
        self._publish_radios()

    def _on_ack(self, radio_id: str, packet_id: int, ok: bool, reason: str | None) -> None:
        status = "acked" if ok else "failed"
        key = f"out:{radio_id}:{packet_id}"
        if any(m["key"] == key for m in self.ingestor.live.messages):
            self.ingestor.set_status(key, status)
            return
        # ack arrivato durante send_text: il messaggio definitivo non esiste ancora
        self._early_acks[(radio_id, packet_id)] = status
        while len(self._early_acks) > MAX_EARLY_ACKS:
            del self._early_acks[next(iter(self._early_acks))]

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
                   to: str | None = None) -> dict:
        self._get(radio_id)
        if not text or not text.strip():
            raise ValueError("Messaggio vuoto")
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("Messaggio troppo lungo (max 200 byte)")
        if to is not None and not _is_node_id(to):
            raise ValueError("Destinatario non valido")
        if not isinstance(channel_index, int) or not 0 <= channel_index <= 7:
            raise ValueError("Canale non valido")
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
                   "channel_index": channel_index, "packet_id": None, "status": "sending"}
        self.ingestor.live.messages.append(message)
        self.ingestor.on_message(dict(message))
        task = asyncio.create_task(
            self._finish_send(conn, message, my_id, text, channel_index, to))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return dict(message)

    async def _finish_send(self, conn, message: dict, my_id: str, text: str,
                           channel_index: int, to: str | None) -> None:
        try:
            packet_id = await conn.send_text(text, channel_index, to)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("invio radio %s fallito: %r", message["radio_id"], exc)
            message["status"] = "failed"
            if self.ingestor.on_status is not None:
                self.ingestor.on_status(message["key"], "failed")
            return
        with contextlib.suppress(ValueError):
            self.ingestor.live.messages.remove(message)
        self.ingestor.record_outgoing(message["radio_id"], my_id, packet_id, text,
                                      channel_index, to or BROADCAST_ID, status="sent",
                                      replaces=message["key"], time_=message["time"])
        early = self._early_acks.pop((message["radio_id"], packet_id), None)
        if early is not None:
            self.ingestor.set_status(f"out:{message['radio_id']}:{packet_id}", early)
