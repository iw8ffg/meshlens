#!/usr/bin/env python
"""Radio simulata per MeshLens (E17): server TCP locale che parla il protocollo a flusso
Meshtastic (0x94 0xC3 + lunghezza + protobuf), risponde all'handshake con un nodo e canali
sintetici e riproduce una sessione registrata con replay_record.py.

Non simula la RF e non e' un firmware: le conferme di consegna sono finte. Solo libreria
standard + meshtastic: nessun import da meshlens. Ascolta solo in locale (127.0.0.1)."""
from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from meshtastic.protobuf import (channel_pb2, config_pb2, mesh_pb2,  # noqa: E402
                                 module_config_pb2, portnums_pb2)

from replay_record import (HEADER_LEN, MAX_TO_FROM_RADIO_SIZE, NODELESS_WANT_CONFIG_ID,  # noqa: E402,F401
                           START1, START2, FrameDecoder, Session, SessionError, encode_frame,
                           packet_frame, read_session, validate_port)

log = logging.getLogger("fake_radio")

DEFAULT_PORT = 4404
FORBIDDEN_PORTS = (8686,)
BROADCAST = 0xFFFFFFFF

_CFG_SECTIONS = ("device", "position", "power", "network", "display", "lora", "bluetooth",
                 "security")
_MODULE_SECTIONS = ("mqtt", "serial", "external_notification", "store_forward", "range_test",
                    "telemetry", "canned_message", "audio", "remote_hardware", "neighbor_info",
                    "ambient_lighting", "detection_sensor", "paxcounter")
_FAKE_PSK = bytes(range(16))  # PSK finta del canale secondario: non e' una chiave vera

# citta' italiane (lat, lon) per i nodi sintetici
_CITIES = ((45.4642, 9.1900), (41.9028, 12.4964), (40.8518, 14.2681), (45.0703, 7.6869),
           (44.4949, 11.3426), (43.7696, 11.2558), (38.1157, 13.3615), (45.4408, 12.3155))
_HW = ("HELTEC_V3", "TBEAM", "TLORA_V2_1_1P6", "RAK4631", "T_ECHO")


@dataclass
class FakeRadioConfig:
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    my_node_num: int = 0xA1B2C3D4
    long_name: str = "Radio finta"
    short_name: str = "FAKE"
    channel_name: str = "Amici"
    node_count: int = 3
    ack: bool = False
    ack_delay: float = 0.05
    nak: str | None = None
    speed: float = 1.0
    loop: bool = False
    max_gap: float = 5.0
    restamp: bool = True
    restart_on_connect: bool = False
    sent_log: str | None = None


@dataclass
class ReceivedPacket:
    time: float
    client: int
    packet: mesh_pb2.MeshPacket
    text: str | None


def synthetic_nodes(my_num: int, count: int) -> list:
    """Nodi finti deterministici con nome e posizione in Italia."""
    out = []
    for i in range(max(0, count)):
        num = 0x0000A001 + i
        if num == my_num:
            num += 0x1000
        lat, lon = _CITIES[i % len(_CITIES)]
        n = mesh_pb2.NodeInfo()
        n.num = num
        n.user.id = f"!{num:08x}"
        n.user.long_name = f"Nodo finto {i + 1}"
        n.user.short_name = f"F{i + 1:02d}"[:4]
        n.user.hw_model = mesh_pb2.HardwareModel.Value(_HW[i % len(_HW)])
        n.user.role = config_pb2.Config.DeviceConfig.Role.CLIENT
        n.position.latitude_i = int(round((lat + 0.01 * (i // len(_CITIES))) * 1e7))
        n.position.longitude_i = int(round(lon * 1e7))
        n.snr = 6.0 - (i % 5)
        out.append(n)
    return out


def _own_node(cfg: FakeRadioConfig, my_num: int, session) -> mesh_pb2.NodeInfo:
    if session is not None:
        for n in session.nodes:
            if n.num == my_num:
                own = mesh_pb2.NodeInfo()
                own.CopyFrom(n)
                if not own.user.id:
                    own.user.id = f"!{my_num:08x}"
                return own
    n = mesh_pb2.NodeInfo()
    n.num = my_num
    n.user.id = f"!{my_num:08x}"
    n.user.long_name = cfg.long_name
    n.user.short_name = cfg.short_name[:4]
    n.user.hw_model = mesh_pb2.HardwareModel.HELTEC_V3
    n.user.role = config_pb2.Config.DeviceConfig.Role.CLIENT
    return n


def _synthetic_config(cfg: FakeRadioConfig, my_num: int) -> dict:
    """Frame sintetici indicizzati per (tipo, chiave)."""
    frames = {}
    mi = mesh_pb2.FromRadio()
    mi.my_info.my_node_num = my_num
    mi.my_info.reboot_count = 1
    mi.my_info.min_app_version = 30200
    mi.my_info.device_id = b"FAKE-RADIO-0001"
    mi.my_info.pio_env = "fake"
    frames[("my_info", None)] = mi
    md = mesh_pb2.FromRadio()
    md.metadata.firmware_version = "2.7.11.fake"
    md.metadata.hw_model = mesh_pb2.HardwareModel.HELTEC_V3
    md.metadata.hasWifi = True
    md.metadata.role = config_pb2.Config.DeviceConfig.Role.CLIENT
    frames[("metadata", None)] = md
    R = channel_pb2.Channel.Role
    for idx in range(8):
        c = mesh_pb2.FromRadio()
        c.channel.index = idx
        if idx == 0:
            c.channel.role = R.PRIMARY
            c.channel.settings.psk = b"\x01"
        elif idx == 1:
            c.channel.role = R.SECONDARY
            c.channel.settings.name = cfg.channel_name
            c.channel.settings.psk = _FAKE_PSK
        else:
            c.channel.role = R.DISABLED
        frames[("channel", idx)] = c
    for name in _CFG_SECTIONS:
        c = mesh_pb2.FromRadio()
        sect = getattr(c.config, name)
        sect.SetInParent()
        if name == "device":
            sect.role = config_pb2.Config.DeviceConfig.Role.CLIENT
        elif name == "lora":
            sect.region = config_pb2.Config.LoRaConfig.RegionCode.EU_868
            sect.modem_preset = config_pb2.Config.LoRaConfig.ModemPreset.LONG_FAST
            sect.hop_limit = 3
            sect.use_preset = True
            sect.tx_enabled = True
        frames[("config", name)] = c
    for name in _MODULE_SECTIONS:
        c = mesh_pb2.FromRadio()
        getattr(c.moduleConfig, name).SetInParent()
        frames[("moduleConfig", name)] = c
    return frames


def _key_of(fr: mesh_pb2.FromRadio):
    which = fr.WhichOneof("payload_variant")
    if which == "channel":
        return ("channel", fr.channel.index)
    if which == "config":
        return ("config", fr.config.WhichOneof("payload_variant"))
    if which == "moduleConfig":
        return ("moduleConfig", fr.moduleConfig.WhichOneof("payload_variant"))
    if which in ("my_info", "metadata"):
        return (which, None)
    return None


def handshake_frames(cfg: FakeRadioConfig, want_config_id: int, session=None) -> list:
    """Sequenza esatta dei FromRadio dopo want_config_id (puro: nessun socket)."""
    my_num = (session.my_node_num if session is not None and session.my_node_num is not None
              else cfg.my_node_num)
    synth = _synthetic_config(cfg, my_num)
    if session is not None and session.config:
        had_channel = False
        for f in session.config:
            key = _key_of(f)
            if key is None:
                continue
            if key[0] == "channel":
                had_channel = True
            if key[0] in ("my_info", "metadata", "channel", "config", "moduleConfig"):
                copy = mesh_pb2.FromRadio()
                copy.CopyFrom(f)
                if key[0] == "my_info":
                    copy.my_info.my_node_num = my_num
                synth[key] = copy
        if had_channel:  # i canali non registrati restano spenti (niente "Amici" finto)
            R = channel_pb2.Channel.Role
            recorded = {k[1] for k in (_key_of(f) for f in session.config) if k and k[0] == "channel"}
            for idx in range(8):
                if idx not in recorded:
                    c = mesh_pb2.FromRadio()
                    c.channel.index = idx
                    c.channel.role = R.DISABLED
                    synth[("channel", idx)] = c
    now = int(time.time())
    own = _own_node(cfg, my_num, session)
    if not own.last_heard:
        own.last_heard = now
    seq = [synth[("my_info", None)], synth[("metadata", None)]]
    f = mesh_pb2.FromRadio()
    f.node_info.CopyFrom(own)
    seq.append(f)
    seq += [synth[("channel", i)] for i in range(8)]
    # le sezioni registrate in piu' (non previste dal set standard) non si inviano mai
    seq += [synth[("config", n)] for n in _CFG_SECTIONS]
    seq += [synth[("moduleConfig", n)] for n in _MODULE_SECTIONS]
    if want_config_id != NODELESS_WANT_CONFIG_ID:
        if session is not None and session.nodes:
            others = [n for n in session.nodes if n.num != my_num]
        else:
            others = synthetic_nodes(my_num, cfg.node_count)
        for n in others:
            c = mesh_pb2.NodeInfo()
            c.CopyFrom(n)
            if not c.user.id:
                c.user.id = f"!{c.num:08x}"
            if not c.last_heard:
                c.last_heard = now
            g = mesh_pb2.FromRadio()
            g.node_info.CopyFrom(c)
            seq.append(g)
    done = mesh_pb2.FromRadio()
    done.config_complete_id = want_config_id
    out = []
    for fr in seq:
        copy = mesh_pb2.FromRadio()
        copy.CopyFrom(fr)
        if copy.ByteSize() > MAX_TO_FROM_RADIO_SIZE:
            log.warning("frame di configurazione troppo grande, omesso")
            continue
        out.append(copy)
    out.append(done)
    for i, fr in enumerate(out, start=1):
        fr.id = i
    return out


# <<FIN>>
