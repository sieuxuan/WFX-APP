"""Confirm tuần tự theo Style và Reject All trên tab đang mở."""

from __future__ import annotations

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _first_line,
    _result,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.oc.constants import (
    _ACTIVE_CONFIRM_TAB_JS,
    _CONFIRM_GROUPS_JS,
    _MARK_CONFIRM_STYLE_JS,
    _PREPARE_REVISION_STYLE_JS,
    CONFIRM_FIRST_PASS_TIMEOUT_SECONDS,
    CONFIRM_GRID_SELECTOR,
    CONFIRM_PAGE_SIZE_SELECTOR,
    CONFIRM_PROCESS_TIMEOUT_SECONDS,
    CONFIRM_TAB_SELECTORS,
    EDI_MENU_SELECTOR,
)
from wfx_panel.automation.oc.dom import (
    _attached_in_frames,
    _toolbar_link,
    _visible_in_frames,
)
from wfx_panel.automation.runtime import cancellation_deferred, checkpoint


def _read_confirm_styles(frame: Frame) -> list[dict[str, Any]]:
    rows = frame.evaluate(_CONFIRM_GROUPS_JS)
    return [dict(row) for row in rows if isinstance(row, dict) and row.get("key")]


def _focus_confirm_grid(page: Page, frame: Frame) -> None:
    for owner in (frame, page):
        try:
            focus = owner.locator("#gridEDIBuyerPO_divFocus")
            if focus.count() and focus.first.is_visible():
                focus.first.click(timeout=2_000)
                return
        except PlaywrightError:
            continue


def _prepare_revision_style(frame: Frame, style_key: str) -> dict[str, Any]:
    prepared = frame.evaluate(_PREPARE_REVISION_STYLE_JS, style_key)
    if not isinstance(prepared, dict):
        return {"ok": False, "reason": "style-changed"}
    return dict(prepared)


def _select_confirm_style(frame: Frame, style_key: str) -> None:
    marked = frame.evaluate(_MARK_CONFIRM_STYLE_JS, style_key)
    if not isinstance(marked, dict) or not marked.get("ok"):
        raise PlaywrightTimeoutError("Style đã thay đổi trước khi chọn Confirm.")
    controls = frame.locator(
        '[data-wfx-oc-confirm-row="1"] #colSelector '
        'input[type="radio"], '
        '[data-wfx-oc-confirm-row="1"] #colSelector '
        'input[type="checkbox"]'
    )
    if not controls.count():
        raise PlaywrightTimeoutError("Không tìm thấy ô chọn của Style.")
    control = controls.first
    try:
        if not control.is_checked():
            control.check(timeout=5_000)
    except PlaywrightError:
        control.click(timeout=5_000)


def _click_confirm_toolbar(page: Page) -> None:
    selector = (
        "#sectionEDIBuyerPO > tbody > tr > td:nth-child(2) "
        "> span > div:nth-child(3) > a"
    )
    try:
        _frame, confirm = _visible_in_frames(page, selector, timeout_s=3)
    except PlaywrightTimeoutError:
        _frame, confirm = _toolbar_link(page, "Confirm", timeout_s=12)
    _click(confirm)


def _click_reject_toolbar(page: Page) -> None:
    selector = (
        "#sectionEDIBuyerPO > tbody > tr > td:nth-child(2) "
        "> span > div:nth-child(5) > a"
    )
    try:
        _frame, reject = _visible_in_frames(page, selector, timeout_s=3)
    except PlaywrightTimeoutError:
        _frame, reject = _toolbar_link(page, "Reject", timeout_s=12)

    def accept_reject_dialog(dialog: Any) -> None:
        dialog.accept()

    page.on("dialog", accept_reject_dialog)
    try:
        _click(reject)
    finally:
        try:
            page.remove_listener("dialog", accept_reject_dialog)
        except Exception:
            pass


def _active_confirm_mode(page: Page) -> str:
    detected: set[str] = set()
    for frame in page.frames:
        try:
            mode = str(frame.evaluate(_ACTIVE_CONFIRM_TAB_JS) or "")
        except PlaywrightError:
            continue
        if mode in CONFIRM_TAB_SELECTORS:
            detected.add(mode)
    if len(detected) == 1:
        return detected.pop()
    raise PlaywrightTimeoutError(
        "Hãy mở đúng tab New hoặc Revision trên EDI Buyer PO trước khi Reject All."
    )


def _confirm_frame(page: Page, *, timeout_s: float = 12) -> Frame:
    try:
        frame, _grid = _attached_in_frames(
            page,
            CONFIRM_GRID_SELECTOR,
            timeout_s=min(timeout_s, 4),
        )
        return frame
    except PlaywrightTimeoutError:
        frame, _grid = _attached_in_frames(
            page,
            "#gridEDIBuyerPO_divFocus",
            timeout_s=timeout_s,
        )
        return frame


def _wait_style_processed(
    page: Page,
    frame: Frame,
    style_key: str,
    *,
    timeout_s: float,
) -> bool:
    deadline = time.monotonic() + timeout_s
    absent_since: float | None = None
    current_frame = frame
    while time.monotonic() < deadline:
        checkpoint()
        try:
            styles = _read_confirm_styles(current_frame)
            loading = current_frame.locator(
                ".loading, .clsLoading, [class*='loading' i], "
                "[id*='progress' i]"
            )
            visible_loading = any(
                loading.nth(index).is_visible()
                for index in range(min(loading.count(), 20))
            )
            still_present = any(style["key"] == style_key for style in styles)
            if not visible_loading and not still_present:
                if absent_since is None:
                    absent_since = time.monotonic()
                elif time.monotonic() - absent_since >= 1:
                    return True
            else:
                absent_since = None
        except PlaywrightError:
            absent_since = None
            try:
                current_frame = _confirm_frame(page, timeout_s=2)
            except PlaywrightTimeoutError:
                pass
        _wait(page, 200)
    return False


def _wait_confirm_grid_ready(
    page: Page,
    frame: Frame,
    *,
    timeout_s: float = 30,
) -> Frame:
    """Đợi grid hết lớp chặn sau postback đổi page size của WFX."""
    deadline = time.monotonic() + timeout_s
    empty_since: float | None = None
    current_frame = frame
    controls_selector = (
        f"{CONFIRM_GRID_SELECTOR} #colSelector input[type='radio'], "
        f"{CONFIRM_GRID_SELECTOR} #colSelector input[type='checkbox']"
    )
    while time.monotonic() < deadline:
        checkpoint()
        try:
            loading = current_frame.locator(
                "#gridEDIBuyerPO_divGridLoading, .loading, .clsLoading, "
                "[class*='loading' i], [id*='progress' i]"
            )
            visible_loading = any(
                loading.nth(index).is_visible()
                for index in range(min(loading.count(), 20))
            )
            controls = current_frame.locator(controls_selector)
            if not visible_loading and controls.count():
                try:
                    controls.first.check(timeout=500, trial=True)
                except PlaywrightError:
                    empty_since = None
                else:
                    return current_frame
            elif not visible_loading and current_frame.locator(
                CONFIRM_GRID_SELECTOR
            ).count():
                if empty_since is None:
                    empty_since = time.monotonic()
                elif time.monotonic() - empty_since >= 1:
                    return current_frame
            else:
                empty_since = None
        except PlaywrightError:
            empty_since = None
            try:
                current_frame = _confirm_frame(page, timeout_s=2)
            except PlaywrightTimeoutError:
                pass
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        "Grid EDI Buyer PO vẫn đang tải sau khi đổi số dòng hiển thị."
    )


def _set_confirm_page_size(page: Page) -> Frame:
    frame, select = _visible_in_frames(
        page,
        CONFIRM_PAGE_SIZE_SELECTOR,
        timeout_s=25,
    )
    try:
        current = str(select.input_value(timeout=1_000) or "").strip()
    except PlaywrightError:
        current = ""
    if current != "100":
        try:
            select.select_option(label="100", timeout=5_000)
        except PlaywrightError:
            select.select_option(value="100", timeout=5_000)
        _wait(page, 500)
        frame, select = _visible_in_frames(
            page,
            CONFIRM_PAGE_SIZE_SELECTOR,
            timeout_s=25,
        )
    selected = str(select.input_value(timeout=1_000) or "").strip()
    if selected != "100":
        option = select.locator("option:checked")
        label = " ".join((option.first.inner_text() or "").split()) if option.count() else ""
        if label != "100":
            raise PlaywrightTimeoutError("Không đổi được số dòng hiển thị thành 100.")
    return _wait_confirm_grid_ready(page, frame)


def _open_confirm_grid(
    page: Page,
    mode: str,
    log: Callable[[str], None],
) -> Frame:
    tab_selector = CONFIRM_TAB_SELECTORS[mode]
    try:
        _frame, tab = _visible_in_frames(page, tab_selector, timeout_s=2)
    except PlaywrightTimeoutError:
        try:
            _menu_frame, menu = _visible_in_frames(page, EDI_MENU_SELECTOR, timeout_s=12)
        except PlaywrightTimeoutError:
            _menu_frame, menu = _attached_in_frames(page, EDI_MENU_SELECTOR, timeout_s=12)
        _click(menu)
        _frame, tab = _visible_in_frames(page, tab_selector, timeout_s=30)
    _click(tab)
    label = "Revision" if mode == "revision" else "New"
    _write_log(log, f"[OC CONFIRM] Đã mở tab {label}")
    frame = _set_confirm_page_size(page)
    _write_log(log, "[OC CONFIRM] Đã đổi số dòng hiển thị thành 100")
    return frame


def _confirm_all_pending(
    page: Page,
    frame: Frame,
    mode: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    confirmed_styles = 0
    selected_sales_orders = 0
    while True:
        checkpoint()
        styles = _read_confirm_styles(frame)
        if not styles:
            return _result(
                True,
                "OC_FAST_CONFIRM_COMPLETED",
                (
                    f"Đã Confirm xong {confirmed_styles} Style."
                    if confirmed_styles
                    else "Không còn Style chờ Confirm."
                ),
                mode=mode,
                confirmed_styles=confirmed_styles,
                selected_sales_orders=selected_sales_orders,
                confirmation_submitted=confirmed_styles > 0,
            )
        style = styles[0]
        style_key = str(style["key"])
        style_label = str(style.get("label") or style_key)
        _write_log(
            log,
            f"[OC CONFIRM] Đang xử lý Style {style_label} "
            f"({confirmed_styles + 1})",
        )
        _focus_confirm_grid(page, frame)
        if mode == "revision":
            prepared = _prepare_revision_style(frame, style_key)
            if not prepared.get("ok"):
                if prepared.get("reason") == "multiple-sales-orders":
                    options = list(prepared.get("options") or ())
                    return _result(
                        False,
                        "OC_FAST_CONFIRM_MULTIPLE_SALES_ORDERS",
                        f"Style {style_label} có nhiều WFX Sales Order. "
                        "Hãy chọn thủ công rồi chạy lại Confirm nhanh.",
                        mode=mode,
                        confirmed_styles=confirmed_styles,
                        selected_sales_orders=selected_sales_orders,
                        stopped_style=style_label,
                        stopped_row=prepared.get("row_number"),
                        sales_order_options=options,
                        confirmation_submitted=confirmed_styles > 0,
                    )
                raise PlaywrightTimeoutError(
                    "Style đã thay đổi khi chuẩn bị WFX Sales Order."
                )
            selected_sales_orders += int(prepared.get("selected_count") or 0)

        confirmation_submitted = False
        try:
            with cancellation_deferred():
                processed = False
                for attempt in range(2):
                    _select_confirm_style(frame, style_key)
                    confirmation_submitted = True
                    _click_confirm_toolbar(page)
                    _write_log(
                        log,
                        f"[OC CONFIRM] Đã bấm Confirm lượt {attempt + 1} "
                        f"cho {style_label}",
                    )
                    processed = _wait_style_processed(
                        page,
                        frame,
                        style_key,
                        timeout_s=(
                            CONFIRM_FIRST_PASS_TIMEOUT_SECONDS
                            if attempt == 0
                            else CONFIRM_PROCESS_TIMEOUT_SECONDS
                        ),
                    )
                    if processed:
                        break
                if not processed:
                    return _result(
                        False,
                        "OC_FAST_CONFIRM_PROCESS_TIMEOUT",
                        f"Style {style_label} chưa process xong sau khi Confirm. "
                        "App đã dừng trước Style tiếp theo.",
                        mode=mode,
                        confirmed_styles=confirmed_styles,
                        selected_sales_orders=selected_sales_orders,
                        stopped_style=style_label,
                        confirmation_submitted=True,
                    )
        except Exception as error:
            if confirmation_submitted:
                return _result(
                    False,
                    "OC_FAST_CONFIRM_UNCONFIRMED",
                    f"Đã bấm Confirm cho Style {style_label} nhưng không đọc được "
                    "kết quả. App không tự chạy lại để tránh Confirm nhầm Style.",
                    mode=mode,
                    confirmed_styles=confirmed_styles,
                    selected_sales_orders=selected_sales_orders,
                    stopped_style=style_label,
                    confirmation_submitted=True,
                    errors=[f"{type(error).__name__}: {_first_line(error)}"],
                )
            raise
        confirmed_styles += 1
        _write_log(log, f"[OC CONFIRM] Style {style_label} đã process xong")


def _reject_all_pending(
    page: Page,
    frame: Frame,
    mode: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    rejected_rows = 0
    while True:
        checkpoint()
        pending = _read_confirm_styles(frame)
        if not pending:
            return _result(
                True,
                "OC_REJECT_ALL_COMPLETED",
                (
                    f"Đã Reject xong {rejected_rows} PO."
                    if rejected_rows
                    else "Không còn PO chờ Reject trong tab đang mở."
                ),
                mode=mode,
                rejected_rows=rejected_rows,
                rejection_submitted=rejected_rows > 0,
            )
        row = pending[0]
        row_key = str(row["key"])
        row_label = str(row.get("label") or row_key)
        _write_log(
            log,
            f"[OC REJECT] Đang Reject {row_label} ({rejected_rows + 1})",
        )
        rejection_submitted = False
        try:
            with cancellation_deferred():
                _focus_confirm_grid(page, frame)
                _select_confirm_style(frame, row_key)
                rejection_submitted = True
                _click_reject_toolbar(page)
                _write_log(log, f"[OC REJECT] Đã bấm Reject cho {row_label}")
                processed = _wait_style_processed(
                    page,
                    frame,
                    row_key,
                    timeout_s=CONFIRM_PROCESS_TIMEOUT_SECONDS,
                )
                if not processed:
                    return _result(
                        False,
                        "OC_REJECT_ALL_PROCESS_TIMEOUT",
                        f"PO {row_label} chưa rời khỏi tab sau khi Reject. "
                        "App đã dừng trước PO tiếp theo.",
                        mode=mode,
                        rejected_rows=rejected_rows,
                        stopped_row=row_label,
                        rejection_submitted=True,
                    )
        except Exception as error:
            if rejection_submitted:
                return _result(
                    False,
                    "OC_REJECT_ALL_UNCONFIRMED",
                    f"Đã bấm Reject cho {row_label} nhưng chưa đọc được kết quả. "
                    "App không tự chạy lại để tránh Reject nhầm PO.",
                    mode=mode,
                    rejected_rows=rejected_rows,
                    stopped_row=row_label,
                    rejection_submitted=True,
                    errors=[f"{type(error).__name__}: {_first_line(error)}"],
                )
            raise
        rejected_rows += 1
        _write_log(log, f"[OC REJECT] {row_label} đã được xử lý xong")
