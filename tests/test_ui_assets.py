from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"


def test_style_css_exists_and_scoped_to_root():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert ".panel" in css
    assert ".accent-cyan" in css
    assert ":host" not in css  # đã đổi hết sang :root


def test_index_html_has_contract_hooks():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'class="module-list"',
        'data-catalog-action="prepare"',
        'data-catalog-action="code-find"',
        'data-catalog-action="buyer-bom"',
        'class="catalog-code"',
        'class="catalog-buyer-reference"',
        'class="user-input"',
        'class="save-button"',
        'class="catalog-log"',
        'data-theme-choice="dark"',
        'src="panel.js"',
    ]:
        assert hook in html, hook
    assert "launcher" not in html


def test_header_has_drag_region_class_for_frameless_window():
    # Finding D: window.easy_drag=False + pywebview's own '.pywebview-drag-region'
    # convention (webview/js/customize.js) is the only thing that lets users move
    # a frameless always-on-top window; style.css alone (-webkit-app-region) is
    # not honored by WebView2/pywebview's drag implementation.
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="panel-header pywebview-drag-region"' in html
