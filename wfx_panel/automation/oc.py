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


def _select_first_transaction(page: Page) -> None:
    _frame, create_link = _toolbar_link(page, "Create Transaction", timeout_s=30)
    create_row = create_link.locator("xpath=ancestor::table[1]")
    for frame in page.frames:
        try:
            checkboxes = frame.locator("input[type='checkbox']")
            candidates: list[Any] = []
            for index in range(checkboxes.count()):
                checkbox = checkboxes.nth(index)
                if checkbox.is_visible() and checkbox.is_enabled():
                    candidates.append(checkbox)
            for checkbox in candidates:
                try:
                    row_text = " ".join(
                        (checkbox.locator("xpath=ancestor::tr[1]").inner_text() or "").split()
                    )
                except PlaywrightError:
                    row_text = ""
                if row_text and not re.search(r"select\s+all", row_text, re.I):
                    if not checkbox.is_checked():
                        checkbox.check()
                    return
            if len(candidates) == 1:
                candidates[0].check()
                return
        except PlaywrightError:
            continue
    if create_row.count():
        raise PlaywrightTimeoutError("Không tìm thấy checkbox đơn hàng để tạo transaction.")
    raise PlaywrightTimeoutError("Không tìm thấy dòng Transaction Detail.")


def _create_transaction(page: Page, log: Callable[[str], None]) -> tuple[bool, list[str]]:
    _frame, create_link = _toolbar_link(page, "Create Transaction", timeout_s=10)
    dialog_messages: list[str] = []

    def accept_create_dialog(dialog: Any) -> None:
        dialog_messages.append(" ".join(str(dialog.message or "").split()))
        dialog.accept()

    page.on("dialog", accept_create_dialog)
    try:
        with cancellation_deferred():
            _click(create_link)
            _write_log(log, "[OC EDI] Đã gửi Create Transaction")
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                # Không cho Stop ngắt đoạn xác nhận sau thao tác không idempotent.
                # Nếu mất kết nối, caller phải coi transaction là unconfirmed.
                checkpoint()
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
                            if text and re.search(r"success|created|complete", text, re.I):
                                return True, dialog_messages + [text]
                    except PlaywrightError:
                        continue
                _wait(page, 300)
        return False, dialog_messages
    finally:
        try:
            page.remove_listener("dialog", accept_create_dialog)
        except Exception:
            pass


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
