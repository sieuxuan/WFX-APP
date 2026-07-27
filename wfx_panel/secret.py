"""Mã hoá mật khẩu at-rest bằng Windows DPAPI (CryptProtectData).

Không thêm phụ thuộc pywin32 — gọi thẳng ``crypt32.dll`` qua ctypes. Blob DPAPI
gắn với tài khoản Windows hiện tại: chỉ đúng user đó, trên đúng máy đó, mới giải
mã được. Nhờ vậy file ``.env`` bị copy đi nơi khác không còn lộ mật khẩu.

Thiết kế cố ý "fail mềm": trên nền tảng không phải Windows hoặc khi DPAPI lỗi,
``protect`` trả ``None`` để caller tự fallback ghi plaintext (giữ app chạy được),
và ``unprotect`` trả ``None`` để caller coi như chưa có mật khẩu (buộc nhập lại).
"""

from __future__ import annotations

import base64
import ctypes
import os

_ENC_PREFIX = "dpapi:v1:"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_ulong),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _available() -> bool:
    return os.name == "nt"


def _to_blob(data: bytes) -> _DataBlob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)),
    )


def _from_blob(blob: _DataBlob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def is_protected(token: object) -> bool:
    return isinstance(token, str) and token.startswith(_ENC_PREFIX)


def protect(plaintext: str) -> str | None:
    """Mã hoá bằng DPAPI; trả token ``dpapi:v1:<base64>`` hoặc None nếu không thể."""
    if not _available() or not plaintext:
        return None
    try:
        crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        blob_in = _to_blob(plaintext.encode("utf-8"))
        blob_out = _DataBlob()
        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )
        if not ok:
            return None
        try:
            raw = _from_blob(blob_out)
        finally:
            kernel32.LocalFree(blob_out.pbData)
        return _ENC_PREFIX + base64.b64encode(raw).decode("ascii")
    except OSError:
        return None


def unprotect(token: str) -> str | None:
    """Giải mã token DPAPI; trả plaintext hoặc None nếu không phải/không giải được."""
    if not is_protected(token) or not _available():
        return None
    try:
        raw = base64.b64decode(token[len(_ENC_PREFIX):])
    except (ValueError, TypeError):
        return None
    try:
        crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        blob_in = _to_blob(raw)
        blob_out = _DataBlob()
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )
        if not ok:
            return None
        try:
            plain = _from_blob(blob_out)
        finally:
            kernel32.LocalFree(blob_out.pbData)
        return plain.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
