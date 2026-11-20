"""Strumento di prova radio Meshtastic (USB seriale e Bluetooth LE).

Uso:
    python tools/radio_probe.py ports
    python tools/radio_probe.py ble-scan
    python tools/radio_probe.py usb COM5 [--seconds 60] [--send "testo"]
    python tools/radio_probe.py ble <indirizzo|nome> [--seconds 60] [--send "testo"]

Serve solo a provare le radio da riga di comando: non e' collegato all'app.
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 - la console potrebbe non supportarlo
    pass


def _err(msg: str) -> None:
    print(f"ERRORE: {msg}", file=sys.stderr, flush=True)


def _describe_exc(exc: BaseException) -> str:
    if isinstance(exc, SystemExit):
        return f"la libreria ha terminato il programma (SystemExit {exc.code!r})"
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


# --------------------------------------------------------------------- ports
def cmd_ports(_args: argparse.Namespace) -> int:
    try:
        from serial.tools import list_ports

        ports = sorted(list_ports.comports(), key=lambda p: p.device)
    except BaseException as exc:  # noqa: BLE001
        _err(f"impossibile elencare le porte seriali ({_describe_exc(exc)})")
        return 1
    if not ports:
        print("Nessuna porta seriale trovata.")
        return 0
    print(f"{len(ports)} porta/e seriale/i:")
    for p in ports:
        vid = f"{p.vid:04x}" if p.vid is not None else "----"
        pid = f"{p.pid:04x}" if p.pid is not None else "----"
        print(f"  {p.device:<8} VID:PID={vid}:{pid}  {p.description}")
    return 0


# ----------------------------------------------------------------- ble-scan
def cmd_ble_scan(_args: argparse.Namespace) -> int:
    print("Scansione Bluetooth LE in corso (circa 10 secondi)...", flush=True)
    try:
        from meshtastic.ble_interface import BLEInterface

        devices = BLEInterface.scan()
    except BaseException as exc:  # noqa: BLE001
        _err(
            "scansione Bluetooth non riuscita. Controlla che il Bluetooth sia "
            f"acceso e disponibile su questo PC. Dettaglio: {_describe_exc(exc)}"
        )
        return 1
    if not devices:
        print("Nessun dispositivo Meshtastic trovato via Bluetooth.")
        return 0
    print(f"{len(devices)} dispositivo/i Meshtastic:")
    for d in devices:
        print(f"  {d.name or '(senza nome)'}  {d.address}")
    return 0


# ------------------------------------------------------------ connessione
def _print_summary(iface) -> None:
    meta = getattr(iface, "metadata", None)
    fw = getattr(meta, "firmware_version", None) or "sconosciuto"
    info = None
    try:
        info = iface.getMyNodeInfo()
    except BaseException:  # noqa: BLE001
        info = None
    user = (info or {}).get("user", {}) if isinstance(info, dict) else {}
    node_id = user.get("id") or "sconosciuto"
    name = user.get("longName") or "sconosciuto"
    short = user.get("shortName") or "?"
    print(f"Nodo locale: id={node_id} nome={name} ({short}) firmware={fw}", flush=True)

    nodes = getattr(iface, "nodes", None) or {}
    print(f"Nodi noti: {len(nodes)}", flush=True)

    try:
        from meshtastic.protobuf import channel_pb2

        channels = getattr(iface.localNode, "channels", None) or []
        print(f"Canali ({len(channels)}):", flush=True)
        for ch in channels:
            role = channel_pb2.Channel.Role.Name(ch.role)
            if role == "DISABLED":
                continue
            print(f"  [{ch.index}] {role} nome={ch.settings.name or '(default)'}",
                  flush=True)
    except BaseException as exc:  # noqa: BLE001
        print(f"Canali non leggibili: {_describe_exc(exc)}", flush=True)


def _make_listener(state: dict):
    def on_receive(packet, interface=None):  # noqa: ANN001
        if state.get("iface") is not None and interface is not state["iface"]:
            return
        try:
            decoded = packet.get("decoded") or {}
            port = decoded.get("portnum", "?")
            hs, hl = packet.get("hopStart"), packet.get("hopLimit")
            hops = hs - hl if hs is not None and hl is not None else "?"
            print(
                f"[{time.strftime('%H:%M:%S')}] da={packet.get('fromId', '?')} "
                f"porta={port} snr={packet.get('rxSnr', '?')} "
                f"rssi={packet.get('rxRssi', '?')} salti={hops}",
                flush=True,
            )
            sent_id = state.get("sent_id")
            if (port == "ROUTING_APP" and sent_id is not None
                    and decoded.get("requestId") == sent_id):
                reason = (decoded.get("routing") or {}).get("errorReason", "?")
                state["ack"] = reason
                print(f"  -> ACK per il messaggio {sent_id}: {reason}", flush=True)
        except BaseException as exc:  # noqa: BLE001 - non rompere il thread pubsub
            print(f"  (pacchetto non leggibile: {_describe_exc(exc)})", flush=True)

    return on_receive


def _run(open_iface, label: str, args: argparse.Namespace) -> int:
    from pubsub import pub

    state: dict = {"iface": None, "sent_id": None, "ack": None}
    listener = _make_listener(state)  # riferimento forte (pubsub e' debole)
    pub.subscribe(listener, "meshtastic.receive")

    iface = None
    rc = 0
    try:
        print(f"Connessione a {label}...", flush=True)
        t0 = time.monotonic()
        try:
            iface = open_iface()
        except BaseException as exc:  # noqa: BLE001
            _err(f"connessione non riuscita ({_describe_exc(exc)})")
            return 1
        state["iface"] = iface
        print(f"Connesso in {time.monotonic() - t0:.1f} s.", flush=True)

        _print_summary(iface)

        if args.send:
            try:
                t1 = time.monotonic()
                pkt = iface.sendText(args.send, channelIndex=0, wantAck=True)
                state["sent_id"] = getattr(pkt, "id", None)
                print(f"Messaggio inviato (id={state['sent_id']}, "
                      f"{time.monotonic() - t1:.1f} s). In attesa dell'ack...",
                      flush=True)
            except BaseException as exc:  # noqa: BLE001
                _err(f"invio non riuscito ({_describe_exc(exc)})")
                rc = 1

        print(f"Ascolto pacchetti per {args.seconds} s (Ctrl+C per fermare)...",
              flush=True)
        end = time.monotonic() + args.seconds
        try:
            while time.monotonic() < end:
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("Interrotto dall'utente.", flush=True)

        if args.send:
            print(f"Esito ack: {state['ack'] or 'nessun ack ricevuto'}", flush=True)
    except BaseException as exc:  # noqa: BLE001
        _err(f"errore durante la prova ({_describe_exc(exc)})")
        rc = 1
    finally:
        try:
            pub.unsubscribe(listener, "meshtastic.receive")
        except BaseException:  # noqa: BLE001
            pass
        if iface is not None:
            t2 = time.monotonic()
            try:
                iface.close()
                print(f"close() completato in {time.monotonic() - t2:.2f} s.",
                      flush=True)
            except BaseException as exc:  # noqa: BLE001
                print(f"close() fallito dopo {time.monotonic() - t2:.2f} s "
                      f"({_describe_exc(exc)}).", flush=True)
                rc = 1
    return rc


def cmd_usb(args: argparse.Namespace) -> int:
    def open_iface():
        from meshtastic.serial_interface import SerialInterface

        return SerialInterface(devPath=args.port)

    return _run(open_iface, f"porta USB {args.port}", args)


def cmd_ble(args: argparse.Namespace) -> int:
    def open_iface():
        from meshtastic.ble_interface import BLEInterface

        return BLEInterface(args.address)

    return _run(open_iface, f"Bluetooth {args.address}", args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Prova radio Meshtastic (USB/BLE).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ports", help="elenca le porte seriali").set_defaults(fn=cmd_ports)
    sub.add_parser("ble-scan", help="cerca radio via Bluetooth LE").set_defaults(
        fn=cmd_ble_scan)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--seconds", type=int, default=60,
                        help="secondi di ascolto (default 60)")
        sp.add_argument("--send", metavar="TESTO",
                        help="invia un messaggio sul canale 0 e attende l'ack")

    u = sub.add_parser("usb", help="prova una radio USB")
    u.add_argument("port", help="porta seriale, es. COM5")
    common(u)
    u.set_defaults(fn=cmd_usb)

    b = sub.add_parser("ble", help="prova una radio Bluetooth LE")
    b.add_argument("address", help="indirizzo o nome della radio")
    common(b)
    b.set_defaults(fn=cmd_ble)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
