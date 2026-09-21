"""Selector, ngưỡng thời gian và snippet JS của luồng tải Documents."""

from __future__ import annotations

PACKING_LIST_SELECTOR = "#lnkANFPackingList"


BUYER_INVOICE_SELECTOR = "#lnkBuyerInvoice"


DOCUMENTS_FRAME_TIMEOUT_SECONDS = 60


REPORT_READY_TIMEOUT_SECONDS = 180


REPORT_DOWNLOAD_START_TIMEOUT_SECONDS = 180


REPORT_DOWNLOAD_RETRY_DELAY_MS = 1_000


REPORT_DOWNLOAD_MAX_ATTEMPTS = 2


REPORT_DOWNLOAD_POLL_MS = 100


REPORT_DOWNLOAD_PROGRESS_INTERVAL_SECONDS = 15


REPORT_DOWNLOAD_CHUNK_BYTES = 256 * 1024


REPORT_EXPORT_SELECTOR = (
    "#rptCustomReportViewer_ctl05_ctl04_ctl00_ButtonLink, "
    'a[title="Export drop down menu"]'
)


_REPORT_FETCH_START_JS = r"""url => {
    const key = '__wfxSaleAsnReportFetch';
    window[key]?.controller?.abort();
    const controller = new AbortController();
    const state = {
        controller,
        done: false,
        ok: false,
        status: 0,
        error: '',
        bytes: null,
    };
    window[key] = state;
    fetch(url, {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
        signal: controller.signal,
    }).then(async response => {
        const bytes = new Uint8Array(await response.arrayBuffer());
        if (window[key] !== state) return;
        state.ok = response.ok;
        state.status = response.status;
        state.bytes = bytes;
        state.done = true;
    }).catch(error => {
        if (window[key] !== state) return;
        state.error = String(error?.message || error || 'fetch-failed');
        state.done = true;
    });
    return true;
}"""


_REPORT_FETCH_STATE_JS = r"""() => {
    const state = window.__wfxSaleAsnReportFetch;
    if (!state) return {done: true, error: 'fetch-state-missing'};
    const bytes = state.bytes;
    return {
        done: Boolean(state.done),
        ok: Boolean(state.ok),
        status: Number(state.status || 0),
        error: String(state.error || ''),
        size: bytes?.length || 0,
        prefix: bytes?.length >= 2
            ? String.fromCharCode(bytes[0], bytes[1])
            : '',
    };
}"""


_REPORT_FETCH_CHUNK_JS = r"""spec => {
    const bytes = window.__wfxSaleAsnReportFetch?.bytes;
    if (!bytes) return '';
    const chunk = bytes.subarray(spec.offset, spec.offset + spec.size);
    let binary = '';
    for (let index = 0; index < chunk.length; index += 0x8000) {
        binary += String.fromCharCode(...chunk.subarray(index, index + 0x8000));
    }
    return btoa(binary);
}"""


_REPORT_FETCH_CLEANUP_JS = r"""() => {
    const state = window.__wfxSaleAsnReportFetch;
    state?.controller?.abort();
    delete window.__wfxSaleAsnReportFetch;
}"""


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
        let buyer = '';
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
                const compactMeta = meta.replace(/[^a-z0-9]+/g, '');
                const excludedBuyerField = /buyer(order|reference|ref|po|division|style)/
                    .test(compactMeta);
                const buyerField = compactMeta === 'buyer'
                    || compactMeta.includes('buyername')
                    || compactMeta.includes('lblbuyer')
                    || compactMeta.includes('cellbuyer');
                if (!buyer && buyerField && !excludedBuyerField) {
                    buyer = text(cell);
                }
            }
        }
        rows.push({ row_key: rowKey, invoice_no: invoiceNo, buyer, selected });
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
