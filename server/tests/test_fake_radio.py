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


# <<FIN>>
