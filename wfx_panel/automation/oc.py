"""Automation Upload OC qua EDI Buyer PO và mở report Revise OC."""

from __future__ import annotations

import re
from pathlib import Path

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _first_line,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules import _active_wfx_page
from wfx_panel.automation.runtime import cancellation_deferred, checkpoint

EDI_MENU_SELECTOR = "a[href*='mnuEDIBuyerPO']"
REVISION_REPORT_MENU_XPATH = '//*[@id="0004_0110"]/a'
REVISION_REPORT_SELECTOR = (
    "[nodeid='258'] > span.groupNode, span.groupNode"
)
PACKAGE_VALUE = "1"
PACKAGE_LABEL = "StandardSalesOrder"
STATUS_TIMEOUT_SECONDS = 120
CONFIRM_PROCESS_TIMEOUT_SECONDS = 180
CONFIRM_FIRST_PASS_TIMEOUT_SECONDS = 8
CONFIRM_PAGE_SIZE_SELECTOR = "#gridEDIBuyerPO_divPageSize select"
CONFIRM_GRID_SELECTOR = "#gridEDIBuyerPO_tblGridContent"
CONFIRM_TAB_SELECTORS = {
    "new": "#tabNew",
    "revision": "#tabRevision",
}

_STATUS_JS = r"""() => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const key = value => norm(value).toLowerCase().replace(/[^a-z]/g, '');
  const wanted = {
    file_name: 'filename',
    imported: 'dataimported',
    validated: 'datavalidated',
    mapped: 'mappingresolved',
    transaction: 'transactiondetail'
  };
  const readGrid = (headerTable, contentTable) => {
    if (!headerTable || !contentTable) return [];
    const headers = [...headerTable.querySelectorAll('tr:first-child th, tr:first-child td')]
      .map(cell => key(cell.innerText || cell.textContent));
    const columns = {};
    for (const [name, token] of Object.entries(wanted)) {
      columns[name] = headers.findIndex(label => label.includes(token));
    }
    if (columns.imported < 0 || columns.validated < 0 ||
        columns.mapped < 0 || columns.transaction < 0) return [];
    for (const row of contentTable.querySelectorAll('tr')) {
      const cells = [...row.querySelectorAll(':scope > td, :scope > th')];
      const read = index => index >= 0
        ? norm(cells[index]?.innerText || cells[index]?.textContent)
        : '';
      const record = {
        file_name: read(columns.file_name),
        imported: read(columns.imported),
        validated: read(columns.validated),
        mapped: read(columns.mapped),
        transaction: read(columns.transaction),
        detail: norm(row.innerText || row.textContent).slice(0, 800)
      };
      if (record.imported || record.validated || record.mapped) return [record];
    }
    return [];
  };
  const direct = readGrid(
    document.querySelector('#gridEDIPackageImport_tblGridHeader'),
    document.querySelector('#gridEDIPackageImport_tblGridContent')
  );
  if (direct.length) return direct;
  for (const headerTable of document.querySelectorAll('table[id$="_tblGridHeader"]')) {
    const contentId = headerTable.id.replace(/_tblGridHeader$/, '_tblGridContent');
    const result = readGrid(headerTable, document.getElementById(contentId));
    if (result.length) return result;
  }
  return [];
}"""

_FAILED_RECORD_JS = r"""() => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const key = value => norm(value).toLowerCase().replace(/[^a-z0-9]/g, '');
  const headerTable = document.querySelector('#gridFailedRecord_tblGridHeader');
  const contentTable = document.querySelector('#gridFailedRecord_tblGridContent');
  if (!headerTable || !contentTable) return [];
  const headers = [...headerTable.querySelectorAll('tr:first-child th, tr:first-child td')]
    .map(cell => norm(cell.innerText || cell.textContent));
  const keyedHeaders = headers.map(key);
  const indexOf = token => keyedHeaders.findIndex(label => label.includes(token));
  const columns = {
    mapping_code: indexOf('mappingcode'),
    doc_no: indexOf('docno'),
    mapping_details: indexOf('mappingdetails'),
    inactive: indexOf('inactive')
  };
  return [...contentTable.querySelectorAll('tr')].slice(0, 50).map(row => {
    const cells = [...row.querySelectorAll(':scope > td, :scope > th')];
    const read = index => index >= 0
      ? norm(cells[index]?.innerText || cells[index]?.textContent)
      : '';
    const pairs = headers.map((header, index) => {
      const value = read(index);
      return header && value ? `${header}: ${value}` : '';
    }).filter(Boolean);
    return {
      mapping_code: read(columns.mapping_code),
      doc_no: read(columns.doc_no),
      mapping_details: read(columns.mapping_details),
      inactive: read(columns.inactive),
      detail: pairs.join(' | ').slice(0, 1200)
    };
  }).filter(record => record.detail);
}"""

_CONFIRM_GROUPS_JS = r"""() => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const table = document.querySelector('#gridEDIBuyerPO_tblGridContent') ||
    document.querySelector('#gridEDIBuyerPO_divFocus');
  if (!table) return [];
  const rows = table.matches('table')
    ? [...table.querySelectorAll(':scope > tbody > tr')]
    : [...table.querySelectorAll('table > tbody > tr')];
  const starts = rows
    .map((row, index) => ({row, index}))
    .filter(item => item.row.querySelector(
      '#colSelector input[type="radio"], #colSelector input[type="checkbox"]'
    ));
  const signature = groupRows => {
    const clone = document.createElement('div');
    groupRows.forEach(row => {
      const copy = row.cloneNode(true);
      copy.querySelectorAll('#colSelector').forEach(cell => cell.remove());
      clone.appendChild(copy);
    });
    const text = norm(clone.textContent).toLocaleLowerCase('en');
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    const rowKey = groupRows[0]?.getAttribute('rowid') || groupRows[0]?.id || '';
    return rowKey ? `row:${rowKey}` : `text:${(hash >>> 0).toString(16)}`;
  };
  return starts.map((start, groupIndex) => {
    const end = starts[groupIndex + 1]?.index ?? rows.length;
    const groupRows = rows.slice(start.index, end);
    const styleCell = groupRows[0].querySelector(
      '#colStyle, #lblStyle, [id*="Style" i]'
    );
    return {
      key: signature(groupRows),
      label: norm(styleCell?.getAttribute('title') || styleCell?.textContent ||
        groupRows[0].textContent).slice(0, 180),
      row_count: groupRows.length,
    };
  });
}"""

_PREPARE_REVISION_STYLE_JS = r"""targetKey => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const table = document.querySelector('#gridEDIBuyerPO_tblGridContent') ||
    document.querySelector('#gridEDIBuyerPO_divFocus');
  if (!table) return {ok: false, reason: 'grid-not-found'};
  const rows = table.matches('table')
    ? [...table.querySelectorAll(':scope > tbody > tr')]
    : [...table.querySelectorAll('table > tbody > tr')];
  const starts = rows
    .map((row, index) => ({row, index}))
    .filter(item => item.row.querySelector(
      '#colSelector input[type="radio"], #colSelector input[type="checkbox"]'
    ));
  const signature = groupRows => {
    const clone = document.createElement('div');
    groupRows.forEach(row => {
      const copy = row.cloneNode(true);
      copy.querySelectorAll('#colSelector').forEach(cell => cell.remove());
      clone.appendChild(copy);
    });
    const text = norm(clone.textContent).toLocaleLowerCase('en');
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    const rowKey = groupRows[0]?.getAttribute('rowid') || groupRows[0]?.id || '';
    return rowKey ? `row:${rowKey}` : `text:${(hash >>> 0).toString(16)}`;
  };
  let groupRows = null;
  for (let groupIndex = 0; groupIndex < starts.length; groupIndex += 1) {
    const end = starts[groupIndex + 1]?.index ?? rows.length;
    const candidate = rows.slice(starts[groupIndex].index, end);
    if (signature(candidate) === targetKey) {
      groupRows = candidate;
      break;
    }
  }
  if (!groupRows) return {ok: false, reason: 'style-changed'};
  const rowPlans = groupRows.map((row, rowIndex) => {
    const cell = row.querySelector('#colWFXSalesOrder');
    const select = cell?.querySelector('select');
    if (!select) return {row, cell, select: null, choices: [], rowIndex};
    cell.click();
    select.focus();
    select.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
    const choices = [...select.options]
      .filter(option => !option.disabled)
      .map(option => ({value: norm(option.value), label: norm(option.textContent)}))
      .filter(option => option.value &&
        !/^(select|choose|--|\[select\])$/i.test(option.label));
    const unique = [...new Map(
      choices.map(option => [option.value.toLocaleLowerCase('en'), option])
    ).values()];
    return {row, cell, select, choices: unique, rowIndex};
  });
  const ambiguous = rowPlans.find(plan => plan.choices.length > 1);
  if (ambiguous) {
    return {
      ok: false,
      reason: 'multiple-sales-orders',
      row_number: ambiguous.rowIndex + 1,
      options: ambiguous.choices.map(option => option.label || option.value),
    };
  }
  let selectedCount = 0;
  let emptyCount = 0;
  rowPlans.forEach(plan => {
    if (plan.choices.length === 0) {
      emptyCount += 1;
      return;
    }
    plan.cell?.click();
    plan.select.focus();
    plan.select.value = plan.choices[0].value;
    plan.select.dispatchEvent(new Event('input', {bubbles: true}));
    plan.select.dispatchEvent(new Event('change', {bubbles: true}));
    selectedCount += 1;
  });
  return {
    ok: true,
    selected_count: selectedCount,
    empty_count: emptyCount,
    row_count: groupRows.length,
  };
}"""

_MARK_CONFIRM_STYLE_JS = r"""targetKey => {
  const norm = value => String(value || '').replace(/\s+/g, ' ').trim();
  const table = document.querySelector('#gridEDIBuyerPO_tblGridContent') ||
    document.querySelector('#gridEDIBuyerPO_divFocus');
  if (!table) return {ok: false, reason: 'grid-not-found'};
  const rows = table.matches('table')
    ? [...table.querySelectorAll(':scope > tbody > tr')]
    : [...table.querySelectorAll('table > tbody > tr')];
  const starts = rows
    .map((row, index) => ({row, index}))
    .filter(item => item.row.querySelector(
      '#colSelector input[type="radio"], #colSelector input[type="checkbox"]'
    ));
  const signature = groupRows => {
    const clone = document.createElement('div');
    groupRows.forEach(row => {
      const copy = row.cloneNode(true);
      copy.querySelectorAll('#colSelector').forEach(cell => cell.remove());
      clone.appendChild(copy);
    });
    const text = norm(clone.textContent).toLocaleLowerCase('en');
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    const rowKey = groupRows[0]?.getAttribute('rowid') || groupRows[0]?.id || '';
    return rowKey ? `row:${rowKey}` : `text:${(hash >>> 0).toString(16)}`;
  };
  document.querySelectorAll('[data-wfx-oc-confirm-row]').forEach(row =>
    row.removeAttribute('data-wfx-oc-confirm-row'));
  for (let groupIndex = 0; groupIndex < starts.length; groupIndex += 1) {
    const end = starts[groupIndex + 1]?.index ?? rows.length;
    const groupRows = rows.slice(starts[groupIndex].index, end);
    if (signature(groupRows) !== targetKey) continue;
    groupRows.forEach(row => row.setAttribute('data-wfx-oc-confirm-row', '1'));
    return {ok: true, row_count: groupRows.length};
  }
  return {ok: false, reason: 'style-changed'};
}"""

_ACTIVE_CONFIRM_TAB_JS = r"""() => {
  const score = element => {
    if (!element) return 0;
    let value = 0;
    let current = element;
    for (let depth = 0; current && depth < 4; depth += 1) {
      const classes = String(current.className || '').toLocaleLowerCase('en')
        .split(/[^a-z0-9]+/).filter(Boolean);
      if (classes.some(token => [
        'active', 'selected', 'tabactive', 'tabselected', 'current',
        'clstabtdselected'
      ].includes(token))) value += 10 - depth;
      if (current.getAttribute('aria-selected') === 'true') value += 20 - depth;
      if (current.getAttribute('aria-current') === 'page') value += 20 - depth;
      if (['active', 'selected'].includes(
        String(current.dataset?.state || '').toLocaleLowerCase('en')
      )) value += 20 - depth;
      current = current.parentElement;
    }
    return value;
  };
  const tabs = [
    {mode: 'new', element: document.querySelector('#tabNew')},
    {mode: 'revision', element: document.querySelector('#tabRevision')},
  ].filter(tab => tab.element);
  if (tabs.length !== 2) return '';
  const ranked = tabs.map(tab => ({...tab, score: score(tab.element)}))
    .sort((left, right) => right.score - left.score);
  if (ranked[0].score > 0 && ranked[0].score > ranked[1].score) {
    return ranked[0].mode;
  }
  const focused = tabs.find(tab => tab.element === document.activeElement ||
    tab.element.contains(document.activeElement));
  return focused?.mode || '';
}"""


def _visible_in_frames(
    page: Page,
    selector: str,
    *,
    timeout_s: float = 25,
) -> tuple[Frame, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        checkpoint()
        for frame in page.frames:
            try:
                matches = frame.locator(selector)
                for index in range(matches.count()):
                    candidate = matches.nth(index)
                    if candidate.is_visible() and candidate.is_enabled():
                        return frame, candidate
            except PlaywrightError:
                continue
        _wait(page, 200)
    raise PlaywrightTimeoutError(f"Không tìm thấy control: {selector}")


def _attached_in_frames(
    page: Page,
    selector: str,
    *,
    timeout_s: float = 25,
) -> tuple[Frame, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        checkpoint()
        for frame in page.frames:
            try:
                matches = frame.locator(selector)
                if matches.count():
                    return frame, matches.first
            except PlaywrightError:
                continue
        _wait(page, 200)
    raise PlaywrightTimeoutError(f"Không tìm thấy control: {selector}")


def _toolbar_link(
    page: Page,
    label: str,
    *,
    timeout_s: float = 25,
) -> tuple[Frame, Any]:
    expected = " ".join(label.casefold().split())
    deadline = time.monotonic() + timeout_s
    selectors = (
        "a.ToolLink",
        "a.clsPageToolButton",
        "button",
        "input[type='button']",
        "[role='button']",
    )
    while time.monotonic() < deadline:
        checkpoint()
        for frame in page.frames:
            for selector in selectors:
                try:
                    matches = frame.locator(selector)
                    for index in range(matches.count()):
                        candidate = matches.nth(index)
                        if not candidate.is_visible() or not candidate.is_enabled():
                            continue
                        text = " ".join(
                            str(
                                candidate.get_attribute("value")
                                or candidate.inner_text(timeout=500)
                                or ""
                            )
                            .casefold()
                            .split()
                        )
                        if text == expected or expected in text:
                            return frame, candidate
                except PlaywrightError:
                    continue
        _wait(page, 200)
    raise PlaywrightTimeoutError(f"Không tìm thấy toolbar: {label}")


def _select_exact_option(
    page: Page,
    selector: str,
    value: str,
    label: str,
    field_label: str,
    *,
    timeout_s: float = 30,
) -> str:
    selected_value = ""
    option_seen = False
    last_error = ""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        checkpoint()
        try:
            _frame, select = _visible_in_frames(page, selector, timeout_s=3)
            # WFX chỉ bind đủ Buyer/Package trong handler onmousedown.
            select.dispatch_event("mousedown", timeout=2_000)
            options = select.locator("option")
            for index in range(options.count()):
                option = options.nth(index)
                option_value = str(option.get_attribute("value") or "")
                option_label = " ".join((option.inner_text() or "").split())
                option_title = " ".join(
                    (option.get_attribute("title") or "").split()
                )
                if (
                    (value and option_value == value)
                    or option_label.casefold() == label.casefold()
                    or option_title.casefold() == label.casefold()
                ):
                    selected_value = option_value
                    option_seen = True
                    break
            if selected_value:
                if select.input_value(timeout=1_000) == selected_value:
                    return selected_value
                try:
                    select.select_option(value=selected_value, timeout=5_000)
                except PlaywrightError as error:
                    last_error = _first_line(error)
                    message = str(error).casefold()
                    if not any(
                        marker in message
                        for marker in (
                            "frame was detached",
                            "execution context was destroyed",
                            "target page, context or browser has been closed",
                        )
                    ):
                        raise
                _wait(page, 300)
        except PlaywrightError:
            selected_value = ""
        _wait(page, 200)
    if not option_seen:
        raise PlaywrightTimeoutError(
            f"{field_label} không có lựa chọn '{label}'."
        )
    suffix = f" Lỗi gần nhất: {last_error}" if last_error else ""
    raise PlaywrightTimeoutError(
        f"WFX chưa xác nhận {field_label}='{label}'.{suffix}"
    )


def _open_edi_form(page: Page, buyer: str, log: Callable[[str], None]) -> Frame:
    _frame, menu = _attached_in_frames(page, EDI_MENU_SELECTOR, timeout_s=12)
    _write_log(log, "[OC EDI] Mở EDI Buyer PO")
    _click(menu)
    _select_exact_option(page, "#ddlBuyer", "", buyer, "Buyer")
    _write_log(log, f"[OC EDI] Đã chọn Buyer: {buyer}")
    _select_exact_option(
        page,
        "#ddlPackage",
        PACKAGE_VALUE,
        PACKAGE_LABEL,
        "Package",
    )
    _write_log(log, f"[OC EDI] Đã chọn Package: {PACKAGE_LABEL}")
    frame, _package_select = _visible_in_frames(page, "#ddlPackage", timeout_s=5)
    return frame


def _process_package(page: Page, upload_path: Path, log: Callable[[str], None]) -> None:
    _frame, import_link = _toolbar_link(page, "Import", timeout_s=30)
    _click(import_link)
    _popup_frame, file_input = _attached_in_frames(
        page,
        "#popupObjectAttachment input[type='file'], "
        "#divFileUpload input[type='file']",
        timeout_s=20,
    )
    file_input.set_input_files(str(upload_path))
    _write_log(log, f"[OC EDI] Đã gắn file {upload_path.name}")
    _process_frame, process_link = _toolbar_link(
        page,
        "Process Package",
        timeout_s=15,
    )
    dialog_messages: list[str] = []

    def accept_process_dialog(dialog: Any) -> None:
        dialog_messages.append(" ".join(str(dialog.message or "").split()))
        dialog.accept()

    page.on("dialog", accept_process_dialog)
    try:
        with cancellation_deferred():
            _click(process_link)
    finally:
        try:
            page.remove_listener("dialog", accept_process_dialog)
        except Exception:
            pass
    _write_log(log, "[OC EDI] Đã gửi Process Package; đang chờ WFX xử lý")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        checkpoint()
        failed_dialog = next(
            (
                message
                for message in dialog_messages
                if re.search(r"error|fail|invalid", message, re.I)
            ),
            "",
        )
        if failed_dialog:
            raise PlaywrightTimeoutError(
                f"Process Package thất bại: {failed_dialog}"
            )
        success_dialog = next(
            (
                message
                for message in dialog_messages
                if re.search(r"success|processed|uploaded", message, re.I)
            ),
            "",
        )
        if success_dialog:
            _write_log(log, f"[OC EDI] {success_dialog}")
            return
        for frame in page.frames:
            try:
                success = frame.locator("#lblSuccessMsg")
                if success.count():
                    text = " ".join((success.first.text_content() or "").split())
                    if text:
                        if re.search(r"error|fail|invalid", text, re.I):
                            raise PlaywrightTimeoutError(
                                f"Process Package thất bại: {text}"
                            )
                        if re.search(r"success|processed|uploaded", text, re.I):
                            _write_log(log, f"[OC EDI] {text}")
                            return
            except PlaywrightTimeoutError:
                raise
            except PlaywrightError:
                continue
        try:
            _toolbar_link(page, "Error Resolution", timeout_s=0.3)
            return
        except PlaywrightTimeoutError:
            pass
        _wait(page, 300)
    raise PlaywrightTimeoutError("WFX chưa xác nhận Process Package.")


def _status_rows(page: Page) -> tuple[Frame | None, list[dict[str, str]]]:
    for frame in page.frames:
        try:
            rows = frame.evaluate(_STATUS_JS)
            if isinstance(rows, list) and rows:
                return frame, rows
        except PlaywrightError:
            continue
    return None, []


def _status_kind(value: str) -> str:
    normalised = " ".join(str(value or "").casefold().split())
    if re.search(
        r"fail|error|invalid|unresolved|not\s+resolved|reject|in\s*progress",
        normalised,
    ):
        return "failed"
    if re.search(r"success|successful|resolved|complete", normalised):
        return "success"
    return "pending"


def _wait_statuses(page: Page, log: Callable[[str], None]) -> list[dict[str, str]]:
    deadline = time.monotonic() + STATUS_TIMEOUT_SECONDS
    last: list[dict[str, str]] = []
    last_summary = ""
    while time.monotonic() < deadline:
        checkpoint()
        _frame, rows = _status_rows(page)
        if rows:
            last = rows
            summary = " | ".join(
                "Imported={imported}, Validated={validated}, Mapping={mapped}".format(
                    imported=row.get("imported", "—") or "—",
                    validated=row.get("validated", "—") or "—",
                    mapped=row.get("mapped", "—") or "—",
                )
                for row in rows
            )
            if summary != last_summary:
                _write_log(log, f"[OC EDI] Trạng thái: {summary}")
                last_summary = summary
            states = [
                _status_kind(row.get(field, ""))
                for row in rows
                for field in ("imported", "validated", "mapped")
            ]
            if any(state == "failed" for state in states):
                return rows
            if states and all(state == "success" for state in states):
                _write_log(
                    log,
                    "[OC EDI] Package mới nhất đạt "
                    "Imported/Validated/Mapping Success",
                )
                return rows
        _wait(page, 500)
    detail = last[0].get("detail", "") if last else "không đọc được bảng trạng thái"
    raise PlaywrightTimeoutError(f"Trạng thái EDI chưa hoàn tất: {detail}")


_STATUS_STAGE_LABELS = {
    "imported": "Data Imported",
    "validated": "Data Validated",
    "mapped": "Mapping Resolved",
}
_STATUS_LINK_SELECTORS = {
    "imported": "a#lnkDataImported",
    "validated": "a#lnkDataValidated",
    "mapped": "a#lnkMappingResolved",
}


def _failed_status(rows: list[dict[str, str]]) -> tuple[str, str]:
    if not rows:
        return "", ""
    latest = rows[0]
    # Mapping thường chứa lỗi nghiệp vụ hữu ích nhất, nên ưu tiên mở trước.
    for field in ("mapped", "validated", "imported"):
        value = latest.get(field, "")
        if _status_kind(value) == "failed":
            return field, value
    return "", ""


def _format_resolution_error(record: dict[str, str]) -> str:
    title = record.get("mapping_code", "").strip()
    details = record.get("mapping_details", "").strip()
    message = " — ".join(part for part in (title, details) if part)
    suffixes = []
    if record.get("doc_no", "").strip():
        suffixes.append(f"Doc No.: {record['doc_no'].strip()}")
    if record.get("inactive", "").strip():
        suffixes.append(f"InActive: {record['inactive'].strip()}")
    if suffixes:
        message = f"{message or 'WFX báo lỗi'} ({'; '.join(suffixes)})"
    return message or record.get("detail", "").strip() or "WFX không hiển thị chi tiết lỗi."


def _open_status_error_details(
    page: Page,
    rows: list[dict[str, str]],
    log: Callable[[str], None],
) -> tuple[str, list[dict[str, str]], list[str]]:
    field, status = _failed_status(rows)
    if not field:
        return "", [], []
    stage = _STATUS_STAGE_LABELS[field]
    selector = _STATUS_LINK_SELECTORS[field]
    target_frame: Frame | None = None
    target: Any = None
    for frame in page.frames:
        try:
            grid_rows = frame.locator("#gridEDIPackageImport_tblGridContent tr")
            for index in range(grid_rows.count()):
                row = grid_rows.nth(index)
                link = row.locator(selector)
                if link.count() and link.first.is_visible() and link.first.is_enabled():
                    target_frame = frame
                    target = link.first
                    break
            if target is not None:
                break
        except PlaywrightError:
            continue
    if target is None or target_frame is None:
        message = f"{stage}: {status} (không mở được chi tiết Failed Record)."
        _write_log(log, f"[OC EDI] {message}")
        return stage, [], [message]

    _write_log(log, f"[OC EDI] Mở chi tiết {stage}: {status}")
    _click(target)
    deadline = time.monotonic() + 12
    records: list[dict[str, str]] = []
    while time.monotonic() < deadline:
        checkpoint()
        try:
            popup = target_frame.locator("#sectionFailedRecord")
            if popup.count() and popup.first.is_visible():
                value = target_frame.evaluate(_FAILED_RECORD_JS)
                if isinstance(value, list) and value:
                    records = value
                    break
        except PlaywrightError:
            pass
        _wait(page, 200)
    errors = [_format_resolution_error(record) for record in records]
    if not errors:
        errors = [f"{stage}: {status} (WFX không hiển thị chi tiết lỗi)."]
    for error in errors[:12]:
        _write_log(log, f"[OC EDI] Lỗi: {error}")
    return stage, records, errors


def _click_pending_transaction(page: Page) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        checkpoint()
        for frame in page.frames:
            try:
                links = frame.locator("a")
                for index in range(links.count()):
                    link = links.nth(index)
                    if not link.is_visible() or not link.is_enabled():
                        continue
                    if " ".join((link.inner_text() or "").casefold().split()) == "pending":
                        _click(link)
                        return
            except PlaywrightError:
                continue
        _wait(page, 250)
    raise PlaywrightTimeoutError("Không tìm thấy Pending ở Transaction Detail.")


def _transaction_checkboxes(frame: Frame) -> list[Any]:
    candidates: list[Any] = []
    try:
        checkboxes = frame.locator("input[type='checkbox']")
        for index in range(checkboxes.count()):
            checkbox = checkboxes.nth(index)
            if not checkbox.is_visible() or not checkbox.is_enabled():
                continue
            try:
                row_text = " ".join(
                    (checkbox.locator("xpath=ancestor::tr[1]").inner_text() or "").split()
                )
            except PlaywrightError:
                row_text = ""
            if re.search(r"select\s+all|all\s+records", row_text, re.I):
                continue
            candidates.append(checkbox)
    except PlaywrightError:
        pass
    return candidates


def _select_first_transaction(page: Page, *, force: bool = False) -> None:
    toolbar_frame, _create_link = _toolbar_link(
        page, "Create Transaction", timeout_s=30
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        checkpoint()
        frames: list[Frame] = [toolbar_frame]
        frames.extend(frame for frame in page.frames if frame is not toolbar_frame)
        for frame in frames:
            candidates = _transaction_checkboxes(frame)
            if not candidates:
                continue
            checkbox = candidates[0]
            try:
                if force and checkbox.is_checked():
                    checkbox.uncheck(timeout=3_000)
                    _wait(page, 150)
                if not checkbox.is_checked():
                    checkbox.check(timeout=5_000)
                if not checkbox.is_checked():
                    checkbox.click(timeout=5_000)
                if checkbox.is_checked():
                    # WFX updates its selected-record state asynchronously after
                    # the native checkbox event. Do not click Create Transaction
                    # in the same tick as the selection.
                    _wait(page, 350)
                    if checkbox.is_checked():
                        return
            except PlaywrightError:
                continue
        _wait(page, 250)
    raise PlaywrightTimeoutError(
        "Không tìm thấy hoặc không xác nhận được checkbox đơn hàng để tạo transaction."
    )


def _create_transaction(page: Page, log: Callable[[str], None]) -> tuple[bool, list[str]]:
    def build_dialog_handler(
        dialog_messages: list[str],
        no_record_state: list[bool],
    ) -> Callable[[Any], None]:
        def accept_create_dialog(dialog: Any) -> None:
            message = " ".join(str(dialog.message or "").split())
            dialog_messages.append(message)
            if re.search(r"no\s+record\s+selected", message, re.I):
                no_record_state[0] = True
            dialog.accept()

        return accept_create_dialog

    for attempt in range(2):
        # Selecting again is safe before the Create Transaction click and closes
        # the race where WFX has rendered the toolbar before binding the row
        # selection. A "No Record Selected" alert confirms no transaction was
        # submitted, so one fresh selection + click is safe as well.
        _select_first_transaction(page, force=attempt > 0)
        _frame, create_link = _toolbar_link(page, "Create Transaction", timeout_s=10)
        dialog_messages: list[str] = []
        no_record_state = [False]
        accept_create_dialog = build_dialog_handler(dialog_messages, no_record_state)

        page.on("dialog", accept_create_dialog)
        try:
            with cancellation_deferred():
                _click(create_link)
                _write_log(log, "[OC EDI] Đã gửi Create Transaction")
                deadline = time.monotonic() + 35
                while time.monotonic() < deadline:
                    # Không cho Stop ngắt đoạn xác nhận sau thao tác không
                    # idempotent. Nếu mất kết nối, caller phải coi transaction
                    # là unconfirmed.
                    checkpoint()
                    if no_record_state[0]:
                        break
                    if any(
                        re.search(r"success|created|complete", message, re.I)
                        for message in dialog_messages
                    ):
                        return True, dialog_messages
                    for frame in page.frames:
                        try:
                            messages = frame.locator(
                                "#lblSuccessMsg, .success, .clsSuccess, "
                                "[class*='success' i], [id*='success' i]"
                            )
                            for index in range(messages.count()):
                                candidate = messages.nth(index)
                                text = " ".join((candidate.text_content() or "").split())
                                if text and re.search(
                                    r"success|created|complete", text, re.I
                                ):
                                    return True, dialog_messages + [text]
                        except PlaywrightError:
                            continue
                    _wait(page, 300)
            if no_record_state[0] and attempt == 0:
                _write_log(
                    log,
                    "[OC EDI] WFX chưa nhận dòng đã chọn; chọn lại và thử Create Transaction một lần.",
                )
                _wait(page, 500)
                continue
            return False, dialog_messages
        finally:
            try:
                page.remove_listener("dialog", accept_create_dialog)
            except Exception:
                pass
    return False, []


def _read_confirm_styles(frame: Frame) -> list[dict[str, Any]]:
    rows = frame.evaluate(_CONFIRM_GROUPS_JS)
    return [dict(row) for row in rows if isinstance(row, dict) and row.get("key")]


def _focus_confirm_grid(page: Page, frame: Frame) -> None:
    for owner in (frame, page):
        try:
            focus = owner.locator("#gridEDIBuyerPO_divFocus")
            if focus.count() and focus.first.is_visible():
                focus.first.click(timeout=2_000)
                return
        except PlaywrightError:
            continue


def _prepare_revision_style(frame: Frame, style_key: str) -> dict[str, Any]:
    prepared = frame.evaluate(_PREPARE_REVISION_STYLE_JS, style_key)
    if not isinstance(prepared, dict):
        return {"ok": False, "reason": "style-changed"}
    return dict(prepared)


def _select_confirm_style(frame: Frame, style_key: str) -> None:
    marked = frame.evaluate(_MARK_CONFIRM_STYLE_JS, style_key)
    if not isinstance(marked, dict) or not marked.get("ok"):
        raise PlaywrightTimeoutError("Style đã thay đổi trước khi chọn Confirm.")
    controls = frame.locator(
        '[data-wfx-oc-confirm-row="1"] #colSelector '
        'input[type="radio"], '
        '[data-wfx-oc-confirm-row="1"] #colSelector '
        'input[type="checkbox"]'
    )
    if not controls.count():
        raise PlaywrightTimeoutError("Không tìm thấy ô chọn của Style.")
    control = controls.first
    try:
        if not control.is_checked():
            control.check(timeout=5_000)
    except PlaywrightError:
        control.click(timeout=5_000)


def _click_confirm_toolbar(page: Page) -> None:
    selector = (
        "#sectionEDIBuyerPO > tbody > tr > td:nth-child(2) "
        "> span > div:nth-child(3) > a"
    )
    try:
        _frame, confirm = _visible_in_frames(page, selector, timeout_s=3)
    except PlaywrightTimeoutError:
        _frame, confirm = _toolbar_link(page, "Confirm", timeout_s=12)
    _click(confirm)


def _click_reject_toolbar(page: Page) -> None:
    selector = (
        "#sectionEDIBuyerPO > tbody > tr > td:nth-child(2) "
        "> span > div:nth-child(5) > a"
    )
    try:
        _frame, reject = _visible_in_frames(page, selector, timeout_s=3)
    except PlaywrightTimeoutError:
        _frame, reject = _toolbar_link(page, "Reject", timeout_s=12)

    def accept_reject_dialog(dialog: Any) -> None:
        dialog.accept()

    page.on("dialog", accept_reject_dialog)
    try:
        _click(reject)
    finally:
        try:
            page.remove_listener("dialog", accept_reject_dialog)
        except Exception:
            pass


def _active_confirm_mode(page: Page) -> str:
    detected: set[str] = set()
    for frame in page.frames:
        try:
            mode = str(frame.evaluate(_ACTIVE_CONFIRM_TAB_JS) or "")
        except PlaywrightError:
            continue
        if mode in CONFIRM_TAB_SELECTORS:
            detected.add(mode)
    if len(detected) == 1:
        return detected.pop()
    raise PlaywrightTimeoutError(
        "Hãy mở đúng tab New hoặc Revision trên EDI Buyer PO trước khi Reject All."
    )


def _confirm_frame(page: Page, *, timeout_s: float = 12) -> Frame:
    try:
        frame, _grid = _attached_in_frames(
            page,
            CONFIRM_GRID_SELECTOR,
            timeout_s=min(timeout_s, 4),
        )
        return frame
    except PlaywrightTimeoutError:
        frame, _grid = _attached_in_frames(
            page,
            "#gridEDIBuyerPO_divFocus",
            timeout_s=timeout_s,
        )
        return frame


def _wait_style_processed(
    page: Page,
    frame: Frame,
    style_key: str,
    *,
    timeout_s: float,
) -> bool:
    deadline = time.monotonic() + timeout_s
    absent_since: float | None = None
    current_frame = frame
    while time.monotonic() < deadline:
        checkpoint()
        try:
            styles = _read_confirm_styles(current_frame)
            loading = current_frame.locator(
                ".loading, .clsLoading, [class*='loading' i], "
                "[id*='progress' i]"
            )
            visible_loading = any(
                loading.nth(index).is_visible()
                for index in range(min(loading.count(), 20))
            )
            still_present = any(style["key"] == style_key for style in styles)
            if not visible_loading and not still_present:
                if absent_since is None:
                    absent_since = time.monotonic()
                elif time.monotonic() - absent_since >= 1:
                    return True
            else:
                absent_since = None
        except PlaywrightError:
            absent_since = None
            try:
                current_frame = _confirm_frame(page, timeout_s=2)
            except PlaywrightTimeoutError:
                pass
        _wait(page, 200)
    return False


def _wait_confirm_grid_ready(
    page: Page,
    frame: Frame,
    *,
    timeout_s: float = 30,
) -> Frame:
    """Đợi grid hết lớp chặn sau postback đổi page size của WFX."""
    deadline = time.monotonic() + timeout_s
    empty_since: float | None = None
    current_frame = frame
    controls_selector = (
        f"{CONFIRM_GRID_SELECTOR} #colSelector input[type='radio'], "
        f"{CONFIRM_GRID_SELECTOR} #colSelector input[type='checkbox']"
    )
    while time.monotonic() < deadline:
        checkpoint()
        try:
            loading = current_frame.locator(
                "#gridEDIBuyerPO_divGridLoading, .loading, .clsLoading, "
                "[class*='loading' i], [id*='progress' i]"
            )
            visible_loading = any(
                loading.nth(index).is_visible()
                for index in range(min(loading.count(), 20))
            )
            controls = current_frame.locator(controls_selector)
            if not visible_loading and controls.count():
                try:
                    controls.first.check(timeout=500, trial=True)
                except PlaywrightError:
                    empty_since = None
                else:
                    return current_frame
            elif not visible_loading and current_frame.locator(
                CONFIRM_GRID_SELECTOR
            ).count():
                if empty_since is None:
                    empty_since = time.monotonic()
                elif time.monotonic() - empty_since >= 1:
                    return current_frame
            else:
                empty_since = None
        except PlaywrightError:
            empty_since = None
            try:
                current_frame = _confirm_frame(page, timeout_s=2)
            except PlaywrightTimeoutError:
                pass
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        "Grid EDI Buyer PO vẫn đang tải sau khi đổi số dòng hiển thị."
    )


def _set_confirm_page_size(page: Page) -> Frame:
    frame, select = _visible_in_frames(
        page,
        CONFIRM_PAGE_SIZE_SELECTOR,
        timeout_s=25,
    )
    try:
        current = str(select.input_value(timeout=1_000) or "").strip()
    except PlaywrightError:
        current = ""
    if current != "100":
        try:
            select.select_option(label="100", timeout=5_000)
        except PlaywrightError:
            select.select_option(value="100", timeout=5_000)
        _wait(page, 500)
        frame, select = _visible_in_frames(
            page,
            CONFIRM_PAGE_SIZE_SELECTOR,
            timeout_s=25,
        )
    selected = str(select.input_value(timeout=1_000) or "").strip()
    if selected != "100":
        option = select.locator("option:checked")
        label = " ".join((option.first.inner_text() or "").split()) if option.count() else ""
        if label != "100":
            raise PlaywrightTimeoutError("Không đổi được số dòng hiển thị thành 100.")
    return _wait_confirm_grid_ready(page, frame)


def _open_confirm_grid(
    page: Page,
    mode: str,
    log: Callable[[str], None],
) -> Frame:
    tab_selector = CONFIRM_TAB_SELECTORS[mode]
    try:
        _frame, tab = _visible_in_frames(page, tab_selector, timeout_s=2)
    except PlaywrightTimeoutError:
        try:
            _menu_frame, menu = _visible_in_frames(page, EDI_MENU_SELECTOR, timeout_s=12)
        except PlaywrightTimeoutError:
            _menu_frame, menu = _attached_in_frames(page, EDI_MENU_SELECTOR, timeout_s=12)
        _click(menu)
        _frame, tab = _visible_in_frames(page, tab_selector, timeout_s=30)
    _click(tab)
    label = "Revision" if mode == "revision" else "New"
    _write_log(log, f"[OC CONFIRM] Đã mở tab {label}")
    frame = _set_confirm_page_size(page)
    _write_log(log, "[OC CONFIRM] Đã đổi số dòng hiển thị thành 100")
    return frame


def _confirm_all_pending(
    page: Page,
    frame: Frame,
    mode: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    confirmed_styles = 0
    selected_sales_orders = 0
    while True:
        checkpoint()
        styles = _read_confirm_styles(frame)
        if not styles:
            return _result(
                True,
                "OC_FAST_CONFIRM_COMPLETED",
                (
                    f"Đã Confirm xong {confirmed_styles} Style."
                    if confirmed_styles
                    else "Không còn Style chờ Confirm."
                ),
                mode=mode,
                confirmed_styles=confirmed_styles,
                selected_sales_orders=selected_sales_orders,
                confirmation_submitted=confirmed_styles > 0,
            )
        style = styles[0]
        style_key = str(style["key"])
        style_label = str(style.get("label") or style_key)
        _write_log(
            log,
            f"[OC CONFIRM] Đang xử lý Style {style_label} "
            f"({confirmed_styles + 1})",
        )
        _focus_confirm_grid(page, frame)
        if mode == "revision":
            prepared = _prepare_revision_style(frame, style_key)
            if not prepared.get("ok"):
                if prepared.get("reason") == "multiple-sales-orders":
                    options = list(prepared.get("options") or ())
                    return _result(
                        False,
                        "OC_FAST_CONFIRM_MULTIPLE_SALES_ORDERS",
                        f"Style {style_label} có nhiều WFX Sales Order. "
                        "Hãy chọn thủ công rồi chạy lại Confirm nhanh.",
                        mode=mode,
                        confirmed_styles=confirmed_styles,
                        selected_sales_orders=selected_sales_orders,
                        stopped_style=style_label,
                        stopped_row=prepared.get("row_number"),
                        sales_order_options=options,
                        confirmation_submitted=confirmed_styles > 0,
                    )
                raise PlaywrightTimeoutError(
                    "Style đã thay đổi khi chuẩn bị WFX Sales Order."
                )
            selected_sales_orders += int(prepared.get("selected_count") or 0)

        confirmation_submitted = False
        try:
            with cancellation_deferred():
                processed = False
                for attempt in range(2):
                    _select_confirm_style(frame, style_key)
                    confirmation_submitted = True
                    _click_confirm_toolbar(page)
                    _write_log(
                        log,
                        f"[OC CONFIRM] Đã bấm Confirm lượt {attempt + 1} "
                        f"cho {style_label}",
                    )
                    processed = _wait_style_processed(
                        page,
                        frame,
                        style_key,
                        timeout_s=(
                            CONFIRM_FIRST_PASS_TIMEOUT_SECONDS
                            if attempt == 0
                            else CONFIRM_PROCESS_TIMEOUT_SECONDS
                        ),
                    )
                    if processed:
                        break
                if not processed:
                    return _result(
                        False,
                        "OC_FAST_CONFIRM_PROCESS_TIMEOUT",
                        f"Style {style_label} chưa process xong sau khi Confirm. "
                        "App đã dừng trước Style tiếp theo.",
                        mode=mode,
                        confirmed_styles=confirmed_styles,
                        selected_sales_orders=selected_sales_orders,
                        stopped_style=style_label,
                        confirmation_submitted=True,
                    )
        except Exception as error:
            if confirmation_submitted:
                return _result(
                    False,
                    "OC_FAST_CONFIRM_UNCONFIRMED",
                    f"Đã bấm Confirm cho Style {style_label} nhưng không đọc được "
                    "kết quả. App không tự chạy lại để tránh Confirm nhầm Style.",
                    mode=mode,
                    confirmed_styles=confirmed_styles,
                    selected_sales_orders=selected_sales_orders,
                    stopped_style=style_label,
                    confirmation_submitted=True,
                    errors=[f"{type(error).__name__}: {_first_line(error)}"],
                )
            raise
        confirmed_styles += 1
        _write_log(log, f"[OC CONFIRM] Style {style_label} đã process xong")


def _reject_all_pending(
    page: Page,
    frame: Frame,
    mode: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    rejected_rows = 0
    while True:
        checkpoint()
        pending = _read_confirm_styles(frame)
        if not pending:
            return _result(
                True,
                "OC_REJECT_ALL_COMPLETED",
                (
                    f"Đã Reject xong {rejected_rows} PO."
                    if rejected_rows
                    else "Không còn PO chờ Reject trong tab đang mở."
                ),
                mode=mode,
                rejected_rows=rejected_rows,
                rejection_submitted=rejected_rows > 0,
            )
        row = pending[0]
        row_key = str(row["key"])
        row_label = str(row.get("label") or row_key)
        _write_log(
            log,
            f"[OC REJECT] Đang Reject {row_label} ({rejected_rows + 1})",
        )
        rejection_submitted = False
        try:
            with cancellation_deferred():
                _focus_confirm_grid(page, frame)
                _select_confirm_style(frame, row_key)
                rejection_submitted = True
                _click_reject_toolbar(page)
                _write_log(log, f"[OC REJECT] Đã bấm Reject cho {row_label}")
                processed = _wait_style_processed(
                    page,
                    frame,
                    row_key,
                    timeout_s=CONFIRM_PROCESS_TIMEOUT_SECONDS,
                )
                if not processed:
                    return _result(
                        False,
                        "OC_REJECT_ALL_PROCESS_TIMEOUT",
                        f"PO {row_label} chưa rời khỏi tab sau khi Reject. "
                        "App đã dừng trước PO tiếp theo.",
                        mode=mode,
                        rejected_rows=rejected_rows,
                        stopped_row=row_label,
                        rejection_submitted=True,
                    )
        except Exception as error:
            if rejection_submitted:
                return _result(
                    False,
                    "OC_REJECT_ALL_UNCONFIRMED",
                    f"Đã bấm Reject cho {row_label} nhưng chưa đọc được kết quả. "
                    "App không tự chạy lại để tránh Reject nhầm PO.",
                    mode=mode,
                    rejected_rows=rejected_rows,
                    stopped_row=row_label,
                    rejection_submitted=True,
                    errors=[f"{type(error).__name__}: {_first_line(error)}"],
                )
            raise
        rejected_rows += 1
        _write_log(log, f"[OC REJECT] {row_label} đã được xử lý xong")


def reject_all_oc_pending(
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Reject tuần tự toàn bộ PO trong tab New/Revision đang được chọn."""
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        mode = _active_confirm_mode(page)
        frame = _set_confirm_page_size(page)
        label = "Revision" if mode == "revision" else "New"
        _write_log(log, f"[OC REJECT] Đang xử lý tab {label}; page size 100")
        return _reject_all_pending(page, frame, mode, log)
    except RuntimeError as error:
        code = str(error)
        if code in {"CHROME_CLOSED", "NOT_LOGGED_IN"}:
            message = (
                "Trình duyệt làm việc chưa được mở."
                if code == "CHROME_CLOSED"
                else "Phiên WFX chưa đăng nhập hoặc đã hết hạn."
            )
            return _result(False, code, message)
        raise
    except PlaywrightTimeoutError as error:
        return _result(
            False,
            "OC_REJECT_ALL_NOT_READY",
            f"Màn Reject OC chưa sẵn sàng: {_first_line(error)}",
            rejection_submitted=False,
        )
    except Exception as error:
        return _result(
            False,
            "OC_REJECT_ALL_FAILED",
            f"{type(error).__name__}: {_first_line(error)}",
            rejection_submitted=False,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def confirm_oc_pending(
    mode: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Confirm tuần tự toàn bộ Style đang chờ trên tab New hoặc Revision."""
    selected_mode = str(mode or "").strip().casefold()
    selected_mode = "revision" if selected_mode in {"revision", "revise"} else selected_mode
    if selected_mode not in CONFIRM_TAB_SELECTORS:
        return _result(
            False,
            "OC_MODE_INVALID",
            "Chế độ Confirm OC phải là New hoặc Revision.",
        )
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_confirm_grid(page, selected_mode, log)
        return _confirm_all_pending(page, frame, selected_mode, log)
    except RuntimeError as error:
        code = str(error)
        if code in {"CHROME_CLOSED", "NOT_LOGGED_IN"}:
            message = (
                "Trình duyệt làm việc chưa được mở."
                if code == "CHROME_CLOSED"
                else "Phiên WFX chưa đăng nhập hoặc đã hết hạn."
            )
            return _result(False, code, message)
        raise
    except PlaywrightTimeoutError as error:
        return _result(
            False,
            "OC_FAST_CONFIRM_NOT_READY",
            f"Màn Confirm OC chưa sẵn sàng: {_first_line(error)}",
            mode=selected_mode,
            confirmation_submitted=False,
        )
    except Exception as error:
        return _result(
            False,
            "OC_FAST_CONFIRM_FAILED",
            f"{type(error).__name__}: {_first_line(error)}",
            mode=selected_mode,
            confirmation_submitted=False,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def upload_oc_edi(
    upload_path: str | Path,
    buyer: str,
    mode: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Upload one validated value-only workbook and create its transaction."""
    path = Path(upload_path).expanduser().resolve()
    playwright: Playwright | None = None
    transaction_submitted = False
    try:
        if not path.is_file() or path.suffix.casefold() != ".xlsx":
            return _result(
                False,
                "OC_UPLOAD_FILE_MISSING",
                "File EDI đã chuẩn hóa không còn tồn tại.",
            )
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        _open_edi_form(page, buyer, log)
        _process_package(page, path, log)
        try:
            _frame, resolution = _toolbar_link(page, "Error Resolution", timeout_s=8)
            _click(resolution)
        except PlaywrightTimeoutError:
            _write_log(log, "[OC EDI] Bảng trạng thái đã hiển thị trực tiếp")
        rows = _wait_statuses(page, log)
        failed = [
            row
            for row in rows
            if any(
                _status_kind(row.get(field, "")) == "failed"
                for field in ("imported", "validated", "mapped")
            )
        ]
        if failed:
            stage, resolution_rows, errors = _open_status_error_details(
                page, rows, log
            )
            return _result(
                False,
                "OC_EDI_VALIDATION_FAILED",
                f"WFX báo lỗi tại {stage or 'Error Resolution'}. "
                "App đã dừng trước Create Transaction; hãy sửa file rồi upload lại.",
                transaction_submitted=False,
                status_rows=rows,
                error_stage=stage,
                resolution_rows=resolution_rows,
                errors=errors,
            )
        _click_pending_transaction(page)
        _select_first_transaction(page)
        # Đặt cờ trước click: nếu browser rơi đúng lúc dispatch, không thể biết
        # WFX đã nhận hay chưa nên phải chặn mọi retry tự động.
        transaction_submitted = True
        confirmed, confirmations = _create_transaction(page, log)
        if not confirmed:
            return _result(
                False,
                "OC_TRANSACTION_UNCONFIRMED",
                "Đã bấm Create Transaction nhưng chưa đọc được xác nhận từ WFX. "
                "Không tự chạy lại để tránh tạo trùng; hãy kiểm tra tab New/Revision.",
                transaction_submitted=True,
                confirmations=confirmations,
                status_rows=rows,
            )
        destination = "Revision" if str(mode).casefold() == "revise" else "New"
        return _result(
            True,
            "OC_TRANSACTION_CREATED",
            f"Upload OC thành công; transaction đã được tạo vào tab {destination}.",
            buyer=buyer,
            mode=mode,
            destination_tab=destination,
            transaction_submitted=True,
            confirmations=confirmations,
            status_rows=rows,
        )
    except RuntimeError as error:
        code = str(error)
        if code in {"CHROME_CLOSED", "NOT_LOGGED_IN"}:
            message = (
                "Trình duyệt làm việc chưa được mở."
                if code == "CHROME_CLOSED"
                else "Phiên WFX chưa đăng nhập hoặc đã hết hạn."
            )
            return _result(False, code, message)
        raise
    except PlaywrightTimeoutError as error:
        if transaction_submitted:
            return _result(
                False,
                "OC_TRANSACTION_UNCONFIRMED",
                "Đã bắt đầu Create Transaction nhưng mất xác nhận từ WFX. "
                "Không tự chạy lại để tránh tạo trùng; hãy kiểm tra tab New/Revision.",
                transaction_submitted=True,
                errors=[_first_line(error)],
            )
        return _result(
            False,
            "OC_EDI_NOT_READY",
            f"WFX EDI chưa sẵn sàng: {_first_line(error)}",
            transaction_submitted=transaction_submitted,
        )
    except Exception as error:
        if transaction_submitted:
            return _result(
                False,
                "OC_TRANSACTION_UNCONFIRMED",
                "Đã bắt đầu Create Transaction nhưng không đọc được kết quả từ WFX. "
                "Không tự chạy lại để tránh tạo trùng; hãy kiểm tra tab New/Revision.",
                transaction_submitted=True,
                errors=[f"{type(error).__name__}: {_first_line(error)}"],
            )
        return _result(
            False,
            "OC_EDI_FAILED",
            f"{type(error).__name__}: {_first_line(error)}",
            transaction_submitted=transaction_submitted,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def open_oc_revision_report(
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở đúng report Upload OC from OC_Sale; chưa tự chọn tham số/export."""
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        menu = page.locator(f"xpath={REVISION_REPORT_MENU_XPATH}")
        if not menu.count():
            _menu_frame, menu = _attached_in_frames(
                page,
                "#0004_0110 > a",
                timeout_s=10,
            )
        _write_log(log, "[REVISE OC] Mở Reporting & Analytic")
        _click(menu)
        _tree_frame, tree = _visible_in_frames(
            page,
            "#treeReportCenter",
            timeout_s=30,
        )
        report = tree.locator(REVISION_REPORT_SELECTOR)
        target = None
        for index in range(report.count()):
            candidate = report.nth(index)
            text = " ".join((candidate.inner_text() or "").split())
            node_id = candidate.get_attribute("nodeid") or candidate.locator(
                "xpath=ancestor-or-self::*[@nodeid][1]"
            ).get_attribute("nodeid")
            if node_id == "258" or text.casefold() == "upload oc from oc_sale":
                target = candidate
                break
        if target is None:
            raise PlaywrightTimeoutError(
                "Không tìm thấy report Upload OC from OC_Sale (node 258)."
            )
        _click(target)
        _write_log(log, "[REVISE OC] Đã mở report Upload OC from OC_Sale")
        return _result(
            True,
            "OC_REVISION_REPORT_READY",
            "Đã mở Upload OC from OC_Sale. Chọn điều kiện và xuất Excel trên WFX.",
            report_node_id="258",
        )
    except RuntimeError as error:
        code = str(error)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên WFX chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message)
    except PlaywrightTimeoutError as error:
        return _result(
            False,
            "OC_REVISION_REPORT_NOT_READY",
            f"Không mở được report Revise OC: {_first_line(error)}",
        )
    except Exception as error:
        return _result(
            False,
            "OC_REVISION_REPORT_FAILED",
            f"{type(error).__name__}: {_first_line(error)}",
        )
    finally:
        if playwright is not None:
            playwright.stop()
