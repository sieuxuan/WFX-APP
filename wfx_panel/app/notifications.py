"""Toast báo tác vụ xong khi người dùng đang nhìn Chrome.

Toast phải hiện khi foreground đang ở WFX, KỂ CẢ khi panel chưa kịp đổi cờ
sang hidden, và không được hiện trùng khi panel thật sự đang foreground.
Tray sẵn sàng thì dùng notification native để khỏi tốn thêm một WebView2
ẩn và vẫn lưu ở Notification Center; tray chưa sẵn sàng thì giữ thông báo
mới nhất rồi phát ngay sau callback setup. Toast không được lấy focus."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_app import PanelApp

from wfx_panel.app.layout import NOTIFICATION_ACTION_LABELS


class NotificationController:
    def __init__(self, app: PanelApp) -> None:
        self._app = app


    def _hide_notification(self) -> None:
        app = self._app
        app._pending_native_notification = None
        if app.tray is not None:
            try:
                app.tray.remove_notification()
            except Exception:
                pass

    def _notify_native(self, message: str, title: str) -> bool:
        app = self._app
        if app.tray is None or not app._tray_ready.is_set():
            app._pending_native_notification = (message, title)
            return True
        try:
            app.tray.notify(message, title)
            return True
        except Exception as error:
            app.api._log(
                "[NOTIFICATION] Windows toast lỗi: "
                f"{type(error).__name__}: {error}"
            )
            return False

    def _show_notification(
        self,
        result: dict,
        *,
        method: str = "",
        elapsed: float | None = None,
    ) -> bool:
        app = self._app
        if not app._toast_enabled:
            return False
        action_label = NOTIFICATION_ACTION_LABELS.get(method, "WFX Smart")
        status_label = "Hoàn thành" if result.get("ok") else "Cần kiểm tra"
        return self._notify_native(
            str(result.get("message") or "Đã xong."),
            f"{action_label} · {status_label}",
        )

    def show_test_notification(self) -> dict:
        app = self._app
        if not app._toast_enabled:
            return {
                "ok": False,
                "code": "TOAST_DISABLED",
                "message": "Hãy bật Thông báo khi xong việc trước.",
            }
        shown = self._show_notification(
            {
                "ok": True,
                "message": "Toast đang hoạt động và sẽ hiện khi bạn làm việc ở WFX.",
            },
            method="test_notification",
            elapsed=0.0,
        )
        if not shown:
            return {
                "ok": False,
                "code": "TOAST_DISPLAY_FAILED",
                "message": (
                    "Toast chưa hiển thị được. Đã ghi chẩn đoán vào Log kỹ thuật."
                ),
            }
        return {
            "ok": True,
            "code": "TOAST_TESTED",
            "message": "Đã gửi một toast thử nghiệm.",
        }

    def set_toast_enabled_state(self, enabled: bool) -> None:
        app = self._app
        app._toast_enabled = bool(enabled)
        if not app._toast_enabled:
            self._hide_notification()
