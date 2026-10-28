"""Điền Expense Invoice New; tuyệt đối không Save/Confirm hoặc import native."""

from __future__ import annotations

import re
import time
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from wfx_panel.automation._common import (
    _browser_boundary_result,
    _result,
    _wait,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.modules.creation import open_module_new
from wfx_panel.automation.modules.menu import _active_wfx_page
from wfx_panel.automation.runtime import checkpoint
from wfx_panel.workbooks.expense_invoice import OPTION_KEYS

GRID = "#gridExpenseInvoiceExpenseDetail_tblGridContent"
HEADER_SELECTS = {
    "supplier": "#ddlSupplier",
    "currency": "#ddlInvoiceCurrency",
    "payment_term": "#ddlPaymentTerms",
    "brand": "#ddlBrand",
    "team": "#ddlTeam",
}
HEADER_INPUTS = {
    "invoice_no": "#txtInvoiceNo",
    "invoice_date": "#dtInvoiceDate",
    "gl_date": "#dtGLDate",
    "due_date": "#dtDueDate",
    "comments": "#txtComments",
}
CELLS = {"ledger": "ColLedgerAcName", "qty": "ColExpenseQty", "rate": "ColExpenseRate"}
EDITORS = {
    "ledger": "#ddlLedgerAcName",
    "qty": "#txtExpenseQty",
    "rate": "#txtExpenseRate",
}


class ExpenseInputError(ValueError):
    pass


def _settle(frame) -> None:
    deadline = time.monotonic() + 20
    quiet_since = None
    while time.monotonic() < deadline:
        checkpoint()
        busy = frame.evaluate("""() => {
            const visible = e => {
                const s=getComputedStyle(e), r=e.getBoundingClientRect();
                return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
            };
            const prm=window.Sys?.WebForms?.PageRequestManager?.getInstance?.();
            return Boolean(prm?.get_isInAsyncPostBack?.() || window.jQuery?.active ||
                [...document.querySelectorAll('.blockUI,.blockOverlay,[id*="UpdateProgress"]')].some(visible));
        }""")
        if busy:
            quiet_since = None
        else:
            quiet_since = quiet_since or time.monotonic()
            if time.monotonic() - quiet_since >= 0.4:
                return
        _wait(frame, 100)
    raise ExpenseInputError(
        "WFX vẫn đang tải dữ liệu; hãy kiểm tra form trước khi chạy lại."
    )


def _normal(value: str) -> str:
    return " ".join(str(value).split()).casefold()


def _option(options: list[dict], label: str, *, ledger: bool = False) -> dict:
    wanted = _normal(label)
    if not wanted:
        blanks = [
            o
            for o in options
            if not o.get("disabled") and _normal(o["label"]) in {"", "[select]"}
        ]
        if len(blanks) != 1:
            raise ExpenseInputError(
                "Không xác định được lựa chọn trống cho Brand/Team."
            )
        return blanks[0]
    valid = [
        o
        for o in options
        if not o.get("disabled") and _normal(o["label"]) not in {"", "[select]"}
    ]
    matches = [o for o in valid if _normal(o["label"]) == wanted]
    if not matches:
        matches = [o for o in valid if _normal(o["value"]) == wanted]
    if not matches and ledger:
        matches = [
            o for o in valid if _normal(o["label"]).split("(", 1)[0].strip() == wanted
        ]
    if len(matches) != 1:
        raise ExpenseInputError(
            f"Không xác định được duy nhất lựa chọn: {label}. Hãy dùng đúng tên trên WFX."
        )
    return matches[0]


def _options(field) -> list[dict]:
    field.dispatch_event("mousedown")
    deadline = time.monotonic() + 10
    while True:
        checkpoint()
        options = field.evaluate(
            "e => [...e.options].map(o => ({value:o.value,label:o.textContent.trim(),disabled:o.disabled}))"
        )
        if any(_normal(o["label"]) not in {"", "[select]"} for o in options):
            return options
        if time.monotonic() >= deadline:
            return options
        _wait(field.page, 150)


def _select(frame, selector: str, label: str, *, ledger: bool = False) -> str:
    field = frame.locator(selector)
    deadline = time.monotonic() + 15
    while True:
        checkpoint()
        try:
            chosen = _option(_options(field), label, ledger=ledger)
            break
        except ExpenseInputError:
            if time.monotonic() >= deadline:
                raise
            _wait(frame, 150)
    if field.input_value() != chosen["value"]:
        # Select2 backing select 1x1: native change gọi đúng onchange của WFX.
        field.evaluate(
            """(e, value) => {
            e.value = value;
            e.dispatchEvent(new Event('change', {bubbles:true}));
        }""",
            chosen["value"],
        )
        _settle(frame)
    # Một số editor tự commit và bị tháo ngay trong onchange; caller phải
    # xác nhận bằng cell sau khi rời editor, không chờ control đã bị tháo.
    if ledger and not frame.locator(selector).count():
        return chosen["value"]
    if frame.locator(selector).input_value() != chosen["value"]:
        raise ExpenseInputError(f"WFX chưa nhận lựa chọn: {label}.")
    return chosen["value"]


def _frames(browser) -> list:
    found = []
    for page in browser.contexts[0].pages:
        for frame in page.frames:
            if (
                urlsplit(frame.url).path.casefold().endswith("/wfxexpenseinvoice.aspx")
                and frame.locator(GRID).count()
                and frame.locator("#ddlInvoiceType").count()
            ):
                found.append(frame)
    return found


def _rows(frame):
    return (
        frame.locator(GRID)
        .locator("tr")
        .filter(has=frame.locator('[id="ColLedgerAcName"]'))
    )


def _empty_draft(frame, supplier: str = "") -> bool:
    if not frame.get_by_text("Expense Invoice - New", exact=True).count():
        return False
    if frame.locator("#txtInvoiceNo").input_value().strip():
        return False
    if frame.locator("#txtComments").input_value().strip():
        return False
    current_supplier = frame.locator("#ddlSupplier").evaluate(
        "e => e.selectedOptions[0]?.textContent.trim() || ''"
    )
    if current_supplier not in {"", "[Select]"} and _normal(
        current_supplier
    ) != _normal(supplier):
        return False
    rows = _rows(frame)
    if rows.count() > 1:
        return False
    for index in range(rows.count()):
        row = rows.nth(index)
        ledger = row.locator('[id="ColLedgerAcName"]').inner_text().strip()
        if ledger not in {"", "[Select]"}:
            return False
        for key in ("qty", "rate"):
            if _read_number(row.locator(f'[id="{CELLS[key]}"]').inner_text()) != 0:
                return False
    # Không xóa draft có Flex Field hoặc file đính kèm.
    for selector in ("#ddlBrand", "#ddlTeam"):
        label = frame.locator(selector).evaluate(
            "e => e.selectedOptions[0]?.textContent.trim() || ''"
        )
        if label not in {"", "[Select]"}:
            return False
    attachments = frame.locator(
        '#gridObjectAttachment_tblGridContent [id="colUserFileName"]'
    )
    return not any(
        attachments.nth(i).is_visible() and attachments.nth(i).inner_text().strip()
        for i in range(attachments.count())
    )


def _read_number(value: str) -> Decimal:
    return Decimal(re.sub(r"\s+", "", value).replace(",", ""))


def _date_text(value: str) -> str:
    day = date.fromisoformat(value)
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    return f"{day.day:02d} {months[day.month - 1]} {day.year}"


def _input(frame, selector: str, value: str) -> None:
    field = frame.locator(selector)
    field.fill(value)
    field.dispatch_event("change")
    field.dispatch_event("blur")
    _settle(frame)
    if frame.locator(selector).input_value().strip() != value:
        raise ExpenseInputError(f"WFX chưa nhận dữ liệu ở {selector}.")


def _line(frame, index: int, data: dict) -> dict:
    row = _rows(frame).nth(index)
    chosen: dict[str, str] = {}
    for key in ("ledger", "qty", "rate"):
        checkpoint()
        row.locator(f'[id="{CELLS[key]}"]').dblclick(timeout=5000)
        field = frame.locator(EDITORS[key])
        field.wait_for(state="attached", timeout=5000)
        if key == "ledger":
            chosen["ledger_label"] = _option(_options(field), data[key], ledger=True)[
                "label"
            ]
            chosen["ledger"] = _select(frame, EDITORS[key], data[key], ledger=True)
        else:
            field.fill(data[key])
        # Click header rời editor để WFX commit xOnBlur/tính tiền.
        frame.locator("#gridExpenseInvoiceExpenseDetail_tblGridHeader").click()
        _settle(frame)
        actual = row.locator(f'[id="{CELLS[key]}"]').inner_text().strip()
        if key == "ledger":
            if _normal(actual) != _normal(chosen["ledger_label"]):
                raise ExpenseInputError(f"WFX chưa nhận Ledger ở dòng {index + 1}.")
        elif _read_number(actual) != Decimal(data[key]):
            raise ExpenseInputError(f"WFX chưa nhận {key} ở dòng {index + 1}.")
    return chosen


# Đọc thẳng từ handler dropdown mà chính WFX gọi (GET, không ghi, không đổi
# control): Ledger chỉ có editor khi grid đã có dòng, còn Currency bind theo
# Supplier và mousedown khi chưa chọn sẽ bật hộp "Please select Supplier first".
# Currency trên WFX hiển thị bằng mã; hợp các mã mặc định của mọi Supplier là
# đủ danh sách công ty dùng. Brand/Team là Flex Field, đã bind sẵn khi tải trang.
_READ_OPTIONS_JS = """() => {
    const rows = data => Array.isArray(data) ? data : [];
    const pick = (data, field) => rows(data).map(r => String(r[field] || '').trim());
    const sub = [...document.querySelector('#ddlSubType').options]
        .find(o => o.textContent.trim().toUpperCase() === 'ALL OTHER EXPENSES');
    const suppliers = GetBindDDLData(
        GUID, 'Supplier', 'WFXExpenseInvoice', 'InvoiceType|' + window.gInvoiceType + '~');
    const ledgers = rows(GetBindDDLData(
        GUID, 'Ledger', 'WFXExpenseInvoice',
        sub && sub.value ? 'InvoiceSubType|' + sub.value + '~' : ''))
        .filter(r => String(r.Active ?? '1') !== '0');
    const flex = selector => [...document.querySelector(selector).options]
        .map(o => o.textContent.trim());
    return {
        supplier: pick(suppliers, 'SupplierCompanyName'),
        currency: pick(suppliers, 'CurrencyCode'),
        payment_term: pick(GetBindDDLData(GUID, 'PaymentTerms', 'WFXExpenseInvoice', ''), 'PaymentTerm'),
        ledger: pick(ledgers, 'LedgerAcName'),
        brand: flex('#ddlBrand'),
        team: flex('#ddlTeam'),
    };
}"""


def read_expense_options(frame) -> dict[str, list[str]]:
    """Đủ sáu danh sách dropdown của mẫu Excel từ form Expense Invoice đang mở."""
    for selector in ("#ddlBrand", "#ddlTeam"):
        if frame.locator(selector).evaluate("e => e.options.length") <= 1:
            _options(frame.locator(selector))
    raw = frame.evaluate(_READ_OPTIONS_JS)
    options = {
        key: list(
            dict.fromkeys(
                v for v in raw.get(key) or [] if _normal(v) not in {"", "[select]"}
            )
        )
        for key in OPTION_KEYS
    }
    missing = [key for key in OPTION_KEYS if not options[key]]
    if missing:
        raise ExpenseInputError(
            "WFX chưa trả đủ danh sách dropdown: " + ", ".join(missing) + "."
        )
    return options


def fill_expense_invoice(data: dict, log=print) -> dict:
    playwright = None
    edited = False
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        candidates = _frames(browser)
        if len(candidates) > 1:
            raise ExpenseInputError(
                "Đang mở nhiều Expense Invoice; hãy giữ lại một form New trống."
            )
        if candidates and not _empty_draft(candidates[0], data["header"]["supplier"]):
            raise ExpenseInputError(
                "Expense Invoice đang có dữ liệu hoặc không phải New. Hãy kiểm tra/lưu bản đang làm rồi mở New trống trước khi nhập file."
            )
        if not candidates:
            opened = open_module_new("0065_0880_0030_0020", log)
            if not opened.get("ok"):
                return opened
            candidates = _frames(browser)
        if len(candidates) != 1 or not _empty_draft(
            candidates[0], data["header"]["supplier"]
        ):
            raise ExpenseInputError(
                "Chưa xác nhận được một form Expense Invoice - New trống."
            )
        frame = candidates[0]
        header, lines = data["header"], data["lines"]
        edited = True
        _select(frame, "#ddlInvoiceType", "General Expense")
        selected = {"supplier": _select(frame, "#ddlSupplier", header["supplier"])}
        _select(frame, "#ddlSubType", "ALL OTHER EXPENSES")
        for key in ("currency", "payment_term"):
            selected[key] = _select(frame, HEADER_SELECTS[key], header[key])
        for key, selector in HEADER_INPUTS.items():
            value = _date_text(header[key]) if key.endswith("_date") else header[key]
            _input(frame, selector, value)
        for key in ("brand", "team"):
            selected[key] = _select(frame, HEADER_SELECTS[key], header[key])
        if _rows(frame).count() == 0:
            frame.get_by_role("link", name="Add", exact=True).click()
            _wait(frame, 250)
        written = []
        for index, line in enumerate(lines):
            checkpoint()
            count = _rows(frame).count()
            if index >= count:
                frame.get_by_role("link", name="Add", exact=True).click()
                deadline = time.monotonic() + 10
                while _rows(frame).count() == count and time.monotonic() < deadline:
                    _wait(frame, 150)
                if _rows(frame).count() != count + 1:
                    raise ExpenseInputError(
                        "WFX chưa xác nhận dòng chi phí mới; hãy kiểm tra form đang mở."
                    )
            written.append(_line(frame, index, line))
            _write_log(log, f"[EXPENSE] Đã điền chi phí {index + 1}/{len(lines)}")
        # Đối chiếu toàn bộ sau cùng: callback WFX có thể thay dữ liệu trước đó.
        if _rows(frame).count() != len(lines):
            raise ExpenseInputError(
                "Số dòng WFX khác file; hãy kiểm tra form trước khi Confirm."
            )
        for key, selector in HEADER_INPUTS.items():
            wanted = _date_text(header[key]) if key.endswith("_date") else header[key]
            if frame.locator(selector).input_value().strip() != wanted:
                raise ExpenseInputError(
                    "Thông tin chung đã thay đổi trong khi điền; hãy kiểm tra lại form."
                )
        for key, value in selected.items():
            if frame.locator(HEADER_SELECTS[key]).input_value() != value:
                raise ExpenseInputError(
                    "Dropdown đã thay đổi trong khi điền; hãy kiểm tra lại form."
                )
        for selector, label in (
            ("#ddlInvoiceType", "General Expense"),
            ("#ddlSubType", "ALL OTHER EXPENSES"),
        ):
            actual = frame.locator(selector).evaluate(
                "e => e.selectedOptions[0]?.textContent.trim() || ''"
            )
            if _normal(actual) != _normal(label):
                raise ExpenseInputError(
                    "Invoice Type hoặc Sub-Type không đúng giá trị cố định."
                )
        for index, line in enumerate(lines):
            row = _rows(frame).nth(index)
            if _normal(row.locator('[id="ColLedgerAcName"]').inner_text()) != _normal(
                written[index]["ledger_label"]
            ):
                raise ExpenseInputError(f"Ledger dòng {index + 1} đã thay đổi.")
            for key in ("qty", "rate"):
                if _read_number(
                    row.locator(f'[id="{CELLS[key]}"]').inner_text()
                ) != Decimal(line[key]):
                    raise ExpenseInputError(f"{key} dòng {index + 1} đã thay đổi.")
        # Form đã mở sẵn: tiện đọc dropdown thật của tài khoản/Division này cho
        # lần tải mẫu sau. Chỉ đọc; lỗi ở đây không được làm hỏng lượt điền.
        try:
            options = read_expense_options(frame)
        except Exception as error:
            options = None
            _write_log(log, f"[EXPENSE OPTIONS] {type(error).__name__}: {error}")
        return _result(
            True,
            "EXPENSE_FORM_COMPLETED",
            f"Đã điền {len(lines)} dòng Expense Invoice. Hãy kiểm tra trên WFX rồi tự Save/Confirm.",
            row_count=len(lines),
            requires_manual_confirm=True,
            options=options,
        )
    except Exception as error:
        boundary = _browser_boundary_result(error)
        if boundary is not None and not edited:
            return boundary
        _write_log(log, f"[EXPENSE] {type(error).__name__}: {error}")
        message = (
            str(error)
            if isinstance(error, ExpenseInputError)
            else "WFX chưa xác nhận dữ liệu đã điền. Hãy kiểm tra form đang mở trước khi chạy lại."
        )
        return _result(False, "EXPENSE_INPUT_FAILED", message, partially_filled=edited)
    finally:
        if playwright is not None:
            playwright.stop()
