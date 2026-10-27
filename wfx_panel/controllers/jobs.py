"""Lịch sử tác vụ, ảnh chẩn đoán, chạy lại job và gửi góp ý.

``retry_job`` chạy lại bằng CHÍNH method đã sinh ra job, đọc từ lịch sử,
nên mọi flow mới tự có Retry mà không phải khai báo thêm."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import job_history, telemetry
from wfx_panel.coercion import boolean
from wfx_panel.version import APP_VERSION


class JobsController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel


    # -- job history ------------------------------------------------------
    def get_job_history(self, limit: int = 30) -> dict:
        panel = self._panel
        return {
            "ok": True,
            "code": "JOB_HISTORY",
            "jobs": job_history.list_jobs(panel._base_dir, limit),
        }

    def acknowledge_job(self, run_id: str) -> dict:
        panel = self._panel
        acknowledged = job_history.acknowledge(panel._base_dir, run_id)
        return {
            "ok": acknowledged,
            "code": "JOB_ACKNOWLEDGED" if acknowledged else "JOB_NOT_FOUND",
            "message": (
                "Đã đánh dấu tác vụ là đã xử lý."
                if acknowledged
                else "Không tìm thấy lần chạy này."
            ),
            "jobs": job_history.list_jobs(panel._base_dir, 30),
        }

    def retry_job(self, run_id: str) -> dict:
        panel = self._panel
        job = job_history.get_job(panel._base_dir, run_id)
        if job is None:
            return {
                "ok": False,
                "code": "JOB_NOT_FOUND",
                "message": "Không tìm thấy lần chạy này.",
            }
        request = job.get("request") or {}
        method = job.get("method")
        if not job_history.can_retry(job):
            return {
                "ok": False,
                "code": "JOB_NOT_RETRYABLE",
                "message": (
                    "Tác vụ này không thể chạy lại vì lịch sử không lưu "
                    "nội dung tìm kiếm nhạy cảm."
                ),
            }
        # Chỉ những method mà `job_history.can_retry` cho qua mới cần handler.
        # Các flow mang query/Article Code bị `_safe_request` xóa khỏi lịch sử
        # nên không bao giờ tới được đây; giữ handler cho chúng chỉ tạo ảo giác
        # là app chạy lại được. `tests/test_jobs_controller.py` canh hai danh
        # sách này luôn trùng nhau.
        category_name = str(request.get("category_name") or "Apparel")
        retry_handlers: dict[str, Callable[[], dict]] = {
            "login": panel.login,
            "check_session": panel.check_session,
            "open_module": lambda: panel.open_module(
                str(request.get("module_id") or "")
            ),
            "prepare_catalog": lambda: panel.prepare_catalog(category_name),
            "scan_catalog_folders": lambda: panel.scan_catalog_folders(
                category_name,
                True,
            ),
            "browse_catalog": lambda: panel.browse_catalog(category_name),
        }
        handler = retry_handlers.get(str(method or ""))
        if handler is not None:
            return handler()
        return {
            "ok": False,
            "code": "JOB_NOT_RETRYABLE",
            "message": "Tác vụ này không hỗ trợ chạy lại.",
        }

    def open_job_screenshot(self, run_id: str) -> dict:
        panel = self._panel
        job = job_history.get_job(panel._base_dir, run_id)
        path = Path(str((job or {}).get("screenshot") or "")).resolve()
        allowed_dir = job_history.screenshot_dir(panel._base_dir).resolve()
        if (
            job is None
            or not path.is_file()
            or path.suffix.lower() != ".png"
            or path.parent != allowed_dir
        ):
            return {
                "ok": False,
                "code": "SCREENSHOT_NOT_FOUND",
                "message": "Không có ảnh lỗi cho lần chạy này.",
            }
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                return {
                    "ok": False,
                    "code": "SCREENSHOT_OPEN_UNSUPPORTED",
                    "message": "Chỉ hỗ trợ mở ảnh trực tiếp trên Windows.",
                }
            return {
                "ok": True,
                "code": "SCREENSHOT_OPENED",
                "message": "Đã mở ảnh lỗi.",
            }
        except OSError as error:
            return {
                "ok": False,
                "code": "SCREENSHOT_OPEN_FAILED",
                "message": f"Không mở được ảnh lỗi: {error}",
            }

    def clear_job_history(self) -> dict:
        panel = self._panel
        job_history.clear(panel._base_dir)
        return {
            "ok": True,
            "code": "JOB_HISTORY_CLEARED",
            "message": "Đã xóa lịch sử và ảnh lỗi cục bộ.",
            "jobs": [],
        }

    def clear_log(self) -> dict:
        panel = self._panel
        panel._logs = []
        return {"ok": True, "code": "LOG_CLEARED", "message": "Đã xóa nhật ký"}

    def submit_feedback(
        self,
        kind: str,
        message: str,
        include_diagnostics: bool = True,
    ) -> dict:
        panel = self._panel
        kind = "bug" if str(kind).casefold() == "bug" else "feedback"
        message = str(message or "").strip()
        if len(message) < 5:
            return {
                "ok": False,
                "code": "FEEDBACK_TOO_SHORT",
                "message": "Vui lòng mô tả ít nhất 5 ký tự.",
            }
        if len(message) > 2_000:
            return {
                "ok": False,
                "code": "FEEDBACK_TOO_LONG",
                "message": "Nội dung góp ý tối đa 2.000 ký tự.",
            }
        include_diagnostics = boolean(include_diagnostics, True)
        event = {
            "event_type": "user_feedback",
            "kind": kind,
            "message": message,
            "app_version": APP_VERSION,
            "account": panel._telemetry_account_context(),
        }
        if include_diagnostics:
            recent = job_history.list_jobs(panel._base_dir, 5)
            event["diagnostics"] = {
                **telemetry.system_summary(),
                **panel.get_status(),
                "recent_jobs": [
                    {
                        "run_id": row.get("run_id"),
                        "method": row.get("method"),
                        "ok": row.get("ok"),
                        "code": row.get("code"),
                        "elapsed_ms": row.get("elapsed_ms"),
                    }
                    for row in recent
                ],
            }
        delivery = telemetry.submit(panel._base_dir, event)
        sent = delivery.get("delivery") == "sent"
        return {
            **delivery,
            "code": "FEEDBACK_SENT" if sent else "FEEDBACK_QUEUED",
            "message": (
                "Đã gửi góp ý. Cảm ơn bạn."
                if sent
                else "Chưa gửi được ngay; góp ý đã lưu an toàn và sẽ tự gửi lại."
            ),
            "reporting_configured": telemetry.is_configured(panel._base_dir),
        }

    def report_job(self, run_id: str) -> dict:
        """Báo lỗi MỘT CHẠM cho một lần chạy hỏng.

        Người dùng không phải mô tả gì: họ chỉ bấm "Báo lỗi". Đổi lại, báo cáo
        gửi về nhóm hỗ trợ phải đủ để chẩn đoán mà không cần hỏi lại — lỗi đã
        diễn giải, Run ID, context request đã whitelist, tài khoản, máy và đuôi
        log của đúng lần chạy đó (đã qua ``redact_telemetry_text``).
        """
        panel = self._panel
        run_id = str(run_id or "").strip()
        job = job_history.get_job(panel._base_dir, run_id) if run_id else None
        if job is None:
            return {
                "ok": False,
                "code": "JOB_NOT_FOUND",
                "message": "Không tìm thấy lần chạy này.",
            }
        if job.get("ok"):
            return {
                "ok": False,
                "code": "JOB_NOT_REPORTABLE",
                "message": "Tác vụ này đã chạy thành công.",
            }
        if job.get("reported"):
            return {
                "ok": True,
                "code": "JOB_ALREADY_REPORTED",
                "message": "Lỗi này đã được báo. Cảm ơn bạn.",
                "jobs": job_history.list_jobs(panel._base_dir, 30),
            }
        method = str(job.get("method") or "")
        code = str(job.get("code") or "UNKNOWN")
        request = job.get("request") if isinstance(job.get("request"), dict) else {}
        context = telemetry.automation_error_context(method, job, request)
        log_tail = job.get("log_tail") or panel._run_log_lines(run_id)
        recent = job_history.list_jobs(panel._base_dir, 5)
        event = {
            "event_type": "user_feedback",
            "kind": "bug",
            "source": "one_click",
            "app_version": APP_VERSION,
            "method": method,
            "code": code,
            "run_id": run_id,
            "started_at": job.get("started_at"),
            "elapsed_ms": job.get("elapsed_ms"),
            "has_screenshot": bool(job.get("screenshot")),
            **context,
            "message": f"Người dùng bấm Báo lỗi: {context['message']}"[:4_000],
            "account": panel._telemetry_account_context(),
            "log_tail": telemetry.redact_log_lines(log_tail),
            "diagnostics": {
                **telemetry.system_summary(),
                **panel.get_status(),
                "recent_jobs": [
                    {
                        "run_id": row.get("run_id"),
                        "method": row.get("method"),
                        "ok": row.get("ok"),
                        "code": row.get("code"),
                        "elapsed_ms": row.get("elapsed_ms"),
                    }
                    for row in recent
                ],
            },
        }
        delivery = telemetry.submit(panel._base_dir, event)
        job_history.mark_reported(panel._base_dir, run_id)
        sent = delivery.get("delivery") == "sent"
        return {
            **delivery,
            "code": "BUG_REPORT_SENT" if sent else "BUG_REPORT_QUEUED",
            "message": (
                "Đã gửi báo lỗi. Nhóm hỗ trợ sẽ kiểm tra."
                if sent
                else "Chưa gửi được ngay; báo lỗi đã lưu an toàn và sẽ tự gửi lại."
            ),
            "run_id": run_id,
            "jobs": job_history.list_jobs(panel._base_dir, 30),
        }

    def flush_error_reports(self) -> dict:
        panel = self._panel
        return {
            **telemetry.flush(panel._base_dir),
            "reporting_configured": telemetry.is_configured(panel._base_dir),
        }
