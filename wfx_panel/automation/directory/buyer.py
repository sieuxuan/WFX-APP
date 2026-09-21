"""Tìm Buyer và mở đúng link Edit đầu tiên."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _document_changed,
    _first_line,
    _mark_document,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.directory.company_query import _filter_company_rows
from wfx_panel.automation.directory.frames import _buyer_search_frame
from wfx_panel.automation.modules import (
    MODULE_CONTEXT_PROBE_SECONDS,
    _active_wfx_page,
    _click_module_menu_on_page,
)


@dataclass(frozen=True)
class _BuyerEditTarget:
    control: Any
    name: str


def _first_buyer_edit_target(
    frame: Frame,
    query: str,
) -> _BuyerEditTarget | None:
    rows = frame.locator("tr")
    for index in range(rows.count()):
        row = rows.nth(index)
        try:
            if not row.is_visible() or row.locator("#txtCompanyName").count():
                continue
            row_text = " ".join(row.inner_text(timeout=500).split())
            if query.casefold() not in row_text.casefold():
                continue
            edit_links = row.locator('a#lnkEdit, a[id="lnkEdit"]')
            if edit_links.count() and edit_links.first.is_visible():
                return _BuyerEditTarget(edit_links.first, row_text)
        except PlaywrightError:
            continue
    return None


def _open_and_confirm_buyer_edit(
    context: Any,
    page: Page,
    frame: Frame,
    target_info: _BuyerEditTarget,
    log: Callable[[str], None],
) -> bool:
    snapshot = _mark_document(frame, "buyer-list")
    page_count = len(context.pages)
    _write_log(log, f"[BUYER FIND] Đang mở Buyer đầu tiên: {target_info.name}")
    target = target_info.control
    target.evaluate("element => element.click()")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if len(context.pages) > page_count:
            return True
        for candidate in page.frames:
            try:
                if candidate == snapshot[0] and _document_changed(
                    candidate,
                    snapshot,
                ):
                    return True
            except PlaywrightError:
                continue
        try:
            if not target.is_visible():
                return True
        except PlaywrightError:
            return True
        _wait(page, 250)
    return False


@dataclass(frozen=True)
class _BuyerSearchResultRequest:
    context: Any
    page: Page
    frame: Frame
    query: str
    state: Mapping[str, Any]
    log: Callable[[str], None]


def _open_first_matching_buyer(
    request: _BuyerSearchResultRequest,
) -> dict[str, Any]:
    matches = [
        row["company"]
        for row in request.state["rows"]
        if row["matches"]
    ]
    if not matches:
        return _result(
            False,
            "BUYER_NOT_FOUND",
            f"Không tìm thấy Buyer chứa: {request.query}.",
        )
    target = _first_buyer_edit_target(request.frame, request.query)
    if target is None:
        return _result(
            False,
            "BUYER_EDIT_NOT_FOUND",
            "Đã thấy Buyer nhưng không tìm thấy nút Edit.",
        )
    if not _open_and_confirm_buyer_edit(
        request.context,
        request.page,
        request.frame,
        target,
        request.log,
    ):
        return _result(
            False,
            "BUYER_EDIT_NOT_CONFIRMED",
            "WFX chưa xác nhận màn Edit Buyer.",
        )
    return _result(
        True,
        "BUYER_EDIT_OPENED",
        "Đã tìm và mở Edit của Buyer đầu tiên phù hợp.",
        buyer=matches[0],
        matches=matches[:10],
    )


def find_and_open_buyer(
    module_xpath: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _result(False, "QUERY_REQUIRED", "Vui lòng nhập tên Buyer cần tìm.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        frame = _buyer_search_frame(
            page,
            timeout_s=MODULE_CONTEXT_PROBE_SECONDS,
        )
        if frame is None:
            _write_log(
                log,
                "[BUYER FIND] Buyer List chưa mở; đang tự mở List...",
            )
            _click_module_menu_on_page(
                page,
                "Buyer List",
                module_xpath,
                log,
            )
            frame = _buyer_search_frame(page, timeout_s=30)
            if frame is None:
                raise PlaywrightTimeoutError(
                    "Không tìm thấy ô Buyer sau khi app tự mở List."
                )
        frame, state = _filter_company_rows(
            page,
            frame,
            query,
            log,
            "buyer",
        )
        return _open_first_matching_buyer(
            _BuyerSearchResultRequest(
                context=browser.contexts[0],
                page=page,
                frame=frame,
                query=query,
                state=state,
                log=log,
            )
        )
    except PlaywrightTimeoutError as exc:
        return _result(False, "BUYER_SEARCH_NOT_READY", _first_line(exc))
    except Exception as exc:
        boundary = _browser_boundary_result(exc)
        if boundary is not None:
            return boundary
        return _result(False, "BUYER_SEARCH_FAILED", f"{type(exc).__name__}: {_first_line(exc)}")
    finally:
        if playwright is not None:
            playwright.stop()
