"""Rotte di WP4 per i profili di configurazione: salva, elenca, confronta, anteprima, esporta.

I dati dei profili non contengono segreti (vedi profiles.py) e non finiscono mai nel log.
L'applicazione passa dall'anteprima esistente (ConfigService) e da POST /api/config/{id}/apply.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .config_model import CONFIG_SECTIONS, schema
from .config_service import ConfigError
from .profiles import (ProfileError, allowed_sections, check_sections, compare, export_doc,
                       extract_profile, import_doc, profile_changes)
from .radio import MODULE_SECTIONS

GUEST_GET_PATHS: tuple[str, ...] = ()

MSG_NO_PROFILES = "Profili non disponibili"
MSG_NO_CONFIG = "Configurazione radio non disponibile"
MSG_NO_READ = "Nessuna configurazione letta per questo nodo"
MSG_NOTHING = "Il profilo non cambia nulla su questa radio"
MSG_COMPARE_SIDES = "Indica un nodo o un profilo per il lato A e un nodo per il lato B"

SectionName = Annotated[str, Field(max_length=64)]


class SaveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(max_length=16)
    name: str = Field(max_length=200)
    sections: list[SectionName] | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=2000)


class UpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=2000)


class DeleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: StrictBool = False


class PreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(max_length=16)
    sections: list[SectionName] | None = Field(None, max_length=40)


class ImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: dict
    name: str | None = Field(None, max_length=200)


def read_sections(row: dict) -> list[str]:
    """Sezioni di una lettura salvata ("lora", "mqtt") come sezioni dei profili."""
    names = set(row.get("sections") or [])
    out = []
    for sec in allowed_sections():
        kind, name = sec.split(".", 1)
        if name in names and ((kind == "config" and name in CONFIG_SECTIONS)
                              or (kind == "module_config" and name in MODULE_SECTIONS)):
            out.append(sec)
    return out


def register(app, ctx, require_auth, require_json) -> None:
    from .api import _num_from_id  # qui: api.py importa api_radioadmin

    def profiles():
        st = ctx.ext.get("profiles")
        if st is None:
            raise HTTPException(503, MSG_NO_PROFILES)
        return st

    def config():
        if ctx.config is None or ctx.radios is None:
            raise HTTPException(503, MSG_NO_CONFIG)
        return ctx.config

    def call(fn, *args, **kw):
        try:
            return fn(*args, **kw)
        except ProfileError as e:
            raise HTTPException(e.status, e.message) from None
        except ConfigError as e:
            raise HTTPException(e.status, e.message) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    def last_read(num: int) -> dict:
        row = ctx.store.last_read(num)
        if row is None:
            raise HTTPException(404, MSG_NO_READ)
        return row

    def node_label(num: int) -> str:
        node = ctx.live.nodes.get(num) or ctx.store.get_node(num) or {}
        return node.get("long_name") or node.get("short_name") or f"!{num:08x}"

    def parse_sections(text: str | None) -> list[str] | None:
        if text is None or not text.strip():
            return None
        return call(check_sections, [s.strip() for s in text.split(",") if s.strip()])

    @app.get("/api/profiles", dependencies=[Depends(require_auth)])
    async def list_profiles():
        return profiles().list()

    @app.get("/api/profiles/compare", dependencies=[Depends(require_auth)])
    async def compare_profiles(b: str = Query(..., max_length=16),
                               a: str | None = Query(None, max_length=16),
                               profile: int | None = None,
                               sections: str | None = Query(None, max_length=2000)):
        if (a is None) == (profile is None):
            raise HTTPException(400, MSG_COMPARE_SIDES)
        wanted = parse_sections(sections)
        bnum = _num_from_id(b)
        if profile is not None:
            p = call(profiles().get, profile)
            side_a = {"label": p["name"], "time": p["updated"]}
            data_a, secs_a = p["data"], list(p["sections"])
        else:
            anum = _num_from_id(a)
            row_a = last_read(anum)
            side_a = {"label": node_label(anum), "time": row_a["time"]}
            data_a, secs_a = row_a["data"], read_sections(row_a)
        row_b = last_read(bnum)
        side_b = {"label": node_label(bnum), "time": row_b["time"]}
        common = [s for s in secs_a if s in set(read_sections(row_b))]
        if wanted is not None:
            common = [s for s in common if s in set(wanted)]
        common = [s for s in allowed_sections() if s in set(common)]
        return {"a": side_a, "b": side_b, "sections": common,
                "rows": compare(data_a, row_b["data"], common)}

    @app.post("/api/profiles/import", status_code=201,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def import_profile(body: ImportBody):
        st = profiles()
        doc = call(import_doc, body.profile)
        return call(st.create, name=body.name if body.name else doc["name"],
                    sections=doc["sections"], data=doc["data"], source_node_num=None,
                    source_hw=doc["source_hw"], firmware=doc["firmware"], notes=doc["notes"])

    @app.get("/api/profiles/{profile_id}", dependencies=[Depends(require_auth)])
    async def get_profile(profile_id: int):
        return call(profiles().get, profile_id)

    @app.post("/api/profiles", status_code=201,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def save_profile(body: SaveBody):
        st = profiles()
        num = _num_from_id(body.node_id)
        row = last_read(num)
        have = read_sections(row)
        wanted = allowed_sections() if body.sections is None else call(check_sections,
                                                                       body.sections)
        wanted = [s for s in wanted if s in set(have)]  # solo sezioni davvero lette
        data, secs = call(extract_profile, row["data"], wanted)
        node = ctx.live.nodes.get(num) or ctx.store.get_node(num) or {}
        return call(st.create, name=body.name, sections=secs, data=data, source_node_num=num,
                    source_hw=node.get("hw_model"), firmware=node.get("firmware"),
                    notes=body.notes)

    @app.put("/api/profiles/{profile_id}",
             dependencies=[Depends(require_auth), Depends(require_json)])
    async def update_profile(profile_id: int, body: UpdateBody):
        st = profiles()
        kw = {}
        if "name" in body.model_fields_set and body.name is not None:
            kw["name"] = body.name
        if "notes" in body.model_fields_set:
            kw["notes"] = body.notes
        return call(st.update, profile_id, **kw)

    @app.delete("/api/profiles/{profile_id}",
                dependencies=[Depends(require_auth), Depends(require_json)])
    async def delete_profile(profile_id: int, body: DeleteBody):
        st = profiles()
        if body.confirm is not True:
            raise HTTPException(400, "Conferma richiesta")
        call(st.delete, profile_id)
        return {"ok": True}

    @app.post("/api/profiles/{profile_id}/preview",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def preview_profile(profile_id: int, body: PreviewBody):
        st = profiles()
        svc = config()
        p = call(st.get, profile_id)
        secs = list(p["sections"])
        if body.sections is not None:
            chosen = set(call(check_sections, body.sections))
            secs = [s for s in secs if s in chosen]
        changes, skipped = profile_changes(p["data"], secs, schema())
        if not changes:
            raise HTTPException(400, MSG_NOTHING)
        nid = f"!{_num_from_id(body.node_id):08x}"
        preview = call(svc.preview_changes, nid, changes)
        if not preview["changes"]:
            raise HTTPException(400, MSG_NOTHING)
        return {"preview": preview, "skipped": skipped}

    @app.get("/api/profiles/{profile_id}/export", dependencies=[Depends(require_auth)])
    async def export_profile(profile_id: int):
        p = call(profiles().get, profile_id)
        return JSONResponse(export_doc(p), headers={
            "Content-Disposition": f'attachment; filename="profilo-{profile_id}.json"'})
