from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import keyboard
import pystray
import webview
from PIL import Image

from wfx_panel import hotkey, prefs, status, updater
from wfx_panel.assets.generate_icon import build_icon
from wfx_panel.panel_api import PanelAPI
from wfx_panel.single_instance import SingleInstance

HOTKEY = hotkey.DEFAULT
STATUS_POLL_SECONDS = 5
FOLLOW_POLL_SECONDS = 0.6
UPDATE_INITIAL_DELAY_SECONDS = 1
UPDATE_POLL_SECONDS = 4 * 60 * 60
TOAST_MIN_SECONDS = 3.0
ICON_PATH = prefs.RESOURCE_DIR / "wfx_panel" / "assets" / "wfx.ico"
UI_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "index.html"

WINDOW_WIDTH = 440
WINDOW_HEIGHT = 620
WINDOW_MARGIN = 24
BROWSER_DOCK_GAP = 12
BROWSER_DOCK_TOP = 72
COMPACT_SIZE = 48


def _bring_process_window_to_front(
    process_id: int | None = None,
    *,
    on_top: bool = True,
) -> bool:
    """Đưa cửa sổ top-level của process lên trước Chrome trên Windows."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        target_pid = int(process_id or os.getpid())
        found: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        @callback_type
        def visit(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if (
                pid.value == target_pid
                and user32.IsWindowVisible(hwnd)
                and user32.GetWindowTextLengthW(hwnd) > 0
            ):
                found.append(int(hwnd))
                return False
            return True

        user32.EnumWindows(visit, 0)
        if not found:
            return False
        hwnd = wintypes.HWND(found[0])
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
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetWindowPos(
                hwnd,
                wintypes.HWND(-1 if on_top else -2),
                0,
                0,
                0,
                0,
                0x0001 | 0x0002 | 0x0040,  # NOMOVE | NOSIZE | SHOWWINDOW
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
    """Rect của top-level window thuộc đúng PID browser CDP."""
    if os.name != "nt" or not process_id:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found: list[tuple[int, int, int, int]] = []
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
            if (
                pid.value == int(process_id)
                and user32.IsWindowVisible(hwnd)
                and user32.GetWindowTextLengthW(hwnd) > 0
            ):
                rect = Rect()
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    found.append(
                        (rect.left, rect.top, rect.right, rect.bottom)
                    )
                    return False
            return True

        user32.EnumWindows(visit, 0)
        return found[0] if found else None
    except Exception:
        return None


def _set_process_window_bounds(
    process_id: int,
    x: int,
    y: int,
    width: int | None = None,
    height: int | None = None,
) -> bool:
    """Đặt rect top-level window trực tiếp bằng physical Win32 coordinates."""
    if os.name != "nt":
        return False
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
                pid.value == int(process_id)
                and user32.IsWindowVisible(hwnd)
                and user32.GetWindowTextLengthW(hwnd) > 0
            ):
                found.append(int(hwnd))
                return False
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
                wintypes.HWND(found[0]),
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


def _top_right_position() -> tuple[int, int]:
    """Toạ độ mở panel gần góc trên-phải màn hình chính.

    pywebview không nhận x/y sẽ tự canh giữa cửa sổ, sai với thiết kế (panel
    phải neo góc trên-phải). webview.screens chỉ khả dụng SAU khi GUI backend
    đã khởi tạo nên phải gọi hàm này bên trong run()/create_window(), không
    phải ở module scope; bọc try/except vì backend hoặc thuộc tính có thể
    thiếu tuỳ môi trường — không được để lỗi ở đây làm sập khởi động app.
    """
    try:
        screen = webview.screens[0]
        screen_width = int(screen.width)
    except Exception:
        screen_width = 1920
    x = max(WINDOW_MARGIN, screen_width - WINDOW_WIDTH - WINDOW_MARGIN)
    y = WINDOW_MARGIN
    return x, y


class PanelApp:
    def __init__(self):
        self.api = PanelAPI()
        self.window = None
        self.tray = None
        preferences = prefs.load_prefs()
        self._hotkey = preferences["hotkey"]
        self._toast_enabled = preferences["toast_enabled"]
        self._always_on_top = preferences["always_on_top"]
        self._stick_to_browser = preferences["stick_to_browser"]
        self._start_hidden = preferences["start_hidden"]
        self._visible = not self._start_hidden
        self._compact = False
        self._full_window_size: tuple[int, int] | None = None
        self._last_compact_browser_rect: tuple[int, int, int, int] | None = None
        self._last_panel_browser_rect: tuple[int, int, int, int] | None = None
        self._last_panel_window_rect: tuple[int, int, int, int] | None = None
        self._compact_drag_thread: threading.Thread | None = None
        self._compact_offset = (
            (
                preferences["compact_offset_x"],
                preferences["compact_offset_y"],
            )
            if preferences["compact_offset_x"] is not None
            and preferences["compact_offset_y"] is not None
            else None
        )
        self._panel_offset = (
            (
                preferences["panel_offset_x"],
                preferences["panel_offset_y"],
            )
            if preferences["panel_offset_x"] is not None
            and preferences["panel_offset_y"] is not None
            else None
        )
        self._quitting = False
        self._chrome_alive: bool | None = None
        self._last_update_notice = preferences["last_update_notice"]
        self._stop_status = threading.Event()
        # Đăng ký hotkey chạy song song lúc trang đang tải (background(), xem
        # run()); lúc đó window.wfxSetStatus có thể chưa tồn tại nên không thể
        # báo lỗi ngay. Ghi lại đây rồi báo từ _startup(), lúc trang chắc chắn
        # đã load xong.
        self._hotkey_error: str | None = None
        self._hotkey_ready = threading.Event()
        # Khoá một-instance; main() gán vào để quit() trả cổng lại cho lần mở sau.
        self.lock: SingleInstance | None = None

    # -- window bridge -----------------------------------------------------
    def _push_log(self, line: str) -> None:
        if self.window is None:
            return
        from wfx_panel.log_bridge import js_string
        try:
            self.window.evaluate_js(f"window.wfxPushLog({js_string(line)})")
        except Exception:
            pass

    def _set_status(self, tone: str, message: str) -> None:
        if self.window is None:
            return
        from wfx_panel.log_bridge import js_string
        try:
            self.window.evaluate_js(
                f"window.wfxSetStatus({js_string(tone)}, {js_string(message)})"
            )
        except Exception:
            pass

    def _push_update_state(self, state: dict) -> None:
        if self.window is None:
            return
        import json

        try:
            self.window.evaluate_js(
                "window.wfxSetUpdateState("
                f"{json.dumps(state, ensure_ascii=False)})"
            )
        except Exception:
            pass

    def hide_panel(self):
        if self.window and self._visible:
            try:
                self.window.hide()
            except Exception:
                pass
            self._visible = False

    def _set_compact_ui(self, enabled: bool) -> None:
        if self.window is None:
            return
        try:
            self.window.evaluate_js(
                f"window.wfxSetCompactMode({'true' if enabled else 'false'})"
            )
        except Exception:
            pass

    def begin_compact_drag(self) -> dict:
        if not self._compact:
            return {
                "ok": False,
                "code": "PANEL_NOT_COMPACT",
                "message": "Panel chưa ở chế độ icon.",
            }
        if (
            self._compact_drag_thread is not None
            and self._compact_drag_thread.is_alive()
        ):
            return {
                "ok": True,
                "code": "PANEL_DRAG_STARTED",
                "message": "Đang di chuyển icon WFX.",
            }
        pid_getter = getattr(
            self.api._login, "automation_browser_pid", None
        )
        browser_pid = pid_getter() if callable(pid_getter) else None
        cursor = _native_cursor_position()
        own_rect = _window_rect_for_process(os.getpid())
        browser_rect = _window_rect_for_process(browser_pid)
        started = bool(
            _native_left_button_down()
            and cursor is not None
            and own_rect is not None
            and browser_rect is not None
        )
        if started:
            self._compact_drag_thread = threading.Thread(
                target=self._compact_drag_loop,
                args=(cursor, own_rect, browser_pid),
                daemon=True,
            )
            self._compact_drag_thread.start()
        return {
            "ok": started,
            "code": "PANEL_DRAG_STARTED" if started else "PANEL_DRAG_FAILED",
            "message": (
                "Đang di chuyển icon WFX."
                if started
                else "Không thể di chuyển icon WFX."
            ),
        }

    def _compact_drag_loop(
        self,
        origin_cursor: tuple[int, int],
        origin_rect: tuple[int, int, int, int],
        browser_pid: int | None,
    ) -> None:
        """Theo con trỏ toàn hệ thống đến lúc nhả chuột rồi lưu vị trí."""
        width = max(1, origin_rect[2] - origin_rect[0])
        height = max(1, origin_rect[3] - origin_rect[1])
        while self._compact and _native_left_button_down():
            cursor = _native_cursor_position()
            browser_rect = _window_rect_for_process(browser_pid)
            if cursor is None or browser_rect is None:
                break
            left, top, right, bottom = browser_rect
            target_x = origin_rect[0] + cursor[0] - origin_cursor[0]
            target_y = origin_rect[1] + cursor[1] - origin_cursor[1]
            target_x = max(
                left + BROWSER_DOCK_GAP,
                min(target_x, right - width - BROWSER_DOCK_GAP),
            )
            target_y = max(
                top + BROWSER_DOCK_GAP,
                min(target_y, bottom - height - BROWSER_DOCK_GAP),
            )
            _set_process_window_bounds(
                os.getpid(), int(target_x), int(target_y)
            )
            time.sleep(0.012)

        browser_rect = _window_rect_for_process(browser_pid)
        own_rect = _window_rect_for_process(os.getpid())
        if browser_rect is None or own_rect is None:
            return
        self._last_compact_browser_rect = browser_rect
        self._compact_offset = (
            own_rect[0] - browser_rect[0],
            own_rect[1] - browser_rect[1],
        )
        prefs.save_prefs(
            compact_offset_x=self._compact_offset[0],
            compact_offset_y=self._compact_offset[1],
        )

    def collapse_to_browser_icon(self) -> dict:
        """Thu panel thành launcher nổi trong đúng cửa sổ browser automation."""
        if not self._stick_to_browser:
            self.hide_panel()
            return {
                "ok": True,
                "code": "PANEL_HIDDEN",
                "message": "Đã thu panel về tray.",
            }
        if self.window is None:
            return {
                "ok": False,
                "code": "PANEL_NOT_READY",
                "message": "Panel chưa sẵn sàng.",
            }
        try:
            current_rect = _window_rect_for_process(os.getpid())
            if current_rect is not None:
                self._full_window_size = (
                    current_rect[2] - current_rect[0],
                    current_rect[3] - current_rect[1],
                )
                pid_getter = getattr(
                    self.api._login, "automation_browser_pid", None
                )
                browser_pid = pid_getter() if callable(pid_getter) else None
                browser_rect = _window_rect_for_process(browser_pid)
                if browser_rect is not None:
                    offset = (
                        current_rect[0] - browser_rect[0],
                        current_rect[1] - browser_rect[1],
                    )
                    if offset != self._panel_offset:
                        self._panel_offset = offset
                        prefs.save_prefs(
                            panel_offset_x=offset[0],
                            panel_offset_y=offset[1],
                        )
            self._set_compact_ui(True)
            self._compact = True
            self._visible = True
            self._last_compact_browser_rect = None
            self._last_panel_browser_rect = None
            self._last_panel_window_rect = None
            resized = bool(
                current_rect
                and _set_process_window_bounds(
                    os.getpid(),
                    current_rect[0],
                    current_rect[1],
                    COMPACT_SIZE,
                    COMPACT_SIZE,
                )
            )
            if not resized:
                self.window.resize(COMPACT_SIZE, COMPACT_SIZE)
            self.window.on_top = True
            if not self._dock_to_browser():
                self.expand_from_browser_icon()
                return {
                    "ok": False,
                    "code": "BROWSER_WINDOW_NOT_FOUND",
                    "message": "Không tìm thấy cửa sổ browser automation để bám.",
                }
            return {
                "ok": True,
                "code": "PANEL_COMPACT",
                "message": "Nút WFX đang bám ở góc dưới bên phải browser automation.",
            }
        except Exception as error:
            self._compact = False
            self._set_compact_ui(False)
            return {
                "ok": False,
                "code": "PANEL_COMPACT_FAILED",
                "message": f"Không thu gọn được panel: {error}",
            }

    def expand_from_browser_icon(self) -> dict:
        """Bung launcher về panel đầy đủ và neo cạnh browser automation."""
        if self.window is None:
            return {
                "ok": False,
                "code": "PANEL_NOT_READY",
                "message": "Panel chưa sẵn sàng.",
            }
        try:
            if not self._visible:
                self.window.show()
                self._visible = True
            current_rect = _window_rect_for_process(os.getpid())
            restored = bool(
                current_rect
                and self._full_window_size
                and _set_process_window_bounds(
                    os.getpid(),
                    current_rect[0],
                    current_rect[1],
                    self._full_window_size[0],
                    self._full_window_size[1],
                )
            )
            if not restored:
                self.window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
            self.window.on_top = self._always_on_top
            self._compact = False
            self._last_compact_browser_rect = None
            self._set_compact_ui(False)
            if self._stick_to_browser:
                self._last_panel_browser_rect = None
                self._last_panel_window_rect = None
                self._dock_to_browser()
            _bring_process_window_to_front(on_top=self._always_on_top)
            return {
                "ok": True,
                "code": "PANEL_EXPANDED",
                "message": "Đã mở WFX Smart.",
            }
        except Exception as error:
            return {
                "ok": False,
                "code": "PANEL_EXPAND_FAILED",
                "message": f"Không mở rộng được panel: {error}",
            }

    def dismiss_panel(self):
        if self._stick_to_browser:
            return self.collapse_to_browser_icon()
        self.hide_panel()
        return {
            "ok": True,
            "code": "PANEL_HIDDEN",
            "message": "Đã thu panel về tray.",
        }

    def show_panel(self):
        if self._compact:
            self.expand_from_browser_icon()
            return
        if self.window and not self._visible:
            try:
                self.window.show()
            except Exception:
                pass
            self._visible = True
        if self._stick_to_browser:
            self._dock_to_browser()

    def toggle(self):
        if self._compact:
            self.expand_from_browser_icon()
        elif self._visible:
            self.dismiss_panel()
        else:
            self.show_panel()

    def _apply_hotkey(self, spec: str) -> str | None:
        """Đăng ký hotkey mới; trả thông điệp lỗi nếu đăng ký thất bại."""
        try:
            keyboard.remove_hotkey(self._hotkey)
        except (KeyError, ValueError):
            pass
        try:
            keyboard.add_hotkey(spec, self.toggle)
        except Exception as error:
            return str(error)
        self._hotkey = spec
        return None

    def set_toast_enabled_state(self, enabled: bool) -> None:
        self._toast_enabled = bool(enabled)

    def _apply_always_on_top(self, enabled: bool) -> None:
        self._always_on_top = bool(enabled)
        if self.window is not None:
            try:
                self.window.on_top = self._always_on_top
            except Exception:
                pass

    def _apply_stick_to_browser(self, enabled: bool) -> None:
        self._stick_to_browser = bool(enabled)
        if self._stick_to_browser:
            self._last_panel_browser_rect = None
            self._last_panel_window_rect = None
            self._dock_to_browser()
        elif self._compact:
            self.expand_from_browser_icon()

    def _dock_to_browser(self) -> bool:
        if self.window is None or not self._visible:
            return False
        pid_getter = getattr(
            self.api._login, "automation_browser_pid", None
        )
        if not callable(pid_getter):
            return False
        browser_rect = _window_rect_for_process(pid_getter())
        if browser_rect is None:
            return False
        left, top, right, bottom = browser_rect
        if right <= left or bottom <= top or left < -20_000:
            return False
        own_rect = _window_rect_for_process(os.getpid())
        width = (
            COMPACT_SIZE
            if self._compact
            else (
                own_rect[2] - own_rect[0]
                if own_rect is not None
                else WINDOW_WIDTH
            )
        )
        height = (
            COMPACT_SIZE
            if self._compact
            else (
                own_rect[3] - own_rect[1]
                if own_rect is not None
                else WINDOW_HEIGHT
            )
        )
        if not self._compact and own_rect is not None:
            self._full_window_size = (width, height)
        if self._compact:
            previous_browser = self._last_compact_browser_rect
            if previous_browser is not None and own_rect is not None:
                if previous_browser == browser_rect:
                    # Browser đứng yên: không kéo launcher khỏi vị trí người
                    # dùng vừa drag. Khi browser di chuyển, mang launcher đi
                    # theo cùng độ lệch và giữ nó trong vùng browser.
                    return True
                delta_x = left - previous_browser[0]
                delta_y = top - previous_browser[1]
                x = own_rect[0] + delta_x
                preferred_y = own_rect[1] + delta_y
            else:
                if self._compact_offset is not None:
                    x = left + self._compact_offset[0]
                    preferred_y = top + self._compact_offset[1]
                else:
                    x = right - width - BROWSER_DOCK_GAP
                    preferred_y = bottom - height - BROWSER_DOCK_GAP
            x = max(
                left + BROWSER_DOCK_GAP,
                min(x, right - width - BROWSER_DOCK_GAP),
            )
            self._last_compact_browser_rect = browser_rect
        else:
            previous_browser = self._last_panel_browser_rect
            if (
                previous_browser == browser_rect
                and own_rect is not None
                and self._last_panel_window_rect is not None
            ):
                # Header pywebview cho phép kéo cửa sổ native. Khi browser
                # đứng yên, giữ nguyên vị trí mới thay vì vòng follow kéo panel
                # ngược về góc phải sau 0.6 giây.
                if own_rect != self._last_panel_window_rect:
                    offset = (own_rect[0] - left, own_rect[1] - top)
                    if offset != self._panel_offset:
                        self._panel_offset = offset
                        prefs.save_prefs(
                            panel_offset_x=offset[0],
                            panel_offset_y=offset[1],
                        )
                    self._last_panel_window_rect = own_rect
                return True
            if previous_browser is not None and own_rect is not None:
                x = own_rect[0] + left - previous_browser[0]
                preferred_y = own_rect[1] + top - previous_browser[1]
            elif self._panel_offset is not None:
                x = left + self._panel_offset[0]
                preferred_y = top + self._panel_offset[1]
            else:
                x = right - width - BROWSER_DOCK_GAP
                preferred_y = top + BROWSER_DOCK_TOP
            x = max(
                left + BROWSER_DOCK_GAP,
                min(x, right - width - BROWSER_DOCK_GAP),
            )
            self._last_panel_browser_rect = browser_rect
        y = max(
            top + BROWSER_DOCK_GAP,
            min(preferred_y, bottom - height - BROWSER_DOCK_GAP),
        )
        try:
            if _set_process_window_bounds(
                os.getpid(), int(x), int(y)
            ):
                if not self._compact:
                    self._last_panel_window_rect = (
                        int(x),
                        int(y),
                        int(x + width),
                        int(y + height),
                    )
                return True
            self.window.move(int(x), int(y))
            if not self._compact:
                self._last_panel_window_rect = (
                    int(x),
                    int(y),
                    int(x + width),
                    int(y + height),
                )
            return True
        except Exception:
            return False

    def _window_follow_loop(self) -> None:
        while not self._stop_status.wait(FOLLOW_POLL_SECONDS):
            if self._stick_to_browser:
                self._dock_to_browser()

    def _apply_update(self, state: dict) -> str | None:
        try:
            executable = (
                Path(sys.executable)
                if getattr(sys, "frozen", False)
                else Path.cwd() / "dist" / "WFX-Panel" / "WFX-Panel.exe"
            )
            executable_args = None
            if not getattr(sys, "frozen", False) and not executable.is_file():
                executable = Path(sys.executable)
                executable_args = ["-m", "wfx_panel.panel_app"]

            updater.schedule_update(
                state,
                current_pid=os.getpid(),
                executable=executable,
                executable_args=executable_args,
            )
            threading.Timer(1.0, self.quit).start()
            return None
        except Exception as error:
            return f"Không lên lịch được cập nhật: {error}"

    def _on_result(self, method: str, result: dict, elapsed: float) -> None:
        state = {
            **self.api._session_status(),
            **self.api._division_state(),
        }
        if self.window is not None:
            import json

            try:
                self.window.evaluate_js(
                    "window.wfxHandleBackendResult("
                    f"{json.dumps({**result, **state}, ensure_ascii=False)})"
                )
            except Exception:
                pass

        if (
            self._visible
            or not self._toast_enabled
            or elapsed < TOAST_MIN_SECONDS
            or self.tray is None
        ):
            return
        try:
            self.tray.notify(
                str(result.get("message") or "Đã xong."), "WFX Smart"
            )
        except Exception:
            pass

    def _status_loop(self) -> None:
        while not self._stop_status.wait(STATUS_POLL_SECONDS):
            alive = status.chrome_alive()
            if alive == self._chrome_alive:
                continue
            self._chrome_alive = alive
            if self.window is None:
                continue
            try:
                self.window.evaluate_js(
                    f"window.wfxSetChromeStatus({'true' if alive else 'false'})"
                )
            except Exception:
                pass

    def _check_update_once(self) -> None:
        state = self.api.check_for_updates()
        self._push_update_state(state)
        notice_id = str(
            state.get("notice_id") or state.get("tag") or state.get("version") or ""
        )
        if (
            state.get("can_update")
            and notice_id
            and notice_id != self._last_update_notice
        ):
            self._last_update_notice = notice_id
            prefs.save_prefs(last_update_notice=notice_id)
            if self.tray is not None and self._toast_enabled:
                try:
                    self.tray.notify(
                        "Có phiên bản WFX Smart mới. Mở ứng dụng và bấm “Cập nhật ngay”.",
                        "WFX Smart",
                    )
                except Exception:
                    pass

    def _update_loop(self) -> None:
        if self._stop_status.wait(UPDATE_INITIAL_DELAY_SECONDS):
            return
        while not self._stop_status.is_set():
            try:
                self._check_update_once()
            except Exception as error:
                self._push_log(
                    f"[UPDATE] Không kiểm tra tự động được: {type(error).__name__}"
                )
            if self._stop_status.wait(UPDATE_POLL_SECONDS):
                return

    def activate(self):
        """Đưa panel ra trước, kể cả khi state nội bộ đang cho là đã hiện.

        Gọi khi người dùng mở app lần thứ hai (SingleInstance báo sang). Không
        dùng show_panel() vì hàm đó bỏ qua khi `_visible` đang True — mà đúng
        tình huống này người dùng bấm lại chính vì không thấy cửa sổ đâu.
        """
        if self.window is None:
            return
        if self._compact:
            self.expand_from_browser_icon()
            return
        try:
            self.window.show()
        except Exception:
            pass
        if self._stick_to_browser:
            self._dock_to_browser()
        _bring_process_window_to_front(on_top=self._always_on_top)
        self._visible = True

    def _on_closing(self):
        # window.destroy() (gọi từ quit(), tức tray "Thoát") cũng đi qua sự
        # kiện này trên Windows — chỉ chặn khi đây là lần đóng ngoài ý muốn
        # (Alt+F4, nút X hệ thống nếu có), thu về tray như nút đóng trong
        # panel. Trả về False để pywebview huỷ hành động đóng gốc; bỏ qua
        # (không trả False) khi đang thoát thật để "Thoát" vẫn hoạt động.
        if self._quitting:
            return None
        self.dismiss_panel()
        return False

    # -- lifecycle ---------------------------------------------------------
    def on_loaded(self):
        # Chạy nền: bơm trạng thái ban đầu + auto-login, không chặn UI.
        threading.Thread(target=self._startup, daemon=True).start()

    def _startup(self):
        update_result = None
        try:
            state = self.api.get_initial_state()
            import json
            self.window.evaluate_js(f"window.wfxBootstrap({json.dumps(state, ensure_ascii=False)})")
            threading.Thread(
                target=self.api.flush_error_reports,
                daemon=True,
            ).start()
            update_result = updater.consume_update_result()
            if update_result:
                self._push_log(
                    f"[UPDATE] {update_result.get('code')}: "
                    f"{update_result.get('message')}"
                )
            account = prefs.load_account()
            if account["user_id"] and account["password"]:
                self._push_log("[SESSION] Tự động đăng nhập...")
                result = self.api.login()
            else:
                result = self.api.check_session()
            tone = "success" if result.get("ok") else "warning"
            self._set_status(tone, result.get("message", ""))
            if update_result:
                tone = "success" if update_result.get("ok") else "warning"
                self._set_status(
                    tone, str(update_result.get("message") or "")
                )
        except Exception as error:  # startup không được làm sập app
            message = f"Lỗi khởi động: {error}"
            self._push_log(f"[ERROR] Startup lỗi: {error}")
            # Footer mặc định là "Đang kiểm tra..." và log overlay đóng theo
            # mặc định — nếu không cập nhật footer ở đây, người dùng sẽ thấy
            # trạng thái treo vĩnh viễn mà không biết vì sao.
            self._set_status("error", message)

        # Hotkey có thể đã đăng ký xong hoặc chưa tại thời điểm này (background()
        # chạy song song). Đợi tối đa 5s rồi báo lỗi hotkey (nếu có) — đây là lần
        # đầu tiên ta chắc chắn window.wfxSetStatus đã tồn tại.
        if self._hotkey_ready.wait(timeout=5) and self._hotkey_error:
            hotkey_message = (
                f"Không đăng ký được phím tắt {self._hotkey.upper()}: "
                f"{self._hotkey_error}. "
                "Hãy đóng và mở lại ứng dụng; có thể cần chạy với quyền Administrator."
            )
            self._push_log(f"[ERROR] {hotkey_message}")
            self._set_status("error", hotkey_message)
        if self._visible:
            self.activate()

    def _build_tray(self):
        image = Image.open(ICON_PATH)
        menu = pystray.Menu(
            pystray.MenuItem("Hiện panel", lambda: self.show_panel(), default=True),
            pystray.MenuItem("Thoát", lambda: self.quit()),
        )
        self.tray = pystray.Icon("wfx-panel", image, "WFX Smart Panel", menu)
        self.tray.run()  # blocking → chạy trong thread riêng

    def quit(self):
        self._quitting = True
        self._stop_status.set()
        try:
            keyboard.remove_hotkey(self._hotkey)
        except (KeyError, ValueError):
            pass
        if self.lock is not None:
            self.lock.close()
        if self.tray:
            self.tray.stop()
        if self.window:
            self.window.destroy()

    def run(self):
        if not ICON_PATH.exists():
            build_icon(ICON_PATH)
        # js_api expose các method của PanelAPI + hide/show cho nút close.
        self.api.hide_panel = self.hide_panel   # type: ignore[attr-defined]
        self.api.dismiss_panel = self.dismiss_panel  # type: ignore[attr-defined]
        self.api.collapse_to_browser_icon = self.collapse_to_browser_icon  # type: ignore[attr-defined]
        self.api.expand_from_browser_icon = self.expand_from_browser_icon  # type: ignore[attr-defined]
        self.api.begin_compact_drag = self.begin_compact_drag  # type: ignore[attr-defined]
        self.api.show_panel = self.show_panel   # type: ignore[attr-defined]
        self.api.set_log_sink(self._push_log)
        self.api.set_result_sink(self._on_result)
        self.api.set_hotkey_applier(self._apply_hotkey)
        self.api.set_update_applier(self._apply_update)
        self.api.set_window_pref_appliers(
            self._apply_always_on_top,
            self._apply_stick_to_browser,
        )

        original_set_toast = self.api.set_toast_enabled

        def set_toast(enabled):
            result = original_set_toast(enabled)
            self.set_toast_enabled_state(
                result.get("toast_enabled", enabled)
            )
            return result

        self.api.set_toast_enabled = set_toast  # type: ignore[method-assign]
        x, y = _top_right_position()
        self.window = webview.create_window(
            "WFX Smart",
            url=str(UI_INDEX),
            js_api=self.api,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=(COMPACT_SIZE, COMPACT_SIZE),
            x=x,
            y=y,
            frameless=True,
            easy_drag=False,
            on_top=self._always_on_top,
            hidden=self._start_hidden,
            background_color="#0b1020",
        )
        self._visible = not self._start_hidden
        self.window.events.loaded += self.on_loaded
        self.window.events.closing += self._on_closing

        def background():
            # Chạy song song lúc trang đang tải; window.wfxSetStatus/wfxPushLog
            # có thể chưa tồn tại nên không gọi evaluate_js ở đây — chỉ ghi lỗi
            # vào state, _startup() sẽ báo lại khi trang chắc chắn đã sẵn sàng.
            try:
                keyboard.add_hotkey(self._hotkey, self.toggle)
            except Exception as error:
                self._hotkey_error = str(error)
            finally:
                self._hotkey_ready.set()
            threading.Thread(target=self._status_loop, daemon=True).start()
            threading.Thread(
                target=self._window_follow_loop, daemon=True
            ).start()
            threading.Thread(target=self._update_loop, daemon=True).start()
            self._build_tray()

        # UI là file đóng gói và state thật nằm trong prefs/.env riêng. Dùng
        # WebView riêng tư để bản app mới không tái sử dụng HTML/CSS/zoom cache
        # của bản cũ — nguyên nhân từng làm UI khác index.html và bị tràn.
        webview.start(background, private_mode=True)


def main():
    app = PanelApp()
    lock = SingleInstance(app.activate)
    if not lock.acquire():
        if lock.signal_existing():
            # Đã có instance đang chạy: bật panel của nó lên rồi thoát im lặng.
            return
        # Cổng bị một chương trình khác giữ (không trả đúng handshake). Không
        # được chặn người dùng mở app vì lý do không liên quan — chạy tiếp,
        # chấp nhận mất khả năng chặn trùng trong phiên này.
    app.lock = lock
    app.run()


if __name__ == "__main__":
    main()
