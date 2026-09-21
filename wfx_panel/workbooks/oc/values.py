"""Ép và kiểm tra giá trị từng ô trước khi tin vào cả file.

Ngày phải nghiêm ngặt Buyer Order Date < Raw Material ETA < Buyer Delivery
Date = OC Delivery Date, cho cả New lẫn Revise."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from openpyxl.worksheet.datavalidation import DataValidation

from wfx_panel.workbooks.oc.schema import (
    EDI_HEADERS,
    FORM_HEADERS,
    INPUT_HEADERS,
    INPUT_SHEET_NAME,
    MAX_ARCHIVE_ENTRIES,
    MAX_UNCOMPRESSED_BYTES,
    MAX_XLSX_BYTES,
    REFERENCE_SHEET_NAME,
    OCWorkbookError,
)


def _normalise_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalise_header(value: Any) -> str:
    return _normalise_text(value).casefold().rstrip(".")


def _validate_xlsx_archive(path: Path) -> None:
    if path.suffix.casefold() != ".xlsx":
        raise OCWorkbookError(
            "OC_FILE_TYPE_UNSUPPORTED",
            "Upload OC chỉ hỗ trợ file .xlsx.",
        )
    if not path.is_file():
        raise OCWorkbookError(
            "OC_FILE_NOT_FOUND",
            "Không tìm thấy file Upload OC đã chọn.",
        )
    if path.stat().st_size > MAX_XLSX_BYTES:
        raise OCWorkbookError(
            "OC_FILE_TOO_LARGE",
            "File Upload OC vượt quá giới hạn 100 MB.",
        )
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise OCWorkbookError(
                    "OC_FILE_UNSAFE",
                    "Workbook có quá nhiều thành phần nội bộ.",
                )
            total = 0
            for entry in entries:
                parts = Path(entry.filename.replace("\\", "/")).parts
                if entry.filename.startswith(("/", "\\")) or ".." in parts:
                    raise OCWorkbookError(
                        "OC_FILE_UNSAFE",
                        "Workbook chứa đường dẫn nội bộ không an toàn.",
                    )
                total += entry.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise OCWorkbookError(
                        "OC_FILE_UNSAFE",
                        "Workbook nén vượt giới hạn giải nén an toàn.",
                    )
            names = {entry.filename for entry in entries}
            if "[Content_Types].xml" not in names or not any(
                name.startswith("xl/workbook") for name in names
            ):
                raise OCWorkbookError(
                    "OC_FILE_INVALID",
                    "File không phải workbook Excel hợp lệ.",
                )
    except BadZipFile as error:
        raise OCWorkbookError(
            "OC_FILE_INVALID",
            "File .xlsx bị hỏng hoặc không phải workbook Excel.",
        ) from error


def _ensure_input_values_only(path: Path, mode: str) -> None:
    """Reject formulas in the sheet users are allowed to edit."""
    try:
        workbook = load_workbook(path, data_only=False, read_only=True)
    except (OSError, ValueError, BadZipFile) as error:
        raise OCWorkbookError(
            "OC_FILE_INVALID",
            f"Không đọc được workbook: {type(error).__name__}: {error}",
        ) from error
    try:
        if mode == "revise":
            sheet_name = "Sheet1"
            width = len(EDI_HEADERS)
        elif INPUT_SHEET_NAME in workbook.sheetnames:
            sheet_name = INPUT_SHEET_NAME
            width = len(INPUT_HEADERS)
        else:
            sheet_name = "FORM"
            width = len(FORM_HEADERS)
        if sheet_name not in workbook.sheetnames:
            return
        sheet = workbook[sheet_name]
        formulas = [
            cell.coordinate
            for row in sheet.iter_rows(max_col=width)
            for cell in row
            if cell.data_type == "f"
        ]
        if formulas:
            shown = ", ".join(formulas[:12])
            suffix = "…" if len(formulas) > 12 else "."
            raise OCWorkbookError(
                "OC_FILE_FORMULA_ERROR",
                f"Sheet {sheet_name} phải chỉ chứa giá trị nhập, không dùng công thức.",
                (f"Ô có công thức: {shown}{suffix}",),
            )
    finally:
        workbook.close()


def _decimal(value: Any, label: str, row_number: int) -> Decimal:
    try:
        # Excel trả TRUE/FALSE thành bool Python. `Decimal(True)` ra 1 nên phải
        # chặn riêng — nhưng phải chặn TRONG try, để nó thành lỗi file của
        # người dùng chứ không thoát ra ngoài dưới dạng InvalidOperation thô.
        # Thoát ra ngoài thì `_run` quy về PANEL_ERROR, mà mã đó nằm ngoài
        # NON_REPORTABLE_FAILURES nên telemetry gửi một lỗi hệ thống không có
        # thật ra webhook production.
        if isinstance(value, bool):
            raise InvalidOperation
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError, ValueError) as error:
        raise OCWorkbookError(
            "OC_FILE_VALIDATION_FAILED",
            "Workbook Upload OC có dữ liệu chưa hợp lệ.",
            (f"Dòng {row_number}: {label} phải là số.",),
        ) from error
    if not number.is_finite():
        raise OCWorkbookError(
            "OC_FILE_VALIDATION_FAILED",
            "Workbook Upload OC có dữ liệu chưa hợp lệ.",
            (f"Dòng {row_number}: {label} phải là số hữu hạn.",),
        )
    return number


def _date_value(value: Any, label: str, row_number: int) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            converted = from_excel(value)
            return converted.date() if isinstance(converted, datetime) else converted
        except (TypeError, ValueError, OverflowError):
            pass
    raw = _normalise_text(value)
    for pattern in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    raise OCWorkbookError(
        "OC_FILE_VALIDATION_FAILED",
        "Workbook Upload OC có dữ liệu chưa hợp lệ.",
        (f"Dòng {row_number}: {label} phải là ngày hợp lệ.",),
    )


def _safe_text(value: Any, label: str, row_number: int) -> str:
    text = _normalise_text(value)
    if text.startswith(("=", "+", "@")):
        raise OCWorkbookError(
            "OC_FILE_VALIDATION_FAILED",
            "Workbook Upload OC có dữ liệu chưa hợp lệ.",
            (f"Dòng {row_number}: {label} không được bắt đầu bằng công thức.",),
        )
    if text.startswith("#") and text.upper() in {
        "#REF!",
        "#VALUE!",
        "#N/A",
        "#NAME?",
        "#DIV/0!",
        "#NUM!",
        "#NULL!",
    }:
        raise OCWorkbookError(
            "OC_FILE_FORMULA_ERROR",
            "Workbook còn lỗi công thức Excel.",
            (f"Dòng {row_number}: {label} đang là {text}.",),
        )
    return text


def _is_zero_quantity(value: Any) -> bool:
    if isinstance(value, bool) or value in (None, ""):
        return False
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError, ValueError):
        return False
    return number.is_finite() and number == 0


def _canonical_option(
    value: Any,
    label: str,
    row_number: int,
    options: tuple[str, ...],
    *,
    default: str = "",
) -> str:
    text = _safe_text(value, label, row_number)
    if not text and default:
        return default
    matches = {option.casefold(): option for option in options}
    canonical = matches.get(text.casefold())
    if canonical:
        return canonical
    raise OCWorkbookError(
        "OC_FILE_VALIDATION_FAILED",
        "Workbook Upload OC có dữ liệu chưa hợp lệ.",
        (f"Dòng {row_number}: {label} '{text or '[trống]'} không có trong danh sách.",),
    )


def _validate_delivery_dates(
    buyer_order_date: date,
    raw_material_eta: date,
    buyer_delivery_date: date,
    row_number: int,
    *,
    oc_delivery_date: date | None = None,
) -> list[str]:
    errors: list[str] = []
    if not buyer_order_date < raw_material_eta < buyer_delivery_date:
        errors.append(
            f"Dòng {row_number}: ngày phải theo Buyer Order Date "
            "< Raw Material ETA < Buyer Delivery Date."
        )
    if oc_delivery_date is not None and buyer_delivery_date != oc_delivery_date:
        errors.append(
            f"Dòng {row_number}: Buyer Delivery Date phải bằng OC Delivery Date."
        )
    return errors


def _ensure_headers(actual: list[Any], expected: tuple[str, ...], label: str) -> None:
    actual_normalised = tuple(_normalise_header(item) for item in actual)
    expected_normalised = tuple(_normalise_header(item) for item in expected)
    if actual_normalised == expected_normalised:
        return
    errors: list[str] = []
    for index, expected_header in enumerate(expected):
        actual_header = _normalise_text(actual[index]) if index < len(actual) else ""
        if _normalise_header(actual_header) != _normalise_header(expected_header):
            errors.append(
                f"Cột {index + 1}: cần '{expected_header}', đang là "
                f"'{actual_header or '[trống]'}'."
            )
        if len(errors) >= 8:
            break
    raise OCWorkbookError(
        "OC_FILE_HEADERS_INVALID",
        f"Header {label} không đúng mẫu Upload OC.",
        errors,
    )


def _lookup_lists(workbook: Any) -> tuple[set[str], set[str], dict[str, tuple[str, str]]]:
    if "THONG TIN" not in workbook.sheetnames:
        raise OCWorkbookError(
            "OC_TEMPLATE_SHEET_MISSING",
            "Thiếu sheet THONG TIN trong UPLOAD FORM.",
        )
    sheet = workbook["THONG TIN"]
    factories = {
        _normalise_text(sheet.cell(row, 1).value).casefold()
        for row in range(2, sheet.max_row + 1)
        if _normalise_text(sheet.cell(row, 1).value)
    }
    buyers: set[str] = set()
    for row in range(2, sheet.max_row + 1):
        value = _normalise_text(sheet.cell(row, 2).value)
        if not value:
            continue
        if value.casefold() == "po type":
            break
        buyers.add(value.casefold())
    countries: dict[str, tuple[str, str]] = {}
    for row in range(2, sheet.max_row + 1):
        destination = _normalise_text(sheet.cell(row, 5).value)
        market = _normalise_text(sheet.cell(row, 6).value)
        key = destination.casefold()
        if key and market:
            countries[key] = (destination, market)
    return factories, buyers, countries


def _add_list_validation(
    sheet: Any,
    reference_sheet: Any,
    header: str,
    reference_column: int,
    option_count: int,
) -> None:
    input_header = {
        "Country": "Country of Final Destination",
    }.get(header, header)
    column = INPUT_HEADERS.index(input_header) + 1
    reference_letter = reference_sheet.cell(1, reference_column).column_letter
    validation = DataValidation(
        type="list",
        formula1=(
            f"'{REFERENCE_SHEET_NAME}'!${reference_letter}$2:"
            f"${reference_letter}${option_count + 1}"
        ),
        allow_blank=header in {
            "Buyer",
            "Order Type",
            "Currency",
            "PO Type (Zone)",
        },
    )
    validation.error = f"Hãy chọn {input_header} từ danh sách."
    validation.errorTitle = "Giá trị không hợp lệ"
    validation.prompt = f"Chọn {input_header}."
    validation.promptTitle = "Upload OC"
    validation.showErrorMessage = True
    validation.showInputMessage = True
    if header in {"Buyer", "Factory", "Payment Terms"}:
        validation.errorStyle = "warning"
        validation.error = (
            f"{input_header} chưa có trong danh sách gợi ý của form. "
            "Chỉ tiếp tục nếu giá trị này đang tồn tại trên WFX."
        )
    sheet.add_data_validation(validation)
    validation.add(f"{sheet.cell(2, column).column_letter}2:{sheet.cell(2, column).column_letter}10001")


def _add_date_sequence_validation(sheet: Any) -> None:
    """Warn in Excel once all three OC dates on a row have been entered."""
    validation = DataValidation(
        type="custom",
        formula1=(
            "OR(COUNTA($K2:$M2)<3,"
            "AND(ISNUMBER($K2),ISNUMBER($L2),ISNUMBER($M2),"
            "$K2<$M2,$M2<$L2))"
        ),
        allow_blank=True,
    )
    validation.errorTitle = "Thứ tự ngày không hợp lệ"
    validation.error = (
        "Ngày phải theo Buyer Order Date < Raw Material ETA Date "
        "< Buyer Delivery Date."
    )
    validation.promptTitle = "Thứ tự ngày Upload OC"
    validation.prompt = (
        "Có thể nhập lần lượt; khi đủ ba ngày, Excel sẽ kiểm tra đúng thứ tự."
    )
    validation.showErrorMessage = True
    validation.showInputMessage = True
    validation.errorStyle = "stop"
    sheet.add_data_validation(validation)
    validation.add("K2:M10001")
