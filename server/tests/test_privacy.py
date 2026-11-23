import base64
import json
import secrets

import pytest
from meshtastic.protobuf import channel_pb2, config_pb2

from meshlens import privacy as pv
from meshlens.coverage import precision_m
from test_config_service import CHAN_PSK, make_protos, secrets_in


def protos(psk=b"\x01", bits=32):
    p = make_protos()
    p["channels"][0].settings.psk = psk
    p["channels"][0].settings.module_settings.position_precision = bits
    return p


def test_public_channel_precise_position_is_risk():
    r = pv.position_risks(protos(), True)
    assert len(r) == 1
    assert r[0]["kind"] == "channel" and r[0]["channel_index"] == 0
    assert r[0]["reasons"] == ["public_key"] and r[0]["precision_m"] is None
    assert r[0]["precision_bits"] == 32 and r[0]["suggested_bits"] == 14
    assert r[0]["channel_name"] == "LongFast"


def test_unnamed_primary_uses_preset_name():
    p = protos()
    p["channels"][0].settings.name = ""
    p["config"].lora.modem_preset = config_pb2.Config.LoRaConfig.MEDIUM_FAST
    assert pv.position_risks(p, True)[0]["channel_name"] == "MediumFast"


def test_precision_14_is_ok_15_is_risk():
    assert pv.position_risks(protos(bits=14), True) == []
    r = pv.position_risks(protos(bits=15), True)
    assert len(r) == 1 and r[0]["precision_m"] == precision_m(15)


def test_private_channel_ok_unless_mqtt_uplink():
    p = protos(psk=secrets.token_bytes(32))
    assert pv.position_risks(p, True) == []
    p["module_config"].mqtt.enabled = True
    p["channels"][0].settings.uplink_enabled = True
    assert pv.position_risks(p, True)[0]["reasons"] == ["mqtt_uplink"]
    p["module_config"].mqtt.enabled = False
    assert pv.position_risks(p, True) == []


def test_disabled_channel_and_zero_precision_ignored():
    p = protos(bits=0)
    ch = channel_pb2.Channel(index=2, role=channel_pb2.Channel.DISABLED)
    ch.settings.psk = b"\x01"
    ch.settings.module_settings.position_precision = 32
    p["channels"].append(ch)
    assert pv.position_risks(p, True) == []


def test_no_key_reason():
    assert pv.position_risks(protos(psk=b""), True)[0]["reasons"] == ["no_key"]


def test_map_report_risk():
    p = protos(psk=secrets.token_bytes(32))
    p["module_config"].mqtt.enabled = True
    p["module_config"].mqtt.map_reporting_enabled = True
    p["module_config"].mqtt.map_report_settings.position_precision = 16
    r = pv.position_risks(p, True)
    assert len(r) == 1 and r[0]["kind"] == "map_report"
    assert r[0]["reasons"] == ["mqtt_map"] and r[0]["suggested_bits"] is None
    assert r[0]["precision_m"] == precision_m(16)
    p["module_config"].mqtt.map_report_settings.position_precision = 0
    assert pv.position_risks(p, True) == []


def test_no_position_no_risk():
    p = protos()
    assert pv.position_risks(p, False) == []
    p["config"].position.gps_mode = config_pb2.Config.PositionConfig.DISABLED
    p["config"].position.fixed_position = False
    assert pv.has_position(p, None) is False
    assert pv.has_position(p, {"lat": 45.0, "lon": 9.0}) is True
    assert pv.has_position(p, {"lat": None, "lon": None}) is False
    p["config"].position.gps_mode = config_pb2.Config.PositionConfig.ENABLED
    assert pv.has_position(p, None) is True
    p["config"].position.gps_mode = config_pb2.Config.PositionConfig.DISABLED
    p["config"].position.fixed_position = True
    assert pv.has_position(p, None) is True


def test_fix_changes():
    p = protos()
    ch = channel_pb2.Channel(index=2, role=channel_pb2.Channel.SECONDARY)
    ch.settings.psk = b""
    ch.settings.module_settings.position_precision = 32
    p["channels"].append(ch)
    r = pv.position_risks(p, True)
    assert pv.fix_changes(r, 13) == {"channels.0.position_precision": 13,
                                     "channels.2.position_precision": 13}
    assert pv.fix_changes(r, 0, [2]) == {"channels.2.position_precision": 0}
    with pytest.raises(ValueError, match="Precisione non ammessa"):
        pv.fix_changes(r, 16)
    with pytest.raises(ValueError, match="Precisione non ammessa"):
        pv.fix_changes(r, True)
    only_map = [{"kind": "map_report", "precision_bits": 16, "precision_m": 1,
                 "reasons": ["mqtt_map"], "suggested_bits": None}]
    with pytest.raises(ValueError, match="Nessun canale da correggere"):
        pv.fix_changes(only_map, 13)
    with pytest.raises(ValueError, match="Nessun canale da correggere"):
        pv.fix_changes(r, 13, [5])


def test_risks_never_contain_psk():
    p = protos(psk=CHAN_PSK)
    p["module_config"].mqtt.enabled = True
    p["channels"][0].settings.uplink_enabled = True
    text = json.dumps(pv.position_risks(p, True))
    assert secrets_in(text) == []
    assert base64.b64encode(CHAN_PSK).decode() not in text
