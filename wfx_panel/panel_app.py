from __future__ import annotations

import threading

import keyboard
import pystray
import webview
from PIL import Image

from wfx_panel import prefs
from wfx_panel.assets.generate_icon import build_icon
from wfx_panel.panel_api import PanelAPI
from wfx_panel.single_instance import SingleInstance

HOTKEY = "ctrl+shift+x"
ICON_PATH = prefs.RESOURCE_DIR / "wfx_panel" / "assets" / "wfx.ico"
UI_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "index.html"

WINDOW_WIDTH = 440
WINDOW_HEIGHT = 620
WINDOW_MARGIN = 24


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
        self._visible = True
        self._quitting = False
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

    def hide_panel(self):
        if self.window and self._visible:
            try:
                self.window.hide()
            except Exception:
                pass
            self._visible = False

    def show_panel(self):
        if self.window and not self._visible:
            try:
                self.window.show()
            except Exception:
                pass
            self._visible = True

    def toggle(self):
        if self._visible:
            self.hide_panel()
        else:
            self.show_panel()

    def activate(self):
        """Đưa panel ra trước, kể cả khi state nội bộ đang cho là đã hiện.

        Gọi khi người dùng mở app lần thứ hai (SingleInstance báo sang). Không
        dùng show_panel() vì hàm đó bỏ qua khi `_visible` đang True — mà đúng
        tình huống này người dùng bấm lại chính vì không thấy cửa sổ đâu.
        """
        if self.window is None:
            return
        try:
            self.window.show()
        except Exception:
            pass
        self._visible = True

    def _on_closing(self):
        # window.destroy() (gọi từ quit(), tức tray "Thoát") cũng đi qua sự
        # kiện này trên Windows — chỉ chặn khi đây là lần đóng ngoài ý muốn
        # (Alt+F4, nút X hệ thống nếu có), thu về tray như nút đóng trong
        # panel. Trả về False để pywebview huỷ hành động đóng gốc; bỏ qua
        # (không trả False) khi đang thoát thật để "Thoát" vẫn hoạt động.
        if self._quitting:
            return None
        self.hide_panel()
        return False

    # -- lifecycle ---------------------------------------------------------
    def on_loaded(self):
        # Chạy nền: bơm trạng thái ban đầu + auto-login, không chặn UI.
        threading.Thread(target=self._startup, daemon=True).start()

    def _startup(self):
        try:
            state = self.api.get_initial_state()
            import json
            self.window.evaluate_js(f"window.wfxBootstrap({json.dumps(state, ensure_ascii=False)})")
            account = prefs.load_account()
            if account["user_id"] and account["password"]:
                self._push_log("[SESSION] Tự động đăng nhập...")
                result = self.api.login()
            else:
                result = self.api.check_session()
            tone = "success" if result.get("ok") else "warning"
            self._set_status(tone, result.get("message", ""))
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
                f"Không đăng ký được phím tắt {HOTKEY.upper()}: {self._hotkey_error}. "
                "Hãy đóng và mở lại ứng dụng; có thể cần chạy với quyền Administrator."
            )
            self._push_log(f"[ERROR] {hotkey_message}")
            self._set_status("error", hotkey_message)

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
        try:
            keyboard.remove_hotkey(HOTKEY)
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
        self.api.show_panel = self.show_panel   # type: ignore[attr-defined]
        self.api.set_log_sink(self._push_log)
        x, y = _top_right_position()
        self.window = webview.create_window(
            "WFX Smart",
            url=str(UI_INDEX),
            js_api=self.api,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            x=x,
            y=y,
            frameless=True,
            easy_drag=False,
            on_top=True,
            background_color="#0b1020",
        )
        self.window.events.loaded += self.on_loaded
        self.window.events.closing += self._on_closing

        def background():
            # Chạy song song lúc trang đang tải; window.wfxSetStatus/wfxPushLog
            # có thể chưa tồn tại nên không gọi evaluate_js ở đây — chỉ ghi lỗi
            # vào state, _startup() sẽ báo lại khi trang chắc chắn đã sẵn sàng.
            try:
                keyboard.add_hotkey(HOTKEY, self.toggle)
            except Exception as error:
                self._hotkey_error = str(error)
            finally:
                self._hotkey_ready.set()
            self._build_tray()

        webview.start(background, private_mode=False)


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
