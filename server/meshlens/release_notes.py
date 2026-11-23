"""Note di versione per la finestra «Novità» (E18), lette dal CHANGELOG incluso nel pacchetto.

Formato: intestazioni `## [x.y.z(-pre)] - AAAA-MM-GG`; dentro, `### Italiano` e `### English`
separano i testi (senza marcatori lo stesso testo vale per entrambe le lingue).
"""
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import paths
from .updater import parse_version_full

MAX_TEXT_CHARS = 8000
MAX_FILE_BYTES = 1024 * 1024
MAX_RELEASES = 3
_HEADER = re.compile(r"^##\s+\[([^\]]+)\](?:\s*-\s*(\d{4}-\d{2}-\d{2}))?")
_LANG = {"### italiano": "it", "### english": "en"}

version_key = parse_version_full  # un solo algoritmo di confronto (updater)


@dataclass(frozen=True)
class Release:
    version: str
    date: str | None
    it: str
    en: str


def _finish(version: str, date: str | None, parts: dict[str, list[str]]) -> Release:
    text = {k: "\n".join(v).strip()[:MAX_TEXT_CHARS] for k, v in parts.items()}
    if not text["it"] and not text["en"]:
        text["it"] = text["en"] = text["common"]
    return Release(version, date, text["it"] or text["en"], text["en"] or text["it"])


def parse_changelog(text: str) -> list[Release]:
    out: list[Release] = []
    current: tuple[str, str | None] | None = None
    parts: dict[str, list[str]] = {}
    lang = "common"
    for line in (text or "").splitlines():
        m = _HEADER.match(line)
        if m or line.startswith("## "):
            if current is not None:
                out.append(_finish(*current, parts))
            current = None
            if m and version_key(m.group(1).strip()) is not None:
                current = (m.group(1).strip(), m.group(2))
                parts, lang = {"common": [], "it": [], "en": []}, "common"
            continue
        if current is None:
            continue
        marker = _LANG.get(line.strip().casefold())
        if marker is not None:
            lang = marker
            continue
        parts[lang].append(line)
    if current is not None:
        out.append(_finish(*current, parts))
    return out


def find_changelog() -> Path | None:
    """Versione installata (meshlens/data, incluso dallo spec), poi radice in sviluppo."""
    for p in (Path(__file__).parent / "data" / "CHANGELOG.md", paths.app_dir() / "CHANGELOG.md"):
        if p.is_file():
            return p
    return None


_cache: dict[str, object] = {}


def load_releases() -> list[Release]:
    path = find_changelog()
    if path is None:
        return []
    try:
        st = path.stat()
        if st.st_size > MAX_FILE_BYTES:
            return []
        key = (str(path), st.st_mtime_ns)
        if _cache.get("key") != key:
            _cache["releases"] = parse_changelog(path.read_text(encoding="utf-8",
                                                                errors="replace"))
            _cache["key"] = key
        return list(_cache["releases"])  # type: ignore[arg-type]
    except OSError:
        return []


def payload(current: str, last_seen: str, onboarding_done: bool, releases: list[Release],
            force: bool = False) -> dict:
    cur = version_key(current)
    seen = version_key(last_seen) if last_seen else None
    by_version = sorted((r for r in releases if version_key(r.version) is not None),
                        key=lambda r: version_key(r.version), reverse=True)
    if force or seen is None:
        chosen = [r for r in by_version if version_key(r.version) == cur][:1]
    else:
        chosen = [r for r in by_version
                  if cur is not None and seen < version_key(r.version) <= cur][:MAX_RELEASES]
    if force:
        show = bool(chosen)
    else:
        show = (bool(chosen) and last_seen != current
                and (last_seen != "" or onboarding_done is True))
    return {"version": current, "last_seen": last_seen, "show": show,
            "releases": [asdict(r) for r in chosen]}
