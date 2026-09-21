"""Tìm và thêm PO trong popup Add Order Details.

Search PO của WFX là tìm chứa chuỗi nên kết quả phải lọc lại theo PO No. exact
trước khi chọn: 779 không được nhận 779A. PO cuối dùng link OK bên
trong cell action, các PO trước dùng Add & Continue."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    PlaywrightError,
    PlaywrightTimeoutError,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.sale_asn_create.constants import (
    PO_CONTINUE_SELECTOR,
    PO_OK_SELECTOR,
    PO_POPUP_RECOVERY_TIMEOUT_SECONDS,
    PO_POPUP_SELECTOR,
    PO_RESULTS_TABLE_SELECTOR,
    PO_SEARCH_SELECTOR,
    SALE_ASN_PO_SEARCH_FIELDS,
    SALE_ASN_PO_SEARCH_LABELS,
    STYLE_INPUT_SELECTORS,
)
from wfx_panel.automation.sale_asn_create.errors import (
    _is_transient_frame_error,
    _POFrameChanged,
)
from wfx_panel.automation.sale_asn_create.form import _frame_with_selector
from wfx_panel.automation.sale_asn_create.values import (
    _decimal_display,
    _decimal_or_none,
    _fold,
)

_PO_RESULTS_JS = r"""root => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const fold = value => clean(value).toLocaleLowerCase('en');
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const tables = (root.matches?.('table')
        ? [root]
        : [...root.querySelectorAll('div table, table')])
        .filter(table => shown(table) && table.querySelectorAll('tr').length > 1);
    let best = [];
    for (const table of tables) {
        const rows = [...table.querySelectorAll(':scope > tbody > tr, :scope > tr')];
        if (rows.length < 2) continue;
        let headers = [];
        let headerCells = [];
        let headerIndex = -1;
        rows.forEach((row, index) => {
            const cells = [...row.children];
            const texts = cells.map(cell => fold(cell.textContent));
            if (texts.some(text => /po\s*(no|number)|buyer order/.test(text))) {
                headers = texts; headerCells = cells; headerIndex = index;
            }
        });
        if (headerIndex < 0) continue;
        const indexFor = patterns => headers.findIndex(text =>
            patterns.some(pattern => pattern.test(text)));
        // Workbook dùng Buyer Order Ref (ví dụ 779), không phải mã PO/OC hệ
        // thống dạng PSW-BDG-.... Ưu tiên cột Buyer Order Ref dù bảng có một
        // cột "PO No." đứng trước; chỉ fallback khi tenant không có cột Ref.
        const buyerReferenceIndex = indexFor([
            /buyer\s*order\s*(ref|reference)/,
            /buyer.*(ref|reference)/,
        ]);
        const poIndex = buyerReferenceIndex >= 0
            ? buyerReferenceIndex
            : indexFor([/po\s*(no|number)/, /buyer order/]);
        const styleIndex = indexFor([/style/, /article/]);
        const qtyIndex = indexFor([/dispatched\s*qty/, /dispatch\s*qty/, /^qty$/]);
        const valueFor = (cells, index, patterns) => {
            // Một số tenant thêm cột checkbox chỉ ở data row, làm index của
            // header lệch một ô. Ưu tiên semantic attributes, rồi ghép theo
            // tọa độ ngang của header/cell thay vì tin tuyệt đối vào index.
            for (const cell of cells) {
                const hint = fold([
                    cell.id,
                    cell.className,
                    cell.getAttribute('data-title'),
                    cell.getAttribute('headers'),
                    cell.getAttribute('aria-label'),
                    cell.getAttribute('colname'),
                ].filter(Boolean).join(' '));
                if (patterns.some(pattern => pattern.test(hint))) {
                    const value = clean(cell.textContent);
                    if (value) return value;
                }
            }
            const header = headerCells[index];
            if (header) {
                const headerRect = header.getBoundingClientRect();
                let aligned = null;
                let largestOverlap = 0;
                for (const cell of cells) {
                    const rect = cell.getBoundingClientRect();
                    const overlap = Math.min(headerRect.right, rect.right)
                        - Math.max(headerRect.left, rect.left);
                    if (overlap > largestOverlap) {
                        largestOverlap = overlap;
                        aligned = cell;
                    }
                }
                if (aligned && largestOverlap > 0) {
                    return clean(aligned.textContent);
                }
            }
            return clean(cells[index]?.textContent);
        };
        const candidates = [];
        rows.slice(headerIndex + 1).forEach((row, rowIndex) => {
            if (!shown(row)) return;
            const cells = [...row.children];
            const action = row.querySelector(
                'input[type="checkbox"][name="optShipmentId"], '
                + 'input[type="checkbox"], input[type="radio"]'
            );
            if (!action) return;
            candidates.push({
                row_index: headerIndex + 1 + rowIndex,
                selection_name: clean(action.name),
                selection_value: clean(action.value),
                selection_order_id: clean(action.getAttribute('orderid')),
                po_no: valueFor(cells, poIndex, [
                    /buyer\s*order\s*(ref|reference)/,
                    /buyer.*(ref|reference)/,
                    /po\s*(no|number)/,
                ]),
                style_no: valueFor(cells, styleIndex, [/style/, /article/]),
                dispatched_qty: valueFor(cells, qtyIndex, [
                    /dispatched\s*qty/, /dispatch\s*qty/, /^qty$/,
                ]),
                cell_values: cells.map(cell => clean(cell.textContent)),
                text: clean(row.textContent),
            });
        });
        if (candidates.length > best.length) best = candidates;
    }
    return best;
}"""


_SELECT_PO_ROW_JS = r"""(root, spec) => {
    const selector =
        'input[type="checkbox"][name="optShipmentId"], '
        + 'input[type="checkbox"], input[type="radio"]';
    const matchesIdentity = control => Boolean(control)
        && control.isConnected
        && String(control.value || '') === String(spec.selection_value || '')
        && (!spec.selection_name || control.name === spec.selection_name)
        && (!spec.selection_order_id
            || control.getAttribute('orderid') === spec.selection_order_id);
    const rows = [...root.querySelectorAll(':scope > tbody > tr, :scope > tr')];
    const rowIndex = Number(spec.row_index);
    const expectedRow = Number.isInteger(rowIndex) ? rows[rowIndex] : null;
    let action = expectedRow?.querySelector(selector) || null;
    if (!matchesIdentity(action)) {
        const exact = [...root.querySelectorAll(selector)].filter(matchesIdentity);
        if (exact.length !== 1) {
            return {
                ok: false,
                reason: 'checkbox-identity-ambiguous',
                count: exact.length,
                row_index: rowIndex,
            };
        }
        action = exact[0];
    }
    action.scrollIntoView({block: 'center', inline: 'nearest'});
    if (!action.checked) action.click();
    return {
        ok: Boolean(action.checked),
        reason: action.checked ? '' : 'checkbox-not-checked',
        value: String(spec.selection_value || ''),
        row_index: rowIndex,
    };
}"""


def _fill_popup_input(frame: Frame, selector: str, value: str) -> bool:
    locator = frame.locator(selector).first
    # Popup root chỉ được trả về sau khi đã render. Selector biến thể của Style
    # thường không tồn tại trên từng tenant; đừng chờ 12 giây cho mỗi selector
    # vắng mặt trước khi thử selector kế tiếp.
    if not locator.count():
        return False
    try:
        locator.wait_for(state="visible", timeout=3_000)
    except (PlaywrightError, PlaywrightTimeoutError):
        return False
    try:
        if locator.input_value(timeout=500) == value:
            return True
    except PlaywrightError:
        pass
    locator.fill(value, timeout=5_000)
    return locator.input_value(timeout=1_000) == value


def _select_popup_destination(frame: Frame, destination: str) -> bool:
    select = frame.locator("#wfx_GMPOAsnSearch select[name='cboDestination'], #wfx_GMPOAsnSearch #cboDestination")
    if not select.count() or not select.first.is_visible():
        return False
    # Danh sách quốc gia có thể hàng trăm option. Đọc/chọn toàn bộ ngay trong
    # DOM một lần thay vì gọi Playwright riêng cho từng option.
    return bool(
        select.first.evaluate(
            r"""(control, requested) => {
                const clean = value => String(value || '')
                    .replace(/\s+/g, ' ').trim();
                const fold = value => clean(value).toLocaleLowerCase('en');
                const wanted = clean(requested);
                const options = [...control.options];
                const matches = wanted
                    ? options.filter(item =>
                        fold(item.textContent || item.title) === fold(wanted)
                        || fold(item.value) === fold(wanted))
                    : options.filter(item =>
                        !clean(item.value)
                        || /^\[?select\]?$/i.test(clean(item.textContent)));
                const option = matches.length === 1
                    ? matches[0]
                    : (!wanted ? options[0] : null);
                if (!option) return false;
                if (control.value === option.value && option.selected) return true;
                control.value = option.value;
                option.selected = true;
                control.dispatchEvent(new Event('change', {bubbles: true}));
                return true;
            }""",
            str(destination or "").strip(),
        )
    )


def _click_dom_action(locator: Any, *, timeout: int = 8_000) -> dict[str, Any]:
    """Click action WFX mà không phụ thuộc scroll hoặc foreground của Chrome."""

    locator.wait_for(state="visible", timeout=timeout)
    result = locator.evaluate(
        r"""node => {
            const action = node.matches('a, button, input, [onclick]')
                ? node
                : node.querySelector('a, button, input, [onclick]') || node;
            if (action.disabled || action.getAttribute('aria-disabled') === 'true') {
                return {ok: false, reason: 'action-disabled'};
            }
            action.click();
            return {ok: true, tag: action.tagName, id: action.id || ''};
        }"""
    )
    if not result.get("ok"):
        raise RuntimeError(
            f"SALE_ASN_ACTION_NOT_READY:{result.get('reason') or 'unknown'}"
        )
    return result


def _click_search(frame: Frame) -> None:
    search = frame.locator(PO_SEARCH_SELECTOR).first
    if not search.count():
        search = frame.locator("xpath=//*[@id='wfx_GMPOAsnSearch']/table[3]/tbody/tr/td[2]/input").first
    monitor_installed = False
    try:
        monitor_installed = bool(
            frame.evaluate(
                r"""() => {
                    const root = document.querySelector('#wfx_GMPOAsnSearch');
                    if (!root) return false;
                    window.__wfxPoSearchMonitor?.observer?.disconnect();
                    const state = {
                        changed: false,
                        lastMutation: performance.now(),
                    };
                    const observer = new MutationObserver(() => {
                        state.changed = true;
                        state.lastMutation = performance.now();
                    });
                    observer.observe(root, {
                        subtree: true,
                        childList: true,
                        attributes: true,
                        characterData: true,
                    });
                    window.__wfxPoSearchMonitor = {state, observer};
                    return true;
                }"""
            )
        )
    except PlaywrightError:
        pass
    _click_dom_action(search)
    if not monitor_installed:
        _wait(frame, 700)
        return

    started = time.monotonic()
    deadline = started + 5
    try:
        while time.monotonic() < deadline:
            state = frame.evaluate(
                r"""() => {
                    const monitor = window.__wfxPoSearchMonitor;
                    const shown = element => {
                        if (!element || !element.isConnected) return false;
                        const style = getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        return style.display !== 'none'
                            && style.visibility !== 'hidden'
                            && rect.width > 0 && rect.height > 0;
                    };
                    const busy = [
                        '.blockUI', '.ui-widget-overlay', '.loading',
                        '[id*="loading" i]', '[id*="progress" i]'
                    ].some(selector =>
                        [...document.querySelectorAll(selector)].some(shown));
                    return {
                        changed: Boolean(monitor?.state?.changed),
                        quietMs: monitor
                            ? performance.now() - monitor.state.lastMutation
                            : 0,
                        busy,
                    };
                }"""
            )
            elapsed_ms = (time.monotonic() - started) * 1_000
            # Response nhanh: DOM đã đổi và yên ít nhất 120 ms. Nếu WFX không
            # mutate DOM khi kết quả giống hệt, giữ fallback 700 ms như trước.
            if (
                not state.get("busy")
                and (
                    (state.get("changed") and state.get("quietMs", 0) >= 120)
                    or (not state.get("changed") and elapsed_ms >= 700)
                )
            ):
                return
            _wait(frame, 60)
    except PlaywrightError as error:
        if _is_transient_frame_error(error):
            # Click Search đã chạy. WFX thường thay cả document để hiển thị
            # kết quả; frame cũ mất context không có nghĩa tìm PO thất bại.
            raise _POFrameChanged(search_submitted=True) from error
        raise
    finally:
        try:
            frame.evaluate(
                """() => {
                    window.__wfxPoSearchMonitor?.observer?.disconnect();
                    delete window.__wfxPoSearchMonitor;
                }"""
            )
        except PlaywrightError:
            pass


def _search_po(
    frame: Frame,
    row: dict,
    *,
    fields: Sequence[str],
) -> list[dict]:
    search_submitted = False
    try:
        enabled = set(fields)
        po_no = str(row.get("po_no") or "") if "po" in enabled else ""
        if not _fill_popup_input(frame, "#txtOCNo", po_no):
            raise _POFrameChanged(fields=fields, search_submitted=False)
        destination = (
            str(row.get("destination") or "")
            if "destination" in enabled
            else ""
        )
        _select_popup_destination(frame, destination)
        style = str(row.get("style_no") or "") if "style" in enabled else ""
        for selector in STYLE_INPUT_SELECTORS:
            if _fill_popup_input(frame, selector, style):
                break
        _click_search(frame)
        search_submitted = True
        table = frame.locator(PO_RESULTS_TABLE_SELECTOR).first
        table.wait_for(state="visible", timeout=5_000)
        return list(table.evaluate(_PO_RESULTS_JS) or [])
    except _POFrameChanged as error:
        if not error.fields:
            error.fields = tuple(fields)
        raise
    except PlaywrightError as error:
        if _is_transient_frame_error(error):
            raise _POFrameChanged(
                fields=fields,
                search_submitted=search_submitted,
            ) from error
        raise


def _recover_submitted_po_results(
    context: Any,
    *,
    timeout_s: float,
) -> tuple[Frame, list[dict]] | None:
    """Nhận bảng kết quả mà WFX đã render sau khi Search đổi document."""

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    table = frame.locator(PO_RESULTS_TABLE_SELECTOR).first
                    if not table.count() or not table.is_visible():
                        continue
                    candidates = list(table.evaluate(_PO_RESULTS_JS) or [])
                    if candidates:
                        return frame, candidates
                except PlaywrightError:
                    continue
        if context.pages:
            _wait(context.pages[0], 100)
    return None


def _auto_add_po_with_frame_retry(
    context: Any,
    popup_frame: Frame,
    row: dict,
    log: Callable[[str], None],
    *,
    final: bool,
    search_fields: Sequence[str],
) -> tuple[bool, list[dict], str, Frame]:
    """Nhận lại popup/kết quả nếu WFX đổi document lúc Search."""

    deadline = time.monotonic() + PO_POPUP_RECOVERY_TIMEOUT_SECONDS
    recovered_search: tuple[tuple[str, ...], list[dict]] | None = None
    reported_reload = False
    while time.monotonic() < deadline:
        try:
            kwargs: dict[str, Any] = {
                "final": final,
                "search_fields": search_fields,
            }
            if recovered_search is not None:
                kwargs["recovered_search"] = recovered_search
            added, candidates, reason = _auto_add_po(
                popup_frame, row, log, **kwargs
            )
            return added, candidates, reason, popup_frame
        except _POFrameChanged as changed:
            if not reported_reload:
                _write_log(
                    log,
                    f"[SALE ASN] Dòng {row.get('source_row')}: popup Add PO vừa tải lại; đang nhận kết quả từ frame mới.",
                )
                reported_reload = True
            remaining = max(0.1, deadline - time.monotonic())
            if changed.search_submitted:
                recovered = _recover_submitted_po_results(
                    context,
                    timeout_s=min(8, remaining),
                )
                if recovered is not None:
                    popup_frame, candidates = recovered
                    recovered_search = (tuple(changed.fields), candidates)
                    _write_log(
                        log,
                        f"[SALE ASN] Dòng {row.get('source_row')}: đã nhận {len(candidates)} kết quả PO từ frame mới.",
                    )
                    continue
            recovered_search = None
            remaining = max(0.1, deadline - time.monotonic())
            _popup_page, popup_frame = _frame_with_selector(
                context,
                f"{PO_POPUP_SELECTOR} #txtOCNo",
                timeout_s=remaining,
            )
    raise RuntimeError("SALE_ASN_PO_SEARCH_NOT_READY")


def _add_selected_po_candidates(
    frame: Frame,
    row: dict,
    candidates: Sequence[dict],
    log: Callable[[str], None],
    *,
    final: bool,
) -> None:
    if not candidates:
        raise RuntimeError("SALE_ASN_PO_SELECTION_REQUIRED")
    selected_values: list[str] = []
    for chosen in candidates:
        selected = frame.locator(PO_RESULTS_TABLE_SELECTOR).first.evaluate(
            _SELECT_PO_ROW_JS,
            {
                "row_index": chosen.get("row_index"),
                "selection_name": str(chosen.get("selection_name") or ""),
                "selection_value": str(chosen.get("selection_value") or ""),
                "selection_order_id": str(chosen.get("selection_order_id") or ""),
            },
        )
        if not selected.get("ok"):
            raise RuntimeError(
                "SALE_ASN_PO_SELECTION_NOT_CONFIRMED:"
                f"{selected.get('reason') or 'unknown'}"
            )
        selected_values.append(str(selected.get("value") or ""))
    _write_log(
        log,
        (
            f"[SALE ASN] Dòng {row.get('source_row')}: đã chọn "
            f"{len(selected_values)} dòng ({', '.join(selected_values)})."
        ),
    )
    action_selector = PO_OK_SELECTOR if final else PO_CONTINUE_SELECTOR
    button = frame.locator(action_selector).first
    button.wait_for(state="visible", timeout=5_000)
    clicked = button.evaluate(
        """container => {
            const action = container.matches('a, button, input, [onclick]')
                ? container
                : container.querySelector('a, button, input, [onclick]');
            if (!action) return {ok: false, reason: 'action-not-found'};
            action.click();
            return {ok: true, tag: action.tagName, id: action.id || ''};
        }"""
    )
    if not clicked.get("ok"):
        raise RuntimeError(
            f"SALE_ASN_PO_SELECTION_NOT_CONFIRMED:{clicked.get('reason')}"
        )
    if final:
        _write_log(
            log,
            (
                "[SALE ASN] PO cuối: đã bấm link OK để thêm PO và đóng "
                f"Add Order Details ({clicked.get('tag') or 'node'})."
            ),
        )
        return
    _wait(frame, 250)


def _unique_dispatched_qty_subset(
    candidates: Sequence[dict],
    expected_qty: Decimal | None,
) -> list[dict] | None:
    """Trả tập dòng duy nhất có tổng Dispatched Qty bằng Qty file.

    ``None`` nghĩa là thiếu Qty, không có đáp án, có nhiều đáp án hoặc số trạng
    thái vượt ngưỡng an toàn. Không đoán khi hai tổ hợp cùng cho một tổng.
    """

    if expected_qty is None or expected_qty <= 0 or not candidates:
        return None
    quantities = [
        _decimal_or_none(candidate.get("dispatched_qty"))
        for candidate in candidates
    ]
    if any(value is None or value <= 0 for value in quantities):
        return None

    # value None đánh dấu tổng này có từ hai tổ hợp trở lên.
    states: dict[Decimal, tuple[int, ...] | None] = {Decimal("0"): ()}
    for index, quantity in enumerate(quantities):
        assert quantity is not None
        updated = dict(states)
        for total, subset in states.items():
            combined = total + quantity
            if combined > expected_qty:
                continue
            proposed = None if subset is None else (*subset, index)
            if combined not in updated:
                updated[combined] = proposed
            elif updated[combined] != proposed:
                updated[combined] = None
        states = updated
        if len(states) > 4096:
            return None

    selected = states.get(expected_qty)
    if not selected:
        return None
    return [dict(candidates[index]) for index in selected]


def _auto_add_po(
    frame: Frame,
    row: dict,
    log: Callable[[str], None],
    *,
    final: bool = False,
    search_fields: Sequence[str] = SALE_ASN_PO_SEARCH_FIELDS,
    recovered_search: tuple[tuple[str, ...], list[dict]] | None = None,
) -> tuple[bool, list[dict], str]:
    configured = tuple(
        field for field in SALE_ASN_PO_SEARCH_FIELDS if field in set(search_fields)
    ) or SALE_ASN_PO_SEARCH_FIELDS
    # Destination là tùy chọn.  Không để một giá trị đang chọn từ PO trước trong
    # popup vô tình trở thành điều kiện lọc cho dòng hiện tại khi ô Excel trống.
    enabled = tuple(
        field
        for field in configured
        if field != "destination" or str(row.get("destination") or "").strip()
    )
    if "destination" in configured and "destination" not in enabled:
        _write_log(
            log,
            f"[SALE ASN] Dòng {row.get('source_row')}: Destination trống, bỏ qua tiêu chí Destination.",
        )
    if not enabled:
        # PO No là khóa bắt buộc của mỗi dòng workbook, nên là điểm tựa an toàn
        # khi người dùng chỉ bật Destination nhưng dòng hiện tại để trống.
        enabled = ("po",)
    active: list[str] = []
    last: list[dict] = []
    label = ""
    for field in enabled:
        active.append(field)
        label = " + ".join(SALE_ASN_PO_SEARCH_LABELS[item] for item in active)
        active_fields = tuple(active)
        if recovered_search is not None:
            recovered_fields = tuple(recovered_search[0])
            if (
                len(active_fields) < len(recovered_fields)
                and recovered_fields[: len(active_fields)] == active_fields
            ):
                # Search của các prefix này đã chạy trước khi popup thay document.
                # Đi thẳng tới đúng bộ tiêu chí đã submit để không reset kết quả
                # vừa phục hồi (ví dụ PO + Style = 1) về Search chỉ theo PO.
                continue
            if recovered_fields == active_fields:
                last = list(recovered_search[1])
                recovered_search = None
            else:
                recovered_search = None
                last = _search_po(frame, row, fields=active_fields)
        else:
            last = _search_po(frame, row, fields=active_fields)
        if "po" in active_fields:
            requested_po = _fold(row.get("po_no"))
            raw_count = len(last)
            raw_candidates = list(last)
            exact: list[dict] = []
            for item in last:
                parsed_po = _fold(item.get("po_no"))
                cell_values = item.get("cell_values")
                if not isinstance(cell_values, (list, tuple)):
                    cell_values = ()
                cell_match = any(
                    requested_po and _fold(value) == requested_po
                    for value in cell_values
                )
                if requested_po and (parsed_po == requested_po or cell_match):
                    candidate = dict(item)
                    if parsed_po != requested_po:
                        # Parser cột là thông tin hiển thị; exact cell match mới
                        # là bằng chứng chọn dòng. Chuẩn hóa label gửi về app.
                        candidate["po_no"] = str(row.get("po_no") or "")
                    exact.append(candidate)
            if exact:
                last = exact
            else:
                # WFX có tenant thêm cột checkbox chỉ ở data row, khiến cột
                # Buyer Order Ref không thể xác định chắc chắn. Không xóa sạch
                # kết quả trước khi lớp Qty/Dispatched Qty có cơ hội quyết định.
                last = raw_candidates
                _write_log(
                    log,
                    (
                        f"[SALE ASN] Dòng {row.get('source_row')}: chưa đọc được "
                        f"Buyer Order Ref exact {row.get('po_no')} trong "
                        f"{raw_count} kết quả; tiếp tục đối chiếu Qty với "
                        "Dispatched Qty."
                    ),
                )
            if exact and len(last) != raw_count:
                _write_log(
                    log,
                    (
                        f"[SALE ASN] Dòng {row.get('source_row')}: đã loại "
                        f"{raw_count - len(last)} kết quả PO gần đúng không "
                        f"khớp exact {row.get('po_no')}."
                    ),
                )
        _write_log(log, f"[SALE ASN] Dòng {row.get('source_row')}: {label} → {len(last)} kết quả.")
        if not last:
            # Mỗi lượt chỉ thêm điều kiện nên 0 kết quả không thể tăng lại.
            break
        if len(last) > 1 and field != enabled[-1]:
            continue

        # Qty trong file vẫn được kiểm ngay tại Add PO. Nếu đã dùng hết tiêu
        # chí nhưng còn nhiều dòng (thường là các size), chỉ auto-add khi tổng
        # Dispatched Qty bằng Qty file. Lệch thì giữ popup để user quyết định.
        expected_qty = _decimal_or_none(row.get("qty"))
        if expected_qty is not None and len(last) >= 2:
            qty_subset = _unique_dispatched_qty_subset(last, expected_qty)
            if qty_subset is not None and len(qty_subset) < len(last):
                last = qty_subset
                _write_log(
                    log,
                    (
                        f"[SALE ASN] Dòng {row.get('source_row')}: Qty file "
                        f"{_decimal_display(expected_qty)} chỉ khớp một tập "
                        f"{len(last)} dòng theo Dispatched Qty; tự chọn."
                    ),
                )
        all_dispatched_qty = [
            _decimal_or_none(item.get("dispatched_qty")) for item in last
        ]
        if expected_qty is not None and len(last) >= 2:
            if not all(value is not None for value in all_dispatched_qty):
                detail = (
                    f"có {len(last)} dòng nhưng WFX không cung cấp đủ "
                    "Dispatched Qty để đối chiếu Qty file"
                )
                _write_log(
                    log,
                    f"[SALE ASN] Dòng {row.get('source_row')}: {detail}; chờ user xác nhận.",
                )
                return False, last, f"qty_unavailable:{detail}"
            total_dispatched_qty = sum(all_dispatched_qty, Decimal("0"))
            if abs(expected_qty - total_dispatched_qty) > Decimal("0.0001"):
                detail = (
                    f"có {len(last)} dòng, tổng Dispatched Qty "
                    f"{_decimal_display(total_dispatched_qty)} khác Qty file "
                    f"{_decimal_display(expected_qty)}"
                )
                _write_log(
                    log,
                    f"[SALE ASN] Dòng {row.get('source_row')}: {detail}; chờ user xác nhận.",
                )
                return False, last, f"qty_mismatch:{detail}"
            _write_log(
                log,
                f"[SALE ASN] Dòng {row.get('source_row')}: tổng Dispatched Qty {_decimal_display(total_dispatched_qty)} khớp Qty file; tự thêm {len(last)} dòng.",
            )
        if expected_qty is not None and len(last) == 1:
            actual_qty = _decimal_or_none(last[0].get("dispatched_qty"))
            if actual_qty is not None:
                if abs(expected_qty - actual_qty) > Decimal("0.0001"):
                    raise RuntimeError(
                        "SALE_ASN_PO_QTY_MISMATCH:"
                        f"Dòng {row.get('source_row')} · file Qty "
                        f"{_decimal_display(expected_qty)} khác WFX "
                        f"{_decimal_display(actual_qty)}."
                    )
                _write_log(
                    log,
                    f"[SALE ASN] Dòng {row.get('source_row')}: Qty {_decimal_display(expected_qty)} khớp Dispatched Qty trước khi thêm PO.",
                )

        _add_selected_po_candidates(frame, row, last, log, final=final)
        return True, last, label
    reason = "not_found" if not last else "ambiguous"
    return False, last, reason
