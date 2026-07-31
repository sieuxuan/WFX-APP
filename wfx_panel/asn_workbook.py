"""Ghép hai workbook report Sale ASN thành một file Excel duy nhất."""

from __future__ import annotations

from copy import copy
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet


class ASNWorkbookError(ValueError):
    """Workbook report WFX không thể đọc hoặc ghép an toàn."""


def _safe_sheet_title(value: str, existing: set[str]) -> str:
    cleaned = "".join(
        " " if character in "[]:*?/\\" else character for character in value
    )
    cleaned = " ".join(cleaned.split()).strip(" '") or "Report"
    cleaned = cleaned[:31].rstrip()
    candidate = cleaned
    suffix = 2
    while candidate.casefold() in existing:
        tail = f" ({suffix})"
        candidate = f"{cleaned[: 31 - len(tail)].rstrip()}{tail}"
        suffix += 1
    existing.add(candidate.casefold())
    return candidate


def _copy_sheet(source: Worksheet, target: Worksheet) -> None:
    """Copy nội dung và layout report mà không thay đổi giá trị."""
    for row in source.iter_rows():
        for source_cell in row:
            target_cell = target.cell(
                row=source_cell.row,
                column=source_cell.column,
                value=source_cell.value,
            )
            if source_cell.has_style:
                # StyleArray mang index của workbook nguồn; gán thẳng sang
                # workbook khác sẽ tạo XLSX mở được nhưng lỗi style index.
                target_cell.font = copy(source_cell.font)
                target_cell.fill = copy(source_cell.fill)
                target_cell.border = copy(source_cell.border)
                target_cell.alignment = copy(source_cell.alignment)
                target_cell.number_format = source_cell.number_format
                target_cell.protection = copy(source_cell.protection)
            if source_cell.hyperlink:
                target_cell._hyperlink = copy(source_cell.hyperlink)
            if source_cell.comment:
                target_cell.comment = copy(source_cell.comment)

    for key, dimension in source.row_dimensions.items():
        copied = copy(dimension)
        copied.worksheet = target
        target.row_dimensions[key] = copied
    for key, dimension in source.column_dimensions.items():
        copied = copy(dimension)
        copied.worksheet = target
        target.column_dimensions[key] = copied
    for merged_range in source.merged_cells.ranges:
        target.merge_cells(str(merged_range))

    target.sheet_format = copy(source.sheet_format)
    target.sheet_properties = copy(source.sheet_properties)
    target.page_margins = copy(source.page_margins)
    target.page_setup = copy(source.page_setup)
    target.print_options = copy(source.print_options)
    target.protection = copy(source.protection)
    target.views = copy(source.views)
    target.scenarios = copy(source.scenarios)
    target.sheet_state = source.sheet_state
    target.freeze_panes = source.freeze_panes
    target.auto_filter = copy(source.auto_filter)
    target.data_validations = copy(source.data_validations)
    target.row_breaks = copy(source.row_breaks)
    target.col_breaks = copy(source.col_breaks)
    target.print_title_cols = source.print_title_cols
    target.print_title_rows = source.print_title_rows
    target.print_area = source.print_area
    for attribute in (
        "oddHeader",
        "oddFooter",
        "evenHeader",
        "evenFooter",
        "firstHeader",
        "firstFooter",
    ):
        setattr(target, attribute, copy(getattr(source, attribute)))

    for image in source._images:
        target.add_image(copy(image), image.anchor)
    for chart in source._charts:
        target.add_chart(copy(chart), chart.anchor)


def merge_sale_asn_reports(
    packing_list_path: str | Path,
    buyer_invoice_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Ghép toàn bộ sheet Packing List và Buyer Invoice vào XLSX."""
    packing_path = Path(packing_list_path).expanduser().resolve()
    buyer_path = Path(buyer_invoice_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if target.suffix.casefold() != ".xlsx":
        raise ASNWorkbookError("File Sale ASN phải có đuôi .xlsx.")
    for source in (packing_path, buyer_path):
        if not source.is_file() or source.stat().st_size <= 0:
            raise ASNWorkbookError(f"Không đọc được report: {source.name}.")

    try:
        packing_book = load_workbook(packing_path, data_only=False)
        buyer_book = load_workbook(buyer_path, data_only=False)
    except Exception as error:
        raise ASNWorkbookError(
            f"Report WFX không phải workbook Excel hợp lệ: {error}"
        ) from error

    # Dùng nguyên workbook Packing List làm nền. Như vậy sheet Packing
    # List không bị dựng lại từng cell/dimension và giữ được toàn bộ
    # metadata OOXML mà openpyxl hỗ trợ (print layout, drawing, view...).
    output = packing_book
    existing: set[str] = set()
    try:
        for index, packing_sheet in enumerate(output.worksheets, start=1):
            preferred = (
                "Packing List"
                if len(output.worksheets) == 1
                else f"Packing List {index}"
            )
            packing_sheet.title = _safe_sheet_title(preferred, existing)

        for index, source_sheet in enumerate(buyer_book.worksheets, start=1):
            preferred = (
                "Buyer Invoice"
                if len(buyer_book.worksheets) == 1
                else f"Buyer Invoice {index}"
            )
            target_sheet = output.create_sheet(
                _safe_sheet_title(preferred, existing)
            )
            try:
                _copy_sheet(source_sheet, target_sheet)
            except Exception:
                output.remove(target_sheet)
                raise
        if not output.worksheets:
            raise ASNWorkbookError("Hai report Sale ASN không có sheet dữ liệu.")
        target.parent.mkdir(parents=True, exist_ok=True)
        output.save(target)
        # Mở lại ngay để không trả file ZIP/XLSX hỏng cho user.
        verified = load_workbook(target, read_only=True, data_only=False)
        verified.close()
    except ASNWorkbookError:
        raise
    except Exception as error:
        raise ASNWorkbookError(f"Không ghép được hai report Sale ASN: {error}") from error
    finally:
        buyer_book.close()
        output.close()
    return target
