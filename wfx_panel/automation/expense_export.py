"""Read the selected Expense Invoice in a dedicated, read-only WFX view."""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from wfx_panel.automation._common import (
    _browser_boundary_result,
    _result,
    _wait,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.expense_cost_centers import read_cost_centers
from wfx_panel.automation.expense_invoice import (
    GRID,
    HEADER_INPUTS,
    HEADER_SELECTS,
    ExpenseInputError,
    _normal,
    _read_number,
    _settle,
)
from wfx_panel.automation.modules.menu import _active_wfx_page
from wfx_panel.automation.runtime import checkpoint
from wfx_panel.workbooks.expense_invoice import MAX_ROWS, _day

_SELECTED_JS = """() => {
    const root = document.querySelector('#gridExpenseInvoiceList_tblGridContent');
    return [...root.querySelectorAll('tr.trContent')].filter(row =>
        row.getBoundingClientRect().height > 0 &&
        row.querySelector('input[type=radio]:checked,input[type=checkbox]:checked')
    ).map(row => ({id:row.id, invoice:row.querySelector('[id="ColInvoiceNo"]')?.textContent.trim() || ''}));
}"""


class ExpenseSelectionError(ExpenseInputError):
    pass


def _selected_invoice(browser):
    choices = []
    for page in browser.contexts[0].pages:
        for frame in page.frames:
            if (
                urlsplit(frame.url)
                .path.casefold()
                .endswith("/wfxexpenseinvoicelist.aspx")
                and frame.locator("#titlebarExpenseInvoiceList").count()
                and frame.locator("#gridExpenseInvoiceList_tblGridContent").count()
                and not frame.locator("#gridAPInvoiceList_tblGridContent").count()
            ):
                _settle(frame)
                choices.extend((frame, row) for row in frame.evaluate(_SELECTED_JS))
    if len(choices) != 1:
        raise ExpenseSelectionError(
            "Hãy chọn đúng một Expense Invoice trong List; bỏ chọn hóa đơn ở các tab List khác rồi Export format lại."
        )
    frame, row = choices[0]
    if not str(row["id"]).isdecimal() or not row["invoice"]:
        raise ExpenseSelectionError(
            "Chưa xác định được hóa đơn đang chọn; hãy chọn lại trong Expense Inv List."
        )
    return frame, row


def _field_text(frame, selector: str) -> str:
    field = frame.locator(selector)
    if field.count() != 1:
        raise ExpenseInputError("WFX chưa trả đủ thông tin hóa đơn để xuất file.")
    return field.evaluate(
        "e => e.tagName === 'SELECT' ? (e.selectedOptions[0]?.textContent.trim() || '') : (e.value ?? e.textContent).trim()"
    )


def read_expense_view(frame, expected: dict) -> dict:
    """Read both editable controls and WFX's span-based View layout."""
    _settle(frame)
    identity = frame.evaluate(
        "() => ({id:String(window.gExpenseInvoiceID || ''), view:String(window.gView || '')})"
    )
    if identity != {"id": str(expected["id"]), "view": "1"}:
        raise ExpenseInputError("WFX chưa mở đúng chế độ xem của hóa đơn đang chọn.")
    if (
        _normal(_field_text(frame, "#ddlInvoiceType")) != "general expense"
        or _normal(_field_text(frame, "#ddlSubType")) != "all other expenses"
    ):
        raise ExpenseInputError(
            "Chỉ xuất mẫu import cho General Expense / ALL OTHER EXPENSES."
        )
    header = {
        key: _field_text(frame, selector)
        for key, selector in {**HEADER_SELECTS, **HEADER_INPUTS}.items()
    }
    if _normal(header["invoice_no"]) != _normal(expected["invoice"]):
        raise ExpenseInputError(
            "Số hóa đơn vừa mở khác dòng đã chọn; hãy chọn lại rồi xuất file."
        )
    for key in ("invoice_date", "gl_date", "due_date"):
        header[key] = _day(header[key])
    for key in ("brand", "team"):
        if _normal(header[key]) == "[select]":
            header[key] = ""
    metadata = frame.evaluate("""() => ({
        rows:window.objsectionExpenseInvoiceExpenseDetail?.gridExpenseInvoiceExpenseDetail?.data,
        charges:window.objsectionExpenseInvoiceAdditionalCharge?.gridExpenseInvoiceAdditionalCharge?.data || []
    })""")
    rows = metadata.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ExpenseInputError(
            "Không đọc đủ dòng chi phí; chỉ hỗ trợ tối đa 500 dòng."
        )
    if any(
        _read_number(str(row.get("OrgAmt") or row.get("Amt") or 0)) != 0
        for row in metadata["charges"]
    ):
        raise ExpenseInputError(
            "Hóa đơn có Additional Charges ngoài mẫu import; chưa thể xuất đầy đủ hóa đơn này."
        )
    lines, costs = [], {}
    for index, row in enumerate(rows, 1):
        checkpoint()
        lines.append(
            {
                "ledger": row["LedgerAcName"],
                "qty": str(_read_number(row["ExpenseQty"])),
                "rate": str(_read_number(row["ExpenseRate"])),
            }
        )
        allocations = read_cost_centers(frame, row)
        if str(row.get("IsCostCenterMandatory", "0")) == "1" and not allocations:
            raise ExpenseInputError(
                f"Chưa đọc được Cost Center bắt buộc của chi phí {index}."
            )
        if allocations:
            costs[index] = allocations
    # WFX may replace the data while its callbacks complete.
    current = frame.evaluate(
        "() => window.objsectionExpenseInvoiceExpenseDetail.gridExpenseInvoiceExpenseDetail.data"
    )
    if current != rows:
        raise ExpenseInputError("Dữ liệu hóa đơn đã đổi trong lúc đọc; hãy xuất lại.")
    return {"header": header, "lines": lines, "cost_centers": costs}


def export_selected_expense_invoice(log=print) -> dict:
    playwright = None
    try:
        playwright = sync_playwright().start()
        browser, _page = _active_wfx_page(playwright, log)
        frame, selected = _selected_invoice(browser)
        # Normal invoice links may open a BI report. Use the exact View route
        # implemented by WFX's ShowExpenseInvoiceView, without changing that flag.
        url = frame.evaluate(
            """invoice => {
            const u=new URL('WFXExpenseInvoice.aspx',location.href);
            u.search=new URLSearchParams({GUID,ExpenseInvoiceID:invoice,Action:'Edit',View:'1'});
            return u.href;
        }""",
            selected["id"],
        )
        view = None
        for candidate in browser.contexts[0].pages:
            if urlsplit(candidate.url).path.casefold().endswith(
                "/wfxexpenseinvoice.aspx"
            ) and candidate.evaluate(
                "() => window.name === 'WfxSmartExpenseExport' && String(window.gView) === '1'"
            ):
                view = candidate
                break
        if view is None:
            view = browser.contexts[0].new_page()
        view.goto(url, wait_until="domcontentloaded", timeout=30000)
        view.evaluate("() => { window.name='WfxSmartExpenseExport'; }")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            checkpoint()
            if view.locator(GRID).count() and view.locator("#ddlSupplier").count():
                break
            _wait(view, 150)
        view.bring_to_front()
        data = read_expense_view(view, selected)
        return _result(
            True, "EXPENSE_EXPORT_READ", "Đã đọc hóa đơn đang chọn.", data=data
        )
    except Exception as error:
        boundary = _browser_boundary_result(error)
        if boundary is not None:
            return boundary
        # Playwright errors may include the session URL. Keep it out of logs.
        _write_log(log, f"[EXPENSE EXPORT] {type(error).__name__}")
        return _result(
            False,
            "EXPENSE_EXPORT_SELECTION_REQUIRED"
            if isinstance(error, ExpenseSelectionError)
            else "EXPENSE_EXPORT_FAILED",
            str(error)
            if isinstance(error, ExpenseInputError)
            else "Chưa đọc đủ dữ liệu hóa đơn. Hãy kiểm tra Expense Inv List và thử lại.",
        )
    finally:
        if playwright is not None:
            playwright.stop()
