"""Lưu mật khẩu và Admin key: chỉ DPAPI, và không đụng cấu hình .env khác.

CLAUDE.md: mật khẩu chỉ nằm trong `.env` đã mã hóa DPAPI; tuyệt đối không ghi
mật khẩu vào `os.environ` vì Chrome automation là tiến trình con nên kế thừa
environment của panel, và mọi tiến trình cùng tài khoản Windows đều đọc được.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from wfx_panel import prefs, secret


def _pretend_os(monkeypatch, name):
    """Đổi `os.name` NGAY TRONG namespace của prefs.

    `prefs.os` chính là module `os` thật, nên `setattr(prefs.os, "name", ...)`
    đổi toàn cục và làm pathlib không dựng được Path nữa.
    """
    monkeypatch.setattr(
        prefs, "os", SimpleNamespace(name=name, environ=os.environ)
    )


def _env(tmp_path):
    return prefs._env_path(tmp_path)


def _write_env(tmp_path, text):
    path = _env(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- đọc giá trị .env ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"co dau ngoac"', "co dau ngoac"),
        ("  khong ngoac  ", "khong ngoac"),
        ('"json hong', "json hong"),
        ('"', ""),
    ],
)
def test_env_values_survive_broken_quoting(raw, expected):
    assert prefs._parse_env_value(raw) == expected


# --- mật khẩu -----------------------------------------------------------


def test_a_password_is_stored_encrypted_and_never_in_plain_text(tmp_path):
    prefs.save_account("tester", "mat-khau-that", base_dir=tmp_path)

    text = _env(tmp_path).read_text(encoding="utf-8")
    assert "mat-khau-that" not in text
    assert "WFX_PASSWORD_ENC=" in text
    assert prefs.load_account(base_dir=tmp_path) == {
        "user_id": "tester",
        "password": "mat-khau-that",
    }


def test_saving_an_account_never_puts_the_password_in_the_environment(tmp_path):
    os.environ.pop("WFX_PASSWORD", None)

    prefs.save_account("tester", "mat-khau-that", base_dir=tmp_path)

    assert os.environ.get("WFX_PASSWORD") is None


def test_other_settings_in_the_env_file_are_preserved(tmp_path):
    _write_env(
        tmp_path,
        "# ghi chu\nWFX_SYNC_ADMIN_KEY_ENC=\"abc\"\nKHAC=giu-lai\n",
    )

    prefs.save_account("tester", "mat-khau", base_dir=tmp_path)

    text = _env(tmp_path).read_text(encoding="utf-8")
    assert "KHAC=giu-lai" in text
    assert "# ghi chu" in text


def test_an_env_file_that_cannot_be_read_is_rewritten_from_scratch(
    tmp_path, monkeypatch
):
    path = _write_env(tmp_path, "KHAC=giu-lai\n")
    real_read = type(path).read_text

    def refuse(self, **kwargs):
        if self == path:
            raise PermissionError("file đang bị khóa")
        return real_read(self, **kwargs)

    monkeypatch.setattr(type(path), "read_text", refuse)

    prefs.save_account("tester", "mat-khau", base_dir=tmp_path)

    monkeypatch.undo()
    assert "WFX_PASSWORD_ENC=" in path.read_text(encoding="utf-8")


def test_windows_refusing_to_encrypt_a_password_is_an_error_not_plain_text(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(prefs.secret, "protect", lambda _value: None)
    _pretend_os(monkeypatch, "nt")

    with pytest.raises(prefs.CredentialProtectionError):
        prefs.save_account("tester", "mat-khau", base_dir=tmp_path)


def test_a_legacy_plain_password_is_upgraded_to_dpapi_on_read(
    tmp_path, monkeypatch
):
    _write_env(
        tmp_path,
        'WFX_USER_ID="tester"\nWFX_PASSWORD="mat-khau-cu"\n',
    )

    account = prefs.load_account(base_dir=tmp_path)

    assert account["password"] == "mat-khau-cu"
    text = _env(tmp_path).read_text(encoding="utf-8")
    assert "mat-khau-cu" not in text or "WFX_PASSWORD_ENC=" in text


def test_an_upgrade_that_cannot_be_written_still_returns_the_password(
    tmp_path, monkeypatch
):
    _write_env(
        tmp_path,
        'WFX_USER_ID="tester"\nWFX_PASSWORD="mat-khau-cu"\n',
    )

    def refuse(*_args, **_kwargs):
        raise PermissionError("ổ đĩa chỉ đọc")

    monkeypatch.setattr(prefs, "save_account", refuse)

    assert prefs.load_account(base_dir=tmp_path)["password"] == "mat-khau-cu"


def test_an_account_file_that_does_not_exist_yet_reads_as_empty(tmp_path):
    assert prefs.load_account(base_dir=tmp_path) == {
        "user_id": "",
        "password": "",
    }


# --- Admin key ----------------------------------------------------------


def test_an_admin_key_is_stored_encrypted(tmp_path, monkeypatch):
    monkeypatch.delenv("WFX_SYNC_ADMIN_KEY", raising=False)

    assert prefs.save_sync_admin_key("khoa-bi-mat", base_dir=tmp_path) is True

    text = _env(tmp_path).read_text(encoding="utf-8")
    assert "khoa-bi-mat" not in text
    assert "WFX_SYNC_ADMIN_KEY_ENC=" in text
    assert prefs.load_sync_admin_key(base_dir=tmp_path) == "khoa-bi-mat"


def test_clearing_the_admin_key_removes_it_from_the_file_and_environment(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("WFX_SYNC_ADMIN_KEY", raising=False)
    prefs.save_sync_admin_key("khoa-bi-mat", base_dir=tmp_path)

    assert prefs.save_sync_admin_key("   ", base_dir=tmp_path) is False

    assert "WFX_SYNC_ADMIN_KEY" not in _env(tmp_path).read_text(encoding="utf-8")
    assert os.environ.get("WFX_SYNC_ADMIN_KEY") is None


def test_saving_the_admin_key_keeps_the_stored_password(tmp_path, monkeypatch):
    monkeypatch.delenv("WFX_SYNC_ADMIN_KEY", raising=False)
    prefs.save_account("tester", "mat-khau", base_dir=tmp_path)

    prefs.save_sync_admin_key("khoa-bi-mat", base_dir=tmp_path)

    assert prefs.load_account(base_dir=tmp_path)["password"] == "mat-khau"


def test_windows_refusing_to_encrypt_the_admin_key_is_an_error(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("WFX_SYNC_ADMIN_KEY", raising=False)
    monkeypatch.setattr(prefs.secret, "protect", lambda _value: None)
    _pretend_os(monkeypatch, "nt")

    with pytest.raises(prefs.CredentialProtectionError):
        prefs.save_sync_admin_key("khoa-bi-mat", base_dir=tmp_path)


def test_a_non_windows_machine_may_store_the_admin_key_as_json(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("WFX_SYNC_ADMIN_KEY", raising=False)
    monkeypatch.setattr(prefs.secret, "protect", lambda _value: None)
    _pretend_os(monkeypatch, "posix")

    assert prefs.save_sync_admin_key("khoa-bi-mat", base_dir=tmp_path) is True
    assert "WFX_SYNC_ADMIN_KEY=" in _env(tmp_path).read_text(encoding="utf-8")


def test_an_admin_key_env_file_that_cannot_be_read_is_rewritten(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("WFX_SYNC_ADMIN_KEY", raising=False)
    path = _write_env(tmp_path, "KHAC=giu-lai\n")
    real_read = type(path).read_text

    def refuse(self, **kwargs):
        if self == path:
            raise PermissionError("file đang bị khóa")
        return real_read(self, **kwargs)

    monkeypatch.setattr(type(path), "read_text", refuse)

    prefs.save_sync_admin_key("khoa-bi-mat", base_dir=tmp_path)

    monkeypatch.undo()
    assert "WFX_SYNC_ADMIN_KEY_ENC=" in path.read_text(encoding="utf-8")


def test_a_runtime_admin_key_wins_over_the_stored_one(tmp_path, monkeypatch):
    prefs.save_sync_admin_key("trong-file", base_dir=tmp_path)
    monkeypatch.setenv("WFX_SYNC_ADMIN_KEY", "tu-moi-truong")

    assert prefs.load_sync_admin_key(base_dir=tmp_path) == "tu-moi-truong"


def test_a_plain_admin_key_in_the_file_is_still_readable(tmp_path, monkeypatch):
    monkeypatch.delenv("WFX_SYNC_ADMIN_KEY", raising=False)
    _write_env(tmp_path, 'WFX_SYNC_ADMIN_KEY="khoa-cu"\n')

    assert prefs.load_sync_admin_key(base_dir=tmp_path) == "khoa-cu"


# --- danh sách module yêu thích ----------------------------------------


def test_favourites_are_deduplicated_and_capped(tmp_path):
    prefs.save_prefs(
        base_dir=tmp_path,
        favorite_module_ids=["a", "a", " ", "b"] + [f"m{i}" for i in range(80)],
    )

    favourites = prefs.load_prefs(base_dir=tmp_path)["favorite_module_ids"]

    assert favourites[:2] == ["a", "b"]
    assert len(favourites) == 50
    assert len(set(favourites)) == len(favourites)


def test_a_favourites_value_that_is_not_a_list_is_ignored(tmp_path):
    path = prefs._prefs_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"favorite_module_ids": "khong phai list"}), encoding="utf-8"
    )

    assert prefs.load_prefs(base_dir=tmp_path)["favorite_module_ids"] == []


def test_a_stored_favourites_list_longer_than_the_cap_is_trimmed_on_read(
    tmp_path,
):
    path = prefs._prefs_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"favorite_module_ids": [f"m{i}" for i in range(80)]}),
        encoding="utf-8",
    )

    assert len(prefs.load_prefs(base_dir=tmp_path)["favorite_module_ids"]) == 50


# --- DPAPI --------------------------------------------------------------


def test_a_value_protected_by_dpapi_round_trips():
    protected = secret.protect("bi-mat")

    if protected is None:
        pytest.skip("Máy này không có DPAPI")
    assert secret.unprotect(protected) == "bi-mat"


def test_an_unreadable_blob_unprotects_to_nothing():
    assert secret.unprotect("khong-phai-blob") in (None, "")


def test_an_encrypted_admin_key_is_decrypted_on_read(tmp_path, monkeypatch):
    monkeypatch.delenv("WFX_SYNC_ADMIN_KEY", raising=False)
    monkeypatch.setattr(prefs.secret, "protect", lambda value: f"enc:{value}")
    monkeypatch.setattr(
        prefs.secret,
        "unprotect",
        lambda blob: str(blob).strip('"').removeprefix("enc:"),
    )

    prefs.save_sync_admin_key("khoa-bi-mat", base_dir=tmp_path)
    monkeypatch.delenv("WFX_SYNC_ADMIN_KEY", raising=False)

    assert prefs.load_sync_admin_key(base_dir=tmp_path) == "khoa-bi-mat"
