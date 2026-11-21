import hashlib
import ipaddress
import time

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from meshlens import tls


def _san(cert_path):
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return cert, san


def test_ensure_cert_creates_and_reuses(tmp_path):
    d = tmp_path / "tls"
    info = tls.ensure_cert(d, ["192.168.1.10"])
    assert info.cert_path == d / "cert.pem" and info.key_path == d / "key.pem"
    assert info.cert_path.is_file() and info.key_path.is_file()
    mtimes = (info.cert_path.stat().st_mtime_ns, info.key_path.stat().st_mtime_ns)

    again = tls.ensure_cert(d, ["192.168.1.10"])
    assert (again.cert_path.stat().st_mtime_ns, again.key_path.stat().st_mtime_ns) == mtimes
    assert again.fingerprint_sha256 == info.fingerprint_sha256

    new = tls.ensure_cert(d, ["192.168.1.10", "10.0.0.5"])
    assert new.fingerprint_sha256 != info.fingerprint_sha256
    _, san = _san(new.cert_path)
    assert ipaddress.ip_address("10.0.0.5") in san.get_values_for_type(x509.IPAddress)


def test_ensure_cert_renews_near_expiry(tmp_path):
    d = tmp_path / "tls"
    info = tls.ensure_cert(d, [])
    assert info.not_after > time.time() + (tls.CERT_DAYS - 2) * 86400
    renewed = tls.ensure_cert(d, [], now=info.not_after - 10 * 86400)
    assert renewed.fingerprint_sha256 != info.fingerprint_sha256
    assert renewed.not_after > info.not_after


def test_ensure_cert_regenerates_unreadable(tmp_path):
    d = tmp_path / "tls"
    info = tls.ensure_cert(d, [])
    info.cert_path.write_text("non un certificato")
    again = tls.ensure_cert(d, [])
    assert again.fingerprint_sha256 != info.fingerprint_sha256
    x509.load_pem_x509_certificate(again.cert_path.read_bytes())


def test_cert_fields(tmp_path):
    info = tls.ensure_cert(tmp_path / "tls", ["192.168.1.10"])
    cert, san = _san(info.cert_path)
    ips = san.get_values_for_type(x509.IPAddress)
    assert ipaddress.ip_address("127.0.0.1") in ips
    assert ipaddress.ip_address("192.168.1.10") in ips
    assert "localhost" in san.get_values_for_type(x509.DNSName)
    cn = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
    assert cn == "MeshLens"
    key = serialization.load_pem_private_key(info.key_path.read_bytes(), None)
    assert isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(key.curve, ec.SECP256R1)
    digest = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    assert info.fingerprint_sha256 == ":".join(digest[i:i + 2] for i in range(0, 64, 2))
    assert info.not_after == cert.not_valid_after_utc.timestamp()


def test_local_ipv4s_are_ipv4_not_loopback():
    for ip in tls.local_ipv4s():
        a = ipaddress.ip_address(ip)
        assert a.version == 4 and not a.is_loopback


def test_ensure_cert_regenerates_on_unsupported_key(tmp_path, monkeypatch):
    from cryptography.exceptions import UnsupportedAlgorithm
    d = tmp_path / "tls"
    info = tls.ensure_cert(d, [])

    def unsupported(*a, **k):
        raise UnsupportedAlgorithm("algoritmo non supportato")

    monkeypatch.setattr(tls.serialization, "load_pem_private_key", unsupported)
    again = tls.ensure_cert(d, [])
    assert again.fingerprint_sha256 != info.fingerprint_sha256
