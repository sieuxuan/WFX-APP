"""Đọc form 22 cột Sale ASN: giá trị, ngày, và các luật một-Invoice-một-FTY.

CLAUDE.md: mỗi file chỉ chứa một Invoice No. và một FTY; chỉ cặp PO No. + Style
No. trùng hoàn toàn là lỗi; Shipping Mode chỉ bắt buộc và chỉ được đọc ở dòng dữ
liệu đầu tiên; nếu cả file không có Cargo Ready Date thì giữ trống chứ không
dùng ngày hiện tại.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook, load_workbook

from wfx_panel.workbooks import sale_asn as sale_asn_workbook
from wfx_panel.workbooks.sale_asn import (
    SALE_ASN_COLUMNS,
    SaleASNWorkbookError,
    read_sale_asn_workbook,
    write_sale_asn_template,
)


def _row(**overrides):
    values = {
        "Style No": "M ACEL JACKET",
        "PO No": "PO-1",
        "Qty": 10,
        "Price": 2.5,
        "Carton": 2,
        "NW": 1.5,
        "GW": 2.0,
        "CBM": 0.3,
        "FOB Price": 2.5,
        "Service Price": 0.1,
        "Cargo Ready Date": date(2026, 3, 1),
        "HS CODE": "6203",
        "Goods Description": "JACKET",
        "Invoice No": "INV-1",
        "Invoice Date": date(2026, 3, 2),
        "Shipping Bill No": "SB-1",
        "Shipping Bill Date": date(2026, 3, 3),
        "Destination": "SWEDEN",
        "FTY": "PSHK VIETNAM",
        "Consignee Address": "ABC",
        "Ship To": "XYZ",
        "Shipping Mode": "SEA",
    }
    values.update(overrides)
    return [values[column] for column in SALE_ASN_COLUMNS]


def _file(tmp_path, *rows, name="Sale ASN.xlsx", headers=None, sheet="Sheet1"):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    worksheet.append(list(headers if headers is not None else SALE_ASN_COLUMNS))
    for row in rows:
        worksheet.append(list(row))
    path = tmp_path / name
    workbook.save(path)
    workbook.close()
    return path


def _read(tmp_path, *rows, **kwargs):
    return read_sale_asn_workbook(_file(tmp_path, *rows), **kwargs)


# --- an toàn file -------------------------------------------------------


def test_only_xlsx_is_accepted(tmp_path):
    path = tmp_path / "Sale ASN.xls"
    path.write_bytes(b"excel")

    with pytest.raises(SaleASNWorkbookError) as error:
        read_sale_asn_workbook(path)

    assert error.value.code == "SALE_ASN_FILE_TYPE_UNSUPPORTED"


def test_a_file_the_user_already_moved_is_reported(tmp_path):
    with pytest.raises(SaleASNWorkbookError) as error:
        read_sale_asn_workbook(tmp_path / "khong-ton-tai.xlsx")

    assert error.value.code == "SALE_ASN_FILE_NOT_FOUND"


def test_a_file_above_the_size_cap_is_refused(tmp_path, monkeypatch):
    path = _file(tmp_path, _row())
    monkeypatch.setattr(sale_asn_workbook, "MAX_SALE_ASN_BYTES", 10)

    with pytest.raises(SaleASNWorkbookError) as error:
        read_sale_asn_workbook(path)

    assert error.value.code == "SALE_ASN_FILE_TOO_LARGE"


def test_a_file_that_is_not_a_zip_is_reported_as_invalid(tmp_path):
    path = tmp_path / "Sale ASN.xlsx"
    path.write_bytes(b"khong phai zip")

    with pytest.raises(SaleASNWorkbookError) as error:
        read_sale_asn_workbook(path)

    assert error.value.code == "SALE_ASN_FILE_INVALID"


def test_a_workbook_carrying_macros_is_refused(tmp_path):
    path = tmp_path / "Sale ASN.xlsx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/vbaProject.bin", "macro")

    with pytest.raises(SaleASNWorkbookError) as error:
        read_sale_asn_workbook(path)

    assert error.value.code == "SALE_ASN_FILE_UNSAFE"


def test_a_zip_that_openpyxl_cannot_read_is_reported(tmp_path):
    path = tmp_path / "Sale ASN.xlsx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("readme.txt", "chi la zip")

    with pytest.raises(SaleASNWorkbookError) as error:
        read_sale_asn_workbook(path)

    assert error.value.code == "SALE_ASN_FILE_INVALID"


def test_a_file_with_too_many_rows_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(sale_asn_workbook, "MAX_SALE_ASN_ROWS", 1)
    second = _row(**{"Style No": "W ACEL"})

    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path, _row(), second)

    assert error.value.code == "SALE_ASN_FILE_TOO_MANY_ROWS"


def test_a_file_without_any_data_row_is_reported(tmp_path):
    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path)

    assert error.value.code == "SALE_ASN_FILE_EMPTY"


def test_a_formula_in_the_input_area_is_refused(tmp_path):
    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path, _row(Qty="=1+1"))

    assert error.value.code == "SALE_ASN_FILE_FORMULA_ERROR"
    assert error.value.errors


# --- chuẩn hoá giá trị --------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, ""), (float("nan"), ""), ("  x  ", "x"), (12, "12")],
)
def test_text_values_are_normalised(value, expected):
    assert sale_asn_workbook._text(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "True"), (12, "12"), (12.0, "12"), (12.5, "12.5"), ("PO-1", "PO-1")],
)
def test_identifiers_keep_the_shape_excel_shows(value, expected):
    assert sale_asn_workbook._identifier(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("", ""), ("1,250.50", "1250.5"), (0, "0"), ("12.000", "12")],
)
def test_numbers_are_normalised_without_trailing_zeros(value, expected):
    assert sale_asn_workbook._number(value, cell="Qty") == expected


def test_a_cell_that_is_not_a_number_names_itself():
    with pytest.raises(ValueError, match="Qty dòng 3: phải là số."):
        sale_asn_workbook._number("abc", cell="Qty dòng 3")


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity"])
def test_a_negative_or_infinite_number_is_refused(value):
    with pytest.raises(ValueError, match="không âm"):
        sale_asn_workbook._number(value, cell="Qty")


def test_a_number_too_large_for_wfx_is_refused_at_the_file(monkeypatch):
    """Chặn ở file để không biến lỗi nhập liệu thành lỗi automation."""
    with pytest.raises(ValueError, match="quá lớn"):
        sale_asn_workbook._number("1E+50", cell="Qty")


def test_a_fractional_value_in_an_integer_column_is_refused():
    with pytest.raises(ValueError, match="số nguyên"):
        sale_asn_workbook._number("1.5", cell="Carton", integer=True)


# --- ngày ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        date(2026, 3, 1),
        datetime(2026, 3, 1, 10, 0),
        "01/03/2026",
        "01-03-2026",
        "2026-03-01",
        "01 Mar 2026",
    ],
)
def test_every_date_format_the_form_accepts_reads_the_same(value):
    assert sale_asn_workbook._date_text(value, cell="X") == "2026-03-01"


def test_an_excel_serial_number_is_still_understood():
    assert sale_asn_workbook._date_text(46082, cell="X") == "2026-03-01"


def test_a_serial_excel_cannot_convert_is_reported():
    with pytest.raises(ValueError, match="ngày không hợp lệ"):
        sale_asn_workbook._date_text(-10_000_000, cell="X")


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_empty_date_cell_stays_empty(value):
    assert sale_asn_workbook._date_text(value, cell="X") == ""


def test_a_date_nobody_can_parse_names_its_cell():
    with pytest.raises(ValueError, match="K3: ngày không hợp lệ."):
        sale_asn_workbook._date_text("hom qua", cell="K3")


# --- luật nghiệp vụ -----------------------------------------------------


def test_a_valid_file_reports_its_totals(tmp_path):
    second = _row(**{"Style No": "W ACEL JACKET", "PO No": "PO-2"})

    document = _read(tmp_path, _row(), second)

    assert document["invoice_no"] == "INV-1"
    assert document["factory"] == "PSHK VIETNAM"
    assert document["po_count"] == 2
    assert document["style_count"] == 2
    assert document["file_name"] == "Sale ASN.xlsx"


def test_two_rows_with_the_same_po_and_style_are_refused(tmp_path):
    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path, _row(), _row())

    assert any("trùng" in item for item in error.value.errors)


def test_one_po_with_two_styles_is_allowed(tmp_path):
    second = _row(**{"Style No": "W ACEL JACKET"})

    assert _read(tmp_path, _row(), second)["po_count"] == 2


def test_a_file_with_two_invoices_is_refused(tmp_path):
    second = _row(**{"Style No": "W ACEL", "Invoice No": "INV-2"})

    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path, _row(), second)

    assert any("một Invoice No" in item for item in error.value.errors)


def test_a_file_with_two_factories_is_refused(tmp_path):
    second = _row(**{"Style No": "W ACEL", "FTY": "NHA MAY KHAC"})

    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path, _row(), second)

    assert any("một FTY" in item for item in error.value.errors)


def test_a_row_without_a_factory_is_reported_with_its_row_number(tmp_path):
    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path, _row(FTY=""))

    assert any("FTY bắt buộc" in item for item in error.value.errors)


def test_an_invoice_missing_from_every_row_is_reported(tmp_path):
    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path, _row(**{"Invoice No": ""}))

    assert any("Invoice No" in item for item in error.value.errors)


@pytest.mark.parametrize("mode", ["", "TAU HOA"])
def test_the_first_row_must_carry_a_supported_shipping_mode(tmp_path, mode):
    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path, _row(**{"Shipping Mode": mode}))

    assert any("Shipping Mode" in item for item in error.value.errors)


def test_later_rows_do_not_need_a_shipping_mode(tmp_path):
    second = _row(**{"Style No": "W ACEL", "Shipping Mode": ""})

    document = _read(tmp_path, _row(), second)

    assert document["rows"][0]["shipping_mode"] == "SEA"


def test_a_missing_shipping_bill_no_falls_back_to_the_invoice_no(tmp_path):
    document = _read(tmp_path, _row(**{"Shipping Bill No": ""}))

    assert document["shipping_bill_no"] == "INV-1"


def test_a_file_without_any_cargo_ready_date_leaves_it_empty(tmp_path):
    document = _read(tmp_path, _row(**{"Cargo Ready Date": None}))

    assert document["rows"][0]["cargo_ready_date"] == ""


def test_a_cargo_ready_date_on_one_row_fills_the_blank_ones(tmp_path):
    second = _row(**{"Style No": "W ACEL", "Cargo Ready Date": None})

    document = _read(tmp_path, _row(), second)

    assert document["rows"][1]["cargo_ready_date"] == "2026-03-01"


def test_a_bad_date_in_the_first_row_is_reported_not_guessed(tmp_path):
    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path, _row(**{"Invoice Date": "hom qua"}))

    assert any("ngày không hợp lệ" in item for item in error.value.errors)


def test_a_bad_number_in_a_later_row_names_that_row(tmp_path):
    second = _row(**{"Style No": "W ACEL", "Qty": "abc"})

    with pytest.raises(SaleASNWorkbookError) as error:
        _read(tmp_path, _row(), second)

    assert any("phải là số" in item for item in error.value.errors)


# --- các bước được chọn -------------------------------------------------


def test_skipping_the_po_step_leaves_blank_dates_alone(tmp_path):
    document = _read(
        tmp_path,
        _row(**{"Invoice Date": None, "Shipping Bill Date": None}),
        required_stages=["order_details"],
    )

    assert document["rows"][0]["invoice_date"] == ""


def test_running_the_po_step_fills_blank_dates_with_today(tmp_path):
    document = _read(
        tmp_path,
        _row(**{"Invoice Date": None, "Shipping Bill Date": None}),
        required_stages=["po"],
    )

    assert document["rows"][0]["invoice_date"] == date.today().isoformat()


def test_skipping_shipping_info_removes_the_shipping_mode_requirement(tmp_path):
    document = _read(
        tmp_path,
        _row(**{"Shipping Mode": ""}),
        required_stages=["order_details"],
    )

    assert document["rows"][0]["shipping_mode"] == ""


# --- form mẫu -----------------------------------------------------------


def test_the_template_has_exactly_the_twenty_two_columns(tmp_path):
    path = write_sale_asn_template(tmp_path / "form.xls")

    assert path.suffix == ".xlsx"
    workbook = load_workbook(path)
    sheet = workbook.active
    assert [cell.value for cell in sheet[1]] == list(SALE_ASN_COLUMNS)
    workbook.close()


def test_the_template_can_be_prefilled_and_read_back(tmp_path):
    path = write_sale_asn_template(
        tmp_path / "form.xlsx",
        [
            {
                "style_no": "M ACEL JACKET",
                "po_no": "PO-1",
                "qty": "10",
                "price": "2.5",
            }
        ],
    )

    workbook = load_workbook(path)
    sheet = workbook.active
    assert sheet.cell(2, 1).value == "M ACEL JACKET"
    assert sheet.cell(2, 2).value == "PO-1"
    workbook.close()


def test_the_template_keeps_the_three_date_columns_optional(tmp_path):
    path = write_sale_asn_template(tmp_path / "form.xlsx")

    workbook = load_workbook(path)
    sheet = workbook.active
    date_validations = [
        validation
        for validation in sheet.data_validations.dataValidation
        if validation.type == "date"
    ]
    assert date_validations
    assert all(validation.allow_blank for validation in date_validations)
    workbook.close()


def test_a_nan_float_is_treated_as_an_empty_cell():
    assert sale_asn_workbook._text(math.nan) == ""


# --- workbook kết quả Check giá ----------------------------------------


def _price_check(**overrides):
    payload = {
        "comparisons": [
            {
                "status": "ok",
                "source_rows": [2],
                "po_no": "PO-1",
                "style_no": "M ACEL",
                "file_qty": "10",
                "system_qty": "10",
                "file_price": "2.5",
                "system_prices": ["2.5"],
                "message": "Khớp Qty và Price.",
            }
        ],
        "summary": {
            "checks": {
                "total_quantity": {"ok": True, "file": "10", "system": "10"},
            }
        },
    }
    payload.update(overrides)
    return payload


def test_the_price_check_workbook_keeps_every_comparison_row(tmp_path):
    path = sale_asn_workbook.write_sale_asn_price_check_workbook(
        tmp_path / "check.xlsx", _price_check()
    )

    workbook = load_workbook(path)
    text = " ".join(
        str(cell.value or "")
        for sheet in workbook.worksheets
        for row in sheet.iter_rows()
        for cell in row
    )
    workbook.close()
    assert "PO-1" in text
    assert "M ACEL" in text


@pytest.mark.parametrize(
    "payload",
    [
        {"comparisons": "khong phai list"},
        {"comparisons": ["khong phai dict"]},
        {"summary": "khong phai dict"},
        {"summary": {"checks": "khong phai dict"}},
        {},
    ],
)
def test_a_malformed_price_check_payload_still_produces_a_workbook(
    tmp_path, payload
):
    """Payload đến từ JS nên phải chịu được mọi hình dạng lạ."""
    path = sale_asn_workbook.write_sale_asn_price_check_workbook(
        tmp_path / "check.xlsx", _price_check(**payload)
    )

    assert path.is_file()


# --- ghi giá trị vào form ----------------------------------------------


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        # Chỉ các cột trong _TEMPLATE_NUMBER_COLUMNS mới đổi sang kiểu số;
        # Qty/Price giữ nguyên chuỗi để không mất định dạng người dùng nhập.
        ("Qty", "10", "10"),
        ("Price", "2.5", "2.5"),
        ("Carton", "2", 2),
        ("NW", "1.5", 1.5),
        ("Carton", "abc", "abc"),
        ("Cargo Ready Date", "2026-03-01", date(2026, 3, 1)),
        ("Cargo Ready Date", "hom qua", "hom qua"),
        ("PO No", 779, "779"),
    ],
)
def test_template_cells_keep_the_type_excel_needs(column, value, expected):
    assert sale_asn_workbook._template_export_value(column, value) == expected
