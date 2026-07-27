"""Opt-in integration test dùng `.env` và Chrome CDP thật.

Chạy thủ công:
    $env:WFX_LIVE_TEST = "1"
    python -m pytest tests/test_wfx_live.py -v

Test không in credential, Code hay giá trị business ra output.
"""

import os

import pytest
from playwright.sync_api import sync_playwright

import login
from wfx_panel import prefs

pytestmark = pytest.mark.skipif(
    os.getenv("WFX_LIVE_TEST") != "1",
    reason="Chỉ chạy khi chủ động bật WFX_LIVE_TEST=1",
)


def test_apparel_code_returns_season_and_costsheet_status():
    account = prefs.load_account()
    assert account["user_id"] and account["password"]
    session = login.run(
        account["user_id"],
        account["password"],
        login.COMPANY_ID,
        lambda _line: None,
    )
    assert session["ok"], session["code"]
    opened = login.open_module(
        "Catalog", login.CATALOG_XPATH, lambda _line: None
    )
    assert opened["ok"], opened["code"]

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(login.CDP_URL)
        page = next(
            page
            for context in browser.contexts
            for page in context.pages
            if "/wfx/default.aspx" in page.url.lower()
        )
        grid = next(
            frame
            for frame in page.frames
            if "wfxcataloglist" in frame.url.lower()
            and frame.locator(".ag-root-wrapper").count()
        )
        pair = grid.locator(".ag-root-wrapper").first.evaluate(
            """root => {
                for (const status of root.querySelectorAll(
                    '[role="gridcell"][col-id="lblInternalCostSheetStatus"]'
                )) {
                    const index = status.closest('.ag-row')
                        ?.getAttribute('row-index');
                    const value = (status.textContent || '').trim();
                    const button = root.querySelector(
                        `.ag-row[row-index="${index}"] ` +
                        '[col-id="lnkArticleCode"] input[type="button"]'
                    );
                    if (value && button?.value) {
                        return {code: button.value.trim()};
                    }
                }
                return null;
            }"""
        )
    assert pair and pair["code"]

    result = login.quick_find_catalog(
        "Apparel",
        "01",
        "code",
        pair["code"],
        account["user_id"],
        account["password"],
        login.COMPANY_ID,
        lambda _line: None,
    )
    assert result["code"] == "RESULT_OPENED"
    style = result["style_status"]
    assert style["season"]
    assert style["internal_costsheet_status"]
