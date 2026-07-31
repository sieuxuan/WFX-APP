from pathlib import Path

# login.py giờ là shim; code automation nằm ở package wfx_panel/automation/.
# Gộp source mọi module (thứ tự sorted: __init__, _common, browser, catalog,
# directory, modules, session) để các assert theo mẫu chuỗi vẫn đúng — và
# _actionable_master/_company_search_frame vẫn nằm cùng directory.py theo thứ tự.
_AUTOMATION_DIR = (
    Path(__file__).resolve().parent.parent / "wfx_panel" / "automation"
)
SOURCE = "\n".join(
    path.read_text(encoding="utf-8") for path in sorted(_AUTOMATION_DIR.glob("*.py"))
)


def test_list_floating_filter_excludes_old_grid_and_confirms_visible_input():
    assert "MODULE_GRID_POLL_MS = 150" in SOURCE
    assert "MODULE_FILTER_VISIBLE_STABLE_SECONDS = 0.5" in SOURCE
    assert "previous_grids = _mark_grid_roots(page)" in SOURCE
    assert "_grid_root_is_new" in SOURCE
    assert "_MODULE_GRID_STATE_JS" in SOURCE
    assert 'last_state["renderedRows"] > 0' in SOURCE
    assert 'or last_state["noRows"]' in SOURCE
    assert 'last_state["filterVisible"]' in SOURCE
    assert 'frame.locator("#showfloatingfilter")' in SOURCE
    assert "visible_input.is_enabled()" in SOURCE
    assert "rowRect.height < 16" in SOURCE
    assert "headerRect.height < 50" in SOURCE
    assert "filter_stable_since" in SOURCE
    assert 'button.evaluate("element => element.click()")' in SOURCE


def test_long_automation_waits_use_cancellable_short_slices():
    assert "def _wait(target: Any, milliseconds: int)" in SOURCE
    assert "step = min(100, remaining)" in SOURCE
    assert "target.wait_for_timeout(step)" in SOURCE
    assert "page.wait_for_timeout(" not in SOURCE
    assert "grid.wait_for_timeout(" not in SOURCE
    assert "with cancellation_deferred():" in SOURCE


def test_chrome_launch_does_not_force_a_window_size():
    assert '"--start-maximized"' not in SOURCE
    assert '"--window-size' not in SOURCE


def test_chrome_launch_caps_renderer_count_for_8gb_machines():
    assert '"--renderer-process-limit=4"' in SOURCE
    assert '"--process-per-site"' in SOURCE
    assert '"--disable-background-networking"' in SOURCE


def test_sale_asn_new_keeps_or_selects_required_values():
    assert '"Sale ASN > New"' in SOURCE
    assert '"#ddlASNType", "1", "ASN Type"' in SOURCE
    assert '"BuyerOrderDispatch"' in SOURCE
    assert 'if last_value == value:' in SOURCE
    assert 'field.select_option(value=value' in SOURCE


def test_oc_sample_and_sale_asn_search_auto_open_their_list():
    for function_name in (
        "search_oc_list",
        "search_sample_list",
        "search_sale_asn_list",
    ):
        assert f"def {function_name}" in SOURCE
    for selector in ("#txtOCNO", "#txtArticle"):
        assert selector in SOURCE
    for label in (
        "Sample Order No.",
        "Created By",
        "Invoice No.",
    ):
        assert label in SOURCE
    assert "field.fill(query)" in SOURCE
    assert "ModuleSearchSpec" in SOURCE
    assert "search_spec.field_selectors" in SOURCE
    assert 'field.press("Enter"' in SOURCE
    assert '"MODULE_SEARCH_APPLIED"' in SOURCE
    search_block = SOURCE[
        SOURCE.index("def _open_list_search_context"):
        SOURCE.index("def search_oc_list")
    ]
    assert "_click_module_menu_on_page" in search_block
    assert "_show_module_floating_filter" in search_block
    assert "_search_input_in_frame" in search_block
    assert "search_spec.context_field.selectors" in search_block
    assert "search_spec.context_field.aliases" in search_block
    assert "đang tự mở List" in search_block
    assert '"MODULE_LIST_NOT_OPEN"' not in search_block
    assert '"MODULE_SEARCH_NOT_CONFIRMED"' in search_block
    assert "def open_sample_new" in SOURCE
    assert "New Sample Order" in SOURCE


def test_sample_check_file_reads_rows_and_opens_only_a_unique_style():
    assert "def find_sample_file_results" in SOURCE
    assert "def open_sample_file_result" in SOURCE
    assert '"SAMPLE_MULTIPLE_RESULTS"' in SOURCE
    assert '"SAMPLE_STYLE_OPENED"' in SOURCE
    assert "_SAMPLE_RESULT_ROWS_JS" in SOURCE
    assert "_CLICK_SAMPLE_STYLE_JS" in SOURCE
    assert "total_rows > 1 or len(rows) > 1" in SOURCE
    assert "_click_sample_style_result" in SOURCE


def test_rmpo_and_indent_support_context_bound_combined_filters():
    assert "def search_rmpo_list" in SOURCE
    assert "def search_indent_list" in SOURCE
    assert "def _search_module_fields" in SOURCE
    for selector in (
        "#gridRMPO_tblGridHeader_trSearch_td_colSupplier",
        "#gridRMPO_tblGridHeader_trSearch_td_colOrderNo",
        "#gridMOLList_tblGridHeader_trSearch_td_ColSupplier",
        "#gridMOLList_tblGridHeader_trSearch_td_ColArticle",
        "#gridMOLList_tblGridHeader_trSearch_td_ColIndentNo",
        "#gridMOLList_tblGridHeader_trSearch_td_ColStyle",
    ):
        assert selector in SOURCE
    combined_block = SOURCE[
        SOURCE.index("def _open_multi_field_search_context"):
        SOURCE.index("def _open_list_search_context")
    ]
    assert "for search_field in fields.values()" in combined_block
    assert 'search_field.fill("")' in combined_block
    assert "for field_name in active_fields:" in combined_block
    assert "_click_module_menu_on_page" in combined_block
    assert "đang tự mở List" in combined_block
    assert '"MODULE_LIST_NOT_OPEN"' not in combined_block


def test_qa_advance_pr_and_expense_new_use_direct_menu_links():
    assert "def open_module_new" in SOURCE
    new_block = SOURCE[
        SOURCE.index("def open_module_new"):
        SOURCE.index("def open_sample_new")
    ]
    assert "mnuQAInspectionRequestNew" in new_block
    assert "QARequestType=QualityInspection" in new_block
    assert "mnuAdvancePaymentRequestNew" in new_block
    assert "ARAPType=APR" in new_block
    assert '//*[@id="0065_0880_0030_0010"]/a' in new_block
    assert "_click_module_menu_on_page" in new_block
    assert '"MODULE_LIST_NOT_OPEN"' not in new_block
    assert "_document_changed" in new_block
    assert '"MODULE_NEW_READY"' in new_block


def test_generic_module_open_requires_real_navigation_confirmation():
    open_block = SOURCE[
        SOURCE.index("def open_module("):
        SOURCE.index("def _active_wfx_page")
    ]
    assert "_mark_page_documents" in open_block
    assert "_wait_for_module_navigation" in open_block
    assert '"MODULE_OPEN_NOT_CONFIRMED"' in open_block


def test_company_foc_auto_opens_company_setup_when_context_is_stale():
    block = SOURCE[
        SOURCE.index("def toggle_company_foc"):
    ]
    assert 'timeout_s=1' in block
    assert '_click_module_menu_on_page(page, "Company Setup", _xpath, log)' in block
    assert '"COMPANY_LIST_OPEN_FAILED"' in block
    assert '"COMPANY_LIST_NOT_OPEN"' not in block


def test_supplier_uses_exact_actionable_master_and_company_search():
    assert "def _actionable_master" in SOURCE
    assert "span[onclick], a, button, [role=\"button\"]" in SOURCE
    actionable_block = SOURCE[
        SOURCE.index("def _actionable_master"):
        SOURCE.index("def _company_search_frame")
    ]
    assert "img" not in actionable_block.casefold()
    assert 'frame.locator("#txtCompanyName")' in SOURCE
    assert "def _supplier_category_frame" in SOURCE
    assert '"wfxpartygroup" in url and "partytype=2" in url' in SOURCE
    assert 'field.dispatch_event("mousedown")' in SOURCE
    assert "Supplier List đã mở; chuyển Category trực tiếp" in SOURCE
    assert 'page.frame(name="left")' not in SOURCE[
        SOURCE.index("def _supplier_category_frame"):
        SOURCE.index("def find_and_open_buyer")
    ]
    assert "for category_name, category_value in categories.items()" in SOURCE
    assert "def find_supplier_in_category" in SOURCE
    assert '"SUPPLIER_FOUND"' in SOURCE
    assert '"SUPPLIER_NOT_FOUND"' in SOURCE


def test_buyer_search_auto_opens_list_and_resolves_first_edit_link():
    assert "def find_and_open_buyer" in SOURCE
    assert "def _buyer_search_frame" in SOURCE
    assert '"partytype=2" in marker' in SOURCE
    assert '"partytype=1" in marker' in SOURCE
    buyer_start = SOURCE.index("def find_and_open_buyer")
    buyer_block = SOURCE[
        buyer_start :
        SOURCE.index("def _click_module_menu_on_page", buyer_start)
    ]
    assert "_click_module_menu_on_page" in buyer_block
    assert "MODULE_CONTEXT_PROBE_SECONDS = 0.75" in SOURCE
    assert "timeout_s=MODULE_CONTEXT_PROBE_SECONDS" in buyer_block
    assert "đang tự mở List" in buyer_block
    assert '"BUYER_LIST_NOT_OPEN"' not in buyer_block
    assert "a#lnkEdit" in SOURCE
    assert "target.evaluate(\"element => element.click()\")" in SOURCE
    assert '"BUYER_EDIT_OPENED"' in SOURCE
    assert '"BUYER_EDIT_NOT_CONFIRMED"' in SOURCE
