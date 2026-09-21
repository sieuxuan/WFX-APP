"""Điểm vào: tải Packing List + Buyer Invoice rồi ghép thành một workbook."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wfx_panel.automation._common import (
    Callable,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.modules import (
    _active_wfx_page,
    _apply_module_search,
    _clear_list_search_fields,
    _open_list_search_context,
    _search_input_in_frame,
)
from wfx_panel.automation.sale_asn_documents.constants import (
    BUYER_INVOICE_SELECTOR,
    PACKING_LIST_SELECTOR,
)
from wfx_panel.automation.sale_asn_documents.grid import (
    _click_sale_asn_docs,
    _sale_asn_result_grid,
    _select_sale_asn_row,
)
from wfx_panel.automation.sale_asn_documents.report import (
    _close_sale_asn_document_popups,
    _documents_frame,
    _download_report_excel,
    _mark_report_frames,
    _restore_documents_screen,
    _wait_report_ready,
)
from wfx_panel.automation.search_specs import SALE_ASN_SEARCH_SPEC
from wfx_panel.workbooks.asn import (
    ASNWorkbookError,
    merge_sale_asn_reports,
    sale_asn_sheet_names,
)


def prepare_sale_asn_documents(
    xpath: str,
    filter_kind: str,
    query: str,
    output_path: str | Path,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Tải hai report của một ASN và ghép vào file tạm."""
    selected_field = SALE_ASN_SEARCH_SPEC.fields.get(filter_kind)
    if selected_field is None:
        return _result(False, "INVALID_FILTER", "Kiểu tìm Sale ASN không hợp lệ.")
    query = str(query or "").strip()
    target = Path(output_path).expanduser().resolve()
    packing_path = target.with_name("packing-list-source.xlsx")
    buyer_path = target.with_name("buyer-invoice-source.xlsx")
    playwright: Playwright | None = None
    context: Any | None = None
    existing_page_ids: set[int] | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        frame = _open_list_search_context(
            page,
            SALE_ASN_SEARCH_SPEC,
            xpath,
            log,
        )
        if query:
            _clear_list_search_fields(frame, SALE_ASN_SEARCH_SPEC.field_selectors)
            _wait(page, 250)
            field = _search_input_in_frame(
                page,
                frame,
                selected_field.selectors,
                selected_field.aliases,
                timeout_s=8,
                scan_horizontal=True,
            )
            _apply_module_search(page, field, query, selected_field.label, log)

        expected_invoice = query if filter_kind == "invoice_no" else ""
        root, payload = _sale_asn_result_grid(
            frame,
            expected_invoice=expected_invoice,
        )
        row = _select_sale_asn_row(payload, filter_kind, query)
        invoice_no = str(row.get("invoice_no") or query or "Invoice").strip()
        existing_page_ids = {id(item) for item in context.pages}
        clicked = _click_sale_asn_docs(
            frame,
            root,
            str(row.get("row_key") or ""),
            log,
        )
        if not clicked:
            return _result(
                False,
                "SALE_ASN_DOCS_NOT_AVAILABLE",
                (
                    f"Đã tìm thấy Invoice {invoice_no} nhưng dòng này không có "
                    "nút Docs. Hãy kiểm tra quyền Documents hoặc trạng thái "
                    "của Sale ASN trên WFX."
                ),
                module="Sale ASN",
                invoice_no=invoice_no,
            )
        _write_log(log, "[SALE ASN DOCS] Đã click Docs; đang chờ Documents...")
        docs_page, docs_frame = _documents_frame(context)

        reports = (
            (PACKING_LIST_SELECTOR, "Packing List", packing_path),
            (BUYER_INVOICE_SELECTOR, "Buyer Invoice", buyer_path),
        )
        for index, (selector, label, report_target) in enumerate(reports):
            docs_url = docs_frame.url
            known_pages = {id(item) for item in context.pages}
            report_snapshots = _mark_report_frames(context)
            docs_frame.locator(selector).first.evaluate("element => element.click()")
            _write_log(log, f"[SALE ASN DOCS] Đang chờ report {label} load xong...")
            report_page, report_frame = _wait_report_ready(
                context,
                report_snapshots,
            )
            _download_report_excel(
                context,
                report_frame,
                report_target,
                label,
                log,
            )
            if index + 1 >= len(reports):
                continue
            if id(report_page) not in known_pages and report_page != docs_page:
                try:
                    report_page.close()
                except PlaywrightError:
                    pass
                docs_page, docs_frame = _documents_frame(context)
            else:
                docs_page, docs_frame = _restore_documents_screen(
                    context,
                    report_page,
                    report_frame,
                    docs_url,
                )

        merge_sale_asn_reports(
            packing_path,
            buyer_path,
            target,
            invoice_no=invoice_no,
            buyer_name=str(row.get("buyer") or ""),
        )
        sheet_names = sale_asn_sheet_names(target)
        return _result(
            True,
            "SALE_ASN_DOCUMENTS_PREPARED",
            f"Đã tải và ghép Packing List + Buyer Invoice cho {invoice_no}.",
            invoice_no=invoice_no,
            prepared_path=str(target),
            sheet_names=sheet_names,
        )
    except RuntimeError as exc:
        code = str(exc)
        messages = {
            "CHROME_CLOSED": "Trình duyệt làm việc chưa được mở.",
            "NOT_LOGGED_IN": "Phiên chưa đăng nhập hoặc đã hết hạn.",
            "SALE_ASN_INVOICE_NOT_FOUND": "Không tìm thấy đúng Invoice No. trên grid.",
            "SALE_ASN_MULTIPLE_RESULTS": (
                "Có nhiều invoice phù hợp. Hãy chọn đúng một dòng."
            ),
            "SALE_ASN_SELECTION_REQUIRED": (
                "Hãy nhập Invoice No. hoặc chọn một dòng Sale ASN trước."
            ),
        }
        if code in messages:
            return _result(False, code, messages[code], module="Sale ASN")
        message = f"Không tải được report Sale ASN: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_REPORT_DOWNLOAD_FAILED", message)
    except ASNWorkbookError as exc:
        message = f"Không ghép được report Sale ASN: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_REPORT_MERGE_FAILED", message)
    except PlaywrightTimeoutError as exc:
        message = f"Report Sale ASN chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_REPORT_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_REPORT_DOWNLOAD_FAILED", message)
    finally:
        if context is not None and existing_page_ids is not None:
            _close_sale_asn_document_popups(context, existing_page_ids, log)
        if playwright is not None:
            playwright.stop()
