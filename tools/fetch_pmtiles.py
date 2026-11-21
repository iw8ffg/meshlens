"""Scarica go-pmtiles, verifica lo SHA-256 e ne estrae pmtiles.exe.

Uso: python tools/fetch_pmtiles.py <cartella-di-destinazione>
Usa le stesse costanti di meshlens.maps (URL e impronta).
"""
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

from meshlens.maps import TOOL_EXE, TOOL_SHA256, TOOL_URL


def fetch(dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(TOOL_URL, timeout=120) as r:
        data = r.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TOOL_SHA256:
        raise SystemExit(f"SHA-256 di go-pmtiles non corrisponde: {digest} != {TOOL_SHA256}")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if Path(n).name == TOOL_EXE]
        if not names:
            raise SystemExit(f"{TOOL_EXE} non trovato nello zip")
        out = dest_dir / TOOL_EXE
        out.write_bytes(z.read(names[0]))
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("uso: fetch_pmtiles.py <cartella>")
    print(f"OK {fetch(Path(sys.argv[1]))}")
