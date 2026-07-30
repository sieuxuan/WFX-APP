from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from wfx_panel import (
    autostart,
    constants,
    job_history,
    log_bridge,
    module_controllers,
    status,
    telemetry,
    updater,
)
from wfx_panel import (
    hotkey as hotkey_spec,
)
from wfx_panel import prefs as prefs_default
from wfx_panel.automation import runtime as automation_runtime
from wfx_panel.automation.runtime import AutomationCancelled
from wfx_panel.catalog_controller import CatalogController
from wfx_panel.version import APP_VERSION, DISPLAY_VERSION

SESSION_OK = frozenset(
    {
        "LOGGED_IN",
        "SESSION_REUSED",
        "SESSION_ACTIVE",
        "MODULE_OPENED",
        "CATEGORY_SELECTED",
        "MASTER_OPENED",
        "CATALOG_PREPARED",
        "RESULT_OPENED",
        "MULTIPLE_RESULTS",
        "NO_RESULTS",
        "CODE_OPENED",
        "DIVISION_CHANGED",
        "DIVISION_ALREADY_ACTIVE",
        "CATALOG_DESTINATION_OPENED",
        "CATALOG_FILES_SCANNED",
        "CATALOG_FILE_DOWNLOADED",
        "CATALOG_FOLDER_OPENED",
        "CATALOG_FOLDER_FALLBACK",
        "CATALOG_FOLDERS_SCANNED",
        "CATALOG_FOLDERS_CACHED",
        "COSTING_CONTEXT_INSPECTED",
        "COSTING_FILE_VALID",
        "COSTING_EXPORTED",
        "COSTING_DRY_RUN_READY",
        "COSTING_APPLIED",
        "MODULE_FILTER_READY",
        "MODULE_SEARCH_APPLIED",
        "MODULE_NEW_READY",
        "SAMPLE_NEW_READY",
        "SALE_ASN_NEW_READY",
        "COMPANY_FOC_CHANGED",
        "SUPPLIER_CATEGORY_READY",
        "SUPPLIER_FOUND",
        "SUPPLIER_NOT_FOUND",
        "BUYER_EDIT_OPENED",
        "BUYER_NOT_FOUND",
    }
)
SESSION_LOST = frozenset(
    {
        "NOT_LOGGED_IN",
        "CHROME_CLOSED",
        "MISSING_CREDENTIALS",
        "LOGIN_FAILED",
        "LOGIN_TIMEOUT",
        "SESSION_CHECK_FAILED",
    }
)
LOGIN_CODES = frozenset({"LOGGED_IN", "SESSION_REUSED", "SESSION_ACTIVE"})
NON_REPORTABLE_FAILURES = frozenset(
    {
        "BROWSER_NOT_FOUND",
        "CHROME_CLOSED",
        "MISSING_CREDENTIALS",
        "NOT_LOGGED_IN",
        "NO_RESULTS",
        "MULTIPLE_RESULTS",
        "CATEGORY_UNKNOWN",
        "MODULE_UNKNOWN",
        "ADMIN_ACCESS_DENIED",
        "SUPPLIER_NOT_FOUND",
        "BUYER_NOT_FOUND",
        "PASSWORD_REQUIRED",
        "USER_ID_REQUIRED",
        "DIVISION_UNKNOWN",
        "DIVISION_OPTION_NOT_FOUND",
        "CATALOG_RESULT_REQUIRED",
        "CATALOG_RESULT_CHANGED",
        "CATALOG_RESULT_EXPIRED",
        "CATALOG_FILES_CONTEXT_EXPIRED",
        "CATALOG_FILE_EXPIRED",
        "CATALOG_PREPARE_REQUIRED",
        "CATALOG_SEARCH_CONTEXT_LOST",
        "CATALOG_FOLDER_STALE",
        "CATALOG_FOLDER_TREE_EMPTY",
        "CATALOG_FOLDER_INVALID",
        "CATALOG_FOLDER_SCAN_IN_PROGRESS",
        "CATALOG_SCAN_ACCOUNT_CHANGED",
        "QUERY_REQUIRED",
        "INVALID_FILTER",
        "APPAREL_ONLY",
        "CODE_REQUIRED",
        "CODE_NOT_FOUND",
        "MODULE_LIST_NOT_OPEN",
        "BUYER_LIST_NOT_OPEN",
        "COMPANY_LIST_NOT_OPEN",
        "ACTION_IN_PROGRESS",
        "ACTION_CANCELLED",
        "ARTICLE_DESTINATION_UNKNOWN",
        "HOTKEY_INVALID",
        "JOB_NOT_FOUND",
        "JOB_NOT_RETRYABLE",
        "COSTING_FILE_REQUIRED",
        "COSTING_FILE_TYPE_UNSUPPORTED",
        "COSTING_FILE_TOO_LARGE",
        "COSTING_FORMAT_UNSUPPORTED",
        "COSTING_FORMULA_NOT_ALLOWED",
        "COSTING_VALIDATION_FAILED",
        "COSTING_REQUIRED_FIELD_MISSING",
        "COSTING_STYLE_MISMATCH",
        "COSTING_NOT_OPEN",
        "COSTING_ARTICLE_NOT_FOUND",
        "COSTING_ARTICLE_AMBIGUOUS",
        "COSTING_PLAN_EXPIRED",
        "COSTING_PLAN_STALE",
        "COSTING_ARTICLE_FLOW_PENDING",
        "COSTING_SOURCE_REQUIRED",
        "COSTING_ACTIVE_TAB_NOT_FOUND",
        "COSTING_ACTIVE_TAB_AMBIGUOUS",
        "COSTING_STYLE_NOT_DETECTED",
    }
)

# Các flow này điều hướng tab WFX chính ra khỏi Catalog. Xoá dấu "Master đã
# chuẩn bị" ngay khi flow thành công để lần Search Catalog kế tiếp tự mở đúng
# List, thay vì thử dùng một grid cũ không còn tồn tại.
CATALOG_CONTEXT_INVALIDATING_METHODS = frozenset(
    {
        "open_module",
        "open_sale_asn_new",
        "search_oc",
        "search_sample",
        "open_sample_new",
        "search_sale_asn",
        "search_rmpo",
        "search_indent",
        "open_module_new",
        "toggle_company_foc",
        "open_supplier_category",
        "find_supplier",
        "find_supplier_in_category",
        "find_buyer",
    }
)


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
        self._hotkey_applier: Callable[[str], str | None] | None = None
        self._update_applier: Callable[[dict], str | None] | None = None
        self._on_top_applier: Callable[[bool], None] | None = None
        self._session_active: bool | None = None
        self._last_login_at: str | None = None
        self._current_run_id: str | None = None
        self._admin_access: bool | None = None
        self._admin_module_ids: set[str] = set()
        self._current_division: str | None = None
        self._division_label: str | None = None
        self._division_name: str | None = None
        # Playwright/CDP không được chạy hai workflow song song trên cùng WFX
        # session. Trả về ngay thay vì xếp hàng khiến WebView trông bị treo.
        self._run_lock = threading.Lock()
        # Toàn bộ state + logic Catalog (kết quả tìm, category đã chuẩn bị, cache
        # cây folder) sống trong controller riêng để bridge không phình to.
        self._catalog = CatalogController(self)

    # -- logging -----------------------------------------------------------
    def set_log_sink(self, sink: Callable[[str], None]) -> None:
        self._sink = sink

    def set_result_sink(
        self, sink: Callable[[str, dict, float], None]
    ) -> None:
        self._result_sink = sink

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
            "user_id": account["user_id"],
            "has_credentials": bool(
                account["user_id"].strip() and account["password"].strip()
            ),
            "theme": preferences["theme"],
            "close_after_module": preferences["close_after_module"],
            "return_to_list_after_action": preferences[
                "return_to_list_after_action"
            ],
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
            "catalog_default_folder": (
                self._catalog.default_folder_for_account(preferences)
            ),
            **self._admin_state(preferences),
            "reporting_configured": telemetry.is_configured(self._base_dir),
            "pending_reports": telemetry.outbox_count(self._base_dir),
            "update_channel": "stable",
            "module_groups": module_controllers.manifest_groups(),
            "divisions": list(constants.DIVISIONS.values()),
            "jobs": job_history.list_jobs(self._base_dir, 20),
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

    def _observe(self, method_name: str, result: dict, elapsed: float) -> None:
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

        if code in {"DIVISION_CHANGED", "LOGGED_IN"}:
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

        if self._result_sink is not None:
            try:
                self._result_sink(method_name, result, elapsed)
            except Exception:
                pass

    def _run(
        self,
        method_name: str,
        action: Callable[[], dict],
        request: dict | None = None,
    ) -> dict:
        if not self._run_lock.acquire(blocking=False):
            return {
                "ok": False,
                "code": "ACTION_IN_PROGRESS",
                "message": "WFX Smart đang xử lý tác vụ trước. Vui lòng chờ hoàn tất.",
                **self._session_status(),
                **self._division_state(),
            }
        try:
            return automation_runtime.run(
                lambda: self._run_unlocked(method_name, action, request)
            )
        finally:
            self._run_lock.release()

    def _run_unlocked(
        self,
        method_name: str,
        action: Callable[[], dict],
        request: dict | None = None,
    ) -> dict:
        run_id = job_history.new_run_id()
        started = time.monotonic()
        started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._current_run_id = run_id
        self._log(f"[RUN] Bắt đầu {method_name}")
        try:
            result = action()
        except AutomationCancelled:
            result = {
                "ok": False,
                "code": "ACTION_CANCELLED",
                "message": "Đã dừng tác vụ tại checkpoint an toàn.",
            }
        except Exception as error:
            result = {
                "ok": False,
                "code": "PANEL_ERROR",
                "message": f"{type(error).__name__}: {error}",
            }
        if not isinstance(result, dict):
            result = {
                "ok": False,
                "code": "PANEL_ERROR",
                "message": "Kết quả không hợp lệ.",
            }
        elapsed = time.monotonic() - started
        code = str(result.get("code") or "UNKNOWN")
        screenshot: str | None = None
        if (
            not result.get("ok")
            and code not in NON_REPORTABLE_FAILURES
            and method_name
            in {
                "login",
                "check_session",
                "open_module",
                "prepare_catalog",
                "find_code",
                "find_buyer_reference",
                "open_sale_asn_new",
                "open_sample_new",
                "search_oc",
                "search_sample",
                "search_sale_asn",
                "search_rmpo",
                "search_indent",
                "open_module_new",
                "open_supplier_category",
                "find_supplier",
                "find_supplier_in_category",
                "find_buyer",
                "toggle_company_foc",
                "switch_division",
                "open_catalog_destination",
                "download_catalog_file",
                "export_catalog_costing",
                "prepare_catalog_costing_import",
                "apply_catalog_costing",
            }
            and hasattr(self._login, "capture_failure_screenshot")
        ):
            shot = (
                job_history.screenshot_dir(self._base_dir)
                / f"{run_id}.png"
            )
            try:
                if self._login.capture_failure_screenshot(shot, self._log):
                    screenshot = str(shot)
            except Exception:
                screenshot = None
        result = {**result, "run_id": run_id}
        self._log(
            f"[RUN] Kết thúc {method_name}: {result.get('code', 'UNKNOWN')} "
            f"({int(elapsed * 1000)} ms)"
        )
        self._current_run_id = None
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
        if not result.get("ok") and code not in NON_REPORTABLE_FAILURES:
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
        self._observe(method_name, result, elapsed)
        return {
            **result,
            **self._session_status(),
            **self._division_state(),
        }

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
        return self._run_lock.locked()

    def shutdown(self) -> None:
        automation_runtime.shutdown()

    # -- automation --------------------------------------------------------
    def login(self) -> dict:
        def action() -> dict:
            account = self._account()
            result = self._login.run(
                account["user_id"],
                account["password"],
                self._login.COMPANY_ID,
                self._log,
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

    def open_chrome(self) -> dict:
        def action() -> dict:
            browser = self._login.start_chrome(self._log)
            if not browser.get("ok"):
                return browser
            account = self._account()
            logged_in = self._login.run(
                account["user_id"],
                account["password"],
                self._login.COMPANY_ID,
                self._log,
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
        def action() -> dict:
            return self._login.open_sale_asn_new(
                constants.SALE_ASN_NEW_XPATH,
                self._log,
            )

        return self._run("open_sale_asn_new", action)

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
        filter_kind: str,
        query: str,
    ) -> dict:
        sample = constants.MODULE_BY_ID["0004_0056_4070"]
        return self._run(
            "search_sample",
            lambda: self._login.search_sample_list(
                sample["xpath"],
                str(filter_kind or ""),
                str(query or "").strip(),
                self._log,
            ),
            {
                "filter_kind": str(filter_kind or ""),
                "query": str(query or "").strip(),
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

    def search_sale_asn(
        self,
        filter_kind: str,
        query: str,
    ) -> dict:
        sale_asn = constants.MODULE_BY_ID["0004_0070_0020"]
        return self._run(
            "search_sale_asn",
            lambda: self._login.search_sale_asn_list(
                sale_asn["xpath"],
                str(filter_kind or ""),
                str(query or "").strip(),
                self._log,
            ),
            {
                "filter_kind": str(filter_kind or ""),
                "query": str(query or "").strip(),
            },
        )

    def search_rmpo(
        self,
        supplier: str,
        order_no: str,
    ) -> dict:
        rmpo = constants.MODULE_BY_ID["0005_0050_0020"]
        return self._run(
            "search_rmpo",
            lambda: self._login.search_rmpo_list(
                rmpo["xpath"],
                str(supplier or "").strip(),
                str(order_no or "").strip(),
                self._log,
            ),
            {"module_id": "0005_0050_0020"},
        )

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
        def action() -> dict:
            denied = self._admin_module_access_error("0090_0007")
            if denied is not None:
                return denied
            company = constants.MODULE_BY_ID["0090_0007"]
            toggler = getattr(self._login, "toggle_company_foc", None)
            if not callable(toggler):
                return {
                    "ok": False,
                    "code": "COMPANY_FOC_UNSUPPORTED",
                    "message": "Bản automation chưa hỗ trợ đổi FOC.",
                }
            return toggler(company["xpath"], self._log)

        return self._run("toggle_company_foc", action)

    def open_supplier_category(self, category_name: str) -> dict:
        def action() -> dict:
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            denied = self._admin_module_access_error("0005_0010_1290")
            if denied is not None:
                return denied
            supplier = constants.MODULE_BY_ID["0005_0010_1290"]
            return self._login.open_supplier_category(
                supplier["xpath"],
                category_name,
                value,
                self._log,
            )

        return self._run(
            "open_supplier_category",
            action,
            {"category_name": category_name},
        )

    def find_supplier(self, query: str) -> dict:
        def action() -> dict:
            denied = self._admin_module_access_error("0005_0010_1290")
            if denied is not None:
                return denied
            supplier = constants.MODULE_BY_ID["0005_0010_1290"]
            return self._login.find_supplier_across_categories(
                supplier["xpath"],
                constants.CATEGORIES,
                str(query or "").strip(),
                self._log,
            )

        return self._run(
            "find_supplier",
            action,
            {"query": str(query or "").strip()},
        )

    def find_supplier_in_category(
        self,
        category_name: str,
        query: str,
    ) -> dict:
        def action() -> dict:
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            denied = self._admin_module_access_error("0005_0010_1290")
            if denied is not None:
                return denied
            supplier = constants.MODULE_BY_ID["0005_0010_1290"]
            return self._login.find_supplier_in_category(
                supplier["xpath"],
                category_name,
                value,
                str(query or "").strip(),
                self._log,
            )

        return self._run(
            "find_supplier_in_category",
            action,
            {
                "category_name": category_name,
                "query": str(query or "").strip(),
            },
        )

    def find_buyer(self, query: str) -> dict:
        def action() -> dict:
            denied = self._admin_module_access_error("0004_0010_1720")
            if denied is not None:
                return denied
            buyer = constants.MODULE_BY_ID["0004_0010_1720"]
            return self._login.find_and_open_buyer(
                buyer["xpath"],
                str(query or "").strip(),
                self._log,
            )

        return self._run(
            "find_buyer",
            action,
            {"query": str(query or "").strip()},
        )

    def switch_division(self, division_key: str) -> dict:
        def action() -> dict:
            if not hasattr(self._login, "switch_division"):
                return {
                    "ok": False,
                    "code": "DIVISION_CHANGE_UNSUPPORTED",
                    "message": "Bản automation chưa hỗ trợ đổi Division.",
                }
            result = self._login.switch_division(division_key, self._log)
            return self._with_admin_access(result)

        return self._run(
            "switch_division",
            action,
            {"division_key": str(division_key or "").casefold()},
        )

    # -- catalog (uỷ quyền cho CatalogController) --------------------------
    def scan_catalog_folders(
        self, category_name: str, force: bool = False
    ) -> dict:
        return self._catalog.scan_folders(category_name, force)

    def set_catalog_default_folder(
        self, category_name: str, node_id: str
    ) -> dict:
        return self._catalog.set_default_folder(category_name, node_id)

    def browse_catalog(self, category_name: str) -> dict:
        return self._catalog.browse(category_name)

    def prepare_catalog(self, category_name: str) -> dict:
        return self._catalog.prepare(category_name)

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
        return self._catalog.download_file(file_id)

    def export_catalog_costing(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
    ) -> dict:
        return self._catalog.export_costing(
            category_name,
            filter_kind,
            query,
            file_path,
        )

    def inspect_active_catalog_costing(self, category_name: str) -> dict:
        return self._catalog.inspect_active_costing(category_name)

    def validate_catalog_costing_file(self, file_path: str) -> dict:
        return self._catalog.validate_costing_file(file_path)

    def prepare_catalog_costing_import(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
    ) -> dict:
        return self._catalog.prepare_costing_import(
            category_name,
            filter_kind,
            query,
            file_path,
        )

    def clear_catalog_costing_plan(self, plan_token: str) -> dict:
        return self._catalog.clear_costing_plan(plan_token)

    def apply_catalog_costing(
        self,
        plan_token: str,
        article_resolutions: dict | None = None,
    ) -> dict:
        return self._catalog.apply_costing(plan_token, article_resolutions)

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
        if not password.strip():
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
        if previous_user_id.casefold() != user_id.casefold():
            self._catalog.reset_for_account_change()
        self._log("[SETTINGS] Đã lưu tài khoản")
        return {
            "ok": True,
            "code": "ACCOUNT_SAVED",
            "message": "Đã lưu tài khoản.",
            "user_id": user_id,
            "has_credentials": True,
        }

    def set_theme(self, theme: str) -> dict:
        saved = self._prefs.save_prefs(base_dir=self._base_dir, theme=theme)
        return {"ok": True, "code": "THEME_SAVED", "message": "Đã đổi giao diện", "theme": saved["theme"]}

    def set_close_after_module(self, value: bool) -> dict:
        saved = self._prefs.save_prefs(base_dir=self._base_dir, close_after_module=bool(value))
        return {"ok": True, "code": "PREF_SAVED", "message": "Đã lưu",
                "close_after_module": saved["close_after_module"]}

    def set_return_to_list_after_action(self, enabled: bool) -> dict:
        saved = self._prefs.save_prefs(
            base_dir=self._base_dir,
            return_to_list_after_action=bool(enabled),
        )
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": (
                "Sau khi thao tác xong, app sẽ trở về List."
                if saved["return_to_list_after_action"]
                else "App sẽ nhớ màn module đang làm."
            ),
            "return_to_list_after_action": saved[
                "return_to_list_after_action"
            ],
        }

    def set_module_favorite(self, module_id: str, favorite: bool) -> dict:
        module_id = str(module_id or "").strip()
        if module_id not in constants.MODULE_BY_ID:
            return {
                "ok": False,
                "code": "MODULE_UNKNOWN",
                "message": "Không tìm thấy module để ghim.",
            }
        preferences = self._prefs.load_prefs(base_dir=self._base_dir)
        ids = list(preferences["favorite_module_ids"])
        if favorite and module_id not in ids:
            ids.append(module_id)
        elif not favorite:
            ids = [value for value in ids if value != module_id]
        saved = self._prefs.save_prefs(
            base_dir=self._base_dir,
            favorite_module_ids=ids,
        )
        module_name = constants.MODULE_BY_ID[module_id]["name"]
        return {
            "ok": True,
            "code": "MODULE_FAVORITE_SAVED",
            "message": (
                f"Đã ghim {module_name} lên đầu."
                if favorite
                else f"Đã bỏ ghim {module_name}."
            ),
            "favorite_module_ids": saved["favorite_module_ids"],
        }

    def set_hotkey(self, spec: str | dict) -> dict:
        try:
            normalized = (
                hotkey_spec.from_event(spec)
                if isinstance(spec, dict)
                else hotkey_spec.normalize(spec)
            )
        except (ValueError, TypeError, AttributeError) as error:
            return {
                "ok": False,
                "code": "HOTKEY_INVALID",
                "message": str(error),
            }

        previous = self._prefs.load_prefs(base_dir=self._base_dir)["hotkey"]
        if self._hotkey_applier is not None:
            failure = self._hotkey_applier(normalized)
            if failure:
                self._hotkey_applier(previous)
                return {
                    "ok": False,
                    "code": "HOTKEY_REGISTER_FAILED",
                    "message": failure,
                    "hotkey": previous,
                    "hotkey_label": hotkey_spec.format_label(previous),
                }

        saved = self._prefs.save_prefs(
            base_dir=self._base_dir, hotkey=normalized
        )
        self._log(f"[SETTINGS] Đã đổi hotkey sang {saved['hotkey_label']}")
        return {
            "ok": True,
            "code": "HOTKEY_SAVED",
            "message": f"Đã đổi hotkey sang {saved['hotkey_label']}.",
            "hotkey": saved["hotkey"],
            "hotkey_label": saved["hotkey_label"],
        }

    def set_autostart(self, enabled: bool) -> dict:
        wanted = bool(enabled)
        actual = autostart.sync(wanted)
        self._prefs.save_prefs(
            base_dir=self._base_dir, autostart=actual
        )
        if actual != wanted:
            return {
                "ok": False,
                "code": "AUTOSTART_FAILED",
                "message": "Không ghi được thiết lập khởi động cùng Windows.",
                "autostart": actual,
            }
        return {
            "ok": True,
            "code": "AUTOSTART_SAVED",
            "message": (
                "Đã bật khởi động cùng Windows."
                if actual
                else "Đã tắt khởi động cùng Windows."
            ),
            "autostart": actual,
        }

    def set_start_hidden(self, enabled: bool) -> dict:
        saved = self._prefs.save_prefs(
            base_dir=self._base_dir, start_hidden=bool(enabled)
        )
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": (
                "Lần mở tới sẽ ẩn trong tray."
                if saved["start_hidden"]
                else "Lần mở tới sẽ hiện panel."
            ),
            "start_hidden": saved["start_hidden"],
        }

    def set_toast_enabled(self, enabled: bool) -> dict:
        saved = self._prefs.save_prefs(
            base_dir=self._base_dir, toast_enabled=bool(enabled)
        )
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": (
                "Đã bật thông báo."
                if saved["toast_enabled"]
                else "Đã tắt thông báo."
            ),
            "toast_enabled": saved["toast_enabled"],
        }

    def set_focus_chrome_on_module(self, enabled: bool) -> dict:
        saved = self._prefs.save_prefs(
            base_dir=self._base_dir,
            focus_chrome_on_module=bool(enabled),
        )
        return {
            "ok": True,
            "code": "PREF_SAVED",
            "message": (
                "Chrome sẽ tự hiện khi chạy module."
                if saved["focus_chrome_on_module"]
                else "Đã tắt tự động đưa Chrome lên trước."
            ),
            "focus_chrome_on_module": saved[
                "focus_chrome_on_module"
            ],
        }

    def set_always_on_top(self, enabled: bool) -> dict:
        value = bool(enabled)
        saved = self._prefs.save_prefs(
            base_dir=self._base_dir, always_on_top=value
        )
        if self._on_top_applier is not None:
            self._on_top_applier(saved["always_on_top"])
        return {
            "ok": True,
            "code": "WINDOW_PREF_SAVED",
            "message": (
                "Panel sẽ luôn nằm trên cùng."
                if saved["always_on_top"]
                else "Panel không còn bị ghim trên cùng."
            ),
            "always_on_top": saved["always_on_top"],
        }

    def set_admin_mode(self, enabled: bool) -> dict:
        wanted = bool(enabled)
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

    def submit_feedback(
        self,
        kind: str,
        message: str,
        include_diagnostics: bool = True,
    ) -> dict:
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
        event = {
            "event_type": "user_feedback",
            "kind": kind,
            "message": message,
            "app_version": APP_VERSION,
            "account": self._telemetry_account_context(),
        }
        if include_diagnostics:
            recent = job_history.list_jobs(self._base_dir, 5)
            event["diagnostics"] = {
                **telemetry.system_summary(),
                **self.get_status(),
                "recent_jobs": [
                    {
                        "run_id": row.get("run_id"),
                        "method": row.get("method"),
                        "code": row.get("code"),
                        "elapsed_ms": row.get("elapsed_ms"),
                    }
                    for row in recent
                ],
            }
        delivery = telemetry.submit(self._base_dir, event)
        sent = delivery.get("delivery") == "sent"
        return {
            **delivery,
            "code": "FEEDBACK_SENT" if sent else "FEEDBACK_QUEUED",
            "message": (
                "Đã gửi góp ý. Cảm ơn bạn."
                if sent
                else "Đã lưu góp ý an toàn trên máy; app sẽ tự gửi khi webhook được cấu hình."
            ),
            "reporting_configured": telemetry.is_configured(self._base_dir),
        }

    def flush_error_reports(self) -> dict:
        return {
            **telemetry.flush(self._base_dir),
            "reporting_configured": telemetry.is_configured(self._base_dir),
        }

    def set_update_channel(self, channel: str) -> dict:
        saved = self._prefs.save_prefs(
            base_dir=self._base_dir, update_channel="stable"
        )
        return {
            "ok": True,
            "code": "UPDATE_CHANNEL_SAVED",
            "message": "Ứng dụng luôn sử dụng kênh Stable.",
            "update_channel": saved["update_channel"],
        }

    def check_for_updates(self) -> dict:
        return updater.check_for_updates(channel="stable")

    def install_update(self) -> dict:
        state = updater.check_for_updates(channel="stable")
        if not state.get("can_update"):
            return state
        if self._update_applier is None:
            return {
                **state,
                "ok": False,
                "code": "UPDATE_APPLIER_MISSING",
                "message": "Bộ cài cập nhật chưa sẵn sàng.",
                "can_update": False,
            }
        failure = self._update_applier(state)
        if failure:
            return {
                **state,
                "ok": False,
                "code": "UPDATE_SCHEDULE_FAILED",
                "message": failure,
                "can_update": False,
            }
        return {
            **state,
            "ok": True,
            "code": "UPDATE_SCHEDULED",
            "message": (
                "Đang cài bản mới. Ứng dụng sẽ đóng và tự mở lại khi hoàn tất."
            ),
            "can_update": False,
        }

    # -- job history ------------------------------------------------------
    def get_job_history(self, limit: int = 30) -> dict:
        return {
            "ok": True,
            "code": "JOB_HISTORY",
            "jobs": job_history.list_jobs(self._base_dir, limit),
        }

    def retry_job(self, run_id: str) -> dict:
        job = job_history.get_job(self._base_dir, run_id)
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
        category_name = str(request.get("category_name") or "Apparel")
        query = str(request.get("query") or "")
        destination = request.get("destination")
        retry_handlers: dict[str, Callable[[], dict]] = {
            "login": self.login,
            "check_session": self.check_session,
            "open_module": lambda: self.open_module(
                str(request.get("module_id") or "")
            ),
            "prepare_catalog": lambda: self.prepare_catalog(category_name),
            "scan_catalog_folders": lambda: self.scan_catalog_folders(
                category_name,
                True,
            ),
            "browse_catalog": lambda: self.browse_catalog(category_name),
            "catalog_action": lambda: self.catalog_action(
                category_name,
                str(request.get("filter_kind") or "code"),
                query,
                destination,
            ),
            "find_code": lambda: self.find_code(
                category_name,
                query,
                destination,
            ),
            "find_buyer_reference": lambda: self.find_buyer_reference(
                category_name,
                query,
                destination,
            ),
            "open_catalog_destination": lambda: self.open_catalog_destination(
                str(destination or ""),
                str(request.get("article_code") or ""),
            ),
            "download_catalog_file": lambda: self.download_catalog_file(
                str(request.get("file_id") or "")
            ),
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
        job = job_history.get_job(self._base_dir, run_id)
        path = Path(str((job or {}).get("screenshot") or "")).resolve()
        allowed_dir = job_history.screenshot_dir(self._base_dir).resolve()
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
        job_history.clear(self._base_dir)
        return {
            "ok": True,
            "code": "JOB_HISTORY_CLEARED",
            "message": "Đã xóa lịch sử và ảnh lỗi cục bộ.",
            "jobs": [],
        }

    def clear_log(self) -> dict:
        self._logs = []
        return {"ok": True, "code": "LOG_CLEARED", "message": "Đã xóa nhật ký"}
