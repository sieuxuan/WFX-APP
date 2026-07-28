"""Opt-in smoke test cho context List/Search trên phiên WFX thật.

Test chỉ dùng query giả cố định, không đọc/in dữ liệu nghiệp vụ và xóa filter
sau mỗi bước.
"""

import os

import pytest
from playwright.sync_api import sync_playwright

import login
from wfx_panel import constants, module_controllers, prefs

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


def _open(module_id: str) -> dict:
    controller = module_controllers.get(module_id)
    assert controller is not None
    return controller.open(login, lambda _line: None)


def test_search_uses_only_the_current_module_list():
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
    wrong_sample = login.search_sample_list(
        constants.MODULE_BY_ID["0004_0056_4070"]["xpath"],
        "style",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert wrong_sample["code"] == "MODULE_LIST_NOT_OPEN"
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
    wrong_sale = login.search_sale_asn_list(
        constants.MODULE_BY_ID["0004_0070_0020"]["xpath"],
        "style",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert wrong_sale["code"] == "MODULE_LIST_NOT_OPEN"
    sample_search = login.search_sample_list(
        sample["xpath"],
        "sample_no",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert sample_search["code"] == "MODULE_SEARCH_APPLIED"
    _clear_visible_filter(
        (
            "#txtSampleOrderNo",
            "#txtSampleNo",
            'input[aria-label*="Sample Order" i]',
            'input[id*="SampleOrder" i]',
        )
    )

    sale = constants.MODULE_BY_ID["0004_0070_0020"]
    assert _open("0004_0070_0020")["ok"]
    wrong_oc = login.search_oc_list(
        oc["xpath"],
        "style",
        SMOKE_QUERY,
        lambda _line: None,
    )
    assert wrong_oc["code"] == "MODULE_LIST_NOT_OPEN"
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
