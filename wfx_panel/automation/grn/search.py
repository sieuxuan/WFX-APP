"""Tìm GRN theo Invoice hoặc RMPO và mở đúng dòng.

Bảng kết quả có hai hàng header. Không click link No. vì nó gọi ReOrder;
phải click link GRN của dòng dữ liệu có onclick PrintGRN, và chỉ báo thành
công sau khi popup GRN đã thực sự mở."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _click,
    _document_changed,
    _first_line,
    _first_visible,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.grn.constants import (
    _GRN_DATE_CHECKBOX,
    _GRN_SEARCH_CONTEXT,
    _GRN_SEARCH_FILTERS,
    GRN_SEARCH_XPATH,
)
from wfx_panel.automation.grn.frames import (
    _context_frames,
    _fold,
    _open_menu_form,
    _snapshot_context,
)
from wfx_panel.automation.modules import _active_wfx_page


def _set_grn_search_filter(
    frame: Frame,
    filter_kind: str,
    value: str,
    *,
    enabled: bool,
) -> None:
    """Điều khiển đúng checkbox + input Document No./Order No. của WFX."""
    checkbox_selector, field_selector = _GRN_SEARCH_FILTERS[filter_kind]
    checkbox = frame.locator(checkbox_selector).first
    field = frame.locator(field_selector).first
    checkbox.wait_for(state="visible", timeout=8_000)
    field.wait_for(state="visible", timeout=8_000)
    # WFX onchange gọi ChkIt(field, checkboxId, false). Click checkbox khi ô
    # còn trống sẽ bị ChkIt đổi ngược về false, khiến Playwright.check() lỗi.
    # Vì vậy luôn điền trước rồi phát change để chính WFX đồng bộ checkbox.
    field.fill(value)
    field.dispatch_event("change")
    if field.input_value(timeout=1_000) != value:
        raise PlaywrightTimeoutError("WFX chưa xác nhận điều kiện tìm GRN.")
    if checkbox.is_checked(timeout=1_000) is not enabled:
        raise PlaywrightTimeoutError(
            "WFX chưa đồng bộ checkbox điều kiện tìm GRN."
        )


def _click_grn_search(frame: Frame) -> None:
    """Click đúng input Search trong #ctrlRpt > table, không dùng số dòng."""
    report = _first_visible(frame.locator("#ctrlRpt"))
    if report is None:
        raise PlaywrightTimeoutError("Không tìm thấy vùng tìm kiếm GRN #ctrlRpt.")
    button = _first_visible(
        report.locator(
            ":scope > table input[type='button'][value='Search' i], "
            "table input[type='button'][value='Search' i]"
        )
    )
    if button is None:
        raise PlaywrightTimeoutError("Không tìm thấy nút Search trong #ctrlRpt.")
    _click(button)


def _wait_grn_result_opened(
    context: Any,
    page_ids: set[int],
    snapshots: dict[int, tuple[Frame | None, str]],
    *,
    timeout_s: float = 25,
) -> None:
    """Xác nhận popup/document mới sau exact link PrintGRN."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in _context_frames(context):
            snapshot = snapshots.get(id(frame))
            is_new_page = id(frame.page) not in page_ids
            changed = snapshot is None or _document_changed(frame, snapshot)
            url = str(frame.url or "").strip().casefold()
            if not changed or (is_new_page and url in {"", "about:blank"}):
                continue
            try:
                frame.page.bring_to_front()
            except PlaywrightError:
                pass
            return
        frames = _context_frames(context)
        _wait(frames[0] if frames else context.pages[0], 150)
    raise PlaywrightTimeoutError(
        "Đã bấm số GRN nhưng WFX chưa mở cửa sổ GRN."
    )


def search_grn_receipt(
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Tìm GRN theo Invoice/RMPO, bỏ Date và mở cột No. đầu tiên."""
    filter_kind = str(filter_kind or "").strip().casefold()
    query = " ".join(str(query or "").split())
    if filter_kind not in {"invoice", "rmpo"}:
        return _result(False, "INVALID_FILTER", "Kiểu tìm GRN không hợp lệ.")
    if not query:
        label = "Số Invoice" if filter_kind == "invoice" else "RMPO No."
        return _result(False, "QUERY_REQUIRED", f"Vui lòng nhập {label}.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        frame = _open_menu_form(
            context,
            page,
            GRN_SEARCH_XPATH,
            _GRN_SEARCH_CONTEXT,
            "GRN Search",
            log,
        )
        # Xóa và bỏ chọn điều kiện cũ để Invoice/RMPO không âm thầm kết hợp.
        for kind in _GRN_SEARCH_FILTERS:
            try:
                _set_grn_search_filter(frame, kind, "", enabled=False)
            except PlaywrightError:
                continue
        _set_grn_search_filter(frame, filter_kind, query, enabled=True)
        date_checkbox = frame.locator(_GRN_DATE_CHECKBOX).first
        date_checkbox.wait_for(state="attached", timeout=8_000)
        date_enabled = date_checkbox.evaluate(
            "element => { if (element.checked) element.click(); return element.checked; }"
        )
        if date_enabled:
            raise PlaywrightTimeoutError("Chưa bỏ tích Date khi tìm GRN.")
        _write_log(log, "[GRN SEARCH] Đã bỏ tích Date.")
        _click_grn_search(frame)
        deadline = time.monotonic() + 35
        result_link = None
        result_frame = None
        while time.monotonic() < deadline:
            for candidate in _context_frames(context):
                try:
                    link = _first_visible(
                        candidate.locator(
                            "table.clsTable tr.clsDataLabel "
                            "a[onclick*='PrintGRN(']"
                        )
                    )
                    if link is not None:
                        result_link = link
                        result_frame = candidate
                        break
                except PlaywrightError:
                    continue
            if result_link is not None:
                break
            frames = _context_frames(context)
            _wait(frames[0] if frames else page, 150)
        if result_link is None or result_frame is None:
            return _result(
                False,
                "GRN_SEARCH_NO_RESULTS",
                "Không tìm thấy GRN phù hợp.",
            )
        try:
            result_row = result_link.locator("xpath=ancestor::tr[1]").first
            row_text = " ".join((result_row.inner_text(timeout=1_000) or "").split())
            if _fold(query) not in _fold(row_text):
                _write_log(
                    log,
                    "[GRN SEARCH] Dòng đầu không hiển thị lại điều kiện; "
                    "vẫn mở đúng cột No. theo kết quả WFX.",
                )
        except PlaywrightError:
            pass
        page_ids, snapshots = _snapshot_context(context, "grn-search-result")
        _click(result_link)
        _wait_grn_result_opened(context, page_ids, snapshots)
        _write_log(
            log,
            "[GRN SEARCH] Đã click đúng link PrintGRN và xác nhận cửa sổ GRN mở.",
        )
        return _result(
            True,
            "GRN_SEARCH_OPENED",
            "Đã mở GRN phù hợp trên WFX.",
            filter_kind=filter_kind,
        )
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module="(GRN) Nhập kho")
        if boundary is not None:
            return boundary
        message = f"Chưa tìm được GRN: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "GRN_SEARCH_FAILED", message, module="(GRN) Nhập kho")
    finally:
        if playwright is not None:
            playwright.stop()
