from __future__ import annotations

import json
import os
import sys
import threading

import keyboard
import webview

# Giới hạn WebView2 của panel/bubble/menu/notification trên máy 8 GB RAM. WebView2
# chỉ đọc giá trị này lúc tạo environment, không phải khi import pywebview.
os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--renderer-process-limit=3 --process-per-site "
    "--disable-background-networking --disable-component-update "
    "--disable-sync --no-service-autorun",
)

from wfx_panel import (
    autostart,
    crash_log,
    hotkey,
    prefs,
    updater,
)
from wfx_panel.app.background import BackgroundLoopController
from wfx_panel.app.bridges import (  # noqa: F401
    _BubbleBridge,
    _BubbleMenuBridge,
    _ManualBridge,
)
from wfx_panel.app.bubble import BubbleController
from wfx_panel.app.dialogs import FileDialogController
from wfx_panel.app.helpers import (  # noqa: F401
    _dialog_selected_path,
    _is_excel_file,
    _reveal_downloaded_file,
    _safe_costing_file_stem,
    _show_webview2_print_dialog,
    _top_right_position,
)
from wfx_panel.app.layout import (  # noqa: F401
    BUBBLE_CONTEXT_POLL_SECONDS,
    BUBBLE_DIRECT_ACTION_SUPPRESS_SECONDS,
    BUBBLE_MENU_GAP,
    BUBBLE_MENU_HEIGHT,
    BUBBLE_MENU_INDEX,
    BUBBLE_MENU_WIDTH,
    BUBBLE_PANEL_GAP,
    BUBBLE_SIZE,
    ICON_PATH,
    MANUAL_INDEX,
    MANUAL_WINDOW_HEIGHT,
    MANUAL_WINDOW_MIN,
    MANUAL_WINDOW_TITLE,
    MANUAL_WINDOW_WIDTH,
    MODULE_NOTIFICATION_METHODS,
    PANEL_BLUR_GRACE_SECONDS,
    TASKBAR_ACTIVATION_POLL_SECONDS,
    WFX_MANUAL_URL,
    WINDOW_HEIGHT,
    WINDOW_MARGIN,
    WINDOW_WIDTH,
)
from wfx_panel.app.manual_window import ManualWindowController
from wfx_panel.app.notifications import NotificationController
from wfx_panel.app.placement import PanelPlacementController
from wfx_panel.app.tray import TrayController
from wfx_panel.assets.generate_icon import build_icon
from wfx_panel.panel_api import PanelAPI
from wfx_panel.single_instance import SingleInstance
from wfx_panel.stores import article_library
from wfx_panel.version import APP_VERSION
from wfx_panel.win32_window import (
    BUBBLE_WINDOW_TITLE,
    MAIN_WINDOW_TITLE,
    _foreground_process_id,
)

HOTKEY = hotkey.DEFAULT
UI_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "index.html"
BUBBLE_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "bubble.html"





























class PanelApp:
    def __init__(self):
        self.api = PanelAPI()
        self._export_sale_asn_price_check = self.api.export_sale_asn_price_check
        self._base_dir = self.api._base_dir
        # Bản EXE đóng gói luôn có Article List cạnh resource để khởi tạo cache
        # dropdown Style copy lần đầu. Source development không ghi cache vào
        # workspace; dùng cache đã đồng bộ nếu có.
        if getattr(sys, "frozen", False):
            article_library.seed_bundled(
                self._base_dir,
                prefs.RESOURCE_DIR / "Article List.csv",
            )
        self.window = None
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
        self.bubble_menu_window = None
        # Hộp thoại file và cửa sổ Manual sống trong controller riêng để
        # PanelApp chỉ còn là orchestrator của cửa sổ, tray và vòng lặp nền.
        self._dialogs = FileDialogController(self)
        self._bubble = BubbleController(self)
        self._placement = PanelPlacementController(self)
        self._notifications = NotificationController(self)
        self._background = BackgroundLoopController(self)
        self._tray = TrayController(self)
        self._manual = ManualWindowController(self)
        # Bubble là trạng thái nghỉ sau khi thu panel. Khi user chạy app bình
        # thường, UI đầy đủ phải xuất hiện ngay lần đầu (trừ khi họ chủ động
        # bật "Mở ẩn trong tray").
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
        self._bubble_size_thread: threading.Thread | None = None
        self._bubble_direct_action_until = 0.0
        self._bubble_pointer_down = False
        self._bubble_pointer_started = 0.0
        self._taskbar_focus_armed = False
        self._taskbar_opening = False
        # _taskbar_opening được dùng như mutex nhưng mỗi event taskbar lại chạy
        # trên một thread mới, nên check-rồi-set không nguyên tử: hai event sát
        # nhau đều thấy False và cùng gọi _restore_bubble()/show_panel().
        self._taskbar_open_lock = threading.Lock()
        self._taskbar_minimize_requested = False
        self._panel_focus_lost_since = 0.0
        self._panel_hide_pending = False
        # WebView biết con trỏ còn nằm trong panel nhưng foreground Win32 có
        # thể đã chuyển sang Chrome do automation. Đồng bộ trạng thái này sang
        # native để monitor không thu UI ngay khi flow vừa kết thúc.
        self._panel_pointer_inside = False
        self._bubble_menu_lock = threading.Lock()
        self._bubble_menu_visible = False
        self._bubble_menu_last_opened = 0.0
        self._bubble_menu_destroying = False
        self._bubble_menu_destroyed = threading.Event()
        self._bubble_menu_destroyed.set()
        self._tray_ready = threading.Event()
        self._pending_native_notification: tuple[str, str] | None = None
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
        # Khóa một-instance; main() gán vào để quit() trả cổng lại cho lần mở sau.
        self.lock: SingleInstance | None = None

    @property
    def manual_window(self):
        """Cửa sổ Manual đang mở — state thật nằm ở ManualWindowController."""
        return self._manual.window

    @manual_window.setter
    def manual_window(self, window) -> None:
        self._manual.window = window

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

        try:
            self.window.evaluate_js(
                "window.wfxSetUpdateState("
                f"{json.dumps(state, ensure_ascii=False)})"
            )
        except Exception:
            pass

    def _handle_downloaded_excel(self, value: object) -> bool:
        return self._dialogs._handle_downloaded_excel(value)

    def _on_progress(self, progress: dict) -> None:
        if self.window is None:
            return

        try:
            self.window.evaluate_js(
                "window.wfxHandleBackendProgress("
                f"{json.dumps(progress, ensure_ascii=False)})"
            )
        except Exception:
            pass

    def choose_costing_import_file(self) -> dict:
        return self._dialogs.choose_costing_import_file()

    def choose_costing_export_file(self, style_name: str, file_format: str='xlsx') -> dict:
        return self._dialogs.choose_costing_export_file(style_name, file_format)

    def choose_report_export_dir(self) -> dict:
        return self._dialogs.choose_report_export_dir()

    def open_report_export_dir(self, path: str='') -> dict:
        return self._dialogs.open_report_export_dir(path)

    def choose_oc_upload_file(self, mode: str) -> dict:
        return self._dialogs.choose_oc_upload_file(mode)

    def choose_oc_upload_export_file(self, source_file: str='') -> dict:
        return self._dialogs.choose_oc_upload_export_file(source_file)

    def choose_sale_asn_export_file(self, invoice_no: str) -> dict:
        return self._dialogs.choose_sale_asn_export_file(invoice_no)

    def choose_sale_asn_price_check_export_file(self, invoice_no: str) -> dict:
        return self._dialogs.choose_sale_asn_price_check_export_file(invoice_no)

    def export_sale_asn_price_check(self, price_check: dict, file_path: str) -> dict:
        return self._dialogs.export_sale_asn_price_check(price_check, file_path)

    def choose_sale_asn_import_file(self) -> dict:
        return self._dialogs.choose_sale_asn_import_file()

    def choose_style_import_file(self) -> dict:
        return self._dialogs.choose_style_import_file()

    def download_style_template(self, group_id: str='') -> dict:
        return self._dialogs.download_style_template(group_id)

    def _style_copy_article_names(self) -> list[str]:
        return self._dialogs._style_copy_article_names()

    def download_oc_template(self) -> dict:
        return self._dialogs.download_oc_template()

    def download_sale_asn_template(self) -> dict:
        return self._dialogs.download_sale_asn_template()

    def save_sale_asn_continue_template(self, rows: list[dict]) -> dict:
        return self._dialogs.save_sale_asn_continue_template(rows)

    def hide_panel(self):
        return self._placement.hide_panel()

    def set_panel_pointer_inside(self, inside: bool) -> dict:
        return self._placement.set_panel_pointer_inside(inside)

    def show_panel(self) -> dict:
        return self._placement.show_panel()

    def _restore_bubble(self) -> None:
        return self._bubble._restore_bubble()

    def toggle_panel(self) -> dict:
        return self._placement.toggle_panel()

    def _position_panel_beside_bubble(self) -> None:
        return self._placement._position_panel_beside_bubble()

    def request_panel_hide(self) -> dict:
        return self._placement.request_panel_hide()

    def _track_panel_foreground(self, foreground_pid: int | None) -> None:
        return self._placement._track_panel_foreground(foreground_pid)

    def note_bubble_interaction(self) -> dict:
        return self._bubble.note_bubble_interaction()

    def begin_bubble_interaction(self) -> dict:
        return self._bubble.begin_bubble_interaction()

    def end_bubble_interaction(self) -> dict:
        return self._bubble.end_bubble_interaction()

    def _bubble_interaction_active(self) -> bool:
        return self._bubble._bubble_interaction_active()

    def save_bubble_position(self) -> dict:
        return self._bubble.save_bubble_position()

    def _ensure_bubble_menu_window(self) -> bool:
        return self._bubble._ensure_bubble_menu_window()

    def bubble_context_menu(self) -> dict:
        return self._bubble.bubble_context_menu()

    def _bubble_menu_position(self) -> tuple[int, int, int, int]:
        return self._bubble._bubble_menu_position()

    def dismiss_bubble_menu(self) -> dict:
        return self._bubble.dismiss_bubble_menu()

    def choose_bubble_menu(self, action: str) -> dict:
        return self._bubble.choose_bubble_menu(action)

    def _bubble_context_menu_loop(self) -> None:
        return self._bubble._bubble_context_menu_loop()

    def minimize_to_taskbar(self) -> dict:
        return self._placement.minimize_to_taskbar()

    def hide_to_tray(self) -> None:
        return self._placement.hide_to_tray()

    def show_from_tray(self) -> dict:
        return self._placement.show_from_tray()

    def manual_payload(self) -> dict:
        return self._manual.manual_payload()

    def manual_entry_for_module(self, module_id: str) -> str:
        return self._manual.manual_entry_for_module(module_id)

    def manual_error_codes(self) -> list[str]:
        return self._manual.manual_error_codes()

    def manual_has_news(self) -> bool:
        return self._manual.manual_has_news()

    def get_manual_entry_for_module(self, module_id: str) -> dict:
        return self._manual.get_manual_entry_for_module(module_id)

    def close_manual_window(self) -> None:
        return self._manual.close_manual_window()

    def print_manual(self) -> dict:
        return self._manual.print_manual()

    def open_wfx_manual(self, target: str='') -> dict:
        return self._manual.open_wfx_manual(target)

    def _on_manual_closed(self, *_args) -> None:
        return self._manual._on_manual_closed(*_args)

    def _focus_module_search(self) -> None:
        return self._placement._focus_module_search()

    def toggle(self):
        """Hotkey luôn khôi phục bubble khi panel đang đóng/minimized."""
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
        return self._notifications.set_toast_enabled_state(enabled)

    def set_focus_chrome_on_module_state(self, enabled: bool) -> None:
        self._focus_chrome_on_module = bool(enabled)

    def focus_automation_browser(self) -> dict:
        return self._placement.focus_automation_browser()

    def _hide_notification(self) -> None:
        return self._notifications._hide_notification()

    def _notify_native(self, message: str, title: str) -> bool:
        return self._notifications._notify_native(message, title)

    def _show_notification(self, result: dict, *, method: str='', elapsed: float | None=None) -> bool:
        return self._notifications._show_notification(
            result,
            method=method,
            elapsed=elapsed,
        )

    def _apply_always_on_top(self, enabled: bool) -> None:
        return self._placement._apply_always_on_top(enabled)

    def _apply_update(self, state: dict) -> str | None:
        return self._background._apply_update(state)

    def _on_result(self, method: str, result: dict, elapsed: float) -> None:
        state = {
            **self.api._session_status(),
            **self.api._division_state(),
        }
        if self.window is not None:
            import json

            try:
                # UI cần biết kết quả đến từ flow nào: kiểm tra nền không được
                # ép mở sheet tài khoản như một thao tác do user bấm.
                payload = json.dumps(
                    {**result, **state, "method": method},
                    ensure_ascii=False,
                )
                self.window.evaluate_js(
                    f"window.wfxHandleBackendResult({payload})"
                )
            except Exception:
                pass

        revealed_excel = True
        if result.get("ok"):
            download_path = result.get("download_path")
            export_path = result.get("export_path")
            excel_path = export_path or (
                download_path if _is_excel_file(download_path) else None
            )
            if excel_path and _is_excel_file(excel_path):
                revealed_excel = self._handle_downloaded_excel(excel_path)
            elif method == "download_catalog_file":
                self._dialogs.reveal_download(download_path)
        if method == "save_sale_asn_documents" and result.get("ok") and not revealed_excel:
            self.api._log(
                "[SALE ASN] Đã lưu file nhưng không mở được thư mục chứa file."
            )

        foreground_pid = _foreground_process_id()
        panel_is_foreground = self._panel_visible and (
            self.window is None
            or foreground_pid is None
            or foreground_pid == os.getpid()
        )
        if method in MODULE_NOTIFICATION_METHODS and not panel_is_foreground:
            self._show_notification(
                result,
                method=method,
                elapsed=elapsed,
            )

    def show_test_notification(self) -> dict:
        return self._notifications.show_test_notification()

    def _status_loop(self) -> None:
        return self._background._status_loop()

    def _check_update_once(self) -> None:
        return self._background._check_update_once()

    def _update_loop(self) -> None:
        return self._background._update_loop()

    def _article_library_loop(self) -> None:
        return self._background._article_library_loop()

    def activate(self):
        """Mở lại khi người dùng bấm mở app lần hai (SingleInstance báo sang)."""
        self.show_from_tray()

    def _open_panel_from_taskbar(self) -> None:
        return self._placement._open_panel_from_taskbar()

    def _on_bubble_minimized(self) -> None:
        return self._bubble._on_bubble_minimized()

    def _on_bubble_restored(self) -> None:
        return self._bubble._on_bubble_restored()

    def _on_bubble_taskbar_event(self) -> None:
        return self._bubble._on_bubble_taskbar_event()

    def _taskbar_activation_loop(self) -> None:
        return self._placement._taskbar_activation_loop()

    def _on_closing(self):
        # Panel bị đóng (Alt+F4 / nút X) → chỉ ẩn panel, bubble vẫn còn. Khi
        # đang thoát thật (quit → destroy) thì bỏ qua để đóng hẳn.
        if self._quitting:
            return None
        self.hide_panel()
        return False

    def _on_bubble_closing(self):
        return self._bubble._on_bubble_closing()

    def _on_bubble_menu_closing(self):
        return self._bubble._on_bubble_menu_closing()

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
            if not self._start_hidden:
                self.show_panel()
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
            if not self._start_hidden:
                self.show_panel()

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
        # Sau khi user thu panel, bubble tiếp tục là trạng thái nghỉ.

    def _build_tray(self):
        return self._tray._build_tray()

    def _on_tray_ready(self, icon) -> None:
        return self._tray._on_tray_ready(icon)

    def _note_tray_context_menu(self) -> None:
        return self._tray._note_tray_context_menu()

    def quit(self, close_browser: bool = False):
        self._quitting = True
        crash_log.clean_shutdown("user_exit")
        self._stop_status.set()
        shutdown = getattr(self.api, "shutdown", None)
        if callable(shutdown):
            shutdown(close_browser=close_browser)
        try:
            keyboard.remove_hotkey(self._hotkey)
        except (KeyError, ValueError):
            pass
        if self.lock is not None:
            self.lock.close()
        if self.tray:
            self.tray.stop()
        # pywebview (winforms) chỉ gọi Application.Exit khi BrowserView.instances
        # rỗng. Bỏ sót BẤT KỲ cửa sổ nào — kể cả bubble menu ẩn ở -32000 và cửa
        # sổ Manual — là vòng lặp thông điệp không bao giờ kết thúc, webview.start()
        # không trả về và process vẫn sống sau khi user bấm Thoát.
        for window in (
            self.bubble_menu_window,
            self.manual_window,
            self.bubble_window,
            self.window,
        ):
            if window is not None:
                try:
                    window.destroy()
                except Exception:
                    pass

    def _bubble_start_position(self) -> tuple[int, int]:
        return self._bubble._bubble_start_position()

    def _enforce_bubble_native_bounds(self) -> bool:
        return self._bubble._enforce_bubble_native_bounds()

    def _schedule_bubble_native_bounds(self) -> None:
        return self._bubble._schedule_bubble_native_bounds()

    def _on_bubble_loaded(self) -> None:
        return self._bubble._on_bubble_loaded()

    def _on_bubble_menu_loaded(self) -> None:
        return self._bubble._on_bubble_menu_loaded()

    def run(self):
        if not ICON_PATH.exists():
            build_icon(ICON_PATH)
        # js_api expose các method điều khiển cửa sổ cho panel.js.
        self.api.hide_panel = self.hide_panel   # type: ignore[attr-defined]
        self.api.show_panel = self.show_panel   # type: ignore[attr-defined]
        self.api.toggle_panel = self.toggle_panel  # type: ignore[attr-defined]
        self.api.request_panel_hide = self.request_panel_hide  # type: ignore[attr-defined]
        self.api.set_panel_pointer_inside = self.set_panel_pointer_inside  # type: ignore[attr-defined]
        self.api.open_wfx_manual = self.open_wfx_manual  # type: ignore[attr-defined]
        self.api.get_manual_entry_for_module = (  # type: ignore[attr-defined]
            self.get_manual_entry_for_module
        )
        original_get_initial_state = self.api.get_initial_state

        def get_initial_state_with_manual() -> dict:
            state = original_get_initial_state()
            state["manual_error_codes"] = self.manual_error_codes()
            state["manual_has_news"] = self.manual_has_news()
            return state

        self.api.get_initial_state = get_initial_state_with_manual  # type: ignore[method-assign]
        self.api.focus_automation_browser = self.focus_automation_browser  # type: ignore[attr-defined]
        self.api.choose_costing_import_file = self.choose_costing_import_file  # type: ignore[attr-defined]
        self.api.choose_costing_export_file = self.choose_costing_export_file  # type: ignore[attr-defined]
        self.api.choose_report_export_dir = self.choose_report_export_dir  # type: ignore[attr-defined]
        self.api.open_report_export_dir = self.open_report_export_dir  # type: ignore[attr-defined]
        self.api.choose_oc_upload_file = self.choose_oc_upload_file  # type: ignore[attr-defined]
        self.api.choose_oc_upload_export_file = (  # type: ignore[attr-defined]
            self.choose_oc_upload_export_file
        )
        self.api.choose_sale_asn_export_file = self.choose_sale_asn_export_file  # type: ignore[attr-defined]
        self.api.choose_sale_asn_price_check_export_file = (  # type: ignore[attr-defined]
            self.choose_sale_asn_price_check_export_file
        )
        self.api.export_sale_asn_price_check = (  # type: ignore[method-assign]
            self.export_sale_asn_price_check
        )
        self.api.choose_sale_asn_import_file = self.choose_sale_asn_import_file  # type: ignore[attr-defined]
        self.api.choose_style_import_file = self.choose_style_import_file  # type: ignore[attr-defined]
        self.api.download_style_template = self.download_style_template  # type: ignore[attr-defined]
        self.api.download_oc_template = self.download_oc_template  # type: ignore[attr-defined]
        self.api.download_sale_asn_template = self.download_sale_asn_template  # type: ignore[attr-defined]
        self.api.save_sale_asn_continue_template = (  # type: ignore[attr-defined]
            self.save_sale_asn_continue_template
        )
        self.api.set_log_sink(self._push_log)
        self.api.set_result_sink(self._on_result)
        self.api.set_progress_sink(self._on_progress)
        self.api.set_hotkey_applier(self._apply_hotkey)
        self.api.set_update_applier(self._apply_update)
        self.api.set_window_pref_appliers(
            self._apply_always_on_top,
        )
        self.api.show_test_notification = self.show_test_notification  # type: ignore[attr-defined]

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
            # Không để mặc định 200×100 của pywebview, đồng thời không dùng
            # min_size=48 logical px vì Windows sẽ DPI-scale giới hạn đó thành
            # 60/72px và chặn SetWindowPos thu bubble về 48 physical px.
            min_size=(1, 1),
            x=bubble_x,
            y=bubble_y,
            resizable=False,
            frameless=True,
            easy_drag=False,
            on_top=True,
            hidden=self._start_hidden,
            background_color="#0f9fb2",
            # Opaque là bắt buộc với WebView2: TransparencyKey khiến toàn bộ
            # form bị hit-test xuyên xuống Chrome dù SVG vẫn nhìn thấy.
            shadow=False,
        )
        self.bubble_window.events.loaded += self._on_bubble_loaded
        self.bubble_window.events.closing += self._on_bubble_closing
        self.bubble_window.events.minimized += self._on_bubble_minimized
        self.bubble_window.events.restored += self._on_bubble_restored

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
                target=self._taskbar_activation_loop, daemon=True
            ).start()
            threading.Thread(
                target=self._bubble_context_menu_loop,
                name="wfx-bubble-context-menu",
                daemon=True,
            ).start()
            threading.Thread(target=self._update_loop, daemon=True).start()
            threading.Thread(
                target=self._article_library_loop,
                name="wfx-article-library-sync",
                daemon=True,
            ).start()
            self._build_tray()

        # UI là file đóng gói và state thật nằm trong prefs/.env riêng. Dùng
        # WebView riêng tư để bản app mới không tái sử dụng HTML/CSS/zoom cache
        # của bản cũ — nguyên nhân từng làm UI khác index.html và bị tràn.
        webview.start(background, private_mode=True)


def _sync_packaged_autostart() -> bool | None:
    """Đồng bộ Windows startup cho bản đóng gói, không chạm máy khi chạy source."""
    if not getattr(sys, "frozen", False):
        return None
    preferences = prefs.load_prefs()
    wanted_autostart = preferences["autostart"]
    actual_autostart = autostart.sync(wanted_autostart)
    if actual_autostart != wanted_autostart:
        prefs.save_prefs(autostart=actual_autostart)
    return actual_autostart


def main():
    crash_log.install(prefs.DATA_DIR, app_version=APP_VERSION)
    app = PanelApp()
    lock = SingleInstance(app.activate)
    if not lock.acquire():
        # Đã có instance đang chạy: cố bật panel của nó lên rồi luôn thoát.
        # Không chạy tiếp nếu IPC tạm lỗi, nếu không sẽ tạo instance thứ hai.
        lock.signal_existing()
        crash_log.clean_shutdown("secondary_instance")
        return
    app.lock = lock
    # Chỉ bản đóng gói mới tự đăng ký startup mặc định. Chạy source để phát
    # triển không được âm thầm thêm pythonw vào Windows Run key.
    _sync_packaged_autostart()
    try:
        app.run()
    except BaseException as error:
        crash_log.record(
            "MAIN_LOOP_EXCEPTION",
            exception=f"{type(error).__name__}: {error}",
        )
        raise
    else:
        crash_log.clean_shutdown("main_loop_returned")


if __name__ == "__main__":
    main()
