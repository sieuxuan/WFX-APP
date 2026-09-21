"""Mở màn New của module — thao tác ghi nên phải xác nhận đúng trang đích."""

from __future__ import annotations

from wfx_panel.automation._common import (
    Any,
    Callable,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _document_changed,
    _ensure_select_value,
    _first_line,
    _mark_document,
    _result,
    _wait,
    _wait_frame_with_selectors,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules.constants import MODULE_NEW_CONFIRM_SECONDS
from wfx_panel.automation.modules.menu import (
    _active_wfx_page,
    _click_module_menu_on_page,
    _menu_target_markers,
)


def open_sale_asn_new(
    xpath: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        _click_module_menu_on_page(page, "Sale ASN > New", xpath, log)
        _wait_frame_with_selectors(page, ("#ddlASNType", "#ddlASNAgainst"))
        _ensure_select_value(page, "#ddlASNType", "1", "ASN Type", log)
        _ensure_select_value(
            page,
            "#ddlASNAgainst",
            "BuyerOrderDispatch",
            "ASN Against",
            log,
        )
        frame = _wait_frame_with_selectors(
            page, ("#ddlASNType", "#ddlASNAgainst")
        )
        asn_type = frame.locator("#ddlASNType").input_value()
        against = frame.locator("#ddlASNAgainst").input_value()
        if asn_type != "1" or against != "BuyerOrderDispatch":
            raise PlaywrightTimeoutError("Giá trị Sale ASN New chưa được xác nhận.")
        return _result(
            True,
            "SALE_ASN_NEW_READY",
            "Đã mở Sale ASN New: With GDN · Buyer Order Dispatch.",
            asn_type=asn_type,
            asn_against=against,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Sale ASN New chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_NEW_NOT_READY", message)
    except Exception as exc:
        boundary = _browser_boundary_result(exc)
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_NEW_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def _wait_module_new_page(
    browser: Any,
    page: Page,
    markers: tuple[str, ...],
    timeout_s: float,
) -> Page | None:
    """Trả về page đang giữ màn New, hoặc None nếu không thấy marker nào."""
    if not markers:
        return None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            candidates = list(browser.contexts[0].pages)
        except (PlaywrightError, IndexError):
            candidates = [page]
        for candidate in candidates:
            try:
                frames = list(candidate.frames)
            except PlaywrightError:
                continue
            for frame in frames:
                url = str(getattr(frame, "url", "") or "").casefold()
                if any(marker in url for marker in markers):
                    return candidate
        _wait(page, 200)
    return None


def open_module_new(
    module_id: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    definitions = {
        "0063_0030_0020": (
            "QA Request",
            '//a[@title="New" '
            'and contains(@href,"MenuName=mnuQAInspectionRequestNew") '
            'and contains(@href,"QARequestType=QualityInspection")]',
            None,
        ),
        "0065_0880_0010_0020": (
            "Advance Payment Request",
            '//a[@title="New" '
            'and contains(@href,"MenuName=mnuAdvancePaymentRequestNew") '
            'and contains(@href,"WFXAdvancePaymentRequest.aspx?ARAPType=APR")]',
            ("#ddlRequestType", "RMPO", "Against RMPO"),
        ),
        "0065_0880_0030_0020": (
            "Expense Invoice",
            '//*[@id="0065_0880_0030_0010"]/a',
            ("#ddlInvoiceType", "GeneralExpense", "General Expense"),
        ),
    }
    if module_id not in definitions:
        return _result(
            False,
            "INVALID_FILTER",
            "Module này không hỗ trợ thao tác New.",
        )
    module_name, selector, default_selection = definitions[module_id]
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        snapshots = [
            _mark_document(candidate, f"module-new-{index}")
            for index, candidate in enumerate(page.frames)
        ]
        old_frames = {snapshot[0] for snapshot in snapshots}
        page_count = len(browser.contexts[0].pages)
        markers = _menu_target_markers(page, selector)
        menu_page = page
        _write_log(log, f"[MODULE NEW] Đang mở trực tiếp {module_name}.")
        _click_module_menu_on_page(
            page,
            f"{module_name} New",
            selector,
            log,
        )

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if len(browser.contexts[0].pages) > page_count:
                page = browser.contexts[0].pages[-1]
                break
            current_frames = list(page.frames)
            if any(candidate not in old_frames for candidate in current_frames):
                break
            if any(
                snapshot[0] in current_frames
                and _document_changed(snapshot[0], snapshot)
                for snapshot in snapshots
                if snapshot[0] is not None
            ):
                break
            _wait(page, 250)
        else:
            return _result(
                False,
                "MODULE_FAILED",
                f"WFX chưa xác nhận màn New của {module_name}.",
                module=module_name,
            )
        if not markers:
            # Link menu có thể chưa attach lúc đọc marker lần đầu (WFX còn đang
            # render menu). Sau click nó chắc chắn có trong DOM, nên đọc lại
            # trên chính trang giữ menu thay vì hạ chuẩn xác nhận.
            markers = _menu_target_markers(menu_page, selector)
        # Một frame đổi document chưa chắc là màn New: menu WFX cũng tự reload.
        # Trang đích đọc thẳng từ link menu mới là bằng chứng thật.
        opened_page = _wait_module_new_page(
            browser,
            page,
            markers,
            MODULE_NEW_CONFIRM_SECONDS,
        )
        if opened_page is not None:
            page = opened_page
        selected_label = ""
        if default_selection is not None:
            # Chọn được đúng dropdown của màn New cũng là một bằng chứng độc
            # lập, nên không chặn flow khi chỉ thiếu marker URL.
            select_selector, select_value, selected_label = default_selection
            _ensure_select_value(
                page,
                select_selector,
                select_value,
                selected_label,
                log,
            )
        elif opened_page is None:
            # Không có dropdown mặc định để làm bằng chứng thay thế, nên thiếu
            # trang đích là thiếu xác nhận — kể cả khi không đọc nổi marker.
            detail = (
                f"không thấy trang {', '.join(markers)} sau khi click menu"
                if markers
                else "không đọc được trang đích từ link menu để xác nhận"
            )
            return _result(
                False,
                "MODULE_FAILED",
                f"WFX chưa xác nhận màn New của {module_name}: {detail}.",
                module=module_name,
            )
        message = f"Đã mở trực tiếp {module_name} New."
        if selected_label:
            message = f"{message} Đã chọn sẵn {selected_label}."
        return _result(
            True,
            "MODULE_NEW_READY",
            message,
            module=module_name,
        )
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module=module_name)
        if boundary is not None:
            return boundary
        detail = f"{type(exc).__name__}: {_first_line(exc)}"
        message = f"Không thể mở New từ {module_name}: {detail}"
        _write_log(log, message)
        return _result(
            False,
            "MODULE_FAILED",
            message,
            module=module_name,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def open_sample_new(
    xpath: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        _click_module_menu_on_page(page, "Sample > New", xpath, log)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            for frame in page.frames:
                url = str(frame.url or "").casefold()
                if "wfxsr.aspx" in url and "action=new" in url:
                    return _result(
                        True,
                        "SAMPLE_NEW_READY",
                        "Đã mở New Sample Order.",
                    )
            _wait(page, 200)
        raise PlaywrightTimeoutError(
            "WFX chưa xác nhận màn New Sample Order."
        )
    except PlaywrightTimeoutError as exc:
        message = f"Sample New chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SAMPLE_NEW_NOT_READY", message)
    except Exception as exc:
        boundary = _browser_boundary_result(exc)
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SAMPLE_NEW_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
