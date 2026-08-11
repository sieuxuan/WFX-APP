"""Mở module WFX tổng quát + floating filter dùng chung + Sale ASN.

Tách nguyên văn từ login.py — không đổi logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

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
    _horizontal_grid_positions,
    _horizontal_grid_state,
    _mark_document,
    _result,
    _scroll_horizontal_grid,
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
    ADVANCE_PR_SEARCH_SPEC,
    EXPENSE_INVOICE_SEARCH_SPEC,
    INDENT_SEARCH_SPECS,
    OC_SEARCH_SPEC,
    RMPO_SEARCH_SPEC,
    SALE_ASN_SEARCH_SPEC,
    SAMPLE_SEARCH_SPEC,
    SUPPLIER_INVOICE_SEARCH_SPEC,
    ModuleSearchSpec,
)

MODULE_GRID_POLL_MS = 150
MODULE_FILTER_VISIBLE_STABLE_SECONDS = 0.5
_MODULE_LOADING_SELECTOR = (
    ".ag-overlay-loading-wrapper, .ag-loading, .blockUI, .blockOverlay, "
    ".ui-widget-overlay, .loading, .loader, [aria-busy='true'], "
    "[id*='loading' i], [id*='progress' i], "
    "[class*='loading' i], [class*='progress' i]"
)
MODULE_CONTEXT_PROBE_SECONDS = 0.75
MODULE_DIRECT_ROUTE_TIMEOUT_MS = 12_000
_MENU_ROUTE_CACHE: dict[str, tuple[str, str]] = {}


def reset_menu_route_cache() -> None:
    """Xóa route chỉ sống trong phiên khi login/Division thay đổi."""
    _MENU_ROUTE_CACHE.clear()


def _same_origin(page_url: str, target_url: str) -> bool:
    try:
        current = urlsplit(page_url)
        target = urlsplit(target_url)
    except ValueError:
        return False
    return bool(
        current.scheme in {"http", "https"}
        and target.scheme == current.scheme
        and target.hostname
        and target.hostname == current.hostname
        and target.port == current.port
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
            return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")

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
            target_href = str(
                target.evaluate("element => element.href || ''") or ""
            )
            target_frame_name = str(target.get_attribute("target") or "")
            cache_hit = False
            cached_route = _MENU_ROUTE_CACHE.get(module_name)
            if cached_route is not None:
                cached_href, cached_target = cached_route
                cache_hit = _open_menu_href_in_target_frame(
                    page,
                    cached_href,
                    cached_target,
                )
                if cache_hit:
                    _write_log(
                        log,
                        f"[MODULE] Dùng route cache để mở {module_name} "
                        "trực tiếp, bỏ qua thời gian chờ menu không phản hồi.",
                    )
                else:
                    _MENU_ROUTE_CACHE.pop(module_name, None)

            confirmed = cache_hit
            if not confirmed:
                _click(target)
                confirmed = _wait_for_module_navigation(
                    browser,
                    page,
                    snapshots,
                    old_frame_ids,
                    page_count,
                    timeout_s=5,
                )
            if not confirmed:
                _write_log(
                    log,
                    "[MODULE] Menu chưa phản hồi sau 5 giây; "
                    "đang thử route trực tiếp...",
                )
            if not confirmed and _open_menu_href_in_target_frame(
                page, target_href, target_frame_name
            ):
                confirmed = True
                if _same_origin(page.url, target_href):
                    _MENU_ROUTE_CACHE[module_name] = (
                        target_href,
                        target_frame_name,
                    )
                _write_log(
                    log,
                    "[MODULE] Menu không phản hồi click; "
                    f"đã mở {module_name} trực tiếp trong frame "
                    f"{target_frame_name}.",
                )
            if not confirmed:
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
            menu_cache_hit=(cache_hit if module_name != "Catalog" else False),
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


def _open_menu_href_in_target_frame(
    page: Page,
    href: str,
    target_name: str,
) -> bool:
    """Fallback cho menu WFX có target=body nhưng click không navigation."""
    page_url = str(getattr(page, "url", "") or "")
    if (
        not href.lower().startswith(("http://", "https://"))
        or not target_name
        or (page_url and not _same_origin(page_url, href))
    ):
        return False
    target_frame = next(
        (frame for frame in page.frames if frame.name == target_name),
        None,
    )
    if target_frame is None:
        return False
    try:
        target_frame.goto(
            href,
            wait_until="domcontentloaded",
            timeout=MODULE_DIRECT_ROUTE_TIMEOUT_MS,
        )
    except PlaywrightError:
        return False
    return True


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
    module_name: str | None = None,
) -> Frame:
    """Chờ grid mới ổn định, bật filter và xác nhận hàng filter thật sự mở."""
    deadline = time.monotonic() + timeout_s
    state = _FloatingFilterState()
    while time.monotonic() < deadline:
        for frame in page.frames:
            if not _frame_matches_module_context(frame, module_name):
                continue
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
        _show_module_floating_filter(
            page,
            log,
            previous_grids,
            module_name=module_name,
        )
        return _result(
            True,
            "MODULE_FILTER_READY",
            f"Đã mở {module_name} và bật Floating Filter.",
            module=module_name,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
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
            "Trình duyệt làm việc chưa được mở."
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
    *,
    scan_horizontal: bool = False,
    module_name: str | None = None,
) -> tuple[Frame, Any]:
    """Resolve đúng ô filter theo selector thật, rồi mới fallback theo header."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            if not _frame_matches_module_context(frame, module_name):
                continue
            candidate = _visible_search_input(frame, selectors, aliases)
            if candidate is not None:
                return frame, candidate
        if scan_horizontal:
            for frame in page.frames:
                if not _frame_matches_module_context(frame, module_name):
                    continue
                candidate = _search_input_across_horizontal_grid(
                    frame,
                    selectors,
                    aliases,
                )
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
    *,
    scan_horizontal: bool = False,
) -> Any:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        candidate = _visible_search_input(frame, selectors, aliases)
        if candidate is not None:
            return candidate
        if scan_horizontal:
            candidate = _search_input_across_horizontal_grid(
                frame,
                selectors,
                aliases,
            )
            if candidate is not None:
                return candidate
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        "Không tìm thấy ô search trong đúng màn List: "
        + ", ".join(aliases)
    )


def _search_input_across_horizontal_grid(
    frame: Frame,
    selectors: tuple[str, ...],
    aliases: tuple[str, ...],
) -> Any | None:
    """Tìm Floating Filter bị AG Grid virtualize ngoài viewport ngang."""
    roots = frame.locator(".ag-root-wrapper")
    for index in range(roots.count()):
        root = roots.nth(index)
        try:
            if not root.is_visible():
                continue
            state = _horizontal_grid_state(root)
            original = max(0, int(float(state.get("current") or 0)))
            for position in _horizontal_grid_positions(state):
                _scroll_horizontal_grid(root, position)
                _wait(frame, MODULE_GRID_POLL_MS)
                candidate = _visible_search_input(
                    frame,
                    selectors,
                    aliases,
                )
                if candidate is not None:
                    # Giữ cột vừa tìm thấy trong viewport để user thấy đúng
                    # filter và kết quả đang được áp dụng.
                    return candidate
            _scroll_horizontal_grid(root, original)
        except PlaywrightError:
            continue
    return None


def _module_search_is_loading(page: Page) -> bool:
    for frame in page.frames:
        try:
            overlays = frame.locator(_MODULE_LOADING_SELECTOR)
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
    _write_log(log, f"[MODULE SEARCH] Đã nhập {label}.")
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
    if module_name == "Sale ASN":
        # Invoice input xuất hiện ở nhiều module WFX. Chỉ URL Sale ASN chưa đủ
        # vì form New cũng dùng cùng họ URL; List phải có AG Grid đang hiển thị.
        try:
            if "salesasn" not in str(frame.url or "").casefold():
                return False
            roots = frame.locator(".ag-root-wrapper")
            return any(
                roots.nth(index).is_visible()
                for index in range(roots.count())
            )
        except PlaywrightError:
            return False
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
    deadline = time.monotonic() + 30
    stable_since = 0.0
    while time.monotonic() < deadline:
        loading = False
        for frame in page.frames:
            try:
                overlays = frame.locator(_MODULE_LOADING_SELECTOR)
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
        tag_name = str(
            search_field.evaluate("element => element.tagName") or ""
        ).upper()
        if tag_name == "SELECT":
            try:
                search_field.select_option(value="")
            except PlaywrightError:
                search_field.select_option(index=0)
        else:
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
        value = cleaned_values[field_name]
        tag_name = str(
            search_field.evaluate("element => element.tagName") or ""
        ).upper()
        if tag_name == "SELECT":
            try:
                search_field.select_option(value=value)
            except PlaywrightError:
                search_field.select_option(label=value)
            selected_text = str(
                search_field.evaluate(
                    "element => element.selectedOptions?.[0]?.textContent || ''"
                )
                or ""
            ).strip()
            value_confirmed = (
                search_field.input_value(timeout=1_000) == value
                or selected_text.casefold() == value.casefold()
            )
        else:
            search_field.type(value, delay=25)
            value_confirmed = (
                search_field.input_value(timeout=1_000) == value
            )
        if not value_confirmed:
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
            "Trình duyệt làm việc chưa được mở."
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
            scan_horizontal=search_spec.requires_floating_filter,
            module_name=search_spec.module_name,
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
            _show_module_floating_filter(
                page,
                log,
                previous_grids,
                module_name=search_spec.module_name,
            )
        frame, _context_field = _search_input_in_frames(
            page,
            search_spec.context_field.selectors,
            search_spec.context_field.aliases,
            timeout_s=30,
            scan_horizontal=search_spec.requires_floating_filter,
            module_name=search_spec.module_name,
        )
        return frame


def _clear_list_search_fields(
    frame: Frame,
    selectors: tuple[str, ...],
    *,
    scan_horizontal: bool = False,
) -> None:
    """Xóa filter cũ để các lần Search không âm thầm kết hợp điều kiện."""
    def clear_visible() -> None:
        # Một locator union trả node unique theo DOM order, tránh query lại
        # cùng input khi nhiều selector fallback cùng match nó.
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

    clear_visible()
    if not scan_horizontal:
        return
    roots = frame.locator(".ag-root-wrapper")
    for index in range(roots.count()):
        root = roots.nth(index)
        try:
            if not root.is_visible():
                continue
            state = _horizontal_grid_state(root)
            original = max(0, int(float(state.get("current") or 0)))
            for position in _horizontal_grid_positions(state):
                _scroll_horizontal_grid(root, position)
                _wait(frame, MODULE_GRID_POLL_MS)
                clear_visible()
            _scroll_horizontal_grid(root, original)
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
        _clear_list_search_fields(
            frame,
            search_spec.field_selectors,
            scan_horizontal=search_spec.requires_floating_filter,
        )
        _wait(page, 250)
        field = _search_input_in_frame(
            page,
            frame,
            selected_field.selectors,
            selected_field.aliases,
            timeout_s=8,
            scan_horizontal=search_spec.requires_floating_filter,
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
            "Trình duyệt làm việc chưa được mở."
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


_SAMPLE_RESULT_ROWS_JS = """root => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none'
            && style.visibility !== 'hidden'
            && Number(style.opacity || 1) !== 0
            && rect.width > 0 && rect.height > 0;
    };
    const directText = element => String(
        element?.value
        || element?.getAttribute?.('value')
        || element?.textContent
        || element?.title
        || element?.getAttribute?.('aria-label')
        || ''
    ).replace(/\\s+/g, ' ').trim();
    const text = element => {
        if (!element) return '';
        const direct = directText(element);
        if (direct) return direct;
        const nested = element.querySelector?.(
            'input[value], button, a, [title], [aria-label]'
        );
        return directText(nested);
    };
    const cellMetadata = cell => {
        if (!cell) return '';
        const colId = cell.getAttribute('col-id') || '';
        const escaped = window.CSS?.escape ? CSS.escape(colId) : colId;
        const header = colId
            ? root.querySelector(`.ag-header-cell[col-id="${escaped}"]`)
            : null;
        return [
            colId,
            cell.getAttribute('aria-label') || '',
            header?.getAttribute('aria-label') || '',
            header?.textContent || '',
        ].join(' ').toLowerCase();
    };
    const styleAction = row => {
        const candidates = [...row.querySelectorAll(
            'input[type="button"], button, a, [onclick]'
        )].filter(shown);
        let best = null;
        let bestScore = 0;
        for (const candidate of candidates) {
            const cell = candidate.closest('[role="gridcell"], .ag-cell, td');
            const metadata = [
                cellMetadata(cell),
                candidate.id || '',
                candidate.name || '',
                candidate.getAttribute('aria-label') || '',
                candidate.getAttribute('title') || '',
            ].join(' ').toLowerCase();
            let score = 0;
            if (/buyer\\s*style|style\\s*code/.test(metadata)) score += 30;
            if (/style/.test(metadata)) score += 18;
            if (/article/.test(metadata)) score += 12;
            if (/sample\\s*(order)?\\s*(no|number)/.test(metadata)) score -= 40;
            if (text(candidate)) score += 2;
            if (score > bestScore) {
                best = candidate;
                bestScore = score;
            }
        }
        return best;
    };
    const fieldText = (row, patterns) => {
        const cells = [...row.querySelectorAll('[role="gridcell"], .ag-cell, td')];
        const cell = cells.find(candidate => {
            const metadata = cellMetadata(candidate);
            return patterns.some(pattern => pattern.test(metadata));
        });
        return text(cell);
    };
    const rowNodes = [...root.querySelectorAll(
        '.ag-row[row-index], [role="row"][row-index]'
    )].filter(row => shown(row)
        && !row.classList.contains('ag-row-loading')
        && !row.classList.contains('ag-row-ghost')
        && row.getAttribute('aria-hidden') !== 'true');
    const uniqueRows = [];
    const grouped = new Map();
    rowNodes.forEach((row, index) => {
        const rowKey = row.getAttribute('row-id')
            || row.getAttribute('row-index') || String(index);
        if (!grouped.has(rowKey)) grouped.set(rowKey, []);
        grouped.get(rowKey).push(row);
    });
    grouped.forEach((rowParts, rowKey) => {
        const row = rowParts[0];
        const action = rowParts.map(styleAction).find(Boolean);
        const groupedFieldText = patterns => {
            for (const part of rowParts) {
                const value = fieldText(part, patterns);
                if (value) return value;
            }
            return '';
        };
        uniqueRows.push({
            row_key: rowKey,
            row_index: row.getAttribute('row-index') || '',
            style_code: text(action),
            sample_no: groupedFieldText([
                /sample\\s*(order)?\\s*(no|number)/,
                /sampleorder(no|number)/,
            ]),
            created_by: groupedFieldText([/created\\s*by/, /createdby/]),
            buyer: groupedFieldText([
                /buyer\\s*(name|company)?$/,
                /buyer(name|company)/,
            ]),
        });
    });
    const noRows = [...root.querySelectorAll(
        '.ag-overlay-no-rows-wrapper, .ag-overlay-no-rows-center'
    )].some(shown);
    return {
        rows: uniqueRows,
        noRows,
        totalRows: uniqueRows.length,
    };
}"""


_CLICK_SAMPLE_STYLE_JS = """(row, expectedCode) => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const text = element => String(
        element?.value || element?.textContent || element?.title || ''
    ).replace(/\\s+/g, ' ').trim();
    const expected = String(expectedCode || '').trim().toLowerCase();
    let best = null;
    let bestScore = -100;
    for (const candidate of row.querySelectorAll(
        'input[type="button"], button, a, [onclick]'
    )) {
        if (!shown(candidate)) continue;
        const cell = candidate.closest('[role="gridcell"], .ag-cell, td');
        const metadata = [
            cell?.getAttribute('col-id') || '',
            cell?.getAttribute('aria-label') || '',
            candidate.id || '',
            candidate.name || '',
            candidate.getAttribute('aria-label') || '',
            candidate.getAttribute('title') || '',
        ].join(' ').toLowerCase();
        const value = text(candidate);
        let score = value.toLowerCase() === expected ? 100 : 0;
        if (/buyer\\s*style|style\\s*code/.test(metadata)) score += 30;
        if (/style/.test(metadata)) score += 18;
        if (/article/.test(metadata)) score += 12;
        if (/sample\\s*(order)?\\s*(no|number)/.test(metadata)) score -= 40;
        if (score > bestScore) {
            best = candidate;
            bestScore = score;
        }
    }
    if (!best || (expected && text(best).toLowerCase() !== expected)) return '';
    const value = text(best);
    best.click();
    return value;
}"""


def _sample_result_grid(
    frame: Frame,
    timeout_s: float = 12,
) -> tuple[Any, dict[str, Any]]:
    """Đọc đúng grid Sample đã lọc và chờ số dòng ổn định."""
    deadline = time.monotonic() + timeout_s
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        best: tuple[Any, dict[str, Any]] | None = None
        try:
            roots = frame.locator(".ag-root-wrapper")
            for index in range(roots.count()):
                root = roots.nth(index)
                if not root.is_visible():
                    continue
                payload = root.evaluate(_SAMPLE_RESULT_ROWS_JS)
                score = (
                    int(payload.get("totalRows") or 0),
                    len(payload.get("rows") or []),
                    int(bool(payload.get("noRows"))),
                )
                if best is None or score > (
                    int(best[1].get("totalRows") or 0),
                    len(best[1].get("rows") or []),
                    int(bool(best[1].get("noRows"))),
                ):
                    best = (root, payload)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            last_error = exc
            _wait(frame, MODULE_GRID_POLL_MS)
            continue
        if best is None:
            _wait(frame, MODULE_GRID_POLL_MS)
            continue
        payload = best[1]
        key = (
            int(payload.get("totalRows") or 0),
            len(payload.get("rows") or []),
            bool(payload.get("noRows")),
        )
        ready = bool(payload.get("rows")) or bool(payload.get("noRows"))
        now = time.monotonic()
        if ready and key == stable_key:
            if now - stable_since >= 0.8:
                return best
        else:
            stable_key = key
            stable_since = now
        _wait(frame, MODULE_GRID_POLL_MS)
    raise PlaywrightTimeoutError(
        "Kết quả Sample chưa ổn định; "
        f"lastError={last_error or ''}"
    )


def _click_sample_style_result(
    frame: Frame,
    row_key: str,
    style_code: str,
    log: Callable[[str], None],
) -> bool:
    root, payload = _sample_result_grid(frame, timeout_s=4)
    expected_key = str(row_key or "")
    expected_code = str(style_code or "").strip()
    rows = root.locator(
        ".ag-row[row-index], [role='row'][row-index]"
    )
    for index in range(rows.count()):
        row = rows.nth(index)
        try:
            current_key = (
                row.get_attribute("row-id")
                or row.get_attribute("row-index")
                or str(index)
            )
            if current_key != expected_key:
                continue
            clicked_code = str(
                row.evaluate(_CLICK_SAMPLE_STYLE_JS, expected_code) or ""
            ).strip()
            if clicked_code.casefold() != expected_code.casefold():
                continue
            _write_log(
                log,
                f"[SAMPLE FILE] Đã click Style Code {clicked_code}.",
            )
            return True
        except PlaywrightError:
            continue
    _write_log(
        log,
        "[SAMPLE FILE] Dòng đã chọn không còn trong kết quả hiện tại; "
        f"renderedRows={len(payload.get('rows') or [])}.",
    )
    return False


def _sample_file_result(
    frame: Frame,
    log: Callable[[str], None],
) -> dict[str, Any]:
    _root, payload = _sample_result_grid(frame)
    rows = [
        row for row in payload.get("rows") or []
        if isinstance(row, dict)
    ]
    total_rows = max(int(payload.get("totalRows") or 0), len(rows))
    _write_log(
        log,
        "[SAMPLE FILE] Đã đọc kết quả Sample; "
        f"totalRows={total_rows}; renderedRows={len(rows)}.",
    )
    if not rows:
        return _result(
            False,
            "NO_RESULTS",
            "Không tìm thấy Sample phù hợp để kiểm tra file.",
            samples=[],
        )
    usable = [row for row in rows if str(row.get("style_code") or "").strip()]
    if not usable:
        return _result(
            False,
            "SAMPLE_STYLE_NOT_FOUND",
            "Kết quả Sample không có Style Code có thể mở.",
        )
    if total_rows > 1 or len(rows) > 1:
        return _result(
            True,
            "SAMPLE_MULTIPLE_RESULTS",
            f"Có {total_rows} kết quả; chọn Sample cần kiểm tra file.",
            samples=usable[:20],
            result_count=total_rows,
        )
    selected = usable[0]
    if not _click_sample_style_result(
        frame,
        str(selected.get("row_key") or ""),
        str(selected.get("style_code") or ""),
        log,
    ):
        return _result(
            False,
            "SAMPLE_RESULT_EXPIRED",
            "Dòng Sample vừa thay đổi trước khi mở Style Code. Hãy thử lại.",
        )
    article_code = str(selected.get("style_code") or "").strip()
    return _result(
        True,
        "SAMPLE_STYLE_OPENED",
        f"Đã mở Style Code {article_code} từ Sample List.",
        article_code=article_code,
    )


def find_sample_file_results(
    xpath: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Tìm Sample như flow thường, tự mở Style nếu chỉ có một dòng."""
    selected_field = SAMPLE_SEARCH_SPEC.fields.get(filter_kind)
    if selected_field is None:
        return _result(
            False,
            "INVALID_FILTER",
            "Kiểu tìm Sample List không hợp lệ.",
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
        frame = _open_list_search_context(
            page,
            SAMPLE_SEARCH_SPEC,
            xpath,
            log,
        )
        _clear_list_search_fields(
            frame,
            SAMPLE_SEARCH_SPEC.field_selectors,
            scan_horizontal=SAMPLE_SEARCH_SPEC.requires_floating_filter,
        )
        _wait(page, 250)
        field = _search_input_in_frame(
            page,
            frame,
            selected_field.selectors,
            selected_field.aliases,
            timeout_s=8,
            scan_horizontal=SAMPLE_SEARCH_SPEC.requires_floating_filter,
        )
        search_started = True
        _apply_module_search(page, field, query, selected_field.label, log)
        return _sample_file_result(frame, log)
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="Sample List")
    except PlaywrightTimeoutError as exc:
        detail = _first_line(exc)
        code = (
            "MODULE_SEARCH_NOT_CONFIRMED"
            if search_started
            else "MODULE_SEARCH_NOT_READY"
        )
        message = f"Chưa thể kiểm tra file từ Sample List: {detail}"
        _write_log(log, message)
        return _result(False, code, message, module="Sample List")
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(
            False,
            "SAMPLE_FILE_SEARCH_FAILED",
            message,
            module="Sample List",
        )
    finally:
        if playwright is not None:
            playwright.stop()


def _sample_filter_values(
    values: Mapping[str, str],
) -> tuple[dict[str, str], list[str]]:
    cleaned = {
        field_name: str(values.get(field_name) or "").strip()
        for field_name in SAMPLE_SEARCH_SPEC.fields
    }
    return cleaned, [
        field_name for field_name, value in cleaned.items() if value
    ]


def _apply_sample_filters(
    page: Page,
    frame: Frame,
    cleaned_values: Mapping[str, str],
    active_fields: list[str],
    log: Callable[[str], None],
) -> list[str]:
    """Áp dụng filter Sample lần lượt để hỗ trợ các cột bị cuộn ngang."""
    _clear_list_search_fields(
        frame,
        SAMPLE_SEARCH_SPEC.field_selectors,
        scan_horizontal=SAMPLE_SEARCH_SPEC.requires_floating_filter,
    )
    _wait(page, 250)
    labels: list[str] = []
    for field_name in active_fields:
        field_spec = SAMPLE_SEARCH_SPEC.fields[field_name]
        field = _search_input_in_frame(
            page,
            frame,
            field_spec.selectors,
            field_spec.aliases,
            timeout_s=8,
            scan_horizontal=SAMPLE_SEARCH_SPEC.requires_floating_filter,
        )
        _apply_module_search(
            page,
            field,
            cleaned_values[field_name],
            field_spec.label,
            log,
        )
        labels.append(field_spec.label)
    return labels


def search_sample_list_with_filters(
    xpath: str,
    values: Mapping[str, str],
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Tìm Sample theo một hoặc nhiều filter trên Floating Filter."""
    cleaned_values, active_fields = _sample_filter_values(values)
    if not active_fields:
        labels = ", ".join(
            field_spec.label for field_spec in SAMPLE_SEARCH_SPEC.fields.values()
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
        frame = _open_list_search_context(page, SAMPLE_SEARCH_SPEC, xpath, log)
        search_started = True
        labels = _apply_sample_filters(
            page,
            frame,
            cleaned_values,
            active_fields,
            log,
        )
        return _result(
            True,
            "MODULE_SEARCH_APPLIED",
            f"Đã lọc Sample List theo {', '.join(labels)}.",
            module="Sample List",
            filter_kinds=active_fields,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="Sample List")
    except PlaywrightTimeoutError as exc:
        detail = _first_line(exc)
        code = (
            "MODULE_SEARCH_NOT_CONFIRMED"
            if search_started
            else "MODULE_SEARCH_NOT_READY"
        )
        message = f"Chưa thể tìm nhiều điều kiện trong Sample List: {detail}"
        _write_log(log, message)
        return _result(False, code, message, module="Sample List")
    except Exception as exc:
        message = f"Không thể tìm Sample List: {type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "MODULE_SEARCH_FAILED", message, module="Sample List")
    finally:
        if playwright is not None:
            playwright.stop()


def find_sample_file_results_with_filters(
    xpath: str,
    values: Mapping[str, str],
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Dùng cùng filter đa điều kiện của Sample trước khi quét file."""
    cleaned_values, active_fields = _sample_filter_values(values)
    if not active_fields:
        labels = ", ".join(
            field_spec.label for field_spec in SAMPLE_SEARCH_SPEC.fields.values()
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
        frame = _open_list_search_context(page, SAMPLE_SEARCH_SPEC, xpath, log)
        search_started = True
        _apply_sample_filters(
            page,
            frame,
            cleaned_values,
            active_fields,
            log,
        )
        return _sample_file_result(frame, log)
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="Sample List")
    except PlaywrightTimeoutError as exc:
        detail = _first_line(exc)
        code = (
            "MODULE_SEARCH_NOT_CONFIRMED"
            if search_started
            else "MODULE_SEARCH_NOT_READY"
        )
        message = f"Chưa thể kiểm tra file từ Sample List: {detail}"
        _write_log(log, message)
        return _result(False, code, message, module="Sample List")
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(
            False,
            "SAMPLE_FILE_SEARCH_FAILED",
            message,
            module="Sample List",
        )
    finally:
        if playwright is not None:
            playwright.stop()


def open_sample_file_result(
    row_key: str,
    style_code: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Tiếp tục từ grid Sample đang giữ sau khi user chọn một kết quả."""
    row_key = str(row_key or "").strip()
    style_code = str(style_code or "").strip()
    if not row_key or not style_code:
        return _result(
            False,
            "SAMPLE_RESULT_EXPIRED",
            "Lựa chọn Sample đã hết hiệu lực. Hãy bấm Check File lại.",
        )
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame, _field = _search_input_in_frames(
            page,
            SAMPLE_SEARCH_SPEC.context_field.selectors,
            SAMPLE_SEARCH_SPEC.context_field.aliases,
            timeout_s=2,
        )
        if not _click_sample_style_result(frame, row_key, style_code, log):
            return _result(
                False,
                "SAMPLE_RESULT_EXPIRED",
                "Kết quả Sample đã thay đổi. Hãy bấm Check File lại.",
            )
        return _result(
            True,
            "SAMPLE_STYLE_OPENED",
            f"Đã mở Style Code {style_code} từ Sample List.",
            article_code=style_code,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="Sample List")
    except (PlaywrightTimeoutError, PlaywrightError):
        return _result(
            False,
            "SAMPLE_RESULT_EXPIRED",
            "Sample List hoặc dòng đã chọn không còn mở. Hãy bấm Check File lại.",
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SAMPLE_FILE_OPEN_FAILED", message)
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
    """Lọc RMPO rồi trả các dòng đang hiển thị để panel cho phép chọn."""
    cleaned = {
        "supplier": str(supplier or "").strip(),
        "order_no": str(order_no or "").strip(),
    }
    active = [key for key, value in cleaned.items() if value]
    if not active:
        return _result(
            False,
            "QUERY_REQUIRED",
            "Vui lòng nhập ít nhất một điều kiện: Supplier, RMPO No.",
        )

    playwright: Playwright | None = None
    search_started = False
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_multi_field_search_context(
            page,
            RMPO_SEARCH_SPEC,
            xpath,
            log,
        )
        fields = _resolve_multi_search_fields(frame, RMPO_SEARCH_SPEC)
        search_started = True
        _clear_multi_search_fields(fields)
        active_labels, last_field = _fill_multi_search_fields(
            fields,
            cleaned,
            active,
            RMPO_SEARCH_SPEC,
            log,
        )
        _submit_multi_search(last_field)
        _wait_module_search_settled(page, active_labels)
        # Một số phiên WFX thay document khi Enter. Resolve lại đúng RMPO List
        # trước khi đọc, không giữ frame của form search cũ.
        frame = _find_rmpo_frame(page)
        rows = _wait_rmpo_rows(frame, expected_values=cleaned)
        _write_log(
            log,
            "[RMPO] Đã đọc kết quả sau khi lọc; "
            f"rows={len(rows)}.",
        )
        if not rows:
            return _result(
                False,
                "RMPO_NO_RESULTS",
                "Không tìm thấy RMPO phù hợp.",
                module=RMPO_SEARCH_SPEC.module_name,
                rmpo_rows=[],
                result_count=0,
            )
        return _result(
            True,
            "RMPO_RESULTS_READY",
            f"Có {len(rows)} RMPO phù hợp; hãy chọn một dòng để thao tác.",
            module=RMPO_SEARCH_SPEC.module_name,
            filter_kinds=active,
            rmpo_rows=rows,
            result_count=len(rows),
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module=RMPO_SEARCH_SPEC.module_name)
    except PlaywrightTimeoutError as exc:
        detail = _first_line(exc)
        if search_started:
            code = "MODULE_SEARCH_NOT_CONFIRMED"
            message = (
                "Đã nhập filter trong RMPO List, nhưng WFX chưa xác nhận "
                f"kết quả: {detail}"
            )
        else:
            code = "MODULE_SEARCH_NOT_READY"
            message = (
                "App đã tự mở RMPO List, nhưng các ô search chưa sẵn sàng: "
                f"{detail}"
            )
        _write_log(log, message)
        return _result(False, code, message, module=RMPO_SEARCH_SPEC.module_name)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {_first_line(exc)}"
        message = f"Không thể tìm trong RMPO List: {detail}"
        _write_log(log, message)
        return _result(
            False,
            "MODULE_SEARCH_FAILED",
            message,
            module=RMPO_SEARCH_SPEC.module_name,
        )
    finally:
        if playwright is not None:
            playwright.stop()


_RMPO_ROWS_JS = """root => {
    const norm = value => String(value || '').replace(/\\s+/g, ' ').trim();
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && Number(style.opacity || 1) !== 0
            && rect.width > 0 && rect.height > 0;
    };
    const valueOf = cell => {
        if (!cell) return '';
        const control = cell.querySelector(
            'input[value], button, a, [title], img[alt]'
        );
        return norm(control?.value || control?.textContent
            || control?.getAttribute?.('title')
            || control?.getAttribute?.('alt') || cell.textContent || '');
    };
    const headerCells = [...document.querySelectorAll(
        '#gridRMPO_tblGridHeader th, #gridRMPO_tblGridHeader td'
    )];
    const metadata = cell => {
        const header = Number.isInteger(cell?.cellIndex)
            ? headerCells[cell.cellIndex] : null;
        return norm([
            cell?.id || '', cell?.getAttribute?.('title') || '',
            cell?.getAttribute?.('aria-label') || '', header?.id || '',
            header?.getAttribute?.('title') || '', header?.textContent || ''
        ].join(' ')).toLowerCase();
    };
    const field = (cells, ids, patterns) => {
        const exact = cells.find(cell => ids.includes(cell.id));
        const matched = exact || cells.find(cell =>
            patterns.some(pattern => pattern.test(metadata(cell)))
        );
        return valueOf(matched);
    };
    const rows = [...root.querySelectorAll('tr')]
        .filter(row => shown(row)
            && [...row.children].some(cell => cell.id === 'colOrderNo'))
        .map((row, index) => {
            const cells = [...row.children].filter(
                child => child.tagName === 'TD'
            );
            return {
                row_key: row.id || row.getAttribute('data-key')
                    || row.getAttribute('data-row-key') || String(index),
                status: field(cells, ['colStatus'], [/status/]),
                supplier: field(cells, [
                    'colSupplier', 'colSupplierName', 'colSupplierDesc',
                    'colVendor', 'colVendorName'
                ], [/supplier/, /vendor/]),
                order_no: field(cells, ['colOrderNo'], [
                    /order\\s*(no|number)/, /rmpo\\s*(no|number)?/
                ]),
                last_created: field(cells, [
                    'colLastCreated', 'colCreatedOn', 'colCreated'
                ], [/last\\s*created/, /created/]),
                qty: field(cells, ['colQty', 'colQuantity'], [
                    /\\bqty\\b/, /quantity/
                ]),
            };
        })
        .filter(row => row.order_no || row.supplier || row.status);
    const noRows = [...root.querySelectorAll(
        '.ag-overlay-no-rows-wrapper, .ag-overlay-no-rows-center, td, span, div'
    )].some(element => shown(element) && !element.children.length
        && /no records?|no data|không có dữ liệu/i.test(element.textContent || ''));
    const loading = [
        '.ag-overlay-loading-wrapper', '.ag-loading', '.blockUI',
        '.blockOverlay', '.ui-widget-overlay', '.loading', '.loader',
        '[aria-busy="true"]', '[id*="loading" i]', '[id*="progress" i]',
        '[class*="loading" i]', '[class*="progress" i]'
    ].some(selector =>
        [...document.querySelectorAll(selector)].some(shown)
    );
    return {rows, noRows, loading};
}"""


_CLICK_RMPO_CELL_JS = """(root, expected) => {
    const norm = value => String(value || '').replace(/\\s+/g, ' ').trim();
    const valueOf = cell => norm(
        cell?.querySelector('input[value], button, a, [title], img[alt]')?.value
        || cell?.querySelector('input[value], button, a, [title], img[alt]')?.textContent
        || cell?.querySelector('[title]')?.getAttribute('title')
        || cell?.querySelector('img[alt]')?.getAttribute('alt')
        || cell?.textContent || ''
    );
    const wantedKey = String(expected.row_key || '');
    const wantedOrder = norm(expected.order_no).toLowerCase();
    const rows = [...root.querySelectorAll('tr')].filter(row =>
        [...row.children].some(cell => cell.id === 'colOrderNo')
    );
    const row = rows.find((candidate, index) => {
        const key = candidate.id || candidate.getAttribute('data-key')
            || candidate.getAttribute('data-row-key') || String(index);
        const order = valueOf(
            [...candidate.children].find(cell => cell.id === 'colOrderNo')
        ).toLowerCase();
        return key === wantedKey && order === wantedOrder;
    });
    if (!row) return false;
    const cell = [...row.children].find(
        candidate => candidate.id === expected.column_id
    );
    if (!cell) return false;
    const control = cell.querySelector(
        'a, input[type="button"], button, [onclick]'
    );
    (control || cell).click();
    return true;
}"""


def _find_rmpo_frame(page: Page, timeout_s: float = 8) -> Frame:
    return _frame_with_visible_context(
        page,
        ", ".join(RMPO_SEARCH_SPEC.context_field.selectors),
        module_name=RMPO_SEARCH_SPEC.module_name,
        timeout_s=timeout_s,
    )


def _rmpo_grid(frame: Frame) -> Any | None:
    for selector in ("#gridRMPO_tblGridContent", "#gridRMPO"):
        try:
            grid = _first_visible(frame.locator(selector))
            if grid is not None:
                return grid
        except PlaywrightError:
            continue
    # Một số bản WFX chỉ render hai table Header/Content độc lập, không có
    # wrapper #gridRMPO. Khi các ô filter của RMPO đang hiện đúng context,
    # đọc từ body vẫn an toàn vì script chỉ nhận row có cell #colOrderNo.
    try:
        context = _first_visible(
            frame.locator(
                "#gridRMPO_tblGridHeader_trSearch_td_colOrderNo, "
                "#gridRMPO_tblGridHeader_trSearch_td_colSupplier"
            )
        )
        body = _first_visible(frame.locator("body"))
        if context is not None and body is not None:
            return body
    except PlaywrightError:
        pass
    return None


def _read_rmpo_rows(frame: Frame) -> tuple[list[dict[str, str]], bool, bool]:
    grid = _rmpo_grid(frame)
    if grid is None:
        raise PlaywrightTimeoutError("Không tìm thấy bảng gridRMPO.")
    payload = grid.evaluate(_RMPO_ROWS_JS)
    raw_rows = payload.get("rows") if isinstance(payload, dict) else []
    rows: list[dict[str, str]] = []
    for raw in raw_rows or []:
        if not isinstance(raw, dict):
            continue
        rows.append(
            {
                key: str(raw.get(key) or "").strip()
                for key in (
                    "row_key",
                    "status",
                    "supplier",
                    "order_no",
                    "last_created",
                    "qty",
                )
            }
        )
    if not isinstance(payload, dict):
        return rows, False, False
    return rows, bool(payload.get("noRows")), bool(payload.get("loading"))


def _wait_rmpo_rows(
    frame: Frame,
    timeout_s: float = 15,
    expected_values: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    deadline = time.monotonic() + timeout_s
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    while time.monotonic() < deadline:
        rows, no_rows, loading = _read_rmpo_rows(frame)
        key = tuple(
            (row["row_key"], row["order_no"], row["status"])
            for row in rows
        )
        expected = expected_values or {}
        filters_match = all(
            not str(expected.get(field) or "").strip()
            or all(
                str(expected[field]).strip().casefold()
                in row[field].casefold()
                for row in rows
            )
            for field in ("supplier", "order_no")
        )
        ready = not loading and (no_rows or (bool(rows) and filters_match))
        now = time.monotonic()
        if ready and key == stable_key:
            if now - stable_since >= 0.8:
                return rows
        else:
            stable_key = key
            stable_since = now
        _wait(frame, MODULE_GRID_POLL_MS)
    raise PlaywrightTimeoutError("Kết quả RMPO chưa ổn định.")


def _snapshot_browser_documents(browser: Any) -> tuple[set[int], list[tuple[Frame, tuple[Frame | None, str]]]]:
    pages = browser.contexts[0].pages
    page_ids = {id(page) for page in pages}
    snapshots: list[tuple[Frame, tuple[Frame | None, str]]] = []
    for page_index, candidate_page in enumerate(pages):
        for frame_index, frame in enumerate(candidate_page.frames):
            snapshots.append(
                (
                    frame,
                    _mark_document(
                        frame,
                        f"rmpo-action-{page_index}-{frame_index}",
                    ),
                )
            )
    return page_ids, snapshots


def _click_rmpo_cell(
    frame: Frame,
    row_key: str,
    order_no: str,
    column_id: str,
) -> bool:
    grid = _rmpo_grid(frame)
    if grid is None:
        return False
    return bool(
        grid.evaluate(
            _CLICK_RMPO_CELL_JS,
            {
                "row_key": row_key,
                "order_no": order_no,
                "column_id": column_id,
            },
        )
    )


def _wait_rmpo_revision_button(
    browser: Any,
    page_ids: set[int],
    snapshots: list[tuple[Frame, tuple[Frame | None, str]]],
    timeout_s: float = 180,
) -> Any:
    selector = 'xpath=//*[@id="titlebarRMPO"]/tbody/tr/td[2]/span/div[9]'
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        current_frames = [
            frame
            for page in reversed(browser.contexts[0].pages)
            for frame in page.frames
        ]
        old_snapshots = {id(frame): snapshot for frame, snapshot in snapshots}
        for frame in current_frames:
            snapshot = old_snapshots.get(id(frame))
            changed = (
                id(frame.page) not in page_ids
                or snapshot is None
                or _document_changed(frame, snapshot)
            )
            if not changed:
                continue
            try:
                button = _first_visible(frame.locator(selector))
                if button is not None:
                    return button
            except PlaywrightError:
                continue
        _wait(current_frames[0] if current_frames else None, 100)
    raise PlaywrightTimeoutError(
        "Nút Revise chưa xuất hiện sau 3 phút."
    )


def open_rmpo_result_action(
    row_key: str,
    order_no: str,
    supplier: str,
    expected_status: str,
    action: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở đúng cột của RMPO đã chọn và hỗ trợ bước Revise."""
    definitions = {
        "check_po": ("colOCNo", "RMPO_PO_OPENED", "Đã mở OC No. của RMPO."),
        "edit_po": ("colOrderNo", "RMPO_REVISE_CLICKED", "Đã bấm Revise cho RMPO."),
        "check_received": (
            "colRecv",
            "RMPO_RECEIVED_OPENED",
            "Đã mở thông tin nhận kho của RMPO.",
        ),
    }
    if action not in definitions:
        return _result(
            False,
            "RMPO_ACTION_INVALID",
            "Thao tác RMPO không hợp lệ.",
        )
    if action == "check_received" and _normalise_search_text(
        expected_status
    ) not in {"received", "part received"}:
        return _result(
            False,
            "RMPO_ACTION_INVALID",
            "RMPO chưa có trạng thái Received hoặc Part Received.",
        )

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _active_wfx_page(playwright, log)
        frame = _find_rmpo_frame(page)
        rows = _wait_rmpo_rows(frame, timeout_s=4)
        selected = next(
            (
                row
                for row in rows
                if row["row_key"] == str(row_key or "")
                and row["order_no"].casefold()
                == str(order_no or "").strip().casefold()
                and row["supplier"].casefold()
                == str(supplier or "").strip().casefold()
                and row["status"].casefold()
                == str(expected_status or "").strip().casefold()
            ),
            None,
        )
        if selected is None:
            return _result(
                False,
                "RMPO_RESULT_EXPIRED",
                "Dòng hoặc Status RMPO đã thay đổi. Hãy tìm lại.",
            )
        column_id, code, message = definitions[action]
        page_ids, snapshots = _snapshot_browser_documents(browser)
        if not _click_rmpo_cell(
            frame,
            selected["row_key"],
            selected["order_no"],
            column_id,
        ):
            return _result(
                False,
                "RMPO_RESULT_EXPIRED",
                "Không còn tìm thấy cột cần mở trên dòng RMPO đã chọn.",
            )
        _write_log(
            log,
            f"[RMPO] Đã click {column_id} của dòng được chọn.",
        )
        if action == "edit_po":
            revise = _wait_rmpo_revision_button(
                browser,
                page_ids,
                snapshots,
                timeout_s=180,
            )
            _click(revise)
            _write_log(log, "[RMPO] Đã click Revise trên cửa sổ RMPO.")
        else:
            # Hai action read-only hoàn tất tại exact click. WFX có thể mở
            # popup mới, tái dùng popup cùng tên hoặc hiển thị nội dung ngay
            # trong document hiện tại, nên không ép một kiểu navigation duy nhất.
            _wait(page, 300)
        return _result(
            True,
            code,
            message,
            order_no=selected["order_no"],
            status=selected["status"],
            action=action,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="RMPO List")
    except PlaywrightTimeoutError as exc:
        message = f"RMPO chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "RMPO_ACTION_NOT_READY", message, module="RMPO List")
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "MODULE_FAILED", message, module="RMPO List")
    finally:
        if playwright is not None:
            playwright.stop()


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


def search_advance_pr_list(
    xpath: str,
    buyer: str,
    supplier: str,
    invoice_no: str,
    order_no: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_fields(
        ADVANCE_PR_SEARCH_SPEC,
        xpath,
        {
            "buyer": buyer,
            "supplier": supplier,
            "invoice_no": invoice_no,
            "order_no": order_no,
        },
        log,
    )


def search_supplier_invoice_list(
    xpath: str,
    supplier: str,
    invoice_no: str,
    po_no: str,
    asn_grn_no: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_fields(
        SUPPLIER_INVOICE_SEARCH_SPEC,
        xpath,
        {
            "supplier": supplier,
            "invoice_no": invoice_no,
            "po_no": po_no,
            "asn_grn_no": asn_grn_no,
        },
        log,
    )


def search_expense_invoice_list(
    xpath: str,
    supplier: str,
    invoice_no: str,
    created_by: str,
    status: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    return _search_module_fields(
        EXPENSE_INVOICE_SEARCH_SPEC,
        xpath,
        {
            "supplier": supplier,
            "invoice_no": invoice_no,
            "created_by": created_by,
            "status": status,
        },
        log,
    )


_SUPPLIER_INVOICE_ROWS_JS = """root => {
    const norm = value => String(value || '').replace(/\\s+/g, ' ').trim();
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
    };
    const headers = [...document.querySelectorAll(
        '#gridAPInvoiceList_tblGridHeader th, '
        + '#gridAPInvoiceList_tblGridHeader td, '
        + '#gridAPInvoiceList_tblGridHeader [id*="Header"]'
    )].map(cell => norm([
        cell.id || '', cell.getAttribute('title') || '',
        cell.getAttribute('aria-label') || '', cell.textContent || ''
    ].join(' ')).toLowerCase());
    const metadata = cell => {
        const index = Number(cell.cellIndex);
        return norm([
            cell.id || '', cell.getAttribute('title') || '',
            cell.getAttribute('aria-label') || '', headers[index] || ''
        ].join(' ')).toLowerCase();
    };
    const field = (cells, patterns) => {
        const cell = cells.find(candidate =>
            patterns.some(pattern => pattern.test(metadata(candidate)))
        );
        return norm(cell?.querySelector('input[value], a, button')?.value
            || cell?.querySelector('input[value], a, button')?.textContent
            || cell?.textContent || '');
    };
    return [...root.querySelectorAll('tbody tr, tr')]
        .filter(row => shown(row) && row.querySelector('td'))
        .map((row, index) => {
            const cells = [...row.querySelectorAll('td')];
            return {
                row_key: row.id || row.getAttribute('data-key')
                    || row.getAttribute('data-row-key') || String(index),
                invoice_no: field(cells, [/invoice\\s*(no|number)?/, /apinvoice/]),
                supplier: field(cells, [/supplier/, /vendor/]),
                po_no: field(cells, [/\\bpo\\s*(no|number)?\\b/, /purchase\\s*order/]),
                asn_grn_no: field(cells, [/asn/, /grn/]),
                status: field(cells, [/status/]),
            };
        })
        .filter(row => row.invoice_no || row.status || row.supplier);
}"""


_CLICK_SUPPLIER_INVOICE_ROW_JS = """(root, expected) => {
    const norm = value => String(value || '').replace(/\\s+/g, ' ').trim();
    const wantedKey = String(expected.row_key || '');
    const wantedInvoice = norm(expected.invoice_no).toLowerCase();
    const rows = [...root.querySelectorAll('tbody tr, tr')]
        .filter(row => row.querySelector('td'));
    const row = rows.find((candidate, index) => {
        const key = candidate.id || candidate.getAttribute('data-key')
            || candidate.getAttribute('data-row-key') || String(index);
        if (wantedKey && key === wantedKey) return true;
        return wantedInvoice && norm(candidate.textContent).toLowerCase()
            .includes(wantedInvoice);
    });
    if (!row) return false;
    const control = row.querySelector(
        'input[type="radio"], input[type="checkbox"], input[type="button"]'
    );
    (control || row.cells?.[0] || row).click();
    return true;
}"""


def _supplier_invoice_grid(frame: Frame) -> Any | None:
    for selector in (
        "#gridAPInvoiceList_tblGridContent",
        "#gridAPInvoiceList",
    ):
        try:
            grid = _first_visible(frame.locator(selector))
            if grid is not None:
                return grid
        except PlaywrightError:
            continue
    return None


def _supplier_invoice_rows(frame: Frame) -> list[dict[str, str]]:
    grid = _supplier_invoice_grid(frame)
    if grid is None:
        raise PlaywrightTimeoutError("Không tìm thấy bảng Supplier Inv List.")
    payload = grid.evaluate(_SUPPLIER_INVOICE_ROWS_JS)
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, str]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        rows.append(
            {
                key: str(raw.get(key) or "").strip()
                for key in (
                    "row_key",
                    "invoice_no",
                    "supplier",
                    "po_no",
                    "asn_grn_no",
                    "status",
                )
            }
        )
    return rows


def _find_supplier_invoice_frame(page: Page) -> Frame:
    return _frame_with_visible_context(
        page,
        ", ".join(SUPPLIER_INVOICE_SEARCH_SPEC.context_field.selectors),
        module_name=SUPPLIER_INVOICE_SEARCH_SPEC.module_name,
        timeout_s=8,
    )


def _select_supplier_invoice_row(
    frame: Frame,
    row_key: str,
    invoice_no: str,
) -> bool:
    grid = _supplier_invoice_grid(frame)
    if grid is None:
        return False
    try:
        return bool(
            grid.evaluate(
                _CLICK_SUPPLIER_INVOICE_ROW_JS,
                {"row_key": row_key, "invoice_no": invoice_no},
            )
        )
    except PlaywrightError:
        return False


def _supplier_invoice_action_for_status(status: str) -> tuple[str, str, str] | None:
    normalised = " ".join(str(status or "").casefold().split())
    if normalised in {"save", "saved"}:
        return (
            '//*[@id="titlebarAPInvoiceList"]/tbody/tr/td[2]/span/div[2]',
            "Delete",
            "SUPPLIER_INVOICE_DELETE_SUBMITTED",
        )
    if normalised in {"confirm", "confirmed"}:
        return (
            '//*[@id="titlebarAPInvoiceList"]/tbody/tr/td[2]/span/div[4]',
            "Cancel",
            "SUPPLIER_INVOICE_CANCEL_SUBMITTED",
        )
    return None


def _submit_supplier_invoice_cancel(
    page: Page,
    frame: Frame,
    row: Mapping[str, str],
    log: Callable[[str], None],
) -> dict[str, Any]:
    status = str(row.get("status") or "").strip()
    action = _supplier_invoice_action_for_status(status)
    if action is None:
        return _result(
            False,
            "SUPPLIER_INVOICE_STATUS_NOT_CANCELLABLE",
            "Invoice chỉ có thể xử lý khi Status là Save hoặc Confirm.",
        )
    row_key = str(row.get("row_key") or "")
    invoice_no = str(row.get("invoice_no") or "")
    if not _select_supplier_invoice_row(frame, row_key, invoice_no):
        return _result(
            False,
            "SUPPLIER_INVOICE_RESULT_EXPIRED",
            "Dòng Supplier Invoice đã thay đổi. Hãy tìm lại trước khi Cancel.",
        )
    selector, action_label, code = action
    button = _first_visible(frame.locator(selector))
    if button is None:
        return _result(
            False,
            "SUPPLIER_INVOICE_ACTION_NOT_READY",
            f"Không tìm thấy nút {action_label} trên Supplier Inv List.",
        )
    _attach_dialog_handler(page, log)
    _click(button)
    _wait(page, 300)
    return _result(
        True,
        code,
        (
            f"Đã bấm {action_label} cho Supplier Invoice. "
            "Nếu WFX hiện hộp xác nhận trong Chrome, hãy kiểm tra rồi xác nhận."
        ),
        action=action_label.casefold(),
        status=status,
    )


def prepare_supplier_invoice_cancel(
    xpath: str,
    invoice_no: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Tìm theo Invoice No.; chỉ tự thao tác khi còn đúng một dòng."""
    invoice_no = str(invoice_no or "").strip()
    if not invoice_no:
        return _result(
            False,
            "QUERY_REQUIRED",
            "Vui lòng nhập Invoice No. cần Cancel.",
        )
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _open_multi_field_search_context(
            page,
            SUPPLIER_INVOICE_SEARCH_SPEC,
            xpath,
            log,
        )
        fields = _resolve_multi_search_fields(
            frame,
            SUPPLIER_INVOICE_SEARCH_SPEC,
        )
        _clear_multi_search_fields(fields)
        _fill_multi_search_fields(
            fields,
            {"invoice_no": invoice_no},
            ["invoice_no"],
            SUPPLIER_INVOICE_SEARCH_SPEC,
            log,
        )
        _submit_multi_search(fields["invoice_no"])
        _wait_module_search_settled(page, ["Invoice No."])
        rows = _supplier_invoice_rows(frame)
        if not rows:
            return _result(
                False,
                "SUPPLIER_INVOICE_NOT_FOUND",
                "Không tìm thấy Supplier Invoice phù hợp.",
            )
        if len(rows) > 1:
            return _result(
                True,
                "SUPPLIER_INVOICE_MULTIPLE_RESULTS",
                "Có nhiều Supplier Invoice phù hợp; hãy chọn đúng invoice để tiếp tục.",
                invoices=rows[:20],
                result_count=len(rows),
            )
        return _submit_supplier_invoice_cancel(page, frame, rows[0], log)
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="Supplier Inv List")
    except PlaywrightTimeoutError as exc:
        message = f"Supplier Inv List chưa sẵn sàng: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SUPPLIER_INVOICE_NOT_READY", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SUPPLIER_INVOICE_CANCEL_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def cancel_supplier_invoice_choice(
    row_key: str,
    invoice_no: str,
    expected_status: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Thực hiện Cancel trên dòng mà người dùng đã chọn từ nhiều kết quả."""
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _active_wfx_page(playwright, log)
        frame = _find_supplier_invoice_frame(page)
        rows = _supplier_invoice_rows(frame)
        selected = next(
            (
                row
                for row in rows
                if row["row_key"] == str(row_key or "")
                and row["invoice_no"].casefold()
                == str(invoice_no or "").strip().casefold()
            ),
            None,
        )
        if selected is None or selected["status"].casefold() != str(
            expected_status or ""
        ).strip().casefold():
            return _result(
                False,
                "SUPPLIER_INVOICE_RESULT_EXPIRED",
                "Danh sách hoặc Status Supplier Invoice đã thay đổi. Hãy tìm lại.",
            )
        return _submit_supplier_invoice_cancel(page, frame, selected, log)
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
            if code == "CHROME_CLOSED"
            else "Phiên chưa đăng nhập hoặc đã hết hạn."
        )
        return _result(False, code, message, module="Supplier Inv List")
    except PlaywrightTimeoutError as exc:
        message = f"Supplier Inv List không còn mở: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SUPPLIER_INVOICE_RESULT_EXPIRED", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "SUPPLIER_INVOICE_CANCEL_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


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
        selected_label = ""
        if default_selection is not None:
            select_selector, select_value, selected_label = default_selection
            _ensure_select_value(
                page,
                select_selector,
                select_value,
                selected_label,
                log,
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
    except RuntimeError as exc:
        code = str(exc)
        message = (
            "Trình duyệt làm việc chưa được mở."
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
            "Trình duyệt làm việc chưa được mở."
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
            "Trình duyệt làm việc chưa được mở."
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
