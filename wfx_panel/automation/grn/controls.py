"""Đặt giá trị control và đọc option trên form GRN."""

from __future__ import annotations

from collections.abc import Callable

from wfx_panel.automation._common import (
    Frame,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _first_visible,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.grn.constants import _CONTROL_OPTIONS_JS, _SELECT_PO_ROW_JS
from wfx_panel.automation.sale_asn_create import _set_control


def _set_exact(
    frame: Frame,
    selector: str,
    value: str,
    field_label: str,
    log: Callable[[str], None],
    *,
    timeout_s: float = 20,
) -> None:
    selected = _set_control(
        frame,
        selector,
        value,
        "exact",
        timeout_s=timeout_s,
    )
    if not selected.get("ok"):
        raise PlaywrightTimeoutError(
            f"Không chọn được {field_label}: {selected.get('reason') or 'unknown'}"
        )
    _write_log(log, f"[GRN] Đã chọn {field_label}.")


def _click_action(frame: Frame, selector: str, label: str) -> None:
    container = _first_visible(frame.locator(selector))
    if container is None:
        raise PlaywrightTimeoutError(f"Không tìm thấy nút {label}.")
    action = _first_visible(
        container.locator('a, button, input[type="button"], [onclick]')
    )
    _click(action or container)


def _read_control_options(
    frame: Frame,
    selector: str,
    *,
    timeout_s: float = 15,
) -> list[str]:
    deadline = time.monotonic() + timeout_s
    opened = False
    while time.monotonic() < deadline:
        try:
            raw = frame.evaluate(
                _CONTROL_OPTIONS_JS,
                {"selector": selector, "open": not opened},
            )
            opened = True
            options = [
                " ".join(str(item or "").split())
                for item in raw or []
                if str(item or "").strip()
            ]
            if options:
                return list(dict.fromkeys(options))
        except PlaywrightError:
            pass
        _wait(frame, 150)
    return []


def _select_po_row(frame: Frame, section_selector: str, rmpo_no: str) -> None:
    section = _first_visible(frame.locator(section_selector))
    if section is None:
        raise PlaywrightTimeoutError(
            f"Không tìm thấy bảng {section_selector}."
        )
    selected = section.evaluate(_SELECT_PO_ROW_JS, rmpo_no)
    if not selected.get("ok"):
        raise PlaywrightTimeoutError(
            "Không chọn được đúng RMPO trong bảng; "
            f"reason={selected.get('reason')}; count={selected.get('count', 0)}"
        )


def _select_imported(frame: Frame, log: Callable[[str], None]) -> None:
    host = _first_visible(
        frame.locator("#CellID14 > div:nth-child(2), #CellID14")
    )
    if host is None:
        raise PlaywrightTimeoutError("Không tìm thấy lựa chọn Imported.")
    state = host.evaluate(
        """host => {
            const checkbox = host.matches('input[type="checkbox"]')
                ? host : host.querySelector('input[type="checkbox"]');
            if (checkbox) {
                if (!checkbox.checked) checkbox.click();
                return Boolean(checkbox.checked);
            }
            const action = host.querySelector(
                'input, button, a, .lblEditable, span, [onclick]'
            ) || host;
            action.click();
            return true;
        }"""
    )
    if not state:
        raise PlaywrightTimeoutError("WFX chưa xác nhận Imported.")
    _write_log(log, "[GRN] Đã chọn Imported.")


def _wait_loading_finished(frame: Frame, timeout_s: float = 25) -> None:
    deadline = time.monotonic() + timeout_s
    stable_since = 0.0
    while time.monotonic() < deadline:
        try:
            loading = frame.locator(
                ".ag-overlay-loading-wrapper, .ag-loading, .loading, "
                ".loader, [aria-busy='true']"
            )
            busy = any(
                loading.nth(index).is_visible()
                for index in range(loading.count())
            )
        except PlaywrightError:
            busy = True
        now = time.monotonic()
        if busy:
            stable_since = 0.0
        elif stable_since <= 0:
            stable_since = now
        elif now - stable_since >= 0.8:
            return
        _wait(frame, 150)
    raise PlaywrightTimeoutError("Kết quả GRN chưa tải xong.")
