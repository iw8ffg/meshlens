import copy
import json

import pytest

from meshlens import db
from meshlens import profiles as pr
from meshlens.config_model import MASK, node_to_dict, schema
from test_config_service import SECRET_TEXTS, make_protos, secrets_in

CONTRACT_EXCLUDED = [
    "config.network.wifi_ssid", "config.network.wifi_psk",
    "module_config.mqtt.address", "module_config.mqtt.username", "module_config.mqtt.password",
    "config.lora.region", "config.lora.tx_power", "config.lora.override_duty_cycle",
    "config.lora.override_frequency", "config.lora.fem_lna_mode", "config.lora.pa_fan_disabled",
    "config.lora.sx126x_rx_boosted_gain",
    "config.device.button_gpio", "config.device.buzzer_gpio", "config.position.rx_gpio",
    "config.position.tx_gpio", "module_config.canned_message.inputbroker_pin_a",
    "module_config.canned_message.inputbroker_pin_b",
    "module_config.canned_message.inputbroker_pin_press",
    "module_config.detection_sensor.monitor_pin", "module_config.external_notification.output",
    "module_config.external_notification.output_vibra",
    "module_config.external_notification.output_buzzer",
    "config.position.fixed_position",
    # aggiunte di WP4 (R4.7)
    "config.bluetooth.fixed_pin", "config.network.ipv4_config", "config.position.gps_en_gpio",
    "module_config.serial.rxd", "module_config.serial.txd", "module_config.audio.ptt_pin",
    "module_config.audio.i2s_ws", "module_config.audio.i2s_sd", "module_config.audio.i2s_din",
    "module_config.audio.i2s_sck", "module_config.remote_hardware.available_pins",
    "config.power.adc_multiplier_override", "config.power.device_battery_ina_address",
]


def read_dict(protos=None) -> dict:
    p = protos or make_protos()
    return node_to_dict(p["config"], p["module_config"], p["channels"], p["owner"])


def test_excluded_fields_cover_contract():
    for path in CONTRACT_EXCLUDED:
        assert pr.is_excluded(path), path
    assert pr.is_excluded("config.security.admin_key")
    assert pr.is_excluded("config.security.is_managed")
    assert pr.is_excluded("owner.long_name")
    assert pr.is_excluded("channels.0.psk")
    for path in ("config.lora.hop_limit", "module_config.mqtt.enabled", "config.device.role"):
        assert not pr.is_excluded(path), path


def test_every_gpio_like_field_is_excluded():
    sch = schema()
    for kind in ("config", "module_config"):
        for sec, fields in sch[kind].items():
            for f in fields:
                if (f.endswith("_gpio") or f.endswith("_pin") or "pin_" in f
                        or (sec == "external_notification" and f.startswith("output"))):
                    assert pr.is_excluded(f"{kind}.{sec}.{f}"), f"{kind}.{sec}.{f}"


def test_allowed_sections_have_no_security():
    allowed = pr.allowed_sections()
    assert "config.security" not in allowed
    assert allowed[0] == "config.device" and "module_config.mqtt" in allowed
    assert "module_config.tak" not in allowed  # non scrivibile con writeConfig


def test_extract_drops_secrets_and_hardware():
    data, sections = pr.extract_profile(read_dict(), None)
    assert "security" not in data["config"]
    lora = data["config"]["lora"]
    for f in ("region", "tx_power", "override_duty_cycle", "override_frequency",
              "fem_lna_mode", "sx126x_rx_boosted_gain"):
        assert f not in lora
    assert lora["hop_limit"] == 3
    assert "wifi_ssid" not in data["config"]["network"]
    assert "wifi_psk" not in data["config"]["network"]
    assert "ipv4_config" not in data["config"]["network"]
    mqtt = data["module_config"]["mqtt"]
    assert not {"address", "username", "password", "map_report_settings"} & set(mqtt)
    text = json.dumps(data)
    assert secrets_in(text) == [] and MASK not in text
    assert sections == [s for s in pr.allowed_sections()
                        if s.split(".")[1] in data[s.split(".")[0]]]
    assert "owner" not in data and "channels" not in data


def test_extract_respects_selected_sections():
    data, sections = pr.extract_profile(read_dict(), ["config.lora", "module_config.mqtt"])
    assert sections == ["config.lora", "module_config.mqtt"]
    assert list(data["config"]) == ["lora"] and list(data["module_config"]) == ["mqtt"]


def test_extract_rejects_security_section():
    with pytest.raises(ValueError) as ei:
        pr.extract_profile(read_dict(), ["config.security"])
    assert str(ei.value) == "Sezione non copiabile: config.security"
    with pytest.raises(ValueError):
        pr.extract_profile(read_dict(), ["config.boh"])


def test_profile_changes_reapplies_exclusions():
    data, sections = pr.extract_profile(read_dict(), None)
    data = copy.deepcopy(data)
    data["config"]["lora"]["region"] = "US"
    data["config"]["lora"]["hop_limit"] = 5
    data["config"]["security"] = {"private_key": "x"}
    data["config"]["device"]["button_gpio"] = 5
    changes, skipped = pr.profile_changes(data, sections, schema())
    assert changes["config.lora.hop_limit"] == 5
    for p in ("config.lora.region", "config.security.private_key", "config.device.button_gpio"):
        assert p in skipped and p not in changes
    assert all(not pr.is_excluded(p) for p in changes)


def test_profile_changes_only_selected_sections():
    data, sections = pr.extract_profile(read_dict(), None)
    changes, skipped = pr.profile_changes(data, ["config.lora"], schema())
    assert changes and all(p.startswith("config.lora.") for p in changes)
    assert skipped == []


def test_profile_changes_skips_unknown_and_invalid():
    data = {"config": {"lora": {"campo_futuro": 1, "hop_limit": "tanti", "use_preset": True}}}
    changes, skipped = pr.profile_changes(data, ["config.lora"], schema())
    assert changes == {"config.lora.use_preset": True}
    assert set(skipped) == {"config.lora.campo_futuro", "config.lora.hop_limit"}


def test_profile_changes_coerces_int64_strings():
    data = {"config": {"device": {"node_info_broadcast_secs": 900}},
            "module_config": {"store_forward": {"records": 10}}}
    changes, skipped = pr.profile_changes(
        data, ["config.device", "module_config.store_forward"], schema())
    assert changes["config.device.node_info_broadcast_secs"] == 900 and skipped == []


def test_compare_two_reads():
    pa, pb = make_protos(), make_protos()
    pb["config"].lora.hop_limit = 5
    pb["config"].network.wifi_psk = "ALTRA-PASSWORD"
    rows = pr.compare(read_dict(pa), read_dict(pb), None)
    assert rows == [{"path": "config.lora.hop_limit", "a": 3, "b": 5, "excluded": False}]
    pb["config"].lora.region = 1  # US
    rows = pr.compare(read_dict(pa), read_dict(pb), None)
    reg = [r for r in rows if r["path"] == "config.lora.region"]
    assert reg and reg[0]["excluded"] is True
    assert pr.compare(read_dict(pa), read_dict(pb), ["config.device"]) == []
    assert secrets_in(json.dumps(rows)) == []


def test_compare_profile_with_read_ignores_missing_fields():
    data, _ = pr.extract_profile(read_dict(), None)
    pb = make_protos()
    pb["config"].lora.region = 1
    rows = pr.compare(data, read_dict(pb), None)
    assert rows == []  # la regione non fa parte del profilo


def store():
    conn = db.connect(":memory:")
    return conn, pr.ProfileStore(conn, clock=lambda: 1000.0)


def test_store_crud_and_unique_name():
    conn, st = store()
    data, sections = pr.extract_profile(read_dict(), ["config.lora"])
    p = st.create(name=" Base ", sections=sections, data=data, source_node_num=0xA1B2C3D4,
                  source_hw="HELTEC_V3", firmware="2.7.11", notes="prova")
    assert p["name"] == "Base" and p["source_node_id"] == "!a1b2c3d4" and p["data"] == data
    assert p["created"] == 1000.0 and p["sections"] == ["config.lora"]
    listed = st.list()
    assert len(listed) == 1 and "data" not in listed[0]
    assert st.get(p["id"])["data"]["config"]["lora"]["hop_limit"] == 3
    with pytest.raises(pr.ProfileError) as ei:
        st.create(name="Base  ", sections=sections, data=data)
    assert ei.value.status == 409
    assert ei.value.message == "Esiste già un profilo con questo nome"
    upd = st.update(p["id"], name="Nuovo")
    assert upd["name"] == "Nuovo" and upd["notes"] == "prova"
    assert st.update(p["id"], notes=None)["notes"] is None
    st.delete(p["id"])
    with pytest.raises(pr.ProfileError) as ei:
        st.get(p["id"])
    assert ei.value.status == 404 and ei.value.message == "Profilo non trovato"
    with pytest.raises(pr.ProfileError):
        st.delete(p["id"])
    for bad in ("", "  ", "a" * 61, "a\tb", None, 5):
        with pytest.raises(ValueError):
            pr.validate_name(bad)
    assert pr.validate_notes("") is None and pr.validate_notes(None) is None
    with pytest.raises(ValueError):
        pr.validate_notes("x" * 501)


def test_store_list_sorted_case_insensitive():
    conn, st = store()
    data, sections = pr.extract_profile(read_dict(), ["config.lora"])
    for name in ("beta", "Alfa", "gamma"):
        st.create(name=name, sections=sections, data=data)
    assert [p["name"] for p in st.list()] == ["Alfa", "beta", "gamma"]


def test_store_create_strips_excluded_even_if_passed():
    conn, st = store()
    st.create(name="X", sections=["config.lora", "config.security"],
              data={"config": {"security": {"private_key": "x"},
                               "lora": {"region": "EU_868", "hop_limit": 3}}})
    raw = conn.execute("SELECT data, sections FROM config_profiles").fetchone()
    assert "security" not in raw["data"] and "region" not in raw["data"]
    assert json.loads(raw["sections"]) == ["config.lora"]
    assert json.loads(raw["data"]) == {"config": {"lora": {"hop_limit": 3}}, "module_config": {}}


def test_export_import_roundtrip():
    conn, st = store()
    data, sections = pr.extract_profile(read_dict(), None)
    p = st.create(name="Base", sections=sections, data=data, source_hw="HELTEC_V3")
    doc = pr.export_doc(p)
    assert doc["format"] == "meshlens-profile" and doc["version"] == 1
    assert set(doc) == {"format", "version", "name", "sections", "data", "source_hw",
                        "firmware", "notes"}
    back = pr.import_doc(json.loads(json.dumps(doc)))
    assert back["sections"] == sections and back["data"] == data
    with pytest.raises(ValueError):
        pr.import_doc({**doc, "format": "altro"})
    with pytest.raises(ValueError):
        pr.import_doc({**doc, "version": 2})
    big = copy.deepcopy(doc)
    big["data"]["config"]["device"]["tzdef"] = "x" * 300_000
    with pytest.raises(ValueError):
        pr.import_doc(big)
    evil = copy.deepcopy(doc)
    evil["data"]["config"]["security"] = {"private_key": "QUJD"}
    evil["sections"] = evil["sections"] + ["config.security"]
    out = pr.import_doc(evil)
    assert "security" not in out["data"]["config"] and "config.security" not in out["sections"]
    for bad in (None, [], "x", {"format": "meshlens-profile", "version": 1, "data": "x"}):
        with pytest.raises(ValueError):
            pr.import_doc(bad)


def test_no_secret_reaches_the_database():
    conn, st = store()
    full = read_dict()
    unmasked = node_to_dict(*[make_protos()[k] for k in ("config", "module_config",
                                                         "channels", "owner")], mask=False)
    for src in (full, unmasked):
        data, sections = pr.extract_profile(src, None)
        st.create(name=f"P{len(st.list())}", sections=sections, data=data)
    dump = "\n".join(r["data"] for r in conn.execute("SELECT data FROM config_profiles"))
    assert secrets_in(dump) == []
    assert all(s.decode() not in dump for s in SECRET_TEXTS)


def test_link_cutting_fields_are_excluded():
    """I3: campi che possono tagliare il collegamento USB/API o bloccare la radio."""
    for path in ("module_config.serial.override_console_serial_port",
                 "config.device.serial_enabled", "config.device.is_managed"):
        assert pr.is_excluded(path), path
