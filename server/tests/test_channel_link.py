import base64

import pytest
from meshtastic.protobuf import apponly_pb2, config_pb2

from meshtastic.protobuf import channel_pb2, localonly_pb2

from meshlens.channel_link import (MSG_NO_CHANNELS, build_channel_url, parse_channel_url,
                                   preset_name)
from meshlens.settings import merge_channels

KEY32 = bytes(range(32))
KEY32_B64 = base64.b64encode(KEY32).decode()


def _fragment(cs) -> str:
    return base64.urlsafe_b64encode(cs.SerializeToString()).decode().rstrip("=")


def _set(*chans, preset=config_pb2.Config.LoRaConfig.LONG_FAST):
    cs = apponly_pb2.ChannelSet()
    for name, psk in chans:
        s = cs.settings.add()
        s.name, s.psk = name, psk
    cs.lora_config.modem_preset = preset
    return cs


def test_preset_name():
    assert preset_name(config_pb2.Config.LoRaConfig.LONG_FAST) == "LongFast"
    assert preset_name(config_pb2.Config.LoRaConfig.MEDIUM_SLOW) == "MediumSlow"
    assert preset_name(999) == "Primario"


def test_parse_link_roundtrip():
    s = _fragment(_set(("", b"\x01"), ("Squadra", KEY32)))
    want = [{"name": "LongFast", "psk": "AQ=="}, {"name": "Squadra", "psk": KEY32_B64}]
    assert parse_channel_url("https://meshtastic.org/e/#" + s) == want
    assert parse_channel_url("https://meshtastic.org/e/?add=true#" + s) == want
    assert parse_channel_url("https://meshtastic.org/e/#" + s + "?add=true") == want
    assert parse_channel_url("https://meshtastic.org/e/#" + s + "==") == want


@pytest.mark.parametrize("url", ["https://example.com/e/#abc", "https://meshtastic.org/e/#!!!",
                                 "http://meshtastic.org/e/#abc", "https://meshtastic.org/evil/#abc", "non un link"])
def test_parse_link_rejects_garbage(url):
    with pytest.raises(ValueError, match="Link non valido: usa un link https://meshtastic.org/e/#"):
        parse_channel_url(url)


def test_parse_link_without_channels():
    for frag in ("", _fragment(apponly_pb2.ChannelSet()),
                 _fragment(_set())):
        with pytest.raises(ValueError, match="Il link non contiene canali"):
            parse_channel_url("https://meshtastic.org/e/#" + frag)


def test_merge_channels_reasons():
    broker = {"channels": [{"name": "Gia", "psk": KEY32_B64}]}
    added, skipped = merge_channels(broker, [
        {"name": "LongFast", "psk": "AQ=="},       # preset con la chiave pubblica
        {"name": "Gia", "psk": KEY32_B64},         # doppione
        {"name": "NomeTroppoLungo", "psk": "AQ=="},
        {"name": "Strano", "psk": "AQID"},
        {"name": "Mal", "psk": "***"}, {"name": "Mal2", "psk": "!!"},
        {"name": "a/b", "psk": "AQ=="}, {"name": "", "psk": "AQ=="},
        {"name": "LongFast", "psk": KEY32_B64},    # preset ma con chiave propria: ok
        {"name": "Nuovo", "psk": KEY32_B64},
    ])
    assert added == ["LongFast", "Nuovo"]
    assert skipped == [{"name": "LongFast", "reason": "canale pubblico predefinito"},
                       {"name": "Gia", "reason": "già presente"},
                       {"name": "NomeTroppoLungo", "reason": "nome troppo lungo"},
                       {"name": "Strano", "reason": "chiave non valida"},
                       {"name": "Mal", "reason": "chiave non valida"},
                       {"name": "Mal2", "reason": "chiave non valida"},
                       {"name": "a/b", "reason": "nome non valido"},
                       {"name": "", "reason": "nome non valido"}]
    assert [c["name"] for c in broker["channels"]] == ["Gia", "LongFast", "Nuovo"]


def test_merge_channels_limit_16():
    broker = {"channels": [{"name": f"c{i}", "psk": KEY32_B64} for i in range(15)]}
    added, skipped = merge_channels(broker, [{"name": "c15", "psk": KEY32_B64},
                                             {"name": "c16", "psk": KEY32_B64}])
    assert added == ["c15"]
    assert skipped == [{"name": "c16", "reason": "limite di 16 canali"}]
    assert len(broker["channels"]) == 16


def test_merge_channels_no_crypto_psk_stored_as_single_zero_byte():
    broker = {"channels": []}
    added, _ = merge_channels(broker, [{"name": "Aperto", "psk": ""}, {"name": " Sp ", "psk": " AA== "}])
    assert added == ["Aperto", "Sp"]
    assert [c["psk"] for c in broker["channels"]] == ["AA==", "AA=="]


# ---- WP4: link di esportazione ----

def _channels():
    out = []
    for i, (role, name, psk) in enumerate([(channel_pb2.Channel.PRIMARY, "", b"\x01"),
                                          (channel_pb2.Channel.SECONDARY, "Amici", KEY32),
                                          (channel_pb2.Channel.DISABLED, "", b"")]):
        c = channel_pb2.Channel(index=i, role=role)
        c.settings.name, c.settings.psk = name, psk
        out.append(c)
    return out


def _lora():
    lc = localonly_pb2.LocalConfig()
    lc.lora.modem_preset = config_pb2.Config.LoRaConfig.LONG_FAST
    lc.lora.region = config_pb2.Config.LoRaConfig.EU_868
    return lc.lora


def test_build_url_roundtrip():
    url = build_channel_url(_channels(), _lora())
    assert url.startswith("https://meshtastic.org/e/#")
    assert "=" not in url.split("#", 1)[1]
    assert parse_channel_url(url) == [{"name": "LongFast", "psk": "AQ=="},
                                      {"name": "Amici", "psk": KEY32_B64}]


def test_build_url_add_and_include():
    url = build_channel_url(_channels(), _lora(), include=[1], add=True)
    assert url.startswith("https://meshtastic.org/e/?add=true#")
    assert parse_channel_url(url) == [{"name": "Amici", "psk": KEY32_B64}]
    with pytest.raises(ValueError, match="Il canale primario deve essere incluso"):
        build_channel_url(_channels(), _lora(), include=[1], add=False)
    with pytest.raises(ValueError) as ei:
        build_channel_url(_channels(), _lora(), include=[2])
    assert str(ei.value) == MSG_NO_CHANNELS
    with pytest.raises(ValueError):
        build_channel_url([], _lora())


def test_build_url_matches_library_format():
    chans = _channels()
    lora = _lora()
    cs = apponly_pb2.ChannelSet()  # come Node.getURL della libreria (node.py r.374)
    for c in chans:
        if c.role in (channel_pb2.Channel.PRIMARY, channel_pb2.Channel.SECONDARY):
            cs.settings.append(c.settings)
    cs.lora_config.CopyFrom(lora)
    s = base64.urlsafe_b64encode(cs.SerializeToString()).decode("ascii")
    s = s.replace("=", "").replace("+", "-").replace("/", "_")
    assert build_channel_url(chans, lora) == f"https://meshtastic.org/e/#{s}"
