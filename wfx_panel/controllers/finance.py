"""Điều phối nhóm Finance: tra cứu và huỷ hoá đơn.

Supplier Inv List và Expense Inv List dùng chung id grid trên WFX, nên mọi
thao tác phải đi qua lớp nhận diện context của ``automation.modules`` —
tuyệt đối không Search hay Cancel trên màn của module kia."""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import constants
from wfx_panel.automation.expense_invoice import fill_expense_invoice
from wfx_panel.workbooks.expense_invoice import (
    ExpenseWorkbookError,
    load_seed_options,
    read_expense_workbook,
)


class FinanceController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel
        # Token hoá dòng Supplier Invoice khi Invoice No. có nhiều kết quả.
        self.supplier_invoice_choices: dict[str, dict[str, str]] = {}
        self.expense_reviews: dict[str, dict] = {}
        self._expense_lock = threading.Lock()

    def _expense_context(self) -> tuple:
        account = self._panel._account()
        return (str(account.get("user_id") or ""), self._panel._current_division)

    def review_expense_import(self, file_path: str) -> dict:
        # Local validation không giữ automation worker/Chrome.
        with self._expense_lock:
            self.expense_reviews.clear()
            try:
                source = Path(str(file_path or ""))
                data = read_expense_workbook(source)
            except ExpenseWorkbookError as error:
                return {"ok": False, "code": "EXPENSE_FILE_INVALID", "message": str(error)}
            token = secrets.token_urlsafe(24)
            self.expense_reviews[token] = {
                "created": time.monotonic(), "data": data,
                "context": self._expense_context(),
            }
        return {
            "ok": True, "code": "EXPENSE_REVIEW_READY",
            "message": "File hợp lệ. Bấm Điền trên WFX để chuẩn bị hóa đơn.",
            "review_token": token, "file_name": source.name,
            "supplier": data["header"]["supplier"], "invoice_no": data["header"]["invoice_no"],
            "row_count": len(data["lines"]), "total": data["total"],
            "currency": data["header"]["currency"],
        }

    def _expense_cache_path(self) -> Path:
        return self._panel._base_dir / "expense-options.json"

    def _save_expense_options(self, options: object) -> None:
        if not isinstance(options, dict) or not options:
            return
        try:
            self._expense_cache_path().write_text(json.dumps({"context": list(self._expense_context()), "options": options}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def expense_template_options(self) -> dict:
        """Dropdown cho mẫu, không chạm Chrome và không cần chọn Supplier.

        Ưu tiên danh sách thật của đúng tài khoản/Division (đọc lại sau mỗi lượt
        điền thành công), chưa có thì dùng bộ dữ liệu ban đầu đóng gói kèm app."""
        try:
            cached = json.loads(self._expense_cache_path().read_text(encoding="utf-8"))
            if cached.get("context") == list(self._expense_context()) and cached.get("options"):
                return {"ok": True, "code": "EXPENSE_OPTIONS_CACHED", "options": cached["options"]}
        except (OSError, ValueError, AttributeError):
            pass
        options = load_seed_options()
        if options:
            return {"ok": True, "code": "EXPENSE_OPTIONS_SEED", "options": options}
        return {"ok": True, "code": "EXPENSE_OPTIONS_UNAVAILABLE", "options": {}, "message": "Mẫu chưa có dropdown; hãy nhập đúng tên như trên WFX."}

    def clear_expense_import(self, review_token: str) -> dict:
        with self._expense_lock:
            self.expense_reviews.pop(str(review_token or ""), None)
        return {"ok": True, "code": "EXPENSE_REVIEW_CLEARED", "message": "Đã bỏ file nhập Expense Invoice."}

    def fill_expense_import(self, review_token: str) -> dict:
        review = None
        loaded = False

        def action() -> dict:
            nonlocal review, loaded
            if not loaded:
                with self._expense_lock:
                    review = self.expense_reviews.pop(str(review_token or ""), None)
                loaded = True
            if (review is None or time.monotonic() - review["created"] > 1800
                    or review["context"] != self._expense_context()):
                return {"ok": False, "code": "EXPENSE_REVIEW_EXPIRED", "message": "File đã hết hiệu lực hoặc tài khoản/Division đã đổi; hãy chọn lại file."}
            result = fill_expense_invoice(review["data"], self._panel._log)
            # Danh sách dropdown chỉ để làm mới cache, không gửi sang UI/lịch sử.
            self._save_expense_options(result.pop("options", None))
            return result
        return self._panel._run("fill_expense_import", action, {"module_id": "0065_0880_0030_0020"})

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
