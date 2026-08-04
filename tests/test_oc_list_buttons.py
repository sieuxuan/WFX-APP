from pathlib import Path

from playwright.sync_api import sync_playwright

UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"


def test_oc_flow_action_labels_fit_inside_buttons_at_panel_width():
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    page_html = html.replace("</head>", f"<style>{css}</style></head>")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": 440, "height": 720})
            page.set_content(page_html)
            page.locator('[data-module-view="oc"]').evaluate(
                """element => {
                  for (let current = element; current; current = current.parentElement) {
                    current.hidden = false;
                  }
                }"""
            )
            measurements = page.locator(
                ".oc-flow-card .oc-upload-card-actions > button"
            ).evaluate_all(
                """buttons => buttons.map(button => {
                  return {
                    label: button.textContent.trim(),
                    clientWidth: button.clientWidth,
                    scrollWidth: button.scrollWidth,
                  };
                })"""
            )
        finally:
            browser.close()

    assert measurements
    assert [item["label"] for item in measurements] == [
        "Tải file mẫu",
        "Chọn file OC mới",
        "Mở report",
        "Chọn file Revise",
    ]
    assert all(
        item["scrollWidth"] <= item["clientWidth"] for item in measurements
    ), measurements
