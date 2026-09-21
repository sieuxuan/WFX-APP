"""Điều phối nhóm Finance: tra cứu và huỷ hoá đơn.

Supplier Inv List và Expense Inv List dùng chung id grid trên WFX, nên mọi
thao tác phải đi qua lớp nhận diện context của ``automation.modules`` —
tuyệt đối không Search hay Cancel trên màn của module kia."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import constants


class FinanceController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel
        # Token hoá dòng Supplier Invoice khi Invoice No. có nhiều kết quả.
        self.supplier_invoice_choices: dict[str, dict[str, str]] = {}

    def search_supplier_invoice(
        self,
        supplier: str = "",
        invoice_no: str = "",
        po_no: str = "",
        asn_grn_no: str = "",
    ) -> dict:
        panel = self._panel
        supplier_invoice = constants.MODULE_BY_ID["0065_0880_0020_0020"]
        values = {
            "supplier": str(supplier or "").strip(),
            "invoice_no": str(invoice_no or "").strip(),
            "po_no": str(po_no or "").strip(),
            "asn_grn_no": str(asn_grn_no or "").strip(),
        }
        return panel._run(
            "search_supplier_invoice",
            lambda: panel._login.search_supplier_invoice_list(
                supplier_invoice["xpath"],
                values["supplier"],
                values["invoice_no"],
                values["po_no"],
                values["asn_grn_no"],
                panel._log,
            ),
            {
                "module_id": "0065_0880_0020_0020",
                "filter_kinds": [
                    name for name, value in values.items() if value
                ],
            },
        )

    def search_advance_pr(
        self,
        buyer: str = "",
        supplier: str = "",
        invoice_no: str = "",
        order_no: str = "",
    ) -> dict:
        panel = self._panel
        advance_pr = constants.MODULE_BY_ID["0065_0880_0010_0020"]
        values = {
            "buyer": str(buyer or "").strip(),
            "supplier": str(supplier or "").strip(),
            "invoice_no": str(invoice_no or "").strip(),
            "order_no": str(order_no or "").strip(),
        }
        return panel._run(
            "search_advance_pr",
            lambda: panel._login.search_advance_pr_list(
                advance_pr["xpath"],
                values["buyer"],
                values["supplier"],
                values["invoice_no"],
                values["order_no"],
                panel._log,
            ),
            {
                "module_id": "0065_0880_0010_0020",
                "filter_kinds": [
                    name for name, value in values.items() if value
                ],
            },
        )

    def search_expense_invoice(
        self,
        supplier: str = "",
        invoice_no: str = "",
        created_by: str = "",
        status: str = "",
    ) -> dict:
        panel = self._panel
        expense_invoice = constants.MODULE_BY_ID["0065_0880_0030_0020"]
        values = {
            "supplier": str(supplier or "").strip(),
            "invoice_no": str(invoice_no or "").strip(),
            "created_by": str(created_by or "").strip(),
            "status": str(status or "").strip(),
        }
        return panel._run(
            "search_expense_invoice",
            lambda: panel._login.search_expense_invoice_list(
                expense_invoice["xpath"],
                values["supplier"],
                values["invoice_no"],
                values["created_by"],
                values["status"],
                panel._log,
            ),
            {
                "module_id": "0065_0880_0030_0020",
                "filter_kinds": [
                    name for name, value in values.items() if value
                ],
            },
        )

    def cancel_supplier_invoice(self, invoice_no: str) -> dict:
        panel = self._panel
        cleaned_invoice = str(invoice_no or "").strip()
        supplier_invoice = constants.MODULE_BY_ID["0065_0880_0020_0020"]

        def action() -> dict:
            self.supplier_invoice_choices.clear()
            result = panel._login.prepare_supplier_invoice_cancel(
                supplier_invoice["xpath"],
                cleaned_invoice,
                panel._log,
            )
            if result.get("code") != "SUPPLIER_INVOICE_MULTIPLE_RESULTS":
                return result
            public_invoices: list[dict[str, str]] = []
            for raw in result.get("invoices") or []:
                if not isinstance(raw, dict):
                    continue
                row_key = str(raw.get("row_key") or "").strip()
                invoice = str(raw.get("invoice_no") or "").strip()
                status = str(raw.get("status") or "").strip()
                if not row_key or not invoice or not status:
                    continue
                choice_id = secrets.token_urlsafe(18)
                self.supplier_invoice_choices[choice_id] = {
                    "row_key": row_key,
                    "invoice_no": invoice,
                    "status": status,
                }
                public_invoices.append(
                    {
                        "choice_id": choice_id,
                        "invoice_no": invoice,
                        "supplier": str(raw.get("supplier") or ""),
                        "po_no": str(raw.get("po_no") or ""),
                        "asn_grn_no": str(raw.get("asn_grn_no") or ""),
                        "status": status,
                    }
                )
            if not public_invoices:
                return {
                    "ok": False,
                    "code": "SUPPLIER_INVOICE_RESULT_EXPIRED",
                    "message": "Không đọc được dòng Supplier Invoice để chọn an toàn.",
                }
            return {
                **result,
                "invoices": public_invoices,
                "exact_match": bool(result.get("exact_match")),
            }

        return panel._run(
            "cancel_supplier_invoice",
            action,
            {"filter_kind": "invoice_no"},
        )

    def cancel_supplier_invoice_choice(self, choice_id: str) -> dict:
        panel = self._panel
        token = str(choice_id or "").strip()

        def action() -> dict:
            choice = self.supplier_invoice_choices.get(token)
            if choice is None:
                return {
                    "ok": False,
                    "code": "SUPPLIER_INVOICE_RESULT_EXPIRED",
                    "message": (
                        "Lựa chọn Supplier Invoice đã hết hiệu lực; "
                        "hãy tìm lại trước khi Cancel."
                    ),
                }
            return panel._login.cancel_supplier_invoice_choice(
                choice["row_key"],
                choice["invoice_no"],
                choice["status"],
                panel._log,
            )

        return panel._run(
            "cancel_supplier_invoice_choice",
            action,
            {"choice_id": token},
        )
