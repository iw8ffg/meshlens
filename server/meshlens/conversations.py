"""Conversazioni radio: chiave, riepilogo e conteggio dei non letti.

Le regole della chiave sono identiche a `conversationKey` di web/src/lib/chat.ts.
"""
from .events import node_id
from .ingest import icon_char

BROADCAST_ID = "!ffffffff"


def conversation_key(msg: dict, local_ids: set[str]) -> str | None:
    radio = msg.get("radio_id")
    if not radio:
        return None
    if msg.get("to") == BROADCAST_ID:
        return f"ch:{radio}:{msg.get('channel_index') or 0}"
    if msg.get("direction") == "out" or msg.get("from") in local_ids:
        peer = msg.get("to")
    else:
        peer = msg.get("from")
    return f"dm:{radio}:{peer}"


def summaries(msgs: list[dict], local_ids: set[str], reads: dict[str, float],
              baseline: float) -> list[dict]:
    out: dict[str, dict] = {}
    for m in msgs:
        key = conversation_key(m, local_ids)
        if key is None:
            continue
        item = out.get(key)
        if item is None:
            read_time = reads.get(key)
            item = out[key] = {"key": key, "last_time": None, "last_text": None,
                               "last_from": None, "last_emoji": False, "unread": 0,
                               "read_time": read_time}
        if item["last_time"] is None or m["time"] >= item["last_time"]:
            item.update(last_time=m["time"], last_text=m.get("text"), last_from=m.get("from"),
                        last_emoji=bool(m.get("emoji")))
        if (m.get("direction") == "in" and m.get("from") not in local_ids
                and not m.get("emoji")
                and m["time"] > max(item["read_time"] or 0, baseline)):
            item["unread"] += 1
    return sorted(out.values(), key=lambda s: s["last_time"], reverse=True)


def waypoint_json(row: dict, nodes: dict, local_nums: set[int]) -> dict:
    """Waypoint come lo vede l'interfaccia, da una riga del database."""
    num = row["from_num"]
    node = nodes.get(num)
    return {"id": row["id"], "from": node_id(num), "from_name": node["long_name"] if node else None,
            "lat": row["lat"], "lon": row["lon"], "name": row["name"],
            "description": row["description"] or "", "icon": icon_char(row["icon"] or 0),
            "expire": row["expire"] or None,
            "locked_to": node_id(row["locked_to"]) if row["locked_to"] else None,
            "time": int(row["time"]), "source": row["source"], "radio_id": row["radio_id"],
            "channel": row["channel"], "mine": num in local_nums}
