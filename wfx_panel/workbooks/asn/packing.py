"""Luật gộp dòng Packing List riêng cho từng Buyer.

Hai luật này khoá theo Buyer exact đọc từ dòng Sale ASN: chỉ ``J.LINDEBERG`` và
``CORPORATE OFFICE - TRUEWERK``. Buyer khác — kể cả BIRDDOGS dùng bộ header
giống TRUEWERK — phải giữ nguyên từng dòng. Chỉ gộp khi cột đó có đúng một giá
trị, để không làm mất số liệu."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from wfx_panel.workbooks.asn.cells import (
    _cell_map,
    _cell_row,
    _cell_text,
    _clear_merged_cell_value,
    _column_index,
    _copy_cell_value,
    _existing_merge_ranges,
    _header_text,
    _merge_range_is_free,
    _report_header_text,
)
from wfx_panel.workbooks.asn.ooxml import (
    MAIN_NS,
    _shared_strings,
    _tag,
    _xml,
    _xml_bytes,
)

_JL_PACKING_HEADERS = {
    "jl po#": "po",
    "style no": "style",
    "net wt": "net_wt",
    "gross wt": "gross_wt",
    "no of carton": "carton",
    "cbm": "cbm",
}


_JL_PACKING_MEASUREMENTS = ("net_wt", "gross_wt", "carton", "cbm")


_TRUEWERK_PACKING_HEADERS = {
    "qty unit": "quantity",
    "net weight": "net_wt",
    "gross weight": "gross_wt",
    "qty cartons": "carton",
    "cbm": "cbm",
}


_TRUEWERK_PACKING_DETAIL_HEADERS = {"style": "style", "po no": "po"}


_TRUEWERK_PACKING_MEASUREMENTS = ("net_wt", "gross_wt", "carton", "cbm")


_JL_BUYER = "j.lindeberg"


_TRUEWERK_BUYER = "corporate office - truewerk"


def _merge_jl_packing_sheet(root: ET.Element, shared_strings: list[str]) -> bool:
    """Gộp cột tổng của Packing List J.Lindeberg theo JL PO# + Style No."""
    sheet_data = root.find(_tag(MAIN_NS, "sheetData"))
    if sheet_data is None:
        return False
    rows = sorted(
        sheet_data.findall(_tag(MAIN_NS, "row")),
        key=lambda row: int(row.get("r", "0")),
    )
    header_index = -1
    columns: dict[str, int] = {}
    for index, row in enumerate(rows):
        labels = {
            _header_text(_cell_text(cell, shared_strings)): column
            for column, cell in _cell_map(row).items()
        }
        candidate = {
            key: labels[label]
            for label, key in _JL_PACKING_HEADERS.items()
            if label in labels
        }
        if len(candidate) == len(_JL_PACKING_HEADERS):
            header_index, columns = index, candidate
            break
    if header_index < 0:
        return False

    existing = _existing_merge_ranges(root)
    new_ranges: list[tuple[int, int, int]] = []

    def merge_group(group: list[tuple[ET.Element, dict[int, ET.Element]]]) -> None:
        if len(group) < 2:
            return
        first_row = int(group[0][0].get("r", "0"))
        last_row = int(group[-1][0].get("r", "0"))
        for name in _JL_PACKING_MEASUREMENTS:
            column = columns[name]
            cells = [cell_map.get(column) for _row, cell_map in group]
            if any(cell is None for cell in cells):
                continue
            values = [_cell_text(cell, shared_strings).strip() for cell in cells]
            if not values[0] or any(value != values[0] for value in values[1:]):
                continue
            if not _merge_range_is_free(existing, column, first_row, last_row):
                continue
            new_ranges.append((column, first_row, last_row))
            existing.append((column, column, first_row, last_row))
            for cell in cells[1:]:
                _clear_merged_cell_value(cell)

    group: list[tuple[ET.Element, dict[int, ET.Element]]] = []
    previous_row = 0
    previous_key: tuple[str, str] | None = None
    for row in rows[header_index + 1 :]:
        row_number = int(row.get("r", "0"))
        cell_map = _cell_map(row)
        po_cell, style_cell = cell_map.get(columns["po"]), cell_map.get(columns["style"])
        key = (
            _cell_text(po_cell, shared_strings).strip() if po_cell is not None else "",
            _cell_text(style_cell, shared_strings).strip() if style_cell is not None else "",
        )
        if not key[0] or not key[1] or row_number != previous_row + 1 or key != previous_key:
            merge_group(group)
            group = []
        if key[0] and key[1]:
            group.append((row, cell_map))
            previous_key = key
            previous_row = row_number
        else:
            previous_key = None
            previous_row = 0
    merge_group(group)
    if not new_ranges:
        return False

    merge_cells = root.find(_tag(MAIN_NS, "mergeCells"))
    if merge_cells is None:
        merge_cells = ET.Element(_tag(MAIN_NS, "mergeCells"))
        root.insert(list(root).index(sheet_data) + 1, merge_cells)
    for column, first_row, last_row in new_ranges:
        letter = ""
        value = column
        while value:
            value, remainder = divmod(value - 1, 26)
            letter = chr(ord("A") + remainder) + letter
        merge_cells.append(
            ET.Element(
                _tag(MAIN_NS, "mergeCell"),
                {"ref": f"{letter}{first_row}:{letter}{last_row}"},
            )
        )
    merge_cells.set("count", str(len(merge_cells)))
    return True


def _merge_jl_packing_measurements(target: Path) -> None:
    """Áp dụng gộp tổng J.Lindeberg, chỉ cho sheet có đủ header đặc trưng."""
    with ZipFile(target, "r") as source:
        shared_strings = _shared_strings(source)
        replacements: dict[str, bytes] = {}
        for info in source.infolist():
            if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", info.filename):
                continue
            root = _xml(source.read(info.filename))
            if _merge_jl_packing_sheet(root, shared_strings):
                replacements[info.filename] = _xml_bytes(root)
        if not replacements:
            return
        temp_target = target.with_suffix(".jl-merge-adjusting.xlsx")
        with ZipFile(temp_target, "w", compression=ZIP_DEFLATED) as output:
            for info in source.infolist():
                output.writestr(
                    info,
                    replacements.get(info.filename, source.read(info.filename)),
                )
    temp_target.replace(target)


def _truewerk_po_base(value: str) -> tuple[str, bool]:
    """Trả PO gốc và cờ dòng phụ ADD của Packing List TRUEWERK."""
    normalized = " ".join(value.split())
    base = re.sub(r"\s*-?\s*ADD$", "", normalized, flags=re.IGNORECASE).strip()
    return base.casefold(), base != normalized


def _is_zero_measurement(value: str) -> bool:
    return bool(re.fullmatch(r"[+-]?0+(?:[.,]0+)?", value.replace(" ", "")))


def _merge_truewerk_packing_sheet(
    root: ET.Element,
    shared_strings: list[str],
) -> bool:
    """Gộp số liệu kiện hàng TRUEWERK từ PO gốc xuống dòng PO ADD."""
    sheet_data = root.find(_tag(MAIN_NS, "sheetData"))
    if sheet_data is None:
        return False
    rows = sorted(
        sheet_data.findall(_tag(MAIN_NS, "row")),
        key=lambda row: int(row.get("r", "0")),
    )
    body_index = -1
    columns: dict[str, int] = {}
    for index, row in enumerate(rows):
        labels = {
            _report_header_text(_cell_text(cell, shared_strings)): column
            for column, cell in _cell_map(row).items()
        }
        candidate = {
            key: labels[label]
            for label, key in _TRUEWERK_PACKING_HEADERS.items()
            if label in labels
        }
        if len(candidate) != len(_TRUEWERK_PACKING_HEADERS):
            continue
        for detail_index, detail_row in enumerate(rows[index + 1 : index + 3], index + 1):
            detail_labels = {
                _report_header_text(_cell_text(cell, shared_strings)): column
                for column, cell in _cell_map(detail_row).items()
            }
            detail_candidate = {
                key: detail_labels[label]
                for label, key in _TRUEWERK_PACKING_DETAIL_HEADERS.items()
                if label in detail_labels
            }
            if len(detail_candidate) == len(_TRUEWERK_PACKING_DETAIL_HEADERS):
                columns = candidate | detail_candidate
                body_index = detail_index + 1
                break
        if body_index >= 0:
            break
    if body_index < 0:
        return False

    existing = _existing_merge_ranges(root)
    new_ranges: list[tuple[int, int, int, int]] = []
    replaced_ranges: set[tuple[int, int, int, int]] = set()

    def merge_group(group: list[tuple[ET.Element, dict[int, ET.Element], bool]]) -> None:
        nonlocal existing
        if len(group) < 2 or not any(is_add for _row, _cells, is_add in group):
            return
        if not any(not is_add for _row, _cells, is_add in group):
            return
        first_row = int(group[0][0].get("r", "0"))
        last_row = int(group[-1][0].get("r", "0"))
        for name in _TRUEWERK_PACKING_MEASUREMENTS:
            column = columns[name]
            cells = [cell_map.get(column) for _row, cell_map, _is_add in group]
            if any(cell is None for cell in cells):
                continue
            values = [_cell_text(cell, shared_strings).strip() for cell in cells]
            non_zero_indices = [
                index
                for index, value in enumerate(values)
                if value and not _is_zero_measurement(value)
            ]
            if len(non_zero_indices) != 1:
                continue
            anchor_range = next(
                (
                    item
                    for item in existing
                    if item[0] <= column <= item[1]
                    and item[2] == first_row
                    and item[3] == first_row
                ),
                None,
            )
            start_column, end_column = (
                anchor_range[:2] if anchor_range is not None else (column, column)
            )
            target_range = (start_column, end_column, first_row, last_row)
            row_ranges = {
                (start_column, end_column, row_number, row_number)
                for row_number in range(first_row, last_row + 1)
            }
            conflicts = [
                item
                for item in existing
                if not (
                    end_column < item[0]
                    or start_column > item[1]
                    or last_row < item[2]
                    or first_row > item[3]
                )
            ]
            if (
                any(item not in row_ranges for item in conflicts)
            ):
                continue
            new_ranges.append(target_range)
            replaced_ranges.update(conflicts)
            existing = [item for item in existing if item not in conflicts]
            existing.append(target_range)
            source_index = non_zero_indices[0]
            if source_index:
                _copy_cell_value(cells[source_index], cells[0])
            for cell in cells[1:]:
                _clear_merged_cell_value(cell)

    group: list[tuple[ET.Element, dict[int, ET.Element], bool]] = []
    previous_row = 0
    previous_key: tuple[str, str] | None = None
    for row in rows[body_index:]:
        row_number = int(row.get("r", "0"))
        cell_map = _cell_map(row)
        style_cell, po_cell = cell_map.get(columns["style"]), cell_map.get(columns["po"])
        style = _cell_text(style_cell, shared_strings).strip() if style_cell is not None else ""
        po_value = _cell_text(po_cell, shared_strings).strip() if po_cell is not None else ""
        po_base, is_add = _truewerk_po_base(po_value)
        key = (style.casefold(), po_base)
        if not all(key) or row_number != previous_row + 1 or key != previous_key:
            merge_group(group)
            group = []
        if all(key):
            group.append((row, cell_map, is_add))
            previous_key = key
            previous_row = row_number
        else:
            previous_key = None
            previous_row = 0
    merge_group(group)
    if not new_ranges:
        return False

    merge_cells = root.find(_tag(MAIN_NS, "mergeCells"))
    if merge_cells is None:
        merge_cells = ET.Element(_tag(MAIN_NS, "mergeCells"))
        root.insert(list(root).index(sheet_data) + 1, merge_cells)
    for item in list(merge_cells):
        reference = str(item.get("ref") or "")
        start, separator, end = reference.partition(":")
        if not separator:
            end = start
        range_tuple = (
            _column_index(start),
            _column_index(end),
            _cell_row(start),
            _cell_row(end),
        )
        if range_tuple in replaced_ranges:
            merge_cells.remove(item)
    for start_column, end_column, first_row, last_row in new_ranges:
        start_letter = ""
        value = start_column
        while value:
            value, remainder = divmod(value - 1, 26)
            start_letter = chr(ord("A") + remainder) + start_letter
        end_letter = ""
        value = end_column
        while value:
            value, remainder = divmod(value - 1, 26)
            end_letter = chr(ord("A") + remainder) + end_letter
        merge_cells.append(
            ET.Element(
                _tag(MAIN_NS, "mergeCell"),
                {"ref": f"{start_letter}{first_row}:{end_letter}{last_row}"},
            )
        )
    merge_cells.set("count", str(len(merge_cells)))
    return True


def _merge_truewerk_packing_measurements(target: Path) -> None:
    """Áp dụng gộp bốn cột tổng PO/PO ADD cho Packing List TRUEWERK."""
    with ZipFile(target, "r") as source:
        shared_strings = _shared_strings(source)
        replacements: dict[str, bytes] = {}
        for info in source.infolist():
            if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", info.filename):
                continue
            root = _xml(source.read(info.filename))
            if _merge_truewerk_packing_sheet(root, shared_strings):
                replacements[info.filename] = _xml_bytes(root)
        if not replacements:
            return
        temp_target = target.with_suffix(".truewerk-merge-adjusting.xlsx")
        with ZipFile(temp_target, "w", compression=ZIP_DEFLATED) as output:
            for info in source.infolist():
                output.writestr(
                    info,
                    replacements.get(info.filename, source.read(info.filename)),
                )
    temp_target.replace(target)
