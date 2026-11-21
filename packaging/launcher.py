"""Punto di ingresso per PyInstaller (il modulo __main__ del pacchetto usa import relativi)."""
import os
import sys


def _fix_std_streams() -> None:
    """Senza console (console=False) stdout/stderr sono None e uvicorn/logging si rompono:
    li reindirizza su %LOCALAPPDATA%\MeshLens\logs\meshlens.log (o su devnull)."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    stream = None
    try:
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        logdir = os.path.join(base, "MeshLens", "logs")
        os.makedirs(logdir, exist_ok=True)
        path = os.path.join(logdir, "meshlens.log")
        try:  # rotazione all'avvio: tiene un solo file precedente
            if os.path.getsize(path) > 1_000_000:
                os.replace(path, path + ".1")
        except OSError:
            pass
        stream = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        stream = None
    if stream is None:
        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


_fix_std_streams()

from meshlens.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
