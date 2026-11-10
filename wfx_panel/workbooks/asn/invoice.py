"""Gộp số liệu đóng gói lặp lại trong Commercial Invoice."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from openpyxl.utils.cell import get_column_letter

from wfx_panel.workbooks.asn.cells import (
    _cell_map,
    _cell_text,
    _clear_merged_cell_value,
    _column_index,
    _existing_merge_ranges,
    _merged_cell_ends,
    _report_header_text,
)
from wfx_panel.workbooks.asn.ooxml import MAIN_NS, _tag

_INVOICE_HEADERS = {
    "po": {"po", "po no", "po no n", "po number", "jl po", "buyer order ref"},
    "style": {"style", "style no", "style number", "style code"},
    "qty": {"qty", "quantity", "no of pcs", "no of pieces", "qty pcs", "qty unit", "pcs"},
    "net": {
        "net wt", "net weight", "net wt kg", "net wt kgs", "net weight kg", "net weight kgs", "nw", "n w",
    },
    "gross": {
        "gross wt", "gross weight", "gross wt kg", "gross wt kgs", "gross weight kg", "gross weight kgs", "gw", "g w",
    },
    "carton": {"carton", "cartons", "no of carton", "no of cartons", "qty cartons", "ctn", "ctns", "no of ctns"},
    "cbm": {"cbm", "c b m", "measurement cbm"},
}
_INVOICE_MEASUREMENTS = ("net", "gross", "carton", "cbm")


def _invoice_number(value: str) -> Decimal | None:
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _merge_invoice_measurements(root: ET.Element, shared_strings: list[str]) -> bool:
    sheet_data = root.find(_tag(MAIN_NS, "sheetData"))
    # Gộp ô sẽ xóa giá trị lặp. Với sheet có công thức, giữ dữ liệu tham chiếu.
    if sheet_data is None or next(sheet_data.iter(_tag(MAIN_NS, "f")), None) is not None:
        return False

    merge_cells = root.find(_tag(MAIN_NS, "mergeCells"))
    merge_items = merge_cells.findall(_tag(MAIN_NS, "mergeCell")) if merge_cells is not None else ()
    existing = dict(zip(_existing_merge_ranges(root), merge_items, strict=True))
    merged_ends = _merged_cell_ends(root)
    columns: dict[str, int] = {}
    group: list[tuple[int, tuple[ET.Element, ...]]] = []
    previous_key: tuple | None = None
    changed = False

    def merge_group() -> None:
        nonlocal merge_cells, changed
        if len(group) < 2:
            return
        first_row, last_row = group[0][0], group[-1][0]
        spans = []
        for cell in group[0][1]:
            anchor = str(cell.get("r"))
            left = _column_index(anchor)
            spans.append((left, merged_ends.get(anchor, left)))
        replacements = set()
        for left, right in spans:
            for bounds in existing:
                start, end, top, bottom = bounds
                if end < left or start > right or bottom < first_row or top > last_row:
                    continue
                if (left, right) != (start, end) or top != bottom:
                    return
                replacements.add(bounds)
        if merge_cells is None:
            merge_cells = ET.Element(_tag(MAIN_NS, "mergeCells"))
            after = {
                "sheetData", "sheetCalcPr", "sheetProtection", "protectedRanges",
                "scenarios", "autoFilter", "sortState", "dataConsolidate", "customSheetViews",
            }
            root.insert(
                max(i for i, item in enumerate(root) if item.tag.rpartition("}")[2] in after) + 1,
                merge_cells,
            )
        for bounds in replacements:
            merge_cells.remove(existing.pop(bounds))
        for left, right in spans:
            ref = f"{get_column_letter(left)}{first_row}:{get_column_letter(right)}{last_row}"
            item = ET.SubElement(merge_cells, _tag(MAIN_NS, "mergeCell"), ref=ref)
            existing[left, right, first_row, last_row] = item
        for _row, measurements in group[1:]:
            for cell in measurements:
                _clear_merged_cell_value(cell)
        changed = True

    for row in sheet_data.findall(_tag(MAIN_NS, "row")):
        row_number = int(row.get("r", "0"))
        populated = {
            col: (cell, value)
            for col, cell in _cell_map(row).items()
            if (value := _cell_text(cell, shared_strings).strip())
        }
        labels = {_report_header_text(value): col for col, (_cell, value) in populated.items()}
        headers = {
            key: labels[label]
            for key, aliases in _INVOICE_HEADERS.items()
            if len(matches := aliases & labels.keys()) == 1
            for label in matches
        }
        key = None
        measurements: tuple[ET.Element, ...] = ()
        if len(headers) == len(_INVOICE_HEADERS):
            columns = headers
        elif labels.keys() & {"total", "grand total", "subtotal", "sub total"}:
            columns = {}
        elif columns and row.get("hidden") not in {"1", "true"}:
            logical_cells = {
                col: (start, end, cell, value)
                for start, (cell, value) in populated.items()
                for end in (merged_ends.get(str(cell.get("r")), start),)
                for col in columns.values()
                if start <= col <= end
            }
            if len(logical_cells) == len(columns):
                po, style, qty = (logical_cells[columns[name]] for name in ("po", "style", "qty"))
                measures = [logical_cells[columns[name]] for name in _INVOICE_MEASUREMENTS]
                signature = tuple((left, right, _invoice_number(value)) for left, right, _, value in measures)
                if (
                    len({item[0] for item in logical_cells.values()}) == len(columns)
                    and _invoice_number(qty[3]) is not None
                    and all(value is not None for _, _, value in signature)
                ):
                    key = (po[3], style[3], signature)
                    measurements = tuple(item[2] for item in measures)
        if group and (key != previous_key or row_number != group[-1][0] + 1):
            merge_group()
            group.clear()
        if key is not None:
            group.append((row_number, measurements))
        previous_key = key
    merge_group()
    if changed:
        merge_cells.set("count", str(len(merge_cells)))
    return changed
