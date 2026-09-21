"""Desktop Win32 giả cho `wfx_panel/win32_window.py`.

Module đó gọi thẳng `ctypes.windll.user32` nên trước đây chỉ có các hàm hình
học thuần được test; mọi nhánh Win32 — EnumWindows, work area đa màn hình,
tool-window không focus, trạng thái chuột — chưa từng chạy. Fake này dựng một
"desktop" khai báo: danh sách cửa sổ (hwnd, pid, title, rect, visible,
minimized, monitor) và vị trí con trỏ; rồi trả lời đúng ngữ nghĩa của từng API
mà code sản phẩm dùng.

`ctypes.WINFUNCTYPE`, `wintypes`, `byref` và `create_unicode_buffer` vẫn là
hàng thật, nên chữ ký và cách code đóng gói tham số vẫn được kiểm.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Any


def _handle(value: Any) -> int:
    """`wintypes.HWND(-1)` đọc ra dạng unsigned 64-bit; đưa về signed."""
    raw = int(getattr(value, "value", value) or 0)
    return raw - (1 << 64) if raw >= (1 << 63) else raw


@dataclass
class Window:
    hwnd: int
    pid: int
    title: str
    rect: tuple[int, int, int, int] = (0, 0, 100, 100)
    visible: bool = True
    minimized: bool = False
    monitor: int = 1
    style: int = 0
    parent: int | None = None


@dataclass
class Monitor:
    handle: int
    work: tuple[int, int, int, int]


@dataclass
class Desktop:
    windows: list[Window] = field(default_factory=list)
    monitors: dict[int, Monitor] = field(default_factory=dict)
    cursor: tuple[int, int] = (0, 0)
    cursor_hwnd: int | None = None
    foreground: int | None = None
    pressed_keys: set[int] = field(default_factory=set)
    dpi: dict[int, int] = field(default_factory=dict)
    system_dpi: int = 96
    calls: list[tuple] = field(default_factory=list)
    fail: set[str] = field(default_factory=set)

    def window(self, hwnd: Any) -> Window | None:
        value = _handle(hwnd)
        return next((item for item in self.windows if item.hwnd == value), None)


class _User32:
    def __init__(self, desktop: Desktop) -> None:
        self._desktop = desktop
        # Code sản phẩm gán `.restype`/`.argtypes` lên các hàm này trước khi
        # gọi, nên chúng phải là object chứ không phải bound method.
        self.WindowFromPoint = _Restyped(self._window_from_point)
        self.GetDpiForWindow = _Restyped(self._dpi_for_window)
        self.GetDpiForSystem = _Restyped(self._dpi_for_system)

    # --- liệt kê ---------------------------------------------------------

    def EnumWindows(self, callback, _lparam):
        for window in list(self._desktop.windows):
            if callback(window.hwnd, 0) is False:
                break
        return True

    def GetWindowThreadProcessId(self, hwnd, pointer=None):
        window = self._desktop.window(hwnd)
        if pointer is not None:
            pointer._obj.value = window.pid if window else 0
        # Thread id giả: cùng process thì cùng thread.
        return (window.pid if window else 0) * 10

    def IsWindowVisible(self, hwnd):
        window = self._desktop.window(hwnd)
        return int(bool(window and window.visible))

    def IsWindow(self, hwnd):
        return int(self._desktop.window(hwnd) is not None)

    def IsIconic(self, hwnd):
        window = self._desktop.window(hwnd)
        return int(bool(window and window.minimized))

    def IsChild(self, parent, child):
        parent_window = self._desktop.window(parent)
        child_window = self._desktop.window(child)
        return int(
            bool(
                parent_window
                and child_window
                and child_window.parent == parent_window.hwnd
            )
        )

    # --- tiêu đề ---------------------------------------------------------

    def GetWindowTextLengthW(self, hwnd):
        window = self._desktop.window(hwnd)
        return len(window.title) if window else 0

    def GetWindowTextW(self, hwnd, buffer, _length):
        window = self._desktop.window(hwnd)
        buffer.value = window.title if window else ""
        return len(buffer.value)

    # --- hiện/ẩn và vị trí ----------------------------------------------

    def ShowWindow(self, hwnd, command):
        window = self._desktop.window(hwnd)
        self._desktop.calls.append(("ShowWindow", _handle(hwnd), command))
        if window is None:
            return 0
        if command == 0:
            window.visible = False
        else:
            window.visible = True
            if command in (5, 9):
                window.minimized = False
        return 1

    def SetWindowPos(self, hwnd, insert_after, x, y, width, height, flags):
        window = self._desktop.window(hwnd)
        self._desktop.calls.append(
            (
                "SetWindowPos",
                _handle(hwnd),
                _handle(insert_after),
                int(x),
                int(y),
                int(width),
                int(height),
                int(flags),
            )
        )
        if "SetWindowPos" in self._desktop.fail or window is None:
            return 0
        left, top, right, bottom = window.rect
        if not flags & 0x0001:  # NOSIZE
            right, bottom = int(x) + int(width), int(y) + int(height)
        else:
            right, bottom = int(x) + (right - left), int(y) + (bottom - top)
        if not flags & 0x0002:  # NOMOVE
            left, top = int(x), int(y)
            right = left + (int(width) if not flags & 0x0001 else right - left)
            bottom = top + (int(height) if not flags & 0x0001 else bottom - top)
        window.rect = (left, top, right, bottom)
        if flags & 0x0040:  # SHOWWINDOW
            window.visible = True
        return 1

    def GetWindowRect(self, hwnd, pointer):
        window = self._desktop.window(hwnd)
        if window is None or "GetWindowRect" in self._desktop.fail:
            return 0
        rect = pointer._obj
        rect.left, rect.top, rect.right, rect.bottom = window.rect
        return 1

    # --- focus -----------------------------------------------------------

    def GetForegroundWindow(self):
        return self._desktop.foreground or 0

    def SetForegroundWindow(self, hwnd):
        self._desktop.foreground = _handle(hwnd)
        self._desktop.calls.append(("SetForegroundWindow", self._desktop.foreground))
        return 1

    def SetActiveWindow(self, hwnd):
        self._desktop.calls.append(
            ("SetActiveWindow", _handle(hwnd))
        )
        return 1

    def SetFocus(self, hwnd):
        self._desktop.calls.append(("SetFocus", _handle(hwnd)))
        return 1

    def BringWindowToTop(self, hwnd):
        self._desktop.calls.append(
            ("BringWindowToTop", _handle(hwnd))
        )
        return 1

    def AttachThreadInput(self, _current, _target, attach):
        self._desktop.calls.append(("AttachThreadInput", bool(attach)))
        return 0 if "AttachThreadInput" in self._desktop.fail else 1

    # --- style -----------------------------------------------------------

    def GetWindowLongW(self, hwnd, _index):
        window = self._desktop.window(hwnd)
        return window.style if window else 0

    def SetWindowLongW(self, hwnd, _index, style):
        window = self._desktop.window(hwnd)
        if window is not None:
            window.style = int(style)
        return int(style)

    # --- màn hình --------------------------------------------------------

    def MonitorFromWindow(self, hwnd, _flags):
        window = self._desktop.window(hwnd)
        return window.monitor if window else 0

    def GetMonitorInfoW(self, monitor, pointer):
        info = self._desktop.monitors.get(int(monitor))
        if info is None or "GetMonitorInfoW" in self._desktop.fail:
            return 0
        target = pointer._obj
        (
            target.rcWork.left,
            target.rcWork.top,
            target.rcWork.right,
            target.rcWork.bottom,
        ) = info.work
        return 1

    def _dpi_for_window(self, hwnd):
        return self._desktop.dpi.get(_handle(hwnd), 0)

    def _dpi_for_system(self):
        return self._desktop.system_dpi

    # --- chuột -----------------------------------------------------------

    def GetCursorPos(self, pointer):
        if "GetCursorPos" in self._desktop.fail:
            return 0
        point = pointer._obj
        point.x, point.y = self._desktop.cursor
        return 1

    def _window_from_point(self, _point):
        return self._desktop.cursor_hwnd or 0

    def GetAsyncKeyState(self, key):
        return 0x8001 if key in self._desktop.pressed_keys else 0


class _Restyped:
    """Bọc một hàm để code sản phẩm gán được `.restype`/`.argtypes`."""

    def __init__(self, call) -> None:
        self._call = call
        self.restype = None
        self.argtypes = None

    def __call__(self, *args):
        return self._call(*args)


class _Kernel32:
    def __init__(self, desktop: Desktop) -> None:
        self._desktop = desktop

    def GetCurrentThreadId(self):
        return 999


class _Dwmapi:
    def __init__(self, desktop: Desktop) -> None:
        self._desktop = desktop
        self.DwmSetWindowAttribute = _Restyped(self._set_attribute)

    def _set_attribute(self, hwnd, attribute, value, size):
        self._desktop.calls.append(
            ("DwmSetWindowAttribute", _handle(hwnd), int(attribute))
        )
        return 1 if "DwmSetWindowAttribute" in self._desktop.fail else 0


class _WinDll:
    def __init__(self, desktop: Desktop) -> None:
        self.user32 = _User32(desktop)
        self.kernel32 = _Kernel32(desktop)
        self.dwmapi = _Dwmapi(desktop)


def install(monkeypatch, desktop: Desktop, *, pid: int = 4242) -> Desktop:
    """Gắn desktop giả vào `ctypes.windll` và giả lập đang chạy trên Windows."""
    from wfx_panel import win32_window

    monkeypatch.setattr(ctypes, "windll", _WinDll(desktop), raising=False)
    monkeypatch.setattr(win32_window.os, "name", "nt", raising=False)
    monkeypatch.setattr(win32_window.os, "getpid", lambda: pid)
    return desktop
