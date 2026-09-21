"""Chọn dòng và bấm Create Transaction.

Đây là ranh giới KHÔNG idempotent: đã click mà không đọc được xác nhận thì trả
``OC_TRANSACTION_UNCONFIRMED`` và tuyệt đối không tự retry."""

from __future__ import annotations

import re

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.oc.dom import _toolbar_link
from wfx_panel.automation.runtime import cancellation_deferred, checkpoint


def _click_pending_transaction(page: Page) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        checkpoint()
        for frame in page.frames:
            try:
                links = frame.locator("a")
                for index in range(links.count()):
                    link = links.nth(index)
                    if not link.is_visible() or not link.is_enabled():
                        continue
                    if " ".join((link.inner_text() or "").casefold().split()) == "pending":
                        _click(link)
                        return
            except PlaywrightError:
                continue
        _wait(page, 250)
    raise PlaywrightTimeoutError("Không tìm thấy Pending ở Transaction Detail.")


def _transaction_checkboxes(frame: Frame) -> list[Any]:
    candidates: list[Any] = []
    try:
        checkboxes = frame.locator("input[type='checkbox']")
        for index in range(checkboxes.count()):
            checkbox = checkboxes.nth(index)
            if not checkbox.is_visible() or not checkbox.is_enabled():
                continue
            try:
                row_text = " ".join(
                    (checkbox.locator("xpath=ancestor::tr[1]").inner_text() or "").split()
                )
            except PlaywrightError:
                row_text = ""
            if re.search(r"select\s+all|all\s+records", row_text, re.I):
                continue
            candidates.append(checkbox)
    except PlaywrightError:
        pass
    return candidates


def _select_first_transaction(page: Page, *, force: bool = False) -> None:
    toolbar_frame, _create_link = _toolbar_link(
        page, "Create Transaction", timeout_s=30
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        checkpoint()
        frames: list[Frame] = [toolbar_frame]
        frames.extend(frame for frame in page.frames if frame is not toolbar_frame)
        for frame in frames:
            candidates = _transaction_checkboxes(frame)
            if not candidates:
                continue
            checkbox = candidates[0]
            try:
                if force and checkbox.is_checked():
                    checkbox.uncheck(timeout=3_000)
                    _wait(page, 150)
                if not checkbox.is_checked():
                    checkbox.check(timeout=5_000)
                if not checkbox.is_checked():
                    checkbox.click(timeout=5_000)
                if checkbox.is_checked():
                    # WFX updates its selected-record state asynchronously after
                    # the native checkbox event. Do not click Create Transaction
                    # in the same tick as the selection.
                    _wait(page, 350)
                    if checkbox.is_checked():
                        return
            except PlaywrightError:
                continue
        _wait(page, 250)
    raise PlaywrightTimeoutError(
        "Không tìm thấy hoặc không xác nhận được checkbox đơn hàng để tạo transaction."
    )


SUCCESS_BANNER_SELECTOR = (
    "#lblSuccessMsg, .success, .clsSuccess, "
    "[class*='success' i], [id*='success' i]"
)


_TRANSACTION_SUCCESS_RE = re.compile(r"success|created|complete", re.IGNORECASE)


_NO_RECORD_SELECTED_RE = re.compile(r"no\s+record\s+selected", re.IGNORECASE)


class _CreateTransactionDialogs:
    """Gom alert WFX bắn ra trong lúc chờ xác nhận Create Transaction.

    ``No Record Selected`` là bằng chứng KHÔNG có transaction nào được gửi, nên
    chỉ khi thấy nó mới được phép chọn lại dòng và bấm lần hai.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []
        self.saw_no_record = False

    def accept(self, dialog: Any) -> None:
        message = " ".join(str(dialog.message or "").split())
        self.messages.append(message)
        if _NO_RECORD_SELECTED_RE.search(message):
            self.saw_no_record = True
        dialog.accept()

    @property
    def reports_success(self) -> bool:
        return any(_TRANSACTION_SUCCESS_RE.search(m) for m in self.messages)


def _success_banner_text(page: Page) -> str:
    """Nội dung banner thành công đang hiển thị, rỗng nếu chưa có."""
    for frame in page.frames:
        try:
            banners = frame.locator(SUCCESS_BANNER_SELECTOR)
            for index in range(banners.count()):
                text = " ".join((banners.nth(index).text_content() or "").split())
                if text and _TRANSACTION_SUCCESS_RE.search(text):
                    return text
        except PlaywrightError:
            continue
    return ""


def _wait_transaction_confirmed(
    page: Page, dialogs: _CreateTransactionDialogs, timeout_s: float = 35
) -> tuple[bool, list[str]]:
    """Chờ WFX xác nhận, trả (đã thành công, các message đọc được).

    Không cho Stop ngắt đoạn này: Create Transaction không idempotent nên mất
    xác nhận phải được caller coi là unconfirmed chứ không phải thất bại.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        checkpoint()
        if dialogs.saw_no_record:
            return False, dialogs.messages
        if dialogs.reports_success:
            return True, dialogs.messages
        banner = _success_banner_text(page)
        if banner:
            return True, dialogs.messages + [banner]
        _wait(page, 300)
    return False, dialogs.messages


def _create_transaction(page: Page, log: Callable[[str], None]) -> tuple[bool, list[str]]:
    for attempt in range(2):
        # Chọn lại trước khi bấm là an toàn và đóng được khe hở khi WFX đã render
        # toolbar nhưng chưa bind selection.
        _select_first_transaction(page, force=attempt > 0)
        _frame, create_link = _toolbar_link(page, "Create Transaction", timeout_s=10)
        dialogs = _CreateTransactionDialogs()
        page.on("dialog", dialogs.accept)
        try:
            with cancellation_deferred():
                _click(create_link)
                _write_log(log, "[OC EDI] Đã gửi Create Transaction")
                confirmed, messages = _wait_transaction_confirmed(page, dialogs)
            if confirmed:
                return True, messages
            if not dialogs.saw_no_record or attempt > 0:
                return False, messages
            _write_log(
                log,
                "[OC EDI] WFX chưa nhận dòng đã chọn; chọn lại và thử Create Transaction một lần.",
            )
            _wait(page, 500)
        finally:
            try:
                page.remove_listener("dialog", dialogs.accept)
            except Exception:
                pass
    return False, []
