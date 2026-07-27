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
    MAIN_WINDOW_TITLE,
    NOTIFICATION_HEIGHT,
    NOTIFICATION_TITLE,
    NOTIFICATION_WIDTH,
    _bring_process_window_to_front,
    _clamp_to_work_area,
    _foreground_process_id,
    _native_compact_context_choice,
    _native_cursor_position,
    _native_left_button_down,
    _native_notification_visibility,
    _set_process_window_bounds,
    _snap_to_nearest_edge,
    _window_rect_for_process,
    _work_area_for_process_window,
)

HOTKEY = hotkey.DEFAULT
STATUS_POLL_SECONDS = 5
COMPACT_ACTIVATION_POLL_SECONDS = 0.25
UPDATE_INITIAL_DELAY_SECONDS = 1
UPDATE_POLL_SECONDS = 4 * 60 * 60
ICON_PATH = prefs.RESOURCE_DIR / "wfx_panel" / "assets" / "wfx.ico"
UI_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "index.html"
NOTIFICATION_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "notification.html"

WINDOW_WIDTH = 440
WINDOW_HEIGHT = 620
WINDOW_MARGIN = 24
COMPACT_SIZE = 48
WINDOW_TRANSITION_SECONDS = 0.14
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
    """Neo toast trên panel đang mở hoặc ngay phía trên icon thu gọn."""
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

    panel = _window_rect_for_process(os.getpid())
    if panel is not None:
        panel_width = panel[2] - panel[0]
        panel_height = panel[3] - panel[1]
        if panel_width <= COMPACT_SIZE + 12 and panel_height <= COMPACT_SIZE + 12:
            x = panel[0] + (panel_width - NOTIFICATION_WIDTH) // 2
            y = panel[1] - NOTIFICATION_HEIGHT - 8
        else:
            x = panel[2] - NOTIFICATION_WIDTH
            above = panel[1] - NOTIFICATION_HEIGHT - 8
            # Panel mặc định nằm sát đầu màn hình. Khi không đủ
            # chỗ ở ngoài, toast nổi trên phần đầu panel thay vì
            # trôi xuống góc màn hình.
            y = above if above >= top + NOTIFICATION_MARGIN else panel[1] + 8
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
        self._visible = not self._start_hidden
        self._compact = False
        self._full_window_size: tuple[int, int] | None = None
        # Vị trí đã lưu của icon thu gọn và của panel (physical Win32 coords).
        # None nghĩa là chưa từng đặt tay; khi dùng luôn clamp lại vào work area
        # của màn hình hiện tại phòng khi cấu hình màn hình đã đổi.
        self._compact_offset: tuple[int, int] | None = (
            (preferences["compact_offset_x"], preferences["compact_offset_y"])
            if preferences["compact_offset_x"] is not None
            and preferences["compact_offset_y"] is not None
            else None
        )
        self._panel_offset: tuple[int, int] | None = (
            (preferences["panel_offset_x"], preferences["panel_offset_y"])
            if preferences["panel_offset_x"] is not None
            and preferences["panel_offset_y"] is not None
            else None
        )
        self._compact_drag_thread: threading.Thread | None = None
        self._expanding_compact = False
        self._compact_focus_armed = False
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
        if self.window and self._visible:
            self._prepare_window_transition()
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
        cursor = _native_cursor_position()
        own_rect = _window_rect_for_process(os.getpid())
        started = bool(
            _native_left_button_down()
            and cursor is not None
            and own_rect is not None
        )
        if started:
            self._compact_drag_thread = threading.Thread(
                target=self._compact_drag_loop,
                args=(cursor, own_rect),
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
    ) -> None:
        """Theo con trỏ toàn hệ thống; không phụ thuộc Chrome.

        Mỗi bước đều clamp vào work area nên icon không bao giờ lọt khỏi màn
        hình. Khi thả chuột thì dính vào mép gần nhất (kiểu bong bóng chat) và
        lưu vị trí để lần thu gọn sau icon quay về đúng chỗ đã đặt.
        """
        width = origin_rect[2] - origin_rect[0]
        height = origin_rect[3] - origin_rect[1]
        area = _work_area_for_process_window(os.getpid())
        last: tuple[int, int] | None = None
        while self._compact and _native_left_button_down():
            cursor = _native_cursor_position()
            if cursor is None:
                break
            target_x = origin_rect[0] + cursor[0] - origin_cursor[0]
            target_y = origin_rect[1] + cursor[1] - origin_cursor[1]
            target_x, target_y = _clamp_to_work_area(
                target_x, target_y, width, height, area
            )
            _set_process_window_bounds(os.getpid(), target_x, target_y)
            last = (target_x, target_y)
            time.sleep(0.012)
        if last is None:
            return
        snap_x, snap_y = _snap_to_nearest_edge(
            last[0], last[1], width, height, area
        )
        _set_process_window_bounds(os.getpid(), snap_x, snap_y)
        self._compact_offset = (snap_x, snap_y)
        prefs.save_prefs(compact_offset_x=snap_x, compact_offset_y=snap_y)

    def collapse_to_browser_icon(self) -> dict:
        """Thu panel thành launcher nổi tại vị trí hiện tại."""
        if self.window is None:
            return {
                "ok": False,
                "code": "PANEL_NOT_READY",
                "message": "Panel chưa sẵn sàng.",
            }
        try:
            current_rect = _window_rect_for_process(os.getpid())
            area = _work_area_for_process_window(os.getpid())
            if current_rect is not None:
                self._full_window_size = (
                    current_rect[2] - current_rect[0],
                    current_rect[3] - current_rect[1],
                )
                # Nhớ vị trí panel để lần mở lại đặt về đúng chỗ.
                self._panel_offset = (current_rect[0], current_rect[1])
                prefs.save_prefs(
                    panel_offset_x=current_rect[0],
                    panel_offset_y=current_rect[1],
                )
            # Icon xuất hiện ngay góc trên-phải của panel (nơi mắt đang nhìn),
            # hoặc quay về đúng chỗ đã parked lần trước; luôn clamp gọn trong
            # màn hình để hết cảnh icon "nhảy" ra mép/khuất.
            if self._compact_offset is not None:
                icon_x, icon_y = self._compact_offset
            elif current_rect is not None:
                icon_x = current_rect[2] - COMPACT_SIZE
                icon_y = current_rect[1]
            else:
                icon_x, icon_y = WINDOW_MARGIN, WINDOW_MARGIN
            icon_x, icon_y = _clamp_to_work_area(
                icon_x, icon_y, COMPACT_SIZE, COMPACT_SIZE, area
            )
            self._prepare_window_transition()
            self._set_compact_ui(True)
            self._compact = True
            self._compact_focus_armed = False
            self._visible = True
            resized = bool(
                _set_process_window_bounds(
                    os.getpid(),
                    icon_x,
                    icon_y,
                    COMPACT_SIZE,
                    COMPACT_SIZE,
                )
            )
            if not resized:
                self.window.resize(COMPACT_SIZE, COMPACT_SIZE)
                self.window.move(icon_x, icon_y)
            self._compact_offset = (icon_x, icon_y)
            self.window.on_top = self._always_on_top
            self._finish_window_transition()
            return {
                "ok": True,
                "code": "PANEL_COMPACT",
                "message": "Đã thu WFX Smart thành icon.",
            }
        except Exception as error:
            self._compact = False
            self._compact_focus_armed = False
            self._set_compact_ui(False)
            self._finish_window_transition()
            return {
                "ok": False,
                "code": "PANEL_COMPACT_FAILED",
                "message": f"Không thu gọn được panel: {error}",
            }

    def expand_from_browser_icon(self) -> dict:
        """Bung launcher về panel đầy đủ tại vị trí hiện tại."""
        if self.window is None:
            return {
                "ok": False,
                "code": "PANEL_NOT_READY",
                "message": "Panel chưa sẵn sàng.",
            }
        if self._expanding_compact:
            return {
                "ok": True,
                "code": "PANEL_EXPANDING",
                "message": "Panel đang mở rộng.",
            }
        self._expanding_compact = True
        try:
            self._prepare_window_transition(wait=self._visible)
            if not self._visible:
                self.window.show()
                self._visible = True
            current_rect = _window_rect_for_process(os.getpid())
            area = _work_area_for_process_window(os.getpid())
            width, height = self._full_window_size or (
                WINDOW_WIDTH,
                WINDOW_HEIGHT,
            )
            # Neo panel tại vị trí icon rồi CLAMP trọn trong màn hình. Đây là
            # chỗ trước đây bung panel từ đúng góc icon nên tràn ra ngoài —
            # clamp tự đẩy panel sang trái/lên trên để luôn thấy đủ.
            anchor = current_rect or (
                self._panel_offset[0] if self._panel_offset else 0,
                self._panel_offset[1] if self._panel_offset else 0,
                0,
                0,
            )
            target_x, target_y = _clamp_to_work_area(
                anchor[0], anchor[1], width, height, area
            )
            restored = bool(
                current_rect
                and _set_process_window_bounds(
                    os.getpid(),
                    target_x,
                    target_y,
                    width,
                    height,
                )
            )
            if not restored:
                self.window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
                self.window.move(target_x, target_y)
            self._panel_offset = (target_x, target_y)
            prefs.save_prefs(
                panel_offset_x=target_x, panel_offset_y=target_y
            )
            self.window.on_top = self._always_on_top
            self._compact = False
            self._compact_focus_armed = False
            self._set_compact_ui(False)
            _bring_process_window_to_front(on_top=self._always_on_top)
            self._focus_module_search()
            self._finish_window_transition()
            return {
                "ok": True,
                "code": "PANEL_EXPANDED",
                "message": "Đã mở WFX Smart.",
            }
        except Exception as error:
            self._finish_window_transition()
            return {
                "ok": False,
                "code": "PANEL_EXPAND_FAILED",
                "message": f"Không mở rộng được panel: {error}",
            }
        finally:
            self._expanding_compact = False

    def dismiss_panel(self):
        return self.collapse_to_browser_icon()

    def show_panel(self):
        if self._compact:
            self.expand_from_browser_icon()
            return
        if self.window and not self._visible:
            self._prepare_window_transition(wait=False)
            try:
                self.window.show()
            except Exception:
                pass
            self._visible = True
            self._finish_window_transition()
        _bring_process_window_to_front(on_top=self._always_on_top)
        self._focus_module_search()

    def _focus_module_search(self) -> None:
        if self.window is None:
            return
        try:
            self.window.evaluate_js(
                "window.setTimeout(() => window.wfxFocusModuleSearch?.(), 60)"
            )
        except Exception:
            pass

    def _prepare_window_transition(self, *, wait: bool = True) -> None:
        if self.window is None:
            return
        try:
            self.window.evaluate_js("window.wfxPrepareWindowTransition?.()")
            if wait:
                time.sleep(WINDOW_TRANSITION_SECONDS)
        except Exception:
            pass

    def _finish_window_transition(self) -> None:
        if self.window is None:
            return
        try:
            self.window.evaluate_js("window.wfxFinishWindowTransition?.()")
        except Exception:
            pass

    def show_compact_context_menu(self) -> dict:
        if not self._compact:
            return {
                "ok": False,
                "code": "PANEL_NOT_COMPACT",
                "message": "Panel chưa ở chế độ icon.",
            }
        choice = _native_compact_context_choice(self._always_on_top)
        if choice == "hide":
            self.hide_panel()
            return {
                "ok": True,
                "code": "PANEL_HIDDEN",
                "message": "Đã ẩn WFX Smart xuống khay hệ thống.",
            }
        if choice == "toggle_on_top":
            return self.api.set_always_on_top(not self._always_on_top)
        return {
            "ok": True,
            "code": "COMPACT_MENU_DISMISSED",
            "message": "Đã đóng menu.",
        }

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

    def _expand_compact_from_taskbar(self) -> None:
        if not self._compact or self._expanding_compact:
            return
        try:
            self.window.restore()
        except Exception:
            pass
        self.expand_from_browser_icon()

    def _on_window_minimized(self) -> None:
        if self._compact:
            threading.Thread(
                target=self._expand_compact_from_taskbar, daemon=True
            ).start()

    def _on_window_restored(self) -> None:
        if self._compact:
            threading.Thread(
                target=self._expand_compact_from_taskbar, daemon=True
            ).start()

    def _apply_always_on_top(self, enabled: bool) -> None:
        self._always_on_top = bool(enabled)
        if self.window is not None:
            try:
                self.window.on_top = self._always_on_top
            except Exception:
                pass

    def _compact_activation_loop(self) -> None:
        """Mở icon khi người dùng kích hoạt nó từ taskbar."""
        while not self._stop_status.wait(COMPACT_ACTIVATION_POLL_SECONDS):
            if self._compact:
                foreground_pid = _foreground_process_id()
                if foreground_pid is not None and foreground_pid != os.getpid():
                    self._compact_focus_armed = True
                elif (
                    foreground_pid == os.getpid()
                    and self._compact_focus_armed
                    and not self._expanding_compact
                ):
                    self._compact_focus_armed = False
                    threading.Thread(
                        target=self._expand_compact_from_taskbar,
                        daemon=True,
                    ).start()

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
        _bring_process_window_to_front(on_top=self._always_on_top)
        self._focus_module_search()
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
        if self.notification_window:
            try:
                self.notification_window.destroy()
            except Exception:
                pass
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
        self.api.show_compact_context_menu = self.show_compact_context_menu  # type: ignore[attr-defined]
        self.api.show_panel = self.show_panel   # type: ignore[attr-defined]
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
        x, y = _top_right_position()
        self.window = webview.create_window(
            MAIN_WINDOW_TITLE,
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
        self.window.events.minimized += self._on_window_minimized
        self.window.events.restored += self._on_window_restored

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
            threading.Thread(
                target=self._compact_activation_loop, daemon=True
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
