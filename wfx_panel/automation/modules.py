"""Mở module WFX tổng quát + floating filter dùng chung + Sale ASN.

Tách nguyên văn từ login.py — không đổi logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

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
    _first_line,
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
from wfx_panel.automation.search_specs import (
    INDENT_SEARCH_SPECS,
    OC_SEARCH_SPEC,
    RMPO_SEARCH_SPEC,
    SALE_ASN_SEARCH_SPEC,
    SAMPLE_SEARCH_SPEC,
    ModuleSearchSpec,
)

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
        detail = _first_line(exc)
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


@dataclass
class _FloatingFilterState:
    last_click: float = 0.0
    last_error: Exception | None = None
    stable_key: tuple[Any, ...] | None = None
    stable_since: float = 0.0
    settled_key: tuple[Any, ...] | None = None
    filter_stable_since: float = 0.0
    last_grid_state: dict[str, Any] | None = None


def _module_grid_settled(
    frame: Frame,
    last_state: Mapping[str, Any],
    state: _FloatingFilterState,
) -> bool:
    state_key = (
        frame.url,
        last_state["loading"],
        last_state["noRows"],
        last_state["renderedRows"],
    )
    ready = not last_state["loading"] and (
        last_state["renderedRows"] > 0 or last_state["noRows"]
    )
    now = time.monotonic()
    if ready and state_key == state.stable_key:
        settled = now - state.stable_since >= 0.75
    else:
        state.stable_key = state_key
        state.stable_since = now
        settled = False
    if settled and state.settled_key != state_key:
        state.settled_key = state_key
    return settled


def _floating_filter_input_ready(
    root: Any,
    last_state: Mapping[str, Any],
    state: _FloatingFilterState,
    log: Callable[[str], None],
) -> bool:
    if not last_state["filterVisible"]:
        state.filter_stable_since = 0.0
        return False
    now = time.monotonic()
    if state.filter_stable_since <= 0:
        state.filter_stable_since = now
    if now - state.filter_stable_since < MODULE_FILTER_VISIBLE_STABLE_SECONDS:
        return False
    inputs = root.locator(
        ".ag-floating-filter input, .ag-header-row-column-filter input"
    )
    visible_input = _first_visible(inputs)
    if visible_input is None or not visible_input.is_enabled():
        return False
    value = visible_input.input_value(timeout=500)
    _write_log(
        log,
        "[FLOATING FILTER] Hàng filter đã hiển thị; "
        f"inputs={last_state['filterInputCount']}; "
        f"headerHeight={last_state['headerHeight']}; "
        f"filterRowHeight={last_state['filterRowHeight']}; "
        f"value={value!r}.",
    )
    return True


def _click_floating_filter_if_due(
    frame: Frame,
    state: _FloatingFilterState,
    log: Callable[[str], None],
) -> None:
    button = _first_visible(frame.locator("#showfloatingfilter"))
    now = time.monotonic()
    if button is None or now - state.last_click < 1.5:
        return
    state.last_click = now
    _write_log(log, "[FLOATING FILTER] Đang click #showfloatingfilter...")
    # WFX binds the handler to a DIV; DOM click survives header relayout.
    button.evaluate("element => element.click()")


def _show_module_floating_filter(
    page: Page,
    log: Callable[[str], None],
    previous_grids: list[tuple[Frame, str]] | None = None,
    timeout_s: float = 40,
) -> Frame:
    """Chờ grid mới ổn định, bật filter và xác nhận hàng filter thật sự mở."""
    deadline = time.monotonic() + timeout_s
    state = _FloatingFilterState()
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
                    grid_state = root.evaluate(_MODULE_GRID_STATE_JS)
                    state.last_grid_state = grid_state
                    previous_settled_key = state.settled_key
                    if not _module_grid_settled(frame, grid_state, state):
                        continue
                    if previous_settled_key != state.settled_key:
                        _write_log(
                            log,
                            "[FLOATING FILTER] Grid đã ổn định; "
                            f"loading={grid_state['loading']}; "
                            f"noRows={grid_state['noRows']}; "
                            f"renderedRows={grid_state['renderedRows']}.",
                        )
                    if _floating_filter_input_ready(root, grid_state, state, log):
                        return frame
                    _click_floating_filter_if_due(frame, state, log)
            except (PlaywrightError, PlaywrightTimeoutError) as exc:
                state.last_error = exc
        _wait(page, MODULE_GRID_POLL_MS)
    raise PlaywrightTimeoutError(
        "Show Floating Filter chưa sẵn sàng; "
        f"gridState={state.last_grid_state or {}}; "
        f"lastError={state.last_error}"
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
        message = f"Timeout khi mở {module_name}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "FLOATING_FILTER_NOT_READY", message, module=module_name)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
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
        message = f"Sale ASN New chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SALE_ASN_NEW_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
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


def _module_search_is_loading(page: Page) -> bool:
    overlay_selector = (
        ".ag-overlay-loading-wrapper, .ag-loading, "
        ".loading, .loader, [aria-busy='true']"
    )
    for frame in page.frames:
        try:
            overlays = frame.locator(overlay_selector)
            if any(
                overlays.nth(index).is_visible()
                for index in range(overlays.count())
            ):
                return True
        except PlaywrightError:
            continue
    return False


def _wait_module_search_stable(
    page: Page,
    label: str,
) -> None:
    deadline = time.monotonic() + 15
    stable_since = 0.0
    while time.monotonic() < deadline:
        if _module_search_is_loading(page):
            stable_since = 0.0
        elif stable_since <= 0:
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= 0.8:
            return
        _wait(page, 200)
    raise PlaywrightTimeoutError(f"Kết quả search {label} chưa ổn định.")


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
    _wait_module_search_stable(page, label)


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


def _open_multi_field_search_context(
    page: Page,
    search_spec: ModuleSearchSpec,
    xpath: str,
    log: Callable[[str], None],
) -> Frame:
    context_selector = ", ".join(search_spec.context_field.selectors)
    try:
        return _frame_with_visible_context(
            page,
            context_selector,
            module_name=search_spec.module_name,
            timeout_s=MODULE_CONTEXT_PROBE_SECONDS,
        )
    except PlaywrightTimeoutError:
        _write_log(
            log,
            f"[MODULE SEARCH] {search_spec.module_name} chưa mở; "
            "đang tự mở List...",
        )
        _click_module_menu_on_page(page, search_spec.module_name, xpath, log)
        return _frame_with_visible_context(
            page,
            context_selector,
            module_name=search_spec.module_name,
            timeout_s=30,
        )


def _resolve_multi_search_fields(
    frame: Frame,
    search_spec: ModuleSearchSpec,
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for field_name, field_spec in search_spec.fields.items():
        candidates = frame.locator(", ".join(field_spec.selectors))
        if (
            not candidates.count()
            or not candidates.first.is_visible()
            or not candidates.first.is_enabled()
        ):
            raise PlaywrightTimeoutError(
                f"Không tìm thấy ô {field_spec.label} trong đúng màn "
                f"{search_spec.module_name}."
            )
        resolved[field_name] = candidates.first
    return resolved


def _clear_multi_search_fields(fields: Mapping[str, Any]) -> None:
    for search_field in fields.values():
        search_field.fill("")
        try:
            search_field.dispatch_event("change")
        except PlaywrightError:
            pass


def _fill_multi_search_fields(
    fields: Mapping[str, Any],
    cleaned_values: Mapping[str, str],
    active_fields: list[str],
    search_spec: ModuleSearchSpec,
    log: Callable[[str], None],
) -> tuple[list[str], Any | None]:
    active_labels: list[str] = []
    last_field: Any | None = None
    for field_name in active_fields:
        field_spec = search_spec.fields[field_name]
        search_field = fields[field_name]
        search_field.type(cleaned_values[field_name], delay=25)
        if search_field.input_value(timeout=1_000) != cleaned_values[field_name]:
            raise PlaywrightTimeoutError(
                f"WFX không xác nhận giá trị search {field_spec.label}."
            )
        active_labels.append(field_spec.label)
        last_field = search_field
        _write_log(log, f"[MODULE SEARCH] Đã nhập {field_spec.label}.")
    return active_labels, last_field


def _submit_multi_search(last_field: Any | None) -> None:
    if last_field is None:
        return
    try:
        last_field.press("Enter", timeout=2_000)
    except PlaywrightError:
        pass
    try:
        last_field.dispatch_event("change")
    except PlaywrightError:
        pass


def _search_module_fields(
    search_spec: ModuleSearchSpec,
    xpath: str,
    values: dict[str, str],
    log: Callable[[str], None],
) -> dict[str, Any]:
    """Xóa và điền một nhóm filter trong cùng frame để hỗ trợ lọc kết hợp."""
    cleaned = {
        key: str(values.get(key) or "").strip()
        for key in search_spec.fields
    }
    active = [key for key, value in cleaned.items() if value]
    if not active:
        labels = ", ".join(
            field_spec.label for field_spec in search_spec.fields.values()
        )
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
        frame = _open_multi_field_search_context(
            page,
            search_spec,
            xpath,
            log,
        )
        fields = _resolve_multi_search_fields(frame, search_spec)
        search_started = True
        _clear_multi_search_fields(fields)
        active_labels, last_field = _fill_multi_search_fields(
            fields,
            cleaned,
            active,
            search_spec,
            log,
        )
        _submit_multi_search(last_field)
        _wait_module_search_settled(page, active_labels)
        return _result(
            True,
            "MODULE_SEARCH_APPLIED",
            f"Đã lọc {search_spec.module_name} theo "
            f"{', '.join(active_labels)}.",
            module=search_spec.module_name,
            filter_kinds=active,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Chrome automation chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module=search_spec.module_name)
    except PlaywrightTimeoutError as exc:
        detail = _first_line(exc)
        if search_started:
            code = "MODULE_SEARCH_NOT_CONFIRMED"
            message = (
                f"Đã nhập filter trong {search_spec.module_name}, nhưng WFX "
                "chưa xác nhận: "
                f"{detail}"
            )
        else:
            code = "MODULE_SEARCH_NOT_READY"
            message = (
                f"App đã tự mở {search_spec.module_name}, nhưng các ô search "
                "chưa sẵn sàng: "
                f"{detail}"
            )
        _write_log(log, message)
        return _result(
            False,
            code,
            message,
            module=search_spec.module_name,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {_first_line(exc)}"
        message = f"Không thể tìm trong {search_spec.module_name}: {detail}"
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_FAILED",
            message,
            module=search_spec.module_name,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def _open_list_search_context(
    page: Page,
    search_spec: ModuleSearchSpec,
    xpath: str,
    log: Callable[[str], None],
) -> Frame:
    try:
        frame, _context_field = _search_input_in_frames(
            page,
            search_spec.context_field.selectors,
            search_spec.context_field.aliases,
            timeout_s=MODULE_CONTEXT_PROBE_SECONDS,
        )
        return frame
    except PlaywrightTimeoutError:
        _write_log(
            log,
            f"[MODULE SEARCH] {search_spec.module_name} chưa sẵn sàng; "
            "đang tự mở List...",
        )
        previous_grids = (
            _mark_grid_roots(page)
            if search_spec.requires_floating_filter
            else None
        )
        _click_module_menu_on_page(page, search_spec.module_name, xpath, log)
        if search_spec.requires_floating_filter:
            _show_module_floating_filter(page, log, previous_grids)
        frame, _context_field = _search_input_in_frames(
            page,
            search_spec.context_field.selectors,
            search_spec.context_field.aliases,
            timeout_s=30,
        )
        return frame


def _clear_list_search_fields(
    frame: Frame,
    selectors: tuple[str, ...],
) -> None:
    """Xóa filter cũ để các lần Search không âm thầm kết hợp điều kiện."""
    # Một locator union trả node unique theo DOM order, tránh query lại cùng
    # input khi nhiều selector fallback cùng match nó.
    candidates = frame.locator(", ".join(selectors))
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        try:
            if not candidate.is_visible() or not candidate.is_enabled():
                continue
            if not candidate.input_value(timeout=500):
                continue
            candidate.fill("")
            try:
                candidate.dispatch_event("change")
            except PlaywrightError:
                pass
        except PlaywrightError:
            continue


def _search_module_list(
    search_spec: ModuleSearchSpec,
    xpath: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    selected_field = search_spec.fields.get(filter_kind)
    if selected_field is None:
        return _result(
            False,
            "INVALID_FILTER",
            f"Kiểu tìm {search_spec.module_name} không hợp lệ.",
        )
    query = str(query or "").strip()
    if not query:
        return _result(
            False,
            "QUERY_REQUIRED",
            f"Vui lòng nhập {selected_field.label} cần tìm.",
        )
    playwright: Playwright | None = None
    search_started = False
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_list_search_context(page, search_spec, xpath, log)
        _clear_list_search_fields(frame, search_spec.field_selectors)
        _wait(page, 250)
        field = _search_input_in_frame(
            page,
            frame,
            selected_field.selectors,
            selected_field.aliases,
            timeout_s=8,
        )
        search_started = True
        _apply_module_search(
            page,
            field,
            query,
            selected_field.label,
            log,
        )
        return _result(
            True,
            "MODULE_SEARCH_APPLIED",
            f"Đã tìm {search_spec.module_name} theo "
            f"{selected_field.label}: {query}.",
            module=search_spec.module_name,
            filter_kind=selected_field.label,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Chrome automation chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module=search_spec.module_name)
    except PlaywrightTimeoutError as exc:
        detail = _first_line(exc)
        if search_started:
            code = "MODULE_SEARCH_NOT_CONFIRMED"
            message = (
                f"Đã nhập {selected_field.label} trong "
                f"{search_spec.module_name}, nhưng WFX chưa xác nhận kết quả: "
                f"{detail}"
            )
        else:
            code = "MODULE_SEARCH_NOT_READY"
            message = (
                f"App đã tự mở {search_spec.module_name}, nhưng ô "
                f"{selected_field.label} chưa sẵn sàng: {detail}"
            )
        _write_log(log, message)
        return _result(
            False,
            code,
            message,
            module=search_spec.module_name,
            filter_kind=selected_field.label,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {_first_line(exc)}"
        message = (
            f"Không thể tìm theo {selected_field.label} trong "
            f"{search_spec.module_name}: {detail}"
        )
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_FAILED",
            message,
            module=search_spec.module_name,
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
    return _search_module_list(
        OC_SEARCH_SPEC,
        xpath,
        filter_kind,
        query,
        log,
    )


def search_sample_list(
    xpath: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_list(
        SAMPLE_SEARCH_SPEC,
        xpath,
        filter_kind,
        query,
        log,
    )


def search_sale_asn_list(
    xpath: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_list(
        SALE_ASN_SEARCH_SPEC,
        xpath,
        filter_kind,
        query,
        log,
    )


def search_rmpo_list(
    xpath: str,
    supplier: str,
    order_no: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_fields(
        RMPO_SEARCH_SPEC,
        xpath,
        {
            "supplier": supplier,
            "order_no": order_no,
        },
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
    search_spec = INDENT_SEARCH_SPECS.get(module_name)
    if search_spec is None:
        return _result(
            False,
            "INVALID_FILTER",
            "Module Indent không hợp lệ.",
        )
    return _search_module_fields(
        search_spec,
        xpath,
        {
            "supplier": supplier,
            "article": article,
            "indent_no": indent_no,
            "style": style,
        },
        log,
    )


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
        ),
        "0065_0880_0010_0020": (
            "Advance Payment Request",
            '//a[@title="New" '
            'and contains(@href,"MenuName=mnuAdvancePaymentRequestNew") '
            'and contains(@href,"WFXAdvancePaymentRequest.aspx?ARAPType=APR")]',
        ),
        "0065_0880_0030_0020": (
            "Expense Invoice",
            '//*[@id="0065_0880_0030_0010"]/a',
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
        snapshots = [
            _mark_document(candidate, f"module-new-{index}")
            for index, candidate in enumerate(page.frames)
        ]
        old_frames = {snapshot[0] for snapshot in snapshots}
        page_count = len(browser.contexts[0].pages)
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
            f"Đã mở trực tiếp {module_name} New.",
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
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Chrome automation chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message)
    except PlaywrightTimeoutError as exc:
        message = f"Sample New chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SAMPLE_NEW_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SAMPLE_NEW_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


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
            f"{_first_line(exc)}"
        )
        _write_log(log, message)
        return _result(False, "COMPANY_FOC_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "COMPANY_FOC_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
