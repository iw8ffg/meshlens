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
    assert cm.parse_changes({"channels.1.psk": "QUJD"})[0][1] == b"ABC"
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
    r = d({"channels.1.psk": "QUJD"})
    assert r[0]["old"] == cm.MASK and r[0]["new"] == cm.MASK
    assert "QUJD" not in repr(r)


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
