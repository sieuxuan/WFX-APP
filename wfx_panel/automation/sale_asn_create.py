"""Tạo Sale ASN từ workbook đã được backend kiểm tra."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _ensure_select_value,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules import (
    _active_wfx_page,
    _click_module_menu_on_page,
)

ADD_ORDER_XPATH = '//*[@id="sectionOrderDetails"]/tbody/tr/td[2]/span/div[3]'
PO_POPUP_SELECTOR = "#wfx_GMPOAsnSearch"
PO_RESULTS_TABLE_XPATH = '//*[@id="wfx_GMPOAsnSearch"]/div[3]/table'
PO_RESULTS_TABLE_SELECTOR = f"xpath={PO_RESULTS_TABLE_XPATH}"
PO_OK_XPATH = '//*[@id="wfx_GMPOAsnSearch"]/table[1]/tbody/tr/td[3]/table/tbody/tr/td[3]'
PO_OK_SELECTOR = f"xpath={PO_OK_XPATH}"
ORDER_GRID_SELECTOR = "#gridOrderDetails_tblGridContent"
PO_SEARCH_SELECTOR = (
    '#wfx_GMPOAsnSearch input[value="Search" i], '
    '#wfx_GMPOAsnSearch input[type="button"][onclick*="Search" i]'
)
PO_CONTINUE_SELECTOR = "#lnkAddnContinue"
STYLE_INPUT_SELECTORS = (
    "#txtStyle",
    "#txtStyleNo",
    "#txtArticle",
    "#txtBuyerStyleRef",
)

ORDER_FIELD_COLUMNS = {
    "carton": "colTotalNoOfCartons",
    "gw": "colTotalGrossWeight",
    "nw": "colTotalNetWeight",
    "cbm": "colTotalVolume",
    "fob_price": "colFFTextField1",
    "service_price": "colFFTextField2",
    "cargo_ready_date": "colFFDate1",
}

SHIPPING_FIELDS = (
    ("#Cell_InvoiceNo", "invoice_no", "value"),
    ("#Cell_InvoiceDate", "invoice_date", "value"),
    ("#Cell_ShippingBillNo", "shipping_bill_no", "value"),
    ("#Cell_ShippingBillDate", "shipping_bill_date", "value"),
    ("#Cell_ShipDate", "shipping_bill_date", "value"),
    ("#Cell_DestinationCountry", "destination", "exact"),
    ("#Cell_FinalDestination", "destination", "exact"),
    ("#ddlConsignorAddress", "__BILL-ADD - PSHK", "exact"),
    ("#ddlDeliveryTerms", "__FOB", "exact"),
    ("#ddlFactory", "factory", "exact"),
    ("#ddlNotify1", "__FIRST", "first"),
)

SHIPPING_FIELD_LABELS = {
    "#Cell_InvoiceNo": "Invoice No.",
    "#Cell_InvoiceDate": "Invoice Date",
    "#Cell_ShippingBillNo": "Shipping Bill No.",
    "#Cell_ShippingBillDate": "Shipping Bill Date",
    "#Cell_ShipDate": "Ship Date",
    "#Cell_DestinationCountry": "Destination Country",
    "#Cell_FinalDestination": "Final Destination",
    "#ddlConsignorAddress": "Consignor Address",
    "#ddlDeliveryTerms": "Delivery Terms",
    "#ddlFactory": "Factory",
    "#ddlNotify1": "Notify",
}

SALE_ASN_STAGE_FRAME_SELECTORS = {
    "order_details": "#sectionOrderDetails",
    "style_details": "#tabStyleDetails",
    "shipping_info": "#tabShippingInfo",
}


def _shipping_warning(label: str, value: str, result: dict[str, Any]) -> str:
    reason = str(result.get("reason") or "không thể điền")
    if reason == "option-not-found":
        return f'{label}: WFX không có lựa chọn "{value}"'
    if reason == "host-not-found":
        return f"{label}: WFX không có trường này"
    if reason == "editor-not-found":
        return f"{label}: trường không thể chỉnh sửa"
    if reason == "document-changed":
        return f"{label}: trang WFX đã thay đổi khi đang điền"
    return f"{label}: {reason}"

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
        let headerIndex = -1;
        rows.forEach((row, index) => {
            const cells = [...row.children].map(cell => fold(cell.textContent));
            if (cells.some(text => /po\s*(no|number)|buyer order/.test(text))) {
                headers = cells; headerIndex = index;
            }
        });
        if (headerIndex < 0) continue;
        const indexFor = patterns => headers.findIndex(text =>
            patterns.some(pattern => pattern.test(text)));
        const poIndex = indexFor([/po\s*(no|number)/, /buyer order/]);
        const styleIndex = indexFor([/style/, /article/]);
        const qtyIndex = indexFor([/dispatched\s*qty/, /dispatch\s*qty/, /^qty$/]);
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
                po_no: clean(cells[poIndex]?.textContent),
                style_no: clean(cells[styleIndex]?.textContent),
                dispatched_qty: clean(cells[qtyIndex]?.textContent),
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

_BUYER_OPTIONS_JS = r"""cell => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const visible = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        return style.display !== 'none' && style.visibility !== 'hidden';
    };
    const controls = [
        ...cell.querySelectorAll('select'),
        ...document.querySelectorAll('select:focus, select.clsCombo'),
    ];
    for (const control of controls) {
        const options = [...control.options].map(option => ({
            label: clean(option.textContent), value: clean(option.value),
            disabled: option.disabled,
        })).filter(option => option.label && option.value && !option.disabled
            && !/^\[?select\]?$/i.test(option.label));
        if (options.length) return options;
    }
    const listItems = [...document.querySelectorAll(
        '[role="option"], .select2-results__option, li.clsMultiSelectContent'
    )].filter(visible).map(item => ({
        label: clean(item.textContent), value: clean(item.getAttribute('data-value')),
    })).filter(option => option.label);
    return listItems;
}"""

_SET_CONTROL_JS = r"""spec => {
    const clean = value => String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
    const fold = value => clean(value).toLocaleLowerCase('en');
    const shown = element => {
        if (!element || !element.isConnected || element.disabled || element.readOnly) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const host = document.querySelector(spec.selector);
    if (!host) return {ok: false, reason: 'host-not-found'};
    let control = ['INPUT', 'SELECT', 'TEXTAREA'].includes(host.tagName) ? host : null;
    control = control || [...host.querySelectorAll('input, select, textarea')]
        .find(item => item.type !== 'hidden' && !item.disabled);
    if (!control) {
        const action = host.querySelector('.lblEditable, [contenteditable="true"], span, div:nth-child(2)') || host;
        action.click();
        control = [...host.querySelectorAll('input, select, textarea')]
            .find(item => item.type !== 'hidden' && !item.disabled)
            || [...document.querySelectorAll('select')]
                .filter(item => shown(item)).at(-1);
        if (!control && ['exact', 'first'].includes(spec.mode)) {
            const choices = [...document.querySelectorAll(
                '[role="option"], .select2-results__option, li.clsMultiSelectContent'
            )].filter(shown);
            const chosen = spec.mode === 'first'
                ? choices[0]
                : choices.find(item => fold(item.textContent) === fold(spec.value)
                    || fold(item.getAttribute('data-value')) === fold(spec.value));
            if (chosen) {
                chosen.click();
                return {ok: true, value: clean(chosen.textContent), tag: chosen.tagName};
            }
        }
        control = control || [...document.querySelectorAll('input, textarea')]
            .filter(item => shown(item) && item.type !== 'hidden').at(-1);
    }
    if (!control) return {ok: false, reason: 'editor-not-found'};
    const wanted = clean(spec.value);
    if (control.tagName === 'SELECT') {
        const choices = [...control.options].filter(option => !option.disabled
            && clean(option.value) && !/^\[?select\]?$/i.test(clean(option.textContent)));
        let option = null;
        if (spec.mode === 'first') option = choices[0] || null;
        else option = choices.find(item => fold(item.textContent) === fold(wanted)
            || fold(item.value) === fold(wanted)) || null;
        if (!option) {
            control.dispatchEvent(new MouseEvent(
                'mousedown', {bubbles: true, cancelable: true, view: window}
            ));
            return {
                ok: false,
                reason: 'option-not-found',
                options: choices.map(item => clean(item.textContent)).slice(0, 30),
            };
        }
        control.value = option.value;
        option.selected = true;
    } else if (control.isContentEditable) {
        control.textContent = wanted;
    } else {
        const prototype = control.tagName === 'TEXTAREA'
            ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
        if (setter) setter.call(control, wanted); else control.value = wanted;
    }
    control.dispatchEvent(new Event('input', {bubbles: true}));
    control.dispatchEvent(new Event('change', {bubbles: true}));
    control.dispatchEvent(new Event('blur', {bubbles: true}));
    return {ok: true, value: clean(control.value || control.textContent), tag: control.tagName};
}"""

_MARK_ORDER_GRID_CELL_JS = r"""spec => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const fold = value => clean(value).toLocaleLowerCase('en')
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, ' ').trim();
    const table = document.querySelector(spec.table);
    if (!table) return {ok: false, reason: 'order-grid-not-found'};
    const wanted = fold(spec.po_no);
    const rows = [...table.querySelectorAll('tr.trContent')];
    const candidates = rows.filter(row =>
        fold(row.querySelector('#colOrderRefNum')?.textContent) === wanted
    );
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

_MARK_STYLE_HTS_CELL_JS = r"""spec => {
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const fold = value => clean(value).toLocaleLowerCase('en')
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, ' ').trim();
    const score = (wanted, actual) => {
        if (!wanted || !actual) return 0;
        if (wanted === actual) return 10000;
        if (actual.includes(wanted) || wanted.includes(actual)) {
            return 8000 + Math.min(wanted.length, actual.length);
        }
        const left = new Set(wanted.split(' ').filter(Boolean));
        const right = new Set(actual.split(' ').filter(Boolean));
        let shared = 0;
        left.forEach(token => { if (right.has(token)) shared += 1; });
        return shared * 100 - Math.abs(left.size - right.size);
    };
    const table = document.querySelector('#gridStyleDetails_tblGridContent');
    if (!table) return {ok: false, reason: 'style-grid-not-found'};
    const wanted = fold(spec.style);
    const candidates = [...table.querySelectorAll('tr.trContent')]
        .map(row => {
            const styleCell = row.querySelector('td#colStyle');
            const styleLabel = styleCell?.querySelector('#lblStyle');
            const styleText = clean(
                styleLabel?.getAttribute('title') || styleLabel?.textContent
                || styleCell?.textContent
            );
            return {row, styleText, score: score(wanted, fold(styleText))};
        })
        .filter(item => item.score > 0);
    const bestScore = Math.max(0, ...candidates.map(item => item.score));
    const best = candidates.filter(item => item.score === bestScore);
    if (best.length !== 1) {
        return {
            ok: false,
            reason: 'style-row-ambiguous',
            count: best.length,
            styles: candidates.map(item => item.styleText),
        };
    }
    const cell = best[0].row.querySelector('td#colHTSCode');
    if (!cell) return {ok: false, reason: 'hts-cell-not-found'};
    document.querySelectorAll('[data-wfx-sale-asn-target]').forEach(item =>
        item.removeAttribute('data-wfx-sale-asn-target'));
    cell.setAttribute('data-wfx-sale-asn-target', '1');
    return {ok: true, style: best[0].styleText, column_id: cell.id};
}"""

SALE_ASN_STAGE_LABELS = {
    "po": "Thêm PO",
    "order_details": "Order Details",
    "style_details": "Style Details",
    "shipping_info": "Shipping Info",
}
SALE_ASN_STAGE_ORDER = tuple(SALE_ASN_STAGE_LABELS)


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def _style_similarity(source: str, candidate: str) -> int:
    left, right = _fold(source), _fold(candidate)
    if not left or not right:
        return 0
    if left == right:
        return 10_000
    if left in right or right in left:
        return 8_000 + min(len(left), len(right))
    left_tokens, right_tokens = set(left.split()), set(right.split())
    shared = left_tokens & right_tokens
    return len(shared) * 100 - abs(len(left_tokens) - len(right_tokens))


def _number_key(value: object) -> str:
    text = str(value or "").replace(",", "").strip()
    try:
        return f"{float(text):.6f}".rstrip("0").rstrip(".")
    except ValueError:
        return ""


def _choose_po_candidate(row: dict, candidates: Sequence[dict]) -> dict | None:
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    po_key = _fold(row.get("po_no"))
    exact_po = [item for item in candidates if _fold(item.get("po_no")) == po_key]
    pool = exact_po or list(candidates)
    style = str(row.get("style_no") or "")
    scores = [(_style_similarity(style, str(item.get("style_no") or item.get("text") or "")), item) for item in pool]
    best_score = max((score for score, _item in scores), default=0)
    best = [item for score, item in scores if score == best_score and score > 0]
    if len(best) == 1:
        return best[0]
    qty = _number_key(row.get("qty"))
    qty_matches = [item for item in (best or pool) if qty and _number_key(item.get("dispatched_qty")) == qty]
    return qty_matches[0] if len(qty_matches) == 1 else None


def _frame_with_selector(context: Any, selector: str, timeout_s: float = 20) -> tuple[Page, Frame]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    locator = frame.locator(selector)
                    if locator.count() and locator.first.is_visible():
                        return page, frame
                except PlaywrightError:
                    continue
        if context.pages:
            _wait(context.pages[0], 120)
    raise PlaywrightTimeoutError(f"Không tìm thấy vùng Sale ASN: {selector}")


def _open_new_form(page: Page, xpath: str, log: Callable[[str], None]) -> Frame:
    _click_module_menu_on_page(page, "Sale ASN > New", xpath, log)
    _ensure_select_value(page, "#ddlASNType", "1", "ASN Type", log)
    _ensure_select_value(page, "#ddlASNAgainst", "BuyerOrderDispatch", "ASN Against", log)
    _page, frame = _frame_with_selector(page.context, "#Cell_Buyer")
    return frame


def _refresh_existing_new_form(page: Page, log: Callable[[str], None]) -> Frame | None:
    """Reload form Sale ASN New đang mở để bỏ Buyer/datasource cũ."""

    try:
        existing_page, frame = _frame_with_selector(
            page.context,
            "#Cell_Buyer",
            timeout_s=1,
        )
    except (PlaywrightError, PlaywrightTimeoutError):
        return None
    if "wfxsalesasn" not in frame.url.casefold():
        return None
    try:
        frame.goto(
            frame.url,
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        _ensure_select_value(
            existing_page,
            "#ddlASNType",
            "1",
            "ASN Type",
            log,
        )
        _ensure_select_value(
            existing_page,
            "#ddlASNAgainst",
            "BuyerOrderDispatch",
            "ASN Against",
            log,
        )
        _page, refreshed = _frame_with_selector(
            page.context,
            "#Cell_Buyer",
            timeout_s=15,
        )
    except (PlaywrightError, PlaywrightTimeoutError):
        _write_log(
            log,
            "[SALE ASN] Không refresh được form New đang mở; sẽ mở lại từ menu.",
        )
        return None
    _write_log(
        log,
        "[SALE ASN] Đã refresh form New đang mở trước khi chọn Buyer.",
    )
    return refreshed


def _buyer_cell(frame: Frame) -> Any:
    cell = frame.locator("#Cell_Buyer").first
    cell.wait_for(state="visible", timeout=8_000)
    return cell


def _normalise_buyer_options(raw: Sequence[dict] | None) -> list[dict[str, str]]:
    """Chuẩn hóa danh sách Buyer và bỏ option placeholder/trùng tên."""

    seen: set[str] = set()
    options: list[dict[str, str]] = []
    for item in raw or []:
        label = " ".join(str(item.get("label") or "").split())
        value = str(item.get("value") or "").strip()
        identity = label.casefold()
        if label and value and identity not in seen:
            seen.add(identity)
            options.append({"label": label, "value": value})
    return options


def _buyer_options(frame: Frame, timeout_s: float = 15) -> list[dict[str, str]]:
    """Chờ dropdown Buyer lazy-bind rồi đọc option thật từ ``#ddlBuyer``.

    WFX render ``#Cell_Buyer`` và ``[Select]`` trước, sau đó mới bind danh sách
    qua request nền. Vì vậy sự xuất hiện của cell chưa đồng nghĩa dropdown đã
    sẵn sàng. Chỉ mở Select2 khi đã chờ một nhịp mà native select vẫn trống.
    """

    cell = _buyer_cell(frame)
    deadline = time.monotonic() + timeout_s
    open_after = time.monotonic() + min(1.5, timeout_s / 2)
    dropdown_opened = False
    while time.monotonic() < deadline:
        options = _normalise_buyer_options(cell.evaluate(_BUYER_OPTIONS_JS) or [])
        if options:
            return options
        if not dropdown_opened and time.monotonic() >= open_after:
            try:
                cell.locator(".select2-selection").first.click(timeout=2_000)
            except PlaywrightError:
                try:
                    cell.locator("select#ddlBuyer, select").first.click(timeout=2_000)
                except PlaywrightError:
                    pass
            dropdown_opened = True
        _wait(frame, 150)
    return []


def _select_buyer(frame: Frame, buyer: str) -> None:
    options = _buyer_options(frame)
    exact = [item for item in options if _fold(item["label"]) == _fold(buyer)]
    if len(exact) != 1:
        raise RuntimeError("SALE_ASN_BUYER_NOT_FOUND")
    selected = _set_control(
        frame,
        "#Cell_Buyer",
        exact[0]["label"],
        "exact",
    )
    if not selected.get("ok"):
        raise RuntimeError(f"SALE_ASN_BUYER_NOT_CONFIRMED:{selected.get('reason')}")


def _set_control(
    frame: Frame,
    selector: str,
    value: str,
    mode: str,
    timeout_s: float = 3,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {"ok": False, "reason": "not-found"}
    while time.monotonic() < deadline:
        try:
            last = frame.evaluate(
                _SET_CONTROL_JS,
                {"selector": selector, "value": value, "mode": mode},
            )
            if last.get("ok"):
                return last
        except PlaywrightError:
            last = {"ok": False, "reason": "document-changed"}
        _wait(frame, 120)
    return last


def scan_sale_asn_buyers(
    xpath: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    playwright = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _refresh_existing_new_form(page, log)
        if frame is None:
            frame = _open_new_form(page, xpath, log)
        _write_log(log, "[SALE ASN] Đang chờ WFX bind danh sách Buyer...")
        buyers = _buyer_options(frame)
        if not buyers:
            raise PlaywrightTimeoutError("Danh sách Buyer chưa bind dữ liệu.")
        _write_log(log, f"[SALE ASN] Đã quét {len(buyers)} Buyer.")
        return _result(
            True,
            "SALE_ASN_BUYERS_SCANNED",
            f"Đã quét {len(buyers)} Buyer từ WFX.",
            buyers=buyers,
        )
    except RuntimeError as error:
        code = str(error)
        return _result(False, code, "Không mở được phiên Sale ASN để quét Buyer.")
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        message = f"Không quét được Buyer Sale ASN: {_first_line(error)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_BUYER_SCAN_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def _fill_popup_input(frame: Frame, selector: str, value: str) -> bool:
    locator = frame.locator(selector).first
    try:
        locator.wait_for(state="visible", timeout=12_000)
    except (PlaywrightError, PlaywrightTimeoutError):
        return False
    locator.fill(value, timeout=5_000)
    return locator.input_value(timeout=1_000) == value


def _select_popup_destination(frame: Frame, destination: str) -> bool:
    select = frame.locator("#wfx_GMPOAsnSearch select[name='cboDestination'], #wfx_GMPOAsnSearch #cboDestination")
    if not select.count() or not select.first.is_visible():
        return False
    options = select.first.locator("option")
    exact = []
    for index in range(options.count()):
        option = options.nth(index)
        label = " ".join((option.inner_text() or option.get_attribute("title") or "").split())
        if _fold(label) == _fold(destination) or _fold(option.get_attribute("value")) == _fold(destination):
            exact.append(option.get_attribute("value") or label)
    if len(exact) != 1:
        return False
    select.first.select_option(value=exact[0])
    return True


def _click_search(frame: Frame) -> None:
    search = frame.locator(PO_SEARCH_SELECTOR).first
    if not search.count():
        search = frame.locator("xpath=//*[@id='wfx_GMPOAsnSearch']/table[3]/tbody/tr/td[2]/input").first
    search.wait_for(state="visible", timeout=5_000)
    search.click(timeout=5_000)
    _wait(frame, 700)


def _search_po(frame: Frame, row: dict, *, destination: bool, style: bool) -> list[dict]:
    if not _fill_popup_input(frame, "#txtOCNo", str(row.get("po_no") or "")):
        raise RuntimeError("SALE_ASN_PO_SEARCH_NOT_READY")
    if destination:
        _select_popup_destination(frame, str(row.get("destination") or ""))
    if style:
        for selector in STYLE_INPUT_SELECTORS:
            if _fill_popup_input(frame, selector, str(row.get("style_no") or "")):
                break
    _click_search(frame)
    table = frame.locator(PO_RESULTS_TABLE_SELECTOR).first
    table.wait_for(state="visible", timeout=5_000)
    return list(table.evaluate(_PO_RESULTS_JS) or [])


def _auto_add_po(
    frame: Frame,
    row: dict,
    log: Callable[[str], None],
    *,
    final: bool = False,
) -> tuple[bool, list[dict], str]:
    attempts = ((False, False, "PO No"), (True, False, "PO + Destination"), (True, True, "PO + Style"))
    last: list[dict] = []
    for with_destination, with_style, label in attempts:
        last = _search_po(frame, row, destination=with_destination, style=with_style)
        chosen = _choose_po_candidate(row, last)
        _write_log(log, f"[SALE ASN] Dòng {row.get('source_row')}: {label} → {len(last)} kết quả.")
        if chosen is None:
            if len(last) <= 1:
                continue
            continue
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
        _write_log(
            log,
            (
                f"[SALE ASN] Dòng {row.get('source_row')}: đã chọn checkbox "
                f"{selected.get('value')}."
            ),
        )
        action_selector = PO_OK_SELECTOR if final else PO_CONTINUE_SELECTOR
        button = frame.locator(action_selector).first
        button.wait_for(state="visible", timeout=5_000)
        # WFX đã nhận click và add PO nhưng Playwright có thể chờ navigation
        # tới timeout khi popup Ajax tự detach. DOM click kết thúc ngay; lượt
        # kế tiếp sẽ chờ #txtOCNo visible lại trước khi điền.
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
            # OK đóng popup/page đồng bộ ngay trong handler click. Không được
            # wait trên frame này sau click vì target đã bị dispose hợp lệ.
            return True, last, label
        _wait(frame, 250)
        return True, last, label
    reason = "not_found" if not last else "ambiguous"
    return False, last, reason


def _date_for_wfx(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value


def _number_for_wfx(value: str, *, integer: bool = False) -> str:
    try:
        number = Decimal(value.replace(",", "").strip())
    except InvalidOperation:
        return value
    if integer:
        number = number.quantize(Decimal("1"))
    else:
        number = number.quantize(Decimal("0.0001"))
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _table_value_matches(expected: str, actual: str) -> bool:
    expected_clean = str(expected or "").replace(",", "").strip()
    actual_clean = str(actual or "").replace(",", "").strip()
    try:
        left, right = Decimal(expected_clean), Decimal(actual_clean)
        return abs(left - right) <= Decimal("0.0001")
    except InvalidOperation:
        pass
    date_formats = ("%d/%m/%Y", "%Y-%m-%d", "%d %b %Y", "%m/%d/%Y")
    expected_date = next(
        (
            parsed
            for pattern in date_formats
            if (parsed := _try_date(expected_clean, pattern)) is not None
        ),
        None,
    )
    actual_date = next(
        (
            parsed
            for pattern in date_formats
            if (parsed := _try_date(actual_clean, pattern)) is not None
        ),
        None,
    )
    if expected_date is not None and actual_date is not None:
        return expected_date == actual_date
    return _fold(expected_clean) == _fold(actual_clean)


def _try_date(value: str, pattern: str) -> datetime | None:
    try:
        return datetime.strptime(value, pattern)
    except ValueError:
        return None


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


def _set_order_grid_cell(frame: Frame, po_no: str, column_id: str, value: str) -> None:
    marked = frame.evaluate(
        _MARK_ORDER_GRID_CELL_JS,
        {
            "table": ORDER_GRID_SELECTOR,
            "po_no": po_no,
            "column_id": column_id,
        },
    )
    if not marked.get("ok"):
        raise RuntimeError(f"SALE_ASN_TABLE_MAPPING_FAILED:{marked.get('reason')}")
    _edit_marked_table_cell(frame, value)


def _set_style_hts_cell(frame: Frame, style: str, value: str) -> None:
    marked = frame.evaluate(
        _MARK_STYLE_HTS_CELL_JS,
        {"style": style},
    )
    if not marked.get("ok"):
        raise RuntimeError(f"SALE_ASN_TABLE_MAPPING_FAILED:{marked.get('reason')}")
    _edit_marked_table_cell(frame, value)


def _missing_order_rows(rows: Sequence[dict], present: set[str]) -> list[dict]:
    return [
        dict(row)
        for row in rows
        if _fold(row.get("po_no")) and _fold(row.get("po_no")) not in present
    ]


def _wait_order_grid(
    frame: Frame,
    rows: Sequence[dict],
    timeout_s: float = 10,
    *,
    allow_incomplete: bool = False,
) -> set[str]:
    table = frame.locator(ORDER_GRID_SELECTOR).first
    table.wait_for(state="visible", timeout=int(timeout_s * 1_000))
    expected = {_fold(row.get("po_no")) for row in rows if _fold(row.get("po_no"))}
    deadline = time.monotonic() + timeout_s
    present: set[str] = set()
    while time.monotonic() < deadline:
        try:
            present = {
                _fold(item)
                for item in (
                    table.evaluate(
                        """root => [...root.querySelectorAll(
                                'tr.trContent [id="colOrderRefNum"]'
                            )].map(cell => String(
                                cell.getAttribute('title') || cell.textContent || ''
                            ).trim())"""
                    )
                    or []
                )
                if _fold(item)
            }
        except PlaywrightError:
            # Grid WFX có thể thay tbody khi request Add Order hoàn tất. Locator
            # vẫn resolve lại được ở vòng poll kế tiếp.
            present = set()
        if expected and expected.issubset(present):
            return present
        _wait(frame, 120)
    if allow_incomplete:
        return present
    raise RuntimeError("SALE_ASN_ORDER_GRID_NOT_READY")


def _ensure_order_grid_rows(
    context: Any,
    main_frame: Frame,
    rows: Sequence[dict],
    log: Callable[[str], None],
) -> Frame:
    """Xác nhận PO đã vào grid và phục hồi đúng các dòng bị rơi khi đóng popup."""

    present = _wait_order_grid(
        main_frame,
        rows,
        timeout_s=10,
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
        add.wait_for(state="visible", timeout=5_000)
        add.click(timeout=5_000)
        _popup_page, popup_frame = _frame_with_selector(
            context,
            PO_POPUP_SELECTOR,
            timeout_s=15,
        )

    for index, row in enumerate(missing):
        added, _candidates, _reason = _auto_add_po(
            popup_frame,
            row,
            log,
            final=index == len(missing) - 1,
        )
        if not added:
            raise RuntimeError("SALE_ASN_ORDER_GRID_NOT_READY")

    _main_page, refreshed_frame = _frame_with_selector(
        context,
        "#sectionOrderDetails",
        timeout_s=15,
    )
    _wait_order_grid(refreshed_frame, rows, timeout_s=15)
    _write_log(log, "[SALE ASN] Đã xác nhận đủ PO trong Order Details.")
    return refreshed_frame


def _fill_order_details(frame: Frame, rows: Sequence[dict], log: Callable[[str], None]) -> None:
    for row in rows:
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
                column_id,
                value,
            )
        _write_log(log, f"[SALE ASN] Đã điền Order Details cho {row.get('po_no')}.")


def _fill_style_details(frame: Frame, rows: Sequence[dict], log: Callable[[str], None]) -> None:
    tab = frame.locator("#tabStyleDetails").first
    tab.wait_for(state="visible", timeout=8_000)
    tab.click(timeout=5_000)
    _wait(frame, 500)
    grouped: dict[str, str] = {}
    for row in rows:
        style, code = str(row.get("style_no") or ""), str(row.get("hs_code") or "")
        if not code:
            continue
        old = grouped.setdefault(style, code)
        if old != code:
            raise RuntimeError("SALE_ASN_STYLE_HS_CODE_CONFLICT")
    for style, code in grouped.items():
        _set_style_hts_cell(frame, style, code)
        _write_log(log, f"[SALE ASN] Đã điền HS Code cho Style {style}.")


def _fill_shipping(
    frame: Frame,
    first_row: dict,
    log: Callable[[str], None],
) -> list[str]:
    tab = frame.locator("#tabShippingInfo").first
    tab.wait_for(state="visible", timeout=8_000)
    tab.click(timeout=5_000)
    _wait(frame, 500)
    warnings: list[str] = []
    for selector, key, mode in SHIPPING_FIELDS:
        label = SHIPPING_FIELD_LABELS.get(selector, selector)
        if key == "__FIRST":
            value = ""
        elif key.startswith("__"):
            value = key[2:]
        else:
            value = str(first_row.get(key) or "")
        if key in {"invoice_date", "shipping_bill_date"}:
            value = _date_for_wfx(value)
        if not value.strip() and not key.startswith("__"):
            warning = f"{label}: file không có dữ liệu"
            warnings.append(warning)
            _write_log(log, f"[SALE ASN] Shipping Info bỏ qua {warning}.")
            continue
        try:
            result = _set_control(frame, selector, value, mode, timeout_s=6)
        except Exception as error:
            reason = _first_line(error)
            warning = f"{label}: {reason}"
            warnings.append(warning)
            _write_log(log, f"[SALE ASN] Shipping Info bỏ qua {warning}.")
            continue
        if not result.get("ok"):
            warning = _shipping_warning(label, value, result)
            warnings.append(warning)
            _write_log(log, f"[SALE ASN] Shipping Info bỏ qua {warning}.")
            continue
        _wait(frame, 150)
    if warnings:
        _write_log(
            log,
            f"[SALE ASN] Đã điền Shipping Info; bỏ qua {len(warnings)} trường và chưa bấm Save.",
        )
    else:
        _write_log(log, "[SALE ASN] Đã điền Shipping Info; chưa bấm Save.")
    return warnings


def run_sale_asn_create(
    xpath: str,
    buyer: str,
    rows: Sequence[dict],
    start_index: int = 0,
    log: Callable[[str], None] = print,
    *,
    stage: str = "po",
    skip_stages: Sequence[str] = (),
) -> dict[str, Any]:
    playwright = None
    current_stage = str(stage or "po")
    shipping_warnings: list[str] = []
    try:
        if not buyer.strip():
            return _result(False, "SALE_ASN_BUYER_REQUIRED", "Hãy chọn Buyer trước khi chạy.")
        if not rows:
            return _result(False, "SALE_ASN_FILE_EMPTY", "File Sale ASN chưa có dữ liệu.")
        if current_stage not in SALE_ASN_STAGE_LABELS:
            return _result(
                False,
                "SALE_ASN_CREATE_STAGE_INVALID",
                "Checkpoint tạo Sale ASN không hợp lệ; hãy chọn file lại.",
            )
        skipped = {item for item in skip_stages if item in SALE_ASN_STAGE_LABELS}
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        context = page.context
        if current_stage == "po":
            if start_index <= 0:
                main_frame = _refresh_existing_new_form(page, log)
                if main_frame is None:
                    main_frame = _open_new_form(page, xpath, log)
                _select_buyer(main_frame, buyer)
                add = main_frame.locator(f"xpath={ADD_ORDER_XPATH}").first
                add.wait_for(state="visible", timeout=8_000)
                add.click(timeout=5_000)
                _write_log(log, "[SALE ASN] Đã chọn Buyer và mở Add Order Details.")
            first_pending = max(0, int(start_index))
            if first_pending < len(rows):
                _popup_page, popup_frame = _frame_with_selector(
                    context,
                    PO_POPUP_SELECTOR,
                    timeout_s=15,
                )

            for index in range(first_pending, len(rows)):
                row = dict(rows[index])
                added, candidates, reason = _auto_add_po(
                    popup_frame,
                    row,
                    log,
                    final=index == len(rows) - 1,
                )
                if not added:
                    final_pending = index == len(rows) - 1
                    manual_action = "OK" if final_pending else "Add & Continue"
                    return _result(
                        True,
                        "SALE_ASN_PO_SELECTION_REQUIRED",
                        (
                            f"Dòng {row.get('source_row')} · PO {row.get('po_no')} cần bạn chọn trên WFX. "
                            f"Chọn đúng dòng rồi bấm {manual_action}; sau đó quay lại app bấm Tiếp tục."
                        ),
                        pending_index=index,
                        next_index=index + 1,
                        source_row=row.get("source_row"),
                        po_no=row.get("po_no"),
                        style_no=row.get("style_no"),
                        reason=reason,
                        candidates=candidates[:20],
                        completed=index,
                        total=len(rows),
                    )
            current_stage = "order_details"

        frame_selector = SALE_ASN_STAGE_FRAME_SELECTORS[current_stage]
        _main_page, main_frame = _frame_with_selector(
            context,
            frame_selector,
            timeout_s=15,
        )
        start_stage_index = SALE_ASN_STAGE_ORDER.index(current_stage)
        for step in SALE_ASN_STAGE_ORDER[start_stage_index:]:
            current_stage = step
            if step in skipped:
                _write_log(
                    log,
                    f"[SALE ASN] Đã bỏ qua bước {SALE_ASN_STAGE_LABELS[step]} theo yêu cầu.",
                )
                continue
            if step == "order_details":
                main_frame = _ensure_order_grid_rows(context, main_frame, rows, log)
                _fill_order_details(main_frame, rows, log)
            elif step == "style_details":
                _fill_style_details(main_frame, rows, log)
            elif step == "shipping_info":
                shipping_warnings.extend(
                    _fill_shipping(main_frame, dict(rows[0]), log) or ()
                )
        warning_message = ""
        if shipping_warnings:
            warning_message = (
                f" Shipping Info đã bỏ qua {len(shipping_warnings)} trường: "
                f"{' · '.join(shipping_warnings)}."
            )
        return _result(
            True,
            "SALE_ASN_FORM_COMPLETED",
            (
                f"Đã thêm {len(rows)} PO và điền Sale ASN.{warning_message} "
                "Hãy kiểm tra lại trên WFX rồi tự bấm Save."
            ),
            completed=len(rows),
            total=len(rows),
            invoice_no=rows[0].get("invoice_no"),
            save_required=True,
            warnings=shipping_warnings,
            warning_count=len(shipping_warnings),
        )
    except RuntimeError as error:
        code = str(error).split(":", 1)[0] or "SALE_ASN_CREATE_FAILED"
        message = f"Không hoàn tất Sale ASN: {_first_line(error)}"
        _write_log(log, message)
        return _result(
            False,
            code,
            message,
            resumable=current_stage in SALE_ASN_STAGE_LABELS,
            resume_stage=current_stage,
            stage_label=SALE_ASN_STAGE_LABELS.get(current_stage, current_stage),
            can_skip=current_stage != "po",
        )
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        message = f"Sale ASN chưa sẵn sàng: {_first_line(error)}"
        _write_log(log, message)
        return _result(
            False,
            "SALE_ASN_CREATE_FAILED",
            message,
            resumable=current_stage in SALE_ASN_STAGE_LABELS,
            resume_stage=current_stage,
            stage_label=SALE_ASN_STAGE_LABELS.get(current_stage, current_stage),
            can_skip=current_stage != "po",
        )
    except Exception as error:
        message = f"{type(error).__name__}: {_first_line(error)}"
        _write_log(log, message)
        return _result(
            False,
            "SALE_ASN_CREATE_FAILED",
            message,
            resumable=current_stage in SALE_ASN_STAGE_LABELS,
            resume_stage=current_stage,
            stage_label=SALE_ASN_STAGE_LABELS.get(current_stage, current_stage),
            can_skip=current_stage != "po",
        )
    finally:
        if playwright is not None:
            playwright.stop()
