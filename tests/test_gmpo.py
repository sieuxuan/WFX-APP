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
            ("colbuyerorderref", "Buyer Order Ref", ""),
            ("colstyle", "Style", ""),
            ("colcolor", "Color", ""),
            ("cols", "S", "S"),
            ("colxl", "XL", "XL"),
        ]
    ]
    rows = [
        {
            "identity": ["220112050", color, "-1", "123"],
            "values": {
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


def test_quantity_import_matches_color_after_sort_and_supports_zero(gmpo):
    path, snapshot = gmpo
    assert read_changes(path) == ("test scope", [])
    book = load_workbook(path)
    sheet = book["GMPO"]
    rows = list(sheet.values)
    for target, values in enumerate(reversed(rows[1:]), 2):
        for index, value in enumerate(values, 1):
            sheet.cell(target, index).value = value
    sheet["F2"] = 0
    sheet["G3"] = None
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
    book["GMPO"]["F2"] = 100
    book["GMPO"]["F3"] = 146
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
    book["GMPO"]["F2"] = "=5+6"
    book.save(path)
    with pytest.raises(ValueError, match="Order Qty - S"):
        read_changes(path)
    book["GMPO"]["F2"] = 11
    book["GMPO"]["E2"] = "45092"
    book.save(path)
    with pytest.raises(ValueError, match="nhận diện"):
        read_changes(path)
