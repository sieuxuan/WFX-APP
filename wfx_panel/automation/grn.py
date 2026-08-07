"""Luồng nhập kho RMPO: Sourcing ASN (nước ngoài) và GRN trong nước."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
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
from wfx_panel.automation.modules import (
    _active_wfx_page,
    search_rmpo_list,
)
from wfx_panel.automation.sale_asn_create import _set_control

SOURCING_ASN_NEW_XPATH = '//*[@id="0005_0105_1200_0010"]/a'
GRN_PENDING_XPATH = '//*[@id="0050_0020_0380"]/a'
GRN_SEARCH_XPATH = '//*[@id="0050_0020_0010"]/a'

_SOURCING_CONTEXT = (
    "#CellID12",
    "#CellIDSupplier",
    "#sectionSupplierASNShipmentDetail",
)
_GRN_CONTEXT = (
    "#CellID1",
    "#CellID11",
    "#CellID12",
    "#sectionOrderShipment",
    "#titlebarGRNPending",
)
_GRN_SEARCH_CONTEXT = (
    "#ctrlRpt",
    "#row_txtDocNum",
    "#row_txtOrderNum",
    "#row_txtFromGRNDate",
)
_GRN_SEARCH_FILTERS = {
    "invoice": ("#chk_8", "#txtDocNum"),
    "rmpo": ("#chk_9", "#txtOrderNum"),
}
_GRN_DATE_CHECKBOX = "#chk_6"

_CONTROL_OPTIONS_JS = r"""spec => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const host = [...document.querySelectorAll(spec.selector)]
        .find(shown) || document.querySelector(spec.selector);
    if (!host) return [];
    if (spec.open) {
        const action = host.querySelector(
            '.select2-selection, .lblEditable, [contenteditable="true"], span'
        ) || host;
        action.click();
    }
    const selects = [
        ...host.querySelectorAll('select'),
        ...document.querySelectorAll('select:focus, select.clsCombo'),
    ];
    const labels = [];
    selects.forEach(select => [...select.options].forEach(option => {
        const label = clean(option.textContent || option.title);
        if (!option.disabled && clean(option.value) && label
            && !/^\[?select\]?$/i.test(label)) labels.push(label);
    }));
    [...document.querySelectorAll(
        '[role="option"], .select2-results__option, li.clsMultiSelectContent'
    )].filter(shown).forEach(option => {
        const label = clean(option.textContent || option.title);
        if (label && !/^\[?select\]?$/i.test(label)) labels.push(label);
    });
    return [...new Map(labels.map(label => [label.toLowerCase(), label])).values()];
}"""

_SELECT_PO_ROW_JS = r"""(root, expectedPo) => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const fold = value => clean(value).toLocaleLowerCase('en');
    const text = cell => clean(
        cell?.querySelector('input[value], a, button')?.value
        || cell?.querySelector('[title]')?.getAttribute('title')
        || cell?.getAttribute('title') || cell?.textContent || ''
    );
    const headerCells = [...root.querySelectorAll('thead th, thead td, tr.trHeader td')];
    const metadata = cell => {
        const header = Number.isInteger(cell?.cellIndex)
            ? headerCells[cell.cellIndex] : null;
        return clean([
            cell?.id || '', cell?.getAttribute('title') || '',
            cell?.getAttribute('aria-label') || '', header?.id || '',
            header?.getAttribute('title') || '', header?.textContent || ''
        ].join(' ')).toLowerCase();
    };
    const rows = [...root.querySelectorAll('tr')].filter(row =>
        [...row.children].some(child => child.tagName === 'TD')
    );
    const matches = rows.filter(row => {
        const cells = [...row.children].filter(child => child.tagName === 'TD');
        const exact = cells.find(cell => [
            'colPONo', 'colPONumber', 'colOrderNo', 'colOrderRefNo'
        ].includes(cell.id));
        const poCell = exact || cells.find(cell =>
            /(^|\s)(po|order)\s*(no|number)(\s|$)/i.test(metadata(cell))
        );
        return fold(text(poCell)) === fold(expectedPo);
    });
    if (matches.length !== 1) {
        return {ok: false, reason: 'po-row-ambiguous', count: matches.length};
    }
    const row = matches[0];
    const selector = row.querySelector(
        'input[type="checkbox"], input[type="radio"]'
    );
    const firstCell = [...row.children].find(child => child.tagName === 'TD');
    const action = selector || firstCell?.querySelector(
        'a, button, input[type="button"], [onclick]'
    ) || firstCell;
    if (!action) return {ok: false, reason: 'row-selector-not-found'};
    if (!selector || !selector.checked) action.click();
    return {
        ok: !selector || Boolean(selector.checked),
        reason: selector && !selector.checked ? 'row-not-selected' : '',
        row_id: row.id || '',
    };
}"""


def _fold(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _resolve_rmpo(
    rmpo_xpath: str,
    rmpo_no: str,
    log: Callable[[str], None],
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    result = search_rmpo_list(rmpo_xpath, "", rmpo_no, log)
    if not result.get("ok"):
        if result.get("code") == "RMPO_NO_RESULTS":
            return None, None, _result(
                False,
                "GRN_RMPO_NOT_FOUND",
                "Không tìm thấy RMPO để lấy Supplier.",
            )
        return None, None, result
    matching_rows = [
        row
        for row in result.get("rmpo_rows") or []
        if isinstance(row, dict)
        and _fold(rmpo_no) in _fold(row.get("order_no"))
    ]
    exact_rows = [
        row
        for row in matching_rows
        if _fold(row.get("order_no")) == _fold(rmpo_no)
    ]
    candidates = exact_rows or matching_rows
    if len(candidates) != 1:
        code = "GRN_RMPO_NOT_FOUND" if not candidates else "GRN_RMPO_AMBIGUOUS"
        message = (
            "Không tìm thấy RMPO phù hợp để lấy Supplier."
            if not candidates
            else "Có nhiều RMPO chứa số đã nhập; hãy nhập thêm ký tự để xác định đúng PO."
        )
        return None, None, _result(False, code, message)
    selected = candidates[0]
    canonical_rmpo = " ".join(str(selected.get("order_no") or "").split())
    supplier = " ".join(str(selected.get("supplier") or "").split())
    if not supplier:
        _write_log(
            log,
            "[GRN] Đã tìm thấy đúng RMPO nhưng chưa đọc được Supplier ở dòng đó.",
        )
        return None, None, _result(
            False,
            "GRN_RMPO_SUPPLIER_NOT_FOUND",
            f"Đã tìm thấy RMPO {canonical_rmpo}, nhưng chưa đọc được Supplier.",
        )
    status = _fold(selected.get("status"))
    if status == "received":
        return None, None, _result(
            False,
            "GRN_ALREADY_RECEIVED",
            f"RMPO {canonical_rmpo} đã nhập kho hết, không thể nhập thêm.",
        )
    _write_log(
        log,
        "[GRN] Đã xác định RMPO đầy đủ và Supplier từ kết quả duy nhất.",
    )
    return canonical_rmpo, supplier, None


def _context_frames(context: Any) -> list[Frame]:
    return [
        frame
        for page in reversed(context.pages)
        for frame in reversed(page.frames)
    ]


def _frame_has_context(frame: Frame, selectors: Sequence[str]) -> bool:
    try:
        return all(frame.locator(selector).count() for selector in selectors)
    except PlaywrightError:
        return False


def _snapshot_context(
    context: Any,
    prefix: str,
) -> tuple[set[int], dict[int, tuple[Frame | None, str]]]:
    page_ids = {id(page) for page in context.pages}
    snapshots: dict[int, tuple[Frame | None, str]] = {}
    for page_index, page in enumerate(context.pages):
        for frame_index, frame in enumerate(page.frames):
            snapshots[id(frame)] = _mark_document(
                frame,
                f"{prefix}-{page_index}-{frame_index}",
            )
    return page_ids, snapshots


def _wait_new_context_frame(
    context: Any,
    page_ids: set[int],
    snapshots: dict[int, tuple[Frame | None, str]],
    selectors: Sequence[str],
    *,
    timeout_s: float = 40,
) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in _context_frames(context):
            if not _frame_has_context(frame, selectors):
                continue
            snapshot = snapshots.get(id(frame))
            if (
                id(frame.page) not in page_ids
                or snapshot is None
                or _document_changed(frame, snapshot)
            ):
                return frame
        frames = _context_frames(context)
        _wait(frames[0] if frames else context.pages[0], 150)
    raise PlaywrightTimeoutError(
        "WFX chưa mở đúng màn hình sau khi click menu."
    )


def _find_context_frame(
    context: Any,
    selectors: Sequence[str],
    *,
    timeout_s: float = 15,
) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in _context_frames(context):
            if _frame_has_context(frame, selectors):
                return frame
        frames = _context_frames(context)
        _wait(frames[0] if frames else context.pages[0], 150)
    raise PlaywrightTimeoutError("Không tìm thấy màn hình WFX đang thao tác.")


def _open_menu_form(
    context: Any,
    page: Page,
    xpath: str,
    selectors: Sequence[str],
    label: str,
    log: Callable[[str], None],
) -> Frame:
    page_ids, snapshots = _snapshot_context(context, f"grn-{label}")
    target = page.locator(f"xpath={xpath}")
    target.wait_for(state="attached", timeout=8_000)
    _write_log(log, f"[GRN] Đang mở {label}...")
    _click(target)
    frame = _wait_new_context_frame(
        context,
        page_ids,
        snapshots,
        selectors,
        timeout_s=45,
    )
    try:
        frame.page.bring_to_front()
    except PlaywrightError:
        pass
    return frame


def _set_exact(
    frame: Frame,
    selector: str,
    value: str,
    field_label: str,
    log: Callable[[str], None],
    *,
    timeout_s: float = 20,
) -> None:
    selected = _set_control(
        frame,
        selector,
        value,
        "exact",
        timeout_s=timeout_s,
    )
    if not selected.get("ok"):
        raise PlaywrightTimeoutError(
            f"Không chọn được {field_label}: {selected.get('reason') or 'unknown'}"
        )
    _write_log(log, f"[GRN] Đã chọn {field_label}.")


def _click_action(frame: Frame, selector: str, label: str) -> None:
    container = _first_visible(frame.locator(selector))
    if container is None:
        raise PlaywrightTimeoutError(f"Không tìm thấy nút {label}.")
    action = _first_visible(
        container.locator('a, button, input[type="button"], [onclick]')
    )
    _click(action or container)


def _read_control_options(
    frame: Frame,
    selector: str,
    *,
    timeout_s: float = 15,
) -> list[str]:
    deadline = time.monotonic() + timeout_s
    opened = False
    while time.monotonic() < deadline:
        try:
            raw = frame.evaluate(
                _CONTROL_OPTIONS_JS,
                {"selector": selector, "open": not opened},
            )
            opened = True
            options = [
                " ".join(str(item or "").split())
                for item in raw or []
                if str(item or "").strip()
            ]
            if options:
                return list(dict.fromkeys(options))
        except PlaywrightError:
            pass
        _wait(frame, 150)
    return []


def _select_po_row(frame: Frame, section_selector: str, rmpo_no: str) -> None:
    section = _first_visible(frame.locator(section_selector))
    if section is None:
        raise PlaywrightTimeoutError(
            f"Không tìm thấy bảng {section_selector}."
        )
    selected = section.evaluate(_SELECT_PO_ROW_JS, rmpo_no)
    if not selected.get("ok"):
        raise PlaywrightTimeoutError(
            "Không chọn được đúng RMPO trong bảng; "
            f"reason={selected.get('reason')}; count={selected.get('count', 0)}"
        )


def _select_imported(frame: Frame, log: Callable[[str], None]) -> None:
    host = _first_visible(
        frame.locator("#CellID14 > div:nth-child(2), #CellID14")
    )
    if host is None:
        raise PlaywrightTimeoutError("Không tìm thấy lựa chọn Imported.")
    state = host.evaluate(
        """host => {
            const checkbox = host.matches('input[type="checkbox"]')
                ? host : host.querySelector('input[type="checkbox"]');
            if (checkbox) {
                if (!checkbox.checked) checkbox.click();
                return Boolean(checkbox.checked);
            }
            const action = host.querySelector(
                'input, button, a, .lblEditable, span, [onclick]'
            ) || host;
            action.click();
            return true;
        }"""
    )
    if not state:
        raise PlaywrightTimeoutError("WFX chưa xác nhận Imported.")
    _write_log(log, "[GRN] Đã chọn Imported.")


def _wait_loading_finished(frame: Frame, timeout_s: float = 25) -> None:
    deadline = time.monotonic() + timeout_s
    stable_since = 0.0
    while time.monotonic() < deadline:
        try:
            loading = frame.locator(
                ".ag-overlay-loading-wrapper, .ag-loading, .loading, "
                ".loader, [aria-busy='true']"
            )
            busy = any(
                loading.nth(index).is_visible()
                for index in range(loading.count())
            )
        except PlaywrightError:
            busy = True
        now = time.monotonic()
        if busy:
            stable_since = 0.0
        elif stable_since <= 0:
            stable_since = now
        elif now - stable_since >= 0.8:
            return
        _wait(frame, 150)
    raise PlaywrightTimeoutError("Kết quả GRN chưa tải xong.")


def _prepare_sourcing_asn(
    context: Any,
    page: Page,
    rmpo_no: str,
    supplier: str,
    log: Callable[[str], None],
) -> None:
    frame = _open_menu_form(
        context,
        page,
        SOURCING_ASN_NEW_XPATH,
        _SOURCING_CONTEXT,
        "Sourcing ASN New",
        log,
    )
    _set_exact(
        frame,
        "#CellID12 > div:nth-child(2), #CellID12",
        "RMPO",
        "Order Type = RMPO",
        log,
    )
    _set_exact(
        frame,
        (
            "#CellIDSupplier > div:nth-child(2) > span, "
            "#CellIDSupplier > div:nth-child(2), #CellIDSupplier"
        ),
        supplier,
        "Supplier",
        log,
    )
    page_ids, snapshots = _snapshot_context(context, "grn-sourcing-add")
    _click_action(
        frame,
        'xpath=//*[@id="sectionSupplierASNShipmentDetail"]/tbody/tr/td[2]/span/div[1]',
        "Add",
    )
    popup = _wait_new_context_frame(
        context,
        page_ids,
        snapshots,
        ("#sectionRMPOList",),
        timeout_s=40,
    )
    _select_po_row(popup, "#sectionRMPOList", rmpo_no)
    _click_action(
        popup,
        'xpath=//*[@id="sectionRMPOList"]/tbody/tr/td[2]/span/div[1]/a',
        "Add & Close",
    )
    _write_log(log, "[GRN] Đã Add RMPO vào Sourcing ASN.")


def _prepare_grn_pending(
    context: Any,
    page: Page,
    supplier: str,
    mode: str,
    log: Callable[[str], None],
) -> list[str]:
    frame = _open_menu_form(
        context,
        page,
        GRN_PENDING_XPATH,
        _GRN_CONTEXT,
        "GRN Pending",
        log,
    )
    receipt_type = (
        "ASN from Supplier - Against ASN"
        if mode == "foreign"
        else "ASN from Supplier - Against PO"
    )
    _set_exact(
        frame,
        "#CellID1 > div:nth-child(2) > span, #CellID1 > div:nth-child(2), #CellID1",
        receipt_type,
        "Receipt Type",
        log,
    )
    # Receipt Type có thể làm WFX bind lại control From; resolve lại document.
    frame = _find_context_frame(context, _GRN_CONTEXT, timeout_s=20)
    _set_exact(
        frame,
        "#CellID12 > div:nth-child(2) > span, #CellID12 > div:nth-child(2), #CellID12",
        supplier,
        "From",
        log,
    )
    if mode == "foreign":
        _select_imported(frame, log)
    _click_action(
        frame,
        'xpath=//*[@id="CellID13"]/div',
        "Search",
    )
    _wait_loading_finished(frame)
    frame = _find_context_frame(context, _GRN_CONTEXT, timeout_s=20)
    sites = _read_control_options(
        frame,
        "#CellID11 > div:nth-child(2) > span, #CellID11 > div:nth-child(2), #CellID11",
    )
    if not sites:
        raise PlaywrightTimeoutError("Không đọc được danh sách Site trên GRN.")
    _write_log(log, f"[GRN] Đã đọc {len(sites)} Site.")
    return sites


def prepare_grn_receipt(
    rmpo_xpath: str,
    rmpo_no: str,
    supplier: str,
    mode: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Chuẩn bị Sourcing ASN hoặc đi thẳng tới màn chọn Site GRN."""
    rmpo_no = " ".join(str(rmpo_no or "").split())
    supplier = " ".join(str(supplier or "").split())
    mode = str(mode or "").strip().casefold()
    if not rmpo_no:
        return _result(False, "GRN_RMPO_REQUIRED", "Vui lòng nhập RMPO No.")
    if mode not in {"foreign", "domestic"}:
        return _result(False, "GRN_MODE_INVALID", "Loại nhập kho không hợp lệ.")
    if not supplier:
        rmpo_no, supplier, error = _resolve_rmpo(rmpo_xpath, rmpo_no, log)
        if error is not None:
            return error
    assert rmpo_no is not None and supplier is not None

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        if mode == "foreign":
            _prepare_sourcing_asn(context, page, rmpo_no, supplier, log)
            return _result(
                True,
                "GRN_SOURCING_ASN_READY",
                (
                    "Đã thêm RMPO vào Sourcing ASN. Hãy tự nhập đủ thông tin, "
                    "số lượng và Confirm trên WFX."
                ),
                rmpo_no=rmpo_no,
                supplier=supplier,
                mode=mode,
            )
        sites = _prepare_grn_pending(context, page, supplier, mode, log)
        return _result(
            True,
            "GRN_SITE_SELECTION_REQUIRED",
            "Đã chuẩn bị GRN. Hãy chọn Site trong ứng dụng.",
            rmpo_no=rmpo_no,
            supplier=supplier,
            mode=mode,
            sites=sites,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="(GRN) Nhập kho")
    except (PlaywrightError, PlaywrightTimeoutError) as exc:
        message = f"Chưa chuẩn bị được nhập kho: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "GRN_PREPARE_FAILED", message, module="(GRN) Nhập kho")
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "GRN_PREPARE_FAILED", message, module="(GRN) Nhập kho")
    finally:
        if playwright is not None:
            playwright.stop()


def continue_grn_receipt(
    supplier: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Sau khi user Confirm Sourcing ASN, mở và chuẩn bị GRN Against ASN."""
    supplier = " ".join(str(supplier or "").split())
    if not supplier:
        return _result(False, "GRN_SESSION_EXPIRED", "Phiên nhập kho đã hết hiệu lực.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        sites = _prepare_grn_pending(
            browser.contexts[0],
            page,
            supplier,
            "foreign",
            log,
        )
        return _result(
            True,
            "GRN_SITE_SELECTION_REQUIRED",
            "Đã chuẩn bị GRN từ Sourcing ASN. Hãy chọn Site trong ứng dụng.",
            supplier=supplier,
            mode="foreign",
            sites=sites,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="(GRN) Nhập kho")
    except Exception as exc:
        message = f"Chưa tiếp tục được GRN: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "GRN_CONTINUE_FAILED", message, module="(GRN) Nhập kho")
    finally:
        if playwright is not None:
            playwright.stop()


def finalize_grn_receipt(
    rmpo_no: str,
    site: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Chọn Site, đúng PO No. và click New trên GRN Pending."""
    rmpo_no = " ".join(str(rmpo_no or "").split())
    site = " ".join(str(site or "").split())
    if not rmpo_no or not site:
        return _result(False, "GRN_SITE_REQUIRED", "Vui lòng chọn Site.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, _page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        frame = _find_context_frame(context, _GRN_CONTEXT, timeout_s=12)
        _set_exact(
            frame,
            "#CellID11 > div:nth-child(2) > span, #CellID11 > div:nth-child(2), #CellID11",
            site,
            "Site",
            log,
        )
        _wait_loading_finished(frame)
        frame = _find_context_frame(context, _GRN_CONTEXT, timeout_s=20)
        _select_po_row(frame, "#sectionOrderShipment", rmpo_no)
        _click_action(
            frame,
            'xpath=//*[@id="titlebarGRNPending"]/tbody/tr/td[2]/span/div[1]',
            "New",
        )
        _wait(frame, 300)
        _write_log(log, "[GRN] Đã chọn đúng PO No. và click New.")
        return _result(
            True,
            "GRN_NEW_READY",
            "Đã chọn RMPO và mở New GRN. Hãy tiếp tục kiểm tra trên WFX.",
            rmpo_no=rmpo_no,
            site=site,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="(GRN) Nhập kho")
    except Exception as exc:
        message = f"Chưa mở được New GRN: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "GRN_FINALIZE_FAILED", message, module="(GRN) Nhập kho")
    finally:
        if playwright is not None:
            playwright.stop()


def _set_grn_search_filter(
    frame: Frame,
    filter_kind: str,
    value: str,
    *,
    enabled: bool,
) -> None:
    """Điều khiển đúng checkbox + input Document No./Order No. của WFX."""
    checkbox_selector, field_selector = _GRN_SEARCH_FILTERS[filter_kind]
    checkbox = frame.locator(checkbox_selector).first
    field = frame.locator(field_selector).first
    checkbox.wait_for(state="visible", timeout=8_000)
    field.wait_for(state="visible", timeout=8_000)
    # WFX onchange gọi ChkIt(field, checkboxId, false). Click checkbox khi ô
    # còn trống sẽ bị ChkIt đổi ngược về false, khiến Playwright.check() lỗi.
    # Vì vậy luôn điền trước rồi phát change để chính WFX đồng bộ checkbox.
    field.fill(value)
    field.dispatch_event("change")
    if field.input_value(timeout=1_000) != value:
        raise PlaywrightTimeoutError("WFX chưa xác nhận điều kiện tìm GRN.")
    if checkbox.is_checked(timeout=1_000) is not enabled:
        raise PlaywrightTimeoutError(
            "WFX chưa đồng bộ checkbox điều kiện tìm GRN."
        )


def _click_grn_search(frame: Frame) -> None:
    """Click đúng input Search trong #ctrlRpt > table, không dùng số dòng."""
    report = _first_visible(frame.locator("#ctrlRpt"))
    if report is None:
        raise PlaywrightTimeoutError("Không tìm thấy vùng tìm kiếm GRN #ctrlRpt.")
    button = _first_visible(
        report.locator(
            ":scope > table input[type='button'][value='Search' i], "
            "table input[type='button'][value='Search' i]"
        )
    )
    if button is None:
        raise PlaywrightTimeoutError("Không tìm thấy nút Search trong #ctrlRpt.")
    _click(button)


def _wait_grn_result_opened(
    context: Any,
    page_ids: set[int],
    snapshots: dict[int, tuple[Frame | None, str]],
    *,
    timeout_s: float = 25,
) -> None:
    """Xác nhận popup/document mới sau exact link PrintGRN."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in _context_frames(context):
            snapshot = snapshots.get(id(frame))
            is_new_page = id(frame.page) not in page_ids
            changed = snapshot is None or _document_changed(frame, snapshot)
            url = str(frame.url or "").strip().casefold()
            if not changed or (is_new_page and url in {"", "about:blank"}):
                continue
            try:
                frame.page.bring_to_front()
            except PlaywrightError:
                pass
            return
        frames = _context_frames(context)
        _wait(frames[0] if frames else context.pages[0], 150)
    raise PlaywrightTimeoutError(
        "Đã bấm số GRN nhưng WFX chưa mở cửa sổ GRN."
    )


def search_grn_receipt(
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Tìm GRN theo Invoice/RMPO, bỏ Date và mở cột No. đầu tiên."""
    filter_kind = str(filter_kind or "").strip().casefold()
    query = " ".join(str(query or "").split())
    if filter_kind not in {"invoice", "rmpo"}:
        return _result(False, "INVALID_FILTER", "Kiểu tìm GRN không hợp lệ.")
    if not query:
        label = "Số Invoice" if filter_kind == "invoice" else "RMPO No."
        return _result(False, "QUERY_REQUIRED", f"Vui lòng nhập {label}.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        frame = _open_menu_form(
            context,
            page,
            GRN_SEARCH_XPATH,
            _GRN_SEARCH_CONTEXT,
            "GRN Search",
            log,
        )
        # Xóa và bỏ chọn điều kiện cũ để Invoice/RMPO không âm thầm kết hợp.
        for kind in _GRN_SEARCH_FILTERS:
            try:
                _set_grn_search_filter(frame, kind, "", enabled=False)
            except PlaywrightError:
                continue
        _set_grn_search_filter(frame, filter_kind, query, enabled=True)
        date_checkbox = frame.locator(_GRN_DATE_CHECKBOX).first
        date_checkbox.wait_for(state="attached", timeout=8_000)
        date_enabled = date_checkbox.evaluate(
            "element => { if (element.checked) element.click(); return element.checked; }"
        )
        if date_enabled:
            raise PlaywrightTimeoutError("Chưa bỏ tích Date khi tìm GRN.")
        _write_log(log, "[GRN SEARCH] Đã bỏ tích Date.")
        _click_grn_search(frame)
        deadline = time.monotonic() + 35
        result_link = None
        result_frame = None
        while time.monotonic() < deadline:
            for candidate in _context_frames(context):
                try:
                    link = _first_visible(
                        candidate.locator(
                            "table.clsTable tr.clsDataLabel "
                            "a[onclick*='PrintGRN(']"
                        )
                    )
                    if link is not None:
                        result_link = link
                        result_frame = candidate
                        break
                except PlaywrightError:
                    continue
            if result_link is not None:
                break
            frames = _context_frames(context)
            _wait(frames[0] if frames else page, 150)
        if result_link is None or result_frame is None:
            return _result(
                False,
                "GRN_SEARCH_NO_RESULTS",
                "Không tìm thấy GRN phù hợp.",
            )
        try:
            result_row = result_link.locator("xpath=ancestor::tr[1]").first
            row_text = " ".join((result_row.inner_text(timeout=1_000) or "").split())
            if _fold(query) not in _fold(row_text):
                _write_log(
                    log,
                    "[GRN SEARCH] Dòng đầu không hiển thị lại điều kiện; "
                    "vẫn mở đúng cột No. theo kết quả WFX.",
                )
        except PlaywrightError:
            pass
        page_ids, snapshots = _snapshot_context(context, "grn-search-result")
        _click(result_link)
        _wait_grn_result_opened(context, page_ids, snapshots)
        _write_log(
            log,
            "[GRN SEARCH] Đã click đúng link PrintGRN và xác nhận cửa sổ GRN mở.",
        )
        return _result(
            True,
            "GRN_SEARCH_OPENED",
            "Đã mở GRN phù hợp trên WFX.",
            filter_kind=filter_kind,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="(GRN) Nhập kho")
    except Exception as exc:
        message = f"Chưa tìm được GRN: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "GRN_SEARCH_FAILED", message, module="(GRN) Nhập kho")
    finally:
        if playwright is not None:
            playwright.stop()
