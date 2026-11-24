"""Diagnosi del collegamento radio (E20): spiega perche' una radio non si collega.

Sola lettura su RadioManager (radios(), ports(), ble_scan()) e sonde indipendenti; nessuna
modifica a radio.py/radio_manager.py. Se il connettore della radio e' collegato o in
collegamento, le sonde che aprono la porta o il socket NON partono (il firmware TCP ammette
un solo client e aprire la COM puo' resettare alcune schede): risultano "skip" con il
consiglio in_use_by_meshlens. Lo stesso vale se il connettore sta ancora lavorando tra due
tentativi (stato "error" con un nuovo tentativo in arrivo): la porta resta sua.
Le sonde TCP (connessione e frame) partono solo verso l'host:porta di una radio salvata:
per un indirizzo non salvato si controllano solo formato e DNS. Una diagnosi alla volta, al
massimo 30 s.
"""
import asyncio
import functools
import logging
import re
import secrets
import socket
import subprocess
import sys
import time

from . import radio as radio_mod
from .radio_manager import KINDS, LIKELY_VIDS, parse_tcp_address

log = logging.getLogger(__name__)

TOTAL_TIMEOUT_S = 30.0
PROBE_WAIT_S = 3.0
POWERSHELL_TIMEOUT_S = 5.0
WAKE = b"\xc3" * 32
START1, START2 = 0x94, 0xC3
IN_USE_STATES = ("connected", "connecting", "reconnecting")
DIAG_BUSY_MSG = "Diagnosi già in corso"
BAD_KIND_MSG = "Tipo di radio non valido"
NO_ADDRESS_MSG = "Indirizzo mancante"

ADVICE = ("usb_port_missing", "usb_driver_missing", "usb_port_busy", "usb_unknown_chip",
          "usb_not_meshtastic", "ble_off", "ble_not_visible", "ble_stale_pairing",
          "ble_pair_needed", "ble_connect_failed", "tcp_bad_address", "tcp_not_found",
          "tcp_refused", "tcp_unreachable", "tcp_not_meshtastic_or_busy",
          "in_use_by_meshlens", "timeout")
IN_USE = "in_use_by_meshlens"

# VID USB -> famiglia del chip (per il driver da installare)
USB_CHIPS = {"10C4": "CP210x", "1A86": "CH340", "303A": "ESP32/native", "239A": "Adafruit/Seeed",
             "2886": "Adafruit/Seeed"}
# ultimo errore del connettore (costanti di radio.py) -> consiglio
LAST_ERROR_ADVICE = {
    radio_mod.MSG_PORT_BUSY: "usb_port_busy",
    radio_mod.MSG_PORT_MISSING: "usb_port_missing",
    radio_mod.MSG_BLE_MISSING: "ble_not_visible",
    radio_mod.MSG_BLE_PAIR: "ble_pair_needed",
    radio_mod.MSG_BLE_CONNECT: "ble_connect_failed",
    radio_mod.MSG_TCP_NOT_FOUND: "tcp_not_found",
    radio_mod.MSG_TCP_REFUSED: "tcp_refused",
    radio_mod.MSG_TCP_UNREACHABLE: "tcp_unreachable",
    radio_mod.MSG_TCP_NO_REPLY: "tcp_not_meshtastic_or_busy",
}
_VID = re.compile(r"^USB\\VID_([0-9A-F]{4})", re.I)
_BTHLE = re.compile(r"^BTHLE\\DEV_([0-9A-F]{12})", re.I)


class DiagBusy(Exception):
    """Un'altra diagnosi e' in corso (l'API risponde 409)."""


def build_wake_and_want_config() -> bytes:
    """32 byte di risveglio 0xC3 + ToRadio(want_config_id) incorniciato 0x94 0xC3 len."""
    from meshtastic.protobuf import mesh_pb2
    body = mesh_pb2.ToRadio(want_config_id=secrets.randbelow(2**31 - 2) + 1).SerializeToString()
    return WAKE + bytes([START1, START2, len(body) >> 8, len(body) & 0xFF]) + body


def has_frame_header(buf: bytes) -> bool:
    return bytes([START1, START2]) in (buf or b"")


def chips_from_instance_ids(ids) -> list[dict]:
    out: list[dict] = []
    for i in ids:
        m = _VID.match(i.strip())
        chip = USB_CHIPS.get(m.group(1).upper()) if m else None
        if chip and {"chip": chip} not in out:
            out.append({"chip": chip})
    return out


def paired_from_instance_ids(ids) -> set[str]:
    return {m.group(1).upper() for i in ids if (m := _BTHLE.match(i.strip()))}


def _powershell_lines(command: str) -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                           capture_output=True, text=True, timeout=POWERSHELL_TIMEOUT_S,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in (r.stdout or "").splitlines() if line.strip()]


def _default_serial():
    import serial  # pyserial (dipendenza di meshtastic)
    return serial.Serial()


class Probes:
    """Sonde reali (sostituibili nei test). Tutte sincrone: girano in un thread."""

    def __init__(self, serial_factory=None, wait_s: float = PROBE_WAIT_S):
        self.serial_factory = serial_factory or _default_serial
        self.wait_s = wait_s

    def _open_serial(self, port: str):
        s = self.serial_factory()
        s.port = port
        try:
            s.baudrate = 115200
            s.timeout = 0.2
        except Exception:  # noqa: BLE001 - porte finte senza questi attributi
            pass
        # DTR/RTS spenti PRIMA dell'apertura: su alcune schede resettano la radio
        s.dtr = False
        s.rts = False
        try:
            s.open()
        except BaseException:
            s.close()
            raise
        return s

    def probe_serial_open(self, port: str) -> None:
        s = self._open_serial(port)
        s.close()

    def probe_frames_serial(self, port: str) -> bool:
        s = self._open_serial(port)
        try:
            s.write(build_wake_and_want_config())
            buf, end = b"", time.monotonic() + self.wait_s
            while time.monotonic() < end:
                buf += s.read(256) or b""
                if has_frame_header(buf):
                    return True
            return False
        finally:
            s.close()

    def probe_tcp(self, host: str, port: int) -> None:
        with socket.create_connection((host, port), timeout=self.wait_s):
            pass

    def probe_frames_tcp(self, host: str, port: int) -> bool:
        with socket.create_connection((host, port), timeout=self.wait_s) as sock:
            sock.sendall(build_wake_and_want_config())
            buf, end = b"", time.monotonic() + self.wait_s
            while time.monotonic() < end:
                sock.settimeout(max(0.05, end - time.monotonic()))
                try:
                    chunk = sock.recv(256)
                except (socket.timeout, TimeoutError):
                    break
                if not chunk:
                    break
                buf += chunk
                if has_frame_header(buf):
                    return True
            return False

    def list_problem_usb(self) -> list[dict]:
        return chips_from_instance_ids(_powershell_lines(
            "Get-PnpDevice -PresentOnly | Where-Object { $_.Status -eq 'Error' } | "
            "ForEach-Object { $_.InstanceId }"))

    def list_paired_ble(self) -> set[str]:
        return paired_from_instance_ids(_powershell_lines(
            "Get-PnpDevice | Where-Object { $_.InstanceId -like 'BTHLE\\DEV_*' } | "
            "ForEach-Object { $_.InstanceId }"))

    def resolve_host(self, host: str):
        return socket.getaddrinfo(host, None)


def _address_key(kind: str, address: str):
    """Indirizzo confrontabile: (host, porta) per TCP, maiuscolo senza spazi per gli altri."""
    if kind == "tcp":
        try:
            host, port = parse_tcp_address(address)
        except ValueError:
            return None
        return host.casefold(), port
    return (address or "").strip().upper()


def _check(name: str, status: str, advice: str | None = None, **params) -> dict:
    return {"check": name, "status": status, "advice": advice, "params": params}


def _serial_advice(exc: BaseException) -> str | None:
    text = f"{type(exc).__name__} {exc}".lower()
    if isinstance(exc, PermissionError) or "permissionerror" in text or "denied" in text \
            or "negato" in text:
        return "usb_port_busy"
    if isinstance(exc, FileNotFoundError) or "filenotfound" in text or "cannot find" in text:
        return "usb_port_missing"
    return None


class RadioDiagnoser:
    def __init__(self, manager, probes=None, clock=time.monotonic,
                 total_timeout: float = TOTAL_TIMEOUT_S):
        self.manager = manager
        self.probes = probes or Probes()
        self.clock = clock
        self.total_timeout = total_timeout
        self._lock = asyncio.Lock()

    async def _call(self, name: str, *args):
        return await asyncio.to_thread(getattr(self.probes, name), *args)

    def _find_radio(self, radio_id: str | None, kind: str | None, address: str | None):
        radios = self.manager.radios() if self.manager is not None else []
        if radio_id is not None:
            r = next((r for r in radios if r["id"] == radio_id), None)
            if r is None:
                raise KeyError(radio_id)
            return r["kind"], r["address"], r.get("state"), r.get("error"), r["id"]
        if kind not in KINDS:
            raise ValueError(BAD_KIND_MSG)
        address = (address or "").strip()
        if not address:
            raise ValueError(NO_ADDRESS_MSG)
        key = _address_key(kind, address)
        same = next((r for r in radios if r["kind"] == kind
                     and _address_key(kind, r["address"]) == key), None)
        if same is not None:  # stessa radio gia' salvata: vale il suo stato
            return kind, address, same.get("state"), same.get("error"), same["id"]
        return kind, address, None, None, None

    def _connector_running(self, rid: str | None) -> bool:
        """Il connettore della radio sta lavorando (anche tra due tentativi): la sua porta
        non va aperta dalla diagnosi."""
        check = getattr(self.manager, "connector_running", None)
        try:
            return bool(rid is not None and check is not None and check(rid))
        except KeyError:
            return False

    async def diagnose(self, *, radio_id: str | None = None, kind: str | None = None,
                       address: str | None = None) -> dict:
        kind, address, state, error, rid = self._find_radio(radio_id, kind, address)
        if self._lock.locked():
            raise DiagBusy(DIAG_BUSY_MSG)
        async with self._lock:
            checks: list[dict] = []
            in_use = state in IN_USE_STATES or self._connector_running(rid)
            runner = {"usb": self._usb, "ble": self._ble, "tcp": self._tcp}[kind]
            if kind == "tcp":
                runner = functools.partial(self._tcp, saved=rid is not None)
            try:
                await asyncio.wait_for(runner(address, in_use, error, checks),
                                       self.total_timeout)
            except asyncio.TimeoutError:
                checks.append(_check("timeout", "fail", "timeout"))
            advice = self._advice(checks)
            if advice is None and error in LAST_ERROR_ADVICE:
                checks.append(_check("last_error", "warn", LAST_ERROR_ADVICE[error]))
                advice = LAST_ERROR_ADVICE[error]
            return {"kind": kind, "address": address, "checks": checks, "advice": advice,
                    "radio_state": state}

    @staticmethod
    def _advice(checks: list[dict]) -> str | None:
        for status in ("fail", "warn"):
            for c in checks:
                if c["status"] == status and c["advice"]:
                    return c["advice"]
        return None

    # ---- USB -------------------------------------------------------------------------
    async def _usb(self, address: str, in_use: bool, error, checks: list) -> None:
        try:
            ports = await self.manager.ports()
        except ValueError:
            ports = []
        found = next((p for p in ports if (p.get("device") or "").upper() == address.upper()),
                     None)
        if found is None:
            problems = await self._call("list_problem_usb")
            if problems:
                chip = problems[0].get("chip")
                checks.append(_check("port_listed", "fail", "usb_driver_missing", chip=chip))
                checks.append(_check("usb_driver", "fail", "usb_driver_missing", chip=chip))
            else:
                checks.append(_check("port_listed", "fail", "usb_port_missing"))
                checks.append(_check("usb_driver", "skip"))
            checks.append(_check("port_open", "skip"))
            checks.append(_check("meshtastic_probe", "skip"))
            return
        checks.append(_check("port_listed", "ok"))
        vid = (found.get("vid") or "").upper()
        if vid in LIKELY_VIDS:
            checks.append(_check("usb_driver", "ok", chip=USB_CHIPS.get(vid)))
        else:
            checks.append(_check("usb_driver", "warn", "usb_unknown_chip", vid=vid or None))
        if in_use:
            checks.append(_check("port_open", "skip", IN_USE))
            checks.append(_check("meshtastic_probe", "skip", IN_USE))
            return
        try:
            await self._call("probe_serial_open", found["device"])
        except Exception as e:  # noqa: BLE001 - errore della porta -> consiglio
            checks.append(_check("port_open", "fail", _serial_advice(e)))
            checks.append(_check("meshtastic_probe", "skip"))
            return
        checks.append(_check("port_open", "ok"))
        try:
            ok = await self._call("probe_frames_serial", found["device"])
        except Exception as e:  # noqa: BLE001
            checks.append(_check("meshtastic_probe", "fail", _serial_advice(e)
                                 or "usb_not_meshtastic"))
            return
        checks.append(_check("meshtastic_probe", "ok") if ok
                      else _check("meshtastic_probe", "fail", "usb_not_meshtastic"))

    # ---- BLE -------------------------------------------------------------------------
    async def _ble(self, address: str, in_use: bool, error, checks: list) -> None:
        try:
            found = await self.manager.ble_scan()
        except ValueError:
            checks.append(_check("bt_adapter", "fail", "ble_off"))
            checks.append(_check("ble_visible", "skip"))
            checks.append(_check("ble_pairing", "skip"))
            return
        checks.append(_check("bt_adapter", "ok"))
        wanted = address.casefold()
        visible = any(wanted in ((d.get("address") or "").casefold(),
                                 (d.get("name") or "").casefold()) for d in found)
        if visible:
            checks.append(_check("ble_visible", "ok"))
        elif in_use:  # collegata a MeshLens: non si annuncia
            checks.append(_check("ble_visible", "skip", IN_USE))
        else:
            checks.append(_check("ble_visible", "fail", "ble_not_visible"))
        paired = await self._call("list_paired_ble")
        is_paired = re.sub(r"[^0-9A-F]", "", address.upper()) in paired
        if error == radio_mod.MSG_BLE_PAIR:
            checks.append(_check("ble_pairing", "fail",
                                 "ble_stale_pairing" if is_paired else "ble_pair_needed"))
        elif error == radio_mod.MSG_BLE_CONNECT:
            checks.append(_check("ble_pairing", "fail", "ble_connect_failed",
                                 paired=is_paired))
        else:
            checks.append(_check("ble_pairing", "ok", paired=is_paired))

    # ---- TCP -------------------------------------------------------------------------
    async def _tcp(self, address: str, in_use: bool, error, checks: list, *,
                   saved: bool = True) -> None:
        try:
            host, port = parse_tcp_address(address)
        except ValueError:
            checks.append(_check("address_valid", "fail", "tcp_bad_address"))
            for name in ("dns", "tcp_connect", "meshtastic_probe"):
                checks.append(_check(name, "skip"))
            return
        checks.append(_check("address_valid", "ok", port=port))
        try:
            await asyncio.wait_for(self._call("resolve_host", host), PROBE_WAIT_S)
        except (socket.gaierror, asyncio.TimeoutError, OSError, UnicodeError):
            checks.append(_check("dns", "fail", "tcp_not_found"))
            checks.append(_check("tcp_connect", "skip"))
            checks.append(_check("meshtastic_probe", "skip"))
            return
        checks.append(_check("dns", "ok"))
        if not saved:
            # M8: connessioni solo verso l'host:porta di una radio salvata (niente sonda di
            # porte arbitrarie); per un indirizzo nuovo: salva la radio e ripeti la diagnosi
            checks.append(_check("tcp_connect", "skip", reason="not_saved"))
            checks.append(_check("meshtastic_probe", "skip", reason="not_saved"))
            return
        if in_use:
            checks.append(_check("tcp_connect", "skip", IN_USE))
            checks.append(_check("meshtastic_probe", "skip", IN_USE))
            return
        try:
            await self._call("probe_tcp", host, port)
        except ConnectionRefusedError:
            checks.append(_check("tcp_connect", "fail", "tcp_refused"))
            checks.append(_check("meshtastic_probe", "skip"))
            return
        except OSError:  # timeout compreso
            checks.append(_check("tcp_connect", "fail", "tcp_unreachable"))
            checks.append(_check("meshtastic_probe", "skip"))
            return
        checks.append(_check("tcp_connect", "ok"))
        try:
            ok = await self._call("probe_frames_tcp", host, port)
        except OSError:
            ok = False
        checks.append(_check("meshtastic_probe", "ok") if ok
                      else _check("meshtastic_probe", "fail", "tcp_not_meshtastic_or_busy"))
