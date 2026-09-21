"""Đối chiếu Qty và Price giữa file và Shipment Details/Summary Total."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

from wfx_panel.automation._common import Page, _result, _wait, _write_log
from wfx_panel.automation.sale_asn_create.constants import (
    SHIPMENT_DETAILS_GRID_SELECTOR,
    SHIPMENT_DETAILS_TAB_SELECTOR,
    SUMMARY_TOTAL_GRID_SELECTOR,
)
from wfx_panel.automation.sale_asn_create.form import _frame_with_selector
from wfx_panel.automation.sale_asn_create.order_details import _order_style_matches
from wfx_panel.automation.sale_asn_create.po import _click_dom_action
from wfx_panel.automation.sale_asn_create.values import (
    _decimal_display,
    _decimal_or_none,
    _fold,
    _table_value_matches,
)

_READ_SHIPMENT_DETAILS_JS = r"""root => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const read = (row, selector) => {
        const cell = row.querySelector(selector);
        const value = cell?.querySelector('[title]')?.getAttribute('title')
            || cell?.getAttribute('title') || cell?.textContent || '';
        return clean(value);
    };
    return [...root.querySelectorAll('tr.trContent')].map(row => ({
        order_no: read(row, '#colOrderNo'),
        article: read(row, '#colArticle'),
        qty: read(row, '#colShippingQty'),
        price: read(row, '#colPrice'),
    })).filter(row => row.order_no || row.article);
}"""


_READ_ASN_SUMMARY_TOTAL_JS = r"""root => {
    const row = root.querySelector('tr.trContent');
    if (!row) return null;
    const read = selector => {
        const cell = row.querySelector(selector);
        return String(cell?.querySelector('[title]')?.getAttribute('title')
            || cell?.getAttribute('title') || cell?.textContent || '')
            .replace(/\s+/g, ' ').trim();
    };
    return {
        total_quantity: read('#colTotalQuantity'),
        value_in_doc_currency: read('#colValueInDocCurrency'),
        net_value_in_doc_currency: read('#colNetValueInDocCurrency'),
    };
}"""


def _shipment_order_po(value: object) -> str:
    """Tách PO từ Order No WFX có dạng ``mã hệ thống/PO``."""

    order_no = str(value or "").strip()
    if "/" not in order_no:
        return order_no
    return order_no.rsplit("/", 1)[-1].strip()


QTY_PRICE_TOLERANCE = Decimal("0.0001")


def _group_file_rows(source_rows: Sequence[dict]) -> dict[tuple[str, str], dict[str, Any]]:
    """Gộp dòng file theo cặp PO No. + Style No. đã chuẩn hoá."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for source in source_rows:
        po_no = str(source.get("po_no") or "").strip()
        style_no = str(source.get("style_no") or "").strip()
        folded_po, folded_style = _fold(po_no), _fold(style_no)
        if not folded_po or not folded_style:
            continue
        group = groups.setdefault(
            (folded_po, folded_style),
            {
                "po_no": po_no,
                "style_no": style_no,
                "folded_po": folded_po,
                "folded_style": folded_style,
                "source_rows": [],
                "qty_values": [],
                "price_values": [],
            },
        )
        group["source_rows"].append(int(source.get("source_row") or 0))
        group["qty_values"].append(_decimal_or_none(source.get("qty")))
        group["price_values"].append(_decimal_or_none(source.get("price")))
    return groups


def _shipment_rows_by_po(shipment_rows: Sequence[dict]) -> dict[str, list[dict]]:
    """Chỉ mục Shipment Details theo PO đã chuẩn hoá, dựng đúng một lần.

    Trước đây mỗi group quét lại toàn bộ Shipment Details và chuẩn hoá chuỗi
    theo từng cặp, tức O(số group × số dòng WFX). Một hoá đơn nhiều PO làm chi
    phí đó tăng theo bình phương mà không thêm thông tin gì.
    """
    index: dict[str, list[dict]] = {}
    for item in shipment_rows:
        folded_po = _fold(_shipment_order_po(item.get("order_no") or item.get("po_no")))
        if not folded_po:
            continue
        index.setdefault(folded_po, []).append(item)
    return index


def _matching_shipment_rows(
    group: dict[str, Any], by_po: dict[str, list[dict]]
) -> list[dict]:
    """Dòng WFX cùng PO và khớp Style; giữ nguyên thứ tự Shipment Details."""
    return [
        item
        for item in by_po.get(group["folded_po"], ())
        if _order_style_matches(group["folded_style"], _fold(item.get("article")))
    ]


def _file_totals(group: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    """Qty cộng dồn và Price của group; None khi file còn thiếu giá trị."""
    qty_values = group["qty_values"]
    file_qty = (
        sum(qty_values, Decimal("0"))
        if all(value is not None for value in qty_values)
        else None
    )
    prices = {value for value in group["price_values"] if value is not None}
    return file_qty, next(iter(prices)) if len(prices) == 1 else None


def _compare_qty_and_price(
    result: dict[str, Any],
    file_qty: Decimal,
    file_price: Decimal,
    system_qty: Decimal,
    system_price: Decimal,
) -> None:
    """Ghi kết luận khớp/lệch vào ``result``."""
    qty_ok = abs(file_qty - system_qty) <= QTY_PRICE_TOLERANCE
    price_ok = abs(file_price - system_price) <= QTY_PRICE_TOLERANCE
    result["qty_ok"] = qty_ok
    result["price_ok"] = price_ok
    if qty_ok and price_ok:
        return
    differences = [
        label
        for label, ok in (("Qty", qty_ok), ("Price", price_ok))
        if not ok
    ]
    result.update(
        status="mismatch",
        message=f"Không khớp {' và '.join(differences)}.",
    )


def _price_check_row(group: dict[str, Any], matched: list[dict]) -> dict[str, Any]:
    """Một dòng kết quả đối chiếu cho đúng một cặp PO + Style."""
    file_qty, file_price = _file_totals(group)
    system_qty_values = [_decimal_or_none(item.get("qty")) for item in matched]
    system_prices = {
        value
        for item in matched
        if (value := _decimal_or_none(item.get("price"))) is not None
    }
    system_qty = (
        sum(system_qty_values, Decimal("0"))
        if matched and all(value is not None for value in system_qty_values)
        else None
    )
    result: dict[str, Any] = {
        "po_no": group["po_no"],
        "style_no": group["style_no"],
        "source_rows": group["source_rows"],
        "system_order_nos": sorted(
            {
                str(item.get("order_no") or "").strip()
                for item in matched
                if str(item.get("order_no") or "").strip()
            }
        ),
        "file_qty": _decimal_display(file_qty),
        "file_price": _decimal_display(file_price),
        "system_qty": _decimal_display(system_qty),
        "system_prices": [_decimal_display(value) for value in sorted(system_prices)],
        "status": "ok",
        "message": "Khớp Qty và Price.",
    }
    if file_qty is None or file_price is None:
        result.update(
            status="file_value_missing",
            message="File thiếu Qty hoặc Price, chưa thể đối chiếu dòng này.",
        )
        return result
    if not matched:
        result.update(
            status="shipment_not_found",
            message="Không tìm thấy PO trong Order No + Article tương ứng trên WFX.",
        )
        return result
    if system_qty is None or not system_prices:
        result.update(
            status="system_value_missing",
            message="Shipment Details thiếu Shipping Qty hoặc Price (USD).",
        )
        return result
    if len(system_prices) != 1:
        result.update(
            status="system_price_ambiguous",
            message="WFX có nhiều Price (USD) cho cùng PO + Style.",
        )
        return result
    _compare_qty_and_price(
        result, file_qty, file_price, system_qty, next(iter(system_prices))
    )
    return result


def _price_check_rows(
    source_rows: Sequence[dict],
    shipment_rows: Sequence[dict],
) -> tuple[list[dict[str, Any]], dict[str, str | bool]]:
    """So sánh file với Shipment Details theo PO trong Order No + Article."""
    groups = _group_file_rows(source_rows)
    by_po = _shipment_rows_by_po(shipment_rows)

    results: list[dict[str, Any]] = []
    complete_file_rows: list[tuple[Decimal, Decimal]] = []
    for group in groups.values():
        results.append(_price_check_row(group, _matching_shipment_rows(group, by_po)))
        file_qty, file_price = _file_totals(group)
        if file_qty is not None and file_price is not None:
            complete_file_rows.append((file_qty, file_price))

    every_file_row_complete = len(complete_file_rows) == len(groups)
    total_qty = sum((qty for qty, _price in complete_file_rows), Decimal("0"))
    total_value = sum((qty * price for qty, price in complete_file_rows), Decimal("0"))
    return results, {
        "file_values_complete": every_file_row_complete,
        "file_total_qty": _decimal_display(total_qty) if every_file_row_complete else "",
        "file_total_value": (
            _decimal_display(total_value) if every_file_row_complete else ""
        ),
    }


def _summary_price_check(
    file_totals: dict[str, str | bool],
    summary: dict[str, str],
) -> dict[str, Any]:
    expected_qty = str(file_totals.get("file_total_qty") or "")
    expected_value = str(file_totals.get("file_total_value") or "")
    values_complete = bool(file_totals.get("file_values_complete"))
    checks = {
        "total_quantity": {
            "expected": expected_qty,
            "actual": str(summary.get("total_quantity") or ""),
        },
        "value_in_doc_currency": {
            "expected": expected_value,
            "actual": str(summary.get("value_in_doc_currency") or ""),
        },
        "net_value_in_doc_currency": {
            "expected": expected_value,
            "actual": str(summary.get("net_value_in_doc_currency") or ""),
        },
    }
    for check in checks.values():
        check["ok"] = values_complete and _table_value_matches(
            check["expected"], check["actual"]
        )
    return {
        "file_values_complete": values_complete,
        "checks": checks,
        "ok": values_complete and all(item["ok"] for item in checks.values()),
    }


def _check_sale_asn_price_on_page(
    page: Page,
    rows: Sequence[dict],
    log: Callable[[str], None],
) -> dict[str, Any]:
    """Đối chiếu ngay trên form vừa tạo, không mở một flow/nút riêng."""

    if not rows:
        raise RuntimeError("SALE_ASN_PRICE_FILE_EMPTY")
    _main_page, frame = _frame_with_selector(
        page.context,
        SHIPMENT_DETAILS_TAB_SELECTOR,
        timeout_s=15,
    )
    _click_dom_action(frame.locator(SHIPMENT_DETAILS_TAB_SELECTOR).first)
    _wait(frame, 350)
    shipment_grid = frame.locator(SHIPMENT_DETAILS_GRID_SELECTOR).first
    shipment_grid.wait_for(state="visible", timeout=15_000)
    shipment_rows = list(shipment_grid.evaluate(_READ_SHIPMENT_DETAILS_JS) or [])
    if not shipment_rows:
        raise RuntimeError("SALE_ASN_SHIPMENT_DETAILS_EMPTY")
    summary_grid = frame.locator(SUMMARY_TOTAL_GRID_SELECTOR).first
    summary_grid.wait_for(state="visible", timeout=10_000)
    summary = summary_grid.evaluate(_READ_ASN_SUMMARY_TOTAL_JS)
    if not isinstance(summary, dict):
        raise RuntimeError("SALE_ASN_SUMMARY_TOTAL_EMPTY")
    comparisons, file_totals = _price_check_rows(rows, shipment_rows)
    summary_check = _summary_price_check(file_totals, summary)
    matched = sum(item["status"] == "ok" for item in comparisons)
    attention = len(comparisons) - matched
    summary_label = "khớp" if summary_check["ok"] else "cần kiểm tra"
    message = (
        f"Đã check {len(comparisons)} PO + Style: {matched} khớp"
        f"{f', {attention} cần kiểm tra' if attention else ''}. "
        f"Summary Total: {summary_label}."
    )
    _write_log(log, f"[SALE ASN] {message}")
    return _result(
        True,
        "SALE_ASN_PRICE_CHECKED",
        message,
        comparisons=comparisons,
        summary=summary_check,
        shipment_row_count=len(shipment_rows),
    )
