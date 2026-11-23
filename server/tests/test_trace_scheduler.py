"""Scheduler dei traceroute periodici (E14)."""
import pytest

from meshlens.bus import Bus
from meshlens.db import connect
from meshlens.live import LiveState
from meshlens.radio import RadioBusy
from meshlens.radio_manager import NoRadioConnected, TracerouteThrottled
from meshlens.store import Store
from meshlens.trace_scheduler import (MAX_TRACE_TARGETS, TraceScheduler, mult)

T0 = 100_000.0


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class FakeManager:
    def __init__(self, store):
        self.store, self.calls, self.raise_ = store, [], None
        self.radio_list = [{"id": "r1"}, {"id": "r2"}]
        self.clock = None

    def radios(self):
        return self.radio_list

    async def traceroute(self, target_id, radio_id, auto=False):
        self.calls.append((target_id, radio_id, auto))
        if self.raise_ is not None:
            raise self.raise_
        num = int(target_id[1:], 16)
        tid = self.store.add_traceroute(radio_id or "r1", num, self.clock(), auto)
        return {"id": tid, "radio_id": radio_id or "r1", "target_id": target_id,
                "status": "pending", "auto": auto}


class Env:
    def __init__(self, **settings):
        self.conn = connect(":memory:")
        self.store = Store(self.conn)
        self.live = LiveState()
        self.bus = Bus()
        self.q = self.bus.subscribe()
        self.clock = Clock()
        self.mgr = FakeManager(self.store)
        self.mgr.clock = self.clock
        self.settings = {"traceroute_auto_enabled": True, "traceroute_auto_max_per_hour": 30,
                         **settings}
        self.sched = TraceScheduler(self.conn, self.store, self.mgr, self.live, self.bus,
                                    lambda: self.settings, self.clock)

    def node(self, num, **kw):
        self.live.nodes[num] = {"id": f"!{num:08x}", "num": num, "long_name": f"N{num}",
                                "is_mine": False, "is_ignored": False, **kw}

    def target(self, num, interval_min=60, radio_id=None, **cols):
        self.node(num) if num not in self.live.nodes else None
        self.sched.upsert(f"!{num:08x}", interval_min=interval_min, radio_id=radio_id)
        for k, v in cols.items():
            self.conn.execute(f"UPDATE trace_targets SET {k}=? WHERE node_num=?", (v, num))

    def get(self, num):
        return next(t for t in self.sched.list_targets() if t["node_id"] == f"!{num:08x}")

    def drain(self):
        out = []
        while not self.q.empty():
            out.append(self.q.get_nowait())
        return out


async def test_disabled_does_nothing():
    e = Env(traceroute_auto_enabled=False)
    e.target(0x10)
    assert await e.sched.tick() == "disabled"
    assert e.mgr.calls == []


async def test_sends_at_most_one_per_tick():
    e = Env()
    e.target(0x10, last_run=T0 - 9000)
    e.clock.t += 1
    e.target(0x11)  # mai eseguito: prima di tutti
    e.clock.t += 1
    e.target(0x12, last_run=T0 - 5000)
    assert await e.sched.tick() == "sent"
    assert e.mgr.calls == [("!00000011", None, True)]
    assert await e.sched.tick() == "sent"
    assert e.mgr.calls[1] == ("!00000010", None, True)  # last_run piu' vecchio


async def test_min_interval_per_node():
    e = Env()
    e.target(0x10, interval_min=60)
    assert await e.sched.tick() == "sent"
    assert e.get(0x10)["last_run"] == T0
    e.clock.t = T0 + 3599
    assert await e.sched.tick() is None
    e.clock.t = T0 + 3600
    assert await e.sched.tick() == "sent"
    assert len(e.mgr.calls) == 2


def test_mult():
    assert [mult(n) for n in (0, 2, 3, 5, 6, 20)] == [1, 1, 2, 2, 4, 4]


async def test_interval_multiplier_after_failures():
    e = Env()
    e.target(0x10, last_run=T0, fail_count=3)
    e.clock.t = T0 + 3600
    assert await e.sched.tick() is None
    e.clock.t = T0 + 7200
    assert await e.sched.tick() == "sent"
    e2 = Env()
    e2.target(0x10, last_run=T0, fail_count=6)
    e2.clock.t = T0 + 14399
    assert await e2.sched.tick() is None
    e2.clock.t = T0 + 14400
    assert await e2.sched.tick() == "sent"


async def test_hourly_cap():
    e = Env(traceroute_auto_max_per_hour=2)
    e.target(0x10)
    e.store.add_traceroute("r1", 0x99, T0 - 100, True)
    e.store.add_traceroute("r1", 0x99, T0 - 200, True)
    e.store.add_traceroute("r1", 0x99, T0 - 300, False)  # manuale: non conta
    assert await e.sched.tick() == "cap"
    assert e.mgr.calls == []
    e.conn.execute("UPDATE traceroutes SET time=? WHERE time=?", (T0 - 3700, T0 - 200))
    assert await e.sched.tick() == "sent"


async def test_throttled_defers_without_consuming_interval():
    e = Env()
    e.target(0x10)
    e.mgr.raise_ = TracerouteThrottled(20)
    assert await e.sched.tick() == "throttled"
    t = e.get(0x10)
    assert t["last_run"] is None and t["last_status"] == "throttled"
    e.mgr.raise_ = None
    e.clock.t = T0 + 24
    assert await e.sched.tick() is None
    e.clock.t = T0 + 26
    assert await e.sched.tick() == "sent"


@pytest.mark.parametrize("exc,status", [(RadioBusy(), "busy"),
                                        (NoRadioConnected("Nessuna radio collegata"), "no_radio")])
async def test_busy_and_no_radio_defer_300s(exc, status):
    e = Env()
    e.target(0x10)
    e.target(0x11)
    e.mgr.raise_ = exc
    assert await e.sched.tick() == status
    assert len(e.mgr.calls) == 1  # fine del giro
    t = e.get(0x10)
    assert t["last_run"] is None and t["last_status"] == status
    e.mgr.raise_ = None
    e.clock.t = T0 + 299
    assert await e.sched.tick() == "sent"
    assert e.mgr.calls[-1][0] == "!00000011"  # il primo e' ancora rinviato
    e.clock.t = T0 + 300
    assert await e.sched.tick() == "sent"
    assert e.mgr.calls[-1][0] == "!00000010"


async def test_value_error_counts_as_failed_attempt():
    e = Env()
    e.target(0x10)
    e.mgr.raise_ = ValueError("invio fallito")
    assert await e.sched.tick() == "failed"
    t = e.get(0x10)
    assert t["last_run"] == T0 and t["fail_count"] == 1 and t["last_status"] == "failed"


async def test_skips_mine_ignored_and_unknown_nodes():
    e = Env()
    e.target(0x10)
    e.clock.t += 1
    e.target(0x11)
    e.clock.t += 1
    e.target(0x12)
    e.clock.t += 1
    e.target(0x13)
    e.live.nodes[0x10]["is_mine"] = True
    e.live.nodes[0x11]["is_ignored"] = True
    del e.live.nodes[0x12]
    assert await e.sched.tick() == "sent"
    assert e.mgr.calls == [("!00000013", None, True)]


async def test_radio_gap_between_autos():
    e = Env()
    e.target(0x10, radio_id="r1")
    e.clock.t += 1
    e.target(0x11, radio_id="r1")
    e.clock.t = T0
    assert await e.sched.tick() == "sent"
    e.clock.t = T0 + 30
    assert await e.sched.tick() is None
    e.clock.t = T0 + 59
    assert await e.sched.tick() is None
    e.clock.t = T0 + 60
    assert await e.sched.tick() == "sent"
    assert [c[0] for c in e.mgr.calls] == ["!00000010", "!00000011"]


async def test_pending_finalized_by_bus_event():
    e = Env()
    e.target(0x10)
    await e.sched.tick()
    t = e.get(0x10)
    assert t["last_status"] == "pending"
    tid = t["last_traceroute_id"]
    e.drain()
    e.sched.on_bus({"type": "traceroute", "result": {"id": tid, "status": "pending"}})
    e.sched.on_bus({"type": "traceroute", "result": {"id": 9999, "status": "ok"}})
    e.sched.on_bus({"type": "nodes", "nodes": []})
    assert e.drain() == [] and e.get(0x10)["last_status"] == "pending"
    e.sched.on_bus({"type": "traceroute", "result": {"id": tid, "status": "ok"}})
    t = e.get(0x10)
    assert t["last_status"] == "ok" and t["fail_count"] == 0
    out = e.drain()
    assert len(out) == 1 and out[0]["type"] == "trace_targets"
    assert out[0]["targets"][0]["last_status"] == "ok"
    e.sched.on_bus({"type": "traceroute", "result": {"id": tid, "status": "timeout"}})
    t = e.get(0x10)
    assert t["last_status"] == "timeout" and t["fail_count"] == 1


async def test_sent_publishes_trace_targets():
    e = Env()
    e.target(0x10)
    e.drain()
    await e.sched.tick()
    out = e.drain()
    assert [m["type"] for m in out] == ["trace_targets"]


def test_reconcile_adopts_final_status():
    e = Env()
    e.target(0x10)
    tid = e.store.add_traceroute("r1", 0x10, T0, True)
    e.store.update_traceroute(tid, "failed", "x", [], [])
    e.conn.execute("UPDATE trace_targets SET last_status='pending', last_traceroute_id=?",
                   (tid,))
    e.sched.reconcile()
    assert e.get(0x10)["last_status"] == "failed"


def test_upsert_validation():
    e = Env()
    e.node(0x10)
    e.node(0x20, is_mine=True)
    for bad in (59, 10081):
        with pytest.raises(ValueError, match="Intervallo non valido"):
            e.sched.upsert("!00000010", interval_min=bad)
    with pytest.raises(ValueError, match="tuo nodo"):
        e.sched.upsert("!00000020", interval_min=60)
    with pytest.raises(ValueError, match="Nodo non trovato"):
        e.sched.upsert("!00000099", interval_min=60)
    with pytest.raises(ValueError, match="Radio non valida"):
        e.sched.upsert("!00000010", interval_min=60, radio_id="zz")
    a = e.sched.upsert("!00000010", interval_min=60)
    assert a["interval_min"] == 60 and a["enabled"] is True and a["node_id"] == "!00000010"
    e.clock.t += 50
    b = e.sched.upsert("!00000010", interval_min=10080, enabled=False, radio_id="r2")
    assert b["created"] == a["created"] and b["interval_min"] == 10080
    assert b["enabled"] is False and b["radio_id"] == "r2"
    assert len(e.sched.list_targets()) == 1
    for i in range(MAX_TRACE_TARGETS - 1):
        e.node(0x100 + i)
        e.sched.upsert(f"!{0x100 + i:08x}", interval_min=60)
    e.node(0x999)
    with pytest.raises(ValueError, match="massimo 20"):
        e.sched.upsert("!00000999", interval_min=60)
    e.sched.upsert("!00000010", interval_min=120)  # aggiornare uno esistente resta possibile
    assert e.sched.remove("!00000010") is True
    assert e.sched.remove("!00000010") is False


async def test_disabled_target_not_sent():
    e = Env()
    e.target(0x10)
    e.sched.upsert("!00000010", interval_min=60, enabled=False)
    assert await e.sched.tick() is None


async def test_integration_with_real_manager_sets_auto_flag():
    from test_radio_manager import Env as RmEnv
    rm = RmEnv()
    await rm.mgr.add("usb", "COM5", "A")
    rm.live.nodes[0x42] = {"id": "!00000042", "num": 0x42, "long_name": "X", "is_mine": False,
                           "is_ignored": False}
    sched = TraceScheduler(rm.conn, rm.store, rm.mgr, rm.live, rm.bus,
                           lambda: {"traceroute_auto_enabled": True,
                                    "traceroute_auto_max_per_hour": 6}, lambda: rm.now)
    sched.upsert("!00000042", interval_min=60)
    assert await sched.tick() == "sent"
    row = rm.conn.execute("SELECT id, auto FROM traceroutes").fetchone()
    assert row["auto"] == 1
    t = sched.list_targets()[0]
    assert t["last_status"] == "pending" and t["last_traceroute_id"] == row["id"]


class FakeRuntime:
    def __init__(self, env):
        self.store, self.radios, self.live, self.bus = env.store, env.mgr, env.live, env.bus
        self.settings = env.settings
        self.periodic, self.message_hooks, self.shutdown = [], [], []

    def add_periodic(self, name, interval_s, fn, first_delay_s=None):
        self.periodic.append((name, interval_s, fn, first_delay_s))

    def add_message_hook(self, fn):
        self.message_hooks.append(fn)

    def add_shutdown(self, fn):
        self.shutdown.append(fn)


def make_installed(env):
    from types import SimpleNamespace
    from meshlens import ext_automation
    rt = FakeRuntime(env)
    ctx = SimpleNamespace(conn=env.conn, ext={}, mqtt_sender=None)
    ext_automation.install(rt, ctx)
    return rt, ctx


def test_install_registers_scheduler_and_bus_task():
    e = Env()
    rt, ctx = make_installed(e)
    names = {p[0]: p for p in rt.periodic}
    assert names["trace_scheduler"][1] == 60 and names["trace_scheduler"][3] == 60
    assert names["automation_bus"][1] == 1.0
    assert isinstance(ctx.ext["trace_scheduler"], TraceScheduler)


async def test_bus_task_forwards_events_and_skips_resync():
    from meshlens.ext_automation import drain_bus

    class Svc:
        def __init__(self):
            self.got = []

        def on_bus(self, msg):
            self.got.append(msg)

    class Broken:
        def on_bus(self, msg):
            raise RuntimeError("x")

    bus = Bus()
    q = bus.subscribe()
    a = Svc()
    bus.publish({"type": "resync"})
    bus.publish({"type": "traceroute", "result": {}})
    assert drain_bus(q, {"trace_scheduler": Broken(), "bot": a}) == 2
    assert a.got == [{"type": "traceroute", "result": {}}]


async def test_db_failure_after_send_never_retransmits_every_tick():
    """I1: un errore inatteso (es. DB pieno dopo l'invio) rinvia il nodo in memoria per
    l'intero intervallo: niente traceroute ogni minuto verso lo stesso nodo."""
    import sqlite3
    e = Env()
    e.target(0x10, interval_min=60, radio_id="r1")
    e.mgr.raise_ = sqlite3.OperationalError("database or disk is full")
    for _ in range(5):
        await e.sched.tick()  # non deve propagare l'errore al task periodico
        e.clock.t += 60
    assert len(e.mgr.calls) == 1
    e.mgr.raise_ = None
    e.clock.t = T0 + 3599
    assert await e.sched.tick() is None
    e.clock.t = T0 + 3600
    assert await e.sched.tick() == "sent"
    assert len(e.mgr.calls) == 2


async def test_db_failure_defer_holds_even_if_target_row_cannot_be_written():
    import sqlite3
    e = Env()
    e.target(0x10, interval_min=60)
    e.mgr.raise_ = sqlite3.OperationalError("database is locked")
    real = e.sched.conn

    class BrokenConn:  # anche le scritture best-effort falliscono
        def __getattr__(self, name):
            return getattr(real, name)

        def execute(self, sql, *a):
            if sql.lstrip().upper().startswith("UPDATE"):
                raise sqlite3.OperationalError("database is locked")
            return real.execute(sql, *a)

        def commit(self):
            raise sqlite3.OperationalError("database is locked")

    e.sched.conn = BrokenConn()
    assert await e.sched.tick() == "error"
    e.clock.t += 60
    await e.sched.tick()
    assert len(e.mgr.calls) == 1


async def test_remove_and_readd_keeps_interval():
    """M3: rimuovere e riaggiungere un nodo non azzera i 60 minuti."""
    e = Env()
    e.target(0x10, interval_min=60)
    assert await e.sched.tick() == "sent"
    e.sched.remove("!00000010")
    e.clock.t = T0 + 120
    e.target(0x10, interval_min=60)
    assert e.get(0x10)["last_run"] == T0
    assert await e.sched.tick() is None
    e.clock.t = T0 + 3600
    assert await e.sched.tick() == "sent"
