from pathlib import Path

_UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"
JS = (_UI / "panel.js").read_text(encoding="utf-8")
BUBBLE_JS = (_UI / "bubble.js").read_text(encoding="utf-8")


def test_exposes_python_callable_globals():
    for name in ["wfxPushLog", "wfxSetStatus", "wfxSetBusy", "wfxApplyTheme", "wfxBootstrap"]:
        assert f"window.{name}" in JS


def test_color_report_progress_is_guarded_by_an_active_flag():
    start = JS.index("function updateColorReportProgress")
    body = JS[start : JS.index("\n  function ", start + 10)]

    assert "colorReportRunActive" in body
    assert "/(\\d+\\/\\d+)\\s*$/" in body


def test_color_report_result_card_is_cleared_when_the_module_reopens():
    start = JS.index("function resetColorReportProgress")
    body = JS[start : JS.index("\n  function ", start + 10)]

    assert '$(".color-report-result-card").hidden = true' in body


def test_color_report_result_does_not_cuon_man_hinh_tu_dong():
    start = JS.index("function renderColorReportResult")
    body = JS[start : JS.index("\n  async function ", start + 10)]

    assert "scrollIntoView" not in body
    assert "failedRefs" in body


def test_color_report_select_all_only_touches_visible_rows():
    start = JS.index("function setColorReportSelection")
    body = JS[start : JS.index("\n  function ", start + 10)]

    assert "row.hidden" in body


def test_color_report_renders_cascade_levels_even_when_style_list_is_empty():
    start = JS.index("async function loadColorReportOptions")
    body = JS[start : JS.index("\n  async function ", start + 10)]

    assert "if (result?.levels) renderColorReportLevels(result)" in body


def test_color_report_ignores_a_late_response_from_an_older_request():
    start = JS.index("async function loadColorReportOptions")
    body = JS[start : JS.index("\n  async function ", start + 10)]

    assert "colorReportOptionsRevision" in body
    assert "revision !== colorReportOptionsRevision" in body


def _push_log_body():
    start = JS.index("function pushLog(line) {")
    return JS[start : JS.index("\n  window.wfxPushLog", start)]


def test_push_log_is_capped_and_never_reads_the_whole_log_back():
    """App nằm ở khay hệ thống cả ngày nên <pre> log phải có trần.

    ``pre.textContent`` nối lại toàn bộ text node con; đọc nó trên từng dòng
    làm chi phí ghi log tăng theo bình phương số dòng đã ghi.
    """
    body = _push_log_body()

    assert "pre.textContent" not in body.replace('pre.textContent = "";', "")
    assert "pre.childNodes.length" in body
    assert "LOG_MAX_LINES" in body
    assert "pre.removeChild(pre.firstChild)" in body
    assert "const LOG_MAX_LINES = 2000;" in JS


def test_push_log_drops_the_leading_newline_after_trimming():
    """Mỗi dòng mang sẵn "\\n" ở đầu, nên dòng đầu còn lại phải được gọt."""
    body = _push_log_body()

    assert 'first.nodeValue.charCodeAt(0) === 10' in body
    assert "first.nodeValue = first.nodeValue.slice(1)" in body
    assert body.index("pre.removeChild(pre.firstChild)") < body.index(
        "first.nodeValue = first.nodeValue.slice(1)"
    )


def test_clearing_history_restores_the_exact_log_placeholder():
    """pushLog nhận diện ô trống bằng đúng chuỗi này, không đọc textContent."""
    assert 'const LOG_PLACEHOLDER = "Chưa có nhật ký hệ thống.";' in JS
    assert '$(".catalog-log").textContent = LOG_PLACEHOLDER;' in JS


def test_wires_all_catalog_actions():
    # Catalog dùng Article Code và đổi Buyer Reference/Article Name theo category.
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


def test_rmpo_results_and_status_actions_are_wired():
    assert '"RMPO_RESULTS_READY"' in JS
    assert '"run_rmpo_action"' in JS
    assert 'runRmpoAction("check_po")' in JS
    assert 'runRmpoAction("edit_po")' in JS
    assert 'runRmpoAction("check_received")' in JS
    assert 'status === "received"' in JS
    assert '["received", "part received"]' in JS


def test_grn_handoff_checkpoint_site_and_search_are_wired():
    for method in (
        "prepare_grn_receipt",
        "continue_grn_receipt",
        "finalize_grn_receipt",
        "search_grn",
    ):
        assert f'"{method}"' in JS
    assert "handoffRmpoToGrn" in JS
    assert 'openModulePage("grn_receipt")' in JS
    assert '"grn-rmpo-list": () => openModulePage("0005_0050_0020")' in JS
    assert "GRN_SOURCING_ASN_READY" in JS
    assert "GRN_SITE_SELECTION_REQUIRED" in JS
    assert "Bạn xác nhận đã nhập đủ thông tin" in JS
    assert "moduleFilterKinds.grn" in JS


def test_wires_bulk_style_review_and_manual_save_flow():
    for method in [
        "download_style_template",
        "choose_style_import_file",
        "review_catalog_style_import",
        "prepare_catalog_style_row",
        "clear_catalog_style_import",
    ]:
        assert f'"{method}"' in JS
    assert "STYLE_COPY_MULTIPLE_RESULTS" in JS
    assert "Tôi đã Save · Chuẩn bị dòng tiếp theo" in JS
    assert "catalogStyleAutoSave" in JS
    assert 'download_style_template", groupId' in JS


def test_costing_weekly_scan_and_clear_all_controls_are_wired():
    assert '"set_costing_special_options_rescan"' in JS
    assert "setCostingSpecialOptionsState" in JS
    assert '"clear-dependencies"' in JS
    assert '"clear_catalog_costing_dependencies"' in JS
    assert "window.confirm(" in JS
    assert '$(".open-costing-folder-input")' not in JS


def test_module_groups_present():
    for group in ["Operation", "Finance", "Admin"]:
        assert f'name: "{group}"' in JS
    assert "0003_6200" in JS and "0090_0250" in JS


def test_module_cards_do_not_repeat_group_or_workflow_subtitles():
    assert 'class="module-kind"' not in JS
    assert "Workflow nâng cao" not in JS


def test_oc_workspace_wires_template_new_and_revise_flows():
    for method in (
        "download_oc_template",
        "choose_oc_upload_file",
        "review_oc_upload",
        "cancel_oc_upload_review",
        "confirm_oc_upload",
        "open_oc_revision_report",
    ):
        assert f'"{method}"' in JS
    assert 'uploadOcFile("new")' in JS
    assert 'uploadOcFile("revise")' in JS
    assert 'call("review_oc_upload", mode, selected.file_path)' in JS
    assert 'call("confirm_oc_upload", token)' in JS
    assert 'call("upload_oc", mode, selected.file_path)' not in JS
    assert "let ocSelectionRevision = 0" in JS
    assert "selectionRevision !== ocSelectionRevision" in JS
    assert 'callQuiet("cancel_oc_upload_review", result.review_token)' in JS


def test_gdn_dispatch_requires_grn_confirmation_and_calls_one_flow():
    assert 'id: "gdn_dispatch"' in JS
    assert 'kind: "gdn_dispatch"' in JS
    assert '"gdn-dispatch-submit": submitGdnDispatch' in JS
    assert 'runSelectedModuleAction("run_gdn_dispatch", invoice, confirmed)' in JS
    assert "syncGdnDispatchAction" in JS
    assert 'method === "run_gdn_dispatch"' in JS
    assert "run_gdn_dispatch: updateGdnProgress" in JS
    assert '"gdn-status": () => runSelectedModuleAction("open_gdn_status")' in JS
    assert "checkpoint === \"inspect_edi\"" in JS


def test_search_forms_validate_before_calling_backend():
    assert "const INPUT_VALIDATION_GROUPS" in JS
    assert "syncAllInputValidation()" in JS
    assert "button.disabled = busy || !valid" in JS
    for group in (
        "indent",
        "advance-pr",
        "supplier-invoice",
        "supplier-invoice-cancel",
        "expense-invoice",
    ):
        assert f'"{group}"' in JS


def test_sale_asn_documents_two_phase_export_is_wired():
    for method in (
        "prepare_sale_asn_documents",
        "choose_sale_asn_export_file",
        "save_sale_asn_documents",
        "cancel_sale_asn_documents",
    ):
        assert f'"{method}"' in JS
    assert 'prepared.invoice_no || "Invoice"' in JS
    assert "prepared.export_token" in JS


def test_sale_asn_create_flow_is_reviewed_and_resumable():
    for method in (
        "download_sale_asn_template",
        "choose_sale_asn_import_file",
        "prepare_sale_asn_create",
        "scan_sale_asn_buyers",
        "start_sale_asn_create",
        "continue_sale_asn_create",
        "skip_sale_asn_create_step",
        "cancel_sale_asn_create",
    ):
        assert f'"{method}"' in JS
    assert "SALE_ASN_PO_SELECTION_REQUIRED" in JS
    assert "result.resumable" in JS
    assert 'manual ? "Thêm dòng đã chọn" : "Thử lại bước này"' in JS
    assert '"continue_sale_asn_create",\n      saleAsnReviewToken,\n      selectedCandidates' in JS
    assert "saleAsnExactBuyer" in JS
    assert "saleAsnReviewToken" in JS
    assert 'showSaleAsnView("lookup", { focus: false })' in JS
    assert 'showSaleAsnView("create"' in JS
    # Mở module phải vào thẳng thẻ Tạo mới, không rơi về Tra cứu như bản cũ.
    opened = JS[JS.index('module.kind === "sale_asn"') :][:800]
    assert 'showSaleAsnView("create", { focus: false })' in opened
    assert "showSaleAsnView(\"lookup\"" not in opened
    assert "openSaleAsnAdvanced()" in opened


def test_sale_asn_file_check_renders_a_prominent_error_card():
    assert "function renderSaleAsnFileError(result)" in JS
    assert "Không kiểm tra được file Sale ASN" in JS
    assert "File chưa hợp lệ. Xem chi tiết bên dưới." in JS
    assert "errors.filter(Boolean).slice(0, 12)" in JS
    assert "destinationStat.hidden = !destination" in JS


def test_sale_asn_done_result_renders_automatic_price_check_and_can_export():
    assert 'const SALE_ASN_STAGES = [...SALE_ASN_USER_STAGES, "price_check"]' in JS
    assert "saleAsnPriceCheck = result.price_check || null" in JS
    assert '"sale-asn-export-price-check": exportSaleAsnPriceCheck' in JS
    assert 'call("export_sale_asn_price_check", saleAsnPriceCheck, selected.file_path)' in JS
    assert "function renderSaleAsnPriceCheck(result)" in JS
    for label in (
        "Total Quantity",
        "Value In Doc Currency",
        "Net Value In Doc Currency",
    ):
        assert label in JS


def test_sale_asn_progress_card_streams_five_stages():
    # Tiến độ dùng chung sink backend nhưng phải rẽ theo method, không đè GDN.
    assert "start_sale_asn_create: updateSaleAsnProgress" in JS
    assert "continue_sale_asn_create: updateSaleAsnProgress" in JS
    assert "skip_sale_asn_create_step: updateSaleAsnProgress" in JS
    assert 'const SALE_ASN_USER_STAGES = ["po", "order_details", "style_details", "shipping_info"]' in JS
    assert 'const SALE_ASN_STAGES = [...SALE_ASN_USER_STAGES, "price_check"]' in JS
    assert "function updateSaleAsnProgress(progress)" in JS
    assert "function setSaleAsnStageState(stage, state, detail" in JS
    # Trạng thái chờ/lỗi nằm trong đúng dòng bước, không còn thẻ pending rời.
    assert "function showSaleAsnStageAction(stage" in JS
    assert "row.appendChild(action)" in JS
    assert "sale-asn-pending" not in JS


def test_sale_asn_progress_is_ignored_outside_an_active_run():
    """Progress đi bằng evaluate_js còn kết quả flow về đường khác; không có cờ
    thì một payload đến trễ sẽ xóa thẻ kết quả và kéo lùi bộ đếm."""
    assert "let saleAsnRunActive = false" in JS
    assert "if (!card || !progress || !saleAsnRunActive) return" in JS
    # Cờ phải bao đúng từng lời gọi chạy flow.
    for method in (
        "start_sale_asn_create",
        "continue_sale_asn_create",
        "skip_sale_asn_create_step",
    ):
        if method == "continue_sale_asn_create":
            assert 'const result = await call(\n      "continue_sale_asn_create"' in JS
            assert "      selectedCandidates," in JS
        else:
            guarded = (
                "    saleAsnRunActive = true;\n"
                f'    const result = await call("{method}", saleAsnReviewToken);\n'
                "    saleAsnRunActive = false;"
            )
            assert guarded in JS, method
    assert "saleAsnRunActive = false;\n    resetSaleAsnReview" in JS


def test_sale_asn_leaves_no_stale_result_card_between_runs():
    """Mở lại module sau một lượt xong không được còn thẻ kết quả cũ, vì nút
    handoff trong đó trỏ vào Invoice của lượt trước."""
    assert 'const done = $(".sale-asn-done");\n    if (done) done.hidden = true;' in JS
    assert "function resetSaleAsnProgress(" in JS


def test_sale_asn_hands_off_to_invoice_and_packing_list():
    assert '"sale-asn-handoff-documents": handoffSaleAsnDocuments' in JS
    assert 'setModuleFilterKind("sale_asn", "invoice_no")' in JS
    assert "query.value = saleAsnDoneInvoice" in JS


def test_sale_asn_order_details_only_flow_is_fully_removed():
    """Luồng 8 cột đã bỏ hẳn; không được để lại nhánh gọi backend mồ côi.

    Riêng ``scan_sale_asn_order_details`` được giữ vì nút `Xuất PO đang mở` dùng
    nó để đọc PO trên chứng từ đang mở rồi ghi ra form 22 cột.
    """

    for method in (
        "save_sale_asn_order_details_template",
        "prepare_sale_asn_order_details",
        "start_sale_asn_order_details",
        "cancel_sale_asn_order_details",
    ):
        assert method not in JS
    assert "showSaleAsnCreateMode" not in JS
    assert "saleAsnOrderReviewToken" not in JS
    assert "SALE_ASN_ORDER_DETAILS_COMPLETED" not in JS


def test_sale_asn_continue_export_writes_the_22_column_form():
    assert '"sale-asn-continue-export": exportSaleAsnContinueTemplate' in JS
    assert '"scan_sale_asn_order_details"' in JS
    assert '"save_sale_asn_continue_template"' in JS


def test_sale_asn_create_shows_one_stage_at_a_time():
    """Buyer/chọn file/Tùy chọn nâng cao phải thu về dòng ngữ cảnh sau khi
    review, nếu không các thẻ lại xếp chồng như trước."""

    assert "function setSaleAsnStageView(view)" in JS
    assert 'pane.dataset.stageView = view' in JS
    for view in ("idle", "review", "running", "done"):
        assert f'setSaleAsnStageView("{view}")' in JS
    # Mở lại module sau một lượt xong không được kẹt ở "done".
    assert 'setSaleAsnStageView(saleAsnReviewToken ? "review" : "idle")' in JS


def test_sale_asn_status_line_is_setup_only_and_never_echoes_the_footer():
    """Thanh footer đã là nơi duy nhất báo trạng thái tác vụ.

    Dòng status trong module chỉ hướng dẫn lúc chọn Buyer/file, nên nó nằm
    trong khối setup và phải im từ giai đoạn review trở đi; nếu không nó đứng
    ngay trên thẻ Tiến độ với text thừa của bước trước.
    """
    html = (Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"
            / "index.html").read_text(encoding="utf-8")
    workspace = html[
        html.index('data-module-view="sale_asn"') : html.index('data-module-view="rmpo"')
    ]
    setup = workspace[
        workspace.index('class="sale-asn-setup"') : workspace.index(
            'class="sale-asn-file-error"'
        )
    ]
    assert 'class="sale-asn-inline-status"' in setup

    # Không lặp lại đúng câu mà thẻ review/kết quả đã in.
    assert '$(".sale-asn-inline-status").textContent = result.message || "File hợp lệ."' not in JS
    assert 'textContent = result.message || "Đã điền xong Sale ASN."' not in JS
    # Thông điệp khi dừng phải còn chỗ hiển thị, cạnh nút Bắt đầu.
    assert "function setSaleAsnReviewNote(message)" in JS
    assert 'setSaleAsnReviewNote(' in JS[JS.index("function haltSaleAsnRun(result) {"):]


def test_sale_asn_handoff_button_label_never_carries_the_invoice():
    """Invoice dài từng bơm vào nhãn nút white-space:nowrap và làm tràn thẻ."""

    assert "Xuất Invoice + PKL cho" not in JS
    assert '$(".sale-asn-done-invoice").textContent = saleAsnDoneInvoice' in JS


def test_sale_asn_price_check_hides_matching_rows_behind_a_toggle():
    assert 'item.status === "ok"' in JS
    assert "sale-asn-price-chip" in JS
    assert "dòng khớp</summary>" in JS
    # Dòng không so được Qty/Price chỉ hiện thông điệp, không in "—  →  —".
    assert 'const comparable = ["ok", "mismatch"].includes(item.status)' in JS


def test_sale_asn_existing_po_flow_passes_only_selected_stages():
    assert "selectedSaleAsnStages()" in JS
    assert 'stages.includes("po")' in JS
    assert '"prepare_sale_asn_create"' in JS
    assert "selected.file_path,\n      buyer,\n      stages," in JS


def test_completed_actions_preserve_current_module():
    assert "returnToListAfterAction" not in JS
    assert "set_return_to_list_after_action" not in JS
    assert "dismissAfterSuccessfulModule" not in JS
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
    call_block = JS[JS.index("async function call("):JS.index("function openModulePage")]
    assert "const pending = bridge[method](...args);" in call_block
    assert "focus_automation_browser" in call_block
    assert call_block.index("const pending") < call_block.index("focus_automation_browser")
    assert "await api()?.focus_automation_browser?.()" not in call_block
    assert "showToast(" not in JS


def test_backend_result_sink_recovers_busy_ui_if_bridge_promise_stalls():
    sink = JS[
        JS.index("window.wfxHandleBackendResult")
        : JS.index("async function call(")
    ]
    assert "handleResult(result);" in sink
    assert "settleBusyUi();" in sink


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
    assert "!favoriteModuleIds.has(module.id)" in JS
    assert '$$(".favorites-list .module-button").filter' in JS


def test_account_view_distinguishes_connected_session_from_editing():
    assert "accountEditing" in JS
    assert "syncAccountView" in JS
    assert 'const connected = sessionActive === true' in JS
    assert '$(".account-change-button").addEventListener("click"' in JS
    assert "accountEditing = false" in JS


def test_feedback_is_validated_and_counted_before_submit():
    assert "function updateFeedbackState()" in JS
    assert "value.trim().length >= 5" in JS
    assert "feedbackSubmitting || !valid" in JS
    assert '$(".feedback-message").addEventListener("input", updateFeedbackState)' in JS
    assert "if (message.length < 5 || feedbackSubmitting) return" in JS


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


def test_bootstrap_has_single_normal_render_and_delayed_fallback():
    bootstrap = JS[JS.index("window.wfxBootstrap"):JS.index("function init()")]
    assert "bootstrapReceived = true" in bootstrap
    assert bootstrap.count("buildModules();") == 1
    assert "if (bootstrapReceived) return" in JS
    assert "}, 600);" in JS
    assert '{ once: true }' in JS


def test_short_motion_feedback_is_wired_to_views_and_busy_state():
    for hook in (
        "function replayMotion",
        'replayMotion(page, "view-enter")',
        'replayMotion(panelBody, "view-enter")',
        '"is-action-source"',
    ):
        assert hook in JS


def test_footer_stop_requests_safe_backend_cancellation():
    assert '$(".stop-action-button").addEventListener("click", stopCurrentAction)' in JS
    assert 'callQuiet("cancel_current_action")' in JS
    assert 'result.code === "ACTION_CANCELLED"' in JS
    assert 'stopButton.hidden = !value' in JS


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
        "search_rmpo",
        "search_indent",
        "search_advance_pr",
        "search_supplier_invoice",
        "search_expense_invoice",
        "cancel_supplier_invoice",
        "cancel_supplier_invoice_choice",
        "open_module_new",
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
        "rmpo-list",
        "rmpo-search",
        "indent-list",
        "indent-search",
        "advance-pr-list",
        "advance-pr-new",
        "advance-pr-search",
        "supplier-invoice-list",
        "supplier-invoice-search",
        "supplier-invoice-cancel",
        "expense-invoice-list",
        "expense-invoice-new",
        "expense-invoice-search",
        "list-new-list",
        "list-new-new",
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


def test_sample_uses_combined_filters_and_group_picker_is_renderable():
    for field in (
        "sample-no-query",
        "sample-style-query",
        "sample-created-by-query",
        "sample-buyer-query",
    ):
        assert field in JS
    assert "function sampleFilterValues()" in JS
    assert "...sampleFilterValues()" in JS
    group_start = JS.index("function renderCatalogStyleGroups()")
    group_end = JS.index("function resetCatalogStyleReview", group_start)
    assert "result.last_success" not in JS[group_start:group_end]


def test_finance_workspaces_use_combined_filters():
    for hook in (
        "advancePrFilterValues",
        "supplierInvoiceFilterValues",
        "expenseInvoiceFilterValues",
        "renderSupplierInvoiceCancelResults",
        "SUPPLIER_INVOICE_MULTIPLE_RESULTS",
        "cancel_supplier_invoice_choice",
    ):
        assert hook in JS

    for selector in (
        "advance-pr-buyer-query",
        "advance-pr-supplier-query",
        "advance-pr-invoice-query",
        "advance-pr-order-query",
    ):
        assert selector in JS


def test_catalog_actions_are_one_click_and_folder_browse_is_separate():
    assert 'runCatalogAction(catalogKind, $(".catalog-query").value)' in JS
    assert 'runCatalogAction(\n        catalogKind, $(".catalog-query").value, "costsheet"' in JS
    assert 'runCatalogAction(\n      catalogKind, $(".catalog-query").value, "bom"' in JS
    assert 'runCatalogAction(\n      catalogKind, $(".catalog-query").value, "files"' in JS
    assert '"catalog_action"' in JS
    assert '"browse_catalog"' in JS
    assert "scanCatalogFolders(false)" in JS
    assert "set_catalog_default_folder" in JS
    assert "clearCatalogResult" in JS
    assert "catalogPreparedCategory" not in JS


def test_catalog_costing_import_export_and_dry_run_are_wired():
    for method in (
        "choose_costing_export_file",
        "choose_costing_import_file",
        "export_catalog_costing",
        "prepare_catalog_costing_import",
        "apply_catalog_costing",
        "clear_catalog_costing_plan",
    ):
        assert f'"{method}"' in JS
    for hook in (
        "renderCostingPlan",
        "costingPlanToken",
        "fields_to_set",
        "COSTING_DRY_RUN_READY",
        "showCatalogSpace",
        'showCatalogSpace("costing", { focus: false })',
    ):
        assert hook in JS


def test_catalog_costing_switches_to_dedicated_workspace_after_upload():
    import_block = JS[
        JS.index("async function importCatalogCosting()")
        : JS.index("async function applyCatalogCosting()")
    ]
    result_block = JS[
        JS.index("function handleResult(result)")
        : JS.index("window.wfxHandleBackendResult")
    ]
    assert 'showCatalogSpace("costing", { focus: false })' in import_block
    assert '"COSTING_DRY_RUN_READY"' in result_block
    assert 'result.destination === "costsheet"' in result_block


def test_catalog_costing_export_can_scan_current_tab_without_query():
    export_block = JS[
        JS.index("async function exportCatalogCosting()")
        : JS.index("async function importCatalogCosting()")
    ]
    assert "costingQuery()" not in export_block
    assert "inspected.style_name" in export_block
    assert '"Current Style"' in export_block
    assert 'catalogKind,\n      "",' in export_block
    assert "catalog-costing-article-scan-input" not in export_block
    assert "suggest_articles" in JS
    assert '"article_name"' in JS
    assert '"suggest_articles",\n        $(".catalog-category")' in JS
    assert "wfxSetArticleLibraryStatus" in JS
    assert "Có thể Export/Import tab Costing hiện tại" not in JS
    import_block = JS[
        JS.index("async function importCatalogCosting()")
        : JS.index("async function applyCatalogCosting()")
    ]
    assert "costingQuery()" not in import_block
    assert 'catalogKind,\n      "",' in import_block


def test_multiple_results_are_selectable_in_panel():
    # Feature: nhiều Code hiện danh sách chọn ngay trong panel; chọn 1 Code mở
    # đúng style đó mà không phải nhìn grid trên WFX.
    assert "renderCatalogResults" in JS
    assert '"MULTIPLE_RESULTS"' in JS
    assert "openCatalogResultCode" in JS
    assert "data-result-code" in JS


def test_article_suggestion_selection_switches_to_exact_code():
    click_block = JS[
        JS.index(
            '$(".catalog-article-suggestions").addEventListener("click"'
        )
        : JS.index(
            'bindListboxKeys($(".catalog-results-list"))'
        )
    ]
    assert "row.dataset.articleCode" in click_block
    assert 'catalogKind = "code"' in click_block
    assert "syncCatalogKind()" in click_block


def test_action_buttons_show_inline_spinner():
    assert "withButtonLoading" in JS
    assert 'classList.add("is-loading", "is-action-source")' in JS
    assert 'button.setAttribute("aria-busy", "true")' in JS
    assert 'button.removeAttribute("aria-busy")' in JS


def test_all_module_workflows_keep_their_source_button_highlighted():
    assert '$$("[data-module-action]").forEach' in JS
    assert "runModuleActionFromKeyboard" in JS
    assert 'runModuleActionFromKeyboard("oc-search")' in JS
    assert 'runModuleActionFromKeyboard("rmpo-search")' in JS


def test_read_only_help_surfaces_remain_available_while_busy():
    assert (
        '".manual-button, .log-button, .module-help-button, '
        '.footer-help-button"'
    ) in JS


def test_custom_tooltips_support_pointer_keyboard_and_escape():
    for hook in (
        "function bindTooltips()",
        'document.addEventListener("pointerover"',
        'document.addEventListener("focusin"',
        'event.key === "Escape"',
        'setAttribute("aria-describedby", tooltip.id)',
        "positionTooltip(target, tooltip)",
    ):
        assert hook in JS


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


def test_autohide_can_hide_while_task_is_running():
    assert 'document.documentElement.addEventListener("pointerenter"' in JS
    assert 'document.documentElement.addEventListener("pointerleave"' in JS
    assert "set_panel_pointer_inside?.(true)" in JS
    assert "set_panel_pointer_inside?.(false)" in JS
    blur_block = JS[
        JS.index('window.addEventListener("blur"'):
        JS.index('window.addEventListener("keydown", trapOverlayFocus')
    ]
    assert "if (busy)" not in blur_block
    assert "request_panel_hide" in blur_block
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
    assert "Sửa vị trí mặc định:" in JS
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
    assert "inspect_gdn" in JS
    assert 'data-activity-view="attention"' not in JS
    assert '"attention", "jobs", "log"' not in JS


def test_running_module_has_visible_progress_and_keeps_close_controls_enabled():
    assert "BUSY_MESSAGES" in JS
    assert 'setStatus("neutral", message)' in JS
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


def test_sample_check_file_supports_multiple_choice_and_token_downloads():
    assert '"check_sample_files"' in JS
    assert '"open_sample_file_choice"' in JS
    assert '"SAMPLE_MULTIPLE_RESULTS"' in JS
    assert "data-sample-choice-id" in JS
    assert "renderSampleFileResults" in JS
    assert 'result.source === "sample"' in JS
    assert 'event.target.closest("[data-file-id]")' in JS


def test_auto_update_banner_uses_one_click_installer():
    assert "wfxSetUpdateState" in JS
    assert '".update-banner-button"' in JS
    assert "installUpdate(event.currentTarget)" in JS
    assert '"Cập nhật ngay"' in JS
    assert "commit" not in JS.lower()


def test_settings_can_check_for_updates_immediately():
    assert 'callQuiet("check_for_updates")' in JS
    assert '".check-update-button"' in JS
    assert "checkUpdateNow" in JS


def test_reference_data_uses_admin_visibility():
    assert 'const syncCard = $(".reference-sync-card")' in JS
    assert "syncCard.hidden = !adminAccess" in JS


def test_panel_auto_hides_when_focus_leaves_the_app():
    # Click ra ngoài (blur) → panel tự thu kể cả khi task vẫn đang chạy.
    assert 'window.addEventListener("blur"' in JS
    assert "request_panel_hide" in JS
    blur_block = JS[
        JS.index('window.addEventListener("blur"'):
        JS.index('window.addEventListener("keydown", trapOverlayFocus')
    ]
    assert "if (busy)" not in blur_block
    assert "if (pointerInsidePanel) {" in JS


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
    assert "requestContextMenu" in BUBBLE_JS
    assert "event.button === 2" in BUBBLE_JS
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


def test_nut_tro_giup_module_goi_manual():
    assert '".module-help-button"' in JS
    assert '"get_manual_entry_for_module"' in JS
    assert '"open_wfx_manual"' in JS


def test_the_loi_moi_duoc_link_toi_huong_dan():
    assert '".footer-help-button"' in JS
    assert "lastErrorCode" in JS


def test_cham_bao_tin_moi_tren_nut_manual():
    assert "manual-alert" in JS
    assert "manual_has_news" in JS


def test_badge_phien_ban_lay_tu_state():
    assert ".app-version" in JS
    assert "state.version" in JS


def _sale_asn_run_result_body():
    start = JS.index("function renderSaleAsnRunResult(result) {")
    return JS[start : JS.index("\n  function renderSaleAsnDone", start)]


def test_halted_sale_asn_run_gives_the_start_button_back():
    """Stop/ACTION_IN_PROGRESS/watchdog không có checkpoint để tiếp tục.

    ``startSaleAsnCreate`` đã ẩn thẻ review — nơi duy nhất chứa nút Bắt đầu —
    nên nếu các mã này rơi ra khỏi mọi nhánh thì user kẹt với thẻ tiến độ trống
    và chỉ còn cách chọn lại file.
    """
    body = _sale_asn_run_result_body()

    # Mọi nhánh nhận diện được đều phải return, phần còn lại rơi vào haltSaleAsnRun.
    assert body.rstrip().endswith("haltSaleAsnRun(result);\n  }")
    # Kết quả null (watchdog thắng race trong call()) cũng phải hồi phục UI.
    assert "if (!result) {\n      haltSaleAsnRun(null);" in body

    halt = JS[JS.index("function haltSaleAsnRun(result) {") : body and JS.index(
        "function renderSaleAsnRunResult(result) {"
    )]
    assert '$(".sale-asn-review").hidden = false;' in halt
    assert 'setSaleAsnStageView("review");' in halt
    assert 'setSaleAsnStageState(stage, "warn", "đã dừng")' in halt


def test_po_checkpoint_renders_selectable_backend_candidates():
    body = _sale_asn_run_result_body()

    assert "candidates: result.candidates," in body
    render = JS[
        JS.index("function renderSaleAsnCandidates(candidates) {") : JS.index(
            "function showSaleAsnStageAction("
        )
    ]
    # Dữ liệu từ WFX phải được escape trước khi ghép vào innerHTML.
    for field in ("po_no", "style_no", "dispatched_qty"):
        assert f"escapeHtml(cell(item?.{field})" in render
    assert "candidates.slice(0, 20)" in render
    assert 'class="sale-asn-candidate-select" type="checkbox"' in render
    assert "item?.candidate_id" in render
    assert "selectedSaleAsnCandidateIds()" in JS
    # Thẻ hành động ẩn đi thì danh sách của lượt cũ không được ở lại.
    hide = JS[
        JS.index("function hideSaleAsnStageAction() {") : JS.index(
            "function renderSaleAsnCandidates("
        )
    ]
    assert "renderSaleAsnCandidates([]);" in hide


def test_completed_sale_asn_scrolls_the_result_into_view():
    start = JS.index("function renderSaleAsnDone(result) {")
    body = JS[start : JS.index("\n  function handoffSaleAsnDocuments", start)]

    assert "done.hidden = false;" in body
    assert 'done.scrollIntoView({ behavior: "smooth", block: "nearest" });' in body
    assert body.index("done.hidden = false;") < body.index("done.scrollIntoView")
