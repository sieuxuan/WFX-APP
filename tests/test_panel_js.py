from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / "wfx_panel" / "ui" / "panel.js").read_text(encoding="utf-8")


def test_exposes_python_callable_globals():
    for name in ["wfxPushLog", "wfxSetStatus", "wfxSetBusy", "wfxApplyTheme", "wfxBootstrap"]:
        assert f"window.{name}" in JS


def test_wires_all_catalog_actions():
    for action in ["prepare", "code-find", "code-costsheet", "code-bom",
                   "buyer-find", "buyer-costsheet", "buyer-bom"]:
        assert f'"{action}"' in JS


def test_module_groups_present():
    for group in ["Operation", "Finance", "Admin"]:
        assert f'name: "{group}"' in JS
    assert "0003_6200" in JS and "0090_0250" in JS


def test_close_after_module_pref_is_consulted_after_open_module():
    # Finding C: the toggle was persisted/restored but never read anywhere.
    # Sau khi mở module, backend tự chọn: thu thành launcher nếu đang bám
    # browser, hoặc ẩn xuống tray nếu không bám.
    assert "closeAfterModule" in JS
    assert "result.ok && closeAfterModule" in JS
    assert "api()?.dismiss_panel?.()" in JS


def test_header_mousedown_does_not_leak_into_drag_region():
    # Finding D: pywebview's frameless drag (easy_drag=False) attaches a
    # mousedown listener to every '.pywebview-drag-region' element. Header
    # buttons must stop that mousedown from bubbling up to the header so
    # clicking log/settings/close doesn't get treated as a window drag.
    assert '$(".header-actions")?.addEventListener("mousedown"' in JS
    assert "stopPropagation" in JS


def test_exposes_status_globals():
    for name in ["wfxSetChromeStatus", "wfxSetSessionStatus"]:
        assert f"window.{name}" in JS
    assert "result.session_active !== undefined" in JS


def test_wires_new_settings_controls():
    for call in [
        "set_autostart",
        "set_start_hidden",
        "set_toast_enabled",
        "set_always_on_top",
        "set_stick_to_browser",
        "set_hotkey",
        "refresh_status",
        "open_chrome",
        "install_update",
    ]:
        assert call in JS, call


def test_hotkey_capture_is_bound_to_the_button_not_document():
    assert 'hotkeyButton.addEventListener("keydown"' in JS
    assert 'document.addEventListener("keydown"' not in JS


def test_style_status_and_conditional_chrome_visibility_are_wired():
    assert "wfxSetStyleStatus" in JS
    assert "style.internal_costsheet_status" in JS
    assert "banner.hidden = alive === true" in JS


def test_module_buttons_open_modal_before_wfx():
    assert "module.kind === \"catalog\"" in JS
    assert "openModuleModal(button.dataset.moduleId)" in JS
    assert "openModuleDirect(button.dataset.moduleId)" in JS
    assert 'data-module-view="catalog"' not in JS  # hook lives in HTML
    assert 'call("open_module", selectedModule.id)' in JS


def test_only_catalog_uses_modal_other_modules_open_directly():
    assert 'if (module && module.kind === "catalog")' in JS
    assert 'call("open_module", moduleId)' in JS


def test_job_history_retry_and_screenshot_are_wired():
    for method in [
        "get_job_history",
        "retry_job",
        "open_job_screenshot",
        "clear_job_history",
    ]:
        assert method in JS


def test_auto_update_banner_uses_one_click_installer():
    assert "wfxSetUpdateState" in JS
    assert '".update-banner-button"' in JS
    assert "installUpdate(event.currentTarget)" in JS


def test_compact_browser_launcher_is_wired():
    assert "window.wfxSetCompactMode" in JS
    assert '".compact-launcher"' in JS
    assert "expand_from_browser_icon" in JS


def test_old_webview_clipboard_has_a_fallback():
    assert 'document.execCommand("copy")' in JS


def test_account_sheet_stays_open_when_save_fails():
    assert "if (saved && saved.ok)" in JS


def test_admin_modules_are_permission_gated_in_ui():
    assert "visibleModuleGroups" in JS
    assert "!adminAccess || !adminMode" in JS
    assert "adminModuleIds.has(module.id)" in JS
    assert "set_admin_mode" in JS
    assert "window.wfxSetAdminAccess" in JS


def test_feedback_submission_is_wired():
    assert "submit_feedback" in JS
    assert '".feedback-submit-button"' in JS
    assert "window.wfxHandleBackendResult" in JS
