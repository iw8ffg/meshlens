"""Riga di comando: meshlens run | tray | reset-pin."""
import argparse
import threading
import webbrowser
from pathlib import Path

from .paths import default_data_dir, is_frozen

PORT = 8686


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meshlens")
    # nella versione installata, senza comando si avvia l'icona di notifica
    sub = parser.add_subparsers(dest="cmd", required=not is_frozen())
    run = sub.add_parser("run", help="avvia MeshLens")
    run.add_argument("--data-dir", default=str(default_data_dir()))
    run.add_argument("--port", type=int, default=PORT)
    run.add_argument("--no-browser", action="store_true")
    tr = sub.add_parser("tray", help="avvia MeshLens con l'icona di notifica")
    tr.add_argument("--data-dir", default=str(default_data_dir()))
    tr.add_argument("--port", type=int, default=PORT)
    tr.add_argument("--no-browser", action="store_true")
    rp = sub.add_parser("reset-pin", help="azzera il PIN")
    rp.add_argument("--data-dir", default=str(default_data_dir()))
    args = parser.parse_args(argv)
    if args.cmd is None:  # solo installata: comando predefinito
        args = parser.parse_args(["tray"])

    if args.cmd == "tray":
        from .tray import run_tray
        return run_tray(Path(args.data_dir), args.port, not args.no_browser)

    if args.cmd == "reset-pin":
        from .auth import Auth
        from .db import connect
        conn = connect(Path(args.data_dir) / "meshlens.db")
        Auth(conn).reset()
        conn.close()
        print("PIN azzerato: al prossimo accesso dal PC potrai sceglierne uno nuovo.")
        return 0

    import uvicorn
    from .app import build
    from .settings import load_settings
    app, rt = build(Path(args.data_dir))
    host = "0.0.0.0" if load_settings(rt.conn)["lan_access"] else "127.0.0.1"
    if not args.no_browser:
        timer = threading.Timer(1.5, webbrowser.open, args=(f"http://127.0.0.1:{args.port}",))
        timer.daemon = True
        timer.start()
    uvicorn.run(app, host=host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
