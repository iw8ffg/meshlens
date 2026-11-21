"""Servizio di configurazione dei nodi: letture, anteprime, copie di sicurezza e lavori.

Mai una scrittura senza anteprima e conferma: `apply` accetta solo un `preview_id` valido
(esistente, monouso, non scaduto, con lettura di base non superata). Prima di scrivere si salva
la copia (con i segreti in chiaro, solo nel database); tutto cio' che esce dal server e' mascherato.
"""
import asyncio
import base64
import logging
import math
import secrets
import time

from .config_model import (CHANNEL_FIELDS, CONFIG_SECTIONS, MASK, OWNER_FIELDS, _current,
                           _is_secret, _split, apply_to_protos, diff, mask_config,
                           node_to_dict, parse_changes, schema, touched_sections)
from .events import node_id as make_node_id
from .radio import MODULE_SECTIONS, AdminError
from .radio_manager import NoRadioConnected

log = logging.getLogger(__name__)

PREVIEW_TTL = 600.0  # anteprime e letture di base: 10 minuti
DROP_WAIT = 15  # dopo una scrittura locale: attesa del distacco (la radio puo' non riavviarsi)
RECONNECT_WAIT = 90  # attesa totale della riconnessione
REMOTE_SETTLE = 15  # dopo una scrittura remota: il nodo si sta riavviando
ALL_SECTIONS = list(CONFIG_SECTIONS) + list(MODULE_SECTIONS) + ["channels", "owner"]
MSG_READ_FIRST = "Leggi prima la configurazione"
MSG_NOT_BACK = "La radio non è tornata dopo il riavvio"
MSG_CHANGED = "La configurazione del nodo è cambiata: rivedi le modifiche"


class ConfigError(Exception):
    """Errore di richiesta: status HTTP e messaggio in italiano."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class _JobFailed(Exception):
    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.message = message
        self.code = code


def _num(node_id: str) -> int:
    try:
        if not node_id.startswith("!") or len(node_id) != 9:
            raise ValueError
        return int(node_id[1:], 16)
    except ValueError:
        raise ConfigError(404, "Nodo non trovato") from None


def _same(old, new) -> bool:
    """Uguaglianza tra valore letto e atteso (i float32 tornano con qualche cifra in piu')."""
    if isinstance(new, bytes):
        new = base64.b64encode(new).decode()
    if isinstance(new, list):
        return (isinstance(old, list) and len(old) == len(new)
                and all(_same(a, b) for a, b in zip(old, new)))
    if isinstance(new, bool) or isinstance(old, bool):
        return old == new
    if isinstance(new, (int, float)):
        try:
            return math.isclose(float(old), float(new), rel_tol=1e-6, abs_tol=1e-9)
        except (TypeError, ValueError):
            return False
    return old == new


def _plain_sections(sections: list[str] | None) -> list[str] | None:
    """Nomi di sezione per read_remote: "config.lora" -> "lora"; canali e nome sono sempre letti."""
    if not sections:
        return None
    out: list[str] = []
    for s in sections:
        name = s.split(".")[1] if s.startswith(("config.", "module_config.")) else s
        if name in ("channels", "owner") or name.startswith("channels."):
            continue
        if name not in CONFIG_SECTIONS and name not in MODULE_SECTIONS:
            raise ConfigError(400, f"Sezione sconosciuta: {s}")
        if name not in out:
            out.append(name)
    return out or None


def _section_names(touched: list[str]) -> list[str]:
    """Sezioni toccate ("config.lora", "channels.1") -> nomi come salvati nella lettura."""
    out = []
    for t in touched:
        if t == "owner" or t.startswith("channels."):
            out.append(t.split(".")[0])
        else:
            out.append(t.split(".")[1])
    return out


class ConfigService:
    def __init__(self, store, radios, live, bus, clock=time.time, sleep=asyncio.sleep):
        self.store, self.radios, self.live, self.bus = store, radios, live, bus
        self._clock = clock
        self._sleep = sleep
        self._previews: dict[str, dict] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: dict[int, asyncio.Task] = {}
        self._schema = schema()
        # lavori rimasti "running" da un avvio precedente non finiranno piu'
        store.fail_running_jobs("Interrotto dal riavvio di MeshLens", clock())
        store.commit()

    # ---- lavori ------------------------------------------------------------
    @staticmethod
    def _job_json(row: dict) -> dict:
        return {"id": row["id"], "node_id": make_node_id(row["node_num"]),
                "radio_id": row["radio_id"], "kind": row["kind"], "status": row["status"],
                "step": row["step"] or "", "progress": [row["done"] or 0, row["total"] or 0],
                "error": row["error"], "error_code": row.get("error_code"),
                "result_id": row["result_id"], "verify": row["verify"],
                "started": row["started"], "ended": row["ended"]}

    def job(self, job_id: int) -> dict:
        row = self.store.get_job(job_id)
        if row is None:
            raise ConfigError(404, "Lavoro non trovato")
        return self._job_json(row)

    def _update(self, jid: int, **fields) -> dict:
        self.store.update_job(jid, **fields)
        self.store.commit()
        job = self.job(jid)
        self.bus.publish({"type": "config_job", "job": job})
        return job

    def _start_job(self, num: int, radio_id: str, kind: str, work, total: int = 1) -> dict:
        jid = self.store.add_job(node_num=num, radio_id=radio_id, kind=kind, status="running",
                                 step="In coda", done=0, total=total, started=self._clock())
        self.store.commit()
        job = self.job(jid)
        self.bus.publish({"type": "config_job", "job": job})
        task = asyncio.create_task(self._run_job(jid, radio_id, work))
        self._tasks[jid] = task
        task.add_done_callback(lambda _t, j=jid: self._tasks.pop(j, None))
        return job

    async def _run_job(self, jid: int, radio_id: str, work) -> None:
        lock = self._locks.setdefault(radio_id, asyncio.Lock())  # un lavoro alla volta per radio
        try:
            async with lock:
                await work(jid)
        except _JobFailed as err:
            self._fail(jid, err.message, err.code)
        except AdminError as err:
            self._fail(jid, err.message, err.code)
        except asyncio.CancelledError:
            self._fail(jid, "Interrotto", "error")
            raise
        except Exception as exc:  # il testo dell'eccezione puo' contenere dati: solo il tipo
            log.warning("lavoro di configurazione %s fallito: %s", jid, type(exc).__name__)
            self._fail(jid, f"Operazione fallita: {type(exc).__name__}", "error")

    def _fail(self, jid: int, message: str, code: str) -> None:
        self._update(jid, status="failed", error=message, error_code=code,
                     ended=self._clock())

    def _done(self, jid: int, **fields) -> None:
        self._update(jid, status="done", ended=self._clock(), **fields)

    def _on_step(self, jid: int, with_progress: bool):
        def cb(text: str, done: int, total: int) -> None:
            if with_progress:
                self._update(jid, step=text, done=done, total=total)
            else:
                self._update(jid, step=text)
        return cb

    async def join(self, jid: int) -> None:
        """Attende la fine di un lavoro (usato dai test)."""
        task = self._tasks.get(jid)
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # ---- selezione della radio ----------------------------------------------
    def _connector(self, radio_id: str):
        try:
            return self.radios.connector(radio_id)
        except KeyError:
            raise ConfigError(404, "Radio non trovata") from None

    def _resolve(self, num: int, radio_id: str | None) -> tuple[str, bool]:
        """(radio, nodo locale?). Il nodo e' locale se e' il nodo della radio scelta."""
        nid = make_node_id(num)
        if radio_id is None:
            local = self.radios.local_radio_for(num)
            if local is not None:
                return local, True
            try:
                return self.radios.pick_radio(num), False
            except NoRadioConnected:
                raise ConfigError(409, "Nessuna radio collegata") from None
        conn = self._connector(radio_id)
        st = conn.state()
        if st["state"] != "connected":
            raise ConfigError(409, "La radio non è collegata")
        return radio_id, st.get("my_node_id") == nid

    # ---- lettura ------------------------------------------------------------
    def start_read(self, node_id: str, radio_id: str | None, sections: list[str] | None) -> dict:
        num = _num(node_id)
        plain = _plain_sections(sections)
        rid, local = self._resolve(num, radio_id)
        conn = self._connector(rid)
        saved = list(ALL_SECTIONS) if (local or plain is None) else plain + ["channels", "owner"]

        async def work(jid: int) -> None:
            if local:
                self._update(jid, step="Leggo la radio", done=0, total=1)
                data = await conn.read_local()
                self._update(jid, step="Letta la configurazione", done=1, total=1)
            else:
                data = await conn.read_remote(num, plain, self._on_step(jid, True))
            rid_saved = self.store.add_read(num, rid, self._clock(), saved, data)
            self.store.commit()
            self._done(jid, result_id=rid_saved)

        return self._start_job(num, rid, "read", work)

    def last_read(self, node_id: str) -> dict:
        row = self.store.last_read(_num(node_id))
        if row is None:
            raise ConfigError(404, "Nessuna configurazione letta per questo nodo")
        return {"id": row["id"], "node_id": node_id, "radio_id": row["radio_id"],
                "time": row["time"], "config": mask_config(row["data"]),
                "sections": row["sections"]}

    # ---- anteprima ----------------------------------------------------------
    def _fresh_read(self, num: int, touched: list[str]) -> dict:
        row = self.store.last_read(num)
        if row is None or self._clock() - row["time"] > PREVIEW_TTL:
            raise ConfigError(409, MSG_READ_FIRST)
        have = set(row["sections"])
        if not set(_section_names(touched)) <= have:
            raise ConfigError(409, MSG_READ_FIRST)
        return row

    def _prune_previews(self) -> None:
        now = self._clock()
        for k in [k for k, p in self._previews.items() if now - p["created"] > PREVIEW_TTL]:
            del self._previews[k]

    def _build_preview(self, num: int, changes: dict) -> dict:
        try:
            parsed = parse_changes(changes, self._schema)
            touched = touched_sections(parsed)
        except ValueError as exc:
            raise ConfigError(400, str(exc)) from None
        row = self._fresh_read(num, touched)
        rid = row["radio_id"]
        local = False
        if rid is not None:
            try:
                local = make_node_id(num) == self.radios.connector(rid).state().get("my_node_id")
                kind = self.radios.radio_kind(rid)
            except KeyError:
                rid, kind = None, None
        else:
            kind = None
        if rid is None:  # radio della lettura non piu' presente: se ne sceglie un'altra
            rid, local = self._resolve(num, None)
            kind = self.radios.radio_kind(rid)
        context = {"radio_kind": kind, "is_local": local}
        entries = diff(row["data"], parsed, context)
        paths = {e["path"] for e in entries}
        effective = [(p, v) for p, v in parsed if p in paths]
        backup_sections = touched_sections(effective)
        self._prune_previews()
        pid = secrets.token_hex(8)
        self._previews[pid] = {
            "num": num, "radio_id": rid, "changes": effective, "created": self._clock(),
            "base_read_id": row["id"], "base_data": row["data"], "entries": entries,
            "sections": backup_sections, "context": context}
        return {"preview_id": pid, "node_id": make_node_id(num), "radio_id": rid,
                "changes": entries, "risky": any(e["risky"] for e in entries),
                "backup_sections": backup_sections}

    def preview(self, node_id: str, changes: dict) -> dict:
        if not isinstance(changes, dict) or not changes:
            raise ConfigError(400, "Nessuna modifica indicata")
        return self._build_preview(_num(node_id), changes)

    # ---- ripristino da copia --------------------------------------------------
    def _coerce(self, spec: dict, value):
        t = spec["type"]
        if t == "int" and isinstance(value, str):
            return int(value)  # MessageToDict rende int64/uint64 come testo
        if t == "repeated" and spec.get("item") == "int":
            return [int(x) for x in value]
        return value

    def _backup_changes(self, data: dict, sections: list[str]) -> dict:
        sch, out = self._schema, {}
        for sec in sections:
            if sec == "owner":
                for k in OWNER_FIELDS:
                    if k in data.get("owner", {}):
                        out[f"owner.{k}"] = data["owner"][k]
            elif sec.startswith("channels."):
                idx = int(sec.split(".")[1])
                ch = next((c for c in data.get("channels", []) if c.get("index") == idx), None)
                for f in CHANNEL_FIELDS:
                    if ch is not None and f in ch:
                        out[f"channels.{idx}.{f}"] = self._coerce(sch["channel"][f], ch[f])
            else:
                kind, name = sec.split(".", 1)
                src = data.get(kind, {}).get(name, {})
                for field, spec in sch[kind][name].items():
                    if field in src:
                        out[f"{kind}.{name}.{field}"] = self._coerce(spec, src[field])
        return out

    def preview_restore(self, backup_id: int) -> dict:
        b = self.store.get_backup(backup_id)
        if b is None:
            raise ConfigError(404, "Copia non trovata")
        changes = self._backup_changes(b["data"], b["sections"])
        if not changes:
            raise ConfigError(400, "La copia non contiene sezioni ripristinabili")
        return self._build_preview(b["node_num"], changes)

    # ---- applicazione --------------------------------------------------------
    def apply(self, node_id: str, preview_id: str, confirm_risky: bool = False) -> dict:
        num = _num(node_id)
        self._prune_previews()
        p = self._previews.get(preview_id)
        if p is None or p["num"] != num:
            raise ConfigError(400, "Anteprima sconosciuta o scaduta: ripeti l'anteprima")
        if not p["changes"]:
            raise ConfigError(400, "Nessuna modifica da applicare")
        if any(e["risky"] for e in p["entries"]) and not confirm_risky:
            raise ConfigError(400, "Conferma richiesta per modifiche a rischio")
        last = self.store.last_read(num)
        if last is None or last["id"] != p["base_read_id"]:
            del self._previews[preview_id]
            raise ConfigError(409, "La configurazione è stata riletta: ripeti l'anteprima")
        rid, local = self._resolve(num, p["radio_id"])
        del self._previews[preview_id]  # monouso: da qui in poi e' consumata
        conn = self._connector(rid)
        changes, sections = p["changes"], p["sections"]
        # sezioni da rileggere (read_remote senza elenco le leggerebbe tutte: ne basta una)
        plain = ([n for n in _section_names(sections) if n not in ("channels", "owner")]
                 or ["device"])
        TOTAL = 5

        async def work(jid: int) -> None:
            cb = self._on_step(jid, False)

            def phase(n: int, text: str) -> None:
                self._update(jid, step=text, done=n, total=TOTAL)

            if not local:  # chiave di sessione e confronto richiedono una lettura fresca
                phase(1, "Rileggo il nodo prima di scrivere")
                fresh = await conn.read_remote(num, plain, cb)
                self._check_unchanged(fresh, p)
            else:
                phase(1, "Controllo la radio")
            current = await conn.current_protos(None if local else num)
            phase(2, "Salvo la copia di sicurezza")
            self._save_backup(num, current, sections, "before_apply")
            phase(3, "Scrivo la configurazione")
            await conn.write(None if local else num, apply_to_protos(current, changes), cb)
            phase(4, "Attendo la radio e verifico" if local else "Verifico")
            if local:
                await self._wait_back(conn)
                fresh = await conn.read_local()
            else:
                await self._sleep(REMOTE_SETTLE)
                try:
                    fresh = await conn.read_remote(num, plain, cb)
                except AdminError:
                    # il nodo si sta riavviando: scritto, ma non ancora verificabile
                    self._done(jid, verify=None, step="Scritto: il nodo si sta riavviando, "
                                                      "rileggi tra poco")
                    return
            verify = self._verify(fresh, changes)
            phase(5, "Salvo la nuova lettura")
            read_sections = list(ALL_SECTIONS) if local else plain + ["channels", "owner"]
            saved = self.store.add_read(num, rid, self._clock(), read_sections, fresh)
            self.store.commit()
            self._done(jid, verify=verify, result_id=saved, step="Fatto")

        return self._start_job(num, rid, "apply", work, total=TOTAL)

    def _check_unchanged(self, fresh: dict, p: dict) -> None:
        """I valori toccati devono essere quelli su cui si basa l'anteprima."""
        for path, _v in p["changes"]:
            kind, section, field = _split(path)
            if _is_secret(kind, section, field):
                continue
            if not _same(_current(fresh, kind, section, field),
                         _current(p["base_data"], kind, section, field)):
                raise _JobFailed(MSG_CHANGED)

    def _verify(self, fresh: dict, changes) -> str:
        for path, new in changes:
            kind, section, field = _split(path)
            if _is_secret(kind, section, field):
                continue  # i segreti non tornano in chiaro: non si confrontano
            if not _same(_current(fresh, kind, section, field), new):
                return "mismatch"
        return "verified"

    async def _wait_back(self, conn) -> None:
        """Dopo una scrittura locale la radio di solito si riavvia, ma non sempre."""
        if await conn.wait_reconnected(DROP_WAIT):
            return
        if conn.state()["state"] == "connected":
            return  # non si e' mai scollegata (es. solo nome o canali): rileggo subito
        if not await conn.wait_reconnected(RECONNECT_WAIT - DROP_WAIT):
            raise _JobFailed(MSG_NOT_BACK)

    def _save_backup(self, num: int, protos: dict, sections: list[str], reason: str,
                     label: str | None = None) -> int:
        full = node_to_dict(protos["config"], protos["module_config"], protos["channels"],
                            protos["owner"], mask=False)  # segreti in chiaro: solo nel database
        data: dict = {"config": {}, "module_config": {}, "channels": []}
        for sec in sections:
            if sec == "owner":
                data["owner"] = full["owner"]
            elif sec.startswith("channels."):
                idx = int(sec.split(".")[1])
                data["channels"] += [c for c in full["channels"] if c["index"] == idx]
            else:
                kind, name = sec.split(".", 1)
                data[kind][name] = full[kind][name]
        bid = self.store.add_backup(num, self._clock(), reason, label, list(sections), data)
        self.store.commit()
        return bid

    # ---- copie ---------------------------------------------------------------
    @staticmethod
    def _backup_json(b: dict) -> dict:
        return {"id": b["id"], "node_id": make_node_id(b["node_num"]), "time": b["time"],
                "reason": b["reason"], "label": b["label"], "sections": b["sections"]}

    def backups(self, node_id: str) -> list[dict]:
        return [self._backup_json(b) for b in self.store.backups(_num(node_id))]

    def backup(self, backup_id: int) -> dict:
        b = self.store.get_backup(backup_id)
        if b is None:
            raise ConfigError(404, "Copia non trovata")
        return {**self._backup_json(b), "config": mask_config(b["data"])}

    # ---- riavvio e posizione fissa ---------------------------------------------
    def reboot(self, node_id: str, radio_id: str | None, confirm: bool) -> dict:
        if confirm is not True:
            raise ConfigError(400, "Conferma richiesta")
        num = _num(node_id)
        rid, local = self._resolve(num, radio_id)
        conn = self._connector(rid)

        async def work(jid: int) -> None:
            self._update(jid, step="Invio il riavvio", done=0, total=2)
            await conn.reboot(None if local else num)
            if local:
                self._update(jid, step="Attendo la radio", done=1, total=2)
                if not await conn.wait_reconnected(RECONNECT_WAIT):
                    raise _JobFailed(MSG_NOT_BACK)
            self._done(jid, step="Fatto", done=2, total=2)

        return self._start_job(num, rid, "reboot", work, total=2)

    def fixed_position(self, node_id: str, radio_id: str | None, confirm: bool,
                       lat: float | None = None, lon: float | None = None, alt: int = 0,
                       remove: bool = False) -> dict:
        if confirm is not True:
            raise ConfigError(400, "Conferma richiesta")
        if not remove:
            if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ConfigError(400, "Coordinate non valide")
        num = _num(node_id)
        rid, local = self._resolve(num, radio_id)
        conn = self._connector(rid)
        target = None if local else num

        async def work(jid: int) -> None:
            self._update(jid, step="Rimuovo la posizione fissa" if remove
                         else "Imposto la posizione fissa", done=0, total=1)
            if remove:
                await conn.remove_fixed_position(target)
            else:
                await conn.set_fixed_position(target, lat, lon, alt)
            self._done(jid, step="Fatto", done=1, total=1)

        return self._start_job(num, rid, "fixed_position", work)

    # ---- segreti su richiesta esplicita ------------------------------------------
    async def reveal_psk(self, node_id: str, index: int) -> dict:
        num = _num(node_id)
        if not 0 <= index < 8:
            raise ConfigError(400, "Canale non valido")
        rid, local = self._resolve(num, None)
        conn = self._connector(rid)
        try:
            protos = await conn.current_protos(None if local else num)
        except AdminError as err:
            raise ConfigError(409, err.message) from None
        ch = next((c for c in protos["channels"] if c.index == index), None)
        if ch is None:
            raise ConfigError(404, "Canale non trovato")
        return {"psk": base64.b64encode(ch.settings.psk).decode()}

    async def admin_key(self, radio_id: str) -> dict:
        conn = self._connector(radio_id)
        try:
            key = await conn.admin_public_key()
        except AdminError as err:
            raise ConfigError(409, err.message) from None
        if not key:
            raise ConfigError(409, "La radio non ha ancora una chiave pubblica")
        return {"public_key_b64": key}


__all__ = ["ConfigService", "ConfigError", "MASK"]
