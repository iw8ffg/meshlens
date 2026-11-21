"""Cifratura dei segreti salvati nel database (DPAPI su Windows).

I valori cifrati dipendono dall'utente Windows: un database copiato su un altro PC o profilo
non si decifra, e chi lo legge (load_settings) ottiene "" invece di un'eccezione."""
import base64
import sys
from typing import Protocol

# chiavi di primo livello delle impostazioni salvate cifrate
SECRET_KEYS = ("update_token", "telegram_token")

DPAPI_PREFIX = "dpapi:v1:"
PLAIN_PREFIX = "plain:"
_ENTROPY = b"MeshLens"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class SecretError(Exception):
    """Valore cifrato non decifrabile (altro PC/profilo, dati rovinati)."""


class Protector(Protocol):
    def protect(self, plain: str) -> str: ...

    def unprotect(self, stored: str) -> str:
        """Decifra; un valore non cifrato (vecchio testo in chiaro) e' restituito cosi' com'e'.
        Solleva SecretError se e' cifrato ma non decifrabile."""

    def is_protected(self, stored: str) -> bool: ...


class DpapiProtector:
    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        self._ct = ctypes
        self._blob = DATA_BLOB
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        blob_p = ctypes.POINTER(DATA_BLOB)
        for fn in (crypt32.CryptProtectData, crypt32.CryptUnprotectData):
            fn.restype = wintypes.BOOL
        crypt32.CryptProtectData.argtypes = [
            blob_p, wintypes.LPCWSTR, blob_p, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.DWORD, blob_p]
        crypt32.CryptUnprotectData.argtypes = [
            blob_p, ctypes.POINTER(wintypes.LPWSTR), blob_p, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.DWORD, blob_p]
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        self._crypt32, self._kernel32 = crypt32, kernel32

    def _in_blob(self, data: bytes):
        ct = self._ct
        buf = ct.create_string_buffer(data, len(data))
        blob = self._blob(len(data), ct.cast(buf, ct.POINTER(ct.c_char)))
        return blob, buf  # buf deve restare vivo finche' blob e' in uso

    def _call(self, fn, data: bytes) -> bytes:
        ct = self._ct
        src, _keep1 = self._in_blob(data)
        ent, _keep2 = self._in_blob(_ENTROPY)
        out = self._blob()
        ok = fn(ct.byref(src), None, ct.byref(ent), None, None,
                _CRYPTPROTECT_UI_FORBIDDEN, ct.byref(out))
        if not ok:
            raise SecretError(f"DPAPI non riuscita (errore {ct.get_last_error()})")
        try:
            return ct.string_at(out.pbData, out.cbData)
        finally:
            self._kernel32.LocalFree(ct.cast(out.pbData, ct.c_void_p))

    def protect(self, plain: str) -> str:
        raw = self._call(
            lambda s, d, e, r, p, f, o: self._crypt32.CryptProtectData(s, "MeshLens", e, r, p, f, o),
            plain.encode("utf-8"))
        return DPAPI_PREFIX + base64.b64encode(raw).decode("ascii")

    def unprotect(self, stored: str) -> str:
        if not stored.startswith(DPAPI_PREFIX):
            if stored.startswith(PLAIN_PREFIX):
                raise SecretError("Valore salvato da un sistema senza DPAPI")
            return stored  # vecchio testo in chiaro
        try:
            raw = base64.b64decode(stored[len(DPAPI_PREFIX):], validate=True)
        except ValueError as e:
            raise SecretError("Valore cifrato non valido") from e
        def fn(s, d, e, r, p, f, o):
            return self._crypt32.CryptUnprotectData(s, None, e, r, p, f, o)
        try:
            return self._call(fn, raw).decode("utf-8")
        except UnicodeDecodeError as e:
            raise SecretError("Valore decifrato non valido") from e

    def is_protected(self, stored: str) -> bool:
        return stored.startswith((DPAPI_PREFIX, PLAIN_PREFIX))


class PlainProtector:
    """Sistemi senza DPAPI: nessuna cifratura reale, solo un prefisso."""

    def protect(self, plain: str) -> str:
        return PLAIN_PREFIX + plain

    def unprotect(self, stored: str) -> str:
        if stored.startswith(DPAPI_PREFIX):
            raise SecretError("Valore cifrato con DPAPI: non decifrabile su questo sistema")
        if stored.startswith(PLAIN_PREFIX):
            return stored[len(PLAIN_PREFIX):]
        return stored

    def is_protected(self, stored: str) -> bool:
        return stored.startswith((DPAPI_PREFIX, PLAIN_PREFIX))


def default_protector() -> Protector:
    return DpapiProtector() if sys.platform == "win32" else PlainProtector()


_protector: Protector | None = None


def get_protector() -> Protector:
    global _protector
    if _protector is None:
        _protector = default_protector()
    return _protector


def set_protector(p: Protector | None) -> None:
    """Per i test (None = torna a quello predefinito)."""
    global _protector
    _protector = p
