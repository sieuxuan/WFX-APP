import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from wfx_panel.automation import modules, search_specs

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


class _ContextRoot:
    def __init__(self, visible=True):
        self.visible = visible

    def count(self):
        return 1

    def nth(self, _index):
        return self

    def is_visible(self):
        return self.visible


class _ContextFrame:
    def __init__(self, url, *, has_grid=True):
        self.url = url
        self.has_grid = has_grid

    def locator(self, selector):
        assert selector == ".ag-root-wrapper"
        root = _ContextRoot()
        if self.has_grid:
            return root
        root.count = lambda: 0
        return root


def test_sale_asn_search_context_rejects_other_modules_and_new_form():
    assert not modules._frame_matches_module_context(
        _ContextFrame("https://wfx.example/WFXSampleList.aspx"),
        "Sale ASN",
    )
    assert not modules._frame_matches_module_context(
        _ContextFrame("https://wfx.example/WFXSalesASN.aspx", has_grid=False),
        "Sale ASN",
    )
    assert modules._frame_matches_module_context(
        _ContextFrame("https://wfx.example/WFXSalesASNList.aspx"),
        "Sale ASN",
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
    assert '"--renderer-process-limit=3"' in SOURCE
    assert '"--process-per-site"' in SOURCE
    assert '"--disable-background-networking"' in SOURCE
    assert '"--disable-extensions"' in SOURCE


def test_sale_asn_new_keeps_or_selects_required_values():
    assert '"Sale ASN > New"' in SOURCE
    assert '"#ddlASNType", "1", "ASN Type"' in SOURCE
    assert '"BuyerOrderDispatch"' in SOURCE
    assert 'if last_value == value:' in SOURCE
    assert 'field.select_option(value=value' in SOURCE


def test_sale_asn_documents_export_both_reports_and_merge_workbook():
    assert "def prepare_sale_asn_documents" in SOURCE
    assert 'PACKING_LIST_SELECTOR = "#lnkANFPackingList"' in SOURCE
    assert 'BUYER_INVOICE_SELECTOR = "#lnkBuyerInvoice"' in SOURCE
    assert "EXCELOPENXML" in SOURCE
    assert "merge_sale_asn_reports" in SOURCE
    assert '"SALE_ASN_SELECTION_REQUIRED"' in SOURCE


def test_sale_asn_search_finds_virtualized_filter_across_horizontal_grid():
    assert "def _search_input_across_horizontal_grid(" in SOURCE
    assert "def _horizontal_grid_positions(" in SOURCE
    assert "def _clear_list_search_fields(" in SOURCE
    assert "scan_horizontal: bool = False" in SOURCE
    assert "clear_visible()" in SOURCE
    assert "scan_horizontal=search_spec.requires_floating_filter" in SOURCE
    assert "scan_horizontal=True" in SOURCE


def test_catalog_search_sweeps_user_reordered_floating_filters():
    assert "def _resolve_catalog_filter(" in SOURCE
    assert "_CATALOG_FILTER_INPUT_SELECTORS" in SOURCE
    assert "Không tìm thấy Floating Filter" in SOURCE


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
    assert "def find_sample_file_results_with_filters" in SOURCE
    assert "def search_sample_list_with_filters" in SOURCE
    assert '"buyer": SearchFieldSpec' in SOURCE
    assert "def open_sample_file_result" in SOURCE
    assert '"SAMPLE_MULTIPLE_RESULTS"' in SOURCE
    assert '"SAMPLE_STYLE_OPENED"' in SOURCE
    assert "_SAMPLE_RESULT_ROWS_JS" in SOURCE
    assert "element.querySelector?.(" in SOURCE
    assert "input[value], button, a, [title], [aria-label]" in SOURCE
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


def test_rmpo_results_use_exact_business_columns_and_revise_selector():
    for selector in (
        "colStatus",
        "colSupplier",
        "colOrderNo",
        "colLastCreated",
        "colQty",
        "colOCNo",
        "colRecv",
        '//*[@id="titlebarRMPO"]/tbody/tr/td[2]/span/div[9]',
    ):
        assert selector in SOURCE
    assert "timeout_s=180" in SOURCE
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
    assert '"#gridRMPO_tblGridContent", "#gridRMPO"' in SOURCE
    assert 'frame.locator("body")' in SOURCE
    assert ".blockUI" in SOURCE
    assert "colSupplierName" in SOURCE
    assert "ready = not loading" in SOURCE


def test_grn_receipt_workflows_use_exact_wfx_controls_and_safe_checkpoint():
    for selector in (
        '//*[@id="0005_0105_1200_0010"]/a',
        '//*[@id="0050_0020_0380"]/a',
        "#CellIDSupplier",
        "#sectionSupplierASNShipmentDetail",
        "#sectionRMPOList",
        "#sectionOrderShipment",
        "#titlebarGRNPending",
    ):
        assert selector in SOURCE
    assert '"ASN from Supplier - Against ASN"' in SOURCE
    assert '"ASN from Supplier - Against PO"' in SOURCE
    assert 'if mode == "foreign":\n        _select_imported(frame, log)' in SOURCE
    assert '"GRN_SOURCING_ASN_READY"' in SOURCE
    assert "def continue_grn_receipt" in SOURCE
    assert '"GRN_SITE_SELECTION_REQUIRED"' in SOURCE
    assert '"GRN_NEW_READY"' in SOURCE


def test_grn_search_unchecks_date_and_opens_first_result_number():
    for selector in (
        '//*[@id="0050_0020_0010"]/a',
        "#row_txtDocNum",
        "#row_txtOrderNum",
        "#row_txtFromGRNDate",
        "#chk_6",
        "#ctrlRpt",
        "a[onclick*='PrintGRN(']",
    ):
        assert selector in SOURCE
    assert "if (element.checked) element.click()" in SOURCE
    assert "_set_grn_search_filter(frame, filter_kind, query, enabled=True)" in SOURCE
    assert "_click_grn_search(frame)" in SOURCE
    assert "_wait_grn_result_opened" in SOURCE
    assert "def search_grn_receipt" in SOURCE


def test_supplier_and_expense_invoice_support_combined_filters_and_safe_cancel():
    for selector in (
        "#gridAPInvoiceList_tblGridHeader_trSearch_td_ColSupplier",
        "#gridAPInvoiceList_tblGridHeader_trSearch_td_ColInvoiceNo",
        "#gridAPInvoiceList_tblGridHeader_trSearch_td_ColPONo",
        "#gridAPInvoiceList_tblGridHeader_trSearch_td_ColCreatedBy",
        "#gridAPInvoiceList_tblGridHeader_trSearch_td_ColStatus",
        "#ddlInvoiceType",
    ):
        assert selector in SOURCE
    assert "def prepare_supplier_invoice_cancel" in SOURCE
    assert "def cancel_supplier_invoice_choice" in SOURCE
    assert '//*[@id="titlebarAPInvoiceList"]/tbody/tr/td[2]/span/div[2]' in SOURCE
    assert '//*[@id="titlebarAPInvoiceList"]/tbody/tr/td[2]/span/div[4]' in SOURCE
    assert '"SUPPLIER_INVOICE_MULTIPLE_RESULTS"' in SOURCE


def test_advance_pr_supports_combined_filters_from_real_grid_fields():
    for selector in (
        "#txtSearchBuyer",
        "#txtSearchSupplier",
        "#txtSearchInvoiceNo",
        "#txtSearchOrderNo",
        "#gridAdvancePaymentRequestList_tblGridHeader",
    ):
        assert selector in SOURCE
    assert "def search_advance_pr_list" in SOURCE


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
    assert '("#ddlRequestType", "RMPO", "Against RMPO")' in new_block
    assert '("#ddlInvoiceType", "GeneralExpense", "General Expense")' in new_block
    assert "_ensure_select_value" in new_block
    assert "_click_module_menu_on_page" in new_block
    assert '"MODULE_LIST_NOT_OPEN"' not in new_block
    assert "_document_changed" in new_block
    assert '"MODULE_NEW_READY"' in new_block
    # Frame đổi document chưa phải bằng chứng: menu WFX cũng tự reload.
    assert "_menu_target_markers(page, selector)" in new_block
    assert "_wait_module_new_page(" in new_block
    assert "MODULE_NEW_CONFIRM_SECONDS" in new_block
    assert "elif markers and opened_page is None:" in new_block


def test_generic_module_open_requires_real_navigation_confirmation():
    open_block = SOURCE[
        SOURCE.index("def open_module("):
        SOURCE.index("def _active_wfx_page")
    ]
    assert "_open_module_menu(page, module_name, xpath, log)" in open_block
    assert '"MODULE_OPEN_NOT_CONFIRMED"' in open_block

    # Mọi lối vào List/New dùng chung một hàm mở menu, nên xác nhận navigation,
    # fallback href và route cache không còn là đặc quyền của nút List.
    menu_block = SOURCE[
        SOURCE.index("def _open_module_menu("):
        SOURCE.index("def _click_module_menu_on_page(")
    ]
    assert "_mark_page_documents" in menu_block
    assert "_wait_for_module_navigation" in menu_block
    assert "_open_menu_href_in_target_frame" in menu_block
    assert "timeout_s=5" in menu_block
    assert "_MENU_ROUTE_CACHE[xpath]" in menu_block
    # Menu bắt theo @title/@href có thể khớp nhiều node; strict locator sẽ ném
    # lỗi thay vì mở được màn hình.
    assert 'page.locator(f"xpath={xpath}").first' in menu_block
    assert (
        "_open_module_menu(page, module_name, xpath, log).confirmed"
        in SOURCE
    )


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


_AP_INVOICE_SHARED_IDS = (
    "titlebarAPInvoiceList",
    "gridAPInvoiceList_tblGridHeader",
    "gridAPInvoiceList_tblGridHeader_trSearch_td_ColSupplier",
    "txtSupplier",
    "gridAPInvoiceList_tblGridHeader_trSearch_td_ColInvoiceNo",
    "txtInvoiceNo",
)
_SUPPLIER_INVOICE_IDS = _AP_INVOICE_SHARED_IDS + (
    "gridAPInvoiceList_tblGridHeader_trSearch_td_ColPONo",
    "txtPONo",
    "gridAPInvoiceList_tblGridHeader_trSearch_td_ColASNGRNNo",
    "txtASNGRNNo",
)
_EXPENSE_INVOICE_IDS = _AP_INVOICE_SHARED_IDS + (
    "gridAPInvoiceList_tblGridHeader_trSearch_td_ColCreatedBy",
    "txtCreatedBy",
    "gridAPInvoiceList_tblGridHeader_trSearch_td_ColStatus",
    "txtStatus",
)


class _APInvoiceFrame:
    """Frame giả của WFX: hai màn AP Invoice chỉ khác nhau ở cột filter."""

    def __init__(self, element_ids, marker):
        self.element_ids = frozenset(element_ids)
        self.marker = marker
        self.url = "https://wfx.example/WFXAPInvoiceList.aspx"

    def _token_matches(self, token):
        wanted = re.findall(r"#([A-Za-z0-9_-]+)", token)
        return bool(wanted) and all(name in self.element_ids for name in wanted)

    def locator(self, selector):
        present = any(
            self._token_matches(token) for token in selector.split(",")
        )
        return SimpleNamespace(
            count=lambda: 1 if present else 0,
            first=SimpleNamespace(
                is_visible=lambda: present,
                is_enabled=lambda: present,
            ),
        )

    def evaluate(self, _script):
        return self.marker


def _supplier_invoice_frame(marker="wfxapinvoicelist.aspx supplier invoice list"):
    return _APInvoiceFrame(_SUPPLIER_INVOICE_IDS, marker)


def _expense_invoice_frame(marker="wfxapinvoicelist.aspx expense invoice list"):
    return _APInvoiceFrame(_EXPENSE_INVOICE_IDS, marker)


def test_ap_invoice_lists_are_told_apart_by_their_own_filter_columns():
    supplier = _supplier_invoice_frame()
    expense = _expense_invoice_frame()

    assert modules._frame_serves_search_spec(
        supplier, search_specs.SUPPLIER_INVOICE_SEARCH_SPEC
    )
    assert modules._frame_serves_search_spec(
        expense, search_specs.EXPENSE_INVOICE_SEARCH_SPEC
    )
    # Expense Inv List không có PO No./ASN-GRN No. nên không được nhận làm
    # context của Supplier Inv List, kể cả khi marker không chứa "expense".
    assert not modules._frame_serves_search_spec(
        _expense_invoice_frame("wfxapinvoicelist.aspx ap invoice list"),
        search_specs.SUPPLIER_INVOICE_SEARCH_SPEC,
    )
    # Supplier Inv List không có Created By/Status.
    assert not modules._frame_serves_search_spec(
        supplier, search_specs.EXPENSE_INVOICE_SEARCH_SPEC
    )


def test_supplier_invoice_context_rejects_a_frame_marked_as_expense():
    assert search_specs.SUPPLIER_INVOICE_SEARCH_SPEC.foreign_markers == (
        "expense",
    )
    # Ngay cả khi WFX render đủ cột, marker Expense vẫn phải loại frame đó ra
    # vì Cancel Supplier Invoice là thao tác phá hủy.
    assert not modules._frame_serves_search_spec(
        _APInvoiceFrame(
            _SUPPLIER_INVOICE_IDS,
            "wfxapinvoicelist.aspx expense invoice list",
        ),
        search_specs.SUPPLIER_INVOICE_SEARCH_SPEC,
    )


def _ap_invoice_search_page(monkeypatch, frames):
    page = SimpleNamespace(frames=list(frames))
    monkeypatch.setattr(modules, "MODULE_CONTEXT_PROBE_SECONDS", 0.05)
    monkeypatch.setattr(modules, "_wait", lambda *_args, **_kwargs: None)
    return page


def test_supplier_inv_search_opens_its_own_list_instead_of_the_expense_list(
    monkeypatch,
):
    page = _ap_invoice_search_page(monkeypatch, [_expense_invoice_frame()])
    supplier = _supplier_invoice_frame()
    clicks = []

    def click_menu(_page, module_name, xpath, _log):
        clicks.append((module_name, xpath))
        page.frames = [_expense_invoice_frame(), supplier]

    monkeypatch.setattr(modules, "_click_module_menu_on_page", click_menu)

    frame = modules._open_multi_field_search_context(
        page,
        search_specs.SUPPLIER_INVOICE_SEARCH_SPEC,
        '//*[@id="0065_0880_0020_0020"]/a',
        lambda _line: None,
    )

    assert frame is supplier
    assert clicks == [
        ("Supplier Inv List", '//*[@id="0065_0880_0020_0020"]/a')
    ]


def test_expense_inv_search_opens_its_own_list_instead_of_the_supplier_list(
    monkeypatch,
):
    page = _ap_invoice_search_page(monkeypatch, [_supplier_invoice_frame()])
    expense = _expense_invoice_frame()
    clicks = []

    def click_menu(_page, module_name, xpath, _log):
        clicks.append((module_name, xpath))
        page.frames = [_supplier_invoice_frame(), expense]

    monkeypatch.setattr(modules, "_click_module_menu_on_page", click_menu)

    frame = modules._open_multi_field_search_context(
        page,
        search_specs.EXPENSE_INVOICE_SEARCH_SPEC,
        '//*[@id="0065_0880_0030_0020"]/a',
        lambda _line: None,
    )

    assert frame is expense
    assert clicks == [
        ("Expense Inv List", '//*[@id="0065_0880_0030_0020"]/a')
    ]


def test_search_reuses_the_matching_list_without_clicking_the_menu_again(
    monkeypatch,
):
    supplier = _supplier_invoice_frame()
    page = _ap_invoice_search_page(monkeypatch, [supplier])
    monkeypatch.setattr(
        modules,
        "_click_module_menu_on_page",
        lambda *_args: pytest.fail("Đã mở đúng List thì không được click lại"),
    )

    frame = modules._open_multi_field_search_context(
        page,
        search_specs.SUPPLIER_INVOICE_SEARCH_SPEC,
        '//*[@id="0065_0880_0020_0020"]/a',
        lambda _line: None,
    )

    assert frame is supplier


def test_cancel_supplier_invoice_resolves_the_frame_with_its_own_spec(
    monkeypatch,
):
    seen = {}

    def fake_context(page, selector, **kwargs):
        seen.update(kwargs)
        seen["selector"] = selector
        return "frame"

    monkeypatch.setattr(modules, "_frame_with_visible_context", fake_context)

    assert modules._find_supplier_invoice_frame(object()) == "frame"
    assert seen["search_spec"] is search_specs.SUPPLIER_INVOICE_SEARCH_SPEC
    assert seen["module_name"] == "Supplier Inv List"


class _MenuLinkLocator:
    def __init__(self, href, on_click=None):
        self.href = href
        self.on_click = on_click

    @property
    def first(self):
        return self

    def wait_for(self, **_options):
        return None

    def evaluate(self, _script):
        return self.href

    def get_attribute(self, name):
        return "body" if name == "target" else None

    def click(self, **_options):
        if self.on_click is not None:
            self.on_click()


_QA_NEW_HREF = (
    "https://wfx.example/wfx_BaseSetting.aspx?"
    "RedirURL=WFXQAInspectionRequest.aspx%3FQARequestType=QualityInspection"
    "&MenuName=mnuQAInspectionRequestNew"
)


def test_menu_target_markers_read_the_real_destination_from_the_link():
    page = SimpleNamespace(locator=lambda _s: _MenuLinkLocator(_QA_NEW_HREF))

    assert modules._menu_target_markers(page, "//a") == (
        "wfxqainspectionrequest.aspx",
        "menuname=mnuqainspectionrequestnew",
    )


class _FakeFrame:
    """Frame giả giữ được document marker như Playwright."""

    def __init__(self, url="", name=""):
        self.url = url
        self.name = name
        self.marker = ""
        self.navigations = []

    def evaluate(self, _script, marker=None):
        if marker is None:
            return self.marker
        self.marker = marker
        return None

    def goto(self, target, **_options):
        self.navigations.append(target)


def _fake_new_page(frame_urls):
    return SimpleNamespace(
        frames=[_FakeFrame(url) for url in frame_urls],
        wait_for_timeout=lambda _ms: None,
    )


def test_new_screen_is_confirmed_by_the_destination_page_not_any_frame():
    markers = ("wfxqainspectionrequest.aspx", "menuname=mnuqainspectionrequestnew")
    opened = _fake_new_page(
        ["https://wfx.example/WFXQAInspectionRequest.aspx?Action=New"]
    )
    browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[opened])])
    assert modules._wait_module_new_page(browser, opened, markers, 1) is opened

    # Menu tự reload không được tính là đã mở màn New.
    stale = _fake_new_page(["https://wfx.example/wfx_Home.aspx"])
    browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[stale])])
    assert modules._wait_module_new_page(browser, stale, markers, 0.3) is None


def _run_qa_new(monkeypatch, frame_urls):
    page = _fake_new_page(frame_urls)
    page.locator = lambda _selector: _MenuLinkLocator(_QA_NEW_HREF)
    browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[page])])

    monkeypatch.setattr(modules, "MODULE_NEW_CONFIRM_SECONDS", 0.3)
    monkeypatch.setattr(
        modules,
        "sync_playwright",
        lambda: SimpleNamespace(start=lambda: SimpleNamespace(stop=lambda: None)),
    )
    monkeypatch.setattr(
        modules, "_active_wfx_page", lambda *_args: (browser, page)
    )
    monkeypatch.setattr(
        modules, "_click_module_menu_on_page", lambda *_args: True
    )
    monkeypatch.setattr(modules, "_document_changed", lambda *_args: True)
    monkeypatch.setattr(modules, "_wait", lambda *_args, **_kwargs: None)
    return modules.open_module_new("0063_0030_0020", lambda _line: None)


def test_qa_new_only_succeeds_when_its_own_screen_is_open(monkeypatch):
    opened = _run_qa_new(
        monkeypatch,
        ["https://wfx.example/WFXQAInspectionRequest.aspx?Action=New"],
    )
    assert opened["code"] == "MODULE_NEW_READY", opened


def test_qa_new_reports_failure_when_only_the_menu_frame_reloaded(monkeypatch):
    failed = _run_qa_new(monkeypatch, ["https://wfx.example/wfx_Home.aspx"])

    assert failed["ok"] is False
    assert failed["code"] == "MODULE_FAILED"
    assert "wfxqainspectionrequest.aspx" in failed["message"]


def test_every_menu_entry_point_gets_the_direct_route_fallback():
    clicks = []
    href = "https://wfx.example/wfx_BaseSetting.aspx?RedirURL=WFXList.aspx"
    body = _FakeFrame(name="body")
    page = SimpleNamespace(
        url="https://wfx.example/wfx/default.aspx",
        wait_for_timeout=lambda _ms: None,
    )
    page.frames = [body]
    page.locator = lambda _selector: _MenuLinkLocator(
        href, on_click=lambda: clicks.append(True)
    )

    modules.reset_menu_route_cache()
    try:
        # Search tự mở List đi qua đúng hàm này, nên click im lặng cũng được
        # cứu bằng href thay vì chờ hết timeout của riêng flow.
        confirmed = modules._click_module_menu_on_page(
            page,
            "Supplier Inv List",
            '//*[@id="0065_0880_0020_0020"]/a',
            lambda _line: None,
        )
        assert confirmed is True
        assert clicks == [True]
        assert body.navigations == [href]
        assert '//*[@id="0065_0880_0020_0020"]/a' in modules._MENU_ROUTE_CACHE
    finally:
        modules.reset_menu_route_cache()
