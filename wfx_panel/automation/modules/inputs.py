"""Tìm và điền ô tìm kiếm trong AG Grid có Floating Filter.

Layout cột lưu riêng theo user nên phải quét cả vùng bị virtualize ngoài
viewport ngang, không giả định cột nằm ở vị trí mặc định."""

from __future__ import annotations

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _horizontal_grid_positions,
    _horizontal_grid_state,
    _scroll_horizontal_grid,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.modules.constants import (
    _MODULE_LOADING_SELECTOR,
    MODULE_GRID_POLL_MS,
)
from wfx_panel.automation.modules.context import _frame_matches_module_context
from wfx_panel.automation.modules.text import _normalise_search_text


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
