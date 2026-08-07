"""Tải Packing List + Buyer Invoice từ Sale ASN và ghép thành XLSX."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wfx_panel.asn_workbook import (
    ASNWorkbookError,
    merge_sale_asn_reports,
    sale_asn_sheet_names,
)
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
from wfx_panel.automation.runtime import (
    cancellation_deferred,
    save_native_download,
    snapshot_downloads,
)
from wfx_panel.automation.search_specs import SALE_ASN_SEARCH_SPEC

PACKING_LIST_SELECTOR = "#lnkANFPackingList"
BUYER_INVOICE_SELECTOR = "#lnkBuyerInvoice"
DOCUMENTS_FRAME_TIMEOUT_SECONDS = 60
REPORT_READY_TIMEOUT_SECONDS = 180
REPORT_EXPORT_MENU_TIMEOUT_SECONDS = 30
REPORT_DOWNLOAD_START_TIMEOUT_SECONDS = 180
REPORT_EXPORT_SELECTOR = (
    "#rptCustomReportViewer_ctl05_ctl04_ctl00_ButtonLink, "
    'a[title="Export drop down menu"]'
)
REPORT_EXCEL_FORMAT_SELECTOR = (
    'a[onclick*="EXCELOPENXML"], a[href*="EXCELOPENXML"], '
    '[data-format="EXCELOPENXML"]'
)
REPORT_EXCEL_LABEL_SELECTOR = (
    'a[title="Excel"], a[alt="Excel"], '
    '[role="menuitem"][title="Excel"], input[value="Excel"]'
)
REPORT_EXCEL_SELECTOR = (
    f"{REPORT_EXCEL_FORMAT_SELECTOR}, {REPORT_EXCEL_LABEL_SELECTOR}"
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
    const text = element => {
        if (!element) return '';
        const candidates = [
            element,
            ...element.querySelectorAll(
                'input, textarea, select, a, button, [title], [aria-label]'
            ),
        ];
        for (const candidate of candidates) {
            const value = String(
                candidate?.value
                || candidate?.getAttribute?.('value')
                || candidate?.textContent
                || candidate?.getAttribute?.('title')
                || candidate?.getAttribute?.('aria-label')
                || ''
            ).replace(/\\s+/g, ' ').trim();
            if (value) return value;
        }
        return '';
    };
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
        const key = row.getAttribute('row-index')
            || row.getAttribute('row-id') || String(index);
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(row);
    });
    const rows = [];
    grouped.forEach((parts, rowKey) => {
        let invoiceNo = '';
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
            }
        }
        rows.push({ row_key: rowKey, invoice_no: invoiceNo, selected });
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
        row.getAttribute('row-index') || row.getAttribute('row-id') || String(index)
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


_SALE_ASN_SCROLL_STATE_JS = """root => {
    const scroller = root.querySelector('.ag-body-horizontal-scroll-viewport')
        || root.querySelector('.ag-center-cols-viewport')
        || root.querySelector('.ag-body-viewport');
    if (!scroller) return { current: 0, maximum: 0, viewport: 0 };
    return {
        current: Number(scroller.scrollLeft || 0),
        maximum: Math.max(0, Number(scroller.scrollWidth || 0)
            - Number(scroller.clientWidth || 0)),
        viewport: Number(scroller.clientWidth || 0),
    };
}"""


_SALE_ASN_SCROLL_TO_JS = """(root, left) => {
    const scroller = root.querySelector('.ag-body-horizontal-scroll-viewport')
        || root.querySelector('.ag-center-cols-viewport')
        || root.querySelector('.ag-body-viewport');
    if (!scroller) return false;
    scroller.scrollLeft = Number(left || 0);
    scroller.dispatchEvent(new Event('scroll', { bubbles: true }));
    return true;
}"""


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
                    "selected": False,
                }
                order.append(row_key)
            current = merged[row_key]
            invoice_no = str(row.get("invoice_no") or "").strip()
            if invoice_no:
                current["invoice_no"] = invoice_no
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
    timeout_s: float = REPORT_READY_TIMEOUT_SECONDS,
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
    attached_pages: list[Page] = []

    def receive(download: Any) -> None:
        downloads.append(download)

    def attach(page: Page) -> None:
        if page in attached_pages:
            return
        attached_pages.append(page)
        page.on("download", receive)

    for current in context.pages:
        attach(current)
    context.on("page", attach)
    try:
        export = report_frame.locator(REPORT_EXPORT_SELECTOR).first
        export.evaluate("element => element.click()")
        deadline = time.monotonic() + REPORT_EXPORT_MENU_TIMEOUT_SECONDS
        excel_frame: Frame | None = None
        excel = None
        retried_export = False
        retry_at = time.monotonic() + 3
        while time.monotonic() < deadline:
            excel_frame, excel = _find_report_excel_action(
                context,
                report_frame,
            )
            if excel is not None:
                break
            if not retried_export and time.monotonic() >= retry_at:
                # WebForms Report Viewer đôi khi bỏ lần click đầu khi toolbar
                # vừa hết loading. Thử mở menu lại đúng một lần; không toggle
                # liên tục vì action Excel có thể đang được tạo bất đồng bộ.
                export.evaluate("element => element.click()")
                retried_export = True
            _wait(report_frame, 100)
        if excel is None or excel_frame is None:
            raise PlaywrightTimeoutError(
                f"Không tìm thấy lựa chọn Excel của {label} trong Report Viewer."
            )

        _write_log(log, f"[SALE ASN DOCS] Đang export Excel: {label}...")
        downloads_before_click = snapshot_downloads()
        # Link export thường nằm trong menu display:none. DOM click vẫn gọi đúng
        # exportReport('EXCELOPENXML') và không phụ thuộc menu có kịp hiện hay
        # không, đồng thời tránh nhầm các format Excel cũ.
        excel.evaluate("element => element.click()")
        deadline = time.monotonic() + REPORT_DOWNLOAD_START_TIMEOUT_SECONDS
        while time.monotonic() < deadline and not downloads:
            try:
                _wait(excel_frame, 100)
            except PlaywrightError:
                if context.pages:
                    _wait(context.pages[0], 100)
        if not downloads:
            raise PlaywrightTimeoutError(f"WFX không bắt đầu download {label}.")
        with cancellation_deferred():
            target.parent.mkdir(parents=True, exist_ok=True)
            save_native_download(
                downloads[0],
                target,
                downloads_before_click,
            )
        if not target.is_file() or target.stat().st_size <= 0:
            raise RuntimeError(f"File {label} tải về bị rỗng.")
        _write_log(log, f"[SALE ASN DOCS] Đã tải {label}.")
    finally:
        try:
            context.remove_listener("page", attach)
        except Exception:
            pass
        for current in attached_pages:
            try:
                current.remove_listener("download", receive)
            except Exception:
                pass


def _find_report_excel_action(
    context: Any,
    preferred_frame: Frame,
) -> tuple[Frame | None, Any | None]:
    """Tìm action Excel của Report Viewer, kể cả link menu đang bị ẩn.

    SSRS/WFX có nhiều biến thể markup: lệnh ``EXCELOPENXML`` có thể nằm trong
    ``onclick`` hoặc ``href``; một số bản chỉ gắn nhãn Excel lên menu item. Menu
    cũng có thể được render ở frame cha, nên phải quét mọi frame nhưng vẫn ưu
    tiên frame report vừa được xác nhận.
    """

    frames: list[Frame] = [preferred_frame]
    for page in reversed(context.pages):
        for frame in reversed(page.frames):
            if frame not in frames:
                frames.append(frame)

    hidden_format_action: tuple[Frame, Any] | None = None
    for frame in frames:
        try:
            format_actions = frame.locator(REPORT_EXCEL_FORMAT_SELECTOR)
            for index in range(format_actions.count()):
                candidate = format_actions.nth(index)
                if candidate.is_visible():
                    return frame, candidate
                if hidden_format_action is None:
                    hidden_format_action = (frame, candidate)

            labelled_actions = frame.locator(REPORT_EXCEL_LABEL_SELECTOR)
            for index in range(labelled_actions.count()):
                candidate = labelled_actions.nth(index)
                if candidate.is_visible():
                    return frame, candidate
        except PlaywrightError:
            continue
    if hidden_format_action is not None:
        return hidden_format_action
    return None, None


def _documents_frame(
    context: Any,
    timeout_s: float = DOCUMENTS_FRAME_TIMEOUT_SECONDS,
) -> tuple[Page, Frame]:
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
    return _documents_frame(context, timeout_s=DOCUMENTS_FRAME_TIMEOUT_SECONDS)


def _close_sale_asn_document_popups(
    context: Any,
    existing_page_ids: set[int],
    log: Callable[[str], None],
) -> None:
    """Đóng các popup sinh từ Docs sau khi đã lưu xong file ghép.

    Chỉ đóng Page không có trước lúc click Docs để không đụng cửa sổ WFX mà
    người dùng đã mở sẵn. Khi WFX tái sử dụng tab List hiện tại, tab đó cũng
    được giữ nguyên.
    """
    closed = 0
    for page in reversed(context.pages):
        if id(page) in existing_page_ids:
            continue
        try:
            if not page.is_closed():
                page.close(run_before_unload=False)
                closed += 1
        except PlaywrightError:
            continue
    if closed:
        _write_log(log, f"[SALE ASN DOCS] Đã đóng {closed} cửa sổ Docs/report.")


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
