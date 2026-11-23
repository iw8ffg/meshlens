"""Profili di configurazione: sezioni salvate da una radio e applicate ad altre.

Un profilo non contiene mai segreti ne' parametri legati all'hardware o alla persona:
sicurezza (intera), nome del nodo, canali e PSK, WiFi, credenziali MQTT, regione e parametri
radio dipendenti dal front-end, pin GPIO, posizione fissa. L'esclusione si applica al
salvataggio/importazione e di nuovo all'applicazione (profili importati o modificati a mano).

Funzioni pure tranne `ProfileStore` (SQL su `config_profiles`, connessione del loop).
Nessun log dei dati dei profili.
"""
import json
import math
import sqlite3
import time

from .config_model import CONFIG_SECTIONS, MASK, _is_secret, parse_changes
from .events import node_id as make_node_id
from .radio import MODULE_SECTIONS

PROFILE_FORMAT = "meshlens-profile"
PROFILE_VERSION = 1
NAME_MAX = 60
NOTES_MAX = 500
DATA_MAX_BYTES = 256 * 1024

EXCLUDED_SECTIONS: frozenset[str] = frozenset({"config.security"})
EXCLUDED_FIELDS: frozenset[str] = frozenset({
    # contratto §6.4
    "config.network.wifi_ssid", "config.network.wifi_psk",
    "module_config.mqtt.address", "module_config.mqtt.username", "module_config.mqtt.password",
    "config.lora.region", "config.lora.tx_power", "config.lora.override_duty_cycle",
    "config.lora.override_frequency", "config.lora.fem_lna_mode", "config.lora.pa_fan_disabled",
    "config.lora.sx126x_rx_boosted_gain",
    "config.device.button_gpio", "config.device.buzzer_gpio",
    "config.position.rx_gpio", "config.position.tx_gpio",
    "module_config.canned_message.inputbroker_pin_a",
    "module_config.canned_message.inputbroker_pin_b",
    "module_config.canned_message.inputbroker_pin_press",
    "module_config.detection_sensor.monitor_pin",
    "module_config.external_notification.output",
    "module_config.external_notification.output_ms",
    "module_config.external_notification.output_vibra",
    "module_config.external_notification.output_buzzer",
    "config.position.fixed_position",
    # aggiunte di WP4 per prudenza (R4.7)
    "config.bluetooth.fixed_pin", "config.network.ipv4_config", "config.position.gps_en_gpio",
    "module_config.serial.rxd", "module_config.serial.txd", "module_config.audio.ptt_pin",
    "module_config.audio.i2s_ws", "module_config.audio.i2s_sd", "module_config.audio.i2s_din",
    "module_config.audio.i2s_sck", "module_config.remote_hardware.available_pins",
    "config.power.adc_multiplier_override", "config.power.device_battery_ina_address",
    # calibrazione del quarzo della singola radio (come i parametri del front-end)
    "config.lora.frequency_offset",
})
# famiglie di campi (anche futuri) escluse per prefisso
_EXCLUDED_PREFIXES = ("module_config.external_notification.output", "module_config.audio.i2s_")

MSG_PROFILE_NOT_FOUND = "Profilo non trovato"
MSG_DUPLICATE = "Esiste già un profilo con questo nome"
MSG_NO_SECTIONS = "Il profilo non contiene sezioni copiabili"
MSG_BAD_FILE = "File non riconosciuto: non è un profilo di MeshLens"
MSG_BAD_VERSION = "Versione del profilo non supportata"
MSG_TOO_BIG = "Profilo troppo grande"
_UNSET = object()


class ProfileError(Exception):
    """Errore di richiesta sui profili: status HTTP e messaggio in italiano."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def allowed_sections() -> list[str]:
    """Sezioni copiabili, nell'ordine dello schema: configurazione senza sicurezza + moduli."""
    return ([f"config.{n}" for n in CONFIG_SECTIONS if f"config.{n}" not in EXCLUDED_SECTIONS]
            + [f"module_config.{n}" for n in MODULE_SECTIONS])


_ALLOWED = frozenset(allowed_sections())


def is_excluded(path: str) -> bool:
    """Campo mai copiato dai profili (segreto, legato all'hardware o alla persona)."""
    parts = path.split(".")
    if len(parts) != 3 or parts[0] not in ("config", "module_config"):
        return True  # owner, canali, percorsi sconosciuti
    kind, section, field = parts
    sec = f"{kind}.{section}"
    if sec in EXCLUDED_SECTIONS or sec not in _ALLOWED:
        return True
    if path in EXCLUDED_FIELDS or path.startswith(_EXCLUDED_PREFIXES):
        return True
    if _is_secret(kind, section, field):
        return True
    return field.endswith("_gpio") or field.endswith("_pin") or "pin_" in field


def _scalar(v) -> bool:
    if isinstance(v, (bool, int, float, str)):
        return True
    return isinstance(v, list) and all(isinstance(x, (bool, int, float, str)) for x in v)


def check_sections(sections) -> list[str]:
    if not isinstance(sections, list) or not all(isinstance(s, str) for s in sections):
        raise ValueError(MSG_NO_SECTIONS)
    out = []
    for s in sections:
        if s in EXCLUDED_SECTIONS:
            raise ValueError(f"Sezione non copiabile: {s}")
        if s not in _ALLOWED:
            raise ValueError(f"Sezione sconosciuta: {s}")
        if s not in out:
            out.append(s)
    return out


def _clean(data: dict, sections: list[str]) -> tuple[dict, list[str]]:
    """Solo sezioni consentite e presenti, campi scalari non esclusi e non mascherati."""
    out: dict = {"config": {}, "module_config": {}}
    present: list[str] = []
    src = data if isinstance(data, dict) else {}
    for sec in allowed_sections():  # ordine dello schema
        if sec not in sections:
            continue
        kind, name = sec.split(".", 1)
        block = (src.get(kind) or {}) if isinstance(src.get(kind), dict) else {}
        fields = block.get(name)
        if not isinstance(fields, dict):
            continue
        kept = {f: v for f, v in fields.items()
                if isinstance(f, str) and _scalar(v) and v != MASK
                and not is_excluded(f"{kind}.{name}.{f}")}
        out[kind][name] = kept
        present.append(sec)
    return out, present


def extract_profile(read_data: dict, sections: list[str] | None) -> tuple[dict, list[str]]:
    """Dati del profilo da una lettura (dict di node_to_dict): (dati, sezioni effettive)."""
    wanted = allowed_sections() if sections is None else check_sections(sections)
    data, present = _clean(read_data, wanted)
    if not present:
        raise ValueError(MSG_NO_SECTIONS)
    return data, present


def _coerce(spec: dict, value):
    """MessageToDict rende int64/uint64 come testo."""
    t = spec["type"]
    try:
        if t == "int" and isinstance(value, str):
            return int(value)
        if t == "repeated" and spec.get("item") == "int" and isinstance(value, list):
            return [int(x) if isinstance(x, str) else x for x in value]
    except ValueError:
        return value
    return value


def profile_changes(data: dict, sections: list[str], sch: dict) -> tuple[dict, list[str]]:
    """Cambi {percorso: valore} per l'anteprima, e percorsi saltati (esclusi o non validi).

    Le esclusioni si riapplicano qui (profili modificati a mano); i campi che il firmware
    attuale non conosce o con valori non validi finiscono in skipped, senza errori.
    """
    changes: dict = {}
    skipped: list[str] = []
    chosen = set(sections or [])
    src = data if isinstance(data, dict) else {}
    for kind in ("config", "module_config"):
        block = src.get(kind)
        if not isinstance(block, dict):
            continue
        for name, fields in block.items():
            if not isinstance(fields, dict):
                continue
            sec = f"{kind}.{name}"
            allowed = sec in _ALLOWED
            if allowed and sec not in chosen:
                continue  # sezione non scelta per questa anteprima
            for field, value in fields.items():
                path = f"{kind}.{name}.{field}"
                if not allowed or is_excluded(path):
                    skipped.append(path)
                    continue
                spec = sch.get(kind, {}).get(name, {}).get(field)
                if spec is None or not _scalar(value) or value == MASK:
                    skipped.append(path)
                    continue
                value = _coerce(spec, value)
                try:
                    parse_changes({path: value}, sch)
                except ValueError:
                    skipped.append(path)
                    continue
                changes[path] = value
    return changes, skipped


def _same(a, b) -> bool:
    """Come config_service._same: tolleranza sui float32 e sugli interi resi come testo."""
    if a == b:
        return True
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    try:
        if isinstance(a, (int, float, str)) and isinstance(b, (int, float, str)) \
                and (isinstance(a, (int, float)) or isinstance(b, (int, float))):
            return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-9)
    except (TypeError, ValueError):
        return False
    return False


def compare(a: dict, b: dict, sections: list[str] | None) -> list[dict]:
    """Differenze fra due configurazioni (letture o profili), solo nelle sezioni copiabili.

    Un campo assente da uno dei due lati (es. escluso dal profilo) non e' una differenza;
    i segreti sono sempre mascherati; sicurezza, nome e canali non compaiono mai.
    """
    wanted = allowed_sections() if sections is None else [
        s for s in allowed_sections() if s in set(sections)]
    rows = []
    for sec in wanted:
        kind, name = sec.split(".", 1)
        fa = ((a or {}).get(kind) or {}).get(name)
        fb = ((b or {}).get(kind) or {}).get(name)
        if not isinstance(fa, dict) or not isinstance(fb, dict):
            continue
        for field in list(fa) + [f for f in fb if f not in fa]:
            if field not in fa or field not in fb:
                continue
            va, vb = fa[field], fb[field]
            if not _scalar(va) or not _scalar(vb):
                continue
            if _is_secret(kind, name, field):
                continue  # mascherati da entrambi i lati: mai una differenza visibile
            if _same(va, vb):
                continue
            rows.append({"path": f"{kind}.{name}.{field}", "a": va, "b": vb,
                         "excluded": is_excluded(f"{kind}.{name}.{field}")})
    return rows


def validate_name(name) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Il nome del profilo è obbligatorio")
    name = name.strip()
    if len(name) > NAME_MAX:
        raise ValueError("Nome del profilo troppo lungo (massimo 60 caratteri)")
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError("Il nome del profilo non può contenere caratteri di controllo")
    return name


def validate_notes(notes) -> str | None:
    if notes is None or notes == "":
        return None
    if not isinstance(notes, str):
        raise ValueError("Note non valide")
    if len(notes) > NOTES_MAX:
        raise ValueError("Note troppo lunghe (massimo 500 caratteri)")
    if any((ord(c) < 32 and c not in "\n\r\t") or ord(c) == 127 for c in notes):
        raise ValueError("Le note non possono contenere caratteri di controllo")
    return notes.strip() or None


def export_doc(profile: dict) -> dict:
    """Documento esportabile (stesso contenuto senza segreti del database)."""
    return {"format": PROFILE_FORMAT, "version": PROFILE_VERSION, "name": profile["name"],
            "sections": list(profile["sections"]), "data": profile["data"],
            "source_hw": profile.get("source_hw"), "firmware": profile.get("firmware"),
            "notes": profile.get("notes")}


def _opt_text(v, limit: int = 64) -> str | None:
    if isinstance(v, str) and v.strip() and len(v) <= limit:
        return v.strip()
    return None


def import_doc(doc: dict) -> dict:
    """Valida un documento importato: {name, sections, data, source_hw, firmware, notes}."""
    if not isinstance(doc, dict) or doc.get("format") != PROFILE_FORMAT:
        raise ValueError(MSG_BAD_FILE)
    if doc.get("version") != PROFILE_VERSION:
        raise ValueError(MSG_BAD_VERSION)
    data = doc.get("data")
    if not isinstance(data, dict):
        raise ValueError(MSG_BAD_FILE)
    try:
        size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise ValueError(MSG_BAD_FILE) from None
    if size > DATA_MAX_BYTES:
        raise ValueError(MSG_TOO_BIG)
    sections = doc.get("sections")
    if not isinstance(sections, list):
        raise ValueError(MSG_BAD_FILE)
    wanted = [s for s in sections if isinstance(s, str) and s in _ALLOWED]  # il resto si scarta
    clean, present = _clean(data, wanted)
    if not present:
        raise ValueError(MSG_NO_SECTIONS)
    notes = doc.get("notes")
    try:
        notes = validate_notes(notes)
    except ValueError:
        notes = None
    return {"name": doc.get("name"), "sections": present, "data": clean,
            "source_hw": _opt_text(doc.get("source_hw")),
            "firmware": _opt_text(doc.get("firmware")), "notes": notes}


class ProfileStore:
    """Archivio dei profili su `config_profiles` (solo dal thread del loop)."""

    def __init__(self, conn: sqlite3.Connection, clock=time.time):
        self.conn = conn
        self._clock = clock

    @staticmethod
    def _json(row, with_data: bool) -> dict:
        out = {"id": row["id"], "name": row["name"], "created": row["created"],
               "updated": row["updated"],
               "source_node_id": (make_node_id(row["source_node_num"])
                                  if row["source_node_num"] is not None else None),
               "source_hw": row["source_hw"], "firmware": row["firmware"],
               "sections": json.loads(row["sections"]), "notes": row["notes"]}
        if with_data:
            out["data"] = json.loads(row["data"])
        return out

    def _row(self, pid: int):
        row = self.conn.execute("SELECT * FROM config_profiles WHERE id = ?", (pid,)).fetchone()
        if row is None:
            raise ProfileError(404, MSG_PROFILE_NOT_FOUND)
        return row

    def list(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM config_profiles ORDER BY name COLLATE NOCASE, id").fetchall()
        return [self._json(r, False) for r in rows]

    def get(self, pid: int) -> dict:
        return self._json(self._row(pid), True)

    def create(self, *, name, sections, data, source_node_num=None, source_hw=None,
               firmware=None, notes=None) -> dict:
        try:
            name = validate_name(name)
            notes = validate_notes(notes)
            wanted = [s for s in (sections or []) if isinstance(s, str) and s in _ALLOWED]
            clean, present = _clean(data, wanted)  # esclusioni riapplicate prima di scrivere
        except ValueError as exc:
            raise ProfileError(400, str(exc)) from None
        if not present:
            raise ProfileError(400, MSG_NO_SECTIONS)
        if len(json.dumps(clean).encode("utf-8")) > DATA_MAX_BYTES:
            raise ProfileError(400, MSG_TOO_BIG)
        now = self._clock()
        try:
            cur = self.conn.execute(
                "INSERT INTO config_profiles(name, created, updated, source_node_num, "
                "source_hw, firmware, sections, data, notes) VALUES (?,?,?,?,?,?,?,?,?)",
                (name, now, now, source_node_num, _opt_text(source_hw),
                 _opt_text(firmware), json.dumps(present), json.dumps(clean), notes))
        except sqlite3.IntegrityError:
            raise ProfileError(409, MSG_DUPLICATE) from None
        self.conn.commit()
        return self.get(cur.lastrowid)

    def update(self, pid: int, *, name=None, notes=_UNSET) -> dict:
        self._row(pid)
        sets, args = [], []
        try:
            if name is not None:
                sets.append("name = ?")
                args.append(validate_name(name))
            if notes is not _UNSET:
                sets.append("notes = ?")
                args.append(validate_notes(notes))
        except ValueError as exc:
            raise ProfileError(400, str(exc)) from None
        if sets:
            sets.append("updated = ?")
            args.append(self._clock())
            try:
                self.conn.execute(f"UPDATE config_profiles SET {', '.join(sets)} WHERE id = ?",
                                  (*args, pid))
            except sqlite3.IntegrityError:
                raise ProfileError(409, MSG_DUPLICATE) from None
            self.conn.commit()
        return self._json(self._row(pid), False)

    def delete(self, pid: int) -> None:
        self._row(pid)
        self.conn.execute("DELETE FROM config_profiles WHERE id = ?", (pid,))
        self.conn.commit()
