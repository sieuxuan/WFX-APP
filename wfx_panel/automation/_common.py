"""Hằng số + helper dùng chung cho lớp automation WFX (tách từ login.py).

Cũng re-export các import stdlib/playwright để các module con lấy qua đây,
giữ một nguồn import duy nhất.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import (
    Browser,
    Frame,
    Page,
    Playwright,
)
from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from wfx_panel.automation.runtime import checkpoint, sync_playwright
from wfx_panel.constants import DIVISIONS

URL = "https://prosports.worldfashionexchange.com/wfx_Home.aspx"


COMPANY_ID = "psh"


CDP_HOST = os.getenv("WFX_CDP_HOST", "127.0.0.1")


CDP_PORT = int(os.getenv("WFX_CDP_PORT", "9222"))


CDP_URL = f"http://{CDP_HOST}:{CDP_PORT}"


DEFAULT_TIMEOUT_MS = 20_000


CATALOG_XPATH = '//*[@id="0003_6200"]/a'


def _wait(target: Any, milliseconds: int) -> None:
    """Wait theo lát ngắn để nút Stop phản hồi tại checkpoint an toàn."""
    remaining = max(0, int(milliseconds))
    while remaining:
        checkpoint()
        step = min(100, remaining)
        target.wait_for_timeout(step)
        remaining -= step
    checkpoint()


def _sleep(seconds: float) -> None:
    """Sleep có thể hủy mà không cắt ngang một thao tác DOM đang thực thi."""
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        checkpoint()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))


def _write_log(log: Callable[[str], None], message: str) -> None:
    """Không để lỗi encoding của console làm hỏng thao tác browser."""
    try:
        log(message)
    except UnicodeEncodeError:
        log(message.encode("ascii", errors="backslashreplace").decode("ascii"))


def _result(
    ok: bool,
    code: str,
    message: str,
    **data: Any,
) -> dict[str, Any]:
    return {"ok": ok, "code": code, "message": message, **data}


def _style_status_suffix(style: dict[str, Any] | None) -> str:
    """Chuỗi ngắn để đưa Season/CostSheet lên status của panel."""
    style = style or {}
    season = str(style.get("season") or "—").strip()
    cost_status = str(style.get("internal_costsheet_status") or "—").strip()
    return f" Season: {season} · CostSheet: {cost_status}."


def _click(locator: Any) -> None:
    """Click menu ASP.NET, dùng JavaScript fallback nếu menu đang bị ẩn."""
    checkpoint()
    locator.wait_for(state="attached")
    try:
        locator.click(timeout=3_000)
    except PlaywrightTimeoutError:
        locator.evaluate("element => element.click()")


def _first_visible(locator: Any) -> Any | None:
    for index in range(locator.count()):
        checkpoint()
        candidate = locator.nth(index)
        try:
            if candidate.is_visible():
                return candidate
        except PlaywrightError:
            continue
    return None


_MODULE_GRID_STATE_JS = """root => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' &&
            Number(style.opacity || 1) !== 0 && rect.width > 0 && rect.height > 0;
    };
    const loading = [
        '.ag-overlay-loading-wrapper', '.ag-loading', '.ag-row-loading'
    ].some(selector => [...root.querySelectorAll(selector)].some(shown));
    const noRows = [
        '.ag-overlay-no-rows-wrapper', '.ag-overlay-no-rows-center'
    ].some(selector => [...root.querySelectorAll(selector)].some(shown));
    const rows = [...root.querySelectorAll(
        '.ag-center-cols-container .ag-row[row-index], ' +
        '.ag-center-cols-container [role="row"][row-index]'
    )].filter(row => {
        if (!shown(row) || row.classList.contains('ag-row-loading') ||
            row.classList.contains('ag-row-ghost') ||
            row.getAttribute('aria-hidden') === 'true') return false;
        const viewport = row.closest('.ag-center-cols-viewport, .ag-body-viewport');
        if (!viewport) return true;
        const r = row.getBoundingClientRect();
        const v = viewport.getBoundingClientRect();
        return r.bottom > v.top + 0.5 && r.top < v.bottom - 0.5;
    });
    const header = root.querySelector('.ag-header');
    const headerRect = header?.getBoundingClientRect();
    const filterRows = [...root.querySelectorAll(
        '.ag-header-row-column-filter, .ag-floating-filter'
    )];
    const rowRects = filterRows.map(row => row.getBoundingClientRect());
    const visuallyAvailable = input => {
        if (!shown(input) || input.disabled || !headerRect) return false;
        const row = input.closest(
            '.ag-header-row-column-filter, .ag-floating-filter'
        );
        const rowRect = row?.getBoundingClientRect();
        const inputRect = input.getBoundingClientRect();
        if (!rowRect || rowRect.height < 16 || headerRect.height < 50) {
            return false;
        }
        const visibleWidth = Math.min(inputRect.right, headerRect.right) -
            Math.max(inputRect.left, headerRect.left);
        const visibleHeight = Math.min(inputRect.bottom, headerRect.bottom) -
            Math.max(inputRect.top, headerRect.top);
        return visibleWidth >= 8 && visibleHeight >= 12;
    };
    const filterInputs = [...root.querySelectorAll(
        '.ag-floating-filter input, .ag-header-row-column-filter input'
    )].filter(visuallyAvailable);
    return {
        loading,
        noRows,
        renderedRows: rows.length,
        filterVisible: filterInputs.length > 0,
        filterInputCount: filterInputs.length,
        headerHeight: headerRect?.height || 0,
        filterRowHeight: Math.max(0, ...rowRects.map(rect => rect.height))
    };
}"""


def _wait_frame_with_selectors(
    page: Page,
    selectors: tuple[str, ...],
    timeout_s: float = 20,
) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                if all(frame.locator(selector).count() > 0 for selector in selectors):
                    return frame
            except PlaywrightError:
                continue
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        f"Không tìm thấy frame chứa: {', '.join(selectors)}"
    )


def _ensure_select_value(
    page: Page,
    selector: str,
    value: str,
    label: str,
    log: Callable[[str], None],
) -> None:
    deadline = time.monotonic() + 12
    last_value = ""
    while time.monotonic() < deadline:
        frame = _wait_frame_with_selectors(page, (selector,), timeout_s=3)
        field = frame.locator(selector)
        last_value = field.input_value(timeout=1_000)
        if last_value == value:
            _write_log(log, f"[SALE ASN NEW] {label} đã đúng: {value}")
            return
        field.dispatch_event("mousedown")
        field.locator(f'option[value="{value}"]').wait_for(
            state="attached", timeout=4_000
        )
        _write_log(log, f"[SALE ASN NEW] Đang chọn {label}: {value}")
        field.select_option(value=value, timeout=4_000)
        _wait(page, 300)
    raise PlaywrightTimeoutError(
        f"WFX không xác nhận {label}={value}; current={last_value}"
    )


def _mark_document(frame: Frame | None, prefix: str) -> tuple[Frame | None, str]:
    marker = f"{prefix}-{time.monotonic_ns()}"
    if frame is not None:
        try:
            frame.evaluate(
                "marker => { window.__wfxPanelDocumentMarker = marker; }",
                marker,
            )
        except PlaywrightError:
            pass
    return frame, marker


def _document_changed(frame: Frame, snapshot: tuple[Frame | None, str]) -> bool:
    old_frame, marker = snapshot
    if old_frame is None or frame != old_frame:
        return True
    try:
        current = frame.evaluate(
            "() => window.__wfxPanelDocumentMarker || ''"
        )
        return current != marker
    except PlaywrightError:
        return True


_COMPANY_ROWS_JS = """(args) => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' &&
            Number(style.opacity || 1) !== 0 && rect.width > 0 && rect.height > 0;
    };
    const query = String(args.query || '').toLocaleLowerCase('vi');
    const loading = [
        '.ag-overlay-loading-wrapper', '.ag-loading', '.ag-row-loading',
        '.clsLoading', '.loading', '[aria-busy="true"]'
    ].some(selector => [...document.querySelectorAll(selector)].some(shown));
    const rows = [...document.querySelectorAll('tr')].filter(row =>
        shown(row) && !row.querySelector('#txtCompanyName') &&
        row.querySelector('td.tdContent')
    ).map(row => {
        const companyCell = row.querySelector(
            '[id*="ColCompanyName"], [id*="CompanyName"]'
        );
        const company = (companyCell?.textContent || row.textContent || '')
            .replace(/\\s+/g, ' ').trim();
        const edit = row.querySelector('a#lnkEdit, a[id="lnkEdit"]');
        return {company, matches: company.toLocaleLowerCase('vi').includes(query), hasEdit: !!edit};
    }).filter(row => row.company);
    const noRows = [...document.querySelectorAll('body *')].some(element => {
        if (!shown(element) || element.children.length) return false;
        return /no records?|no data|không có dữ liệu/i.test(element.textContent || '');
    });
    return {rows: rows.slice(0, 50), noRows, loading};
}"""


__all__ = [
    'Any',
    'Browser',
    'CATALOG_XPATH',
    'CDP_HOST',
    'CDP_PORT',
    'CDP_URL',
    'COMPANY_ID',
    'Callable',
    'DEFAULT_TIMEOUT_MS',
    'DIVISIONS',
    'Frame',
    'Page',
    'Path',
    'Playwright',
    'PlaywrightError',
    'PlaywrightTimeoutError',
    'URL',
    'URLError',
    '_COMPANY_ROWS_JS',
    '_MODULE_GRID_STATE_JS',
    '_click',
    '_document_changed',
    '_ensure_select_value',
    '_first_visible',
    '_mark_document',
    '_result',
    '_style_status_suffix',
    '_wait_frame_with_selectors',
    '_write_log',
    'dataclass',
    'json',
    'os',
    'shutil',
    'subprocess',
    'sync_playwright',
    'time',
    'urlopen',
]
