"""Điểm vào: chạy (GDN) Dispatch và mở màn EDI ở chế độ chỉ đọc."""

from __future__ import annotations

import tempfile
from pathlib import Path

from wfx_panel.automation._common import (
    Any,
    Callable,
    Playwright,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _click,
    _first_line,
    _result,
    _write_log,
    sync_playwright,
)
from wfx_panel.automation.dispatch.constants import PACKAGE_LABEL, _emit_progress
from wfx_panel.automation.dispatch.edi import (
    _create_transaction_link,
    _edi_rows,
    _open_edi,
    _process_package,
    _select_transaction,
    _wait_transaction_result,
)
from wfx_panel.automation.dispatch.report import _prepare_dispatch_workbook
from wfx_panel.automation.dispatch.status import (
    DispatchFlowError,
    _processed_sort_key,
    _status_failed,
)
from wfx_panel.automation.modules import _active_wfx_page
from wfx_panel.automation.runtime import cancellation_deferred


def run_gdn_dispatch(
    invoice: str,
    log: Callable[[str], None] = print,
    progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Chạy trọn flow report -> XLSX -> EDI -> Create Transaction."""
    invoice = " ".join(str(invoice or "").split())
    if not invoice:
        return _result(
            False,
            "GDN_INVOICE_REQUIRED",
            "Hãy nhập Invoice GRN trước khi Submit.",
        )
    if len(invoice) > 100 or any(ord(character) < 32 for character in invoice):
        return _result(
            False,
            "GDN_INVOICE_INVALID",
            "Invoice GRN không hợp lệ.",
        )

    playwright: Playwright | None = None
    transaction_submitted = False
    active_stage = "report"
    active_step = 1

    def stage(
        name: str,
        message: str,
        step: int,
        _total: int | None = None,
        *,
        state: str = "active",
    ) -> None:
        nonlocal active_stage, active_step
        active_stage, active_step = name, step
        _emit_progress(progress, name, message, step, state=state)

    def failure_context(code: str) -> dict[str, Any]:
        inspect_edi = transaction_submitted or active_step >= 5 or code in {
            "GDN_PACKAGE_PROCESS_FAILED",
            "GDN_PENDING_NOT_FOUND",
            "GDN_TRANSACTION_FAILED",
            "GDN_TRANSACTION_UNCONFIRMED",
        }
        return {
            "failed_stage": active_stage,
            "failed_step": active_step,
            "checkpoint": "inspect_edi" if inspect_edi else "restart_safe",
            "safe_to_retry": not inspect_edi,
        }

    try:
        stage("report", "Đang mở báo cáo Buyer Dispatch…", 1)
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        context = browser.contexts[0]
        with tempfile.TemporaryDirectory(prefix="wfx-gdn-dispatch-") as temporary:
            upload_path = _prepare_dispatch_workbook(
                context,
                invoice,
                Path(temporary),
                log,
                stage,
            )
            stage("edi", "Đang mở EDI Production Order…", 4)
            frame = _open_edi(page, log)
            known_ids = {
                str(row.get("row_id") or "") for row in _edi_rows(frame)
            }
            stage("package", "Đang upload và Process Package…", 5)
            pending = _process_package(
                page,
                frame,
                upload_path,
                known_ids,
                log,
            )
            stage("transaction", "Đang tạo transaction và chờ WFX xác nhận…", 6)
            _select_transaction(frame, pending)
            create_link = _create_transaction_link(frame)
            dialog_messages: list[str] = []

            def accept_dialog(dialog: Any) -> None:
                dialog_messages.append(
                    " ".join(str(dialog.message or "").split())
                )
                dialog.accept()

            page.on("dialog", accept_dialog)
            try:
                transaction_submitted = True
                with cancellation_deferred():
                    _click(create_link)
                    _write_log(
                        log,
                        "[GDN] Đã gửi Create Transaction; đang chờ WFX hoàn tất.",
                    )
                    confirmed, confirmations = _wait_transaction_result(
                        page,
                        frame,
                        str(pending.get("row_id") or ""),
                        dialog_messages,
                    )
            finally:
                try:
                    page.remove_listener("dialog", accept_dialog)
                except Exception:
                    pass
            if not confirmed:
                failed = any(_status_failed(value) for value in confirmations)
                code = (
                    "GDN_TRANSACTION_FAILED"
                    if failed
                    else "GDN_TRANSACTION_UNCONFIRMED"
                )
                stage(
                    "transaction",
                    (
                        "WFX báo lỗi khi tạo transaction."
                        if failed
                        else "Transaction đã gửi nhưng chưa được WFX xác nhận."
                    ),
                    6,
                    state="failed" if failed else "pending",
                )
                return _result(
                    False,
                    code,
                    (
                        "WFX báo lỗi khi tạo GDN Dispatch."
                        if failed
                        else "Đã gửi Create Transaction nhưng WFX chưa xác nhận hoàn tất. "
                        "Không tự chạy lại để tránh tạo trùng."
                    ),
                    transaction_submitted=True,
                    errors=confirmations,
                    **failure_context(code),
                )
            stage(
                "transaction",
                "WFX đã xác nhận (GDN) Dispatch hoàn tất.",
                6,
                state="completed",
            )
            return _result(
                True,
                "GDN_DISPATCH_COMPLETED",
                "(GDN) Dispatch đã được WFX xử lý thành công.",
                transaction_submitted=True,
                confirmations=confirmations,
                failed_stage="",
                checkpoint="completed",
                safe_to_retry=False,
            )
    except RuntimeError as error:
        code = str(error)
        if code in {"CHROME_CLOSED", "NOT_LOGGED_IN"}:
            result = _result(
                False,
                code,
                (
                    "Trình duyệt làm việc chưa được mở."
                    if code == "CHROME_CLOSED"
                    else "Phiên WFX chưa đăng nhập hoặc đã hết hạn."
                ),
                transaction_submitted=transaction_submitted,
            )
            stage(
                active_stage,
                str(result.get("message") or "Không thể tiếp tục GDN."),
                active_step,
                state="failed",
            )
            return {**result, **failure_context(code)}
        if isinstance(error, DispatchFlowError):
            stage(
                active_stage,
                error.message,
                active_step,
                state=(
                    "pending"
                    if error.code == "GDN_PENDING_NOT_FOUND"
                    else "failed"
                ),
            )
            return _result(
                False,
                error.code,
                error.message,
                errors=error.errors,
                transaction_submitted=transaction_submitted,
                **failure_context(error.code),
            )
        raise
    except PlaywrightTimeoutError as error:
        code = (
            "GDN_TRANSACTION_UNCONFIRMED"
            if transaction_submitted
            else "GDN_EDI_NOT_READY"
        )
        stage(
            active_stage,
            "WFX chưa phản hồi trong thời gian chờ.",
            active_step,
            state="pending" if transaction_submitted else "failed",
        )
        return _result(
            False,
            code,
            (
                "Đã gửi Create Transaction nhưng mất xác nhận từ WFX. "
                "Không tự chạy lại để tránh tạo trùng."
                if transaction_submitted
                else "EDI Production Order chưa sẵn sàng."
            ),
            errors=[_first_line(error)],
            transaction_submitted=transaction_submitted,
            **failure_context(code),
        )
    except Exception as error:
        code = (
            "GDN_TRANSACTION_UNCONFIRMED"
            if transaction_submitted
            else "GDN_DISPATCH_FAILED"
        )
        stage(
            active_stage,
            "GDN dừng do lỗi chưa xác định.",
            active_step,
            state="pending" if transaction_submitted else "failed",
        )
        return _result(
            False,
            code,
            (
                "Đã gửi Create Transaction nhưng không đọc được kết quả WFX. "
                "Không tự chạy lại để tránh tạo trùng."
                if transaction_submitted
                else "Không hoàn tất được (GDN) Dispatch."
            ),
            errors=[f"{type(error).__name__}: {_first_line(error)}"],
            transaction_submitted=transaction_submitted,
            **failure_context(code),
        )
    finally:
        if playwright is not None:
            playwright.stop()


def open_gdn_status(log: Callable[[str], None] = print) -> dict[str, Any]:
    """Mở đúng EDI package GDN để user kiểm tra mà không ghi transaction."""
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_edi(page, log)
        rows = [
            row
            for row in _edi_rows(frame)
            if row.get("package_name", "").casefold() == PACKAGE_LABEL.casefold()
        ]
        latest = max(rows, key=_processed_sort_key) if rows else None
        detail = str((latest or {}).get("transaction_detail") or "").strip()
        return _result(
            True,
            "GDN_STATUS_READY",
            (
                f"Đã mở EDI Production Order. Package GDN mới nhất: {detail}."
                if detail
                else "Đã mở EDI Production Order để kiểm tra package GDN."
            ),
            package_count=len(rows),
            latest_status=detail,
        )
    except DispatchFlowError as error:
        return _result(False, error.code, error.message, errors=error.errors)
    except Exception as error:
        boundary = _browser_boundary_result(error)
        if boundary is not None:
            return boundary
        return _result(
            False,
            "GDN_EDI_NOT_READY",
            "Không mở được EDI Production Order để kiểm tra GDN.",
            errors=[f"{type(error).__name__}: {_first_line(error)}"],
        )
    finally:
        if playwright is not None:
            playwright.stop()
