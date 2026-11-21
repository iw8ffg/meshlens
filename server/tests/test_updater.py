import hashlib
import json
import logging

import pytest

from meshlens import updater as up
from meshlens.bus import Bus
from meshlens.settings import DEFAULTS
from meshlens.updater import NetworkError, Updater, is_newer, parse_version

TOKEN = "ghp_SEGRETISSIMO123"
EXE = b"MZ" + b"x" * 5000
SHA = hashlib.sha256(EXE).hexdigest()


def release(tag="v1.0.1"):
    v = tag.lstrip("v")
    return {"tag_name": tag, "body": "Novità", "published_at": "2026-11-01T10:00:00Z",
            "assets": [
                {"name": f"MeshLens-Setup-{v}.exe", "url": "https://api.github.com/a/1"},
                {"name": f"MeshLens-Setup-{v}.exe.sha256", "url": "https://api.github.com/a/2"}]}


class FakeHttp:
    def __init__(self, rel=None, status=200, sha_text=None, exe=EXE, offline=False):
        self.rel, self.status, self.exe, self.offline = rel or release(), status, exe, offline
        self.sha_text = sha_text if sha_text is not None else f"{SHA}  MeshLens-Setup-1.0.1.exe\n"
        self.calls = []

    def get(self, url, headers, max_bytes=5_000_000):
        self.calls.append((url, dict(headers)))
        if self.offline:
            raise NetworkError("Nessuna connessione")
        if url.endswith("/a/2"):
            return 200, self.sha_text.encode()
        return self.status, json.dumps(self.rel).encode()

    def download(self, url, headers, dest, progress):
        self.calls.append((url, dict(headers)))
        dest.write_bytes(self.exe)
        progress(len(self.exe), len(self.exe))
        return 200


def make(tmp_path, http=None, token=TOKEN, frozen=True, clock=lambda: 1000.0, **kw):
    st = {**DEFAULTS, "update_token": token}
    exits, launched = [], []
    u = Updater(lambda: st, Bus(), http or FakeHttp(), clock=clock, frozen=frozen,
                updates_dir=tmp_path / "updates", launcher_exit=exits.append,
                launcher=launched.append, current="1.0.0", progress_interval=0.01, **kw)
    u.exits, u.launched, u.settings_dict = exits, launched, st
    return u


def test_parse_and_newer():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.0.0-beta") is None
    assert parse_version("boh") is None
    assert is_newer("1.0.1", "1.0.0") and is_newer("v1.10.0", "1.9.9")
    assert not is_newer("1.0.0", "1.0.0")
    assert not is_newer("1.0.1-beta", "1.0.0")


async def test_check_finds_update_and_uses_token(tmp_path):
    http = FakeHttp()
    u = make(tmp_path, http)
    s = await u.check()
    assert s["available"] and s["latest"] == "1.0.1" and s["notes"] == "Novità"
    assert s["error"] is None and s["checked_at"] == 1000.0 and s["can_install"] is False
    url, headers = http.calls[0]
    assert url == "https://api.github.com/repos/iw8ffg/meshlens/releases/latest"
    assert headers["Authorization"] == f"Bearer {TOKEN}"


async def test_check_prerelease_ignored(tmp_path):
    u = make(tmp_path, FakeHttp(rel=release("v1.1.0-beta")))
    s = await u.check()
    assert s["latest"] is None and not s["available"] and s["error"] is None


async def test_check_private_repo_message(tmp_path):
    for token in ("", "sbagliato"):
        u = make(tmp_path, FakeHttp(status=404), token=token)
        s = await u.check()
        assert s["error"] == up.PRIVATE_MSG and not s["available"]
    assert "Repository privato" in up.PRIVATE_MSG


async def test_check_offline(tmp_path):
    s = await make(tmp_path, FakeHttp(offline=True)).check()
    assert s["error"] == "Nessuna connessione"


async def test_token_never_in_status_or_logs(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    u = make(tmp_path)
    msgs = []
    q = u.bus.subscribe()
    await u.check()
    await u.start_download()
    await u._task
    while not q.empty():
        msgs.append(q.get_nowait())
    u2 = make(tmp_path, FakeHttp(status=404))
    await u2.check()
    blob = json.dumps([u.status(), u2.status(), msgs]) + caplog.text
    assert TOKEN not in blob


async def test_download_ok_then_ready(tmp_path):
    u = make(tmp_path)
    await u.check()
    q = u.bus.subscribe()
    job = await u.start_download()
    assert job["status"] == "running"
    await u._task
    st = u.status()
    assert st["job"]["status"] == "done" and st["job"]["bytes_done"] == len(EXE)
    assert st["can_install"] is True
    d = tmp_path / "updates"
    assert (d / "MeshLens-Setup-1.0.1.exe").read_bytes() == EXE
    assert not list(d.glob("*.tmp"))
    types = []
    while not q.empty():
        types.append(q.get_nowait()["type"])
    assert set(types) == {"update_job"}


async def test_download_bad_sha_deleted(tmp_path):
    u = make(tmp_path, FakeHttp(exe=EXE + b"manomesso"))
    await u.check()
    await u.start_download()
    await u._task
    assert u.status()["job"]["status"] == "failed"
    assert "SHA-256" in u.status()["job"]["error"]
    assert list((tmp_path / "updates").iterdir()) == []
    assert u.status()["can_install"] is False


async def test_download_interrupted_leaves_nothing(tmp_path):
    class Boom(FakeHttp):
        def download(self, url, headers, dest, progress):
            dest.write_bytes(b"parziale")
            raise NetworkError("Nessuna connessione")
    u = make(tmp_path, Boom())
    await u.check()
    await u.start_download()
    await u._task
    assert u.status()["job"]["status"] == "failed"
    assert list((tmp_path / "updates").iterdir()) == []


async def test_download_rejects_when_nothing_to_download(tmp_path):
    u = make(tmp_path)
    with pytest.raises(up.UpdateError) as e:
        await u.start_download()
    assert e.value.status == 409


async def test_install_requires_confirm_and_frozen(tmp_path):
    u = make(tmp_path, frozen=False)
    await u.check()
    await u.start_download()
    await u._task
    with pytest.raises(up.UpdateError) as e:
        await u.install(False)
    assert e.value.status == 400
    with pytest.raises(up.UpdateError) as e:
        await u.install(True)
    assert e.value.status == 409 and str(e.value) == "Disponibile solo nella versione installata"
    assert u.launched == []
    f = make(tmp_path)  # installata ma niente file scaricato
    await f.check()
    f.updates_dir = tmp_path / "vuota"
    with pytest.raises(up.UpdateError) as e:
        await f.install(True)
    assert e.value.status == 409


async def test_install_launches_detached_and_requests_exit(tmp_path):
    u = make(tmp_path)
    await u.check()
    await u.start_download()
    await u._task
    assert await u.install(True) == {"ok": True}
    argv = u.launched[0]
    assert argv[0].endswith("MeshLens-Setup-1.0.1.exe")
    assert argv[1:] == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
    assert u.exits == [2.0]


async def test_install_reverifies_and_refuses_tampered_file(tmp_path):
    u = make(tmp_path)
    await u.check()
    await u.start_download()
    await u._task
    (tmp_path / "updates" / "MeshLens-Setup-1.0.1.exe").write_bytes(b"altro")
    with pytest.raises(up.UpdateError):
        await u.install(True)
    assert u.launched == [] and u.exits == []
    assert not (tmp_path / "updates" / "MeshLens-Setup-1.0.1.exe").exists()


async def test_auto_check_daily(tmp_path):
    now = [1000.0]
    http = FakeHttp()
    u = make(tmp_path, http, clock=lambda: now[0])
    await u.tick()
    n = len(http.calls)
    assert n == 1
    now[0] += 3600
    await u.tick()
    assert len(http.calls) == n
    now[0] += 24 * 3600
    await u.tick()
    assert len(http.calls) == n + 1
    u.settings_dict["update_auto_check"] = False
    now[0] += 48 * 3600
    await u.tick()
    assert len(http.calls) == n + 1


# ---- UrllibHttp: redirect manuali, token non propagato ----
class Resp:
    def __init__(self, status, headers=None, body=b""):
        import io
        self.status, self.headers, self._b = status, headers or {}, io.BytesIO(body)

    def read(self, n=-1):
        return self._b.read(n)

    def close(self):
        pass


def scripted(responses, seen):
    h = up.UrllibHttp()

    def once(url, headers):
        seen.append((url, dict(headers)))
        return responses.pop(0)
    h._open_once = once
    return h


def test_redirect_drops_auth_on_other_host():
    seen = []
    h = scripted([Resp(302, {"Location": "https://objects.githubusercontent.com/x"}),
                  Resp(200, {}, b"ok")], seen)
    status, body = h.get("https://api.github.com/a/1", {"Authorization": "Bearer t", "Accept": "x"})
    assert status == 200 and body == b"ok"
    assert seen[0][1]["Authorization"] == "Bearer t"
    assert "Authorization" not in seen[1][1] and seen[1][1]["Accept"] == "x"


def test_redirect_rejects_http_and_loops():
    h = scripted([Resp(302, {"Location": "http://evil.example/x"})], [])
    with pytest.raises(up.UpdateError):
        h.get("https://api.github.com/a", {})
    loop = [Resp(302, {"Location": "https://api.github.com/b"}) for _ in range(10)]
    with pytest.raises(up.UpdateError):
        scripted(loop, []).get("https://api.github.com/a", {})


# ---- hardening (round 1) ----
async def test_assets_on_other_hosts_ignored(tmp_path):
    rel = release()
    rel["assets"][0]["url"] = "https://evil.example/a/1"
    u = make(tmp_path, FakeHttp(rel=rel))
    await u.check()
    with pytest.raises(up.UpdateError) as e:
        await u.start_download()
    assert e.value.status == 502


async def _ready(tmp_path, **kw):
    u = make(tmp_path, **kw)
    await u.check()
    await u.start_download()
    await u._task
    return u


async def test_install_empty_sidecar_is_bad_hash(tmp_path):
    u = await _ready(tmp_path)
    (tmp_path / "updates" / "MeshLens-Setup-1.0.1.exe.sha256").write_text("")
    with pytest.raises(up.UpdateError) as e:
        await u.install(True)
    assert e.value.status == 409 and u.launched == []


async def test_install_compares_with_memory_sha(tmp_path):
    u = await _ready(tmp_path)
    other = b"altro"
    d = tmp_path / "updates"
    (d / "MeshLens-Setup-1.0.1.exe").write_bytes(other)  # file e sidecar coerenti tra loro, ma non col download
    (d / "MeshLens-Setup-1.0.1.exe.sha256").write_text(hashlib.sha256(other).hexdigest() + "  x\n")
    with pytest.raises(up.UpdateError):
        await u.install(True)
    assert u.launched == []


async def test_install_twice_and_during_download(tmp_path):
    u = await _ready(tmp_path)
    assert (await u.install(True)) == {"ok": True}
    with pytest.raises(up.UpdateError) as e:
        await u.install(True)
    assert e.value.status == 409 and len(u.launched) == 1
    v = make(tmp_path / "b")
    await v.check()
    await v.start_download()
    with pytest.raises(up.UpdateError) as e:
        await v.install(True)
    assert e.value.status == 409
    await v._task


async def test_auto_check_retries_after_network_error(tmp_path):
    now = [1000.0]
    http = FakeHttp(offline=True)
    u = make(tmp_path, http, clock=lambda: now[0])
    await u.tick()
    assert len(http.calls) == 1
    now[0] += 1800
    await u.tick()
    assert len(http.calls) == 1
    now[0] += 3600
    await u.tick()
    assert len(http.calls) == 2  # ritenta dopo ~1 h, non dopo 24 h


async def test_download_size_cap_and_mismatch(tmp_path):
    rel = release()
    rel["assets"][0]["size"] = len(EXE) + 1
    u = make(tmp_path, FakeHttp(rel=rel))
    await u.check()
    await u.start_download()
    await u._task
    assert u.status()["job"]["status"] == "failed"
    assert list((tmp_path / "updates").iterdir()) == []
    rel = release()
    rel["assets"][0]["size"] = up.MAX_DOWNLOAD_BYTES + 1
    u = make(tmp_path / "c", FakeHttp(rel=rel))
    await u.check()
    with pytest.raises(up.UpdateError):
        await u.start_download()


def test_status_has_frozen(tmp_path):
    assert make(tmp_path, frozen=True).status()["frozen"] is True
    assert make(tmp_path, frozen=False).status()["frozen"] is False


def test_cleanup_removes_old_installers(tmp_path):
    u = make(tmp_path)
    d = tmp_path / "updates"
    d.mkdir()
    old = ["MeshLens-Setup-0.9.0.exe", "MeshLens-Setup-0.9.0.exe.sha256",
           "MeshLens-Setup-1.0.0.exe", "MeshLens-Setup-1.0.0.exe.sha256", "x.tmp"]
    new = ["MeshLens-Setup-1.0.1.exe", "MeshLens-Setup-1.0.1.exe.sha256", "altro.txt"]
    for n in old + new:
        (d / n).write_bytes(b"x")
    u.cleanup_tmp()
    assert sorted(p.name for p in d.iterdir()) == sorted(new)


def test_wait_then_run_command_waits_for_pid_and_quotes():
    from meshlens.updater import wait_then_run_command
    cmd = wait_then_run_command(1234, [r"C:\Users\O'Brien\updates\MeshLens-Setup-1.0.2.exe", "/VERYSILENT", "/NORESTART"])
    assert cmd[0] == "powershell.exe" and "-Command" in cmd
    script = cmd[-1]
    assert script.startswith("Wait-Process -Id 1234 ")
    assert r"'C:\Users\O''Brien\updates\MeshLens-Setup-1.0.2.exe'" in script
    assert "-ArgumentList '/VERYSILENT','/NORESTART'" in script
    assert script.index("Wait-Process") < script.index("Start-Process")
