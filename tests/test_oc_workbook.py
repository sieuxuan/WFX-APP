from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from wfx_panel.oc_workbook import (
    EDI_HEADERS,
    INPUT_HEADERS,
    OCWorkbookError,
    prepare_oc_workbook,
    write_oc_input_template,
)


def _input_row(**overrides):
    values = {
        "Buyer": "J.LINDEBERG",
        "Season": "SS26",
        "Order Type": "Confirmed",
        "Currency": "USD",
        "Factory": "888 COMPANY LTD",
        "Ship Under PO Ref": "PO-SS26-01",
        "Article Code": "SWV0004581",
        "Buyer Style Ref": "GMPA17697",
        "Buyer PO Num": "PO-SS26-01",
        "Summary Buyer Order Ref": "PO-SS26-01",
        "Buyer Order Date": "08-10-2025",
        "Buyer Delivery Date": "31-12-2025",
        "Raw Material ETA Date": "05-12-2025",
        "Payment Terms": "TT After Shipment 60 Days",
        "Country of Final Destination": "Sweden",
        "Color Code": "O127",
        "Color Name": "Forget-Me-Not",
        "Size Code": "M",
        "Selling Price": 23.65,
        "Units": 9,
        "Internal Lot No.": "1",
        "PO Type (Zone)": "FOB",
        "Extra Production %": 0,
        "Buyer Lot No.": "RAB",
    }
    values.update(overrides)
    return [values[header] for header in INPUT_HEADERS]


def _filled_input_file(tmp_path: Path, *rows: list[object]) -> Path:
    path = write_oc_input_template(tmp_path / "input.xlsx")
    workbook = load_workbook(path)
    sheet = workbook["OC INPUT"]
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def test_generated_template_has_one_visible_header_and_hidden_references(tmp_path):
    path = write_oc_input_template(tmp_path / "WFX-Smart-Upload-OC.xlsx")

    workbook = load_workbook(path)
    assert workbook.sheetnames == ["OC INPUT", "REFERENCES"]
    assert workbook["REFERENCES"].sheet_state == "veryHidden"
    sheet = workbook["OC INPUT"]
    assert [cell.value for cell in sheet[1]] == list(INPUT_HEADERS)
    assert sheet.freeze_panes == "A2"
    assert len(sheet.data_validations.dataValidation) == 6
    validations = {
        next(iter(validation.sqref.ranges)).min_col: validation
        for validation in sheet.data_validations.dataValidation
    }
    assert validations[1].errorStyle == "warning"
    assert validations[5].errorStyle == "warning"
    assert validations[15].errorStyle is None
    assert sheet["A1"].comment.text.startswith("Chọn Buyer")
    assert sheet["X1"].fill.fgColor.rgb == "00F4B183"
    workbook.close()


def test_new_input_is_mapped_to_value_only_edi_and_total_qty(tmp_path):
    source = _filled_input_file(
        tmp_path,
        _input_row(Units=9, **{"Size Code": "M"}),
        _input_row(Units=6, **{"Size Code": "L"}),
    )
    output = tmp_path / "edi.xlsx"

    prepared = prepare_oc_workbook(source, "new", output)

    assert prepared.buyer == "J.LINDEBERG"
    assert prepared.row_count == 2
    assert prepared.seasons == ("SS26",)
    assert prepared.po_count == 1
    assert prepared.style_count == 1
    assert prepared.total_units == 15
    workbook = load_workbook(output, data_only=False)
    assert workbook.sheetnames == ["Sheet1"]
    sheet = workbook["Sheet1"]
    assert [cell.value for cell in sheet[1]] == list(EDI_HEADERS)
    indexes = {header: index + 1 for index, header in enumerate(EDI_HEADERS)}
    assert sheet.cell(2, indexes["Color"]).value == "O127^Forget-Me-Not"
    assert sheet.cell(2, indexes["Market"]).value == "Europe"
    assert sheet.cell(2, indexes["Total Qty"]).value == 15
    assert sheet.cell(3, indexes["Total Qty"]).value == 15
    assert sheet.cell(2, indexes["Buyer Order Date"]).value.date() == date(2025, 10, 8)
    assert all(cell.data_type != "f" for row in sheet.iter_rows() for cell in row)
    workbook.close()


def test_new_input_rejects_more_than_one_buyer(tmp_path):
    source = _filled_input_file(
        tmp_path,
        _input_row(),
        _input_row(
            Buyer="PUMA",
            **{"Buyer PO Num": "PO-2", "Summary Buyer Order Ref": "PO-2"},
        ),
    )

    with pytest.raises(OCWorkbookError) as caught:
        prepare_oc_workbook(source, "new", tmp_path / "edi.xlsx")

    assert caught.value.code == "OC_FILE_VALIDATION_FAILED"
    assert any("nhiều Buyer" in error for error in caught.value.errors)


def test_new_input_allows_new_wfx_buyer_and_factory_with_warning(tmp_path):
    source = _filled_input_file(
        tmp_path,
        _input_row(Buyer="NEW LIVE BUYER", Factory="NEW LIVE FACTORY"),
    )

    prepared = prepare_oc_workbook(source, "new", tmp_path / "edi.xlsx")

    assert prepared.buyer == "NEW LIVE BUYER"
    assert prepared.warnings == (
        "Buyer 'NEW LIVE BUYER' chưa có trong danh sách gợi ý; app sẽ yêu cầu "
        "khớp chính xác trên WFX.",
        "Factory 'NEW LIVE FACTORY' chưa có trong danh sách gợi ý; WFX sẽ kiểm "
        "tra khi Process Package.",
    )


def test_new_input_rejects_formula_error_and_unknown_country(tmp_path):
    source = _filled_input_file(
        tmp_path,
        _input_row(
            **{
                "Color Name": "#VALUE!",
                "Country of Final Destination": "Atlantis",
            }
        ),
    )

    with pytest.raises(OCWorkbookError) as caught:
        prepare_oc_workbook(source, "new", tmp_path / "edi.xlsx")

    assert caught.value.code == "OC_FILE_VALIDATION_FAILED"
    assert any("#VALUE!" in error for error in caught.value.errors)


def test_new_input_rejects_live_formula_in_editable_sheet(tmp_path):
    source = _filled_input_file(tmp_path, _input_row())
    workbook = load_workbook(source)
    workbook["OC INPUT"]["T2"] = "=4+5"
    workbook.save(source)
    workbook.close()

    with pytest.raises(OCWorkbookError) as caught:
        prepare_oc_workbook(source, "new", tmp_path / "edi.xlsx")

    assert caught.value.code == "OC_FILE_FORMULA_ERROR"
    assert caught.value.errors == ("Ô có công thức: T2.",)


def _revise_file(tmp_path: Path) -> Path:
    path = tmp_path / "revise.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(list(EDI_HEADERS))
    base = dict.fromkeys(EDI_HEADERS)
    base.update(
        {
            "Factory": "888 COMPANY LTD",
            "Ship Under PO Ref": "PO-1",
            "Article": "SWV0004581",
            "Buyer": "J.LINDEBERG",
            "Currency": "USD",
            "Season": "SS26",
            "Country of Origin": "Vietnam",
            "Payment Terms": "TT After Shipment 60 Days",
            "Buyer PO Num": "PO-1",
            "Summary Buyer Order Ref": "PO-1",
            "Market Buyer Order Ref": "PO-1",
            "Destination Buyer Order Ref": "PO-1",
            "Delivery Buyer Order Ref": "PO-1",
            "Buyer Order Date": date(2025, 10, 8),
            "Order Type": "Confirmed",
            "Mode of Shipment": "AIR/SEA",
            "Buyer Delivery Date": date(2025, 12, 31),
            "OC Delivery Date": date(2025, 12, 31),
            "Raw Matetrial ETA": date(2025, 12, 5),
            "Country of Final Destination": "Sweden",
            "Final Destination": "Sweden",
            "Market": "Europe",
            "Buyer Style Ref.": "GMPA17697",
            "Color": "O127^Forget-Me-Not",
            "Size": "M",
            "Total Qty": 999,
            "Price": 23.65,
            "Units": 9,
            "Zone": "FOB",
            "Internal Lot No.": "1",
            "DeliveryOCID": "OC-DELIVERY-1",
            "Fulfillment Type": "Back Order",
            "Extra Production %": 0,
        }
    )
    sheet.append([base[header] for header in EDI_HEADERS])
    second = dict(base)
    second.update({"Size": "L", "Units": 6})
    sheet.append([second[header] for header in EDI_HEADERS])
    workbook.save(path)
    return path


def test_revise_recalculates_total_qty_and_keeps_delivery_id(tmp_path):
    source = _revise_file(tmp_path)
    output = tmp_path / "revise-edi.xlsx"

    prepared = prepare_oc_workbook(source, "revise", output)

    assert prepared.row_count == 2
    assert prepared.seasons == ("SS26",)
    assert prepared.po_count == 1
    assert prepared.style_count == 1
    assert prepared.total_units == 15
    assert prepared.warnings == (
        "App đã tính lại Total Qty cho 2 dòng từ cột Units.",
    )
    workbook = load_workbook(output, data_only=True)
    sheet = workbook["Sheet1"]
    indexes = {header: index + 1 for index, header in enumerate(EDI_HEADERS)}
    assert sheet.cell(2, indexes["Total Qty"]).value == 15
    assert sheet.cell(3, indexes["Total Qty"]).value == 15
    assert sheet.cell(2, indexes["DeliveryOCID"]).value == "OC-DELIVERY-1"
    workbook.close()
