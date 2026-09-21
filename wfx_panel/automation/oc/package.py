"""Upload package và đọc trạng thái Imported/Validated/Mapping.

Chỉ đọc package MỚI NHẤT trong Error Resolution. Bất kỳ ``InProgress`` hay Fail
nào cũng là lỗi ngay, không chờ hết timeout."""

from __future__ import annotations

import re
from pathlib import Path

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.oc.constants import (
    _FAILED_RECORD_JS,
    _STATUS_JS,
    EDI_MENU_SELECTOR,
    PACKAGE_LABEL,
    PACKAGE_VALUE,
    STATUS_TIMEOUT_SECONDS,
)
from wfx_panel.automation.oc.dom import (
    _attached_in_frames,
    _select_exact_option,
    _toolbar_link,
    _visible_in_frames,
)
from wfx_panel.automation.runtime import cancellation_deferred, checkpoint


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
