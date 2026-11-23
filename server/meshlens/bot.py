"""Bot di MeshLens (E15): risponde a comandi espliciti sui canali scelti dall'utente.

Regole (contratto §0.7, §6.5 e decisione R5.2):
- risponde solo a messaggi di canale dal vivo il cui testo INIZIA con un comando abilitato
  o con una parola personalizzata; mai a testi che iniziano col marcatore "[bot]" e mai ai
  nodi visti usarlo (altri bot);
- risposte in italiano, sempre con il prefisso "[bot] ", al massimo 200 byte UTF-8, mai con
  nomi di nodi o testo altrui;
- invio solo attraverso RadioManager.send / MqttSender.send (conferma pubblica mai data in
  automatico), mai override del duty cycle; coda con limiti e pausa sui rifiuti del firmware.
"""
import time
from dataclasses import dataclass

BOT_MARK = "[bot]"
MAX_REPLY_BYTES = 200

# parola del comando (casefold) -> nome del comando (settings.BOT_COMMANDS)
COMMAND_WORDS: dict[str, str] = {
    "!ping": "ping", "!info": "info", "!nodi": "nodes", "!nodes": "nodes",
    "!ora": "time", "!time": "time", "!meteo": "weather", "!weather": "weather",
}


@dataclass(frozen=True)
class Request:
    kind: str  # "command" | "reply"
    name: str  # nome del comando o trigger della risposta personalizzata
    reply_text: str | None  # solo "reply": testo scelto dall'utente


@dataclass(frozen=True)
class ReplyContext:
    snr: float | None
    rssi: int | None
    hops: int | None
    via_mqtt: bool
    version: str
    now: float
    nodes_active_1h: int
    nodes_total: int
    heard_1h: int
    heard_24h: int
    weather: dict | None  # None = nodo meteo non valido (nessuna risposta)


def clamp_utf8(text: str, max_bytes: int = MAX_REPLY_BYTES) -> str:
    """Taglia a max_bytes byte UTF-8 su un confine di carattere."""
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    return data[:max_bytes].decode("utf-8", errors="ignore")


def is_marked(text: str) -> bool:
    """Testo che inizia col marcatore delle risposte di un bot (senza maiuscole)."""
    return (text or "").strip().casefold().startswith(BOT_MARK)


def parse_request(text: str, commands: list[str], replies: list[dict]) -> Request | None:
    """Richiesta esplicita: il testo inizia con la parola di un comando abilitato (prima
    parola) o con un trigger di bot_replies seguito da fine testo o da un carattere non
    alfanumerico. I comandi integrati hanno la precedenza."""
    stripped = (text or "").strip()
    if not stripped or is_marked(stripped):
        return None
    word = stripped.split()[0].casefold()
    name = COMMAND_WORDS.get(word)
    if name is not None and name in commands:
        return Request("command", name, None)
    folded = stripped.casefold()
    for r in replies or []:
        trigger = (r.get("trigger") or "").casefold()
        if not trigger or not folded.startswith(trigger):
            continue
        rest = folded[len(trigger):]
        if rest and rest[0].isalnum():
            continue
        return Request("reply", r["trigger"], r.get("text") or "")
    return None


def match_target(msg: dict, targets: list[dict]) -> dict | None:
    """Bersaglio di bot_targets a cui appartiene il messaggio (radio+canale o broker+canale)."""
    for t in targets or []:
        if t.get("kind") == "radio":
            if (msg.get("source") == "rf" and msg.get("radio_id") == t.get("radio_id")
                    and msg.get("channel_index") == t.get("channel_index")):
                return t
        elif t.get("kind") == "mqtt":
            if (msg.get("source") == "mqtt" and msg.get("broker") == t.get("broker")
                    and msg.get("channel") == t.get("channel")):
                return t
    return None


def _hops_text(hops: int | None) -> str:
    if hops is None:
        return "salti n/d"
    if hops == 0:
        return "diretto"
    return "1 salto" if hops == 1 else f"{hops} salti"


def _weather_text(w: dict) -> str:
    parts = []
    if w.get("temperature") is not None:
        parts.append(f"{w['temperature']:.1f} °C")
    if w.get("relative_humidity") is not None:
        parts.append(f"UR {w['relative_humidity']:.0f}%")
    if w.get("barometric_pressure") is not None:
        parts.append(f"{w['barometric_pressure']:.0f} hPa")
    if not parts:
        return f"{BOT_MARK} Meteo non disponibile"
    return f"{BOT_MARK} Meteo: " + ", ".join(parts)


def build_reply(request: Request, ctx: ReplyContext) -> str | None:
    """Testo della risposta (con prefisso, tagliato a 200 byte) o None se non si risponde."""
    if request.kind == "reply":
        text = f"{BOT_MARK} {request.reply_text or ''}"
    elif request.name == "ping":
        if ctx.via_mqtt:
            text = f"{BOT_MARK} pong! via MQTT, {_hops_text(ctx.hops)}"
        else:
            snr = "n/d" if ctx.snr is None else f"{ctx.snr:+.1f} dB"
            rssi = "n/d" if ctx.rssi is None else f"{int(ctx.rssi)} dBm"
            text = f"{BOT_MARK} pong! SNR {snr}, RSSI {rssi}, {_hops_text(ctx.hops)}"
    elif request.name == "info":
        text = (f"{BOT_MARK} MeshLens {ctx.version}: {ctx.nodes_active_1h} nodi attivi "
                f"nell'ultima ora, {ctx.nodes_total} noti")
    elif request.name == "nodes":
        text = (f"{BOT_MARK} Nodi sentiti: {ctx.heard_1h} nell'ultima ora, "
                f"{ctx.heard_24h} nelle ultime 24 h")
    elif request.name == "time":
        text = time.strftime(f"{BOT_MARK} Ora: %H:%M del %d/%m/%Y", time.localtime(ctx.now))
    elif request.name == "weather":
        if ctx.weather is None:
            return None
        text = _weather_text(ctx.weather)
    else:
        return None
    return clamp_utf8(text)
