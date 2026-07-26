from pathlib import Path

from wfx_panel import prefs


def test_account_round_trip(tmp_path: Path):
    prefs.save_account("user1", "secret", base_dir=tmp_path)
    loaded = prefs.load_account(base_dir=tmp_path)
    assert loaded == {"user_id": "user1", "password": "secret"}


def test_account_updates_environ(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("WFX_USER_ID", raising=False)
    prefs.save_account("abc", "pw", base_dir=tmp_path)
    import os
    assert os.environ["WFX_USER_ID"] == "abc"
    assert os.environ["WFX_PASSWORD"] == "pw"


def test_load_account_missing_returns_empty(tmp_path: Path):
    assert prefs.load_account(base_dir=tmp_path) == {"user_id": "", "password": ""}


def test_prefs_defaults(tmp_path: Path):
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["theme"] == "light"
    assert loaded["close_after_module"] is True
    assert loaded["hotkey_label"] == "Ctrl + Shift + X"


def test_prefs_partial_update_preserves_others(tmp_path: Path):
    prefs.save_prefs(base_dir=tmp_path, theme="dark")
    prefs.save_prefs(base_dir=tmp_path, close_after_module=False)
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["theme"] == "dark"
    assert loaded["close_after_module"] is False


def test_save_account_temp_file_uses_dot_env_tmp_suffix(tmp_path: Path):
    # .env is a leading-dot name with no suffix, so Path.with_suffix(".env.tmp")
    # APPENDS rather than replaces, producing ".env.env.tmp" (a plaintext-password
    # file no .gitignore rule covers). The correct idiom is with_name(name + ".tmp").
    prefs.save_account("user1", "secret", base_dir=tmp_path)
    assert (tmp_path / ".env.tmp").exists() is False  # cleaned up after replace()
    assert (tmp_path / ".env.env.tmp").exists() is False
    assert (tmp_path / ".env").exists()


def test_resource_dir_is_repo_root_based_on_file_location():
    assert prefs.RESOURCE_DIR == Path(prefs.__file__).resolve().parent.parent
    assert prefs.APP_DIR == prefs.RESOURCE_DIR


def test_data_dir_defaults_to_resource_dir_when_not_frozen(monkeypatch):
    monkeypatch.delattr(__import__("sys"), "frozen", raising=False)
    assert prefs._resolve_data_dir() == prefs.RESOURCE_DIR


def test_data_dir_routes_to_local_appdata_when_frozen(monkeypatch, tmp_path):
    import sys

    fake_local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(fake_local_app_data))
    data_dir = prefs._resolve_data_dir()
    assert data_dir == fake_local_app_data / "WFX-Panel"
    assert data_dir != prefs.RESOURCE_DIR
    # Directory must be created so load/save can write immediately.
    assert data_dir.exists()


def test_new_pref_defaults(tmp_path):
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["hotkey"] == "ctrl+shift+x"
    assert loaded["hotkey_label"] == "Ctrl + Shift + X"
    assert loaded["autostart"] is False
    assert loaded["start_hidden"] is False
    assert loaded["toast_enabled"] is True
    assert loaded["always_on_top"] is True
    assert loaded["stick_to_browser"] is False
    assert loaded["admin_mode"] is False
    assert loaded["update_channel"] == "stable"
    assert loaded["last_update_notice"] == ""


def test_admin_mode_round_trip(tmp_path):
    prefs.save_prefs(base_dir=tmp_path, admin_mode=True)
    assert prefs.load_prefs(base_dir=tmp_path)["admin_mode"] is True


def test_save_account_preserves_hidden_webhook_setting(tmp_path):
    (tmp_path / ".env").write_text(
        'WFX_ERROR_WEBHOOK_URL="https://hooks.example.test/private"\n',
        encoding="utf-8",
    )
    prefs.save_account("user", "password", base_dir=tmp_path)
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "WFX_ERROR_WEBHOOK_URL" in content
    assert "hooks.example.test/private" in content


def test_hotkey_round_trip_and_label_is_derived(tmp_path):
    prefs.save_prefs(base_dir=tmp_path, hotkey="alt+shift+k")
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["hotkey"] == "alt+shift+k"
    assert loaded["hotkey_label"] == "Alt + Shift + K"


def test_hotkey_label_is_never_persisted(tmp_path):
    import json

    prefs.save_prefs(
        base_dir=tmp_path,
        hotkey="ctrl+alt+j",
        hotkey_label="Nhãn Bịa Đặt",
    )
    raw = json.loads((tmp_path / "prefs.json").read_text(encoding="utf-8"))
    assert "hotkey_label" not in raw
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey_label"] == "Ctrl + Alt + J"


def test_corrupt_hotkey_falls_back_to_default(tmp_path):
    (tmp_path / "prefs.json").write_text(
        '{"hotkey": "ctrl+backspace"}', encoding="utf-8"
    )
    assert prefs.load_prefs(base_dir=tmp_path)["hotkey"] == "ctrl+shift+x"


def test_new_prefs_partial_update_preserves_others(tmp_path):
    prefs.save_prefs(base_dir=tmp_path, autostart=True)
    prefs.save_prefs(base_dir=tmp_path, toast_enabled=False)
    prefs.save_prefs(base_dir=tmp_path, start_hidden=True)
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["autostart"] is True
    assert loaded["toast_enabled"] is False
    assert loaded["start_hidden"] is True
    assert loaded["theme"] == "light"


def test_old_settings_survive_new_update_fields(tmp_path):
    import json

    old = {
        "theme": "dark",
        "close_after_module": False,
        "hotkey": "alt+shift+k",
        "autostart": True,
    }
    (tmp_path / "prefs.json").write_text(
        json.dumps(old), encoding="utf-8"
    )
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["theme"] == "dark"
    assert loaded["close_after_module"] is False
    assert loaded["hotkey"] == "alt+shift+k"
    assert loaded["autostart"] is True
    assert loaded["update_channel"] == "stable"

    prefs.save_prefs(
        base_dir=tmp_path,
        update_channel="current",
        last_update_notice="abc123",
    )
    again = prefs.load_prefs(base_dir=tmp_path)
    assert again["theme"] == "dark"
    assert again["hotkey"] == "alt+shift+k"
    assert again["update_channel"] == "current"


def test_legacy_settings_migrate_once_without_overwrite(tmp_path):
    legacy = tmp_path / "old-install"
    data = tmp_path / "LocalAppData" / "WFX-Panel"
    legacy.mkdir()
    data.mkdir(parents=True)
    (legacy / ".env").write_text(
        'WFX_USER_ID="old-user"\nWFX_PASSWORD="old-password"\n',
        encoding="utf-8",
    )
    (legacy / "prefs.json").write_text(
        '{"theme":"dark","hotkey":"alt+shift+k"}',
        encoding="utf-8",
    )

    prefs._migrate_legacy_files(data, [legacy])
    assert prefs.load_account(base_dir=data)["user_id"] == "old-user"
    assert prefs.load_prefs(base_dir=data)["theme"] == "dark"

    # Bản LOCALAPPDATA là nguồn chuẩn sau migration, không bị bản cũ ghi đè.
    prefs.save_account("new-user", "new-password", base_dir=data)
    prefs._migrate_legacy_files(data, [legacy])
    assert prefs.load_account(base_dir=data)["user_id"] == "new-user"
