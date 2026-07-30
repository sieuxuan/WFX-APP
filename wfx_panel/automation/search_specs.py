"""Khai báo filter của các module WFX, tách khỏi logic Playwright."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchFieldSpec:
    label: str
    selectors: tuple[str, ...]
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModuleSearchSpec:
    module_name: str
    fields: Mapping[str, SearchFieldSpec]
    context_field: SearchFieldSpec
    requires_floating_filter: bool = False
    field_selectors: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "field_selectors",
            tuple(
                dict.fromkeys(
                    selector
                    for field_spec in self.fields.values()
                    for selector in field_spec.selectors
                )
            )
        )


OC_SEARCH_SPEC = ModuleSearchSpec(
    module_name="OC List",
    fields={
        "oc_no": SearchFieldSpec(
            "OC No.",
            ("#txtOCNO", 'input[name="txtOCNO"]'),
            ("oc no", "proforma invoice num with order ref num"),
        ),
        "style": SearchFieldSpec(
            "Style",
            ("#txtArticle", 'input[name="txtArticle"]'),
            ("buyer style ref num", "style", "article"),
        ),
    },
    context_field=SearchFieldSpec(
        "OC No.",
        ("#txtOCNO", 'input[name="txtOCNO"]'),
        ("proforma invoice num with order ref num", "oc no"),
    ),
)

SAMPLE_SEARCH_SPEC = ModuleSearchSpec(
    module_name="Sample List",
    fields={
        "sample_no": SearchFieldSpec(
            "Sample Order No.",
            (
                "#txtSampleOrderNo",
                "#txtSampleNo",
                'input[aria-label*="Sample Order" i]',
                'input[id*="SampleOrder" i]',
            ),
            ("sample order no", "sample order number", "sample no"),
        ),
        "style": SearchFieldSpec(
            "Style",
            (
                "#txtArticle",
                'input[aria-label*="Style" i]',
                'input[id*="Style" i]',
                'input[id*="Article" i]',
            ),
            ("buyer style", "style", "article"),
        ),
        "created_by": SearchFieldSpec(
            "Created By",
            (
                'input[aria-label*="Created By" i]',
                'input[id*="CreatedBy" i]',
                'input[name*="CreatedBy" i]',
            ),
            ("created by", "createdby", "creator"),
        ),
    },
    context_field=SearchFieldSpec(
        "Sample Order No.",
        (
            "#txtSampleOrderNo",
            "#txtSampleNo",
            'input[aria-label*="Sample Order" i]',
            'input[id*="SampleOrder" i]',
        ),
        ("sample order no", "sample order number", "sample no"),
    ),
    requires_floating_filter=True,
)

SALE_ASN_BUYER_ORDER_FIELD = SearchFieldSpec(
    "Buyer Order Ref/OC No.",
    (
        'input[aria-label*="Buyer Order Ref/Oc Num" i]',
        'input[aria-label*="Buyer Order Ref" i]',
    ),
    ("buyer order ref oc num", "buyer order ref", "oc num"),
)
SALE_ASN_SEARCH_SPEC = ModuleSearchSpec(
    module_name="Sale ASN",
    fields={
        "invoice_no": SearchFieldSpec(
            "Invoice No.",
            (
                "#txtInvoiceNo",
                'input[aria-label*="Invoice" i]',
                'input[id*="Invoice" i]',
            ),
            ("invoice no", "invoice number", "invoice"),
        ),
        "buyer_order_ref": SALE_ASN_BUYER_ORDER_FIELD,
        # Tương thích job cũ trước khi UI đổi tên filter "Style".
        "style": SALE_ASN_BUYER_ORDER_FIELD,
    },
    context_field=SearchFieldSpec(
        "Invoice No.",
        (
            "#txtInvoiceNo",
            'input[aria-label*="Invoice" i]',
            'input[id*="Invoice" i]',
        ),
        ("invoice no", "invoice number", "invoice"),
    ),
    requires_floating_filter=True,
)

RMPO_SEARCH_SPEC = ModuleSearchSpec(
    module_name="RMPO List",
    fields={
        "supplier": SearchFieldSpec(
            "Supplier",
            (
                "#gridRMPO_tblGridHeader_trSearch_td_colSupplier "
                "input#txtSupplier",
            ),
        ),
        "order_no": SearchFieldSpec(
            "RMPO No.",
            (
                "#gridRMPO_tblGridHeader_trSearch_td_colOrderNo "
                "input#txtOrderNo",
            ),
        ),
    },
    context_field=SearchFieldSpec(
        "Supplier",
        ("#gridRMPO_tblGridHeader_trSearch_td_colSupplier",),
    ),
)

INDENT_SEARCH_FIELDS = {
    "supplier": SearchFieldSpec(
        "Supplier",
        (
            "#gridMOLList_tblGridHeader_trSearch_td_ColSupplier "
            "input#txtSupplier",
        ),
    ),
    "article": SearchFieldSpec(
        "Article",
        (
            "#gridMOLList_tblGridHeader_trSearch_td_ColArticle "
            "input#txtArticle",
        ),
    ),
    "indent_no": SearchFieldSpec(
        "Indent No.",
        (
            "#gridMOLList_tblGridHeader_trSearch_td_ColIndentNo "
            "input#txtIndentNo",
        ),
    ),
    "style": SearchFieldSpec(
        "Style",
        (
            "#gridMOLList_tblGridHeader_trSearch_td_ColStyle "
            "input#txtStyle",
        ),
    ),
}
INDENT_SEARCH_SPECS = {
    module_name: ModuleSearchSpec(
        module_name=module_name,
        fields=INDENT_SEARCH_FIELDS,
        context_field=SearchFieldSpec(
            "Indent No.",
            ("#gridMOLList_tblGridHeader_trSearch_td_ColIndentNo",),
        ),
    )
    for module_name in ("Indent List", "User Indent")
}
