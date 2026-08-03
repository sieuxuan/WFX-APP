import re
from pathlib import Path

from wfx_panel import panel_app

UI = Path(__file__).resolve().parent.parent / "wfx_panel" / "ui"


def test_style_css_exists_and_scoped_to_root():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert ".panel" in css
    assert ".accent-cyan" in css
    assert ":host" not in css  # đã đổi hết sang :root


def test_desktop_override_forces_panel_visible():
    """Layout gốc ẩn panel bằng `opacity`/`visibility`/`pointer-events`.
    Desktop panel không dùng class trượt `.panel-open` — nếu khối
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
        # Override phải nằm TRƯỚC rule ẩn gốc thì mới thắng nhờ
        # !important; nếu bị đặt sau, thứ tự cascade vẫn đúng nhưng ta muốn
        # giữ nguyên vị trí khối override đầu file.
        assert css.index(declaration) < hidden_default, declaration


def test_transition_background_is_restored_after_root_reset():
    css = (UI / "style.css").read_text(encoding="utf-8")
    root_reset = css.index(":root {")
    restored = css.index(":root { background: var(--panel-bg); }")
    assert restored > root_reset
    assert ":root.compact-mode { background: #0f9fb2; }" in css


def test_overlay_toggle_classes_match_the_css():
    """panel.js phải bật overlay bằng ĐÚNG tên class mà style.css định nghĩa.

    CSS bật Settings bằng `.settings-open` và Log bằng
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
        'data-catalog-action="refresh-folders"',
        'data-catalog-action="browse"',
        'data-catalog-action="find"',
        'data-catalog-action="bom"',
        'data-catalog-action="costsheet"',
        'data-catalog-action="files"',
        'data-costing-action="export-xlsx"',
        'data-costing-action="import"',
        'data-costing-action="apply"',
        'data-costing-action="clear-dependencies"',
        'class="catalog-special-rescan-input"',
        'class="catalog-style-autosave-input"',
        'class="catalog-style-group-summary"',
        'class="catalog-style-group-search"',
        'class="catalog-article-suggestions"',
        'data-catalog-kind="code"',
        'data-catalog-kind="buyer_reference"',
        'class="catalog-folder-search"',
        'class="catalog-folder-list"',
        'class="catalog-query"',
        'class="catalog-results-list"',
        'data-catalog-space="search"',
        'data-catalog-space="costing"',
        'data-catalog-space="styles"',
        'data-catalog-space-panel="costing"',
        'data-catalog-space-panel="styles"',
        'class="user-input"',
        'class="save-button settings-save-button"',
        'class="catalog-log"',
        'data-theme-choice="dark"',
        'data-theme-choice="system"',
        'data-module-action="oc-template"',
        'data-module-action="oc-upload-new"',
        'data-module-action="oc-review-cancel"',
        'data-module-action="oc-review-confirm"',
        'data-module-action="oc-revise-report"',
        'data-module-action="oc-upload-revise"',
        'data-module-action="sale-asn-documents"',
        'data-module-action="sale-asn-template"',
        'data-module-action="sale-asn-import"',
        'data-module-action="sale-asn-start"',
        'data-module-action="sale-asn-continue"',
        'data-module-action="sale-asn-skip-step"',
        'class="sale-asn-buyer"',
        'data-sale-asn-view="create"',
        'data-sale-asn-view="lookup"',
        'class="catalog-space-switch sale-asn-view-tabs"',
        'class="oc-upload-review"',
        'class="oc-review-identities"',
        'class="oc-review-metrics"',
        'class="oc-flow-grid"',
        'class="oc-list-search"',
        'src="panel.js?v=20260803-4"',
    ]:
        assert hook in html, hook
    assert "Tìm và mở đúng Style" not in html
    assert "Costing workspace" not in html
    assert "Xuất để chỉnh sửa" not in html
    assert "Quét Article cho dropdown" not in html
    assert '<span class="catalog-browse-label">Mở Catalog</span>' in html
    assert 'data-costing-action="export-csv"' not in html
    assert 'class="open-costing-folder-input"' not in html
    # Bubble tách thành cửa sổ/trang riêng → panel không còn nhúng launcher.
    assert 'class="compact-launcher"' not in html


def test_sale_asn_workspace_uses_one_flat_guided_flow():
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")

    assert 'class="workflow-choice-grid"' not in html[
        html.index('data-module-view="sale_asn"') : html.index(
            'data-module-view="rmpo"'
        )
    ]
    assert ".sale-asn-toolbar" in css
    assert ".sale-asn-step-heading" in css
    assert ".sale-asn-review" in css


def test_oc_workspace_uses_readable_balanced_layout():
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")

    assert 'class="special-module-workspace oc-workspace"' in html
    assert ".oc-list-search { display: grid; grid-template-columns: 118px minmax(0,1fr)" in css
    assert ".oc-flow-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr))" in css
    assert ".oc-list-card .oc-upload-card-copy strong { font-size: 16px" in css
    assert ".oc-review-metrics strong" in css and "font-size: 17px" in css


def test_status_is_only_in_footer_and_log_can_be_selected():
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert 'class="footer-status-text"' in html
    assert "module-page-status" not in html
    log_style = css[
        css.index(".catalog-log {") : css.index(".feedback-diagnostics")
    ]
    assert "-webkit-user-select: text" in log_style
    assert "user-select: text" in log_style
    assert "cursor: text" in log_style


def test_catalog_search_and_destinations_are_direct_actions():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert "Tìm trong Master" not in html
    assert 'class="catalog-destination-step"' not in html
    for action in ("find", "costsheet", "bom", "files"):
        tag = html[html.index(f'data-catalog-action="{action}"') :]
        tag = tag[: tag.index(">")]
        assert "disabled" not in tag
    assert 'class="catalog-folder-search"' in html
    assert 'class="catalog-folder-list"' in html
    assert 'class="catalog-browse-button"' in html
    assert 'class="catalog-results-list"' in html
    assert 'class="catalog-costing-card"' in html
    assert "Quét tab Costing hiện tại" not in html


def test_catalog_costing_has_a_dedicated_workspace():
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert 'data-catalog-space-panel="search"' in html
    assert 'data-catalog-space-panel="costing"' in html
    assert "Costing workspace" not in html
    assert 'id="catalog-costing-title">File Costing' in html
    assert ".catalog-space-switch" in css
    assert ".catalog-costing-workspace" in css


def test_catalog_folder_picker_is_searchable_and_hides_technical_copy():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'placeholder="Tìm folder, group hoặc đường dẫn…"' in html
    assert 'role="listbox"' in html
    assert 'class="catalog-folder-current"' in html
    assert "Duyệt Catalog" not in html
    assert "WFX Smart tự quét" not in html


def test_module_detail_page_header_uses_name_and_description_only():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'id="module-page-title"' in html
    assert 'class="module-back-button"' in html
    assert 'class="module-modal-subtitle"' in html
    assert 'class="module-modal-kicker"' not in html
    assert 'class="module-modal-description"' not in html
    page = html[html.index('class="module-page"') :]
    assert 'role="dialog"' not in page[: page.index('class="settings-overlay')]
    assert ">Operation<" not in page


def test_gdn_dispatch_workspace_matches_existing_module_ui():
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert 'data-module-view="gdn_dispatch"' in html
    assert 'class="gdn-invoice-query"' in html
    assert 'class="gdn-grn-confirm-input"' in html
    assert 'data-module-action="gdn-dispatch-submit"' in html
    assert "GRN ít nhất 15 phút" in html
    assert ".dispatch-warning" in css
    assert ".dispatch-submit-button" in css


def test_bubble_page_advertises_interactions():
    html = (UI / "bubble.html").read_text(encoding="utf-8")
    assert 'class="bubble pywebview-drag-region"' in html
    assert 'src="bubble.js?v=20260729-6"' in html
    button = html[html.index('class="bubble pywebview-drag-region"') :]
    button = button[: button.index(">")]
    assert "chuột phải" in button  # menu tùy chọn
    assert "kéo" in button


def test_bubble_menu_has_two_real_actions_in_a_separate_window():
    html = (UI / "bubble_menu.html").read_text(encoding="utf-8")
    js = (UI / "bubble_menu.js").read_text(encoding="utf-8")
    assert 'data-action="taskbar"' in html
    assert 'data-action="tray"' in html
    assert "Ẩn xuống taskbar" in html
    assert "Thu vào system tray" in html
    assert "api()?.choose?.(action)" in js
    assert "api()?.dismiss?.()" in js


def test_bubble_restores_the_previous_launcher_size():
    assert panel_app.BUBBLE_SIZE == 48


def test_bubble_restores_the_exact_main_launcher_visual():
    html = (UI / "bubble.html").read_text(encoding="utf-8")
    css = (UI / "bubble.css").read_text(encoding="utf-8")
    assert 'class="compact-icon-shell"' in html
    assert 'class="compact-orbit"' in html
    assert 'class="compact-mark"' in html
    assert "border-radius: 12px" in css
    assert "width: 32px" in css
    assert "width: 27px" in css
    assert "bubble-breathe" not in css
    assert "bubble-glow" not in html
    assert "body {\n  margin: 0;" in css
    assert "inset 0 0 0 1px rgba(255,255,255,.38)" in css
    assert "transparent=True" not in Path(panel_app.__file__).read_text(
        encoding="utf-8"
    )
    assert "shadow=False" in Path(panel_app.__file__).read_text(encoding="utf-8")


def test_bubble_uses_antialiased_dwm_corners_not_pixel_region():
    from wfx_panel import win32_window

    source = Path(win32_window.__file__).read_text(encoding="utf-8")
    assert "DWMWA_WINDOW_CORNER_PREFERENCE" in source
    assert "DWMWCP_ROUNDSMALL" in source
    assert "DWMWA_BORDER_COLOR" in source
    assert "CreateRoundRectRgn" not in source


def test_bubble_has_no_corner_status_dot():
    html = (UI / "bubble.html").read_text(encoding="utf-8")
    css = (UI / "bubble.css").read_text(encoding="utf-8")
    assert "compact-badge" not in html
    assert "compact-badge" not in css


def test_header_has_drag_region_class_for_frameless_window():
    # Finding D: window.easy_drag=False + pywebview's own '.pywebview-drag-region'
    # convention (webview/js/customize.js) is the only thing that lets users move
    # a frameless always-on-top window; style.css alone (-webkit-app-region) is
    # not honored by WebView2/pywebview's drag implementation.
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="panel-header pywebview-drag-region"' in html


def test_header_exposes_wfx_manual_button():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="icon-button manual-button"' in html
    assert 'aria-label="Mở hướng dẫn sử dụng WFX"' in html
    assert 'data-tooltip="Mở hướng dẫn sử dụng"' in html


def test_panel_uses_custom_tooltips_instead_of_native_titles():
    html = (UI / "index.html").read_text(encoding="utf-8")
    bubble_html = (UI / "bubble.html").read_text(encoding="utf-8")
    js = (UI / "panel.js").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")

    assert 'id="app-tooltip" role="tooltip"' in html
    assert "[data-tooltip]" in js
    assert ".app-tooltip[data-placement=\"top\"]::after" in css
    assert ".app-tooltip[data-placement=\"bottom\"]::after" in css
    assert re.search(r"\stitle=\"", html) is None
    assert re.search(r"\stitle=\"", bubble_html) is None
    assert ".title =" not in js


def test_sale_asn_documents_explains_query_and_reordered_docs_column():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'aria-describedby="sale-asn-documents-hint"' in html
    assert 'id="sale-asn-documents-hint"' in html
    assert "Không cần kéo cột Docs." in html


def test_visual_regression_harness_covers_theme_dpi_and_key_views():
    source = (
        UI.parent.parent / "scripts" / "visual_regression_panel.py"
    ).read_text(encoding="utf-8")
    for hook in (
        "DPI_FACTORS = {100: 1.0, 125: 1.25, 150: 1.5, 200: 2.0}",
        'THEMES = ("light", "dark")',
        'STATES = ("home", "tooltip", "catalog", "sale-asn", "settings")',
        '"Emulation.setDeviceMetricsOverride"',
        'webview.settings["REMOTE_DEBUGGING_PORT"]',
        'metrics.get("nativeTitles") != 0',
        'metrics.get("tinyButtons")',
        'metrics.get("scrollWidth", 0) > metrics.get("innerWidth", 0)',
    ):
        assert hook in source


def test_footer_has_health_indicators():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'class="footer-health"',
        'class="health-chrome"',
        'class="health-session"',
        'class="health-refresh"',
    ]:
        assert hook in html, hook
    assert 'class="stop-action-button"' in html
    assert "checkpoint an toàn" in html


def test_settings_has_new_toggles_and_enabled_hotkey_button():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'class="autostart-input"',
        'class="start-hidden-input"',
        'class="toast-input"',
        'class="focus-chrome-input"',
        'class="always-on-top-input"',
    ]:
        assert hook in html, hook
    hotkey_tag = html[html.index('class="hotkey-button"') :]
    hotkey_tag = hotkey_tag[: hotkey_tag.index(">")]
    assert "disabled" not in hotkey_tag


def test_settings_account_flow_and_defaults_are_safe():
    html = (UI / "index.html").read_text(encoding="utf-8")
    save_index = html.index('class="save-button settings-save-button"')
    account_index = html.index('class="form-grid"')
    # CTA nằm sau hai field để luồng đọc/nhập tự nhiên từ trên xuống.
    assert save_index > account_index
    start_hidden_tag = html[html.index('class="start-hidden-input"') :]
    start_hidden_tag = start_hidden_tag[: start_hidden_tag.index(">")]
    admin_tag = html[html.index('class="admin-mode-input"') :]
    admin_tag = admin_tag[: admin_tag.index(">")]
    assert "checked" not in start_hidden_tag
    assert "checked" not in admin_tag
    assert 'class="account-connected-view" hidden' in html
    assert 'class="account-change-button"' in html
    assert 'class="account-status-user" hidden' in html


def test_division_switcher_precedes_operation_and_has_three_choices():
    html = (UI / "index.html").read_text(encoding="utf-8")
    division_index = html.index('class="division-card"')
    operation_index = html.index('class="module-list"')
    assert division_index < operation_index
    for key, label in [
        ("woven", "WOVEN"),
        ("knit", "KNIT"),
        ("pssg", "PSSG"),
    ]:
        assert f'data-division="{key}"' in html
        assert f"<span>{label}</span>" in html
    for removed in [
        "Không gian làm việc",
        "Mở đúng màn hình WFX chỉ với một lần bấm",
        "Division đang làm việc",
        "Hà Nội",
        "Singapore",
        "Chọn Division trước khi mở",
    ]:
        assert removed not in html


def test_module_page_header_is_compact_with_clear_back_icon():
    html = (UI / "index.html").read_text(encoding="utf-8")
    header = html[html.index('class="module-page-header"') :]
    header = header[: header.index("</header>")]
    assert "<svg" in header
    assert 'd="m15 18-6-6 6-6"' in header
    assert 'class="module-modal-icon' not in html


def test_catalog_uses_compact_category_search_and_costing_actions():
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")

    assert 'class="catalog-topbar"' in html
    assert html.index('class="catalog-category-row"') < html.index(
        'data-catalog-action="browse"'
    )
    assert 'class="catalog-search-heading"' not in html
    assert 'class="catalog-costing-state"' not in html
    assert "Có thể Export/Import" not in html
    assert 'class="catalog-costing-utility-row"' in html
    assert ".catalog-topbar {" in css
    assert "grid-template-columns: repeat(3, minmax(0,1fr))" in css


def test_favorites_scroll_without_moving_module_search():
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert html.index('class="search-box"') < html.index(
        'class="favorites-section"'
    )
    modules_scroll = html[
        html.index('class="modules-scroll"') : html.index(
            'class="module-list"'
        )
    ]
    assert 'class="favorites-section"' in modules_scroll
    assert 'class="module-favorite-button"' not in html
    assert 'class="return-list-input" type="checkbox"' in html
    favorite_button = css[
        css.index(".module-favorite-button {") : css.index(
            ".module-favorite-button:hover"
        )
    ]
    favorites_list = css[
        css.index(".favorites-list {") : css.index(
            ".favorites-list .module-button"
        )
    ]
    assert "place-items: center" in favorite_button
    assert "transform: translateY(-50%)" in favorite_button
    assert "width: 34px" in favorite_button
    assert "height: 34px" in favorite_button
    assert "overflow" not in favorites_list
    assert "max-height" not in favorites_list
    assert ".favorites-list .module-card:last-child:nth-child(odd)" not in css


def test_header_alerts_are_labeled_instead_of_ambiguous_red_dots():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert '.log-alert::before { content: "!"; }' in css
    assert '.manual-alert::before { content: "Mới"; }' in css
    assert ".log-alert { background: var(--warn); }" in css
    assert "Có tác vụ cần xử lý" not in (
        UI / "panel.js"
    ).read_text(encoding="utf-8")


def test_external_notification_and_generic_svg_icon_are_present():
    html = (UI / "index.html").read_text(encoding="utf-8")
    notification = (UI / "notification.html").read_text(encoding="utf-8")
    notification_js = (UI / "notification.js").read_text(encoding="utf-8")
    assert 'class="toast-stack"' not in html
    assert 'class="notification notification-success"' in notification
    assert "window.wfxShowNotification" in notification_js
    assert "textContent = payload.message" in notification_js
    assert 'class="notification-detail"' in notification
    assert "-webkit-line-clamp" not in (
        UI / "notification.css"
    ).read_text(encoding="utf-8")
    assert 'classList.add("notification-visible")' in notification_js
    assert "window.requestAnimationFrame(" not in notification_js
    assert "getBoundingClientRect().height" not in notification_js
    assert 'class="operation-progress"' in html
    assert 'class="generic-module-icon"' in html
    assert 'class="generic-module-code"' not in html


def test_rmpo_indent_invoice_and_list_new_workspaces_are_present():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for view in (
        "rmpo",
        "indent",
        "advance_pr",
        "supplier_invoice",
        "expense_invoice",
        "list_new",
    ):
        assert f'data-module-view="{view}"' in html
    for hook in (
        "rmpo-supplier-query",
        "rmpo-order-query",
        "indent-supplier-query",
        "indent-article-query",
        "indent-no-query",
        "indent-style-query",
        "advance-pr-buyer-query",
        "advance-pr-supplier-query",
        "advance-pr-invoice-query",
        "advance-pr-order-query",
        'data-module-action="advance-pr-search"',
        "supplier-invoice-supplier-query",
        "supplier-invoice-no-query",
        "supplier-invoice-po-query",
        "supplier-invoice-asn-grn-query",
        'data-module-action="supplier-invoice-cancel"',
        "expense-invoice-supplier-query",
        "expense-invoice-created-by-query",
        'data-module-action="expense-invoice-search"',
        'data-module-action="list-new-new"',
    ):
        assert hook in html


def test_ui_uses_short_compositor_motion_with_reduced_motion_fallback():
    css = (UI / "style.css").read_text(encoding="utf-8")
    for hook in (
        "@keyframes view-enter",
        "@keyframes operation-enter",
        "@keyframes operation-track",
        ".is-action-source",
        "@media (prefers-reduced-motion: reduce)",
    ):
        assert hook in css


def test_button_states_are_consistent_and_keyboard_visible():
    css = (UI / "style.css").read_text(encoding="utf-8")
    for hook in (
        "button:focus-visible",
        "button:disabled",
        "button.is-action-source:disabled",
        "button:not(.module-favorite-button):active:not(:disabled)",
        ".footer-help-button { width: 22px; height: 22px; }",
    ):
        assert hook in css

    supporting_css = {
        path.name: path.read_text(encoding="utf-8")
        for path in (
            UI / "manual.css",
            UI / "bubble.css",
            UI / "bubble_menu.css",
            UI / "notification.css",
        )
    }
    assert "button:focus-visible" in supporting_css["manual.css"]
    assert ".bubble:focus-visible" in supporting_css["bubble.css"]
    assert "button:focus-visible" in supporting_css["bubble_menu.css"]
    assert ".notification-close:focus-visible" in supporting_css[
        "notification.css"
    ]


def test_small_light_theme_text_tokens_meet_wcag_contrast():
    css = (UI / "style.css").read_text(encoding="utf-8")
    light_theme = css[: css.index(':root[data-theme="dark"]')]

    def token(name: str) -> str:
        match = re.search(rf"--{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}})", light_theme)
        assert match is not None
        return match.group(1)

    def luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    background = luminance(token("surface-2"))
    for name in ("text-3", "accent", "accent-strong", "warn", "bad"):
        foreground = luminance(token(name))
        ratio = (max(foreground, background) + 0.05) / (
            min(foreground, background) + 0.05
        )
        assert ratio >= 4.5, f"{name} chỉ đạt contrast {ratio:.2f}:1"


def test_spinners_use_one_calm_cross_device_duration():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert "--spinner-duration: 1.25s" in css
    assert css.count("var(--spinner-duration) linear infinite") == 3
    assert "animation: spin .7s" not in css


def test_settings_are_split_into_three_focused_tabs_with_auth_prompt():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'data-settings-tab="account"',
        'data-settings-tab="automation"',
        'data-settings-tab="appearance"',
        'data-settings-panel="account"',
        'data-settings-panel="automation"',
        'data-settings-panel="appearance"',
        'class="auth-prompt"',
        'class="account-form-status"',
        'class="settings-sticky-header"',
    ]:
        assert hook in html
    assert html.index('data-settings-tab="automation"') < html.index(
        'data-settings-tab="appearance"'
    )
    assert html.index('data-settings-tab="appearance"') < html.index(
        'data-settings-tab="account"'
    )


def test_settings_sheet_is_pinned_to_top_and_catalog_keeps_browse_card():
    html = (UI / "index.html").read_text(encoding="utf-8")
    css = (UI / "style.css").read_text(encoding="utf-8")
    js = (UI / "panel.js").read_text(encoding="utf-8")

    assert ".settings-main-overlay { align-items: flex-start; }" in css
    assert 'openSettings("automation")' in js
    assert 'class="catalog-browse-card"' in html
    assert "!supportsDefault || !catalogFolderEditorOpen" in js
    assert 'class="catalog-folder-summary"' in html
    assert '$(".catalog-browse-card").hidden' not in js


def test_catalog_uses_one_outer_scroll_and_reduced_card_borders():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert (
        ".catalog-results-list { display: flex; flex-direction: column; "
        "gap: 3px; max-height: none; overflow: visible; }"
    ) in css
    assert (
        ".catalog-browse-card { padding: 0 0 6px; border: 0; "
        "border-bottom: 1px solid var(--border); background: transparent; }"
    ) in css
    assert ".catalog-workspace {\n      padding: 1px 2px 10px;\n      border: 0;" in css


def test_panel_uses_crisp_windows_font_rendering():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert 'font-family: "Segoe UI", Tahoma, Arial, sans-serif;' in css
    assert "-webkit-font-smoothing: auto; text-rendering: auto;" in css
    assert "Segoe UI Variable Text" not in css


def test_supporting_text_and_footer_use_readable_minimum_size():
    css = "\n".join(
        path.read_text(encoding="utf-8")
        for path in UI.glob("*.css")
    )
    assert not re.search(
        r"font-size:\s*(?:8(?:\.5)?|9(?:\.5)?|10(?:\.5)?)px",
        css,
    )
    assert ".panel-footer { min-height: 30px" in css
    assert ".admin-mode-row[hidden] { display: none !important; }" in css


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
    assert "Có bản cập nhật mới" in html
    assert "Cập nhật phần mềm mới" in html
    assert 'class="app-version"' in html


def test_workspace_status_and_last_login_are_removed():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="workspace-pill"' not in html
    assert 'class="workspace-state"' not in html
    assert 'class="health-login"' not in html


def test_catalog_is_a_module_detail_page_not_a_fixed_dashboard_card():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="module-page"' in html
    assert 'aria-hidden="true" hidden' in html
    assert 'class="module-overlay"' not in html
    assert 'data-module-view="catalog"' in html
    assert 'class="catalog-card"' not in html


def test_special_module_workspaces_have_contract_hooks():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'data-module-view="oc"',
        'data-module-action="oc-list"',
        'data-module-action="oc-search"',
        'class="oc-query"',
        'data-module-view="sample"',
        'data-module-action="sample-list"',
        'data-module-action="sample-new"',
        'data-module-action="sample-search"',
        'data-module-action="sample-check-file"',
        'class="sample-no-query"',
        'class="sample-style-query"',
        'class="sample-created-by-query"',
        'class="sample-buyer-query"',
        'class="sample-file-results"',
        'data-module-view="sale_asn"',
        'data-module-action="sale-asn-list"',
        'data-module-action="sale-asn-new"',
        'data-module-action="sale-asn-search"',
        'class="sale-asn-query"',
        'data-filter-kind="buyer_order_ref"',
        'data-module-view="supplier"',
        'class="supplier-category"',
        'class="supplier-query"',
        'data-module-action="supplier-list"',
        'data-module-action="supplier-open"',
        'data-module-action="supplier-find"',
        'data-module-view="company_setup"',
        'data-module-action="company-list"',
        'data-module-action="company-toggle-foc"',
        'data-module-view="buyer"',
        'class="buyer-query"',
        'data-module-action="buyer-list"',
        'data-module-action="buyer-find"',
    ]:
        assert hook in html, hook
    assert 'class="stick-browser-input"' not in html
    assert "Bám theo browser automation" not in html
    for category in [
        "Apparel",
        "Fixed Asset",
        "Miscellaneous",
        "Services",
        "Textiles/Fabric",
        "Trims",
    ]:
        assert f'>{category}</option>' in html


def test_activity_sheet_has_jobs_screenshot_and_retry_hooks():
    html = (UI / "index.html").read_text(encoding="utf-8")
    for hook in [
        'class="job-history"',
        'data-activity-tab="jobs"',
        'data-activity-tab="log"',
        'class="clear-history-button"',
    ]:
        assert hook in html
    assert 'data-activity-tab="attention"' not in html
    assert 'data-activity-view="attention"' not in html
    assert "Cần xử lý" not in html


def test_desktop_webview_width_does_not_trigger_single_column_layout():
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert "@media (max-width: 430px)" not in css
    assert "@media (max-width: 360px)" in css
    assert (
        ".module-grid { display: grid; "
        "grid-template-columns: repeat(2, minmax(0, 1fr));"
    ) in css
    assert ".module-grid { grid-template-columns: 1fr; }" not in css


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
    assert 'id="feedback-character-count"' in html
    assert "Tối thiểu 5 ký tự" in html
    submit_tag = html[html.index("feedback-submit-button") :]
    submit_tag = submit_tag[: submit_tag.index(">")]
    assert "disabled" in submit_tag
    assert "WFX_ERROR_WEBHOOK_URL" not in html


def test_division_switcher_is_visually_compact():
    css = (UI / "style.css").read_text(encoding="utf-8")
    compact_refresh = css[css.index("/* 1.0.4 visual refresh") :]
    division_card = compact_refresh[
        compact_refresh.index(".division-card {") :
        compact_refresh.index(".division-card::after")
    ]
    division_button = compact_refresh[
        compact_refresh.index(".division-button {") :
        compact_refresh.index(".division-button:hover")
    ]
    assert "padding: 4px" in division_card
    assert "margin: 0 0 5px" in division_card
    assert "height: 29px" in division_button


def test_manual_window_co_du_ba_vung_chinh():
    html = (UI / "manual.html").read_text(encoding="utf-8")
    assert 'class="manual-search"' in html
    assert 'class="manual-toc"' in html
    assert 'class="manual-content"' in html
    assert "manual.css" in html
    assert "manual.js" in html
    # Manual chạy offline: không được nạp tài nguyên từ mạng.
    assert "http://" not in html
    assert "https://" not in html


def test_manual_css_co_token_rieng_va_ban_in():
    css = (UI / "manual.css").read_text(encoding="utf-8")
    assert ":root {" in css
    assert ':root[data-theme="dark"]' in css
    assert "@media print" in css
    assert ".callout-meo" in css
    assert ".callout-luuy" in css
    assert ".callout-loi" in css


def test_manual_js_phoi_bay_ham_dieu_huong():
    js = (UI / "manual.js").read_text(encoding="utf-8")
    assert "window.wfxManualGoTo" in js
    assert "get_manual_book" in js


def test_manual_js_dung_bang_ma_loi():
    js = (UI / "manual.js").read_text(encoding="utf-8")
    assert "error_table" in js
    assert "su-co-tra-ma-loi" in js


def test_manual_tra_ma_loi_chinh_xac_mo_bang_va_cuon_toi_ma():
    js = (UI / "manual.js").read_text(encoding="utf-8")
    assert "showErrorTable" in js
    assert "data-error-code" in js
    assert "scrollIntoView" in js


def test_manual_home_co_loi_tat_va_enter_mo_ket_qua_dau():
    js = (UI / "manual.js").read_text(encoding="utf-8")
    assert "Tra nhanh mã lỗi" in js
    assert "Câu hỏi thường gặp" in js
    assert 'event.key === "Enter"' in js
    assert '$(".manual-results .manual-hit")?.click()' in js


def test_manual_co_nut_in_va_ctrl_p_goi_bridge_native():
    html = (UI / "manual.html").read_text(encoding="utf-8")
    js = (UI / "manual.js").read_text(encoding="utf-8")
    assert 'class="manual-print"' in html
    assert "In / Lưu PDF" in html
    assert 'event.key.toLowerCase() === "p"' in js
    assert "print_manual" in js
    assert "window.print()" not in js


def test_manual_tim_kiem_khong_dau_va_tim_duoc_noi_dung_ma_loi():
    js = (UI / "manual.js").read_text(encoding="utf-8")
    assert '.normalize("NFD")' in js
    assert 'replace(/đ/g, "d")' in js
    assert "row.haystack.includes(needle)" in js


def test_nhan_giao_dien_dung_tieng_viet_thong_nhat():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert "Phím tắt mở bảng điều khiển" in html
    assert "Mở ẩn trong khay hệ thống" in html
    assert "Chưa có trình duyệt làm việc" in html
    for phrase in ("Hotkey mở panel", "Mở ẩn trong tray", "trình duyệt automation"):
        assert phrase not in html


def test_module_page_co_nut_tro_giup():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="icon-button module-help-button"' in html


def test_footer_co_nut_xem_huong_dan():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'class="footer-help-button"' in html


def test_badge_phien_ban_khong_hardcode():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert '<span class="app-version"></span>' in html
    assert "Phiên bản 1.0<" not in html
