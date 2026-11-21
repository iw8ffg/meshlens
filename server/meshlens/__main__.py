"""Riga di comando: meshlens run | tray | reset-pin."""
import argparse
import logging
import multiprocessing
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .paths import default_data_dir, is_frozen, logs_dir

PORT = 8686


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()  # non fa nulla se il programma non e' congelato
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

    if args.cmd in ("run", "tray"):
        from .logsetup import setup_logging
        setup_logging(logs_dir())
        logging.getLogger("meshlens").info("Avvio di MeshLens %s (%s)", __version__, args.cmd)

    if args.cmd == "tray":
        from .tray import run_tray
        return run_tray(Path(args.data_dir), args.port, not args.no_browser)

    if args.cmd == "reset-pin":
        from .auth import Auth
        from .backup import open_db
        conn = open_db(Path(args.data_dir))  # un database 1.2.x si migra solo dopo il backup
        Auth(conn).reset()
        conn.close()
        print("PIN azzerato: al prossimo accesso dal PC potrai sceglierne uno nuovo.")
        return 0

    import asyncio
    from uvicorn.config import LOGGING_CONFIG
    from .app import build
    from .serving import make_servers, prepare_serving, serve_all
    from .settings import load_settings
    app, rt = build(Path(args.data_dir), auto_update=True, log_dir=logs_dir())
    settings = load_settings(rt.conn)
    binds, cert, rt.ctx.tls = prepare_serving(Path(args.data_dir), settings["lan_access"],
                                              settings["lan_https"], args.port)
    servers = make_servers(app, binds, cert, LOGGING_CONFIG)
    if not args.no_browser:
        timer = threading.Timer(1.5, webbrowser.open, args=(f"http://127.0.0.1:{args.port}",))
        timer.daemon = True
        timer.start()
    try:
        asyncio.run(serve_all(servers, rt.ctx.tls_errors))
    except KeyboardInterrupt:  # uvicorn rilancia il Ctrl+C dopo l'arresto ordinato
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
