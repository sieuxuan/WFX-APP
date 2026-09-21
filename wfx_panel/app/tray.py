"""Biểu tượng khay hệ thống và menu của nó.

Menu có hai lựa chọn thoát rõ ràng: ``Thoát và đóng trình duyệt`` gửi CDP
``Browser.close`` tới đúng Chrome automation để giải phóng RAM, còn
``Thoát, giữ trình duyệt`` chỉ đóng app. Không kill process theo tên."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pystray
from PIL import Image

if TYPE_CHECKING:
    from wfx_panel.panel_app import PanelApp

from wfx_panel.app.layout import (
    BUBBLE_DIRECT_ACTION_SUPPRESS_SECONDS,
    ICON_PATH,
)

TRAY_RIGHT_BUTTON_UP = 0x0205  # WM_RBUTTONUP

TRAY_LEFT_BUTTON_DOUBLE_CLICK = 0x0203  # WM_LBUTTONDBLCLK

# WM_USER + 5. Windows gửi message này khi user bấm vào THÂN toast, không phải
# WM_LBUTTONUP như bấm vào icon tray; pystray không xử lý nên phải tự bắt.
TRAY_BALLOON_USER_CLICK = 0x0405  # NIN_BALLOONUSERCLICK

class _WfxTrayIcon(pystray.Icon):
    """Bắt activation/right-click của tray theo đúng hành vi Windows."""

    def __init__(
        self,
        *args,
        on_context_menu=None,
        on_activate=None,
        **kwargs,
    ):
        self._on_context_menu = on_context_menu
        self._on_activate = on_activate
        super().__init__(*args, **kwargs)

    def _on_notify(self, wparam, lparam):
        if (
            int(lparam)
            in (TRAY_LEFT_BUTTON_DOUBLE_CLICK, TRAY_BALLOON_USER_CLICK)
            and self._on_activate
        ):
            self._on_activate()
            return None
        if int(lparam) == TRAY_RIGHT_BUTTON_UP and self._on_context_menu:
            self._on_context_menu()
        return super()._on_notify(wparam, lparam)


class TrayController:
    def __init__(self, app: PanelApp) -> None:
        self._app = app


    def _build_tray(self):
        app = self._app
        image = Image.open(ICON_PATH)
        menu = pystray.Menu(
            pystray.MenuItem("Hiện WFX Smart", lambda: app.show_from_tray()),
            pystray.MenuItem(
                "Thoát và đóng trình duyệt",
                lambda: app.quit(close_browser=True),
            ),
            pystray.MenuItem("Thoát, giữ trình duyệt", lambda: app.quit()),
        )
        app.tray = _WfxTrayIcon(
            "wfx-panel",
            image,
            "WFX Smart Panel",
            menu,
            on_context_menu=self._note_tray_context_menu,
            on_activate=app.show_from_tray,
        )
        app.tray.run(setup=self._on_tray_ready)  # blocking → thread riêng

    def _on_tray_ready(self, icon) -> None:
        """Hiện tray rồi phát thông báo sớm nhất đã xếp hàng lúc startup."""
        app = self._app
        icon.visible = True
        app._tray_ready.set()
        pending = app._pending_native_notification
        app._pending_native_notification = None
        if pending is not None and app._toast_enabled:
            app._notify_native(*pending)

    def _note_tray_context_menu(self) -> None:
        """Chặn tray right-click bị taskbar monitor hiểu nhầm là bubble."""
        app = self._app
        app._taskbar_focus_armed = False
        app._bubble_direct_action_until = (
            time.monotonic() + BUBBLE_DIRECT_ACTION_SUPPRESS_SECONDS
        )
