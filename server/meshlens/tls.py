"""Certificato autofirmato per l'HTTPS facoltativo dell'accesso dalla rete locale.

La chiave privata resta in data_dir/tls/key.pem: non si scrive nei log, non entra nel
pacchetto diagnostico né nell'esportazione delle impostazioni."""
import datetime as dt
import hashlib
import ipaddress
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CERT_DAYS = 825  # massimo accettato dai browser per un certificato server
RENEW_BEFORE_DAYS = 30
CERT_FILE = "cert.pem"
KEY_FILE = "key.pem"


@dataclass(frozen=True)
class CertInfo:
    cert_path: Path
    key_path: Path
    fingerprint_sha256: str  # esadecimale maiuscolo separato da ":"
    not_after: float  # secondi epoch


def local_ipv4s() -> list[str]:
    """Indirizzi IPv4 del PC raggiungibili dalla rete (senza loopback e link-local)."""
    found: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    try:  # interfaccia della rotta predefinita: connect su UDP non invia pacchetti
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            found.add(s.getsockname()[0])
    except OSError:
        pass
    ips = []
    for ip in found:
        try:
            a = ipaddress.IPv4Address(ip)
        except ValueError:
            continue
        if not (a.is_loopback or a.is_link_local or a.is_unspecified):
            ips.append(a)
    return [str(a) for a in sorted(ips)]


def _fingerprint(cert: x509.Certificate) -> str:
    digest = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def _info(cert_dir: Path, cert: x509.Certificate) -> CertInfo:
    return CertInfo(cert_dir / CERT_FILE, cert_dir / KEY_FILE, _fingerprint(cert),
                    cert.not_valid_after_utc.timestamp())


def _load_valid(cert_dir: Path, wanted: set, now: float) -> x509.Certificate | None:
    """Il certificato esistente se è leggibile, ha la sua chiave, non scade presto e copre gli IP."""
    try:
        cert = x509.load_pem_x509_certificate((cert_dir / CERT_FILE).read_bytes())
        key = serialization.load_pem_private_key((cert_dir / KEY_FILE).read_bytes(), None)
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (OSError, ValueError, TypeError, x509.ExtensionNotFound):
        return None
    same_key = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    ) == cert.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if not same_key:
        return None
    if cert.not_valid_after_utc.timestamp() - now <= RENEW_BEFORE_DAYS * 86400:
        return None
    if not wanted <= set(san.get_values_for_type(x509.IPAddress)):
        return None
    return cert


def _write_atomic(path: Path, data: bytes, private: bool = False) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0),
                 0o600 if private else 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _generate(cert_dir: Path, wanted: set, now: float) -> x509.Certificate:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MeshLens")])
    start = dt.datetime.fromtimestamp(now - 3600, dt.timezone.utc)  # tollera orologi un po' indietro
    end = dt.datetime.fromtimestamp(now + CERT_DAYS * 86400, dt.timezone.utc)
    san = [x509.DNSName("localhost")] + [x509.IPAddress(a) for a in
                                         sorted(wanted, key=lambda a: (a.version, int(a)))]
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start).not_valid_after(end)
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_dir.mkdir(parents=True, exist_ok=True)
    _write_atomic(cert_dir / KEY_FILE, key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()), private=True)
    _write_atomic(cert_dir / CERT_FILE, cert.public_bytes(serialization.Encoding.PEM))
    return cert


def ensure_cert(cert_dir: Path, ips: list[str], now: float | None = None) -> CertInfo:
    """Certificato valido per localhost, 127.0.0.1 e gli IP dati: riusa quello esistente,
    altrimenti (mancante, illeggibile, in scadenza entro 30 giorni o senza un IP) lo rigenera."""
    cert_dir = Path(cert_dir)
    now = time.time() if now is None else now
    wanted = {ipaddress.ip_address("127.0.0.1"), *(ipaddress.ip_address(ip) for ip in ips)}
    cert = _load_valid(cert_dir, wanted, now) or _generate(cert_dir, wanted, now)
    return _info(cert_dir, cert)
