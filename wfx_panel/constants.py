from __future__ import annotations

CATEGORIES = {
    "Apparel": "01",
    "Fixed Asset": "04",
    "Miscellaneous": "12",
    "Services": "06",
    "Textiles/Fabric": "03",
    "Trims": "05",
}

SALE_ASN_NEW_XPATH = '//*[@id="0004_0070_4340"]/a'
SAMPLE_NEW_XPATH = (
    '//a[@title="New Sample Order" '
    'and contains(@href,"mnuSWNNewSampling")]'
)
USER_INDENT_XPATH = (
    '//a[@title="User Indent List" '
    'and contains(@href,"mnuIndentControlUserList")]'
)
GDN_DISPATCH_XPATH = '//*[@id="0040_0020_0100"]/a'
GRN_RECEIPT_XPATH = '//*[@id="0050_0020_0380"]/a'

DIVISIONS = {
    "woven": {
        "key": "woven",
        "label": "WOVEN",
        "name": "PRO SPORTS - WOVEN HANOI",
        "member_company_code": "77400",
        "folder_id": "7740001",
    },
    "knit": {
        "key": "knit",
        "label": "KNIT",
        "name": "PRO SPORTS - KNIT HANOI",
        "member_company_code": "77400",
        "folder_id": "7740002",
    },
    "pssg": {
        "key": "pssg",
        "label": "PSSG",
        "name": "Pro Sports - Singapore",
        "member_company_code": "78307",
        "folder_id": "774001040",
    },
}

MODULE_GROUPS = [
    {
        "name": "Operation",
        "accent": "cyan",
        "modules": [
            {"name": "Catalog", "id": "0003_6200", "icon": "CA"},
            {"name": "OC List", "id": "0004_0050_0020", "icon": "OC"},
            {"name": "Sample Order", "id": "0004_0056_4070", "icon": "SL"},
            {"name": "Sale ASN", "id": "0004_0070_0020", "icon": "AS"},
            {
                "name": "(GDN) Dispatch",
                "id": "gdn_dispatch",
                "icon": "GD",
                "xpath": GDN_DISPATCH_XPATH,
            },
            {
                "name": "(GRN) Nhập kho",
                "id": "grn_receipt",
                "icon": "GR",
                "xpath": GRN_RECEIPT_XPATH,
            },
            {"name": "RMPO List", "id": "0005_0050_0020", "icon": "RM"},
            {"name": "Indent List", "id": "0005_0080_0020", "icon": "IN"},
            {
                "name": "User Indent",
                "id": "user_indent_list",
                "icon": "UI",
                "xpath": USER_INDENT_XPATH,
            },
            {"name": "QA List", "id": "0063_0030_0020", "icon": "QA"},
        ],
    },
    {
        "name": "Finance",
        "accent": "violet",
        "modules": [
            {"name": "Advance PR", "id": "0065_0880_0010_0020", "icon": "PR"},
            {"name": "Supplier Inv", "id": "0065_0880_0020_0020", "icon": "SI"},
            {"name": "Expense Inv", "id": "0065_0880_0030_0020", "icon": "EI"},
        ],
    },
    {
        "name": "Reports",
        "accent": "cyan",
        "modules": [
            {"name": "Reports", "id": "reports", "icon": "RP"},
        ],
    },
    {
        "name": "Admin",
        "accent": "amber",
        "modules": [
            {"name": "Org Structure", "id": "0090_0001", "icon": "OR"},
            {"name": "System Coding", "id": "0090_0250", "icon": "SC"},
            {"name": "Company Setup", "id": "0090_0007", "icon": "CO"},
            {"name": "Buyer List", "id": "0004_0010_1720", "icon": "BU"},
            {"name": "Supplier List", "id": "0005_0010_1290", "icon": "SU"},
        ],
    },
]


def xpath_for(module_id: str) -> str:
    return f'//*[@id="{module_id}"]/a'


MODULE_BY_ID = {
    module["id"]: {
        **module,
        "group": group["name"],
        "accent": group["accent"],
        "xpath": module.get("xpath") or xpath_for(module["id"]),
    }
    for group in MODULE_GROUPS
    for module in group["modules"]
}

ADMIN_MODULE_IDS = frozenset(
    module["id"]
    for group in MODULE_GROUPS
    if group["name"] == "Admin"
    for module in group["modules"]
)

ADMIN_MODULE_SPECS = [
    {
        "id": module_id,
        "name": MODULE_BY_ID[module_id]["name"],
        "xpath": MODULE_BY_ID[module_id]["xpath"],
    }
    for module_id in ADMIN_MODULE_IDS
]
