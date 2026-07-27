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


def test_module_cards_do_not_repeat_group_or_workflow_subtitles():
    assert 'class="module-kind"' not in JS
    assert "Workflow nâng cao" not in JS


def test_close_after_module_pref_is_consulted_after_open_module():
    # Finding C: the toggle was persisted/restored but never read anywhere.
    # Sau khi mở module, backend tự chọn: thu thành launcher nếu đang bám
    # browser, hoặc ẩn xuống tray nếu không bám.
    assert "closeAfterModule" in JS
    assert "result.ok && closeAfterModule" in JS
    assert "api()?.dismiss_panel?.()" in JS


def test_completed_module_actions_use_external_notifications():
    assert "window.wfxShowToast" not in JS
    assert "MODULE_RUN_METHODS" in JS
    for method in ["open_module", "prepare_catalog", "find_code", "find_buyer_reference"]:
        assert f'"{method}"' in JS
    assert "await api()?.focus_automation_browser?.()" in JS
    assert "showToast(" not in JS


def test_hotkey_can_focus_and_select_module_search():
    assert "window.wfxFocusModuleSearch = focusModuleSearch" in JS
    assert 'const input = $(".search-box input")' in JS
    assert "closeSettings();" in JS
    assert "closeModuleModal();" in JS
    assert "input.focus();" in JS
    assert "input.select();" in JS


def test_module_cards_render_svg_icons_instead_of_letter_codes():
    assert "MODULE_ICON_PATHS" in JS
    assert "moduleIconSvg(module.icon)" in JS
    assert '${escapeHtml(module.icon)}</span>' not in JS


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
        "set_focus_chrome_on_module",
        "set_always_on_top",
        "set_hotkey",
        "refresh_status",
        "open_chrome",
        "install_update",
    ]:
        assert call in JS, call
    assert "set_stick_to_browser" not in JS


def test_hotkey_capture_is_bound_to_the_button_not_document():
    assert 'hotkeyButton.addEventListener("keydown"' in JS
    assert 'document.addEventListener("keydown"' not in JS


def test_hotkey_update_does_not_reference_removed_label():
    # The current UI exposes the shortcut only through .hotkey-button. The old
    # .hotkey-label hook was removed from index.html; dereferencing it crashed
    # wfxBootstrap before the panel could finish starting.
    assert '$(".hotkey-label").textContent' not in JS
    assert "hotkeyLabel = state.hotkey_label" in JS
    assert "resetHotkeyButton();" in JS


def test_style_status_and_conditional_chrome_visibility_are_wired():
    assert "wfxSetStyleStatus" in JS
    assert "style.internal_costsheet_status" in JS
    assert "banner.hidden = alive === true" in JS


def test_advanced_module_buttons_open_modal_before_wfx():
    assert '["catalog", "sale_asn", "supplier", "buyer"].includes(module.kind)' in JS
    assert "openModuleModal(button.dataset.moduleId)" in JS
    assert "openModuleDirect(button.dataset.moduleId)" in JS
    assert 'data-module-view="catalog"' not in JS  # hook lives in HTML
    assert 'call("open_module", selectedModule.id)' in JS


def test_generic_modules_still_open_directly():
    assert 'if (module && ["catalog", "sale_asn", "supplier", "buyer"].includes(module.kind))' in JS
    assert 'call("open_module", moduleId)' in JS


def test_special_module_workflows_are_wired():
    for method in [
        "open_sale_asn_new",
        "open_supplier_category",
        "find_supplier",
        "find_buyer",
    ]:
        assert f'"{method}"' in JS
    for action in [
        "sale-asn-list",
        "sale-asn-new",
        "supplier-open",
        "supplier-find",
        "buyer-list",
        "buyer-find",
    ]:
        assert f'"{action}"' in JS


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
    assert '"Cập nhật phần mềm mới"' in JS
    assert "commit" not in JS.lower()


def test_compact_browser_launcher_is_wired():
    assert "window.wfxSetCompactMode" in JS
    assert '".compact-launcher"' in JS
    assert "expand_from_browser_icon" in JS
    assert "begin_compact_drag" in JS
    assert "compactHoldTimer" in JS
    assert "compactHoldTriggered" in JS
    assert "180" in JS


def test_compact_launcher_has_native_context_menu_and_smooth_transition_hooks():
    assert 'compactLauncher.addEventListener("contextmenu"' in JS
    assert "show_compact_context_menu" in JS
    assert "window.wfxPrepareWindowTransition" in JS
    assert "window.wfxFinishWindowTransition" in JS
    assert 'document.documentElement.classList.toggle("compact-mode"' in JS


def test_old_webview_clipboard_has_a_fallback():
    assert 'document.execCommand("copy")' in JS


def test_account_sheet_stays_open_when_save_fails():
    assert "if (!saved || !saved.ok)" in JS
    assert "return;" in JS
    assert "window.setTimeout(closeSettings, 450)" in JS


def test_credentials_are_requested_again_when_missing_or_rejected():
    assert "showCredentialPrompt" in JS
    for code in [
        "MISSING_CREDENTIALS",
        "PASSWORD_REQUIRED",
        "USER_ID_REQUIRED",
        "LOGIN_FAILED",
        "LOGIN_TIMEOUT",
        "NOT_LOGGED_IN",
    ]:
        assert f'"{code}"' in JS
    assert '$(".password-input").value = ""' in JS


def test_missing_credentials_open_a_mandatory_account_form_immediately():
    assert 'settingsOverlay().classList.add("credentials-required")' in JS
    assert 'if (overlay.classList.contains("credentials-required")) return;' in JS
    assert 'name !== "account"' in JS
    assert 'window.setTimeout(\n        () => showCredentialPrompt' not in JS


def test_division_switcher_is_wired_and_highlighted_from_backend_state():
    assert 'call("switch_division", key)' in JS
    assert "window.wfxSetDivisionState" in JS
    assert 'button.setAttribute(\n        "aria-pressed"' in JS


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
