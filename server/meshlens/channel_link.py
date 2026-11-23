"""Link dei canali https://meshtastic.org/e/#... (ChannelSet): importazione ed esportazione."""
import base64
import re
from urllib.parse import urlsplit

from meshtastic.protobuf import apponly_pb2, channel_pb2, config_pb2

MSG_BAD_LINK = "Link non valido: usa un link https://meshtastic.org/e/#…"
MSG_NO_CHANNELS = "Il link non contiene canali"
MSG_PRIMARY_REQUIRED = "Il canale primario deve essere incluso"
BASE_URL = "https://meshtastic.org/e/"
_HOSTS = ("meshtastic.org", "www.meshtastic.org")
_B64_RE = re.compile(r"[A-Za-z0-9_+/\-]*={0,2}")


def preset_name(modem_preset: int) -> str:
    """LONG_FAST -> "LongFast" (come il nome del canale primario senza nome)."""
    try:
        name = config_pb2.Config.LoRaConfig.ModemPreset.Name(modem_preset)
    except ValueError:
        return "Primario"
    return "".join(p.capitalize() for p in name.split("_"))


def parse_channel_url(url: str) -> list[dict]:
    """Canali [{name, psk (base64 standard)}] di un link di condivisione di Meshtastic."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        raise ValueError(MSG_BAD_LINK) from None
    if (parts.scheme != "https" or (parts.hostname or "").lower() not in _HOSTS
            or parts.path not in ("/e", "/e/")):
        raise ValueError(MSG_BAD_LINK)
    frag = parts.fragment.split("?", 1)[0].strip()  # "...#<dati>?add=true"
    if not frag:
        raise ValueError(MSG_NO_CHANNELS)
    if not _B64_RE.fullmatch(frag):
        raise ValueError(MSG_BAD_LINK)
    raw = frag.rstrip("=").replace("+", "-").replace("/", "_")
    try:
        data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        cs = apponly_pb2.ChannelSet()
        cs.ParseFromString(data)
    except Exception as e:  # base64 o protobuf (DecodeError) non validi
        raise ValueError(MSG_BAD_LINK) from e
    if not cs.settings:
        raise ValueError(MSG_NO_CHANNELS)
    out = []
    for i, s in enumerate(cs.settings):
        name = s.name
        if not name and i == 0:
            name = preset_name(cs.lora_config.modem_preset)
        out.append({"name": name, "psk": base64.b64encode(s.psk).decode()})
    return out


def build_channel_url(channels: list, lora_config, include: list[int] | None = None,
                      add: bool = False) -> str:
    """Link di condivisione (contiene le PSK in chiaro: mai nei log ne' nel database).

    channels: protobuf Channel della libreria; si prendono quelli attivi, in ordine di indice,
    filtrati da include (None = tutti gli attivi). add=True: link "aggiungi canali".
    """
    active = sorted((c for c in channels if c.role != channel_pb2.Channel.DISABLED),
                    key=lambda c: c.index)
    if include is not None:
        wanted = set(include)
        if (not add and any(c.role == channel_pb2.Channel.PRIMARY for c in active)
                and not any(c.role == channel_pb2.Channel.PRIMARY and c.index in wanted
                            for c in active)
                and any(c.index in wanted for c in active)):
            raise ValueError(MSG_PRIMARY_REQUIRED)
        active = [c for c in active if c.index in wanted]
    if not active:
        raise ValueError(MSG_NO_CHANNELS)
    cs = apponly_pb2.ChannelSet()
    for c in active:
        cs.settings.add().CopyFrom(c.settings)
    cs.lora_config.CopyFrom(lora_config)
    data = base64.urlsafe_b64encode(cs.SerializeToString(deterministic=True)).decode("ascii")
    data = data.rstrip("=")
    return f"{BASE_URL}?add=true#{data}" if add else f"{BASE_URL}#{data}"
