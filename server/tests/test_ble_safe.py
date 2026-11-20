import asyncio
import threading
import time

import pytest

from meshlens import ble_safe
from meshlens.ble_safe import SafeBLEInterface
from meshtastic.ble_interface import BLEInterface
from meshtastic.mesh_interface import MeshInterface


class FakeClient:
    def __init__(self, address=None, **kwargs):
        self.address = address
        self.cb = kwargs.get("disconnected_callback")
        self.disconnects = 0
        self.closes = 0
        self.default_timeout = None
        self.fail_connect = None
        self.fail_disconnect = False
        self.iface = None

    def connect(self):
        if self.fail_connect:
            raise self.fail_connect

    def discover(self):
        pass

    def disconnect(self):
        self.disconnects += 1
        if self.fail_disconnect:
            raise TimeoutError()
        if self.iface is not None:  # come bleak: il callback parte dal disconnect
            self.iface.close()

    def close(self):
        self.closes += 1


def bare(monkeypatch, client=None):
    iface = SafeBLEInterface.__new__(SafeBLEInterface)
    iface._init_safe_state()
    iface.client = client
    iface._want_receive = False
    iface._receiveThread = None
    lost = threading.Event()
    monkeypatch.setattr(SafeBLEInterface, "_disconnected", lambda self: lost.set())
    monkeypatch.setattr(MeshInterface, "close", lambda self: None)
    return iface, lost


def fake_device(monkeypatch):
    monkeypatch.setattr(SafeBLEInterface, "find_device",
                        lambda self, a: type("D", (), {"address": "AA"})())


def test_disconnect_callback_publishes_lost_without_close(monkeypatch):
    holder = {}

    def make(address, **kw):
        holder["c"] = FakeClient(address, **kw)
        return holder["c"]
    monkeypatch.setattr(ble_safe, "SafeBLEClient", make)
    iface, lost = bare(monkeypatch)
    fake_device(monkeypatch)
    closed = []
    monkeypatch.setattr(SafeBLEInterface, "close", lambda self: closed.append(1))
    client = iface.connect("AA")
    assert client.default_timeout == ble_safe.OP_TIMEOUT
    holder["c"].cb(holder["c"])  # callback del loop BLE
    assert lost.wait(2)
    assert closed == []


def test_connect_failure_closes_client(monkeypatch):
    c = FakeClient("AA")
    c.fail_connect = RuntimeError("boom")
    monkeypatch.setattr(ble_safe, "SafeBLEClient", lambda address, **kw: c)
    iface, _ = bare(monkeypatch)
    fake_device(monkeypatch)
    with pytest.raises(RuntimeError):
        iface.connect("AA")
    assert c.closes == 1


def test_close_is_reentrant_and_bounded(monkeypatch):
    c = FakeClient("AA")
    iface, lost = bare(monkeypatch, c)
    c.iface = iface  # disconnect() richiama close()
    iface.close()
    iface.close()
    assert c.disconnects == 1 and c.closes == 1 and iface.client is None
    assert c.default_timeout == ble_safe.CLOSE_TIMEOUT
    assert lost.is_set()


def test_close_swallows_errors(monkeypatch):
    c = FakeClient("AA")
    c.fail_disconnect = True
    iface, lost = bare(monkeypatch, c)
    iface.close()
    assert c.closes == 1 and iface.client is None and lost.is_set()


def test_constructor_failure_closes_in_background(monkeypatch):
    def boom(self, *a, **kw):
        raise TimeoutError("60s")
    monkeypatch.setattr(BLEInterface, "__init__", boom)
    closed = threading.Event()
    monkeypatch.setattr(SafeBLEInterface, "close", lambda self: closed.set())
    with pytest.raises(TimeoutError):
        SafeBLEInterface("AA")
    assert closed.wait(2)


def test_safe_client_times_out():
    client = ble_safe.SafeBLEClient()  # senza indirizzo: solo il loop
    try:
        async def hang():
            await asyncio.sleep(60)
        client.default_timeout = 0.1
        t0 = time.time()
        with pytest.raises(BaseException):
            client.async_await(hang())
        assert time.time() - t0 < 2
    finally:
        client.close()
