"""Tải Packing List + Buyer Invoice từ Sale ASN và ghép thành XLSX."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wfx_panel.asn_workbook import ASNWorkbookError, merge_sale_asn_reports
from wfx_panel.automation._common import (
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules import (
    MODULE_GRID_POLL_MS,
    _active_wfx_page,
    _apply_module_search,
    _clear_list_search_fields,
    _open_list_search_context,
    _search_input_in_frame,
)
from wfx_panel.automation.runtime import cancellation_deferred
from wfx_panel.automation.search_specs import SALE_ASN_SEARCH_SPEC

PACKING_LIST_SELECTOR = "#lnkANFPackingList"
BUYER_INVOICE_SELECTOR = "#lnkBuyerInvoice"
REPORT_EXPORT_SELECTOR = (
    "#rptCustomReportViewer_ctl05_ctl04_ctl00_ButtonLink, "
    'a[title="Export drop down menu"]'
)
REPORT_EXCEL_SELECTOR = (
    'a[title="Excel"][onclick*="EXCELOPENXML"], '
    'a[alt="Excel"][onclick*="EXCELOPENXML"]'
)


_SALE_ASN_ROWS_JS = """root => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && Number(style.opacity || 1) !== 0
            && rect.width > 0 && rect.height > 0;
    };
    const text = element => String(
        element?.value || element?.textContent || element?.title || ''
    ).replace(/\\s+/g, ' ').trim();
    const metadata = cell => {
        if (!cell) return '';
        const colId = cell.getAttribute('col-id') || '';
        const escaped = window.CSS?.escape ? CSS.escape(colId) : colId;
        const header = colId
            ? root.querySelector(`.ag-header-cell[col-id="${escaped}"]`)
            : null;
        return [
            colId,
            cell.getAttribute('aria-label') || '',
            header?.getAttribute('aria-label') || '',
            header?.textContent || '',
        ].join(' ').toLowerCase();
    };
    const rowNodes = [...root.querySelectorAll(
        '.ag-row[row-index], [role="row"][row-index]'
    )].filter(row => shown(row)
        && !row.classList.contains('ag-row-loading')
        && !row.classList.contains('ag-row-ghost')
        && row.getAttribute('aria-hidden') !== 'true');
    const grouped = new Map();
    rowNodes.forEach((row, index) => {
        const key = row.getAttribute('row-id')
            || row.getAttribute('row-index') || String(index);
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(row);
    });
    const rows = [];
    grouped.forEach((parts, rowKey) => {
        let invoiceNo = '';
        let hasDocs = false;
        let selected = false;
        for (const row of parts) {
            selected = selected
                || row.classList.contains('ag-row-selected')
                || row.getAttribute('aria-selected') === 'true'
                || Boolean(row.querySelector('input[type="checkbox"]:checked'));
            for (const cell of row.querySelectorAll(
                '[role="gridcell"], .ag-cell, td'
            )) {
                const meta = metadata(cell);
                if (!invoiceNo && /invoice\\s*(no|number)|invoiceno/.test(meta)) {
                    invoiceNo = text(cell);
                }
                if (/\\bdocs?\\b|document/.test(meta)) {
                    hasDocs = [...cell.querySelectorAll(
                        'a, button, input[type="button"], [onclick]'
                    )].some(shown);
                }
            }
        }
        rows.push({ row_key: rowKey, invoice_no: invoiceNo, has_docs: hasDocs,
            selected });
    });
    const noRows = [...root.querySelectorAll(
        '.ag-overlay-no-rows-wrapper, .ag-overlay-no-rows-center'
    )].some(shown);
    return { rows, noRows };
}"""


_CLICK_SALE_ASN_DOCS_JS = """(root, target) => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const rows = [...root.querySelectorAll(
        '.ag-row[row-index], [role="row"][row-index]'
    )];
    const parts = rows.filter((row, index) => (
        row.getAttribute('row-id') || row.getAttribute('row-index') || String(index)
    ) === target.rowKey);
    for (const row of parts) {
        for (const cell of row.querySelectorAll('[role="gridcell"], .ag-cell, td')) {
            const colId = cell.getAttribute('col-id') || '';
            const escaped = window.CSS?.escape ? CSS.escape(colId) : colId;
            const header = colId
                ? root.querySelector(`.ag-header-cell[col-id="${escaped}"]`)
                : null;
            const meta = [
                colId,
                cell.getAttribute('aria-label') || '',
                header?.getAttribute('aria-label') || '',
                header?.textContent || '',
            ].join(' ').toLowerCase();
            if (!/\\bdocs?\\b|document/.test(meta)) continue;
            const action = [...cell.querySelectorAll(
                'a, button, input[type="button"], [onclick]'
            )].find(shown);
            if (action) {
                action.click();
                return true;
            }
        }
    }
    return false;
}"""


def _sale_asn_result_grid(
    frame: Frame,
    timeout_s: float = 15,
) -> tuple[Any, dict[str, Any]]:
    deadline = time.monotonic() + timeout_s
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
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
                        str(row.get("invoice_no") or ""),
                        bool(row.get("selected")),
                        bool(row.get("has_docs")),
                    )
                    for row in rows
                )
                ready = bool(rows) or bool(payload.get("noRows"))
                now = time.monotonic()
                if ready and key == stable_key:
                    if now - stable_since >= 0.8:
                        return root, payload
                else:
                    stable_key = key
                    stable_since = now
        except PlaywrightError:
            pass
        _wait(frame, MODULE_GRID_POLL_MS)
    raise PlaywrightTimeoutError("Kết quả Sale ASN chưa ổn định.")


def _select_sale_asn_row(
    payload: dict[str, Any],
    filter_kind: str,
    query: str,
) -> dict[str, Any]:
    rows = [row for row in payload.get("rows") or [] if row.get("has_docs")]
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
            raise RuntimeError("SALE_ASN_MULTIPLE_RESULTS")
    selected = [row for row in rows if row.get("selected")]
    if len(selected) == 1:
        return selected[0]
    if len(selected) > 1:
        raise RuntimeError("SALE_ASN_MULTIPLE_RESULTS")
    if query and len(rows) == 1:
        return rows[0]
    raise RuntimeError("SALE_ASN_SELECTION_REQUIRED")


def _find_frame_with(
    context: Any,
    selectors: tuple[str, ...],
    *,
    timeout_s: float,
    visible: bool = False,
) -> tuple[Page, Frame]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    matched = True
                    for selector in selectors:
                        locator = frame.locator(selector)
                        if not locator.count() or (
                            visible and not locator.first.is_visible()
                        ):
                            matched = False
                            break
                    if matched:
                        return page, frame
                except PlaywrightError:
                    continue
        first_page = context.pages[0] if context.pages else None
        if first_page is not None:
            _wait(first_page, 150)
    raise PlaywrightTimeoutError(
        "Không tìm thấy màn hình chứa: " + ", ".join(selectors)
    )


def _mark_report_frames(context: Any) -> list[tuple[Frame, str]]:
    snapshots: list[tuple[Frame, str]] = []
    for page in context.pages:
        for frame in page.frames:
            try:
                if not frame.locator(REPORT_EXPORT_SELECTOR).count():
                    continue
                marker = f"asn-report-{time.monotonic_ns()}"
                frame.evaluate(
                    "marker => { window.__wfxAsnReportMarker = marker; }",
                    marker,
                )
                snapshots.append((frame, marker))
            except PlaywrightError:
                continue
    return snapshots


def _report_frame_is_new(
    frame: Frame,
    snapshots: list[tuple[Frame, str]],
) -> bool:
    old = next((item for item in snapshots if item[0] == frame), None)
    if old is None:
        return True
    try:
        marker = frame.evaluate("() => window.__wfxAsnReportMarker || ''")
        return marker != old[1]
    except PlaywrightError:
        return True


def _wait_report_ready(
    context: Any,
    snapshots: list[tuple[Frame, str]],
    timeout_s: float = 70,
) -> tuple[Page, Frame]:
    deadline = time.monotonic() + timeout_s
    stable_since = 0.0
    candidate_key: tuple[int, int] | None = None
    while time.monotonic() < deadline:
        try:
            page, frame = _find_frame_with(
                context,
                (REPORT_EXPORT_SELECTOR,),
                timeout_s=0.2,
                visible=True,
            )
            if not _report_frame_is_new(frame, snapshots):
                if context.pages:
                    _wait(context.pages[0], 150)
                continue
            export = frame.locator(REPORT_EXPORT_SELECTOR).first
            loading = frame.locator(
                '[id*="AsyncWait"][style*="display: block"], '
                '[id*="AsyncWait"][aria-hidden="false"], [aria-busy="true"]'
            )
            has_loading = any(
                loading.nth(index).is_visible()
                for index in range(loading.count())
            )
            key = (id(page), id(frame))
            now = time.monotonic()
            if export.is_enabled() and not has_loading:
                if key != candidate_key:
                    candidate_key = key
                    stable_since = now
                elif now - stable_since >= 0.8:
                    return page, frame
            else:
                candidate_key = None
                stable_since = 0.0
        except (PlaywrightError, PlaywrightTimeoutError):
            candidate_key = None
            stable_since = 0.0
        if context.pages:
            _wait(context.pages[0], 150)
    raise PlaywrightTimeoutError("Report Viewer chưa load xong.")


def _download_report_excel(
    context: Any,
    report_frame: Frame,
    target: Path,
    label: str,
    log: Callable[[str], None],
) -> None:
    downloads: list[Any] = []

    def attach(page: Page) -> None:
        page.on("download", lambda download: downloads.append(download))

    for current in context.pages:
        attach(current)
    context.on("page", attach)

    export = report_frame.locator(REPORT_EXPORT_SELECTOR).first
    export.evaluate("element => element.click()")
    deadline = time.monotonic() + 12
    excel = None
    while time.monotonic() < deadline:
        try:
            candidate = report_frame.locator(REPORT_EXCEL_SELECTOR)
            if candidate.count() and candidate.first.is_visible():
                excel = candidate.first
                break
        except PlaywrightError:
            pass
        _wait(report_frame, 100)
    if excel is None:
        raise PlaywrightTimeoutError(f"Menu Excel của {label} chưa hiện.")

    _write_log(log, f"[SALE ASN DOCS] Đang export Excel: {label}...")
    excel.evaluate("element => element.click()")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline and not downloads:
        _wait(report_frame, 100)
    if not downloads:
        raise PlaywrightTimeoutError(f"WFX không bắt đầu download {label}.")
    with cancellation_deferred():
        target.parent.mkdir(parents=True, exist_ok=True)
        downloads[0].save_as(target)
    if not target.is_file() or target.stat().st_size <= 0:
        raise RuntimeError(f"File {label} tải về bị rỗng.")
    _write_log(log, f"[SALE ASN DOCS] Đã tải {label}.")


def _documents_frame(context: Any, timeout_s: float = 35) -> tuple[Page, Frame]:
    return _find_frame_with(
        context,
        (PACKING_LIST_SELECTOR, BUYER_INVOICE_SELECTOR),
        timeout_s=timeout_s,
        visible=True,
    )


def _restore_documents_screen(
    context: Any,
    report_page: Page,
    report_frame: Frame,
    docs_url: str,
) -> tuple[Page, Frame]:
    try:
        return _documents_frame(context, timeout_s=1)
    except PlaywrightTimeoutError:
        pass
    try:
        report_frame.evaluate("history.back()")
    except PlaywrightError:
        try:
            report_frame.goto(docs_url, wait_until="domcontentloaded", timeout=15_000)
        except PlaywrightError:
            try:
                report_page.go_back(wait_until="domcontentloaded", timeout=15_000)
            except PlaywrightError:
                pass
    return _documents_frame(context, timeout_s=35)


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
            )
            _apply_module_search(page, field, query, selected_field.label, log)

        root, payload = _sale_asn_result_grid(frame)
        row = _select_sale_asn_row(payload, filter_kind, query)
        invoice_no = str(row.get("invoice_no") or query or "Invoice").strip()
        clicked = root.evaluate(
            _CLICK_SALE_ASN_DOCS_JS,
            {"rowKey": str(row.get("row_key") or "")},
        )
        if not clicked:
            raise PlaywrightTimeoutError("Không click được cột Docs của invoice.")
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

        merge_sale_asn_reports(packing_path, buyer_path, target)
        return _result(
            True,
            "SALE_ASN_DOCUMENTS_PREPARED",
            f"Đã tải và ghép Packing List + Buyer Invoice cho {invoice_no}.",
            invoice_no=invoice_no,
            prepared_path=str(target),
            sheet_names=["Packing List", "Buyer Invoice"],
        )
    except RuntimeError as exc:
        code = str(exc)
        messages = {
            "CHROME_CLOSED": "Trình duyệt làm việc chưa được mở.",
            "NOT_LOGGED_IN": "Phiên chưa đăng nhập hoặc đã hết hạn.",
            "SALE_ASN_INVOICE_NOT_FOUND": "Không tìm thấy invoice có cột Docs.",
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
        if playwright is not None:
            playwright.stop()
