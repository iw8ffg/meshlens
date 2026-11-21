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

for name in ("meshtastic", "bleak", "winrt", "pmtiles", "shapely"):
    try:
        d, b, h = collect_all(name)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

for name in ("uvicorn", "websockets", "meshlens", "argon2"):
    hiddenimports += collect_submodules(name)

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
