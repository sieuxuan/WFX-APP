"""Mở module WFX tổng quát + floating filter dùng chung + Sale ASN.

Tách nguyên văn từ login.py — không đổi logic.
"""

from __future__ import annotations

from wfx_panel.automation._common import (
    _MODULE_GRID_STATE_JS,
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _document_changed,
    _ensure_select_value,
    _first_visible,
    _mark_document,
    _result,
    _wait_frame_with_selectors,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.catalog import (
    _click_catalog_master,
    _show_catalog_floating_filter,
)


def open_module(
    module_name: str,
    xpath: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Kết nối lại tab WFX đang login và mở module được yêu cầu."""
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        _write_log(log, f"[MODULE] Đang tìm menu: {module_name}")

        login_form = page.locator("#txtUserID")
        if login_form.is_visible(timeout=1_500):
            return _result(False, "NOT_LOGGED_IN", "Phiên chưa đăng nhập hoặc đã hết hạn.")

        previous_left = page.frame(name="left") if module_name == "Catalog" else None
        previous_grid = (
            next((f for f in page.frames if "wfxcataloglist" in f.url.lower()), None)
            if module_name == "Catalog"
            else None
        )
        target = page.locator(f"xpath={xpath}")
        target.wait_for(state="attached", timeout=8_000)
        _write_log(log, f"[MODULE] Đã tìm thấy {module_name}, đang click...")
        _click(target)

        if module_name == "Catalog":
            _write_log(log, "[CATALOG] Đang chờ frame left...")
            _click_catalog_master(page, log, previous_frame=previous_left)
            _show_catalog_floating_filter(page, log, previous_frame=previous_grid)
            _write_log(log, "[CATALOG] Đã mở Master và Floating Filter")
            message = "Đã mở Catalog > Master và Floating Filter."
        else:
            _write_log(log, f"[MODULE] Đã mở: {module_name}")
            message = f"Đã mở {module_name}."

        return _result(
            True,
            "MODULE_OPENED",
            message,
            module=module_name,
            url=page.url,
        )
    except PlaywrightTimeoutError as exc:
        detail = str(exc).splitlines()[0]
        message = f"Timeout khi mở {module_name}: {detail}"
        _write_log(log, message)
        return _result(False, "MODULE_NOT_FOUND", message, module=module_name)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _write_log(log, message)
        return _result(False, "MODULE_FAILED", message, module=module_name)
    finally:
        if playwright is not None:
            playwright.stop()


def _active_wfx_page(playwright: Playwright, log: Callable[[str], None]) -> tuple[Any, Page]:
    if not _chrome_is_ready():
        raise RuntimeError("CHROME_CLOSED")
    browser, page = _connect_to_chrome(playwright)
    _attach_dialog_handler(page, log)
    login_form = page.locator("#txtUserID")
    if login_form.count() and login_form.is_visible(timeout=1_500):
        raise RuntimeError("NOT_LOGGED_IN")
    return browser, page


def _click_module_menu_on_page(
    page: Page,
    module_name: str,
    xpath: str,
    log: Callable[[str], None],
) -> None:
    target = page.locator(f"xpath={xpath}")
    target.wait_for(state="attached", timeout=8_000)
    _write_log(log, f"[MODULE] Đang mở {module_name}...")
    _click(target)


def _mark_grid_roots(page: Page) -> list[tuple[Frame, str]]:
    """Đánh dấu các grid đang có để không nhận nhầm grid cũ sau navigation."""
    snapshots: list[tuple[Frame, str]] = []
    for frame in page.frames:
        try:
            roots = frame.locator(".ag-root-wrapper")
            for index in range(roots.count()):
                marker = f"module-grid-{time.monotonic_ns()}-{index}"
                roots.nth(index).evaluate(
                    "(root, marker) => { root.__wfxPanelGridMarker = marker; }",
                    marker,
                )
                snapshots.append((frame, marker))
        except PlaywrightError:
            continue
    return snapshots


def _grid_root_is_new(
    frame: Frame,
    root: Any,
    snapshots: list[tuple[Frame, str]],
) -> bool:
    old_markers = {marker for old_frame, marker in snapshots if old_frame == frame}
    if not old_markers:
        return True
    try:
        marker = root.evaluate("root => root.__wfxPanelGridMarker || ''")
        return marker not in old_markers
    except PlaywrightError:
        return True


def _show_module_floating_filter(
    page: Page,
    log: Callable[[str], None],
    previous_grids: list[tuple[Frame, str]] | None = None,
    timeout_s: float = 40,
) -> Frame:
    """Chờ grid mới ổn định, bật filter và xác nhận hàng filter thật sự mở."""
    deadline = time.monotonic() + timeout_s
    last_click = 0.0
    last_error: Exception | None = None
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    settled_key: tuple[Any, ...] | None = None
    filter_stable_since = 0.0
    last_state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                roots = frame.locator(".ag-root-wrapper")
                for index in range(roots.count()):
                    root = roots.nth(index)
                    if not root.is_visible() or not _grid_root_is_new(
                        frame, root, previous_grids or []
                    ):
                        continue
                    last_state = root.evaluate(_MODULE_GRID_STATE_JS)
                    key = (
                        frame.url,
                        last_state["loading"],
                        last_state["noRows"],
                        last_state["renderedRows"],
                    )
                    ready = (
                        not last_state["loading"]
                        and (
                            last_state["renderedRows"] > 0
                            or last_state["noRows"]
                        )
                    )
                    if ready and key == stable_key:
                        grid_settled = time.monotonic() - stable_since >= 0.75
                    else:
                        stable_key = key
                        stable_since = time.monotonic()
                        grid_settled = False
                    if not grid_settled:
                        continue
                    if settled_key != key:
                        settled_key = key
                        _write_log(
                            log,
                            "[FLOATING FILTER] Grid đã ổn định; "
                            f"loading={last_state['loading']}; "
                            f"noRows={last_state['noRows']}; "
                            f"renderedRows={last_state['renderedRows']}.",
                        )

                    if last_state["filterVisible"]:
                        if filter_stable_since <= 0:
                            filter_stable_since = time.monotonic()
                        if time.monotonic() - filter_stable_since < 0.9:
                            continue
                        inputs = root.locator(
                            ".ag-floating-filter input, "
                            ".ag-header-row-column-filter input"
                        )
                        visible_input = _first_visible(inputs)
                        if (
                            visible_input is not None
                            and visible_input.is_enabled()
                        ):
                            value = visible_input.input_value(timeout=500)
                            _write_log(
                                log,
                                "[FLOATING FILTER] Hàng filter đã hiển thị; "
                                f"inputs={last_state['filterInputCount']}; "
                                f"headerHeight={last_state['headerHeight']}; "
                                f"filterRowHeight={last_state['filterRowHeight']}; "
                                f"value={value!r}.",
                            )
                            return frame
                    else:
                        filter_stable_since = 0.0

                    show_button = frame.locator("#showfloatingfilter")
                    button = _first_visible(show_button)
                    if (
                        button is not None
                        and time.monotonic() - last_click >= 1.5
                    ):
                        last_click = time.monotonic()
                        _write_log(
                            log,
                            "[FLOATING FILTER] Đang click #showfloatingfilter...",
                        )
                        # WFX gắn handler trực tiếp lên DIV. Native DOM click
                        # ổn định hơn pointer click khi sidebar/grid vừa relayout.
                        button.evaluate("element => element.click()")
            except (PlaywrightError, PlaywrightTimeoutError) as exc:
                last_error = exc
        page.wait_for_timeout(250)
    raise PlaywrightTimeoutError(
        "Show Floating Filter chưa sẵn sàng; "
        f"gridState={last_state}; lastError={last_error}"
    )


def open_module_with_floating_filter(
    module_name: str,
    xpath: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        previous_grids = _mark_grid_roots(page)
        _click_module_menu_on_page(page, module_name, xpath, log)
        _show_module_floating_filter(page, log, previous_grids)
        return _result(
            True,
            "MODULE_FILTER_READY",
            f"Đã mở {module_name} và bật Floating Filter.",
            module=module_name,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Chrome automation chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module=module_name)
    except PlaywrightTimeoutError as exc:
        message = f"Timeout khi mở {module_name}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "FLOATING_FILTER_NOT_READY", message, module=module_name)
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "MODULE_FAILED", message, module=module_name)
    finally:
        if playwright is not None:
            playwright.stop()


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
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Chrome automation chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message)
    except PlaywrightTimeoutError as exc:
        message = f"Sale ASN New chưa sẵn sàng: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_NEW_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_NEW_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def _visible_locator_in_frames(
    page: Page,
    selector: str,
    timeout_s: float = 20,
) -> tuple[Frame, Any]:
    """Chờ một control WFX đang hiển thị, bất kể nó nằm trong frame nào."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                matches = frame.locator(selector)
                for index in range(matches.count()):
                    candidate = matches.nth(index)
                    if candidate.is_visible():
                        return frame, candidate
            except PlaywrightError:
                continue
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError(f"Không tìm thấy control: {selector}")


def _click_navigation_control(locator: Any) -> None:
    """Click control ASP.NET; frame detach ngay sau click là navigation thành công."""
    try:
        _click(locator)
    except PlaywrightError as exc:
        message = str(exc).casefold()
        if not any(
            marker in message
            for marker in (
                "frame was detached",
                "execution context was destroyed",
                "target page, context or browser has been closed",
            )
        ):
            raise


def toggle_company_foc(
    xpath: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Đổi FOC giữa ASN/GRN trong Company Setup và xác nhận WFX đã lưu."""
    checkbox_selector = "#chkAllowToMarkFOCQtyOnRMPOASN"
    misc_selector = (
        'a.clsDataLabel[onclick*="wfx_MyCompanySite.aspx"]'
        '[onclick*="CurrentTab=4"][onclick*="CurrentItem=12"]'
    )
    save_selector = (
        'td.clsBtnOff[title="Save"] a#lnkSave.clsNavLink, '
        'a#lnkSave.clsNavLink[onclick*="ChangeAction"][onclick*="SAVE"]'
    )
    playwright: Playwright | None = None
    response_handler: Callable[[Any], None] | None = None
    page: Page | None = None
    save_responses: list[dict[str, Any]] = []
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        _click_module_menu_on_page(page, "Company Setup", xpath, log)

        _write_log(
            log,
            "[COMPANY SETUP] Đang mở 12. Miscellaneous Settings...",
        )
        _misc_frame, misc = _visible_locator_in_frames(
            page, misc_selector, timeout_s=20
        )
        _click_navigation_control(misc)

        frame, checkbox = _visible_locator_in_frames(
            page, checkbox_selector, timeout_s=20
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

        response_handler = record_save_response
        page.on("response", response_handler)
        # set_checked có thể làm WFX thay document/frame. Không giữ lại `frame`
        # cũ của checkbox: resolve lại đúng link Save đang hiển thị trên toàn
        # bộ frame, gồm markup td.clsBtnOff mà trang Company Setup đang dùng.
        save_frame, save = _visible_locator_in_frames(
            page,
            save_selector,
            timeout_s=12,
        )
        snapshot = _mark_document(save_frame, "company-foc-save")
        _write_log(log, "[COMPANY SETUP] Đang bấm Save...")
        _click_navigation_control(save)

        deadline = time.monotonic() + 25
        confirmed = False
        observed_state: bool | None = None
        while time.monotonic() < deadline:
            try:
                current_frame, current_checkbox = _visible_locator_in_frames(
                    page, checkbox_selector, timeout_s=1
                )
                observed_state = current_checkbox.is_checked(timeout=1_000)
                document_saved = _document_changed(current_frame, snapshot)
                request_saved = any(
                    response.get("ok") for response in save_responses
                )
                if observed_state == wanted and (
                    document_saved or request_saved
                ):
                    confirmed = True
                    break
            except (PlaywrightError, PlaywrightTimeoutError):
                pass
            page.wait_for_timeout(250)

        if not confirmed:
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
            return _result(
                False,
                "COMPANY_FOC_SAVE_NOT_CONFIRMED",
                "Đã đổi checkbox nhưng chưa xác nhận được WFX lưu thành công."
                + detail,
                previous_foc_mode=previous_mode,
                foc_mode=(
                    "FOC cho ASN"
                    if observed_state
                    else "FOC cho GRN"
                    if observed_state is False
                    else previous_mode
                ),
                foc_enabled=observed_state,
                saved=False,
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
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Chrome automation chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message)
    except PlaywrightTimeoutError as exc:
        message = (
            "Company Setup chưa sẵn sàng: "
            f"{str(exc).splitlines()[0]}"
        )
        _write_log(log, message)
        return _result(False, "COMPANY_FOC_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "COMPANY_FOC_FAILED", message)
    finally:
        if page is not None and response_handler is not None:
            try:
                page.remove_listener("response", response_handler)
            except Exception:
                pass
        if playwright is not None:
            playwright.stop()
