import base64
import json

from meshlens.config_model import MASK
from meshlens.coverage import prepare_changes
from meshlens.radio import MSG_ADMIN_UNAUTH, AdminError
from test_api import client, logged
from test_api_config import make_env
from test_config_service import LOCAL_NUM, REMOTE, REMOTE_NUM
from test_radio_manager import MY_ID


async def settle(ctx, jobs):
    for j in jobs:
        await ctx.config.join(j["id"])


async def prepare(c, rid, private=False, interval=30):
    r = await c.post("/api/coverage/prepare", json={
        "radio_id": rid, "mobile_id": REMOTE, "interval_s": interval,
        "private_channel": private})
    assert r.status_code == 200, r.text
    return r.json()


def test_prepare_changes_mobile_and_base():
    assert prepare_changes("mobile", 30, None) == {
        "module_config.range_test.enabled": True,
        "module_config.range_test.sender": 30,
        "config.position.position_broadcast_secs": 30,
        "config.position.position_broadcast_smart_enabled": True,
        "config.position.broadcast_smart_minimum_interval_secs": 30,
        "config.position.gps_mode": "ENABLED"}
    assert prepare_changes("base", 30, None) == {
        "module_config.range_test.enabled": True, "module_config.range_test.sender": 0}
    pc = {"name": "prova", "psk": "AAAA"}
    for role in ("mobile", "base"):
        ch = {k: v for k, v in prepare_changes(role, 60, pc).items()
              if k.startswith("channels.")}
        assert ch == {"channels.0.name": "prova", "channels.0.psk": "AAAA",
                      "channels.0.position_precision": 32}


async def test_private_channel_same_psk_both_and_risky():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        plan = await prepare(c, rid, private=True)
        assert [s["node_id"] for s in plan["steps"]] == [REMOTE, MY_ID]  # mobile prima
        assert all(s["preview"]["risky"] for s in plan["steps"])
        # confermata esplicitamente: senza confirm_risky non parte nulla
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply", json={})
        assert r.status_code == 400 and "rischio" in r.json()["detail"]
        assert conn.writes == []
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply",
                         json={"confirm_risky": True})
        assert r.status_code == 202
        await settle(ctx, r.json()["jobs"])
        assert [j["status"] for j in r.json()["jobs"]] == ["running", "running"]
    psks = {n: protos["channels"][0].settings.psk
            for n, protos in ((REMOTE_NUM, conn.nodes[REMOTE_NUM]), (None, conn.nodes[None]))}
    assert len(psks[None]) == 32 and psks[None] == psks[REMOTE_NUM]
    assert psks[None] != b"CHANPSK-SECRET-0001"
    for n in (None, REMOTE_NUM):
        ch = conn.nodes[n]["channels"][0].settings
        assert ch.name == "MLprova" and ch.module_settings.position_precision == 32
    # la psk non esce mai: ne' nelle anteprime ne' nei messaggi
    b64 = base64.b64encode(psks[None]).decode()
    assert b64 not in json.dumps(plan) + json.dumps(e.drain())


async def test_prepare_order_mobile_first_and_stop_on_failure():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        plan = await prepare(c, rid)
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply", json={})
        jobs = r.json()["jobs"]
        await settle(ctx, jobs)
        assert [j["node_id"] for j in jobs] == [REMOTE, MY_ID]
        assert [w[0] for w in conn.writes] == [REMOTE_NUM, None]  # mobile, poi base
        assert all(ctx.config.job(j["id"])["status"] == "done" for j in jobs)
        assert conn.nodes[None]["module_config"].range_test.enabled
        assert conn.nodes[REMOTE_NUM]["config"].position.position_broadcast_secs == 30
        # secondo piano: il mobile fallisce, la base non parte
        e.now += 1
        conn.write_error = AdminError("unauthorized", MSG_ADMIN_UNAUTH)
        conn.nodes[None]["module_config"].range_test.enabled = False
        conn.nodes[REMOTE_NUM]["config"].position.position_broadcast_secs = 0
        n_writes = len(conn.writes)
        plan = await prepare(c, rid)
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply", json={})
        jobs = r.json()["jobs"]
        await settle(ctx, jobs)
        first, second = (ctx.config.job(j["id"]) for j in jobs)
        assert first["status"] == "failed" and first["error_code"] == "unauthorized"
        assert second["status"] == "failed" and second["error_code"] == "skipped"
        assert len(conn.writes) == n_writes


async def test_restore_only_changed_nodes():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        plan = await prepare(c, rid, private=True)
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply",
                         json={"confirm_risky": True})
        jobs = r.json()["jobs"]
        await settle(ctx, jobs)
        # la base non e' cambiata (finta): ripristino solo del mobile
        last = (await c.get("/api/coverage/prepare/last")).json()
        assert [s["backup_id"] is not None for s in last["steps"]] == [True, True]
        e.store.update_plan(plan["plan_id"], steps={
            **e.store.get_plan(plan["plan_id"])["steps"],
            "steps": [e.store.get_plan(plan["plan_id"])["steps"]["steps"][0],
                      {**e.store.get_plan(plan["plan_id"])["steps"]["steps"][1],
                       "backup_id": None}]})
        e.store.commit()
        e.now += 1
        r = await c.post("/api/coverage/restore", json={"plan_id": plan["plan_id"]})
        assert r.status_code == 200, r.text
        rplan = r.json()
        assert rplan["plan_id"] != plan["plan_id"]
        assert [s["node_id"] for s in rplan["steps"]] == [REMOTE]
        assert MASK in json.dumps(rplan, ensure_ascii=False)
        r = await c.post(f"/api/coverage/prepare/{rplan['plan_id']}/apply",
                         json={"confirm_risky": True})
        assert r.status_code == 202
        await settle(ctx, r.json()["jobs"])
        assert conn.nodes[REMOTE_NUM]["channels"][0].settings.name == "LongFast"
        assert conn.nodes[REMOTE_NUM]["config"].position.position_broadcast_secs == 0
        assert conn.nodes[None]["channels"][0].settings.name == "MLprova"  # base intatta
        assert (await c.get("/api/coverage/prepare/last")).json() is None


async def test_restore_both_nodes_mobile_first():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        plan = await prepare(c, rid, private=True)
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply",
                         json={"confirm_risky": True})
        await settle(ctx, r.json()["jobs"])
        e.now += 1
        rplan = (await c.post("/api/coverage/restore", json={"plan_id": plan["plan_id"]})).json()
        assert [s["node_id"] for s in rplan["steps"]] == [REMOTE, MY_ID]
        n = len(conn.writes)
        r = await c.post(f"/api/coverage/prepare/{rplan['plan_id']}/apply",
                         json={"confirm_risky": True})
        await settle(ctx, r.json()["jobs"])
        assert [w[0] for w in conn.writes[n:]] == [REMOTE_NUM, None]
        assert conn.nodes[None]["channels"][0].settings.name == "LongFast"
        assert conn.nodes[None]["channels"][0].settings.psk == b"CHANPSK-SECRET-0001"
        assert not conn.nodes[None]["module_config"].range_test.enabled
        # gia' ripristinato
        r = await c.post("/api/coverage/restore", json={"plan_id": plan["plan_id"]})
        assert r.status_code == 409


async def test_prepare_last_route():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        assert (await c.get("/api/coverage/prepare/last")).json() is None
        plan = await prepare(c, rid)
        assert (await c.get("/api/coverage/prepare/last")).json() is None  # non ancora applicato
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply", json={})
        jobs = r.json()["jobs"]
        assert len(jobs) == 2 and jobs[0]["kind"] == "apply" and "error_code" in jobs[0]
        await settle(ctx, jobs)
        last = (await c.get("/api/coverage/prepare/last")).json()
        assert last["plan_id"] == plan["plan_id"]
        assert [s["node_id"] for s in last["steps"]] == [REMOTE, MY_ID]
        assert [j["status"] for j in last["jobs"]] == ["done", "done"]
        backups = ctx.config.backups(REMOTE)
        assert backups[0]["reason"] == "coverage_prepare"
        # applicare di nuovo lo stesso piano non e' possibile
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply", json={})
        assert r.status_code == 409


async def test_prepare_errors_and_auth():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with client(ctx) as c:
        for m, path in (("post", "/api/coverage/prepare"), ("post", "/api/coverage/restore"),
                        ("get", "/api/coverage/prepare/last"),
                        ("post", "/api/coverage/prepare/1/apply")):
            kw = {} if m == "get" else {"json": {}}
            assert (await getattr(c, m)(path, **kw)).status_code == 401
    async with logged(ctx) as c:
        r = await c.post("/api/coverage/prepare", json={
            "radio_id": rid, "mobile_id": MY_ID})
        assert r.status_code == 400 and "coincide" in r.json()["detail"]
        r = await c.post("/api/coverage/prepare", json={
            "radio_id": "rnope", "mobile_id": REMOTE})
        assert r.status_code == 404
        assert (await c.post("/api/coverage/prepare/99/apply", json={})).status_code == 404
        assert (await c.post("/api/coverage/restore", json={"plan_id": 99})).status_code == 404
        conn.read_error = AdminError("unauthorized", MSG_ADMIN_UNAUTH)
        r = await c.post("/api/coverage/prepare", json={
            "radio_id": rid, "mobile_id": REMOTE})
        assert r.status_code == 409 and r.json()["detail"] == MSG_ADMIN_UNAUTH


async def test_mobile_local_when_connected_radio():
    """Il mobile e' una radio collegata: lettura e scrittura locali, non tramite la base."""
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    assert ctx.config.radios.local_radio_for(LOCAL_NUM) == rid  # la base stessa e' locale
    async with logged(ctx) as c:
        plan = await prepare(c, rid)
        assert plan["steps"][0]["preview"]["radio_id"] == rid


async def test_plan_steps_carry_role_and_base_only_plan():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        plan = await prepare(c, rid)
        assert [s["role"] for s in plan["steps"]] == ["mobile", "base"]
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply", json={})
        await settle(ctx, r.json()["jobs"])
        last = (await c.get("/api/coverage/prepare/last")).json()
        assert [s["role"] for s in last["steps"]] == ["mobile", "base"]
        # mobile gia' pronto: il piano ha solo la base, e lo dice il ruolo (non la posizione)
        e.now += 1
        conn.nodes[None]["module_config"].range_test.enabled = False
        plan = await prepare(c, rid)
        assert [(s["node_id"], s["role"]) for s in plan["steps"]] == [(MY_ID, "base")]


async def test_failed_restore_keeps_plan_and_running_blocks_restore():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        plan = await prepare(c, rid)
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply", json={})
        await settle(ctx, r.json()["jobs"])
        # un lavoro del piano risulta ancora in corso: niente ripristino
        jid = r.json()["jobs"][0]["id"]
        e.store.update_job(jid, status="running")
        r2 = await c.post("/api/coverage/restore", json={"plan_id": plan["plan_id"]})
        assert r2.status_code == 409 and r2.json()["detail"] == "Preparazione ancora in corso"
        e.store.update_job(jid, status="done")
        e.now += 1
        rplan = (await c.post("/api/coverage/restore", json={"plan_id": plan["plan_id"]})).json()
        conn.write_error = AdminError("unauthorized", MSG_ADMIN_UNAUTH)
        r = await c.post(f"/api/coverage/prepare/{rplan['plan_id']}/apply", json={})
        await settle(ctx, r.json()["jobs"])
        assert all(ctx.config.job(j["id"])["status"] == "failed" for j in r.json()["jobs"])
        last = (await c.get("/api/coverage/prepare/last")).json()
        assert last is not None and last["plan_id"] == plan["plan_id"]


async def test_untouched_plan_is_not_restorable():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        plan = await prepare(c, rid)
        conn.read_error = AdminError("error", "Nessuna risposta")  # nessun nodo verra' toccato
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply", json={})
        await settle(ctx, r.json()["jobs"])
        assert all(ctx.config.job(j["id"])["status"] == "failed" for j in r.json()["jobs"])
        assert (await c.get("/api/coverage/prepare/last")).json() is None
        conn.read_error = None
        r = await c.post("/api/coverage/restore", json={"plan_id": plan["plan_id"]})
        assert r.status_code == 400 and "Nessuna modifica da ripristinare" in r.json()["detail"]
        assert e.store.get_plan(plan["plan_id"])["restored"] is not None


async def test_apply_plan_prevalidates_base_reads():
    e, ctx, conn = await make_env()
    rid = e.mgr.radios()[0]["id"]
    async with logged(ctx) as c:
        plan = await prepare(c, rid)
        base_pv = plan["steps"][1]
        await ctx.config.join(ctx.config.start_read(MY_ID, None, None)["id"])  # riletta la base
        r = await c.post(f"/api/coverage/prepare/{plan['plan_id']}/apply", json={})
        assert r.status_code == 409
        assert conn.writes == [] and base_pv["node_id"] == MY_ID
        assert e.store.get_plan(plan["plan_id"])["applied"] is None
