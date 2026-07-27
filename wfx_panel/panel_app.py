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
from wfx_panel.win32_window import (
    BUBBLE_WINDOW_TITLE,
    MAIN_WINDOW_TITLE,
    NOTIFICATION_HEIGHT,
    NOTIFICATION_TITLE,
    NOTIFICATION_WIDTH,
    _bring_process_window_to_front,
    _clamp_to_work_area,
    _find_window_hwnd,
    _foreground_process_id,
    _move_hwnd,
    _native_compact_context_choice,
    _native_cursor_position,
    _native_left_button_down,
    _native_notification_visibility,
    _set_bounds_by_title,
    _set_process_window_bounds,
    _window_rect_by_title,
    _work_area_for_process_window,
    _work_area_for_window_title,
)

HOTKEY = hotkey.DEFAULT
STATUS_POLL_SECONDS = 5
UPDATE_INITIAL_DELAY_SECONDS = 1
UPDATE_POLL_SECONDS = 4 * 60 * 60
ICON_PATH = prefs.RESOURCE_DIR / "wfx_panel" / "assets" / "wfx.ico"
UI_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "index.html"
NOTIFICATION_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "notification.html"
BUBBLE_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "bubble.html"

WINDOW_WIDTH = 440
WINDOW_HEIGHT = 620
WINDOW_MARGIN = 24
# Khôi phục đúng kích thước launcher cũ; bubble chỉ tách thành cửa sổ riêng.
BUBBLE_SIZE = 48
BUBBLE_PANEL_GAP = 10
# NOTIFICATION_TITLE/WIDTH/HEIGHT sống ở win32_window (lớp native cần chúng);
# import lại phía trên để _notification_position và create_window dùng chung.
NOTIFICATION_MARGIN = 10
NOTIFICATION_SECONDS = 4.2
MODULE_NOTIFICATION_METHODS = frozenset(
    {
        "open_module",
        "prepare_catalog",
        "find_code",
        "find_buyer_reference",
        "open_sale_asn_new",
        "open_supplier_category",
        "find_supplier",
        "find_buyer",
    }
)


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


def _notification_position() -> tuple[int, int]:
    """Neo toast quanh bubble và giữ trọn trong đúng màn hình của bubble."""
    left, top, right, bottom = (0, 0, 1920, 1080)
    if os.name == "nt":
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
            if ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(rect), 0
            ):
                left, top, right, bottom = (
                    rect.left, rect.top, rect.right, rect.bottom
                )
        except Exception:
            pass
    else:
        try:
            screen = webview.screens[0]
            right, bottom = int(screen.width), int(screen.height)
        except Exception:
            pass

    # Neo toast quanh bubble (luôn hiển thị): ưu tiên nổi phía trên bubble,
    # canh phải mép bubble; nếu không đủ chỗ phía trên thì nổi ngay dưới.
    bubble = _window_rect_by_title(BUBBLE_WINDOW_TITLE)
    if bubble is not None:
        bubble_area = _work_area_for_window_title(BUBBLE_WINDOW_TITLE)
        if bubble_area is not None:
            left, top, right, bottom = bubble_area
        x = bubble[2] - NOTIFICATION_WIDTH
        above = bubble[1] - NOTIFICATION_HEIGHT - 8
        y = above if above >= top + NOTIFICATION_MARGIN else bubble[3] + 8
    else:
        x = right - NOTIFICATION_WIDTH - NOTIFICATION_MARGIN
        y = bottom - NOTIFICATION_HEIGHT - NOTIFICATION_MARGIN
    return (
        max(left + NOTIFICATION_MARGIN, min(x, right - NOTIFICATION_WIDTH - NOTIFICATION_MARGIN)),
        max(top + NOTIFICATION_MARGIN, min(y, bottom - NOTIFICATION_HEIGHT - NOTIFICATION_MARGIN)),
    )


class _NotificationBridge:
    def __init__(self, app: PanelApp):
        self._app = app

    def dismiss(self) -> dict:
        self._app._hide_notification()
        return {"ok": True}


class _BubbleBridge:
    """Cầu nối JS cho cửa sổ bubble (icon nổi thường trực)."""

    def __init__(self, app: PanelApp):
        self._app = app

    def toggle_panel(self) -> dict:
        return self._app.toggle_panel()

    def begin_bubble_drag(self) -> dict:
        return self._app.begin_bubble_drag()

    def bubble_context_menu(self) -> dict:
        return self._app.bubble_context_menu()


class PanelApp:
    def __init__(self):
        self.api = PanelAPI()
        self.window = None
        self.notification_window = None
        self.tray = None
        preferences = prefs.load_prefs()
        self._hotkey = preferences["hotkey"]
        self._toast_enabled = preferences["toast_enabled"]
        self._focus_chrome_on_module = preferences[
            "focus_chrome_on_module"
        ]
        self._always_on_top = preferences["always_on_top"]
        self._start_hidden = preferences["start_hidden"]
        self.bubble_window = None
        # Bubble (icon) là trạng thái nghỉ thường trực; panel mặc định ẩn và
        # chỉ bung ra khi bấm bubble, tự ẩn khi click ra ngoài.
        self._panel_visible = False
        self._bubble_hidden = self._start_hidden
        # Vị trí thường trực của bubble (physical Win32 coords) — tái dùng pref
        # compact_offset_*. None = chưa đặt tay → mặc định góc trên-phải.
        self._bubble_offset: tuple[int, int] | None = (
            (preferences["compact_offset_x"], preferences["compact_offset_y"])
            if preferences["compact_offset_x"] is not None
            and preferences["compact_offset_y"] is not None
            else None
        )
        self._bubble_drag_thread: threading.Thread | None = None
        self._notification_ready = threading.Event()
        self._notification_lock = threading.Lock()
        self._notification_generation = 0
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
        if self.window is not None and self._panel_visible:
            try:
                self.window.hide()
            except Exception:
                pass
        self._panel_visible = False

    def show_panel(self) -> dict:
        """Bung panel cạnh bubble (bubble vẫn hiện)."""
        if self.window is None:
            return {
                "ok": False,
                "code": "PANEL_NOT_READY",
                "message": "Panel chưa sẵn sàng.",
            }
        try:
            if not self._panel_visible:
                try:
                    self.window.show()
                except Exception:
                    pass
                self._panel_visible = True
            # Đặt bounds sau khi show để Win32 chắc chắn thấy HWND panel và
            # dùng cùng hệ toạ độ physical với bubble (quan trọng khi DPI khác
            # nhau giữa hai màn hình).
            self._position_panel_beside_bubble()
            try:
                self.window.on_top = self._always_on_top
            except Exception:
                pass
            _bring_process_window_to_front(on_top=self._always_on_top)
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
        if self._panel_visible:
            self.hide_panel()
            return {"ok": True, "code": "PANEL_HIDDEN", "message": "Đã thu panel."}
        return self.show_panel()

    def _position_panel_beside_bubble(self) -> None:
        """Đặt panel cạnh bubble và giữ toàn bộ trong cùng một màn hình."""
        bubble = _window_rect_by_title(BUBBLE_WINDOW_TITLE)
        # Panel đang ẩn nên helper theo process có thể không tìm thấy nó. Lấy
        # monitor trực tiếp từ HWND bubble mới là nguồn chuẩn.
        area = _work_area_for_window_title(BUBBLE_WINDOW_TITLE)
        if area is None:
            area = _work_area_for_process_window(os.getpid())

        width, height = WINDOW_WIDTH, WINDOW_HEIGHT
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
                self.window.resize(width, height)
                self.window.move(x, y)
            except Exception:
                pass

    def request_panel_hide(self) -> dict:
        """Panel mất focus (click ra ngoài) → tự thu; giữ lại nếu focus vẫn
        trong app (bấm chính bubble/toast) hoặc panel đã ẩn."""
        if not self._panel_visible:
            return {"ok": True, "code": "PANEL_ALREADY_HIDDEN"}
        foreground = _foreground_process_id()
        if foreground is not None and foreground == os.getpid():
            return {"ok": True, "code": "PANEL_FOCUS_KEPT"}
        self.hide_panel()
        return {"ok": True, "code": "PANEL_HIDDEN_ON_BLUR"}

    def begin_bubble_drag(self) -> dict:
        """Bắt đầu kéo bubble — cache HWND MỘT lần để vòng kéo không enum lại."""
        if (
            self._bubble_drag_thread is not None
            and self._bubble_drag_thread.is_alive()
        ):
            return {"ok": True, "code": "BUBBLE_DRAG_STARTED"}
        hwnd = _find_window_hwnd(BUBBLE_WINDOW_TITLE)
        cursor = _native_cursor_position()
        rect = _window_rect_by_title(BUBBLE_WINDOW_TITLE)
        started = bool(
            _native_left_button_down()
            and hwnd is not None
            and cursor is not None
            and rect is not None
        )
        if started:
            # Kéo bubble thì thu panel cho gọn.
            if self._panel_visible:
                self.hide_panel()
            self._bubble_drag_thread = threading.Thread(
                target=self._bubble_drag_loop,
                args=(hwnd, cursor, rect),
                daemon=True,
            )
            self._bubble_drag_thread.start()
        return {
            "ok": started,
            "code": "BUBBLE_DRAG_STARTED" if started else "BUBBLE_DRAG_FAILED",
            "message": (
                "Đang di chuyển icon WFX."
                if started
                else "Không thể di chuyển icon WFX."
            ),
        }

    def _bubble_drag_loop(
        self,
        hwnd: int,
        origin_cursor: tuple[int, int],
        origin_rect: tuple[int, int, int, int],
    ) -> None:
        """Theo con trỏ, dời thẳng HWND đã cache (SetWindowPos rẻ, không enum
        → hết lag). Cho đặt ở đâu cũng được, chỉ clamp để không lọt khỏi màn."""
        width = origin_rect[2] - origin_rect[0]
        height = origin_rect[3] - origin_rect[1]
        area = _work_area_for_window_title(BUBBLE_WINDOW_TITLE)
        if area is None:
            area = _work_area_for_process_window(os.getpid())
        last: tuple[int, int] | None = None
        while _native_left_button_down():
            cursor = _native_cursor_position()
            if cursor is None:
                break
            target_x = origin_rect[0] + cursor[0] - origin_cursor[0]
            target_y = origin_rect[1] + cursor[1] - origin_cursor[1]
            target_x, target_y = _clamp_to_work_area(
                target_x, target_y, width, height, area
            )
            _move_hwnd(hwnd, target_x, target_y)
            last = (target_x, target_y)
            time.sleep(0.008)
        if last is None:
            return
        self._bubble_offset = last
        prefs.save_prefs(compact_offset_x=last[0], compact_offset_y=last[1])

    def bubble_context_menu(self) -> dict:
        """Menu chuột phải trên bubble: ẩn vào tray / bật-tắt luôn trên cùng."""
        choice = _native_compact_context_choice(
            self._always_on_top, BUBBLE_WINDOW_TITLE
        )
        if choice == "hide":
            self.hide_to_tray()
            return {
                "ok": True,
                "code": "HIDDEN_TO_TRAY",
                "message": "Đã ẩn WFX Smart xuống khay hệ thống.",
            }
        if choice == "toggle_on_top":
            return self.api.set_always_on_top(not self._always_on_top)
        return {
            "ok": True,
            "code": "MENU_DISMISSED",
            "message": "Đã đóng menu.",
        }

    def hide_to_tray(self) -> None:
        """Giấu cả panel lẫn bubble; chỉ còn icon khay hệ thống."""
        self.hide_panel()
        if self.bubble_window is not None:
            try:
                self.bubble_window.hide()
            except Exception:
                pass
        self._bubble_hidden = True

    def show_from_tray(self) -> None:
        """Bật lại bubble (và mở panel) từ khay hệ thống."""
        if self.bubble_window is not None:
            try:
                self.bubble_window.show()
                self.bubble_window.on_top = self._always_on_top
            except Exception:
                pass
        self._bubble_hidden = False
        self.show_panel()

    def _focus_module_search(self) -> None:
        if self.window is None:
            return
        try:
            self.window.evaluate_js(
                "window.setTimeout(() => window.wfxFocusModuleSearch?.(), 60)"
            )
        except Exception:
            pass

    def toggle(self):
        """Hotkey: nếu đang ẩn hẳn trong tray thì bật lại, còn lại bung/thu panel."""
        if self._bubble_hidden:
            self.show_from_tray()
        else:
            self.toggle_panel()

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
        if not self._toast_enabled:
            self._hide_notification()

    def set_focus_chrome_on_module_state(self, enabled: bool) -> None:
        self._focus_chrome_on_module = bool(enabled)

    def focus_automation_browser(self) -> dict:
        if not self._focus_chrome_on_module:
            return {
                "ok": True,
                "code": "CHROME_FOCUS_DISABLED",
                "message": "Đã tắt tự động đưa Chrome lên trước.",
            }
        pid_getter = getattr(
            self.api._login, "automation_browser_pid", None
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
                else "Chưa tìm thấy cửa sổ browser automation."
            ),
        }

    def _notification_loaded(self) -> None:
        self._notification_ready.set()
        _native_notification_visibility(False)

    def _hide_notification(self, generation: int | None = None) -> None:
        with self._notification_lock:
            if (
                generation is not None
                and generation != self._notification_generation
            ):
                return
            self._notification_generation += 1
        if _native_notification_visibility(False):
            return
        if self.notification_window is not None:
            try:
                self.notification_window.hide()
            except Exception:
                pass

    def _show_notification(self, result: dict) -> None:
        if (
            not self._toast_enabled
            or self.notification_window is None
            or not self._notification_ready.is_set()
        ):
            return
        import json

        tone = "success" if result.get("ok") else "error"
        payload = {
            "tone": tone,
            "title": "Đã hoàn thành" if result.get("ok") else "Chưa hoàn thành",
            "message": str(result.get("message") or "Đã xong."),
            "theme": prefs.load_prefs()["theme"],
        }
        try:
            self.notification_window.evaluate_js(
                "window.wfxShowNotification("
                f"{json.dumps(payload, ensure_ascii=False)})"
            )
            x, y = _notification_position()
            if not _native_notification_visibility(True, x, y):
                self.notification_window.move(x, y)
                self.notification_window.show()
        except Exception:
            return
        with self._notification_lock:
            self._notification_generation += 1
            generation = self._notification_generation
        timer = threading.Timer(
            NOTIFICATION_SECONDS,
            self._hide_notification,
            args=(generation,),
        )
        timer.daemon = True
        timer.start()

    def _apply_always_on_top(self, enabled: bool) -> None:
        self._always_on_top = bool(enabled)
        for window in (self.window, self.bubble_window):
            if window is not None:
                try:
                    window.on_top = self._always_on_top
                except Exception:
                    pass

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

        if method in MODULE_NOTIFICATION_METHODS:
            self._show_notification(result)

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
        """Mở lại khi người dùng bấm mở app lần hai (SingleInstance báo sang)."""
        if self._bubble_hidden:
            self.show_from_tray()
        else:
            self.show_panel()

    def _on_closing(self):
        # Panel bị đóng (Alt+F4 / nút X) → chỉ ẩn panel, bubble vẫn còn. Khi
        # đang thoát thật (quit → destroy) thì bỏ qua để đóng hẳn.
        if self._quitting:
            return None
        self.hide_panel()
        return False

    def _on_bubble_closing(self):
        # Bubble bị đóng ngoài ý muốn → thu vào tray thay vì huỷ cửa sổ.
        if self._quitting:
            return None
        self.hide_to_tray()
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
        # Trạng thái nghỉ = bubble; không tự bung panel lúc khởi động.

    def _build_tray(self):
        image = Image.open(ICON_PATH)
        menu = pystray.Menu(
            pystray.MenuItem(
                "Hiện WFX Smart", lambda: self.show_from_tray(), default=True
            ),
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
        for window in (self.notification_window, self.bubble_window, self.window):
            if window is not None:
                try:
                    window.destroy()
                except Exception:
                    pass

    def _bubble_start_position(self) -> tuple[int, int]:
        """Vị trí bubble lúc khởi động: chỗ đã lưu, hoặc góc trên-phải màn hình."""
        if self._bubble_offset is not None:
            return self._bubble_offset
        try:
            screen_width = int(webview.screens[0].width)
        except Exception:
            screen_width = 1920
        x = max(WINDOW_MARGIN, screen_width - BUBBLE_SIZE - WINDOW_MARGIN)
        return x, 120

    def _on_bubble_loaded(self) -> None:
        """Giữ bubble đúng 48px native và tự chữa vị trí ngoài màn hình."""
        rect = _window_rect_by_title(BUBBLE_WINDOW_TITLE)
        area = _work_area_for_window_title(BUBBLE_WINDOW_TITLE)
        if rect is None or area is None:
            return
        x, y = _clamp_to_work_area(
            rect[0], rect[1], BUBBLE_SIZE, BUBBLE_SIZE, area
        )
        # create_window dùng logical pixels và có thể bị Windows DPI scale.
        # SetWindowPos lại bằng physical pixels để launcher không thành 72/96px.
        _set_bounds_by_title(
            BUBBLE_WINDOW_TITLE, x, y, BUBBLE_SIZE, BUBBLE_SIZE
        )
        if (x, y) != (rect[0], rect[1]):
            self._bubble_offset = (x, y)
            prefs.save_prefs(compact_offset_x=x, compact_offset_y=y)

    def run(self):
        if not ICON_PATH.exists():
            build_icon(ICON_PATH)
        # js_api expose các method điều khiển cửa sổ cho panel.js.
        self.api.hide_panel = self.hide_panel   # type: ignore[attr-defined]
        self.api.show_panel = self.show_panel   # type: ignore[attr-defined]
        self.api.toggle_panel = self.toggle_panel  # type: ignore[attr-defined]
        self.api.request_panel_hide = self.request_panel_hide  # type: ignore[attr-defined]
        self.api.focus_automation_browser = self.focus_automation_browser  # type: ignore[attr-defined]
        self.api.set_log_sink(self._push_log)
        self.api.set_result_sink(self._on_result)
        self.api.set_hotkey_applier(self._apply_hotkey)
        self.api.set_update_applier(self._apply_update)
        self.api.set_window_pref_appliers(
            self._apply_always_on_top,
        )

        original_set_toast = self.api.set_toast_enabled

        def set_toast(enabled):
            result = original_set_toast(enabled)
            self.set_toast_enabled_state(
                result.get("toast_enabled", enabled)
            )
            return result

        self.api.set_toast_enabled = set_toast  # type: ignore[method-assign]

        original_set_focus_chrome = self.api.set_focus_chrome_on_module

        def set_focus_chrome(enabled):
            result = original_set_focus_chrome(enabled)
            self.set_focus_chrome_on_module_state(
                result.get("focus_chrome_on_module", enabled)
            )
            return result

        self.api.set_focus_chrome_on_module = set_focus_chrome  # type: ignore[method-assign]
        # Panel: ẩn mặc định (trạng thái nghỉ là bubble). Vị trí ban đầu góc
        # trên-phải; khi bấm bubble sẽ được đặt lại ngay cạnh bubble.
        panel_x, panel_y = _top_right_position()
        self.window = webview.create_window(
            MAIN_WINDOW_TITLE,
            url=str(UI_INDEX),
            js_api=self.api,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            x=panel_x,
            y=panel_y,
            frameless=True,
            easy_drag=False,
            on_top=self._always_on_top,
            hidden=True,
            background_color="#0b1020",
        )
        self._panel_visible = False
        self.window.events.loaded += self.on_loaded
        self.window.events.closing += self._on_closing

        # Bubble: icon nổi thường trực (chat-head).
        bubble_x, bubble_y = self._bubble_start_position()
        self.bubble_window = webview.create_window(
            BUBBLE_WINDOW_TITLE,
            url=str(BUBBLE_INDEX),
            js_api=_BubbleBridge(self),
            width=BUBBLE_SIZE,
            height=BUBBLE_SIZE,
            min_size=(BUBBLE_SIZE, BUBBLE_SIZE),
            x=bubble_x,
            y=bubble_y,
            resizable=False,
            frameless=True,
            easy_drag=False,
            on_top=True,
            hidden=self._start_hidden,
            background_color="#0f9fb2",
        )
        self.bubble_window.events.loaded += self._on_bubble_loaded
        self.bubble_window.events.closing += self._on_bubble_closing

        notification_x, notification_y = _notification_position()
        self.notification_window = webview.create_window(
            NOTIFICATION_TITLE,
            url=str(NOTIFICATION_INDEX),
            js_api=_NotificationBridge(self),
            width=NOTIFICATION_WIDTH,
            height=NOTIFICATION_HEIGHT,
            x=notification_x,
            y=notification_y,
            resizable=False,
            frameless=True,
            easy_drag=False,
            focus=False,
            on_top=True,
            hidden=True,
            background_color="#f4f8fa",
        )
        self.notification_window.events.loaded += self._notification_loaded

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
            threading.Thread(target=self._update_loop, daemon=True).start()
            self._build_tray()

        # UI là file đóng gói và state thật nằm trong prefs/.env riêng. Dùng
        # WebView riêng tư để bản app mới không tái sử dụng HTML/CSS/zoom cache
        # của bản cũ — nguyên nhân từng làm UI khác index.html và bị tràn.
        webview.start(background, private_mode=True)


def main():
    app = PanelApp()
    lock = SingleInstance(app.activate)
    if not lock.acquire() and lock.signal_existing():
        # Đã có instance đang chạy: bật panel của nó lên rồi thoát im lặng.
        return
    # Nếu acquire() thất bại mà signal_existing() cũng thất bại: cổng bị một
    # chương trình khác giữ (không trả đúng handshake). Không được chặn người
    # dùng mở app vì lý do không liên quan — chạy tiếp, chấp nhận mất khả năng
    # chặn trùng trong phiên này.
    app.lock = lock
    app.run()


if __name__ == "__main__":
    main()
