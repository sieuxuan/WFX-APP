"""Ghép Invoice + Packing List: lỗi nguồn và bảo toàn style ở mức OOXML.

CLAUDE.md: ghép thành một workbook giữ nguyên format report nguồn, và khi copy
sheet giữa hai workbook phải phục hồi style theo thuộc tính chứ không mang
nguyên style index sang. Ghép hỏng thì không được để lại file nửa vời cho
người dùng mở.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

import wfx_panel.workbooks.asn.merge as merge_module
from wfx_panel.workbooks.asn import merge_sale_asn_reports, sale_asn_sheet_names
from wfx_panel.workbooks.asn.ooxml import (
    MAIN_NS,
    ASNWorkbookError,
    _append_components,
    _merge_number_formats,
    _merge_styles,
    _next_relationship_id,
    _relationship_member,
    _remap_sheet_styles,
    _remap_xf,
    _shared_strings,
    _sheet_records,
    _style_section,
    _tag,
    _update_defined_names,
)


def _report(path, title, value="Báo cáo"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    sheet["A1"] = value
    workbook.save(path)
    workbook.close()


def _pair(tmp_path):
    packing = tmp_path / "packing.xlsx"
    invoice = tmp_path / "invoice.xlsx"
    _report(packing, "Packing")
    _report(invoice, "Invoice")
    return packing, invoice


def _merge(tmp_path, **kwargs):
    packing, invoice = _pair(tmp_path)
    return merge_sale_asn_reports(
        packing, invoice, tmp_path / "ghep.xlsx", **kwargs
    )


def _xml_of(text):
    return ET.fromstring(text.replace("MAIN", MAIN_NS))


# --- nguồn không dùng được ----------------------------------------------


def test_a_target_that_is_not_an_xlsx_is_refused(tmp_path):
    packing, invoice = _pair(tmp_path)

    with pytest.raises(ASNWorkbookError, match=".xlsx"):
        merge_sale_asn_reports(packing, invoice, tmp_path / "ghep.xls")


def test_a_report_wfx_never_delivered_is_named_in_the_error(tmp_path):
    packing, invoice = _pair(tmp_path)
    invoice.unlink()

    with pytest.raises(ASNWorkbookError, match="invoice.xlsx"):
        merge_sale_asn_reports(packing, invoice, tmp_path / "ghep.xlsx")


def test_an_empty_report_file_is_refused_before_anything_is_written(tmp_path):
    packing, invoice = _pair(tmp_path)
    invoice.write_bytes(b"")
    target = tmp_path / "ghep.xlsx"

    with pytest.raises(ASNWorkbookError):
        merge_sale_asn_reports(packing, invoice, target)

    assert not target.exists()


def test_a_report_that_is_not_a_workbook_at_all_is_reported_as_such(tmp_path):
    packing, invoice = _pair(tmp_path)
    invoice.write_text("<html>Session expired</html>", encoding="utf-8")
    target = tmp_path / "ghep.xlsx"

    with pytest.raises(ASNWorkbookError, match="không phải workbook Excel"):
        merge_sale_asn_reports(packing, invoice, target)

    assert not target.exists()


def test_a_report_with_no_sheet_at_all_is_refused(tmp_path):
    packing, invoice = _pair(tmp_path)
    _strip_sheets(invoice)

    with pytest.raises(ASNWorkbookError, match="ít nhất một sheet"):
        merge_sale_asn_reports(packing, invoice, tmp_path / "ghep.xlsx")


def test_a_packing_list_with_linked_objects_is_refused_not_mangled(tmp_path):
    packing, invoice = _pair(tmp_path)
    workbook = load_workbook(packing)
    workbook.active["A2"].hyperlink = "https://wfx.test/report"
    workbook.save(packing)
    workbook.close()
    target = tmp_path / "ghep.xlsx"

    with pytest.raises(ASNWorkbookError, match="đối tượng liên kết"):
        merge_sale_asn_reports(packing, invoice, target)

    assert not target.exists()


def test_a_half_written_merge_is_never_left_behind(tmp_path, monkeypatch):
    def boom(_target):
        raise RuntimeError("openpyxl không đặt được khổ giấy")

    monkeypatch.setattr(merge_module, "_fit_reports_to_a4", boom)
    packing, invoice = _pair(tmp_path)
    target = tmp_path / "ghep.xlsx"

    with pytest.raises(ASNWorkbookError, match="Không ghép được"):
        merge_sale_asn_reports(packing, invoice, target)

    assert not target.exists()


def _strip_sheets(path: Path) -> None:
    """Bỏ hẳn phần tử <sheets> để mô phỏng gói report WFX bị cắt."""
    with zipfile.ZipFile(path) as archive:
        members = {info.filename: archive.read(info) for info in archive.infolist()}
    root = ET.fromstring(members["xl/workbook.xml"])
    sheets = root.find(_tag(MAIN_NS, "sheets"))
    root.remove(sheets)
    ET.register_namespace("", MAIN_NS)
    members["xl/workbook.xml"] = ET.tostring(root, encoding="utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)


# --- đọc tên sheet sau khi ghép -----------------------------------------


def test_the_real_sheet_names_are_read_back_from_the_merged_file(tmp_path):
    target = _merge(tmp_path)

    assert sale_asn_sheet_names(target) == ["Invoice", "Packing"]


def test_reading_sheet_names_from_something_that_is_not_a_workbook_fails_clearly(
    tmp_path,
):
    broken = tmp_path / "hong.xlsx"
    broken.write_text("khong phai xlsx", encoding="utf-8")

    with pytest.raises(ASNWorkbookError, match="Không đọc được tên sheet"):
        sale_asn_sheet_names(broken)


# --- giữ style khi trộn hai bảng style ----------------------------------


def test_a_style_section_missing_from_the_base_is_created_in_the_right_order():
    root = _xml_of('<styleSheet xmlns="MAIN"><fonts/><dxfs/></styleSheet>')

    section = _style_section(root, "fills")

    assert [child.tag.rsplit("}", 1)[-1] for child in root] == [
        "fonts",
        "fills",
        "dxfs",
    ]
    assert section.tag == _tag(MAIN_NS, "fills")


def test_a_style_section_that_sorts_last_is_appended_at_the_end():
    root = _xml_of('<styleSheet xmlns="MAIN"><fonts/></styleSheet>')

    _style_section(root, "colors")

    assert [child.tag.rsplit("}", 1)[-1] for child in root] == ["fonts", "colors"]


def test_a_source_without_a_section_contributes_no_style_remapping():
    base = _xml_of('<styleSheet xmlns="MAIN"><fonts><font/></fonts></styleSheet>')
    source = _xml_of('<styleSheet xmlns="MAIN"/>')

    assert _append_components(base, source, "fonts") == {}


def test_source_styles_are_appended_after_the_base_ones_and_counted():
    base = _xml_of('<styleSheet xmlns="MAIN"><fonts><font/></fonts></styleSheet>')
    source = _xml_of(
        '<styleSheet xmlns="MAIN"><fonts><font/><font/></fonts></styleSheet>'
    )

    mapping = _append_components(base, source, "fonts")

    assert mapping == {0: 1, 1: 2}
    assert base.find(_tag(MAIN_NS, "fonts")).get("count") == "3"


# --- định dạng số -------------------------------------------------------


def test_a_number_format_the_base_already_has_is_reused_not_duplicated():
    base = _xml_of(
        '<styleSheet xmlns="MAIN"><numFmts>'
        '<numFmt numFmtId="200" formatCode="#,##0.000"/>'
        "</numFmts></styleSheet>"
    )
    source = _xml_of(
        '<styleSheet xmlns="MAIN"><numFmts>'
        '<numFmt numFmtId="176" formatCode="#,##0.000"/>'
        "</numFmts></styleSheet>"
    )

    mapping = _merge_number_formats(base, source)

    assert mapping == {176: 200}
    assert len(base.find(_tag(MAIN_NS, "numFmts"))) == 1


def test_a_new_number_format_never_reuses_an_id_the_base_already_took():
    base = _xml_of(
        '<styleSheet xmlns="MAIN"><numFmts>'
        '<numFmt numFmtId="164" formatCode="0.00"/>'
        '<numFmt numFmtId="165" formatCode="0.000"/>'
        "</numFmts></styleSheet>"
    )
    source = _xml_of(
        '<styleSheet xmlns="MAIN"><numFmts>'
        '<numFmt numFmtId="164" formatCode="dd/mm/yyyy"/>'
        '<numFmt numFmtId="170" formatCode="#,##0 &quot;CBM&quot;"/>'
        "</numFmts></styleSheet>"
    )

    mapping = _merge_number_formats(base, source)

    assert set(mapping) == {164, 170}
    assert set(mapping.values()).isdisjoint({164, 165})
    assert len(set(mapping.values())) == 2


def test_a_source_without_number_formats_leaves_the_base_untouched():
    base = _xml_of('<styleSheet xmlns="MAIN"/>')
    source = _xml_of('<styleSheet xmlns="MAIN"/>')

    assert _merge_number_formats(base, source) == {}


def test_a_cell_format_is_repointed_at_the_styles_it_actually_landed_on():
    item = _xml_of(
        '<xf xmlns="MAIN" fontId="1" fillId="2" borderId="3" numFmtId="164" xfId="1"/>'
    )

    copied = _remap_xf(
        item,
        font_map={1: 11},
        fill_map={2: 22},
        border_map={3: 33},
        number_format_map={164: 200},
        style_xf_map={1: 5},
    )

    assert copied.attrib["fontId"] == "11"
    assert copied.attrib["fillId"] == "22"
    assert copied.attrib["borderId"] == "33"
    assert copied.attrib["numFmtId"] == "200"
    assert copied.attrib["xfId"] == "5"


def test_a_cell_format_pointing_at_an_unmapped_style_keeps_its_index():
    item = _xml_of('<xf xmlns="MAIN" fontId="7"/>')

    copied = _remap_xf(
        item, font_map={}, fill_map={}, border_map={}, number_format_map={}
    )

    assert copied.attrib["fontId"] == "7"


# --- quan hệ sheet trong gói --------------------------------------------


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("worksheets/sheet1.xml", "xl/worksheets/sheet1.xml"),
        ("xl/worksheets/sheet1.xml", "xl/worksheets/sheet1.xml"),
        ("/xl/worksheets/sheet1.xml", "xl/worksheets/sheet1.xml"),
        ("worksheets\\sheet1.xml", "xl/worksheets/sheet1.xml"),
    ],
)
def test_a_sheet_relationship_always_resolves_to_its_member_in_the_package(
    target, expected
):
    assert _relationship_member(target) == expected


def test_a_workbook_without_a_sheet_list_has_no_sheet_records():
    workbook = _xml_of('<workbook xmlns="MAIN"/>')
    relationships = _xml_of(
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006'
        '/relationships"/>'
    )

    assert _sheet_records(workbook, relationships) == []


def test_a_new_relationship_id_skips_the_ones_already_used():
    used = {"rId1", "rId2", "rId4"}

    assert _next_relationship_id(used) == "rId3"
    assert _next_relationship_id(used) == "rId5"


# --- defined names ------------------------------------------------------


def _workbook_with_names(names):
    root = ET.Element(_tag(MAIN_NS, "workbook"))
    ET.SubElement(root, _tag(MAIN_NS, "sheets"))
    if names is None:
        return root
    container = ET.SubElement(root, _tag(MAIN_NS, "definedNames"))
    for name, local_id in names:
        item = ET.SubElement(container, _tag(MAIN_NS, "definedName"), name=name)
        if local_id is not None:
            item.set("localSheetId", str(local_id))
    return root


def test_print_areas_of_the_invoice_follow_it_to_its_new_position():
    base = _workbook_with_names([("_xlnm.Print_Area", 0)])
    source = _workbook_with_names(None)

    _update_defined_names(base, source, {0: 2}, {})

    item = base.find(_tag(MAIN_NS, "definedNames"))[0]
    assert item.get("localSheetId") == "2"


def test_a_packing_list_print_area_is_carried_over_when_the_invoice_has_none():
    base = _workbook_with_names(None)
    source = _workbook_with_names([("_xlnm.Print_Area", 0)])

    _update_defined_names(base, source, {}, {0: 3})

    container = base.find(_tag(MAIN_NS, "definedNames"))
    assert container is not None
    assert container[0].get("localSheetId") == "3"
    assert list(base).index(container) == 1


def test_a_workbook_wide_defined_name_is_not_pinned_to_a_sheet():
    base = _workbook_with_names(None)
    source = _workbook_with_names([("TyGia", None)])

    _update_defined_names(base, source, {}, {0: 3})

    # Không gắn được vào sheet nào thì bỏ hẳn: đoán sai localSheetId sẽ trỏ
    # công thức của report này sang sheet của report kia.
    assert list(base.find(_tag(MAIN_NS, "definedNames"))) == []


# --- shared strings -----------------------------------------------------


def test_the_text_of_a_report_is_read_from_its_shared_string_table(tmp_path):
    # SSRS xuất chuỗi vào sharedStrings.xml (openpyxl thì ghi inline), nên bảng
    # này phải đọc được thì layout mới nhận ra cột Net Wt/CBM của Packing List.
    package = tmp_path / "ssrs.xlsx"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="{MAIN_NS}" count="2" uniqueCount="2">'
            "<si><t>No of Carton</t></si>"
            "<si><r><t>Net </t></r><r><t>Wt</t></r></si>"
            "</sst>",
        )

    with zipfile.ZipFile(package) as archive:
        assert _shared_strings(archive) == ["No of Carton", "Net Wt"]


def test_a_package_without_a_shared_string_table_reads_as_no_text(tmp_path):
    empty = tmp_path / "trong.xlsx"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")

    with zipfile.ZipFile(empty) as archive:
        assert _shared_strings(archive) == []


# --- conditional formatting ---------------------------------------------


def test_conditional_formats_of_the_packing_list_keep_their_own_styles():
    base = (
        '<styleSheet xmlns="MAIN"><dxfs><dxf/></dxfs></styleSheet>'
    ).replace("MAIN", MAIN_NS).encode()
    source = (
        '<styleSheet xmlns="MAIN"><dxfs><dxf/><dxf/></dxfs></styleSheet>'
    ).replace("MAIN", MAIN_NS).encode()

    merged, _cell_style_map, dxf_map = _merge_styles(base, source)

    assert dxf_map == {0: 1, 1: 2}
    assert ET.fromstring(merged).find(_tag(MAIN_NS, "dxfs")).get("count") == "3"


def test_a_sheet_rule_points_at_the_conditional_format_it_landed_on():
    sheet = (
        '<worksheet xmlns="MAIN"><conditionalFormatting sqref="A1:A9">'
        '<cfRule type="cellIs" dxfId="0" priority="1"/>'
        "</conditionalFormatting></worksheet>"
    ).replace("MAIN", MAIN_NS).encode()

    remapped = ET.fromstring(_remap_sheet_styles(sheet, {}, {0: 4}))

    rule = remapped.find(f"{_tag(MAIN_NS, 'conditionalFormatting')}/{_tag(MAIN_NS, 'cfRule')}")
    assert rule.get("dxfId") == "4"
