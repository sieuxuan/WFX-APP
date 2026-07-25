from __future__ import annotations

import threading

import keyboard
import pystray
import webview
from PIL import Image

from wfx_panel import prefs
from wfx_panel.assets.generate_icon import build_icon
from wfx_panel.panel_api import PanelAPI

HOTKEY = "ctrl+shift+x"
ICON_PATH = prefs.APP_DIR / "wfx_panel" / "assets" / "wfx.ico"
UI_INDEX = prefs.APP_DIR / "wfx_panel" / "ui" / "index.html"


class PanelApp:
    def __init__(self):
        self.api = PanelAPI()
        self.window = None
        self.tray = None
        self._visible = True

    # -- window bridge -----------------------------------------------------
    def _push_log(self, line: str) -> None:
        if self.window is None:
            return
        from wfx_panel.log_bridge import js_string
        try:
            self.window.evaluate_js(f"window.wfxPushLog({js_string(line)})")
        except Exception:
            pass

    def hide_panel(self):
        if self.window and self._visible:
            self.window.hide()
            self._visible = False

    def show_panel(self):
        if self.window and not self._visible:
            self.window.show()
            self._visible = True

    def toggle(self):
        if self._visible:
            self.hide_panel()
        else:
            self.show_panel()

    # -- lifecycle ---------------------------------------------------------
    def on_loaded(self):
        # Chạy nền: bơm trạng thái ban đầu + auto-login, không chặn UI.
        threading.Thread(target=self._startup, daemon=True).start()

    def _startup(self):
        try:
            state = self.api.get_initial_state()
            from wfx_panel.log_bridge import js_string
            import json
            self.window.evaluate_js(f"window.wfxBootstrap({json.dumps(state, ensure_ascii=False)})")
            account = prefs.load_account()
            if account["user_id"] and account["password"]:
                self._push_log("[SESSION] Tự động đăng nhập...")
                result = self.api.login()
            else:
                result = self.api.check_session()
            tone = "success" if result.get("ok") else "warning"
            self.window.evaluate_js(
                f"window.wfxSetStatus({js_string(tone)}, {js_string(result.get('message',''))})"
            )
        except Exception as error:  # startup không được làm sập app
            self._push_log(f"[ERROR] Startup lỗi: {error}")

    def _build_tray(self):
        image = Image.open(ICON_PATH)
        menu = pystray.Menu(
            pystray.MenuItem("Hiện panel", lambda: self.show_panel(), default=True),
            pystray.MenuItem("Thoát", lambda: self.quit()),
        )
        self.tray = pystray.Icon("wfx-panel", image, "WFX Smart Panel", menu)
        self.tray.run()  # blocking → chạy trong thread riêng

    def quit(self):
        try:
            keyboard.remove_hotkey(HOTKEY)
        except (KeyError, ValueError):
            pass
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
        self.window = webview.create_window(
            "WFX Smart",
            url=str(UI_INDEX),
            js_api=self.api,
            width=440,
            height=620,
            frameless=True,
            easy_drag=False,
            on_top=True,
            background_color="#0b1020",
        )
        self.window.events.loaded += self.on_loaded

        def background():
            try:
                keyboard.add_hotkey(HOTKEY, self.toggle)
            except Exception as error:
                self._push_log(f"[ERROR] Không đăng ký được hotkey: {error}")
            self._build_tray()

        webview.start(background, private_mode=False)


def main():
    PanelApp().run()


if __name__ == "__main__":
    main()
