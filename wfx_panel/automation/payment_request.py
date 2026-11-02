"""In ĐNTT từ đúng dòng Finance, dùng Payment Request Form của WFX."""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Mapping
from urllib.parse import urlsplit

from wfx_panel.automation import reports
from wfx_panel.automation._common import (
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _click,
    _result,
    _wait,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.modules.ap_invoice_grid import (
    _classic_grid_result_count,
    _classic_grid_signature,
)
from wfx_panel.automation.modules.menu import _active_wfx_page
from wfx_panel.automation.modules.search import (
    _open_multi_field_search_context,
    _search_module_fields,
)
from wfx_panel.automation.runtime import checkpoint, recycle_playwright
from wfx_panel.automation.search_specs import (
    ADVANCE_PR_SEARCH_SPEC,
    EXPENSE_INVOICE_SEARCH_SPEC,
    SUPPLIER_INVOICE_SEARCH_SPEC,
)

MODULES = {
    "0065_0880_0010_0020": (ADVANCE_PR_SEARCH_SPEC, "AdvancePaymentRequestList"),
    "0065_0880_0020_0020": (SUPPLIER_INVOICE_SEARCH_SPEC, "APInvoiceList"),
    "0065_0880_0030_0020": (EXPENSE_INVOICE_SEARCH_SPEC, "ExpenseInvoiceList"),
}

_ROWS_JS = r"""root => {
    const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
    return [...root.querySelectorAll('tr.trContent')]
        .filter(row => row.getBoundingClientRect().height > 0)
        .map(row => {
            const cell = [...row.querySelectorAll('td')].find(
                cell => cell.id.toLowerCase() === 'colinvoiceno');
            const box = row.querySelector('input[type=radio],input[type=checkbox]');
            return {id:row.id, invoice_no:norm(cell?.textContent),
                selected:Boolean(box?.checked)};
        }).filter(row => row.id && row.invoice_no);
}"""

_SELECT_JS = """(root, expected) => {
    const rows = [...root.querySelectorAll('tr.trContent')];
    const row = rows.find(row => row.id === expected.id);
    const norm = value => String(value || '').replace(/\\s+/g, ' ').trim();
    const cell = row && [...row.querySelectorAll('td')].find(
        cell => cell.id.toLowerCase() === 'colinvoiceno');
    if (!row || norm(cell?.textContent) !== expected.invoice_no) return false;
    const box = row.querySelector('input[type=radio],input[type=checkbox]');
    if (!box || box.disabled) return false;
    for (const other of root.querySelectorAll('input[type=checkbox]:checked')) {
        if (other !== box) other.click();
    }
    if (!box.checked) box.click();
    return box.checked;
}"""


class PaymentSelectionError(ValueError):
    pass


def _list_frames(context, suffix):
    for page in context.pages:
        for frame in page.frames:
            try:
                if (
                    urlsplit(frame.url)
                    .path.casefold()
                    .endswith(f"/wfx{suffix}.aspx".casefold())
                    and frame.locator(f"#titlebar{suffix}").count() > 0
                    and frame.locator(f"#grid{suffix}_tblGridContent").count() == 1
                ):
                    yield frame
            except PlaywrightError:
                continue


def _selected_invoice(context, suffix):
    selected = []
    for frame in _list_frames(context, suffix):
        rows = frame.locator(f"#grid{suffix}_tblGridContent").evaluate(_ROWS_JS)
        selected.extend((frame, row) for row in rows if row["selected"])
    if len(selected) != 1:
        raise PaymentSelectionError(
            "Hãy nhập Invoice No. hoặc chọn đúng một dòng trong List của module này; "
            "bỏ chọn ở các tab List khác rồi bấm In ĐNTT."
        )
    frame, row = selected[0]
    if not str(row["id"]).isdecimal():
        raise PaymentSelectionError(
            "Chưa xác định được chứng từ; hãy chọn lại dòng trên WFX."
        )
    return frame, row


def _find_invoice(page, module_id, invoice_no, log):
    spec, suffix = MODULES[module_id]
    grid_id = f"grid{suffix}"
    xpath = f'//*[@id="{module_id}"]/a'
    result = _search_module_fields(
        spec,
        xpath,
        {"invoice_no": invoice_no},
        log,
        result_signature=lambda frame: _classic_grid_signature(frame, grid_id),
        count_results=lambda frame: _classic_grid_result_count(frame, grid_id),
    )
    if not result.get("ok"):
        return result
    frame = _open_multi_field_search_context(page, spec, xpath, log)
    root = frame.locator(f"#{grid_id}_tblGridContent")
    rows = root.evaluate(_ROWS_JS)
    exact = [
        row for row in rows if row["invoice_no"].casefold() == invoice_no.casefold()
    ]
    total = _classic_grid_result_count(frame, grid_id)
    if len(exact) != 1 or total is None or total > len(rows):
        raise PaymentSelectionError(
            "Chưa tìm được duy nhất một dòng khớp chính xác Invoice No. "
            "Hãy chọn đúng dòng trên WFX, để trống ô Invoice No. của In ĐNTT rồi bấm lại."
        )
    if not root.evaluate(_SELECT_JS, exact[0]):
        raise PaymentSelectionError("Dòng hóa đơn đã thay đổi; hãy tìm hoặc chọn lại.")
    selected = [row for row in root.evaluate(_ROWS_JS) if row["selected"]]
    if len(selected) != 1 or selected[0]["id"] != exact[0]["id"]:
        raise PaymentSelectionError(
            "WFX chưa chọn duy nhất dòng hóa đơn cần in; hãy chọn lại."
        )
    return frame, selected[0]


def _mark_documents(context, marker):
    for page in context.pages:
        for frame in page.frames:
            try:
                frame.evaluate("marker => { window.__wfxDnttBefore = marker; }", marker)
            except PlaywrightError:
                continue


def _new_report(context, before):
    for page in reversed(context.pages):
        for frame in page.frames:
            try:
                if (
                    frame.locator(reports.PARAMETER_TABLE).count() == 1
                    and frame.evaluate("() => window.__wfxDnttBefore || ''") != before
                ):
                    return page, frame
            except PlaywrightError:
                continue
    return None


def _parameters(frame, selected):
    parameters = reports._read_parameters(frame, shipment_date_ids=False)
    identity = [
        item for item in parameters if item["label"].strip().casefold() == "txnid"
    ]
    if len(identity) != 1 or str(identity[0]["value"]).strip() != selected["id"]:
        raise PaymentSelectionError(
            "Báo cáo chưa khớp chứng từ đã chọn; hãy bấm In ĐNTT lại từ đúng dòng."
        )
    public = [item for item in parameters if item not in identity]
    for item in public:
        if "requester" in item["label"].casefold():
            item["required"] = True
        if item["key"].endswith("_cbNull"):
            item["label"] += " — để trống"
    return public, identity[0]


def _close_previous_reports(context, current):
    # Only tabs claimed by this workflow may be closed. A user's other WFX
    # report or List is never a cleanup target.
    for page in list(context.pages):
        if page == current:
            continue
        try:
            if page.evaluate("() => Boolean(window.__wfxDnttReport)"):
                page.close()
        except PlaywrightError:
            continue


def prepare_payment_request(module_id, invoice_no="", log=print):
    if module_id not in MODULES:
        return _result(False, "MODULE_UNKNOWN", "Module này không hỗ trợ In ĐNTT.")
    playwright = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        suffix = MODULES[module_id][1]
        if str(invoice_no or "").strip():
            found_invoice = _find_invoice(page, module_id, str(invoice_no).strip(), log)
            if isinstance(found_invoice, dict):
                return found_invoice
            frame, selected = found_invoice
        else:
            frame, selected = _selected_invoice(page.context, suffix)
        frame.page.bring_to_front()
        _write_log(log, "[ĐNTT] Mở BI Print → Payment Request Form.")
        _click(frame.locator(f"#titlebar{suffix} .clsPageTitleBarToolBI.Print > a"))
        link = frame.locator("#lnkPrintBIReport").filter(
            has_text=re.compile(r"^\s*Payment\s+Request\s+Form\s*$", re.I)
        )
        link.wait_for(state="visible", timeout=10_000)
        before = secrets.token_urlsafe(24)
        _mark_documents(page.context, before)
        _click(link)
        found = None
        # A named WFX report popup can be invisible to the current CDP driver.
        # Probe first, then reconnect once; never click BI Print a second time.
        for attempt in range(2):
            deadline = time.monotonic() + (8 if attempt == 0 else 30)
            while time.monotonic() < deadline:
                checkpoint()
                found = _new_report(page.context, before)
                if found:
                    break
                _wait(page, 150)
            if found:
                break
            if attempt == 0:
                playwright = recycle_playwright(playwright)
                _browser, page = _active_wfx_page(playwright, log)
        if found is None:
            raise PlaywrightTimeoutError("Payment Request Form chưa mở.")
        report_page, report_frame = found
        reports._wait_postback_settled(report_frame)
        parameters, identity = _parameters(report_frame, selected)
        marker = secrets.token_urlsafe(24)
        report_frame.evaluate("marker => { window.__wfxDnttReport = marker; }", marker)
        _close_previous_reports(report_page.context, report_page)
        report_page.bring_to_front()
        return _result(
            True,
            "PAYMENT_REQUEST_PREPARED",
            "Đã mở đề nghị thanh toán. Điền họ tên rồi xuất báo cáo.",
            module_id=module_id,
            invoice_no=selected["invoice_no"],
            parameters=parameters,
            _report_state={
                "marker": marker,
                "identity": identity,
                "parameters": parameters,
            },
        )
    except PaymentSelectionError as error:
        return _result(False, "PAYMENT_REQUEST_SELECTION_REQUIRED", str(error))
    except Exception as error:
        boundary = _browser_boundary_result(error)
        if boundary:
            return boundary
        _write_log(log, f"[ĐNTT] {type(error).__name__}: {error}")
        return _result(
            False,
            "PAYMENT_REQUEST_FAILED",
            "Chưa mở được Payment Request Form. Hãy kiểm tra WFX rồi thử lại.",
        )
    finally:
        if playwright is not None:
            playwright.stop()


def _export_values(state, values):
    if not isinstance(values, Mapping):
        raise ValueError("Tham số báo cáo không hợp lệ.")
    parameters = state["parameters"]
    allowed = {item["key"] for item in parameters}
    if set(values) - allowed:
        raise ValueError("Tham số không thuộc đề nghị thanh toán đang mở.")
    cleaned = {}
    # Null checkboxes enable/disable the associated text field on ReportViewer.
    for item in sorted(
        parameters, key=lambda item: not item["key"].endswith("_cbNull")
    ):
        key = item["key"]
        value = values.get(key, item["value"])
        if item["type"] == "checkbox":
            if not isinstance(value, bool):
                raise ValueError("Lựa chọn để trống tham số không hợp lệ.")
        elif not isinstance(value, str) or len(value) > 500:
            raise ValueError("Giá trị tham số báo cáo không hợp lệ.")
        elif item.get("required") and not value.strip():
            raise ValueError("Hãy điền họ và tên người đề nghị trước khi xuất báo cáo.")
        null_key = key.removesuffix("_txtValue") + "_cbNull"
        if null_key in cleaned and cleaned[null_key] is True:
            continue
        cleaned[key] = value
    return cleaned


def export_payment_request(state, values, log=print):
    try:
        cleaned = _export_values(state, values)
    except ValueError as error:
        return _result(False, "REPORT_PARAMETERS_INVALID", str(error))
    playwright = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        found = None
        for candidate in page.context.pages:
            for frame in candidate.frames:
                try:
                    if (
                        frame.evaluate("() => window.__wfxDnttReport || ''")
                        != state["marker"]
                    ):
                        continue
                    identity = state["identity"]
                    if (
                        frame.locator(f'[id="{identity["key"]}"]').input_value()
                        != identity["value"]
                    ):
                        continue
                    found = candidate, frame
                except PlaywrightError:
                    continue
        if found is None:
            return _result(
                False,
                "PAYMENT_REQUEST_EXPIRED",
                "Báo cáo đã đóng hoặc thay đổi. Hãy bấm In ĐNTT lại.",
            )
        candidate, frame = found
        candidate.bring_to_front()
        reports._set_parameters(frame, cleaned)
        reports._click_view_report(frame)
        reports._wait_report_ready(frame, log)
        path = reports._export_excel(candidate, report_frame=frame)
        return _result(
            True,
            "REPORT_EXPORTED",
            f"Đã tải xong {path.name}.",
            file_name=path.name,
            download_path=str(path),
        )
    except Exception as error:
        boundary = _browser_boundary_result(error)
        if boundary:
            return boundary
        _write_log(log, f"[ĐNTT] {type(error).__name__}: {error}")
        return _result(
            False,
            "REPORT_EXPORT_FAILED",
            "Chưa xuất được đề nghị thanh toán. Hãy kiểm tra tên và báo cáo trên WFX.",
        )
    finally:
        if playwright is not None:
            playwright.stop()
