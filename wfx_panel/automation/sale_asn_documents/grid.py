"""Tìm đúng dòng Sale ASN và bấm cột Docs.

Mỗi user kéo cột một kiểu nên phải quét ngang AG Grid để tìm Docs theo
metadata, không dựa vào vị trí cột."""

from __future__ import annotations

from typing import Any

from wfx_panel.automation._common import (
    Callable,
    Frame,
    PlaywrightError,
    PlaywrightTimeoutError,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.modules import MODULE_GRID_POLL_MS
from wfx_panel.automation.sale_asn_documents.constants import (
    _CLICK_SALE_ASN_DOCS_JS,
    _SALE_ASN_ROWS_JS,
    _SALE_ASN_SCROLL_STATE_JS,
    _SALE_ASN_SCROLL_TO_JS,
)


def _sale_asn_result_grid(
    frame: Frame,
    expected_invoice: str = "",
    timeout_s: float = 15,
) -> tuple[Any, dict[str, Any]]:
    deadline = time.monotonic() + timeout_s
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    last_candidate: tuple[Any, dict[str, Any]] | None = None
    while time.monotonic() < deadline:
        try:
            roots = frame.locator(".ag-root-wrapper")
            for index in range(roots.count()):
                root = roots.nth(index)
                if not root.is_visible():
                    continue
                payload = root.evaluate(_SALE_ASN_ROWS_JS)
                rows = payload.get("rows") or []
                key = tuple(
                    (
                        str(row.get("row_key") or ""),
                        bool(row.get("selected")),
                    )
                    for row in rows
                )
                expected = expected_invoice.strip().casefold()
                ready = bool(rows) or (
                    not expected and bool(payload.get("noRows"))
                )
                now = time.monotonic()
                if ready and key == stable_key:
                    if now - stable_since >= 0.8:
                        # Invoice No. có thể nằm ngoài viewport ngang và value
                        # thật nằm trong input[type=button] của cell. Quét toàn
                        # grid trước khi chọn row để không phụ thuộc layout cột
                        # riêng của từng user.
                        payload = _scan_sale_asn_rows(frame, root)
                        last_candidate = (root, payload)
                        exact_invoice_ready = not expected or any(
                            str(row.get("invoice_no") or "")
                            .strip()
                            .casefold()
                            == expected
                            for row in payload.get("rows") or []
                        )
                        if exact_invoice_ready:
                            return root, payload
                        # Floating Filter có debounce. Không nhận DOM cũ nếu
                        # invoice exact chưa xuất hiện sau lần quét đầy đủ.
                        stable_since = now
                else:
                    stable_key = key
                    stable_since = now
                last_candidate = (root, payload)
        except PlaywrightError:
            pass
        _wait(frame, MODULE_GRID_POLL_MS)
    if expected_invoice and last_candidate is not None:
        return last_candidate
    raise PlaywrightTimeoutError("Kết quả Sale ASN chưa ổn định.")


def _select_sale_asn_row(
    payload: dict[str, Any],
    filter_kind: str,
    query: str,
) -> dict[str, Any]:
    rows = list(payload.get("rows") or [])
    if not rows:
        raise RuntimeError("SALE_ASN_INVOICE_NOT_FOUND")
    if filter_kind == "invoice_no" and query:
        exact = [
            row
            for row in rows
            if str(row.get("invoice_no") or "").strip().casefold()
            == query.casefold()
        ]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            selected_exact = [row for row in exact if row.get("selected")]
            if len(selected_exact) == 1:
                return selected_exact[0]
            raise RuntimeError("SALE_ASN_MULTIPLE_RESULTS")
        raise RuntimeError("SALE_ASN_INVOICE_NOT_FOUND")
    selected = [row for row in rows if row.get("selected")]
    if len(selected) == 1:
        return selected[0]
    if len(selected) > 1:
        raise RuntimeError("SALE_ASN_MULTIPLE_RESULTS")
    if query and len(rows) == 1:
        return rows[0]
    raise RuntimeError("SALE_ASN_SELECTION_REQUIRED")


def _sale_asn_horizontal_positions(state: dict[str, Any]) -> list[int]:
    current = max(0, int(float(state.get("current") or 0)))
    maximum = max(0, int(float(state.get("maximum") or 0)))
    viewport = max(0, int(float(state.get("viewport") or 0)))
    step = max(160, int(viewport * 0.75))
    positions = [current, 0]
    positions.extend(range(step, maximum, step))
    positions.append(maximum)
    return list(dict.fromkeys(min(maximum, position) for position in positions))


def _merge_sale_asn_row_payloads(
    payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    """Ghép các phần row được AG Grid render ở từng vị trí cuộn ngang."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for payload in payloads:
        for row in payload.get("rows") or []:
            row_key = str(row.get("row_key") or "")
            if row_key not in merged:
                merged[row_key] = {
                    "row_key": row_key,
                    "invoice_no": "",
                    "buyer": "",
                    "selected": False,
                }
                order.append(row_key)
            current = merged[row_key]
            invoice_no = str(row.get("invoice_no") or "").strip()
            if invoice_no:
                current["invoice_no"] = invoice_no
            buyer = str(row.get("buyer") or "").strip()
            if buyer:
                current["buyer"] = buyer
            current["selected"] = bool(
                current["selected"] or row.get("selected")
            )
    return {
        "rows": [merged[row_key] for row_key in order],
        "noRows": bool(payloads)
        and all(bool(payload.get("noRows")) for payload in payloads),
    }


def _scan_sale_asn_rows(frame: Frame, root: Any) -> dict[str, Any]:
    """Đọc row metadata ở mọi vị trí ngang rồi khôi phục vị trí ban đầu."""
    state = root.evaluate(_SALE_ASN_SCROLL_STATE_JS)
    original = max(0, int(float(state.get("current") or 0)))
    payloads: list[dict[str, Any]] = []
    try:
        for position in _sale_asn_horizontal_positions(state):
            root.evaluate(_SALE_ASN_SCROLL_TO_JS, position)
            _wait(frame, MODULE_GRID_POLL_MS)
            payloads.append(root.evaluate(_SALE_ASN_ROWS_JS))
    finally:
        root.evaluate(_SALE_ASN_SCROLL_TO_JS, original)
    return _merge_sale_asn_row_payloads(payloads)


def _click_sale_asn_docs(
    frame: Frame,
    root: Any,
    row_key: str,
    log: Callable[[str], None],
) -> bool:
    """Quét ngang AG Grid vì người dùng có thể kéo Docs tới vị trí bất kỳ."""
    state = root.evaluate(_SALE_ASN_SCROLL_STATE_JS)
    original = max(0, int(float(state.get("current") or 0)))
    for position in _sale_asn_horizontal_positions(state):
        root.evaluate(_SALE_ASN_SCROLL_TO_JS, position)
        _wait(frame, MODULE_GRID_POLL_MS)
        if root.evaluate(
            _CLICK_SALE_ASN_DOCS_JS,
            {"rowKey": row_key},
        ):
            _write_log(
                log,
                "[SALE ASN DOCS] Đã tìm thấy cột Docs sau khi quét ngang grid.",
            )
            return True
    root.evaluate(_SALE_ASN_SCROLL_TO_JS, original)
    return False
