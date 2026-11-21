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


def fetch(dest_dir: Path, license_dir: Path | None = None) -> Path:
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
        lic = [n for n in z.namelist() if Path(n).name.upper() == "LICENSE"]
        if license_dir is not None and lic:  # BSD-3 di go-pmtiles, dalla stessa zip
            license_dir.mkdir(parents=True, exist_ok=True)
            (license_dir / "go-pmtiles-LICENSE.txt").write_bytes(z.read(lic[0]))
    return out


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit("uso: fetch_pmtiles.py <cartella> [<cartella-licenze>]")
    lic = Path(sys.argv[2]) if len(sys.argv) == 3 else None
    print(f"OK {fetch(Path(sys.argv[1]), lic)}")
