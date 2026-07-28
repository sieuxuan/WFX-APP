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


def test_chrome_launch_does_not_force_a_window_size():
    assert '"--start-maximized"' not in SOURCE
    assert '"--window-size' not in SOURCE


def test_sale_asn_new_keeps_or_selects_required_values():
    assert '"Sale ASN > New"' in SOURCE
    assert '"#ddlASNType", "1", "ASN Type"' in SOURCE
    assert '"BuyerOrderDispatch"' in SOURCE
    assert 'if last_value == value:' in SOURCE
    assert 'field.select_option(value=value' in SOURCE


def test_oc_sample_and_sale_asn_search_fill_only_the_requested_filter():
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
    assert "field.type(query, delay=25)" in SOURCE
    assert 'field.press("Enter"' in SOURCE
    assert '"MODULE_SEARCH_APPLIED"' in SOURCE
    search_block = SOURCE[
        SOURCE.index("def _search_module_list"):
        SOURCE.index("def search_oc_list")
    ]
    assert "_click_module_menu_on_page" not in search_block
    assert "_show_module_floating_filter" not in search_block
    assert "_search_input_in_frame" in search_block
    assert "context_selectors" in search_block
    assert "context_aliases" in search_block
    assert '"MODULE_LIST_NOT_OPEN"' in search_block
    assert '"MODULE_SEARCH_NOT_CONFIRMED"' in search_block
    assert "def open_sample_new" in SOURCE
    assert "New Sample Order" in SOURCE


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


def test_buyer_search_resolves_first_matching_edit_link_before_click():
    assert "def find_and_open_buyer" in SOURCE
    assert "def _buyer_search_frame" in SOURCE
    assert '"partytype=2" in marker' in SOURCE
    assert '"partytype=1" in marker' in SOURCE
    buyer_start = SOURCE.index("def find_and_open_buyer")
    buyer_block = SOURCE[
        buyer_start :
        SOURCE.index("def _click_module_menu_on_page", buyer_start)
    ]
    assert "_click_module_menu_on_page" not in buyer_block
    assert "_buyer_search_frame(page, timeout_s=4)" in buyer_block
    assert '"BUYER_LIST_NOT_OPEN"' in buyer_block
    assert "a#lnkEdit" in SOURCE
    assert "target.evaluate(\"element => element.click()\")" in SOURCE
    assert '"BUYER_EDIT_OPENED"' in SOURCE
    assert '"BUYER_EDIT_NOT_CONFIRMED"' in SOURCE
