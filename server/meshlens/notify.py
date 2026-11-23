"""Notifiche esterne: toast di Windows (icona nell'area di notifica) e bot Telegram.

Il token di Telegram sta nell'URL delle richieste: ogni errore passa da scrub_text prima di
diventare un NotifyError, e le eccezioni originali non vengono concatenate (traceback)."""
import json
import logging
import threading
import unicodedata
import urllib.error
import urllib.request
from collections import deque
from typing import Callable, Iterable

from .settings import scrub_text

log = logging.getLogger(__name__)

# titolo e corpo di ogni notifica (segnaposto di str.format)
TEXTS: dict[str, tuple[str, str]] = {
    "mine_offline": ("{name} non risponde", "Nessun pacchetto da {hours} h"),
    "mine_online": ("{name} è tornato online", "Di nuovo sentito dopo {hours} h di silenzio"),
    "new_node": ("Nodo nuovo: {name}", "Sentito via radio per la prima volta"),
    "keyword": ("«{word}» in chat", "{name}: {text}"),
    "test": ("Prova di MeshLens", "Le notifiche funzionano"),
    # 1.6: avvisi delle regole su misura e del Detection Sensor
    "rule_keyword": ("Parola «{word}» in chat", "{name}: {text}"),
    "rule_snr": ("Segnale debole: {name}", "SNR medio {snr} dB (soglia {thr} dB)"),
    "rule_geofence_exit": ("{name} è uscito da «{zone}»", "Ultima posizione: {lat}, {lon}"),
    "rule_geofence_enter": ("{name} è entrato in «{zone}»", "Posizione: {lat}, {lon}"),
    "rule_battery": ("Batteria bassa: {name}", "Batteria al {pct}% (soglia {thr}%)"),
    "rule_silent": ("{name} non risponde", "Nessun pacchetto da {hours} h (soglia {thr} h)"),
    "sensor_detection": ("{name}: rilevamento", "{text}"),
}

TELEGRAM_NO_CHAT = "Scrivi un messaggio al bot su Telegram e riprova"
TOAST_UNAVAILABLE = ("Notifiche di Windows disponibili solo con MeshLens avviato dall'icona "
                     "nell'area di notifica")
TELEGRAM_NOT_CONFIGURED = "Inserisci il token del bot e l'id della chat"
TELEGRAM_BAD_REPLY = "Risposta di Telegram non valida"

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
QUIET_S = 300  # silenzio dopo l'avvio e dopo ogni cambio delle radio connesse
NEW_NODE_HEARD_S = 600  # un nodo "nuovo" deve essere stato sentito da poco
DEDUP_S = 600
MAX_PER_HOUR = 30
KEYWORD_PER_HOUR = 10  # le parole chiave hanno un budget proprio, piu' stretto
MESSAGE_MAX_AGE_S = 600  # messaggi piu' vecchi (replay di Store & Forward): niente notifica
# kind -> gruppo del budget orario; i kind non elencati stanno nel gruppo "other"
RULE_PER_HOUR = 20  # avvisi delle regole su misura: budget proprio
RULE_KINDS = ("rule_keyword", "rule_snr", "rule_geofence_exit", "rule_geofence_enter",
              "rule_battery", "rule_silent", "sensor_detection")
BUDGET_GROUP = {"keyword": "keyword", "mine_offline": "alerts", "mine_online": "alerts",
                **{k: "rule" for k in RULE_KINDS}}
BUDGET = {"keyword": KEYWORD_PER_HOUR, "alerts": MAX_PER_HOUR, "other": MAX_PER_HOUR,
          "rule": RULE_PER_HOUR}
KEYWORD_TEXT_MAX = 120


class NotifyError(Exception):
    """Invio non riuscito; il messaggio e' gia' ripulito dal token."""


def _secrets_of(token: str) -> tuple[str, ...]:
    # il token e' "<id del bot>:<segreto>": si ripuliscono sia l'intero sia il segreto
    return (token, token.partition(":")[2])


def _telegram_call(token: str, method: str, payload: dict | None, opener, timeout: float):
    url = TELEGRAM_API.format(token=token, method=method)
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="GET" if data is None else "POST",
                                 headers={"Content-Type": "application/json"})
    try:
        try:
            with opener(req, timeout=timeout) as r:
                body = json.loads(r.read(1_000_000).decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            text = str(e)
            try:  # Telegram spiega il motivo nel corpo ("Bad Request: chat not found")
                desc = json.loads(e.read(65536).decode("utf-8", "replace")).get("description")
            except Exception:  # noqa: BLE001 - corpo assente o non JSON
                desc = None
            raise NotifyError(f"{text}: {desc}" if desc else text) from None
        if not isinstance(body, dict) or not body.get("ok"):
            desc = body.get("description") if isinstance(body, dict) else None
            raise NotifyError(desc or TELEGRAM_BAD_REPLY)
        return body.get("result")
    except NotifyError as e:
        raise NotifyError(scrub_text(str(e), *_secrets_of(token))) from None
    except Exception as e:  # noqa: BLE001 - rete, timeout, JSON: tutto diventa NotifyError
        raise NotifyError(scrub_text(str(e) or type(e).__name__, *_secrets_of(token))) from None


def telegram_send(token: str, chat_id: str, text: str, opener=urllib.request.urlopen,
                  timeout: float = 10) -> None:
    _telegram_call(token, "sendMessage",
                   {"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                   opener, timeout)


def telegram_find_chat(token: str, opener=urllib.request.urlopen,
                       timeout: float = 10) -> tuple[str, str]:
    """Id e nome della chat dell'ultimo messaggio ricevuto dal bot."""
    updates = _telegram_call(token, "getUpdates", None, opener, timeout)
    for u in reversed(updates if isinstance(updates, list) else []):
        if not isinstance(u, dict):
            continue
        for k in ("message", "edited_message", "channel_post", "edited_channel_post"):
            chat = (u.get(k) or {}).get("chat") if isinstance(u.get(k), dict) else None
            if isinstance(chat, dict) and chat.get("id") is not None:
                return str(chat["id"]), str(chat.get("title") or chat.get("first_name") or "")
    raise NotifyError(TELEGRAM_NO_CHAT)


def fold(text: str) -> str:
    """Minuscole senza accenti, per confrontare le parole chiave ("Perché" ~ "perche")."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def _daemon(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="meshlens-notify", daemon=True).start()


def _node_name(n: dict) -> str:
    return n.get("long_name") or n.get("short_name") or n.get("id") or str(n.get("num"))


class Notifier:
    def __init__(self, get_settings: Callable[[], dict],
                 get_toast: Callable[[], Callable[[str, str], None] | None],
                 get_radios: Callable[[], list[dict]], clock: Callable[[], float],
                 send_telegram=telegram_send,
                 run_bg: Callable[[Callable[[], None]], None] = _daemon,
                 get_mqtt_connected: Callable[[], bool] = lambda: False):
        self.get_settings = get_settings
        self.get_toast = get_toast
        self.get_radios = get_radios
        self.clock = clock
        self.send_telegram = send_telegram
        self.run_bg = run_bg
        self.get_mqtt_connected = get_mqtt_connected
        self._known: set[int] = set()
        self._radio_ids: frozenset = frozenset()
        self._quiet_until = clock() + QUIET_S
        self._sent: dict[tuple[str, str], float] = {}  # (tipo, chiave) -> ultimo invio
        self._recent: dict[str, deque[float]] = {g: deque() for g in BUDGET}  # invii dell'ultima ora
        self._lock = threading.Lock()
        self.telegram_last_ok: float | None = None
        self.telegram_last_error: str | None = None

    # ---- eventi ----
    def seed(self, nodes: Iterable[dict]) -> None:
        self._known = {n["num"] for n in nodes if "rf" in (n.get("sources") or [])}
        self._quiet_until = self.clock() + QUIET_S

    def _track_radios(self, now: float) -> frozenset:
        """Radio collegate; se cambiano (arriva il loro database dei nodi) scatta il silenzio."""
        ids = frozenset(r.get("id") for r in self.get_radios() if r.get("state") == "connected")
        if ids != self._radio_ids:
            self._radio_ids = ids
            self._quiet_until = max(self._quiet_until, now + QUIET_S)
        return ids

    def on_nodes(self, changed: list[dict]) -> None:
        now = self.clock()
        self._track_radios(now)
        enabled = None
        for n in changed:
            num = n.get("num")
            if num is None or num in self._known or "rf" not in (n.get("sources") or []):
                continue
            self._known.add(num)
            if enabled is None:
                enabled = bool(self.get_settings().get("notify_new_node"))
            if (enabled and now >= self._quiet_until
                    and now - (n.get("last_heard") or 0) <= NEW_NODE_HEARD_S):
                self.send("new_node", str(num), name=_node_name(n))

    def on_alerts(self, old: list[dict], new: list[dict]) -> None:
        if not self.get_settings().get("notify_mine_status"):
            return
        now = self.clock()
        ids = self._track_radios(now)
        if now < self._quiet_until or not (ids or self.get_mqtt_connected()):
            return  # senza sorgenti collegate (o appena collegate) un nodo "muto" non e' una notizia
        before = {a["key"] for a in old}
        for a in new:
            if a["key"] in before:
                continue
            if a["key"].startswith("silent:"):
                self.send("mine_offline", a["key"], name=a["node_name"], hours=a["value"])
            elif a["key"].startswith("online:"):
                self.send("mine_online", a["key"], name=a["node_name"], hours=a["value"])

    def on_message(self, msg: dict) -> str | None:
        if msg.get("direction") != "in" or msg.get("emoji"):
            return None
        words = self.get_settings().get("notify_keywords") or []
        text = msg.get("text") or ""
        if not words or not text:
            return None
        t = msg.get("time")
        if isinstance(t, (int, float)) and self.clock() - t > MESSAGE_MAX_AGE_S:
            return None  # replay (Store & Forward dopo un'unione): non e' una novita'
        mine = {r.get("my_node_id") for r in self.get_radios() if r.get("my_node_id")}
        if msg.get("from") in mine:  # proprio messaggio sentito da un'altra radio locale
            return None
        folded = fold(text)
        word = next((w for w in words if fold(w) in folded), None)
        if word is None:
            return None
        self.send("keyword", str(msg.get("key")), word=word,
                  name=msg.get("from_name") or msg.get("from") or "", text=text[:KEYWORD_TEXT_MAX])
        return word

    # ---- invio ----
    def rules_ready(self, now: float | None = None) -> bool:
        """Le regole di stato possono notificare: fuori dal silenzio e con almeno una sorgente."""
        now = self.clock() if now is None else now
        ids = self._track_radios(now)
        return now >= self._quiet_until and bool(ids or self.get_mqtt_connected())

    def _admit(self, kind: str, dedup_key: str, dedup: bool = True) -> bool:
        now = self.clock()
        with self._lock:
            for k in [k for k, t in self._sent.items() if now - t >= DEDUP_S]:
                del self._sent[k]
            if dedup and (kind, dedup_key) in self._sent:
                return False
            group = BUDGET_GROUP.get(kind, "other")
            recent = self._recent[group]
            while recent and now - recent[0] >= 3600:
                recent.popleft()
            if len(recent) >= BUDGET[group]:
                return False
            if dedup:
                self._sent[(kind, dedup_key)] = now
            recent.append(now)
            return True

    def send(self, kind: str, dedup_key: str, *, dedup: bool = True, **fmt) -> None:
        s = self.get_settings()
        toast = self.get_toast() if s.get("notify_toast") else None
        token, chat_id = s.get("telegram_token") or "", s.get("telegram_chat_id") or ""
        telegram = bool(s.get("notify_telegram") and token and chat_id)
        if toast is None and not telegram:
            return
        if not self._admit(kind, dedup_key, dedup):
            return
        title, body = (t.format(**fmt) for t in TEXTS[kind])
        if toast is not None:
            try:
                toast(title, body)
            except Exception as e:  # noqa: BLE001 - il toast non deve mai fermare il server
                log.warning("Notifica di Windows non riuscita: %s", e)
        if telegram:
            # in un thread: Telegram lento o irraggiungibile non blocca il loop
            self.run_bg(lambda: self._telegram_bg(token, chat_id, f"{title}\n{body}"))

    def _telegram(self, token: str, chat_id: str, text: str) -> None:
        try:
            self.send_telegram(token, chat_id, text)
        except NotifyError as e:
            self.telegram_last_error = str(e)
            log.warning("Notifica Telegram non riuscita: %s", e)
            raise
        except Exception as e:  # noqa: BLE001 - un invio finto o inatteso: niente token nel testo
            msg = scrub_text(str(e) or type(e).__name__, *_secrets_of(token))
            self.telegram_last_error = msg
            log.warning("Notifica Telegram non riuscita: %s", msg)
            raise NotifyError(msg) from None
        self.telegram_last_ok = self.clock()
        self.telegram_last_error = None

    def _telegram_bg(self, token: str, chat_id: str, text: str) -> None:
        try:
            self._telegram(token, chat_id, text)
        except NotifyError:
            pass  # gia' registrato in telegram_last_error e nel log

    def test(self, channel: str) -> None:
        """Invio di prova sincrono (Telegram: chiamare fuori dal loop); solleva NotifyError."""
        title, body = TEXTS["test"]
        if channel == "toast":
            toast = self.get_toast()
            if toast is None:
                raise NotifyError(TOAST_UNAVAILABLE)
            try:
                toast(title, body)
            except Exception as e:  # noqa: BLE001
                raise NotifyError(str(e) or type(e).__name__) from None
        elif channel == "telegram":
            s = self.get_settings()
            token, chat_id = s.get("telegram_token") or "", s.get("telegram_chat_id") or ""
            if not (token and chat_id):
                raise NotifyError(TELEGRAM_NOT_CONFIGURED)
            self._telegram(token, chat_id, f"{title}\n{body}")
        else:
            raise NotifyError(f"Canale sconosciuto: {channel}")

    def status(self) -> dict:
        return {"toast_available": self.get_toast() is not None,
                "telegram_last_ok": self.telegram_last_ok,
                "telegram_last_error": self.telegram_last_error}
