"""Ricerca nel testo dei messaggi e nei nodi (E2/E4, contratto §1.3 e §6.1).

Modulo puro: riceve una connessione SQLite (anche in sola lettura, `queries.ro_connect`) e non
scrive mai. Con FTS5 (`db.search_engine`) usa l'indice `messages_fts`; altrimenti, o se la query
FTS non e' utilizzabile, ripiega su LIKE (sottostringa, senza distinzione di maiuscole ASCII).
Nessun valore dell'utente finisce nel testo SQL: solo parametri; i frammenti di clausola sono
costanti del codice. I messaggi dei mittenti ignorati sono esclusi (decisione dell'utente, §4.6).
"""
from __future__ import annotations

import math
import re
import sqlite3
import unicodedata

from . import db
from .conversations import conversation_key
from .store import Store, not_ignored_sender_sql

SNIP_OPEN = "\x02"
SNIP_CLOSE = "\x03"
MAX_QUERY_CHARS = 200
MAX_TERMS = 8
MAX_TERM_CHARS = 64
LIMIT_MAX = 100
BROADCAST_NUM = 0xFFFFFFFF
SNIPPET_WINDOW = 60
SNIPPET_LEAD = 20

CH_KEY_RE = re.compile(r"^ch:(r[0-9a-f]{6,16}):(\d{1,3})$")
DM_KEY_RE = re.compile(r"^dm:(r[0-9a-f]{6,16}):(![0-9a-f]{8})$")
MQTT_KEY_RE = re.compile(r"^mqtt(?::([a-z0-9-]{1,24}))?$")


class InvalidCursor(ValueError):
    """Cursore di paginazione malformato."""


def _terms(q: str) -> list[str]:
    """Parole della query (max MAX_TERMS, ognuna <= MAX_TERM_CHARS caratteri)."""
    return [w for w in q.split() if len(w) <= MAX_TERM_CHARS][:MAX_TERMS]


def fts_query(q: str) -> str | None:
    """Query FTS5 sicura: ogni parola come "parola"* (virgolette interne raddoppiate), in AND.
    None se nessuna parola contiene un carattere alfanumerico."""
    out = []
    for w in _terms(q):
        if not any(ch.isalnum() for ch in w):
            continue
        out.append('"' + w.replace('"', '""') + '"*')
    return " ".join(out) if out else None


def like_pattern(term: str) -> str:
    """Pattern LIKE `%term%` con `\\`, `%` e `_` letterali (da usare con ESCAPE '\\')."""
    esc = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def parse_cursor(cursor: str) -> tuple[float, str]:
    """Cursore "<time>:<key>" (la chiave puo' contenere ':': si divide sul primo)."""
    head, sep, key = (cursor or "").partition(":")
    if not sep:
        raise InvalidCursor("Cursore di ricerca non valido")
    try:
        t = float(head)
    except ValueError:
        raise InvalidCursor("Cursore di ricerca non valido") from None
    if not math.isfinite(t):
        raise InvalidCursor("Cursore di ricerca non valido")
    return t, key


def _nums(ids) -> list[int]:
    out = []
    for i in ids or ():
        try:
            out.append(int(i[1:], 16))
        except (ValueError, TypeError):
            continue
    return out


def conv_where(key: str, local_nums) -> tuple[str, list]:
    """Clausola SQL (su messages con alias `m`) e parametri di una chiave di conversazione.
    ValueError("Conversazione non valida") se la chiave non e' riconosciuta."""
    if m := CH_KEY_RE.match(key):
        return ("m.radio_id = ? AND m.to_num = ? AND COALESCE(m.channel_index, 0) = ?",
                [m.group(1), BROADCAST_NUM, int(m.group(2))])
    if m := DM_KEY_RE.match(key):
        radio, peer = m.group(1), int(m.group(2)[1:], 16)
        nums = sorted(set(local_nums or ()))
        if nums:
            ph = ",".join("?" * len(nums))
            mine = f"(m.direction = 'out' OR m.from_num IN ({ph}))"
            params = [radio, BROADCAST_NUM, *nums, peer, *nums, peer]  # `mine` compare due volte
        else:
            mine = "(m.direction = 'out')"
            params = [radio, BROADCAST_NUM, peer, peer]
        sql = (f"m.radio_id = ? AND m.to_num <> ? AND (({mine} AND m.to_num = ?) "
               f"OR (NOT {mine} AND m.from_num = ?))")
        return sql, params
    if m := MQTT_KEY_RE.match(key):
        if m.group(1):
            return "m.radio_id IS NULL AND m.broker = ?", [m.group(1)]
        return "m.radio_id IS NULL", []
    raise ValueError("Conversazione non valida")


def _fold_char(c: str) -> str:
    """Minuscola senza accento, sempre di un solo carattere (le posizioni restano allineate)."""
    base = unicodedata.normalize("NFD", c)[:1] or c
    low = base.lower()
    return low if len(low) == 1 else c


def _fold_text(text: str) -> str:
    return "".join(_fold_char(c) for c in text)


def _like_snippet(text: str, terms: list[str], prefix: bool = False) -> str:
    """Finestra di ~60 caratteri attorno alla prima occorrenza; parole tra i marcatori.
    Il confronto ignora maiuscole e accenti (come l'indice FTS5); con `prefix` i termini
    alfanumerici valgono solo a inizio parola (come "termine"* di FTS5)."""
    folded = _fold_text(text)
    lead = r"(?<![^\W_])" if prefix else ""
    pat = (re.compile("|".join((lead if any(c.isalnum() for c in t) else "") + re.escape(_fold_text(t))
                               for t in terms)) if terms else None)
    first = pat.search(folded) if pat else None
    start = max(0, first.start() - SNIPPET_LEAD) if first else 0
    end = min(len(text), start + SNIPPET_WINDOW)
    out, pos = [], start
    if pat:
        for m in pat.finditer(folded, start, end):
            out.append(text[pos:m.start()] + SNIP_OPEN + text[m.start():m.end()] + SNIP_CLOSE)
            pos = m.end()
    out.append(text[pos:end])
    return ("…" if start > 0 else "") + "".join(out) + ("…" if end < len(text) else "")


def search_messages(conn: sqlite3.Connection, q: str, *, conv: str | None = None,
                    sender: int | None = None, since: float | None = None,
                    until: float | None = None, cursor: str | None = None, limit: int = 50,
                    local_ids=frozenset()) -> dict:
    """Cerca `q` nel testo dei messaggi. Risposta: {"hits": [{"message", "snippet", "conv"}],
    "next": cursore | None, "engine": "fts5" | "like"}. Ordine `time DESC, key DESC`."""
    engine = db.search_engine(conn)
    q = (q or "").strip()[:MAX_QUERY_CHARS]
    if not q:
        return {"hits": [], "next": None, "engine": engine}
    limit = max(1, min(int(limit), LIMIT_MAX))
    local_nums = _nums(local_ids)

    where = ["m.text IS NOT NULL", "m.text <> ''", "COALESCE(m.emoji, 0) = 0",
             not_ignored_sender_sql("m")]
    where_params: list = []
    if conv:
        sql_c, p = conv_where(conv, local_nums)
        where.append(f"({sql_c})")
        where_params += p
    if sender is not None:
        where.append("m.from_num = ?")
        where_params.append(sender)
    if since is not None:
        where.append("m.time >= ?")
        where_params.append(since)
    if until is not None:
        where.append("m.time <= ?")
        where_params.append(until)
    if cursor:
        ct, ck = parse_cursor(cursor)
        where.append("(m.time < ? OR (m.time = ? AND m.key < ?))")
        where_params += [ct, ct, ck]

    base = "FROM messages m LEFT JOIN nodes n ON n.num = m.from_num"
    tail = " ORDER BY m.time DESC, m.key DESC LIMIT ?"
    rows = None
    used_engine = "like"
    fq = fts_query(q) if engine == "fts5" else None
    if fq is not None:
        # i termini senza caratteri alfanumerici non entrano nell'indice FTS: restano come LIKE
        # (stesso risultato del ripiego su LIKE)
        extra = [t for t in _terms(q) if not any(ch.isalnum() for ch in t)]
        fts_where = where + ["m.text LIKE ? ESCAPE '\\'" for _ in extra]
        fts_params = [*where_params, *(like_pattern(t) for t in extra)]
        # il frammento si ricava in Python sulle sole righe restituite: snippet() di FTS5 girerebbe
        # su ogni riga trovata prima di ORDER BY/LIMIT
        sql = (f"SELECT m.*, n.long_name AS from_name "
               f"{base} JOIN messages_fts ON messages_fts.rowid = m.rowid "
               f"WHERE messages_fts MATCH ? AND " + " AND ".join(fts_where) + tail)
        try:
            rows = conn.execute(sql, [fq, *fts_params, limit + 1]).fetchall()
            used_engine = "fts5"
        except sqlite3.OperationalError:
            rows = None
    terms = _terms(q)
    if rows is None:
        if not terms:
            return {"hits": [], "next": None, "engine": "like"}
        likes = " AND ".join("m.text LIKE ? ESCAPE '\\'" for _ in terms)
        sql = (f"SELECT m.*, n.long_name AS from_name, NULL AS snip {base} "
               f"WHERE {likes} AND " + " AND ".join(where) + tail)
        rows = conn.execute(
            sql, [*(like_pattern(t) for t in terms), *where_params, limit + 1]).fetchall()

    more = len(rows) > limit
    rows = rows[:limit]
    hits = []
    for r in rows:
        msg = Store._message_row(r)
        snippet = _like_snippet(r["text"], terms, prefix=used_engine == "fts5")
        hits.append({"message": msg, "snippet": snippet,
                     "conv": conversation_key(msg, set(local_ids))})
    nxt = None
    if more and rows:
        last = rows[-1]
        nxt = f"{float(last['time'])!r}:{last['key']}"
    return {"hits": hits, "next": nxt, "engine": used_engine}


def search_nodes(conn: sqlite3.Connection, q: str, limit: int = 8) -> list[dict]:
    """Nodi per nome lungo, sigla o id esadecimale (`!` facoltativo, minimo 2 caratteri);
    esclusi gli ignorati, piu' recenti prima."""
    q = (q or "").strip()[:MAX_QUERY_CHARS]
    bare = q[1:] if q.startswith("!") else q
    if len(bare) < 2:
        return []
    pat = like_pattern(bare)
    rows = conn.execute(
        "SELECT id, long_name, short_name, hw_model, last_heard, is_mine, is_favorite FROM nodes "
        "WHERE COALESCE(is_ignored, 0) = 0 AND (long_name LIKE ? ESCAPE '\\' "
        "OR short_name LIKE ? ESCAPE '\\' OR id LIKE ? ESCAPE '\\') "
        "ORDER BY last_heard IS NULL, last_heard DESC, num LIMIT ?",
        (pat, pat, pat, max(1, min(int(limit), LIMIT_MAX)))).fetchall()
    return [{"id": r["id"], "long_name": r["long_name"], "short_name": r["short_name"],
             "hw_model": r["hw_model"], "last_heard": r["last_heard"],
             "is_mine": bool(r["is_mine"]), "is_favorite": bool(r["is_favorite"])} for r in rows]
