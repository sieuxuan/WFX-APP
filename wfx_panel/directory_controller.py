"""Buyer, Supplier, Division và Company Setup.

Buyer/Supplier chỉ được resolve lại frame cùng PartyType với flow ban đầu.
Tìm trong tất cả Supplier Category phải tiếp tục khi một Category lỗi, và
báo rõ đây là kết quả một phần."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import constants


class DirectoryController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel


    def open_supplier_category(self, category_name: str) -> dict:
        panel = self._panel
        def action() -> dict:
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            denied = panel._admin_module_access_error("0005_0010_1290")
            if denied is not None:
                return denied
            supplier = constants.MODULE_BY_ID["0005_0010_1290"]
            return panel._login.open_supplier_category(
                supplier["xpath"],
                category_name,
                value,
                panel._log,
            )

        return panel._run(
            "open_supplier_category",
            action,
            {"category_name": category_name},
        )

    def find_supplier(self, query: str) -> dict:
        panel = self._panel
        def action() -> dict:
            denied = panel._admin_module_access_error("0005_0010_1290")
            if denied is not None:
                return denied
            supplier = constants.MODULE_BY_ID["0005_0010_1290"]
            return panel._login.find_supplier_across_categories(
                supplier["xpath"],
                constants.CATEGORIES,
                str(query or "").strip(),
                panel._log,
            )

        return panel._run(
            "find_supplier",
            action,
            {"query": str(query or "").strip()},
        )

    def find_supplier_in_category(
        self,
        category_name: str,
        query: str,
    ) -> dict:
        panel = self._panel
        def action() -> dict:
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            denied = panel._admin_module_access_error("0005_0010_1290")
            if denied is not None:
                return denied
            supplier = constants.MODULE_BY_ID["0005_0010_1290"]
            return panel._login.find_supplier_in_category(
                supplier["xpath"],
                category_name,
                value,
                str(query or "").strip(),
                panel._log,
            )

        return panel._run(
            "find_supplier_in_category",
            action,
            {
                "category_name": category_name,
                "query": str(query or "").strip(),
            },
        )

    def find_buyer(self, query: str) -> dict:
        panel = self._panel
        def action() -> dict:
            denied = panel._admin_module_access_error("0004_0010_1720")
            if denied is not None:
                return denied
            buyer = constants.MODULE_BY_ID["0004_0010_1720"]
            return panel._login.find_and_open_buyer(
                buyer["xpath"],
                str(query or "").strip(),
                panel._log,
            )

        return panel._run(
            "find_buyer",
            action,
            {"query": str(query or "").strip()},
        )

    def switch_division(self, division_key: str) -> dict:
        panel = self._panel
        def action() -> dict:
            if not hasattr(panel._login, "switch_division"):
                return {
                    "ok": False,
                    "code": "DIVISION_CHANGE_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ đổi Division.",
                }
            result = panel._login.switch_division(division_key, panel._log)
            return panel._with_admin_access(result)

        return panel._run(
            "switch_division",
            action,
            {"division_key": str(division_key or "").casefold()},
        )

    def toggle_company_foc(self) -> dict:
        panel = self._panel
        def action() -> dict:
            denied = panel._admin_module_access_error("0090_0007")
            if denied is not None:
                return denied
            company = constants.MODULE_BY_ID["0090_0007"]
            toggler = getattr(panel._login, "toggle_company_foc", None)
            if not callable(toggler):
                return {
                    "ok": False,
                    "code": "COMPANY_FOC_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ đổi FOC.",
                }
            return toggler(company["xpath"], panel._log)

        return panel._run("toggle_company_foc", action)
