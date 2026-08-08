from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    value = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return value, buffer


def protect(secret: str) -> str:
    if not secret:
        return ""
    if not hasattr(ctypes, "windll"):
        return "plain:" + base64.b64encode(secret.encode("utf-8")).decode("ascii")
    source, keepalive = _blob(secret.encode("utf-8"))
    result = _DataBlob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "AngelinaDesktopPet", None, None, None, 0, ctypes.byref(result)
    )
    if not ok:
        raise ctypes.WinError()
    try:
        raw = ctypes.string_at(result.pbData, result.cbData)
        return "dpapi:" + base64.b64encode(raw).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)

def unprotect(value: str) -> str:
    if not value:
        return ""
    if value.startswith("plain:"):
        return base64.b64decode(value[6:]).decode("utf-8")
    if not value.startswith("dpapi:") or not hasattr(ctypes, "windll"):
        return ""
    encrypted = base64.b64decode(value[6:])
    source, keepalive = _blob(encrypted)
    result = _DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)
    )
    if not ok:
        return ""
    try:
        return ctypes.string_at(result.pbData, result.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)
