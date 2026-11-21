import json
import re

import pytest

from meshlens import secretbox
from meshlens.db import connect
from meshlens.settings import (MASK, MAX_BROKERS, export_settings, load_settings, mask_secrets,
                               migrate_brokers, migrate_secrets, prepare_import,
                               resolve_broker_secrets, save_settings)

from test_secretbox import RotProtector

K1 = "AQ=="  # chiave predefinita (1 byte)
K2 = "Ag=="
K3 = "Aw=="
K16 = "AAECAwQFBgcICQoLDA0ODw=="  # 16 byte


@pytest.fixture(autouse=True)
def _rot():
    secretbox.set_protector(RotProtector())
    yield
    secretbox.set_protector(None)


@pytest.fixture
def conn():
    return connect(":memory:")


def raw(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return None if row is None else row[0]


def default_of(s):
    return next(b for b in s["mqtt_brokers"] if b["id"] == "default")


def extra(name="Casa", host="casa.example", **kw):
    return {"name": name, "host": host, "topics": ["msh/EU_868/#"], **kw}


def test_fresh_install_has_default_broker(conn):
    s = load_settings(conn)
    assert len(s["mqtt_brokers"]) == 1
    b = s["mqtt_brokers"][0]
    assert b["id"] == "default" and b["encryption"] is True and b["tls"] is False
    assert b["name"] == "mqtt.meshtastic.org (predefinito)" and b["enabled"] is True
    assert b["channels"] == [] and b["extra_keys"] == []
    assert s["mqtt"]["host"] == "mqtt.meshtastic.org"
    assert s["mqtt_send_confirmed_brokers"] == []


def test_migrate_legacy_mqtt(conn):
    legacy = {"host": "mio.example", "port": 1884, "username": "io", "password": "segreta",
              "topics": ["msh/EU_868/IT"], "extra_keys": [K1]}
    conn.execute("INSERT INTO settings(key, value) VALUES('mqtt', ?)", (json.dumps(legacy),))
    conn.execute("INSERT INTO settings(key, value) VALUES('mqtt_send_confirmed', 'true')")
    conn.commit()
    assert migrate_brokers(conn) is True
    s = load_settings(conn)
    b = default_of(s)
    assert (b["host"], b["port"], b["username"], b["password"]) == ("mio.example", 1884, "io",
                                                                  "segreta")
    assert b["topics"] == ["msh/EU_868/IT/#"] and b["extra_keys"] == [K1]
    assert b["encryption"] is True and b["tls"] is False and b["enabled"] is True
    assert "segreta" not in raw(conn, "mqtt_brokers") and K1 not in raw(conn, "mqtt_brokers")
    assert raw(conn, "mqtt") is None
    assert s["mqtt_send_confirmed"] is True
    assert migrate_brokers(conn) is False
    assert load_settings(conn)["mqtt"]["host"] == "mio.example"
    assert load_settings(conn)["mqtt"]["password"] == "segreta"


def test_migrate_without_legacy_row_does_nothing(conn):
    assert migrate_brokers(conn) is False
    assert raw(conn, "mqtt_brokers") is None


def test_put_legacy_mqtt_updates_default_broker(conn):
    save_settings(conn, {"mqtt_brokers": [default_of(load_settings(conn)), extra()]})
    out = save_settings(conn, {"mqtt": {"host": "altro.example"}})
    assert out["mqtt_brokers"][0]["host"] == "altro.example"
    assert out["mqtt_brokers"][0]["username"] == "meshdev"
    assert out["mqtt_brokers"][1]["host"] == "casa.example"
    assert out["mqtt"]["host"] == "altro.example"
    assert raw(conn, "mqtt") is None


def test_brokers_take_precedence_over_mqtt(conn):
    d = default_of(load_settings(conn))
    out = save_settings(conn, {"mqtt": {"host": "ignorato.example"},
                               "mqtt_brokers": [{**d, "host": "vince.example"}]})
    assert out["mqtt_brokers"][0]["host"] == "vince.example"
    assert out["mqtt"]["host"] == "vince.example"


def test_new_broker_defaults_and_id(conn):
    out = save_settings(conn, {"mqtt_brokers": [default_of(load_settings(conn)), extra()]})
    b = out["mqtt_brokers"][1]
    assert b["enabled"] is True and b["tls"] is False and b["encryption"] is False
    assert b["port"] == 1883 and b["username"] == "" and b["password"] == ""
    assert b["channels"] == [] and b["extra_keys"] == []
    assert re.fullmatch(r"b[0-9a-f]{6}", b["id"])
    # l'id resta lo stesso ai salvataggi successivi
    again = save_settings(conn, {"mqtt_brokers": out["mqtt_brokers"]})
    assert again["mqtt_brokers"][1]["id"] == b["id"]


def test_cannot_delete_default_broker(conn):
    with pytest.raises(ValueError, match="Il broker predefinito non si può eliminare: puoi "
                                         "disattivarlo"):
        save_settings(conn, {"mqtt_brokers": [extra()]})
    # disattivarlo si puo'
    d = default_of(load_settings(conn))
    out = save_settings(conn, {"mqtt_brokers": [{**d, "enabled": False}]})
    assert out["mqtt_brokers"][0]["enabled"] is False


def test_max_brokers(conn):
    d = default_of(load_settings(conn))
    many = [d] + [extra(f"B{i}", f"h{i}.example") for i in range(MAX_BROKERS)]
    with pytest.raises(ValueError, match=f"Al massimo {MAX_BROKERS} broker"):
        save_settings(conn, {"mqtt_brokers": many})
    assert len(save_settings(conn, {"mqtt_brokers": many[:MAX_BROKERS]})["mqtt_brokers"]) == 8


def test_bad_ids_and_unknown_keys(conn):
    d = default_of(load_settings(conn))
    for bad in ([d, extra(id="default")], [d, extra(id="Maiuscolo")], [d, extra(id="x" * 25)],
                [d, extra(colore="rosso")], [d, extra(channels=[{"name": "A", "psk": K1, "x": 1}])],
                [d, extra(name="")], [d, extra(name="n" * 41)], [d, extra(tls="si")]):
        with pytest.raises(ValueError):
            save_settings(conn, {"mqtt_brokers": bad})
    with pytest.raises(ValueError, match="Broker Casa: host vuoto"):
        save_settings(conn, {"mqtt_brokers": [d, extra(host="  ")]})
    with pytest.raises(ValueError, match="Broker Casa: porta non valida"):
        save_settings(conn, {"mqtt_brokers": [d, extra(port=0)]})


def test_channel_name_rules(conn):
    d = default_of(load_settings(conn))

    def with_channels(*chs):
        return {"mqtt_brokers": [d, extra(channels=list(chs))]}

    with pytest.raises(ValueError, match="Canale aaaaaaaaaaaa: il nome deve avere da 1 a 11 "
                                         "caratteri"):
        save_settings(conn, with_channels({"name": "a" * 12, "psk": K1}))
    with pytest.raises(ValueError, match="Canale a/b: il nome non può contenere / # \\+"):
        save_settings(conn, with_channels({"name": "a/b", "psk": K1}))
    with pytest.raises(ValueError, match="Canale Uno: nome già usato in questo broker"):
        save_settings(conn, with_channels({"name": "Uno", "psk": K1}, {"name": "Uno", "psk": K2}))
    with pytest.raises(ValueError, match="Broker Casa: al massimo 16 canali"):
        save_settings(conn, with_channels(*[{"name": f"c{i}", "psk": K1} for i in range(17)]))
    out = save_settings(conn, with_channels({"name": "Città", "psk": K1}))  # 6 byte
    assert out["mqtt_brokers"][1]["channels"] == [{"name": "Città", "psk": K1}]
    # lo stesso nome in due broker diversi va bene
    save_settings(conn, {"mqtt_brokers": [{**d, "channels": [{"name": "Uno", "psk": K1}]},
                                          extra(channels=[{"name": "Uno", "psk": K2}])]})


def test_bad_psk_rejected(conn):
    d = default_of(load_settings(conn))
    with pytest.raises(ValueError, match=r"Canale Uno: chiave PSK non valida \("):
        save_settings(conn, {"mqtt_brokers": [d, extra(channels=[{"name": "Uno", "psk": "abc"}])]})
    with pytest.raises(ValueError, match=r"Canale Uno: chiave PSK non valida \("):
        save_settings(conn, {"mqtt_brokers": [d, extra(channels=[{"name": "Uno", "psk": "AAA="}])]})
    with pytest.raises(ValueError):
        save_settings(conn, {"mqtt_brokers": [d, extra(extra_keys=["abc"])]})


def test_empty_topics_rejected(conn):
    d = default_of(load_settings(conn))
    with pytest.raises(ValueError, match="Broker Casa: indica almeno un topic"):
        save_settings(conn, {"mqtt_brokers": [d, extra(topics=["  "])]})
    with pytest.raises(ValueError, match="Broker Casa: indica almeno un topic"):
        save_settings(conn, {"mqtt_brokers": [d, {"name": "Casa", "host": "h"}]})
    out = save_settings(conn, {"mqtt_brokers": [d, extra(topics=["msh/EU_868/IT"])]})
    assert out["mqtt_brokers"][1]["topics"] == ["msh/EU_868/IT/#"]


def test_send_confirmed_brokers_validation(conn):
    assert save_settings(conn, {"mqtt_send_confirmed_brokers": ["default"]})[
        "mqtt_send_confirmed_brokers"] == ["default"]
    for bad in ("default", [1], ["Default"]):
        with pytest.raises(ValueError):
            save_settings(conn, {"mqtt_send_confirmed_brokers": bad})


def _secret_setup(conn):
    d = default_of(load_settings(conn))
    return save_settings(conn, {"mqtt_brokers": [
        {**d, "password": "pw-default"},
        extra(id="casa", password="pw-casa", extra_keys=[K3],
              channels=[{"name": "A", "psk": K16}, {"name": "B", "psk": K2}])]})


def test_secrets_masked_and_encrypted(conn):
    s = _secret_setup(conn)
    m = mask_secrets(s)
    casa = m["mqtt_brokers"][1]
    assert casa["password"] == MASK and m["mqtt_brokers"][0]["password"] == MASK
    assert [c["psk"] for c in casa["channels"]] == [MASK, MASK]
    assert [c["name"] for c in casa["channels"]] == ["A", "B"]
    assert casa["extra_keys"] == [MASK] and m["mqtt"]["password"] == MASK
    text = json.dumps(m)
    stored = raw(conn, "mqtt_brokers")
    for secret in ("pw-default", "pw-casa", K16, K2, K3):
        assert secret not in text and secret not in stored
    # l'originale non e' toccato e si rilegge in chiaro
    assert s["mqtt_brokers"][1]["password"] == "pw-casa"
    assert load_settings(conn)["mqtt_brokers"][1]["channels"][0]["psk"] == K16


def test_migrate_secrets_encrypts_plain_brokers(conn):
    plain = [{"id": "default", "name": "D", "enabled": True, "host": "h", "port": 1883,
              "tls": False, "encryption": True, "username": "", "password": "chiaro",
              "topics": ["msh/#"], "channels": [{"name": "A", "psk": K16}], "extra_keys": [K2]}]
    conn.execute("INSERT INTO settings(key, value) VALUES('mqtt_brokers', ?)",
                 (json.dumps(plain),))
    conn.commit()
    assert migrate_secrets(conn) == 1
    stored = raw(conn, "mqtt_brokers")
    assert "chiaro" not in stored and K16 not in stored and K2 not in stored
    b = load_settings(conn)["mqtt_brokers"][0]
    assert b["password"] == "chiaro" and b["channels"][0]["psk"] == K16 and b["extra_keys"] == [K2]
    assert migrate_secrets(conn) == 0


def test_resolve_masked_secrets():
    existing = [{"id": "default", "password": "pw", "channels": [], "extra_keys": []},
                {"id": "casa", "password": "pw-casa", "extra_keys": [K1, K2],
                 "channels": [{"name": "A", "psk": "k1"}, {"name": "B", "psk": "k2"},
                              {"name": "C", "psk": "k3"}]}]
    new = [{"id": "default", "password": MASK, "channels": [], "extra_keys": []},
           {"id": "casa", "password": MASK, "extra_keys": ["••••#1"],
            "channels": [{"name": "A", "psk": "••••#0"}, {"name": "C2", "psk": "••••#2"},
                         {"name": "B", "psk": MASK}, {"name": "N", "psk": K3}]}]
    out = resolve_broker_secrets(new, existing)
    assert out[0]["password"] == "pw" and out[1]["password"] == "pw-casa"
    assert out[1]["channels"] == [{"name": "A", "psk": "k1"}, {"name": "C2", "psk": "k3"},
                                  {"name": "B", "psk": "k2"}, {"name": "N", "psk": K3}]
    assert out[1]["extra_keys"] == [K2]
    assert new[1]["password"] == MASK  # l'ingresso non e' modificato
    with pytest.raises(ValueError, match="Chiave mascherata senza corrispondenza: reinseriscila"):
        resolve_broker_secrets([{"id": "casa", "channels": [{"name": "A", "psk": "••••#7"}]}],
                               existing)
    with pytest.raises(ValueError, match="Chiave mascherata senza corrispondenza"):
        resolve_broker_secrets([{"id": "casa", "channels": [{"name": "Z", "psk": MASK}]}],
                               existing)
    with pytest.raises(ValueError, match="Chiave mascherata senza corrispondenza"):
        resolve_broker_secrets([{"name": "Nuovo", "password": MASK}], existing)
    with pytest.raises(ValueError, match="Chiave mascherata senza corrispondenza"):
        resolve_broker_secrets([{"id": "ignoto", "extra_keys": [MASK]}], existing)
    # le PSK non passano da un broker all'altro
    with pytest.raises(ValueError, match="Chiave mascherata senza corrispondenza"):
        resolve_broker_secrets([{"id": "default", "channels": [{"name": "A", "psk": "••••#0"}]}],
                               existing)


def test_prepare_import_resolves_and_skips(conn):
    _secret_setup(conn)
    before = load_settings(conn)
    doc = export_settings(before, False)
    changes, skipped = prepare_import(doc, load_settings(conn))
    assert "mqtt" not in changes and "mqtt_send_confirmed_brokers" in skipped
    assert not any(s.startswith("mqtt_brokers.") for s in skipped)
    after = save_settings(conn, changes)
    assert after["mqtt_brokers"] == before["mqtt_brokers"]

    changes, skipped = prepare_import(doc, None)
    assert "mqtt_brokers.default.password" in skipped
    assert {"mqtt_brokers.casa.password", "mqtt_brokers.casa.channels.A",
            "mqtt_brokers.casa.channels.B", "mqtt_brokers.casa.extra_keys"} <= set(skipped)
    empty = connect(":memory:")
    out = save_settings(empty, changes)
    casa = out["mqtt_brokers"][1]
    assert casa["password"] == "" and casa["channels"] == [] and casa["extra_keys"] == []
    assert out["mqtt_brokers"][0]["password"] == ""


def test_prepare_import_legacy_mqtt_updates_default(conn):
    doc = {"format": 1, "settings": {"mqtt": {"host": "vecchio.example", "password": MASK}}}
    changes, skipped = prepare_import(doc, load_settings(conn))
    assert skipped == ["mqtt.password"]
    out = save_settings(conn, changes)
    assert out["mqtt_brokers"][0]["host"] == "vecchio.example"
    assert out["mqtt_brokers"][0]["password"] == "large4cats"


def test_legacy_mqtt_without_topics_keeps_default_topics(conn):
    out = save_settings(conn, {"mqtt": {"host": "127.0.0.1", "port": 1, "topics": []}})
    assert out["mqtt_brokers"][0]["topics"] == ["msh/EU_868/#"]
    assert out["mqtt"]["host"] == "127.0.0.1"


def test_build_migrates_legacy_mqtt(tmp_path, caplog):
    import logging

    from meshlens.app import build
    db = connect(tmp_path / "meshlens.db")
    db.execute("INSERT INTO settings(key, value) VALUES('mqtt', ?)",
               (json.dumps({"host": "mio.example", "password": "segreta"}),))
    db.commit()
    db.close()
    with caplog.at_level(logging.INFO, logger="meshlens.app"):
        app, rt = build(tmp_path, static_dir=None)
    try:
        assert "Impostazioni MQTT migrate a più broker" in caplog.text
        assert rt.settings["mqtt_brokers"][0]["password"] == "segreta"
        assert "segreta" not in raw(rt.conn, "mqtt_brokers")
    finally:
        rt.conn.close()


def test_validate_channels_trims_and_normalizes_empty_psk(conn):
    b = {"id": "default", "name": "X", "host": "h", "topics": ["msh/#"],
         "channels": [{"name": " Priv ", "psk": " AQ== "}, {"name": "Aperto", "psk": ""}]}
    out = save_settings(conn, {"mqtt_brokers": [b]})
    assert out["mqtt_brokers"][0]["channels"] == [
        {"name": "Priv", "psk": "AQ=="}, {"name": "Aperto", "psk": "AA=="}]
