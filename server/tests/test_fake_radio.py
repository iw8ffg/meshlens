"""Radio simulata e replay (WP7, E17): formato di sessione, registratori, server finto."""
import base64
import json

import pytest
from meshtastic.protobuf import channel_pb2, mesh_pb2, portnums_pb2

import fakeradio as fx  # noqa: F401  (aggiunge tools/ a sys.path)
from fakeradio import nodeinfo_packet, position_packet, text_packet, wait_until  # noqa: F401

import replay_record as rr  # noqa: E402


def _session(n=3):
    node = mesh_pb2.NodeInfo(num=0x42)
    node.user.id = "!00000042"
    node.user.long_name = "Altro"
    cfg_fr = mesh_pb2.FromRadio(id=1)
    cfg_fr.my_info.my_node_num = 0xA1B2C3D4
    pkts = [(float(i), rr.packet_frame(text_packet(0x42, 0xFFFFFFFF, f"m{i}", 100 + i)))
            for i in range(n)]
    return rr.Session(header={"format": rr.SESSION_FORMAT, "version": 1, "source": "synthetic",
                              "my_node_num": 0xA1B2C3D4},
                      nodes=[node], config=[cfg_fr], packets=pkts)


def _b64(msg):
    return base64.b64encode(msg.SerializeToString()).decode()


def _header(**kw):
    return json.dumps({"format": "meshlens-session", "version": 1, **kw})


# ---------------------------------------------------------------- Task 1: formato di sessione

def test_session_roundtrip(tmp_path):
    s = _session(3)
    path = tmp_path / "s.jsonl"
    rr.write_session(path, s)
    back = rr.read_session(path)
    assert back.nodes == s.nodes
    assert back.config == s.config
    assert [t for t, _ in back.packets] == [0.0, 1.0, 2.0]
    assert [f for _, f in back.packets] == [f for _, f in s.packets]
    assert back.my_node_num == 0xA1B2C3D4


def test_session_write_is_atomic(tmp_path):
    rr.write_session(tmp_path / "s.jsonl", _session(1))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["s.jsonl"]


def test_session_rejects_wrong_version():
    with pytest.raises(rr.SessionError, match="Versione di sessione non supportata"):
        rr.read_session(['{"format":"meshlens-session","version":2}'])


def test_session_rejects_missing_header():
    with pytest.raises(rr.SessionError):
        rr.read_session(['{"k":"pkt","t":0,"b64":""}'])


def test_session_error_reports_line_number():
    lines = [_header(), "# commento", '{"k":"node","b64":"!!!non-base64"}']
    with pytest.raises(rr.SessionError, match="riga 3"):
        rr.read_session(lines)


def test_session_requires_monotonic_t():
    frame = _b64(rr.packet_frame(text_packet(1, 2, "x", 1)))
    lines = [_header(), json.dumps({"k": "pkt", "t": 5.0, "b64": frame}),
             json.dumps({"k": "pkt", "t": 1.0, "b64": frame})]
    with pytest.raises(rr.SessionError):
        rr.read_session(lines)


def test_session_ignores_comments_blank_lines_and_unknown_kinds():
    frame = _b64(rr.packet_frame(text_packet(1, 2, "x", 1)))
    lines = ["", "# x", _header(), "", '{"k":"futuro"}', "# altro",
             json.dumps({"k": "pkt", "t": 0.0, "b64": frame})]
    s = rr.read_session(lines)
    assert len(s.packets) == 1 and s.nodes == [] and s.my_node_num is None


def test_sanitize_replaces_channel_psk():
    fr = mesh_pb2.FromRadio()
    fr.channel.index = 1
    fr.channel.role = channel_pb2.Channel.Role.SECONDARY
    fr.channel.settings.psk = bytes(range(16))
    out = rr.sanitize_from_radio(fr)
    assert out.channel.settings.psk == b"\x01"
    assert fr.channel.settings.psk == bytes(range(16))


def test_sanitize_clears_security_config():
    fr = mesh_pb2.FromRadio()
    fr.config.security.private_key = b"p" * 32
    fr.config.security.public_key = b"q" * 32
    fr.config.security.admin_key.append(b"a" * 32)
    out = rr.sanitize_from_radio(fr)
    assert out.config.WhichOneof("payload_variant") == "security"
    assert out.config.security.private_key == b"" and out.config.security.public_key == b""
    assert list(out.config.security.admin_key) == []


def test_sanitize_clears_device_id_and_drops_noise():
    fr = mesh_pb2.FromRadio()
    fr.my_info.my_node_num = 5
    fr.my_info.device_id = b"serial-segreto"
    out = rr.sanitize_from_radio(fr)
    assert out.my_info.device_id == b"" and out.my_info.my_node_num == 5
    for name in ("log_record", "xmodemPacket", "mqttClientProxyMessage", "fileInfo",
                 "clientNotification"):
        noisy = mesh_pb2.FromRadio()
        getattr(noisy, name).SetInParent()
        assert rr.sanitize_from_radio(noisy) is None, name


def test_packet_frame_sets_from_with_reserved_word():
    pkt = text_packet(0x1234, 0xFFFFFFFF, "ciao", 9)
    frame = rr.packet_frame(pkt)
    assert getattr(frame.packet, "from") == 0x1234
    assert frame.WhichOneof("payload_variant") == "packet"


# ---------------------------------------------------------------- Task 2: registratore da database

import hashlib  # noqa: E402
import sqlite3  # noqa: E402

from meshlens import db as mdb  # noqa: E402


def _mkdb(tmp_path, packets=(), nodes=()):
    path = tmp_path / "m.db"
    conn = mdb.connect(path)
    for p in packets:
        row = {"time": 1000.0, "from_num": 0x42, "to_num": 0xFFFFFFFF, "packet_id": 7,
               "source": "rf", "channel": "0", "portnum": "TEXT_MESSAGE_APP", "kind": "text",
               "status": "ok", "snr": 5.5, "rssi": -80, "hop_start": 3, "hop_limit": 2,
               "raw": b"ciao"}
        row.update(p)
        row["size"] = len(row["raw"]) if row["raw"] is not None else 0
        cols = ",".join(row)
        conn.execute(f"INSERT INTO packets({cols}) VALUES({','.join('?' * len(row))})",
                     tuple(row.values()))
    for n in nodes:
        row = {"num": 0x42, "id": "!00000042", "long_name": "Altro", "short_name": "AL",
               "hw_model": "HELTEC_V3", "last_heard": 900.0, "is_mine": 0}
        row.update(n)
        conn.execute(f"INSERT INTO nodes({','.join(row)}) VALUES({','.join('?' * len(row))})",
                     tuple(row.values()))
    conn.commit()
    conn.close()
    return path


def test_from_db_text_packet_roundtrip(tmp_path):
    p = _mkdb(tmp_path, [{}])
    s, st = rr.session_from_db(p)
    t, fr = s.packets[0]
    pkt = fr.packet
    assert pkt.decoded.portnum == portnums_pb2.PortNum.TEXT_MESSAGE_APP
    assert pkt.decoded.payload == b"ciao"
    assert (getattr(pkt, "from"), pkt.to, pkt.id) == (0x42, 0xFFFFFFFF, 7)
    assert (pkt.rx_snr, pkt.hop_start, pkt.hop_limit, pkt.rx_rssi) == (5.5, 3, 2, -80)
    assert st["read"] == 1 and st["kept"] == 1
    assert s.header["source"] == "db"


def test_from_db_skips_truncated_and_empty_raw(tmp_path):
    p = _mkdb(tmp_path, [{"raw": b"x" * 256, "packet_id": 1}, {"raw": None, "packet_id": 2},
                         {"packet_id": 3}])
    s, st = rr.session_from_db(p)
    assert st["skipped"]["truncated"] == 1 and st["skipped"]["no_raw"] == 1
    assert len(s.packets) == 1


def test_from_db_encrypted_goes_to_encrypted_field(tmp_path):
    p = _mkdb(tmp_path, [{"status": "encrypted", "portnum": None, "raw": b"\x01\x02\x03"}])
    s, _ = rr.session_from_db(p)
    pkt = s.packets[0][1].packet
    assert pkt.encrypted == b"\x01\x02\x03"
    assert pkt.WhichOneof("payload_variant") == "encrypted"


def test_from_db_mqtt_channel_name_maps_to_index_0(tmp_path):
    p = _mkdb(tmp_path, [{"source": "mqtt", "channel": "MediumFast", "broker": "pub"}])
    s, _ = rr.session_from_db(p)
    pkt = s.packets[0][1].packet
    assert pkt.channel == 0 and pkt.via_mqtt


def test_from_db_no_mqtt_flag(tmp_path):
    p = _mkdb(tmp_path, [{"source": "mqtt", "packet_id": 1}, {"packet_id": 2}])
    s, st = rr.session_from_db(p, include_mqtt=False)
    assert [f.packet.id for _, f in s.packets] == [2]
    assert st["kept"] == 1


def test_from_db_unknown_port_skipped(tmp_path):
    p = _mkdb(tmp_path, [{"portnum": "NON_ESISTE_APP", "packet_id": 1}, {"packet_id": 2}])
    s, st = rr.session_from_db(p)
    assert st["skipped"]["unknown_port"] == 1 and len(s.packets) == 1


def test_from_db_times_are_relative_and_sorted(tmp_path):
    p = _mkdb(tmp_path, [{"time": 1010.0, "packet_id": 2}, {"time": 1000.0, "packet_id": 1},
                         {"time": 1005.5, "packet_id": 3}])
    s, _ = rr.session_from_db(p)
    assert [t for t, _ in s.packets] == [0.0, 5.5, 10.0]
    assert [f.packet.id for _, f in s.packets] == [1, 3, 2]


def test_from_db_builds_nodes_and_my_node(tmp_path):
    p = _mkdb(tmp_path, [{}], nodes=[
        {"num": 0xA1B2C3D4, "id": "!a1b2c3d4", "long_name": "Mia", "is_mine": 1},
        {"num": 0x42, "lat": 45.5, "lon": 9.25}])
    s, _ = rr.session_from_db(p)
    assert s.my_node_num == 0xA1B2C3D4
    by = {n.num: n for n in s.nodes}
    assert by[0x42].user.long_name == "Altro" and by[0x42].user.id == "!00000042"
    assert by[0x42].position.latitude_i == 455000000
    assert by[0x42].user.hw_model == mesh_pb2.HardwareModel.Value("HELTEC_V3")


def test_from_db_empty_log_message_mentions_packet_log_mode(tmp_path):
    p = _mkdb(tmp_path, [])
    with pytest.raises(rr.SessionError, match="registro pacchetti"):
        rr.session_from_db(p)


def test_from_db_missing_file_and_missing_table(tmp_path):
    with pytest.raises(rr.SessionError, match="Database non trovato"):
        rr.session_from_db(tmp_path / "no.db")
    old = tmp_path / "old.db"
    c = sqlite3.connect(old)
    c.execute("CREATE TABLE x(a)")
    c.commit()
    c.close()
    with pytest.raises(rr.SessionError, match="tabella dei pacchetti"):
        rr.session_from_db(old)


def test_from_db_never_writes_to_the_database(tmp_path):
    p = _mkdb(tmp_path, [{}])
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    rr.session_from_db(p)
    after = hashlib.sha256(p.read_bytes()).hexdigest()
    assert before == after


def test_cli_db_writes_file_and_prints_summary(tmp_path, capsys):
    p = _mkdb(tmp_path, [{"packet_id": 1}, {"packet_id": 2, "raw": b"x" * 256}])
    out = tmp_path / "o.jsonl"
    assert rr.main(["--db", str(p), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "1" in text and "pacchett" in text
    assert len(rr.read_session(out).packets) == 1


def test_cli_rejects_missing_source():
    with pytest.raises(SystemExit) as e:
        rr.main([])
    assert e.value.code == 2


# ---------------------------------------------------------------- Task 4: framing e registratore live

import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402


def test_frame_decoder_handles_split_and_garbage():
    body = mesh_pb2.FromRadio(id=5, config_complete_id=9)
    frame = rr.encode_frame(body)
    dec = rr.FrameDecoder()
    data = b"\xc3" * 32 + b"\x00\x11" + frame
    out = []
    out += dec.feed(data[:36])
    out += dec.feed(data[36:41])
    out += dec.feed(data[41:])
    assert len(out) == 1
    assert mesh_pb2.FromRadio.FromString(out[0]) == body


def test_frame_decoder_resets_on_oversize_length():
    good = rr.encode_frame(mesh_pb2.FromRadio(id=1, config_complete_id=2))
    dec = rr.FrameDecoder()
    out = dec.feed(b"\x94\xc3\x02\x58" + good)  # lunghezza 600 > 512
    assert [mesh_pb2.FromRadio.FromString(b).config_complete_id for b in out] == [2]


def test_encode_frame_header_and_limit():
    msg = mesh_pb2.FromRadio(id=1, config_complete_id=2)
    frame = rr.encode_frame(msg)
    n = len(msg.SerializeToString())
    assert frame[:4] == bytes([0x94, 0xC3, n >> 8, n & 0xFF])
    big = mesh_pb2.FromRadio()
    big.packet.decoded.payload = b"x" * 600
    with pytest.raises(ValueError):
        rr.encode_frame(big)


class MiniRadio:
    """Mini-server di prova (non e' fake_radio): risponde a want_config_id con uno script."""

    def __init__(self, script=None, mute=False):
        self.script, self.mute = script or (lambda want: []), mute
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.got = []
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def _run(self):
        try:
            conn, _ = self.srv.accept()
        except OSError:
            return
        dec = rr.FrameDecoder()
        conn.settimeout(0.2)
        try:
            for _ in range(100):
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    return
                for body in dec.feed(data):
                    msg = mesh_pb2.ToRadio.FromString(body)
                    self.got.append(msg)
                    if msg.WhichOneof("payload_variant") == "want_config_id" and not self.mute:
                        for item in self.script(msg.want_config_id):
                            if isinstance(item, float):
                                time.sleep(item)
                            else:
                                conn.sendall(rr.encode_frame(item))
                        for _ in range(60):  # tiene aperta la connessione finche' il client chiude
                            try:
                                if not conn.recv(4096):
                                    return
                            except socket.timeout:
                                continue
                        return
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self.srv.close()


def test_record_live_collects_config_and_packets_and_sanitizes(tmp_path):
    def script(want):
        a = mesh_pb2.FromRadio(id=1)
        a.my_info.my_node_num = 0xA1B2C3D4
        a.my_info.device_id = b"serial"
        b = mesh_pb2.FromRadio(id=2)
        b.channel.index = 0
        b.channel.settings.psk = bytes(range(16))
        n = mesh_pb2.FromRadio(id=3)
        n.node_info.num = 0x42
        n.node_info.user.id = "!00000042"
        done = mesh_pb2.FromRadio(id=4, config_complete_id=want)
        p1 = rr.packet_frame(text_packet(0x42, 0xFFFFFFFF, "uno", 11))
        p2 = rr.packet_frame(text_packet(0x42, 0xFFFFFFFF, "due", 12))
        return [a, b, n, done, 0.05, p1, 0.05, p2]

    radio = MiniRadio(script)
    out = tmp_path / "live.jsonl"
    try:
        st = rr.record_live("127.0.0.1", radio.port, 0.6, out_path=out)
    finally:
        radio.close()
    s = rr.read_session(out)
    assert s.header["source"] == "radio" and s.my_node_num == 0xA1B2C3D4
    assert len(s.packets) == 2 and st["packets"] == 2
    ts = [t for t, _ in s.packets]
    assert ts[0] == 0.0 and ts[1] >= ts[0]
    chans = [c for c in s.config if c.WhichOneof("payload_variant") == "channel"]
    assert chans[0].channel.settings.psk == b"\x01"
    myinfo = [c for c in s.config if c.WhichOneof("payload_variant") == "my_info"]
    assert myinfo[0].my_info.device_id == b""
    assert [n.num for n in s.nodes] == [0x42]
    wants = [m for m in radio.got if m.WhichOneof("payload_variant") == "want_config_id"]
    assert wants and wants[0].want_config_id not in (0, 69420)
    # la connessione resta aperta lato server finche' il client non chiude: il disconnect e'
    # best effort, quindi si verifica solo che il server abbia visto chiudere il client.
    assert wait_until(lambda: not radio.t.is_alive(), 3.0)


def test_record_live_times_out_without_config_complete(tmp_path):
    radio = MiniRadio(mute=True)
    try:
        with pytest.raises(rr.SessionError, match="Nessuna risposta dalla radio"):
            rr.record_live("127.0.0.1", radio.port, 1.0, out_path=tmp_path / "x.jsonl",
                           config_timeout=0.3)
    finally:
        radio.close()
    assert not (tmp_path / "x.jsonl").exists()


def test_record_live_rejects_forbidden_port(tmp_path):
    with pytest.raises(rr.SessionError, match="8686"):
        rr.record_live("127.0.0.1", 8686, 1.0, out_path=tmp_path / "x.jsonl")


# ---------------------------------------------------------------- Task 5: handshake puro

from meshtastic.protobuf import config_pb2  # noqa: E402

import fake_radio as fr  # noqa: E402


def _kinds(frames):
    return [f.WhichOneof("payload_variant") for f in frames]


def test_handshake_order_is_exact():
    cfg = fr.FakeRadioConfig()
    frames = fr.handshake_frames(cfg, 1234, None)
    assert _kinds(frames) == (["my_info", "metadata", "node_info"] + ["channel"] * 8
                              + ["config"] * 8 + ["moduleConfig"] * 13
                              + ["node_info"] * cfg.node_count + ["config_complete_id"])
    assert [f.id for f in frames] == list(range(1, len(frames) + 1))


def test_handshake_echoes_want_config_id():
    assert fr.handshake_frames(fr.FakeRadioConfig(), 1234, None)[-1].config_complete_id == 1234


def test_handshake_nodeless_skips_other_nodes():
    frames = fr.handshake_frames(fr.FakeRadioConfig(), 69420, None)
    assert _kinds(frames).count("node_info") == 1
    assert frames[-1].config_complete_id == 69420


def test_handshake_my_info_and_own_nodeinfo_consistent():
    cfg = fr.FakeRadioConfig(my_node_num=0x12345678)
    frames = fr.handshake_frames(cfg, 7, None)
    mine = frames[2].node_info
    assert frames[0].my_info.my_node_num == 0x12345678 == mine.num
    assert mine.user.id == "!12345678"
    assert mine.user.long_name == cfg.long_name


def test_handshake_channels():
    cfg = fr.FakeRadioConfig(channel_name="Famiglia")
    chans = [f.channel for f in fr.handshake_frames(cfg, 7, None) if f.WhichOneof(
        "payload_variant") == "channel"]
    assert [c.index for c in chans] == list(range(8))
    R = channel_pb2.Channel.Role
    assert [c.role for c in chans] == [R.PRIMARY, R.SECONDARY] + [R.DISABLED] * 6
    assert chans[1].settings.name == "Famiglia"
    assert chans[0].settings.psk == b"\x01"


def test_handshake_config_sections_complete():
    frames = fr.handshake_frames(fr.FakeRadioConfig(), 7, None)
    cfgs = [f.config for f in frames if f.WhichOneof("payload_variant") == "config"]
    assert [c.WhichOneof("payload_variant") for c in cfgs] == [
        "device", "position", "power", "network", "display", "lora", "bluetooth", "security"]
    lora = cfgs[5].lora
    assert lora.region == config_pb2.Config.LoRaConfig.RegionCode.EU_868
    assert lora.hop_limit == 3 and lora.use_preset
    assert lora.modem_preset == config_pb2.Config.LoRaConfig.ModemPreset.LONG_FAST
    sec = cfgs[7].security
    assert sec.private_key == b"" and sec.public_key == b"" and not sec.admin_key


def test_handshake_module_config_sections_complete():
    frames = fr.handshake_frames(fr.FakeRadioConfig(), 7, None)
    mods = [f.moduleConfig.WhichOneof("payload_variant") for f in frames
            if f.WhichOneof("payload_variant") == "moduleConfig"]
    assert mods == ["mqtt", "serial", "external_notification", "store_forward", "range_test",
                    "telemetry", "canned_message", "audio", "remote_hardware", "neighbor_info",
                    "ambient_lighting", "detection_sensor", "paxcounter"]


def test_handshake_frames_fit_the_stream_limit():
    s = _session(1)
    big = mesh_pb2.NodeInfo(num=0x99)
    big.user.long_name = "L" * 39
    big.user.short_name = "LLLL"
    big.user.public_key = b"k" * 32
    s.nodes.append(big)
    for f in fr.handshake_frames(fr.FakeRadioConfig(), 7, s):
        assert len(f.SerializeToString()) <= 512


def test_handshake_uses_session_nodes_and_my_num():
    s = _session(1)
    s.nodes = [mesh_pb2.NodeInfo(num=0x31), mesh_pb2.NodeInfo(num=0x32),
               mesh_pb2.NodeInfo(num=0xA1B2C3D4)]
    s.config = []
    s.header["my_node_num"] = 0xA1B2C3D4
    frames = fr.handshake_frames(fr.FakeRadioConfig(my_node_num=0x77), 7, s)
    assert frames[0].my_info.my_node_num == 0xA1B2C3D4
    nums = [f.node_info.num for f in frames if f.WhichOneof("payload_variant") == "node_info"]
    assert nums == [0xA1B2C3D4, 0x31, 0x32]


def test_handshake_uses_session_config_frames_when_present():
    s = _session(1)
    s.config = []
    mi = mesh_pb2.FromRadio()
    mi.my_info.my_node_num = 0xA1B2C3D4
    mi.my_info.pio_env = "da-sessione"
    ch = mesh_pb2.FromRadio()
    ch.channel.index = 1
    ch.channel.role = channel_pb2.Channel.Role.SECONDARY
    ch.channel.settings.name = "Registrato"
    lora = mesh_pb2.FromRadio()
    lora.config.lora.region = config_pb2.Config.LoRaConfig.RegionCode.US
    s.config = [mi, ch, lora]
    frames = fr.handshake_frames(fr.FakeRadioConfig(), 7, s)
    assert _kinds(frames).count("my_info") == 1 and frames[0].my_info.pio_env == "da-sessione"
    chans = {f.channel.index: f.channel for f in frames if f.WhichOneof(
        "payload_variant") == "channel"}
    assert len(chans) == 8 and chans[1].settings.name == "Registrato"
    cfgs = {f.config.WhichOneof("payload_variant"): f.config for f in frames
            if f.WhichOneof("payload_variant") == "config"}
    assert len(cfgs) == 8
    assert cfgs["lora"].lora.region == config_pb2.Config.LoRaConfig.RegionCode.US
    assert _kinds(frames)[-1] == "config_complete_id"


def test_synthetic_nodes_are_deterministic_and_valid():
    a, b = fr.synthetic_nodes(0xA1B2C3D4, 5), fr.synthetic_nodes(0xA1B2C3D4, 5)
    assert a == b and len(a) == 5
    ids = [n.user.id for n in a]
    assert len(set(ids)) == 5 and all(i == f"!{n.num:08x}" for i, n in zip(ids, a))
    assert 0xA1B2C3D4 not in [n.num for n in a]
    for n in a:
        assert 36 <= n.position.latitude_i / 1e7 <= 47.5
        assert 6 <= n.position.longitude_i / 1e7 <= 19


def test_forbidden_port_rejected():
    with pytest.raises(ValueError, match="8686"):
        fr.validate_port(8686)
    assert fr.DEFAULT_PORT == 4404


# ---------------------------------------------------------------- Task 6: server TCP

from contextlib import contextmanager  # noqa: E402


class Client:
    """Client di prova con socket grezzo + FrameDecoder (niente libreria meshtastic)."""

    def __init__(self, server):
        self.sock = socket.create_connection(("127.0.0.1", server.port), timeout=3)
        self.sock.settimeout(0.05)
        self.dec = rr.FrameDecoder()
        self.frames = []
        self.arrival = {}
        self.eof = False

    def send(self, msg):
        self.sock.sendall(rr.encode_frame(msg))

    def raw(self, data):
        self.sock.sendall(data)

    def pump(self, timeout=0.5):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                self.eof = True
                return
            if not data:
                self.eof = True
                return
            now = time.monotonic()
            for body in self.dec.feed(data):
                f = mesh_pb2.FromRadio.FromString(body)
                if f.WhichOneof("payload_variant") == "packet":
                    self.arrival.setdefault(f.packet.id, now)
                self.frames.append(f)

    def read(self, n, timeout=3.0):
        """Aspetta almeno n frame in coda e ne consegna n (o meno al timeout)."""
        end = time.monotonic() + timeout
        while len(self.frames) < n and time.monotonic() < end and not self.eof:
            self.pump(0.05)
        out, self.frames = self.frames[:n], self.frames[n:]
        return out

    def read_until(self, pred, timeout=3.0):
        out = []
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            got = self.read(1, 0.2)
            if not got:
                if self.eof:
                    break
                continue
            out.append(got[0])
            if pred(got[0]):
                return out
        return out

    def handshake(self, want=777):
        self.raw(b"\xc3" * 32)
        req = mesh_pb2.ToRadio()
        req.want_config_id = want
        self.send(req)
        return self.read_until(lambda f: f.WhichOneof("payload_variant") == "config_complete_id")

    def close(self):
        self.sock.close()


@contextmanager
def _radio(session=None, **kw):
    with fx.running_fake_radio(session, **kw) as s:
        clients = []
        s._test_clients = clients
        try:
            yield s
        finally:
            for c in clients:
                c.close()


def _client(server):
    c = Client(server)
    server._test_clients.append(c)
    return c


def _to_text(text, pid=42, to=0xFFFFFFFF, channel=0, want_ack=False):
    m = mesh_pb2.ToRadio()
    m.packet.to = to
    m.packet.id = pid
    m.packet.channel = channel
    m.packet.want_ack = want_ack
    m.packet.decoded.portnum = portnums_pb2.PortNum.TEXT_MESSAGE_APP
    m.packet.decoded.payload = text.encode()
    return m


def _pkt_session(times, **hdr):
    pk = [(t, rr.packet_frame(text_packet(0x42, 0xFFFFFFFF, f"p{i}", 500 + i)))
          for i, t in enumerate(times)]
    return rr.Session(header={"format": rr.SESSION_FORMAT, "version": 1, **hdr}, packets=pk)


def _packets(frames):
    return [f for f in frames if f.WhichOneof("payload_variant") == "packet"]


def test_server_binds_ephemeral_port_on_loopback():
    with _radio() as s:
        assert s.port > 0 and s.port not in (4403, 8686)
        s.stop()
        s.stop()


def test_server_handshake_over_socket_matches_pure_sequence():
    with _radio() as s:
        c = _client(s)
        frames = c.handshake(777)
        assert _kinds(frames) == _kinds(fr.handshake_frames(s.cfg, 777, None))
        assert s.wait_handshake(1.0) and s.stats["handshakes"] == 1


def test_server_ignores_wake_bytes_and_garbage_before_frame():
    with _radio() as s:
        c = _client(s)
        c.raw(b"\xc3" * 32 + b"\x00\x01\x02")
        req = mesh_pb2.ToRadio()
        req.want_config_id = 5
        c.send(req)
        frames = c.read_until(lambda f: f.WhichOneof("payload_variant") == "config_complete_id")
        assert frames[-1].config_complete_id == 5


def test_server_survives_malformed_frames():
    with _radio() as s:
        c = _client(s)
        c.raw(b"\x94\xc3\x02\x58")                       # lunghezza 600
        c.raw(b"\x94\xc3\x00\x03\xff\xff\xff")          # corpo non protobuf
        c.raw(b"\x94\xc3\x00\x00")                      # ToRadio vuoto
        frames = c.handshake(9)
        assert frames and frames[-1].config_complete_id == 9
        assert s.stats["ignored"] >= 2


def test_text_packet_is_recorded():
    with _radio() as s:
        c = _client(s)
        c.handshake()
        c.send(_to_text("ciao", pid=42, channel=1))
        assert wait_until(lambda: s.received_snapshot())
        r = s.received_snapshot()[0]
        assert r.text == "ciao" and r.packet.id == 42 and r.packet.channel == 1
        assert r.client == 0 and r.packet.to == 0xFFFFFFFF


def test_every_packet_gets_queue_status():
    with _radio() as s:
        c = _client(s)
        c.handshake()
        c.send(_to_text("ciao", pid=42))
        got = c.read_until(lambda f: f.WhichOneof("payload_variant") == "queueStatus")
        qs = got[-1].queueStatus
        assert qs.res == 0 and qs.mesh_packet_id == 42 and qs.free > 0


def _routing_acks(c, timeout=0.4):
    c.pump(timeout)
    return [f.packet for f in _packets(c.frames)
            if f.packet.decoded.portnum == portnums_pb2.PortNum.ROUTING_APP]


def test_ack_disabled_by_default():
    with _radio() as s:
        c = _client(s)
        c.handshake()
        c.send(_to_text("x", to=0x42, want_ack=True))
        assert _routing_acks(c) == []


def test_ack_enabled_sends_routing_ack_from_destination():
    with _radio(ack=True, ack_delay=0.01) as s:
        c = _client(s)
        c.handshake()
        c.send(_to_text("x", pid=77, to=0x42, want_ack=True))
        got = c.read_until(lambda f: f.WhichOneof("payload_variant") == "packet")
        p = got[-1].packet
        assert getattr(p, "from") == 0x42 and p.to == s.cfg.my_node_num
        assert p.decoded.portnum == portnums_pb2.PortNum.ROUTING_APP
        assert p.decoded.request_id == 77
        routing = mesh_pb2.Routing.FromString(p.decoded.payload)
        assert routing.error_reason == mesh_pb2.Routing.Error.NONE


def test_ack_for_broadcast_comes_from_own_node():
    with _radio(ack=True, ack_delay=0.01) as s:
        c = _client(s)
        c.handshake()
        c.send(_to_text("x", pid=5, want_ack=True))
        p = c.read_until(lambda f: f.WhichOneof("payload_variant") == "packet")[-1].packet
        assert getattr(p, "from") == s.cfg.my_node_num and p.decoded.request_id == 5


def test_nak_reason_is_sent():
    with _radio(ack=True, ack_delay=0.01, nak="NO_RESPONSE") as s:
        c = _client(s)
        c.handshake()
        c.send(_to_text("x", pid=6, to=0x42, want_ack=True))
        p = c.read_until(lambda f: f.WhichOneof("payload_variant") == "packet")[-1].packet
        routing = mesh_pb2.Routing.FromString(p.decoded.payload)
        assert routing.error_reason == mesh_pb2.Routing.Error.NO_RESPONSE


def test_heartbeat_and_disconnect_toradio():
    with _radio() as s:
        c = _client(s)
        c.handshake()
        hb = mesh_pb2.ToRadio()
        hb.heartbeat.SetInParent()
        c.send(hb)
        c.send(_to_text("ancora vivo", pid=1))
        assert wait_until(lambda: s.received_snapshot())
        bye = mesh_pb2.ToRadio()
        bye.disconnect = True
        c.send(bye)
        c.pump(0.5)
        assert c.eof
        c2 = _client(s)
        assert c2.handshake()[-1].config_complete_id == 777


def test_replay_starts_only_after_config_complete():
    with _radio(_pkt_session([0.0, 0.0]), speed=0) as s:
        c = _client(s)
        frames = c.handshake()
        assert not _packets(frames)  # nessun pacchetto prima di config_complete
        c.pump(0.4)
        assert [f.packet.id for f in _packets(c.frames)] == [500, 501]


def test_replay_respects_timing_and_speed():
    with _radio(_pkt_session([0.0, 1.0]), speed=20) as s:
        c = _client(s)
        c.handshake()
        assert wait_until(lambda: c.pump(0.02) or len(c.arrival) == 2, 2.0)
        assert 0.04 <= c.arrival[501] - c.arrival[500] < 0.5


def test_replay_max_gap_caps_waits():
    with _radio(_pkt_session([0.0, 1000.0]), speed=1, max_gap=0.05) as s:
        c = _client(s)
        c.handshake()
        c.pump(1.0)
        assert len(_packets(c.frames)) == 2


def test_replay_speed_zero_has_no_waits():
    with _radio(_pkt_session([0.0, 3600.0]), speed=0) as s:
        c = _client(s)
        c.handshake()
        c.pump(0.6)
        assert len(_packets(c.frames)) == 2


def test_replay_waits_for_client_and_loses_nothing():
    with _radio(_pkt_session([0.0, 0.0, 0.0]), speed=0) as s:
        time.sleep(0.2)
        assert s.stats["replayed"] == 0
        c = _client(s)
        c.handshake()
        c.pump(0.4)
        assert [f.packet.id for f in _packets(c.frames)] == [500, 501, 502]


def _drop_first_client(s, session_times, **kw):
    c1 = _client(s)
    c1.handshake()
    got = c1.read_until(lambda f: f.WhichOneof("payload_variant") == "packet")
    assert _packets(got)[0].packet.id == 500
    c1.close()
    assert wait_until(lambda: s.stats["clients"] == 0)


def test_replay_continues_after_reconnect_by_default():
    with _radio(_pkt_session([0.0, 0.8]), speed=1) as s:
        _drop_first_client(s, None)
        c2 = _client(s)
        c2.handshake()
        c2.pump(1.5)
        assert [f.packet.id for f in _packets(c2.frames)] == [501]


def test_restart_on_connect_replays_from_start():
    with _radio(_pkt_session([0.0, 0.8]), speed=1, restart_on_connect=True) as s:
        _drop_first_client(s, None)
        c2 = _client(s)
        c2.handshake()
        c2.pump(1.5)
        assert [f.packet.id for f in _packets(c2.frames)] == [500, 501]


def test_loop_restarts_session():
    with _radio(_pkt_session([0.0, 0.0]), speed=0, loop=True) as s:
        c = _client(s)
        c.handshake()
        c.pump(0.3)
        ids = [f.packet.id for f in _packets(c.frames)]
        assert len(ids) >= 3 and ids[:4] == [500, 501, 500, 501][:len(ids[:4])]


def test_restamp_rewrites_rx_time():
    sess = _pkt_session([0.0])
    old = sess.packets[0][1].packet.rx_time
    with _radio(sess, speed=0) as s:
        c = _client(s)
        c.handshake()
        c.pump(0.3)
        got = _packets(c.frames)[0].packet.rx_time
        assert abs(got - time.time()) < 5 and got != old
    with _radio(sess, speed=0, restamp=False) as s:
        c = _client(s)
        c.handshake()
        c.pump(0.3)
        assert _packets(c.frames)[0].packet.rx_time == old


def test_push_packet_delivers_immediately_to_ready_client():
    with _radio() as s:
        c = _client(s)
        c.handshake()
        s.push_packet(text_packet(0x42, 0xFFFFFFFF, "pushato", 900))
        got = c.read_until(lambda f: f.WhichOneof("payload_variant") == "packet")
        assert got[-1].packet.decoded.payload == b"pushato"


def test_multiple_clients_get_own_handshake_and_index():
    with _radio() as s:
        a, b = _client(s), _client(s)
        assert a.handshake(11)[-1].config_complete_id == 11
        assert b.handshake(22)[-1].config_complete_id == 22
        a.send(_to_text("da a", pid=1))
        b.send(_to_text("da b", pid=2))
        assert wait_until(lambda: len(s.received_snapshot()) == 2)
        by = {r.text: r.client for r in s.received_snapshot()}
        assert by["da a"] != by["da b"] and s.stats["handshakes"] == 2


def test_stop_closes_clients_and_joins_threads():
    with _radio(_pkt_session([0.0])) as s:
        c = _client(s)
        c.handshake()
        s.stop()
        c.pump(0.5)
        assert c.eof
    live = [t.name for t in threading.enumerate() if t.name.startswith("FakeRadio") and t.is_alive()]
    assert live == []


def test_sent_log_file_appends_jsonl(tmp_path):
    log = tmp_path / "inviati.jsonl"
    with _radio(sent_log=str(log)) as s:
        c = _client(s)
        c.handshake()
        c.send(_to_text("ciao log", pid=3, channel=1))
        assert wait_until(lambda: log.exists() and log.read_text(encoding="utf-8").strip())
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert row["text"] == "ciao log" and row["id"] == 3 and row["channel"] == 1
    assert row["portnum"] == "TEXT_MESSAGE_APP" and set(row) == {
        "time", "to", "channel", "id", "portnum", "text"}


# ---------------------------------------------------------------- Task 7: CLI e libreria vera

from meshtastic.tcp_interface import TCPInterface  # noqa: E402
from pubsub import pub  # noqa: E402


def test_cli_rejects_port_8686(capsys):
    assert fr.main(["--port", "8686"]) == 2
    assert "8686" in capsys.readouterr().err


def test_cli_default_port_is_4404():
    assert fr.build_parser().parse_args([]).port == 4404


def test_cli_bad_session_file_exits_1(tmp_path, capsys):
    assert fr.main(["--session", str(tmp_path / "manca.jsonl"), "--port", "0"]) == 1
    assert "non trovato" in capsys.readouterr().err
    broken = tmp_path / "rotto.jsonl"
    broken.write_text("{non json\n", encoding="utf-8")
    assert fr.main(["--session", str(broken), "--port", "0"]) == 1
    assert "Sessione non valida" in capsys.readouterr().err


def test_cli_invalid_speed_rejected(capsys):
    assert fr.main(["--speed", "-1", "--port", "0"]) == 2
    assert "velocita" in capsys.readouterr().err.lower()


def test_cli_speed_zero_is_allowed():
    ev = threading.Event()
    ev.set()
    assert fr.main(["--speed", "0", "--port", "0"], stop_event=ev) == 0


def test_cli_runs_until_interrupted(capsys, tmp_path):
    ev = threading.Event()
    rc = []
    sess = tmp_path / "s.jsonl"
    rr.write_session(sess, _pkt_session([0.0, 2.0]))
    t = threading.Thread(target=lambda: rc.append(fr.main(
        ["--port", "0", "--session", str(sess), "--speed", "10", "--nodes", "2"],
        stop_event=ev)), daemon=True)
    t.start()
    out = ""

    def listening():
        nonlocal out
        out += capsys.readouterr().out
        return "in ascolto" in out
    assert wait_until(listening, 3.0)
    assert "Sessione: 2 pacchetti" in out
    ev.set()
    t.join(3.0)
    assert not t.is_alive() and rc == [0]


@contextmanager
def _iface(server, **kw):
    iface = TCPInterface("127.0.0.1", portNumber=server.port, timeout=10, **kw)
    try:
        yield iface
    finally:
        iface.close()


def _collector(topic):
    """Ascoltatore pubsub con la stessa firma di PubSubHub (pubsub deduce gli argomenti del
    topic dal primo ascoltatore: devono combaciare con quelli della libreria)."""
    got = []
    if topic.startswith("meshtastic.connection."):
        def cb(interface):
            got.append(interface)
    else:
        def cb(packet, interface):
            got.append(packet)
    pub.subscribe(cb, topic)
    return got, cb


def test_real_tcp_interface_completes_handshake():
    cfg = dict(my_node_num=0x0A0B0C0D, long_name="Prova lunga", node_count=3)
    with _radio(**cfg) as s:
        with _iface(s) as iface:
            my = 0x0A0B0C0D
            assert iface.myInfo.my_node_num == my
            assert iface.nodes[f"!{my:08x}"]["user"]["longName"] == "Prova lunga"
            assert len(iface.nodes) == 1 + 3
            lora = iface.localNode.localConfig.lora
            assert lora.region == config_pb2.Config.LoRaConfig.RegionCode.EU_868
            active = [c for c in iface.localNode.channels
                      if c.role != channel_pb2.Channel.Role.DISABLED]
            assert len(active) == 2


def test_real_interface_receives_replayed_text():
    pkt = text_packet(0x42, 0xFFFFFFFF, "Ciao dalla sessione", 4242, snr=7.25, hop_start=3,
                      hop_limit=1)
    sess = rr.Session(header={"format": rr.SESSION_FORMAT, "version": 1},
                      nodes=[mesh_pb2.NodeInfo(num=0x42)], packets=[(0.0, rr.packet_frame(pkt))])
    sess.nodes[0].user.id = "!00000042"
    got, keep = _collector("meshtastic.receive.text")
    try:
        with _radio(sess, speed=0) as s:
            with _iface(s):
                assert wait_until(lambda: got, 5.0)
    finally:
        pub.unsubscribe(keep, "meshtastic.receive.text")
    p = got[0]
    assert p["decoded"]["text"] == "Ciao dalla sessione"
    assert p["from"] == 0x42 and p["rxSnr"] == 7.25 and p["hopLimit"] == 1


def test_real_interface_send_text_is_received_by_fake_radio():
    with _radio() as s:
        with _iface(s) as iface:
            iface.sendText("ciao radio", channelIndex=1, wantAck=True)
            assert wait_until(lambda: s.received_snapshot(), 5.0)
            r = s.received_snapshot()[0]
            assert r.text == "ciao radio" and r.packet.channel == 1
            assert r.packet.to == 0xFFFFFFFF and r.packet.want_ack


def test_two_sends_are_not_duplicated():
    with _radio() as s:
        with _iface(s) as iface:
            iface.sendText("uno")
            assert wait_until(lambda: len(s.received_snapshot()) == 1, 5.0)
            time.sleep(0.2)
            iface.sendText("due")
            assert wait_until(lambda: len(s.received_snapshot()) >= 2, 5.0)
            time.sleep(0.2)
            assert [r.text for r in s.received_snapshot()] == ["uno", "due"]
            # la libreria registra il queueStatus della radio finta (come farebbe un firmware)
            # NB: in 2.7.11 senza queueStatus i pacchetti NON si duplicano (verificato a mano):
            # la risposta resta per fedelta' al firmware, non per evitare duplicati.
            assert wait_until(lambda: iface.queueStatus is not None
                              and iface.queueStatus.res == 0 and iface.queueStatus.free == 15, 3.0)


def test_real_interface_unicast_ack_resolves():
    got, keep = _collector("meshtastic.receive")
    try:
        with _radio(ack=True, ack_delay=0.01) as s:
            with _iface(s) as iface:
                iface.sendText("x", destinationId="!00000042", wantAck=True)
                assert wait_until(lambda: s.received_snapshot(), 5.0)
                pid = s.received_snapshot()[0].packet.id
                assert wait_until(lambda: any(
                    p.get("decoded", {}).get("portnum") == "ROUTING_APP" for p in got), 5.0)
    finally:
        pub.unsubscribe(keep, "meshtastic.receive")
    ack = [p for p in got if p.get("decoded", {}).get("portnum") == "ROUTING_APP"][0]
    assert ack["decoded"]["requestId"] == pid and ack["from"] == 0x42


def test_real_interface_nodeless_config():
    with _radio() as s:
        with _iface(s, noNodes=True) as iface:
            assert list(iface.nodes) == [f"!{s.cfg.my_node_num:08x}"]


def test_real_interface_close_then_reconnect_continues_replay():
    sess = _pkt_session([0.0, 0.0])
    got, keep = _collector("meshtastic.receive.text")
    try:
        with _radio(sess, speed=0) as s:
            with _iface(s):
                assert wait_until(lambda: len(got) == 2, 5.0)
            with _iface(s):
                assert wait_until(lambda: s.stats["handshakes"] == 2, 5.0)
                time.sleep(0.2)
            assert len(got) == 2
    finally:
        pub.unsubscribe(keep, "meshtastic.receive.text")


def test_server_drop_makes_interface_lose_connection():
    got, keep = _collector("meshtastic.connection.lost")
    try:
        with _radio() as s:
            with _iface(s):
                s.disconnect_clients()
                assert wait_until(lambda: got, 3.0)
    finally:
        pub.unsubscribe(keep, "meshtastic.connection.lost")


def test_record_live_from_fake_radio_then_replay_again(tmp_path):
    src = _pkt_session([0.0, 1.0, 2.0])
    out = tmp_path / "registrata.jsonl"
    with _radio(src, speed=20) as a:
        rr.record_live("127.0.0.1", a.port, 1.0, out_path=out)
    s = rr.read_session(out)
    assert s.header["source"] == "radio" and len(s.packets) == 3
    chans = [c for c in s.config if c.WhichOneof("payload_variant") == "channel"]
    assert chans and all(c.channel.settings.psk in (b"", b"\x01") for c in chans)
    with _radio(s, speed=0) as b:
        c = _client(b)
        c.handshake()
        c.pump(0.4)
        pk = _packets(c.frames)
        assert [f.packet.id for f in pk] == [500, 501, 502]
        assert [f.packet.decoded.payload for f in pk] == [b"p0", b"p1", b"p2"]


# <<FIN>>
