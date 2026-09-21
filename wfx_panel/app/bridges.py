"""js_api riêng cho bubble, bubble menu và cửa sổ Manual.

Mỗi cửa sổ pywebview có js_api của chính nó; các lớp mỏng ở đây chỉ chuyển
lời gọi về ``PanelApp`` để cửa sổ con không cầm nguyên bề mặt của panel.
"""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

from wfx_panel.app.layout import WFX_MANUAL_URL

if TYPE_CHECKING:
    from wfx_panel.panel_app import PanelApp


class _BubbleBridge:
    """Cầu nối JS cho cửa sổ bubble (icon nổi thường trực)."""

    def __init__(self, app: PanelApp):
        self._app = app

    def toggle_panel(self) -> dict:
        return self._app.toggle_panel()

    def save_bubble_position(self) -> dict:
        return self._app.save_bubble_position()

    def note_bubble_interaction(self) -> dict:
        return self._app.note_bubble_interaction()

    def begin_bubble_interaction(self) -> dict:
        return self._app.begin_bubble_interaction()

    def end_bubble_interaction(self) -> dict:
        return self._app.end_bubble_interaction()

    def bubble_context_menu(self) -> dict:
        return self._app.bubble_context_menu()


class _ManualBridge:
    """Cầu nối JS cho cửa sổ Hướng dẫn sử dụng.

    Cửa sổ này hoàn toàn offline: nó chỉ đọc nội dung tĩnh đã đóng gói, không
    chạm tới Playwright, Chrome hay phiên WFX. Nhờ vậy người dùng tra cứu được
    ngay cả khi chưa đăng nhập hoặc đang mất mạng.
    """

    def __init__(self, app: PanelApp):
        self._app = app

    def get_manual_book(self) -> dict:
        return self._app.manual_payload()

    def print_manual(self) -> dict:
        return self._app.print_manual()

    def open_manual_external(self) -> dict:
        try:
            opened = bool(webbrowser.open(WFX_MANUAL_URL, new=2))
        except Exception as error:
            return {
                "ok": False,
                "code": "MANUAL_OPEN_FAILED",
                "message": f"Không mở được trang WFX: {error}",
            }
        return {
            "ok": opened,
            "code": "MANUAL_OPENED" if opened else "MANUAL_OPEN_FAILED",
            "message": (
                "Đã mở System Manual của WFX."
                if opened
                else "Không tìm thấy trình duyệt."
            ),
        }

    def close_manual(self) -> dict:
        self._app.close_manual_window()
        return {"ok": True, "code": "MANUAL_CLOSED", "message": ""}


class _BubbleMenuBridge:
    """Cầu nối cho popup menu tách riêng khỏi cửa sổ bubble."""

    def __init__(self, app: PanelApp):
        self._app = app

    def choose(self, action: str) -> dict:
        return self._app.choose_bubble_menu(action)

    def dismiss(self) -> dict:
        return self._app.dismiss_bubble_menu()
