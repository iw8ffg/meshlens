"""Catalogo inglese dei messaggi del server: ogni testo italiano che puo' arrivare all'utente
deve avere la traduzione in web/src/lib/i18n/server-en.json.

Il test scorre con `ast` i sorgenti di server/meshlens e raccoglie:
- gli argomenti-messaggio delle chiamate alle classi d'errore elencate in ERROR_CALLS;
- le costanti di modulo che hanno nome da messaggio (MSG_*, *_MSG, *_TEXT, ...);
- i testi dei passi di avanzamento dei lavori (`step=`, `phase(n, ...)`, STEP_*);
- i valori di `error=`/`.error =`/`_fail(...)` e le chiavi "detail"/"error" dei dizionari.
Una `Constant` deve stare in `exact`; una `JoinedStr`, con una cifra al posto dei campi, deve
corrispondere a un pattern.
"""
import ast
import json
import re
from pathlib import Path

SERVER = Path(__file__).parents[1] / "meshlens"
CATALOG = Path(__file__).parents[2] / "web" / "src" / "lib" / "i18n" / "server-en.json"

# classe d'errore -> indice dell'argomento posizionale con il messaggio. L'elenco viene da
# `grep -n "class .*Error" server/meshlens/*.py` (piu' le eccezioni di dominio che arrivano
# all'utente). Escluse: ItmError (codici della libreria), LockedError e TracerouteThrottled
# (portano solo secondi), _Cancelled/_Empty/_Unsupported/UnsupportedTelemetry/EmptyTelemetry
# (interne, mai mostrate), _LibraryError (testo della libreria).
ERROR_CALLS = {
    "HTTPException": 1,
    "MapsError": 0,
    "AdminError": 1,
    "MqttSendError": 2,
    "PredictionError": 1,
    "ElevationError": 0,
    "SfError": 0,
    "ConfigError": 1,
    "_JobFailed": 0,
    "UpdateError": 0,
    "NetworkError": 0,
    "NotifyError": 0,
    "SecretError": 0,
    "BackupUnusable": 0,
    "SessionActive": 0,
    "NoRadioConnected": 0,
    # i ValueError di validazione arrivano all'utente (come 400/422 o dentro un errore di lavoro)
    "ValueError": 0,
}
# Moduli i cui ValueError sono invarianti interne, mai mostrate: non servono traduzioni.
INTERNAL_VALUE_ERRORS = {"store.py", "tiles.py", "maps.py", "serving.py", "coverage.py"}
# Chiamate che ricevono il testo di un passo di avanzamento di un lavoro: nome -> indice dell'argomento.
STEP_CALLS = {"phase": 1, "_step": 1, "step": 0}
KEYWORDS = {"detail", "message", "error"}
MSG_CONST = re.compile(
    r"^(MSG_.*|STEP_.*|.*_MSG|.*_TEXT|TELEGRAM_(NO|NOT|BAD)_.*|WAYPOINT_.*|CONV_.*|REACTION_.*|INVALID_.*)$"
)
# costanti con nome da messaggio che non sono testi per l'utente
NOT_MESSAGES = {"MSG_PORT_BUSY_RE"}
DICT_KEYS = {"detail", "error", "step"}
LETTERS = re.compile(r"[^\W\d_]{3,}")


def _module_constants(trees):
    """nome -> valori stringa assegnati a livello di modulo (anche concatenazioni implicite)."""
    out: dict[str, set[str]] = {}
    for tree in trees.values():
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        out.setdefault(tgt.id, set()).add(node.value.value)
    return out


def _render(node, consts):
    """Costante (str) o modello di JoinedStr con "1" al posto dei campi (una cifra: corrisponde
    sia a un gruppo numerico sia a uno generico); None se non e' testo."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return ("const", node.value)
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            parts.append(v.value if isinstance(v, ast.Constant) else "1")
        text = "".join(parts)
        literal = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
        if not LETTERS.search(literal):
            return None  # solo campi: testo dinamico (es. eccezione di una libreria)
        if all(isinstance(v, ast.Constant) for v in node.values):
            return ("const", text)
        return ("fmt", text)
    return None


def _collect():
    trees = {p.name: ast.parse(p.read_text(encoding="utf-8")) for p in sorted(SERVER.glob("*.py"))}
    consts = _module_constants(trees)
    found: list[tuple[str, str, str]] = []  # (file, kind, text)

    def add(fname, node):
        if isinstance(node, ast.IfExp):
            add(fname, node.body)
            add(fname, node.orelse)
            return
        if isinstance(node, ast.Name):
            for v in consts.get(node.id, ()):
                found.append((fname, "const", v))
            return
        r = _render(node, consts)
        if r:
            found.append((fname, r[0], r[1]))

    for fname, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                if name == "ValueError" and fname in INTERNAL_VALUE_ERRORS:
                    continue
                if name in STEP_CALLS and len(node.args) > STEP_CALLS[name]:
                    add(fname, node.args[STEP_CALLS[name]])
                if name in ERROR_CALLS:
                    idx = ERROR_CALLS[name]
                    if len(node.args) > idx:
                        add(fname, node.args[idx])
                    for kw in node.keywords:
                        if kw.arg in KEYWORDS:
                            add(fname, kw.value)
                elif name == "_fail" and len(node.args) > 1:
                    add(fname, node.args[1])
                for kw in node.keywords:
                    if kw.arg in ("error", "step") and name not in ERROR_CALLS:
                        add(fname, kw.value)
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Attribute) and tgt.attr in ("error", "last_error"):
                        add(fname, node.value)
            elif isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value in DICT_KEYS:
                        add(fname, v)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and MSG_CONST.match(tgt.id) and tgt.id not in NOT_MESSAGES:
                        add(fname, node.value)
    return found


def _is_user_text(text: str) -> bool:
    """Scarta i codici (SEND_FAILED, 'timeout'...): solo maiuscole o solo minuscole senza spazi."""
    return bool(LETTERS.search(text)) and not re.fullmatch(r"[A-Z0-9_]+|[a-z0-9_]+", text.strip())


def test_catalog_is_valid_json_with_compilable_patterns():
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert set(cat) == {"exact", "patterns"}
    assert all(isinstance(k, str) and isinstance(v, str) and v for k, v in cat["exact"].items())
    for pat, repl in cat["patterns"]:
        re.compile(pat)
        assert isinstance(repl, str) and repl


def test_every_server_message_has_an_english_translation():
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    exact = cat["exact"]
    patterns = [re.compile(p) for p, _ in cat["patterns"]]
    missing = []
    for fname, kind, text in _collect():
        if not _is_user_text(text):
            continue
        if kind == "const":
            if text not in exact:
                missing.append(f"{fname}: {text!r}")
        elif not any(p.search(text) for p in patterns):
            missing.append(f"{fname} (pattern): {text!r}")
    assert not missing, "Messaggi senza traduzione in server-en.json:\n" + "\n".join(sorted(set(missing)))
