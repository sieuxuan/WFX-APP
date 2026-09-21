"""Bubble 48×48 và menu chuột phải của nó.

Native bounds phải scale theo DPI của HWND (48/60/72/96 physical tại
100/125/150/200%), kể cả khi cửa sổ đang hidden. WebView đôi khi bỏ lỡ sự
kiện ``contextmenu`` nên phải có fallback Win32 bắt chuột phải; menu là một
tool-window pywebview riêng, chỉ tạo khi người dùng mở lần đầu và không
dùng ``TrackPopupMenu`` đồng bộ từ worker/WebView thread."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import webview

if TYPE_CHECKING:
    from wfx_panel.panel_app import PanelApp

from wfx_panel import crash_log, prefs
from wfx_panel.app.bridges import _BubbleMenuBridge
from wfx_panel.app.layout import (
    BUBBLE_CONTEXT_POLL_SECONDS,
    BUBBLE_DIRECT_ACTION_SUPPRESS_SECONDS,
    BUBBLE_MENU_GAP,
    BUBBLE_MENU_HEIGHT,
    BUBBLE_MENU_INDEX,
    BUBBLE_MENU_WIDTH,
    BUBBLE_SIZE,
    WINDOW_MARGIN,
)
from wfx_panel.win32_window import (
    BUBBLE_MENU_TITLE,
    BUBBLE_WINDOW_TITLE,
    _clamp_to_work_area,
    _find_window_hwnd,
    _mouse_buttons_state_over_hwnd,
    _native_popup_visibility,
    _native_window_visibility,
    _right_mouse_state_over_hwnd,
    _scale_logical_size,
    _set_bounds_by_title,
    _set_smooth_corners_by_title,
    _window_dpi_by_title,
    _window_rect_by_title,
    _window_rect_by_title_any_state,
    _work_area_for_window_title,
    _work_area_for_window_title_any_state,
)


class BubbleController:
    def __init__(self, app: PanelApp) -> None:
        self._app = app


    def _restore_bubble(self) -> None:
        """Hiện hoặc restore launcher, kể cả khi đang minimized ở taskbar."""
        app = self._app
        restored = _native_window_visibility(
            BUBBLE_WINDOW_TITLE,
            True,
            on_top=app._always_on_top,
        )
        if not restored and app.bubble_window is not None:
            try:
                app.bubble_window.show()
                app.bubble_window.on_top = app._always_on_top
            except Exception:
                pass
        self._schedule_bubble_native_bounds()
        app._bubble_hidden = False

    def note_bubble_interaction(self) -> dict:
        """Đánh dấu click/drag trực tiếp để monitor taskbar không toggle lần hai."""
        app = self._app
        app._bubble_direct_action_until = (
            time.monotonic() + BUBBLE_DIRECT_ACTION_SUPPRESS_SECONDS
        )
        return {"ok": True, "code": "BUBBLE_INTERACTION_NOTED"}

    def begin_bubble_interaction(self) -> dict:
        """Giữ taskbar monitor đứng yên trong suốt thao tác click/kéo."""
        app = self._app
        app._bubble_pointer_down = True
        app._bubble_pointer_started = time.monotonic()
        app._taskbar_focus_armed = False
        crash_log.record("BUBBLE_INTERACTION_BEGIN")
        return {"ok": True, "code": "BUBBLE_INTERACTION_STARTED"}

    def end_bubble_interaction(self) -> dict:
        app = self._app
        app._bubble_pointer_down = False
        app._bubble_pointer_started = 0.0
        app._bubble_direct_action_until = (
            time.monotonic() + BUBBLE_DIRECT_ACTION_SUPPRESS_SECONDS
        )
        crash_log.record("BUBBLE_INTERACTION_END")
        return {"ok": True, "code": "BUBBLE_INTERACTION_ENDED"}

    def _bubble_interaction_active(self) -> bool:
        app = self._app
        if not app._bubble_pointer_down:
            return False
        # Fail-safe nếu WebView2 nuốt mouseup/blur trong một native move-loop.
        if time.monotonic() - app._bubble_pointer_started <= 30.0:
            return True
        app._bubble_pointer_down = False
        app._bubble_pointer_started = 0.0
        crash_log.record("BUBBLE_INTERACTION_TIMEOUT")
        return False

    def save_bubble_position(self) -> dict:
        """Lưu vị trí sau native pywebview drag và giữ bubble trong màn hình."""
        app = self._app
        # Khi kéo qua màn hình có scale khác, resize trước rồi mới lưu tọa độ.
        self._enforce_bubble_native_bounds()
        rect = _window_rect_by_title(BUBBLE_WINDOW_TITLE)
        area = _work_area_for_window_title(BUBBLE_WINDOW_TITLE)
        if rect is None:
            return {
                "ok": False,
                "code": "BUBBLE_POSITION_UNAVAILABLE",
                "message": "Không đọc được vị trí icon WFX.",
            }
        width = max(1, rect[2] - rect[0])
        height = max(1, rect[3] - rect[1])
        x, y = _clamp_to_work_area(rect[0], rect[1], width, height, area)
        if (x, y) != (rect[0], rect[1]):
            _set_bounds_by_title(BUBBLE_WINDOW_TITLE, x, y, width, height)
        app._bubble_offset = (x, y)
        prefs.save_prefs(compact_offset_x=x, compact_offset_y=y)
        return {
            "ok": True,
            "code": "BUBBLE_POSITION_SAVED",
            "message": "Đã lưu vị trí icon WFX.",
            "x": x,
            "y": y,
        }

    def _ensure_bubble_menu_window(self) -> bool:
        """Chỉ tạo WebView menu khi user thật sự bấm chuột phải bubble."""
        app = self._app
        if app.bubble_menu_window is not None:
            return True
        if not app._bubble_menu_destroyed.wait(timeout=2):
            return False
        created: list[object] = []
        errors: list[Exception] = []
        ready = threading.Event()

        def create_menu_window() -> None:
            try:
                window = webview.create_window(
                    BUBBLE_MENU_TITLE,
                    url=str(BUBBLE_MENU_INDEX),
                    js_api=_BubbleMenuBridge(self),
                    width=BUBBLE_MENU_WIDTH,
                    height=BUBBLE_MENU_HEIGHT,
                    x=-32000,
                    y=-32000,
                    min_size=(1, 1),
                    resizable=False,
                    frameless=True,
                    easy_drag=False,
                    on_top=True,
                    hidden=True,
                    background_color="#f7fafb",
                    shadow=False,
                )
                created.append(window)
            except Exception as error:
                errors.append(error)
            finally:
                ready.set()

        threading.Thread(
            target=create_menu_window,
            name="wfx-bubble-menu-create",
            daemon=True,
        ).start()
        if not ready.wait(5) or not created:
            detail = type(errors[0]).__name__ if errors else "Timeout"
            app.api._log(f"[BUBBLE] Không tạo được menu: {detail}.")
            return False
        window = created[0]
        app.bubble_menu_window = window
        window.events.loaded += self._on_bubble_menu_loaded
        window.events.closing += self._on_bubble_menu_closing
        return True

    def bubble_context_menu(self) -> dict:
        """Hiện popup menu tách riêng để không bị Win32 dismiss tức thì."""
        app = self._app
        if not app._bubble_menu_lock.acquire(blocking=False):
            return {
                "ok": True,
                "code": "MENU_ALREADY_OPEN",
                "message": "Menu bubble đang mở.",
            }
        try:
            now = time.monotonic()
            if app._bubble_menu_visible and now - app._bubble_menu_last_opened < 0.5:
                return {
                    "ok": True,
                    "code": "MENU_ALREADY_OPEN",
                    "message": "Menu bubble đang mở.",
                }
            if not self._ensure_bubble_menu_window():
                return {
                    "ok": False,
                    "code": "MENU_NOT_READY",
                    "message": "Menu bubble chưa sẵn sàng.",
                }
            x, y, width, height = self._bubble_menu_position()
            crash_log.record("BUBBLE_CONTEXT_MENU_OPEN")
            native_shown = _native_popup_visibility(
                BUBBLE_MENU_TITLE,
                True,
                x,
                y,
                width,
                height,
                activate=True,
            )
            shown = native_shown
            fallback_error = ""
            if not shown:
                try:
                    app.bubble_menu_window.resize(BUBBLE_MENU_WIDTH, BUBBLE_MENU_HEIGHT)
                    app.bubble_menu_window.move(x, y)
                    app.bubble_menu_window.show()
                    shown = True
                except Exception as error:
                    fallback_error = str(error)
                    shown = False
            if shown:
                _set_smooth_corners_by_title(BUBBLE_MENU_TITLE)
            crash_log.record(
                "BUBBLE_CONTEXT_MENU_RESULT",
                shown=shown,
                native_shown=native_shown,
                x=x,
                y=y,
                width=width,
                height=height,
                fallback_error=fallback_error,
            )
            app._bubble_menu_visible = shown
            app._bubble_menu_last_opened = now
            return {
                "ok": shown,
                "code": "MENU_OPENED" if shown else "MENU_OPEN_FAILED",
                "message": "Đã mở menu bubble." if shown else "Không mở được menu bubble.",
            }
        finally:
            app._bubble_menu_lock.release()

    def _bubble_menu_position(self) -> tuple[int, int, int, int]:
        bubble = _window_rect_by_title(BUBBLE_WINDOW_TITLE)
        area = _work_area_for_window_title(BUBBLE_WINDOW_TITLE)
        dpi = _window_dpi_by_title(BUBBLE_WINDOW_TITLE)
        width, height = _scale_logical_size(
            BUBBLE_MENU_WIDTH, BUBBLE_MENU_HEIGHT, dpi
        )
        if bubble is None or area is None:
            return WINDOW_MARGIN, WINDOW_MARGIN, width, height
        right_x = bubble[2] + BUBBLE_MENU_GAP
        left_x = bubble[0] - width - BUBBLE_MENU_GAP
        x = right_x if right_x + width <= area[2] else left_x
        x, y = _clamp_to_work_area(x, bubble[1], width, height, area)
        return x, y, width, height

    def dismiss_bubble_menu(self) -> dict:
        app = self._app
        _native_popup_visibility(BUBBLE_MENU_TITLE, False)
        window, app.bubble_menu_window = app.bubble_menu_window, None
        if window is not None:
            try:
                window.hide()
            except Exception:
                pass
            app._bubble_menu_destroying = True
            app._bubble_menu_destroyed.clear()

            def destroy_menu() -> None:
                try:
                    window.destroy()
                except Exception:
                    pass
                finally:
                    app._bubble_menu_destroying = False
                    app._bubble_menu_destroyed.set()

            threading.Thread(
                target=destroy_menu,
                name="wfx-bubble-menu-destroy",
                daemon=True,
            ).start()
        app._bubble_menu_visible = False
        return {"ok": True, "code": "MENU_DISMISSED", "message": "Đã đóng menu."}

    def choose_bubble_menu(self, action: str) -> dict:
        app = self._app
        self.dismiss_bubble_menu()
        crash_log.record("BUBBLE_CONTEXT_MENU_CHOICE", choice=action)
        if action == "taskbar":
            return app.minimize_to_taskbar()
        if action == "tray":
            app.hide_to_tray()
            return {
                "ok": True,
                "code": "HIDDEN_TO_TRAY",
                "message": "Đã ẩn WFX Smart xuống khay hệ thống.",
            }
        return {
            "ok": False,
            "code": "MENU_ACTION_INVALID",
            "message": "Lựa chọn menu không hợp lệ.",
        }

    def _bubble_context_menu_loop(self) -> None:
        """Bắt chuột phải và đóng menu khi click ra ngoài bằng một poll loop."""
        app = self._app
        bubble_hwnd: int | None = None
        menu_hwnd: int | None = None
        menu_input_released = False
        was_down = False
        armed = False
        while not app._stop_status.wait(BUBBLE_CONTEXT_POLL_SECONDS):
            if app._bubble_menu_visible:
                if menu_hwnd is None:
                    menu_hwnd = _find_window_hwnd(BUBBLE_MENU_TITLE)
                if menu_hwnd is not None:
                    menu_down, menu_over = _mouse_buttons_state_over_hwnd(menu_hwnd)
                    if not menu_input_released:
                        # Bỏ qua chính click vừa mở menu. Chỉ arm sau khi mọi
                        # nút đã nhả, tránh menu tự đóng ngay trên một số máy.
                        menu_input_released = not menu_down
                    elif menu_down and not menu_over:
                        crash_log.record("BUBBLE_CONTEXT_MENU_OUTSIDE_DISMISS")
                        self.dismiss_bubble_menu()
                        menu_hwnd = None
                        menu_input_released = False
            else:
                menu_hwnd = None
                menu_input_released = False

            if bubble_hwnd is None:
                bubble_hwnd = _find_window_hwnd(BUBBLE_WINDOW_TITLE)
                if bubble_hwnd is None:
                    continue
            down, over = _right_mouse_state_over_hwnd(bubble_hwnd)
            if down and not was_down:
                armed = over
            elif not down and was_down:
                if armed and over and not app._bubble_hidden:
                    self.note_bubble_interaction()
                    self.bubble_context_menu()
                armed = False
            was_down = down

    def _bubble_start_position(self) -> tuple[int, int]:
        """Vị trí bubble lúc khởi động: chỗ đã lưu, hoặc góc trên-phải màn hình."""
        app = self._app
        if app._bubble_offset is not None:
            return app._bubble_offset
        try:
            screen_width = int(webview.screens[0].width)
        except Exception:
            screen_width = 1920
        x = max(WINDOW_MARGIN, screen_width - BUBBLE_SIZE - WINDOW_MARGIN)
        return x, 120

    def _enforce_bubble_native_bounds(self) -> bool:
        """Giữ bubble 48 logical px theo DPI của đúng màn hình hiện tại.

        Không chỉ tin giá trị trả về của ``SetWindowPos``: WinForms có thể báo
        thành công nhưng vẫn giữ minimum tracking size 120×39. Luôn đọc rect
        sau cùng để scheduler biết còn phải retry.
        """
        app = self._app
        rect = _window_rect_by_title_any_state(BUBBLE_WINDOW_TITLE)
        area = _work_area_for_window_title_any_state(BUBBLE_WINDOW_TITLE)
        if rect is None or area is None:
            return False
        dpi = _window_dpi_by_title(BUBBLE_WINDOW_TITLE)
        target_width, target_height = _scale_logical_size(
            BUBBLE_SIZE, BUBBLE_SIZE, dpi
        )
        x, y = _clamp_to_work_area(
            rect[0], rect[1], target_width, target_height, area
        )
        # create_window dùng logical pixels; SetWindowPos dùng physical pixels.
        # Vì vậy 48 logical tương ứng 48/60/72/96 physical ở 100/125/150/200%.
        resized = _set_bounds_by_title(
            BUBBLE_WINDOW_TITLE, x, y, target_width, target_height
        )
        if not resized:
            return False
        # Cửa sổ opaque nhận hit-test ổn định; DWM bo góc anti-aliased mà
        # không cần TransparencyKey/WS_EX_LAYERED hay region răng cưa.
        _set_smooth_corners_by_title(BUBBLE_WINDOW_TITLE)
        actual = _window_rect_by_title_any_state(BUBBLE_WINDOW_TITLE)
        if (
            actual is None
            or actual[2] - actual[0] != target_width
            or actual[3] - actual[1] != target_height
        ):
            return False
        if (x, y) != (rect[0], rect[1]):
            app._bubble_offset = (x, y)
            prefs.save_prefs(compact_offset_x=x, compact_offset_y=y)
        return True

    def _schedule_bubble_native_bounds(self) -> None:
        """Ép lại kích thước sau cả load lẫn show từ trạng thái khởi động ẩn."""
        app = self._app
        if self._enforce_bubble_native_bounds():
            return

        def retry_native_size() -> None:
            # Một số máy phát sự kiện loaded trước khi HWND tra được theo title.
            # Mỗi loaded/show/restore được quyền tạo một lượt retry riêng để
            # không mất tín hiệu đúng lúc thread cũ vừa hết hạn.
            for _attempt in range(20):
                time.sleep(0.1)
                if self._enforce_bubble_native_bounds():
                    return

        app._bubble_size_thread = threading.Thread(
            target=retry_native_size,
            name="wfx-bubble-native-size",
            daemon=True,
        )
        app._bubble_size_thread.start()

    def _on_bubble_minimized(self) -> None:
        app = self._app
        # Event minimized do chính menu bubble yêu cầu không được lập tức mở
        # panel trở lại.
        if app._taskbar_minimize_requested:
            app._taskbar_minimize_requested = False
            return
        self._on_bubble_taskbar_event()

    def _on_bubble_restored(self) -> None:
        app = self._app
        # Nếu backend không phát minimized, restored vẫn phải mở ngay từ lần
        # click taskbar đầu tiên thay vì chỉ tiêu thụ cờ/debounce của menu cũ.
        app._taskbar_minimize_requested = False
        app._bubble_direct_action_until = 0.0
        self._on_bubble_taskbar_event()

    def _on_bubble_taskbar_event(self) -> None:
        app = self._app
        # Callback GUI phải trả nhanh; restore/show có thể phát event lồng nhau.
        threading.Thread(
            target=app._open_panel_from_taskbar, daemon=True
        ).start()

    def _on_bubble_loaded(self) -> None:
        """Giữ bubble đúng 48px logical, kể cả khi WebView2 tạo HWND chậm."""
        self._schedule_bubble_native_bounds()

    def _on_bubble_menu_loaded(self) -> None:
        # Menu giờ chỉ được tạo đúng lúc user mở. Không ẩn trong callback
        # loaded: lần show đầu tiên có thể phát loaded muộn và tự đóng menu.
        _set_smooth_corners_by_title(BUBBLE_MENU_TITLE)

    def _on_bubble_closing(self):
        app = self._app
        # Bubble bị đóng ngoài ý muốn → thu vào tray thay vì hủy cửa sổ.
        if app._quitting:
            return None
        app.hide_to_tray()
        return False

    def _on_bubble_menu_closing(self):
        app = self._app
        if app._quitting or app._bubble_menu_destroying:
            return None
        self.dismiss_bubble_menu()
        return False
