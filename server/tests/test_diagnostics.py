import io
import json
import zipfile

import httpx
from httpx import ASGITransport

import meshlens
from meshlens.api import create_app
from meshlens.diagnostics import build_bundle
from meshlens.settings import DEFAULTS
from test_api import make_ctx


def _settings():
    s = json.loads(json.dumps(DEFAULTS))
    s["mqtt"]["password"] = "segreta123"
    s["mqtt"]["extra_keys"] = ["AQ=="]
    s["update_token"] = "ghp_abc"
    return s


def test_bundle_contains_files_and_no_secrets(tmp_path):
    (tmp_path / "meshlens.log").write_text("2026-01-01 INFO meshlens: avvio normale\n", encoding="utf-8")
    (tmp_path / "meshlens.log.1").write_text("vecchia riga\n", encoding="utf-8")
    (tmp_path / "console.log").write_text("console\n", encoding="utf-8")
    info = {"version": "1.2.3", "mqtt": {"connected": True}}
    data = build_bundle(info, _settings(), tmp_path)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert set(z.namelist()) == {"info.json", "settings.json", "meshlens.log",
                                     "meshlens.log.1", "console.log"}
        for name in z.namelist():
            raw = z.read(name)
            assert b"segreta123" not in raw and b"ghp_abc" not in raw and b"AQ==" not in raw
        assert b"avvio normale" in z.read("meshlens.log")
        assert json.loads(z.read("info.json"))["version"] == "1.2.3"
        assert json.loads(z.read("settings.json"))["mqtt"]["password"] == "••••"


def test_bundle_truncates_logs_and_skips_missing(tmp_path):
    (tmp_path / "meshlens.log").write_bytes(b"x" * 100 + b"\n" + (b"y" * 99 + b"\n") * 7000)
    data = build_bundle({}, _settings(), tmp_path)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert set(z.namelist()) == {"info.json", "settings.json", "meshlens.log"}
        assert len(z.read("meshlens.log")) <= 512 * 1024


def test_bundle_without_log_dir():
    data = build_bundle({}, _settings(), None)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert set(z.namelist()) == {"info.json", "settings.json"}


async def test_bundle_endpoint(tmp_path):
    from meshlens.backup import BackupManager
    from meshlens.db import connect
    db = tmp_path / "meshlens.db"
    conn = connect(db)
    ctx = make_ctx()
    ctx.db_path, ctx.log_dir = db, tmp_path
    ctx.backups = BackupManager(db, tmp_path / "backups")
    (tmp_path / "meshlens.log").write_text("INFO riga\n", encoding="utf-8")
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(ctx), client=("127.0.0.1", 1)),
                                 base_url="http://127.0.0.1") as c:
        assert (await c.get("/api/diagnostics/bundle")).status_code == 401
        assert (await c.post("/api/auth/setup", json={"pin": "1234"})).status_code == 200
        r = await c.get("/api/diagnostics/bundle")
    conn.close()
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "meshlens-diagnostica-" in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        info = json.loads(z.read("info.json"))
        assert info["version"] == meshlens.__version__ and info["frozen"] is False
        assert "uptime_s" in info and "mqtt" in info and "radios" in info
        assert info["db"]["schema_version"] >= 1 and "backups" in info
        assert b"INFO riga" in z.read("meshlens.log")


def test_bundle_scrubs_mqtt_credentials_from_last_error():
    import io, json, zipfile
    info = {"mqtt": {"connected": False, "last_error": "errore s3gr3t0 per mario"}}
    data = build_bundle(info, {"mqtt": {"username": "mario", "password": "s3gr3t0"}}, None)
    out = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("info.json"))
    assert "s3gr3t0" not in out["mqtt"]["last_error"] and "mario" not in out["mqtt"]["last_error"]


def test_scrub_text_handles_symbol_edged_and_short_secrets():
    from meshlens.settings import scrub_text
    assert "x!pw" not in scrub_text("errore con x!pw dentro", "x!pw")
    assert scrub_text("errore xpw!y", "pw!") == "errore xpw!y"  # corto: solo parola intera
    assert scrub_text("persa", "p") == "persa"


def test_bundle_scrubs_all_broker_credentials():
    s = json.loads(json.dumps(DEFAULTS))
    b1 = {**s["mqtt_brokers"][0], "id": "b1", "name": "Secondo", "username": "utente-b1",
          "password": "pw-b1"}
    s["mqtt_brokers"].append(b1)
    info = {"mqtt": {"connected": False, "last_error": "Secondo: rifiutato pw-b1 utente-b1",
                     "brokers": [{"id": "default", "last_error": None},
                                 {"id": "b1", "last_error": "rifiutato pw-b1 per utente-b1"}]}}
    data = build_bundle(info, s, None)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            assert b"pw-b1" not in z.read(name)
        assert b"utente-b1" not in z.read("info.json")  # in settings.json l'utente resta visibile
        out = json.loads(z.read("info.json"))
    assert out["mqtt"]["brokers"][1]["last_error"].startswith("rifiutato")
    assert out["mqtt"]["brokers"][0]["last_error"] is None
