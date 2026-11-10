from decimal import Decimal

import pytest
from openpyxl import load_workbook

from wfx_panel.automation.gmpo import GMPOError, _plan_edits
from wfx_panel.workbooks.gmpo import read_changes, write_workbook


@pytest.fixture
def gmpo(tmp_path):
    columns = [
        {"id": key, "label": label, "size": size}
        for key, label, size in [
            ("colgmpono", "GMPO No.", ""),
            ("colbuyerorderref", "Buyer Order Ref", ""),
            ("colcostprofitcenter", "Cost Center", ""),
            ("colstyle", "Style", ""),
            ("colpackingcodesku", "Packing Code SKU", ""),
            ("colpackingtype", "Packing Type", ""),
            ("colpackingoption", "Packing Option", ""),
            ("colcolor", "Color", ""),
            ("colprepack", "PP", ""),
            ("colcarton", "Carton", ""),
            ("cols", "S", "S"),
            ("colxl", "XL", "XL"),
            ("coltotalqty", "Total Qty", ""),
            ("colprice", "Price", ""),
            ("coltotalvalue", "Total Value", ""),
            ("colocdeliverydate", "OC Delivery Date", ""),
            ("coltaxamount", "Tax Amt", ""),
        ]
    ]
    rows = [
        {
            "identity": ["220112050", color, "-1", "123"],
            "total_qty": str((s + xl) * 2),
            "qty_factor": 2,
            "values": {
                **dict.fromkeys((column["id"] for column in columns), ""),
                "colbuyerorderref": "PO 20549",
                "colstyle": "0017",
                "colcolor": color,
                "cols": str(s),
                "colxl": str(xl),
            },
            "qty": {
                size: {
                    "value": str(value),
                    "max": str(value),
                    "decimals": 0,
                    "editable": True,
                }
                for size, value in [("S", s), ("XL", xl)]
            },
        }
        for color, s, xl in [("37566", 113, 199), ("45092", 145, 340)]
    ]
    snapshot = {"scope": "test scope", "kit": False, "rows": rows, "columns": columns}
    path = tmp_path / "GMPO.xlsx"
    write_workbook(path, snapshot)
    return path, snapshot


def test_compact_export_ends_at_total_value_and_has_quantity_formula(gmpo):
    path, _snapshot = gmpo
    sheet = load_workbook(path)["GMPO"]
    assert [cell.value for cell in sheet[1]] == [
        "Mã dòng",
        "Buyer Order Ref",
        "Style",
        "Color",
        "Order Qty - S",
        "Order Qty - XL",
        "Total Qty",
        "Price",
        "Total Value",
    ]
    assert sheet.column_dimensions["A"].hidden
    assert (
        sheet["G2"].value
        == '=ROUND(624+2*SUM(IF(E2="",0,E2-113),IF(F2="",0,F2-199)),4)'
    )


def test_import_accepts_legacy_order_id_column(gmpo):
    path, _snapshot = gmpo
    book = load_workbook(path)
    sheet = book["GMPO"]
    sheet.insert_cols(1)
    sheet["A1"] = "Order ID"
    sheet["A2"] = sheet["A3"] = "220112050"
    sheet["F2"] = 112
    book.save(path)
    _scope, changes = read_changes(path)
    assert [(item["size"], item["value"]) for item in changes] == [("S", Decimal(112))]


def test_quantity_import_matches_color_after_sort_and_supports_zero(gmpo):
    path, snapshot = gmpo
    assert read_changes(path) == ("test scope", [])
    book = load_workbook(path)
    sheet = book["GMPO"]
    rows = list(sheet.values)
    for target, values in enumerate(reversed(rows[1:]), 2):
        for index, value in enumerate(values, 1):
            sheet.cell(target, index).value = value
    sheet["E2"] = 0
    sheet["F3"] = None
    book.save(path)

    scope, changes = read_changes(path)
    plan = _plan_edits(snapshot, scope, changes)
    assert [(item["index"], item["size"], item["value"]) for item in plan] == [
        (1, "S", "0")
    ]
    assert changes[0]["before"] == Decimal(145)
    snapshot["rows"][1]["qty"]["S"]["value"] = "0"
    assert _plan_edits(snapshot, scope, changes) == []


def test_quantity_import_blocks_conflicts_before_filling(gmpo):
    path, snapshot = gmpo
    book = load_workbook(path)
    book["GMPO"]["E2"] = 100
    book["GMPO"]["E3"] = 146
    book.save(path)
    scope, changes = read_changes(path)
    with pytest.raises(GMPOError) as conflict:
        _plan_edits(snapshot, scope, changes)
    assert conflict.value.code == "GMPO_IMPORT_CONFLICT"

    snapshot["rows"][0]["qty"]["S"]["value"] = "112"
    with pytest.raises(GMPOError, match="đã đổi"):
        _plan_edits(snapshot, scope, changes[:1])
    with pytest.raises(GMPOError, match="GMPO khác"):
        _plan_edits(snapshot, "different document", changes)


def test_quantity_import_rejects_formula_and_partial_row_sort(gmpo):
    path, _snapshot = gmpo
    book = load_workbook(path)
    book["GMPO"]["E2"] = "=5+6"
    book.save(path)
    with pytest.raises(ValueError, match="Order Qty - S"):
        read_changes(path)
    book["GMPO"]["E2"] = 11
    book["GMPO"]["D2"] = "45092"
    book.save(path)
    with pytest.raises(ValueError, match="nhận diện"):
        read_changes(path)
