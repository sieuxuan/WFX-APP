"""Workflow Supplier và Buyer (chia sẻ helper company search).

Tách nguyên văn từ login.py — không đổi logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field

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
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules import (
    MODULE_CONTEXT_PROBE_SECONDS,
    _active_wfx_page,
    _click_module_menu_on_page,
    _click_navigation_control,
)


def _supplier_category_frame(page: Page) -> Frame | None:
    """Tìm đúng frame Supplier; không nhầm #ddlCategory của Catalog."""
    for frame in page.frames:
        try:
            if frame.locator("#ddlCategory").count() == 0:
                continue
            url = str(frame.url or "").casefold()
            if "wfxpartygroup" in url and "partytype=2" in url:
                return frame
            title = str(frame.evaluate("() => document.title || ''"))
            if "supplier" in title.casefold():
                return frame
        except PlaywrightError:
            continue
    return None


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
        _wait(page, 200)
    raise PlaywrightTimeoutError("Không tìm thấy frame Supplier List.")


def _select_supplier_category(
    page: Page,
    category_name: str,
    category_value: str,
    log: Callable[[str], None],
) -> bool:
    frame = _wait_supplier_left(page, (None, ""), timeout_s=8)
    field = frame.locator("#ddlCategory")
    changed = field.input_value() != category_value
    if changed:
        # WFX chỉ nạp đủ 6 option khi dropdown nhận mousedown.
        # Trước đó DOM thường chỉ có [Select] + Apparel.
        field.dispatch_event("mousedown")
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
                return changed
        except PlaywrightError:
            pass
        _wait(page, 200)
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


def _company_frame_marker(frame: Frame) -> str:
    return str(
        frame.evaluate(
            """() => {
                const partyType = [...document.querySelectorAll(
                    'input, select'
                )].filter(element => /party.?type/i.test(
                    `${element.id} ${element.name}`
                )).map(element => element.value).join(' ');
                const heading = document.querySelector(
                    'h1, h2, .page-title, .clsPageTitle, td.clsPageTitle'
                )?.textContent || '';
                return [
                    location.href,
                    document.title,
                    partyType,
                    heading
                ].join(' ');
            }"""
        )
    ).casefold()


def _company_marker_matches(marker: str, expected_kind: str) -> bool:
    marker = str(marker or "").casefold()
    supplier = "partytype=2" in marker or "supplier" in marker
    buyer = (
        "partytype=1" in marker
        or "party type 1" in marker
        or "buyer" in marker
    )
    if expected_kind == "supplier":
        return supplier and not buyer
    if expected_kind == "buyer":
        return buyer and not supplier
    return False


def _company_search_frame(
    page: Page,
    expected_kind: str,
    timeout_s: float = 4,
) -> Frame | None:
    """Resolve Company search theo đúng PartyType; không dùng frame generic."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                if (
                    frame.locator("#txtCompanyName").count() > 0
                    and _company_marker_matches(
                        _company_frame_marker(frame),
                        expected_kind,
                    )
                ):
                    return frame
            except PlaywrightError:
                continue
        _wait(page, 200)
    return None


def _buyer_search_frame(page: Page, timeout_s: float = 4) -> Frame | None:
    """Chỉ nhận frame Buyer, không dùng nhầm Supplier cùng #txtCompanyName."""
    return _company_search_frame(page, "buyer", timeout_s)


def _supplier_company_ready(
    frame: Frame,
    category_value: str,
) -> bool:
    try:
        search = frame.locator("#txtCompanyName")
        if (
            frame.locator("#ddlCategory").input_value(timeout=500)
            != category_value
            or search.count() == 0
            or not search.first.is_visible()
            or not search.first.is_enabled()
        ):
            return False
        return not bool(
            frame.evaluate(
                """() => [...document.querySelectorAll(
                    '.loading, .loader, [aria-busy="true"]'
                )].some(element => {
                    const rect = element.getBoundingClientRect();
                    const style = getComputedStyle(element);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                })"""
            )
        )
    except PlaywrightError:
        return False


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


def _fill_company_query(
    page: Page,
    frame: Frame,
    query: str,
    log: Callable[[str], None],
    expected_kind: str,
) -> Frame:
    current = frame
    # WFX có thể thay frame Company ngay sau khi Master vừa báo ready. Resolve
    # lại đúng PartyType một lần thay vì trả lỗi ngẫu nhiên ở field đầu tiên.
    for attempt in range(2):
        try:
            field = current.locator("#txtCompanyName")
            field.wait_for(state="visible", timeout=5_000)
            field.fill("")
            field.type(query, delay=25)
            if field.input_value(timeout=1_000) != query:
                raise PlaywrightTimeoutError(
                    "WFX không xác nhận Company Name query."
                )
            try:
                field.press("Enter", timeout=2_000)
            except PlaywrightError:
                pass
            break
        except (PlaywrightError, PlaywrightTimeoutError):
            if attempt:
                raise
            replacement = _company_search_frame(
                page,
                expected_kind,
                timeout_s=3,
            )
            if replacement is None:
                raise PlaywrightTimeoutError(
                    "Frame Company Name đã đổi và chưa sẵn sàng."
                ) from None
            current = replacement
            _write_log(log, "[COMPANY SEARCH] Đã đồng bộ lại frame Company.")
    _write_log(log, f"[COMPANY SEARCH] Đã nhập query={query!r}")
    return current


def _company_result_state_key(state: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        state["noRows"],
        tuple((row["company"], row["hasEdit"]) for row in state["rows"]),
    )


def _wait_company_results(
    page: Page,
    frame: Frame,
    query: str,
    expected_kind: str,
) -> tuple[Frame, dict[str, Any]]:
    current = frame
    deadline = time.monotonic() + 18
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    last: dict[str, Any] = {"rows": [], "noRows": False, "loading": False}
    while time.monotonic() < deadline:
        try:
            if not _company_marker_matches(
                _company_frame_marker(current),
                expected_kind,
            ):
                replacement = _company_search_frame(
                    page,
                    expected_kind,
                    timeout_s=2,
                )
                if replacement is None:
                    _wait(page, 200)
                    continue
                current = replacement
            last = current.evaluate(_COMPANY_ROWS_JS, {"query": query})
            rows = last["rows"]
            matching = [row for row in rows if row["matches"]]
            filtered = not rows or len(matching) == len(rows)
            state_key = _company_result_state_key(last)
            if not last.get("loading") and filtered and state_key == stable_key:
                required = 2.5 if not rows else 0.8
                if time.monotonic() - stable_since >= required:
                    return current, last
            else:
                stable_key = state_key
                stable_since = time.monotonic()
        except PlaywrightError:
            replacement = _company_search_frame(
                page,
                expected_kind,
                timeout_s=2,
            )
            if replacement is not None:
                current = replacement
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        f"Kết quả Company Name chưa ổn định: {last}"
    )


def _filter_company_rows(
    page: Page,
    frame: Frame,
    query: str,
    log: Callable[[str], None],
    expected_kind: str,
) -> tuple[Frame, dict[str, Any]]:
    current = _fill_company_query(page, frame, query, log, expected_kind)
    return _wait_company_results(page, current, query, expected_kind)


@dataclass(frozen=True)
class _SupplierSearchRequest:
    page: Page
    module_xpath: str
    categories: Mapping[str, str]
    query: str
    log: Callable[[str], None]


@dataclass
class _SupplierSearchState:
    checked: list[str] = dataclass_field(default_factory=list)
    found_by_category: list[dict[str, Any]] = dataclass_field(
        default_factory=list
    )
    failed_categories: list[dict[str, str]] = dataclass_field(
        default_factory=list
    )


def _scan_supplier_categories(
    request: _SupplierSearchRequest,
) -> _SupplierSearchState:
    state = _SupplierSearchState()
    categories = request.categories
    for category_name, category_value in categories.items():
        state.checked.append(category_name)
        _write_log(
            request.log,
            f"[SUPPLIER FIND] Đang kiểm tra {category_name}...",
        )
        try:
            frame = _open_supplier_category_on_page(
                request.page,
                request.module_xpath,
                category_name,
                category_value,
                request.log,
            )
            _frame, company_state = _filter_company_rows(
                request.page,
                frame,
                request.query,
                request.log,
                "supplier",
            )
        except (PlaywrightError, PlaywrightTimeoutError) as error:
            detail = str(error).splitlines()[0]
            state.failed_categories.append(
                {"category": category_name, "detail": detail}
            )
            _write_log(
                request.log,
                f"[SUPPLIER FIND] Bỏ qua {category_name}: {detail}",
            )
            continue
        matches = list(
            dict.fromkeys(
                row["company"]
                for row in company_state["rows"]
                if row["matches"]
            )
        )
        if not matches:
            continue
        state.found_by_category.append(
            {
                "category": category_name,
                "count": len(matches),
                "matches": matches[:10],
            }
        )
        _write_log(
            request.log,
            f"[SUPPLIER FIND] {category_name}: {len(matches)} kết quả.",
        )
    return state


def _restore_first_supplier_result(
    request: _SupplierSearchRequest,
    state: _SupplierSearchState,
) -> None:
    if not state.found_by_category:
        return
    first_category = str(state.found_by_category[0]["category"])
    if state.checked[-1] == first_category:
        return
    try:
        first_frame = _open_supplier_category_on_page(
            request.page,
            request.module_xpath,
            first_category,
            request.categories[first_category],
            request.log,
        )
        _filter_company_rows(
            request.page,
            first_frame,
            request.query,
            request.log,
            "supplier",
        )
    except (PlaywrightError, PlaywrightTimeoutError) as error:
        _write_log(
            request.log,
            "[SUPPLIER FIND] Đã tổng hợp đủ kết quả nhưng không "
            f"đưa được WFX về Category đầu tiên: {error}",
        )


def _supplier_search_result(
    query: str,
    state: _SupplierSearchState,
) -> dict[str, Any]:
    if state.found_by_category:
        first = state.found_by_category[0]
        first_category = str(first["category"])
        category_names = [
            str(item["category"]) for item in state.found_by_category
        ]
        total_matches = sum(
            int(item["count"]) for item in state.found_by_category
        )
        partial = bool(state.failed_categories)
        return _result(
            True,
            "SUPPLIER_FOUND_PARTIAL" if partial else "SUPPLIER_FOUND",
            f"Đã tìm thấy {total_matches} kết quả trong "
            f"{len(state.found_by_category)} Category: "
            f"{', '.join(category_names)}. "
            f"Đang hiển thị kết quả ở {first_category}."
            + (
                f" Có {len(state.failed_categories)} Category chưa kiểm tra được."
                if partial
                else ""
            ),
            category=first_category,
            categories=category_names,
            matches=first["matches"],
            matches_by_category=state.found_by_category,
            checked_categories=state.checked,
            failed_categories=state.failed_categories,
        )
    if state.failed_categories:
        return _result(
            False,
            "SUPPLIER_SEARCH_PARTIAL",
            "Không tìm thấy kết quả trong các Category đã kiểm tra, "
            f"nhưng có {len(state.failed_categories)} Category bị lỗi.",
            checked_categories=state.checked,
            failed_categories=state.failed_categories,
        )
    return _result(
        False,
        "SUPPLIER_NOT_FOUND",
        f"Không tìm thấy Supplier chứa “{query}” trong "
        f"{len(state.checked)} Category.",
        checked_categories=state.checked,
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
    state = _SupplierSearchState()
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        request = _SupplierSearchRequest(
            page=page,
            module_xpath=module_xpath,
            categories=categories,
            query=query,
            log=log,
        )
        state = _scan_supplier_categories(request)
        _restore_first_supplier_result(request, state)
        return _supplier_search_result(query, state)
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Chrome automation chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message)
    except PlaywrightTimeoutError as exc:
        return _result(
            False,
            "SUPPLIER_SEARCH_NOT_READY",
            str(exc).splitlines()[0],
            checked_categories=state.checked,
        )
    except Exception as exc:
        return _result(
            False,
            "SUPPLIER_SEARCH_FAILED",
            f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
            checked_categories=state.checked,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def find_supplier_in_category(
    module_xpath: str,
    category_name: str,
    category_value: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở/đổi Category một lần rồi tìm Supplier ngay trong Category đó."""
    query = query.strip()
    if not query:
        return _result(
            False,
            "QUERY_REQUIRED",
            "Vui lòng nhập tên Supplier cần tìm.",
        )
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_supplier_category_on_page(
            page,
            module_xpath,
            category_name,
            category_value,
            log,
        )
        _frame, state = _filter_company_rows(
            page,
            frame,
            query,
            log,
            "supplier",
        )
        matches = [
            row["company"]
            for row in state["rows"]
            if row["matches"]
        ]
        if not matches:
            return _result(
                False,
                "SUPPLIER_NOT_FOUND",
                f"Không tìm thấy Supplier trong {category_name}: {query}.",
                category=category_name,
            )
        return _result(
            True,
            "SUPPLIER_FOUND",
            f"Đã tìm thấy Supplier trong Category {category_name}.",
            category=category_name,
            matches=matches[:10],
            checked_categories=[category_name],
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
        return _result(
            False,
            "SUPPLIER_SEARCH_NOT_READY",
            str(exc).splitlines()[0],
            category=category_name,
        )
    except Exception as exc:
        return _result(
            False,
            "SUPPLIER_SEARCH_FAILED",
            f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
            category=category_name,
        )
    finally:
        if playwright is not None:
            playwright.stop()


@dataclass(frozen=True)
class _BuyerEditTarget:
    control: Any
    name: str


def _first_buyer_edit_target(
    frame: Frame,
    query: str,
) -> _BuyerEditTarget | None:
    rows = frame.locator("tr")
    for index in range(rows.count()):
        row = rows.nth(index)
        try:
            if not row.is_visible() or row.locator("#txtCompanyName").count():
                continue
            row_text = " ".join(row.inner_text(timeout=500).split())
            if query.casefold() not in row_text.casefold():
                continue
            edit_links = row.locator('a#lnkEdit, a[id="lnkEdit"]')
            if edit_links.count() and edit_links.first.is_visible():
                return _BuyerEditTarget(edit_links.first, row_text)
        except PlaywrightError:
            continue
    return None


def _open_and_confirm_buyer_edit(
    context: Any,
    page: Page,
    frame: Frame,
    target_info: _BuyerEditTarget,
    log: Callable[[str], None],
) -> bool:
    snapshot = _mark_document(frame, "buyer-list")
    page_count = len(context.pages)
    _write_log(log, f"[BUYER FIND] Đang mở Buyer đầu tiên: {target_info.name}")
    target = target_info.control
    target.evaluate("element => element.click()")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if len(context.pages) > page_count:
            return True
        for candidate in page.frames:
            try:
                if candidate == snapshot[0] and _document_changed(
                    candidate,
                    snapshot,
                ):
                    return True
            except PlaywrightError:
                continue
        try:
            if not target.is_visible():
                return True
        except PlaywrightError:
            return True
        _wait(page, 250)
    return False


@dataclass(frozen=True)
class _BuyerSearchResultRequest:
    context: Any
    page: Page
    frame: Frame
    query: str
    state: Mapping[str, Any]
    log: Callable[[str], None]


def _open_first_matching_buyer(
    request: _BuyerSearchResultRequest,
) -> dict[str, Any]:
    matches = [
        row["company"]
        for row in request.state["rows"]
        if row["matches"]
    ]
    if not matches:
        return _result(
            False,
            "BUYER_NOT_FOUND",
            f"Không tìm thấy Buyer chứa: {request.query}.",
        )
    target = _first_buyer_edit_target(request.frame, request.query)
    if target is None:
        return _result(
            False,
            "BUYER_EDIT_NOT_FOUND",
            "Đã thấy Buyer nhưng không tìm thấy nút Edit.",
        )
    if not _open_and_confirm_buyer_edit(
        request.context,
        request.page,
        request.frame,
        target,
        request.log,
    ):
        return _result(
            False,
            "BUYER_EDIT_NOT_CONFIRMED",
            "WFX chưa xác nhận màn Edit Buyer.",
        )
    return _result(
        True,
        "BUYER_EDIT_OPENED",
        "Đã tìm và mở Edit của Buyer đầu tiên phù hợp.",
        buyer=matches[0],
        matches=matches[:10],
    )


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
        frame = _buyer_search_frame(
            page,
            timeout_s=MODULE_CONTEXT_PROBE_SECONDS,
        )
        if frame is None:
            _write_log(
                log,
                "[BUYER FIND] Buyer List chưa mở; đang tự mở List...",
            )
            _click_module_menu_on_page(
                page,
                "Buyer List",
                module_xpath,
                log,
            )
            frame = _buyer_search_frame(page, timeout_s=30)
            if frame is None:
                raise PlaywrightTimeoutError(
                    "Không tìm thấy ô Buyer sau khi app tự mở List."
                )
        frame, state = _filter_company_rows(
            page,
            frame,
            query,
            log,
            "buyer",
        )
        return _open_first_matching_buyer(
            _BuyerSearchResultRequest(
                context=browser.contexts[0],
                page=page,
                frame=frame,
                query=query,
                state=state,
                log=log,
            )
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
