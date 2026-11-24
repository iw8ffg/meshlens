"""Diagnosi del collegamento radio (E20): sola lettura, consigli concreti."""
import asyncio
import socket
import threading

import pytest

from meshlens.radio import MSG_BLE_CONNECT, MSG_BLE_PAIR, MSG_PORT_BUSY
from meshlens.radio_diag import (ADVICE, DiagBusy, Probes, RadioDiagnoser,
                                 build_wake_and_want_config, has_frame_header)
from meshtastic.protobuf import mesh_pb2

SENTINEL = "PSK-SEGRETA-123"


class FakeManager:
    def __init__(self, radios=None, ports=None, ble=None, ble_error=None, running=()):
        self._radios = radios or []
        self.running = set(running)
        self._ports = ports if ports is not None else []
        self._ble = ble or []
        self.ble_error = ble_error
        self.calls = []

    def radios(self):
        return [dict(r) for r in self._radios]

    def connector_running(self, radio_id):
        return radio_id in self.running

    async def ports(self):
        self.calls.append("ports")
        return list(self._ports)

    async def ble_scan(self):
        self.calls.append("ble_scan")
        if self.ble_error:
            raise ValueError(self.ble_error)
        return list(self._ble)


class FakeProbes:
    def __init__(self, **kw):
        self.counts = {k: 0 for k in ("probe_serial_open", "probe_frames_serial", "probe_tcp",
                                      "probe_frames_tcp", "list_problem_usb", "list_paired_ble",
                                      "resolve_host")}
        self.serial_error = kw.get("serial_error")
        self.frames = kw.get("frames", True)
        self.tcp_error = kw.get("tcp_error")
        self.problems = kw.get("problems", [])
        self.paired = kw.get("paired", set())
        self.dns_error = kw.get("dns_error")
        self.block = kw.get("block")

    def _hit(self, name):
        self.counts[name] += 1
        if self.block is not None and name == self.block[0]:
            self.block[1].wait(5)

    def probe_serial_open(self, port):
        self._hit("probe_serial_open")
        if self.serial_error:
            raise self.serial_error

    def probe_frames_serial(self, port):
        self._hit("probe_frames_serial")
        return self.frames

    def probe_tcp(self, host, port):
        self._hit("probe_tcp")
        if self.tcp_error:
            raise self.tcp_error

    def probe_frames_tcp(self, host, port):
        self._hit("probe_frames_tcp")
        return self.frames

    def list_problem_usb(self):
        self._hit("list_problem_usb")
        return list(self.problems)

    def list_paired_ble(self):
        self._hit("list_paired_ble")
        return set(self.paired)

    def resolve_host(self, host):
        self._hit("resolve_host")
        if self.dns_error:
            raise self.dns_error
        return ["192.0.2.1"]


def port(device="COM5", vid="10C4"):
    return {"device": device, "description": "CP2102", "vid": vid, "pid": "EA60",
            "likely_meshtastic": vid in ("10C4", "1A86", "303A", "239A", "2886"),
            "in_use_by": None}


def radio(kind="usb", address="COM5", state="error", error=None, rid="r1"):
    return {"id": rid, "name": "R", "kind": kind, "address": address, "auto_connect": True,
            "state": state, "error": error, "my_node_id": None, "my_node_name": None,
            "channels": [{"index": 0, "psk": SENTINEL}], "security": SENTINEL}


def check(result, name):
    return next(c for c in result["checks"] if c["check"] == name)


async def diag(manager, probes, **kw):
    return await RadioDiagnoser(manager, probes=probes).diagnose(**kw)


# ---- USB ------------------------------------------------------------------
async def test_usb_port_missing_and_driver_missing():
    m = FakeManager(ports=[port("COM9")])
    r = await diag(m, FakeProbes(problems=[{"chip": "CP210x"}]), kind="usb", address="COM5")
    c = check(r, "port_listed")
    assert c["status"] == "fail" and c["advice"] == "usb_driver_missing"
    assert c["params"]["chip"] == "CP210x" and r["advice"] == "usb_driver_missing"
    r = await diag(m, FakeProbes(), kind="usb", address="COM5")
    assert check(r, "port_listed")["advice"] == "usb_port_missing"
    assert r["advice"] == "usb_port_missing"
    assert check(r, "port_open")["status"] == "skip"


async def test_usb_port_busy():
    m = FakeManager(ports=[port()])
    p = FakeProbes(serial_error=PermissionError(13, "Access is denied", "C:\\Users\\mario\\x"))
    r = await diag(m, p, kind="usb", address="COM5")
    c = check(r, "port_open")
    assert c["status"] == "fail" and r["advice"] == "usb_port_busy"
    assert "mario" not in str(r)
    p = FakeProbes(serial_error=OSError("could not open port 'COM5': PermissionError(13, "
                                        "'Accesso negato.', None, 5)"))
    assert (await diag(m, p, kind="usb", address="com5"))["advice"] == "usb_port_busy"
    p = FakeProbes(serial_error=FileNotFoundError(2, "x"))
    assert (await diag(m, p, kind="usb", address="COM5"))["advice"] == "usb_port_missing"


async def test_usb_unknown_chip_warns():
    m = FakeManager(ports=[port(vid="0403")])
    r = await diag(m, FakeProbes(), kind="usb", address="COM5")
    c = check(r, "usb_driver")
    assert c["status"] == "warn" and c["advice"] == "usb_unknown_chip"
    assert check(r, "meshtastic_probe")["status"] == "ok"  # la diagnosi prosegue
    assert r["advice"] == "usb_unknown_chip"


async def test_usb_not_meshtastic():
    m = FakeManager(ports=[port()])
    r = await diag(m, FakeProbes(frames=False), kind="usb", address="COM5")
    assert check(r, "meshtastic_probe")["advice"] == "usb_not_meshtastic"


async def test_usb_all_ok():
    m = FakeManager(ports=[port()])
    r = await diag(m, FakeProbes(), kind="usb", address="COM5")
    assert r["advice"] is None and all(c["status"] == "ok" for c in r["checks"])
    assert r["kind"] == "usb" and r["address"] == "COM5"


def test_dtr_rts_disabled_before_open():
    events = []

    class FakeSerial:
        def __init__(self):
            self._dtr = self._rts = True
            self.port = None
            self.is_open = False

        @property
        def dtr(self):
            return self._dtr

        @dtr.setter
        def dtr(self, v):
            events.append(("dtr", v))
            self._dtr = v

        @property
        def rts(self):
            return self._rts

        @rts.setter
        def rts(self, v):
            events.append(("rts", v))
            self._rts = v

        def open(self):
            events.append(("open", self._dtr, self._rts))
            if FakeSerial.fail:
                raise PermissionError(13, "denied")
            self.is_open = True

        def close(self):
            events.append(("close",))

    FakeSerial.fail = False
    p = Probes(serial_factory=FakeSerial)
    p.probe_serial_open("COM5")
    assert ("dtr", False) in events and ("rts", False) in events
    assert events.index(("open", False, False)) > events.index(("dtr", False))
    assert events[-1] == ("close",)
    events.clear()
    FakeSerial.fail = True
    with pytest.raises(PermissionError):
        p.probe_serial_open("COM5")
    assert events[-1] == ("close",)


# ---- BLE ------------------------------------------------------------------
async def test_ble_adapter_off():
    m = FakeManager(ble_error="Scansione Bluetooth non riuscita: il Bluetooth è acceso?")
    r = await diag(m, FakeProbes(), kind="ble", address="AA:BB:CC:DD:EE:FF")
    assert check(r, "bt_adapter")["advice"] == "ble_off" and r["advice"] == "ble_off"


async def test_ble_not_visible():
    m = FakeManager(ble=[{"address": "11:22:33:44:55:66", "name": "Meshtastic_1"}])
    r = await diag(m, FakeProbes(), kind="ble", address="aa:bb:cc:dd:ee:ff")
    assert check(r, "ble_visible")["advice"] == "ble_not_visible"
    m = FakeManager(ble=[{"address": "AA:BB:CC:DD:EE:FF", "name": "Meshtastic_1"}])
    r = await diag(m, FakeProbes(paired={"AABBCCDDEEFF"}), kind="ble",
                   address="aa:bb:cc:dd:ee:ff")
    assert check(r, "ble_visible")["status"] == "ok" and r["advice"] is None


async def test_ble_stale_pairing_and_pair_needed():
    addr = "AA:BB:CC:DD:EE:FF"
    vis = [{"address": addr, "name": "M"}]
    m = FakeManager(radios=[radio("ble", addr, "error", MSG_BLE_PAIR)], ble=vis)
    r = await diag(m, FakeProbes(paired={"AABBCCDDEEFF"}), radio_id="r1")
    assert check(r, "ble_pairing")["advice"] == "ble_stale_pairing"
    r = await diag(m, FakeProbes(paired=set()), radio_id="r1")
    assert check(r, "ble_pairing")["advice"] == "ble_pair_needed"
    m = FakeManager(radios=[radio("ble", addr, "error", MSG_BLE_CONNECT)], ble=vis)
    r = await diag(m, FakeProbes(paired={"AABBCCDDEEFF"}), radio_id="r1")
    assert r["advice"] == "ble_connect_failed"


# ---- TCP ------------------------------------------------------------------
async def test_tcp_bad_address():
    r = await diag(FakeManager(), FakeProbes(), kind="tcp", address="bad host!")
    assert check(r, "address_valid")["advice"] == "tcp_bad_address"
    assert check(r, "tcp_connect")["status"] == "skip"


async def test_tcp_dns_failure():
    p = FakeProbes(dns_error=socket.gaierror(11001, "x"))
    r = await diag(FakeManager(), p, kind="tcp", address="radio.local")
    assert r["advice"] == "tcp_not_found" and p.counts["probe_tcp"] == 0


def tcp_saved(addr="192.0.2.1"):
    """Radio TCP salvata e ferma: le sonde di rete vanno solo verso radio configurate (M8)."""
    return FakeManager(radios=[radio("tcp", addr, "disconnected")])


async def test_tcp_refused():
    r = await diag(tcp_saved(), FakeProbes(tcp_error=ConnectionRefusedError()), kind="tcp",
                   address="192.0.2.1")
    assert r["advice"] == "tcp_refused"


async def test_tcp_unreachable_timeout():
    for err in (socket.timeout(), TimeoutError(), OSError("no route")):
        r = await diag(tcp_saved(), FakeProbes(tcp_error=err), kind="tcp",
                       address="192.0.2.1:4403")
        assert r["advice"] == "tcp_unreachable"


async def test_tcp_not_meshtastic_or_busy():
    r = await diag(tcp_saved(), FakeProbes(frames=False), radio_id="r1")
    assert check(r, "meshtastic_probe")["advice"] == "tcp_not_meshtastic_or_busy"


# ---- trasversali ----------------------------------------------------------
@pytest.mark.parametrize("state", ["connected", "connecting", "reconnecting"])
async def test_probes_skipped_when_radio_in_use(state):
    for kind, addr in (("usb", "COM5"), ("tcp", "192.0.2.1"), ("ble", "AA:BB:CC:DD:EE:FF")):
        m = FakeManager(radios=[radio(kind, addr, state)], ports=[port()],
                        ble=[{"address": "AA:BB:CC:DD:EE:FF", "name": "M"}])
        p = FakeProbes()
        r = await diag(m, p, radio_id="r1")
        for name in ("probe_serial_open", "probe_frames_serial", "probe_tcp",
                     "probe_frames_tcp"):
            assert p.counts[name] == 0, (kind, name)
        skipped = [c for c in r["checks"] if c["status"] == "skip"]
        if kind != "ble":
            assert skipped and all(c["advice"] == "in_use_by_meshlens" for c in skipped)
        assert r["radio_state"] == state
    # anche una radio non salvata con lo stesso indirizzo di una in uso
    m = FakeManager(radios=[radio("usb", "COM5", "connected")], ports=[port()])
    p = FakeProbes()
    await diag(m, p, kind="usb", address="com5")
    assert p.counts["probe_serial_open"] == 0


async def test_last_error_mapping():
    m = FakeManager(radios=[radio("usb", "COM5", "error", MSG_PORT_BUSY)], ports=[port()])
    r = await diag(m, FakeProbes(), radio_id="r1")
    c = check(r, "last_error")
    assert c["advice"] == "usb_port_busy" and r["advice"] == "usb_port_busy"
    m = FakeManager(radios=[radio("usb", "COM5", "error", "errore mai visto")], ports=[port()])
    r = await diag(m, FakeProbes(), radio_id="r1")
    assert r["advice"] is None
    assert not any(c["check"] == "last_error" for c in r["checks"])


async def test_advice_priority_first_fail_then_warn():
    m = FakeManager(ports=[port(vid="0403")])
    r = await diag(m, FakeProbes(frames=False), kind="usb", address="COM5")
    assert check(r, "usb_driver")["status"] == "warn"
    assert r["advice"] == "usb_not_meshtastic"


async def test_single_diagnosis_at_a_time():
    gate = threading.Event()
    m = FakeManager(ports=[port()])
    d = RadioDiagnoser(m, probes=FakeProbes(block=("probe_serial_open", gate)))
    first = asyncio.create_task(d.diagnose(kind="usb", address="COM5"))
    await asyncio.sleep(0.05)
    with pytest.raises(DiagBusy):
        await d.diagnose(kind="usb", address="COM5")
    gate.set()
    assert (await first)["advice"] is None


async def test_total_timeout():
    gate = threading.Event()
    m = FakeManager(ports=[port()])
    d = RadioDiagnoser(m, probes=FakeProbes(block=("probe_serial_open", gate)),
                       total_timeout=0.2)
    r = await d.diagnose(kind="usb", address="COM5")
    gate.set()
    c = check(r, "timeout")
    assert c["status"] == "fail" and r["advice"] == "timeout"
    assert check(r, "port_listed")["status"] == "ok"  # quanto fatto resta


async def test_unknown_radio_and_bad_input():
    with pytest.raises(KeyError):
        await diag(FakeManager(), FakeProbes(), radio_id="nope")
    with pytest.raises(ValueError, match="Tipo di radio non valido"):
        await diag(FakeManager(), FakeProbes(), kind="x", address="a")
    with pytest.raises(ValueError, match="Indirizzo mancante"):
        await diag(FakeManager(), FakeProbes(), kind="tcp", address="  ")


def test_wake_and_want_config_frame():
    frame = build_wake_and_want_config()
    assert frame[:32] == b"\xc3" * 32
    assert frame[32:34] == b"\x94\xc3"
    length = (frame[34] << 8) | frame[35]
    body = frame[36:]
    assert len(body) == length
    msg = mesh_pb2.ToRadio()
    msg.ParseFromString(body)
    assert msg.want_config_id != 0
    assert has_frame_header(b"junk\x94\xc3\x00\x10abc")
    assert not has_frame_header(b"hello")


async def test_no_secrets_in_result():
    for kind, addr in (("usb", "COM5"), ("ble", "AA:BB:CC:DD:EE:FF"), ("tcp", "192.0.2.1")):
        m = FakeManager(radios=[radio(kind, addr, "error", MSG_PORT_BUSY)], ports=[port()],
                        ble=[{"address": addr, "name": "M"}])
        r = await diag(m, FakeProbes(), radio_id="r1")
        assert SENTINEL not in str(r) and "security" not in str(r)


def test_advice_codes_listed():
    for code in ("usb_port_missing", "usb_driver_missing", "usb_port_busy", "usb_unknown_chip",
                 "usb_not_meshtastic", "ble_off", "ble_not_visible", "ble_stale_pairing",
                 "ble_pair_needed", "ble_connect_failed", "tcp_bad_address", "tcp_not_found",
                 "tcp_refused", "tcp_unreachable", "tcp_not_meshtastic_or_busy",
                 "in_use_by_meshlens", "timeout"):
        assert code in ADVICE


def test_problem_usb_parsing():
    from meshlens.radio_diag import chips_from_instance_ids, paired_from_instance_ids
    ids = ["USB\\VID_10C4&PID_EA60\\0001", "USB\\VID_1A86&PID_7523\\5&1",
           "USB\\VID_046D&PID_C52B\\x", "PCI\\VEN_8086"]
    assert chips_from_instance_ids(ids) == [{"chip": "CP210x"}, {"chip": "CH340"}]
    assert paired_from_instance_ids(["BTHLE\\DEV_AABBCCDDEEFF\\7&1", "BTHENUM\\x"]) == \
        {"AABBCCDDEEFF"}



# ---- M7: mai aprire una porta di un connettore che sta riprovando -----------------------
async def test_probes_skipped_while_connector_retries():
    for kind, addr in (("usb", "COM5"), ("tcp", "192.0.2.1")):
        m = FakeManager(radios=[radio(kind, addr, "error")], ports=[port()], running={"r1"})
        p = FakeProbes()
        r = await diag(m, p, radio_id="r1")
        for name in ("probe_serial_open", "probe_frames_serial", "probe_tcp",
                     "probe_frames_tcp"):
            assert p.counts[name] == 0, (kind, name)
        assert any(c["advice"] == "in_use_by_meshlens" for c in r["checks"])
        p = FakeProbes()
        await diag(m, p, kind=kind, address=addr.lower())  # stesso indirizzo, non salvato
        assert p.counts["probe_serial_open"] == 0 and p.counts["probe_tcp"] == 0


# ---- M8: sonda TCP solo verso l'host:porta di una radio salvata --------------------------
async def test_tcp_probe_only_towards_saved_radio():
    p = FakeProbes()
    r = await diag(FakeManager(), p, kind="tcp", address="192.0.2.7:4403")
    assert p.counts["probe_tcp"] == 0 and p.counts["probe_frames_tcp"] == 0
    assert check(r, "tcp_connect")["status"] == "skip"
    assert check(r, "tcp_connect")["params"] == {"reason": "not_saved"}
    assert check(r, "address_valid")["status"] == "ok"
    # stesso host ma porta diversa: non e' la radio salvata
    p = FakeProbes()
    await diag(tcp_saved("192.0.2.7"), p, kind="tcp", address="192.0.2.7:8080")
    assert p.counts["probe_tcp"] == 0
    # radio salvata (porta predefinita 4403, maiuscole diverse): sonde ammesse
    p = FakeProbes()
    await diag(tcp_saved("Radio.Local"), p, kind="tcp", address="radio.local:4403")
    assert p.counts["probe_tcp"] == 1
