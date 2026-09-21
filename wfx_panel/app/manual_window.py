"""Cửa sổ Hướng dẫn sử dụng — chạy offline hoàn toàn.

Không gọi mạng, không cần Chrome, không cần phiên WFX. Bấm Manual lần hai
đưa cửa sổ đang mở lên trước chứ không tạo cửa sổ trùng, và cửa sổ này không
tham gia logic tự thu của panel."""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

import webview

if TYPE_CHECKING:
    from wfx_panel.panel_app import PanelApp

from wfx_panel import manual_book, prefs
from wfx_panel.app.bridges import _ManualBridge
from wfx_panel.app.helpers import _show_webview2_print_dialog
from wfx_panel.app.layout import (
    MANUAL_INDEX,
    MANUAL_WINDOW_HEIGHT,
    MANUAL_WINDOW_MIN,
    MANUAL_WINDOW_TITLE,
    MANUAL_WINDOW_WIDTH,
    WFX_MANUAL_URL,
)
from wfx_panel.version import APP_VERSION


class ManualWindowController:
    def __init__(self, app: PanelApp) -> None:
        self._app = app
        self.window = None
        self._target = ""
        # Nội dung Manual là asset chỉ-đọc đóng gói cùng app nên đọc đúng một
        # lần cho cả phiên. load_book() đọc ~30 file markdown, render HTML và
        # dựng chỉ mục tìm kiếm; trước đây mỗi lần bấm dấu hỏi của một module
        # đều chạy lại toàn bộ việc đó.
        self._book: dict | None = None
        self._entry_by_module: dict[str, str] | None = None

    def book(self) -> dict:
        """Sách hướng dẫn đã dựng, đọc một lần rồi dùng lại."""
        if self._book is None:
            self._book = manual_book.load_book()
        return self._book

    def manual_payload(self) -> dict:
        """Nội dung sách hướng dẫn kèm theme và mục cần mở sẵn.

        Trả bản sao nông: theme và target đổi theo từng lần mở, không được ghi
        đè lên sách đang cache dùng chung.
        """
        return {
            **self.book(),
            "theme": prefs.load_prefs().get("theme", "light"),
            "target": self._target,
            "manual_url": WFX_MANUAL_URL,
        }

    def manual_entry_for_module(self, module_id: str) -> str:
        """Mục hướng dẫn đầu tiên khai báo phủ module này.

        Bảng tra dựng một lần: panel hỏi cho từng module nên quét tuyến tính cả
        sách mỗi lần là O(số module × số mục) mà kết quả không bao giờ đổi.
        """
        if self._entry_by_module is None:
            book = self.book()
            first: dict[str, str] = {}
            for entry_id in book["order"]:
                for covered in book["entries"][entry_id]["covers"]["modules"]:
                    first.setdefault(covered, entry_id)
            self._entry_by_module = first
        return self._entry_by_module.get(module_id, "")

    def manual_error_codes(self) -> list[str]:
        """Mã lỗi đã có mục hướng dẫn riêng, dùng cho nút trợ giúp ở footer."""
        return [row["code"] for row in self.book()["error_table"] if row["entry"]]

    def manual_has_news(self) -> bool:
        """Có tin mới chưa đọc cho đúng phiên bản đang chạy hay không."""
        seen = prefs.load_prefs().get("manual_seen_version", "")
        if seen == APP_VERSION:
            return False
        try:
            versions = {item["version"] for item in manual_book.load_whats_new()}
        except manual_book.ManualContentError:
            return False
        return APP_VERSION in versions

    def get_manual_entry_for_module(self, module_id: str) -> dict:
        return {
            "ok": True,
            "code": "MANUAL_ENTRY",
            "message": "",
            "entry": self.manual_entry_for_module(str(module_id or "")),
        }

    def close_manual_window(self) -> None:
        window, self.window = self.window, None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass

    def print_manual(self) -> dict:
        """Mở hộp thoại in hệ thống; người dùng có thể chọn lưu thành PDF."""
        if self.window is None:
            return {
                "ok": False,
                "code": "MANUAL_PRINT_FAILED",
                "message": "Cửa sổ hướng dẫn chưa mở.",
            }
        if not _show_webview2_print_dialog(self.window):
            return {
                "ok": False,
                "code": "MANUAL_PRINT_FAILED",
                "message": "Không mở được hộp thoại in.",
            }
        return {
            "ok": True,
            "code": "MANUAL_PRINT_OPENED",
            "message": "Đã mở hộp thoại in hoặc lưu PDF.",
        }

    def open_wfx_manual(self, target: str = "") -> dict:
        """Mở Hướng dẫn; bấm lần hai thì đưa cửa sổ đó lên trước.

        `target` là id mục manual hoặc mã lỗi. Rỗng thì mở trang chủ hướng dẫn.
        """
        app = self._app
        self._target = str(target or "")
        if self.manual_has_news() and not self._target:
            self._target = "co-gi-moi"
        prefs.save_prefs(manual_seen_version=APP_VERSION)
        windows = getattr(webview, "windows", None)
        if (
            self.window is not None
            and windows
            and self.window not in windows
        ):
            self.window = None
        if self.window is not None:
            try:
                self.window.show()
                if self._target:
                    self.window.evaluate_js(
                        f"window.wfxManualGoTo({json.dumps(self._target)})"
                    )
                app.hide_panel()
                return {
                    "ok": True,
                    "code": "MANUAL_FOCUSED",
                    "message": "Cửa sổ hướng dẫn đang mở.",
                }
            except Exception:
                self.window = None
        created: list[object] = []
        errors: list[Exception] = []
        ready = threading.Event()

        def create_manual_window() -> None:
            try:
                window = webview.create_window(
                    MANUAL_WINDOW_TITLE,
                    url=str(MANUAL_INDEX),
                    js_api=_ManualBridge(self),
                    width=MANUAL_WINDOW_WIDTH,
                    height=MANUAL_WINDOW_HEIGHT,
                    min_size=MANUAL_WINDOW_MIN,
                    resizable=True,
                    on_top=app._always_on_top,
                )
                created.append(window)
            except Exception as error:
                errors.append(error)
            finally:
                ready.set()

        threading.Thread(
            target=create_manual_window,
            name="WFXManualWindow",
            daemon=True,
        ).start()
        if not ready.wait(5) or not created:
            error = errors[0] if errors else "quá thời gian tạo cửa sổ"
            return {
                "ok": False,
                "code": "MANUAL_OPEN_FAILED",
                "message": f"Không mở được hướng dẫn: {error}",
            }
        window = created[0]
        try:
            window.show()
        except Exception as error:
            return {
                "ok": False,
                "code": "MANUAL_OPEN_FAILED",
                "message": f"Không mở được hướng dẫn: {error}",
            }
        self.window = window
        try:
            window.events.closed += self._on_manual_closed
        except Exception:
            pass
        app.hide_panel()
        return {
            "ok": True,
            "code": "MANUAL_OPENED",
            "message": "Đã mở hướng dẫn sử dụng.",
        }

    def _on_manual_closed(self, *_args) -> None:
        self.window = None
