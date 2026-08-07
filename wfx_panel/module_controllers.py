"""Controller riêng cho từng module WFX.

UI chỉ biết module id và metadata. Mọi hành vi mở module nằm trong các lớp ở
đây để sau này mỗi màn hình có thể thêm workflow riêng mà không làm PanelAPI
thành một khối if/else lớn.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from wfx_panel import constants


@dataclass(frozen=True)
class ModuleController:
    module_id: ClassVar[str]
    kind: ClassVar[str] = "generic"
    description: ClassVar[str] = "Mở màn hình WFX trong trình duyệt làm việc."

    @property
    def spec(self) -> dict[str, Any]:
        return constants.MODULE_BY_ID[self.module_id]

    def open(self, login_module: Any, log: Callable[[str], None]) -> dict:
        return login_module.open_module(
            self.spec["name"], self.spec["xpath"], log
        )

    def manifest(self) -> dict[str, Any]:
        return {
            **self.spec,
            "kind": self.kind,
            "description": self.description,
        }


class CatalogModule(ModuleController):
    module_id = "0003_6200"
    kind = "catalog"
    description = "Quản lý Style, làm và tra cứu Costing, BOM."


class OCListModule(ModuleController):
    module_id = "0004_0050_0020"
    kind = "oc"
    description = "Quản lý, tạo mới và điều chỉnh đơn đặt hàng OC."


class SampleListModule(ModuleController):
    module_id = "0004_0056_4070"
    kind = "sample"
    description = "Quản lý và tạo mới đơn hàng mẫu."

    def open(self, login_module: Any, log: Callable[[str], None]) -> dict:
        opener = getattr(login_module, "open_module_with_floating_filter", None)
        if callable(opener):
            return opener(self.spec["name"], self.spec["xpath"], log)
        return super().open(login_module, log)


class SaleASNModule(ModuleController):
    module_id = "0004_0070_0020"
    kind = "sale_asn"
    description = "Tạo và tra cứu thông báo giao hàng Sale ASN."

    def open(self, login_module: Any, log: Callable[[str], None]) -> dict:
        opener = getattr(login_module, "open_module_with_floating_filter", None)
        if callable(opener):
            return opener(self.spec["name"], self.spec["xpath"], log)
        return super().open(login_module, log)


class GDNDispatchModule(ModuleController):
    module_id = "gdn_dispatch"
    kind = "gdn_dispatch"
    description = "Tạo phiếu xuất kho GDN từ Invoice GRN."


class GRNReceiptModule(ModuleController):
    module_id = "grn_receipt"
    kind = "grn_receipt"
    description = "Nhập kho nguyên phụ liệu từ RMPO và tra cứu GRN."


class RMPOListModule(ModuleController):
    module_id = "0005_0050_0020"
    kind = "rmpo"
    description = "Quản lý đơn mua nguyên phụ liệu và theo dõi nhập kho."


class IndentListModule(ModuleController):
    module_id = "0005_0080_0020"
    kind = "indent"
    description = "Quản lý yêu cầu cấp nguyên phụ liệu."


class UserIndentModule(ModuleController):
    module_id = "user_indent_list"
    kind = "indent"
    description = "Tra cứu yêu cầu cấp nguyên phụ liệu của người dùng."


class QAListModule(ModuleController):
    module_id = "0063_0030_0020"
    kind = "list_new"
    description = "Quản lý và tạo yêu cầu kiểm tra chất lượng."


class AdvancePRListModule(ModuleController):
    module_id = "0065_0880_0010_0020"
    kind = "advance_pr"
    description = "Quản lý và tạo đề nghị thanh toán tạm ứng."


class SupplierInvoiceListModule(ModuleController):
    module_id = "0065_0880_0020_0020"
    kind = "supplier_invoice"
    description = "Quản lý, tra cứu và hủy hóa đơn nhà cung cấp."


class ExpenseInvoiceListModule(ModuleController):
    module_id = "0065_0880_0030_0020"
    kind = "expense_invoice"
    description = "Quản lý và tạo hóa đơn chi phí."


class ReportsModule(ModuleController):
    module_id = "reports"
    kind = "reports"
    description = "Tải báo cáo WFX với tham số đã chọn."


class OrgStructureModule(ModuleController):
    module_id = "0090_0001"
    description = "Quản lý cơ cấu tổ chức."


class SystemCodingModule(ModuleController):
    module_id = "0090_0250"
    description = "Quản lý mã dùng trong hệ thống."


class CompanySetupModule(ModuleController):
    module_id = "0090_0007"
    kind = "company_setup"
    description = "Quản lý thiết lập công ty và nơi áp dụng FOC."


class BuyerListModule(ModuleController):
    module_id = "0004_0010_1720"
    kind = "buyer"
    description = "Quản lý và tra cứu khách hàng."


class SupplierListModule(ModuleController):
    module_id = "0005_0010_1290"
    kind = "supplier"
    description = "Quản lý và tra cứu nhà cung cấp."


CONTROLLER_TYPES = (
    CatalogModule,
    OCListModule,
    SampleListModule,
    SaleASNModule,
    GDNDispatchModule,
    GRNReceiptModule,
    RMPOListModule,
    IndentListModule,
    UserIndentModule,
    QAListModule,
    AdvancePRListModule,
    SupplierInvoiceListModule,
    ExpenseInvoiceListModule,
    ReportsModule,
    OrgStructureModule,
    SystemCodingModule,
    CompanySetupModule,
    BuyerListModule,
    SupplierListModule,
)

CONTROLLERS = {
    controller.module_id: controller() for controller in CONTROLLER_TYPES
}


def get(module_id: str) -> ModuleController | None:
    return CONTROLLERS.get(module_id)


def manifest_groups() -> list[dict[str, Any]]:
    return [
        {
            "name": group["name"],
            "accent": group["accent"],
            "modules": [
                CONTROLLERS[module["id"]].manifest()
                for module in group["modules"]
            ],
        }
        for group in constants.MODULE_GROUPS
    ]
