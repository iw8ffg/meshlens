"""ATAK (portnum 72): decodifica dei pacchetti TAKPacket con posizione (PLI) e servizio dei contatti.

I pacchetti arrivano anche da MQTT decifrati con la chiave sbagliata: i byte possono essere
qualsiasi cosa, quindi nessuna eccezione esce da `parse_tak`. Con `is_compressed` vero i testi
(nominativi) sono compressi e non si leggono: restano NULL. Se il messaggio intero non e'
analizzabile (testi compressi con byte non UTF-8) si ripiega su un lettore "a mano" del formato
binario che estrae solo i campi numerici (1, 3, 4, 5). Nessun log del contenuto dei pacchetti.
"""
import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Callable, Iterator

from google.protobuf.message import DecodeError
from meshtastic.protobuf import atak_pb2

from .events import AppData, MeshEvent, node_id

log = logging.getLogger(__name__)

MAX_TAK_BYTES = 4096
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


@dataclass(frozen=True)
class TakParsed:
    compressed: bool
    callsign: str | None
    device_callsign: str | None
    team: str | None            # Team.Name(v), None se 0/assente/sconosciuto
    role: str | None            # MemberRole.Name(v), idem
    battery: int | None         # 0..100, altrimenti None
    lat: float | None           # gradi (latitude_i * 1e-7), None senza fix valido
    lon: float | None
    altitude: int | None        # metri HAE; None senza fix
    speed: int | None
    course: int | None
    has_pli: bool               # campo 5 presente
    fallback: bool              # True se si e' usato il lettore a mano


def _clean(s: str | None) -> str | None:
    if not s:
        return None
    s = _CTRL.sub("", s).strip()[:64]
    return s or None


def _enum_name(enum, v: int) -> str | None:
    if not v:
        return None
    try:
        return enum.Name(v)
    except ValueError:
        return None


def _wire_fields(data: bytes) -> Iterator[tuple[int, int, object]]:
    """(numero_campo, tipo_wire, valore) per i tipi 0, 1, 2, 5; si ferma in silenzio su gruppi o dati troncati."""
    i, n = 0, len(data)

    def varint() -> int | None:
        nonlocal i
        shift = val = 0
        while i < n and shift < 70:
            b = data[i]
            i += 1
            val |= (b & 0x7F) << shift
            if not b & 0x80:
                return val
            shift += 7
        return None

    while i < n:
        key = varint()
        if key is None:
            return
        num, wt = key >> 3, key & 7
        if wt == 0:
            v = varint()
            if v is None:
                return
            yield num, wt, v
        elif wt == 2:
            ln = varint()
            if ln is None or i + ln > n:
                return
            yield num, wt, bytes(data[i:i + ln])
            i += ln
        elif wt in (1, 5):
            ln = 8 if wt == 1 else 4
            if i + ln > n:
                return
            yield num, wt, bytes(data[i:i + ln])
            i += ln
        else:
            return


def _build(compressed, callsign, device_callsign, group, status, pli, fallback) -> TakParsed | None:
    if pli is None:
        return None
    lat = pli.latitude_i * 1e-7
    lon = pli.longitude_i * 1e-7
    fix = not ((pli.latitude_i, pli.longitude_i) == (0, 0) or abs(lat) > 90 or abs(lon) > 180)
    battery = status.battery if status is not None and 0 <= status.battery <= 100 else None
    return TakParsed(
        compressed=compressed, callsign=callsign, device_callsign=device_callsign,
        team=_enum_name(atak_pb2.Team, group.team) if group is not None else None,
        role=_enum_name(atak_pb2.MemberRole, group.role) if group is not None else None,
        battery=battery,
        lat=lat if fix else None, lon=lon if fix else None,
        altitude=pli.altitude if fix else None,
        speed=pli.speed if fix and pli.speed >= 0 else None,
        course=pli.course if fix and pli.course >= 0 else None,
        has_pli=True, fallback=fallback)


def _parse_by_hand(payload: bytes) -> TakParsed | None:
    compressed, group, status, pli = False, None, None, None
    for num, wt, v in _wire_fields(payload):
        try:
            if num == 1 and wt == 0:
                compressed = bool(v)
            elif num == 3 and wt == 2:
                group = atak_pb2.Group.FromString(v)
            elif num == 4 and wt == 2:
                status = atak_pb2.Status.FromString(v)
            elif num == 5 and wt == 2:
                pli = atak_pb2.PLI.FromString(v)
        except (DecodeError, ValueError):
            continue
    return _build(compressed, None, None, group, status, pli, True)


def parse_tak(payload: bytes) -> TakParsed | None:
    """None se vuoto, troppo grande, irrecuperabile o senza campo pli. Non solleva mai."""
    try:
        if not payload or len(payload) > MAX_TAK_BYTES:
            return None
        try:
            msg = atak_pb2.TAKPacket.FromString(payload)
        except (DecodeError, ValueError):
            return _parse_by_hand(payload)
        comp = bool(msg.is_compressed)
        return _build(comp,
                      None if comp else _clean(msg.contact.callsign),
                      None if comp else _clean(msg.contact.device_callsign),
                      msg.group if msg.HasField("group") else None,
                      msg.status if msg.HasField("status") else None,
                      msg.pli if msg.HasField("pli") else None, False)
    except Exception:
        return None
