"""Layout report Sale ASN: XML mà SSRS xuất ra không phải lúc nào cũng chuẩn.

CLAUDE.md: khi ghép, tăng chiều cao các hàng wrap text theo nội dung và độ rộng
cột để không cắt dòng trong Excel; mọi sheet đặt A4, giữ hướng dọc/ngang từ
report WFX và fit vừa một trang theo chiều ngang.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from wfx_panel.workbooks.asn.layout import (
    _column_width,
    _fit_reports_to_a4,
    _fit_wrapped_report_rows,
    _set_a4_page_setup,
    _set_column_minimum_width,
    _sheet_column_widths,
    _wrapped_style_ids,
)
from wfx_panel.workbooks.asn.ooxml import MAIN_NS, _tag


def _xml_of(text):
    return ET.fromstring(text.replace("MAIN", MAIN_NS))


def _package(tmp_path, members, name="report.xlsx"):
    target = tmp_path / name
    with zipfile.ZipFile(target, "w") as archive:
        for path, data in members.items():
            archive.writestr(path, data)
    return target


def _sheet(body):
    return (
        f'<worksheet xmlns="{MAIN_NS}">{body}</worksheet>'
    ).encode()


# --- bảng style ----------------------------------------------------------


def test_a_style_sheet_without_cell_formats_has_no_wrapped_styles(tmp_path):
    target = _package(
        tmp_path,
        {"xl/styles.xml": f'<styleSheet xmlns="{MAIN_NS}"/>'.encode()},
    )

    with zipfile.ZipFile(target) as archive:
        assert _wrapped_style_ids(archive) == set()


def test_only_formats_that_wrap_text_are_collected(tmp_path):
    target = _package(
        tmp_path,
        {
            "xl/styles.xml": (
                f'<styleSheet xmlns="{MAIN_NS}"><cellXfs>'
                "<xf/>"
                '<xf><alignment wrapText="1"/></xf>'
                '<xf><alignment wrapText="true"/></xf>'
                '<xf><alignment vertical="top"/></xf>'
                "</cellXfs></styleSheet>"
            ).encode()
        },
    )

    with zipfile.ZipFile(target) as archive:
        assert _wrapped_style_ids(archive) == {1, 2}


# --- độ rộng cột ---------------------------------------------------------


def test_a_column_range_excel_wrote_wrong_is_skipped():
    root = _xml_of(
        '<worksheet xmlns="MAIN"><cols>'
        '<col min="khong-phai-so" max="3" width="12"/>'
        '<col min="4" max="5" width="20"/>'
        "</cols></worksheet>"
    )

    default, ranges = _sheet_column_widths(root)

    assert default == pytest.approx(8.43)
    assert ranges == [(4, 5, 20.0)]


def test_a_sheet_without_column_ranges_uses_its_default_width():
    root = _xml_of(
        '<worksheet xmlns="MAIN"><sheetFormatPr defaultColWidth="11"/></worksheet>'
    )

    default, ranges = _sheet_column_widths(root)

    assert default == 11.0
    assert ranges == []
    assert _column_width(3, default, ranges) == 11.0


# --- chiều cao hàng wrap text --------------------------------------------


LONG_TEXT = "Goods description with quite a lot of words that must wrap"


def _wrapped_package(tmp_path, *, row_attrs="", default_height='15'):
    body = (
        f'<sheetFormatPr defaultRowHeight="{default_height}"/>'
        '<cols><col min="1" max="1" width="8"/></cols>'
        f"<sheetData><row r=\"2\" {row_attrs}>"
        f'<c r="A2" s="1" t="inlineStr"><is><t>{LONG_TEXT}</t></is></c>'
        "</row></sheetData>"
    )
    return _package(
        tmp_path,
        {
            "xl/styles.xml": (
                f'<styleSheet xmlns="{MAIN_NS}"><cellXfs>'
                "<xf/><xf><alignment wrapText=\"1\"/></xf>"
                "</cellXfs></styleSheet>"
            ).encode(),
            "xl/worksheets/sheet1.xml": _sheet(body),
        },
    )


def _row_height(target):
    with zipfile.ZipFile(target) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    row = root.find(f".//{_tag(MAIN_NS, 'row')}")
    return row.get("ht"), row.get("customHeight")


def test_a_wrapped_row_is_made_tall_enough_for_its_text(tmp_path):
    target = _wrapped_package(tmp_path)

    _fit_wrapped_report_rows(target)

    height, custom = _row_height(target)
    assert float(height) > 15
    assert custom == "1"


def test_a_default_row_height_excel_wrote_wrong_falls_back_to_fifteen(tmp_path):
    target = _wrapped_package(tmp_path, default_height="rat-cao")

    _fit_wrapped_report_rows(target)

    height, _custom = _row_height(target)
    assert float(height) > 15


def test_a_row_height_excel_wrote_wrong_is_replaced(tmp_path):
    target = _wrapped_package(tmp_path, row_attrs='ht="khong-phai-so"')

    _fit_wrapped_report_rows(target)

    height, _custom = _row_height(target)
    assert float(height) > 15


def test_a_row_that_is_already_tall_enough_is_left_alone(tmp_path):
    target = _wrapped_package(tmp_path, row_attrs='ht="400"')

    _fit_wrapped_report_rows(target)

    height, _custom = _row_height(target)
    assert height == "400"


def test_a_package_with_no_wrapped_rows_is_not_rewritten(tmp_path):
    target = _package(
        tmp_path,
        {
            "xl/styles.xml": f'<styleSheet xmlns="{MAIN_NS}"/>'.encode(),
            "xl/worksheets/sheet1.xml": _sheet("<sheetData/>"),
        },
    )
    before = target.read_bytes()

    _fit_wrapped_report_rows(target)

    assert target.read_bytes() == before


# --- nới cột tối thiểu ---------------------------------------------------


def _widths(root):
    columns = root.find(_tag(MAIN_NS, "cols"))
    if columns is None:
        return []
    return [
        (item.get("min"), item.get("max"), item.get("width")) for item in columns
    ]


def test_a_column_inside_a_wider_range_is_split_out_on_both_sides():
    root = _xml_of(
        '<worksheet xmlns="MAIN"><cols>'
        '<col min="1" max="5" width="4"/>'
        "</cols><sheetData/></worksheet>"
    )

    assert _set_column_minimum_width(root, 3, 12.0) is True
    assert _widths(root) == [
        ("1", "2", "4"),
        ("3", "3", "12"),
        ("4", "5", "4"),
    ]


def test_a_column_at_the_start_of_a_range_only_splits_after_it():
    root = _xml_of(
        '<worksheet xmlns="MAIN"><cols>'
        '<col min="1" max="5" width="4"/>'
        "</cols><sheetData/></worksheet>"
    )

    assert _set_column_minimum_width(root, 1, 12.0) is True
    assert _widths(root) == [("1", "1", "12"), ("2", "5", "4")]


def test_a_column_range_excel_wrote_wrong_is_skipped_while_widening():
    root = _xml_of(
        '<worksheet xmlns="MAIN"><cols>'
        '<col min="a" max="b" width="4"/>'
        "</cols><sheetData/></worksheet>"
    )

    assert _set_column_minimum_width(root, 3, 12.0) is True
    assert ("3", "3", "12") in _widths(root)


def test_a_column_that_is_already_wide_enough_is_left_alone():
    root = _xml_of(
        '<worksheet xmlns="MAIN"><cols>'
        '<col min="1" max="5" width="20"/>'
        "</cols><sheetData/></worksheet>"
    )

    assert _set_column_minimum_width(root, 3, 12.0) is False


# --- khổ A4 --------------------------------------------------------------


def test_a_sheet_with_no_properties_at_all_gets_them(tmp_path):
    root = _xml_of('<worksheet xmlns="MAIN"><sheetData/></worksheet>')

    assert _set_a4_page_setup(root) is True

    properties = root.find(_tag(MAIN_NS, "sheetPr"))
    assert list(root).index(properties) == 0
    assert properties.find(_tag(MAIN_NS, "pageSetUpPr")).get("fitToPage") == "1"


def test_a_sheet_that_already_has_properties_only_gains_what_it_lacks():
    root = _xml_of(
        '<worksheet xmlns="MAIN"><sheetPr><outlinePr/></sheetPr>'
        "<sheetData/></worksheet>"
    )

    assert _set_a4_page_setup(root) is True

    properties = root.find(_tag(MAIN_NS, "sheetPr"))
    assert len(root.findall(_tag(MAIN_NS, "sheetPr"))) == 1
    assert properties.find(_tag(MAIN_NS, "pageSetUpPr")) is not None


def test_a_package_with_no_worksheet_is_left_untouched(tmp_path):
    target = _package(
        tmp_path, {"xl/workbook.xml": f'<workbook xmlns="{MAIN_NS}"/>'.encode()}
    )
    before = target.read_bytes()

    _fit_reports_to_a4(target)

    assert target.read_bytes() == before
    assert not list(Path(tmp_path).glob("*.a4-adjusting.xlsx"))


def test_every_worksheet_in_the_package_is_set_to_a4(tmp_path):
    target = _package(
        tmp_path,
        {
            "xl/worksheets/sheet1.xml": _sheet("<sheetData/>"),
            "xl/worksheets/sheet2.xml": _sheet("<sheetData/>"),
        },
    )

    _fit_reports_to_a4(target)

    with zipfile.ZipFile(target) as archive:
        for name in ("sheet1", "sheet2"):
            root = ET.fromstring(archive.read(f"xl/worksheets/{name}.xml"))
            setup = root.find(
                f"{_tag(MAIN_NS, 'sheetPr')}/{_tag(MAIN_NS, 'pageSetUpPr')}"
            )
            assert setup.get("fitToPage") == "1"
