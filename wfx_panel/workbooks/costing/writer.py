"""Sinh file Costing: sheet Hướng dẫn, form nhập, dropdown và công thức.

Workbook có đúng hai sheet — `Hướng dẫn` và `Costing`. Chỉ round-trip field
item `editable=true`; hai cột đỏ công thức là chỉ-đọc."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from wfx_panel.workbooks.costing.schema import (
    _HEADER_FILL,
    _HEADER_FONT,
    _INPUT_FILL,
    _READ_ONLY_FILL,
    _READ_ONLY_HEADER_FILL,
    _SECTION_BORDER,
    _STRUCTURE_BORDER,
    _SUBHEADER_FILL,
    _TEMPLATE_INPUT_FILL,
    _TITLE_FONT,
    CLEAR_MARKER,
    FORM_BASE_COLUMNS,
    FORM_COLUMNS,
    FORM_SHEET,
    FORM_TECH_COLUMNS,
    FORMAT_VERSION,
    GUIDE_SHEET,
    STANDARD_ITEM_FIELDS,
    CostingWorkbookError,
    _article_lookup_options,
    _excel_safe,
    _form_field_key,
    _preflight_path,
    _section_item_type,
    _standard_section_token,
    _template_row_count,
    _text,
    workbook_document,
)


def _set_header(ws: Any, row: int, columns: Sequence[str]) -> None:
    for column, value in enumerate(columns, 1):
        cell = ws.cell(row=row, column=column, value=value)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 28
    ws.auto_filter.ref = (
        f"A{row}:{get_column_letter(len(columns))}{max(row, ws.max_row)}"
    )
    ws.freeze_panes = f"A{row + 1}"


def _finish_sheet(
    ws: Any,
    widths: Mapping[int, float],
    *,
    editable_columns: Iterable[int] = (),
) -> None:
    editable = set(editable_columns)
    for column, width in widths.items():
        ws.column_dimensions[get_column_letter(column)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = _STRUCTURE_BORDER
            if cell.column in editable:
                cell.fill = _INPUT_FILL
    ws.sheet_view.showGridLines = False


def _write_guide(workbook: Workbook, document: Mapping[str, Any]) -> None:
    ws = workbook.create_sheet(GUIDE_SHEET)
    ws.merge_cells("A1:F1")
    ws["A1"] = "WFX Smart · Catalog Costing"
    ws["A1"].font = _TITLE_FONT
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 34
    rows = [
        ("Style Code", document["style_code"]),
        ("Style Name", document.get("style_name") or "—"),
        ("Trạng thái khi tải", document.get("cost_sheet_status") or "—"),
        ("Phiên bản file", f"v{FORMAT_VERSION}"),
        (
            "Cách dùng",
            "Mở sheet Costing và sửa các ô màu vàng. Dòng không dùng thì để trống.",
        ),
        (
            "Phạm vi",
            "Có thể tải file ở mọi trạng thái. Chỉ Cost Sheet đang Open mới "
            "được cập nhật lại lên WFX.",
        ),
        (
            "Các nhóm trong file",
            ", ".join(
                str(section.get("name") or section.get("section_key") or "")
                for section in document.get("sections") or ()
                if str(
                    section.get("name") or section.get("section_key") or ""
                ).strip()
            )
            or "—",
        ),
        (
            "Thêm nhiều dòng",
            "Điền lần lượt các dòng vàng trong đúng nhóm. Nếu cần thêm dòng, "
            "sao chép dòng vàng cuối và chèn trước nhóm tiếp theo.",
        ),
        (
            "Tách dòng màu/size",
            "Hai dòng liền nhau cùng Article Code sẽ được tách thành hai dòng "
            "riêng trên WFX.",
        ),
        (
            "Phối màu/size",
            "Mỗi dòng phối ghi Màu/Size vật tư => Màu/Size của style. Nhiều lựa "
            "chọn được ngăn bằng dấu |.",
        ),
        (
            "Cột công thức",
            "Cons. Qty. Incl. Waste = Cons. Qty. × (1 + Waste %/100); "
            "Value in (USD) = Rate × Cons. Qty. Incl. Waste. Hai cột đỏ chỉ đọc.",
        ),
        (
            "Purchase Officer",
            "Chọn từ danh sách nếu ô này trên WFX đang trống. App sẽ báo trước "
            "khi còn thiếu.",
        ),
        (
            "Cột Action",
            "Để trống = thêm mới hoặc cập nhật. Chọn DELETE chỉ khi muốn xóa dòng.",
        ),
        (
            "Xóa giá trị",
            f"Ô trống sẽ giữ nguyên dữ liệu cũ. Muốn xóa, ghi đúng {CLEAR_MARKER}.",
        ),
        (
            "An toàn",
            "App luôn cho xem trước thay đổi và chỉ lưu sau khi điền xong.",
        ),
        (
            "CM / Production / Indirect",
            "Chọn tên trong danh sách. CM và Indirect dùng USD. Production tự "
            "đặt Minutes = 1. Dòng không chọn tên sẽ không được thêm.",
        ),
    ]
    for row, (label, value) in enumerate(rows, 3):
        label_cell = ws.cell(row=row, column=1, value=label)
        label_cell.font = Font(bold=True)
        label_cell.alignment = Alignment(vertical="top", wrap_text=True)
        ws.cell(row=row, column=2, value=_excel_safe(value))
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
        ws.cell(row=row, column=2).alignment = Alignment(
            horizontal="left",
            vertical="top",
            wrap_text=True,
        )
        ws.row_dimensions[row].height = 42 if row >= 6 else 24
        if label == "Cách dùng":
            ws.cell(row=row, column=2).fill = _INPUT_FILL
    for column, width in enumerate((23, 18, 18, 18, 18, 18), 1):
        ws.column_dimensions[get_column_letter(column)].width = width
    ws.sheet_view.showGridLines = False


def _base_field_key(value: Any) -> str:
    return re.sub(r"__\d+$", "", _text(value)).casefold()


def _unique_values(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        folded = text.casefold()
        if not text or folded in seen:
            continue
        seen.add(folded)
        output.append(text)
    return output


def _split_wfx_multiselect(value: Any) -> list[str]:
    """Tách chuỗi WFX theo dấu phẩy nhưng giữ nguyên dấu phẩy trong ngoặc."""
    text = _text(value)
    if not text:
        return []
    output: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        elif character in {",", "|"} and depth == 0:
            token = text[start:index].strip()
            if token:
                output.append(token)
            start = index + 1
    token = text[start:].strip()
    if token:
        output.append(token)
    return output


def _form_dropdown_options(
    document: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Tạo lookup chung; option Material được gắn riêng theo từng item."""
    fields = list(document.get("fields") or ())

    def matching(field_key: str) -> list[Mapping[str, Any]]:
        wanted = field_key.casefold()
        return [
            field
            for field in fields
            if _base_field_key(field.get("field_key")) == wanted
        ]

    purchase_officers = matching("colPurchaseOfficer")
    return {
        "Color Dep.": _unique_values(
            [
                "[None]",
                "[Table]",
                "[Body Type]",
                "[Base Colors]",
            ]
        ),
        "Size Dep.": _unique_values(
            [
                "[None]",
                "[Table]",
                "[Body Type]",
            ]
        ),
        "Purchase Officer": _unique_values(
            [
                *(field.get("value") for field in purchase_officers),
                *(
                    option
                    for field in purchase_officers
                    for option in field.get("options") or ()
                ),
            ]
        ),
    }


def _add_form_dropdowns(
    ws: Any,
    document: Mapping[str, Any],
    *,
    last_row: int,
) -> int:
    """Gắn dropdown bằng lookup columns ẩn, không tạo sheet thứ ba."""
    option_sets = _form_dropdown_options(document)
    lookup_column = len(FORM_COLUMNS) + 1
    for label, options in option_sets.items():
        if not options:
            continue
        column_letter = get_column_letter(lookup_column)
        for row, option in enumerate(options, 2):
            ws.cell(row=row, column=lookup_column, value=_excel_safe(option))
        ws.column_dimensions[column_letter].hidden = True
        validation = DataValidation(
            type="list",
            formula1=f"=${column_letter}$2:${column_letter}${len(options) + 1}",
            allow_blank=True,
        )
        # Cho phép gõ mapping mới hoặc nhiều giá trị bằng dấu | khi lookup live
        # chưa có đủ màu/size. Dropdown vẫn là đường nhập mặc định.
        validation.showErrorMessage = False
        validation.promptTitle = "WFX Smart"
        validation.prompt = (
            "Chọn từ danh sách; có thể gõ nhiều giá trị, ngăn bằng dấu |."
        )
        validation.showInputMessage = True
        ws.add_data_validation(validation)
        target_column = FORM_COLUMNS.index(label) + 1
        target_letter = get_column_letter(target_column)
        validation.add(f"{target_letter}2:{target_letter}{last_row}")
        lookup_column += 1
    return lookup_column


def _add_item_option_dropdowns(
    ws: Any,
    document: Mapping[str, Any],
    row_by_item: Mapping[tuple[str, str], int],
    *,
    lookup_column: int,
) -> None:
    """Gắn dropdown Material Color/Size đúng option của từng Article row."""
    wanted_fields = {
        "colmaterialcolorlist": "Material Color",
        "colmaterialsizelist": "Material Size",
    }
    for field in document.get("fields") or ():
        base_key = _base_field_key(field.get("field_key"))
        label = wanted_fields.get(base_key)
        if label is None:
            continue
        row = row_by_item.get(
            (
                _text(field.get("section_key")).casefold(),
                _text(field.get("item_key")).casefold(),
            )
        )
        options = _unique_values(
            [
                *(field.get("options") or ()),
                *_split_wfx_multiselect(field.get("value")),
            ]
        )
        if row is None or not options:
            continue
        lookup_letter = get_column_letter(lookup_column)
        for option_row, option in enumerate(options, 2):
            ws.cell(
                row=option_row,
                column=lookup_column,
                value=_excel_safe(option),
            )
        ws.column_dimensions[lookup_letter].hidden = True
        validation = DataValidation(
            type="list",
            formula1=(
                f"=${lookup_letter}$2:"
                f"${lookup_letter}${len(options) + 1}"
            ),
            allow_blank=True,
        )
        validation.showErrorMessage = False
        validation.promptTitle = f"{label} của Article"
        validation.prompt = (
            "Chọn một giá trị; nhiều giá trị có thể nhập theo đúng chuỗi WFX."
        )
        validation.showInputMessage = True
        ws.add_data_validation(validation)
        target_letter = get_column_letter(FORM_COLUMNS.index(label) + 1)
        validation.add(f"{target_letter}{row}")
        lookup_column += 1


def _add_special_article_dropdowns(
    ws: Any,
    document: Mapping[str, Any],
    layout: _CostingFormLayout,
    *,
    lookup_column: int,
) -> int:
    """Gắn danh sách nhà máy/quy trình/chi phí cho từng block đặc biệt."""
    article_name_letter = get_column_letter(FORM_COLUMNS.index("Article Name") + 1)
    ordered_sections = sorted(
        document["sections"],
        key=lambda value: value["row_order"],
    )
    for section, rows in zip(ordered_sections, layout.section_rows, strict=True):
        if _section_item_type(section) != "cost_line":
            continue
        options = _unique_values(section.get("article_options") or ())
        if not options or not rows:
            continue
        lookup_letter = get_column_letter(lookup_column)
        for option_row, option in enumerate(options, 2):
            ws.cell(option_row, lookup_column, _excel_safe(option))
        ws.column_dimensions[lookup_letter].hidden = True
        validation = DataValidation(
            type="list",
            formula1=(
                f"=${lookup_letter}$2:"
                f"${lookup_letter}${len(options) + 1}"
            ),
            allow_blank=True,
        )
        validation.showErrorMessage = False
        validation.promptTitle = "Chọn từ WFX"
        validation.prompt = "Chọn tên đã quét; có thể gõ để tìm trong Excel."
        validation.showInputMessage = True
        ws.add_data_validation(validation)
        validation.add(
            f"{article_name_letter}{min(rows)}:{article_name_letter}{max(rows)}"
        )
        lookup_column += 1
    return lookup_column


def _add_material_article_dropdowns(
    ws: Any,
    document: Mapping[str, Any],
    layout: _CostingFormLayout,
    *,
    lookup_column: int,
) -> int:
    """Dropdown Article Code/Name từ thư viện server/cache."""
    ordered_sections = sorted(
        document["sections"],
        key=lambda value: value["row_order"],
    )
    validation_cache: dict[
        tuple[tuple[str, str], ...],
        tuple[DataValidation, DataValidation, str, str, int],
    ] = {}
    code_column = FORM_COLUMNS.index("Article Code") + 1
    name_column = FORM_COLUMNS.index("Article Name") + 1
    code_target_letter = get_column_letter(code_column)
    name_target_letter = get_column_letter(name_column)
    for section, rows in zip(ordered_sections, layout.section_rows, strict=True):
        if _section_item_type(section) == "cost_line" or not rows:
            continue
        pairs = _article_lookup_options(section.get("article_lookup_options"))
        if not pairs:
            codes = _unique_values(section.get("article_code_options") or ())
            names = _unique_values(section.get("article_name_options") or ())
            pairs = [
                {"article_code": code, "article_name": names[index]}
                for index, code in enumerate(codes)
                if index < len(names)
            ]
        if not pairs:
            continue
        signature = tuple(
            (option["article_code"], option["article_name"])
            for option in pairs
        )
        target_code_range = (
            f"{code_target_letter}{min(rows)}:"
            f"{code_target_letter}{max(rows)}"
        )
        target_name_range = (
            f"{name_target_letter}{min(rows)}:"
            f"{name_target_letter}{max(rows)}"
        )
        cached = validation_cache.get(signature)
        if cached is None:
            lookup_code_letter = get_column_letter(lookup_column)
            lookup_name_letter = get_column_letter(lookup_column + 1)
            for option_row, option in enumerate(pairs, 2):
                ws.cell(
                    option_row,
                    lookup_column,
                    _excel_safe(option["article_code"]),
                )
                ws.cell(
                    option_row,
                    lookup_column + 1,
                    _excel_safe(option["article_name"]),
                )
            ws.column_dimensions[lookup_code_letter].hidden = True
            ws.column_dimensions[lookup_name_letter].hidden = True
            last_option_row = len(pairs) + 1

            def validation_for(
                letter: str,
                label: str,
                option_last_row: int = last_option_row,
            ) -> DataValidation:
                validation = DataValidation(
                    type="list",
                    formula1=(
                        f"=${letter}$2:${letter}${option_last_row}"
                    ),
                    allow_blank=True,
                )
                validation.showErrorMessage = False
                validation.promptTitle = f"{label} từ thư viện"
                validation.prompt = (
                    "Danh sách tự đồng bộ từ server; vẫn có thể nhập tay."
                )
                validation.showInputMessage = True
                ws.add_data_validation(validation)
                return validation

            code_validation = validation_for(
                lookup_code_letter,
                "Article Code",
            )
            name_validation = validation_for(
                lookup_name_letter,
                "Article Name",
            )
            cached = (
                code_validation,
                name_validation,
                lookup_code_letter,
                lookup_name_letter,
                last_option_row,
            )
            validation_cache[signature] = cached
            lookup_column += 2
        (
            code_validation,
            name_validation,
            lookup_code_letter,
            lookup_name_letter,
            last_option_row,
        ) = cached
        code_validation.add(target_code_range)
        name_validation.add(target_name_range)
        available_codes = {
            option["article_code"].casefold() for option in pairs
        }
        for row in rows:
            current_code = _text(ws.cell(row, code_column).value)
            current_name = _text(ws.cell(row, name_column).value)
            if current_name and current_code.casefold() not in available_codes:
                continue
            ws.cell(row, name_column).value = (
                f'=IFERROR(INDEX(${lookup_name_letter}$2:'
                f'${lookup_name_letter}${last_option_row},'
                f'MATCH({code_target_letter}{row},'
                f'${lookup_code_letter}$2:'
                f'${lookup_code_letter}${last_option_row},0)),"")'
            )
    return lookup_column


@dataclass(frozen=True)
class _CostingFormLayout:
    section_rows: list[list[int]]
    template_rows: list[tuple[int, str]]
    row_by_item: dict[tuple[str, str], int]


def _form_field_index(
    document: Mapping[str, Any],
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    return {
        (
            field["section_key"].casefold(),
            field["item_key"].casefold(),
            _base_field_key(field["field_key"]),
        ): field
        for field in document["fields"]
    }


def _form_items_by_section(
    document: Mapping[str, Any],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in document["items"]:
        grouped.setdefault(item["section_key"].casefold(), []).append(item)
    for items in grouped.values():
        items.sort(key=lambda value: value["row_order"])
    return grouped


def _form_row_values(
    section: Mapping[str, Any],
    item: Mapping[str, Any] | None,
    row_order: int,
    field_by_item: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> list[Any]:
    section_key = str(section["section_key"])
    item_key = "" if item is None else str(item["item_key"])
    values: list[Any] = [
        section["name"],
        "" if item is None or item["action"] == "UPSERT" else item["action"],
        "" if item is None else item["article_code"],
        "" if item is None else item["article_name"],
    ]
    for definition in STANDARD_ITEM_FIELDS:
        field_key = _form_field_key(definition, section)
        field = field_by_item.get(
            (
                section_key.casefold(),
                item_key.casefold(),
                field_key.casefold(),
            )
        )
        value = "" if field is None else field["value"]
        token = _standard_section_token(section)
        if definition["label"] == "Minutes" and token == "productioncosts":
            value = 1
        elif definition["label"] == "Curr." and token in {
            "cmcosts",
            "indirectcosts",
        }:
            value = "USD"
        values.append(value)
    values.extend([section_key, item_key, row_order, _section_item_type(section)])
    return values


def _write_form_data_rows(
    ws: Any,
    document: Mapping[str, Any],
) -> _CostingFormLayout:
    field_by_item = _form_field_index(document)
    items_by_section = _form_items_by_section(document)
    section_rows: list[list[int]] = []
    template_rows: list[tuple[int, str]] = []
    row_by_item: dict[tuple[str, str], int] = {}
    output_row = 2
    for section in sorted(
        document["sections"],
        key=lambda value: value["row_order"],
    ):
        section_key = str(section["section_key"])
        section_items = items_by_section.get(section_key.casefold(), [])
        highest_row_order = max(
            (int(item["row_order"]) for item in section_items),
            default=0,
        )
        current_section_rows: list[int] = []
        rows_to_write = [
            *section_items,
            *([None] * _template_row_count(section)),
        ]
        for template_index, item in enumerate(rows_to_write, 1):
            is_template = item is None
            row_order = (
                highest_row_order + template_index - len(section_items)
                if is_template
                else int(item["row_order"])
            )
            for column, value in enumerate(
                _form_row_values(
                    section,
                    item,
                    row_order,
                    field_by_item,
                ),
                1,
            ):
                ws.cell(
                    row=output_row,
                    column=column,
                    value=_excel_safe(value),
                )
            if is_template:
                template_rows.append((output_row, str(section["name"])))
            else:
                row_by_item[
                    (section_key.casefold(), str(item["item_key"]).casefold())
                ] = output_row
            current_section_rows.append(output_row)
            output_row += 1
        section_rows.append(current_section_rows)
    return _CostingFormLayout(section_rows, template_rows, row_by_item)


def _form_column_widths() -> dict[int, int]:
    widths = {1: 24, 2: 12, 3: 20, 4: 30}
    special_widths = {
        "Material Color": 32,
        "Material Size": 28,
        "Color Mapping": 44,
        "Size Mapping": 44,
        "Cons. Qty. Incl. Waste": 24,
        "Value in (USD)": 20,
        "Remarks": 28,
        "Supplier": 25,
        "Placement": 20,
        "Purchase Officer": 20,
        "Shrinkage %(LxW)": 20,
    }
    for offset, definition in enumerate(
        STANDARD_ITEM_FIELDS,
        len(FORM_BASE_COLUMNS) + 1,
    ):
        widths[offset] = special_widths.get(str(definition["label"]), 16)
    return widths


def _style_formula_columns(ws: Any, last_row: int) -> set[int]:
    read_only_definitions = [
        definition
        for definition in STANDARD_ITEM_FIELDS
        if definition.get("read_only")
    ]
    read_only_columns: set[int] = set()
    for definition in read_only_definitions:
        column = FORM_COLUMNS.index(str(definition["label"])) + 1
        read_only_columns.add(column)
        header = ws.cell(row=1, column=column)
        header.fill = _READ_ONLY_HEADER_FILL
        header.font = _HEADER_FONT
        for row in range(2, last_row + 1):
            cell = ws.cell(row=row, column=column)
            cell.fill = _READ_ONLY_FILL
            cell.font = Font(color="991B1B")
        formula = (
            "Cons. Qty. × (1 + Waste %/100)"
            if definition["field_key"] == "colConsPlusWastageQty"
            else "Rate × Cons. Qty. Incl. Waste"
        )
        header.comment = Comment(
            f"Cột công thức WFX, chỉ đọc: {formula}.",
            "WFX Smart",
        )
    return read_only_columns


def _write_costing_formulas(ws: Any, last_row: int) -> None:
    columns = {
        label: FORM_COLUMNS.index(label) + 1
        for label in (
            "Cons. Qty.",
            "Waste %",
            "Cons. Qty. Incl. Waste",
            "Rate",
            "Value in (USD)",
        )
    }
    for row in range(2, last_row + 1):
        cons_ref = f"{get_column_letter(columns['Cons. Qty.'])}{row}"
        waste_ref = f"{get_column_letter(columns['Waste %'])}{row}"
        cons_incl_ref = (
            f"{get_column_letter(columns['Cons. Qty. Incl. Waste'])}{row}"
        )
        rate_ref = f"{get_column_letter(columns['Rate'])}{row}"
        cons_incl_cell = ws.cell(
            row=row,
            column=columns["Cons. Qty. Incl. Waste"],
        )
        value_cell = ws.cell(row=row, column=columns["Value in (USD)"])
        cons_incl_cell.value = (
            f'=IF({cons_ref}="","",{cons_ref}*'
            f'(1+IF({waste_ref}="",0,{waste_ref})/100))'
        )
        value_cell.value = (
            f'=IF(OR({rate_ref}="",{cons_incl_ref}=""),"",'
            f"{rate_ref}*{cons_incl_ref})"
        )
        cons_incl_cell.number_format = "0.0000"
        value_cell.number_format = "0.0000"


def _add_dependency_mapping_comments(
    ws: Any,
    document: Mapping[str, Any],
    row_by_item: Mapping[tuple[str, str], int],
) -> None:
    mapping_columns = {
        "colcolordependencymapping": FORM_COLUMNS.index("Color Mapping") + 1,
        "colsizedependencymapping": FORM_COLUMNS.index("Size Mapping") + 1,
    }
    for field in document.get("fields") or ():
        column = mapping_columns.get(_base_field_key(field.get("field_key")))
        if column is None:
            continue
        row = row_by_item.get(
            (
                _text(field.get("section_key")).casefold(),
                _text(field.get("item_key")).casefold(),
            )
        )
        if row is None:
            continue
        choices = _unique_values(field.get("options") or ())
        detail = "\n".join(choices[:100]) or "Chưa scan được option Style."
        cell = ws.cell(row=row, column=column)
        cell.comment = Comment(
            "Mỗi dòng: Material => Style 1 | Style 2\n\n"
            "Các lựa chọn Style đã scan:\n" + detail,
            "WFX Smart",
        )
        cell.alignment = Alignment(vertical="top", wrap_text=True)


def _style_form_sections(
    ws: Any,
    section_rows: Sequence[Sequence[int]],
    visible_column_count: int,
) -> None:
    for rows in section_rows:
        if not rows:
            continue
        for row in rows:
            section_cell = ws.cell(row=row, column=1)
            section_cell.fill = _SUBHEADER_FILL
            section_cell.font = Font(color="0F5660", bold=True)
        for column in range(1, visible_column_count + 1):
            ws.cell(row=rows[0], column=column).border = _SECTION_BORDER


def _style_form_templates(
    ws: Any,
    template_rows: Sequence[tuple[int, str]],
    visible_column_count: int,
    read_only_columns: set[int],
) -> None:
    article_code_column = FORM_COLUMNS.index("Article Code") + 1
    article_name_column = FORM_COLUMNS.index("Article Name") + 1
    for row, section_name in template_rows:
        ws.cell(row=row, column=1).font = Font(
            color="0F5660",
            bold=True,
            italic=True,
        )
        for column in range(2, visible_column_count + 1):
            if column not in read_only_columns:
                ws.cell(row=row, column=column).fill = _TEMPLATE_INPUT_FILL
        section = {"section_key": section_name, "name": section_name}
        is_cost_line = _section_item_type(section) == "cost_line"
        hint = (
            f"Chọn Article Name cho {section_name}; để trống nếu không dùng."
            if is_cost_line
            else (
                f"Dòng thêm Article mới cho {section_name}. "
                "Nhập Article Code hoặc Article Name; để trống nếu không dùng."
            )
        )
        ws.cell(row=row, column=article_code_column).comment = Comment(
            hint,
            "WFX Smart",
        )
        ws.cell(row=row, column=article_name_column).comment = Comment(
            hint,
            "WFX Smart",
        )


def _finish_costing_form(
    ws: Any,
    layout: _CostingFormLayout,
    visible_column_count: int,
) -> None:
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = (
        f"A1:{get_column_letter(visible_column_count)}{max(1, ws.max_row)}"
    )
    ws.row_dimensions[1].height = 34
    for row in range(2, ws.max_row + 1):
        ws.row_dimensions[row].height = 23
    for mapping_label in ("Color Mapping", "Size Mapping"):
        column = FORM_COLUMNS.index(mapping_label) + 1
        for row in layout.row_by_item.values():
            line_count = str(ws.cell(row=row, column=column).value or "").count(
                "\n"
            ) + 1
            if line_count > 1:
                ws.row_dimensions[row].height = max(
                    ws.row_dimensions[row].height or 23,
                    min(120, 16 * line_count),
                )
    for column in range(visible_column_count + 1, len(FORM_COLUMNS) + 1):
        ws.column_dimensions[get_column_letter(column)].hidden = True
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = "0F766E"


def _write_costing_form(
    workbook: Workbook,
    document: Mapping[str, Any],
) -> None:
    """Ghi form một sheet với bộ cột cố định và dòng thêm Article sẵn có."""
    ws = workbook.create_sheet(FORM_SHEET)
    _set_header(ws, 1, FORM_COLUMNS)
    visible_column_count = len(FORM_COLUMNS) - len(FORM_TECH_COLUMNS)
    layout = _write_form_data_rows(ws, document)

    form_data_last_row = ws.max_row
    last_row = max(form_data_last_row, 200)
    action_validation = DataValidation(
        type="list",
        formula1='"DELETE"',
        allow_blank=True,
    )
    ws.add_data_validation(action_validation)
    action_validation.add(f"B2:B{last_row}")
    next_lookup_column = _add_form_dropdowns(
        ws,
        document,
        last_row=last_row,
    )
    next_lookup_column = _add_special_article_dropdowns(
        ws,
        document,
        layout,
        lookup_column=next_lookup_column,
    )
    next_lookup_column = _add_material_article_dropdowns(
        ws,
        document,
        layout,
        lookup_column=next_lookup_column,
    )
    _add_item_option_dropdowns(
        ws,
        document,
        layout.row_by_item,
        lookup_column=next_lookup_column,
    )
    for offset, definition in enumerate(
        STANDARD_ITEM_FIELDS,
        len(FORM_BASE_COLUMNS) + 1,
    ):
        ws.cell(row=1, column=offset).comment = Comment(
            f"WFX Field Key: {definition['field_key']}",
            "WFX Smart",
        )
    _finish_sheet(
        ws,
        _form_column_widths(),
        editable_columns=range(2, visible_column_count + 1),
    )
    read_only_columns = _style_formula_columns(ws, form_data_last_row)
    _write_costing_formulas(ws, form_data_last_row)
    _add_dependency_mapping_comments(ws, document, layout.row_by_item)
    _style_form_sections(ws, layout.section_rows, visible_column_count)
    _style_form_templates(
        ws,
        layout.template_rows,
        visible_column_count,
        read_only_columns,
    )
    _finish_costing_form(ws, layout, visible_column_count)


def write_costing_xlsx(document: Mapping[str, Any], path: str | Path) -> Path:
    normalized = workbook_document(document)
    target = _preflight_path(path, must_exist=False)
    if target.suffix.casefold() != ".xlsx":
        raise CostingWorkbookError(
            "COSTING_FILE_TYPE_UNSUPPORTED",
            "Đường dẫn export XLSX phải kết thúc bằng .xlsx.",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.calculation.calcMode = "auto"
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    _write_guide(workbook, normalized)
    _write_costing_form(workbook, normalized)
    workbook.save(target)
    return target


def write_costing_file(document: Mapping[str, Any], path: str | Path) -> Path:
    target = _preflight_path(path, must_exist=False)
    return write_costing_xlsx(document, target)
