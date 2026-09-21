from __future__ import annotations

import hashlib
import inspect
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from wfx_panel import (
    constants,
    job_history,
    log_bridge,
    module_controllers,
    status,
    telemetry,
)
from wfx_panel import prefs as prefs_default
from wfx_panel.automation import runtime as automation_runtime
from wfx_panel.automation.runtime import RUNTIME as AUTOMATION_RUNTIME
from wfx_panel.automation.runtime import AutomationCancelled
from wfx_panel.coercion import boolean
from wfx_panel.controllers import (
    CatalogController,
    DirectoryController,
    FinanceController,
    InventoryController,
    JobsController,
    OCController,
    ReportsController,
    SaleASNController,
    SettingsController,
)
from wfx_panel.run_policy import (  # noqa: F401
    AUTO_RELOGIN_EXCLUDED_METHODS,
    CATALOG_CONTEXT_INVALIDATING_METHODS,
    DIAGNOSTIC_FAILURES,
    LOGIN_CODES,
    NON_REPORTABLE_FAILURES,
    SCREENSHOT_METHODS,
    SESSION_LOST,
    SESSION_OK,
)
from wfx_panel.stores import reference_sync
from wfx_panel.version import APP_VERSION, DISPLAY_VERSION


class PanelAPI:
    def __init__(self, login_module=None, prefs_module=None, base_dir: Path | None = None):
        if login_module is None:
            import login as login_module  # imported lazily so tests can inject a fake
        self._login = login_module
        self._prefs = prefs_module or prefs_default
        self._base_dir = base_dir or self._prefs.DATA_DIR
        self._logs: list[str] = []
        self._sink: Callable[[str], None] | None = None
        self._result_sink: Callable[[str, dict, float], None] | None = None
        self._progress_sink: Callable[[dict], None] | None = None
        self._hotkey_applier: Callable[[str], str | None] | None = None
        self._update_applier: Callable[[dict], str | None] | None = None
        self._on_top_applier: Callable[[bool], None] | None = None
        self._session_active: bool | None = None
        self._last_login_at: str | None = None
        # User ID mà app tin rằng đang sở hữu phiên Chrome hiện tại. Đọc trễ:
        # __init__ chạy trước khi UI kịp hiện, không được chạm đĩa ở đây.
        self._session_user_id_loaded = False
        self._session_user_id_value: str | None = None
        # Chặn vòng lặp tự đăng nhập lại bằng đúng bộ credential vừa bị WFX
        # từ chối: mỗi cú bấm của người dùng là một lần nhập sai nữa, đủ nhiều
        # là WFX khóa tài khoản.
        self._rejected_credential: str | None = None
        self._current_run_id: str | None = None
        self._admin_access: bool | None = None
        self._admin_module_ids: set[str] = set()
        self._current_division: str | None = None
        self._division_label: str | None = None
        self._division_name: str | None = None
        # Playwright/CDP không được chạy hai workflow song song trên cùng WFX
        # session. Trả về ngay thay vì xếp hàng khiến WebView trông bị treo.
        # RLock chứ không phải Lock: các thao tác Costing là composite gồm NHIỀU
        # _run liên tiếp (mở Costing rồi export/dry-run/apply). Với Lock thường,
        # cách duy nhất để chúng chạy được là nhả khóa giữa các bước — và đúng
        # khe hở đó cho phép flow khác đổi module/Division khiến bước sau thao
        # tác nhầm màn hình. run_composite() giữ khóa xuyên suốt, các _run lồng
        # bên trong tái nhập trên cùng thread.
        self._run_lock = threading.RLock()
        # Không dùng RLock.locked() cho is_action_running(): API đó chỉ có từ
        # Python 3.13 mà project khai báo requires-python >=3.11.
        self._run_depth = 0
        self._run_depth_lock = threading.Lock()
        # Toàn bộ state + logic Catalog (kết quả tìm, category đã chuẩn bị, cache
        # cây folder) sống trong controller riêng để bridge không phình to.
        self._catalog = CatalogController(self)
        # Toàn bộ state + logic OC (review workbook, token upload) nằm trong
        # controller riêng, giống Catalog.
        self._oc = OCController(self)
        self._sale_asn = SaleASNController(self)
        self._inventory = InventoryController(self)
        self._reports = ReportsController(self)
        self._finance = FinanceController(self)
        self._directory = DirectoryController(self)
        self._settings = SettingsController(self)
        self._jobs = JobsController(self)

    # -- logging -----------------------------------------------------------
    def set_log_sink(self, sink: Callable[[str], None]) -> None:
        self._sink = sink
        # Runtime cứu file người dùng tự tải trong lúc flow chạy; họ phải thấy
        # được nó đã lưu vào đâu.
        AUTOMATION_RUNTIME.log_sink = self._log

    def set_result_sink(
        self, sink: Callable[[str, dict, float], None]
    ) -> None:
        self._result_sink = sink

    def set_progress_sink(self, sink: Callable[[dict], None]) -> None:
        self._progress_sink = sink

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
        if self._progress_sink is None:
            return
        try:
            self._progress_sink(
                {
                    "method": str(method),
                    "stage": str(stage),
                    "message": str(message),
                    "step": max(1, int(step)),
                    "total": max(1, int(total)),
                    "state": str(state),
                    "run_id": self._current_run_id,
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

    def set_hotkey_applier(
        self, applier: Callable[[str], str | None]
    ) -> None:
        self._hotkey_applier = applier

    def set_update_applier(
        self, applier: Callable[[dict], str | None]
    ) -> None:
        self._update_applier = applier

    def set_window_pref_appliers(
        self,
        on_top: Callable[[bool], None],
    ) -> None:
        self._on_top_applier = on_top

    def _log(self, message: str) -> None:
        if self._current_run_id:
            message = f"[{self._current_run_id}] {message}"
        line = log_bridge.format_log_line(message)
        self._logs.append(line)
        if len(self._logs) > 300:
            self._logs = self._logs[-300:]
        if self._sink is not None:
            try:
                self._sink(line)
            except Exception:
                pass

    def _account(self) -> dict:
        return self._prefs.load_account(base_dir=self._base_dir)

    @property
    def _session_user_id(self) -> str | None:
        """Chủ phiên Chrome hiện tại, nhớ xuyên lần chạy qua prefs."""
        if not self._session_user_id_loaded:
            self._session_user_id_loaded = True
            try:
                stored = self._prefs.load_prefs(
                    base_dir=self._base_dir
                ).get("session_user_id")
            except OSError:
                stored = ""
            self._session_user_id_value = str(stored or "").strip() or None
        return self._session_user_id_value

    @_session_user_id.setter
    def _session_user_id(self, value: str | None) -> None:
        self._session_user_id_loaded = True
        self._session_user_id_value = str(value or "").strip() or None

    def _login_run(self, user_id: str, password: str) -> dict:
        """Gọi login module kèm chủ phiên hiện tại nếu module hỗ trợ.

        Các login module cũ/giả lập trong test không có tham số
        ``session_owner``; kiểm tra chữ ký thay vì bắt TypeError để không
        nuốt nhầm lỗi thật phát sinh bên trong flow đăng nhập.
        """
        kwargs: dict[str, Any] = {}
        try:
            parameters = inspect.signature(self._login.run).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "session_owner" in parameters:
            kwargs["session_owner"] = self._session_user_id
        return self._login.run(
            user_id,
            password,
            self._login.COMPANY_ID,
            self._log,
            **kwargs,
        )

    def _remember_session_user(self, user_id: str | None) -> None:
        value = str(user_id or "").strip() or None
        if value == self._session_user_id:
            return
        self._session_user_id = value
        try:
            self._prefs.save_prefs(
                base_dir=self._base_dir,
                session_user_id=value or "",
            )
        except TypeError:
            # prefs module cũ chưa biết khóa này; trạng thái trong bộ nhớ vẫn
            # đủ để bảo vệ trong phiên chạy hiện tại.
            pass

    @staticmethod
    def _credential_fingerprint(user_id: str, password: str) -> str:
        return hashlib.sha256(
            f"{user_id.strip().casefold()}\x00{password}".encode()
        ).hexdigest()

    def _credential_state(self) -> str:
        reader = getattr(self._prefs, "credential_status", None)
        if not callable(reader):
            return "ok" if self._account()["password"].strip() else "empty"
        try:
            return str(reader(base_dir=self._base_dir))
        except OSError:
            return "empty"

    def _telemetry_account_context(self) -> dict:
        account = self._account()
        return {
            "user_id": str(account.get("user_id") or "").strip(),
            "company_id": str(
                getattr(self._login, "COMPANY_ID", "") or ""
            ).strip(),
            "division_key": self._current_division or "",
            "division_label": self._division_label or "",
            "division_name": self._division_name or "",
        }

    def _admin_state(self, preferences: Mapping | None = None) -> dict:
        if preferences is None:
            preferences = self._prefs.load_prefs(base_dir=self._base_dir)
        allowed = self._admin_access is True and bool(self._admin_module_ids)
        return {
            "admin_access": allowed,
            "admin_module_ids": sorted(self._admin_module_ids) if allowed else [],
            "admin_mode": bool(preferences["admin_mode"] and allowed),
        }

    def _division_state(self) -> dict:
        return {
            "current_division": self._current_division,
            "division_label": self._division_label,
            "division_name": self._division_name,
        }

    def _refresh_admin_access(self) -> dict:
        if not hasattr(self._login, "check_module_access"):
            self._admin_access = False
            self._admin_module_ids = set()
            return self._admin_state()
        checked = self._login.check_module_access(
            constants.ADMIN_MODULE_SPECS,
            self._log,
        )
        ids = {
            str(module_id)
            for module_id in checked.get("accessible_module_ids", [])
            if str(module_id) in constants.ADMIN_MODULE_IDS
        }
        self._admin_module_ids = ids
        self._admin_access = bool(checked.get("ok") and ids)
        if not self._admin_access:
            self._prefs.save_prefs(
                base_dir=self._base_dir,
                admin_mode=False,
            )
        return self._admin_state()

    def _with_admin_access(self, result: dict) -> dict:
        if result.get("ok"):
            return {**result, **self._refresh_admin_access()}
        self._admin_access = False
        self._admin_module_ids = set()
        return {**result, **self._admin_state()}

    # -- state -------------------------------------------------------------
    def get_initial_state(self) -> dict:
        account = self._account()
        preferences = self._prefs.load_prefs(base_dir=self._base_dir)
        return {
            "app_version": APP_VERSION,
            "app_version_label": DISPLAY_VERSION,
            "version": DISPLAY_VERSION,
            "user_id": account["user_id"],
            "has_credentials": bool(
                account["user_id"].strip() and account["password"].strip()
            ),
            "credential_state": self._credential_state(),
            "theme": preferences["theme"],
            "favorite_module_ids": preferences["favorite_module_ids"],
            "hotkey": preferences["hotkey"],
            "hotkey_label": preferences["hotkey_label"],
            "autostart": preferences["autostart"],
            "start_hidden": preferences["start_hidden"],
            "toast_enabled": preferences["toast_enabled"],
            "focus_chrome_on_module": preferences[
                "focus_chrome_on_module"
            ],
            "always_on_top": preferences["always_on_top"],
            "open_excel_file_after_download": preferences[
                "open_excel_file_after_download"
            ],
            "open_costing_folder_after_export": preferences[
                "open_costing_folder_after_export"
            ],
            "report_export_dir": preferences["report_export_dir"],
            "catalog_default_folder": (
                self._catalog.default_folder_for_account(preferences)
            ),
            "article_library": self._catalog.article_library_status(),
            "reference_sync": reference_sync.status(self._base_dir),
            "costing_special_options": (
                self._catalog.costing.special_options_state(preferences)
            ),
            **self._admin_state(preferences),
            "reporting_configured": telemetry.is_configured(self._base_dir),
            "pending_reports": telemetry.outbox_count(self._base_dir),
            "update_channel": "stable",
            "module_groups": module_controllers.manifest_groups(),
            "divisions": list(constants.DIVISIONS.values()),
            "jobs": job_history.list_jobs(self._base_dir, 20),
            "sale_asn_buyers": list(self._sale_asn.buyers),
            "sale_asn_stages": preferences["sale_asn_stages"],
            "sale_asn_po_search_fields": preferences[
                "sale_asn_po_search_fields"
            ],
            "logs": list(self._logs),
            **self.get_status(),
        }

    def get_status(self) -> dict:
        browser_state = (
            self._login.browser_status()
            if hasattr(self._login, "browser_status")
            else {"chrome_alive": status.chrome_alive()}
        )
        return {
            **browser_state,
            **self._session_status(),
            **self._division_state(),
        }

    def _session_status(self) -> dict:
        """Trạng thái phiên đã quan sát, không thực hiện thêm I/O tới Chrome."""
        return {
            "session_active": self._session_active,
            "last_login_at": self._last_login_at,
        }

    def refresh_status(self) -> dict:
        return self.get_status()

    def _observe(
        self,
        method_name: str,
        result: dict,
        elapsed: float,
        *,
        emit_result: bool = True,
    ) -> None:
        code = str(result.get("code") or "")
        if code in SESSION_OK:
            self._session_active = True
            if code in LOGIN_CODES:
                self._last_login_at = time.strftime("%H:%M:%S")
        elif code in SESSION_LOST:
            self._session_active = False
            self._current_division = None
            self._division_label = None
            self._division_name = None
            self._catalog.reset_context()

        if code in {"LOGGED_IN", "LOGGED_IN_AFTER_DELAY"}:
            self._remember_session_user(
                result.get("session_user_id") or self._account()["user_id"]
            )
        elif (
            code in {"SESSION_REUSED", "SESSION_ACTIVE"}
            and self._session_user_id is None
        ):
            # Phiên có sẵn trong Chrome không chứng minh được là của ai. Giả
            # định nó thuộc tài khoản đang lưu: đoán sai thì lần đổi tài khoản
            # sau chỉ tốn thêm một lần đăng nhập, còn bỏ trống thì mất luôn
            # lớp chặn "chạy nhầm bằng tài khoản người khác".
            self._remember_session_user(
                result.get("session_user_id") or self._account()["user_id"]
            )
        elif code in {"NOT_LOGGED_IN", "MISSING_CREDENTIALS"}:
            # Phiên trong Chrome đã mất -> không còn tài khoản nào "đang sở
            # hữu" nó. Giữ lại giá trị cũ sẽ ép một lần đổi tài khoản thừa.
            self._remember_session_user(None)

        if code in SESSION_LOST or code in {
            "DIVISION_CHANGED",
            "LOGGED_IN",
            "LOGGED_IN_AFTER_DELAY",
            "SESSION_RESTORED",
        }:
            reset_menu_cache = getattr(
                self._login, "reset_menu_route_cache", None
            )
            if callable(reset_menu_cache):
                reset_menu_cache()

        if code in {"DIVISION_CHANGED", "LOGGED_IN", "LOGGED_IN_AFTER_DELAY"}:
            self._catalog.reset_context()

        if (
            result.get("ok")
            and method_name in CATALOG_CONTEXT_INVALIDATING_METHODS
        ):
            self._catalog.reset_context()

        if result.get("current_division") is not None:
            self._current_division = str(result["current_division"])
            self._division_label = str(result.get("division_label") or "")
            self._division_name = str(result.get("division_name") or "")

        quiet_keepalive = (
            method_name == "maintain_session"
            and code in {"SESSION_ACTIVE", "SESSION_REUSED"}
        )
        if emit_result and not quiet_keepalive and self._result_sink is not None:
            try:
                self._result_sink(method_name, result, elapsed)
            except Exception:
                pass

    def _action_in_progress(self) -> dict:
        return {
            "ok": False,
            "code": "ACTION_IN_PROGRESS",
            "message": "WFX Smart đang xử lý tác vụ trước. Vui lòng chờ hoàn tất.",
            **self._session_status(),
            **self._division_state(),
        }

    def _enter_run(self) -> None:
        with self._run_depth_lock:
            self._run_depth += 1

    def _exit_run(self) -> None:
        with self._run_depth_lock:
            self._run_depth = max(0, self._run_depth - 1)

    def run_composite(self, steps: Callable[[], dict]) -> dict:
        """Chạy một chuỗi nhiều ``_run`` như MỘT tác vụ không thể chen ngang.

        Import/export Costing phải mở đúng Costing rồi mới scan/apply. Nếu run
        lock được nhả giữa hai bước, một flow khác (mở module, đổi Division,
        tìm Catalog) có thể chen vào và bước sau sẽ thao tác trên màn hình khác
        hẳn — trong khi plan token 15 phút không hề biết điều đó.
        """
        if not self._run_lock.acquire(blocking=False):
            return self._action_in_progress()
        self._enter_run()
        try:
            return steps()
        finally:
            self._exit_run()
            self._run_lock.release()

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
        if not self._run_lock.acquire(blocking=False):
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
            self._run_lock.release()

    def _normalised_result(self, method_name: str, action: Callable[[], dict]) -> dict:
        """Chạy action và quy mọi kết cục về đúng một dict kết quả."""
        try:
            result = self._run_action_with_auto_relogin(method_name, action)
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
        if method_name not in SCREENSHOT_METHODS:
            return False
        if code in NON_REPORTABLE_FAILURES and code not in DIAGNOSTIC_FAILURES:
            return False
        return hasattr(self._login, "capture_failure_screenshot")

    def _capture_failure_screenshot(self, run_id: str) -> str | None:
        """Ảnh chẩn đoán cho một lượt hỏng; None nếu không chụp được."""
        shot = job_history.screenshot_dir(self._base_dir) / f"{run_id}.png"
        try:
            if self._login.capture_failure_screenshot(shot, self._log):
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
        try:
            job_history.append(
                self._base_dir,
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
            self._log(f"[RUN] Không ghi được lịch sử: {type(error).__name__}")

    def _announce_finish(
        self, method_name: str, result: dict, elapsed: float, announce: bool
    ) -> None:
        code = result.get("code", "UNKNOWN")
        if announce:
            self._log(
                f"[RUN] Kết thúc {method_name}: {code} ({int(elapsed * 1000)} ms)"
            )
        elif not result.get("ok"):
            self._log(f"[SESSION] Kiểm tra nền cần chú ý: {code}.")

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
        run_id = job_history.new_run_id()
        started = time.monotonic()
        started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._current_run_id = run_id
        if announce:
            self._log(f"[RUN] Bắt đầu {method_name}")

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
        self._current_run_id = None

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
                self._log(f"[RUN] Không xếp được báo lỗi: {type(error).__name__}")

        self._observe(method_name, result, elapsed, emit_result=emit_result)
        return {**result, **self._session_status(), **self._division_state()}

    def _restore_expired_session(self) -> dict | None:
        """Đăng nhập lại bằng credential đã lưu; ``None`` nếu chưa cấu hình."""
        account = self._account()
        user_id = str(account.get("user_id") or "").strip()
        password = str(account.get("password") or "")
        if not user_id or not password:
            return None
        # WFX khóa tài khoản sau vài lần sai liên tiếp. Một bộ credential đã
        # bị từ chối thì mọi cú bấm tiếp theo của người dùng không được biến
        # thành một lần nhập sai nữa — chờ tới khi họ lưu credential khác.
        fingerprint = self._credential_fingerprint(user_id, password)
        if self._rejected_credential == fingerprint:
            self._log(
                "[SESSION] Bỏ qua tự đăng nhập lại: WFX đã từ chối đúng tài "
                "khoản/mật khẩu này. Hãy cập nhật lại trong Cài đặt."
            )
            return {
                "ok": False,
                "code": "LOGIN_FAILED",
                "message": (
                    "WFX đã từ chối tài khoản đang lưu. Mở Cài đặt và nhập "
                    "lại mật khẩu WFX trước khi chạy tiếp."
                ),
            }
        self._log("[SESSION] Phiên WFX đã hết hạn; đang tự đăng nhập lại...")
        restored = self._login_run(user_id, password)
        if not isinstance(restored, dict) or not restored.get("ok"):
            if (
                isinstance(restored, dict)
                and str(restored.get("code") or "") == "LOGIN_FAILED"
            ):
                self._rejected_credential = fingerprint
            return restored if isinstance(restored, dict) else {
                "ok": False,
                "code": "LOGIN_FAILED",
                "message": "Kết quả tự đăng nhập lại không hợp lệ.",
            }

        self._rejected_credential = None
        self._session_active = True
        self._last_login_at = time.strftime("%H:%M:%S")
        self._admin_access = None
        self._admin_module_ids.clear()
        self._remember_session_user(restored.get("session_user_id") or user_id)
        self._catalog.reset_context()
        if restored.get("current_division") is not None:
            self._current_division = str(restored["current_division"])
            self._division_label = str(restored.get("division_label") or "")
            self._division_name = str(restored.get("division_name") or "")
        self._log("[SESSION] Đã tự đăng nhập lại; tiếp tục tác vụ hiện tại.")
        return {
            **restored,
            "code": "SESSION_RESTORED",
            "message": "Đã tự đăng nhập lại WFX.",
        }

    def _run_action_with_auto_relogin(
        self,
        method_name: str,
        action: Callable[[], dict],
    ) -> dict:
        """Khôi phục Chrome/phiên rồi retry toàn bộ action đúng một lần."""
        result = action()
        if (
            method_name in AUTO_RELOGIN_EXCLUDED_METHODS
            or not isinstance(result, dict)
        ):
            return result
        code = str(result.get("code") or "")
        if code == "CHROME_CLOSED":
            self._log(
                "[BROWSER] Trình duyệt làm việc đã đóng; đang tự mở lại..."
            )
            opened = self._login.start_chrome(self._log)
            if not isinstance(opened, dict) or not opened.get("ok"):
                return opened if isinstance(opened, dict) else {
                    "ok": False,
                    "code": "CHROME_OPEN_FAILED",
                    "message": "Kết quả mở lại trình duyệt không hợp lệ.",
                    "chrome_alive": False,
                }
            restored = self._restore_expired_session()
            if restored is None:
                return {
                    "ok": False,
                    "code": "MISSING_CREDENTIALS",
                    "message": (
                        "Đã mở lại trình duyệt. Hãy lưu tài khoản WFX để ứng dụng "
                        "có thể tự đăng nhập và tiếp tục tác vụ."
                    ),
                    "chrome_alive": True,
                    "browser_available": True,
                    "browser_name": opened.get("browser_name"),
                }
            if not restored.get("ok"):
                return {
                    **restored,
                    "chrome_alive": True,
                    "browser_available": True,
                    "browser_name": opened.get("browser_name"),
                }
            self._log(
                "[BROWSER] Đã mở lại trình duyệt và khôi phục phiên; "
                "tiếp tục tác vụ hiện tại."
            )
            return action()
        if code != "NOT_LOGGED_IN":
            return result
        restored = self._restore_expired_session()
        if restored is None:
            return result
        if not restored.get("ok"):
            return restored
        return action()

    def _report_automation_error(
        self,
        method_name: str,
        result: dict,
        request: dict | None,
        code: str,
        run_id: str,
        elapsed: float,
    ) -> None:
        error_context = telemetry.automation_error_context(
            method_name,
            result,
            request,
        )
        telemetry.enqueue(
            self._base_dir,
            {
                "event_type": "automation_error",
                "app_version": APP_VERSION,
                "method": method_name,
                "code": code,
                "run_id": run_id,
                "elapsed_ms": int(elapsed * 1000),
                **error_context,
                "account": self._telemetry_account_context(),
                **telemetry.system_summary(),
            },
        )
        # Chốt endpoint trước khi tạo thread. Nếu test/cấu hình hiện tại
        # đã tắt webhook thì thread chạy trễ cũng không được tự resolve lại
        # DEFAULT_WEBHOOK_URL và gửi payload sang production.
        telemetry_endpoint = telemetry.webhook_url(self._base_dir)
        threading.Thread(
            target=telemetry.flush,
            args=(self._base_dir, telemetry_endpoint),
            daemon=True,
        ).start()

    def cancel_current_action(self) -> dict:
        if automation_runtime.request_cancel():
            self._log("[STOP] Đã nhận yêu cầu dừng; đang chờ checkpoint an toàn.")
            return {
                "ok": True,
                "code": "CANCEL_REQUESTED",
                "message": "Đang dừng tại checkpoint an toàn…",
                "run_id": self._current_run_id,
            }
        return {
            "ok": False,
            "code": "NO_ACTION_RUNNING",
            "message": "Không có tác vụ automation đang chạy.",
        }

    def is_action_running(self) -> bool:
        """Nguồn trạng thái native để panel tự thu không phụ thuộc WebView."""
        with self._run_depth_lock:
            return self._run_depth > 0

    def shutdown(self, close_browser: bool = False) -> None:
        if close_browser:
            closer = getattr(self._login, "close_chrome", None)
            if callable(closer):
                # Nếu user thoát giữa flow, dừng ở checkpoint rồi đóng Chrome
                # trên chính automation worker để không tạo race CDP.
                AUTOMATION_RUNTIME.request_cancel()
                try:
                    AUTOMATION_RUNTIME.execute(lambda: closer(self._log))
                except Exception as exc:
                    self._log(
                        "Không đóng được trình duyệt làm việc khi thoát: "
                        f"{type(exc).__name__}: {exc}"
                    )
        automation_runtime.shutdown()

    # -- automation --------------------------------------------------------
    def login(self) -> dict:
        def action() -> dict:
            account = self._account()
            # Người dùng vừa chủ động bấm đăng nhập: cho phép thử lại đúng bộ
            # credential mà lần trước WFX từ chối (họ có thể đã sửa mật khẩu).
            self._rejected_credential = None
            result = self._login_run(
                account["user_id"],
                account["password"],
            )
            return self._with_admin_access(result)

        return self._run("login", action)

    def check_session(self) -> dict:
        return self._run(
            "check_session",
            lambda: self._with_admin_access(
                self._login.check_session(self._log)
            ),
        )

    def should_maintain_session(self) -> bool:
        """Chỉ keepalive sau khi app đã xác nhận từng có phiên đăng nhập."""
        if self._session_active is not True:
            return False
        account = self._account()
        return bool(
            str(account.get("user_id") or "").strip()
            and str(account.get("password") or "")
        )

    def maintain_session(self) -> dict:
        """Kiểm tra nền; hết phiên thì tự login lại bằng credential đã lưu."""

        def action() -> dict:
            buffered_logs: list[str] = []
            checked = self._login.check_session(buffered_logs.append)
            if str(checked.get("code") or "") != "NOT_LOGGED_IN":
                return checked
            for line in buffered_logs:
                self._log(line)
            restored = self._restore_expired_session()
            return restored or checked

        # Heartbeat thành công không phải tác vụ người dùng: không ghi jobs.json,
        # không thêm hai dòng RUN và không thay footer. Khi session thật sự lỗi,
        # _run_unlocked vẫn ghi một dòng cô đọng và _observe vẫn cập nhật state.
        return self._run(
            "maintain_session",
            action,
            record_job=False,
            record_job_on_failure=True,
            announce=False,
        )

    def open_chrome(self) -> dict:
        def action() -> dict:
            browser = self._login.start_chrome(self._log)
            if not browser.get("ok"):
                return browser
            account = self._account()
            self._rejected_credential = None
            logged_in = self._login_run(
                account["user_id"],
                account["password"],
            )
            result = {
                **logged_in,
                "chrome_alive": True,
                "browser_available": True,
                "browser_name": browser.get("browser_name"),
                "message": (
                    "Đã mở trình duyệt và đăng nhập WFX."
                    if logged_in.get("ok")
                    else logged_in.get("message")
                ),
            }
            return self._with_admin_access(result)

        return self._run("open_chrome", action)

    def open_module(self, module_id: str) -> dict:
        def action() -> dict:
            controller = module_controllers.get(module_id)
            if controller is None:
                return {
                    "ok": False,
                    "code": "MODULE_UNKNOWN",
                    "message": f"Module lạ: {module_id}",
                }
            if module_id in constants.ADMIN_MODULE_IDS:
                self._refresh_admin_access()
                if (
                    self._admin_access is not True
                    or module_id not in self._admin_module_ids
                ):
                    return {
                        "ok": False,
                        "code": "ADMIN_ACCESS_DENIED",
                        "message": "Tài khoản WFX không có quyền mở module Admin này.",
                        **self._admin_state(),
                    }
            return controller.open(self._login, self._log)

        return self._run(
            "open_module", action, {"module_id": module_id}
        )

    def report_catalog(self) -> dict:
        return self._reports.report_catalog()

    def _saved_report_parameters(self, report_id: str) -> dict[str, Any]:
        return self._reports._saved_report_parameters(report_id)

    def load_report_parameters(self, report_id: str) -> dict:
        return self._reports.load_report_parameters(report_id)

    def save_report_parameters(self, report_id: str, values: Mapping[str, Any] | None=None) -> dict:
        return self._reports.save_report_parameters(report_id, values)

    def export_report_excel(self, report_id: str, values: Mapping[str, Any] | None=None) -> dict:
        return self._reports.export_report_excel(report_id, values)

    def load_color_report_options(self, values: Mapping[str, Any] | None=None) -> dict:
        return self._reports.load_color_report_options(values)

    def run_color_report_batch(self, selection: Mapping[str, Any] | None=None, style_refs: list[str] | None=None, output_dir: str='') -> dict:
        return self._reports.run_color_report_batch(selection, style_refs, output_dir)

    def _admin_module_access_error(self, module_id: str) -> dict | None:
        self._refresh_admin_access()
        if (
            self._admin_access is True
            and module_id in self._admin_module_ids
        ):
            return None
        return {
            "ok": False,
            "code": "ADMIN_ACCESS_DENIED",
            "message": "Tài khoản WFX không có quyền mở module Admin này.",
            **self._admin_state(),
        }

    def open_sale_asn_new(self) -> dict:
        return self._sale_asn.open_sale_asn_new()

    def scan_sale_asn_buyers(self) -> dict:
        return self._sale_asn.scan_sale_asn_buyers()

    def scan_sale_asn_order_details(self) -> dict:
        return self._sale_asn.scan_sale_asn_order_details()

    def _discard_sale_asn_create_review(self, review_token: str) -> bool:
        return self._sale_asn._discard_sale_asn_create_review(review_token)

    def prepare_sale_asn_create(self, file_path: str, buyer: str, selected_stages: list[str] | tuple[str, ...] | None=None) -> dict:
        return self._sale_asn.prepare_sale_asn_create(file_path, buyer, selected_stages)

    def _run_sale_asn_create_review(self, review_token: str, *, continue_existing: bool, selected_candidate_ids: list[str] | None=None) -> dict:
        return self._sale_asn._run_sale_asn_create_review(
            review_token,
            continue_existing=continue_existing,
            selected_candidate_ids=selected_candidate_ids,
        )

    def start_sale_asn_create(self, review_token: str) -> dict:
        return self._sale_asn.start_sale_asn_create(review_token)

    def continue_sale_asn_create(self, review_token: str, selected_candidate_ids: list[str] | None=None) -> dict:
        return self._sale_asn.continue_sale_asn_create(
            review_token,
            selected_candidate_ids,
        )

    def skip_sale_asn_create_step(self, review_token: str) -> dict:
        return self._sale_asn.skip_sale_asn_create_step(review_token)

    def cancel_sale_asn_create(self, review_token: str) -> dict:
        return self._sale_asn.cancel_sale_asn_create(review_token)

    def search_oc(
        self,
        filter_kind: str,
        query: str,
    ) -> dict:
        oc = constants.MODULE_BY_ID["0004_0050_0020"]
        return self._run(
            "search_oc",
            lambda: self._login.search_oc_list(
                oc["xpath"],
                str(filter_kind or ""),
                str(query or "").strip(),
                self._log,
            ),
            {
                "filter_kind": str(filter_kind or ""),
                "query": str(query or "").strip(),
            },
        )

    def search_sample(
        self,
        sample_no: str = "",
        style: str = "",
        created_by: str = "",
        buyer: str = "",
    ) -> dict:
        sample = constants.MODULE_BY_ID["0004_0056_4070"]
        values = {
            "sample_no": str(sample_no or "").strip(),
            "style": str(style or "").strip(),
            "created_by": str(created_by or "").strip(),
            "buyer": str(buyer or "").strip(),
        }
        active_filters = [key for key, value in values.items() if value]
        return self._run(
            "search_sample",
            lambda: self._login.search_sample_list_with_filters(
                sample["xpath"],
                values,
                self._log,
            ),
            {
                "filter_kind": "multiple",
                "filter_kinds": active_filters,
            },
        )

    def open_sample_new(self) -> dict:
        return self._run(
            "open_sample_new",
            lambda: self._login.open_sample_new(
                constants.SAMPLE_NEW_XPATH,
                self._log,
            ),
        )

    def search_sale_asn(self, filter_kind: str, query: str) -> dict:
        return self._sale_asn.search_sale_asn(filter_kind, query)

    def export_sale_asn_price_check(self, price_check: dict, file_path: str) -> dict:
        return self._sale_asn.export_sale_asn_price_check(price_check, file_path)

    def _discard_sale_asn_document_export(self, export_token: str) -> bool:
        return self._sale_asn._discard_sale_asn_document_export(export_token)

    def prepare_sale_asn_documents(self, filter_kind: str, query: str) -> dict:
        return self._sale_asn.prepare_sale_asn_documents(filter_kind, query)

    def cancel_sale_asn_documents(self, export_token: str) -> dict:
        return self._sale_asn.cancel_sale_asn_documents(export_token)

    def save_sale_asn_documents(self, export_token: str, file_path: str) -> dict:
        return self._sale_asn.save_sale_asn_documents(export_token, file_path)

    def search_rmpo(self, supplier: str, order_no: str) -> dict:
        return self._inventory.search_rmpo(supplier, order_no)

    def run_rmpo_action(self, choice_id: str, action_name: str) -> dict:
        return self._inventory.run_rmpo_action(choice_id, action_name)

    def prepare_grn_receipt(self, rmpo_no: str, mode: str, rmpo_choice_id: str='') -> dict:
        return self._inventory.prepare_grn_receipt(rmpo_no, mode, rmpo_choice_id)

    def continue_grn_receipt(self, receipt_token: str, sourcing_confirmed: bool) -> dict:
        return self._inventory.continue_grn_receipt(receipt_token, sourcing_confirmed)

    def finalize_grn_receipt(self, receipt_token: str, site: str) -> dict:
        return self._inventory.finalize_grn_receipt(receipt_token, site)

    def search_grn(self, filter_kind: str, query: str) -> dict:
        return self._inventory.search_grn(filter_kind, query)

    def search_indent(
        self,
        module_id: str,
        supplier: str,
        article: str,
        indent_no: str,
        style: str,
    ) -> dict:
        if module_id not in {"0005_0080_0020", "user_indent_list"}:
            return self._run(
                "search_indent",
                lambda: {
                    "ok": False,
                    "code": "MODULE_UNKNOWN",
                    "message": f"Module Indent lạ: {module_id}",
                },
                {"module_id": module_id},
            )
        module = constants.MODULE_BY_ID[module_id]
        return self._run(
            "search_indent",
            lambda: self._login.search_indent_list(
                module["xpath"],
                module["name"],
                str(supplier or "").strip(),
                str(article or "").strip(),
                str(indent_no or "").strip(),
                str(style or "").strip(),
                self._log,
            ),
            {"module_id": module_id},
        )

    def search_supplier_invoice(self, supplier: str='', invoice_no: str='', po_no: str='', asn_grn_no: str='') -> dict:
        return self._finance.search_supplier_invoice(
            supplier,
            invoice_no,
            po_no,
            asn_grn_no,
        )

    def search_advance_pr(self, buyer: str='', supplier: str='', invoice_no: str='', order_no: str='') -> dict:
        return self._finance.search_advance_pr(buyer, supplier, invoice_no, order_no)

    def search_expense_invoice(self, supplier: str='', invoice_no: str='', created_by: str='', status: str='') -> dict:
        return self._finance.search_expense_invoice(
            supplier,
            invoice_no,
            created_by,
            status,
        )

    def cancel_supplier_invoice(self, invoice_no: str) -> dict:
        return self._finance.cancel_supplier_invoice(invoice_no)

    def cancel_supplier_invoice_choice(self, choice_id: str) -> dict:
        return self._finance.cancel_supplier_invoice_choice(choice_id)

    def open_module_new(self, module_id: str) -> dict:
        return self._run(
            "open_module_new",
            lambda: self._login.open_module_new(
                str(module_id or ""),
                self._log,
            ),
            {"module_id": str(module_id or "")},
        )

    def toggle_company_foc(self) -> dict:
        return self._directory.toggle_company_foc()

    def open_supplier_category(self, category_name: str) -> dict:
        return self._directory.open_supplier_category(category_name)

    def find_supplier(self, query: str) -> dict:
        return self._directory.find_supplier(query)

    def find_supplier_in_category(self, category_name: str, query: str) -> dict:
        return self._directory.find_supplier_in_category(category_name, query)

    def find_buyer(self, query: str) -> dict:
        return self._directory.find_buyer(query)

    def switch_division(self, division_key: str) -> dict:
        return self._directory.switch_division(division_key)

    # -- catalog (uỷ quyền cho CatalogController) --------------------------
    def scan_catalog_folders(
        self, category_name: str, force: bool = False
    ) -> dict:
        return self._catalog.scan_folders(category_name, boolean(force))

    def set_catalog_default_folder(
        self, category_name: str, node_id: str
    ) -> dict:
        return self._catalog.set_default_folder(category_name, node_id)

    def browse_catalog(self, category_name: str) -> dict:
        return self._catalog.browse(category_name)

    def prepare_catalog(self, category_name: str) -> dict:
        return self._catalog.prepare(category_name)

    def review_catalog_style_import(
        self,
        file_path: str,
        group_id: str,
    ) -> dict:
        return self._catalog.style.review_style_import(file_path, group_id)

    def clear_catalog_style_import(self, review_token: str) -> dict:
        return self._catalog.style.clear_style_import(review_token)

    def ensure_catalog_style_options(
        self,
        group_id: str,
        force: bool = False,
    ) -> dict:
        return self._catalog.style.ensure_style_options(group_id, boolean(force))

    def prepare_catalog_style_row(
        self,
        review_token: str,
        source_row: int,
        copy_choice: int | None = None,
        auto_save: bool = False,
    ) -> dict:
        return self._catalog.style.prepare_style_row(
            review_token,
            source_row,
            copy_choice,
            boolean(auto_save),
        )

    def find_code(
        self, category_name: str, code: str, destination: str | None = None
    ) -> dict:
        return self._catalog.action(
            category_name,
            "code",
            code,
            destination,
            method_name="find_code",
        )

    def find_buyer_reference(
        self, category_name: str, query: str, destination: str | None = None
    ) -> dict:
        return self._catalog.action(
            category_name,
            "buyer_reference",
            query,
            destination,
            method_name="find_buyer_reference",
        )

    def catalog_action(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        destination: str | None = None,
    ) -> dict:
        return self._catalog.action(
            category_name, filter_kind, query, destination
        )

    def open_catalog_destination(
        self, destination: str, article_code: str
    ) -> dict:
        return self._catalog.open_destination(destination, article_code)

    def download_catalog_file(self, file_id: str) -> dict:
        return self._catalog.files_view.download_file(file_id)

    def export_catalog_costing(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
        scan_article_options: bool = False,
    ) -> dict:
        return self._catalog.costing.export(
            category_name,
            filter_kind,
            query,
            file_path,
            boolean(scan_article_options),
        )

    def check_sample_files(
        self,
        sample_no: str = "",
        style: str = "",
        created_by: str = "",
        buyer: str = "",
    ) -> dict:
        return self._catalog.files_view.check_sample_files_with_filters(
            {
                "sample_no": str(sample_no or "").strip(),
                "style": str(style or "").strip(),
                "created_by": str(created_by or "").strip(),
                "buyer": str(buyer or "").strip(),
            }
        )

    def open_sample_file_choice(self, choice_id: str) -> dict:
        return self._catalog.files_view.open_sample_file_choice(choice_id)

    def open_oc_revision_report(self) -> dict:
        return self._oc.open_oc_revision_report()

    def run_gdn_dispatch(
        self,
        invoice: str,
        grn_wait_confirmed: bool = False,
    ) -> dict:
        invoice_value = " ".join(str(invoice or "").split())
        if not boolean(grn_wait_confirmed):
            return {
                "ok": False,
                "code": "GDN_GRN_WAIT_CONFIRMATION_REQUIRED",
                "message": (
                    "Chỉ Submit sau khi GRN nhập kho thành phẩm đã hoàn tất "
                    "ít nhất 15 phút."
                ),
            }
        if not invoice_value:
            return {
                "ok": False,
                "code": "GDN_INVOICE_REQUIRED",
                "message": "Hãy nhập Invoice GRN trước khi Submit.",
            }

        def action() -> dict:
            runner = getattr(self._login, "run_gdn_dispatch", None)
            if not callable(runner):
                return {
                    "ok": False,
                    "code": "GDN_DISPATCH_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ (GDN) Dispatch.",
                }
            return runner(
                invoice_value,
                self._log,
                self._progress_for("run_gdn_dispatch"),
            )

        # Không lưu Invoice vào request/job history/telemetry.
        return self._run(
            "run_gdn_dispatch",
            action,
            {"module_id": "gdn_dispatch"},
        )

    def open_gdn_status(self) -> dict:
        """Mở EDI BuyerOrderDispatch để kiểm tra package, không submit lại."""

        def action() -> dict:
            opener = getattr(self._login, "open_gdn_status", None)
            if not callable(opener):
                return {
                    "ok": False,
                    "code": "GDN_DISPATCH_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ kiểm tra GDN.",
                }
            return opener(self._log)

        return self._run(
            "open_gdn_status",
            action,
            {"module_id": "gdn_dispatch"},
        )

    def _discard_oc_upload_review(self, review_token: str) -> bool:
        return self._oc._discard_oc_upload_review(review_token)

    def review_oc_upload(self, mode: str, file_path: str) -> dict:
        return self._oc.review_oc_upload(mode, file_path)

    def cancel_oc_upload_review(self, review_token: str) -> dict:
        return self._oc.cancel_oc_upload_review(review_token)

    def save_oc_upload_file(self, review_token: str, file_path: str) -> dict:
        return self._oc.save_oc_upload_file(review_token, file_path)

    def confirm_oc_upload(self, review_token: str) -> dict:
        return self._oc.confirm_oc_upload(review_token)

    def confirm_oc_pending(self, mode: str) -> dict:
        return self._oc.confirm_oc_pending(mode)

    def reject_all_oc_pending(self) -> dict:
        return self._oc.reject_all_oc_pending()

    def upload_oc(self, mode: str, file_path: str) -> dict:
        return self._oc.upload_oc(mode, file_path)

    def inspect_active_catalog_costing(self, category_name: str) -> dict:
        return self._catalog.costing.inspect_active(category_name)

    def clear_catalog_costing_dependencies(self) -> dict:
        return self._catalog.costing.clear_active_dependencies()

    def sync_article_library(self) -> dict:
        return self._catalog.sync_article_library()

    def sync_reference_data(self, force: bool=True) -> dict:
        return self._settings.sync_reference_data(force)

    def save_sync_admin_key(self, admin_key: str) -> dict:
        return self._settings.save_sync_admin_key(admin_key)

    def publish_reference_data(self) -> dict:
        return self._settings.publish_reference_data()

    def set_costing_special_options_rescan(self, value: bool) -> dict:
        return self._catalog.costing.set_special_options_rescan(value)

    def suggest_articles(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        limit: int = 20,
    ) -> dict:
        return self._catalog.suggest_articles(
            category_name,
            filter_kind,
            query,
            limit,
        )

    def validate_catalog_costing_file(self, file_path: str) -> dict:
        return self._catalog.costing.validate_file(file_path)

    def prepare_catalog_costing_import(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
    ) -> dict:
        return self._catalog.costing.prepare_import(
            category_name,
            filter_kind,
            query,
            file_path,
        )

    def clear_catalog_costing_plan(self, plan_token: str) -> dict:
        return self._catalog.costing.clear_plan(plan_token)

    def apply_catalog_costing(
        self,
        plan_token: str,
        article_resolutions: dict | None = None,
    ) -> dict:
        return self._catalog.costing.apply(plan_token, article_resolutions)

    # -- settings ----------------------------------------------------------
    def save_account(self, user_id: str, password: str) -> dict:
        # Password field trên UI không bao giờ được điền lại (get_initial_state
        # chỉ trả user_id) nên luôn trống khi sheet mở lại. Nếu người dùng chỉ
        # sửa User ID hoặc bấm CTA mà không gõ lại mật khẩu, KHÔNG được ghi đè
        # mật khẩu đã lưu bằng chuỗi rỗng — giữ nguyên mật khẩu cũ.
        user_id = str(user_id or "").strip()
        previous_user_id = str(
            self._account().get("user_id") or ""
        ).strip()
        password = password or ""
        if not user_id:
            return {
                "ok": False,
                "code": "USER_ID_REQUIRED",
                "message": "Vui lòng nhập User ID trước khi kết nối.",
            }
        account_changed = previous_user_id.casefold() != user_id.casefold()
        if not password.strip():
            # Kế thừa mật khẩu cũ CHỈ đúng khi vẫn là tài khoản cũ. Ghép User
            # ID mới với mật khẩu của người khác thì lần đăng nhập nào cũng
            # sai, và mỗi lần sai là một bước tới khóa tài khoản trên WFX.
            if account_changed and previous_user_id:
                return {
                    "ok": False,
                    "code": "PASSWORD_REQUIRED",
                    "message": (
                        "Đổi sang User ID khác thì phải nhập mật khẩu của "
                        "chính tài khoản đó."
                    ),
                }
            existing_password = self._account().get("password", "")
            if not existing_password.strip():
                return {
                    "ok": False,
                    "code": "PASSWORD_REQUIRED",
                    "message": "Vui lòng nhập mật khẩu trước khi lưu.",
                }
            password = existing_password
        try:
            self._prefs.save_account(user_id, password, base_dir=self._base_dir)
        except getattr(
            self._prefs,
            "CredentialProtectionError",
            RuntimeError,
        ) as error:
            return {
                "ok": False,
                "code": "CREDENTIAL_PROTECTION_FAILED",
                "message": str(error),
            }
        self._rejected_credential = None
        if account_changed:
            # Chrome vẫn đang giữ phiên của tài khoản CŨ. Giữ nguyên cờ "đã
            # đăng nhập" ở đây là nói dối: mọi automation chạy sau đó vẫn là
            # người cũ. Hạ toàn bộ trạng thái dẫn xuất và để lần login kế
            # tiếp tự đổi phiên (_session_user_id vẫn là chủ phiên cũ).
            self._session_active = None
            self._last_login_at = None
            self._current_division = None
            self._division_label = None
            self._division_name = None
            self._admin_access = None
            self._admin_module_ids.clear()
            self._catalog.reset_for_account_change()
        self._log("[SETTINGS] Đã lưu tài khoản")
        return {
            "ok": True,
            "code": "ACCOUNT_SAVED",
            "message": "Đã lưu tài khoản.",
            "user_id": user_id,
            "has_credentials": True,
            "credential_state": self._credential_state(),
            **self._session_status(),
            **self._division_state(),
            **self._admin_state(),
        }

    def set_theme(self, theme: str) -> dict:
        return self._settings.set_theme(theme)

    def set_sale_asn_stages(self, stages: list[str] | None=None) -> dict:
        return self._settings.set_sale_asn_stages(stages)

    def set_sale_asn_po_search_fields(self, fields: list[str] | None=None) -> dict:
        return self._settings.set_sale_asn_po_search_fields(fields)

    def set_excel_file_after_download(self, enabled: bool) -> dict:
        return self._settings.set_excel_file_after_download(enabled)

    def set_module_favorite(self, module_id: str, favorite: bool) -> dict:
        return self._settings.set_module_favorite(module_id, favorite)

    def set_hotkey(self, spec: str | dict) -> dict:
        return self._settings.set_hotkey(spec)

    def set_autostart(self, enabled: bool) -> dict:
        return self._settings.set_autostart(enabled)

    def set_start_hidden(self, enabled: bool) -> dict:
        return self._settings.set_start_hidden(enabled)

    def set_toast_enabled(self, enabled: bool) -> dict:
        return self._settings.set_toast_enabled(enabled)

    def set_focus_chrome_on_module(self, enabled: bool) -> dict:
        return self._settings.set_focus_chrome_on_module(enabled)

    def set_always_on_top(self, enabled: bool) -> dict:
        return self._settings.set_always_on_top(enabled)

    def set_admin_mode(self, enabled: bool) -> dict:
        wanted = boolean(enabled)
        if wanted:
            self._refresh_admin_access()
        if wanted and self._admin_access is not True:
            self._prefs.save_prefs(
                base_dir=self._base_dir,
                admin_mode=False,
            )
            return {
                "ok": False,
                "code": "ADMIN_ACCESS_DENIED",
                "message": "Tài khoản WFX này không có module Admin được cấp quyền.",
                **self._admin_state(),
            }
        saved = self._prefs.save_prefs(
            base_dir=self._base_dir,
            admin_mode=wanted,
        )
        return {
            "ok": True,
            "code": "ADMIN_MODE_SAVED",
            "message": (
                "Đã hiện các module Admin được cấp quyền."
                if saved["admin_mode"]
                else "Đã ẩn nhóm module Admin."
            ),
            **self._admin_state(),
        }

    def submit_feedback(self, kind: str, message: str, include_diagnostics: bool=True) -> dict:
        return self._jobs.submit_feedback(kind, message, include_diagnostics)

    def flush_error_reports(self) -> dict:
        return self._jobs.flush_error_reports()

    def set_update_channel(self, channel: str) -> dict:
        return self._settings.set_update_channel(channel)

    def check_for_updates(self) -> dict:
        return self._settings.check_for_updates()

    def install_update(self) -> dict:
        return self._settings.install_update()

    def get_job_history(self, limit: int=30) -> dict:
        return self._jobs.get_job_history(limit)

    def acknowledge_job(self, run_id: str) -> dict:
        return self._jobs.acknowledge_job(run_id)

    def retry_job(self, run_id: str) -> dict:
        return self._jobs.retry_job(run_id)

    def open_job_screenshot(self, run_id: str) -> dict:
        return self._jobs.open_job_screenshot(run_id)

    def clear_job_history(self) -> dict:
        return self._jobs.clear_job_history()

    def clear_log(self) -> dict:
        return self._jobs.clear_log()
