"""Importazione dei canali da un link https://meshtastic.org/e/#... (ChannelSet)."""
import base64
import re
from urllib.parse import urlsplit

from meshtastic.protobuf import apponly_pb2, config_pb2

MSG_BAD_LINK = "Link non valido: usa un link https://meshtastic.org/e/#…"
MSG_NO_CHANNELS = "Il link non contiene canali"
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
            or not parts.path.startswith("/e")):
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
