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
    assert loaded["return_to_list_after_action"] is False
    assert loaded["favorite_module_ids"] == []
    assert loaded["hotkey_label"] == "Ctrl + Shift + X"
    assert loaded["open_costing_file_after_export"] is True
    assert loaded["open_costing_folder_after_export"] is False


def test_prefs_partial_update_preserves_others(tmp_path: Path):
    prefs.save_prefs(base_dir=tmp_path, theme="dark")
    prefs.save_prefs(
        base_dir=tmp_path,
        close_after_module=False,
        return_to_list_after_action=True,
        favorite_module_ids=["0003_6200", "0003_6200", "0004_0050_0020"],
    )
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["theme"] == "dark"
    assert loaded["close_after_module"] is False
    assert loaded["return_to_list_after_action"] is True
    assert loaded["favorite_module_ids"] == ["0003_6200", "0004_0050_0020"]


def test_costing_export_directory_round_trip(tmp_path: Path):
    export_dir = tmp_path / "Costing exports"
    export_dir.mkdir()

    prefs.save_prefs(
        base_dir=tmp_path,
        costing_export_dir=str(export_dir),
    )

    assert prefs.load_prefs(base_dir=tmp_path)["costing_export_dir"] == str(
        export_dir
    )


def test_costing_export_open_options_round_trip(tmp_path: Path):
    prefs.save_prefs(
        base_dir=tmp_path,
        open_costing_file_after_export=False,
        open_costing_folder_after_export=True,
    )

    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["open_costing_file_after_export"] is False
    assert loaded["open_costing_folder_after_export"] is True


def test_save_account_temp_file_uses_dot_env_tmp_suffix(tmp_path: Path):
    # .env is a leading-dot name with no suffix, so Path.with_suffix(".env.tmp")
    # APPENDS rather than replaces, producing ".env.env.tmp" (a plaintext-password
    # file no .gitignore rule covers). The correct idiom is with_name(name + ".tmp").
    prefs.save_account("user1", "secret", base_dir=tmp_path)
    assert (tmp_path / ".env.tmp").exists() is False  # cleaned up after replace()
    assert (tmp_path / ".env.env.tmp").exists() is False
    assert (tmp_path / ".env").exists()


def test_resource_dir_is_repo_root_based_on_file_location():
    assert Path(prefs.__file__).resolve().parent.parent == prefs.RESOURCE_DIR
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
    assert loaded["autostart"] is True
    assert loaded["start_hidden"] is False
    assert loaded["toast_enabled"] is True
    assert loaded["focus_chrome_on_module"] is True
    assert loaded["always_on_top"] is True
    assert "stick_to_browser" not in loaded
    assert loaded["admin_mode"] is False
    assert loaded["update_channel"] == "stable"
    assert loaded["last_update_notice"] == ""
    assert loaded["compact_offset_x"] is None
    assert loaded["compact_offset_y"] is None
    assert loaded["panel_offset_x"] is None
    assert loaded["panel_offset_y"] is None
    assert loaded["catalog_default_folder"] is None


def test_catalog_default_folder_round_trip(tmp_path):
    folder = {
        "user_id": "alice",
        "category_name": "Apparel",
        "category_value": "01",
        "node_id": "101",
        "node_code": "22_1",
        "name": "DEV",
        "path": ["KNIT", "DEV"],
        "path_label": "ignored",
        "kind": "group",
    }
    prefs.save_prefs(
        base_dir=tmp_path,
        catalog_default_folder=folder,
    )
    loaded = prefs.load_prefs(base_dir=tmp_path)["catalog_default_folder"]
    assert loaded == {
        **folder,
        "path_label": "KNIT / DEV",
        "depth": 2,
    }


def test_catalog_default_folder_rejects_unsafe_node_id(tmp_path):
    prefs.save_prefs(
        base_dir=tmp_path,
        catalog_default_folder={
            "user_id": "alice",
            "category_name": "Apparel",
            "category_value": "01",
            "node_id": '1"] script',
            "name": "bad",
            "path": ["bad"],
        },
    )
    assert prefs.load_prefs(
        base_dir=tmp_path
    )["catalog_default_folder"] is None


def test_catalog_default_folder_rejects_non_apparel_category(tmp_path):
    prefs.save_prefs(
        base_dir=tmp_path,
        catalog_default_folder={
            "user_id": "alice",
            "category_name": "Trims",
            "category_value": "06",
            "node_id": "",
            "name": "Master",
            "path": ["Master"],
        },
    )
    assert prefs.load_prefs(
        base_dir=tmp_path
    )["catalog_default_folder"] is None


def test_catalog_folder_cache_round_trip_is_scoped_to_user(tmp_path):
    folders = [
        {
            "node_id": "101",
            "node_code": "KNIT",
            "name": "Development",
            "path": ["KNIT", "Development"],
            "kind": "group",
            "depth": 99,
        },
        {
            "node_id": "102",
            "name": "Active",
            "path": ["KNIT", "Development", "Active"],
            "kind": "folder",
        },
    ]

    saved = prefs.save_catalog_folder_cache(
        "alice",
        folders,
        base_dir=tmp_path,
    )

    assert len(saved) == 2
    assert saved[0]["depth"] == 2
    assert prefs.load_catalog_folder_cache(
        "alice",
        base_dir=tmp_path,
    ) == saved
    assert prefs.load_catalog_folder_cache(
        "bob",
        base_dir=tmp_path,
    ) is None
    assert (tmp_path / "catalog-folders.json").is_file()


def test_catalog_folder_cache_rejects_invalid_or_non_apparel_data(tmp_path):
    assert prefs.save_catalog_folder_cache(
        "alice",
        [{"node_id": '1"]', "name": "bad", "path": ["bad"]}],
        base_dir=tmp_path,
    ) == []
    assert prefs.save_catalog_folder_cache(
        "alice",
        [{"node_id": "1", "name": "Trims", "path": ["Trims"]}],
        category_name="Trims",
        base_dir=tmp_path,
    ) == []


def test_costing_article_cache_round_trip_is_scoped_and_expires(
    tmp_path,
    monkeypatch,
):
    sections = [
        {
            "section_key": "fabric",
            "section_name": "Fabric",
            "options": [
                {"article_code": "FAB-001", "article_name": "Jersey"},
                {"article_code": "FAB-002", "article_name": "Rib"},
            ],
        }
    ]
    monkeypatch.setattr(prefs.time, "time", lambda: 1_000.0)

    saved = prefs.save_costing_article_cache(
        "alice",
        sections,
        base_dir=tmp_path,
    )

    assert saved == sections
    assert prefs.load_costing_article_cache(
        "alice",
        base_dir=tmp_path,
    ) == sections
    assert prefs.load_costing_article_cache(
        "bob",
        base_dir=tmp_path,
    ) is None
    monkeypatch.setattr(prefs.time, "time", lambda: 1_000.0 + 8 * 24 * 60 * 60)
    assert prefs.load_costing_article_cache(
        "alice",
        base_dir=tmp_path,
    ) is None


def test_costing_special_options_cache_is_complete_scoped_and_weekly(
    tmp_path,
    monkeypatch,
):
    sections = [
        {"section_key": "cmcosts", "options": ["Factory A"]},
        {
            "section_key": "productioncosts",
            "options": ["CM (PROCESS001)"],
        },
        {"section_key": "indirectcosts", "options": []},
    ]
    monkeypatch.setattr(prefs.time, "time", lambda: 2_000.0)

    saved = prefs.save_costing_special_options_cache(
        "alice",
        "woven",
        sections,
        base_dir=tmp_path,
    )

    assert saved is not None
    assert prefs.load_costing_special_options_cache(
        "alice",
        "woven",
        base_dir=tmp_path,
    )["sections"] == sections
    assert prefs.load_costing_special_options_cache(
        "bob",
        "woven",
        base_dir=tmp_path,
    ) is None
    assert prefs.load_costing_special_options_cache(
        "alice",
        "knit",
        base_dir=tmp_path,
    ) is None
    monkeypatch.setattr(prefs.time, "time", lambda: 2_000.0 + 8 * 24 * 60 * 60)
    assert prefs.load_costing_special_options_cache(
        "alice",
        "woven",
        base_dir=tmp_path,
    ) is None


def test_costing_special_rescan_preference_defaults_off_and_round_trips(tmp_path):
    assert prefs.load_prefs(tmp_path)["costing_special_options_rescan"] is False
    saved = prefs.save_prefs(
        tmp_path,
        costing_special_options_rescan=True,
    )
    assert saved["costing_special_options_rescan"] is True


def test_admin_mode_round_trip(tmp_path):
    prefs.save_prefs(base_dir=tmp_path, admin_mode=True)
    assert prefs.load_prefs(base_dir=tmp_path)["admin_mode"] is True


def test_compact_icon_position_round_trip(tmp_path):
    prefs.save_prefs(
        base_dir=tmp_path,
        compact_offset_x=640,
        compact_offset_y=420,
    )
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["compact_offset_x"] == 640
    assert loaded["compact_offset_y"] == 420


def test_panel_position_round_trip(tmp_path):
    prefs.save_prefs(
        base_dir=tmp_path,
        panel_offset_x=360,
        panel_offset_y=96,
    )
    loaded = prefs.load_prefs(base_dir=tmp_path)
    assert loaded["panel_offset_x"] == 360
    assert loaded["panel_offset_y"] == 96


def test_save_account_preserves_hidden_webhook_setting(tmp_path):
    (tmp_path / ".env").write_text(
        'WFX_ERROR_WEBHOOK_URL="https://hooks.example.test/private"\n',
        encoding="utf-8",
    )
    prefs.save_account("user", "password", base_dir=tmp_path)
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "WFX_ERROR_WEBHOOK_URL" in content
    assert "hooks.example.test/private" in content


def test_theme_accepts_system_and_rejects_garbage(tmp_path):
    assert prefs.save_prefs(base_dir=tmp_path, theme="system")["theme"] == "system"
    assert prefs.load_prefs(base_dir=tmp_path)["theme"] == "system"
    assert prefs.save_prefs(base_dir=tmp_path, theme="neon")["theme"] == "light"


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


def test_explicitly_disabled_autostart_stays_disabled(tmp_path):
    prefs.save_prefs(base_dir=tmp_path, autostart=False)
    assert prefs.load_prefs(base_dir=tmp_path)["autostart"] is False


def test_focus_chrome_on_module_round_trip(tmp_path):
    prefs.save_prefs(base_dir=tmp_path, focus_chrome_on_module=False)
    assert prefs.load_prefs(base_dir=tmp_path)["focus_chrome_on_module"] is False


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
    assert loaded["return_to_list_after_action"] is False
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


def test_concurrent_save_prefs_keeps_every_setting(tmp_path: Path):
    """save_prefs là read-modify-write và bị gọi từ UI thread, automation worker
    và thread poll cập nhật cùng lúc. Không được mất thay đổi, và không được
    raise FileNotFoundError vì hai bên dùng chung một file .tmp."""
    import threading

    errors: list[BaseException] = []
    barrier = threading.Barrier(4)

    def writer(index: int):
        try:
            barrier.wait(timeout=5)
            for _ in range(15):
                prefs.save_prefs(
                    base_dir=tmp_path,
                    last_update_notice=f"notice-{index}",
                )
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    # File cuối cùng phải còn đọc được (không bị ghi dở/rỗng).
    assert prefs.load_prefs(base_dir=tmp_path)["last_update_notice"].startswith(
        "notice-"
    )
    assert not list(tmp_path.glob("*.tmp"))
