"""Settings: Admin key, khởi động cùng Windows và nút cài bản cập nhật.

CLAUDE.md: thẻ `Dữ liệu Article & Style` dùng cùng điều kiện hiển thị với `Chế
độ quản trị` — tài khoản không có quyền quản trị không thấy cả hai; Admin key
nằm trong `.env` đã mã hóa DPAPI; và Settings có nút `Kiểm tra ngay` cạnh trạng
thái cập nhật tự động.
"""

from __future__ import annotations

import pytest

from tests.test_panel_api import FakeLogin, make_api
from wfx_panel.controllers import settings as settings_module


@pytest.fixture
def api(tmp_path):
    instance, _fake = make_api(tmp_path)
    return instance


@pytest.fixture
def settings(api):
    return api._settings


def _release(**overrides):
    state = {
        "ok": True,
        "code": "UPDATE_AVAILABLE",
        "message": "Có bản 1.1.0",
        "can_update": True,
        "version": "1.1.0",
    }
    state.update(overrides)
    return state


# --- Admin key ------------------------------------------------------------


def test_an_account_without_admin_rights_cannot_save_an_admin_key(api, settings):
    api._admin_access = False

    result = settings.save_sync_admin_key("khoa-bi-mat")

    assert result["code"] == "ADMIN_ACCESS_DENIED"


def test_an_admin_account_saves_the_key_and_is_told_so(api, settings):
    api._admin_access = True

    result = settings.save_sync_admin_key("khoa-bi-mat")

    assert result["code"] == "REFERENCE_ADMIN_KEY_SAVED"
    assert "Đã lưu Admin key" in result["message"]


def test_clearing_the_admin_key_says_it_was_removed(api, settings):
    api._admin_access = True
    settings.save_sync_admin_key("khoa-bi-mat")

    result = settings.save_sync_admin_key("   ")

    assert result["code"] == "REFERENCE_ADMIN_KEY_SAVED"
    assert "Đã xóa Admin key" in result["message"]


def test_an_admin_key_windows_refuses_to_encrypt_is_reported(
    api, settings, monkeypatch
):
    api._admin_access = True

    def refuse(*_args, **_kwargs):
        raise RuntimeError("DPAPI từ chối mã hóa")

    monkeypatch.setattr(api._prefs, "save_sync_admin_key", refuse)

    result = settings.save_sync_admin_key("khoa-bi-mat")

    assert result["code"] == "REFERENCE_ADMIN_KEY_SAVE_FAILED"
    assert "DPAPI" in result["message"]


def test_an_account_without_admin_rights_cannot_publish_reference_data(
    api, settings
):
    api._admin_access = False

    result = settings.publish_reference_data()

    assert result["code"] == "ADMIN_ACCESS_DENIED"


# --- khởi động cùng Windows ----------------------------------------------


def test_a_startup_setting_windows_would_not_write_is_reported(
    api, settings, monkeypatch
):
    monkeypatch.setattr(
        settings_module.autostart, "sync", lambda _wanted: False
    )

    result = settings.set_autostart(True)

    assert result["code"] == "AUTOSTART_FAILED"
    assert result["autostart"] is False


def test_turning_the_startup_setting_off_is_confirmed(
    api, settings, monkeypatch
):
    monkeypatch.setattr(
        settings_module.autostart, "sync", lambda wanted: wanted
    )

    result = settings.set_autostart(False)

    assert result["code"] == "AUTOSTART_SAVED"
    assert "Đã tắt khởi động cùng Windows" in result["message"]


# --- cài bản cập nhật ----------------------------------------------------


def test_the_install_button_does_nothing_when_there_is_no_new_release(
    api, settings, monkeypatch
):
    monkeypatch.setattr(
        settings_module.updater,
        "check_for_updates",
        lambda **_kwargs: _release(can_update=False, code="UPDATE_UP_TO_DATE"),
    )

    assert settings.install_update()["code"] == "UPDATE_UP_TO_DATE"


def test_a_build_without_an_installer_says_so_instead_of_pretending(
    api, settings, monkeypatch
):
    monkeypatch.setattr(
        settings_module.updater, "check_for_updates", lambda **_kw: _release()
    )
    api._update_applier = None

    result = settings.install_update()

    assert result["code"] == "UPDATE_APPLIER_MISSING"
    assert result["can_update"] is False


def test_an_installer_that_refuses_to_start_is_reported_with_its_reason(
    api, settings, monkeypatch
):
    monkeypatch.setattr(
        settings_module.updater, "check_for_updates", lambda **_kw: _release()
    )
    api._update_applier = lambda _state: "Không tìm thấy WFX-Panel.exe"

    result = settings.install_update()

    assert result["code"] == "UPDATE_SCHEDULE_FAILED"
    assert "WFX-Panel.exe" in result["message"]
    assert result["can_update"] is False


def test_a_scheduled_update_tells_the_user_the_app_will_restart(
    api, settings, monkeypatch
):
    monkeypatch.setattr(
        settings_module.updater, "check_for_updates", lambda **_kw: _release()
    )
    api._update_applier = lambda _state: None

    result = settings.install_update()

    assert result["code"] == "UPDATE_SCHEDULED"
    assert "tự mở lại" in result["message"]
    assert result["can_update"] is False


def test_checking_for_updates_always_uses_the_stable_channel(
    api, settings, monkeypatch
):
    seen: list[str] = []
    monkeypatch.setattr(
        settings_module.updater,
        "check_for_updates",
        lambda **kwargs: seen.append(kwargs["channel"]) or _release(),
    )

    settings.check_for_updates()

    assert seen == ["stable"]


def test_an_old_build_without_an_update_applier_never_crashes(tmp_path):
    from wfx_panel import prefs
    from wfx_panel.panel_api import PanelAPI

    api = PanelAPI(
        login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path
    )

    assert api._update_applier is None
