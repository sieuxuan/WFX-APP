from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"


def test_style_css_exists_and_scoped_to_root():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert ".panel" in css
    assert ".accent-cyan" in css
    assert ":host" not in css  # đã đổi hết sang :root


def test_desktop_override_forces_panel_visible():
    """Panel của extension ẩn mặc định (`.panel { opacity:0; visibility:hidden;
    pointer-events:none }`) và chỉ hiện khi JS thêm `.panel-open` lúc bấm nút
    launcher. Bản desktop bỏ launcher, không bao giờ thêm class đó — nếu khối
    override không vô hiệu hoá ba thuộc tính này thì cửa sổ chỉ hiển thị
    background_color, tức UI đen hoàn toàn. Đây là hồi quy đã xảy ra thật.
    """
    css = (UI / "style.css").read_text(encoding="utf-8")
    hidden_default = css.index("visibility: hidden")
    for declaration in (
        "opacity: 1 !important",
        "visibility: visible !important",
        "pointer-events: auto !important",
    ):
        assert declaration in css, declaration
        # Override phải nằm TRƯỚC rule ẩn của extension thì mới thắng nhờ
        # !important; nếu bị đặt sau, thứ tự cascade vẫn đúng nhưng ta muốn
        # giữ nguyên vị trí khối override đầu file.
        assert css.index(declaration) < hidden_default, declaration


def test_overlay_toggle_classes_match_the_css():
    """panel.js phải bật overlay bằng ĐÚNG tên class mà style.css định nghĩa.

    CSS trích từ extension bật Settings bằng `.settings-open` và Log bằng
    `.log-open`; `.settings-overlay` mặc định là `visibility:hidden; opacity:0`.
    Nếu JS thêm một class khác (vd `open` trần) thì không rule nào khớp và cả
    hai overlay KHÔNG BAO GIỜ mở được — đã xảy ra thật, người dùng không vào
    được Settings.
    """
    css = (UI / "style.css").read_text(encoding="utf-8")
    js = (UI / "panel.js").read_text(encoding="utf-8")
    assert ".settings-open" in css
    assert ".log-open" in css
    assert '"settings-open"' in js
    assert '"log-open"' in js
    assert 'classList.add("open")' not in js
    assert 'classList.remove("open")' not in js
    assert 'classList.contains("open")' not in js


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
