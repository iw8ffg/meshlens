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


# <<FIN>>
