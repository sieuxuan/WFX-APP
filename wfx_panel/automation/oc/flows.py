"""Điểm vào: upload EDI, Confirm New/Revision, Reject All, mở report Revise."""

from __future__ import annotations

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
from wfx_panel.automation.modules import _active_wfx_page
from wfx_panel.automation.oc.confirm import (
    _active_confirm_mode,
    _confirm_all_pending,
    _open_confirm_grid,
    _reject_all_pending,
    _set_confirm_page_size,
)
from wfx_panel.automation.oc.constants import (
    CONFIRM_TAB_SELECTORS,
    REVISION_REPORT_MENU_XPATH,
    REVISION_REPORT_SELECTOR,
)
from wfx_panel.automation.oc.dom import (
    _attached_in_frames,
    _toolbar_link,
    _visible_in_frames,
)
from wfx_panel.automation.oc.package import (
    _open_edi_form,
    _open_status_error_details,
    _process_package,
    _status_kind,
    _wait_statuses,
)
from wfx_panel.automation.oc.transaction import (
    _click_pending_transaction,
    _create_transaction,
    _select_first_transaction,
)


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
        boundary = _browser_boundary_result(error)
        if boundary is not None:
            return boundary
        return _result(
            False,
            "OC_REVISION_REPORT_FAILED",
            f"RuntimeError: {_first_line(error)}",
        )
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
