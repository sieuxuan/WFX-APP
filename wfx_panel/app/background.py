"""Bốn vòng lặp nền: trạng thái, giữ phiên, cập nhật và Article Library.

Heartbeat giữ phiên chạy mỗi 4 phút khi Chrome rảnh. Lượt THÀNH CÔNG phải
im lặng tuyệt đối — không ghi ``jobs.json``, không thêm log RUN, không đổi
footer; chỉ khi hỏng mới được để lại đúng một dòng.

Vòng cập nhật chạy mỗi 4 giờ và không tự cài: nó chỉ đẩy trạng thái lên UI."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_app import PanelApp

from wfx_panel import prefs, status, updater
from wfx_panel.app.layout import (
    ARTICLE_LIBRARY_INITIAL_DELAY_SECONDS,
    ARTICLE_LIBRARY_POLL_SECONDS,
    SESSION_MAINTENANCE_INITIAL_DELAY_SECONDS,
    SESSION_MAINTENANCE_SECONDS,
    STATUS_POLL_SECONDS,
    UPDATE_INITIAL_DELAY_SECONDS,
    UPDATE_POLL_SECONDS,
)


class BackgroundLoopController:
    def __init__(self, app: PanelApp) -> None:
        self._app = app


    def _status_loop(self) -> None:
        app = self._app
        next_session_maintenance = (
            time.monotonic() + SESSION_MAINTENANCE_INITIAL_DELAY_SECONDS
        )
        while not app._stop_status.wait(STATUS_POLL_SECONDS):
            # Một lỗi native/evaluate_js tạm thời không được giết luôn thread,
            # nếu không trạng thái Chrome sẽ đứng im cả phiên.
            try:
                alive = status.chrome_alive()
                if alive != app._chrome_alive:
                    app._chrome_alive = alive
                    if app.window is not None:
                        app.window.evaluate_js(
                            "window.wfxSetChromeStatus("
                            f"{'true' if alive else 'false'})"
                        )

                now = time.monotonic()
                if now < next_session_maintenance:
                    continue
                next_session_maintenance = now + SESSION_MAINTENANCE_SECONDS
                if (
                    alive
                    and app.api.should_maintain_session()
                    and not app.api.is_action_running()
                ):
                    app.api.maintain_session()
            except Exception:
                continue

    def _check_update_once(self) -> None:
        app = self._app
        state = app.api.check_for_updates()
        app._push_update_state(state)
        notice_id = str(
            state.get("notice_id") or state.get("tag") or state.get("version") or ""
        )
        if (
            state.get("can_update")
            and notice_id
            and notice_id != app._last_update_notice
        ):
            app._last_update_notice = notice_id
            prefs.save_prefs(last_update_notice=notice_id)
            if app.tray is not None and app._toast_enabled:
                try:
                    app.tray.notify(
                        "Có phiên bản WFX Smart mới. Mở ứng dụng và bấm “Cập nhật ngay”.",
                        "WFX Smart",
                    )
                except Exception:
                    pass

    def _update_loop(self) -> None:
        app = self._app
        if app._stop_status.wait(UPDATE_INITIAL_DELAY_SECONDS):
            return
        while not app._stop_status.is_set():
            try:
                self._check_update_once()
            except Exception as error:
                app._push_log(
                    f"[UPDATE] Không kiểm tra tự động được: {type(error).__name__}"
                )
            if app._stop_status.wait(UPDATE_POLL_SECONDS):
                return

    def _article_library_loop(self) -> None:
        app = self._app
        if app._stop_status.wait(ARTICLE_LIBRARY_INITIAL_DELAY_SECONDS):
            return
        while not app._stop_status.is_set():
            try:
                result = app.api.sync_reference_data(False)
                if not result.get("ok"):
                    # Tương thích offline/cấu hình cũ: GitHub vẫn là fallback,
                    # không bao giờ xóa cache PostgreSQL cuối cùng.
                    fallback = app.api.sync_article_library()
                    if fallback.get("ok"):
                        result = {**result, **fallback}
                if app.window is not None:
                    import json

                    app.window.evaluate_js(
                        "window.wfxSetReferenceSyncStatus("
                        f"{json.dumps(result, ensure_ascii=False)});"
                        "window.wfxSetArticleLibraryStatus("
                        f"{json.dumps(result, ensure_ascii=False)})"
                    )
            except Exception as error:
                app._push_log(
                    "[ARTICLE LIBRARY] Không kiểm tra tự động được: "
                    f"{type(error).__name__}"
                )
            if app._stop_status.wait(ARTICLE_LIBRARY_POLL_SECONDS):
                return

    def _apply_update(self, state: dict) -> str | None:
        app = self._app
        try:
            if not getattr(sys, "frozen", False):
                return (
                    "Bản development không tự cài cập nhật. "
                    "Hãy build WFX-Panel.exe hoặc cài bản phát hành đã ký."
                )
            executable = Path(sys.executable)

            updater.schedule_update(
                state,
                current_pid=os.getpid(),
                executable=executable,
            )
            threading.Timer(1.0, app.quit).start()
            return None
        except Exception as error:
            return f"Không lên lịch được cập nhật: {error}"
