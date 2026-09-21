"""Chạy một flow automation: khóa, hủy theo checkpoint, lịch sử, telemetry.

Mọi flow từ ``PanelAPI._run()`` đi qua đây và chạy trên automation worker
duy nhất. Khóa là RLock chứ không phải Lock: thao tác Costing là composite
gồm NHIỀU ``_run`` liên tiếp, nhả khóa giữa các bước sẽ cho flow khác đổi
module/Division khiến bước sau thao tác nhầm màn hình.

Lịch sử và telemetry là phụ trợ: ổ đĩa đầy hay payload không serialize được
KHÔNG được biến một flow đã chạy xong thành exception bay ra bridge
pywebview — khi đó UI mất kết quả và các nút workflow đứng busy vĩnh viễn.

``_run_lock``/``_current_run_id`` ở lại ``PanelAPI``: chúng là trạng thái
toàn cục của bridge, và test/`panel_app` đọc thẳng qua ``api``."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import crash_log, job_history, telemetry
from wfx_panel.automation import runtime as automation_runtime
from wfx_panel.automation.runtime import AutomationCancelled
from wfx_panel.run_policy import (
    CATALOG_CONTEXT_INVALIDATING_METHODS,
    DIAGNOSTIC_FAILURES,
    LOGIN_CODES,
    NON_REPORTABLE_FAILURES,
    SCREENSHOT_METHODS,
    SESSION_LOST,
    SESSION_OK,
)
from wfx_panel.version import APP_VERSION


def _flush_telemetry_quietly(base_dir, endpoint: str) -> None:
    """Gửi outbox ở thread nền mà không bao giờ để lỗi giết thread im lặng.

    ``telemetry.flush`` ghi lại outbox bằng temp file + replace, nên ổ đĩa đầy,
    quyền bị chặn hay antivirus khoá file tạm đều làm nó ném ``OSError``. Thread
    này là daemon và không ai join, nên một exception ở đây chỉ làm thread chết
    không dấu vết — đúng loại lỗi mà ``crash_log`` sinh ra để thấy được. Cùng
    tinh thần với docstring module: telemetry là phụ trợ, không được làm hỏng
    tiến trình đang chạy.
    """
    try:
        telemetry.flush(base_dir, endpoint)
    except Exception as error:  # noqa: BLE001 - thread nền phải nuốt mọi lỗi
        crash_log.record(
            "TELEMETRY_FLUSH_FAILED",
            exception=f"{type(error).__name__}: {error}",
        )


class AutomationRunEngine:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel


    def _run(
        self,
        method_name: str,
        action: Callable[[], dict],
        request: dict | None = None,
        *,
        record_job: bool = True,
        record_job_on_failure: bool = False,
        announce: bool = True,
        emit_result: bool = True,
    ) -> dict:
        panel = self._panel
        if not panel._run_lock.acquire(blocking=False):
            return self._action_in_progress()
        self._enter_run()
        try:
            return automation_runtime.run(
                lambda: self._run_unlocked(
                    method_name,
                    action,
                    request,
                    record_job=record_job,
                    record_job_on_failure=record_job_on_failure,
                    announce=announce,
                    emit_result=emit_result,
                )
            )
        finally:
            self._exit_run()
            panel._run_lock.release()

    def _run_unlocked(
        self,
        method_name: str,
        action: Callable[[], dict],
        request: dict | None = None,
        *,
        record_job: bool = True,
        record_job_on_failure: bool = False,
        announce: bool = True,
        emit_result: bool = True,
    ) -> dict:
        panel = self._panel
        run_id = job_history.new_run_id()
        started = time.monotonic()
        started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        panel._current_run_id = run_id
        if announce:
            panel._log(f"[RUN] Bắt đầu {method_name}")

        result = self._normalised_result(method_name, action)
        elapsed = time.monotonic() - started
        code = str(result.get("code") or "UNKNOWN")
        failed = not result.get("ok")

        # Kiểm tra nền thành công phải im lặng tuyệt đối, nhưng khi nó hỏng thì
        # người dùng bị hỏi đăng nhập lại mà không có chỗ nào tra ra vì sao —
        # nên một lần hỏng vẫn phải để lại đúng một dòng lịch sử.
        if record_job_on_failure and failed:
            record_job = True

        screenshot = (
            self._capture_failure_screenshot(run_id)
            if record_job and failed and self._wants_failure_screenshot(method_name, code)
            else None
        )
        result = {
            **result,
            "run_id": run_id,
            "requires_attention": job_history.requires_attention(result),
        }
        self._announce_finish(method_name, result, elapsed, announce)
        panel._current_run_id = None

        # Lịch sử và telemetry là phụ trợ: hỏng thì ghi log, không ném ra bridge.
        if record_job:
            self._append_job_history(
                run_id, method_name, request, result, started_at, elapsed, screenshot
            )
        if failed and code not in NON_REPORTABLE_FAILURES:
            try:
                self._report_automation_error(
                    method_name, result, request, code, run_id, elapsed
                )
            except Exception as error:
                panel._log(f"[RUN] Không xếp được báo lỗi: {type(error).__name__}")

        self._observe(method_name, result, elapsed, emit_result=emit_result)
        return {**result, **panel._session_status(), **panel._division_state()}

    def _normalised_result(self, method_name: str, action: Callable[[], dict]) -> dict:
        """Chạy action và quy mọi kết cục về đúng một dict kết quả."""
        panel = self._panel
        try:
            result = panel._run_action_with_auto_relogin(method_name, action)
        except AutomationCancelled:
            return {
                "ok": False,
                "code": "ACTION_CANCELLED",
                "message": "Đã dừng tác vụ tại checkpoint an toàn.",
            }
        except Exception as error:
            return {
                "ok": False,
                "code": "PANEL_ERROR",
                "message": f"{type(error).__name__}: {error}",
            }
        if not isinstance(result, dict):
            return {
                "ok": False,
                "code": "PANEL_ERROR",
                "message": "Kết quả không hợp lệ.",
            }
        return result

    def _wants_failure_screenshot(self, method_name: str, code: str) -> bool:
        panel = self._panel
        if method_name not in SCREENSHOT_METHODS:
            return False
        if code in NON_REPORTABLE_FAILURES and code not in DIAGNOSTIC_FAILURES:
            return False
        return hasattr(panel._login, "capture_failure_screenshot")

    def _capture_failure_screenshot(self, run_id: str) -> str | None:
        """Ảnh chẩn đoán cho một lượt hỏng; None nếu không chụp được."""
        panel = self._panel
        shot = job_history.screenshot_dir(panel._base_dir) / f"{run_id}.png"
        try:
            if panel._login.capture_failure_screenshot(shot, panel._log):
                return str(shot)
        except Exception:
            return None
        return None

    def _append_job_history(
        self,
        run_id: str,
        method_name: str,
        request: dict | None,
        result: dict,
        started_at: str,
        elapsed: float,
        screenshot: str | None,
    ) -> None:
        """Ghi một dòng lịch sử. Lỗi ghi KHÔNG được làm hỏng kết quả flow.

        Ổ đĩa đầy, jobs.json bị khóa hoặc payload không serialize được mà ném
        ra bridge pywebview là UI mất kết quả và các nút workflow đứng busy
        vĩnh viễn.
        """
        panel = self._panel
        try:
            job_history.append(
                panel._base_dir,
                {
                    "run_id": run_id,
                    "method": method_name,
                    "request": dict(request or {}),
                    "ok": bool(result.get("ok")),
                    "code": str(result.get("code") or "UNKNOWN"),
                    "message": str(result.get("message") or ""),
                    "started_at": started_at,
                    "elapsed_ms": int(elapsed * 1000),
                    "screenshot": screenshot,
                },
            )
        except Exception as error:
            panel._log(f"[RUN] Không ghi được lịch sử: {type(error).__name__}")

    def _announce_finish(
        self, method_name: str, result: dict, elapsed: float, announce: bool
    ) -> None:
        panel = self._panel
        code = result.get("code", "UNKNOWN")
        if announce:
            panel._log(
                f"[RUN] Kết thúc {method_name}: {code} ({int(elapsed * 1000)} ms)"
            )
        elif not result.get("ok"):
            panel._log(f"[SESSION] Kiểm tra nền cần chú ý: {code}.")

    def _report_automation_error(
        self,
        method_name: str,
        result: dict,
        request: dict | None,
        code: str,
        run_id: str,
        elapsed: float,
    ) -> None:
        panel = self._panel
        error_context = telemetry.automation_error_context(
            method_name,
            result,
            request,
        )
        telemetry.enqueue(
            panel._base_dir,
            {
                "event_type": "automation_error",
                "app_version": APP_VERSION,
                "method": method_name,
                "code": code,
                "run_id": run_id,
                "elapsed_ms": int(elapsed * 1000),
                **error_context,
                "account": panel._telemetry_account_context(),
                **telemetry.system_summary(),
            },
        )
        # Chốt endpoint trước khi tạo thread. Nếu test/cấu hình hiện tại
        # đã tắt webhook thì thread chạy trễ cũng không được tự resolve lại
        # DEFAULT_WEBHOOK_URL và gửi payload sang production.
        telemetry_endpoint = telemetry.webhook_url(panel._base_dir)
        threading.Thread(
            target=_flush_telemetry_quietly,
            args=(panel._base_dir, telemetry_endpoint),
            name="wfx-telemetry-flush",
            daemon=True,
        ).start()

    def _observe(
        self,
        method_name: str,
        result: dict,
        elapsed: float,
        *,
        emit_result: bool = True,
    ) -> None:
        panel = self._panel
        code = str(result.get("code") or "")
        if code in SESSION_OK:
            panel._session_active = True
            if code in LOGIN_CODES:
                panel._last_login_at = time.strftime("%H:%M:%S")
        elif code in SESSION_LOST:
            panel._session_active = False
            panel._current_division = None
            panel._division_label = None
            panel._division_name = None
            panel._catalog.reset_context()

        if code in {"LOGGED_IN", "LOGGED_IN_AFTER_DELAY"}:
            panel._remember_session_user(
                result.get("session_user_id") or panel._account()["user_id"]
            )
        elif (
            code in {"SESSION_REUSED", "SESSION_ACTIVE"}
            and panel._session_user_id is None
        ):
            # Phiên có sẵn trong Chrome không chứng minh được là của ai. Giả
            # định nó thuộc tài khoản đang lưu: đoán sai thì lần đổi tài khoản
            # sau chỉ tốn thêm một lần đăng nhập, còn bỏ trống thì mất luôn
            # lớp chặn "chạy nhầm bằng tài khoản người khác".
            panel._remember_session_user(
                result.get("session_user_id") or panel._account()["user_id"]
            )
        elif code in {"NOT_LOGGED_IN", "MISSING_CREDENTIALS"}:
            # Phiên trong Chrome đã mất -> không còn tài khoản nào "đang sở
            # hữu" nó. Giữ lại giá trị cũ sẽ ép một lần đổi tài khoản thừa.
            panel._remember_session_user(None)

        if code in SESSION_LOST or code in {
            "DIVISION_CHANGED",
            "LOGGED_IN",
            "LOGGED_IN_AFTER_DELAY",
            "SESSION_RESTORED",
        }:
            reset_menu_cache = getattr(
                panel._login, "reset_menu_route_cache", None
            )
            if callable(reset_menu_cache):
                reset_menu_cache()

        if code in {"DIVISION_CHANGED", "LOGGED_IN", "LOGGED_IN_AFTER_DELAY"}:
            panel._catalog.reset_context()

        if (
            result.get("ok")
            and method_name in CATALOG_CONTEXT_INVALIDATING_METHODS
        ):
            panel._catalog.reset_context()

        if result.get("current_division") is not None:
            panel._current_division = str(result["current_division"])
            panel._division_label = str(result.get("division_label") or "")
            panel._division_name = str(result.get("division_name") or "")

        quiet_keepalive = (
            method_name == "maintain_session"
            and code in {"SESSION_ACTIVE", "SESSION_REUSED"}
        )
        if emit_result and not quiet_keepalive and panel._result_sink is not None:
            try:
                panel._result_sink(method_name, result, elapsed)
            except Exception:
                pass

    def _progress(
        self,
        method: str,
        stage: str,
        message: str,
        step: int,
        total: int,
        *,
        state: str = "active",
    ) -> None:
        panel = self._panel
        if panel._progress_sink is None:
            return
        try:
            panel._progress_sink(
                {
                    "method": str(method),
                    "stage": str(stage),
                    "message": str(message),
                    "step": max(1, int(step)),
                    "total": max(1, int(total)),
                    "state": str(state),
                    "run_id": panel._current_run_id,
                }
            )
        except Exception:
            pass

    def _progress_for(self, method: str) -> Callable[..., None]:
        """Callback progress đã gắn sẵn method của flow đang chạy."""

        def emit(
            stage: str,
            message: str,
            step: int,
            total: int,
            *,
            state: str = "active",
        ) -> None:
            self._progress(method, stage, message, step, total, state=state)

        return emit

    def _action_in_progress(self) -> dict:
        panel = self._panel
        return {
            "ok": False,
            "code": "ACTION_IN_PROGRESS",
            "message": "WFX Smart đang xử lý tác vụ trước. Vui lòng chờ hoàn tất.",
            **panel._session_status(),
            **panel._division_state(),
        }

    def _enter_run(self) -> None:
        panel = self._panel
        with panel._run_depth_lock:
            panel._run_depth += 1

    def _exit_run(self) -> None:
        panel = self._panel
        with panel._run_depth_lock:
            panel._run_depth = max(0, panel._run_depth - 1)

    def run_composite(self, steps: Callable[[], dict]) -> dict:
        """Chạy một chuỗi nhiều ``_run`` như MỘT tác vụ không thể chen ngang.

        Import/export Costing phải mở đúng Costing rồi mới scan/apply. Nếu run
        lock được nhả giữa hai bước, một flow khác (mở module, đổi Division,
        tìm Catalog) có thể chen vào và bước sau sẽ thao tác trên màn hình khác
        hẳn — trong khi plan token 15 phút không hề biết điều đó.
        """
        panel = self._panel
        if not panel._run_lock.acquire(blocking=False):
            return self._action_in_progress()
        self._enter_run()
        try:
            return steps()
        finally:
            self._exit_run()
            panel._run_lock.release()

    def cancel_current_action(self) -> dict:
        panel = self._panel
        if automation_runtime.request_cancel():
            panel._log("[STOP] Đã nhận yêu cầu dừng; đang chờ checkpoint an toàn.")
            return {
                "ok": True,
                "code": "CANCEL_REQUESTED",
                "message": "Đang dừng tại checkpoint an toàn…",
                "run_id": panel._current_run_id,
            }
        return {
            "ok": False,
            "code": "NO_ACTION_RUNNING",
            "message": "Không có tác vụ automation đang chạy.",
        }

    def is_action_running(self) -> bool:
        """Nguồn trạng thái native để panel tự thu không phụ thuộc WebView."""
        panel = self._panel
        with panel._run_depth_lock:
            return panel._run_depth > 0
