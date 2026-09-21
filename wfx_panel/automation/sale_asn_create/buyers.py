"""Quét và chọn Buyer trên form Sale ASN New."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules import _active_wfx_page
from wfx_panel.automation.sale_asn_create.form import (
    _open_new_form,
    _refresh_existing_new_form,
    _set_control,
)
from wfx_panel.automation.sale_asn_create.values import _fold

_BUYER_OPTIONS_JS = r"""cell => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const visible = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        return style.display !== 'none' && style.visibility !== 'hidden';
    };
    const controls = [
        ...cell.querySelectorAll('select'),
        ...document.querySelectorAll('select:focus, select.clsCombo'),
    ];
    for (const control of controls) {
        const options = [...control.options].map(option => ({
            label: clean(option.textContent), value: clean(option.value),
            disabled: option.disabled,
        })).filter(option => option.label && option.value && !option.disabled
            && !/^\[?select\]?$/i.test(option.label));
        if (options.length) return options;
    }
    const listItems = [...document.querySelectorAll(
        '[role="option"], .select2-results__option, li.clsMultiSelectContent'
    )].filter(visible).map(item => ({
        label: clean(item.textContent), value: clean(item.getAttribute('data-value')),
    })).filter(option => option.label);
    return listItems;
}"""


def _buyer_cell(frame: Frame) -> Any:
    cell = frame.locator("#Cell_Buyer").first
    cell.wait_for(state="visible", timeout=8_000)
    return cell


def _normalise_buyer_options(raw: Sequence[dict] | None) -> list[dict[str, str]]:
    """Chuẩn hóa danh sách Buyer và bỏ option placeholder/trùng tên."""

    seen: set[str] = set()
    options: list[dict[str, str]] = []
    for item in raw or []:
        label = " ".join(str(item.get("label") or "").split())
        value = str(item.get("value") or "").strip()
        identity = label.casefold()
        if label and value and identity not in seen:
            seen.add(identity)
            options.append({"label": label, "value": value})
    return options


def _buyer_options(frame: Frame, timeout_s: float = 15) -> list[dict[str, str]]:
    """Chờ dropdown Buyer lazy-bind rồi đọc option thật từ ``#ddlBuyer``.

    WFX render ``#Cell_Buyer`` và ``[Select]`` trước, sau đó mới bind danh sách
    qua request nền. Vì vậy sự xuất hiện của cell chưa đồng nghĩa dropdown đã
    sẵn sàng. Chỉ mở Select2 khi đã chờ một nhịp mà native select vẫn trống.
    """

    cell = _buyer_cell(frame)
    deadline = time.monotonic() + timeout_s
    # Mở dropdown sớm để kích hoạt lazy-bind Buyer của WFX; chờ 1,5 giây như
    # trước làm mỗi lượt bắt đầu chậm thêm dù popup đã sẵn sàng nhận click.
    open_after = time.monotonic() + min(0.5, timeout_s / 2)
    dropdown_opened = False
    while time.monotonic() < deadline:
        options = _normalise_buyer_options(cell.evaluate(_BUYER_OPTIONS_JS) or [])
        if options:
            return options
        if not dropdown_opened and time.monotonic() >= open_after:
            try:
                cell.locator(".select2-selection").first.click(timeout=2_000)
            except PlaywrightError:
                try:
                    cell.locator("select#ddlBuyer, select").first.click(timeout=2_000)
                except PlaywrightError:
                    pass
            dropdown_opened = True
        _wait(frame, 150)
    return []


def _select_buyer(frame: Frame, buyer: str) -> None:
    options = _buyer_options(frame)
    exact = [item for item in options if _fold(item["label"]) == _fold(buyer)]
    if len(exact) != 1:
        raise RuntimeError("SALE_ASN_BUYER_NOT_FOUND")
    selected = _set_control(
        frame,
        "#Cell_Buyer",
        exact[0]["label"],
        "exact",
    )
    if not selected.get("ok"):
        raise RuntimeError(f"SALE_ASN_BUYER_NOT_CONFIRMED:{selected.get('reason')}")


def scan_sale_asn_buyers(
    xpath: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    playwright = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _refresh_existing_new_form(page, log)
        if frame is None:
            frame = _open_new_form(page, xpath, log)
        _write_log(log, "[SALE ASN] Đang chờ WFX bind danh sách Buyer...")
        buyers = _buyer_options(frame)
        if not buyers:
            raise PlaywrightTimeoutError("Danh sách Buyer chưa bind dữ liệu.")
        _write_log(log, f"[SALE ASN] Đã quét {len(buyers)} Buyer.")
        return _result(
            True,
            "SALE_ASN_BUYERS_SCANNED",
            f"Đã quét {len(buyers)} Buyer từ WFX.",
            buyers=buyers,
        )
    except RuntimeError as error:
        boundary = _browser_boundary_result(error)
        if boundary is not None:
            return boundary
        message = f"Không mở được phiên Sale ASN để quét Buyer: {_first_line(error)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_BUYER_SCAN_FAILED", message)
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        message = f"Không quét được Buyer Sale ASN: {_first_line(error)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_BUYER_SCAN_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
