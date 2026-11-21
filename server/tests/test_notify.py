import io
import json
import urllib.error

import pytest

from meshlens import notify
from meshlens.notify import (TELEGRAM_NO_CHAT, NotifyError, Notifier, fold, telegram_find_chat,
                             telegram_send)

TOKEN = "123456:AAH-secret_token_value"


class Clock:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def settings(**over) -> dict:
    s = {"notify_toast": True, "notify_telegram": True, "telegram_token": TOKEN,
         "telegram_chat_id": "42", "notify_mine_status": True, "notify_new_node": True,
         "notify_keywords": []}
    s.update(over)
    return s


def make(clock=None, radios=None, **over):
    clock = clock or Clock()
    s = settings(**over)
    toasts: list[tuple[str, str]] = []
    sent: list[tuple[str, str, str]] = []
    radios = radios if radios is not None else []
    n = Notifier(lambda: s, lambda: (lambda t, b: toasts.append((t, b))), lambda: radios, clock,
                 send_telegram=lambda tok, chat, text: sent.append((tok, chat, text)),
                 run_bg=lambda f: f())
    return n, clock, s, toasts, sent, radios


def rf_node(num: int, heard: float, name: str = "Nodo") -> dict:
    return {"num": num, "id": f"!{num:08x}", "long_name": name, "sources": ["rf"],
            "last_heard": heard}


def test_quiet_after_start_and_radio_change():
    n, clock, _s, toasts, sent, radios = make()
    n.seed([rf_node(1, clock.t), {"num": 2, "sources": ["mqtt"], "last_heard": clock.t}])
    clock.t += 100
    n.on_nodes([rf_node(3, clock.t)])  # nel silenzio iniziale: diventa noto, niente avviso
    assert toasts == [] and sent == []
    clock.t += 250
    n.on_nodes([rf_node(3, clock.t)])  # gia' noto
    n.on_nodes([rf_node(1, clock.t)])  # dal seed
    assert toasts == []
    n.on_nodes([rf_node(4, clock.t, "Nuovo")])
    assert toasts == [("Nodo nuovo: Nuovo", "Sentito via radio per la prima volta")]
    assert sent == [(TOKEN, "42", "Nodo nuovo: Nuovo\nSentito via radio per la prima volta")]
    radios.append({"id": "r1", "state": "connected"})
    clock.t += 10
    n.on_nodes([rf_node(5, clock.t)])  # radio collegata: altri 300 s di silenzio
    clock.t += 280
    n.on_nodes([rf_node(6, clock.t)])
    assert len(toasts) == 1
    clock.t += 30
    n.on_nodes([rf_node(5, clock.t), rf_node(6, clock.t)])  # noti nel silenzio
    n.on_nodes([rf_node(7, clock.t, "Sette")])
    assert toasts[-1][0] == "Nodo nuovo: Sette" and len(toasts) == 2


def test_new_node_needs_setting_and_recent_heard():
    n, clock, s, toasts, _sent, _r = make(notify_new_node=False)
    n.seed([])
    clock.t += 400
    n.on_nodes([rf_node(1, clock.t)])
    assert toasts == []
    s["notify_new_node"] = True
    n.on_nodes([rf_node(2, clock.t - 700)])  # sentito troppo tempo fa (database della radio)
    assert toasts == []
    n.on_nodes([{"num": 3, "sources": ["mqtt"], "last_heard": clock.t}])  # non via radio
    assert toasts == []
    n.on_nodes([rf_node(4, clock.t - 500)])
    assert len(toasts) == 1


SILENT = {"key": "silent:!00000001", "kind": "silent", "node_id": "!00000001",
          "node_name": "Base", "value": 7, "since": 0}
ONLINE = {"key": "online:!00000001", "kind": "back_online", "node_id": "!00000001",
          "node_name": "Base", "value": 7, "since": 0}


def test_mine_status_transitions():
    n, clock, s, toasts, _sent, radios = make()
    radios.append({"id": "r1", "state": "connected"})
    n.on_alerts([], [])  # registra la radio: silenzio di 300 s
    clock.t += 301
    n.on_alerts([], [SILENT])
    assert toasts == [("Base non risponde", "Nessun pacchetto da 7 h")]
    n.on_alerts([], [SILENT])  # stessa coppia: nessun doppione
    n.on_alerts([SILENT], [{**SILENT, "value": 8}])  # cambia solo il valore
    assert len(toasts) == 1
    n.on_alerts([SILENT], [ONLINE])
    assert toasts[-1] == ("Base è tornato online", "Di nuovo sentito dopo 7 h di silenzio")
    s["notify_mine_status"] = False
    n.on_alerts([], [{**SILENT, "key": "silent:!00000002", "node_name": "Altro"}])
    assert len(toasts) == 2


def test_alerts_silent_without_sources_or_during_quiet():
    mqtt = {"up": False}
    clock = Clock()
    s = settings()
    toasts = []
    radios = []
    n = Notifier(lambda: s, lambda: (lambda t, b: toasts.append((t, b))), lambda: radios, clock,
                 send_telegram=lambda *a: None, run_bg=lambda f: f(),
                 get_mqtt_connected=lambda: mqtt["up"])
    clock.t += 1000
    n.on_alerts([], [SILENT])  # nessuna radio ne' broker: niente
    assert toasts == []
    mqtt["up"] = True
    n.on_alerts([], [{**SILENT, "key": "silent:!00000002"}])
    assert len(toasts) == 1
    radios.append({"id": "r1", "state": "connected"})  # cambio delle radio: altri 300 s
    n.on_alerts([], [ONLINE])
    assert len(toasts) == 1
    clock.t += 301
    n.on_alerts([], [ONLINE])
    assert len(toasts) == 2


def test_message_replay_ignored_and_keyword_budget():
    n, clock, _s, toasts, _sent, _r = make(notify_keywords=["aiuto"])
    assert n.on_message(msg("aiuto", key="9:old", time=clock.t - 601)) is None
    assert n.on_message(msg("aiuto", key="9:new", time=clock.t - 599)) == "aiuto"
    for i in range(12):
        n.on_message(msg("aiuto", key=f"9:k{i}", time=clock.t))
    assert len(toasts) == 10  # budget orario delle parole chiave


def test_alert_budget_independent_of_keywords():
    n, clock, _s, toasts, _sent, radios = make(notify_keywords=["aiuto"])
    radios.append({"id": "r1", "state": "connected"})
    n.on_alerts([], [])
    clock.t += 301
    for i in range(12):
        n.on_message(msg("aiuto", key=f"9:k{i}"))
    n.on_alerts([], [{**SILENT, "key": "silent:!00000003"}])
    assert len(toasts) == 11


def msg(text: str, **over) -> dict:
    m = {"key": f"9:{abs(hash(text))}", "from": "!00000009", "from_name": "Mario",
         "text": text, "direction": "in", "emoji": False}
    m.update(over)
    return m


def test_keyword_folding():
    n, _clock, _s, toasts, _sent, _r = make(notify_keywords=["perche"])
    assert fold("Perché ÀÉ ﬁ") == "perche ae fi"
    assert n.on_message(msg("Perché no?")) == "perche"
    assert toasts == [("«perche» in chat", "Mario: Perché no?")]
    assert n.on_message(msg("perché", emoji=True)) is None
    assert n.on_message(msg("perché sì", direction="out")) is None
    assert n.on_message(msg("altro testo")) is None
    long = "perche " + "x" * 300
    n.on_message(msg(long, key="9:long"))
    assert toasts[-1][1] == "Mario: " + long[:120]


def test_keyword_ignores_own_radio_nodes():
    n, _clock, _s, toasts, _sent, radios = make(notify_keywords=["aiuto"])
    radios.append({"id": "r1", "state": "connected", "my_node_id": "!00000009"})
    assert n.on_message(msg("aiuto")) is None and toasts == []


def test_rate_and_dedup():
    n, clock, _s, toasts, sent, _r = make(notify_keywords=[f"parola{i:02d}" for i in range(20)])
    words = [f"parola{i:02d}" for i in range(20)]
    for i in range(31):
        clock.t += 60
        n.on_message(msg(words[i % 20], key=f"9:{i}"))
    assert len(toasts) == 10 and len(sent) == 10
    clock.t += 3600  # dopo un'ora il limite si libera
    n.on_message(msg(words[0], key="9:new"))
    assert len(toasts) == 11


def test_no_channel_enabled_sends_nothing():
    n, _clock, _s, toasts, sent, _r = make(notify_toast=False, notify_telegram=False)
    n.send("test", "x")
    assert toasts == [] and sent == []
    n2, _c, _s2, toasts2, sent2, _r2 = make(telegram_chat_id="")
    n2.send("test", "x")
    assert len(toasts2) == 1 and sent2 == []


def test_toast_error_is_swallowed():
    def boom(_t, _b):
        raise RuntimeError("shell non disponibile")
    sent = []
    n = Notifier(lambda: settings(), lambda: boom, lambda: [], Clock(),
                 send_telegram=lambda *a: sent.append(a), run_bg=lambda f: f())
    n.send("test", "x")
    assert len(sent) == 1


def test_telegram_error_scrubbed():
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    def opener(req, timeout=None):
        raise urllib.error.HTTPError(url, 401, f"Unauthorized for {url}", {},
                                     io.BytesIO(b'{"ok":false,"description":"Unauthorized"}'))

    with pytest.raises(NotifyError) as ei:
        telegram_send(TOKEN, "42", "ciao", opener=opener)
    assert TOKEN not in str(ei.value) and "secret_token_value" not in str(ei.value)
    assert "401" in str(ei.value) and ei.value.__cause__ is None

    def failing(tok, chat, text):
        telegram_send(tok, chat, text, opener=opener)

    n = Notifier(lambda: settings(notify_toast=False), lambda: None, lambda: [], Clock(),
                 send_telegram=failing, run_bg=lambda f: f())
    n.send("test", "x")
    st = n.status()
    assert st["toast_available"] is False and st["telegram_last_ok"] is None
    assert st["telegram_last_error"] and TOKEN not in st["telegram_last_error"]
    with pytest.raises(NotifyError) as ei2:
        n.test("telegram")
    assert TOKEN not in str(ei2.value)


def test_telegram_send_request():
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(req, timeout=None):
        seen["url"], seen["method"] = req.full_url, req.get_method()
        seen["body"], seen["timeout"] = json.loads(req.data), timeout
        return Resp(b'{"ok":true,"result":{}}')

    telegram_send(TOKEN, "-100123", "testo", opener=opener)
    assert seen["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert seen["method"] == "POST" and seen["timeout"] == 10
    assert seen["body"] == {"chat_id": "-100123", "text": "testo",
                            "disable_web_page_preview": True}


def test_find_chat():
    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener_for(updates):
        def opener(req, timeout=None):
            assert req.full_url == f"https://api.telegram.org/bot{TOKEN}/getUpdates"
            return Resp(json.dumps({"ok": True, "result": updates}).encode())
        return opener

    updates = [{"update_id": 1, "message": {"chat": {"id": 11, "type": "private",
                                                     "first_name": "Primo"}}},
               {"update_id": 2, "message": {"chat": {"id": -1002, "type": "group",
                                                     "title": "Gruppo"}}}]
    assert telegram_find_chat(TOKEN, opener=opener_for(updates)) == ("-1002", "Gruppo")
    assert telegram_find_chat(TOKEN, opener=opener_for(updates[:1])) == ("11", "Primo")
    with pytest.raises(NotifyError) as ei:
        telegram_find_chat(TOKEN, opener=opener_for([]))
    assert str(ei.value) == TELEGRAM_NO_CHAT


def test_test_toast_unavailable():
    n = Notifier(lambda: settings(), lambda: None, lambda: [], Clock(),
                 send_telegram=lambda *a: None, run_bg=lambda f: f())
    with pytest.raises(NotifyError) as ei:
        n.test("toast")
    assert str(ei.value) == notify.TOAST_UNAVAILABLE


def test_texts_exact():
    assert notify.TEXTS["keyword"] == ("«{word}» in chat", "{name}: {text}")
    assert notify.TEXTS["test"] == ("Prova di MeshLens", "Le notifiche funzionano")
    assert notify.QUIET_S == 300 and notify.DEDUP_S == 600 and notify.MAX_PER_HOUR == 30
