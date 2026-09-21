"""Đọc ô, dò header và thao tác vùng merge trên worksheet openpyxl."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from copy import deepcopy

from wfx_panel.workbooks.asn.ooxml import MAIN_NS, _tag


def _column_index(reference: str) -> int:
    match = re.match(r"([A-Z]+)", reference.upper())
    if match is None:
        return 1
    value = 0
    for character in match.group(1):
        value = value * 26 + ord(character) - ord("A") + 1
    return value


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(_tag(MAIN_NS, "is"))
        return "".join(inline.itertext()) if inline is not None else ""
    value = cell.find(_tag(MAIN_NS, "v"))
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        try:
            return shared_strings[int(value.text)]
        except (IndexError, ValueError):
            return ""
    return value.text


def _merged_cell_ends(root: ET.Element) -> dict[str, int]:
    merged = root.find(_tag(MAIN_NS, "mergeCells"))
    if merged is None:
        return {}
    ends: dict[str, int] = {}
    for item in merged.findall(_tag(MAIN_NS, "mergeCell")):
        reference = str(item.get("ref") or "")
        if ":" not in reference:
            continue
        start, end = reference.split(":", 1)
        ends[start.upper()] = _column_index(end)
    return ends


def _cell_row(reference: str) -> int:
    match = re.search(r"(\d+)$", reference)
    return int(match.group(1)) if match is not None else 0


def _cell_map(row: ET.Element) -> dict[int, ET.Element]:
    return {
        _column_index(str(cell.get("r") or "A1")): cell
        for cell in row.findall(_tag(MAIN_NS, "c"))
    }


def _header_text(value: str) -> str:
    return " ".join(value.replace("\n", " ").split()).casefold()


def _report_header_text(value: str) -> str:
    """Chuẩn hoá các biến thể dấu nối/chấm trong header report WFX."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _header_text(value)).split())


def _existing_merge_ranges(root: ET.Element) -> list[tuple[int, int, int, int]]:
    merge_cells = root.find(_tag(MAIN_NS, "mergeCells"))
    if merge_cells is None:
        return []
    ranges: list[tuple[int, int, int, int]] = []
    for item in merge_cells.findall(_tag(MAIN_NS, "mergeCell")):
        reference = str(item.get("ref") or "")
        start, separator, end = reference.partition(":")
        if not separator:
            end = start
        start_column, end_column = _column_index(start), _column_index(end)
        start_row, end_row = _cell_row(start), _cell_row(end)
        if start_row and end_row:
            ranges.append((start_column, end_column, start_row, end_row))
    return ranges


def _merge_range_is_free(
    existing: list[tuple[int, int, int, int]],
    column: int,
    first_row: int,
    last_row: int,
) -> bool:
    return not any(
        start_column <= column <= end_column
        and not (last_row < start_row or first_row > end_row)
        for start_column, end_column, start_row, end_row in existing
    )


def _clear_merged_cell_value(cell: ET.Element) -> None:
    for child in tuple(cell):
        if child.tag in {
            _tag(MAIN_NS, "f"),
            _tag(MAIN_NS, "v"),
            _tag(MAIN_NS, "is"),
        }:
            cell.remove(child)
    cell.attrib.pop("t", None)


def _copy_cell_value(source: ET.Element, target: ET.Element) -> None:
    """Chuyển nội dung ô nguồn sang ô đầu của vùng merge, giữ style ô đích."""
    _clear_merged_cell_value(target)
    if "t" in source.attrib:
        target.set("t", source.attrib["t"])
    for child in source:
        if child.tag in {
            _tag(MAIN_NS, "f"),
            _tag(MAIN_NS, "v"),
            _tag(MAIN_NS, "is"),
        }:
            target.append(deepcopy(child))
