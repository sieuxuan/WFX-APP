"""Điền Shipping Info; field không có option tương ứng thì bỏ qua có warning."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _wait,
    _write_log,
)
from wfx_panel.automation.sale_asn_create.constants import (
    PORT_OF_LOADING_SELECTOR,
    PORT_OF_LOADING_SELECTORS,
    SHIPPING_FIELD_LABELS,
    SHIPPING_FIELDS,
    SHIPPING_MODE_VALUES,
)
from wfx_panel.automation.sale_asn_create.errors import _shipping_warning
from wfx_panel.automation.sale_asn_create.form import _set_control
from wfx_panel.automation.sale_asn_create.values import _date_for_wfx


def _fill_shipping(
    frame: Frame,
    first_row: dict,
    log: Callable[[str], None],
) -> list[str]:
    tab = frame.locator("#tabShippingInfo").first
    tab.wait_for(state="visible", timeout=8_000)
    tab.click(timeout=5_000)
    _wait(frame, 500)
    warnings: list[str] = []
    shipping_mode = str(first_row.get("shipping_mode") or "").strip().upper()
    mapped = SHIPPING_MODE_VALUES.get(shipping_mode)
    if mapped is None:
        warning = f'Shipping Mode: không hỗ trợ "{shipping_mode or "(trống)"}"'
        warnings.append(warning)
        _write_log(log, f"[SALE ASN] Shipping Info bỏ qua {warning}.")
        mapped = {}
    shipping_values = {**first_row, **mapped}
    destination_is_blank = not str(shipping_values.get("destination") or "").strip()
    destination_country_confirmed: bool | None = None
    for selector, key, mode in SHIPPING_FIELDS:
        label = SHIPPING_FIELD_LABELS.get(selector, selector)
        if destination_is_blank and selector in {
            "#Cell_DestinationCountry",
            "#Cell_FinalDestination",
        }:
            # Destination không bắt buộc.  Khi file để trống, giữ nguyên các
            # giá trị WFX khởi tạo thay vì xóa/đổi một nửa cặp country/final.
            continue
        if (
            selector == "#Cell_FinalDestination"
            and destination_country_confirmed is False
        ):
            # WFX khởi tạo Final Destination giống Country Of Destination.
            # Nếu tên trong file không khớp danh sách country (WFX thường dùng
            # tên quốc gia đầy đủ), giữ nguyên cả hai giá trị mặc định thay vì
            # chỉ đổi Final Destination và tạo ra một cặp không nhất quán.
            _write_log(
                log,
                "[SALE ASN] Giữ nguyên Final Destination theo "
                "Country Of Destination mặc định vì không chọn được country.",
            )
            continue
        # `__` mở đầu nghĩa là hằng số điền thẳng (Consignor Address), phần còn
        # lại là khóa đọc từ file. `tests/test_sale_asn_stages.py` canh để không
        # ai thêm sentinel mới mà quên xử lý ở đây.
        value = (
            key[2:]
            if key.startswith("__")
            else str(shipping_values.get(key) or "")
        )
        if key in {"invoice_date", "shipping_bill_date"}:
            value = _date_for_wfx(value)
        if not value.strip() and not key.startswith("__"):
            warning = f"{label}: file không có dữ liệu"
            warnings.append(warning)
            _write_log(log, f"[SALE ASN] Shipping Info bỏ qua {warning}.")
            continue
        targets = (
            PORT_OF_LOADING_SELECTORS
            if selector == PORT_OF_LOADING_SELECTOR
            else (selector,)
        )
        results: list[dict[str, Any]] = []
        exception_reason = ""
        for target in targets:
            try:
                result = _set_control(frame, target, value, mode, timeout_s=6)
            except (PlaywrightError, PlaywrightTimeoutError) as error:
                exception_reason = _first_line(error)
                continue
            results.append(result)
            if result.get("ok"):
                _wait(frame, 150)
        field_confirmed = any(result.get("ok") for result in results)
        if selector == "#Cell_DestinationCountry":
            destination_country_confirmed = field_confirmed
        if field_confirmed:
            continue
        if exception_reason:
            warning = f"{label}: {exception_reason}"
        else:
            failure = results[-1] if results else {"reason": "not-found"}
            warning = _shipping_warning(label, value, failure)
        if warning:
            warnings.append(warning)
            _write_log(log, f"[SALE ASN] Shipping Info bỏ qua {warning}.")
    if warnings:
        _write_log(
            log,
            f"[SALE ASN] Đã điền Shipping Info; bỏ qua {len(warnings)} trường và chưa bấm Save.",
        )
    else:
        _write_log(log, "[SALE ASN] Đã điền Shipping Info; chưa bấm Save.")
    return warnings
