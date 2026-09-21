"""Tìm link toolbar và đặt option cho dropdown WFX.

``ddlBuyer`` và ``ddlPackage`` chỉ bind đủ option sau ``mousedown``, nên phải
dispatch sự kiện đó, tìm option theo label/title exact rồi xác nhận lại control
sau postback."""

from __future__ import annotations

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
