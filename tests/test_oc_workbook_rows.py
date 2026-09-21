"""Đọc dòng OC INPUT và Revise: kế thừa giá trị, dòng Units = 0, và dòng trùng.

CLAUDE.md: với OC New, Buyer/Season/Order Type/Currency chỉ bắt buộc ở dòng dữ
liệu đầu tiên — dòng sau để trống phải kế thừa. Dòng `Units = 0` bị bỏ khỏi
Sheet1 và review; chỉ cặp PO No. + Style trùng hoàn toàn mới là lỗi.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from wfx_panel.workbooks.oc import (
    EDI_HEADERS,
    INPUT_HEADERS,
    OCWorkbookError,
    prepare_oc_workbook,
    write_oc_input_template,
)

INHERITED = ("Buyer", "Season", "Order Type", "Currency")


def _row(**overrides):
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


def _file(tmp_path: Path, *rows) -> Path:
    path = write_oc_input_template(tmp_path / "input.xlsx")
    workbook = load_workbook(path)
    sheet = workbook["OC INPUT"]
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def _prepare(tmp_path, *rows):
    return prepare_oc_workbook(
        _file(tmp_path, *rows), "new", tmp_path / "upload.xlsx"
    )


def _uploaded(prepared):
    workbook = load_workbook(prepared.upload_path)
    sheet = workbook["Sheet1"]
    index = {header: position for position, header in enumerate(EDI_HEADERS)}
    rows = [
        [cell.value for cell in row]
        for row in sheet.iter_rows(min_row=2, max_col=len(EDI_HEADERS))
    ]
    workbook.close()
    return index, rows


# --- kế thừa bốn cột đầu ------------------------------------------------


def test_the_four_shared_values_are_inherited_by_later_rows(tmp_path):
    later = _row(**dict.fromkeys(INHERITED))
    later[INPUT_HEADERS.index("Color Code")] = "O200"

    prepared = _prepare(tmp_path, _row(), later)

    index, rows = _uploaded(prepared)
    assert len(rows) == 2
    for header in INHERITED:
        assert rows[1][index[header]] == rows[0][index[header]]


def test_a_later_row_that_states_its_own_value_keeps_it(tmp_path):
    later = _row(Season="AW26")
    later[INPUT_HEADERS.index("Color Code")] = "O200"

    prepared = _prepare(tmp_path, _row(), later)

    index, rows = _uploaded(prepared)
    assert rows[0][index["Season"]] == "SS26"
    assert rows[1][index["Season"]] == "AW26"


def test_the_first_data_row_must_state_all_four(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare(tmp_path, _row(Buyer=None))

    assert error.value.code == "OC_FILE_VALIDATION_FAILED"
    assert any("Buyer" in item for item in error.value.errors)


# --- dòng Units = 0 -----------------------------------------------------


def test_a_zero_unit_row_is_dropped_from_the_upload(tmp_path):
    zero = _row(Units=0)
    zero[INPUT_HEADERS.index("Color Code")] = "O200"

    prepared = _prepare(tmp_path, _row(), zero)

    _index, rows = _uploaded(prepared)
    assert len(rows) == 1
    assert prepared.row_count == 1


def test_a_file_where_every_row_has_zero_units_is_refused(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare(tmp_path, _row(Units=0))

    assert error.value.code == "OC_FILE_EMPTY"


@pytest.mark.parametrize("units", [-1, 1.5])
def test_units_that_are_negative_or_fractional_are_still_errors(tmp_path, units):
    with pytest.raises(OCWorkbookError) as error:
        _prepare(tmp_path, _row(Units=units))

    assert any("Units" in item for item in error.value.errors)


# --- các trường bắt buộc ------------------------------------------------


def test_an_empty_sheet_is_reported_before_anything_else(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare(tmp_path)

    assert error.value.code == "OC_FILE_EMPTY"


def test_a_row_missing_several_required_columns_lists_the_first_five(tmp_path):
    empty = _row()
    for header in (
        "Factory",
        "Article Code",
        "Buyer Style Ref",
        "Color Code",
        "Color Name",
        "Size Code",
    ):
        empty[INPUT_HEADERS.index(header)] = None

    with pytest.raises(OCWorkbookError) as error:
        _prepare(tmp_path, empty)

    message = next(item for item in error.value.errors if "thiếu" in item)
    assert message.rstrip().endswith("…")


def test_a_selling_price_of_zero_is_refused(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare(tmp_path, _row(**{"Selling Price": 0}))

    assert any("Selling Price" in item for item in error.value.errors)


def test_a_negative_extra_production_is_refused(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare(tmp_path, _row(**{"Extra Production %": -1}))

    assert any("Extra Production" in item for item in error.value.errors)


def test_an_empty_extra_production_defaults_to_zero(tmp_path):
    prepared = _prepare(tmp_path, _row(**{"Extra Production %": None}))

    index, rows = _uploaded(prepared)
    assert str(rows[0][index["Extra Production %"]]) in {"0", "0.00"}


# --- dòng trùng ---------------------------------------------------------


def test_two_rows_identical_on_po_style_colour_and_size_are_refused(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare(tmp_path, _row(), _row())

    assert any("trùng" in item for item in error.value.errors)


def test_two_rows_differing_only_by_size_are_both_kept(tmp_path):
    other = _row()
    other[INPUT_HEADERS.index("Size Code")] = "L"

    prepared = _prepare(tmp_path, _row(), other)

    _index, rows = _uploaded(prepared)
    assert len(rows) == 2


# --- một Buyer mỗi file -------------------------------------------------


def test_a_file_with_two_buyers_is_refused(tmp_path):
    other = _row(Buyer="TRUEWERK")
    other[INPUT_HEADERS.index("Color Code")] = "O200"

    with pytest.raises(OCWorkbookError) as error:
        _prepare(tmp_path, _row(), other)

    assert any("nhiều Buyer" in item for item in error.value.errors) or (
        "nhiều Buyer" in error.value.message
    )


# --- Destination → Country + Market ------------------------------------


def test_a_country_without_a_market_mapping_is_reported(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare(
            tmp_path,
            _row(**{"Country of Final Destination": "Sao Hoa"}),
        )

    assert any("mapping Market" in item for item in error.value.errors)


def test_a_known_country_is_normalised_into_country_and_market(tmp_path):
    prepared = _prepare(tmp_path, _row())

    index, rows = _uploaded(prepared)
    assert rows[0][index["Country of Final Destination"]]
    assert rows[0][index["Market"]]


# --- tổng hợp review ----------------------------------------------------


def test_the_review_counts_distinct_pos_and_styles(tmp_path):
    second = _row()
    second[INPUT_HEADERS.index("Buyer Style Ref")] = "GMPA99999"
    second[INPUT_HEADERS.index("Article Code")] = "SWV0009999"
    third = _row()
    third[INPUT_HEADERS.index("Summary Buyer Order Ref")] = "PO-SS26-02"
    third[INPUT_HEADERS.index("Ship Under PO Ref")] = "PO-SS26-02"

    prepared = _prepare(tmp_path, _row(), second, third)

    assert prepared.row_count == 3
    assert prepared.po_count == 2
    assert prepared.style_count == 2
    assert prepared.total_units == 27
    assert prepared.buyer == "J.LINDEBERG"
    assert prepared.mode == "new"


# --- file Revise OC -----------------------------------------------------


def _revise_file(tmp_path, *rows, sheet_name="Sheet1", headers=None):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(list(headers if headers is not None else EDI_HEADERS))
    for row in rows:
        sheet.append(list(row))
    path = tmp_path / "revise.xlsx"
    workbook.save(path)
    workbook.close()
    return path


def _revise_row(**overrides):
    from datetime import date

    from wfx_panel.workbooks.oc.schema import (
        DATE_HEADERS,
        REVISE_REQUIRED_HEADERS,
    )

    values = dict.fromkeys(EDI_HEADERS, "")
    for header in REVISE_REQUIRED_HEADERS:
        values[header] = f"{header}-1"
    for header in DATE_HEADERS:
        values[header] = date(2026, 2, 1)
    values["Buyer"] = "J.LINDEBERG"
    values["Order Type"] = "Confirmed"
    values["Zone"] = "FOB"
    values["Buyer Order Date"] = date(2026, 1, 1)
    values["Raw Matetrial ETA"] = date(2026, 2, 1)
    values["Buyer Delivery Date"] = date(2026, 3, 1)
    values["OC Delivery Date"] = date(2026, 3, 1)
    values["Units"] = 9
    values["Price"] = 10
    values["Extra Production %"] = 0
    values.update(overrides)
    return [values[header] for header in EDI_HEADERS]


def _prepare_revise(tmp_path, *rows, **kwargs):
    return prepare_oc_workbook(
        _revise_file(tmp_path, *rows, **kwargs),
        "revise",
        tmp_path / "upload.xlsx",
    )


def test_a_revise_file_without_sheet1_is_reported(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(tmp_path, _revise_row(), sheet_name="KHAC")

    assert error.value.code == "OC_TEMPLATE_SHEET_MISSING"


def test_a_revise_file_with_no_data_row_is_reported(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(tmp_path)

    assert error.value.code == "OC_FILE_EMPTY"


def test_a_revise_file_with_wrong_headers_is_reported(tmp_path):
    headers = list(EDI_HEADERS)
    headers[2] = "Cot Sai"

    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(tmp_path, _revise_row(), headers=headers)

    assert error.value.code == "OC_FILE_HEADERS_INVALID"


def test_a_valid_revise_row_survives_into_the_upload(tmp_path):
    prepared = _prepare_revise(tmp_path, _revise_row())

    assert prepared.mode == "revise"
    assert prepared.row_count == 1
    assert prepared.buyer == "J.LINDEBERG"
    assert prepared.total_units == 9


def test_a_revise_row_with_zero_units_is_dropped(tmp_path):
    other = _revise_row(Units=0, Color="KHAC")

    prepared = _prepare_revise(tmp_path, _revise_row(), other)

    assert prepared.row_count == 1


def test_a_revise_file_where_everything_is_zero_units_is_refused(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(tmp_path, _revise_row(Units=0))

    assert error.value.code == "OC_FILE_EMPTY"


def test_a_revise_row_missing_a_required_column_is_reported(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(tmp_path, _revise_row(Factory=""))

    assert any("thiếu" in item for item in error.value.errors)


def test_two_revise_rows_with_the_same_identity_are_refused(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(tmp_path, _revise_row(), _revise_row())

    assert any("trùng" in item for item in error.value.errors)


def test_a_revise_file_with_two_buyers_is_refused(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(
            tmp_path,
            _revise_row(),
            _revise_row(Buyer="TRUEWERK", Color="KHAC"),
        )

    assert "nhiều Buyer" in " ".join(error.value.errors)


def test_a_revise_row_whose_delivery_dates_are_out_of_order_is_refused(tmp_path):
    from datetime import date

    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(
            tmp_path,
            _revise_row(**{"Raw Matetrial ETA": date(2025, 12, 1)}),
        )

    assert any("Buyer Order Date" in item for item in error.value.errors)


def test_a_revise_row_whose_oc_delivery_date_differs_is_refused(tmp_path):
    from datetime import date

    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(
            tmp_path, _revise_row(**{"OC Delivery Date": date(2026, 3, 2)})
        )

    assert any("OC Delivery Date" in item for item in error.value.errors)


def test_a_revise_row_with_a_bad_order_type_is_refused(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(tmp_path, _revise_row(**{"Order Type": "La Lam"}))

    assert any("Order Type" in item for item in error.value.errors)


# --- ràng buộc số của Revise -------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "marker"),
    [
        ({"Units": 1.5}, "Units"),
        ({"Price": 0}, "Price"),
        ({"Extra Production %": -1}, "Extra Production"),
    ],
)
def test_revise_numeric_rules_are_reported_per_row(tmp_path, overrides, marker):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_revise(tmp_path, _revise_row(**overrides))

    assert any(marker in item for item in error.value.errors)


# --- form UPLOAD FORM.xlsx cũ ------------------------------------------


def _legacy_file(tmp_path, *rows, metadata=None, reference=True):
    """Workbook FORM/THONG TIN như bản phát hành cũ, vẫn phải đọc được."""
    from openpyxl import Workbook

    from wfx_panel.workbooks.oc.schema import FORM_HEADERS

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "FORM"
    values = {
        "B1": "J.LINDEBERG",
        "B2": "SS26",
        "B3": "Confirmed",
        "B4": "USD",
    }
    values.update(metadata or {})
    for cell, value in values.items():
        sheet[cell] = value
    for column, header in enumerate(FORM_HEADERS, start=1):
        sheet.cell(5, column, header)
    for row in rows:
        sheet.append(list(row))
    if reference:
        info = workbook.create_sheet("THONG TIN")
        info.append(["Factory", "Buyer", "", "", "Destination", "Market"])
        info.append(
            ["888 COMPANY LTD", "J.LINDEBERG", "", "", "Sweden", "EUROPE"]
        )
    path = tmp_path / "UPLOAD FORM.xlsx"
    workbook.save(path)
    workbook.close()
    return path


def _legacy_row(**overrides):
    from datetime import date

    values = {
        "Factory": "888 COMPANY LTD",
        "Ship Under PO Ref": "PO-1",
        "Article Code": "SWV0004581",
        "Buyer Style Ref": "GMPA17697",
        "Buyer PO Num": "PO-1",
        "Summary Buyer Order Ref": "PO-1",
        "Buyer Order Date": date(2026, 1, 1),
        "Order/Buyer Delivery Date": date(2026, 3, 1),
        "Raw Matetrial ETA Date": date(2026, 2, 1),
        "Payment Terms": "TT After Shipment 60 Days",
        "Country of Final Destination": "Sweden",
        "Color code": "O127",
        "Color name": "Forget-Me-Not",
        "Size code": "M",
        "Selling Price": 23.65,
        "Units": 9,
        "Internal Lot No.": "1",
        "PO Type": "FOB",
        "Extra Production": 0,
        "Buyer Lot No.": "RAB",
    }
    values.update(overrides)
    from wfx_panel.workbooks.oc.schema import FORM_HEADERS

    return [values[header] for header in FORM_HEADERS]


def _prepare_legacy(tmp_path, *rows, **kwargs):
    return prepare_oc_workbook(
        _legacy_file(tmp_path, *rows, **kwargs), "new", tmp_path / "upload.xlsx"
    )


def test_a_workbook_with_neither_input_nor_form_sheet_is_reported(tmp_path):
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.active.title = "KHAC"
    path = tmp_path / "OC.xlsx"
    workbook.save(path)
    workbook.close()

    with pytest.raises(OCWorkbookError) as error:
        prepare_oc_workbook(path, "new", tmp_path / "upload.xlsx")

    assert error.value.code == "OC_TEMPLATE_SHEET_MISSING"


def test_the_legacy_form_is_still_readable(tmp_path):
    prepared = _prepare_legacy(tmp_path, _legacy_row())

    assert prepared.buyer == "J.LINDEBERG"
    assert prepared.row_count == 1
    assert prepared.total_units == 9


def test_the_legacy_form_needs_its_four_metadata_cells(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_legacy(tmp_path, _legacy_row(), metadata={"B2": None})

    assert any("Season" in item for item in error.value.errors)


def test_the_legacy_form_needs_its_reference_sheet(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_legacy(tmp_path, _legacy_row(), reference=False)

    assert error.value.code == "OC_TEMPLATE_SHEET_MISSING"


def test_a_legacy_form_without_data_rows_is_reported(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_legacy(tmp_path)

    assert error.value.code == "OC_FILE_EMPTY"


def test_a_legacy_row_with_zero_units_is_dropped(tmp_path):
    other = _legacy_row(Units=0, **{"Color code": "O200"})

    prepared = _prepare_legacy(tmp_path, _legacy_row(), other)

    assert prepared.row_count == 1


def test_a_legacy_row_missing_required_columns_is_reported(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_legacy(tmp_path, _legacy_row(Factory=None))

    assert any("thiếu" in item for item in error.value.errors)


def test_a_legacy_buyer_outside_the_reference_sheet_is_reported(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_legacy(
            tmp_path, _legacy_row(), metadata={"B1": "KHONG CO TRONG DS"}
        )

    assert any("THONG TIN" in item for item in error.value.errors)


def test_two_identical_legacy_rows_are_refused(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_legacy(tmp_path, _legacy_row(), _legacy_row())

    assert any("trùng" in item for item in error.value.errors)


@pytest.mark.parametrize(
    ("overrides", "marker"),
    [
        ({"Factory": "KHONG CO TRONG DS"}, "Factory"),
        ({"Country of Final Destination": "Sao Hoa"}, "mapping Market"),
        ({"Selling Price": 0}, "Selling Price"),
        ({"Units": 1.5}, "Units"),
        ({"Extra Production": -1}, "Extra Production"),
    ],
)
def test_legacy_row_rules_are_reported_per_row(tmp_path, overrides, marker):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_legacy(tmp_path, _legacy_row(**overrides))

    assert any(marker in item for item in error.value.errors)


def test_a_legacy_file_where_every_row_has_zero_units_is_refused(tmp_path):
    with pytest.raises(OCWorkbookError) as error:
        _prepare_legacy(tmp_path, _legacy_row(Units=0))

    assert error.value.code == "OC_FILE_EMPTY"


def test_a_legacy_cell_holding_an_excel_error_names_its_row(tmp_path):
    """`#REF!` trong ô của form cũ phải thành lỗi dòng, không làm vỡ cả file."""
    with pytest.raises(OCWorkbookError) as error:
        _prepare_legacy(tmp_path, _legacy_row(**{"Color name": "#REF!"}))

    assert any("Dòng 6" in item for item in error.value.errors)
