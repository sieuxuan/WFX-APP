"""Điền 7 cột Order Details và giữ grid đồng bộ với file."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    PlaywrightError,
    PlaywrightTimeoutError,
    _domain_error_code,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules import _active_wfx_page
from wfx_panel.automation.sale_asn_create.constants import (
    ADD_ORDER_XPATH,
    ORDER_FIELD_COLUMNS,
    ORDER_GRID_SELECTOR,
    ORDER_GRID_SYNC_TIMEOUT_SECONDS,
    PO_POPUP_RECOVERY_TIMEOUT_SECONDS,
    PO_POPUP_SELECTOR,
    SALE_ASN_PO_SEARCH_FIELDS,
)
from wfx_panel.automation.sale_asn_create.errors import _POSelectionRequired
from wfx_panel.automation.sale_asn_create.form import _frame_with_selector
from wfx_panel.automation.sale_asn_create.po import (
    _auto_add_po_with_frame_retry,
    _click_dom_action,
)
from wfx_panel.automation.sale_asn_create.progress import _emit_stage_progress
from wfx_panel.automation.sale_asn_create.values import (
    _date_for_wfx,
    _fold,
    _number_for_wfx,
    _table_value_matches,
)

_MARK_ORDER_GRID_CELL_JS = r"""spec => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const fold = value => clean(value).toLocaleLowerCase('en')
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, ' ').trim();
    const table = document.querySelector(spec.table);
    if (!table) return {ok: false, reason: 'order-grid-not-found'};
    const cellText = cell => clean(
        cell?.querySelector('.clsGridLabelContent, span')?.getAttribute('title')
        || cell?.getAttribute('title')
        || cell?.textContent
    );
    const matchesStyle = (wantedStyle, actualStyle) => {
        if (!wantedStyle || !actualStyle) return false;
        if (wantedStyle === actualStyle) return true;
        return (` ${actualStyle} `).includes(` ${wantedStyle} `)
            || (` ${wantedStyle} `).includes(` ${actualStyle} `);
    };
    const wanted = fold(spec.po_no);
    const wantedStyle = fold(spec.style_no);
    const rows = [...table.querySelectorAll('tr.trContent')];
    const poCandidates = rows.filter(row =>
        fold(row.querySelector('#colOrderRefNum')?.textContent) === wanted
    );
    const candidates = poCandidates.length > 1 && wantedStyle
        ? poCandidates.filter(row => {
            const styleCell = row.querySelector(
                'td#colStyle, td#colStyleNo, td#colBuyerStyleRef, td[id*="Style"]'
            );
            return matchesStyle(wantedStyle, fold(cellText(styleCell)));
        })
        : poCandidates;
    if (candidates.length !== 1) {
        return {ok: false, reason: 'row-ambiguous', count: candidates.length};
    }
    const cell = [...candidates[0].children]
        .find(item => item.id === spec.column_id);
    if (!cell) return {ok: false, reason: 'cell-not-found'};
    document.querySelectorAll('[data-wfx-sale-asn-target]').forEach(item =>
        item.removeAttribute('data-wfx-sale-asn-target'));
    cell.setAttribute('data-wfx-sale-asn-target', '1');
    return {ok: true, row_id: candidates[0].id, column_id: cell.id};
}"""


_READ_ORDER_DETAILS_JS = r"""spec => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const table = document.querySelector(spec.table);
    if (!table) return [];
    const readCell = cell => {
        if (!cell) return '';
        const editor = cell.querySelector(
            'input:not([type="hidden"]), textarea, [contenteditable="true"]'
        );
        if (editor) return clean(editor.value || editor.textContent);
        const label = cell.querySelector(
            '.lblEditable, .lblEditDatePicker, .clsGridLabelContent, span'
        );
        return clean(
            label?.getAttribute('title') || label?.textContent || cell.textContent
        );
    };
    return [...table.querySelectorAll('tr.trContent')].map(row => {
        const output = {
            po_no: readCell(row.querySelector('td#colOrderRefNum')),
        };
        Object.entries(spec.columns || {}).forEach(([key, columnId]) => {
            output[key] = readCell(
                [...row.children].find(cell => cell.id === columnId)
            );
        });
        return output;
    }).filter(row => row.po_no);
}"""


def _edit_marked_table_cell(frame: Frame, value: str) -> str:
    target = frame.locator("[data-wfx-sale-asn-target='1']").first
    target.scroll_into_view_if_needed(timeout=3_000)
    editor = target.locator(
        "input:not([type='hidden']), textarea, [contenteditable='true']"
    ).first
    if not editor.count():
        action = target.locator(
            ".lblEditable, .lblEditDatePicker, [contenteditable='true']"
        ).first
        if not action.count():
            raise RuntimeError("SALE_ASN_FIELD_NOT_EDITABLE:editor-not-found")
        action.click(timeout=3_000)
        editor = target.locator(
            "input:not([type='hidden']), textarea, [contenteditable='true']"
        ).first
    editor.wait_for(state="visible", timeout=3_000)
    editor.fill(value, timeout=3_000)
    editor.press("Tab", timeout=3_000)

    deadline = time.monotonic() + 3
    actual = ""
    while time.monotonic() < deadline:
        actual = str(
            target.evaluate(
                """cell => {
                    const editor = cell.querySelector(
                        'input:not([type="hidden"]), textarea, [contenteditable="true"]'
                    );
                    if (editor) return editor.value || editor.textContent || '';
                    const label = cell.querySelector(
                        '.lblEditable, .lblEditDatePicker, .clsGridLabelContent'
                    );
                    return label?.getAttribute('title')
                        || label?.textContent || cell.textContent || '';
                }"""
            )
            or ""
        ).strip()
        if _table_value_matches(value, actual):
            return actual
        _wait(frame, 120)
    raise RuntimeError(f"SALE_ASN_FIELD_VALUE_NOT_CONFIRMED:{actual}")


def _set_order_grid_cell(
    frame: Frame,
    po_no: str,
    style_no: str,
    column_id: str,
    value: str,
) -> None:
    marked = frame.evaluate(
        _MARK_ORDER_GRID_CELL_JS,
        {
            "table": ORDER_GRID_SELECTOR,
            "po_no": po_no,
            "style_no": style_no,
            "column_id": column_id,
        },
    )
    if not marked.get("ok"):
        raise RuntimeError(f"SALE_ASN_TABLE_MAPPING_FAILED:{marked.get('reason')}")
    _edit_marked_table_cell(frame, value)


def _order_row_identity(row: dict) -> tuple[str, str]:
    return _fold(row.get("po_no")), _fold(row.get("style_no"))


def _order_style_matches(wanted: str, actual: str) -> bool:
    if not wanted or not actual:
        return False
    if wanted == actual:
        return True
    return f" {wanted} " in f" {actual} " or f" {actual} " in f" {wanted} "


def _order_row_is_present(
    row: dict,
    present: set[str | tuple[str, str]],
) -> bool:
    po_key, style_key = _order_row_identity(row)
    if (po_key, style_key) in present or po_key in present:
        return True
    if not style_key:
        return any(
            isinstance(item, tuple) and item[0] == po_key
            for item in present
        )
    return any(
        isinstance(item, tuple)
        and item[0] == po_key
        and _order_style_matches(style_key, item[1])
        for item in present
    )


def _missing_order_rows(
    rows: Sequence[dict],
    present: set[str | tuple[str, str]],
) -> list[dict]:
    return [
        dict(row)
        for row in rows
        if _fold(row.get("po_no")) and not _order_row_is_present(row, present)
    ]


def _wait_order_grid(
    frame: Frame,
    rows: Sequence[dict],
    timeout_s: float = ORDER_GRID_SYNC_TIMEOUT_SECONDS,
    *,
    allow_incomplete: bool = False,
) -> set[tuple[str, str]]:
    table = frame.locator(ORDER_GRID_SELECTOR).first
    table.wait_for(state="visible", timeout=int(timeout_s * 1_000))
    expected = [dict(row) for row in rows if _fold(row.get("po_no"))]
    deadline = time.monotonic() + timeout_s
    present: set[tuple[str, str]] = set()
    while time.monotonic() < deadline:
        try:
            present = {
                _order_row_identity(item)
                for item in (
                    table.evaluate(
                        """root => [...root.querySelectorAll('tr.trContent')]
                            .map(row => {
                                const read = cell => String(
                                    cell?.querySelector('.clsGridLabelContent, span')
                                        ?.getAttribute('title')
                                    || cell?.getAttribute('title')
                                    || cell?.textContent || ''
                                ).trim();
                                return {
                                    po_no: read(row.querySelector('#colOrderRefNum')),
                                    style_no: read(row.querySelector(
                                        'td#colStyle, td#colStyleNo, '
                                        + 'td#colBuyerStyleRef, td[id*="Style"]'
                                    )),
                                };
                            })"""
                    )
                    or []
                )
                if _fold(item.get("po_no"))
            }
        except PlaywrightError:
            # Grid WFX có thể thay tbody khi request Add Order hoàn tất. Locator
            # vẫn resolve lại được ở vòng poll kế tiếp.
            present = set()
        if expected and not _missing_order_rows(expected, present):
            return present
        _wait(frame, 120)
    if allow_incomplete:
        return present
    raise RuntimeError("SALE_ASN_ORDER_GRID_NOT_READY")


def _ensure_po_popup_for_next_row(
    context: Any,
    added_rows: Sequence[dict],
    log: Callable[[str], None],
) -> Frame:
    """Giữ flow chạy tiếp nếu WFX tự đóng popup sau Add & Continue."""

    try:
        _popup_page, popup_frame = _frame_with_selector(
            context,
            PO_POPUP_SELECTOR,
            timeout_s=2,
        )
        return popup_frame
    except PlaywrightTimeoutError:
        pass

    _main_page, main_frame = _frame_with_selector(
        context,
        "#sectionOrderDetails",
        timeout_s=PO_POPUP_RECOVERY_TIMEOUT_SECONDS,
    )
    # Chỉ mở lại sau khi các dòng vừa chọn đã thật sự vào grid; nếu request WFX
    # còn chạy thì bước chờ này ngăn click Add chồng lên postback cũ.
    _write_log(
        log,
        "[SALE ASN] Add & Continue đang được WFX ghi nhận; "
        "đang chờ Order Details cập nhật...",
    )
    _wait_order_grid(
        main_frame,
        added_rows,
        timeout_s=ORDER_GRID_SYNC_TIMEOUT_SECONDS,
    )
    add = main_frame.locator(f"xpath={ADD_ORDER_XPATH}").first
    _click_dom_action(add)
    _popup_page, popup_frame = _frame_with_selector(
        context,
        PO_POPUP_SELECTOR,
        timeout_s=PO_POPUP_RECOVERY_TIMEOUT_SECONDS,
    )
    _write_log(
        log,
        (
            "[SALE ASN] WFX đã đóng popup sau Add & Continue; đã xác nhận "
            f"{len(added_rows)} dòng và đã mở lại Add Order Details."
        ),
    )
    return popup_frame


def _ensure_order_grid_rows(
    context: Any,
    main_frame: Frame,
    rows: Sequence[dict],
    log: Callable[[str], None],
    search_fields: Sequence[str] = SALE_ASN_PO_SEARCH_FIELDS,
) -> Frame:
    """Xác nhận PO đã vào grid và phục hồi đúng các dòng bị rơi khi đóng popup."""

    _write_log(
        log,
        "[SALE ASN] Đang chờ WFX xác nhận các PO trong Order Details...",
    )
    present = _wait_order_grid(
        main_frame,
        rows,
        timeout_s=ORDER_GRID_SYNC_TIMEOUT_SECONDS,
        allow_incomplete=True,
    )
    missing = _missing_order_rows(rows, present)
    if not missing:
        return main_frame

    _write_log(
        log,
        (
            f"[SALE ASN] Order Details còn thiếu {len(missing)} PO sau khi đóng "
            "Add Order Details; đang thêm lại đúng các PO còn thiếu."
        ),
    )
    try:
        _popup_page, popup_frame = _frame_with_selector(
            context,
            PO_POPUP_SELECTOR,
            timeout_s=0.8,
        )
    except PlaywrightTimeoutError:
        add = main_frame.locator(f"xpath={ADD_ORDER_XPATH}").first
        _click_dom_action(add)
        _popup_page, popup_frame = _frame_with_selector(
            context,
            PO_POPUP_SELECTOR,
            timeout_s=PO_POPUP_RECOVERY_TIMEOUT_SECONDS,
        )

    for index, row in enumerate(missing):
        final = index == len(missing) - 1
        added, candidates, reason, popup_frame = _auto_add_po_with_frame_retry(
            context,
            popup_frame,
            row,
            log,
            final=final,
            search_fields=search_fields,
        )
        if not added:
            # Popup vẫn đang mở và đang chờ user chọn dòng. Trả đúng trạng thái
            # chờ thay vì lỗi kỹ thuật; lượt Tiếp tục sẽ tự dò lại PO còn thiếu.
            raise _POSelectionRequired(row, candidates, reason, final=final)

    _main_page, refreshed_frame = _frame_with_selector(
        context,
        "#sectionOrderDetails",
        timeout_s=PO_POPUP_RECOVERY_TIMEOUT_SECONDS,
    )
    _wait_order_grid(
        refreshed_frame,
        rows,
        timeout_s=ORDER_GRID_SYNC_TIMEOUT_SECONDS,
    )
    _write_log(log, "[SALE ASN] Đã xác nhận đủ PO trong Order Details.")
    return refreshed_frame


def _fill_order_details(
    frame: Frame,
    rows: Sequence[dict],
    log: Callable[[str], None],
    progress: Callable[..., None] | None = None,
) -> None:
    for index, row in enumerate(rows, 1):
        _emit_stage_progress(
            progress,
            "order_details",
            f"Order Details {index}/{len(rows)}",
        )
        for key, column_id in ORDER_FIELD_COLUMNS.items():
            value = str(row.get(key) or "").strip()
            if not value:
                continue
            if key == "cargo_ready_date":
                value = _date_for_wfx(value)
            else:
                value = _number_for_wfx(value, integer=key == "carton")
            _set_order_grid_cell(
                frame,
                str(row.get("po_no") or ""),
                str(row.get("style_no") or ""),
                column_id,
                value,
            )
        _write_log(log, f"[SALE ASN] Đã điền Order Details cho {row.get('po_no')}.")


def scan_sale_asn_order_details(
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Đọc các PO và giá trị Order Details trên form Sale ASN đang mở."""

    playwright = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        _main_page, frame = _frame_with_selector(
            page.context,
            ORDER_GRID_SELECTOR,
            timeout_s=15,
        )
        rows = frame.evaluate(
            _READ_ORDER_DETAILS_JS,
            {"table": ORDER_GRID_SELECTOR, "columns": ORDER_FIELD_COLUMNS},
        )
        if not rows:
            raise RuntimeError("SALE_ASN_ORDER_GRID_EMPTY")
        _write_log(
            log,
            f"[SALE ASN] Đã đọc {len(rows)} PO từ Order Details đang mở.",
        )
        return _result(
            True,
            "SALE_ASN_ORDER_DETAILS_SCANNED",
            f"Đã đọc {len(rows)} PO. Chọn nơi lưu form Order Details.",
            rows=rows,
            po_count=len(rows),
        )
    except RuntimeError as error:
        code = _domain_error_code(error, "SALE_ASN_ORDER_SCAN_FAILED")
        message = f"Không xuất được Order Details: {_first_line(error)}"
        _write_log(log, message)
        return _result(False, code, message)
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        message = f"Order Details chưa sẵn sàng: {_first_line(error)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_ORDER_SCAN_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
