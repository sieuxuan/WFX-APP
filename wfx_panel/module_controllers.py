"""Controller riêng cho từng module WFX.

UI chỉ biết module id và metadata. Mọi hành vi mở module nằm trong các lớp ở
đây để sau này mỗi màn hình có thể thêm workflow riêng mà không làm PanelAPI
thành một khối if/else lớn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, ClassVar

from wfx_panel import constants


@dataclass(frozen=True)
class ModuleController:
    module_id: ClassVar[str]
    kind: ClassVar[str] = "generic"
    description: ClassVar[str] = "Mở màn hình WFX trong trình duyệt automation."

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
    description = "Tìm style, kiểm tra Season/CostSheet và mở BOM hoặc Costsheet."


class OCListModule(ModuleController):
    module_id = "0004_0050_0020"
    description = "Theo dõi và mở danh sách Order Confirmation."


class SampleListModule(ModuleController):
    module_id = "0004_0056_4070"
    description = "Tra cứu và thao tác danh sách sample."


class SaleASNModule(ModuleController):
    module_id = "0004_0070_0020"
    description = "Mở danh sách Sale ASN."


class RMPOListModule(ModuleController):
    module_id = "0005_0050_0020"
    description = "Theo dõi đơn mua nguyên phụ liệu."


class IndentListModule(ModuleController):
    module_id = "0005_0080_0020"
    description = "Mở danh sách Indent."


class QAListModule(ModuleController):
    module_id = "0063_0030_0020"
    description = "Mở danh sách kiểm tra chất lượng."


class AdvancePRListModule(ModuleController):
    module_id = "0065_0880_0010_0020"
    description = "Mở danh sách Advance PR."


class SupplierInvoiceListModule(ModuleController):
    module_id = "0065_0880_0020_0020"
    description = "Mở danh sách hóa đơn nhà cung cấp."


class ExpenseInvoiceListModule(ModuleController):
    module_id = "0065_0880_0030_0020"
    description = "Mở danh sách hóa đơn chi phí."


class OrgStructureModule(ModuleController):
    module_id = "0090_0001"
    description = "Mở cấu trúc tổ chức."


class SystemCodingModule(ModuleController):
    module_id = "0090_0250"
    description = "Mở cấu hình mã hệ thống."


class CompanySetupModule(ModuleController):
    module_id = "0090_0007"
    description = "Mở thiết lập công ty."


class BuyerListModule(ModuleController):
    module_id = "0004_0010_1720"
    description = "Mở danh sách buyer."


class SupplierListModule(ModuleController):
    module_id = "0005_0010_1290"
    description = "Mở danh sách nhà cung cấp."


CONTROLLER_TYPES = (
    CatalogModule,
    OCListModule,
    SampleListModule,
    SaleASNModule,
    RMPOListModule,
    IndentListModule,
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
