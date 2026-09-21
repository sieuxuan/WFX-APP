"""EDI Production Order: upload package, Process Package, Create Transaction.

``Create Transaction`` là ranh giới không idempotent: click rồi mà mất xác nhận
phải trả ``GDN_TRANSACTION_UNCONFIRMED`` và hướng dẫn kiểm tra WFX, tuyệt đối
không tự thử lại để tránh tạo trùng."""

from __future__ import annotations

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
from wfx_panel.automation.dispatch.constants import (
    _EDI_ROWS_JS,
    EDI_CREATE_SELECTOR,
    EDI_GRID_SELECTOR,
    EDI_MENU_XPATH,
    EDI_UPLOAD_SELECTOR,
    PACKAGE_LABEL,
    PACKAGE_TIMEOUT_SECONDS,
    PACKAGE_TYPE_SELECTOR,
    PACKAGE_TYPE_VALUE,
    PACKAGE_VALUE,
    TRANSACTION_TIMEOUT_SECONDS,
)
from wfx_panel.automation.dispatch.status import (
    DispatchFlowError,
    _status_complete,
    _status_failed,
    choose_latest_pending_row,
)
from wfx_panel.automation.oc import (
    _attached_in_frames,
    _select_exact_option,
    _toolbar_link,
)
from wfx_panel.automation.runtime import cancellation_deferred, checkpoint


def _edi_frame(page: Page, timeout_s: float = 30) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        checkpoint()
        for frame in page.frames:
            try:
                if (
                    frame.locator(PACKAGE_TYPE_SELECTOR).count()
                    and frame.locator("#ddlPackage").count()
                ):
                    return frame
            except PlaywrightError:
                continue
        _wait(page, 150)
    raise DispatchFlowError(
        "GDN_EDI_NOT_READY",
        "Màn EDI Production Order chưa sẵn sàng.",
    )


def _open_edi(page: Page, log: Callable[[str], None]) -> Frame:
    try:
        _edi_frame(page, timeout_s=1)
    except DispatchFlowError:
        menu = page.locator(f"xpath={EDI_MENU_XPATH}")
        menu.wait_for(state="attached", timeout=10_000)
        _write_log(log, "[GDN] Mở EDI Production Order.")
        _click(menu)
        _edi_frame(page)
    _select_exact_option(
        page,
        PACKAGE_TYPE_SELECTOR,
        PACKAGE_TYPE_VALUE,
        PACKAGE_TYPE_VALUE,
        "PackageType",
    )
    _select_exact_option(
        page,
        "#ddlPackage",
        PACKAGE_VALUE,
        PACKAGE_LABEL,
        "Package",
    )
    _write_log(log, f"[GDN] Đã chọn Package: {PACKAGE_LABEL}.")
    return _edi_frame(page, timeout_s=5)


def _edi_rows(frame: Frame) -> list[dict[str, str]]:
    try:
        value = frame.evaluate(_EDI_ROWS_JS)
    except PlaywrightError:
        return []
    if not isinstance(value, list):
        return []
    return [
        {str(key): str(item_value or "") for key, item_value in row.items()}
        for row in value
        if isinstance(row, dict)
    ]


def _visible_message(frame: Frame) -> str:
    try:
        messages = frame.locator(
            "#sectionObjectAttachment #lblSuccessMsg, "
            "#lblSuccessMsg, [role='alert'], "
            ".clsErrorMessage, .clsSuccessMessage"
        )
        for index in range(messages.count()):
            candidate = messages.nth(index)
            if not candidate.is_visible():
                continue
            text = " ".join((candidate.text_content() or "").split())
            if text:
                return text[:1000]
    except PlaywrightError:
        pass
    return ""


def _open_import_popup(page: Page) -> tuple[Frame, Any]:
    try:
        return _attached_in_frames(page, EDI_UPLOAD_SELECTOR, timeout_s=1)
    except PlaywrightTimeoutError:
        _frame, import_link = _toolbar_link(page, "Import", timeout_s=20)
        _click(import_link)
        return _attached_in_frames(page, EDI_UPLOAD_SELECTOR, timeout_s=20)


def _process_package(
    page: Page,
    frame: Frame,
    upload_path: Path,
    known_ids: set[str],
    log: Callable[[str], None],
) -> dict[str, str]:
    _upload_frame, file_input = _open_import_popup(page)
    file_input.set_input_files(str(upload_path))
    _write_log(log, "[GDN] Đã gắn file XLSX vào Import Excel.")
    _process_frame, process_link = _toolbar_link(
        page,
        "Process Package",
        timeout_s=15,
    )
    dialog_messages: list[str] = []

    def accept_dialog(dialog: Any) -> None:
        dialog_messages.append(" ".join(str(dialog.message or "").split()))
        dialog.accept()

    page.on("dialog", accept_dialog)
    try:
        with cancellation_deferred():
            _click(process_link)
            _write_log(log, "[GDN] Đã gửi Process Package; đang chờ dòng mới.")
            deadline = time.monotonic() + PACKAGE_TIMEOUT_SECONDS
            last_new_rows: list[dict[str, str]] = []
            while time.monotonic() < deadline:
                checkpoint()
                failed_dialog = next(
                    (
                        message
                        for message in dialog_messages
                        if _status_failed(message)
                    ),
                    "",
                )
                if failed_dialog:
                    raise DispatchFlowError(
                        "GDN_PACKAGE_PROCESS_FAILED",
                        "WFX từ chối Process Package.",
                        errors=[failed_dialog],
                    )
                message = _visible_message(frame)
                if message and _status_failed(message):
                    raise DispatchFlowError(
                        "GDN_PACKAGE_PROCESS_FAILED",
                        "WFX báo lỗi khi Process Package.",
                        errors=[message],
                    )
                rows = _edi_rows(frame)
                last_new_rows = [
                    row
                    for row in rows
                    if row.get("row_id") not in known_ids
                    and row.get("package_name", "").casefold()
                    == PACKAGE_LABEL.casefold()
                ]
                for row in last_new_rows:
                    if _status_failed(
                        row.get("status"),
                        row.get("transaction_detail"),
                        row.get("error"),
                    ):
                        raise DispatchFlowError(
                            "GDN_PACKAGE_PROCESS_FAILED",
                            "Package mới bị WFX báo lỗi.",
                            errors=[row.get("error") or row.get("status") or "Failed"],
                        )
                selected = choose_latest_pending_row(
                    rows,
                    excluded_ids=known_ids,
                )
                if selected is not None:
                    _write_log(
                        log,
                        "[GDN] Package mới đã Pending; chọn theo Processed ON.",
                    )
                    return selected
                _wait(page, 250)
        detail = last_new_rows[0] if last_new_rows else {}
        raise DispatchFlowError(
            "GDN_PENDING_NOT_FOUND",
            "Không tìm thấy Transaction Detail Pending của package mới.",
            errors=[
                str(detail.get("error") or detail.get("transaction_detail") or "")
            ],
        )
    finally:
        try:
            page.remove_listener("dialog", accept_dialog)
        except Exception:
            pass


def _select_transaction(frame: Frame, row: dict[str, str]) -> None:
    row_id = str(row.get("row_id") or "")
    if not row_id:
        raise DispatchFlowError(
            "GDN_PENDING_NOT_FOUND",
            "Dòng package Pending không có mã nhận diện.",
        )
    target = frame.locator(
        f'{EDI_GRID_SELECTOR} tr[rowid="{row_id}"] input[name="rdSelector"]'
    )
    if target.count() != 1 or not target.first.is_visible():
        raise DispatchFlowError(
            "GDN_PENDING_NOT_FOUND",
            "Dòng package Pending đã thay đổi trước khi chọn.",
        )
    if not target.first.is_checked():
        target.first.check(timeout=5_000)
    if not target.first.is_checked():
        raise DispatchFlowError(
            "GDN_PENDING_NOT_FOUND",
            "WFX chưa xác nhận chọn package Pending.",
        )


def _create_transaction_link(frame: Frame) -> Any:
    links = frame.locator(EDI_CREATE_SELECTOR)
    matches: list[Any] = []
    for index in range(links.count()):
        link = links.nth(index)
        try:
            if (
                link.is_visible()
                and link.is_enabled()
                and " ".join((link.inner_text() or "").casefold().split())
                == "create transaction"
            ):
                matches.append(link)
        except PlaywrightError:
            continue
    if len(matches) != 1:
        raise DispatchFlowError(
            "GDN_EDI_NOT_READY",
            "Nút Create Transaction chưa sẵn sàng.",
        )
    return matches[0]


def _wait_transaction_result(
    page: Page,
    frame: Frame,
    row_id: str,
    dialog_messages: list[str],
) -> tuple[bool, list[str]]:
    deadline = time.monotonic() + TRANSACTION_TIMEOUT_SECONDS
    seen_row = True
    missing_polls = 0
    last_detail = "Pending"
    while time.monotonic() < deadline:
        checkpoint()
        failed_dialogs = [
            message for message in dialog_messages if _status_failed(message)
        ]
        if failed_dialogs:
            return False, failed_dialogs
        completed_dialogs = [
            message for message in dialog_messages if _status_complete(message)
        ]
        if completed_dialogs:
            return True, completed_dialogs
        message = _visible_message(frame)
        if message and _status_failed(message):
            return False, [message]
        if (
            message
            and "upload" not in message.casefold()
            and _status_complete(message)
        ):
            return True, [message]

        rows = _edi_rows(frame)
        current = next(
            (row for row in rows if row.get("row_id") == row_id),
            None,
        )
        if current is None:
            try:
                grid_ready = frame.locator(EDI_GRID_SELECTOR).count() > 0
            except PlaywrightError:
                grid_ready = False
            missing_polls = missing_polls + 1 if grid_ready else 0
            # WFX refreshes the grid while Create Transaction is running.
            # Require several stable reads before treating a removed row as done.
            if seen_row and missing_polls >= 3:
                return True, ["Package đã rời danh sách chờ xử lý."]
        else:
            seen_row = True
            missing_polls = 0
            last_detail = str(current.get("transaction_detail") or "")
            if _status_failed(
                current.get("status"),
                last_detail,
                current.get("error"),
            ):
                return False, [
                    str(
                        current.get("error")
                        or last_detail
                        or current.get("status")
                        or "Failed"
                    )
                ]
            if _status_complete(last_detail):
                return True, [last_detail]
        _wait(page, 300)
    return False, [
        f"WFX chưa xác nhận hoàn tất; Transaction Detail hiện là {last_detail or '—'}."
    ]
