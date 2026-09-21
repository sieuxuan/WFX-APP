"""Mở màn hình WFX và tìm kiếm trên List của các module dùng chung.

Mỗi nút là một flow riêng: ``List`` mở đúng màn danh sách, ``New`` xác nhận
đã tới trang đích thật, còn ``Search`` tự mở List khi context chưa sẵn sàng
— người dùng không cần bấm List trước.

``(GDN) Dispatch`` cũng ở đây vì nó là một flow module: mở report, tải
workbook rồi đẩy qua EDI Production Order. ``Create Transaction`` là ranh
giới không idempotent nên mất xác nhận phải trả ``GDN_TRANSACTION_UNCONFIRMED``
chứ không tự thử lại."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import constants, module_registry
from wfx_panel.coercion import boolean


class ModulesController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel


    def open_module(self, module_id: str) -> dict:
        panel = self._panel
        def action() -> dict:
            controller = module_registry.get(module_id)
            if controller is None:
                return {
                    "ok": False,
                    "code": "MODULE_UNKNOWN",
                    "message": f"Module lạ: {module_id}",
                }
            if module_id in constants.ADMIN_MODULE_IDS:
                panel._refresh_admin_access()
                if (
                    panel._admin_access is not True
                    or module_id not in panel._admin_module_ids
                ):
                    return {
                        "ok": False,
                        "code": "ADMIN_ACCESS_DENIED",
                        "message": "Tài khoản WFX không có quyền mở module Admin này.",
                        **panel._admin_state(),
                    }
            return controller.open(panel._login, panel._log)

        return panel._run(
            "open_module", action, {"module_id": module_id}
        )

    def open_module_new(self, module_id: str) -> dict:
        panel = self._panel
        return panel._run(
            "open_module_new",
            lambda: panel._login.open_module_new(
                str(module_id or ""),
                panel._log,
            ),
            {"module_id": str(module_id or "")},
        )

    def open_sample_new(self) -> dict:
        panel = self._panel
        return panel._run(
            "open_sample_new",
            lambda: panel._login.open_sample_new(
                constants.SAMPLE_NEW_XPATH,
                panel._log,
            ),
        )

    def search_oc(
        self,
        filter_kind: str,
        query: str,
    ) -> dict:
        panel = self._panel
        oc = constants.MODULE_BY_ID["0004_0050_0020"]
        return panel._run(
            "search_oc",
            lambda: panel._login.search_oc_list(
                oc["xpath"],
                str(filter_kind or ""),
                str(query or "").strip(),
                panel._log,
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
        panel = self._panel
        sample = constants.MODULE_BY_ID["0004_0056_4070"]
        values = {
            "sample_no": str(sample_no or "").strip(),
            "style": str(style or "").strip(),
            "created_by": str(created_by or "").strip(),
            "buyer": str(buyer or "").strip(),
        }
        active_filters = [key for key, value in values.items() if value]
        return panel._run(
            "search_sample",
            lambda: panel._login.search_sample_list_with_filters(
                sample["xpath"],
                values,
                panel._log,
            ),
            {
                "filter_kind": "multiple",
                "filter_kinds": active_filters,
            },
        )

    def search_indent(
        self,
        module_id: str,
        supplier: str,
        article: str,
        indent_no: str,
        style: str,
    ) -> dict:
        panel = self._panel
        if module_id not in {"0005_0080_0020", "user_indent_list"}:
            return panel._run(
                "search_indent",
                lambda: {
                    "ok": False,
                    "code": "MODULE_UNKNOWN",
                    "message": f"Module Indent lạ: {module_id}",
                },
                {"module_id": module_id},
            )
        module = constants.MODULE_BY_ID[module_id]
        return panel._run(
            "search_indent",
            lambda: panel._login.search_indent_list(
                module["xpath"],
                module["name"],
                str(supplier or "").strip(),
                str(article or "").strip(),
                str(indent_no or "").strip(),
                str(style or "").strip(),
                panel._log,
            ),
            {"module_id": module_id},
        )

    def search_supplier_invoice(self, supplier: str='', invoice_no: str='', po_no: str='', asn_grn_no: str='') -> dict:
        panel = self._panel
        return panel._finance.search_supplier_invoice(
            supplier,
            invoice_no,
            po_no,
            asn_grn_no,
        )

    def search_expense_invoice(self, supplier: str='', invoice_no: str='', created_by: str='', status: str='') -> dict:
        panel = self._panel
        return panel._finance.search_expense_invoice(
            supplier,
            invoice_no,
            created_by,
            status,
        )

    def run_gdn_dispatch(
        self,
        invoice: str,
        grn_wait_confirmed: bool = False,
    ) -> dict:
        panel = self._panel
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
            runner = getattr(panel._login, "run_gdn_dispatch", None)
            if not callable(runner):
                return {
                    "ok": False,
                    "code": "GDN_DISPATCH_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ (GDN) Dispatch.",
                }
            return runner(
                invoice_value,
                panel._log,
                panel._progress_for("run_gdn_dispatch"),
            )

        # Không lưu Invoice vào request/job history/telemetry.
        return panel._run(
            "run_gdn_dispatch",
            action,
            {"module_id": "gdn_dispatch"},
        )

    def open_gdn_status(self) -> dict:
        """Mở EDI BuyerOrderDispatch để kiểm tra package, không submit lại."""
        panel = self._panel

        def action() -> dict:
            opener = getattr(panel._login, "open_gdn_status", None)
            if not callable(opener):
                return {
                    "ok": False,
                    "code": "GDN_DISPATCH_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ kiểm tra GDN.",
                }
            return opener(panel._log)

        return panel._run(
            "open_gdn_status",
            action,
            {"module_id": "gdn_dispatch"},
        )
