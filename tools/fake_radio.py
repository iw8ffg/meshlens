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


class _Client:
    def __init__(self, sock: socket.socket, index: int) -> None:
        self.sock = sock
        self.index = index
        self.lock = threading.Lock()
        self.ready = False
        self.dead = False
        self.decoder = FrameDecoder()
        self.thread: threading.Thread | None = None

    def close(self) -> None:
        self.dead = True
        self.ready = False
        for fn in (lambda: self.sock.shutdown(socket.SHUT_RDWR), self.sock.close):
            try:
                fn()
            except OSError:
                pass


class FakeRadioServer:
    def __init__(self, cfg: FakeRadioConfig, session=None) -> None:
        if cfg.nak is not None:
            try:
                mesh_pb2.Routing.Error.Value(cfg.nak)
            except ValueError as exc:
                raise ValueError(f"Motivo di rifiuto sconosciuto: {cfg.nak}") from exc
        self.cfg = cfg
        self.session = session
        self.received: list = []
        self.stats = {"clients": 0, "handshakes": 0, "frames_out": 0, "ignored": 0,
                      "replayed": 0, "connections": 0}
        self.on_received = None  # callback facoltativo (ReceivedPacket) per la CLI
        self._lock = threading.Lock()
        self._clients: list = []
        self._next_index = 0
        self._stop = threading.Event()
        self._started = False
        self._stopped = False
        self._listen: socket.socket | None = None
        self._threads: list = []
        self._timers: list = []
        self._hs = threading.Event()
        self._cur_lock = threading.Lock()
        self._cursor = 0
        self._gen = 0
        self._wake = threading.Event()
        self._port = 0
        self._log_lock = threading.Lock()

    # ------------------------------------------------------------------ ciclo di vita
    @property
    def port(self) -> int:
        return self._port

    @property
    def my_node_num(self) -> int:
        s = self.session
        return s.my_node_num if s is not None and s.my_node_num is not None \
            else self.cfg.my_node_num

    def start(self) -> None:
        if self._started:
            return
        validate_port(self.cfg.port, allow_zero=True)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.cfg.host, self.cfg.port))
            sock.listen(8)
        except OSError:
            sock.close()
            raise
        sock.settimeout(0.2)
        self._listen = sock
        self._port = sock.getsockname()[1]
        self._started = True
        t = threading.Thread(target=self._accept_loop, name="FakeRadioAccept", daemon=True)
        t.start()
        self._threads.append(t)
        if self.session is not None and self.session.packets:
            r = threading.Thread(target=self._replay_loop, name="FakeRadioReplay", daemon=True)
            r.start()
            self._threads.append(r)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._stop.set()
        self._wake.set()
        if self._listen is not None:
            try:
                self._listen.close()
            except OSError:
                pass
        for c in list(self._clients):
            c.close()
        for tm in list(self._timers):
            tm.cancel()
        for t in list(self._threads):
            if t is not threading.current_thread():
                t.join(2.0)

    def received_snapshot(self) -> list:
        with self._lock:
            return list(self.received)

    def wait_handshake(self, timeout: float = 5.0) -> bool:
        return self._hs.wait(timeout)

    def disconnect_clients(self) -> None:
        for c in list(self._clients):
            c.close()

    def push_packet(self, pkt: mesh_pb2.MeshPacket) -> None:
        """Inietta subito un pacchetto radio -> client ai client pronti."""
        fr = packet_frame(pkt)
        if not fr.packet.rx_time:
            fr.packet.rx_time = int(time.time())
        self._send_ready(fr)

    # ------------------------------------------------------------------ rete
    def _bump(self, key: str, n: int = 1) -> None:
        with self._lock:
            self.stats[key] += n

    def _send(self, c: _Client, msg) -> bool:
        try:
            data = encode_frame(msg)
        except ValueError:
            return False
        try:
            with c.lock:
                c.sock.sendall(data)
        except OSError:
            c.close()
            return False
        self._bump("frames_out")
        return True

    def _send_ready(self, fr) -> int:
        n = 0
        for c in list(self._clients):
            if c.ready and not c.dead and self._send(c, fr):
                n += 1
        return n

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = self._listen.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            conn.settimeout(0.2)
            try:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            with self._lock:
                idx = self._next_index
                self._next_index += 1
                self.stats["connections"] += 1
                self.stats["clients"] += 1
            c = _Client(conn, idx)
            self._clients.append(c)
            t = threading.Thread(target=self._client_loop, args=(c,),
                                 name=f"FakeRadioClient-{idx}", daemon=True)
            c.thread = t
            self._threads.append(t)
            t.start()

    def _client_loop(self, c: _Client) -> None:
        try:
            while not self._stop.is_set() and not c.dead:
                try:
                    data = c.sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                for body in c.decoder.feed(data):
                    try:
                        self._on_toradio(c, body)
                    except Exception:  # un client non deve mai fermare il server
                        log.exception("errore nel gestire un ToRadio")
                        self._bump("ignored")
        finally:
            c.close()
            with self._lock:
                if c in self._clients:
                    self._clients.remove(c)
                    self.stats["clients"] -= 1

    # ------------------------------------------------------------------ ToRadio
    def _on_toradio(self, c: _Client, body: bytes) -> None:
        msg = mesh_pb2.ToRadio()
        try:
            msg.ParseFromString(body)
        except Exception:
            self._bump("ignored")
            return
        which = msg.WhichOneof("payload_variant")
        if which == "want_config_id":
            self._handshake(c, msg.want_config_id)
        elif which == "packet":
            self._on_packet(c, msg.packet)
        elif which == "heartbeat":
            return
        elif which == "disconnect":
            c.close()
        else:
            self._bump("ignored")

    def _handshake(self, c: _Client, want: int) -> None:
        c.ready = False
        frames = handshake_frames(self.cfg, want, self.session)
        for f in frames:
            if not self._send(c, f):
                return
        if self.cfg.restart_on_connect:
            self._reset_cursor()
        self._bump("handshakes")
        c.ready = True
        self._hs.set()

    def _on_packet(self, c: _Client, pkt: mesh_pb2.MeshPacket) -> None:
        copy = mesh_pb2.MeshPacket()
        copy.CopyFrom(pkt)
        text = None
        if copy.HasField("decoded") and \
                copy.decoded.portnum == portnums_pb2.PortNum.TEXT_MESSAGE_APP:
            text = copy.decoded.payload.decode("utf-8", errors="replace")
        rec = ReceivedPacket(time.time(), c.index, copy, text)
        with self._lock:
            self.received.append(rec)
        self._append_sent_log(rec)
        cb = self.on_received
        if cb is not None:
            try:
                cb(rec)
            except Exception:
                log.exception("errore nel callback di ricezione")
        qs = mesh_pb2.FromRadio()
        qs.queueStatus.res = 0
        qs.queueStatus.free = 15
        qs.queueStatus.maxlen = 16
        qs.queueStatus.mesh_packet_id = pkt.id
        self._send(c, qs)
        if self.cfg.ack and pkt.want_ack:
            tm = threading.Timer(max(0.0, self.cfg.ack_delay), self._send_ack, args=(c, pkt))
            tm.daemon = True
            self._timers.append(tm)
            tm.start()

    def _send_ack(self, c: _Client, pkt: mesh_pb2.MeshPacket) -> None:
        import random
        if self._stop.is_set() or c.dead:
            return
        mine = self.my_node_num
        ack = mesh_pb2.FromRadio()
        p = ack.packet
        setattr(p, "from", mine if pkt.to == BROADCAST or pkt.to == 0 else pkt.to)
        p.to = mine
        p.id = random.randint(1, 0xFFFFFFFF)
        p.rx_time = int(time.time())
        p.decoded.portnum = portnums_pb2.PortNum.ROUTING_APP
        p.decoded.request_id = pkt.id
        routing = mesh_pb2.Routing()
        routing.error_reason = mesh_pb2.Routing.Error.Value(self.cfg.nak or "NONE")
        p.decoded.payload = routing.SerializeToString()
        self._send(c, ack)

    def _append_sent_log(self, rec: ReceivedPacket) -> None:
        path = self.cfg.sent_log
        if not path:
            return
        p = rec.packet
        port = ""
        if p.HasField("decoded"):
            try:
                port = portnums_pb2.PortNum.Name(p.decoded.portnum)
            except ValueError:
                port = str(p.decoded.portnum)
        row = {"time": round(rec.time, 3), "to": p.to, "channel": p.channel, "id": p.id,
               "portnum": port, "text": rec.text}
        try:
            with self._log_lock, open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            log.warning("impossibile scrivere il registro degli invii")

    # ------------------------------------------------------------------ riproduzione
    def _reset_cursor(self) -> None:
        with self._cur_lock:
            self._cursor = 0
            self._gen += 1
        self._wake.set()

    def _gap(self, i: int) -> float:
        if i <= 0:
            return 0.0
        speed = self.cfg.speed
        if not speed or speed == float("inf") or speed < 0:
            return 0.0
        pk = self.session.packets
        return max(0.0, min((pk[i][0] - pk[i - 1][0]) / speed, self.cfg.max_gap))

    def _replay_loop(self) -> None:
        pkts = self.session.packets
        while not self._stop.is_set():
            self._wake.clear()
            with self._cur_lock:
                i, gen = self._cursor, self._gen
            if i >= len(pkts):
                if self.cfg.loop:
                    with self._cur_lock:
                        if self._gen == gen:
                            self._cursor = 0
                    self._stop.wait(0.002)
                else:
                    self._wake.wait(0.1)
                continue
            delay = self._gap(i)
            if delay and self._wake.wait(delay):
                continue  # cursore riportato all'inizio o stop: ricalcola
            if self._stop.is_set():
                return
            fr = mesh_pb2.FromRadio()
            fr.CopyFrom(pkts[i][1])
            if self.cfg.restamp:
                fr.packet.rx_time = int(time.time())
            if not any(c.ready and not c.dead for c in self._clients):
                self._wake.wait(0.01)  # nessun client pronto: il cursore aspetta
                continue
            delivered = self._send_ready(fr)
            if not delivered:
                continue
            with self._cur_lock:
                if self._gen == gen and self._cursor == i:
                    self._cursor = i + 1
            self._bump("replayed")


# <<FIN>>
