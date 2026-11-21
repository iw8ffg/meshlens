"""Regole comuni di risposte e reazioni, per l'invio via radio e via MQTT."""
MAX_REACTION_BYTES = 16
MAX_PACKET_ID = 2**32 - 1
REACTION_NEEDS_REPLY = "La reazione richiede il messaggio a cui reagire"
INVALID_REACTION = "Reazione non valida"
INVALID_REPLY = "Messaggio di riferimento non valido"


def reply_problem(text: str, reply_id: int | None, emoji: bool) -> str | None:
    """Motivo per cui risposta o reazione non sono valide (None se valide). Condiviso
    dall'invio via radio e via MQTT."""
    if emoji and reply_id is None:
        return REACTION_NEEDS_REPLY
    if reply_id is not None and (not isinstance(reply_id, int) or isinstance(reply_id, bool)
                                 or not 1 <= reply_id <= MAX_PACKET_ID):
        return INVALID_REPLY
    if emoji and (len(text.encode("utf-8")) > MAX_REACTION_BYTES
                  or any(c.isspace() for c in text)):
        return INVALID_REACTION
    return None
