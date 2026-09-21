"""Điểm vào chỉ-đọc: quét Costing đang mở, dọn dependency, kiểm tra context."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from wfx_panel.automation._common import (
    Page,
    Playwright,
    _first_line,
    _result,
    _sleep,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.costing.constants import FORBIDDEN_ACTION_SELECTORS
from wfx_panel.automation.costing.context import (
    _active_costing_page,
    _article_code_from_page,
    _costing_frame,
    _selected_costing_title,
    _status_from_tree,
    _style_name_from_page,
)
from wfx_panel.automation.costing.fields import _save_costing
from wfx_panel.automation.costing.inventory import _inventory_costing_frame
from wfx_panel.automation.runtime import cancellation_deferred
from wfx_panel.automation.session import _session_is_active


def _scan_open_costing_context(
    context: Any,
    article_code: str,
    *,
    pages: Sequence[Page] | None = None,
    style_status: Mapping[str, Any] | None = None,
    require_open: bool = True,
    scan_details: bool = False,
    scan_article_options: bool = False,
    scan_special_cost_options: bool = True,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Quét Costing trong phạm vi Page đã chỉ định."""
    _page, frame = _costing_frame(context, pages=pages)
    status = str((style_status or {}).get("internal_costsheet_status") or "").strip()
    status = status or _status_from_tree(frame)
    if require_open and status.casefold() != "open":
        return _result(
            False,
            "COSTING_NOT_OPEN",
            (
                "CostSheet phải ở trạng thái Open mới có thể Export/Import. "
                "Hãy tự tạo hoặc mở Costing đầy đủ trước."
            ),
            article_code=article_code,
            style_name=_style_name_from_page(_page),
            costing_status=status or "Unknown",
        )
    season = str((style_status or {}).get("season") or "").strip()
    title = _selected_costing_title(context, pages=pages)
    document = _inventory_costing_frame(
        frame,
        article_code,
        costing_status=status,
        season=season,
        title=title,
        style_name=_style_name_from_page(_page),
        scan_details=scan_details,
        scan_article_options=scan_article_options,
        scan_special_cost_options=scan_special_cost_options,
        log=log,
    )
    if not (document["sections"] or document["fields"]):
        # Quick Find returns as soon as the Costing frame exists, while WFX
        # fills its grid in a later request. Never export a transient workbook.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not (
            document["sections"] or document["fields"]
        ):
            _sleep(0.25)
            _page, frame = _costing_frame(
                context,
                timeout_seconds=2,
                pages=pages,
            )
            title = _selected_costing_title(context, pages=pages) or title
            document = _inventory_costing_frame(
                frame,
                article_code,
                costing_status=status,
                season=season,
                title=title,
                style_name=_style_name_from_page(_page),
                scan_details=scan_details,
                scan_article_options=scan_article_options,
                scan_special_cost_options=scan_special_cost_options,
                log=log,
            )
        if not (document["sections"] or document["fields"]):
            return _result(
                False,
                "COSTING_OPEN_NOT_LOADED",
                "Costing đang Open nhưng WFX chưa tải xong dữ liệu.",
                article_code=article_code,
            )
    _write_log(
        log,
        "[COSTING] Đã đọc "
        f"{len(document['sections'])} section, "
        f"{len(document['items'])} Article, "
        f"{len(document['fields'])} field.",
    )
    return _result(
        True,
        "COSTING_SCANNED",
        f"Đã đọc đầy đủ thông tin Costing cho style {article_code}.",
        article_code=article_code,
        costing=document,
        section_count=len(document["sections"]),
        item_count=len(document["items"]),
        field_count=len(document["fields"]),
    )


def _costing_scan_error(
    error: Exception,
    article_code: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    raw = _first_line(error)
    messages = {
        "COSTING_ACTIVE_TAB_NOT_FOUND": (
            "Tab đang chọn chưa ở màn Costing. Hãy mở Costing cần xuất rồi thử lại."
        ),
        "COSTING_ACTIVE_TAB_AMBIGUOUS": (
            "Có nhiều cửa sổ Costing đang hiển thị; hãy chỉ giữ màn cần xuất "
            "ở trạng thái đang chọn."
        ),
        "COSTING_CONTEXT_NOT_FOUND": (
            "Không tìm thấy màn Costing của style đang chọn."
        ),
        "COSTING_DEPENDENCY_SCAN_INCOMPLETE": (
            "Chưa đọc được đầy đủ bảng Color/Size Dependency. Hãy đóng các "
            "popup Dependency còn mở trên WFX rồi xuất lại."
        ),
    }
    if raw in messages:
        return _result(
            False,
            raw,
            messages[raw],
            article_code=article_code,
        )
    message = f"{type(error).__name__}: {raw}"
    _write_log(log, f"[COSTING] {message}")
    return _result(
        False,
        "COSTING_SCAN_FAILED",
        message,
        article_code=article_code,
    )


def scan_open_costing(
    article_code: str,
    *,
    style_status: Mapping[str, Any] | None = None,
    require_open: bool = True,
    scan_details: bool = False,
    scan_article_options: bool = False,
    scan_special_cost_options: bool = True,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Đọc Costing đã tìm bằng app; không click New, Article, Delete hoặc Save."""
    article_code = str(article_code or "").strip()
    if not article_code:
        return _result(
            False,
            "CATALOG_RESULT_REQUIRED",
            "Hãy tìm và mở một Style Code trước.",
        )
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _connect_to_chrome(playwright, bring_to_front=False)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        return _scan_open_costing_context(
            browser.contexts[0],
            article_code,
            style_status=style_status,
            require_open=require_open,
            scan_details=scan_details,
            scan_article_options=scan_article_options,
            scan_special_cost_options=scan_special_cost_options,
            log=log,
        )
    except Exception as error:
        return _costing_scan_error(error, article_code, log)
    finally:
        if playwright is not None:
            playwright.stop()


def scan_active_open_costing(
    *,
    require_open: bool = True,
    scan_details: bool = False,
    scan_article_options: bool = False,
    scan_special_cost_options: bool = True,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Quét đúng tab Costing đang hiển thị, không tìm Style hoặc đổi tab."""
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    article_code = ""
    try:
        playwright = sync_playwright().start()
        browser, session_page = _connect_to_chrome(
            playwright,
            bring_to_front=False,
        )
        _attach_dialog_handler(session_page, log)
        if not _session_is_active(session_page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        context = browser.contexts[0]
        active_page = _active_costing_page(context)
        article_code = _article_code_from_page(active_page)
        if not article_code:
            return _result(
                False,
                "COSTING_STYLE_NOT_DETECTED",
                (
                    "Đã thấy tab Costing nhưng chưa đọc được Style Code. "
                    "Hãy giữ phần thông tin Style trên tab rồi thử lại."
                ),
            )
        _write_log(
            log,
            f"[COSTING] Dùng tab Costing đang chọn của style {article_code}.",
        )
        return _scan_open_costing_context(
            context,
            article_code,
            pages=[active_page],
            require_open=require_open,
            scan_details=scan_details,
            scan_article_options=scan_article_options,
            scan_special_cost_options=scan_special_cost_options,
            log=log,
        )
    except Exception as error:
        return _costing_scan_error(error, article_code, log)
    finally:
        if playwright is not None:
            playwright.stop()


def clear_active_costing_dependencies(
    *,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Bấm mọi Clear Dependency của đúng tab Costing đang chọn rồi Save."""
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    article_code = ""
    try:
        playwright = sync_playwright().start()
        browser, session_page = _connect_to_chrome(
            playwright,
            bring_to_front=False,
        )
        _attach_dialog_handler(session_page, log)
        if not _session_is_active(session_page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        context = browser.contexts[0]
        active_page = _active_costing_page(context)
        article_code = _article_code_from_page(active_page)
        _page, frame = _costing_frame(context, pages=[active_page])
        status = _status_from_tree(frame)
        if status.casefold() != "open":
            return _result(
                False,
                "COSTING_NOT_OPEN",
                "Chỉ CostSheet Open mới được Clear All Dependency.",
                article_code=article_code,
            )
        links = frame.locator('[id="lnkClearDependency"]')
        link_count = links.count()
        if link_count < 1:
            return _result(
                True,
                "COSTING_DEPENDENCIES_ALREADY_CLEAR",
                "Costing hiện tại không có nút Clear Dependency.",
                article_code=article_code,
                cleared_section_count=0,
            )
        dialog_messages: list[str] = []

        def accept_clear_dialog(dialog: Any) -> None:
            dialog_messages.append(str(dialog.message or "").strip())
            dialog.accept()

        active_page.on("dialog", accept_clear_dialog)
        try:
            with cancellation_deferred():
                # Snapshot theo index: link có id trùng nhau ở nhiều section.
                # evaluate click được cả section đang cuộn khỏi viewport.
                for index in range(link_count):
                    current_links = frame.locator('[id="lnkClearDependency"]')
                    if current_links.count() <= index:
                        raise RuntimeError("COSTING_CLEAR_DEPENDENCY_TARGET_CHANGED")
                    current_links.nth(index).evaluate("element => element.click()")
                    _sleep(0.15)
        finally:
            active_page.remove_listener("dialog", accept_clear_dialog)
        _save_costing(active_page, frame, log)
        _write_log(
            log,
            f"[COSTING] Đã Clear Dependency ở {link_count} section và Save.",
        )
        return _result(
            True,
            "COSTING_DEPENDENCIES_CLEARED",
            f"Đã Clear Dependency ở {link_count} phần và Save Costing.",
            article_code=article_code,
            cleared_section_count=link_count,
            confirmations=[message for message in dialog_messages if message],
        )
    except Exception as error:
        raw = _first_line(error)
        code = raw if raw.startswith("COSTING_") else "COSTING_CLEAR_FAILED"
        _write_log(log, f"[COSTING CLEAR] {type(error).__name__}: {raw}")
        return _result(
            False,
            code,
            "Không thể Clear toàn bộ Dependency hoặc chưa xác nhận Save.",
            article_code=article_code,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def inspect_active_costing(
    *,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Đọc nhanh Style Code/status của tab Costing hiện tại, không inventory."""
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")
    playwright: Playwright | None = None
    article_code = ""
    try:
        playwright = sync_playwright().start()
        browser, session_page = _connect_to_chrome(
            playwright,
            bring_to_front=False,
        )
        _attach_dialog_handler(session_page, log)
        if not _session_is_active(session_page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        context = browser.contexts[0]
        active_page = _active_costing_page(context)
        article_code = _article_code_from_page(active_page)
        if not article_code:
            return _result(
                False,
                "COSTING_STYLE_NOT_DETECTED",
                "Đã thấy tab Costing nhưng chưa đọc được Style Code.",
            )
        _page, frame = _costing_frame(
            context,
            timeout_seconds=3,
            pages=[active_page],
        )
        status = _status_from_tree(frame)
        _write_log(
            log,
            f"[COSTING] Tab hiện tại: {article_code}; status={status or 'Unknown'}.",
        )
        return _result(
            True,
            "COSTING_CONTEXT_INSPECTED",
            f"Đã nhận tab Costing {article_code}.",
            article_code=article_code,
            style_name=_style_name_from_page(active_page),
            costing_status=status or "Unknown",
            style_status={
                "code": article_code,
                "season": "",
                "internal_costsheet_status": status or "Unknown",
            },
        )
    except Exception as error:
        return _costing_scan_error(error, article_code, log)
    finally:
        if playwright is not None:
            playwright.stop()


def costing_forbidden_selectors() -> Sequence[str]:
    """Bề mặt testable để audit không có flow nào dùng selector bị cấm."""
    return tuple(sorted(FORBIDDEN_ACTION_SELECTORS))
