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
    description = "Tìm Style · Season · Costing/BOM."


class OCListModule(ModuleController):
    module_id = "0004_0050_0020"
    kind = "oc"
    description = "Mở/tìm OC List, tạo Upload OC New hoặc Revise OC."


class SampleListModule(ModuleController):
    module_id = "0004_0056_4070"
    kind = "sample"
    description = "Mở Sample List, tìm Sample hoặc tạo Sample Order mới."

    def open(self, login_module: Any, log: Callable[[str], None]) -> dict:
        opener = getattr(login_module, "open_module_with_floating_filter", None)
        if callable(opener):
            return opener(self.spec["name"], self.spec["xpath"], log)
        return super().open(login_module, log)


class SaleASNModule(ModuleController):
    module_id = "0004_0070_0020"
    kind = "sale_asn"
    description = "Tìm Sale ASN, tải bộ Documents Excel hoặc tạo ASN mới."

    def open(self, login_module: Any, log: Callable[[str], None]) -> dict:
        opener = getattr(login_module, "open_module_with_floating_filter", None)
        if callable(opener):
            return opener(self.spec["name"], self.spec["xpath"], log)
        return super().open(login_module, log)


class RMPOListModule(ModuleController):
    module_id = "0005_0050_0020"
    kind = "rmpo"
    description = "Mở RMPO List hoặc lọc kết hợp theo Supplier và RMPO No."


class IndentListModule(ModuleController):
    module_id = "0005_0080_0020"
    kind = "indent"
    description = "Mở Indent List hoặc lọc kết hợp theo 4 điều kiện."


class UserIndentModule(ModuleController):
    module_id = "user_indent_list"
    kind = "indent"
    description = "Mở User Indent List hoặc lọc kết hợp theo 4 điều kiện."


class QAListModule(ModuleController):
    module_id = "0063_0030_0020"
    kind = "list_new"
    description = "Mở QA List hoặc tạo QA Request mới."


class AdvancePRListModule(ModuleController):
    module_id = "0065_0880_0010_0020"
    kind = "list_new"
    description = "Mở danh sách Advance PR hoặc tạo yêu cầu mới."


class SupplierInvoiceListModule(ModuleController):
    module_id = "0065_0880_0020_0020"
    description = "Mở danh sách hóa đơn nhà cung cấp."


class ExpenseInvoiceListModule(ModuleController):
    module_id = "0065_0880_0030_0020"
    kind = "list_new"
    description = "Mở danh sách Expense Invoice hoặc tạo hóa đơn mới."


class OrgStructureModule(ModuleController):
    module_id = "0090_0001"
    description = "Mở cấu trúc tổ chức."


class SystemCodingModule(ModuleController):
    module_id = "0090_0250"
    description = "Mở cấu hình mã hệ thống."


class CompanySetupModule(ModuleController):
    module_id = "0090_0007"
    kind = "company_setup"
    description = "Mở thiết lập công ty hoặc đổi nơi áp dụng FOC."


class BuyerListModule(ModuleController):
    module_id = "0004_0010_1720"
    kind = "buyer"
    description = "Mở Buyers List hoặc tìm và mở Buyer đầu tiên phù hợp."


class SupplierListModule(ModuleController):
    module_id = "0005_0010_1290"
    kind = "supplier"
    description = "Mở Supplier theo Category hoặc tìm Supplier trên mọi Category."


CONTROLLER_TYPES = (
    CatalogModule,
    OCListModule,
    SampleListModule,
    SaleASNModule,
    RMPOListModule,
    IndentListModule,
    UserIndentModule,
    QAListModule,
    AdvancePRListModule,
    SupplierInvoiceListModule,
    ExpenseInvoiceListModule,
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
