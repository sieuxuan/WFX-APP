"""RMPO List: tìm, đọc dòng và mở Kiểm tra/Sửa/Check Received."""

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
    _document_changed,
    _first_line,
    _first_visible,
    _mark_document,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules.constants import MODULE_GRID_POLL_MS
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
from wfx_panel.automation.modules.text import _normalise_search_text
from wfx_panel.automation.search_specs import RMPO_SEARCH_SPEC


def search_rmpo_list(
    xpath: str,
    supplier: str,
    order_no: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Lọc RMPO rồi trả các dòng đang hiển thị để panel cho phép chọn."""
    cleaned = {
        "supplier": str(supplier or "").strip(),
        "order_no": str(order_no or "").strip(),
    }
    active = [key for key, value in cleaned.items() if value]
    if not active:
        return _result(
            False,
            "QUERY_REQUIRED",
            "Vui lòng nhập ít nhất một điều kiện: Supplier, RMPO No.",
        )

    playwright: Playwright | None = None
    search_started = False
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_multi_field_search_context(
            page,
            RMPO_SEARCH_SPEC,
            xpath,
            log,
        )
        fields = _resolve_multi_search_fields(frame, RMPO_SEARCH_SPEC)
        search_started = True
        _clear_multi_search_fields(fields)
        active_labels, last_field = _fill_multi_search_fields(
            fields,
            cleaned,
            active,
            RMPO_SEARCH_SPEC,
            log,
        )
        _submit_multi_search(last_field)
        _wait_module_search_settled(page, active_labels)
        # Một số phiên WFX thay document khi Enter. Resolve lại đúng RMPO List
        # trước khi đọc, không giữ frame của form search cũ.
        frame = _find_rmpo_frame(page)
        rows = _wait_rmpo_rows(frame, expected_values=cleaned)
        _write_log(
            log,
            "[RMPO] Đã đọc kết quả sau khi lọc; "
            f"rows={len(rows)}.",
        )
        if not rows:
            return _result(
                False,
                "RMPO_NO_RESULTS",
                "Không tìm thấy RMPO phù hợp.",
                module=RMPO_SEARCH_SPEC.module_name,
                rmpo_rows=[],
                result_count=0,
            )
        return _result(
            True,
            "RMPO_RESULTS_READY",
            f"Có {len(rows)} RMPO phù hợp; hãy chọn một dòng để thao tác.",
            module=RMPO_SEARCH_SPEC.module_name,
            filter_kinds=active,
            rmpo_rows=rows,
            result_count=len(rows),
        )
    except PlaywrightTimeoutError as exc:
        detail = _first_line(exc)
        if search_started:
            code = "MODULE_SEARCH_NOT_CONFIRMED"
            message = (
                "Đã nhập filter trong RMPO List, nhưng WFX chưa xác nhận "
                f"kết quả: {detail}"
            )
        else:
            code = "MODULE_SEARCH_NOT_READY"
            message = (
                "App đã tự mở RMPO List, nhưng các ô search chưa sẵn sàng: "
                f"{detail}"
            )
        _write_log(log, message)
        return _result(False, code, message, module=RMPO_SEARCH_SPEC.module_name)
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module=RMPO_SEARCH_SPEC.module_name)
        if boundary is not None:
            return boundary
        detail = f"{type(exc).__name__}: {_first_line(exc)}"
        message = f"Không thể tìm trong RMPO List: {detail}"
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_FAILED",
            message,
            module=RMPO_SEARCH_SPEC.module_name,
        )
    finally:
        if playwright is not None:
            playwright.stop()


_RMPO_ROWS_JS = """root => {
    const norm = value => String(value || '').replace(/\\s+/g, ' ').trim();
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && Number(style.opacity || 1) !== 0
            && rect.width > 0 && rect.height > 0;
    };
    const valueOf = cell => {
        if (!cell) return '';
        const control = cell.querySelector(
            'input[value], button, a, [title], img[alt]'
        );
        return norm(control?.value || control?.textContent
            || control?.getAttribute?.('title')
            || control?.getAttribute?.('alt') || cell.textContent || '');
    };
    const headerCells = [...document.querySelectorAll(
        '#gridRMPO_tblGridHeader th, #gridRMPO_tblGridHeader td'
    )];
    const metadata = cell => {
        const header = Number.isInteger(cell?.cellIndex)
            ? headerCells[cell.cellIndex] : null;
        return norm([
            cell?.id || '', cell?.getAttribute?.('title') || '',
            cell?.getAttribute?.('aria-label') || '', header?.id || '',
            header?.getAttribute?.('title') || '', header?.textContent || ''
        ].join(' ')).toLowerCase();
    };
    const field = (cells, ids, patterns) => {
        const exact = cells.find(cell => ids.includes(cell.id));
        const matched = exact || cells.find(cell =>
            patterns.some(pattern => pattern.test(metadata(cell)))
        );
        return valueOf(matched);
    };
    const rows = [...root.querySelectorAll('tr')]
        .filter(row => shown(row)
            && [...row.children].some(cell => cell.id === 'colOrderNo'))
        .map((row, index) => {
            const cells = [...row.children].filter(
                child => child.tagName === 'TD'
            );
            return {
                row_key: row.id || row.getAttribute('data-key')
                    || row.getAttribute('data-row-key') || String(index),
                status: field(cells, ['colStatus'], [/status/]),
                supplier: field(cells, [
                    'colSupplier', 'colSupplierName', 'colSupplierDesc',
                    'colVendor', 'colVendorName'
                ], [/supplier/, /vendor/]),
                order_no: field(cells, ['colOrderNo'], [
                    /order\\s*(no|number)/, /rmpo\\s*(no|number)?/
                ]),
                last_created: field(cells, [
                    'colLastCreated', 'colCreatedOn', 'colCreated'
                ], [/last\\s*created/, /created/]),
                qty: field(cells, ['colQty', 'colQuantity'], [
                    /\\bqty\\b/, /quantity/
                ]),
            };
        })
        .filter(row => row.order_no || row.supplier || row.status);
    const noRows = [...root.querySelectorAll(
        '.ag-overlay-no-rows-wrapper, .ag-overlay-no-rows-center, td, span, div'
    )].some(element => shown(element) && !element.children.length
        && /no records?|no data|không có dữ liệu/i.test(element.textContent || ''));
    const loading = [
        '.ag-overlay-loading-wrapper', '.ag-loading', '.blockUI',
        '.blockOverlay', '.ui-widget-overlay', '.loading', '.loader',
        '[aria-busy="true"]', '[id*="loading" i]', '[id*="progress" i]',
        '[class*="loading" i]', '[class*="progress" i]'
    ].some(selector =>
        [...document.querySelectorAll(selector)].some(shown)
    );
    return {rows, noRows, loading};
}"""


_CLICK_RMPO_CELL_JS = """(root, expected) => {
    const norm = value => String(value || '').replace(/\\s+/g, ' ').trim();
    const valueOf = cell => norm(
        cell?.querySelector('input[value], button, a, [title], img[alt]')?.value
        || cell?.querySelector('input[value], button, a, [title], img[alt]')?.textContent
        || cell?.querySelector('[title]')?.getAttribute('title')
        || cell?.querySelector('img[alt]')?.getAttribute('alt')
        || cell?.textContent || ''
    );
    const wantedKey = String(expected.row_key || '');
    const wantedOrder = norm(expected.order_no).toLowerCase();
    const rows = [...root.querySelectorAll('tr')].filter(row =>
        [...row.children].some(cell => cell.id === 'colOrderNo')
    );
    const row = rows.find((candidate, index) => {
        const key = candidate.id || candidate.getAttribute('data-key')
            || candidate.getAttribute('data-row-key') || String(index);
        const order = valueOf(
            [...candidate.children].find(cell => cell.id === 'colOrderNo')
        ).toLowerCase();
        return key === wantedKey && order === wantedOrder;
    });
    if (!row) return false;
    const cell = [...row.children].find(
        candidate => candidate.id === expected.column_id
    );
    if (!cell) return false;
    const control = cell.querySelector(
        'a, input[type="button"], button, [onclick]'
    );
    (control || cell).click();
    return true;
}"""


def _find_rmpo_frame(page: Page, timeout_s: float = 8) -> Frame:
    return _frame_with_visible_context(
        page,
        ", ".join(RMPO_SEARCH_SPEC.context_field.selectors),
        module_name=RMPO_SEARCH_SPEC.module_name,
        timeout_s=timeout_s,
    )


def _rmpo_grid(frame: Frame) -> Any | None:
    for selector in ("#gridRMPO_tblGridContent", "#gridRMPO"):
        try:
            grid = _first_visible(frame.locator(selector))
            if grid is not None:
                return grid
        except PlaywrightError:
            continue
    # Một số bản WFX chỉ render hai table Header/Content độc lập, không có
    # wrapper #gridRMPO. Khi các ô filter của RMPO đang hiện đúng context,
    # đọc từ body vẫn an toàn vì script chỉ nhận row có cell #colOrderNo.
    try:
        context = _first_visible(
            frame.locator(
                "#gridRMPO_tblGridHeader_trSearch_td_colOrderNo, "
                "#gridRMPO_tblGridHeader_trSearch_td_colSupplier"
            )
        )
        body = _first_visible(frame.locator("body"))
        if context is not None and body is not None:
            return body
    except PlaywrightError:
        pass
    return None


def _read_rmpo_rows(frame: Frame) -> tuple[list[dict[str, str]], bool, bool]:
    grid = _rmpo_grid(frame)
    if grid is None:
        raise PlaywrightTimeoutError("Không tìm thấy bảng gridRMPO.")
    payload = grid.evaluate(_RMPO_ROWS_JS)
    raw_rows = payload.get("rows") if isinstance(payload, dict) else []
    rows: list[dict[str, str]] = []
    for raw in raw_rows or []:
        if not isinstance(raw, dict):
            continue
        rows.append(
            {
                key: str(raw.get(key) or "").strip()
                for key in (
                    "row_key",
                    "status",
                    "supplier",
                    "order_no",
                    "last_created",
                    "qty",
                )
            }
        )
    if not isinstance(payload, dict):
        return rows, False, False
    return rows, bool(payload.get("noRows")), bool(payload.get("loading"))


def _wait_rmpo_rows(
    frame: Frame,
    timeout_s: float = 15,
    expected_values: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    deadline = time.monotonic() + timeout_s
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    while time.monotonic() < deadline:
        rows, no_rows, loading = _read_rmpo_rows(frame)
        key = tuple(
            (row["row_key"], row["order_no"], row["status"])
            for row in rows
        )
        expected = expected_values or {}
        filters_match = all(
            not str(expected.get(field) or "").strip()
            or all(
                str(expected[field]).strip().casefold()
                in row[field].casefold()
                for row in rows
            )
            for field in ("supplier", "order_no")
        )
        ready = not loading and (no_rows or (bool(rows) and filters_match))
        now = time.monotonic()
        if ready and key == stable_key:
            if now - stable_since >= 0.8:
                return rows
        else:
            stable_key = key
            stable_since = now
        _wait(frame, MODULE_GRID_POLL_MS)
    raise PlaywrightTimeoutError("Kết quả RMPO chưa ổn định.")


def _snapshot_browser_documents(browser: Any) -> tuple[set[int], list[tuple[Frame, tuple[Frame | None, str]]]]:
    pages = browser.contexts[0].pages
    page_ids = {id(page) for page in pages}
    snapshots: list[tuple[Frame, tuple[Frame | None, str]]] = []
    for page_index, candidate_page in enumerate(pages):
        for frame_index, frame in enumerate(candidate_page.frames):
            snapshots.append(
                (
                    frame,
                    _mark_document(
                        frame,
                        f"rmpo-action-{page_index}-{frame_index}",
                    ),
                )
            )
    return page_ids, snapshots


def _click_rmpo_cell(
    frame: Frame,
    row_key: str,
    order_no: str,
    column_id: str,
) -> bool:
    grid = _rmpo_grid(frame)
    if grid is None:
        return False
    return bool(
        grid.evaluate(
            _CLICK_RMPO_CELL_JS,
            {
                "row_key": row_key,
                "order_no": order_no,
                "column_id": column_id,
            },
        )
    )


def _wait_rmpo_revision_button(
    browser: Any,
    page_ids: set[int],
    snapshots: list[tuple[Frame, tuple[Frame | None, str]]],
    timeout_s: float = 180,
) -> Any:
    selector = 'xpath=//*[@id="titlebarRMPO"]/tbody/tr/td[2]/span/div[9]'
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        current_frames = [
            frame
            for page in reversed(browser.contexts[0].pages)
            for frame in page.frames
        ]
        old_snapshots = {id(frame): snapshot for frame, snapshot in snapshots}
        for frame in current_frames:
            snapshot = old_snapshots.get(id(frame))
            changed = (
                id(frame.page) not in page_ids
                or snapshot is None
                or _document_changed(frame, snapshot)
            )
            if not changed:
                continue
            try:
                button = _first_visible(frame.locator(selector))
                if button is not None:
                    return button
            except PlaywrightError:
                continue
        _wait(current_frames[0] if current_frames else None, 100)
    raise PlaywrightTimeoutError(
        "Nút Revise chưa xuất hiện sau 3 phút."
    )


def open_rmpo_result_action(
    row_key: str,
    order_no: str,
    supplier: str,
    expected_status: str,
    action: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở đúng cột của RMPO đã chọn và hỗ trợ bước Revise."""
    definitions = {
        "check_po": ("colOCNo", "RMPO_PO_OPENED", "Đã mở OC No. của RMPO."),
        "edit_po": ("colOrderNo", "RMPO_REVISE_CLICKED", "Đã bấm Revise cho RMPO."),
        "check_received": (
            "colRecv",
            "RMPO_RECEIVED_OPENED",
            "Đã mở thông tin nhận kho của RMPO.",
        ),
    }
    if action not in definitions:
        return _result(
            False,
            "RMPO_ACTION_INVALID",
            "Thao tác RMPO không hợp lệ.",
        )
    if action == "check_received" and _normalise_search_text(
        expected_status
    ) not in {"received", "part received"}:
        return _result(
            False,
            "RMPO_ACTION_INVALID",
            "RMPO chưa có trạng thái Received hoặc Part Received.",
        )

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        frame = _find_rmpo_frame(page)
        rows = _wait_rmpo_rows(frame, timeout_s=4)
        selected = next(
            (
                row
                for row in rows
                if row["row_key"] == str(row_key or "")
                and row["order_no"].casefold()
                == str(order_no or "").strip().casefold()
                and row["supplier"].casefold()
                == str(supplier or "").strip().casefold()
                and row["status"].casefold()
                == str(expected_status or "").strip().casefold()
            ),
            None,
        )
        if selected is None:
            return _result(
                False,
                "RMPO_RESULT_EXPIRED",
                "Dòng hoặc Status RMPO đã thay đổi. Hãy tìm lại.",
            )
        column_id, code, message = definitions[action]
        page_ids, snapshots = _snapshot_browser_documents(browser)
        if not _click_rmpo_cell(
            frame,
            selected["row_key"],
            selected["order_no"],
            column_id,
        ):
            return _result(
                False,
                "RMPO_RESULT_EXPIRED",
                "Không còn tìm thấy cột cần mở trên dòng RMPO đã chọn.",
            )
        _write_log(
            log,
            f"[RMPO] Đã click {column_id} của dòng được chọn.",
        )
        if action == "edit_po":
            revise = _wait_rmpo_revision_button(
                browser,
                page_ids,
                snapshots,
                timeout_s=180,
            )
            _click(revise)
            _write_log(log, "[RMPO] Đã click Revise trên cửa sổ RMPO.")
        else:
            # Hai action read-only hoàn tất tại exact click. WFX có thể mở
            # popup mới, tái dùng popup cùng tên hoặc hiển thị nội dung ngay
            # trong document hiện tại, nên không ép một kiểu navigation duy nhất.
            _wait(page, 300)
        return _result(
            True,
            code,
            message,
            order_no=selected["order_no"],
            status=selected["status"],
            action=action,
        )
    except PlaywrightTimeoutError as exc:
        message = f"RMPO chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "RMPO_ACTION_NOT_READY", message, module="RMPO List")
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module="RMPO List")
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "MODULE_FAILED", message, module="RMPO List")
    finally:
        if playwright is not None:
            playwright.stop()
