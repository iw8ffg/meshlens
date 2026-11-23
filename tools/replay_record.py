#!/usr/bin/env python
"""Registratore di sessioni per la radio simulata di MeshLens (E17).

Possiede il formato di sessione (JSON lines, versione 1) usato da fake_radio.py.
Solo libreria standard + meshtastic: nessun import da meshlens.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from meshtastic.protobuf import mesh_pb2, portnums_pb2

log = logging.getLogger("replay_record")

SESSION_FORMAT = "meshlens-session"
SESSION_VERSION = 1
DEFAULT_PSK = b"\x01"  # "chiave predefinita" della rete: non e' un segreto


class SessionError(ValueError):
    """Errore di lettura/scrittura/registrazione di una sessione (messaggi in italiano)."""


@dataclass
class Session:
    header: dict
    nodes: list = field(default_factory=list)       # list[mesh_pb2.NodeInfo]
    config: list = field(default_factory=list)      # list[mesh_pb2.FromRadio]
    packets: list = field(default_factory=list)     # list[tuple[float, mesh_pb2.FromRadio]]

    @property
    def my_node_num(self) -> int | None:
        v = self.header.get("my_node_num")
        return int(v) if isinstance(v, int) and not isinstance(v, bool) else None


# ------------------------------------------------------------------ utilità sui pacchetti

def packet_frame(pkt: mesh_pb2.MeshPacket) -> mesh_pb2.FromRadio:
    """Avvolge un MeshPacket in un FromRadio (il campo `from` e' parola riservata di Python)."""
    fr = mesh_pb2.FromRadio()
    fr.packet.CopyFrom(pkt)
    return fr


_DROPPED = ("log_record", "xmodemPacket", "mqttClientProxyMessage", "fileInfo",
            "clientNotification")


def sanitize_from_radio(fr: mesh_pb2.FromRadio):
    """Copia ripulita dai segreti, oppure None per i frame da scartare.

    PSK dei canali -> chiave predefinita; config.security svuotata; device_id azzerato;
    wifi_psk e password MQTT azzerate."""
    which = fr.WhichOneof("payload_variant")
    if which in _DROPPED:
        return None
    out = mesh_pb2.FromRadio()
    out.CopyFrom(fr)
    if which == "channel":
        if out.channel.settings.psk:
            out.channel.settings.psk = DEFAULT_PSK
    elif which == "my_info":
        out.my_info.device_id = b""
    elif which == "config":
        sub = out.config.WhichOneof("payload_variant")
        if sub == "security":
            out.config.security.Clear()
            out.config.security.SetInParent()
        elif sub == "network":
            out.config.network.wifi_psk = ""
    elif which == "moduleConfig":
        if out.moduleConfig.WhichOneof("payload_variant") == "mqtt":
            out.moduleConfig.mqtt.password = ""
    return out


# ------------------------------------------------------------------ lettura / scrittura

def _decode(line_no: int, what: str, b64: object, cls):
    try:
        raw = base64.b64decode(b64, validate=True)
        msg = cls()
        msg.ParseFromString(raw)
        return msg
    except (binascii.Error, ValueError, TypeError) as exc:
        raise SessionError(f"Sessione non valida alla riga {line_no}: {what} illeggibile") from exc
    except Exception as exc:  # DecodeError di protobuf
        raise SessionError(
            f"Sessione non valida alla riga {line_no}: {what} non e' un messaggio valido") from exc


def _lines_of(source) -> Iterable[str]:
    if isinstance(source, (str, os.PathLike)):
        try:
            with open(source, "r", encoding="utf-8") as fh:
                return fh.read().splitlines()
        except FileNotFoundError as exc:
            raise SessionError(f"File di sessione non trovato: {source}") from exc
        except (OSError, UnicodeDecodeError) as exc:
            raise SessionError(f"File di sessione illeggibile: {source}") from exc
    return list(source)


def read_session(path_or_lines) -> Session:
    header = None
    sess = None
    last_t = None
    for line_no, raw in enumerate(_lines_of(path_or_lines), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except ValueError as exc:
            raise SessionError(f"Sessione non valida alla riga {line_no}: JSON non valido") from exc
        if not isinstance(obj, dict):
            raise SessionError(f"Sessione non valida alla riga {line_no}: atteso un oggetto JSON")
        if header is None:
            if obj.get("format") != SESSION_FORMAT:
                raise SessionError(
                    f"Sessione non valida alla riga {line_no}: manca l'intestazione "
                    f"\"{SESSION_FORMAT}\"")
            ver = obj.get("version")
            if ver != SESSION_VERSION:
                raise SessionError(f"Versione di sessione non supportata: {ver}")
            header = obj
            sess = Session(header=header)
            continue
        kind = obj.get("k")
        if kind == "node":
            sess.nodes.append(_decode(line_no, "il nodo", obj.get("b64"), mesh_pb2.NodeInfo))
        elif kind == "config":
            sess.config.append(_decode(line_no, "la configurazione", obj.get("b64"),
                                       mesh_pb2.FromRadio))
        elif kind == "pkt":
            t = obj.get("t")
            if isinstance(t, bool) or not isinstance(t, (int, float)) or t < 0:
                raise SessionError(
                    f"Sessione non valida alla riga {line_no}: tempo \"t\" mancante o negativo")
            if last_t is not None and t < last_t:
                raise SessionError(
                    f"Sessione non valida alla riga {line_no}: il tempo \"t\" non puo' decrescere")
            last_t = float(t)
            fr = _decode(line_no, "il pacchetto", obj.get("b64"), mesh_pb2.FromRadio)
            if fr.WhichOneof("payload_variant") != "packet":
                raise SessionError(
                    f"Sessione non valida alla riga {line_no}: il frame non contiene un pacchetto")
            sess.packets.append((last_t, fr))
        else:
            log.warning("riga %d: tipo \"%s\" sconosciuto, ignorata", line_no, kind)
    if sess is None:
        raise SessionError("Sessione vuota: manca l'intestazione")
    return sess


def _b64(msg) -> str:
    return base64.b64encode(msg.SerializeToString()).decode("ascii")


def write_session(path, session: Session) -> None:
    """Scrittura atomica: file temporaneo nella stessa cartella + os.replace."""
    path = Path(path)
    header = {"format": SESSION_FORMAT, "version": SESSION_VERSION,
              "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "source": "synthetic", "note": ""}
    header.update(session.header)
    header["format"], header["version"] = SESSION_FORMAT, SESSION_VERSION
    lines = [json.dumps(header, ensure_ascii=False)]
    lines += [json.dumps({"k": "node", "b64": _b64(n)}) for n in session.nodes]
    lines += [json.dumps({"k": "config", "b64": _b64(c)}) for c in session.config]
    lines += [json.dumps({"k": "pkt", "t": round(float(t), 3), "b64": _b64(f)})
              for t, f in session.packets]
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------ registratore da database

RAW_MAX = 256            # il registro pacchetti tronca il payload a 256 byte (packet_log.RAW_MAX)
BROADCAST = 0xFFFFFFFF
_GENERATED_ID_BASE = 0x7F000000


def _open_ro(db_path):
    p = Path(db_path)
    if not p.is_file():
        raise SessionError(f"Database non trovato: {p}")
    try:
        return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise SessionError(f"Impossibile aprire il database in sola lettura: {p}") from exc


def _table_columns(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _num(v):
    return v is not None


def _row_to_packet(row: dict, include_mqtt: bool, only_decoded: bool, stats: dict, gen):
    """Ricostruisce un MeshPacket da una riga di `packets`. None = scartata (gia' contata)."""
    skipped = stats["skipped"]
    raw = row.get("raw")
    status = row.get("status")
    if not raw and status != "empty":
        skipped["no_raw"] += 1
        return None
    raw = bytes(raw or b"")
    if len(raw) >= RAW_MAX:
        skipped["truncated"] += 1
        return None
    mqtt = row.get("source") == "mqtt"
    if mqtt and not include_mqtt:
        return None
    if only_decoded and status != "ok":
        return None
    encrypted = status in ("encrypted", "undecodable")
    port = None
    if not encrypted:
        try:
            port = portnums_pb2.PortNum.Value(row.get("portnum") or "")
        except ValueError:
            skipped["unknown_port"] += 1
            return None
    ch = row.get("channel")
    try:
        channel = int(ch) if ch is not None and str(ch).lstrip("-").isdigit() else 0
    except ValueError:
        channel = 0
    if not 0 <= channel <= 255:
        skipped["bad_channel"] += 1
        return None
    pkt = mesh_pb2.MeshPacket()
    setattr(pkt, "from", int(row.get("from_num") or 0))
    to = row.get("to_num")
    pkt.to = BROADCAST if to is None else int(to)
    pid = row.get("packet_id")
    pkt.id = int(pid) if pid else gen()
    pkt.channel = channel
    pkt.rx_time = int(row.get("time") or 0)
    if _num(row.get("snr")):
        pkt.rx_snr = float(row["snr"])
    if _num(row.get("rssi")):
        pkt.rx_rssi = int(row["rssi"])
    if _num(row.get("hop_start")):
        pkt.hop_start = int(row["hop_start"])
    if _num(row.get("hop_limit")):
        pkt.hop_limit = int(row["hop_limit"])
    if _num(row.get("relay_node")):
        pkt.relay_node = int(row["relay_node"])
    pkt.via_mqtt = mqtt
    if encrypted:
        pkt.encrypted = raw
    else:
        pkt.decoded.portnum = port
        pkt.decoded.payload = raw
    return pkt


def _nodes_from_db(conn, max_nodes: int):
    cols = _table_columns(conn, "nodes")
    if not cols:
        return [], None
    conn.row_factory = sqlite3.Row
    order = " ORDER BY last_heard DESC" if "last_heard" in cols else ""
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM nodes{order} LIMIT ?", (max_nodes,))]
    mine = [int(r["num"]) for r in conn.execute("SELECT num FROM nodes WHERE is_mine = 1")] \
        if "is_mine" in cols else []
    out = []
    for r in rows:
        if r.get("num") is None:
            continue
        n = mesh_pb2.NodeInfo()
        n.num = int(r["num"])
        n.user.id = r.get("id") or f"!{n.num:08x}"
        n.user.long_name = r.get("long_name") or ""
        n.user.short_name = r.get("short_name") or ""
        try:
            n.user.hw_model = mesh_pb2.HardwareModel.Value(r.get("hw_model") or "UNSET")
        except ValueError:
            pass
        if r.get("last_heard"):
            n.last_heard = int(r["last_heard"])
        if r.get("lat") is not None and r.get("lon") is not None:
            n.position.latitude_i = int(round(float(r["lat"]) * 1e7))
            n.position.longitude_i = int(round(float(r["lon"]) * 1e7))
        out.append(n)
    return out, (mine[0] if len(mine) == 1 else None)


def session_from_db(db_path, *, since=None, until=None, limit=None, include_mqtt=True,
                    only_decoded=False, max_nodes=200):
    """Sessione ricostruita dal registro pacchetti del database (sola lettura).

    Il registro conserva solo Data.payload (max 256 byte) piu' le colonne: i MeshPacket
    sono ricostruiti, non copiati bit a bit."""
    conn = _open_ro(db_path)
    try:
        if not _table_columns(conn, "packets"):
            raise SessionError(
                "Il database non ha la tabella dei pacchetti (versione troppo vecchia?)")
        conn.row_factory = sqlite3.Row
        where, params = [], []
        if since is not None:
            where.append("time >= ?")
            params.append(float(since))
        if until is not None:
            where.append("time <= ?")
            params.append(float(until))
        sql = "SELECT * FROM packets"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY time, id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        stats = {"read": 0, "kept": 0,
                 "skipped": {"no_raw": 0, "truncated": 0, "unknown_port": 0, "bad_channel": 0}}
        counter = [_GENERATED_ID_BASE]

        def gen():
            counter[0] += 1
            return counter[0]

        kept = []
        for r in conn.execute(sql, params):
            stats["read"] += 1
            row = dict(r)
            pkt = _row_to_packet(row, include_mqtt, only_decoded, stats, gen)
            if pkt is not None:
                kept.append((float(row["time"]), row.get("packet_id") or 0, pkt))
        nodes, my_num = _nodes_from_db(conn, max_nodes)
    finally:
        conn.close()
    if not kept:
        raise SessionError(
            "Nessun pacchetto registrabile: il registro pacchetti e' vuoto o spento. "
            "Attiva il registro pacchetti (Impostazioni -> modalita' «tutti») e riprova.")
    kept.sort(key=lambda k: (k[0], k[1]))
    t0 = kept[0][0]
    packets = [(round(t - t0, 3), packet_frame(p)) for t, _, p in kept]
    stats["kept"] = len(packets)
    header = {"source": "db", "note": "Ricostruita dal registro pacchetti (payload <= 256 byte)"}
    if my_num is not None:
        header["my_node_num"] = my_num
    return Session(header=header, nodes=nodes, packets=packets), stats


# ------------------------------------------------------------------ framing del flusso Meshtastic

START1, START2, HEADER_LEN, MAX_TO_FROM_RADIO_SIZE = 0x94, 0xC3, 4, 512
NODELESS_WANT_CONFIG_ID = 69420
FORBIDDEN_PORTS = (8686,)  # porta del server MeshLens: mai usata da questi strumenti
DEFAULT_RADIO_PORT = 4403


def validate_port(port: int, *, allow_zero: bool = False) -> int:
    if port in FORBIDDEN_PORTS:
        raise ValueError(f"La porta {port} e' riservata al server MeshLens: scegline un'altra")
    if not (0 if allow_zero else 1) <= port <= 65535:
        raise ValueError(f"Porta non valida: {port}")
    return port


def encode_frame(msg) -> bytes:
    body = msg.SerializeToString()
    if len(body) > MAX_TO_FROM_RADIO_SIZE:
        raise ValueError(f"Messaggio troppo grande per il flusso ({len(body)} > "
                         f"{MAX_TO_FROM_RADIO_SIZE} byte)")
    return bytes([START1, START2, len(body) >> 8, len(body) & 0xFF]) + body


class FrameDecoder:
    """Stesso comportamento del lettore della libreria: scarta i byte che non sono un frame."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list:
        self._buf += data
        out = []
        buf = self._buf
        while True:
            i = buf.find(START1)
            if i < 0:
                buf.clear()
                break
            if i:
                del buf[:i]
            if len(buf) < 2:
                break
            if buf[1] != START2:
                del buf[0]
                continue
            if len(buf) < HEADER_LEN:
                break
            length = (buf[2] << 8) | buf[3]
            if length > MAX_TO_FROM_RADIO_SIZE:
                del buf[0]
                continue
            if len(buf) < HEADER_LEN + length:
                break
            out.append(bytes(buf[HEADER_LEN:HEADER_LEN + length]))
            del buf[:HEADER_LEN + length]
        return out


# ------------------------------------------------------------------ registratore live

def record_live(host, port, seconds, *, out_path, wake=True, on_packet=None,
                config_timeout=15.0, connect_timeout=5.0) -> dict:
    """Si collega a una radio via TCP, scarica la configurazione e registra i pacchetti.

    Client TCP grezzo (non TCPInterface) per catturare i FromRadio veri. La radio ha una sola
    connessione TCP alla volta: chiudere prima MeshLens o le altre app."""
    import random
    import socket
    import time
    try:
        validate_port(int(port))
    except ValueError as exc:
        raise SessionError(str(exc)) from exc
    want = random.randint(1, 0xFFFFFFFF)
    while want == NODELESS_WANT_CONFIG_ID:
        want = random.randint(1, 0xFFFFFFFF)
    try:
        sock = socket.create_connection((host, int(port)), timeout=connect_timeout)
    except OSError as exc:
        raise SessionError(f"Impossibile collegarsi a {host}:{port}: {exc.strerror or exc}") from exc
    nodes, config, packets = [], [], []
    my_num = None
    t_first = None
    dec = FrameDecoder()
    interrupted = False
    try:
        sock.settimeout(0.2)
        if wake:
            sock.sendall(bytes([START2]) * 32)
            time.sleep(0.1)
        req = mesh_pb2.ToRadio()
        req.want_config_id = want
        sock.sendall(encode_frame(req))
        deadline = time.monotonic() + config_timeout
        configured = False
        end = None
        try:
            while True:
                now = time.monotonic()
                if not configured and now > deadline:
                    raise SessionError(f"Nessuna risposta dalla radio entro {config_timeout:g} s")
                if configured and now >= end:
                    break
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    data = b""
                if not data:
                    if not configured:
                        raise SessionError("La radio ha chiuso la connessione prima di finire "
                                           "la configurazione")
                    break
                for body in dec.feed(data):
                    fr = mesh_pb2.FromRadio()
                    try:
                        fr.ParseFromString(body)
                    except Exception:
                        continue
                    which = fr.WhichOneof("payload_variant")
                    if not configured:
                        if which == "config_complete_id":
                            if fr.config_complete_id == want:
                                configured = True
                                end = time.monotonic() + float(seconds)
                            continue
                        if which == "my_info":
                            my_num = fr.my_info.my_node_num
                        clean = sanitize_from_radio(fr)
                        if clean is None:
                            continue
                        if which == "node_info":
                            nodes.append(clean.node_info)
                        elif which in ("my_info", "metadata", "channel", "config", "moduleConfig"):
                            config.append(clean)
                    elif which == "packet":
                        pkt = fr.packet
                        if pkt.HasField("decoded") and \
                                pkt.decoded.portnum == portnums_pb2.PortNum.ADMIN_APP:
                            continue  # le risposte di amministrazione possono portare segreti
                        mono = time.monotonic()
                        if t_first is None:
                            t_first = mono
                        packets.append((round(mono - t_first, 3), fr))
                        if on_packet is not None:
                            on_packet(fr)
        except KeyboardInterrupt:
            interrupted = True
        try:
            bye = mesh_pb2.ToRadio()
            bye.disconnect = True
            sock.sendall(encode_frame(bye))
        except OSError:
            pass
    finally:
        sock.close()
    header = {"source": "radio", "note": "Registrata da una radio (PSK e chiavi rimosse)"}
    if my_num is not None:
        header["my_node_num"] = my_num
    write_session(out_path, Session(header=header, nodes=nodes, config=config, packets=packets))
    return {"nodes": len(nodes), "config": len(config), "packets": len(packets),
            "seconds": float(seconds), "interrupted": interrupted}


# ------------------------------------------------------------------ CLI

def _utf8_streams():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def build_parser():
    import argparse
    ap = argparse.ArgumentParser(
        prog="replay_record.py",
        description="Registra una sessione per la radio simulata (fake_radio.py).")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--db", metavar="FILE", help="database di MeshLens (registro pacchetti)")
    src.add_argument("--radio", metavar="HOST[:PORTA]",
                     help="radio vera via TCP (porta predefinita 4403); ha una sola connessione "
                          "alla volta: chiudi prima MeshLens e le altre app")
    ap.add_argument("--seconds", type=float, default=60.0, metavar="S",
                    help="con --radio: durata della registrazione dopo la configurazione")
    ap.add_argument("--out", metavar="FILE", required=True, help="file di sessione da scrivere")
    ap.add_argument("--since", type=float, metavar="EPOCH", help="solo pacchetti dopo questo istante")
    ap.add_argument("--until", type=float, metavar="EPOCH", help="solo pacchetti prima di questo istante")
    ap.add_argument("--limit", type=int, metavar="N", help="al massimo N pacchetti")
    ap.add_argument("--no-mqtt", action="store_true", help="salta i pacchetti arrivati da MQTT")
    ap.add_argument("--only-decoded", action="store_true", help="solo pacchetti decodificati")
    ap.add_argument("--max-nodes", type=int, default=200, metavar="N",
                    help="nodi da includere (predefinito 200)")
    return ap


def main(argv=None) -> int:
    _utf8_streams()
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.radio:
        host, _, p = args.radio.rpartition(":")
        if not host:
            host, p = args.radio, str(DEFAULT_RADIO_PORT)
        try:
            port = validate_port(int(p))
        except ValueError as exc:
            print(f"Errore: {exc}", file=sys.stderr)
            return 2
        print("Attenzione: la radio ha una sola connessione TCP alla volta: "
              "chiudi MeshLens/app prima di registrare.")
        try:
            st = record_live(host, port, args.seconds, out_path=args.out)
        except SessionError as exc:
            print(f"Errore: {exc}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"Errore: {exc.strerror or exc}", file=sys.stderr)
            return 1
        print(f"Sessione scritta in {args.out}: {st['packets']} pacchetti registrati, "
              f"{st['nodes']} nodi, {st['config']} blocchi di configurazione.")
        return 0
    try:
        sess, stats = session_from_db(
            args.db, since=args.since, until=args.until, limit=args.limit,
            include_mqtt=not args.no_mqtt, only_decoded=args.only_decoded,
            max_nodes=args.max_nodes)
        write_session(args.out, sess)
    except SessionError as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Errore: impossibile scrivere {args.out}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    sk = stats["skipped"]
    print(f"Sessione scritta in {args.out}: {stats['kept']} pacchetti registrati "
          f"su {stats['read']} letti, {len(sess.nodes)} nodi.")
    print(f"Saltati: {sk['no_raw']} senza dati, {sk['truncated']} troncati (>= {RAW_MAX} byte), "
          f"{sk['unknown_port']} con porta sconosciuta, {sk['bad_channel']} con canale non valido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# <<FIN>>
