from pathlib import Path

_UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"
JS = (_UI / "panel.js").read_text(encoding="utf-8")
BUBBLE_JS = (_UI / "bubble.js").read_text(encoding="utf-8")


def test_exposes_python_callable_globals():
    for name in ["wfxPushLog", "wfxSetStatus", "wfxSetBusy", "wfxApplyTheme", "wfxBootstrap"]:
        assert f"window.{name}" in JS


def test_wires_all_catalog_actions():
    # Khu tìm Catalog gộp về: 1 ô + segmented Style Code | Buyer Reference,
    # rồi Tìm (primary) · Costing · BOM · File.
    for action in [
        "refresh-folders",
        "browse",
        "find",
        "costsheet",
        "bom",
        "files",
    ]:
        assert f'"{action}"' in JS
    assert "catalogKind" in JS
    assert "catalog-kind-button" in JS
    assert '"catalog_action"' in JS
    assert '"browse_catalog"' in JS
    assert '"scan_catalog_folders"' in JS


def test_module_groups_present():
    for group in ["Operation", "Finance", "Admin"]:
        assert f'name: "{group}"' in JS
    assert "0003_6200" in JS and "0090_0250" in JS


def test_module_cards_do_not_repeat_group_or_workflow_subtitles():
    assert 'class="module-kind"' not in JS
    assert "Workflow nâng cao" not in JS


def test_return_to_list_is_opt_in_and_current_module_is_preserved():
    assert "returnToListAfterAction = false" in JS
    assert "result.ok && returnToListAfterAction" in JS
    assert "set_return_to_list_after_action" in JS
    assert 'if (!$(".module-page").hidden)' in JS


def test_completed_module_actions_use_external_notifications():
    assert "window.wfxShowToast" not in JS
    assert "MODULE_RUN_METHODS" in JS
    for method in [
        "open_module",
        "prepare_catalog",
        "find_code",
        "find_buyer_reference",
        "open_catalog_destination",
        "browse_catalog",
        "catalog_action",
    ]:
        assert f'"{method}"' in JS
    assert "await api()?.focus_automation_browser?.()" in JS
    assert "showToast(" not in JS


def test_hotkey_can_focus_and_select_module_search():
    assert "window.wfxFocusModuleSearch = focusModuleSearch" in JS
    assert 'const input = $(".search-box input")' in JS
    assert "closeSettings();" in JS
    assert 'if (!$(".module-page").hidden)' in JS
    assert "input.focus();" in JS
    assert "input.select();" in JS


def test_module_favorites_are_persisted_and_rendered_before_search():
    assert "favoriteModuleIds" in JS
    assert "toggleModuleFavorite" in JS
    assert "set_module_favorite" in JS
    assert 'class="module-favorite-button"' in JS


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


def test_only_modules_with_workspaces_open_a_detail_page():
    assert "openModulePage(button.dataset.moduleId)" in JS
    assert 'module?.kind === "generic"' in JS
    assert 'data-module-view="catalog"' not in JS  # hook lives in HTML
    assert 'call("open_module", selectedModule.id)' in JS


def test_generic_modules_open_directly_from_the_card():
    assert "async function openModuleDirect(moduleId)" in JS
    assert 'call("open_module", moduleId)' in JS
    assert "openModuleDirect(button.dataset.moduleId)" in JS
    assert "withButtonLoading(" in JS
    assert '$(".generic-module-open").addEventListener("click", openModule)' in JS


def test_special_module_workflows_are_wired():
    for method in [
        "open_sale_asn_new",
        "open_sample_new",
        "search_oc",
        "search_sample",
        "search_sale_asn",
        "open_supplier_category",
        "find_supplier",
        "find_supplier_in_category",
        "find_buyer",
        "toggle_company_foc",
    ]:
        assert f'"{method}"' in JS
    for action in [
        "oc-list",
        "oc-search",
        "sample-list",
        "sample-new",
        "sample-search",
        "sale-asn-list",
        "sale-asn-new",
        "sale-asn-search",
        "supplier-open",
        "supplier-list",
        "supplier-find",
        "buyer-list",
        "buyer-find",
        "company-list",
        "company-toggle-foc",
    ]:
        assert f'"{action}"' in JS
    assert '"supplier-list": () => selectedModule && call("open_module"' in JS
    assert '"find_supplier_in_category"' in JS
    assert '$(".supplier-category").value' in JS


def test_catalog_actions_are_one_click_and_folder_browse_is_separate():
    assert 'runCatalogAction(catalogKind, $(".catalog-query").value)' in JS
    assert 'runCatalogAction(\n      catalogKind, $(".catalog-query").value, "costsheet"' in JS
    assert 'runCatalogAction(\n      catalogKind, $(".catalog-query").value, "bom"' in JS
    assert 'runCatalogAction(\n      catalogKind, $(".catalog-query").value, "files"' in JS
    assert '"catalog_action"' in JS
    assert '"browse_catalog"' in JS
    assert "scanCatalogFolders(false)" in JS
    assert "set_catalog_default_folder" in JS
    assert "clearCatalogResult" in JS
    assert "catalogPreparedCategory" not in JS


def test_multiple_results_are_selectable_in_panel():
    # Feature: nhiều Code hiện danh sách chọn ngay trong panel; chọn 1 Code mở
    # đúng style đó mà không phải nhìn grid trên WFX.
    assert "renderCatalogResults" in JS
    assert '"MULTIPLE_RESULTS"' in JS
    assert "openCatalogResultCode" in JS
    assert "data-result-code" in JS


def test_action_buttons_show_inline_spinner():
    assert "withButtonLoading" in JS
    assert 'classList.add("is-loading")' in JS


def test_bridge_calls_have_a_watchdog_against_hangs():
    # Nếu một bridge call treo, UI phải tự hồi phục thay vì disable vĩnh viễn.
    assert "CALL_WATCHDOG_MS" in JS
    assert "Promise.race([pending, timeout])" in JS
    assert "__timeout" in JS


def test_job_history_uses_friendly_labels():
    assert "JOB_METHOD_LABELS" in JS
    assert "jobMethodLabel(job.method)" in JS


def test_clear_history_requires_confirmation():
    assert "Bấm lần nữa để xóa" in JS
    assert 'button.dataset.confirm' in JS


def test_account_form_submits_on_enter():
    assert '[".user-input", ".password-input"]' in JS
    assert '$(".save-button").click()' in JS


def test_overlays_trap_focus_and_restore_it():
    assert "trapOverlayFocus" in JS
    assert "activeOverlay" in JS
    assert "overlayReturnFocus" in JS
    assert 'addEventListener("keydown", trapOverlayFocus, true)' in JS


def test_autohide_remembers_busy_blur_and_hides_when_idle():
    assert "hidePanelWhenIdle = true" in JS
    assert "if (hidePanelWhenIdle)" in JS
    assert "hasPendingUserInput" not in JS


def test_status_only_renders_in_footer_and_log_text_is_appendable():
    assert 'const status = $(".footer-status")' in JS
    assert "module-page-status" not in JS
    assert "pre.append(document.createTextNode(" in JS
    assert "selectionInLog" in JS
    assert "followLatest" in JS
    assert "if (followLatest) pre.scrollTop = pre.scrollHeight" in JS


def test_listboxes_support_arrow_key_navigation():
    assert "bindListboxKeys" in JS
    assert 'bindListboxKeys($(".catalog-results-list"))' in JS
    assert 'bindListboxKeys($(".catalog-folder-list"))' in JS


def test_system_theme_choice_is_wired():
    assert "resolveTheme" in JS
    assert '"(prefers-color-scheme: dark)"' in JS
    assert '[data-theme-choice]' in JS


def test_tablists_use_selected_state_and_arrow_keys():
    assert "bindTablistKeys" in JS
    assert 'aria-selected' in JS
    assert '"ArrowRight"' in JS


def test_catalog_folder_picker_groups_and_searches_large_trees():
    assert "catalogFolderTree" in JS
    assert "normalizeCatalogSearch" in JS
    assert "renderCatalogFolderList" in JS
    assert "visibleMatches = matches.slice(0, 100)" in JS
    assert '"[data-folder-toggle]"' in JS
    assert '"[data-folder-select]"' in JS
    assert 'data-node-kind="group"' in JS
    assert 'data-catalog-group-action="select"' in JS
    assert 'selectedFolder.kind === "group"' in JS
    assert 'CATALOG_DEFAULT_CATEGORY = "Apparel"' in JS
    assert 'category === CATALOG_DEFAULT_CATEGORY' in JS
    assert 'category !== CATALOG_DEFAULT_CATEGORY' in JS
    assert "!supportsDefault || !catalogFolderEditorOpen" in JS
    assert '$(".catalog-folder-summary").hidden = !supportsDefault' in JS
    assert "if (catalogFolderEditorOpen) scanCatalogFolders(false)" in JS
    assert '$(".catalog-browse-card").hidden' not in JS
    assert "if (catalogFolderScanning) return;" in JS
    assert "data-folder-retry" in JS
    assert 'button.matches("[data-folder-retry]")' in JS
    assert "const hasRetry = Boolean(" in JS
    assert '"scan_catalog_folders",\n      category,\n      Boolean(force)' in JS


def test_module_modal_header_uses_module_description_as_subtitle():
    assert '$(".module-modal-subtitle").textContent' in JS
    assert '$(".module-modal-kicker")' not in JS
    assert '$(".module-modal-description")' not in JS


def test_job_history_retry_and_screenshot_are_wired():
    for method in [
        "get_job_history",
        "retry_job",
        "open_job_screenshot",
        "clear_job_history",
    ]:
        assert method in JS


def test_running_module_has_visible_progress_and_keeps_close_controls_enabled():
    assert "BUSY_MESSAGES" in JS
    assert '$(".operation-progress-text").textContent = message' in JS
    assert 'element.matches(".close-button, .module-back-button")' in JS
    assert '$$("button.is-loading")' in JS


def test_catalog_file_results_are_downloadable_from_backend_tokens():
    assert '"CATALOG_FILES_SCANNED"' in JS
    assert "data-file-id" in JS
    assert 'call("download_catalog_file", fileId)' in JS
    assert "catalog-file-group-label" in JS
    assert "previousSection" in JS
    assert "file.uploaded_on" in JS
    assert "file.uploaded_by" in JS
    assert "file.comments" in JS
    assert 'querySelectorAll(".catalog-file-row")' in JS
    assert 'row.addEventListener("click", () => downloadCatalogFile(row))' in JS


def test_auto_update_banner_uses_one_click_installer():
    assert "wfxSetUpdateState" in JS
    assert '".update-banner-button"' in JS
    assert "installUpdate(event.currentTarget)" in JS
    assert '"Cập nhật phần mềm mới"' in JS
    assert "commit" not in JS.lower()


def test_panel_auto_hides_when_focus_leaves_the_app():
    # Click ra ngoài (blur) → panel tự thu; nếu đang bận thì thu ngay khi xong.
    assert 'window.addEventListener("blur"' in JS
    assert "request_panel_hide" in JS
    assert "hidePanelWhenIdle = true" in JS


def test_bubble_launcher_is_wired():
    # Bubble là trang riêng: bấm → mở panel, kéo ngay → di chuyển, phải → menu.
    assert "toggle_panel" in BUBBLE_JS
    assert "save_bubble_position" in BUBBLE_JS
    assert "note_bubble_interaction" in BUBBLE_JS
    assert "begin_bubble_interaction" in BUBBLE_JS
    assert "end_bubble_interaction" in BUBBLE_JS
    assert "bubble_context_menu" in BUBBLE_JS
    assert "DRAG_THRESHOLD = 4" in BUBBLE_JS
    assert "Math.hypot" in BUBBLE_JS
    assert "setTimeout" not in BUBBLE_JS


def test_wfx_manual_button_is_wired_to_native_browser():
    assert '".manual-button"' in JS
    assert '"open_wfx_manual"' in JS


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
