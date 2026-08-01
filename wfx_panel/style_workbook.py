"""Form Excel và validation cho luồng tạo Style Apparel hàng loạt."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

STYLE_SHEET = "Tạo Style"
GUIDE_SHEET = "Hướng dẫn"
MAX_STYLE_ROWS = 500
MAX_STYLE_FILE_BYTES = 15 * 1024 * 1024

STYLE_COLUMNS = (
    "Type",
    "Style copy",
    "Material Type",
    "Buyer",
    "Division",
    "Product Group",
    "Sub-Category",
    "Color Card",
    "Size Range",
    "Season",
    "Buyer Style Ref.",
    "Internal Style Ref",
)

_FIELD_KEYS = (
    "type",
    "style_copy",
    "material_type",
    "buyer",
    "division",
    "product_group",
    "sub_category",
    "color_card",
    "size_range",
    "season",
    "buyer_style_ref",
    "internal_style_ref",
)


class StyleWorkbookError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        errors: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.errors = errors


@dataclass(frozen=True)
class StyleImportRow:
    source_row: int
    type: str
    style_copy: str
    material_type: str
    buyer: str
    division: str
    product_group: str
    sub_category: str
    color_card: str
    size_range: str
    season: str
    buyer_style_ref: str
    internal_style_ref: str

    def automation_payload(self) -> dict[str, str | int]:
        return {
            key: getattr(self, key)
            for key in ("source_row", *_FIELD_KEYS)
        }


def _text(value: object) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def _assert_safe_xlsx(path: Path) -> None:
    if path.suffix.casefold() != ".xlsx":
        raise StyleWorkbookError(
            "STYLE_FILE_TYPE_UNSUPPORTED",
            "Tạo Style hàng loạt chỉ hỗ trợ file .xlsx.",
        )
    if not path.is_file():
        raise StyleWorkbookError(
            "STYLE_FILE_NOT_FOUND",
            "Không tìm thấy file Tạo Style đã chọn.",
        )
    if path.stat().st_size > MAX_STYLE_FILE_BYTES:
        raise StyleWorkbookError(
            "STYLE_FILE_TOO_LARGE",
            "File Tạo Style vượt quá giới hạn 15 MB.",
        )
    try:
        with ZipFile(path) as archive:
            names = {name.casefold() for name in archive.namelist()}
    except (BadZipFile, OSError) as error:
        raise StyleWorkbookError(
            "STYLE_FILE_INVALID",
            "File đã chọn không phải workbook Excel hợp lệ.",
        ) from error
    if any(name.endswith("vbaproject.bin") for name in names):
        raise StyleWorkbookError(
            "STYLE_FILE_UNSAFE",
            "File Tạo Style không được chứa macro.",
        )


def write_style_template(output_path: str | Path) -> Path:
    """Tạo form nhập liệu ổn định, không chứa selector hay macro."""
    target = Path(output_path).expanduser().resolve()
    if target.suffix.casefold() != ".xlsx":
        target = target.with_suffix(".xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    guide = workbook.active
    guide.title = GUIDE_SHEET
    guide.sheet_view.showGridLines = False
    guide.column_dimensions["A"].width = 24
    guide.column_dimensions["B"].width = 92
    guide.append(["WFX Smart", "Tạo Style Apparel hàng loạt"])
    guide.append(["Bước 1", "Trong tab Catalog > Tạo Style, chọn đúng một Group."])
    guide.append(["Bước 2", "Điền dữ liệu trong sheet Tạo Style rồi chọn Import."])
    guide.append([
        "Bước 3",
        "App chuẩn bị từng dòng trên WFX và luôn dừng trước Save. "
        "Kiểm tra rồi tự bấm Save trên WFX trước khi sang dòng kế tiếp.",
    ])
    guide.append([
        "Type",
        "New để tạo mới hoàn toàn; Copy để tìm Style nguồn và Copy as Variant.",
    ])
    guide.append([
        "Style copy",
        "Bắt buộc với Copy. Mã bắt đầu SWN/SKN được tìm bằng Article Code; "
        "giá trị khác được tìm bằng Buyer Reference.",
    ])
    guide.append([
        "Ô trống",
        "Với Copy, ô trống giữ nguyên dữ liệu nguồn. Với New, các cột dữ liệu "
        "từ Material Type đến Internal Style Ref đều bắt buộc.",
    ])
    guide.append([
        "Mặc định",
        "Purchase UOM = Pcs; Price Per = Article; "
        "Color Definition = Single Colors.",
    ])
    guide.append([
        "An toàn",
        "App không tự Save Style. Không đóng/chuyển màn WFX khi đang chuẩn bị dòng.",
    ])
    for cell in guide[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="214A66")
    for row in guide.iter_rows(min_row=2, max_col=2):
        row[0].font = Font(bold=True, color="214A66")
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
    guide.freeze_panes = "A2"

    sheet = workbook.create_sheet(STYLE_SHEET)
    sheet.sheet_view.showGridLines = False
    sheet.append(STYLE_COLUMNS)
    # Phát hành sẵn các dòng trống để dropdown/format hoạt động ngay trong Excel.
    for _ in range(100):
        sheet.append([""] * len(STYLE_COLUMNS))
    widths = (13, 22, 18, 24, 20, 22, 22, 22, 22, 18, 24, 24)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="214A66")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 24
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:L{MAX_STYLE_ROWS + 1}"
    table = Table(displayName="StyleUpload", ref="A1:L101")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)

    type_validation = DataValidation(
        type="list",
        formula1='"New,Copy"',
        allow_blank=False,
    )
    material_validation = DataValidation(
        type="list",
        formula1='"KNIT,WOVEN"',
        allow_blank=True,
    )
    sheet.add_data_validation(type_validation)
    sheet.add_data_validation(material_validation)
    type_validation.add(f"A2:A{MAX_STYLE_ROWS + 1}")
    material_validation.add(f"C2:C{MAX_STYLE_ROWS + 1}")
    warning_fill = PatternFill("solid", fgColor="FDE9D9")
    sheet.conditional_formatting.add(
        f"B2:B{MAX_STYLE_ROWS + 1}",
        FormulaRule(formula=['AND($A2="Copy",$B2="")'], fill=warning_fill),
    )
    sheet.conditional_formatting.add(
        f"C2:L{MAX_STYLE_ROWS + 1}",
        FormulaRule(formula=['AND($A2="New",C2="")'], fill=warning_fill),
    )
    workbook.save(target)
    workbook.close()
    return target


def read_style_workbook(source_path: str | Path) -> list[StyleImportRow]:
    """Đọc và validate toàn bộ hàng trước khi mở WFX."""
    source = Path(source_path).expanduser().resolve()
    _assert_safe_xlsx(source)
    try:
        workbook = load_workbook(source, read_only=True, data_only=False)
    except Exception as error:
        raise StyleWorkbookError(
            "STYLE_FILE_INVALID",
            "Không đọc được workbook Tạo Style.",
        ) from error
    try:
        if STYLE_SHEET not in workbook.sheetnames:
            raise StyleWorkbookError(
                "STYLE_TEMPLATE_SHEET_MISSING",
                f"File phải có sheet {STYLE_SHEET}.",
            )
        sheet = workbook[STYLE_SHEET]
        headers = tuple(_text(cell.value) for cell in sheet[1][: len(STYLE_COLUMNS)])
        if headers != STYLE_COLUMNS:
            raise StyleWorkbookError(
                "STYLE_FILE_HEADERS_INVALID",
                "Header sheet Tạo Style không đúng form chuẩn.",
                ("Cần đúng thứ tự: " + " | ".join(STYLE_COLUMNS),),
            )
        rows: list[StyleImportRow] = []
        errors: list[str] = []
        for source_row, cells in enumerate(
            sheet.iter_rows(min_row=2, max_col=len(STYLE_COLUMNS)),
            start=2,
        ):
            values: list[str] = []
            formula = False
            for cell in cells:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    formula = True
                values.append(_text(cell.value))
            if not any(values):
                continue
            if len(rows) >= MAX_STYLE_ROWS:
                errors.append(f"Vượt quá {MAX_STYLE_ROWS} dòng dữ liệu.")
                break
            if formula:
                errors.append(f"Dòng {source_row}: không được dùng công thức.")
                continue
            kind = values[0].casefold()
            if kind not in {"new", "copy"}:
                errors.append(f"Dòng {source_row}: Type phải là New hoặc Copy.")
                continue
            normalized_kind = "New" if kind == "new" else "Copy"
            if normalized_kind == "Copy" and not values[1]:
                errors.append(f"Dòng {source_row}: Copy cần có Style copy.")
                continue
            if normalized_kind == "New":
                missing = [
                    STYLE_COLUMNS[index]
                    for index, value in enumerate(values[2:], start=2)
                    if not value
                ]
                if missing:
                    errors.append(
                        f"Dòng {source_row}: New còn thiếu {', '.join(missing)}."
                    )
                    continue
            material = values[2].upper()
            if material and material not in {"KNIT", "WOVEN"}:
                errors.append(
                    f"Dòng {source_row}: Material Type phải là KNIT hoặc WOVEN."
                )
                continue
            payload = [normalized_kind, values[1], material, *values[3:]]
            rows.append(
                StyleImportRow(
                    source_row=source_row,
                    **dict(zip(_FIELD_KEYS, payload, strict=True)),
                )
            )
        if errors:
            raise StyleWorkbookError(
                "STYLE_FILE_VALIDATION_FAILED",
                f"File Tạo Style có {len(errors)} lỗi.",
                tuple(errors[:50]),
            )
        if not rows:
            raise StyleWorkbookError(
                "STYLE_FILE_EMPTY",
                "File Tạo Style chưa có dòng dữ liệu.",
            )
        return rows
    finally:
        workbook.close()
