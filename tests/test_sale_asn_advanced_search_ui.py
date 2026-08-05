from pathlib import Path

from playwright.sync_api import sync_playwright

UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"


def _sale_asn_workspace() -> str:
    html = (UI / "index.html").read_text(encoding="utf-8")
    start = html.index('data-module-view="sale_asn"')
    end = html.index('data-module-view="rmpo"')
    return html[start:end]


def test_sale_asn_advanced_exposes_all_three_po_search_fields():
    workspace = _sale_asn_workspace()
    advanced = workspace[workspace.index('class="sale-asn-advanced"') :]

    for field in ("po", "style", "destination"):
        assert f'data-sale-asn-po-search-field="{field}"' in advanced
    assert advanced.count("data-sale-asn-po-search-field=") == 3


def test_sale_asn_create_keeps_file_action_compact_without_column_label():
    workspace = _sale_asn_workspace()

    assert "Chọn file &amp; kiểm tra" in workspace
    assert "File 22 cột" not in workspace
    assert "File 21 cột" not in workspace


def test_sale_asn_advanced_groups_render_as_distinct_cards():
    css = (UI / "style.css").read_text(encoding="utf-8")
    markup = f"""
      <style>{css}</style>
      <details class="sale-asn-advanced" open>
        <summary><span>Tùy chọn nâng cao</span></summary>
        <div class="sale-asn-advanced-body">
          <div class="sale-asn-advanced-group">
            <strong>Tiêu chí tìm PO</strong>
            <small>Chọn tiêu chí</small>
          </div>
        </div>
      </details>
    """

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": 430, "height": 720})
            page.set_content(markup)
            card_style = page.locator(".sale-asn-advanced-group").evaluate(
                """element => {
                  const style = getComputedStyle(element);
                  return {
                    background: style.backgroundColor,
                    border: style.borderTopWidth,
                    radius: style.borderTopLeftRadius,
                    padding: style.paddingTop,
                  };
                }"""
            )
        finally:
            browser.close()

    assert card_style["background"] != "rgba(0, 0, 0, 0)"
    assert card_style["border"] != "0px"
    assert card_style["radius"] != "0px"
    assert float(card_style["padding"].removesuffix("px")) >= 8
