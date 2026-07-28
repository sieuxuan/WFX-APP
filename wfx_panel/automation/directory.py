"""Workflow Supplier và Buyer (chia sẻ helper company search).

Tách nguyên văn từ login.py — không đổi logic.
"""

from __future__ import annotations

from wfx_panel.automation._common import (
    _COMPANY_ROWS_JS,
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _document_changed,
    _mark_document,
    _result,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules import (
    _active_wfx_page,
    _click_module_menu_on_page,
    _click_navigation_control,
)


def _supplier_category_frame(page: Page) -> Frame | None:
    """Tìm frame Supplier theo control thực tế; WFX hiện dùng name=body."""
    fallback: Frame | None = None
    for frame in page.frames:
        try:
            if frame.locator("#ddlCategory").count() == 0:
                continue
            if "wfxpartygroup" in str(frame.url or "").casefold():
                return frame
            fallback = fallback or frame
        except PlaywrightError:
            continue
    return fallback


def _wait_supplier_left(
    page: Page,
    snapshot: tuple[Frame | None, str],
    timeout_s: float = 15,
) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = _supplier_category_frame(page)
        if frame is not None:
            try:
                if (
                    frame.locator("#ddlCategory").count() > 0
                    and _document_changed(frame, snapshot)
                ):
                    return frame
            except PlaywrightError:
                pass
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError("Không tìm thấy frame left của Supplier List.")


def _select_supplier_category(
    page: Page,
    category_name: str,
    category_value: str,
    log: Callable[[str], None],
) -> None:
    frame = _wait_supplier_left(page, (None, ""), timeout_s=8)
    field = frame.locator("#ddlCategory")
    if field.input_value() != category_value:
        field.locator(f'option[value="{category_value}"]').wait_for(
            state="attached", timeout=5_000
        )
        _write_log(log, f"[SUPPLIER] Đang chọn Category {category_name}...")
        try:
            field.select_option(value=category_value, timeout=5_000)
        except PlaywrightError as exc:
            message = str(exc).casefold()
            if not any(
                marker in message
                for marker in (
                    "frame was detached",
                    "execution context was destroyed",
                )
            ):
                raise
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current = _supplier_category_frame(page)
        try:
            if (
                current is not None
                and current.locator("#ddlCategory").input_value(timeout=500)
                == category_value
            ):
                _write_log(log, f"[SUPPLIER] Đã chọn {category_name}.")
                return
        except PlaywrightError:
            pass
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError(f"WFX không xác nhận Category {category_name}.")


def _actionable_master(frame: Frame) -> Any | None:
    nodes = frame.locator(
        'span[onclick], a, button, [role="button"], input[type="button"]'
    )
    for index in range(nodes.count()):
        node = nodes.nth(index)
        try:
            text = (
                node.input_value(timeout=300)
                if node.evaluate("element => element.tagName") == "INPUT"
                else node.inner_text(timeout=300)
            )
            if " ".join((text or "").split()).casefold() == "master":
                return node
        except PlaywrightError:
            continue
    return None


def _company_search_frame(page: Page, timeout_s: float = 4) -> Frame | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                if frame.locator("#txtCompanyName").count() > 0:
                    return frame
            except PlaywrightError:
                continue
        page.wait_for_timeout(200)
    return None


def _open_supplier_master(
    page: Page,
    log: Callable[[str], None],
    timeout_s: float = 35,
) -> Frame:
    deadline = time.monotonic() + timeout_s
    attempt = 0
    while time.monotonic() < deadline:
        left = _supplier_category_frame(page)
        if left is None:
            page.wait_for_timeout(200)
            continue
        try:
            master = _actionable_master(left)
            if master is None:
                page.wait_for_timeout(200)
                continue
            attempt += 1
            _write_log(log, f"[SUPPLIER] Click exact Master; attempt={attempt}")
            _click_navigation_control(master)
            company_frame = _company_search_frame(page, timeout_s=4.5)
            if company_frame is not None:
                _write_log(log, "[SUPPLIER] Master và Company Name search đã sẵn sàng.")
                return company_frame
        except PlaywrightError:
            pass
        page.wait_for_timeout(250)
    raise PlaywrightTimeoutError("Không mở được Supplier > Master.")


def _open_supplier_category_on_page(
    page: Page,
    module_xpath: str,
    category_name: str,
    category_value: str,
    log: Callable[[str], None],
) -> Frame:
    old_left = _mark_document(
        _supplier_category_frame(page),
        "supplier-left",
    )
    _click_module_menu_on_page(page, "Supplier List", module_xpath, log)
    _wait_supplier_left(page, old_left)
    _select_supplier_category(page, category_name, category_value, log)
    return _open_supplier_master(page, log)


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
    except RuntimeError as exc:
        code = str(exc)
        message = "Chrome automation chưa được mở." if code == "CHROME_CLOSED" else "Phiên chưa đăng nhập hoặc đã hết hạn."
        return _result(False, code, message)
    except PlaywrightTimeoutError as exc:
        message = f"Supplier chưa sẵn sàng: {str(exc).splitlines()[0]}"
        return _result(False, "SUPPLIER_MASTER_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        return _result(False, "SUPPLIER_OPEN_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def _filter_company_rows(
    page: Page,
    frame: Frame,
    query: str,
    log: Callable[[str], None],
) -> tuple[Frame, dict[str, Any]]:
    field = frame.locator("#txtCompanyName")
    field.wait_for(state="visible", timeout=5_000)
    field.fill("")
    field.type(query, delay=25)
    if field.input_value(timeout=1_000) != query:
        raise PlaywrightTimeoutError("WFX không xác nhận Company Name query.")
    try:
        field.press("Enter", timeout=2_000)
    except PlaywrightError:
        pass
    _write_log(log, f"[COMPANY SEARCH] Đã nhập query={query!r}")
    deadline = time.monotonic() + 18
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    last: dict[str, Any] = {"rows": [], "noRows": False, "loading": False}
    while time.monotonic() < deadline:
        current = _company_search_frame(page, timeout_s=2)
        if current is None:
            page.wait_for_timeout(200)
            continue
        try:
            last = current.evaluate(_COMPANY_ROWS_JS, {"query": query})
            rows = last["rows"]
            matching = [row for row in rows if row["matches"]]
            filtered = not rows or len(matching) == len(rows)
            key = (last["noRows"], tuple((row["company"], row["hasEdit"]) for row in rows))
            if not last.get("loading") and filtered and key == stable_key:
                required = 2.5 if not rows else 0.8
                if time.monotonic() - stable_since >= required:
                    return current, last
            else:
                stable_key = key
                stable_since = time.monotonic()
        except PlaywrightError:
            pass
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError(
        f"Kết quả Company Name chưa ổn định: {last}"
    )


def find_supplier_across_categories(
    module_xpath: str,
    categories: dict[str, str],
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _result(False, "QUERY_REQUIRED", "Vui lòng nhập tên Supplier cần tìm.")
    playwright: Playwright | None = None
    checked: list[str] = []
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        for category_name, category_value in categories.items():
            checked.append(category_name)
            _write_log(log, f"[SUPPLIER FIND] Đang kiểm tra {category_name}...")
            frame = _open_supplier_category_on_page(
                page, module_xpath, category_name, category_value, log
            )
            _frame, state = _filter_company_rows(page, frame, query, log)
            matches = [row["company"] for row in state["rows"] if row["matches"]]
            if matches:
                return _result(
                    True,
                    "SUPPLIER_FOUND",
                    f"Đã tìm thấy Supplier trong Category {category_name}. Giữ màn hình để bạn kiểm tra.",
                    category=category_name,
                    matches=matches[:10],
                    checked_categories=checked,
                )
        return _result(
            False,
            "SUPPLIER_NOT_FOUND",
            f"Không tìm thấy Supplier chứa: {query}.",
            checked_categories=checked,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = "Chrome automation chưa được mở." if code == "CHROME_CLOSED" else "Phiên chưa đăng nhập hoặc đã hết hạn."
        return _result(False, code, message)
    except PlaywrightTimeoutError as exc:
        return _result(False, "SUPPLIER_SEARCH_NOT_READY", str(exc).splitlines()[0], checked_categories=checked)
    except Exception as exc:
        return _result(False, "SUPPLIER_SEARCH_FAILED", f"{type(exc).__name__}: {str(exc).splitlines()[0]}", checked_categories=checked)
    finally:
        if playwright is not None:
            playwright.stop()


def find_and_open_buyer(
    module_xpath: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return _result(False, "QUERY_REQUIRED", "Vui lòng nhập tên Buyer cần tìm.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        _click_module_menu_on_page(page, "Buyer List", module_xpath, log)
        frame = _company_search_frame(page, timeout_s=20)
        if frame is None:
            raise PlaywrightTimeoutError("Không tìm thấy #txtCompanyName của Buyer List.")
        frame, state = _filter_company_rows(page, frame, query, log)
        matches = [row["company"] for row in state["rows"] if row["matches"]]
        if not matches:
            return _result(
                False,
                "BUYER_NOT_FOUND",
                f"Không tìm thấy Buyer chứa: {query}.",
            )

        rows = frame.locator("tr")
        target = None
        target_name = ""
        for index in range(rows.count()):
            row = rows.nth(index)
            try:
                if not row.is_visible() or row.locator("#txtCompanyName").count():
                    continue
                text = " ".join(row.inner_text(timeout=500).split())
                if query.casefold() not in text.casefold():
                    continue
                edit = row.locator('a#lnkEdit, a[id="lnkEdit"]')
                if edit.count() and edit.first.is_visible():
                    target = edit.first
                    target_name = text
                    break
            except PlaywrightError:
                continue
        if target is None:
            return _result(False, "BUYER_EDIT_NOT_FOUND", "Đã thấy Buyer nhưng không tìm thấy nút Edit.")

        snapshot = _mark_document(frame, "buyer-list")
        page_count = len(browser.contexts[0].pages)
        _write_log(log, f"[BUYER FIND] Đang mở Buyer đầu tiên: {target_name}")
        target.evaluate("element => element.click()")
        deadline = time.monotonic() + 15
        confirmed = False
        while time.monotonic() < deadline:
            if len(browser.contexts[0].pages) > page_count:
                confirmed = True
                break
            for candidate in page.frames:
                try:
                    if candidate == snapshot[0] and _document_changed(candidate, snapshot):
                        confirmed = True
                        break
                except PlaywrightError:
                    continue
            if confirmed:
                break
            try:
                if not target.is_visible():
                    confirmed = True
                    break
            except PlaywrightError:
                confirmed = True
                break
            page.wait_for_timeout(250)
        if not confirmed:
            return _result(False, "BUYER_EDIT_NOT_CONFIRMED", "WFX chưa xác nhận màn Edit Buyer.")
        return _result(
            True,
            "BUYER_EDIT_OPENED",
            "Đã tìm và mở Edit của Buyer đầu tiên phù hợp.",
            buyer=matches[0],
            matches=matches[:10],
        )
    except RuntimeError as exc:
        code = str(exc)
        message = "Chrome automation chưa được mở." if code == "CHROME_CLOSED" else "Phiên chưa đăng nhập hoặc đã hết hạn."
        return _result(False, code, message)
    except PlaywrightTimeoutError as exc:
        return _result(False, "BUYER_SEARCH_NOT_READY", str(exc).splitlines()[0])
    except Exception as exc:
        return _result(False, "BUYER_SEARCH_FAILED", f"{type(exc).__name__}: {str(exc).splitlines()[0]}")
    finally:
        if playwright is not None:
            playwright.stop()
