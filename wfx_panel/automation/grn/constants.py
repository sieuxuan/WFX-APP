"""XPath, bộ selector nhận diện context và snippet JS của GRN."""

from __future__ import annotations

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
    const mousedown = element => element.dispatchEvent(new MouseEvent(
        'mousedown', {bubbles: true, cancelable: true, view: window}
    ));
    const host = [...document.querySelectorAll(spec.selector)]
        .find(shown) || document.querySelector(spec.selector);
    if (!host) return [];
    if (spec.open) {
        const action = host.querySelector(
            '.select2-selection, .lblEditable, [contenteditable="true"], span'
        ) || host;
        // Select2 mở bằng mousedown; label WFX mở editor bằng click.
        mousedown(action);
        action.click();
    }
    let selects = [...host.querySelectorAll('select')];
    // Label WFX có thể dựng editor <select> ở cuối document thay vì trong host.
    // Chỉ lấy đúng editor đó: gom mọi select.clsCombo sẽ trộn option của
    // Receipt Type/From vào danh sách Site.
    if (!selects.length) {
        const editor = document.querySelector('select:focus')
            || [...document.querySelectorAll('select')].filter(shown).at(-1);
        if (editor) selects = [editor];
    }
    const labels = [];
    selects.forEach(select => {
        // Dropdown WFX chỉ bind option sau mousedown (như ddlBuyer/ddlPackage),
        // nên lượt đọc đầu có thể rỗng; lượt sau đọc lại option vừa bind.
        mousedown(select);
        [...select.options].forEach(option => {
            const label = clean(option.textContent || option.title);
            if (!option.disabled && clean(option.value) && label
                && !/^\[?select\]?$/i.test(label)) labels.push(label);
        });
    });
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
    const dataCells = row => [...row.children].filter(child => child.tagName === 'TD');
    let matches = rows.filter(row => {
        const cells = dataCells(row);
        const exact = cells.find(cell => [
            'colPONo', 'colPONumber', 'colOrderNo', 'colOrderRefNo'
        ].includes(cell.id));
        const poCell = exact || cells.find(cell =>
            /(^|\s)(po|order)\s*(no|number)(\s|$)/i.test(metadata(cell))
        );
        return fold(text(poCell)) === fold(expectedPo);
    });
    // WFX có thể vẽ Header và Content thành hai table riêng, khi đó cellIndex
    // không trỏ được về tiêu đề cột PO No. Số RMPO đầy đủ đủ đặc trưng để khớp
    // exact trên chính ô của dòng; vẫn bắt buộc đúng một dòng.
    if (!matches.length) {
        matches = rows.filter(row => dataCells(row).some(
            cell => fold(text(cell)) === fold(expectedPo)
        ));
    }
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
