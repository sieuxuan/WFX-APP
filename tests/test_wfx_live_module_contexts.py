"""Opt-in smoke test cho context List/Search trên phiên WFX thật.

Test chỉ dùng query giả cố định, không đọc/in dữ liệu nghiệp vụ và xóa filter
sau mỗi bước.
"""

import os

import pytest
from playwright.sync_api import sync_playwright

import login
from wfx_panel import constants, module_controllers, prefs
from wfx_panel.automation import directory

pytestmark = pytest.mark.skipif(
    os.getenv("WFX_LIVE_TEST") != "1",
    reason="Chỉ chạy khi chủ động bật WFX_LIVE_TEST=1",
)

SMOKE_QUERY = "__WFX_SMOKE_NO_MATCH__"


def _clear_visible_filter(selectors: tuple[str, ...]) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(login.CDP_URL)
        page = next(
            page
            for context in browser.contexts
            for page in context.pages
            if "/wfx/default.aspx" in page.url.lower()
        )
        for frame in page.frames:
            for selector in selectors:
                candidates = frame.locator(selector)
                for index in range(candidates.count()):
                    candidate = candidates.nth(index)
                    if candidate.is_visible() and candidate.is_enabled():
                        candidate.fill("")
                        candidate.dispatch_event("change")
                        return


def _clear_company_filter(expected_kind: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(login.CDP_URL)
        page = next(
            page
            for context in browser.contexts
            for page in context.pages
            if "/wfx/default.aspx" in page.url.lower()
        )
        frame = directory._company_search_frame(
            page,
            expected_kind,
            timeout_s=2,
        )
        if frame is None:
            return
        field = frame.locator("#txtCompanyName")
        if field.is_visible() and field.is_enabled():
            field.fill("")
            field.dispatch_event("change")


def _open(module_id: str) -> dict:
    controller = module_controllers.get(module_id)
    assert controller is not None
    return controller.open(login, lambda _line: None)


def test_search_auto_opens_the_required_module_list():
    account = prefs.load_account()
    assert account["user_id"] and account["password"]
    session = login.run(
        account["user_id"],
        account["password"],
        login.COMPANY_ID,
        lambda _line: None,
    )
    assert session["ok"], session["code"]

    oc = constants.MODULE_BY_ID["0004_0050_0020"]
    assert _open("0004_0050_0020")["ok"]
    sample_from_oc = login.search_sample_list(
        constants.MODULE_BY_ID["0004_0056_4070"]["xpath"],
        "style",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert sample_from_oc["code"] == "MODULE_SEARCH_APPLIED"
    _clear_visible_filter(("#txtArticle", 'input[id*="Article" i]'))
    oc_search = login.search_oc_list(
        oc["xpath"],
        "oc_no",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert oc_search["code"] == "MODULE_SEARCH_APPLIED"
    _clear_visible_filter(("#txtOCNO", 'input[name="txtOCNO"]'))

    sample = constants.MODULE_BY_ID["0004_0056_4070"]
    assert _open("0004_0056_4070")["ok"]
    sale_from_sample = login.search_sale_asn_list(
        constants.MODULE_BY_ID["0004_0070_0020"]["xpath"],
        "buyer_order_ref",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert sale_from_sample["code"] == "MODULE_SEARCH_APPLIED"
    _clear_visible_filter(
        ('input[aria-label*="Buyer Order Ref/Oc Num" i]',)
    )
    sample_search = login.search_sample_list(
        sample["xpath"],
        "sample_no",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert sample_search["code"] == "MODULE_SEARCH_APPLIED"
    created_by_search = login.search_sample_list(
        sample["xpath"],
        "created_by",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert created_by_search["code"] == "MODULE_SEARCH_APPLIED"
    created_by_files = login.find_sample_file_results(
        sample["xpath"],
        "created_by",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert created_by_files["code"] == "NO_RESULTS"

    sale = constants.MODULE_BY_ID["0004_0070_0020"]
    assert _open("0004_0070_0020")["ok"]
    oc_from_sale = login.search_oc_list(
        oc["xpath"],
        "style",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert oc_from_sale["code"] == "MODULE_SEARCH_APPLIED"
    _clear_visible_filter(("#txtArticle", 'input[name="txtArticle"]'))
    sale_search = login.search_sale_asn_list(
        sale["xpath"],
        "invoice_no",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert sale_search["code"] == "MODULE_SEARCH_APPLIED"
    _clear_visible_filter(
        (
            "#txtInvoiceNo",
            'input[aria-label*="Invoice" i]',
            'input[id*="Invoice" i]',
        )
    )


def test_buyer_and_supplier_keep_their_own_company_frame():
    account = prefs.load_account()
    session = login.run(
        account["user_id"],
        account["password"],
        login.COMPANY_ID,
        lambda _line: None,
    )
    assert session["ok"], session["code"]

    supplier = constants.MODULE_BY_ID["0005_0010_1290"]
    opened_supplier = login.open_supplier_category(
        supplier["xpath"],
        "Apparel",
        constants.CATEGORIES["Apparel"],
        lambda _line: None,
    )
    assert opened_supplier["ok"], opened_supplier["code"]
    supplier_result = login.find_supplier_in_category(
        supplier["xpath"],
        "Apparel",
        constants.CATEGORIES["Apparel"],
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert supplier_result["code"] == "SUPPLIER_NOT_FOUND"
    _clear_company_filter("supplier")

    buyer = constants.MODULE_BY_ID["0004_0010_1720"]
    opened_buyer = login.open_module(
        buyer["name"],
        buyer["xpath"],
        lambda _line: None,
    )
    assert opened_buyer["ok"], opened_buyer["code"]
    buyer_result = login.find_and_open_buyer(
        buyer["xpath"],
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert buyer_result["code"] == "BUYER_NOT_FOUND"
    _clear_company_filter("buyer")


def test_supplier_search_visits_every_category():
    account = prefs.load_account()
    session = login.run(
        account["user_id"],
        account["password"],
        login.COMPANY_ID,
        lambda _line: None,
    )
    assert session["ok"], session["code"]

    supplier = constants.MODULE_BY_ID["0005_0010_1290"]
    result = login.find_supplier_across_categories(
        supplier["xpath"],
        constants.CATEGORIES,
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert result["code"] == "SUPPLIER_NOT_FOUND", result
    assert result["checked_categories"] == list(constants.CATEGORIES)
    _clear_company_filter("supplier")
