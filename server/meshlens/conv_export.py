"""Esportazione dei messaggi di una conversazione (E4).

Modulo puro, solo lettura: restituisce i dati; i file TXT/CSV/JSON si costruiscono nel browser
(separatore e virgola decimale dipendono dalla lingua dell'interfaccia). Le righe sono quelle di
`/api/messages` piu' `to_name`; nessun campo grezzo del database. I messaggi dei mittenti ignorati
restano nascosti (§4.6) come ovunque.
"""
from __future__ import annotations

import sqlite3

from .msgsearch import MQTT_KEY_RE, _nums, conv_where  # noqa: F401  (MQTT_KEY_RE: ri-esportata)
from .store import Store, not_ignored_sender_sql

EXPORT_MAX = 20000


def export_conversation(conn: sqlite3.Connection, key: str, local_ids, *,
                        since: float | None = None, until: float | None = None,
                        limit: int = EXPORT_MAX) -> dict:
    """Messaggi della conversazione `key` in ordine cronologico crescente.
    Oltre `limit` righe si tengono le piu' recenti e `truncated` e' vero.
    ValueError("Conversazione non valida") se la chiave non e' riconosciuta."""
    sql_c, params = conv_where(key, _nums(local_ids))
    where = [f"({sql_c})", not_ignored_sender_sql("m")]
    if since is not None:
        where.append("m.time >= ?")
        params.append(since)
    if until is not None:
        where.append("m.time <= ?")
        params.append(until)
    cond = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM messages m WHERE {cond}", params).fetchone()[0]
    limit = max(1, int(limit))
    rows = conn.execute(
        "SELECT m.*, n.long_name AS from_name, t.long_name AS to_name "
        "FROM messages m LEFT JOIN nodes n ON n.num = m.from_num "
        "LEFT JOIN nodes t ON t.num = m.to_num "
        f"WHERE {cond} ORDER BY m.time DESC, m.rowid DESC LIMIT ?", [*params, limit]).fetchall()
    rows.reverse()
    messages = [{**Store._message_row(r), "to_name": r["to_name"]} for r in rows]
    return {"key": key, "messages": messages, "total": total, "truncated": total > len(messages)}
