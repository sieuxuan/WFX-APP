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
