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
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from meshtastic.protobuf import mesh_pb2

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
