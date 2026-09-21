"""Company Setup: đổi nơi áp dụng FOC trong Miscellaneous Settings."""

from __future__ import annotations

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _browser_boundary_result,
    _document_changed,
    _first_line,
    _mark_document,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules.inputs import (
    _click_navigation_control,
    _visible_locator_in_frames,
)
from wfx_panel.automation.modules.menu import (
    _active_wfx_page,
    _click_module_menu_on_page,
)
from wfx_panel.automation.runtime import cancellation_deferred

_COMPANY_FOC_CHECKBOX_SELECTOR = "#chkAllowToMarkFOCQtyOnRMPOASN"


_COMPANY_MISC_SELECTOR = (
    'a.clsDataLabel[onclick*="wfx_MyCompanySite.aspx"]'
    '[onclick*="CurrentTab=4"][onclick*="CurrentItem=12"]'
)


_COMPANY_SAVE_SELECTOR = (
    'td.clsBtnOff[title="Save"] a#lnkSave.clsNavLink, '
    'a#lnkSave.clsNavLink[onclick*="ChangeAction"][onclick*="SAVE"]'
)


def _company_save_response_handler(
    save_responses: list[dict[str, Any]],
) -> Callable[[Any], None]:
    def record_save_response(response: Any) -> None:
        try:
            method = str(response.request.method or "").upper()
            if method not in {"POST", "PUT", "PATCH"}:
                return
            url = str(response.url or "")
            if "wfx_mycompanysite" not in url.casefold():
                return
            save_responses.append(
                {
                    "ok": bool(response.ok),
                    "status": int(response.status),
                    "url": url,
                }
            )
        except Exception:
            return

    return record_save_response


def _wait_company_foc_saved(
    page: Page,
    wanted: bool,
    snapshot: tuple[Frame | None, str],
    save_responses: list[dict[str, Any]],
) -> tuple[bool, bool | None]:
    deadline = time.monotonic() + 25
    observed_state: bool | None = None
    while time.monotonic() < deadline:
        try:
            current_frame, current_checkbox = _visible_locator_in_frames(
                page,
                _COMPANY_FOC_CHECKBOX_SELECTOR,
                timeout_s=1,
            )
            observed_state = current_checkbox.is_checked(timeout=1_000)
            document_saved = _document_changed(current_frame, snapshot)
            request_saved = any(response.get("ok") for response in save_responses)
            if observed_state == wanted and (document_saved or request_saved):
                return True, observed_state
        except (PlaywrightError, PlaywrightTimeoutError):
            pass
        _wait(page, 250)
    return False, observed_state


def _unsaved_company_foc_result(
    previous_mode: str,
    observed_state: bool | None,
    save_responses: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_statuses = [
        response["status"]
        for response in save_responses
        if not response.get("ok")
    ]
    detail = (
        f" Server trả về HTTP {failed_statuses[-1]}."
        if failed_statuses
        else ""
    )
    observed_mode = previous_mode
    if observed_state is True:
        observed_mode = "FOC cho ASN"
    elif observed_state is False:
        observed_mode = "FOC cho GRN"
    return _result(
        False,
        "COMPANY_FOC_SAVE_NOT_CONFIRMED",
        "Đã đổi checkbox nhưng chưa xác nhận được WFX lưu thành công." + detail,
        previous_foc_mode=previous_mode,
        foc_mode=observed_mode,
        foc_enabled=observed_state,
        saved=False,
    )


def _toggle_company_foc_setting(
    page: Page,
    log: Callable[[str], None],
) -> dict[str, Any]:
    _frame, checkbox = _visible_locator_in_frames(
        page,
        _COMPANY_FOC_CHECKBOX_SELECTOR,
        timeout_s=20,
    )
    previous = checkbox.is_checked(timeout=2_000)
    wanted = not previous
    previous_mode = "FOC cho ASN" if previous else "FOC cho GRN"
    wanted_mode = "FOC cho ASN" if wanted else "FOC cho GRN"
    _write_log(
        log,
        f"[COMPANY SETUP] Đang đổi {previous_mode} → {wanted_mode}...",
    )
    checkbox.set_checked(wanted, timeout=4_000)
    if checkbox.is_checked(timeout=2_000) != wanted:
        raise PlaywrightTimeoutError(
            "Checkbox Allow To Mark FOC Qty On RMPO ASN chưa đổi trạng thái."
        )

    save_responses: list[dict[str, Any]] = []
    response_handler = _company_save_response_handler(save_responses)
    page.on("response", response_handler)
    try:
        # Reacquire Save after set_checked because WFX may replace the frame.
        # Stop is deferred across the persistence confirmation critical section.
        with cancellation_deferred():
            save_frame, save = _visible_locator_in_frames(
                page,
                _COMPANY_SAVE_SELECTOR,
                timeout_s=12,
            )
            snapshot = _mark_document(save_frame, "company-foc-save")
            _write_log(log, "[COMPANY SETUP] Đang bấm Save...")
            _click_navigation_control(save)
            confirmed, observed_state = _wait_company_foc_saved(
                page,
                wanted,
                snapshot,
                save_responses,
            )
    finally:
        try:
            page.remove_listener("response", response_handler)
        except Exception:
            pass
    if not confirmed:
        return _unsaved_company_foc_result(
            previous_mode,
            observed_state,
            save_responses,
        )
    _write_log(log, f"[COMPANY SETUP] Đã lưu thành công: {wanted_mode}.")
    return _result(
        True,
        "COMPANY_FOC_CHANGED",
        f"Đổi FOC thành công. Trạng thái hiện tại: {wanted_mode}.",
        previous_foc_mode=previous_mode,
        foc_mode=wanted_mode,
        foc_enabled=wanted,
        saved=True,
    )


def toggle_company_foc(
    _xpath: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Đổi FOC giữa ASN/GRN trong Company Setup và xác nhận WFX đã lưu."""
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)

        try:
            _misc_frame, misc = _visible_locator_in_frames(
                page,
                _COMPANY_MISC_SELECTOR,
                timeout_s=1,
            )
        except PlaywrightTimeoutError:
            _write_log(
                log,
                "[COMPANY SETUP] Context hiện tại không phải Company Setup; "
                "đang tự mở List...",
            )
            _click_module_menu_on_page(page, "Company Setup", _xpath, log)
            try:
                _misc_frame, misc = _visible_locator_in_frames(
                    page,
                    _COMPANY_MISC_SELECTOR,
                    timeout_s=20,
                )
            except PlaywrightTimeoutError:
                return _result(
                    False,
                    "COMPANY_LIST_OPEN_FAILED",
                    "App đã tự mở Company Setup nhưng trang thiết lập "
                    "chưa sẵn sàng.",
                )
        _write_log(
            log,
            "[COMPANY SETUP] Đã thấy đúng List; "
            "đang mở 12. Miscellaneous Settings...",
        )
        _click_navigation_control(misc)
        return _toggle_company_foc_setting(page, log)
    except PlaywrightTimeoutError as exc:
        message = (
            "Company Setup chưa sẵn sàng: "
            f"{_first_line(exc)}"
        )
        _write_log(log, message)
        return _result(False, "COMPANY_FOC_NOT_READY", message)
    except Exception as exc:
        boundary = _browser_boundary_result(exc)
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "COMPANY_FOC_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
