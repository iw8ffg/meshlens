"""Note di versione dal CHANGELOG (E18) e controlli statici del pacchetto."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from meshlens import release_notes
from meshlens.release_notes import (MAX_TEXT_CHARS, Release, parse_changelog, payload,
                                    version_key)
from meshlens.updater import parse_version_full

ROOT = Path(__file__).parents[2]

SAMPLE = """# Changelog

## [Unreleased]
- da fare

## [1.6.0] - 2026-12-01

### Italiano

#### Aggiunto
- **Bot:** risponde a !ping

### English

#### Added
- **Bot:** answers !ping

## [1.5.1] - 2026-11-23

Testo comune senza lingue.

## [1.7.0-beta.1] - 2027-01-10

### Italiano
Prova

### English
Test
"""


def rel(v):
    return Release(v, "2026-01-01", f"it {v}", f"en {v}")


def test_parse_two_languages():
    rs = {r.version: r for r in parse_changelog(SAMPLE)}
    r = rs["1.6.0"]
    assert r.date == "2026-12-01"
    assert "risponde a !ping" in r.it and "#### Aggiunto" in r.it
    assert "answers !ping" in r.en and "risponde" not in r.en


def test_unreleased_skipped():
    versions = [r.version for r in parse_changelog(SAMPLE)]
    assert "Unreleased" not in versions and versions[0] == "1.6.0"
    assert all("da fare" not in r.it for r in parse_changelog(SAMPLE))


def test_section_without_language_markers_fills_both():
    r = {r.version: r for r in parse_changelog(SAMPLE)}["1.5.1"]
    assert r.it == r.en == "Testo comune senza lingue."


def test_prerelease_header():
    r = {r.version: r for r in parse_changelog(SAMPLE)}["1.7.0-beta.1"]
    assert r.date == "2027-01-10" and r.it == "Prova" and r.en == "Test"


def test_text_truncated_to_8000():
    text = "## [1.0.0] - 2020-01-01\n\n" + "x" * 20000
    r = parse_changelog(text)[0]
    assert len(r.it) == MAX_TEXT_CHARS and len(r.en) == MAX_TEXT_CHARS


def test_real_changelog_parses():
    rs = {r.version: r for r in parse_changelog((ROOT / "CHANGELOG.md").read_text("utf-8"))}
    for v in ("1.5.1", "1.5.0"):
        assert rs[v].it and rs[v].en and rs[v].it != rs[v].en


def test_version_key_ordering():
    k = version_key
    assert k("1.6.0") > k("1.6.0-beta.2") > k("1.6.0-beta.1") > k("1.6.0-alpha") > k("1.5.9")
    assert k("1.6.0-beta.10") > k("1.6.0-beta.2")
    assert k("1.6.0-beta") > k("1.6.0-1")
    assert k("v1.6.0") == k("1.6.0")
    assert k("1.6.0-alpha.1") > k("1.6.0-alpha")
    for bad in ("", "1.6", "abc", "1.6.0-", None, "Unreleased"):
        assert k(bad) is None


def test_single_version_algorithm():
    assert version_key is parse_version_full


def test_payload_shows_after_update():
    rs = [rel("1.6.0"), rel("1.5.4"), rel("1.5.3"), rel("1.5.2"), rel("1.5.1"), rel("1.5.0")]
    p = payload("1.6.0", "1.5.1", True, rs)
    assert p["show"] is True and p["version"] == "1.6.0" and p["last_seen"] == "1.5.1"
    assert [r["version"] for r in p["releases"]] == ["1.6.0", "1.5.4", "1.5.3"]
    assert set(p["releases"][0]) == {"version", "date", "it", "en"}


def test_payload_fresh_install_hidden():
    rs = [rel("1.6.0"), rel("1.5.1")]
    p = payload("1.6.0", "", False, rs)
    assert p["show"] is False
    p = payload("1.6.0", "", True, rs)  # aggiornamento da 1.5.1 (che non scriveva la versione)
    assert p["show"] is True and [r["version"] for r in p["releases"]] == ["1.6.0"]


def test_payload_same_version_hidden():
    assert payload("1.6.0", "1.6.0", True, [rel("1.6.0")])["show"] is False


def test_payload_force():
    p = payload("1.6.0", "1.6.0", True, [rel("1.6.0"), rel("1.5.1")], force=True)
    assert p["show"] is True and [r["version"] for r in p["releases"]] == ["1.6.0"]


def test_missing_changelog_is_not_an_error(monkeypatch):
    monkeypatch.setattr(release_notes, "find_changelog", lambda: None)
    release_notes._cache.clear()
    assert release_notes.load_releases() == []
    p = payload("1.6.0", "1.5.1", True, release_notes.load_releases())
    assert p["releases"] == [] and p["show"] is False


def test_load_releases_cached_by_mtime(tmp_path, monkeypatch):
    f = tmp_path / "CHANGELOG.md"
    f.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(release_notes, "find_changelog", lambda: f)
    release_notes._cache.clear()
    calls = []
    real = release_notes.parse_changelog
    monkeypatch.setattr(release_notes, "parse_changelog", lambda t: calls.append(1) or real(t))
    assert release_notes.load_releases()[0].version == "1.6.0"
    release_notes.load_releases()
    assert len(calls) == 1


def test_load_releases_ignores_huge_file(tmp_path, monkeypatch):
    f = tmp_path / "CHANGELOG.md"
    f.write_bytes(b"x" * (release_notes.MAX_FILE_BYTES + 1))
    monkeypatch.setattr(release_notes, "find_changelog", lambda: f)
    release_notes._cache.clear()
    assert release_notes.load_releases() == []


def test_find_changelog_in_development():
    p = release_notes.find_changelog()
    assert p is not None and p.name == "CHANGELOG.md"
