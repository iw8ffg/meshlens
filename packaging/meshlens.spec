# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir. Eseguire dalla radice del repository: pyinstaller packaging/meshlens.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
pkg = root / "server" / "meshlens"

datas = [
    (str(root / "web" / "dist"), "web/dist"),
    (str(pkg / "data"), "meshlens/data"),
    (str(pkg / "assets"), "meshlens/assets"),
]
binaries = []
hiddenimports = ["pystray._win32", "PIL.Image", "PIL.ImageDraw"]

REQUIRED = ("meshtastic", "bleak", "uvicorn", "fastapi")
missing = []
for name in ("meshtastic", "bleak", "winrt", "pmtiles", "shapely", "fastapi"):
    try:
        d, b, h = collect_all(name)
    except Exception as e:
        print(f"ATTENZIONE: collect_all({name!r}) non riuscito: {e}")
        missing.append(name)
        continue
    datas += d
    binaries += b
    hiddenimports += h

for name in ("uvicorn", "websockets", "meshlens", "argon2"):
    try:
        hiddenimports += collect_submodules(name)
    except Exception as e:
        print(f"ATTENZIONE: collect_submodules({name!r}) non riuscito: {e}")
        missing.append(name)

import importlib.util

missing += [n for n in REQUIRED if importlib.util.find_spec(n) is None]
fatal = sorted({n for n in missing if n in REQUIRED})
if fatal:
    raise SystemExit(f"Build interrotta: pacchetti obbligatori mancanti: {', '.join(fatal)}")

a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root / "server")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MeshLens",
    console=False,
    icon=str(pkg / "assets" / "meshlens.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MeshLens")
