"""Hiện, thu và định vị cửa sổ panel so với bubble, tray và taskbar.

Panel tự thu khi mất focus, KỂ CẢ khi automation đang chạy, để user xem
Chrome mà không dừng task. Ngoài ``window.blur`` phải có monitor foreground
Win32 làm fallback vì WebView2 đôi khi bỏ lỡ blur — và không được thu panel
chỉ vì automation vừa đưa Chrome lên foreground khi con trỏ vẫn đang thao
tác trong UI."""

from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_app import PanelApp

from wfx_panel import crash_log
from wfx_panel.app.helpers import _top_right_position
from wfx_panel.app.layout import (
    BUBBLE_PANEL_GAP,
    PANEL_BLUR_GRACE_SECONDS,
    TASKBAR_ACTIVATION_POLL_SECONDS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from wfx_panel.win32_window import (
    BUBBLE_WINDOW_TITLE,
    MAIN_WINDOW_TITLE,
    _bring_process_window_to_front,
    _clamp_to_work_area,
    _find_window_hwnd,
    _foreground_process_id,
    _foreground_window_hwnd,
    _native_window_visibility,
    _scale_logical_size,
    _set_process_window_bounds,
    _unscale_physical_size,
    _window_dpi_by_title,
    _window_rect_by_title,
    _work_area_for_process_window,
    _work_area_for_window_title,
)


class PanelPlacementController:
    def __init__(self, app: PanelApp) -> None:
        self._app = app


    def hide_panel(self):
        app = self._app
        if (
            app.window is not None
            and app._panel_visible
            and not _native_window_visibility(MAIN_WINDOW_TITLE, False)
        ):
            try:
                app.window.hide()
            except Exception:
                pass
        app._panel_visible = False
        app._panel_pointer_inside = False
        app._panel_hide_pending = False
        app._panel_focus_lost_since = 0.0

    def set_panel_pointer_inside(self, inside: bool) -> dict:
        """Đồng bộ hover WebView cho cơ chế auto-hide native."""
        app = self._app
        app._panel_pointer_inside = bool(inside)
        if app._panel_pointer_inside:
            app._panel_hide_pending = False
            app._panel_focus_lost_since = 0.0
        return {
            "ok": True,
            "code": (
                "PANEL_POINTER_INSIDE"
                if app._panel_pointer_inside
                else "PANEL_POINTER_OUTSIDE"
            ),
        }

    def show_panel(self) -> dict:
        """Bung panel cạnh bubble (bubble vẫn hiện)."""
        app = self._app
        if app.window is None:
            return {
                "ok": False,
                "code": "PANEL_NOT_READY",
                "message": "Panel chưa sẵn sàng.",
            }
        try:
            if not app._panel_visible:
                if not _native_window_visibility(
                    MAIN_WINDOW_TITLE,
                    True,
                    on_top=app._always_on_top,
                ):
                    try:
                        app.window.show()
                    except Exception:
                        pass
                app._panel_visible = True
            # Đặt bounds sau khi show để Win32 chắc chắn thấy HWND panel và
            # dùng cùng hệ tọa độ physical với bubble (quan trọng khi DPI khác
            # nhau giữa hai màn hình).
            self._position_panel_beside_bubble()
            if not _native_window_visibility(
                MAIN_WINDOW_TITLE,
                True,
                on_top=app._always_on_top,
            ):
                try:
                    app.window.on_top = app._always_on_top
                except Exception:
                    pass
            _bring_process_window_to_front(on_top=app._always_on_top)
            self._focus_module_search()
            return {
                "ok": True,
                "code": "PANEL_OPENED",
                "message": "Đã mở WFX Smart.",
            }
        except Exception as error:
            return {
                "ok": False,
                "code": "PANEL_OPEN_FAILED",
                "message": f"Không mở được panel: {error}",
            }

    def toggle_panel(self) -> dict:
        """Bấm bubble: đang mở thì thu, đang ẩn thì bung."""
        app = self._app
        if app._panel_visible:
            self.hide_panel()
            return {"ok": True, "code": "PANEL_HIDDEN", "message": "Đã thu panel."}
        return self.show_from_tray()

    def _position_panel_beside_bubble(self) -> None:
        """Đặt panel cạnh bubble và giữ toàn bộ trong cùng một màn hình."""
        app = self._app
        bubble = _window_rect_by_title(BUBBLE_WINDOW_TITLE)
        # Panel đang ẩn nên helper theo process có thể không tìm thấy nó. Lấy
        # monitor trực tiếp từ HWND bubble mới là nguồn chuẩn.
        area = _work_area_for_window_title(BUBBLE_WINDOW_TITLE)
        if area is None:
            area = _work_area_for_process_window(os.getpid())

        dpi = _window_dpi_by_title(BUBBLE_WINDOW_TITLE)
        width, height = _scale_logical_size(
            WINDOW_WIDTH,
            WINDOW_HEIGHT,
            dpi,
        )
        if area is not None:
            # Với màn hình/work area nhỏ hơn panel chuẩn, co cửa sổ vừa đúng
            # work area để không có cạnh nào tràn sang màn hình khác/taskbar.
            width = min(width, max(1, area[2] - area[0]))
            height = min(height, max(1, area[3] - area[1]))

        if bubble is not None:
            left_x = bubble[0] - width - BUBBLE_PANEL_GAP
            right_x = bubble[2] + BUBBLE_PANEL_GAP
            if area is not None:
                fits_left = left_x >= area[0]
                fits_right = right_x + width <= area[2]
                if fits_left != fits_right:
                    x = left_x if fits_left else right_x
                elif fits_left:
                    # Cả hai phía đều đủ: mở về phía có nhiều khoảng trống hơn.
                    bubble_mid = (bubble[0] + bubble[2]) // 2
                    screen_mid = (area[0] + area[2]) // 2
                    x = left_x if bubble_mid >= screen_mid else right_x
                else:
                    # Không phía nào đủ nguyên vẹn: chọn phía rộng hơn rồi clamp.
                    left_space = bubble[0] - area[0]
                    right_space = area[2] - bubble[2]
                    x = left_x if left_space >= right_space else right_x
            else:
                x = left_x if bubble[0] >= width else right_x
            y = bubble[1]
        else:
            x, y = _top_right_position()
        x, y = _clamp_to_work_area(x, y, width, height, area)
        if not _set_process_window_bounds(os.getpid(), x, y, width, height):
            try:
                logical_width, logical_height = _unscale_physical_size(
                    width,
                    height,
                    dpi,
                )
                app.window.resize(logical_width, logical_height)
                app.window.move(x, y)
            except Exception:
                pass

    def request_panel_hide(self) -> dict:
        """Panel mất focus (click ra ngoài) → tự thu; giữ lại nếu focus vẫn
        trong app (bấm chính bubble/toast) hoặc panel đã ẩn."""
        app = self._app
        if not app._panel_visible:
            return {"ok": True, "code": "PANEL_ALREADY_HIDDEN"}
        if app._panel_pointer_inside:
            app._panel_hide_pending = False
            app._panel_focus_lost_since = 0.0
            return {"ok": True, "code": "PANEL_POINTER_KEPT"}
        foreground = _foreground_process_id()
        if foreground is not None and foreground == os.getpid():
            return {"ok": True, "code": "PANEL_FOCUS_KEPT"}
        self.hide_panel()
        return {"ok": True, "code": "PANEL_HIDDEN_ON_BLUR"}

    def _track_panel_foreground(self, foreground_pid: int | None) -> None:
        """Fallback native khi WebView2 bỏ lỡ sự kiện ``window.blur``."""
        app = self._app
        if not app._panel_visible:
            app._panel_focus_lost_since = 0.0
            app._panel_hide_pending = False
            return
        if app._panel_pointer_inside:
            app._panel_focus_lost_since = 0.0
            app._panel_hide_pending = False
            return
        if foreground_pid is None or foreground_pid == os.getpid():
            app._panel_focus_lost_since = 0.0
            app._panel_hide_pending = False
            return

        now = time.monotonic()
        if app._panel_hide_pending or (
            app._panel_focus_lost_since > 0
            and now - app._panel_focus_lost_since >= PANEL_BLUR_GRACE_SECONDS
        ):
            crash_log.record("PANEL_HIDDEN_NATIVE_BLUR")
            self.hide_panel()
            app._panel_hide_pending = False
            app._panel_focus_lost_since = 0.0
            return
        if app._panel_focus_lost_since <= 0:
            app._panel_focus_lost_since = now

    def minimize_to_taskbar(self) -> dict:
        """Thu bubble xuống taskbar; click taskbar sẽ mở lại toàn bộ UI."""
        app = self._app
        if app._bubble_menu_visible:
            app.dismiss_bubble_menu()
        self.hide_panel()
        if app.bubble_window is None:
            return {
                "ok": False,
                "code": "BUBBLE_NOT_READY",
                "message": "Icon WFX chưa sẵn sàng để thu xuống taskbar.",
            }
        app._taskbar_minimize_requested = True
        app._bubble_hidden = False
        try:
            app.bubble_window.minimize()
        except Exception as error:
            app._taskbar_minimize_requested = False
            return {
                "ok": False,
                "code": "TASKBAR_MINIMIZE_FAILED",
                "message": f"Không thu được WFX Smart xuống taskbar: {error}",
            }
        return {
            "ok": True,
            "code": "HIDDEN_TO_TASKBAR",
            "message": "Đã thu WFX Smart xuống taskbar.",
        }

    def hide_to_tray(self) -> None:
        """Giấu cả panel lẫn bubble; chỉ còn icon khay hệ thống."""
        app = self._app
        if app._bubble_menu_visible:
            app.dismiss_bubble_menu()
        self.hide_panel()
        if app.bubble_window is not None:
            try:
                app.bubble_window.hide()
            except Exception:
                pass
        app._bubble_hidden = True

    def show_from_tray(self) -> dict:
        """Khôi phục cả bubble lẫn panel từ tray, taskbar hoặc hotkey."""
        app = self._app
        app._restore_bubble()
        return self.show_panel()

    def _apply_always_on_top(self, enabled: bool) -> None:
        app = self._app
        app._always_on_top = bool(enabled)
        for title, window in (
            (MAIN_WINDOW_TITLE, app.window),
            (BUBBLE_WINDOW_TITLE, app.bubble_window),
        ):
            if window is not None and not _native_window_visibility(
                    title,
                    True,
                    on_top=app._always_on_top,
                ):
                try:
                    window.on_top = app._always_on_top
                except Exception:
                    pass

    def _open_panel_from_taskbar(self) -> None:
        """Khôi phục bubble và mở toàn bộ UI khi kích hoạt từ taskbar."""
        app = self._app
        with app._taskbar_open_lock:
            if (
                app._taskbar_opening
                or app._bubble_hidden
                or app._bubble_interaction_active()
                or time.monotonic() < app._bubble_direct_action_until
            ):
                return
            app._taskbar_opening = True
        crash_log.record("TASKBAR_OPEN_BEGIN")
        completed = threading.Event()
        threading.Thread(
            target=crash_log.watch_for_hang,
            args=(completed, "TASKBAR_OPEN_HANG"),
            daemon=True,
        ).start()
        try:
            # Bubble đang visible vì _bubble_hidden đã được guard ở trên.
            # Không gọi restore/show qua WinForms Invoke từ thread monitor:
            # thao tác đó từng gây AppHangB1 khi trùng native drag/input-loop.
            app._restore_bubble()
            self.show_panel()
        finally:
            completed.set()
            app._taskbar_opening = False
            crash_log.record("TASKBAR_OPEN_END")

    def _taskbar_activation_loop(self) -> None:
        """Chỉ mở UI khi foreground chuyển từ app khác sang đúng HWND bubble."""
        app = self._app
        while not app._stop_status.wait(TASKBAR_ACTIVATION_POLL_SECONDS):
            try:
                foreground_pid = _foreground_process_id()
                foreground_hwnd = _foreground_window_hwnd()
                bubble_hwnd = _find_window_hwnd(BUBBLE_WINDOW_TITLE)
                panel_hwnd = _find_window_hwnd(MAIN_WINDOW_TITLE)
                self._track_panel_foreground(foreground_pid)
                if foreground_pid is not None and foreground_pid != os.getpid():
                    app._taskbar_focus_armed = True
                elif (
                    foreground_pid == os.getpid()
                    and foreground_hwnd in {bubble_hwnd, panel_hwnd}
                    and app._taskbar_focus_armed
                ):
                    app._taskbar_focus_armed = False
                    if app._bubble_interaction_active():
                        crash_log.record(
                            "TASKBAR_OPEN_SUPPRESSED_FOR_BUBBLE",
                            foreground_hwnd=foreground_hwnd,
                            bubble_hwnd=bubble_hwnd,
                        )
                    else:
                        # Windows có thể đưa HWND panel/WebView con lên foreground,
                        # không nhất thiết đúng top-level HWND của bubble.
                        crash_log.record(
                            "TASKBAR_ACTIVATED",
                            foreground_hwnd=foreground_hwnd,
                            bubble_hwnd=bubble_hwnd,
                            panel_hwnd=panel_hwnd,
                        )
                        self._open_panel_from_taskbar()
                elif foreground_pid == os.getpid():
                    # Menu pystray cũng thuộc process này. Hủy trạng thái chờ để
                    # đóng menu tray không bị hiểu nhầm thành click taskbar.
                    app._taskbar_focus_armed = False
            except Exception:
                continue

    def _focus_module_search(self) -> None:
        app = self._app
        if app.window is None:
            return
        try:
            app.window.evaluate_js(
                "window.setTimeout(() => window.wfxFocusModuleSearch?.(), 60)"
            )
        except Exception:
            pass

    def focus_automation_browser(self) -> dict:
        app = self._app
        if not app._focus_chrome_on_module:
            return {
                "ok": True,
                "code": "CHROME_FOCUS_DISABLED",
                "message": "Đã tắt tự động đưa Chrome lên trước.",
            }
        pid_getter = getattr(
            app.api._login, "automation_browser_pid", None
        )
        browser_pid = pid_getter() if callable(pid_getter) else None
        focused = _bring_process_window_to_front(
            browser_pid, on_top=None
        )
        return {
            "ok": focused,
            "code": "CHROME_FOCUSED" if focused else "CHROME_WINDOW_NOT_FOUND",
            "message": (
                "Đã đưa cửa sổ WFX lên trước."
                if focused
                else "Chưa tìm thấy cửa sổ trình duyệt làm việc."
            ),
        }
