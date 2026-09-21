"""Bật và xác nhận Floating Filter của grid module."""

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
    _browser_boundary_result,
    _first_line,
    _first_visible,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.modules.constants import (
    MODULE_FILTER_VISIBLE_STABLE_SECONDS,
    MODULE_GRID_POLL_MS,
)
from wfx_panel.automation.modules.context import _frame_matches_module_context
from wfx_panel.automation.modules.menu import (
    _active_wfx_page,
    _click_module_menu_on_page,
)


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
    except PlaywrightTimeoutError as exc:
        message = f"Timeout khi mở {module_name}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "FLOATING_FILTER_NOT_READY", message, module=module_name)
    except Exception as exc:
        boundary = _browser_boundary_result(exc, module=module_name)
        if boundary is not None:
            return boundary
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(False, "MODULE_FAILED", message, module=module_name)
    finally:
        if playwright is not None:
            playwright.stop()
