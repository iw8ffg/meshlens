r"""Genera la cartella licenses\ da includere nell'installer.

Uso: python tools/gen_licenses.py <cartella-licenze>
Richiede pip-licenses (solo in build/CI, non e' una dipendenza di esecuzione):
    pip install pip-licenses
Scrive: python.txt (testi completi delle licenze delle dipendenze Python), i testi di
OFL (caratteri Noto) e MIT (sprite) da packaging/licenses e la licenza BSD-3 di go-pmtiles.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# pacchetti di sviluppo/build che non finiscono nell'installer
IGNORE = ["pytest", "pytest-asyncio", "pluggy", "iniconfig", "pyinstaller",
          "pyinstaller-hooks-contrib", "altgraph", "pefile", "pywin32-ctypes", "setuptools",
          "pip", "pip-licenses", "prettytable", "wcwidth", "colorama", "Pygments", "meshlens"]


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--with-license-file", "--no-license-path",
         "--format=plain-vertical", "--ignore-packages", *IGNORE],
        capture_output=True, text=True, encoding="utf-8", check=False)
    if res.returncode:
        raise SystemExit(f"pip-licenses fallito: {res.stderr.strip()}")
    (out / "python.txt").write_text(res.stdout, encoding="utf-8")
    for f in (ROOT / "packaging" / "licenses").glob("*.txt"):
        shutil.copy2(f, out / f.name)
    sys.path.insert(0, str(ROOT / "tools"))
    from fetch_pmtiles import fetch  # scarica la zip verificata e ne estrae la LICENSE
    fetch(out.parent / "tools", out)
    print(f"OK licenze in {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("uso: gen_licenses.py <cartella-licenze>")
    main(Path(sys.argv[1]))
