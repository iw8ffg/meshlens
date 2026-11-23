import pytest
from meshtastic.protobuf import channel_pb2, config_pb2, localonly_pb2

from meshlens import config_model as cm

PRIV = b"P" * 32
PUB = b"U" * 32
PSK = b"K" * 16
CTX_USB = {"radio_kind": "usb", "is_local": True}
CTX_BLE = {"radio_kind": "ble", "is_local": True}


def protos():
    lc = localonly_pb2.LocalConfig()
    lc.security.private_key = PRIV
    lc.security.public_key = PUB
    lc.network.wifi_ssid = "casa"
    lc.network.wifi_psk = "segretissima"
    lc.bluetooth.fixed_pin = 123456
    lc.bluetooth.enabled = True
    lc.lora.hop_limit = 3
    lc.lora.modem_preset = config_pb2.Config.LoRaConfig.LONG_FAST
    mc = localonly_pb2.LocalModuleConfig()
    mc.mqtt.password = "mqttpw"
    chans = []
    for i, name in enumerate(["Primario", "Altro"]):
        c = channel_pb2.Channel(index=i, role=1 if i == 0 else 2)
        c.settings.name = name
        c.settings.psk = PSK
        chans.append(c)
    owner = {"long_name": "Nodo", "short_name": "ND", "is_licensed": False}
    return {"config": lc, "module_config": mc, "channels": chans, "owner": owner}


def cfg():
    p = protos()
    return cm.node_to_dict(p["config"], p["module_config"], p["channels"], p["owner"])


def test_node_to_dict_masks_secrets():
    d = cfg()
    assert d["config"]["security"]["private_key"] == cm.MASK
    assert d["config"]["network"]["wifi_psk"] == cm.MASK
    assert d["config"]["bluetooth"]["fixed_pin"] == cm.MASK
    assert d["module_config"]["mqtt"]["password"] == cm.MASK
    assert d["channels"][0]["psk"] == cm.MASK
    assert d["config"]["security"]["public_key"] == "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVU="
    assert d["config"]["lora"]["modem_preset"] == "LONG_FAST"
    assert d["channels"][0]["role"] == "PRIMARY" and d["channels"][1]["name"] == "Altro"
    assert d["owner"] == {"long_name": "Nodo", "short_name": "ND", "is_licensed": False}
    blob = repr(d)
    for s in ("segretissima", "mqttpw", "UFBQ", "S0tL"):
        assert s not in blob


def test_node_to_dict_unmasked_for_backups():
    p = protos()
    d = cm.node_to_dict(p["config"], p["module_config"], p["channels"], p["owner"], mask=False)
    assert d["config"]["network"]["wifi_psk"] == "segretissima"
    assert d["channels"][0]["psk"] != cm.MASK
    assert cm.mask_config(d)["config"]["network"]["wifi_psk"] == cm.MASK


def test_schema_has_enum_names():
    s = cm.schema()
    assert "LONG_FAST" in s["config"]["lora"]["modem_preset"]["enum"]
    assert "CLIENT" in s["config"]["device"]["role"]["enum"]
    assert s["config"]["security"]["private_key"]["secret"] is True
    assert s["channel"]["psk"]["secret"] and s["owner"]["long_name"]["type"] == "string"
    assert "mqtt" in s["module_config"]


def test_parse_changes_validates():
    with pytest.raises(ValueError):
        cm.parse_changes({"config.lora.nonesiste": 1})
    with pytest.raises(ValueError):
        cm.parse_changes({"config.lora.hop_limit": "x"})
    with pytest.raises(ValueError):
        cm.parse_changes({"config.lora.modem_preset": "NOPE"})
    with pytest.raises(ValueError):
        cm.parse_changes({"channels.9.name": "x"})
    with pytest.raises(ValueError):
        cm.parse_changes({"config.lora.tx_enabled": "si"})
    assert cm.parse_changes({"config.lora.modem_preset": "SHORT_FAST"}) == [
        ("config.lora.modem_preset", "SHORT_FAST")]
    assert cm.parse_changes({"config.lora.hop_limit": 4, "owner.long_name": "x"}) == [
        ("config.lora.hop_limit", 4), ("owner.long_name", "x")]
    assert cm.parse_changes({"channels.1.psk": "QQ=="})[0][1] == b"A"
    assert cm.parse_changes({"channels.1.psk": cm.MASK}) == [("channels.1.psk", cm.MASK)]
    with pytest.raises(ValueError):
        cm.parse_changes({"channels.1.psk": "###"})


def d(changes, ctx=CTX_USB):
    return cm.diff(cfg(), cm.parse_changes(changes), ctx)


def test_diff_marks_risky():
    r = d({"config.lora.modem_preset": "SHORT_FAST"})
    assert r[0]["risky"] and r[0]["old"] == "LONG_FAST" and r[0]["reason"]
    assert d({"channels.0.name": "Nuovo"})[0]["risky"]
    r = d({"channels.1.name": "Nuovo"})
    assert not r[0]["risky"] and r[0]["reason"] is None and r[0]["old"] == "Altro"
    assert d({"config.bluetooth.enabled": False}, CTX_BLE)[0]["risky"]
    assert not d({"config.bluetooth.enabled": False}, CTX_USB)[0]["risky"]
    assert d({"config.device.role": "REPEATER"})[0]["risky"]
    assert d({"config.security.is_managed": True})[0]["risky"]
    assert d({"config.network.wifi_ssid": "x"}, {"radio_kind": "net", "is_local": True})[0]["risky"]
    assert d({"config.lora.hop_limit": 3}) == []  # valore uguale
    assert d({"config.network.wifi_psk": cm.MASK}) == []  # mascherato


def test_diff_hides_secret_values():
    r = d({"channels.1.psk": "QUFBQUFBQUFBQUFBQUFBQQ=="})
    assert r[0]["old"] == cm.MASK and r[0]["new"] == cm.MASK
    assert "QUFB" not in repr(r)


def test_apply_keeps_masked_secret():
    p = protos()
    ch = cm.parse_changes({"config.network.wifi_ssid": "nuova",
                           "config.network.wifi_psk": cm.MASK,
                           "config.lora.modem_preset": "SHORT_FAST",
                           "channels.1.name": "X", "channels.1.position_precision": 12,
                           "channels.1.psk": cm.MASK, "owner.long_name": "Nuovo",
                           "config.security.admin_key": ["QUJD"]})
    out = cm.apply_to_protos(p, ch)
    assert out["config"].network.wifi_ssid == "nuova"
    assert out["config"].network.wifi_psk == "segretissima"
    assert out["config"].lora.modem_preset == config_pb2.Config.LoRaConfig.SHORT_FAST
    assert out["channels"][1].settings.name == "X"
    assert out["channels"][1].settings.psk == PSK
    assert out["channels"][1].settings.module_settings.position_precision == 12
    assert out["owner"]["long_name"] == "Nuovo"
    assert list(out["config"].security.admin_key) == [b"ABC"]
    # gli originali non cambiano
    assert p["config"].network.wifi_ssid == "casa" and p["owner"]["long_name"] == "Nodo"


def test_touched_sections():
    ch = cm.parse_changes({"config.lora.hop_limit": 4, "channels.1.name": "x",
                           "config.lora.tx_power": 5, "owner.long_name": "y"})
    assert cm.touched_sections(ch) == ["config.lora", "channels.1", "owner"]


def test_parse_changes_int_ranges():
    # uint32: hop_limit; int32: tx_power; uint32 canale: position_precision
    for bad in (-1, 2**32):
        with pytest.raises(ValueError):
            cm.parse_changes({"config.lora.hop_limit": bad})
    with pytest.raises(ValueError):
        cm.parse_changes({"config.lora.tx_power": 2**31})
    with pytest.raises(ValueError):
        cm.parse_changes({"config.lora.tx_power": -2**31 - 1})
    with pytest.raises(ValueError):
        cm.parse_changes({"channels.1.position_precision": -1})
    for ok in (0, 2**32 - 1):
        assert cm.parse_changes({"config.lora.hop_limit": ok}) == [("config.lora.hop_limit", ok)]
    assert cm.parse_changes({"config.lora.tx_power": 2**31 - 1})[0][1] == 2**31 - 1
    assert cm.parse_changes({"config.lora.tx_power": -2**31})[0][1] == -2**31


def test_mask_unchanged_only_for_secrets():
    # "••••" su un campo non segreto e' un testo normale, non "invariato"
    r = d({"owner.long_name": cm.MASK})
    assert r and r[0]["new"] == cm.MASK
    out = cm.apply_to_protos(protos(), cm.parse_changes({"owner.long_name": cm.MASK}))
    assert out["owner"]["long_name"] == cm.MASK


def test_channel_psk_length_validated():
    import base64
    for n in (0, 1, 16, 32):
        raw = base64.b64encode(b"A" * n).decode()
        assert cm.parse_changes({"channels.1.psk": raw})[0][1] == b"A" * n
    for n in (2, 3, 15, 17, 31, 33):
        raw = base64.b64encode(b"A" * n).decode()
        with pytest.raises(ValueError):
            cm.parse_changes({"channels.1.psk": raw})


# ---- WP4: tipo di chiave dei canali e messaggi predefiniti ----

def test_psk_kind_classes():
    from meshlens import crypto
    assert cm.psk_kind(b"") == "none"
    assert cm.psk_kind(b"\x00") == "none"
    assert cm.psk_kind(b"\x01") == "default"
    assert cm.psk_kind(b"\x05") == "default"
    assert cm.psk_kind(crypto.DEFAULT_KEY) == "default"
    assert cm.psk_kind(bytes(range(16))) == "custom"
    assert cm.psk_kind(bytes(range(32))) == "custom"
    assert cm.KEY_KINDS == ("none", "default", "custom")


def test_channel_dict_has_key_kind_without_leaking_psk():
    import base64
    import json
    import secrets
    p = protos()
    key = secrets.token_bytes(32)
    p["channels"][0].settings.psk = b"\x01"
    p["channels"][1].settings.psk = key
    d = cm.node_to_dict(p["config"], p["module_config"], p["channels"], p["owner"])
    assert d["channels"][0]["key_kind"] == "default"
    assert d["channels"][1]["key_kind"] == "custom"
    assert all(c["psk"] == cm.MASK for c in d["channels"])
    assert base64.b64encode(key).decode() not in json.dumps(d)


def test_key_kind_not_a_change():
    with pytest.raises(ValueError):
        cm.parse_changes({"channels.1.key_kind": "none"})
    assert "key_kind" not in cm.CHANNEL_FIELDS


def test_join_canned_rules():
    assert cm.join_canned(["Ciao", " Arrivo "]) == "Ciao|Arrivo"
    cases = [([], "Serve almeno un messaggio"),
             ([""], "I messaggi non possono essere vuoti"),
             (["  "], "I messaggi non possono essere vuoti"),
             (["a|b"], "I messaggi non possono contenere il carattere |"),
             (["a\nb"], "I messaggi non possono contenere caratteri di controllo"),
             (["è" * 100, "x"], "Troppo lunghi: 202 byte su 200 (separatori compresi)"),
             (["a" * 199, "b"], "Troppo lunghi: 201 byte su 200 (separatori compresi)")]
    for msgs, msg in cases:
        with pytest.raises(ValueError) as ei:
            cm.join_canned(msgs)
        assert str(ei.value) == msg, msgs
    assert cm.join_canned(["a" * 200]) == "a" * 200
    for bad in ("ciao", None, [1, 2]):
        with pytest.raises(ValueError):
            cm.join_canned(bad)


def test_split_canned():
    assert cm.split_canned("") == []
    assert cm.split_canned("a||b|") == ["a", "b"]
    assert cm.split_canned("Ciao|OK") == ["Ciao", "OK"]


def test_diff_marks_link_cutting_fields_risky():
    """I3: modificati a mano restano possibili, ma segnalati nell'anteprima."""
    for changes in ({"config.power.is_power_saving": True},
                    {"config.lora.ignore_incoming": [1234]},
                    {"config.lora.serial_hal_only": True},
                    {"module_config.serial.override_console_serial_port": True}):
        r = d(changes)
        assert r and r[0]["risky"] and r[0]["reason"], changes
