import threading
import time

from meshlens import watchdog
from meshlens.tray import ToastQueue
from meshlens.watchdog import Watchdog


def test_dump_una_volta_e_riarmo():
    now = [0.0]
    calls = []
    w = Watchdog(None, stall_after=15, clock=lambda: now[0], dump=lambda age: calls.append(age))
    now[0] = 10
    assert not w.check()
    now[0] = 16
    assert w.check()
    now[0] = 30
    assert not w.check()  # un solo dump per blocco
    assert len(calls) == 1
    w.beat()  # il loop riprende
    assert not w.check()
    now[0] = 50
    assert w.check()
    assert len(calls) == 2


def test_dump_su_file(tmp_path):
    now = [0.0]
    w = Watchdog(tmp_path, stall_after=1, clock=lambda: now[0])
    now[0] = 5
    assert w.check()
    files = list(tmp_path.glob("stall-*.txt"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "MainThread" in text and "faulthandler" in text


def test_beat_globale_senza_watchdog():
    watchdog.stop()
    watchdog.beat()  # non deve fallire


def test_toast_non_blocca():
    gate = threading.Event()
    got = []

    def notify(title, body):
        gate.wait(5)
        got.append((title, body))

    q = ToastQueue(notify)
    t0 = time.monotonic()
    q.post("a", "b")
    q.post("c", "d")
    assert time.monotonic() - t0 < 0.5
    gate.set()
    q.close()
    q._thread.join(2)
    assert got == [("a", "b"), ("c", "d")]
