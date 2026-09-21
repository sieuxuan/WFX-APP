"""Mở Supplier List và đổi Category."""

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
    _first_line,
    _mark_document,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.directory.frames import (
    _actionable_master,
    _company_search_frame,
    _select_supplier_category,
    _supplier_category_frame,
    _supplier_company_ready,
    _wait_supplier_left,
)
from wfx_panel.automation.modules import (
    _active_wfx_page,
    _click_module_menu_on_page,
    _click_navigation_control,
)


def _wait_supplier_company_ready(
    page: Page,
    category_value: str,
    deadline: float,
) -> Frame | None:
    stable_since = 0.0
    while time.monotonic() < deadline:
        company_frame = _company_search_frame(
            page,
            "supplier",
            timeout_s=0.5,
        )
        if company_frame is None or not _supplier_company_ready(
            company_frame,
            category_value,
        ):
            stable_since = 0.0
            _wait(page, 200)
            continue
        if stable_since <= 0:
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= 0.8:
            return company_frame
        _wait(page, 200)
    return None


def _open_supplier_master(
    page: Page,
    log: Callable[[str], None],
    category_value: str,
    category_changed: bool,
    timeout_s: float = 35,
) -> Frame:
    if not category_changed:
        existing = _company_search_frame(page, "supplier", timeout_s=0.5)
        if (
            existing is not None
            and _supplier_company_ready(existing, category_value)
        ):
            _write_log(
                log,
                "[SUPPLIER] Master hiện tại đã đúng Category; dùng lại grid.",
            )
            return existing
    deadline = time.monotonic() + timeout_s
    attempt = 0
    while time.monotonic() < deadline:
        left = _supplier_category_frame(page)
        if left is None:
            _wait(page, 200)
            continue
        try:
            master = _actionable_master(left)
            if master is None:
                _wait(page, 200)
                continue
            attempt += 1
            _write_log(log, f"[SUPPLIER] Click exact Master; attempt={attempt}")
            _click_navigation_control(master)
            ready_deadline = min(deadline, time.monotonic() + 4.5)
            company_frame = _wait_supplier_company_ready(
                page,
                category_value,
                ready_deadline,
            )
            if company_frame is not None:
                _write_log(
                    log,
                    "[SUPPLIER] Master, Category và Company Name "
                    "search đã sẵn sàng.",
                )
                return company_frame
        except PlaywrightError:
            pass
        _wait(page, 250)
    raise PlaywrightTimeoutError("Không mở được Supplier > Master.")


def _open_supplier_category_on_page(
    page: Page,
    module_xpath: str,
    category_name: str,
    category_value: str,
    log: Callable[[str], None],
) -> Frame:
    current = _supplier_category_frame(page)
    if current is None:
        old_left = _mark_document(None, "supplier-left")
        _click_module_menu_on_page(page, "Supplier List", module_xpath, log)
        _wait_supplier_left(page, old_left)
    else:
        _write_log(
            log,
            "[SUPPLIER] Supplier List đã mở; chuyển Category trực tiếp.",
        )
    category_changed = _select_supplier_category(
        page,
        category_name,
        category_value,
        log,
    )
    return _open_supplier_master(
        page,
        log,
        category_value,
        category_changed,
    )


def open_supplier_category(
    module_xpath: str,
    category_name: str,
    category_value: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_supplier_category_on_page(
            page, module_xpath, category_name, category_value, log
        )
        search = frame.locator("#txtCompanyName")
        search.wait_for(state="visible", timeout=5_000)
        return _result(
            True,
            "SUPPLIER_CATEGORY_READY",
            f"Đã mở Supplier > {category_name} > Master.",
            category=category_name,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Supplier chưa sẵn sàng: {_first_line(exc)}"
        return _result(False, "SUPPLIER_MASTER_NOT_READY", message)
    except Exception as exc:
        boundary = _browser_boundary_result(exc)
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        return _result(False, "SUPPLIER_OPEN_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
