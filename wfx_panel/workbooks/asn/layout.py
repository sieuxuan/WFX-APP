"""Chiều rộng cột, chiều cao dòng wrap và thiết lập trang A4.

Mọi sheet đặt A4, giữ hướng dọc/ngang từ report WFX, fit vừa một trang theo
chiều ngang và tự phân trang theo chiều dọc. Riêng No of Pcs, Net Wt, Gross Wt,
No of Carton và CBM được nới đủ để thấy trọn header và số liệu."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from wfx_panel.workbooks.asn.cells import (
    _cell_map,
    _cell_text,
    _column_index,
    _merged_cell_ends,
    _report_header_text,
)
from wfx_panel.workbooks.asn.ooxml import (
    MAIN_NS,
    _shared_strings,
    _tag,
    _xml,
    _xml_bytes,
)


def _wrapped_style_ids(archive: ZipFile) -> set[int]:
    root = _xml(archive.read("xl/styles.xml"))
    cell_xfs = root.find(_tag(MAIN_NS, "cellXfs"))
    if cell_xfs is None:
        return set()
    wrapped: set[int] = set()
    for index, item in enumerate(cell_xfs):
        alignment = item.find(_tag(MAIN_NS, "alignment"))
        if alignment is not None and alignment.get("wrapText") in {"1", "true"}:
            wrapped.add(index)
    return wrapped


def _sheet_column_widths(root: ET.Element) -> tuple[float, list[tuple[int, int, float]]]:
    sheet_format = root.find(_tag(MAIN_NS, "sheetFormatPr"))
    default = float(sheet_format.get("defaultColWidth", "8.43")) if sheet_format is not None else 8.43
    ranges: list[tuple[int, int, float]] = []
    columns = root.find(_tag(MAIN_NS, "cols"))
    if columns is not None:
        for column in columns.findall(_tag(MAIN_NS, "col")):
            try:
                ranges.append(
                    (
                        int(column.get("min", "1")),
                        int(column.get("max", "1")),
                        float(column.get("width", str(default))),
                    )
                )
            except ValueError:
                continue
    return default, ranges


def _column_width(
    column: int,
    default: float,
    ranges: list[tuple[int, int, float]],
) -> float:
    for first, last, width in reversed(ranges):
        if first <= column <= last:
            return width
    return default


def _display_units(value: str) -> float:
    # Ký tự full-width/CJK chiếm gần gấp đôi ký tự Latin trong Excel.
    return sum(2 if ord(character) > 0x2E7F else 1 for character in value)


def _needed_row_lines(value: str, capacity: float) -> int:
    return sum(
        max(1, math.ceil(_display_units(line) / max(1.0, capacity)))
        for line in value.replace("\r", "").split("\n")
    )


def _fit_wrapped_report_rows(target: Path) -> None:
    """Tăng đúng các hàng wrap text để Excel không cắt nội dung report WFX."""
    with ZipFile(target, "r") as source:
        shared_strings = _shared_strings(source)
        wrapped_styles = _wrapped_style_ids(source)
        replacements: dict[str, bytes] = {}
        for info in source.infolist():
            if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", info.filename):
                continue
            root = _xml(source.read(info.filename))
            default_width, width_ranges = _sheet_column_widths(root)
            merged_ends = _merged_cell_ends(root)
            sheet_format = root.find(_tag(MAIN_NS, "sheetFormatPr"))
            try:
                default_height = float(
                    sheet_format.get("defaultRowHeight", "15")
                    if sheet_format is not None
                    else "15"
                )
            except ValueError:
                default_height = 15.0
            changed = False
            for row in root.findall(f".//{_tag(MAIN_NS, 'row')}"):
                row_style = int(row.get("s", "0"))
                needed_lines = 1
                for cell in row.findall(_tag(MAIN_NS, "c")):
                    text = _cell_text(cell, shared_strings)
                    if not text:
                        continue
                    style = int(cell.get("s", str(row_style)))
                    if style not in wrapped_styles and "\n" not in text:
                        continue
                    reference = str(cell.get("r") or "A1").upper()
                    start = _column_index(reference)
                    end = merged_ends.get(reference, start)
                    width = sum(
                        _column_width(column, default_width, width_ranges)
                        for column in range(start, end + 1)
                    )
                    # Width trong OOXML là số ký tự chuẩn; chừa một ít khoảng
                    # đệm để text wrap không bị sát mép/bị cắt dòng cuối.
                    needed_lines = max(
                        needed_lines,
                        _needed_row_lines(text, max(1.0, width * 0.95)),
                    )
                if needed_lines <= 1:
                    continue
                try:
                    current_height = float(row.get("ht", str(default_height)))
                except ValueError:
                    current_height = default_height
                desired = default_height * needed_lines + 2
                if desired > current_height:
                    row.set("ht", f"{desired:g}")
                    row.set("customHeight", "1")
                    changed = True
            if changed:
                replacements[info.filename] = _xml_bytes(root)
        if not replacements:
            return
        temp_target = target.with_suffix(".height-adjusting.xlsx")
        with ZipFile(temp_target, "w", compression=ZIP_DEFLATED) as output:
            for info in source.infolist():
                output.writestr(
                    info,
                    replacements.get(info.filename, source.read(info.filename)),
                )
    temp_target.replace(target)


_PACKING_COLUMN_MINIMUM_WIDTHS = {
    "no of pcs": 11.0,
    "qty unit": 11.0,
    "net wt": 11.0,
    "net weight": 11.0,
    "gross wt": 12.0,
    "gross weight": 12.0,
    "no of carton": 13.0,
    "qty cartons": 13.0,
    "cbm": 8.0,
}


def _set_column_minimum_width(
    root: ET.Element,
    column: int,
    minimum_width: float,
) -> bool:
    default_width, width_ranges = _sheet_column_widths(root)
    if _column_width(column, default_width, width_ranges) >= minimum_width:
        return False
    columns = root.find(_tag(MAIN_NS, "cols"))
    if columns is None:
        columns = ET.Element(_tag(MAIN_NS, "cols"))
        sheet_data = root.find(_tag(MAIN_NS, "sheetData"))
        root.insert(
            list(root).index(sheet_data) if sheet_data is not None else len(root),
            columns,
        )
    for index, item in enumerate(list(columns)):
        try:
            start = int(item.get("min", "0"))
            end = int(item.get("max", "0"))
        except ValueError:
            continue
        if not start <= column <= end:
            continue
        attributes = dict(item.attrib)
        replacements: list[ET.Element] = []
        if start < column:
            before = ET.Element(_tag(MAIN_NS, "col"), attributes | {"max": str(column - 1)})
            replacements.append(before)
        adjusted = ET.Element(
            _tag(MAIN_NS, "col"),
            attributes
            | {
                "min": str(column),
                "max": str(column),
                "width": f"{minimum_width:g}",
                "customWidth": "1",
            },
        )
        replacements.append(adjusted)
        if column < end:
            after = ET.Element(_tag(MAIN_NS, "col"), attributes | {"min": str(column + 1)})
            replacements.append(after)
        columns.remove(item)
        for offset, replacement in enumerate(replacements):
            columns.insert(index + offset, replacement)
        return True
    columns.append(
        ET.Element(
            _tag(MAIN_NS, "col"),
            {
                "min": str(column),
                "max": str(column),
                "width": f"{minimum_width:g}",
                "customWidth": "1",
            },
        )
    )
    return True


def _fit_packing_measurement_columns(target: Path) -> None:
    """Nới cột số PKL để header và số liệu luôn đọc đủ khi mở Excel."""
    with ZipFile(target, "r") as source:
        shared_strings = _shared_strings(source)
        replacements: dict[str, bytes] = {}
        for info in source.infolist():
            if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", info.filename):
                continue
            root = _xml(source.read(info.filename))
            changed = False
            for row in root.findall(f".//{_tag(MAIN_NS, 'row')}"):
                for column, cell in _cell_map(row).items():
                    label = _report_header_text(_cell_text(cell, shared_strings))
                    minimum_width = _PACKING_COLUMN_MINIMUM_WIDTHS.get(label)
                    if minimum_width is not None:
                        changed = _set_column_minimum_width(
                            root,
                            column,
                            minimum_width,
                        ) or changed
            if changed:
                replacements[info.filename] = _xml_bytes(root)
        if not replacements:
            return
        temp_target = target.with_suffix(".packing-width-adjusting.xlsx")
        with ZipFile(temp_target, "w", compression=ZIP_DEFLATED) as output:
            for info in source.infolist():
                output.writestr(
                    info,
                    replacements.get(info.filename, source.read(info.filename)),
                )
    temp_target.replace(target)


def _set_a4_page_setup(root: ET.Element) -> bool:
    """Đặt khổ A4, giữ hướng in gốc và cho phép phân trang theo chiều dọc."""
    changed = False
    sheet_properties = root.find(_tag(MAIN_NS, "sheetPr"))
    if sheet_properties is None:
        sheet_properties = ET.Element(_tag(MAIN_NS, "sheetPr"))
        root.insert(0, sheet_properties)
        changed = True
    page_setup_properties = sheet_properties.find(_tag(MAIN_NS, "pageSetUpPr"))
    if page_setup_properties is None:
        page_setup_properties = ET.Element(_tag(MAIN_NS, "pageSetUpPr"))
        sheet_properties.append(page_setup_properties)
        changed = True
    if page_setup_properties.get("fitToPage") != "1":
        page_setup_properties.set("fitToPage", "1")
        changed = True

    page_setup = root.find(_tag(MAIN_NS, "pageSetup"))
    if page_setup is None:
        page_setup = ET.Element(_tag(MAIN_NS, "pageSetup"))
        # pageSetup đứng sau pageMargins/printOptions và trước headerFooter.
        insert_before = next(
            (
                index
                for index, child in enumerate(root)
                if child.tag
                in {
                    _tag(MAIN_NS, "headerFooter"),
                    _tag(MAIN_NS, "drawing"),
                    _tag(MAIN_NS, "legacyDrawing"),
                    _tag(MAIN_NS, "tableParts"),
                    _tag(MAIN_NS, "extLst"),
                }
            ),
            len(root),
        )
        root.insert(insert_before, page_setup)
        changed = True
    desired = {
        "paperSize": "9",
        "fitToWidth": "1",
        "fitToHeight": "0",
    }
    for key, value in desired.items():
        if page_setup.get(key) != value:
            page_setup.set(key, value)
            changed = True
    return changed


def _fit_reports_to_a4(target: Path) -> None:
    """Chuẩn hóa mọi sheet đã ghép sang A4 mà không đổi hướng in WFX."""
    with ZipFile(target, "r") as source:
        replacements: dict[str, bytes] = {}
        for info in source.infolist():
            if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", info.filename):
                continue
            root = _xml(source.read(info.filename))
            if _set_a4_page_setup(root):
                replacements[info.filename] = _xml_bytes(root)
        if not replacements:
            return
        temp_target = target.with_suffix(".a4-adjusting.xlsx")
        with ZipFile(temp_target, "w", compression=ZIP_DEFLATED) as output:
            for info in source.infolist():
                output.writestr(
                    info,
                    replacements.get(info.filename, source.read(info.filename)),
                )
    temp_target.replace(target)
