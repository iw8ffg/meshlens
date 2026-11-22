r"""Genera la cartella licenses\ da includere nell'installer.

Uso: python tools/gen_licenses.py <cartella-licenze>
Richiede pip-licenses (solo in build/CI, non e' una dipendenza di esecuzione):
    pip install pip-licenses
Scrive: python.txt (testi completi delle licenze delle dipendenze Python), i testi di
OFL (caratteri Noto) e MIT (sprite) da packaging/licenses, la licenza BSD-3 di go-pmtiles e,
da web/node_modules (serve `npm ci` prima), OFL di IBM Plex, ISC di Lucide e MIT di flag-icons.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# pacchetti di sviluppo/build che non finiscono nell'installer
IGNORE = ["pytest", "pytest-asyncio", "pluggy", "iniconfig", "pyinstaller",
          "pyinstaller-hooks-contrib", "altgraph", "pefile", "pywin32-ctypes", "setuptools",
          "pip", "pip-licenses", "prettytable", "wcwidth", "colorama", "Pygments", "meshlens"]

# (file di destinazione, [licenze in web/node_modules]): copiate a build time
WEB_LICENSES = [
    ("OFL-IBM-Plex.txt", ["@fontsource/ibm-plex-sans/LICENSE", "@fontsource/ibm-plex-mono/LICENSE"]),
    ("ISC-Lucide.txt", ["@lucide/svelte/LICENSE"]),
    ("MIT-flag-icons.txt", ["flag-icons/LICENSE"]),
]


def copy_web_licenses(out: Path) -> None:
    modules = ROOT / "web" / "node_modules"
    for name, sources in WEB_LICENSES:
        parts = []
        for rel in sources:
            src = modules / rel
            if not src.is_file():
                raise SystemExit(f"licenza mancante: {src} (esegui `npm ci` in web/)")
            parts.append(rel.rsplit("/", 1)[0] + "\n\n" + src.read_text(encoding="utf-8").strip() + "\n")
        (out / name).write_text("\n\n".join(parts), encoding="utf-8")


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--with-license-file", "--no-license-path",
         "--format=plain-vertical", "--ignore-packages", *IGNORE],
        capture_output=True, text=True, encoding="utf-8", check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})  # altrimenti stampa in cp1252
    if res.returncode:
        raise SystemExit(f"pip-licenses fallito: {res.stderr.strip()}")
    (out / "python.txt").write_text(res.stdout, encoding="utf-8")
    for f in (ROOT / "packaging" / "licenses").glob("*.txt"):
        shutil.copy2(f, out / f.name)
    copy_web_licenses(out)
    sys.path.insert(0, str(ROOT / "tools"))
    from fetch_pmtiles import fetch  # scarica la zip verificata e ne estrae la LICENSE
    fetch(out.parent / "tools", out)
    print(f"OK licenze in {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("uso: gen_licenses.py <cartella-licenze>")
    main(Path(sys.argv[1]))
