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
