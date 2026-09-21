"""Luật của document Costing: chuẩn hóa ô, validate, và giới hạn file.

CLAUDE.md: file Costing không được cung cấp selector cho automation; blank giữ
nguyên, `__CLEAR__` mới là xóa, Action trống là UPSERT. Workbook chỉ có hai
sheet `Hướng dẫn` và `Costing`, và mọi lỗi file là lỗi người dùng nên phải có
mã ổn định để UI phân loại chứ không thoát ra thành lỗi hệ thống.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from wfx_panel.workbooks.costing import schema


def _document(**overrides):
    document = {
        "format_version": schema.FORMAT_VERSION,
        "style_code": "SWN0000001",
        "sections": [{"section_key": "fabricshell", "name": "FABRIC- SHELL"}],
        "items": [
            {
                "section_key": "fabricshell",
                "item_key": "item-1",
                "article_code": "F0001",
                "article_name": "Cotton",
            }
        ],
        "fields": [
            {
                "scope": "item",
                "section_key": "fabricshell",
                "item_key": "item-1",
                "field_key": "consqty",
                "value": "1.5",
            }
        ],
    }
    document.update(overrides)
    return document


def _errors(**overrides):
    with pytest.raises(schema.CostingWorkbookError) as raised:
        schema.normalize_document(_document(**overrides))
    return raised.value


# --- mã lỗi cho UI ------------------------------------------------------


def test_a_file_error_carries_a_code_and_the_lines_to_fix():
    error = schema.CostingWorkbookError(
        "COSTING_VALIDATION_FAILED", "File sai.", details=["Dòng 3", "Dòng 7"]
    )

    assert error.as_result() == {
        "ok": False,
        "code": "COSTING_VALIDATION_FAILED",
        "message": "File sai.",
        "validation_errors": ["Dòng 3", "Dòng 7"],
    }


# --- đọc giá trị ô Excel ------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (True, "true"),
        (False, "false"),
        ("  Cotton  ", "Cotton"),
        (12, "12"),
    ],
)
def test_a_cell_value_is_read_as_the_text_the_user_typed(value, expected):
    assert schema._text(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("x", True),
        ("Có", True),
        ("yes", True),
        ("", False),
        ("khong", False),
        (None, False),
    ],
)
def test_a_tick_box_accepts_the_shapes_excel_actually_produces(value, expected):
    assert schema._bool(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("3", 3), (4.7, 4), ("", 9), (None, 9), ("ba", 9), ([], 9)],
)
def test_a_row_order_that_excel_mangled_falls_back_to_the_file_order(
    value, expected
):
    assert schema._order(value, 9) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["A", "", "B"], ["A", "B"]),
        (("A", "B"), ["A", "B"]),
        ("A|B| ", ["A", "B"]),
        ('["A", "B"]', ["A", "B"]),
        ('["A", 2]', ["A", "2"]),
        ('[khong phai json', ["[khong phai json"]),
        ('{"a": 1}', ['{"a": 1}']),
        ("", []),
        (None, []),
    ],
)
def test_a_dropdown_list_is_read_from_every_shape_the_export_writes(
    value, expected
):
    assert schema._options(value) == expected


def test_a_cell_longer_than_the_limit_is_refused_with_its_location():
    with pytest.raises(schema.CostingWorkbookError) as raised:
        schema._clean_cell("x" * (schema.MAX_CELL_CHARS + 1), "Costing!B12")

    assert raised.value.details == ["Costing!B12"]


# --- dropdown Article ---------------------------------------------------


@pytest.mark.parametrize("value", [None, "F0001", {"article_code": "F0001"}])
def test_an_article_list_in_the_wrong_shape_yields_no_dropdown(value):
    assert schema._article_lookup_options(value) == []


def test_rows_without_both_a_code_and_a_name_are_not_offered():
    options = schema._article_lookup_options(
        [
            "F0001",
            {"article_code": "F0001"},
            {"article_name": "Cotton"},
            {"article_code": "F0001", "article_name": "Cotton"},
        ]
    )

    assert options == [{"article_code": "F0001", "article_name": "Cotton"}]


def test_the_same_article_code_is_only_offered_once():
    options = schema._article_lookup_options(
        [
            {"article_code": "F0001", "article_name": "Cotton"},
            {"article_code": "f0001", "article_name": "Cotton (cu)"},
        ]
    )

    assert [item["article_name"] for item in options] == ["Cotton"]


# --- nhận diện section chuẩn --------------------------------------------


def test_a_section_the_form_does_not_know_has_no_standard_token():
    assert schema._standard_section_token({"section_key": "khac"}) == ""


def test_an_old_export_that_only_said_fabric_still_maps_to_the_shell_section():
    assert schema._standard_section({"section_key": "Fabric"}) == (
        0,
        schema.STANDARD_SECTIONS[0][1],
    )


def test_a_section_the_form_does_not_know_is_left_out_of_the_workbook():
    document = schema.workbook_document(
        _document(
            sections=[
                {"section_key": "fabricshell", "name": "FABRIC- SHELL"},
                {"section_key": "ghichu", "name": "Ghi chú nội bộ"},
            ]
        )
    )

    keys = [section["section_key"] for section in document["sections"]]
    # Workbook luôn có đủ bộ section chuẩn để người dùng nhập trực tiếp; section
    # lạ của WFX không được chen vào đó.
    assert len(keys) == len(schema.STANDARD_SECTIONS)
    assert not any("ghichu" in key for key in keys)


# --- giới hạn kích thước document ---------------------------------------


def test_a_file_with_too_many_sections_is_refused():
    sections = [
        {"section_key": f"s{index}", "name": f"S{index}"}
        for index in range(schema.MAX_SECTIONS + 1)
    ]

    error = _errors(sections=sections, items=[], fields=[])

    assert any("section" in detail.casefold() for detail in error.details)


def test_a_file_with_too_many_articles_is_refused():
    items = [
        {
            "section_key": "fabricshell",
            "item_key": f"item-{index}",
            "article_code": "F0001",
        }
        for index in range(schema.MAX_ITEMS + 1)
    ]

    error = _errors(items=items, fields=[])

    assert any("Article" in detail for detail in error.details)


def test_a_file_with_too_many_fields_is_refused():
    fields = [
        {
            "scope": "cost_sheet",
            "field_key": f"field-{index}",
        }
        for index in range(schema.MAX_FIELDS + 1)
    ]

    error = _errors(fields=fields)

    assert any("field" in detail.casefold() for detail in error.details)


# --- validate section ---------------------------------------------------


def test_a_section_without_a_key_is_named_in_the_error():
    error = _errors(sections=[{"name": "FABRIC- SHELL"}], items=[], fields=[])

    assert "Section thiếu Section Key." in error.details


def test_two_sections_with_the_same_key_are_refused():
    error = _errors(
        sections=[
            {"section_key": "fabricshell", "name": "A"},
            {"section_key": "fabricshell", "name": "B"},
        ],
        items=[],
        fields=[],
    )

    assert "Section Key trùng: fabricshell." in error.details


# --- validate Article ---------------------------------------------------


def test_an_article_row_without_a_section_is_refused():
    error = _errors(
        items=[{"item_key": "item-1", "article_code": "F0001"}], fields=[]
    )

    assert "Article thiếu Section Key." in error.details


def test_an_article_row_without_an_item_key_is_named_by_its_code():
    error = _errors(
        items=[{"section_key": "fabricshell", "article_code": "F0001"}],
        fields=[],
    )

    assert any("F0001" in detail and "Item Key" in detail for detail in error.details)


def test_two_rows_sharing_an_item_key_in_one_section_are_refused():
    item = {
        "section_key": "fabricshell",
        "item_key": "item-1",
        "article_code": "F0001",
    }

    error = _errors(items=[item, dict(item)], fields=[])

    assert "Item Key trùng trong section: item-1." in error.details


def test_an_action_the_file_format_does_not_define_is_refused():
    error = _errors(
        items=[
            {
                "section_key": "fabricshell",
                "item_key": "item-1",
                "article_code": "F0001",
                "action": "REMOVE",
            }
        ],
        fields=[],
    )

    assert "Action không hợp lệ: REMOVE." in error.details


def test_an_item_type_the_file_format_does_not_define_is_refused():
    error = _errors(
        items=[
            {
                "section_key": "fabricshell",
                "item_key": "item-1",
                "item_type": "material",
            }
        ],
        fields=[],
    )

    assert "Item Type không hợp lệ: material." in error.details


def test_an_article_row_with_neither_a_code_nor_a_name_is_refused():
    error = _errors(
        items=[{"section_key": "fabricshell", "item_key": "item-1"}], fields=[]
    )

    assert "Article item-1 thiếu Code/Name." in error.details


def test_a_cost_line_without_a_name_is_refused():
    error = _errors(
        items=[
            {
                "section_key": "cmcosts",
                "item_key": "cm-1",
                "item_type": "cost_line",
            }
        ],
        fields=[],
    )

    assert "Dòng chi phí cm-1 thiếu tên." in error.details


# --- validate field -----------------------------------------------------


def test_a_field_scope_the_file_format_does_not_define_is_refused():
    error = _errors(fields=[{"scope": "article", "field_key": "consqty"}])

    assert "Field scope không hợp lệ: article." in error.details


def test_a_field_without_a_key_is_refused():
    error = _errors(fields=[{"scope": "cost_sheet"}])

    assert "Field thiếu Field Key." in error.details


def test_two_fields_with_the_same_key_in_one_scope_are_refused():
    field = {
        "scope": "item",
        "section_key": "fabricshell",
        "item_key": "item-1",
        "field_key": "consqty",
    }

    error = _errors(fields=[field, dict(field)])

    assert any("Field Key trùng" in detail for detail in error.details)


def test_a_section_field_without_its_section_is_refused():
    error = _errors(fields=[{"scope": "section", "field_key": "note"}])

    assert "Field note thiếu Section Key." in error.details


def test_an_item_field_without_its_item_is_refused():
    error = _errors(
        fields=[
            {
                "scope": "item",
                "section_key": "fabricshell",
                "field_key": "consqty",
            }
        ]
    )

    assert "Item field consqty thiếu Item Key." in error.details


# --- file trên đĩa ------------------------------------------------------


def _xlsx(path, members=None):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in (members or {"xl/workbook.xml": b"<workbook/>"}).items():
            archive.writestr(name, data)
    return path


def test_a_file_the_user_moved_away_is_reported_clearly(tmp_path):
    with pytest.raises(schema.CostingWorkbookError) as raised:
        schema._preflight_path(tmp_path / "khong-co.xlsx", must_exist=True)

    assert raised.value.code == "COSTING_FILE_REQUIRED"


def test_a_file_larger_than_the_limit_is_refused_before_it_is_parsed(tmp_path):
    big = tmp_path / "to.xlsx"
    big.write_bytes(b"0" * (schema.MAX_FILE_BYTES + 1))

    with pytest.raises(schema.CostingWorkbookError) as raised:
        schema._preflight_path(big, must_exist=True)

    assert raised.value.code == "COSTING_FILE_TOO_LARGE"


def test_a_workbook_with_far_too_many_parts_is_refused(tmp_path):
    target = _xlsx(
        tmp_path / "nhieu.xlsx",
        {f"part{index}.xml": b"<x/>" for index in range(schema.MAX_XLSX_MEMBERS + 1)},
    )

    with pytest.raises(schema.CostingWorkbookError) as raised:
        schema._preflight_xlsx_archive(target)

    assert raised.value.code == "COSTING_FILE_TOO_LARGE"


def test_a_workbook_that_explodes_when_unzipped_is_refused(tmp_path, monkeypatch):
    target = _xlsx(tmp_path / "bom.xlsx")
    real_infolist = zipfile.ZipFile.infolist

    def inflate(self):
        members = real_infolist(self)
        for member in members:
            member.file_size = schema.MAX_XLSX_UNCOMPRESSED_BYTES + 1
        return members

    monkeypatch.setattr(zipfile.ZipFile, "infolist", inflate)

    with pytest.raises(schema.CostingWorkbookError) as raised:
        schema._preflight_xlsx_archive(target)

    assert raised.value.code == "COSTING_FILE_TOO_LARGE"


def test_a_file_that_is_not_a_workbook_at_all_is_reported_as_invalid(tmp_path):
    broken = tmp_path / "hong.xlsx"
    broken.write_text("khong phai xlsx", encoding="utf-8")

    with pytest.raises(schema.CostingWorkbookError) as raised:
        schema._preflight_xlsx_archive(broken)

    assert raised.value.code == "COSTING_VALIDATION_FAILED"


def test_a_healthy_workbook_passes_the_preflight(tmp_path):
    target = _xlsx(tmp_path / "ok.xlsx")

    assert schema._preflight_path(target, must_exist=True) == Path(target)


def test_the_options_of_a_field_survive_a_round_trip_through_json():
    field = schema._normalized_field(
        {"field_key": "supplier", "options": json.dumps(["A", "B"])}, 0
    )

    assert field["options"] == ["A", "B"]


def test_a_field_pointing_at_a_section_the_workbook_dropped_is_dropped_too():
    document = schema.workbook_document(
        _document(
            sections=[{"section_key": "ghichu", "name": "Ghi chú nội bộ"}],
            items=[
                {
                    "section_key": "ghichu",
                    "item_key": "item-1",
                    "article_code": "F0001",
                }
            ],
            fields=[
                {
                    "scope": "item",
                    "section_key": "ghichu",
                    "item_key": "item-1",
                    "field_key": "colConsQty",
                    "editable": True,
                    "value": "1.5",
                }
            ],
        )
    )

    assert document["items"] == []
    assert document["fields"] == []
