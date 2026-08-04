"""Form Excel và validation cho luồng tạo Sale ASN từ nhiều PO."""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

SALE_ASN_SHEET = "SALE ASN"
SALE_ASN_COLUMNS = (
    "Invoice No",
    "Invoice Date",
    "Shipping Bill No",
    "Shipping Bill Date",
    "Style No",
    "PO No",
    "HS CODE",
    "Qty",
    "Carton",
    "NW",
    "GW",
    "CBM",
    "Destination",
    "FTY",
    "FOB Price",
    "Service Price",
    "Cargo Ready Date",
    "Consignee Address",
    "Ship To",
    "Shipping Mode",
)

SHIPPING_MODES = ("AIR", "SEA", "COURIER")

SALE_ASN_ORDER_DETAILS_SHEET = "ORDER DETAILS"
SALE_ASN_ORDER_DETAILS_COLUMNS = (
    "PO No",
    "Carton",
    "NW",
    "GW",
    "CBM",
    "FOB Price",
    "Service Price",
    "Cargo Ready Date",
)
_ORDER_DETAILS_NUMBER_COLUMNS = frozenset(
    {"Carton", "NW", "GW", "CBM", "FOB Price", "Service Price"}
)

MAX_SALE_ASN_ROWS = 2_000
MAX_SALE_ASN_BYTES = 20 * 1024 * 1024
# Số mũ tối đa của chữ số đầu; 15 tương đương 16 chữ số phần nguyên, thừa sức
# cho Qty/Carton/NW/GW/CBM/giá và vẫn an toàn cho quantize() ở lớp automation.
MAX_SALE_ASN_NUMBER_EXPONENT = 15

_OPTIONAL_COLUMNS = frozenset(
    {
        "HS CODE",
        "Qty",
        "Carton",
        "NW",
        "GW",
        "CBM",
        "FOB Price",
        "Service Price",
        "Cargo Ready Date",
        "Consignee Address",
        "Ship To",
    }
)
_DATE_COLUMNS = frozenset(
    {"Invoice Date", "Shipping Bill Date", "Cargo Ready Date"}
)
_NUMBER_COLUMNS = frozenset(
    {"Qty", "Carton", "NW", "GW", "CBM", "FOB Price", "Service Price"}
)


class SaleASNWorkbookError(ValueError):
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
class SaleASNRow:
    source_row: int
    invoice_no: str
    invoice_date: str
    shipping_bill_no: str
    shipping_bill_date: str
    style_no: str
    po_no: str
    hs_code: str
    qty: str
    carton: str
    nw: str
    gw: str
    cbm: str
    destination: str
    factory: str
    fob_price: str
    service_price: str
    cargo_ready_date: str
    consignee_address: str
    ship_to: str
    shipping_mode: str

    def automation_payload(self) -> dict[str, str | int]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def _identifier(value: object) -> str:
    if isinstance(value, bool):
        return _text(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _text(value)


def _number(value: object, *, cell: str, integer: bool = False) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        number = Decimal(text.replace(",", ""))
    except InvalidOperation as error:
        raise ValueError(f"{cell}: phải là số.") from error
    if not number.is_finite() or number < 0:
        raise ValueError(f"{cell}: phải là số không âm.")
    # Decimal context chỉ giữ 28 chữ số. Một ô dán nhầm kiểu 1E+50 vẫn "hợp lệ"
    # ở đây nhưng sẽ làm quantize() lúc điền lên WFX ném InvalidOperation, biến
    # lỗi nhập liệu thành lỗi automation có gửi telemetry. Chặn ngay tại file.
    if number != 0 and number.adjusted() > MAX_SALE_ASN_NUMBER_EXPONENT:
        raise ValueError(f"{cell}: giá trị quá lớn, hãy kiểm tra lại ô này.")
    if integer and number != number.to_integral_value():
        raise ValueError(f"{cell}: phải là số nguyên.")
    normalized = format(number.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _date_text(value: object, *, cell: str) -> str:
    if value is None or _text(value) == "":
        return ""
    parsed: date | None = None
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        # openpyxl thường trả datetime khi ô có date format. Chỉ giữ fallback
        # cho workbook cũ đã mất style ngày.
        try:
            from openpyxl.utils.datetime import from_excel

            converted = from_excel(value)
            parsed = converted.date() if isinstance(converted, datetime) else converted
        except (TypeError, ValueError, OverflowError):
            parsed = None
    else:
        raw = _text(value)
        for pattern in (
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d %b %Y",
        ):
            try:
                parsed = datetime.strptime(raw, pattern).date()
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValueError(f"{cell}: ngày không hợp lệ.")
    return parsed.isoformat()


def _assert_safe_xlsx(path: Path) -> None:
    if path.suffix.casefold() != ".xlsx":
        raise SaleASNWorkbookError(
            "SALE_ASN_FILE_TYPE_UNSUPPORTED",
            "Tạo Sale ASN chỉ hỗ trợ file .xlsx.",
        )
    if not path.is_file():
        raise SaleASNWorkbookError(
            "SALE_ASN_FILE_NOT_FOUND",
            "Không tìm thấy file Sale ASN đã chọn.",
        )
    if path.stat().st_size > MAX_SALE_ASN_BYTES:
        raise SaleASNWorkbookError(
            "SALE_ASN_FILE_TOO_LARGE",
            "File Sale ASN vượt quá giới hạn 20 MB.",
        )
    try:
        with ZipFile(path) as archive:
            names = {name.casefold() for name in archive.namelist()}
    except (BadZipFile, OSError) as error:
        raise SaleASNWorkbookError(
            "SALE_ASN_FILE_INVALID",
            "File đã chọn không phải workbook Excel hợp lệ.",
        ) from error
    if any(name.endswith("vbaproject.bin") for name in names):
        raise SaleASNWorkbookError(
            "SALE_ASN_FILE_UNSAFE",
            "File Sale ASN không được chứa macro.",
        )


def _header_identity(value: object) -> str:
    return " ".join(_text(value).split()).casefold()


def _find_input_sheet(workbook) -> object:
    expected = {_header_identity(value) for value in SALE_ASN_COLUMNS}
    for sheet in workbook.worksheets:
        actual = {_header_identity(cell.value) for cell in sheet[1] if cell.value}
        if expected <= actual:
            return sheet
    raise SaleASNWorkbookError(
        "SALE_ASN_FILE_HEADERS_INVALID",
        "Không tìm thấy hàng tiêu đề Sale ASN gồm đủ 20 cột chuẩn.",
    )


def read_sale_asn_workbook(
    input_path: str | Path,
    required_stages: tuple[str, ...] | list[str] | None = None,
) -> dict:
    """Đọc workbook và chỉ bắt buộc dữ liệu cho các bước được chọn."""

    strict_create = required_stages is None
    stages = set(required_stages or ())
    require_style = strict_create or bool(stages & {"po", "style_details"})
    require_destination = strict_create or bool(stages & {"po", "shipping_info"})
    require_factory = strict_create or "shipping_info" in stages
    require_invoice = strict_create or "shipping_info" in stages
    require_shipping = strict_create or "shipping_info" in stages
    path = Path(input_path).expanduser().resolve()
    _assert_safe_xlsx(path)
    try:
        workbook = load_workbook(path, data_only=False, read_only=False)
    except Exception as error:
        raise SaleASNWorkbookError(
            "SALE_ASN_FILE_INVALID",
            "Không đọc được workbook Sale ASN.",
        ) from error

    try:
        sheet = _find_input_sheet(workbook)
        header_map = {
            _header_identity(cell.value): cell.column
            for cell in sheet[1]
            if cell.value
        }
        if sheet.max_row - 1 > MAX_SALE_ASN_ROWS:
            raise SaleASNWorkbookError(
                "SALE_ASN_FILE_TOO_MANY_ROWS",
                f"File Sale ASN chỉ hỗ trợ tối đa {MAX_SALE_ASN_ROWS} dòng.",
            )

        raw_rows: list[dict[str, object]] = []
        for source_row in range(2, sheet.max_row + 1):
            values = {
                column: sheet.cell(
                    source_row, header_map[_header_identity(column)]
                ).value
                for column in SALE_ASN_COLUMNS
            }
            # PO No quyết định một dòng có phải dữ liệu ASN hay không. Dòng
            # tổng, ghi chú hoặc format thừa không có PO được bỏ qua hoàn toàn.
            if not _identifier(values["PO No"]):
                continue
            formula_cells = [
                f"{sheet.cell(source_row, header_map[_header_identity(column)]).coordinate}"
                for column, value in values.items()
                if isinstance(value, str) and value.startswith("=")
            ]
            if formula_cells:
                raise SaleASNWorkbookError(
                    "SALE_ASN_FILE_FORMULA_ERROR",
                    "File Sale ASN không được dùng công thức trong vùng nhập liệu.",
                    tuple(f"{cell}: đang chứa công thức." for cell in formula_cells),
                )
            raw_rows.append({"source_row": source_row, **values})
    finally:
        workbook.close()

    if not raw_rows:
        raise SaleASNWorkbookError(
            "SALE_ASN_FILE_EMPTY",
            "File Sale ASN chưa có dòng dữ liệu.",
        )

    first_values: dict[str, str] = {}
    errors: list[str] = []
    for column in (
        "Invoice No",
        "Invoice Date",
        "Shipping Bill No",
        "Shipping Bill Date",
        "Destination",
        "FTY",
        "Cargo Ready Date",
        "Consignee Address",
        "Ship To",
        "Shipping Mode",
    ):
        raw = next((row[column] for row in raw_rows if _text(row[column])), None)
        try:
            first_values[column] = (
                _date_text(raw, cell=f"{column} dòng đầu")
                if column in _DATE_COLUMNS
                else _identifier(raw)
            )
        except ValueError as error:
            errors.append(str(error))
            first_values[column] = ""

    # Form tạo mới giữ fallback ngày cũ. Khi tiếp tục một ASN đã có PO, ô ngày
    # trống phải thật sự được bỏ qua thay vì vô tình ghi ngày hôm nay lên WFX.
    if strict_create or "po" in stages:
        today = date.today().isoformat()
        for column in ("Invoice Date", "Shipping Bill Date"):
            if not first_values[column]:
                first_values[column] = today
    if require_invoice and not first_values["Invoice No"]:
        errors.append("Invoice No: bắt buộc nhập ở ít nhất một dòng.")
    if require_destination and not first_values["Destination"]:
        errors.append("Destination: bắt buộc nhập ở ít nhất một dòng.")
    if require_factory and not first_values["FTY"]:
        errors.append("FTY: bắt buộc nhập ở ít nhất một dòng.")
    if not first_values["Shipping Bill No"]:
        first_values["Shipping Bill No"] = first_values["Invoice No"]

    rows: list[SaleASNRow] = []
    seen_pos: set[str] = set()
    invoice_values: set[str] = set()
    for raw in raw_rows:
        source_row = int(raw["source_row"])
        invoice_no = _identifier(raw["Invoice No"]) or first_values["Invoice No"]
        if invoice_no:
            invoice_values.add(invoice_no.casefold())
        style_no = _identifier(raw["Style No"])
        po_no = _identifier(raw["PO No"])
        destination = _text(raw["Destination"]) or first_values["Destination"]
        factory = _text(raw["FTY"]) or first_values["FTY"]
        consignee_address = (
            _text(raw["Consignee Address"])
            or first_values["Consignee Address"]
        )
        ship_to = _text(raw["Ship To"]) or first_values["Ship To"]
        shipping_mode = (
            _text(raw["Shipping Mode"]) or first_values["Shipping Mode"]
        ).upper()
        if require_style and not style_no:
            errors.append(f"E{source_row}: Style No bắt buộc.")
        if po_no.casefold() in seen_pos:
            errors.append(f"F{source_row}: PO No bị trùng ({po_no}).")
        else:
            seen_pos.add(po_no.casefold())
        if require_destination and not destination:
            errors.append(f"M{source_row}: Destination bắt buộc.")
        if require_factory and not factory:
            errors.append(f"N{source_row}: FTY bắt buộc.")
        if require_shipping and shipping_mode not in SHIPPING_MODES:
            errors.append(
                f"T{source_row}: Shipping Mode bắt buộc chọn AIR, SEA hoặc COURIER."
            )

        numbers: dict[str, str] = {}
        for column in _NUMBER_COLUMNS:
            try:
                numbers[column] = _number(
                    raw[column],
                    cell=f"{column} dòng {source_row}",
                    integer=column in {"Qty", "Carton"},
                )
            except ValueError as error:
                errors.append(str(error))
                numbers[column] = ""
        dates: dict[str, str] = {}
        for column in _DATE_COLUMNS:
            try:
                parsed_date = _date_text(
                    raw[column], cell=f"{column} dòng {source_row}"
                )
                dates[column] = (
                    parsed_date
                    if column == "Cargo Ready Date"
                    else parsed_date or first_values[column]
                )
            except ValueError as error:
                errors.append(str(error))
                dates[column] = (
                    "" if column == "Cargo Ready Date" else first_values[column]
                )

        rows.append(
            SaleASNRow(
                source_row=source_row,
                invoice_no=invoice_no,
                invoice_date=dates["Invoice Date"],
                shipping_bill_no=(
                    _identifier(raw["Shipping Bill No"])
                    or first_values["Shipping Bill No"]
                    or invoice_no
                ),
                shipping_bill_date=dates["Shipping Bill Date"],
                style_no=style_no,
                po_no=po_no,
                hs_code=_identifier(raw["HS CODE"]),
                qty=numbers["Qty"],
                carton=numbers["Carton"],
                nw=numbers["NW"],
                gw=numbers["GW"],
                cbm=numbers["CBM"],
                destination=destination,
                factory=factory,
                fob_price=numbers["FOB Price"],
                service_price=numbers["Service Price"],
                cargo_ready_date=dates["Cargo Ready Date"],
                consignee_address=consignee_address,
                ship_to=ship_to,
                shipping_mode=shipping_mode,
            )
        )

    if require_invoice and len(invoice_values) > 1:
        errors.append("File chỉ được chứa một Invoice No.")
    factories = {row.factory.casefold() for row in rows if row.factory}
    if require_factory and len(factories) > 1:
        errors.append("File chỉ được chứa một FTY cho mỗi Sale ASN.")
    if errors:
        raise SaleASNWorkbookError(
            "SALE_ASN_FILE_VALIDATION_FAILED",
            f"File Sale ASN có {len(errors)} lỗi cần sửa.",
            tuple(errors[:100]),
        )

    return {
        "file_name": path.name,
        "invoice_no": rows[0].invoice_no,
        "invoice_date": rows[0].invoice_date,
        "shipping_bill_no": rows[0].shipping_bill_no,
        "shipping_bill_date": rows[0].shipping_bill_date,
        "destination": rows[0].destination,
        "factory": rows[0].factory,
        "po_count": len(rows),
        "style_count": len(
            {row.style_no.casefold() for row in rows if row.style_no}
        ),
        "rows": [row.automation_payload() for row in rows],
    }


def write_sale_asn_template(
    output_path: str | Path,
    rows: list[dict] | tuple[dict, ...] = (),
) -> Path:
    """Tạo form Sale ASN gọn với schema Shipping Info hiện hành."""
    target = Path(output_path).expanduser().resolve()
    if target.suffix.casefold() != ".xlsx":
        target = target.with_suffix(".xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SALE_ASN_SHEET
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A2"
    sheet.append(list(SALE_ASN_COLUMNS))
    key_map = {
        "Invoice No": "invoice_no",
        "Invoice Date": "invoice_date",
        "Shipping Bill No": "shipping_bill_no",
        "Shipping Bill Date": "shipping_bill_date",
        "Style No": "style_no",
        "PO No": "po_no",
        "HS CODE": "hs_code",
        "Qty": "qty",
        "Carton": "carton",
        "NW": "nw",
        "GW": "gw",
        "CBM": "cbm",
        "Destination": "destination",
        "FTY": "factory",
        "FOB Price": "fob_price",
        "Service Price": "service_price",
        "Cargo Ready Date": "cargo_ready_date",
        "Consignee Address": "consignee_address",
        "Ship To": "ship_to",
        "Shipping Mode": "shipping_mode",
    }
    for row in rows:
        sheet.append(
            [
                _order_details_export_value(column, row.get(key_map[column]))
                for column in SALE_ASN_COLUMNS
            ]
        )
    reserved_rows = max(20, len(rows))
    for _ in range(len(rows), reserved_rows):
        sheet.append([None] * len(SALE_ASN_COLUMNS))

    widths = (
        20, 14, 20, 18, 34, 22, 15, 12, 12, 12,
        12, 12, 20, 34, 14, 14, 18, 34, 34, 16,
    )
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[sheet.cell(1, index).column_letter].width = width

    required_fill = PatternFill("solid", fgColor="FDE68A")
    optional_fill = PatternFill("solid", fgColor="DBEAFE")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="172033")
        cell.fill = optional_fill if cell.value in _OPTIONAL_COLUMNS else required_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        note = (
            "Có thể để trống; app sẽ bỏ qua trường này."
            if cell.value in _OPTIONAL_COLUMNS
            else "Cột bắt buộc hoặc được app kế thừa từ dòng có dữ liệu đầu tiên."
        )
        cell.comment = Comment(note, "WFX Smart")
    sheet.row_dimensions[1].height = 34

    for row in range(2, reserved_rows + 2):
        for column in (2, 4, 17):
            sheet.cell(row, column).number_format = "dd/mm/yyyy"
        for column in (8, 9, 10, 11, 12, 15, 16):
            sheet.cell(row, column).number_format = "#,##0.00"
    shipping_mode_validation = DataValidation(
        type="list",
        formula1='"AIR,SEA,COURIER"',
        allow_blank=False,
    )
    shipping_mode_validation.error = "Chọn AIR, SEA hoặc COURIER."
    shipping_mode_validation.errorTitle = "Shipping Mode không hợp lệ"
    shipping_mode_validation.prompt = "Chọn AIR, SEA hoặc COURIER."
    shipping_mode_validation.promptTitle = "Shipping Mode"
    sheet.add_data_validation(shipping_mode_validation)
    shipping_mode_validation.add(f"T2:T{MAX_SALE_ASN_ROWS + 1}")
    table_ref = f"A1:T{reserved_rows + 1}"
    table = Table(displayName="SaleASNInput", ref=table_ref)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)
    workbook.save(target)
    workbook.close()
    return target


def _find_order_details_sheet(workbook) -> object:
    expected = {
        _header_identity(value) for value in SALE_ASN_ORDER_DETAILS_COLUMNS
    }
    for sheet in workbook.worksheets:
        actual = {_header_identity(cell.value) for cell in sheet[1] if cell.value}
        if expected <= actual:
            return sheet
    raise SaleASNWorkbookError(
        "SALE_ASN_ORDER_FILE_HEADERS_INVALID",
        "Không tìm thấy hàng tiêu đề Order Details gồm đủ 8 cột chuẩn.",
    )


def _order_details_export_value(column: str, value: object) -> object:
    """Giữ ô export là number/date thật để người dùng tiếp tục tính toán."""

    if value is None or _text(value) == "":
        return None
    if column in _ORDER_DETAILS_NUMBER_COLUMNS:
        try:
            normalized = _number(
                value,
                cell=column,
                integer=column == "Carton",
            )
            number = Decimal(normalized)
            return int(number) if number == number.to_integral_value() else float(number)
        except (ValueError, InvalidOperation):
            return _text(value)
    if column == "Cargo Ready Date":
        try:
            return date.fromisoformat(_date_text(value, cell=column))
        except ValueError:
            return _text(value)
    return _identifier(value)


def read_sale_asn_order_details_workbook(input_path: str | Path) -> dict:
    """Đọc file chỉ dùng để cập nhật Order Details trên form WFX đang mở."""

    path = Path(input_path).expanduser().resolve()
    _assert_safe_xlsx(path)
    try:
        workbook = load_workbook(path, data_only=False, read_only=False)
    except Exception as error:
        raise SaleASNWorkbookError(
            "SALE_ASN_FILE_INVALID",
            "Không đọc được workbook Order Details.",
        ) from error

    errors: list[str] = []
    rows: list[dict[str, str | int]] = []
    seen_pos: set[str] = set()
    try:
        sheet = _find_order_details_sheet(workbook)
        header_map = {
            _header_identity(cell.value): cell.column
            for cell in sheet[1]
            if cell.value
        }
        if sheet.max_row - 1 > MAX_SALE_ASN_ROWS:
            raise SaleASNWorkbookError(
                "SALE_ASN_FILE_TOO_MANY_ROWS",
                f"File Order Details chỉ hỗ trợ tối đa {MAX_SALE_ASN_ROWS} dòng.",
            )
        for source_row in range(2, sheet.max_row + 1):
            values = {
                column: sheet.cell(
                    source_row,
                    header_map[_header_identity(column)],
                ).value
                for column in SALE_ASN_ORDER_DETAILS_COLUMNS
            }
            po_no = _identifier(values["PO No"])
            if not po_no:
                continue
            formula_cells = [
                sheet.cell(
                    source_row,
                    header_map[_header_identity(column)],
                ).coordinate
                for column, value in values.items()
                if isinstance(value, str) and value.startswith("=")
            ]
            if formula_cells:
                errors.extend(
                    f"{cell}: đang chứa công thức." for cell in formula_cells
                )
            po_key = po_no.casefold()
            if po_key in seen_pos:
                errors.append(f"A{source_row}: PO No bị trùng ({po_no}).")
            seen_pos.add(po_key)

            payload: dict[str, str | int] = {
                "source_row": source_row,
                "po_no": po_no,
            }
            key_map = {
                "Carton": "carton",
                "NW": "nw",
                "GW": "gw",
                "CBM": "cbm",
                "FOB Price": "fob_price",
                "Service Price": "service_price",
            }
            for column, key in key_map.items():
                try:
                    payload[key] = _number(
                        values[column],
                        cell=f"{column} dòng {source_row}",
                        integer=column == "Carton",
                    )
                except ValueError as error:
                    errors.append(str(error))
                    payload[key] = ""
            try:
                payload["cargo_ready_date"] = _date_text(
                    values["Cargo Ready Date"],
                    cell=f"Cargo Ready Date dòng {source_row}",
                )
            except ValueError as error:
                errors.append(str(error))
                payload["cargo_ready_date"] = ""
            rows.append(payload)
    finally:
        workbook.close()

    if not rows:
        raise SaleASNWorkbookError(
            "SALE_ASN_ORDER_FILE_EMPTY",
            "File Order Details chưa có PO No.",
        )
    editable_keys = (
        "carton",
        "nw",
        "gw",
        "cbm",
        "fob_price",
        "service_price",
        "cargo_ready_date",
    )
    filled_count = sum(
        1 for row in rows for key in editable_keys if str(row.get(key) or "").strip()
    )
    if not filled_count:
        errors.append("Chưa có dữ liệu Order Details nào để điền lên WFX.")
    if errors:
        raise SaleASNWorkbookError(
            "SALE_ASN_ORDER_FILE_VALIDATION_FAILED",
            f"File Order Details có {len(errors)} lỗi cần sửa.",
            tuple(errors[:100]),
        )
    return {
        "file_name": path.name,
        "po_count": len(rows),
        "filled_count": filled_count,
        "rows": rows,
    }


def write_sale_asn_order_details_template(
    output_path: str | Path,
    rows: list[dict] | tuple[dict, ...] = (),
) -> Path:
    """Xuất form Order Details, ưu tiên các PO/giá trị đang có trên WFX."""

    target = Path(output_path).expanduser().resolve()
    if target.suffix.casefold() != ".xlsx":
        target = target.with_suffix(".xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SALE_ASN_ORDER_DETAILS_SHEET
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A2"
    sheet.append(list(SALE_ASN_ORDER_DETAILS_COLUMNS))
    key_map = {
        "PO No": "po_no",
        "Carton": "carton",
        "NW": "nw",
        "GW": "gw",
        "CBM": "cbm",
        "FOB Price": "fob_price",
        "Service Price": "service_price",
        "Cargo Ready Date": "cargo_ready_date",
    }
    for row in rows:
        sheet.append(
            [
                _order_details_export_value(column, row.get(key_map[column]))
                for column in SALE_ASN_ORDER_DETAILS_COLUMNS
            ]
        )
    reserved_rows = max(20, len(rows))
    for _ in range(len(rows), reserved_rows):
        sheet.append([None] * len(SALE_ASN_ORDER_DETAILS_COLUMNS))

    widths = (24, 12, 12, 12, 12, 15, 18, 22)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[sheet.cell(1, index).column_letter].width = width
    required_fill = PatternFill("solid", fgColor="FDE68A")
    optional_fill = PatternFill("solid", fgColor="DBEAFE")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="172033")
        cell.fill = required_fill if cell.value == "PO No" else optional_fill
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )
        cell.comment = Comment(
            (
                "Không sửa PO No nếu form được xuất từ WFX; app dùng cột này để map đúng dòng."
                if cell.value == "PO No"
                else "Có thể để trống; app chỉ điền các ô có dữ liệu."
            ),
            "WFX Smart",
        )
    sheet.row_dimensions[1].height = 34
    for row_index in range(2, reserved_rows + 2):
        for column in range(2, 8):
            sheet.cell(row_index, column).number_format = "#,##0.00"
        sheet.cell(row_index, 2).number_format = "#,##0"
        sheet.cell(row_index, 8).number_format = "dd/mm/yyyy"
    table = Table(
        displayName="SaleASNOrderDetailsInput",
        ref=f"A1:H{reserved_rows + 1}",
    )
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)
    workbook.save(target)
    workbook.close()
    return target
