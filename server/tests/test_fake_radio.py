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
