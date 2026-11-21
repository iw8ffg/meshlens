"""Server uvicorn: loopback in HTTP sempre, più un HTTPS facoltativo per la rete locale.

L'indirizzo del client viene solo dalla connessione (proxy_headers=False): un dispositivo
della rete non può farsi passare per il PC su nessuno dei due ascolti."""
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from .tls import CertInfo, ensure_cert, local_ipv4s

HTTPS_PORT_OFFSET = 1
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Bind:
    host: str
    port: int
    tls: bool


def plan_binds(lan_access: bool, lan_https: bool, port: int) -> list[Bind]:
    if not lan_access:
        return [Bind("127.0.0.1", port, False)]
    if not lan_https:
        return [Bind("0.0.0.0", port, False)]
    return [Bind("127.0.0.1", port, False), Bind("0.0.0.0", port + HTTPS_PORT_OFFSET, True)]


def tls_status(**changes) -> dict:
    """Stato dell'HTTPS mostrato da GET /api/tls."""
    return {"enabled": False, "port": None, "fingerprint_sha256": None, "not_after": None,
            "error": None, **changes}


def prepare_serving(data_dir: Path, lan_access: bool, lan_https: bool, port: int,
                    ips: list[str] | None = None) -> tuple[list[Bind], CertInfo | None, dict]:
    """Ascolti, certificato e stato TLS. Se il certificato non si crea si serve solo il
    loopback: con l'HTTPS chiesto, la rete non si apre in chiaro."""
    binds = plan_binds(lan_access, lan_https, port)
    if not any(b.tls for b in binds):
        return binds, None, tls_status()
    https_port = port + HTTPS_PORT_OFFSET
    try:
        cert = ensure_cert(Path(data_dir) / "tls", local_ipv4s() if ips is None else ips)
    except Exception as e:  # noqa: BLE001 - l'app deve partire comunque
        log.exception("Certificato HTTPS non generabile: si serve solo il loopback")
        return [Bind("127.0.0.1", port, False)], None, tls_status(
            port=https_port,
            error=(f"Impossibile creare il certificato HTTPS ({e}): l'accesso dalla rete è "
                   f"spento. Dal PC resta http://127.0.0.1:{port}."))
    return binds, cert, tls_status(enabled=True, port=https_port,
                                   fingerprint_sha256=cert.fingerprint_sha256,
                                   not_after=cert.not_after)


def make_servers(app, binds: list[Bind], cert: CertInfo | None, log_config) -> list:
    """Un uvicorn.Server per ascolto; solo il primo esegue il lifespan (Runtime.start/stop)."""
    import uvicorn
    servers = []
    for i, b in enumerate(binds):
        ssl = {}
        if b.tls:
            if cert is None:
                raise ValueError("Ascolto HTTPS senza certificato")
            ssl = {"ssl_certfile": str(cert.cert_path), "ssl_keyfile": str(cert.key_path)}
        cfg = uvicorn.Config(app, host=b.host, port=b.port, log_config=log_config,
                             proxy_headers=False, forwarded_allow_ips=None, use_colors=False,
                             lifespan="on" if i == 0 else "off", **ssl)
        servers.append(uvicorn.Server(cfg))
    return servers


async def _serve_secondary(primary, srv, errors: list[str]) -> None:
    # parte dopo il primario: il runtime (lifespan) è già avviato quando arrivano richieste
    while not (primary.started or primary.should_exit or srv.should_exit):
        await asyncio.sleep(0.05)
    if primary.should_exit or srv.should_exit:
        return
    port = srv.config.port
    try:
        await srv.serve()
    except asyncio.CancelledError:
        raise
    except BaseException as e:  # noqa: BLE001 - uvicorn chiama sys.exit(1) se la porta è occupata
        detail = "porta occupata o non disponibile" if isinstance(e, SystemExit) else str(e)
        log.error("HTTPS non avviato sulla porta %s: %s", port, detail)
        errors.append(f"HTTPS non avviato sulla porta {port}: {detail}. "
                      f"Dal PC resta disponibile http://127.0.0.1:{primary.config.port}.")


async def serve_all(servers: list, errors: list[str]) -> None:
    """Il primo server come sempre; un secondario che fallisce finisce in `errors`
    senza fermare il primo. Quando il primo si ferma si fermano tutti."""
    primary, *others = servers
    tasks = [asyncio.create_task(_serve_secondary(primary, s, errors)) for s in others]
    try:
        await primary.serve()
    finally:
        for s in others:
            s.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)
