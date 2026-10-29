"""Bảng ASP.NET cổ điển của Supplier Inv và Expense Inv: chữ ký kết quả, tổng dòng.

Hai bảng này không phải AG Grid: không có overlay no-rows, nên luật đoán "rỗng"
của AG Grid không dùng được. Đo trên WFX thật (29/10/2026), cả
WFXAPInvoiceList.aspx (`gridAPInvoiceList`) lẫn WFXExpenseInvoiceList.aspx
(`gridExpenseInvoiceList`) cùng khung grid: dòng dữ liệu là `tr.trContent`
(id = mã nội bộ của invoice) trong `#<grid>_tblGridContent`, pager ghi
`View 1 - 10 of 47`. Lớp loading `#<grid>_divGridLoading` đã nằm trong
`_MODULE_LOADING_SELECTOR`.

Không import `search.py`/`supplier_invoice.py` để cả hai dùng chung được.
"""

from __future__ import annotations

from wfx_panel.automation._common import Any, Frame, PlaywrightError

AP_INVOICE_GRID_ID = "gridAPInvoiceList"
EXPENSE_INVOICE_GRID_ID = "gridExpenseInvoiceList"

_CLASSIC_GRID_STATE_JS = r"""gridId => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const rows = [...document.querySelectorAll(
        `#${gridId}_tblGridContent tr.trContent`
    )].filter(shown);
    const pager = document.querySelector(`#${gridId}_divGridPager`);
    const pagerText = shown(pager)
        ? String(pager.innerText || '').replace(/\s+/g, ' ').trim()
        : '';
    // "Page 1 of 5" cũng có chữ "of": chỉ tin đúng cụm "View a - b of N".
    const match = pagerText.match(/view\s+\d+\s*-\s*\d+\s+of\s+(\d+)/i);
    return {
        signature: pagerText + '|' + rows.map(row => row.id || '').join(','),
        rows: rows.length,
        total: match ? Number(match[1]) : null,
    };
}"""


def _classic_grid_state(frame: Frame, grid_id: str) -> dict[str, Any]:
    try:
        state = frame.evaluate(_CLASSIC_GRID_STATE_JS, grid_id)
    except PlaywrightError:
        return {}
    return state if isinstance(state, dict) else {}


def _classic_grid_signature(frame: Frame, grid_id: str) -> str:
    """Pager + id các dòng đang hiện; đổi khi WFX vẽ lại kết quả lọc."""
    return str(_classic_grid_state(frame, grid_id).get("signature") or "")


def _classic_grid_result_count(frame: Frame, grid_id: str) -> int | None:
    """Tổng số dòng khớp bộ lọc; None khi bảng chưa nhất quán để kết luận.

    Pager chỉ hiện một trang nên tổng lấy từ `of N`. Pager còn ghi tổng > 0 mà
    bảng không còn dòng nào là bảng đang vẽ dở: không được báo "không có kết
    quả" từ trạng thái đó.
    """
    state = _classic_grid_state(frame, grid_id)
    if not state:
        return None
    rows = int(state.get("rows") or 0)
    total = state.get("total")
    if total is None:
        return rows
    total = int(total)
    if total > 0 and rows == 0:
        return None
    return total


def _ap_invoice_grid_signature(frame: Frame) -> str:
    return _classic_grid_signature(frame, AP_INVOICE_GRID_ID)


def _ap_invoice_result_count(frame: Frame) -> int | None:
    return _classic_grid_result_count(frame, AP_INVOICE_GRID_ID)


def _expense_invoice_grid_signature(frame: Frame) -> str:
    return _classic_grid_signature(frame, EXPENSE_INVOICE_GRID_ID)


def _expense_invoice_result_count(frame: Frame) -> int | None:
    return _classic_grid_result_count(frame, EXPENSE_INVOICE_GRID_ID)
