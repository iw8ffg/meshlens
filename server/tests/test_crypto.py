import base64

import pytest

from meshlens.crypto import DEFAULT_KEY, expand_psk, make_nonce, decrypt


def test_expand_default_psk():
    assert expand_psk("AQ==") == bytes.fromhex("d4f1bb3a20290759f0bcffabcf4e6901")


def test_expand_simple_psk_variant():
    assert expand_psk("Ag==")[-1] == DEFAULT_KEY[-1] + 1


def test_expand_none_and_full_and_invalid():
    assert expand_psk("AA==") == b""
    k = bytes(range(32))
    assert expand_psk(base64.b64encode(k).decode()) == k
    with pytest.raises(ValueError):
        expand_psk(base64.b64encode(b"abc").decode())


def test_nonce_layout():
    assert make_nonce(0x01020304, 0xa1b2c3d4) == bytes.fromhex("0403020100000000d4c3b2a100000000")


def test_decrypt_roundtrip_is_symmetric():
    plain = b"\x08\x01\x12\x05ciao!"
    enc = decrypt(DEFAULT_KEY, 42, 0xa1b2c3d4, plain)
    assert enc != plain
    assert decrypt(DEFAULT_KEY, 42, 0xa1b2c3d4, enc) == plain
