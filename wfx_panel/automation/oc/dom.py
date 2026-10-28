"""Tìm link toolbar và đặt option cho dropdown WFX.

``ddlBuyer`` và ``ddlPackage`` chỉ bind đủ option sau ``mousedown``, nên phải
dispatch sự kiện đó, tìm option theo label/title exact rồi xác nhận lại control
sau postback."""

from __future__ import annotations

import re

from wfx_panel.automation._common import (
    Any,
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _wait,
    time,
)
from wfx_panel.automation.runtime import checkpoint

# Alert WFX báo xong việc; mọi alert khác sau một thao tác ghi là WFX từ chối.
_DIALOG_SUCCESS_RE = re.compile(
    r"success|successful|confirmed|rejected|processed|uploaded|saved|updated|created|complete",
    re.IGNORECASE,
)
_DIALOG_FAILURE_RE = re.compile(r"error|fail|invalid", re.IGNORECASE)
# Câu phủ định thắng chữ "confirmed"/"rejected" trong cùng câu:
# "Cannot reject: PO already confirmed" là từ chối, không phải thành công.
_DIALOG_REFUSAL_RE = re.compile(
    r"error|fail|invalid|cannot|can't|unable|not\s+allowed|already|please|"
    r"must|required|mandatory",
    re.IGNORECASE,
)


class _DialogCollector:
    """Nhận và ghi lại mọi hộp thoại WFX trong suốt MỘT thao tác automation.

    Handler chỉ gắn trong lúc click thì bỏ sót alert WFX bắn ra sau postback:
    hộp thoại nằm đó chặn trang, flow chờ tới hết timeout mà không biết WFX
    nói gì. Collector gắn từ trước cú click tới khi thao tác đọc xong kết quả.
    Đây là handler của một thao tác cụ thể (CLAUDE.md: listener chung của
    runtime không được tự accept), và chỉ đóng hộp thoại bằng OK/accept.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []
        self.alerts: list[str] = []
        self._page: Any = None

    def handle(self, dialog: Any) -> None:
        message = " ".join(str(getattr(dialog, "message", "") or "").split())
        self.messages.append(message)
        # confirm() là câu hỏi cho chính thao tác user vừa bấm; alert mới là
        # câu trả lời của WFX.
        if str(getattr(dialog, "type", "alert") or "alert") != "confirm":
            self.alerts.append(message)
        try:
            dialog.accept()
        except Exception:
            # Handler khác của cùng thao tác có thể đã đóng hộp thoại này.
            pass

    def attach(self, page: Any) -> _DialogCollector:
        subscribe = getattr(page, "on", None)
        if callable(subscribe):
            subscribe("dialog", self.handle)
            self._page = page
        return self

    def detach(self) -> None:
        page, self._page = self._page, None
        if page is None:
            return
        try:
            page.remove_listener("dialog", self.handle)
        except Exception:
            pass

    def failure(self) -> str:
        """Alert báo lỗi rõ ràng (error/fail/invalid), rỗng nếu chưa có."""
        return next(
            (m for m in self.messages if _DIALOG_FAILURE_RE.search(m)), ""
        )

    def refusal(self) -> str:
        """Alert không phải thông báo thành công — WFX từ chối thao tác."""
        return next(
            (
                m
                for m in self.alerts
                if m
                and (_DIALOG_REFUSAL_RE.search(m) or not _DIALOG_SUCCESS_RE.search(m))
            ),
            "",
        ) or self.failure()


def _visible_in_frames(
    page: Page,
    selector: str,
    *,
    timeout_s: float = 25,
) -> tuple[Frame, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        checkpoint()
        for frame in page.frames:
            try:
                matches = frame.locator(selector)
                for index in range(matches.count()):
                    candidate = matches.nth(index)
                    if candidate.is_visible() and candidate.is_enabled():
                        return frame, candidate
            except PlaywrightError:
                continue
        _wait(page, 200)
    raise PlaywrightTimeoutError(f"Không tìm thấy control: {selector}")


def _attached_in_frames(
    page: Page,
    selector: str,
    *,
    timeout_s: float = 25,
) -> tuple[Frame, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        checkpoint()
        for frame in page.frames:
            try:
                matches = frame.locator(selector)
                if matches.count():
                    return frame, matches.first
            except PlaywrightError:
                continue
        _wait(page, 200)
    raise PlaywrightTimeoutError(f"Không tìm thấy control: {selector}")


def _toolbar_link(
    page: Page,
    label: str,
    *,
    timeout_s: float = 25,
) -> tuple[Frame, Any]:
    expected = " ".join(label.casefold().split())
    deadline = time.monotonic() + timeout_s
    selectors = (
        "a.ToolLink",
        "a.clsPageToolButton",
        "button",
        "input[type='button']",
        "[role='button']",
    )
    while time.monotonic() < deadline:
        checkpoint()
        for frame in page.frames:
            for selector in selectors:
                try:
                    matches = frame.locator(selector)
                    for index in range(matches.count()):
                        candidate = matches.nth(index)
                        if not candidate.is_visible() or not candidate.is_enabled():
                            continue
                        text = " ".join(
                            str(
                                candidate.get_attribute("value")
                                or candidate.inner_text(timeout=500)
                                or ""
                            )
                            .casefold()
                            .split()
                        )
                        if text == expected or expected in text:
                            return frame, candidate
                except PlaywrightError:
                    continue
        _wait(page, 200)
    raise PlaywrightTimeoutError(f"Không tìm thấy toolbar: {label}")


def _select_exact_option(
    page: Page,
    selector: str,
    value: str,
    label: str,
    field_label: str,
    *,
    timeout_s: float = 30,
) -> str:
    selected_value = ""
    option_seen = False
    last_error = ""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        checkpoint()
        try:
            _frame, select = _visible_in_frames(page, selector, timeout_s=3)
            # WFX chỉ bind đủ Buyer/Package trong handler onmousedown.
            select.dispatch_event("mousedown", timeout=2_000)
            options = select.locator("option")
            for index in range(options.count()):
                option = options.nth(index)
                option_value = str(option.get_attribute("value") or "")
                option_label = " ".join((option.inner_text() or "").split())
                option_title = " ".join(
                    (option.get_attribute("title") or "").split()
                )
                if (
                    (value and option_value == value)
                    or option_label.casefold() == label.casefold()
                    or option_title.casefold() == label.casefold()
                ):
                    selected_value = option_value
                    option_seen = True
                    break
            if selected_value:
                if select.input_value(timeout=1_000) == selected_value:
                    return selected_value
                try:
                    select.select_option(value=selected_value, timeout=5_000)
                except PlaywrightError as error:
                    last_error = _first_line(error)
                    message = str(error).casefold()
                    if not any(
                        marker in message
                        for marker in (
                            "frame was detached",
                            "execution context was destroyed",
                            "target page, context or browser has been closed",
                        )
                    ):
                        raise
                _wait(page, 300)
        except PlaywrightError:
            selected_value = ""
        _wait(page, 200)
    if not option_seen:
        raise PlaywrightTimeoutError(
            f"{field_label} không có lựa chọn '{label}'."
        )
    suffix = f" Lỗi gần nhất: {last_error}" if last_error else ""
    raise PlaywrightTimeoutError(
        f"WFX chưa xác nhận {field_label}='{label}'.{suffix}"
    )
