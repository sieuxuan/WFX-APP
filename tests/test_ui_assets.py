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
    assert 'class="compact-launcher"' in html


def test_header_has_drag_region_class_for_frameless_window():
    # Finding D: window.easy_drag=False + pywebview's own '.pywebview-drag-region'
    # convention (webview/js/customize.js) is the only thing that lets users move
    # a frameless always-on-top window; style.css alone (-webkit-app-region) is
    # not honored by WebView2/pywebview's drag implementation.
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="panel-header pywebview-drag-region"' in html


def test_footer_has_health_indicators():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'class="footer-health"',
        'class="health-chrome"',
        'class="health-session"',
        'class="health-refresh"',
    ]:
        assert hook in html, hook


def test_settings_has_new_toggles_and_enabled_hotkey_button():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'class="autostart-input"',
        'class="start-hidden-input"',
        'class="toast-input"',
        'class="always-on-top-input"',
        'class="stick-browser-input"',
    ]:
        assert hook in html, hook
    hotkey_tag = html[html.index('class="hotkey-button"') :]
    hotkey_tag = hotkey_tag[: hotkey_tag.index(">")]
    assert "disabled" not in hotkey_tag


def test_catalog_has_conditional_chrome_button_and_style_status():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'class="open-chrome-button"',
        'class="style-status"',
        'class="style-status-season"',
        'class="style-status-costsheet"',
    ]:
        assert hook in html, hook
    assert 'class="browser-banner" hidden' in html


def test_update_is_only_exposed_as_automatic_outside_banner():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="update-banner"' in html
    assert 'class="update-banner-button"' in html
    assert 'class="update-check-button"' not in html
    assert 'class="update-apply-button"' not in html
    assert 'class="update-channel-input"' not in html
    assert "Có phiên bản mới" in html
    assert "Cập nhật ngay" in html
    assert "Phiên bản 1.0" in html


def test_workspace_status_and_last_login_are_removed():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="workspace-pill"' not in html
    assert 'class="workspace-state"' not in html
    assert 'class="health-login"' not in html


def test_catalog_is_a_module_modal_not_a_fixed_dashboard_card():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="module-overlay"' in html
    assert 'data-module-view="catalog"' in html
    assert 'class="catalog-card"' not in html


def test_activity_sheet_has_jobs_screenshot_and_retry_hooks():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'class="job-history"',
        'data-activity-tab="jobs"',
        'data-activity-tab="log"',
        'class="clear-history-button"',
    ]:
        assert hook in html


def test_desktop_webview_width_does_not_trigger_single_column_layout():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert "@media (max-width: 430px)" not in css
    assert "@media (max-width: 360px)" in css


def test_windows_10_webview_css_avoids_new_color_mix_dependency():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert "color-mix(" not in css


def test_admin_toggle_and_feedback_dialog_have_contract_hooks():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'class="setting-row toggle-row admin-mode-row" hidden',
        'class="admin-mode-input"',
        'class="icon-button feedback-button"',
        'class="settings-overlay feedback-overlay"',
        'class="feedback-message"',
        "feedback-submit-button",
    ]:
        assert hook in html
    assert "WFX_ERROR_WEBHOOK_URL" not in html
