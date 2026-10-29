"""Điểm vào Catalog mà panel gọi: browse, prepare, find, folder, Costing/BOM."""

from __future__ import annotations

from wfx_panel import constants
from wfx_panel.automation._common import (
    CATALOG_XPATH,
    COMPANY_ID,
    Any,
    Callable,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _sleep,
    _style_status_suffix,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
    _start_persistent_chrome,
)
from wfx_panel.automation.catalog.article import (
    _article_navigation_states,
    _open_article_destination,
    _refresh_article_context,
)
from wfx_panel.automation.catalog.filters import (
    _CATALOG_FILTER_SPECS,
    _click_catalog_style,
    _filter_grid_and_maybe_open,
)
from wfx_panel.automation.catalog.folders import (
    _catalog_folder_for_node,
    _catalog_folder_nodes,
    _wait_catalog_folder_selected,
)
from wfx_panel.automation.catalog.grid import (
    _catalog_master_context_problem,
    _reuse_prepared_catalog_master,
    _show_catalog_floating_filter,
)
from wfx_panel.automation.catalog.navigation import (
    _catalog_left_frame,
    _catalog_tree_frame_now,
    _click_catalog_master,
    _open_catalog_menu_on_page,
    _open_catalog_tree_on_page,
    _select_catalog_category_on_page,
)
from wfx_panel.automation.catalog.quick_find import _quick_find_catalog_code
from wfx_panel.automation.session import _session_is_active, login

# Sau khi Master đã tạo grid mới: datasource + Floating Filter có tổng ngân
# sách riêng, không tính dồn với thời gian click Master.
_GRID_READY_TIMEOUT_S = 35


def _context_lost() -> dict[str, Any]:
    return _result(
        False,
        "CATALOG_SEARCH_CONTEXT_LOST",
        "Catalog không còn ở bước Master; app sẽ tự mở lại đúng List.",
    )


def _find_in_open_catalog(
    category_name: str,
    filter_kind: str,
    query: str,
    destination: str | None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Lọc grid và có thể mở đích trong cùng một phiên CDP/popup."""
    query = str(query or "").strip()
    if not query:
        return _result(False, "QUERY_REQUIRED", "Vui lòng nhập nội dung cần tìm.")
    if not _chrome_is_ready():
        return _result(
            False,
            "CHROME_CLOSED",
            "Trình duyệt làm việc chưa được mở.",
        )

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        category_value = constants.CATEGORIES.get(category_name, "")
        contexts = getattr(browser, "contexts", None) or []
        context = contexts[0] if contexts else None
        # Chụp popup TRƯỚC mọi lối mở Style (GetData hoặc click grid).
        previous_states = (
            _article_navigation_states(context)
            if context is not None
            else []
        )
        grid = None
        result = (
            _quick_find_catalog_code(page, category_value, query, log)
            if filter_kind == "code"
            else None
        )
        if result is None:
            _write_log(log, "[CATALOG] Đang kiểm tra grid Master hiện tại...")
            problem = _catalog_master_context_problem(page, category_value)
            if problem is not None:
                _write_log(log, f"[CATALOG] {problem}")
                return _context_lost()
            grid = _show_catalog_floating_filter(
                page,
                log,
                timeout_seconds=2,
            )
            _write_log(log, "[CATALOG] Đã xác nhận grid Master, bắt đầu tìm.")
            result = _filter_grid_and_maybe_open(
                grid,
                filter_kind,
                query,
                log,
            )
        # WFX đặt tên cửa sổ `ArticleDetail`: nếu popup Article đã mở thì
        # window.open TÁI DÙNG nó và kết nối CDP hiện tại không thấy document
        # mới (đo trên WFX: probe 3–4 giây luôn trượt, driver mới thấy ngay).
        # Khi đó recycle ngay đúng một lần, không probe. Nút File quét popup ở
        # một sub-op sau nên nhận cờ này qua kết quả.
        popup_already_open = any(state[2] for state in previous_states)
        if result.get("code") == "RESULT_OPENED":
            result["article_popup_reused"] = popup_already_open
        if (
            destination in {"costsheet", "bom"}
            and result.get("code") == "RESULT_OPENED"
        ):
            article_code = str(result.get("article_code") or "")
            label: str | None = None
            if not popup_already_open:
                try:
                    label = _open_article_destination(
                        context,
                        destination,
                        previous_states,
                        log,
                        timeout_seconds=4,
                        expected_article_code=article_code,
                    )
                except PlaywrightTimeoutError:
                    if grid is not None:
                        # Một số bản WFX bỏ click đầu tiên khi native popup
                        # chưa được activate. Click lại đúng nút Style trên
                        # grid đang có nhanh hơn mở lại Catalog và lọc từ đầu.
                        _write_log(
                            log,
                            "[ARTICLE] Popup chưa phản hồi; đang kích hoạt lại "
                            "đúng Style trên grid hiện tại...",
                        )
                        _click_catalog_style(
                            grid,
                            article_code,
                            _CATALOG_FILTER_SPECS[filter_kind].label,
                            log,
                        )
            else:
                _write_log(
                    log,
                    "[ARTICLE] WFX tái dùng popup Article đang mở; "
                    "kết nối lại để thấy trang mới...",
                )
            if label is None:
                # Không trả nhầm CATALOG_SEARCH_CONTEXT_LOST để controller mở
                # lại Catalog và lọc lần hai: Style đã được mở, chỉ cần nhận
                # lại popup bằng driver mới.
                playwright, browser, page = _refresh_article_context(
                    playwright,
                    browser,
                    page,
                    log,
                )
                context = browser.contexts[0]
                try:
                    label = _open_article_destination(
                        context,
                        destination,
                        [],
                        log,
                        timeout_seconds=18,
                        expected_article_code=article_code,
                    )
                except PlaywrightTimeoutError as exc:
                    # Style ĐÃ được mở; đây là lỗi popup, không phải mất
                    # context Master (ARTICLE_OPEN_NOT_CONFIRMED trong đặc tả).
                    _write_log(log, f"[ARTICLE] {_first_line(exc)}")
                    return {
                        **result,
                        **_result(
                            False,
                            "CATALOG_DESTINATION_FAILED",
                            "ARTICLE_OPEN_NOT_CONFIRMED: WFX chưa mở popup "
                            f"Article {article_code}. Bấm lại "
                            "Costing/BOM để thử mở trên Style vừa tìm.",
                        ),
                        "destination": destination,
                        "category": category_name,
                        "filter_kind": filter_kind,
                        "query": query,
                    }
            result["code"] = "CATALOG_DESTINATION_OPENED"
            result["destination"] = destination
            result["message"] = (
                f"Đã mở style {result['article_code']} → {label}."
                f"{_style_status_suffix(result.get('style_status'))}"
            )
        result["session_active"] = True
        result["category"] = category_name
        result["filter_kind"] = filter_kind
        result["query"] = query
        return result
    except PlaywrightTimeoutError:
        return _context_lost()
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CATALOG_SEARCH_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def find_in_open_catalog(
    category_name: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Lọc grid Catalog đã chuẩn bị; không mở lại menu/category/master."""
    return _find_in_open_catalog(
        category_name,
        filter_kind,
        query,
        None,
        log,
    )


def find_and_open_catalog_destination(
    category_name: str,
    filter_kind: str,
    query: str,
    destination: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Click style và mở Costing/BOM trong cùng driver để không mất popup."""
    if destination not in {"costsheet", "bom"}:
        return _result(
            False,
            "ARTICLE_DESTINATION_UNKNOWN",
            f"Đích Article không hỗ trợ: {destination}",
        )
    return _find_in_open_catalog(
        category_name,
        filter_kind,
        query,
        destination,
        log,
    )


# Ô nhập dữ liệu trên màn WFX đang mở mà người dùng có thể đã gõ dở. Ô lọc
# của AG Grid và thanh phân trang chỉ là bộ lọc List: mất đi không mất việc.
_UNSAVED_INPUT_JS = """() => {
    const shown = element => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' &&
            rect.width > 0 && rect.height > 0;
    };
    const skippedTypes = new Set([
        'hidden', 'button', 'submit', 'reset', 'image', 'checkbox', 'radio',
        'file', 'search'
    ]);
    return [...document.querySelectorAll('input, textarea')].some(field => {
        if (field.disabled || field.readOnly) return false;
        if (field.tagName === 'INPUT' &&
            skippedTypes.has((field.type || '').toLowerCase())) return false;
        if (field.closest('.ag-floating-filter, .ag-header, .ag-paging-panel')) {
            return false;
        }
        return String(field.value || '').trim() !== '' && shown(field);
    });
}"""


def _catalog_auto_open_blocker(page: Page) -> str | None:
    """Lý do KHÔNG được tự điều hướng tab WFX chính, hoặc None nếu an toàn.

    Tự mở Catalog khi người dùng chỉ vào module là thao tác họ chưa bấm. Nếu
    tab chính đang ở một màn khác còn dữ liệu nhập dở (New/Edit chứng từ,
    form tìm kiếm cổ điển), điều hướng body là mất trắng phần đó. Đọc lỗi
    cũng coi là không an toàn: không chắc thì không đụng.
    """
    if _catalog_tree_frame_now(page) is not None:
        return None
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            if frame.evaluate(_UNSAVED_INPUT_JS):
                return "màn WFX đang mở còn dữ liệu nhập"
        except PlaywrightError:
            return "không đọc được màn WFX đang mở"
    return None


def prepare_catalog_master(
    category_name: str,
    category_value: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở Catalog/Category/Master cho luồng Tìm, Costing và BOM."""
    return _prepare_catalog_master(category_name, category_value, log)


def auto_prepare_catalog_master(
    category_name: str,
    category_value: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Chuẩn bị Master ngay khi người dùng vào module Catalog, chưa bấm Tìm.

    Khác lượt do người dùng bấm: không đưa Chrome lên foreground và bỏ qua
    (``CATALOG_AUTO_PREPARE_SKIPPED``) khi tab chính đang có việc dở.
    """
    return _prepare_catalog_master(category_name, category_value, log, auto=True)


def _prepare_catalog_master(
    category_name: str,
    category_value: str,
    log: Callable[[str], None],
    *,
    auto: bool = False,
) -> dict[str, Any]:
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright, bring_to_front=not auto)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên chưa đăng nhập hoặc đã hết hạn.",
            )

        if _reuse_prepared_catalog_master(page, category_value, log):
            return _result(
                True,
                "CATEGORY_SELECTED",
                f"Đã chuẩn bị {category_name} > Master để tìm kiếm.",
                category=category_name,
                value=category_value,
            )

        blocker = _catalog_auto_open_blocker(page) if auto else None
        if blocker is not None:
            _write_log(
                log,
                f"[CATALOG] Không tự mở Catalog: {blocker}. Bấm Tìm khi sẵn sàng.",
            )
            return _result(
                True,
                "CATALOG_AUTO_PREPARE_SKIPPED",
                "Chưa tự mở Catalog để giữ màn WFX đang làm; bấm Tìm khi sẵn sàng.",
                category=category_name,
            )

        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        _open_catalog_tree_on_page(
            page,
            category_name,
            category_value,
            log,
        )
        _write_log(log, "[CATALOG] Đang chuẩn bị Master cho tìm kiếm...")
        _click_catalog_master(page, log)
        _show_catalog_floating_filter(
            page,
            log,
            previous_frame=previous_grid,
            require_data_ready=True,
            timeout_seconds=_GRID_READY_TIMEOUT_S,
        )
        return _result(
            True,
            "CATEGORY_SELECTED",
            f"Đã chuẩn bị {category_name} > Master để tìm kiếm.",
            category=category_name,
            value=category_value,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Catalog Master chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, getattr(exc, "code", "CATALOG_NOT_OPEN"), message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CATEGORY_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def scan_catalog_folders(
    category_name: str,
    category_value: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở cây Catalog và trả về mọi folder/group user được nhìn thấy."""
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên chưa đăng nhập hoặc đã hết hạn.",
            )

        frame = _open_catalog_tree_on_page(
            page,
            category_name,
            category_value,
            log,
        )
        folders = _catalog_folder_nodes(frame)
        if not folders:
            return _result(
                False,
                "CATALOG_FOLDER_TREE_EMPTY",
                "WFX chưa trả về cây thư mục Catalog.",
                category=category_name,
                value=category_value,
                folders=[],
            )
        _write_log(
            log,
            f"[CATALOG FOLDER] Đã quét {len(folders)} thư mục user được quyền xem.",
        )
        return _result(
            True,
            "CATALOG_FOLDERS_SCANNED",
            f"Đã quét {len(folders)} thư mục Catalog.",
            category=category_name,
            value=category_value,
            folders=folders,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Không quét được cây Catalog: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CATALOG_FOLDER_SCAN_TIMEOUT", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CATALOG_FOLDER_SCAN_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def open_catalog_folder(
    category_name: str,
    category_value: str,
    node_id: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở một folder user theo node ID; node rỗng nghĩa là Master."""
    node_id = str(node_id or "").strip()
    if node_id and not node_id.isdigit():
        return _result(
            False,
            "CATALOG_FOLDER_INVALID",
            "Thư mục Catalog không hợp lệ.",
        )

    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên chưa đăng nhập hoặc đã hết hạn.",
            )

        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        frame = _open_catalog_tree_on_page(
            page,
            category_name,
            category_value,
            log,
        )
        if not node_id:
            _click_catalog_master(page, log)
            _show_catalog_floating_filter(
                page,
                log,
                previous_frame=previous_grid,
                require_data_ready=True,
                timeout_seconds=_GRID_READY_TIMEOUT_S,
            )
            return _result(
                True,
                "CATALOG_FOLDER_OPENED",
                f"Đã mở {category_name} > Master.",
                category=category_name,
                value=category_value,
                folder={
                    "node_id": "",
                    "node_code": "Master",
                    "name": "Master",
                    "path": ["Master"],
                    "path_label": "Master",
                    "kind": "master",
                    "depth": 0,
                },
            )

        folder = _catalog_folder_for_node(frame, node_id)
        if folder is None:
            return _result(
                False,
                "CATALOG_FOLDER_STALE",
                "Folder mặc định không còn tồn tại hoặc user không còn quyền xem.",
                category=category_name,
                value=category_value,
            )

        target = frame.locator(f'span[nodeid="{node_id}"][onclick]').first
        target.wait_for(state="attached", timeout=3_000)
        _write_log(
            log,
            f"[CATALOG FOLDER] Đang mở {folder['path_label']}...",
        )
        target.evaluate("element => element.click()")
        if not _wait_catalog_folder_selected(page, node_id):
            raise PlaywrightTimeoutError("WFX không xác nhận folder đã chọn.")
        return _result(
            True,
            "CATALOG_FOLDER_OPENED",
            f"Đã mở Catalog > {folder['path_label']}.",
            category=category_name,
            value=category_value,
            folder=folder,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Không mở được thư mục Catalog: {_first_line(exc)}"
        _write_log(log, message)
        return _result(
            False,
            getattr(exc, "code", "CATALOG_FOLDER_OPEN_TIMEOUT"),
            message,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CATALOG_FOLDER_OPEN_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def quick_find_catalog(
    category_name: str,
    category_value: str,
    filter_kind: str,
    query: str,
    user_id: str,
    password: str,
    company_id: str = COMPANY_ID,
    log: Callable[[str], None] = print,
    destination: str | None = None,
) -> dict[str, Any]:
    """Tự login, vào Catalog/Category/Master rồi lọc và mở khi chỉ có một dòng."""
    query = query.strip()
    if not query:
        return _result(False, "QUERY_REQUIRED", "Vui lòng nhập nội dung cần tìm.")
    if destination and category_value != "01":
        return _result(
            False,
            "APPAREL_ONLY",
            "Costsheet và BOM chỉ hỗ trợ Category Apparel.",
        )

    playwright: Playwright | None = None
    try:
        _start_persistent_chrome(log)
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)

        if _session_is_active(page):
            _write_log(log, "[SESSION] Dùng lại phiên WFX đang login.")
        else:
            if not user_id.strip() or not password:
                return _result(
                    False,
                    "MISSING_CREDENTIALS",
                    "Chưa có tài khoản. Hãy lưu trong Settings.",
                )
            _write_log(log, "[SESSION] Chưa login, đang tự đăng nhập...")
            login(page, user_id.strip(), password, company_id)
            _write_log(log, "[SESSION] Tự đăng nhập thành công.")

        previous_left = _catalog_tree_frame_now(page)
        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        _write_log(log, "[QUICK SEARCH] Đang mở Catalog...")
        catalog = page.locator(f"xpath={CATALOG_XPATH}")
        catalog.wait_for(state="attached", timeout=8_000)
        _open_catalog_menu_on_page(
            page,
            catalog,
            log,
            previous_frame=previous_left,
        )

        _select_catalog_category_on_page(
            page,
            category_name,
            category_value,
            log,
            previous_frame=previous_left,
        )
        _write_log(log, "[QUICK SEARCH] Đang mở Master...")
        _click_catalog_master(page, log)
        grid = _show_catalog_floating_filter(
            page,
            log,
            previous_frame=previous_grid,
            require_data_ready=True,
        )
        result = _filter_grid_and_maybe_open(
            grid,
            filter_kind,
            query,
            log,
        )
        if destination and result.get("code") == "RESULT_OPENED":
            # Popup WFX cũ đôi khi chỉ được CDP nhận đầy đủ sau khi reconnect.
            _write_log(log, "[ARTICLE] Đang kết nối lại để nhận popup Article...")
            playwright.stop()
            playwright = None
            _sleep(0.8)
            playwright = sync_playwright().start()
            browser_after_popup, _main_page = _connect_to_chrome(playwright)
            destination_label = _open_article_destination(
                browser_after_popup.contexts[0],
                destination,
                [],
                log,
            )
            result["destination"] = destination
            result["message"] = (
                f"Đã mở style {result['article_code']} → {destination_label}."
                f"{_style_status_suffix(result.get('style_status'))}"
            )
        result["session_active"] = True
        result["category"] = category_name
        result["filter_kind"] = filter_kind
        result["query"] = query
        return result
    except PlaywrightTimeoutError as exc:
        message = f"Quick Search timeout: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "QUICK_SEARCH_TIMEOUT", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "QUICK_SEARCH_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def set_catalog_category(
    category_name: str,
    category_value: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Chọn Category trong frame left của Catalog."""
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        _write_log(log, "[CATEGORY] Đang tìm frame left và dropdown...")
        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        frame = _catalog_left_frame(page)
        category = frame.locator("#ddlCategory")
        current_value = category.input_value()
        _write_log(
            log,
            f"[CATEGORY] Giá trị hiện tại={current_value or '[Select]'}, cần chọn={category_value}",
        )

        # WFX chỉ nạp đủ option sau mousedown qua hàm BindDDL.
        _write_log(log, "[CATEGORY] Đang tải danh sách Category từ WFX...")
        category.dispatch_event("mousedown")
        option = category.locator(f'option[value="{category_value}"]')
        option.wait_for(state="attached", timeout=5_000)
        _write_log(log, f"[CATEGORY] Đã tải option {category_name}, đang chọn...")
        category.select_option(value=category_value, timeout=5_000)

        # Xác nhận lại sau onchange; WFX có thể reload nội dung frame.
        deadline = time.monotonic() + 8
        selected_value = ""
        while time.monotonic() < deadline:
            current_frame = _catalog_tree_frame_now(page)
            if current_frame is not None:
                try:
                    selected_value = current_frame.locator("#ddlCategory").input_value(
                        timeout=500
                    )
                    if selected_value == category_value:
                        break
                except PlaywrightTimeoutError:
                    pass
            _wait(page, 200)
        if selected_value != category_value:
            raise PlaywrightTimeoutError(
                f"WFX không xác nhận Category value={category_value}."
            )

        _write_log(log, f"[CATEGORY] Đã chọn thành công: {category_name}")
        _write_log(log, "[CATEGORY] Đang tự động mở Master...")
        _click_catalog_master(page, log)
        _show_catalog_floating_filter(
            page,
            log,
            previous_frame=previous_grid,
            require_data_ready=True,
        )
        return _result(
            True,
            "CATEGORY_SELECTED",
            f"Đã chọn {category_name}, mở Master và Floating Filter.",
            category=category_name,
            value=category_value,
        )
    except PlaywrightTimeoutError:
        message = "Không tìm thấy Category. Hãy mở Catalog trước."
        _write_log(log, message)
        return _result(False, "CATALOG_NOT_OPEN", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _write_log(log, message)
        return _result(False, "CATEGORY_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def open_catalog_master(log: Callable[[str], None] = print) -> dict[str, Any]:
    """Click node Master trong frame left của Catalog."""
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        _click_catalog_master(page, log)
        _show_catalog_floating_filter(
            page,
            log,
            previous_frame=previous_grid,
            require_data_ready=True,
        )
        _write_log(log, "Đã mở Catalog > Master và Floating Filter")
        return _result(
            True,
            "MASTER_OPENED",
            "Đã mở Catalog > Master và Floating Filter.",
        )
    except PlaywrightTimeoutError:
        message = "Không tìm thấy nút Master. Hãy mở Catalog trước."
        _write_log(log, message)
        return _result(False, "MASTER_NOT_FOUND", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _write_log(log, message)
        return _result(False, "MASTER_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def filter_and_open_catalog_code(
    article_code: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Lọc chính xác cột Code, cào kết quả rồi click mở style tương ứng."""
    article_code = article_code.strip()
    if not article_code:
        return _result(False, "CODE_REQUIRED", "Vui lòng nhập Code cần tìm.")

    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        grid = _show_catalog_floating_filter(page, log)

        code_input = grid.locator('input[aria-label="Code Filter Input"]')
        _write_log(log, f"[CODE] Đang lọc chính xác: {article_code}")
        code_input.fill(article_code, timeout=3_000)
        # AG Grid debounce trước khi áp dụng floating filter.
        _wait(grid, 1_000)

        code_cells = grid.locator(
            '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'
        )
        deadline = time.monotonic() + 12
        codes: list[str] = []
        exact_target = None
        while time.monotonic() < deadline:
            codes = []
            exact_target = None
            for index in range(code_cells.count()):
                item = code_cells.nth(index)
                try:
                    if not item.is_visible():
                        continue
                    value = item.input_value(timeout=500).strip()
                    if value:
                        codes.append(value)
                    if value.casefold() == article_code.casefold():
                        exact_target = item
                except PlaywrightError:
                    continue
            filter_applied = bool(codes) and all(
                article_code.casefold() in value.casefold() for value in codes
            )
            if exact_target is not None and filter_applied:
                break
            _wait(grid, 300)

        _write_log(log, f"[CODE] Kết quả grid: {codes if codes else 'không có'}")
        if exact_target is None:
            return _result(
                False,
                "CODE_NOT_FOUND",
                f"Không tìm thấy Code chính xác: {article_code}.",
                codes=codes,
            )

        _write_log(log, f"[CODE] Đã tìm thấy {article_code}, đang click mở style...")
        exact_target.click(timeout=5_000)
        _write_log(log, f"[CODE] Đã mở style: {article_code}")
        return _result(
            True,
            "CODE_OPENED",
            f"Đã lọc và mở style {article_code}.",
            article_code=article_code,
            codes=codes,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Timeout khi lọc Code: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CODE_FILTER_TIMEOUT", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "CODE_FILTER_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
