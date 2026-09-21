"""Supplier Invoice List: chọn dòng và huỷ hoá đơn."""

from __future__ import annotations

from collections.abc import Mapping

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _click,
    _first_line,
    _first_visible,
    _result,
    _wait,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.browser import _attach_dialog_handler
from wfx_panel.automation.modules.context import (
    _frame_with_visible_context,
    _wait_module_search_settled,
)
from wfx_panel.automation.modules.menu import _active_wfx_page
from wfx_panel.automation.modules.search import (
    _clear_multi_search_fields,
    _fill_multi_search_fields,
    _open_multi_field_search_context,
    _resolve_multi_search_fields,
    _submit_multi_search,
)
from wfx_panel.automation.search_specs import SUPPLIER_INVOICE_SEARCH_SPEC

# Đọc dòng và click dòng phải nhìn thấy CÙNG một danh sách. `row_key` có thể
# chỉ là chỉ số dòng khi WFX không gắn id, nên hai script lọc khác nhau là đủ để
# lệch chỉ số và bấm Delete/Cancel lên dòng khác. Vì vậy cả hai dùng chung đúng
# một hàm quét.
_SUPPLIER_INVOICE_SCAN_JS = r"""
    const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const headers = [...document.querySelectorAll(
        '#gridAPInvoiceList_tblGridHeader th, '
        + '#gridAPInvoiceList_tblGridHeader td, '
        + '#gridAPInvoiceList_tblGridHeader [id*="Header"]'
    )].map(cell => norm([
        cell.id || '', cell.getAttribute('title') || '',
        cell.getAttribute('aria-label') || '', cell.textContent || ''
    ].join(' ')).toLowerCase());
    const metadata = cell => {
        const index = Number(cell.cellIndex);
        return norm([
            cell.id || '', cell.getAttribute('title') || '',
            cell.getAttribute('aria-label') || '', headers[index] || ''
        ].join(' ')).toLowerCase();
    };
    const field = (cells, patterns) => {
        const cell = cells.find(candidate =>
            patterns.some(pattern => pattern.test(metadata(candidate)))
        );
        return norm(cell?.querySelector('input[value], a, button')?.value
            || cell?.querySelector('input[value], a, button')?.textContent
            || cell?.textContent || '');
    };
    const scanRows = root => [...root.querySelectorAll('tbody tr, tr')]
        .filter(row => shown(row) && row.querySelector('td'))
        .map((row, index) => {
            const cells = [...row.querySelectorAll('td')];
            return {
                element: row,
                row_key: row.id || row.getAttribute('data-key')
                    || row.getAttribute('data-row-key') || String(index),
                invoice_no: field(cells, [/invoice\s*(no|number)?/, /apinvoice/]),
                supplier: field(cells, [/supplier/, /vendor/]),
                po_no: field(cells, [/\bpo\s*(no|number)?\b/, /purchase\s*order/]),
                asn_grn_no: field(cells, [/asn/, /grn/]),
                status: field(cells, [/status/]),
            };
        })
        .filter(row => row.invoice_no || row.status || row.supplier);
"""


_SUPPLIER_INVOICE_ROWS_JS = (
    "root => {"
    + _SUPPLIER_INVOICE_SCAN_JS
    + """
    return scanRows(root).map(row => {
        const {element, ...rest} = row;
        return rest;
    });
}"""
)


# Dòng đích phải khớp cả row_key lẫn exact Invoice No. Trước đây fallback dùng
# `row.textContent.includes(invoice)`, nên một dòng khác chỉ cần *chứa* số
# invoice ở bất kỳ cột nào cũng bị chọn rồi Delete/Cancel.
_CLICK_SUPPLIER_INVOICE_ROW_JS = (
    "(root, expected) => {"
    + _SUPPLIER_INVOICE_SCAN_JS
    + """
    const wantedKey = String(expected.row_key || '');
    const wantedInvoice = norm(expected.invoice_no).toLowerCase();
    const sameInvoice = row =>
        !wantedInvoice || row.invoice_no.toLowerCase() === wantedInvoice;
    const rows = scanRows(root);
    const match = rows.find(row => wantedKey && row.row_key === wantedKey
        && sameInvoice(row))
        || rows.find(row => wantedInvoice && sameInvoice(row));
    if (!match) return false;
    const row = match.element;
    const control = row.querySelector(
        'input[type="radio"], input[type="checkbox"], input[type="button"]'
    );
    (control || row.cells?.[0] || row).click();
    return true;
}"""
)


def _supplier_invoice_grid(frame: Frame) -> Any | None:
    for selector in (
        "#gridAPInvoiceList_tblGridContent",
        "#gridAPInvoiceList",
    ):
        try:
            grid = _first_visible(frame.locator(selector))
            if grid is not None:
                return grid
        except PlaywrightError:
            continue
    return None


def _supplier_invoice_rows(frame: Frame) -> list[dict[str, str]]:
    grid = _supplier_invoice_grid(frame)
    if grid is None:
        raise PlaywrightTimeoutError("Không tìm thấy bảng Supplier Inv List.")
    payload = grid.evaluate(_SUPPLIER_INVOICE_ROWS_JS)
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, str]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        rows.append(
            {
                key: str(raw.get(key) or "").strip()
                for key in (
                    "row_key",
                    "invoice_no",
                    "supplier",
                    "po_no",
                    "asn_grn_no",
                    "status",
                )
            }
        )
    return rows


def _find_supplier_invoice_frame(page: Page) -> Frame:
    return _frame_with_visible_context(
        page,
        ", ".join(SUPPLIER_INVOICE_SEARCH_SPEC.context_field.selectors),
        module_name=SUPPLIER_INVOICE_SEARCH_SPEC.module_name,
        timeout_s=8,
        search_spec=SUPPLIER_INVOICE_SEARCH_SPEC,
    )


def _select_supplier_invoice_row(
    frame: Frame,
    row_key: str,
    invoice_no: str,
) -> bool:
    grid = _supplier_invoice_grid(frame)
    if grid is None:
        return False
    try:
        return bool(
            grid.evaluate(
                _CLICK_SUPPLIER_INVOICE_ROW_JS,
                {"row_key": row_key, "invoice_no": invoice_no},
            )
        )
    except PlaywrightError:
        return False


def _supplier_invoice_action_for_status(status: str) -> tuple[str, str, str] | None:
    normalised = " ".join(str(status or "").casefold().split())
    if normalised in {"save", "saved"}:
        return (
            '//*[@id="titlebarAPInvoiceList"]/tbody/tr/td[2]/span/div[2]',
            "Delete",
            "SUPPLIER_INVOICE_DELETE_SUBMITTED",
        )
    if normalised in {"confirm", "confirmed"}:
        return (
            '//*[@id="titlebarAPInvoiceList"]/tbody/tr/td[2]/span/div[4]',
            "Cancel",
            "SUPPLIER_INVOICE_CANCEL_SUBMITTED",
        )
    return None


def _submit_supplier_invoice_cancel(
    page: Page,
    frame: Frame,
    row: Mapping[str, str],
    log: Callable[[str], None],
) -> dict[str, Any]:
    status = str(row.get("status") or "").strip()
    action = _supplier_invoice_action_for_status(status)
    if action is None:
        return _result(
            False,
            "SUPPLIER_INVOICE_STATUS_NOT_CANCELLABLE",
            "Invoice chỉ có thể xử lý khi Status là Save hoặc Confirm.",
        )
    row_key = str(row.get("row_key") or "")
    invoice_no = str(row.get("invoice_no") or "")
    if not _select_supplier_invoice_row(frame, row_key, invoice_no):
        return _result(
            False,
            "SUPPLIER_INVOICE_RESULT_EXPIRED",
            "Dòng Supplier Invoice đã thay đổi. Hãy tìm lại trước khi Cancel.",
        )
    selector, action_label, code = action
    button = _first_visible(frame.locator(selector))
    if button is None:
        return _result(
            False,
            "SUPPLIER_INVOICE_ACTION_NOT_READY",
            f"Không tìm thấy nút {action_label} trên Supplier Inv List.",
        )
    _attach_dialog_handler(page, log)
    _click(button)
    _wait(page, 300)
    return _result(
        True,
        code,
        (
            f"Đã bấm {action_label} cho Supplier Invoice. "
            "Nếu WFX hiện hộp xác nhận trong Chrome, hãy kiểm tra rồi xác nhận."
        ),
        action=action_label.casefold(),
        status=status,
    )


def prepare_supplier_invoice_cancel(
    xpath: str,
    invoice_no: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Tìm theo Invoice No.; chỉ tự thao tác khi còn đúng một dòng."""
    invoice_no = str(invoice_no or "").strip()
    if not invoice_no:
        return _result(
            False,
            "QUERY_REQUIRED",
            "Vui lòng nhập Invoice No. cần Cancel.",
        )
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_multi_field_search_context(
            page,
            SUPPLIER_INVOICE_SEARCH_SPEC,
            xpath,
            log,
        )
        fields = _resolve_multi_search_fields(
            frame,
            SUPPLIER_INVOICE_SEARCH_SPEC,
        )
        _clear_multi_search_fields(fields)
        _fill_multi_search_fields(
            fields,
            {"invoice_no": invoice_no},
            ["invoice_no"],
            SUPPLIER_INVOICE_SEARCH_SPEC,
            log,
        )
        _submit_multi_search(fields["invoice_no"])
        _wait_module_search_settled(page, ["Invoice No."])
        rows = _supplier_invoice_rows(frame)
        if not rows:
            return _result(
                False,
                "SUPPLIER_INVOICE_NOT_FOUND",
                "Không tìm thấy Supplier Invoice phù hợp.",
            )
        # Search của WFX là tìm chứa chuỗi: gõ "SI-102" vẫn ra "SI-1024". Đây là
        # nhánh bấm Delete/Cancel nên chỉ exact Invoice No. mới được tự chạy;
        # mọi dòng gần đúng phải để người dùng tự chọn.
        exact = [
            row
            for row in rows
            if row["invoice_no"].strip().casefold() == invoice_no.casefold()
        ]
        if len(exact) == 1:
            return _submit_supplier_invoice_cancel(page, frame, exact[0], log)
        candidates = exact or rows
        message = (
            "Có nhiều Supplier Invoice trùng đúng Invoice No.; "
            "hãy chọn đúng dòng để tiếp tục."
            if exact
            else (
                f"Không có Supplier Invoice nào đúng Invoice No. {invoice_no}; "
                "hãy chọn đúng invoice trong danh sách gần đúng để tiếp tục."
            )
        )
        return _result(
            True,
            "SUPPLIER_INVOICE_MULTIPLE_RESULTS",
            message,
            invoices=candidates[:20],
            result_count=len(candidates),
            exact_match=bool(exact),
        )
    except PlaywrightTimeoutError as exc:
        message = f"Supplier Inv List chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SUPPLIER_INVOICE_NOT_READY", message)
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module="Supplier Inv List")
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SUPPLIER_INVOICE_CANCEL_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def cancel_supplier_invoice_choice(
    row_key: str,
    invoice_no: str,
    expected_status: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Thực hiện Cancel trên dòng mà người dùng đã chọn từ nhiều kết quả."""
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _find_supplier_invoice_frame(page)
        rows = _supplier_invoice_rows(frame)
        selected = next(
            (
                row
                for row in rows
                if row["row_key"] == str(row_key or "")
                and row["invoice_no"].casefold()
                == str(invoice_no or "").strip().casefold()
            ),
            None,
        )
        if selected is None or selected["status"].casefold() != str(
            expected_status or ""
        ).strip().casefold():
            return _result(
                False,
                "SUPPLIER_INVOICE_RESULT_EXPIRED",
                "Danh sách hoặc Status Supplier Invoice đã thay đổi. Hãy tìm lại.",
            )
        return _submit_supplier_invoice_cancel(page, frame, selected, log)
    except PlaywrightTimeoutError as exc:
        message = f"Supplier Inv List không còn mở: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SUPPLIER_INVOICE_RESULT_EXPIRED", message)
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module="Supplier Inv List")
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SUPPLIER_INVOICE_CANCEL_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
