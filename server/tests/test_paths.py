import sys
from pathlib import Path

import httpx
from httpx import ASGITransport

from meshlens import __version__, paths
from meshlens.api import create_app
from test_api import make_ctx
from test_maps import make_manager


def test_default_data_dir_frozen_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.is_frozen()
    assert paths.default_data_dir() == tmp_path / "MeshLens" / "data"
    assert paths.updates_dir() == tmp_path / "MeshLens" / "updates"


def test_default_data_dir_dev_is_repo_data(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert not paths.is_frozen()
    assert paths.default_data_dir() == paths.app_dir() / "data"
    assert (paths.app_dir() / "server" / "meshlens").is_dir()


def test_bundled_tool_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "app_dir", lambda: tmp_path)
    assert paths.bundled_tool() is None
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "pmtiles.exe").write_bytes(b"MZ")
    assert paths.bundled_tool() == tmp_path / "tools" / "pmtiles.exe"


def test_bundled_tool_used_by_maps(monkeypatch, tmp_path):
    exe = tmp_path / "app" / "tools" / "pmtiles.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ-bundled")
    monkeypatch.setattr(paths, "bundled_tool", lambda: exe)
    mgr = make_manager(tmp_path / "data")
    assert mgr.tool_path == exe
    st = mgr.status()
    assert st["tool"]["installed"] is True


async def test_version_route():
    ctx = make_ctx()
    app = create_app(ctx)
    async with httpx.AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 1)),
                                 base_url="http://127.0.0.1") as c:
        assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
        r = await c.get("/api/version")
        assert r.status_code == 200
        j = r.json()
        assert j["version"] == __version__ == "1.1.0"
        assert j["frozen"] is False
        assert isinstance(j["data_dir"], str)
