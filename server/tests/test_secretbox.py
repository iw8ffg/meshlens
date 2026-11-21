import base64
import json
import logging
import sys

import pytest

from meshlens import secretbox
from meshlens.app import build
from meshlens.db import connect
from meshlens.secretbox import PlainProtector, SecretError
from meshlens.settings import export_settings, load_settings, migrate_secrets, save_settings


class RotProtector:
    """Cifratura finta ma reversibile: la riga grezza non contiene il testo in chiaro."""

    def protect(self, plain):
        return "rot:" + base64.b64encode(plain[::-1].encode()).decode()

    def unprotect(self, stored):
        if not stored.startswith("rot:"):
            return stored
        return base64.b64decode(stored[4:]).decode()[::-1]

    def is_protected(self, stored):
        return stored.startswith("rot:")


class BrokenProtector(RotProtector):
    def unprotect(self, stored):
        if stored.startswith("rot:"):
            raise SecretError("altro profilo")
        return stored


@pytest.fixture(autouse=True)
def _reset_protector():
    yield
    secretbox.set_protector(None)


def raw(conn, key="update_token"):
    return conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()[0]


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI solo su Windows")
def test_dpapi_roundtrip():
    p = secretbox.DpapiProtector()
    stored = p.protect("ghp_x")
    assert stored.startswith("dpapi:v1:") and "ghp_x" not in stored
    assert p.unprotect(stored) == "ghp_x"
    assert p.unprotect("ghp_legacy") == "ghp_legacy"
    assert p.is_protected(stored) and not p.is_protected("ghp_legacy")
    with pytest.raises(SecretError):
        p.unprotect("dpapi:v1:" + base64.b64encode(b"spazzatura").decode())
    with pytest.raises(SecretError):
        p.unprotect("dpapi:v1:!!non-base64!!")


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI solo su Windows")
def test_default_protector_is_dpapi_and_end_to_end():
    assert isinstance(secretbox.default_protector(), secretbox.DpapiProtector)
    conn = connect(":memory:")
    save_settings(conn, {"update_token": "ghp_real"})
    assert "ghp_real" not in raw(conn) and json.loads(raw(conn)).startswith("dpapi:v1:")
    assert load_settings(conn)["update_token"] == "ghp_real"


def test_plain_protector_roundtrip():
    p = PlainProtector()
    assert p.protect("abc") == "plain:abc" and p.unprotect("plain:abc") == "abc"
    assert p.unprotect("vecchio") == "vecchio"
    with pytest.raises(SecretError):
        p.unprotect("dpapi:v1:AAAA")


def test_saved_token_is_not_plaintext_in_db():
    secretbox.set_protector(RotProtector())
    conn = connect(":memory:")
    save_settings(conn, {"update_token": "ghp_secret"})
    assert "ghp_secret" not in raw(conn)
    assert load_settings(conn)["update_token"] == "ghp_secret"
    save_settings(conn, {"update_token": ""})  # svuotare non cifra
    assert json.loads(raw(conn)) == "" and load_settings(conn)["update_token"] == ""


def test_legacy_plaintext_token_migrated():
    secretbox.set_protector(RotProtector())
    conn = connect(":memory:")
    conn.execute("INSERT INTO settings(key, value) VALUES('update_token', ?)", (json.dumps("ghp_old"),))
    assert load_settings(conn)["update_token"] == "ghp_old"  # leggibile anche prima
    assert migrate_secrets(conn) == 1
    assert "ghp_old" not in raw(conn)
    assert load_settings(conn)["update_token"] == "ghp_old"
    assert migrate_secrets(conn) == 0


def test_undecryptable_token_becomes_empty(tmp_path, caplog):
    secretbox.set_protector(RotProtector())
    conn = connect(":memory:")
    save_settings(conn, {"update_token": "ghp_x"})
    secretbox.set_protector(BrokenProtector())
    with caplog.at_level(logging.WARNING, logger="meshlens.settings"):
        assert load_settings(conn)["update_token"] == ""
    assert "Impossibile decifrare update_token" in caplog.text
    assert migrate_secrets(conn) == 0  # non riscrive un valore gia' cifrato

    # un database con un token non decifrabile: l'app parte lo stesso
    db = connect(tmp_path / "meshlens.db")
    secretbox.set_protector(RotProtector())
    save_settings(db, {"update_token": "ghp_x"})
    db.close()
    secretbox.set_protector(BrokenProtector())
    app, rt = build(tmp_path, static_dir=None)
    assert rt.settings["update_token"] == ""


def test_export_with_secrets_is_clear_and_import_reencrypts():
    secretbox.set_protector(RotProtector())
    conn = connect(":memory:")
    save_settings(conn, {"update_token": "ghp_move"})
    doc = export_settings(load_settings(conn), True)
    assert doc["settings"]["update_token"] == "ghp_move"  # non il blob
    other = connect(":memory:")
    save_settings(other, {"update_token": doc["settings"]["update_token"]})
    assert "ghp_move" not in raw(other) and load_settings(other)["update_token"] == "ghp_move"


class CountingBroken(BrokenProtector):
    calls = 0

    def unprotect(self, stored):
        CountingBroken.calls += 1
        return super().unprotect(stored)


def test_decrypt_is_cached_and_warns_once(caplog):
    secretbox.set_protector(RotProtector())
    conn = connect(":memory:")
    save_settings(conn, {"update_token": "ghp_x"})
    p = CountingBroken()
    secretbox.set_protector(p)
    CountingBroken.calls = 0
    with caplog.at_level(logging.WARNING, logger="meshlens.settings"):
        assert load_settings(conn)["update_token"] == ""
        assert load_settings(conn)["update_token"] == ""
    assert CountingBroken.calls == 1
    assert caplog.text.count("Impossibile decifrare") == 1


class FailingProtect(RotProtector):
    def protect(self, plain):
        raise SecretError("DPAPI ko")


def test_migrate_keeps_plaintext_when_protect_fails(tmp_path, caplog):
    secretbox.set_protector(FailingProtect())
    conn = connect(":memory:")
    conn.execute("INSERT INTO settings(key, value) VALUES('update_token', ?)", (json.dumps("ghp_old"),))
    with caplog.at_level(logging.WARNING, logger="meshlens.settings"):
        assert migrate_secrets(conn) == 0
    assert json.loads(raw(conn)) == "ghp_old" and "Impossibile cifrare" in caplog.text
    db = connect(tmp_path / "meshlens.db")
    db.execute("INSERT INTO settings(key, value) VALUES('update_token', ?)", (json.dumps("ghp_old"),))
    db.commit()
    db.close()
    app, rt = build(tmp_path, static_dir=None)  # parte lo stesso
    assert rt.settings["update_token"] == "ghp_old"


def test_save_protect_failure_is_valueerror():
    secretbox.set_protector(FailingProtect())
    conn = connect(":memory:")
    with pytest.raises(ValueError, match="Impossibile cifrare update_token"):
        save_settings(conn, {"update_token": "ghp_x"})
    assert load_settings(conn)["update_token"] == ""
