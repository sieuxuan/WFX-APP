"""Sample List: tìm, chọn dòng và quét file đính kèm của Style."""

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
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules.constants import MODULE_GRID_POLL_MS
from wfx_panel.automation.modules.inputs import (
    _apply_module_search,
    _search_input_in_frame,
    _search_input_in_frames,
)
from wfx_panel.automation.modules.menu import _active_wfx_page
from wfx_panel.automation.modules.search import (
    _clear_list_search_fields,
    _open_list_search_context,
)
from wfx_panel.automation.search_specs import SAMPLE_SEARCH_SPEC

_SAMPLE_RESULT_ROWS_JS = """root => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none'
            && style.visibility !== 'hidden'
            && Number(style.opacity || 1) !== 0
            && rect.width > 0 && rect.height > 0;
    };
    const directText = element => String(
        element?.value
        || element?.getAttribute?.('value')
        || element?.textContent
        || element?.title
        || element?.getAttribute?.('aria-label')
        || ''
    ).replace(/\\s+/g, ' ').trim();
    const text = element => {
        if (!element) return '';
        const direct = directText(element);
        if (direct) return direct;
        const nested = element.querySelector?.(
            'input[value], button, a, [title], [aria-label]'
        );
        return directText(nested);
    };
    const cellMetadata = cell => {
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
    const styleAction = row => {
        const candidates = [...row.querySelectorAll(
            'input[type="button"], button, a, [onclick]'
        )].filter(shown);
        let best = null;
        let bestScore = 0;
        for (const candidate of candidates) {
            const cell = candidate.closest('[role="gridcell"], .ag-cell, td');
            const metadata = [
                cellMetadata(cell),
                candidate.id || '',
                candidate.name || '',
                candidate.getAttribute('aria-label') || '',
                candidate.getAttribute('title') || '',
            ].join(' ').toLowerCase();
            let score = 0;
            if (/buyer\\s*style|style\\s*code/.test(metadata)) score += 30;
            if (/style/.test(metadata)) score += 18;
            if (/article/.test(metadata)) score += 12;
            if (/sample\\s*(order)?\\s*(no|number)/.test(metadata)) score -= 40;
            if (text(candidate)) score += 2;
            if (score > bestScore) {
                best = candidate;
                bestScore = score;
            }
        }
        return best;
    };
    const fieldText = (row, patterns) => {
        const cells = [...row.querySelectorAll('[role="gridcell"], .ag-cell, td')];
        const cell = cells.find(candidate => {
            const metadata = cellMetadata(candidate);
            return patterns.some(pattern => pattern.test(metadata));
        });
        return text(cell);
    };
    const rowNodes = [...root.querySelectorAll(
        '.ag-row[row-index], [role="row"][row-index]'
    )].filter(row => shown(row)
        && !row.classList.contains('ag-row-loading')
        && !row.classList.contains('ag-row-ghost')
        && row.getAttribute('aria-hidden') !== 'true');
    const uniqueRows = [];
    const grouped = new Map();
    rowNodes.forEach((row, index) => {
        const rowKey = row.getAttribute('row-id')
            || row.getAttribute('row-index') || String(index);
        if (!grouped.has(rowKey)) grouped.set(rowKey, []);
        grouped.get(rowKey).push(row);
    });
    grouped.forEach((rowParts, rowKey) => {
        const row = rowParts[0];
        const action = rowParts.map(styleAction).find(Boolean);
        const groupedFieldText = patterns => {
            for (const part of rowParts) {
                const value = fieldText(part, patterns);
                if (value) return value;
            }
            return '';
        };
        uniqueRows.push({
            row_key: rowKey,
            row_index: row.getAttribute('row-index') || '',
            style_code: text(action),
            sample_no: groupedFieldText([
                /sample\\s*(order)?\\s*(no|number)/,
                /sampleorder(no|number)/,
            ]),
            created_by: groupedFieldText([/created\\s*by/, /createdby/]),
            buyer: groupedFieldText([
                /buyer\\s*(name|company)?$/,
                /buyer(name|company)/,
            ]),
        });
    });
    const noRows = [...root.querySelectorAll(
        '.ag-overlay-no-rows-wrapper, .ag-overlay-no-rows-center'
    )].some(shown);
    return {
        rows: uniqueRows,
        noRows,
        totalRows: uniqueRows.length,
    };
}"""


_CLICK_SAMPLE_STYLE_JS = """(row, expectedCode) => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const text = element => String(
        element?.value || element?.textContent || element?.title || ''
    ).replace(/\\s+/g, ' ').trim();
    const expected = String(expectedCode || '').trim().toLowerCase();
    let best = null;
    let bestScore = -100;
    for (const candidate of row.querySelectorAll(
        'input[type="button"], button, a, [onclick]'
    )) {
        if (!shown(candidate)) continue;
        const cell = candidate.closest('[role="gridcell"], .ag-cell, td');
        const metadata = [
            cell?.getAttribute('col-id') || '',
            cell?.getAttribute('aria-label') || '',
            candidate.id || '',
            candidate.name || '',
            candidate.getAttribute('aria-label') || '',
            candidate.getAttribute('title') || '',
        ].join(' ').toLowerCase();
        const value = text(candidate);
        let score = value.toLowerCase() === expected ? 100 : 0;
        if (/buyer\\s*style|style\\s*code/.test(metadata)) score += 30;
        if (/style/.test(metadata)) score += 18;
        if (/article/.test(metadata)) score += 12;
        if (/sample\\s*(order)?\\s*(no|number)/.test(metadata)) score -= 40;
        if (score > bestScore) {
            best = candidate;
            bestScore = score;
        }
    }
    if (!best || (expected && text(best).toLowerCase() !== expected)) return '';
    const value = text(best);
    best.click();
    return value;
}"""


def _sample_result_grid(
    frame: Frame,
    timeout_s: float = 12,
) -> tuple[Any, dict[str, Any]]:
    """Đọc đúng grid Sample đã lọc và chờ số dòng ổn định."""
    deadline = time.monotonic() + timeout_s
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        best: tuple[Any, dict[str, Any]] | None = None
        try:
            roots = frame.locator(".ag-root-wrapper")
            for index in range(roots.count()):
                root = roots.nth(index)
                if not root.is_visible():
                    continue
                payload = root.evaluate(_SAMPLE_RESULT_ROWS_JS)
                score = (
                    int(payload.get("totalRows") or 0),
                    len(payload.get("rows") or []),
                    int(bool(payload.get("noRows"))),
                )
                if best is None or score > (
                    int(best[1].get("totalRows") or 0),
                    len(best[1].get("rows") or []),
                    int(bool(best[1].get("noRows"))),
                ):
                    best = (root, payload)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            last_error = exc
            _wait(frame, MODULE_GRID_POLL_MS)
            continue
        if best is None:
            _wait(frame, MODULE_GRID_POLL_MS)
            continue
        payload = best[1]
        key = (
            int(payload.get("totalRows") or 0),
            len(payload.get("rows") or []),
            bool(payload.get("noRows")),
        )
        ready = bool(payload.get("rows")) or bool(payload.get("noRows"))
        now = time.monotonic()
        if ready and key == stable_key:
            if now - stable_since >= 0.8:
                return best
        else:
            stable_key = key
            stable_since = now
        _wait(frame, MODULE_GRID_POLL_MS)
    raise PlaywrightTimeoutError(
        "Kết quả Sample chưa ổn định; "
        f"lastError={last_error or ''}"
    )


def _click_sample_style_result(
    frame: Frame,
    row_key: str,
    style_code: str,
    log: Callable[[str], None],
) -> bool:
    root, payload = _sample_result_grid(frame, timeout_s=4)
    expected_key = str(row_key or "")
    expected_code = str(style_code or "").strip()
    rows = root.locator(
        ".ag-row[row-index], [role='row'][row-index]"
    )
    for index in range(rows.count()):
        row = rows.nth(index)
        try:
            current_key = (
                row.get_attribute("row-id")
                or row.get_attribute("row-index")
                or str(index)
            )
            if current_key != expected_key:
                continue
            clicked_code = str(
                row.evaluate(_CLICK_SAMPLE_STYLE_JS, expected_code) or ""
            ).strip()
            if clicked_code.casefold() != expected_code.casefold():
                continue
            _write_log(
                log,
                f"[SAMPLE FILE] Đã click Style Code {clicked_code}.",
            )
            return True
        except PlaywrightError:
            continue
    _write_log(
        log,
        "[SAMPLE FILE] Dòng đã chọn không còn trong kết quả hiện tại; "
        f"renderedRows={len(payload.get('rows') or [])}.",
    )
    return False


def _sample_file_result(
    frame: Frame,
    log: Callable[[str], None],
) -> dict[str, Any]:
    _root, payload = _sample_result_grid(frame)
    rows = [
        row for row in payload.get("rows") or []
        if isinstance(row, dict)
    ]
    total_rows = max(int(payload.get("totalRows") or 0), len(rows))
    _write_log(
        log,
        "[SAMPLE FILE] Đã đọc kết quả Sample; "
        f"totalRows={total_rows}; renderedRows={len(rows)}.",
    )
    if not rows:
        return _result(
            False,
            "NO_RESULTS",
            "Không tìm thấy Sample phù hợp để kiểm tra file.",
            samples=[],
        )
    usable = [row for row in rows if str(row.get("style_code") or "").strip()]
    if not usable:
        return _result(
            False,
            "SAMPLE_STYLE_NOT_FOUND",
            "Kết quả Sample không có Style Code có thể mở.",
        )
    if total_rows > 1 or len(rows) > 1:
        # `result_count` là số dòng người dùng bấm được, không phải số dòng
        # grid trả về: dòng không có Style Code không vào danh sách, nên đếm
        # theo `total_rows` sẽ hiện "3 kết quả" cho một danh sách chỉ có một
        # dòng chọn được. Chênh lệch phải nói rõ trong message.
        message = f"Có {len(usable)} kết quả; chọn Sample cần kiểm tra file."
        if len(usable) < total_rows:
            message = (
                f"Có {total_rows} kết quả, {len(usable)} dòng mở được Style "
                "Code; chọn Sample cần kiểm tra file."
            )
        return _result(
            True,
            "SAMPLE_MULTIPLE_RESULTS",
            message,
            samples=usable[:20],
            result_count=len(usable),
        )
    selected = usable[0]
    if not _click_sample_style_result(
        frame,
        str(selected.get("row_key") or ""),
        str(selected.get("style_code") or ""),
        log,
    ):
        return _result(
            False,
            "SAMPLE_RESULT_EXPIRED",
            "Dòng Sample vừa thay đổi trước khi mở Style Code. Hãy thử lại.",
        )
    article_code = str(selected.get("style_code") or "").strip()
    return _result(
        True,
        "SAMPLE_STYLE_OPENED",
        f"Đã mở Style Code {article_code} từ Sample List.",
        article_code=article_code,
    )


def _sample_filter_values(
    values: Mapping[str, str],
) -> tuple[dict[str, str], list[str]]:
    cleaned = {
        field_name: str(values.get(field_name) or "").strip()
        for field_name in SAMPLE_SEARCH_SPEC.fields
    }
    return cleaned, [
        field_name for field_name, value in cleaned.items() if value
    ]


def _apply_sample_filters(
    page: Page,
    frame: Frame,
    cleaned_values: Mapping[str, str],
    active_fields: list[str],
    log: Callable[[str], None],
) -> list[str]:
    """Áp dụng filter Sample lần lượt để hỗ trợ các cột bị cuộn ngang."""
    _clear_list_search_fields(
        frame,
        SAMPLE_SEARCH_SPEC.field_selectors,
        scan_horizontal=SAMPLE_SEARCH_SPEC.requires_floating_filter,
    )
    _wait(page, 250)
    labels: list[str] = []
    for field_name in active_fields:
        field_spec = SAMPLE_SEARCH_SPEC.fields[field_name]
        field = _search_input_in_frame(
            page,
            frame,
            field_spec.selectors,
            field_spec.aliases,
            timeout_s=8,
            scan_horizontal=SAMPLE_SEARCH_SPEC.requires_floating_filter,
        )
        _apply_module_search(
            page,
            field,
            cleaned_values[field_name],
            field_spec.label,
            log,
        )
        labels.append(field_spec.label)
    return labels


def search_sample_list_with_filters(
    xpath: str,
    values: Mapping[str, str],
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Tìm Sample theo một hoặc nhiều filter trên Floating Filter."""
    cleaned_values, active_fields = _sample_filter_values(values)
    if not active_fields:
        labels = ", ".join(
            field_spec.label for field_spec in SAMPLE_SEARCH_SPEC.fields.values()
        )
        return _result(
            False,
            "QUERY_REQUIRED",
            f"Vui lòng nhập ít nhất một điều kiện: {labels}.",
        )
    playwright: Playwright | None = None
    search_started = False
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_list_search_context(page, SAMPLE_SEARCH_SPEC, xpath, log)
        search_started = True
        labels = _apply_sample_filters(
            page,
            frame,
            cleaned_values,
            active_fields,
            log,
        )
        return _result(
            True,
            "MODULE_SEARCH_APPLIED",
            f"Đã lọc Sample List theo {', '.join(labels)}.",
            module="Sample List",
            filter_kinds=active_fields,
        )
    except PlaywrightTimeoutError as exc:
        detail = _first_line(exc)
        code = (
            "MODULE_SEARCH_NOT_CONFIRMED"
            if search_started
            else "MODULE_SEARCH_NOT_READY"
        )
        message = f"Chưa thể tìm nhiều điều kiện trong Sample List: {detail}"
        _write_log(log, message)
        return _result(False, code, message, module="Sample List")
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module="Sample List")
        if boundary is not None:
            return boundary
        message = f"Không thể tìm Sample List: {type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "MODULE_SEARCH_FAILED", message, module="Sample List")
    finally:
        if playwright is not None:
            playwright.stop()


def find_sample_file_results_with_filters(
    xpath: str,
    values: Mapping[str, str],
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Dùng cùng filter đa điều kiện của Sample trước khi quét file."""
    cleaned_values, active_fields = _sample_filter_values(values)
    if not active_fields:
        labels = ", ".join(
            field_spec.label for field_spec in SAMPLE_SEARCH_SPEC.fields.values()
        )
        return _result(
            False,
            "QUERY_REQUIRED",
            f"Vui lòng nhập ít nhất một điều kiện: {labels}.",
        )
    playwright: Playwright | None = None
    search_started = False
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_list_search_context(page, SAMPLE_SEARCH_SPEC, xpath, log)
        search_started = True
        _apply_sample_filters(
            page,
            frame,
            cleaned_values,
            active_fields,
            log,
        )
        return _sample_file_result(frame, log)
    except PlaywrightTimeoutError as exc:
        detail = _first_line(exc)
        code = (
            "MODULE_SEARCH_NOT_CONFIRMED"
            if search_started
            else "MODULE_SEARCH_NOT_READY"
        )
        message = f"Chưa thể kiểm tra file từ Sample List: {detail}"
        _write_log(log, message)
        return _result(False, code, message, module="Sample List")
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module="Sample List")
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(
            False,
            "SAMPLE_FILE_SEARCH_FAILED",
            message,
            module="Sample List",
        )
    finally:
        if playwright is not None:
            playwright.stop()


def open_sample_file_result(
    row_key: str,
    style_code: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Tiếp tục từ grid Sample đang giữ sau khi user chọn một kết quả."""
    row_key = str(row_key or "").strip()
    style_code = str(style_code or "").strip()
    if not row_key or not style_code:
        return _result(
            False,
            "SAMPLE_RESULT_EXPIRED",
            "Lựa chọn Sample đã hết hiệu lực. Hãy bấm Xem file đính kèm lại.",
        )
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        # Grid vẫn đang mở, chỉ cần nhận lại context. Phải quét ngang như mọi
        # lối vào Sample khác: mỗi tài khoản kéo cột một kiểu nên cột Sample
        # Order No. có thể đang nằm ngoài viewport, và khi đó AG Grid không
        # render ô filter — bỏ quét ngang sẽ báo nhầm là lựa chọn hết hiệu lực.
        frame, _field = _search_input_in_frames(
            page,
            SAMPLE_SEARCH_SPEC.context_field.selectors,
            SAMPLE_SEARCH_SPEC.context_field.aliases,
            timeout_s=2,
            scan_horizontal=SAMPLE_SEARCH_SPEC.requires_floating_filter,
            module_name=SAMPLE_SEARCH_SPEC.module_name,
        )
        if not _click_sample_style_result(frame, row_key, style_code, log):
            return _result(
                False,
                "SAMPLE_RESULT_EXPIRED",
                "Kết quả Sample đã thay đổi. Hãy bấm Xem file đính kèm lại.",
            )
        return _result(
            True,
            "SAMPLE_STYLE_OPENED",
            f"Đã mở Style Code {style_code} từ Sample List.",
            article_code=style_code,
        )
    except (PlaywrightTimeoutError, PlaywrightError):
        return _result(
            False,
            "SAMPLE_RESULT_EXPIRED",
            "Sample List hoặc dòng đã chọn không còn mở. Hãy bấm Xem file đính kèm lại.",
        )
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module="Sample List")
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SAMPLE_FILE_OPEN_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
