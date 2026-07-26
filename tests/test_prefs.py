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
    assert prefs.load_prefs(base_dir=tmp_path) == {
        "theme": "light",
        "close_after_module": True,
        "hotkey_label": "Ctrl + Shift + X",
    }


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
