"""Riga di comando: meshlens run | reset-pin."""
import argparse
import threading
import webbrowser
from pathlib import Path

PORT = 8686


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meshlens")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="avvia MeshLens")
    run.add_argument("--data-dir", default="data")
    run.add_argument("--port", type=int, default=PORT)
    run.add_argument("--no-browser", action="store_true")
    rp = sub.add_parser("reset-pin", help="azzera il PIN")
    rp.add_argument("--data-dir", default="data")
    args = parser.parse_args(argv)

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
