"""Lớp thao tác cửa sổ native Win32 cho WFX Smart Panel.

Gom toàn bộ code ``ctypes``/Win32 (đưa cửa sổ lên trước, đọc/đặt rect, work
area đúng màn hình, con trỏ, menu chuột phải native, hiện toast không focus) và
các hàm hình học thuần (clamp/snap vào work area) tách khỏi ``panel_app`` để lớp
vòng đời app mỏng và dễ đọc hơn. Mọi hàm trả giá trị an toàn (``False``/``None``)
khi không chạy trên Windows hoặc khi Win32 lỗi — không được ném lỗi làm sập app.
"""

from __future__ import annotations

import os

# Tiêu đề cửa sổ pywebview — dùng để lọc đúng cửa sổ của app trong EnumWindows.
# panel_app import lại các hằng này để đặt title lúc create_window, đảm bảo khớp.
MAIN_WINDOW_TITLE = "WFX Smart"
NOTIFICATION_TITLE = "WFX Smart Notification"
BUBBLE_WINDOW_TITLE = "WFX Smart Bubble"
BUBBLE_MENU_TITLE = "WFX Smart Bubble Menu"

# Kích thước ổn định: không resize WebView trong callback automation vì có thể
# làm nghẽn GUI thread. Phần tử bên trong vẫn nhỏ, dành đủ chỗ cho nội dung.
NOTIFICATION_WIDTH = 232
NOTIFICATION_HEIGHT = 88
COMPACT_EDGE_MARGIN = 12
DEFAULT_DPI = 96


def _scale_logical_size(
    width: int,
    height: int,
    dpi: int | None,
) -> tuple[int, int]:
    """Đổi logical pixels của WebView thành physical pixels của Win32."""
    safe_dpi = int(dpi or DEFAULT_DPI)
    if safe_dpi <= 0:
        safe_dpi = DEFAULT_DPI
    scale = safe_dpi / DEFAULT_DPI
    return (
        max(1, round(int(width) * scale)),
        max(1, round(int(height) * scale)),
    )


def _unscale_physical_size(
    width: int,
    height: int,
    dpi: int | None,
) -> tuple[int, int]:
    """Đổi physical pixels về logical pixels cho fallback pywebview."""
    safe_dpi = int(dpi or DEFAULT_DPI)
    if safe_dpi <= 0:
        safe_dpi = DEFAULT_DPI
    scale = DEFAULT_DPI / safe_dpi
    return (
        max(1, round(int(width) * scale)),
        max(1, round(int(height) * scale)),
    )


def _window_dpi_by_title(title: str) -> int:
    """DPI của màn hình chứa cửa sổ; luôn fallback 96 an toàn."""
    if os.name != "nt":
        return DEFAULT_DPI
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        # Cả cửa sổ hidden cũng phải lấy đúng DPI (startup vào tray/màn phụ).
        hwnd = _find_window_hwnd_any_state(title)
        get_window_dpi = getattr(user32, "GetDpiForWindow", None)
        if hwnd and get_window_dpi is not None:
            get_window_dpi.argtypes = [wintypes.HWND]
            get_window_dpi.restype = wintypes.UINT
            dpi = int(get_window_dpi(wintypes.HWND(hwnd)))
            if dpi > 0:
                return dpi
        get_system_dpi = getattr(user32, "GetDpiForSystem", None)
        if get_system_dpi is not None:
            dpi = int(get_system_dpi())
            if dpi > 0:
                return dpi
    except Exception:
        pass
    return DEFAULT_DPI


def _native_window_text(user32, hwnd) -> str:
    try:
        import ctypes

        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return str(buffer.value)
    except Exception:
        return ""


def _window_priority(process_id: int, title: str) -> int | None:
    if process_id != os.getpid():
        return 1
    if title == MAIN_WINDOW_TITLE:
        return 0
    # Toast và bubble bị loại khỏi việc chọn "cửa sổ chính" (panel) khi
    # enumerate — nếu không, các helper rect/bounds/front sẽ nhắm nhầm.
    if title in (NOTIFICATION_TITLE, BUBBLE_WINDOW_TITLE, BUBBLE_MENU_TITLE):
        return None
    return 2


def _restore_window_only_if_minimized(user32, hwnd) -> None:
    """Khôi phục cửa sổ minimized mà không bỏ trạng thái maximize."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE


def _bring_process_window_to_front(
    process_id: int | None = None,
    *,
    on_top: bool | None = True,
) -> bool:
    """Đưa đúng cửa sổ process lên trước; ``None`` giữ nguyên topmost."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        target_pid = int(process_id or os.getpid())
        found: list[tuple[int, int]] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        @callback_type
        def visit(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == target_pid and user32.IsWindowVisible(hwnd):
                priority = _window_priority(
                    target_pid, _native_window_text(user32, hwnd)
                )
                if priority is not None:
                    found.append((priority, int(hwnd)))
            return True

        user32.EnumWindows(visit, 0)
        if not found:
            return False
        hwnd = wintypes.HWND(min(found, key=lambda item: item[0])[1])
        foreground = user32.GetForegroundWindow()
        current_thread = kernel32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        foreground_thread = (
            user32.GetWindowThreadProcessId(foreground, None)
            if foreground
            else 0
        )
        attached_foreground = bool(
            foreground_thread
            and foreground_thread != current_thread
            and user32.AttachThreadInput(
                current_thread, foreground_thread, True
            )
        )
        attached_target = bool(
            target_thread
            and target_thread != current_thread
            and user32.AttachThreadInput(current_thread, target_thread, True)
        )
        try:
            # SW_RESTORE trên cửa sổ đang maximize sẽ làm Chrome co về
            # kích thước thường. Chỉ dùng nó khi cửa sổ thật sự
            # minimized; các trạng thái khác chỉ được focus.
            _restore_window_only_if_minimized(user32, hwnd)
            if on_top is not None:
                user32.SetWindowPos(
                    hwnd,
                    wintypes.HWND(-1 if on_top else -2),
                    0,
                    0,
                    0,
                    0,
                    0x0001 | 0x0002 | 0x0040,
                )
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
        finally:
            if attached_target:
                user32.AttachThreadInput(current_thread, target_thread, False)
            if attached_foreground:
                user32.AttachThreadInput(
                    current_thread, foreground_thread, False
                )
        return True
    except Exception:
        return False


def _window_rect_for_process(
    process_id: int | None,
) -> tuple[int, int, int, int] | None:
    """Rect của cửa sổ chính thuộc PID, bỏ qua notification cùng process."""
    if os.name != "nt" or not process_id:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found: list[
            tuple[int, int, tuple[int, int, int, int]]
        ] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        class Rect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        @callback_type
        def visit(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == int(process_id) and user32.IsWindowVisible(hwnd):
                rect = Rect()
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    priority = _window_priority(
                        int(process_id), _native_window_text(user32, hwnd)
                    )
                    if priority is not None:
                        bounds = (
                            rect.left, rect.top, rect.right, rect.bottom
                        )
                        area = max(0, rect.right - rect.left) * max(
                            0, rect.bottom - rect.top
                        )
                        found.append((priority, -area, bounds))
            return True

        user32.EnumWindows(visit, 0)
        return min(found, key=lambda item: (item[0], item[1]))[2] if found else None
    except Exception:
        return None


def _work_area_for_process_window(
    process_id: int | None,
) -> tuple[int, int, int, int] | None:
    """Work area (rcWork) của MÀN HÌNH đang chứa cửa sổ chính của process.

    Dùng ``MonitorFromWindow`` + ``GetMonitorInfoW`` nên xử lý đúng đa màn hình
    và đã trừ taskbar — khác ``webview.screens[0]`` (chỉ màn hình chính) và
    ``SPI_GETWORKAREA`` (cũng chỉ màn hình chính). Trả ``None`` nếu không xác
    định được; caller phải coi đó là "không clamp", không được đoán bừa.
    """
    if os.name != "nt" or not process_id:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found: list[tuple[int, int]] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        @callback_type
        def visit(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == int(process_id) and user32.IsWindowVisible(hwnd):
                priority = _window_priority(
                    int(process_id), _native_window_text(user32, hwnd)
                )
                if priority is not None:
                    found.append((priority, int(hwnd)))
            return True

        user32.EnumWindows(visit, 0)
        if not found:
            return None
        return _work_area_for_hwnd(min(found, key=lambda item: item[0])[1])
    except Exception:
        return None


def _work_area_for_hwnd(
    hwnd: int | None,
) -> tuple[int, int, int, int] | None:
    """Work area của đúng màn hình chứa ``hwnd``.

    Khác helper theo process, hàm này dùng được cho bubble ngay cả khi panel
    chính đang ẩn. ``MONITOR_DEFAULTTONEAREST`` còn giúp khôi phục cửa sổ vào
    màn hình gần nhất sau khi người dùng tháo/đổi bố cục màn hình.
    """
    if os.name != "nt" or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        monitor = user32.MonitorFromWindow(
            wintypes.HWND(int(hwnd)), 2
        )  # MONITOR_DEFAULTTONEAREST
        if not monitor:
            return None

        class Rect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", Rect),
                ("rcWork", Rect),
                ("dwFlags", wintypes.DWORD),
            ]

        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        work = info.rcWork
        return (work.left, work.top, work.right, work.bottom)
    except Exception:
        return None


def _work_area_for_point(
    x: int,
    y: int,
) -> tuple[int, int, int, int] | None:
    """Work area của màn hình chứa điểm physical ``(x, y)``.

    Dùng khi kéo bubble để màn hình đích thay đổi ngay lúc con trỏ đi qua ranh
    giới monitor. ``MONITOR_DEFAULTTONEAREST`` cũng xử lý được khoảng trống
    giữa các màn hình trong một layout không thẳng hàng.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class Rect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", Rect),
                ("rcWork", Rect),
                ("dwFlags", wintypes.DWORD),
            ]

        monitor_from_point = user32.MonitorFromPoint
        monitor_from_point.argtypes = [Point, wintypes.DWORD]
        monitor_from_point.restype = wintypes.HANDLE
        monitor = monitor_from_point(
            Point(int(x), int(y)), 2
        )  # MONITOR_DEFAULTTONEAREST
        if not monitor:
            return None

        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        work = info.rcWork
        return (work.left, work.top, work.right, work.bottom)
    except Exception:
        return None


def _work_area_for_window_title(
    title: str,
) -> tuple[int, int, int, int] | None:
    """Work area của màn hình chứa cửa sổ có đúng ``title``."""
    return _work_area_for_hwnd(_find_window_hwnd(title))


def _work_area_for_window_title_any_state(
    title: str,
) -> tuple[int, int, int, int] | None:
    """Work area theo title kể cả khi cửa sổ đang hidden."""
    return _work_area_for_hwnd(_find_window_hwnd_any_state(title))


def _set_process_window_bounds(
    process_id: int,
    x: int,
    y: int,
    width: int | None = None,
    height: int | None = None,
) -> bool:
    """Đặt rect cửa sổ chính bằng physical Win32 coordinates."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found: list[tuple[int, int]] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        @callback_type
        def visit(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == int(process_id) and user32.IsWindowVisible(hwnd):
                priority = _window_priority(
                    int(process_id), _native_window_text(user32, hwnd)
                )
                if priority is not None:
                    found.append((priority, int(hwnd)))
            return True

        user32.EnumWindows(visit, 0)
        if not found:
            return False
        flags = 0x0004 | 0x0040  # NOZORDER | SHOWWINDOW
        if width is None or height is None:
            flags |= 0x0001  # NOSIZE
            width = 0
            height = 0
        return bool(
            user32.SetWindowPos(
                wintypes.HWND(min(found, key=lambda item: item[0])[1]),
                None,
                int(x),
                int(y),
                int(width),
                int(height),
                flags,
            )
        )
    except Exception:
        return False


def _native_cursor_position() -> tuple[int, int] | None:
    """Toạ độ con trỏ theo physical screen coordinates của Win32."""
    if os.name != "nt":
        return None
    try:
        import ctypes

        user32 = ctypes.windll.user32
        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        point = Point()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return None
        return int(point.x), int(point.y)
    except Exception:
        return None


def _native_left_button_down() -> bool:
    """Đọc trực tiếp trạng thái chuột trái, không phụ thuộc WebView events."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
    except Exception:
        return False


def _clamp_to_work_area(
    x: int,
    y: int,
    width: int,
    height: int,
    area: tuple[int, int, int, int] | None,
) -> tuple[int, int]:
    """Ép rect ``width×height`` nằm trọn trong work area.

    Nếu cửa sổ rộng/cao hơn work area thì neo góc trên-trái để phần đầu
    (header, nút đóng) luôn thấy được. ``area`` là ``None`` khi không xác định
    được màn hình — khi đó giữ nguyên toạ độ, không được đoán bừa.
    """
    if area is None:
        return int(x), int(y)
    left, top, right, bottom = area
    max_x = right - width
    max_y = bottom - height
    clamped_x = left if max_x < left else min(max(x, left), max_x)
    clamped_y = top if max_y < top else min(max(y, top), max_y)
    return int(clamped_x), int(clamped_y)


def _snap_to_nearest_edge(
    x: int,
    y: int,
    width: int,
    height: int,
    area: tuple[int, int, int, int] | None,
    margin: int = COMPACT_EDGE_MARGIN,
) -> tuple[int, int]:
    """Dính rect vào mép work area gần nhất (trái/phải/trên/dưới).

    Chỉ đổi toạ độ trên trục của mép gần nhất, giữ nguyên trục còn lại rồi
    clamp lại — để icon luôn nằm gọn trong màn hình sau khi dính.
    """
    if area is None:
        return int(x), int(y)
    left, top, right, bottom = area
    x, y = _clamp_to_work_area(x, y, width, height, area)
    distances = {
        "left": x - left,
        "right": (right - width) - x,
        "top": y - top,
        "bottom": (bottom - height) - y,
    }
    nearest = min(distances, key=distances.get)  # type: ignore[arg-type]
    if nearest == "left":
        x = left + margin
    elif nearest == "right":
        x = right - width - margin
    elif nearest == "top":
        y = top + margin
    else:
        y = bottom - height - margin
    return _clamp_to_work_area(x, y, width, height, area)


def _native_notification_visibility(
    visible: bool,
    x: int = 0,
    y: int = 0,
    width: int = NOTIFICATION_WIDTH,
    height: int = NOTIFICATION_HEIGHT,
) -> bool:
    """Hiện toast không lấy focus và không tạo thêm icon taskbar."""
    return _native_popup_visibility(
        NOTIFICATION_TITLE,
        visible,
        x,
        y,
        width,
        height,
        activate=False,
    )


def _native_popup_visibility(
    title: str,
    visible: bool,
    x: int = 0,
    y: int = 0,
    width: int = 1,
    height: int = 1,
    *,
    activate: bool = False,
) -> bool:
    """Hiện popup tool-window có/không focus mà không tạo icon taskbar."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = _find_window_hwnd_any_state(title)
        if not found:
            return False
        hwnd = wintypes.HWND(found)
        get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        style = int(get_style(hwnd, -20))
        style = (style | 0x00000080) & ~0x00040000  # TOOLWINDOW, no APPWINDOW
        if activate:
            style &= ~0x08000000  # bỏ NOACTIVATE
        else:
            style |= 0x08000000
        set_style(hwnd, -20, style)
        if not visible:
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
            return True
        user32.ShowWindow(hwnd, 5 if activate else 4)  # SHOW / SHOWNOACTIVATE
        flags = 0x0020 | 0x0040  # FRAMECHANGED | SHOW
        if not activate:
            flags |= 0x0010  # NOACTIVATE
        moved = bool(
            user32.SetWindowPos(
                hwnd,
                wintypes.HWND(-1),
                int(x),
                int(y),
                max(1, int(width)),
                max(1, int(height)),
                flags,
            )
        )
        if activate:
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        return moved and bool(user32.IsWindowVisible(hwnd))
    except Exception:
        return False


def _foreground_process_id() -> int | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) if pid.value else None
    except Exception:
        return None


def _foreground_window_hwnd() -> int | None:
    """HWND foreground hiện tại, dùng để phân biệt bubble với menu tray."""
    if os.name != "nt":
        return None
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        return int(hwnd) if hwnd else None
    except Exception:
        return None


def _mouse_state_over_hwnd(
    hwnd: int | None,
    virtual_keys: tuple[int, ...],
) -> tuple[bool, bool]:
    """Trạng thái các nút chuột và con trỏ có nằm trên HWND/child hay không."""
    if os.name != "nt" or not hwnd:
        return False, False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        if not user32.IsWindow(wintypes.HWND(hwnd)):
            return False, False

        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        point = Point()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return False, False
        user32.WindowFromPoint.restype = wintypes.HWND
        target = user32.WindowFromPoint(point)
        over = bool(
            target
            and (
                int(target) == int(hwnd)
                or user32.IsChild(wintypes.HWND(hwnd), target)
            )
        )
        # High bit = đang giữ; low bit = đã bấm kể từ lần đọc trước. Giữ cả hai
        # để không bỏ lỡ click rất nhanh giữa hai nhịp poll 40ms.
        down = any(
            bool(user32.GetAsyncKeyState(key) & 0x8001)
            for key in virtual_keys
        )
        return down, over
    except Exception:
        return False, False


def _right_mouse_state_over_hwnd(hwnd: int | None) -> tuple[bool, bool]:
    """Trạng thái chuột phải và con trỏ có nằm trên HWND/child hay không."""
    return _mouse_state_over_hwnd(hwnd, (0x02,))  # VK_RBUTTON


def _mouse_buttons_state_over_hwnd(hwnd: int | None) -> tuple[bool, bool]:
    """Trạng thái chuột trái/phải để đóng popup khi click ra ngoài."""
    return _mouse_state_over_hwnd(hwnd, (0x01, 0x02))  # VK_LBUTTON / VK_RBUTTON


def _native_compact_context_choice(
    _always_on_top: bool,
    title: str = MAIN_WINDOW_TITLE,
) -> str | None:
    """Hiện menu chuột phải native cạnh con trỏ cho cửa sổ ``title``."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        @callback_type
        def visit(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if (
                pid.value == os.getpid()
                and user32.IsWindowVisible(hwnd)
                and _native_window_text(user32, hwnd) == title
            ):
                found.append(int(hwnd))
                return False
            return True

        user32.EnumWindows(visit, 0)
        if not found:
            return None

        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        point = Point()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return None
        menu = user32.CreatePopupMenu()
        if not menu:
            return None
        try:
            user32.AppendMenuW(menu, 0, 1, "Ẩn xuống taskbar")
            user32.AppendMenuW(menu, 0x0800, 0, "")  # MF_SEPARATOR
            user32.AppendMenuW(menu, 0, 2, "Thu vào system tray")
            hwnd = wintypes.HWND(found[0])
            user32.SetForegroundWindow(hwnd)
            selected = user32.TrackPopupMenu(
                menu,
                0x0100 | 0x0002,  # TPM_RETURNCMD | TPM_RIGHTBUTTON
                point.x,
                point.y,
                0,
                hwnd,
                None,
            )
            user32.PostMessageW(hwnd, 0, 0, 0)  # WM_NULL đóng menu sạch trên Win32
            return {
                1: "taskbar",
                2: "tray",
            }.get(int(selected))
        finally:
            user32.DestroyMenu(menu)
    except Exception:
        return None


def _find_window_hwnd_impl(
    title: str,
    *,
    visible_only: bool,
) -> int | None:
    """Tìm HWND của process này theo title, có thể gồm cả cửa sổ đang ẩn."""
    if os.name != "nt" or not title:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        @callback_type
        def visit(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if (
                pid.value == os.getpid()
                and (not visible_only or user32.IsWindowVisible(hwnd))
                and _native_window_text(user32, hwnd) == title
            ):
                found.append(int(hwnd))
                return False
            return True

        user32.EnumWindows(visit, 0)
        return found[0] if found else None
    except Exception:
        return None


def _find_window_hwnd(title: str) -> int | None:
    """HWND cửa sổ hiển thị của process này có đúng tiêu đề ``title``.

    Dùng để cache HWND của bubble MỘT lần lúc bắt đầu kéo, rồi ``_move_hwnd``
    thẳng vào HWND đó mỗi frame — không EnumWindows lại mỗi lần (nguyên nhân lag
    khi kéo trước đây).
    """
    return _find_window_hwnd_impl(title, visible_only=True)


def _find_window_hwnd_any_state(title: str) -> int | None:
    """HWND theo title kể cả khi hidden (dùng cho startup ẩn trong tray)."""
    return _find_window_hwnd_impl(title, visible_only=False)


def _native_window_visibility(
    title: str,
    visible: bool,
    *,
    on_top: bool | None = None,
) -> bool:
    """Hiện/ẩn top-level HWND trực tiếp, tránh WinForms Invoke bị deadlock."""
    hwnd = _find_window_hwnd_any_state(title)
    if os.name != "nt" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        native = wintypes.HWND(int(hwnd))
        if not visible:
            user32.ShowWindow(native, 0)  # SW_HIDE
            return not bool(user32.IsWindowVisible(native))
        user32.ShowWindow(native, 9 if user32.IsIconic(native) else 5)
        if on_top is not None:
            user32.SetWindowPos(
                native,
                wintypes.HWND(-1 if on_top else -2),
                0,
                0,
                0,
                0,
                0x0001 | 0x0002 | 0x0040,  # NOSIZE | NOMOVE | SHOW
            )
        return bool(user32.IsWindowVisible(native))
    except Exception:
        return False


def _window_rect_by_title(title: str) -> tuple[int, int, int, int] | None:
    """Rect (left, top, right, bottom) của cửa sổ có đúng tiêu đề ``title``."""
    hwnd = _find_window_hwnd(title)
    return _window_rect_for_hwnd(hwnd)


def _window_rect_by_title_any_state(
    title: str,
) -> tuple[int, int, int, int] | None:
    """Rect theo title kể cả khi cửa sổ đang hidden."""
    return _window_rect_for_hwnd(_find_window_hwnd_any_state(title))


def _window_rect_for_hwnd(
    hwnd: int | None,
) -> tuple[int, int, int, int] | None:
    """Rect (left, top, right, bottom) của một HWND đã xác định."""
    if hwnd is None:
        return None
    try:
        import ctypes

        class Rect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = Rect()
        if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return (rect.left, rect.top, rect.right, rect.bottom)
        return None
    except Exception:
        return None


def _move_hwnd(hwnd: int | None, x: int, y: int) -> bool:
    """Dời một HWND đã biết bằng SetWindowPos rẻ (NOSIZE|NOZORDER|NOACTIVATE).

    Không enumerate — dùng trong vòng kéo bubble để mượt, không giật.
    """
    if os.name != "nt" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        return bool(
            ctypes.windll.user32.SetWindowPos(
                wintypes.HWND(int(hwnd)),
                None,
                int(x),
                int(y),
                0,
                0,
                0x0001 | 0x0004 | 0x0010,  # NOSIZE | NOZORDER | NOACTIVATE
            )
        )
    except Exception:
        return False


def _set_bounds_by_title(
    title: str,
    x: int,
    y: int,
    width: int | None = None,
    height: int | None = None,
) -> bool:
    """Đặt bounds theo title, kể cả hidden, mà không tự ý hiện cửa sổ."""
    hwnd = _find_window_hwnd_any_state(title)
    if hwnd is None:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        # Không dùng SHOWWINDOW: helper này còn chạy khi start_hidden=True.
        flags = 0x0004 | 0x0010 | 0x0020  # NOZORDER | NOACTIVATE | FRAMECHANGED
        if width is None or height is None:
            flags |= 0x0001  # NOSIZE
            width = 0
            height = 0
        return bool(
            ctypes.windll.user32.SetWindowPos(
                wintypes.HWND(int(hwnd)),
                None,
                int(x),
                int(y),
                int(width),
                int(height),
                flags,
            )
        )
    except Exception:
        return False


def _set_smooth_corners_by_title(title: str) -> bool:
    """Dùng DWM bo góc anti-aliased và bỏ viền native của bubble.

    ``SetWindowRgn`` cắt theo pixel nguyên nên cạnh cong 48px nhìn răng cưa,
    nhất là khi CSS còn có viền 1px. Windows 11 DWM render corner mượt theo
    scale màn hình; Windows cũ chỉ bỏ qua an toàn và giữ cửa sổ vuông.
    """
    hwnd = _find_window_hwnd_any_state(title)
    if os.name != "nt" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        dwmapi = ctypes.windll.dwmapi
        set_attribute = dwmapi.DwmSetWindowAttribute
        set_attribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        set_attribute.restype = ctypes.c_long
        handle = wintypes.HWND(int(hwnd))
        corner = ctypes.c_int(3)  # DWMWCP_ROUNDSMALL
        corner_result = set_attribute(
            handle,
            33,  # DWMWA_WINDOW_CORNER_PREFERENCE
            ctypes.byref(corner),
            ctypes.sizeof(corner),
        )
        border_color = wintypes.DWORD(0xFFFFFFFE)  # DWMWA_COLOR_NONE
        set_attribute(
            handle,
            34,  # DWMWA_BORDER_COLOR
            ctypes.byref(border_color),
            ctypes.sizeof(border_color),
        )
        return int(corner_result) == 0
    except Exception:
        return False
