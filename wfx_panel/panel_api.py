from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
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
        "MODULE_FILTER_READY",
        "SALE_ASN_NEW_READY",
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
        "HOTKEY_INVALID",
        "JOB_NOT_FOUND",
        "JOB_NOT_RETRYABLE",
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

    def _admin_state(self) -> dict:
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
            "hotkey": preferences["hotkey"],
            "hotkey_label": preferences["hotkey_label"],
            "autostart": preferences["autostart"],
            "start_hidden": preferences["start_hidden"],
            "toast_enabled": preferences["toast_enabled"],
            "focus_chrome_on_module": preferences[
                "focus_chrome_on_module"
            ],
            "always_on_top": preferences["always_on_top"],
            **self._admin_state(),
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
        run_id = job_history.new_run_id()
        started = time.monotonic()
        started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._current_run_id = run_id
        self._log(f"[RUN] Bắt đầu {method_name}")
        try:
            result = action()
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
        screenshot: str | None = None
        if (
            not result.get("ok")
            and method_name
            in {
                "login",
                "check_session",
                "open_module",
                "prepare_catalog",
                "find_code",
                "find_buyer_reference",
                "open_sale_asn_new",
                "open_supplier_category",
                "find_supplier",
                "find_buyer",
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
        code = str(result.get("code") or "UNKNOWN")
        if not result.get("ok") and code not in NON_REPORTABLE_FAILURES:
            telemetry.enqueue(
                self._base_dir,
                {
                    "event_type": "automation_error",
                    "app_version": APP_VERSION,
                    "method": method_name,
                    "code": code,
                    "run_id": run_id,
                    "elapsed_ms": int(elapsed * 1000),
                    **telemetry.system_summary(),
                },
            )
            threading.Thread(
                target=telemetry.flush,
                args=(self._base_dir,),
                daemon=True,
            ).start()
        self._observe(method_name, result, elapsed)
        return {
            **result,
            **self._session_status(),
            **self._division_state(),
        }

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

    def prepare_catalog(self, category_name: str) -> dict:
        def action() -> dict:
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            opened = self._login.open_module(
                "Catalog", self._login.CATALOG_XPATH, self._log
            )
            if not opened.get("ok"):
                return opened
            return self._login.set_catalog_category(
                category_name, value, self._log
            )

        return self._run(
            "prepare_catalog", action, {"category_name": category_name}
        )

    def find_code(self, category_name: str, code: str, destination: str | None = None) -> dict:
        return self._quick("find_code", category_name, "code", code, destination)

    def find_buyer_reference(self, category_name: str, query: str, destination: str | None = None) -> dict:
        return self._quick(
            "find_buyer_reference",
            category_name,
            "buyer_reference",
            query,
            destination,
        )

    def _quick(
        self,
        method_name: str,
        category_name: str,
        filter_kind: str,
        query: str,
        destination,
    ):
        def action() -> dict:
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            account = self._account()
            return self._login.quick_find_catalog(
                category_name,
                value,
                filter_kind,
                query,
                account["user_id"],
                account["password"],
                self._login.COMPANY_ID,
                self._log,
                destination=destination,
            )

        return self._run(
            method_name,
            action,
            {
                "category_name": category_name,
                "query": query,
                "destination": destination,
            },
        )

    # -- settings ----------------------------------------------------------
    def save_account(self, user_id: str, password: str) -> dict:
        # Password field trên UI không bao giờ được điền lại (get_initial_state
        # chỉ trả user_id) nên luôn trống khi sheet mở lại. Nếu người dùng chỉ
        # sửa User ID hoặc bấm CTA mà không gõ lại mật khẩu, KHÔNG được ghi đè
        # mật khẩu đã lưu bằng chuỗi rỗng — giữ nguyên mật khẩu cũ.
        user_id = str(user_id or "").strip()
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
        self._prefs.save_account(user_id, password, base_dir=self._base_dir)
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
        if method == "login":
            return self.login()
        if method == "check_session":
            return self.check_session()
        if method == "open_module":
            return self.open_module(str(request.get("module_id") or ""))
        if method == "prepare_catalog":
            return self.prepare_catalog(
                str(request.get("category_name") or "Apparel")
            )
        if method == "find_code":
            return self.find_code(
                str(request.get("category_name") or "Apparel"),
                str(request.get("query") or ""),
                request.get("destination"),
            )
        if method == "find_buyer_reference":
            return self.find_buyer_reference(
                str(request.get("category_name") or "Apparel"),
                str(request.get("query") or ""),
                request.get("destination"),
            )
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
