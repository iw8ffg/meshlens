import asyncio
import hashlib
import io
import json
import zipfile
from datetime import date, datetime, timezone

import pytest

from meshlens import maps
from meshlens.bus import Bus
from meshlens.maps import (ITALY_BBOX, MapsError, MapsManager, estimate_bytes, find_source,
                           validate_bbox)
from meshlens.settings import DEFAULTS, load_settings, save_settings

GB = 1_000_000_000
TODAY = date(2026, 11, 21)
NOW = datetime(2026, 11, 21, 12, tzinfo=timezone.utc).timestamp()
SRC = "https://build.protomaps.com/20261121.pmtiles"


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("LICENSE", "x")
        z.writestr("pmtiles.exe", b"MZ-fake")
    return buf.getvalue()


def good_downloader(url, dest, progress):
    data = make_zip()
    dest.write_bytes(data)
    progress(len(data), len(data))


def fake_head_ok(url):
    return 200


class FakeRunner:
    """Scrive il .tmp (argv[3]) e termina; con hang=True resta in attesa fino alla cancellazione."""

    def __init__(self, hang=False, rc=0, write=b"PMTILES-DATA"):
        self.hang, self.rc, self.write = hang, rc, write
        self.calls, self.started, self.killed = [], asyncio.Event(), False

    async def __call__(self, argv, on_output):
        self.calls.append(argv)
        with open(argv[3], "wb") as f:
            f.write(self.write)
        on_output("50% |#####     |")
        self.started.set()
        if self.hang:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                self.killed = True  # come il runner vero: uccide il processo
                raise
        return self.rc


def make_manager(tmp_path, runner=None, downloader=good_downloader, head=fake_head_ok,
                 disk_free=lambda p: 100 * GB, install_tool=False, sha=None, settings=None):
    if sha is None:
        sha = hashlib.sha256(make_zip()).hexdigest()
    st = settings if settings is not None else dict(DEFAULTS)
    mgr = MapsManager(tmp_path, lambda: st, Bus(), runner=runner or FakeRunner(),
                      downloader=downloader, clock=lambda: NOW, head=head,
                      disk_free=disk_free, tool_sha256=sha, progress_interval=0.05)
    if install_tool:
        (tmp_path / "tools").mkdir(parents=True, exist_ok=True)
        (tmp_path / "tools" / "pmtiles.exe").write_bytes(b"MZ")
    return mgr


async def wait_done(mgr):
    await mgr._task
    return mgr.status()["job"]


def test_tool_constants_pinned():
    assert maps.TOOL_VERSION == "1.31.2"
    assert maps.TOOL_URL.startswith("https://github.com/protomaps/go-pmtiles/releases/download/")
    assert maps.TOOL_URL.endswith("Windows_x86_64.zip")
    assert len(maps.TOOL_SHA256) == 64


def test_find_source_walks_back_7_days():
    asked = []

    def head(url):
        asked.append(url)
        return 200 if url.endswith("20261118.pmtiles") else 404

    url, d = find_source(head, TODAY, None)
    assert (url, d) == ("https://build.protomaps.com/20261118.pmtiles", "20261118")
    assert len(asked) == 4
    with pytest.raises(MapsError) as e:
        find_source(lambda u: 404, TODAY, None)
    assert e.value.status == 502
    assert "ultimi 7 giorni" in str(e.value)
    called = []
    assert find_source(called.append, TODAY, "https://x.example/a.pmtiles") == (
        "https://x.example/a.pmtiles", None)
    assert called == []  # URL personalizzato: nessun HEAD


def test_estimate_and_bbox_validation():
    assert estimate_bytes("italy", None) == 2 * GB
    assert estimate_bytes("world", None) == 200_000_000
    half = [6.6, 36.6, 12.6, 47.1]
    assert abs(estimate_bytes("area", half) - 1 * GB) < 0.05 * GB
    assert estimate_bytes("area", [10, 40, 10.01, 40.01]) == 50_000_000
    assert validate_bbox(ITALY_BBOX) == ITALY_BBOX
    for bad in ([10, 40, 5, 41], [10, 40, 11, 40], [-181, 0, 0, 1], [0, -86, 1, 0],
                [0, 0, 41, 1], [0, 0, 1, 41], [1, 2, 3], None, ["a", 0, 1, 1]):
        with pytest.raises(MapsError) as e:
            validate_bbox(bad)
        assert e.value.status == 400


async def test_tool_bad_checksum_rejected(tmp_path):
    def bad_downloader(url, dest, progress):
        dest.write_bytes(b"non e lo zip giusto")

    runner = FakeRunner()
    mgr = make_manager(tmp_path, runner=runner, downloader=bad_downloader)
    await mgr.start("tool", None, None)
    job = await wait_done(mgr)
    assert job["status"] == "failed"
    assert job["error"] == "Impronta del file non valida: download annullato"
    assert list((tmp_path / "tools").iterdir()) == []
    assert runner.calls == []


async def test_tool_install_and_extract_success(tmp_path):
    runner = FakeRunner()
    mgr = make_manager(tmp_path, runner=runner)
    job = await mgr.start("italy", None, None)
    assert job["kind"] == "tool"  # primo passo: strumento mancante
    job = await wait_done(mgr)
    assert job["status"] == "done", job
    assert (tmp_path / "tools" / "pmtiles.exe").read_bytes() == b"MZ-fake"
    assert [p.name for p in (tmp_path / "tools").iterdir()] == ["pmtiles.exe"]
    argv = runner.calls[0]
    assert argv[1] == "extract" and argv[2] == SRC and argv[3].endswith(".tmp")
    assert "--bbox=6.6,36.6,18.6,47.1" in argv and "--maxzoom=14" in argv
    assert "--download-threads=4" in argv
    st = mgr.status()
    assert st["tool"]["installed"] and st["tool"]["version"] == maps.TOOL_VERSION
    assert [m["id"] for m in st["maps"]] == ["italy"]
    m = st["maps"][0]
    assert m["kind"] == "italy" and m["maxzoom"] == 14 and m["source_date"] == "20261121"
    assert m["size_bytes"] == len(b"PMTILES-DATA")
    assert (tmp_path / "maps" / "italy.pmtiles").exists()
    assert list((tmp_path / "maps").glob("*.tmp")) == []
    assert json.loads((tmp_path / "maps" / "maps.json").read_text())["maps"][0]["id"] == "italy"


async def test_extract_world_has_no_bbox_and_failure_cleans_tmp(tmp_path):
    runner = FakeRunner(rc=2)
    mgr = make_manager(tmp_path, runner=runner, install_tool=True)
    await mgr.start("world", None, None)
    job = await wait_done(mgr)
    assert job["status"] == "failed" and "2" in job["error"]
    assert not any(a.startswith("--bbox") for a in runner.calls[0])
    assert "--maxzoom=6" in runner.calls[0]
    assert list((tmp_path / "maps").glob("*.tmp")) == []
    assert mgr.status()["maps"] == []


async def test_cancel_kills_and_deletes_tmp(tmp_path):
    runner = FakeRunner(hang=True)
    mgr = make_manager(tmp_path, runner=runner, install_tool=True)
    job = await mgr.start("area", [10, 40, 11, 41], "Mia")
    await runner.started.wait()
    assert list((tmp_path / "maps").glob("*.tmp"))
    out = await mgr.cancel(job["id"])
    assert out["status"] == "cancelled"
    assert runner.killed
    assert list((tmp_path / "maps").glob("*.tmp")) == []
    assert mgr.status()["maps"] == [] and mgr.status()["job"]["status"] == "cancelled"
    with pytest.raises(MapsError) as e:
        await mgr.cancel("inesistente")
    assert e.value.status == 404


async def test_shutdown_kills_running_job(tmp_path):
    runner = FakeRunner(hang=True)
    mgr = make_manager(tmp_path, runner=runner, install_tool=True)
    await mgr.start("world", None, None)
    await runner.started.wait()
    await mgr.shutdown()
    assert runner.killed
    assert list((tmp_path / "maps").glob("*.tmp")) == []
    assert mgr.status()["maps"] == []


def test_cleanup_tmp_on_start(tmp_path):
    (tmp_path / "maps").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "maps" / "x.pmtiles.tmp").write_bytes(b"1")
    (tmp_path / "maps" / "ok.pmtiles").write_bytes(b"1")
    (tmp_path / "tools" / "pmtiles.zip.tmp").write_bytes(b"1")
    mgr = make_manager(tmp_path)
    mgr.cleanup_tmp()
    assert [p.name for p in (tmp_path / "maps").iterdir()] == ["ok.pmtiles"]
    assert list((tmp_path / "tools").iterdir()) == []


async def test_disk_space_check_409(tmp_path):
    mgr = make_manager(tmp_path, disk_free=lambda p: 2 * GB, install_tool=True)
    with pytest.raises(MapsError) as e:
        await mgr.start("italy", None, None)  # servono 2*1.5+1 = 4 GB
    assert e.value.status == 409
    assert str(e.value) == "Spazio su disco insufficiente: servono circa 4 GB"
    assert mgr.status()["job"] is None


async def test_one_job_at_a_time(tmp_path):
    runner = FakeRunner(hang=True)
    mgr = make_manager(tmp_path, runner=runner, install_tool=True)
    await mgr.start("world", None, None)
    await runner.started.wait()
    with pytest.raises(MapsError) as e:
        await mgr.start("italy", None, None)
    assert e.value.status == 409
    await mgr.shutdown()


async def test_progress_published_and_delete(tmp_path):
    runner = FakeRunner(hang=True)
    mgr = make_manager(tmp_path, runner=runner, install_tool=True)
    q = mgr.bus.subscribe()
    await mgr.start("world", None, None)
    await runner.started.wait()
    await asyncio.sleep(0.2)
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    assert msgs and all(m["type"] == "map_job" for m in msgs)
    assert any(m["job"]["bytes_done"] == 100_000_000 for m in msgs)  # 50% di 200 MB
    assert msgs[-1]["job"]["bytes_total"] == 200_000_000
    await mgr.shutdown()
    mgr2 = make_manager(tmp_path, install_tool=True)
    await mgr2.start("world", None, None)
    await wait_done(mgr2)
    assert (tmp_path / "maps" / "world.pmtiles").exists()
    await mgr2.delete("world")
    assert not (tmp_path / "maps" / "world.pmtiles").exists()
    assert mgr2.status()["maps"] == []
    with pytest.raises(MapsError):
        await mgr2.delete("world")


async def test_estimate_dict(tmp_path):
    mgr = make_manager(tmp_path)
    r = await mgr.estimate("italy", None)
    assert r == {"estimate_bytes": 2 * GB, "source_url": SRC, "source_date": "20261121",
                 "needs_tool": True, "tool_size_bytes": maps.TOOL_SIZE}


def test_settings_map_mode_and_source_validation():
    from meshlens.db import connect
    conn = connect(":memory:")
    assert load_settings(conn)["map_mode"] == "auto"
    assert load_settings(conn)["maps_source_url"] == ""
    assert save_settings(conn, {"map_mode": "offline"})["map_mode"] == "offline"
    ok = "https://example.com/a/x.pmtiles"
    assert save_settings(conn, {"maps_source_url": ok})["maps_source_url"] == ok
    assert save_settings(conn, {"maps_source_url": ""})["maps_source_url"] == ""
    for k, v in (("map_mode", "boh"), ("map_mode", 1), ("maps_source_url", "http://x.com/a.pmtiles"),
                 ("maps_source_url", "https://x.com/a.zip"), ("maps_source_url", 5),
                 ("maps_source_url", "https:///a.pmtiles")):
        with pytest.raises(ValueError):
            save_settings(conn, {k: v})
