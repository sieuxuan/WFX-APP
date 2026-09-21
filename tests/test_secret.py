import base64
import ctypes
import os

import pytest

from wfx_panel import prefs, secret

_ON_WINDOWS = os.name == "nt"


def test_is_protected_detects_token():
    assert secret.is_protected("dpapi:v1:AAAA") is True
    assert secret.is_protected("plain") is False
    assert secret.is_protected(None) is False


@pytest.mark.skipif(not _ON_WINDOWS, reason="DPAPI chỉ có trên Windows")
def test_protect_unprotect_round_trip():
    token = secret.protect("s3cret-pass")
    assert token is not None
    assert token.startswith("dpapi:v1:")
    assert "s3cret-pass" not in token  # không lộ plaintext
    assert secret.unprotect(token) == "s3cret-pass"


def test_unprotect_rejects_non_token():
    assert secret.unprotect("not-a-dpapi-token") is None


@pytest.mark.skipif(not _ON_WINDOWS, reason="DPAPI chỉ có trên Windows")
def test_saved_env_stores_ciphertext_not_plaintext(tmp_path):
    prefs.save_account("alice", "top-secret-pw", base_dir=tmp_path)
    raw = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "top-secret-pw" not in raw
    assert "WFX_PASSWORD_ENC=" in raw
    assert "WFX_PASSWORD=" not in raw
    # Nhưng load_account vẫn trả đúng mật khẩu.
    assert prefs.load_account(base_dir=tmp_path)["password"] == "top-secret-pw"


def test_legacy_plaintext_password_still_loads(tmp_path):
    # File .env cũ (trước DPAPI) hoặc file migrate có WFX_PASSWORD plaintext.
    (tmp_path / ".env").write_text(
        'WFX_USER_ID="bob"\nWFX_PASSWORD="legacy-pw"\n',
        encoding="utf-8",
    )
    loaded = prefs.load_account(base_dir=tmp_path)
    assert loaded == {"user_id": "bob", "password": "legacy-pw"}
    raw = (tmp_path / ".env").read_text(encoding="utf-8")
    if _ON_WINDOWS:
        assert "legacy-pw" not in raw
        assert "WFX_PASSWORD_ENC=" in raw
    else:
        assert 'WFX_PASSWORD="legacy-pw"' in raw


@pytest.mark.skipif(not _ON_WINDOWS, reason="DPAPI chỉ có trên Windows")
def test_windows_never_falls_back_to_plaintext_when_dpapi_fails(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(secret, "protect", lambda _password: None)

    with pytest.raises(prefs.CredentialProtectionError):
        prefs.save_account("alice", "must-not-leak", base_dir=tmp_path)

    assert not (tmp_path / ".env").exists()


def test_save_account_preserves_unknown_env_lines(tmp_path):
    (tmp_path / ".env").write_text(
        "WFX_ERROR_WEBHOOK_URL=https://hooks.example.test/x\n"
        "CUSTOM_FLAG=keep-me\n"
        'WFX_USER_ID="old"\n'
        'WFX_PASSWORD="old-pw"\n',
        encoding="utf-8",
    )
    prefs.save_account("newuser", "newpw", base_dir=tmp_path)
    raw = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "WFX_ERROR_WEBHOOK_URL=https://hooks.example.test/x" in raw
    assert "CUSTOM_FLAG=keep-me" in raw
    assert prefs.load_account(base_dir=tmp_path)["user_id"] == "newuser"


class _FakeCrypt:
    """crypt32 giả: điều khiển được kết quả CryptProtect/UnprotectData."""

    def __init__(self, *, ok=True, payload=b"", error=None):
        self.ok = ok
        self.payload = payload
        self.error = error
        self.calls = 0

    def _run(self, blob_in, _desc, _entropy, _reserved, _prompt, _flags, blob_out):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if not self.ok:
            return 0
        data = self.payload
        buffer = ctypes.create_string_buffer(data, len(data))
        target = blob_out._obj
        target.cbData = len(data)
        target.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
        # Giữ buffer sống tới hết lời gọi; LocalFree của fake không giải phóng.
        self._buffer = buffer
        return 1

    CryptProtectData = _run
    CryptUnprotectData = _run


class _FakeKernel:
    def LocalFree(self, _pointer):
        return 0


def _install_fake_dpapi(monkeypatch, crypt):
    monkeypatch.setattr(secret, "_available", lambda: True)
    monkeypatch.setattr(ctypes.windll, "crypt32", crypt, raising=False)
    monkeypatch.setattr(ctypes.windll, "kernel32", _FakeKernel(), raising=False)


def test_protect_refuses_an_empty_password():
    assert secret.protect("") is None


def test_protect_returns_none_off_windows(monkeypatch):
    monkeypatch.setattr(secret, "_available", lambda: False)

    assert secret.protect("pw") is None


def test_protect_returns_none_when_dpapi_reports_failure(monkeypatch):
    _install_fake_dpapi(monkeypatch, _FakeCrypt(ok=False))

    assert secret.protect("pw") is None


def test_protect_returns_none_when_the_dll_call_raises(monkeypatch):
    _install_fake_dpapi(monkeypatch, _FakeCrypt(error=OSError("crypt32 hỏng")))

    assert secret.protect("pw") is None


def test_protect_encodes_the_ciphertext_as_base64(monkeypatch):
    _install_fake_dpapi(monkeypatch, _FakeCrypt(payload=b"\x00\x01\xffcipher"))

    token = secret.protect("pw")

    assert token == "dpapi:v1:" + base64.b64encode(b"\x00\x01\xffcipher").decode()


def test_unprotect_returns_none_off_windows(monkeypatch):
    monkeypatch.setattr(secret, "_available", lambda: False)

    assert secret.unprotect("dpapi:v1:AAAA") is None


def test_unprotect_rejects_a_token_with_broken_base64(monkeypatch):
    monkeypatch.setattr(secret, "_available", lambda: True)

    assert secret.unprotect("dpapi:v1:!!!not-base64!!!") is None


def test_unprotect_returns_none_when_dpapi_reports_failure(monkeypatch):
    _install_fake_dpapi(monkeypatch, _FakeCrypt(ok=False))

    assert secret.unprotect("dpapi:v1:AAAA") is None


def test_unprotect_returns_none_when_the_dll_call_raises(monkeypatch):
    _install_fake_dpapi(monkeypatch, _FakeCrypt(error=OSError("crypt32 hỏng")))

    assert secret.unprotect("dpapi:v1:AAAA") is None


def test_unprotect_returns_none_when_the_plaintext_is_not_utf8(monkeypatch):
    _install_fake_dpapi(monkeypatch, _FakeCrypt(payload=b"\xff\xfe\xfd"))

    assert secret.unprotect("dpapi:v1:AAAA") is None


def test_unprotect_decodes_the_plaintext(monkeypatch):
    _install_fake_dpapi(monkeypatch, _FakeCrypt(payload="mật khẩu".encode()))

    assert secret.unprotect("dpapi:v1:AAAA") == "mật khẩu"


def test_blob_round_trip_keeps_every_byte():
    data = b"\x00binary\xff payload"

    assert secret._from_blob(secret._to_blob(data)) == data
