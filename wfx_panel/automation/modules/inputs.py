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
from wfx_panel.automation.modules.constants import MODULE_GRID_POLL_MS
from wfx_panel.automation.modules.context import (
    _frame_matches_module_context,
    _wait_module_search_settled,
)
from wfx_panel.automation.modules.text import _normalise_search_text


class SearchValueNotConfirmed(PlaywrightTimeoutError):
    """WFX không giữ đúng giá trị vừa nhập vào ô lọc.

    Tách khỏi timeout chờ kết quả vì người dùng xử lý khác nhau: một bên là ô
    bị WFX vẽ lại giữa chừng, một bên là bảng còn đang tải.
    """


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


_INPUT_HEADER_METADATA_JS = """elements => elements.map(element => {
    if (!element.isConnected || element.disabled) return null;
    if (getComputedStyle(element).visibility === 'hidden') return null;
    const rect = element.getBoundingClientRect();
    if (!(rect.width > 0 && rect.height > 0)) return null;
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
})"""


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
        # Một evaluate_all cho cả frame thay vì một round-trip CDP cho từng
        # input: đường dự phòng này chạy ở mọi vị trí khi quét ngang AG Grid.
        metadata_list = inputs.evaluate_all(_INPUT_HEADER_METADATA_JS)
    except PlaywrightError:
        return None
    scored: list[tuple[int, int]] = []
    for index, metadata in enumerate(metadata_list or ()):
        if not metadata:
            continue
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
        if score:
            scored.append((score, index))
    # sorted ổn định nên cùng điểm thì input đứng trước trong DOM thắng, giống
    # luật chọn cũ. Xác nhận lại bằng Playwright vì luật hiển thị trong JS chỉ
    # là xấp xỉ.
    for _score, index in sorted(scored, key=lambda item: -item[0]):
        candidate = inputs.nth(index)
        try:
            if candidate.is_visible() and candidate.is_enabled():
                return candidate
        except PlaywrightError:
            continue
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


def _wait_module_search_stable(
    page: Page,
    label: str,
) -> None:
    _wait_module_search_settled(page, [label], timeout_s=15)


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
        raise SearchValueNotConfirmed(
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
