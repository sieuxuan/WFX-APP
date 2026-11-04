"""Tự mở lại app sau khi WebView2 chết.

Giao diện không cứu được tại chỗ: mọi `CoreWebView2` đã đóng và state JS đã mất.
Trước khi thoát phải chờ flow đang chạy xong, vì Save hay Create Transaction bị
cắt ngang là không biết WFX đã ghi tới đâu. Chrome làm việc được giữ nguyên.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from wfx_panel import crash_log, telemetry
from wfx_panel.telemetry_labels import ERROR_CODE_INFO
from wfx_panel.version import APP_VERSION

if TYPE_CHECKING:
    from wfx_panel.panel_app import PanelApp

ERROR_CODE = "WEBVIEW2_PROCESS_FAILED"
RECOVERED_ARG = "--recovered-from-webview2"
HISTORY_NAME = "webview2-restarts.json"
# Máy hỏng WebView2 hẳn thì restart mãi chỉ làm icon nhấp nháy và cướp focus.
MAX_RESTARTS = 3
RESTART_WINDOW_SECONDS = 600.0
IDLE_POLL_SECONDS = 1.0
TOAST_TITLE = "WFX Smart"
WAITING_MESSAGE = (
    "Giao diện bị lỗi. Ứng dụng sẽ tự mở lại ngay khi tác vụ đang chạy kết thúc."
)
GAVE_UP_MESSAGE = (
    "Giao diện bị lỗi nhiều lần. Bấm chuột phải biểu tượng WFX Smart cạnh đồng hồ, "
    "chọn Thoát rồi mở lại ứng dụng."
)
RECOVERED_MESSAGE = "Giao diện vừa gặp lỗi và đã tự mở lại."


def claim_restart(base_dir: Path, now: float) -> bool:
    """Giữ một lượt restart; `False` khi đã dùng hết trong cửa sổ thời gian.

    Lịch sử nằm trên đĩa vì mỗi lần restart là một process mới.
    """
    path = Path(base_dir) / HISTORY_NAME
    try:
        history = [float(item) for item in json.loads(path.read_text("utf-8"))]
    except (OSError, ValueError, TypeError):
        history = []
    recent = [item for item in history if now - item < RESTART_WINDOW_SECONDS]
    if len(recent) >= MAX_RESTARTS:
        return False
    try:
        path.write_text(json.dumps([*recent, now]), encoding="utf-8")
    except OSError as error:
        crash_log.record("WEBVIEW2_RESTART_HISTORY_FAILED", error=type(error).__name__)
    return True


def relaunch_command() -> list[str]:
    arguments = [item for item in sys.argv if item != RECOVERED_ARG]
    if getattr(sys, "frozen", False):
        arguments = arguments[1:]
    return [sys.executable, *arguments, RECOVERED_ARG]


class WebView2Recovery:
    def __init__(self, app: PanelApp) -> None:
        self._app = app

    def handle(self, info: dict) -> None:
        app = self._app
        # Thoát app cũng làm WebView2 kết thúc.
        if app._quitting:
            return
        self._report(info)
        if not claim_restart(app.api._base_dir, time.time()):
            crash_log.record("WEBVIEW2_RESTART_GAVE_UP")
            app._notify_native(GAVE_UP_MESSAGE, TOAST_TITLE)
            return
        if app.api.is_action_running():
            app._notify_native(WAITING_MESSAGE, TOAST_TITLE)
            while app.api.is_action_running():
                if app._stop_status.wait(IDLE_POLL_SECONDS):
                    return
        if app._quitting or app._stop_status.is_set():
            return
        self._restart()

    def _report(self, info: dict) -> None:
        """Xếp vào outbox; process mới gửi đi ở `flush_error_reports` lúc khởi động."""
        app = self._app
        title, suggestion = ERROR_CODE_INFO[ERROR_CODE]
        detail = " · ".join(
            str(info[key])
            for key in ("kind", "reason", "exit_code", "window")
            if info.get(key) not in (None, "")
        )
        try:
            account_context = getattr(app.api, "_telemetry_account_context", dict)
            telemetry.enqueue(
                app.api._base_dir,
                {
                    "event_type": "automation_error",
                    "app_version": APP_VERSION,
                    "method": "webview2_watchdog",
                    "code": ERROR_CODE,
                    "message": title,
                    "error_title": title,
                    "error_detail": telemetry.redact_telemetry_text(detail),
                    "suggestion": suggestion,
                    "account": account_context(),
                    **telemetry.system_summary(),
                },
            )
        except Exception as error:  # noqa: BLE001 - báo lỗi không được chặn hồi phục
            crash_log.record("WEBVIEW2_REPORT_FAILED", error=type(error).__name__)

    def _restart(self) -> None:
        self._app.release_for_exit("webview2_restart")
        try:
            subprocess.Popen(
                relaunch_command(),
                # Không kế thừa thư mục tạm của bootloader PyInstaller.
                env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            )
        except Exception as error:  # noqa: BLE001
            crash_log.record("WEBVIEW2_RESTART_FAILED", error=type(error).__name__)
            os._exit(1)
            return
        # Không destroy cửa sổ: sau khi WebView2 chết, destroy() bị treo.
        os._exit(0)
