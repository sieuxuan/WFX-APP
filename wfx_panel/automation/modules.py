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
    _wait,
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
    _catalog_tree_frame_now,
    _click_catalog_master,
    _open_catalog_menu_on_page,
    _show_catalog_floating_filter,
)
from wfx_panel.automation.runtime import cancellation_deferred

MODULE_GRID_POLL_MS = 150
MODULE_FILTER_VISIBLE_STABLE_SECONDS = 0.5
MODULE_CONTEXT_PROBE_SECONDS = 0.75


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
        browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        _write_log(log, f"[MODULE] Đang tìm menu: {module_name}")

        login_form = page.locator("#txtUserID")
        if login_form.is_visible(timeout=1_500):
            return _result(False, "NOT_LOGGED_IN", "Phiên chưa đăng nhập hoặc đã hết hạn.")

        previous_left = (
            _catalog_tree_frame_now(page) if module_name == "Catalog" else None
        )
        previous_grid = (
            next((f for f in page.frames if "wfxcataloglist" in f.url.lower()), None)
            if module_name == "Catalog"
            else None
        )
        target = page.locator(f"xpath={xpath}")
        target.wait_for(state="attached", timeout=8_000)
        _write_log(log, f"[MODULE] Đã tìm thấy {module_name}, đang click...")

        if module_name == "Catalog":
            _open_catalog_menu_on_page(
                page,
                target,
                log,
                previous_frame=previous_left,
            )
            _write_log(log, "[CATALOG] Đang chờ frame left...")
            _click_catalog_master(page, log, previous_frame=previous_left)
            _show_catalog_floating_filter(page, log, previous_frame=previous_grid)
            _write_log(log, "[CATALOG] Đã mở Master và Floating Filter")
            message = "Đã mở Catalog > Master và Floating Filter."
        else:
            snapshots = _mark_page_documents(page, "module-open")
            old_frame_ids = {
                id(snapshot[0])
                for snapshot in snapshots
                if snapshot[0] is not None
            }
            page_count = len(browser.contexts[0].pages)
            _click(target)
            if not _wait_for_module_navigation(
                browser,
                page,
                snapshots,
                old_frame_ids,
                page_count,
            ):
                raise PlaywrightTimeoutError(
                    "MODULE_OPEN_NOT_CONFIRMED:"
                    f"WFX chưa xác nhận navigation tới {module_name}."
                )
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
        code = (
            "MODULE_OPEN_NOT_CONFIRMED"
            if detail.startswith("MODULE_OPEN_NOT_CONFIRMED:")
            else "MODULE_NOT_FOUND"
        )
        detail = detail.removeprefix("MODULE_OPEN_NOT_CONFIRMED:")
        message = f"Timeout khi mở {module_name}: {detail}"
        _write_log(log, message)
        return _result(False, code, message, module=module_name)
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


def _mark_page_documents(
    page: Page,
    prefix: str,
) -> list[tuple[Frame | None, str]]:
    return [
        _mark_document(frame, f"{prefix}-{index}")
        for index, frame in enumerate(page.frames)
    ]


def _wait_for_module_navigation(
    browser: Any,
    page: Page,
    snapshots: list[tuple[Frame | None, str]],
    old_frame_ids: set[int],
    page_count: int,
    *,
    timeout_s: float = 20,
) -> bool:
    """Chỉ báo mở module khi WFX thật sự đổi page/frame/document."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if len(browser.contexts[0].pages) > page_count:
                return True
            current_frames = list(page.frames)
            current_frame_ids = {id(frame) for frame in current_frames}
            if any(id(frame) not in old_frame_ids for frame in current_frames):
                return True
            if any(
                snapshot[0] is not None
                and id(snapshot[0]) in current_frame_ids
                and _document_changed(snapshot[0], snapshot)
                for snapshot in snapshots
            ):
                return True
        except PlaywrightError:
            # Frame detach/navigation cũng là bằng chứng WFX đã nhận click.
            return True
        _wait(page, 150)
    return False


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
                        if (
                            time.monotonic() - filter_stable_since
                            < MODULE_FILTER_VISIBLE_STABLE_SECONDS
                        ):
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
        _wait(page, MODULE_GRID_POLL_MS)
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
        _wait(page, 200)
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


def _normalise_search_text(value: Any) -> str:
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in str(value or "").casefold()
        ).split()
    )


def _visible_search_input(
    frame: Frame,
    selectors: tuple[str, ...],
    aliases: tuple[str, ...],
) -> Any | None:
    normalised_aliases = tuple(_normalise_search_text(item) for item in aliases)
    for selector in selectors:
        try:
            candidates = frame.locator(selector)
            for index in range(candidates.count()):
                candidate = candidates.nth(index)
                if candidate.is_visible() and candidate.is_enabled():
                    return candidate
        except PlaywrightError:
            continue

    try:
        inputs = frame.locator("input")
        best: tuple[int, Any] | None = None
        for index in range(inputs.count()):
            candidate = inputs.nth(index)
            if not candidate.is_visible() or not candidate.is_enabled():
                continue
            metadata = candidate.evaluate(
                """element => {
                    const header = element.closest(
                        '.ag-header-cell, .tdSearch, th, td, label'
                    );
                    return [
                        element.id,
                        element.name,
                        element.getAttribute('aria-label'),
                        element.placeholder,
                        header?.getAttribute('col-id'),
                        header?.getAttribute('aria-label'),
                        header?.innerText
                    ].filter(Boolean).join(' ');
                }"""
            )
            normalised = _normalise_search_text(metadata)
            compact = normalised.replace(" ", "")
            score = max(
                (
                    len(alias)
                    for alias in normalised_aliases
                    if alias in normalised
                    or alias.replace(" ", "") in compact
                ),
                default=0,
            )
            if score and (best is None or score > best[0]):
                best = (score, candidate)
        return best[1] if best is not None else None
    except PlaywrightError:
        return None


def _search_input_in_frames(
    page: Page,
    selectors: tuple[str, ...],
    aliases: tuple[str, ...],
    timeout_s: float = 25,
) -> tuple[Frame, Any]:
    """Resolve đúng ô filter theo selector thật, rồi mới fallback theo header."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            candidate = _visible_search_input(frame, selectors, aliases)
            if candidate is not None:
                return frame, candidate
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        "Không tìm thấy ô search cho: " + ", ".join(aliases)
    )


def _search_input_in_frame(
    page: Page,
    frame: Frame,
    selectors: tuple[str, ...],
    aliases: tuple[str, ...],
    timeout_s: float = 4,
) -> Any:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        candidate = _visible_search_input(frame, selectors, aliases)
        if candidate is not None:
            return candidate
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        "Không tìm thấy ô search trong đúng màn List: "
        + ", ".join(aliases)
    )


def _apply_module_search(
    page: Page,
    field: Any,
    query: str,
    label: str,
    log: Callable[[str], None],
) -> None:
    # Floating Filter của một số màn (đặc biệt Sample) re-render input sau mỗi
    # keyup. `type()` có thể tiếp tục gõ vào locator đã detach và chỉ giữ một
    # phần giá trị; `fill()` phát input atomically rồi Enter/change kích search.
    field.fill(query)
    if field.input_value(timeout=1_000) != query:
        raise PlaywrightTimeoutError(
            f"WFX không xác nhận giá trị search {label}."
        )
    _write_log(log, f"[MODULE SEARCH] Đã nhập {label}: {query!r}")
    try:
        field.press("Enter", timeout=2_000)
    except PlaywrightError:
        pass
    try:
        field.dispatch_event("change")
    except PlaywrightError:
        pass

    deadline = time.monotonic() + 15
    stable_since = 0.0
    while time.monotonic() < deadline:
        loading = False
        for frame in page.frames:
            try:
                overlays = frame.locator(
                    ".ag-overlay-loading-wrapper, .ag-loading, "
                    ".loading, .loader, [aria-busy='true']"
                )
                if any(
                    overlays.nth(index).is_visible()
                    for index in range(overlays.count())
                ):
                    loading = True
                    break
            except PlaywrightError:
                continue
        if loading:
            stable_since = 0.0
        elif stable_since <= 0:
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= 0.8:
            return
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        f"Kết quả search {label} chưa ổn định."
    )


def _frame_with_visible_context(
    page: Page,
    context_selector: str,
    module_name: str | None = None,
    timeout_s: float = 4,
) -> Frame:
    """Chỉ nhận frame có marker riêng của đúng màn List đang mở."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                context = frame.locator(context_selector)
                if (
                    context.count()
                    and context.first.is_visible()
                    and _frame_matches_module_context(frame, module_name)
                ):
                    return frame
            except PlaywrightError:
                continue
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        f"Không tìm thấy context List: {context_selector}"
    )


def _frame_matches_module_context(
    frame: Frame,
    module_name: str | None,
) -> bool:
    """Phân biệt các màn dùng chung toàn bộ selector, nhất là hai Indent List."""
    if module_name not in {"Indent List", "User Indent"}:
        return True
    try:
        titles = frame.locator("title")
        title = (
            _normalise_search_text(titles.first.text_content(timeout=500))
            if titles.count()
            else ""
        )
    except PlaywrightError:
        return False
    if module_name == "User Indent":
        return "user indent" in title
    return "indent list" in title and "user indent" not in title


def _wait_module_search_settled(
    page: Page,
    labels: list[str],
) -> None:
    deadline = time.monotonic() + 15
    stable_since = 0.0
    while time.monotonic() < deadline:
        loading = False
        for frame in page.frames:
            try:
                overlays = frame.locator(
                    ".ag-overlay-loading-wrapper, .ag-loading, "
                    ".loading, .loader, [aria-busy='true']"
                )
                if any(
                    overlays.nth(index).is_visible()
                    for index in range(overlays.count())
                ):
                    loading = True
                    break
            except PlaywrightError:
                continue
        if loading:
            stable_since = 0.0
        elif stable_since <= 0:
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= 0.8:
            return
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        "Kết quả search chưa ổn định cho: " + ", ".join(labels)
    )


def _search_module_fields(
    module_name: str,
    xpath: str,
    values: dict[str, str],
    definitions: dict[str, tuple[str, str]],
    context_selector: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    """Xóa và điền một nhóm filter trong cùng frame để hỗ trợ lọc kết hợp."""
    cleaned = {
        key: str(values.get(key) or "").strip()
        for key in definitions
    }
    active = [key for key, value in cleaned.items() if value]
    if not active:
        labels = ", ".join(label for label, _selector in definitions.values())
        return _result(
            False,
            "QUERY_REQUIRED",
            f"Vui lòng nhập ít nhất một điều kiện: {labels}.",
        )

    playwright: Playwright | None = None
    search_started = False
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        try:
            frame = _frame_with_visible_context(
                page,
                context_selector,
                module_name=module_name,
                timeout_s=MODULE_CONTEXT_PROBE_SECONDS,
            )
        except PlaywrightTimeoutError:
            _write_log(
                log,
                f"[MODULE SEARCH] {module_name} chưa mở; "
                "đang tự mở List...",
            )
            _click_module_menu_on_page(page, module_name, xpath, log)
            frame = _frame_with_visible_context(
                page,
                context_selector,
                module_name=module_name,
                timeout_s=30,
            )

        fields: dict[str, Any] = {}
        for key, (label, selector) in definitions.items():
            field = frame.locator(selector)
            if (
                not field.count()
                or not field.first.is_visible()
                or not field.first.is_enabled()
            ):
                raise PlaywrightTimeoutError(
                    f"Không tìm thấy ô {label} trong đúng màn {module_name}."
                )
            fields[key] = field.first

        for field in fields.values():
            search_started = True
            field.fill("")
            try:
                field.dispatch_event("change")
            except PlaywrightError:
                pass

        last_field: Any | None = None
        active_labels: list[str] = []
        for key in active:
            label, _selector = definitions[key]
            field = fields[key]
            field.type(cleaned[key], delay=25)
            if field.input_value(timeout=1_000) != cleaned[key]:
                raise PlaywrightTimeoutError(
                    f"WFX không xác nhận giá trị search {label}."
                )
            active_labels.append(label)
            last_field = field
            _write_log(log, f"[MODULE SEARCH] Đã nhập {label}.")

        if last_field is not None:
            try:
                last_field.press("Enter", timeout=2_000)
            except PlaywrightError:
                pass
            try:
                last_field.dispatch_event("change")
            except PlaywrightError:
                pass
        _wait_module_search_settled(page, active_labels)
        return _result(
            True,
            "MODULE_SEARCH_APPLIED",
            f"Đã lọc {module_name} theo {', '.join(active_labels)}.",
            module=module_name,
            filter_kinds=active,
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
        detail = str(exc).splitlines()[0]
        if search_started:
            code = "MODULE_SEARCH_NOT_CONFIRMED"
            message = (
                f"Đã nhập filter trong {module_name}, nhưng WFX chưa xác nhận: "
                f"{detail}"
            )
        else:
            code = "MODULE_SEARCH_NOT_READY"
            message = (
                f"App đã tự mở {module_name}, nhưng các ô search chưa sẵn sàng: "
                f"{detail}"
            )
        _write_log(log, message)
        return _result(
            False,
            code,
            message,
            module=module_name,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        message = f"Không thể tìm trong {module_name}: {detail}"
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_FAILED",
            message,
            module=module_name,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def _search_module_list(
    module_name: str,
    xpath: str,
    query: str,
    label: str,
    selectors: tuple[str, ...],
    aliases: tuple[str, ...],
    context_selectors: tuple[str, ...],
    context_aliases: tuple[str, ...],
    module_field_selectors: tuple[str, ...],
    requires_floating_filter: bool,
    log: Callable[[str], None],
) -> dict[str, Any]:
    query = str(query or "").strip()
    if not query:
        return _result(
            False,
            "QUERY_REQUIRED",
            f"Vui lòng nhập {label} cần tìm.",
        )
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        try:
            frame, _context_field = _search_input_in_frames(
                page,
                context_selectors,
                context_aliases,
                timeout_s=MODULE_CONTEXT_PROBE_SECONDS,
            )
        except PlaywrightTimeoutError:
            _write_log(
                log,
                f"[MODULE SEARCH] {module_name} chưa sẵn sàng; "
                "đang tự mở List...",
            )
            previous_grids = (
                _mark_grid_roots(page) if requires_floating_filter else None
            )
            _click_module_menu_on_page(page, module_name, xpath, log)
            if requires_floating_filter:
                _show_module_floating_filter(
                    page,
                    log,
                    previous_grids,
                )
            frame, _context_field = _search_input_in_frames(
                page,
                context_selectors,
                context_aliases,
                timeout_s=30,
            )

        # OC/Sample/Sale chỉ chọn một kiểu filter mỗi lần. Xóa các filter còn
        # lại để lần tìm trước không âm thầm kết hợp với lần tìm hiện tại.
        for selector in dict.fromkeys(module_field_selectors):
            try:
                candidates = frame.locator(selector)
                for index in range(candidates.count()):
                    candidate = candidates.nth(index)
                    if (
                        candidate.is_visible()
                        and candidate.is_enabled()
                        and candidate.input_value(timeout=500)
                    ):
                        candidate.fill("")
                        try:
                            candidate.dispatch_event("change")
                        except PlaywrightError:
                            pass
            except PlaywrightError:
                continue
        _wait(page, 250)
        field = _search_input_in_frame(
            page,
            frame,
            selectors,
            aliases,
            timeout_s=8,
        )
        try:
            _apply_module_search(page, field, query, label, log)
        except PlaywrightTimeoutError as exc:
            detail = str(exc).splitlines()[0]
            message = (
                f"Đã nhập {label} trong {module_name}, nhưng WFX chưa "
                f"xác nhận kết quả: {detail}"
            )
            _write_log(log, message)
            return _result(
                False,
                "MODULE_SEARCH_NOT_CONFIRMED",
                message,
                module=module_name,
                filter_kind=label,
            )
        return _result(
            True,
            "MODULE_SEARCH_APPLIED",
            f"Đã tìm {module_name} theo {label}: {query}.",
            module=module_name,
            filter_kind=label,
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
        detail = str(exc).splitlines()[0]
        message = (
            f"App đã tự mở {module_name}, nhưng ô {label} chưa sẵn sàng: "
            f"{detail}"
        )
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_NOT_READY",
            message,
            module=module_name,
            filter_kind=label,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        message = (
            f"Không thể tìm theo {label} trong {module_name}: {detail}"
        )
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_FAILED",
            message,
            module=module_name,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def search_oc_list(
    xpath: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    definitions = {
        "oc_no": (
            "OC No.",
            ("#txtOCNO", 'input[name="txtOCNO"]'),
            ("oc no", "proforma invoice num with order ref num"),
        ),
        "style": (
            "Style",
            ("#txtArticle", 'input[name="txtArticle"]'),
            ("buyer style ref num", "style", "article"),
        ),
    }
    if filter_kind not in definitions:
        return _result(False, "INVALID_FILTER", "Kiểu tìm OC không hợp lệ.")
    label, selectors, aliases = definitions[filter_kind]
    return _search_module_list(
        "OC List",
        xpath,
        query,
        label,
        selectors,
        aliases,
        ("#txtOCNO", 'input[name="txtOCNO"]'),
        ("proforma invoice num with order ref num", "oc no"),
        tuple(
            selector
            for _label, selectors, _aliases in definitions.values()
            for selector in selectors
        ),
        False,
        log,
    )


def search_sample_list(
    xpath: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    definitions = {
        "sample_no": (
            "Sample Order No.",
            (
                "#txtSampleOrderNo",
                "#txtSampleNo",
                'input[aria-label*="Sample Order" i]',
                'input[id*="SampleOrder" i]',
            ),
            ("sample order no", "sample order number", "sample no"),
        ),
        "style": (
            "Style",
            (
                "#txtArticle",
                'input[aria-label*="Style" i]',
                'input[id*="Style" i]',
                'input[id*="Article" i]',
            ),
            ("buyer style", "style", "article"),
        ),
        "created_by": (
            "Created By",
            (
                'input[aria-label*="Created By" i]',
                'input[id*="CreatedBy" i]',
                'input[name*="CreatedBy" i]',
            ),
            ("created by", "createdby", "creator"),
        ),
    }
    if filter_kind not in definitions:
        return _result(False, "INVALID_FILTER", "Kiểu tìm Sample không hợp lệ.")
    label, selectors, aliases = definitions[filter_kind]
    return _search_module_list(
        "Sample List",
        xpath,
        query,
        label,
        selectors,
        aliases,
        (
            "#txtSampleOrderNo",
            "#txtSampleNo",
            'input[aria-label*="Sample Order" i]',
            'input[id*="SampleOrder" i]',
        ),
        ("sample order no", "sample order number", "sample no"),
        tuple(
            selector
            for _label, selectors, _aliases in definitions.values()
            for selector in selectors
        ),
        True,
        log,
    )


def search_sale_asn_list(
    xpath: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    definitions = {
        "invoice_no": (
            "Invoice No.",
            (
                "#txtInvoiceNo",
                'input[aria-label*="Invoice" i]',
                'input[id*="Invoice" i]',
            ),
            ("invoice no", "invoice number", "invoice"),
        ),
        "buyer_order_ref": (
            "Buyer Order Ref/OC No.",
            (
                'input[aria-label*="Buyer Order Ref/Oc Num" i]',
                'input[aria-label*="Buyer Order Ref" i]',
            ),
            (
                "buyer order ref oc num",
                "buyer order ref",
                "oc num",
            ),
        ),
    }
    # Tương thích job cũ trước khi UI đổi tên filter không tồn tại "Style".
    definitions["style"] = definitions["buyer_order_ref"]
    if filter_kind not in definitions:
        return _result(False, "INVALID_FILTER", "Kiểu tìm Sale ASN không hợp lệ.")
    label, selectors, aliases = definitions[filter_kind]
    return _search_module_list(
        "Sale ASN",
        xpath,
        query,
        label,
        selectors,
        aliases,
        (
            "#txtInvoiceNo",
            'input[aria-label*="Invoice" i]',
            'input[id*="Invoice" i]',
        ),
        ("invoice no", "invoice number", "invoice"),
        tuple(
            selector
            for _label, selectors, _aliases in definitions.values()
            for selector in selectors
        ),
        True,
        log,
    )


def search_rmpo_list(
    xpath: str,
    supplier: str,
    order_no: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_fields(
        "RMPO List",
        xpath,
        {
            "supplier": supplier,
            "order_no": order_no,
        },
        {
            "supplier": (
                "Supplier",
                "#gridRMPO_tblGridHeader_trSearch_td_colSupplier "
                "input#txtSupplier",
            ),
            "order_no": (
                "RMPO No.",
                "#gridRMPO_tblGridHeader_trSearch_td_colOrderNo "
                "input#txtOrderNo",
            ),
        },
        "#gridRMPO_tblGridHeader_trSearch_td_colSupplier",
        log,
    )


def search_indent_list(
    xpath: str,
    module_name: str,
    supplier: str,
    article: str,
    indent_no: str,
    style: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    if module_name not in {"Indent List", "User Indent"}:
        return _result(
            False,
            "INVALID_FILTER",
            "Module Indent không hợp lệ.",
        )
    return _search_module_fields(
        module_name,
        xpath,
        {
            "supplier": supplier,
            "article": article,
            "indent_no": indent_no,
            "style": style,
        },
        {
            "supplier": (
                "Supplier",
                "#gridMOLList_tblGridHeader_trSearch_td_ColSupplier "
                "input#txtSupplier",
            ),
            "article": (
                "Article",
                "#gridMOLList_tblGridHeader_trSearch_td_ColArticle "
                "input#txtArticle",
            ),
            "indent_no": (
                "Indent No.",
                "#gridMOLList_tblGridHeader_trSearch_td_ColIndentNo "
                "input#txtIndentNo",
            ),
            "style": (
                "Style",
                "#gridMOLList_tblGridHeader_trSearch_td_ColStyle "
                "input#txtStyle",
            ),
        },
        "#gridMOLList_tblGridHeader_trSearch_td_ColIndentNo",
        log,
    )


def open_module_new(
    module_id: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    definitions = {
        "0063_0030_0020": (
            "QA List",
            "div.clsPageTitleBarToolNew"
            "[onclick*=\"titlebarQARequestList\"]",
        ),
        "0065_0880_0010_0020": (
            "Advance PR List",
            "div.clsPageTitleBarToolNew"
            "[onclick*=\"titlebarAdvancePaymentRequestList\"], "
            "a[href*=\"MenuName=mnuAdvancePaymentRequestNew\"]"
            "[href*=\"WFXAdvancePaymentRequest.aspx?ARAPType=APR\"]",
        ),
        "0065_0880_0030_0020": (
            "Expense Inv List",
            "div.clsPageTitleBarToolNew"
            "[onclick*=\"titlebarExpenseInvoiceList\"], "
            "a[href*=\"MenuName=mnuExpenseInvoiceNew\"]"
            "[href*=\"WFXExpenseInvoice.aspx?InvoiceType=Expense\"]",
        ),
    }
    if module_id not in definitions:
        return _result(
            False,
            "INVALID_FILTER",
            "Module này không hỗ trợ thao tác New.",
        )
    module_name, selector = definitions[module_id]
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        try:
            frame = _frame_with_visible_context(page, selector, timeout_s=4)
            target = frame.locator(selector).first
        except PlaywrightTimeoutError:
            message = (
                f"Chưa thấy nút New trong {module_name}. "
                "Hãy bấm List trước và chờ màn danh sách hiển thị."
            )
            _write_log(log, message)
            return _result(
                False,
                "MODULE_LIST_NOT_OPEN",
                message,
                module=module_name,
            )

        snapshots = [
            _mark_document(candidate, f"module-new-{index}")
            for index, candidate in enumerate(page.frames)
        ]
        old_frames = {snapshot[0] for snapshot in snapshots}
        page_count = len(browser.contexts[0].pages)
        _write_log(log, f"[MODULE NEW] Đang mở New từ {module_name}.")
        _click_navigation_control(target)

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if len(browser.contexts[0].pages) > page_count:
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
        return _result(
            True,
            "MODULE_NEW_READY",
            f"Đã mở New từ {module_name}.",
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
    except Exception as exc:
        detail = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
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
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Chrome automation chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message)
    except PlaywrightTimeoutError as exc:
        message = f"Sample New chưa sẵn sàng: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "SAMPLE_NEW_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "SAMPLE_NEW_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def toggle_company_foc(
    _xpath: str,
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

        try:
            _misc_frame, misc = _visible_locator_in_frames(
                page,
                misc_selector,
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
                    misc_selector,
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
        # Từ lúc click Save đến khi xác nhận response/document là critical
        # section: Stop được ghi nhận nhưng chỉ áp dụng sau bước lưu an toàn.
        with cancellation_deferred():
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
                _wait(page, 250)

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
