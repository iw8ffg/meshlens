"""Decifratura AES-CTR dei pacchetti Meshtastic."""
import base64
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEFAULT_KEY = bytes.fromhex("d4f1bb3a20290759f0bcffabcf4e6901")


def expand_psk(b64: str) -> bytes:
    """Converte una PSK base64 nella chiave effettiva (b"" = nessuna cifratura)."""
    raw = base64.b64decode(b64)
    if len(raw) == 0 or raw == b"\x00":
        return b""
    if len(raw) == 1:
        n = raw[0]
        if 1 <= n <= 10:
            return DEFAULT_KEY[:-1] + bytes([(DEFAULT_KEY[-1] + n - 1) & 0xFF])
        raise ValueError(f"PSK a un byte non valida: {n}")
    if len(raw) in (16, 32):
        return raw
    raise ValueError(f"lunghezza PSK non valida: {len(raw)} byte")


def make_nonce(packet_id: int, from_node: int) -> bytes:
    return struct.pack("<QI", packet_id, from_node) + b"\0" * 4


def decrypt(key: bytes, packet_id: int, from_node: int, data: bytes) -> bytes:
    """AES-CTR e' simmetrico: serve sia per cifrare sia per decifrare."""
    cipher = Cipher(algorithms.AES(key), modes.CTR(make_nonce(packet_id, from_node)))
    d = cipher.decryptor()
    return d.update(data) + d.finalize()
