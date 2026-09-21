"""Quyền quản trị và Division đang làm việc.

Thẻ `Dữ liệu Article & Style` dùng CHUNG điều kiện hiển thị với `Chế độ
quản trị`: tài khoản không có quyền thì không thấy cả hai mục.

State (`_admin_access`, `_current_division`…) cố tình ở lại ``PanelAPI``:
mọi kết quả flow đều mang nó về UI qua ``_run_unlocked``, nên nó là state
toàn cục của panel chứ không phải của riêng màn này."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import constants
from wfx_panel.coercion import boolean


class AccessController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel


    def _admin_state(self, preferences: Mapping | None = None) -> dict:
        panel = self._panel
        if preferences is None:
            preferences = panel._prefs.load_prefs(base_dir=panel._base_dir)
        allowed = panel._admin_access is True and bool(panel._admin_module_ids)
        return {
            "admin_access": allowed,
            "admin_module_ids": sorted(panel._admin_module_ids) if allowed else [],
            "admin_mode": bool(preferences["admin_mode"] and allowed),
        }

    def _division_state(self) -> dict:
        panel = self._panel
        return {
            "current_division": panel._current_division,
            "division_label": panel._division_label,
            "division_name": panel._division_name,
        }

    def _refresh_admin_access(self) -> dict:
        panel = self._panel
        if not hasattr(panel._login, "check_module_access"):
            panel._admin_access = False
            panel._admin_module_ids = set()
            return self._admin_state()
        checked = panel._login.check_module_access(
            constants.ADMIN_MODULE_SPECS,
            panel._log,
        )
        ids = {
            str(module_id)
            for module_id in checked.get("accessible_module_ids", [])
            if str(module_id) in constants.ADMIN_MODULE_IDS
        }
        panel._admin_module_ids = ids
        panel._admin_access = bool(checked.get("ok") and ids)
        if not panel._admin_access:
            panel._prefs.save_prefs(
                base_dir=panel._base_dir,
                admin_mode=False,
            )
        return self._admin_state()

    def _with_admin_access(self, result: dict) -> dict:
        panel = self._panel
        if result.get("ok"):
            return {**result, **self._refresh_admin_access()}
        panel._admin_access = False
        panel._admin_module_ids = set()
        return {**result, **self._admin_state()}

    def set_admin_mode(self, enabled: bool) -> dict:
        panel = self._panel
        wanted = boolean(enabled)
        if wanted:
            self._refresh_admin_access()
        if wanted and panel._admin_access is not True:
            panel._prefs.save_prefs(
                base_dir=panel._base_dir,
                admin_mode=False,
            )
            return {
                "ok": False,
                "code": "ADMIN_ACCESS_DENIED",
                "message": "Tài khoản WFX này không có module Admin được cấp quyền.",
                **self._admin_state(),
            }
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir,
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

    def _admin_module_access_error(self, module_id: str) -> dict | None:
        panel = self._panel
        self._refresh_admin_access()
        if (
            panel._admin_access is True
            and module_id in panel._admin_module_ids
        ):
            return None
        return {
            "ok": False,
            "code": "ADMIN_ACCESS_DENIED",
            "message": "Tài khoản WFX không có quyền mở module Admin này.",
            **self._admin_state(),
        }

    def switch_division(self, division_key: str) -> dict:
        panel = self._panel
        return panel._directory.switch_division(division_key)
