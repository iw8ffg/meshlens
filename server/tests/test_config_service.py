import asyncio
import base64
import copy

import pytest
from meshtastic.protobuf import channel_pb2, config_pb2, localonly_pb2

from meshlens.config_model import MASK, node_to_dict
from meshlens.config_service import (MSG_CHANGED, MSG_NOT_BACK, ConfigError, ConfigService)
from meshlens.radio import MSG_ADMIN_UNAUTH, AdminError
from test_radio_manager import MY_ID, Env, FakeConnector

REMOTE = "!11111111"
REMOTE_NUM = 0x11111111
LOCAL_NUM = int(MY_ID[1:], 16)
PRIV = b"PRIVKEY-SECRET-0123456789abcdef"
CHAN_PSK = b"CHANPSK-SECRET-1"
WIFI, MQTT = "WIFISECRET-xyz", "MQTTSECRET-xyz"
SECRET_TEXTS = [PRIV, CHAN_PSK, WIFI.encode(), MQTT.encode()]


def make_protos() -> dict:
    cfg = localonly_pb2.LocalConfig()
    cfg.lora.region = config_pb2.Config.LoRaConfig.EU_868
    cfg.lora.hop_limit = 3
    cfg.security.private_key = PRIV
    cfg.security.public_key = b"PUBLIC-KEY-0123456789abcdef-----"
    cfg.network.wifi_psk = WIFI
    cfg.bluetooth.fixed_pin = 123456
    mod = localonly_pb2.LocalModuleConfig()
    mod.mqtt.password = MQTT
    ch = channel_pb2.Channel(index=0, role=channel_pb2.Channel.PRIMARY)
    ch.settings.name = "LongFast"
    ch.settings.psk = CHAN_PSK
    ch1 = channel_pb2.Channel(index=1, role=channel_pb2.Channel.SECONDARY)
    ch1.settings.name = "uno"
    return {"config": cfg, "module_config": mod, "channels": [ch, ch1],
            "owner": {"long_name": "Base", "short_name": "BS", "is_licensed": False}}


def secrets_in(text: str) -> list:
    """Segreti (in chiaro o base64) presenti nel testo."""
    found = []
    for s in SECRET_TEXTS:
        if s.decode() in text or base64.b64encode(s).decode() in text:
            found.append(s)
    return found


class CfgConnector(FakeConnector):
    """Connettore finto con le operazioni admin, su protobuf veri."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.nodes = {None: make_protos(), REMOTE_NUM: make_protos()}
        self.fresh_remote = set()  # nodi letti di recente (cache e chiave di sessione)
        self.reads = []
        self.writes = []
        self.read_error = None
        self.write_error = None
        self.drops = True  # la scrittura locale riavvia la radio
        self.back = True
        self.ignore_write = False
        self.timeouts = []
        self.rebooted = []
        self.fixed = []
        self.at_write = []
        self.store = None  # per controllare la copia prima della scrittura
        # WP4: flag del NodeDB, comandi admin, messaggi predefiniti
        self.flags = {}
        self.flag_calls = []
        self.busy = False
        self.commands = []
        self.canned = ""
        self.canned_calls = []

    def _dict(self, num):
        p = self.nodes[num]
        return node_to_dict(p["config"], p["module_config"], p["channels"], p["owner"])

    async def admin_public_key(self):
        return base64.b64encode(self.nodes[None]["config"].security.public_key).decode()

    async def read_local(self):
        if self.gate is not None:
            await self.gate.wait()
        self.reads.append(None)
        return self._dict(None)

    async def read_remote(self, node_num, sections, on_step):
        self.reads.append((node_num, sections))
        if self.read_error:
            raise self.read_error
        total = 3
        for i, text in enumerate(("Contatto il nodo", "Canali letti", "Letta la sezione")):
            on_step(text, i, total)
            await asyncio.sleep(0)
        self.fresh_remote.add(node_num)
        return self._dict(node_num)

    async def current_protos(self, node_num):
        if node_num is not None and node_num not in self.fresh_remote:
            raise AdminError("error", "Leggi di nuovo la configurazione del nodo")
        return copy.deepcopy(self.nodes[node_num])

    async def write(self, node_num, protos_changed, on_step):
        if self.write_error:
            raise self.write_error
        self.at_write.append(len(self.store.backups(node_num or LOCAL_NUM)))
        if node_num is not None and node_num not in self.fresh_remote:
            raise AdminError("error", "Leggi di nuovo")
        on_step("Scrivo", 1, 2)
        self.writes.append((node_num, protos_changed))
        if not self.ignore_write:
            self.nodes[node_num] = copy.deepcopy(protos_changed)
        if node_num is None and self.drops:
            self.state_name = "reconnecting"
        if node_num is not None:
            self.fresh_remote.discard(node_num)

    async def wait_reconnected(self, timeout=90):
        self.timeouts.append(timeout)
        if self.back and self.state_name != "connected":
            self.state_name = "connected"
            return True
        return False

    async def reboot(self, node_num, secs=5):
        self.rebooted.append(node_num)
        if node_num is None:
            self.state_name = "reconnecting"

    async def set_fixed_position(self, node_num, lat, lon, alt=0):
        self.fixed.append((node_num, lat, lon, alt))

    async def remove_fixed_position(self, node_num):
        self.fixed.append((node_num, None))

    def has_admin_session(self, node_num):
        return node_num in self.fresh_remote

    def node_flags(self, num):
        if self.state_name != "connected":
            return None
        return self.flags.get(num)

    async def set_node_flag(self, num, flag, value, wait=None):
        from meshlens.radio import RadioBusy
        if self.busy:
            raise RadioBusy()
        self.flag_calls.append((num, flag, value))
        self.flags.setdefault(num, {"favorite": False, "ignored": False, "muted": None})
        self.flags[num][flag] = value

    async def set_time(self, num, epoch):
        self.commands.append(("set_time", num, epoch))

    async def reset_nodedb(self, num):
        self.commands.append(("nodedb_reset", num))

    async def shutdown(self, num, secs=5):
        self.commands.append(("shutdown", num))

    async def get_canned(self, num, wait=None):
        from meshlens.radio import RadioBusy
        if self.busy:
            raise RadioBusy()
        return self.canned

    async def set_canned(self, num, text, wait=None):
        from meshlens.radio import RadioBusy
        if self.busy:
            raise RadioBusy()
        self.canned_calls.append((num, text))
        self.canned = text


async def nosleep(_s):
    await asyncio.sleep(0)


async def make_service():
    e = Env()
    e.mgr._connector_factory = CfgConnector
    await e.mgr.add("usb", "COM5", "H")
    conn = FakeConnector.instances[0]
    conn.store = e.store
    svc = ConfigService(e.store, e.mgr, e.live, e.bus, clock=lambda: e.now, sleep=nosleep)
    e.drain()
    return e, svc, conn


async def run(svc, job):
    await svc.join(job["id"])
    return svc.job(job["id"])


async def read_local(svc):
    return await run(svc, svc.start_read(MY_ID, None, None))


async def test_read_job_local_finishes_and_saves_read():
    e, svc, conn = await make_service()
    job = svc.start_read(MY_ID, None, None)
    assert job["status"] == "running" and job["kind"] == "read" and job["node_id"] == MY_ID
    done = await run(svc, job)
    assert done["status"] == "done" and done["result_id"] and done["ended"] is not None
    saved = svc.last_read(MY_ID)
    assert saved["id"] == done["result_id"] and saved["config"]["config"]["lora"]["hop_limit"] == 3
    assert saved["config"]["config"]["security"]["private_key"] == MASK
    assert "lora" in saved["sections"]


async def test_read_job_remote_progress_published():
    e, svc, conn = await make_service()
    job = svc.start_read(REMOTE, None, ["config.lora", "mqtt"])
    done = await run(svc, job)
    assert done["status"] == "done"
    assert conn.reads[-1] == (REMOTE_NUM, ["lora", "mqtt"])
    jobs = [m["job"] for m in e.drain() if m["type"] == "config_job"]
    seq = [j["progress"][0] for j in jobs if j["status"] == "running"]
    assert len(seq) >= 3 and seq == sorted(seq) and seq[-1] > seq[0]
    assert jobs[-1]["status"] == "done"


async def test_read_remote_unauthorized_fails_with_code():
    e, svc, conn = await make_service()
    conn.read_error = AdminError("unauthorized", MSG_ADMIN_UNAUTH)
    done = await run(svc, svc.start_read(REMOTE, None, None))
    assert done["status"] == "failed" and done["error"] == MSG_ADMIN_UNAUTH
    assert done["error_code"] == "unauthorized"


async def test_preview_requires_fresh_read():
    e, svc, conn = await make_service()
    with pytest.raises(ConfigError) as err:
        svc.preview(MY_ID, {"config.lora.hop_limit": 4})
    assert err.value.status == 409 and err.value.message == "Leggi prima la configurazione"
    await read_local(svc)
    assert svc.preview(MY_ID, {"config.lora.hop_limit": 4})["changes"][0]["new"] == 4
    e.now += 601
    with pytest.raises(ConfigError) as err:
        svc.preview(MY_ID, {"config.lora.hop_limit": 4})
    assert err.value.status == 409
    # sezione non letta: serve una nuova lettura
    e.now += 0
    await run(svc, svc.start_read(REMOTE, None, ["lora"]))
    with pytest.raises(ConfigError) as err:
        svc.preview(REMOTE, {"config.device.role": "ROUTER"})
    assert err.value.status == 409


async def test_apply_requires_confirm_risky():
    e, svc, conn = await make_service()
    await read_local(svc)
    pv = svc.preview(MY_ID, {"config.lora.region": "US"})
    assert pv["risky"] is True
    with pytest.raises(ConfigError) as err:
        svc.apply(MY_ID, pv["preview_id"], False)
    assert err.value.status == 400 and err.value.message == "Conferma richiesta per modifiche a rischio"
    assert conn.writes == []
    done = await run(svc, svc.apply(MY_ID, pv["preview_id"], True))  # l'anteprima resta valida
    assert done["status"] == "done" and len(conn.writes) == 1


async def test_apply_creates_backup_then_writes_then_verifies():
    e, svc, conn = await make_service()
    await read_local(svc)
    pv = svc.preview(MY_ID, {"config.lora.hop_limit": 5, "owner.long_name": "Nuovo"})
    assert pv["risky"] is False and pv["backup_sections"] == ["config.lora", "owner"]
    done = await run(svc, svc.apply(MY_ID, pv["preview_id"], False))
    assert done["status"] == "done" and done["verify"] == "verified"
    assert conn.at_write == [1]  # la copia c'era gia' al momento della scrittura
    (b,) = svc.backups(MY_ID)
    assert b["reason"] == "before_apply" and b["sections"] == ["config.lora", "owner"]
    raw = e.store.get_backup(b["id"])["data"]
    assert raw["config"]["lora"]["hop_limit"] == 3 and raw["owner"]["long_name"] == "Base"
    assert conn.timeouts[0] == 15
    assert svc.last_read(MY_ID)["id"] == done["result_id"]
    assert svc.last_read(MY_ID)["config"]["config"]["lora"]["hop_limit"] == 5
    # la copia contiene i segreti in chiaro solo nel database e solo per le sezioni toccate
    assert "security" not in raw["config"]


async def test_backup_unmasked_for_touched_secret_sections_but_masked_in_api_shape():
    e, svc, conn = await make_service()
    await read_local(svc)
    pv = svc.preview(MY_ID, {"config.network.wifi_psk": "NUOVAPSK", "channels.1.name": "due"})
    await run(svc, svc.apply(MY_ID, pv["preview_id"], False))
    (b,) = svc.backups(MY_ID)
    assert e.store.get_backup(b["id"])["data"]["config"]["network"]["wifi_psk"] == WIFI
    assert svc.backup(b["id"])["config"]["config"]["network"]["wifi_psk"] == MASK


async def test_apply_mismatch_when_radio_keeps_old_value():
    e, svc, conn = await make_service()
    await read_local(svc)
    conn.ignore_write = True
    pv = svc.preview(MY_ID, {"config.lora.hop_limit": 5})
    done = await run(svc, svc.apply(MY_ID, pv["preview_id"], False))
    assert done["status"] == "done" and done["verify"] == "mismatch"


async def test_preview_single_use_and_expiry():
    e, svc, conn = await make_service()
    await read_local(svc)
    pv = svc.preview(MY_ID, {"config.lora.hop_limit": 5})
    await run(svc, svc.apply(MY_ID, pv["preview_id"], False))
    with pytest.raises(ConfigError) as err:  # gia' usata
        svc.apply(MY_ID, pv["preview_id"], False)
    assert err.value.status == 400
    with pytest.raises(ConfigError) as err:  # sconosciuta
        svc.apply(MY_ID, "nope", False)
    assert err.value.status == 400
    pv = svc.preview(MY_ID, {"config.lora.hop_limit": 6})
    e.now += 601
    with pytest.raises(ConfigError) as err:  # scaduta
        svc.apply(MY_ID, pv["preview_id"], False)
    assert err.value.status == 400
    # lettura piu' recente: l'anteprima non e' piu' valida
    await read_local(svc)
    pv = svc.preview(MY_ID, {"config.lora.hop_limit": 6})
    await read_local(svc)
    with pytest.raises(ConfigError) as err:
        svc.apply(MY_ID, pv["preview_id"], False)
    assert err.value.status == 409
    assert len(conn.writes) == 1


async def test_restore_preview_from_backup():
    e, svc, conn = await make_service()
    await read_local(svc)
    pv = svc.preview(MY_ID, {"config.lora.hop_limit": 5})
    await run(svc, svc.apply(MY_ID, pv["preview_id"], False))
    (b,) = svc.backups(MY_ID)
    rp = svc.preview_restore(b["id"])
    (ch,) = rp["changes"]
    assert (ch["path"], ch["old"], ch["new"]) == ("config.lora.hop_limit", 5, 3)
    done = await run(svc, svc.apply(MY_ID, rp["preview_id"], False))
    assert done["verify"] == "verified"
    assert conn.nodes[None]["config"].lora.hop_limit == 3


async def test_restore_writes_back_secret_values():
    e, svc, conn = await make_service()
    await read_local(svc)
    pv = svc.preview(MY_ID, {"config.network.wifi_psk": "NUOVAPSK"})
    await run(svc, svc.apply(MY_ID, pv["preview_id"], False))
    (b,) = svc.backups(MY_ID)
    rp = svc.preview_restore(b["id"])
    assert rp["changes"][0]["new"] == MASK and WIFI not in str(rp)
    await run(svc, svc.apply(MY_ID, rp["preview_id"], False))
    assert conn.nodes[None]["config"].network.wifi_psk == WIFI


async def test_masked_secret_unchanged_is_not_written():
    e, svc, conn = await make_service()
    await read_local(svc)
    pv = svc.preview(MY_ID, {"config.network.wifi_psk": MASK, "config.lora.hop_limit": 4})
    assert [c["path"] for c in pv["changes"]] == ["config.lora.hop_limit"]
    await run(svc, svc.apply(MY_ID, pv["preview_id"], False))
    assert conn.nodes[None]["config"].network.wifi_psk == WIFI


async def test_local_reboot_not_back_fails_after_90s():
    e, svc, conn = await make_service()
    await read_local(svc)
    conn.back = False
    pv = svc.preview(MY_ID, {"config.lora.hop_limit": 5})
    done = await run(svc, svc.apply(MY_ID, pv["preview_id"], False))
    assert done["status"] == "failed" and done["error"] == MSG_NOT_BACK
    assert conn.timeouts == [15, 75]  # 90 s in tutto


async def test_local_write_without_reboot_rereads_directly():
    e, svc, conn = await make_service()
    await read_local(svc)
    conn.drops = False
    pv = svc.preview(MY_ID, {"owner.long_name": "Altro"})
    done = await run(svc, svc.apply(MY_ID, pv["preview_id"], False))
    # nessun riavvio rilevato: la rilettura non prova nulla, quindi nessuna verifica
    assert done["status"] == "done" and done["verify"] is None
    assert done["step"] == "Applicato (nessun riavvio rilevato)"
    assert conn.timeouts == [15]


async def test_local_apply_fails_when_config_changed_since_preview():
    e, svc, conn = await make_service()
    await read_local(svc)
    first = svc.preview(MY_ID, {"config.lora.hop_limit": 4})
    second = svc.preview(MY_ID, {"config.lora.hop_limit": 5})
    j1 = svc.apply(MY_ID, first["preview_id"], False)
    j2 = svc.apply(MY_ID, second["preview_id"], False)
    assert (await run(svc, j1))["status"] == "done"
    done = await run(svc, j2)
    assert done["status"] == "failed" and done["error"] == MSG_CHANGED
    assert conn.nodes[None]["config"].lora.hop_limit == 4


async def test_remote_apply_rereads_then_writes():
    e, svc, conn = await make_service()
    await run(svc, svc.start_read(REMOTE, None, None))
    e.now += 30
    pv = svc.preview(REMOTE, {"config.lora.hop_limit": 5})
    n_reads = len(conn.reads)
    done = await run(svc, svc.apply(REMOTE, pv["preview_id"], False))
    assert done["status"] == "done" and done["verify"] == "verified"
    assert conn.reads[n_reads][0] == REMOTE_NUM  # rilettura fresca prima di scrivere
    assert conn.writes[0][0] == REMOTE_NUM
    assert len(svc.backups(REMOTE)) == 1


async def test_remote_apply_fails_if_node_changed():
    e, svc, conn = await make_service()
    await run(svc, svc.start_read(REMOTE, None, None))
    pv = svc.preview(REMOTE, {"config.lora.hop_limit": 5})
    conn.nodes[REMOTE_NUM]["config"].lora.hop_limit = 7  # modificato da altri nel frattempo
    done = await run(svc, svc.apply(REMOTE, pv["preview_id"], False))
    assert done["status"] == "failed" and done["error"] == MSG_CHANGED
    assert conn.writes == [] and svc.backups(REMOTE) == []


async def test_remote_apply_unauthorized():
    e, svc, conn = await make_service()
    await run(svc, svc.start_read(REMOTE, None, None))
    pv = svc.preview(REMOTE, {"config.lora.hop_limit": 5})
    conn.write_error = AdminError("unauthorized", MSG_ADMIN_UNAUTH)
    done = await run(svc, svc.apply(REMOTE, pv["preview_id"], False))
    assert done["status"] == "failed" and done["error_code"] == "unauthorized"


async def test_reboot_and_fixed_position_jobs():
    e, svc, conn = await make_service()
    with pytest.raises(ConfigError) as err:
        svc.reboot(MY_ID, None, False)
    assert err.value.status == 400
    done = await run(svc, svc.reboot(MY_ID, None, True))
    assert done["status"] == "done" and conn.rebooted == [None]
    done = await run(svc, svc.reboot(REMOTE, None, True))
    assert conn.rebooted == [None, REMOTE_NUM] and done["kind"] == "reboot"
    done = await run(svc, svc.fixed_position(MY_ID, None, True, 45.5, 9.1, 120))
    assert done["kind"] == "fixed_position" and conn.fixed == [(None, 45.5, 9.1, 120)]
    await run(svc, svc.fixed_position(MY_ID, None, True, remove=True))
    assert conn.fixed[-1] == (None, None)
    with pytest.raises(ConfigError):
        svc.fixed_position(MY_ID, None, True, 95, 9)


async def test_jobs_serialized_per_radio():
    e, svc, conn = await make_service()
    conn.gate = asyncio.Event()
    j1, j2 = svc.start_read(MY_ID, None, None), svc.start_read(MY_ID, None, None)
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(conn.reads) == 0 and svc.job(j2["id"])["step"] == "In coda"
    conn.gate.set()
    await svc.join(j1["id"])
    await svc.join(j2["id"])
    assert svc.job(j1["id"])["status"] == svc.job(j2["id"])["status"] == "done"


async def test_running_jobs_failed_on_restart():
    e, svc, conn = await make_service()
    jid = e.store.add_job(node_num=LOCAL_NUM, radio_id="r", kind="read", status="running",
                          step="x", done=0, total=1, started=1.0)
    e.store.commit()
    ConfigService(e.store, e.mgr, e.live, e.bus, clock=lambda: e.now)
    assert e.store.get_job(jid)["status"] == "failed"


async def test_reveal_psk_and_admin_key():
    e, svc, conn = await make_service()
    out = await svc.reveal_psk(MY_ID, 0)
    assert base64.b64decode(out["psk"]) == CHAN_PSK
    with pytest.raises(ConfigError) as err:
        await svc.reveal_psk(MY_ID, 5)
    assert err.value.status == 404
    key = await svc.admin_key(e.mgr.radios()[0]["id"])
    assert base64.b64decode(key["public_key_b64"]) == b"PUBLIC-KEY-0123456789abcdef-----"


async def test_channel_secrets_from_local_radio():
    e, svc, conn = await make_service()
    conn.nodes[None]["channels"][0].settings.name = ""  # primario senza nome
    off = channel_pb2.Channel(index=2, role=channel_pb2.Channel.DISABLED)
    off.settings.name = "spento"
    conn.nodes[None]["channels"].append(off)
    out = await svc.channel_secrets(e.mgr.radios()[0]["id"])
    assert [c["name"] for c in out] == ["LongFast", "uno"]
    assert base64.b64decode(out[0]["psk"]) == CHAN_PSK
    conn.state_name = "reconnecting"
    with pytest.raises(ConfigError) as err:
        await svc.channel_secrets(e.mgr.radios()[0]["id"])
    assert err.value.status == 409 and err.value.message == "Radio non collegata"
    with pytest.raises(ConfigError) as err:
        await svc.channel_secrets("rnope")
    assert err.value.status == 404


# ---- WP4: comandi admin, canned, flag radio, anteprime esterne, privacy, canali ----

from meshlens.config_service import ADMIN_COMMANDS, MSG_REMOTE_READ_SECURITY  # noqa: E402

ERRORS: list = []  # ConfigError visti dai test WP4 (nessun segreto nei messaggi)


def _err(excinfo):
    ERRORS.append(excinfo.value.message)
    return excinfo.value


async def test_admin_command_requires_confirm_and_known_command():
    e, svc, conn = await make_service()
    with pytest.raises(ConfigError) as ei:
        await svc.admin_command(MY_ID, None, "set_time", False)
    assert _err(ei).status == 400 and ei.value.message == "Conferma richiesta"
    with pytest.raises(ConfigError) as ei:
        await svc.admin_command(MY_ID, None, "factory_reset", True)
    assert _err(ei).status == 400 and ei.value.message == "Comando sconosciuto"
    assert e.store.conn.execute("SELECT COUNT(*) FROM config_jobs").fetchone()[0] == 0


async def test_admin_command_local_jobs():
    e, svc, conn = await make_service()
    assert ADMIN_COMMANDS == ("reboot", "set_time", "nodedb_reset", "shutdown")
    for cmd in ADMIN_COMMANDS:
        job = await svc.admin_command(MY_ID, None, cmd, True)
        assert job["kind"] == cmd
        done = await run(svc, job)
        assert done["status"] == "done", (cmd, done)
    assert ("set_time", None, int(e.now)) in conn.commands
    assert ("nodedb_reset", None) in conn.commands
    assert ("shutdown", None) in conn.commands
    assert conn.rebooted == [None]
    assert svc.job(job["id"])["step"] == "Fatto: la radio è spenta"


async def test_admin_command_remote_requires_admin_key():
    e, svc, conn = await make_service()
    with pytest.raises(ConfigError) as ei:
        await svc.admin_command(REMOTE, None, "set_time", True)
    assert _err(ei).status == 409 and ei.value.message == MSG_REMOTE_READ_SECURITY
    await run(svc, svc.start_read(REMOTE, None, None))
    with pytest.raises(ConfigError) as ei:
        await svc.admin_command(REMOTE, None, "set_time", True)
    assert _err(ei).status == 409 and ei.value.message == MSG_ADMIN_UNAUTH
    assert conn.commands == []
    conn.nodes[REMOTE_NUM]["config"].security.admin_key.append(
        conn.nodes[None]["config"].security.public_key)
    await run(svc, svc.start_read(REMOTE, None, ["security"]))
    done = await run(svc, await svc.admin_command(REMOTE, None, "set_time", True))
    assert done["status"] == "done"
    assert conn.commands == [("set_time", REMOTE_NUM, int(e.now))]


async def test_admin_status_shapes():
    e, svc, conn = await make_service()
    key = base64.b64encode(conn.nodes[None]["config"].security.public_key).decode()
    st = await svc.admin_status(MY_ID, None)
    assert st["local"] is True and st["authorized"] is True and st["reason"] is None
    assert st["node_id"] == MY_ID and st["radio_id"] == e.mgr.radios()[0]["id"]
    assert st["radio_public_key"] == key
    st = await svc.admin_status(REMOTE, None)
    assert st["local"] is False and st["authorized"] is None
    assert st["reason"] == MSG_REMOTE_READ_SECURITY and st["read_time"] is None
    assert st["radio_public_key"] == key
    await run(svc, svc.start_read(REMOTE, None, ["config.lora"]))  # senza Sicurezza
    assert (await svc.admin_status(REMOTE, None))["authorized"] is None
    await run(svc, svc.start_read(REMOTE, None, ["security"]))
    st = await svc.admin_status(REMOTE, None)
    assert st["authorized"] is False and st["reason"] == MSG_ADMIN_UNAUTH
    assert st["read_time"] == e.now


async def test_get_set_canned():
    e, svc, conn = await make_service()
    conn.canned = "Ciao|OK"
    assert await svc.get_canned(MY_ID, None) == {"messages": ["Ciao", "OK"], "bytes": 7,
                                                 "max_bytes": 200}
    out = await svc.set_canned(MY_ID, None, ["A", "B"])
    assert conn.canned_calls == [(None, "A|B")] and out["messages"] == ["A", "B"]
    with pytest.raises(ConfigError) as ei:
        await svc.set_canned(MY_ID, None, ["a|b"])
    assert _err(ei).status == 400 and conn.canned_calls == [(None, "A|B")]
    with pytest.raises(ConfigError) as ei:
        await svc.set_canned(MY_ID, None, [])
    assert _err(ei).status == 400
    conn.busy = True
    for coro in (svc.get_canned(MY_ID, None), svc.set_canned(MY_ID, None, ["x"])):
        with pytest.raises(ConfigError) as ei:
            await coro
        assert _err(ei).status == 409 and ei.value.message == "Radio occupata, riprova tra poco"
    conn.busy = False
    with pytest.raises(ConfigError) as ei:
        await svc.set_canned(REMOTE, None, ["x"])  # remoto senza la nostra chiave
    assert _err(ei).status == 409


async def test_canned_admin_error_is_409():
    e, svc, conn = await make_service()

    async def no_canned(num, wait=None):
        raise AdminError("error", "Il firmware di questa radio non include i messaggi predefiniti")
    conn.get_canned = no_canned
    with pytest.raises(ConfigError) as ei:
        await svc.get_canned(MY_ID, None)
    assert _err(ei).status == 409 and "messaggi predefiniti" in ei.value.message


async def test_set_radio_flags_reports_per_radio():
    e, svc, conn = await make_service()
    assert await svc.set_radio_flags("!00000042", favorite=True) == [
        {"radio_id": e.mgr.radios()[0]["id"], "ok": True, "error": None}]
    await e.mgr.add("tcp", "10.0.0.2", "T")
    conn2 = FakeConnector.instances[1]
    conn2.busy = True
    r1, r2 = e.mgr.radios()[0]["id"], e.mgr.radios()[1]["id"]
    out = await svc.set_radio_flags("!00000042", ignored=True)
    assert out == [{"radio_id": r1, "ok": True, "error": None},
                   {"radio_id": r2, "ok": False, "error": "Radio occupata, riprova tra poco"}]
    assert conn.flag_calls[-1] == (0x42, "ignored", True)
    out = await svc.set_radio_flags("!00000042", favorite=False, radio_ids=[r1])
    assert [o["radio_id"] for o in out] == [r1]
    conn.state_name = "disconnected"
    conn2.state_name = "disconnected"
    assert await svc.set_radio_flags("!00000042", favorite=True) == []


async def test_set_radio_flags_value_error_is_reported():
    e, svc, conn = await make_service()

    async def own(num, flag, value, wait=None):
        raise ValueError("Non si può marcare il nodo della radio stessa")
    conn.set_node_flag = own
    out = await svc.set_radio_flags(MY_ID, favorite=True)
    assert out[0]["ok"] is False and out[0]["error"] == "Non si può marcare il nodo della radio stessa"


async def test_radio_flags_lists_known_only():
    e, svc, conn = await make_service()
    conn.flags = {0x42: {"favorite": True, "ignored": False, "muted": None}}
    out = svc.radio_flags("!00000042")
    assert out == [{"radio_id": e.mgr.radios()[0]["id"], "radio_name": "H", "favorite": True,
                    "ignored": False, "muted": None}]
    assert svc.radio_flags("!00000099") == []


async def test_preview_from_profile_changes_uses_existing_flow():
    e, svc, conn = await make_service()
    with pytest.raises(ConfigError) as ei:
        svc.preview_changes(MY_ID, {"config.lora.hop_limit": 5})
    assert _err(ei).status == 409
    await read_local(svc)
    pv = svc.preview_changes(MY_ID, {"config.lora.hop_limit": 5})
    assert [c["path"] for c in pv["changes"]] == ["config.lora.hop_limit"]
    done = await run(svc, svc.apply(MY_ID, pv["preview_id"], confirm_risky=True))
    assert done["status"] == "done"
    assert conn.writes[-1][1]["config"].lora.hop_limit == 5
    assert conn.at_write == [1]  # copia di sicurezza salvata prima della scrittura
    with pytest.raises(ConfigError) as ei:
        svc.preview_changes(MY_ID, {})
    assert _err(ei).status == 400


def _privacy_protos(conn):
    from meshtastic.protobuf import config_pb2
    p = conn.nodes[None]
    p["channels"][0].settings.psk = b"\x01"
    p["channels"][0].settings.module_settings.position_precision = 32
    p["config"].position.gps_mode = config_pb2.Config.PositionConfig.ENABLED


async def test_privacy_report_and_preview():
    e, svc, conn = await make_service()
    assert (await svc.privacy_report())[0]["risks"] == []  # precisione 0: nessun rischio
    _privacy_protos(conn)
    rep = await svc.privacy_report()
    assert len(rep) == 1 and rep[0]["node_id"] == MY_ID and rep[0]["name"] == "H"
    assert rep[0]["error"] is None and rep[0]["risks"][0]["reasons"] == ["public_key"]
    with pytest.raises(ConfigError) as ei:
        await svc.privacy_preview(MY_ID, 13, None)
    assert _err(ei).status == 409 and ei.value.message == "Leggi prima la configurazione"
    await read_local(svc)
    pv = await svc.privacy_preview(MY_ID, 13, None)
    assert pv["changes"] == [{"path": "channels.0.position_precision", "old": 32, "new": 13,
                              "risky": True, "reason": pv["changes"][0]["reason"]}]
    with pytest.raises(ConfigError) as ei:
        await svc.privacy_preview(MY_ID, 20, None)
    assert _err(ei).status == 400
    with pytest.raises(ConfigError) as ei:
        await svc.privacy_preview(REMOTE, 13, None)
    assert _err(ei).status == 409


async def test_privacy_report_radio_error():
    e, svc, conn = await make_service()

    async def broken(num):
        raise AdminError("error", "Radio non connessa")
    conn.current_protos = broken
    rep = await svc.privacy_report()
    assert rep[0]["risks"] == [] and rep[0]["error"] == "Radio non connessa"


async def test_export_channels_local_and_errors():
    from meshlens.channel_link import parse_channel_url
    e, svc, conn = await make_service()
    out = await svc.export_channels(MY_ID, None, False)
    assert out["url"].startswith("https://meshtastic.org/e/#")
    assert parse_channel_url(out["url"])[0]["psk"] == base64.b64encode(CHAN_PSK).decode()
    assert out["channels"] == [{"index": 0, "name": "LongFast"}, {"index": 1, "name": "uno"}]
    add = await svc.export_channels(MY_ID, [1], True)
    assert add["url"].startswith("https://meshtastic.org/e/?add=true#")
    assert add["channels"] == [{"index": 1, "name": "uno"}]
    with pytest.raises(ConfigError) as ei:
        await svc.export_channels(MY_ID, [5], False)
    assert _err(ei).status == 400
    with pytest.raises(ConfigError) as ei:
        await svc.export_channels(REMOTE, None, False)
    assert _err(ei).status == 409


async def test_no_secrets_in_service_errors():
    assert ERRORS, "i test WP4 precedenti devono aver raccolto errori"
    for msg in ERRORS:
        assert secrets_in(msg) == [], msg
