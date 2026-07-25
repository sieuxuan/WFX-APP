from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from wfx_panel import constants, log_bridge, prefs as prefs_default


class PanelAPI:
    def __init__(self, login_module=None, prefs_module=None, base_dir: Path | None = None):
        if login_module is None:
            import login as login_module  # imported lazily so tests can inject a fake
        self._login = login_module
        self._prefs = prefs_module or prefs_default
        self._base_dir = base_dir or self._prefs.APP_DIR
        self._logs: list[str] = []
        self._sink: Callable[[str], None] | None = None

    # -- logging -----------------------------------------------------------
    def set_log_sink(self, sink: Callable[[str], None]) -> None:
        self._sink = sink

    def _log(self, message: str) -> None:
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

    # -- state -------------------------------------------------------------
    def get_initial_state(self) -> dict:
        account = self._account()
        preferences = self._prefs.load_prefs(base_dir=self._base_dir)
        return {
            "user_id": account["user_id"],
            "theme": preferences["theme"],
            "close_after_module": preferences["close_after_module"],
            "hotkey_label": preferences["hotkey_label"],
            "logs": list(self._logs),
        }

    # -- automation --------------------------------------------------------
    def login(self) -> dict:
        account = self._account()
        return self._login.run(account["user_id"], account["password"],
                               self._login.COMPANY_ID, self._log)

    def check_session(self) -> dict:
        return self._login.check_session(self._log)

    def open_module(self, module_id: str) -> dict:
        module = constants.MODULE_BY_ID.get(module_id)
        if module is None:
            return {"ok": False, "code": "MODULE_UNKNOWN", "message": f"Module lạ: {module_id}"}
        return self._login.open_module(module["name"], module["xpath"], self._log)

    def prepare_catalog(self, category_name: str) -> dict:
        value = constants.CATEGORIES.get(category_name)
        if value is None:
            return {"ok": False, "code": "CATEGORY_UNKNOWN", "message": f"Category lạ: {category_name}"}
        opened = self._login.open_module("Catalog", self._login.CATALOG_XPATH, self._log)
        if not opened.get("ok"):
            return opened
        return self._login.set_catalog_category(category_name, value, self._log)

    def find_code(self, category_name: str, code: str, destination: str | None = None) -> dict:
        return self._quick(category_name, "code", code, destination)

    def find_buyer_reference(self, category_name: str, query: str, destination: str | None = None) -> dict:
        return self._quick(category_name, "buyer_reference", query, destination)

    def _quick(self, category_name: str, filter_kind: str, query: str, destination):
        value = constants.CATEGORIES.get(category_name)
        if value is None:
            return {"ok": False, "code": "CATEGORY_UNKNOWN", "message": f"Category lạ: {category_name}"}
        account = self._account()
        return self._login.quick_find_catalog(
            category_name, value, filter_kind, query,
            account["user_id"], account["password"], self._login.COMPANY_ID,
            self._log, destination=destination,
        )

    # -- settings ----------------------------------------------------------
    def save_account(self, user_id: str, password: str) -> dict:
        self._prefs.save_account(user_id, password, base_dir=self._base_dir)
        self._log("[SETTINGS] Đã lưu tài khoản")
        return {"ok": True, "code": "ACCOUNT_SAVED", "message": "Đã lưu tài khoản", "user_id": user_id}

    def set_theme(self, theme: str) -> dict:
        saved = self._prefs.save_prefs(base_dir=self._base_dir, theme=theme)
        return {"ok": True, "code": "THEME_SAVED", "message": "Đã đổi giao diện", "theme": saved["theme"]}

    def set_close_after_module(self, value: bool) -> dict:
        saved = self._prefs.save_prefs(base_dir=self._base_dir, close_after_module=bool(value))
        return {"ok": True, "code": "PREF_SAVED", "message": "Đã lưu",
                "close_after_module": saved["close_after_module"]}

    def clear_log(self) -> dict:
        self._logs = []
        return {"ok": True, "code": "LOG_CLEARED", "message": "Đã xóa nhật ký"}
