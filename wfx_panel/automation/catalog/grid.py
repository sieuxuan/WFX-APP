"""Xác nhận Catalog Grid đã nạp dữ liệu và bật Floating Filter.

Header và Floating Filter xuất hiện TRƯỚC datasource nên không tính là grid
ready: phải có ít nhất một row thật, hoặc no-rows overlay đang hiển thị ổn định."""

from __future__ import annotations

from wfx_panel.automation._common import (
    Callable,
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.catalog.navigation import _catalog_tree_frame_now


def _catalog_grid_frame(
    page: Page,
    previous_frame: Frame | None = None,
    timeout_seconds: float = 15,
) -> Frame:
    """Chờ đúng AG Grid Catalog đang hiển thị ở body frame.

    Khi người dùng chuyển sang module khác, Chromium đôi lúc vẫn giữ Frame
    Catalog cũ trong ``page.frames`` vài giây. URL và DOM của frame đó còn nguyên
    nhưng phần tử đã bị ẩn/detach, nên click toolbar sẽ timeout mãi. Không dùng
    identity ``previous_frame`` làm điều kiện mới vì WFX cũng có thể reload tài
    liệu *trong cùng* Frame object.
    """
    _ = previous_frame
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while time.monotonic() < deadline:
        for frame in reversed(page.frames):
            if "wfxcataloglist" not in frame.url.lower():
                continue
            if _catalog_grid_is_interactive(frame):
                return frame
        _wait(page, 250)
    raise PlaywrightTimeoutError("Không tìm thấy AG Grid của Catalog.")


def _catalog_grid_is_interactive(frame: Frame) -> bool:
    """Chỉ nhận grid còn gắn với frame đang nhìn thấy trên màn hình."""
    frame_element = None
    try:
        if frame.is_detached():
            return False
        root = frame.locator(".ag-root-wrapper").first
        if root.count() != 1:
            return False
        grid_visible = bool(
            root.evaluate(
                """root => {
                    const style = getComputedStyle(root);
                    const rect = root.getBoundingClientRect();
                    return document.visibilityState !== 'hidden'
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.width > 0 && rect.height > 0;
                }"""
            )
        )
        if not grid_visible:
            return False
        # URL/DOM của document cũ đôi khi vẫn đọc được sau khi người dùng chuyển
        # module. Kiểm tra cả HTMLFrameElement ở cha để loại grid nằm trong pane
        # đã bị hidden. Main frame không có frame element thì coi như hợp lệ.
        try:
            frame_element = frame.frame_element()
        except PlaywrightError:
            return True
        return bool(
            frame_element.evaluate(
                """element => {
                    const style = getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.width > 0 && rect.height > 0;
                }"""
            )
        )
    except PlaywrightError:
        return False
    finally:
        if frame_element is not None:
            try:
                frame_element.dispose()
            except PlaywrightError:
                pass


def _wait_catalog_grid_data_ready(
    grid: Frame,
    timeout_seconds: float = 20,
) -> None:
    """Chờ datasource AG Grid thật sự có row hoặc no-rows ổn định.

    WFX dựng header/Floating Filter trước rồi mới bind datasource. Chỉ nhìn
    input visible có thể bắt trúng trạng thái ``aria-rowcount`` còn giá trị cũ
    nhưng center container cao 1px và chưa có row nào.
    """
    root = grid.locator(".ag-root-wrapper").first
    read_state_js = """root => {
        const shown = element => {
            if (!element || !element.isConnected) return false;
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                Number(style.opacity || 1) !== 0 &&
                rect.width > 0 && rect.height > 0;
        };
        const loading = [
            '.ag-overlay-loading-wrapper', '.ag-loading', '.ag-row-loading'
        ].some(selector => [...root.querySelectorAll(selector)].some(shown));
        const noRows = [
            '.ag-overlay-no-rows-wrapper', '.ag-overlay-no-rows-center'
        ].some(selector => [...root.querySelectorAll(selector)].some(shown));
        const rows = [...root.querySelectorAll(
            '.ag-center-cols-container .ag-row[row-index], ' +
            '.ag-center-cols-container [role="row"][row-index]'
        )].filter(shown).length;
        return {loading, noRows, rows};
    }"""
    deadline = time.monotonic() + timeout_seconds
    stable_key: tuple[bool, bool, int] | None = None
    stable_since = 0.0
    while time.monotonic() < deadline:
        state = root.evaluate(read_state_js)
        key = (state["loading"], state["noRows"], state["rows"])
        ready = not state["loading"] and (state["rows"] > 0 or state["noRows"])
        if ready and key == stable_key:
            required_stable = 1.8 if state["noRows"] else 0.6
            if time.monotonic() - stable_since >= required_stable:
                return
        else:
            stable_key = key
            stable_since = time.monotonic()
        _wait(grid, 200)
    raise PlaywrightTimeoutError("Dữ liệu AG Grid của Catalog chưa sẵn sàng.")


def _catalog_filter_row_active(grid: Frame) -> bool:
    """Chỉ coi filter bật khi có ô nhập thực sự dùng được trong grid hiện tại."""
    try:
        root = grid.locator(".ag-root-wrapper").first
        return bool(
            root.evaluate(
                """root => [...root.querySelectorAll(
                    '.ag-floating-filter input, .ag-header-row-column-filter input'
                )].some(input => {
                    const row = input.closest(
                        '.ag-header-row-column-filter, .ag-floating-filter'
                    );
                    if (!row || input.disabled) return false;
                    const style = getComputedStyle(row);
                    const rect = row.getBoundingClientRect();
                    const inputRect = input.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.height >= 16
                        && inputRect.width >= 8
                        && inputRect.height >= 12;
                })"""
            )
        )
    except PlaywrightError:
        return False


def _show_catalog_floating_filter(
    page: Page,
    log: Callable[[str], None],
    previous_frame: Frame | None = None,
    require_data_ready: bool = False,
    timeout_seconds: float = 20,
) -> Frame:
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    excluded_frame = previous_frame
    last_error: Exception | None = None
    clicked_grid_id: int | None = None
    clicked_at = 0.0
    while time.monotonic() < deadline:
        try:
            remaining = max(0.1, deadline - time.monotonic())
            grid = _catalog_grid_frame(
                page,
                previous_frame=excluded_frame,
                timeout_seconds=min(1.0, remaining),
            )
            # Nếu Floating Filter đã hiển thị sẵn (vd. vừa prepare Master rồi
            # bấm Tìm), KHÔNG click lại #showfloatingfilter: nút này là toggle,
            # click sẽ TẮT filter rồi phải chờ 4s + retry — đúng cảm giác
            # "search phải tải lại màn Catalog". Không phụ thuộc riêng ô Code
            # vì AG Grid có thể virtualize cột này ngoài viewport của user.
            if _catalog_filter_row_active(grid):
                if require_data_ready:
                    _wait_catalog_grid_data_ready(grid)
                _write_log(log, "[FILTER] Floating Filter đã sẵn sàng, dùng lại grid.")
                return grid
            grid_id = id(grid)
            show_button = grid.locator("#showfloatingfilter").first
            # Click Playwright bị lớp loading/blockUI chặn dù handler của WFX đã
            # sẵn sàng. Dispatch native click trực tiếp; button là toggle nên chỉ
            # cho phép một lần trên cùng grid, tránh retry biến thành tắt filter.
            if (
                show_button.count() == 1
                and show_button.is_visible()
                and (clicked_grid_id != grid_id or not clicked_at)
            ):
                _write_log(log, "[FILTER] Đang bật Show Floating Filters...")
                show_button.evaluate(
                    """button => {
                        button.dispatchEvent(new MouseEvent('click', {
                            bubbles: true, cancelable: true, view: window
                        }));
                    }"""
                )
                clicked_grid_id = grid_id
                clicked_at = time.monotonic()
            # Chờ DOM re-render bằng các lát nhỏ. Nếu frame/grid bị thay trong
            # lúc đó, vòng ngoài sẽ tự chọn grid mới và mới được click một lần.
            if _catalog_filter_row_active(grid):
                if require_data_ready:
                    _wait_catalog_grid_data_ready(
                        grid,
                        timeout_seconds=max(0.1, deadline - time.monotonic()),
                    )
                _write_log(log, "[FILTER] Đã sẵn sàng hàng Floating Filter.")
                return grid
            _wait(grid, 150)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            last_error = exc
            # Angular/WFX có thể thay frame một lần nữa sau khi Master load.
            excluded_frame = None
            clicked_grid_id = None
            clicked_at = 0.0
            if time.monotonic() < deadline:
                _wait(page, min(300, int((deadline - time.monotonic()) * 1_000)))
    raise PlaywrightTimeoutError(f"Floating Filter chưa sẵn sàng: {last_error}")


def _reuse_prepared_catalog_master(
    page: Page,
    category_value: str,
    log: Callable[[str], None],
) -> bool:
    """Fast-path chỉ nhận đúng Category + grid đang hiển thị và đã ổn định."""
    try:
        tree = _catalog_tree_frame_now(page)
        if tree is None:
            return False
        if tree.locator("#ddlCategory").input_value(timeout=500) != category_value:
            return False
        grid = _catalog_grid_frame(page, timeout_seconds=0.75)
        if not _catalog_filter_row_active(grid):
            return False
        _wait_catalog_grid_data_ready(grid, timeout_seconds=3.0)
        _write_log(
            log,
            "[CATALOG] Master và Floating Filter còn sẵn sàng, dùng lại context.",
        )
        return True
    except (PlaywrightError, PlaywrightTimeoutError):
        return False
