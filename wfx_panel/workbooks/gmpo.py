"""Excel round trip for the Blanket GMPO order grid."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

_SHEET = "GMPO"
_BASELINE = "_WFX_GMPO"
_VERSION = "WFX GMPO v1"
_IDENTITY = {
    "colbuyerorderref": "Buyer Order Ref",
    "colstyle": "Style",
    "colcolor": "Color",
}


def row_key(identity: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(identity, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def quantity(value: object) -> Decimal:
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]{1,11}(?:\.[0-9]{1,4}0*)?", text):
        raise ValueError("Số lượng phải là số không âm, tối đa 4 chữ số thập phân.")
    return Decimal(text)


def _text(cell, value: str) -> None:
    cell.value = value
    cell.data_type = "s"


def write_workbook(path: Path, snapshot: dict) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = _SHEET
    baseline = book.create_sheet(_BASELINE)
    baseline.sheet_state = "veryHidden"
    baseline.append([_VERSION, snapshot["scope"]])
    columns = ["Order ID", "Mã dòng"] + [
        f"Order Qty - {column['label']}"
        if column["size"]
        else _IDENTITY.get(column["id"], column["label"])
        for column in snapshot["columns"]
    ]
    for index, label in enumerate(columns, 1):
        cell = sheet.cell(1, index)
        _text(cell, label)
        cell.fill = PatternFill(
            "solid", fgColor="146C62" if label.startswith("Order Qty - ") else "263C50"
        )
        cell.font = Font(color="FFFFFF", bold=True)
        sheet.column_dimensions[get_column_letter(index)].width = max(
            16, len(label) + 4
        )

    for index, column in enumerate(snapshot["columns"], 3):
        width = max(len(row["values"][column["id"]]) for row in snapshot["rows"])
        dim = sheet.column_dimensions[get_column_letter(index)]
        dim.width = min(62, max(dim.width, width + 3))

    qty_headers = {
        f"Order Qty - {column['label']}": column["size"]
        for column in snapshot["columns"]
        if column["size"]
    }
    baseline.append(
        ["Mã dòng", "Dòng WFX", "Thông tin đối chiếu", *qty_headers.values()]
    )
    baseline.append([None, None, None, *qty_headers])
    for number, row in enumerate(snapshot["rows"], 2):
        key = row_key(row["identity"])
        _text(sheet.cell(number, 1), row["identity"][0])
        _text(sheet.cell(number, 2), key)
        baseline.append(
            [
                key,
                json.dumps(row["identity"], ensure_ascii=False),
                json.dumps(
                    {k: row["values"].get(k, "") for k in _IDENTITY}, ensure_ascii=False
                ),
                *(
                    row["qty"][size]["value"] if size in row["qty"] else None
                    for size in qty_headers.values()
                ),
            ]
        )
        for index, column in enumerate(snapshot["columns"], 3):
            cell = sheet.cell(number, index)
            size = column["size"]
            if not size:
                _text(cell, row["values"][column["id"]])
            elif size in row["qty"]:
                cell.value = quantity(row["qty"][size]["value"])
                decimals = row["qty"][size]["decimals"]
                cell.number_format = "0." + "0" * decimals if decimals else "0"
                if row["qty"][size]["editable"] and not snapshot["kit"]:
                    cell.fill = PatternFill("solid", fgColor="DCF3E9")

    sheet.column_dimensions["B"].hidden = True
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = sheet.dimensions
    with TemporaryDirectory(prefix=".wfx-gmpo-", dir=path.parent) as folder:
        pending = Path(folder) / path.name
        book.save(pending)
        pending.replace(path)


def read_changes(path: Path) -> tuple[str, list[dict]]:
    if path.suffix.casefold() != ".xlsx":
        raise ValueError("Hãy chọn file .xlsx do WFX Smart xuất.")
    try:
        book = load_workbook(path, read_only=True)
    except (
        OSError,
        BadZipFile,
        InvalidFileException,
        KeyError,
        ParseError,
        ValueError,
    ) as error:
        raise ValueError(
            "Không đọc được file Excel GMPO. Hãy chọn file .xlsx do WFX Smart xuất."
        ) from error
    try:
        return _read_changes(book)
    except (
        OSError,
        BadZipFile,
        KeyError,
        TypeError,
        IndexError,
        ParseError,
        StopIteration,
    ) as error:
        raise ValueError(
            "File GMPO thiếu thông tin đối chiếu. Hãy xuất lại file từ WFX."
        ) from error
    finally:
        book.close()


def _read_changes(book) -> tuple[str, list[dict]]:
    visible = iter(book[_SHEET].values)
    hidden = iter(book[_BASELINE].values)
    version, scope, *_ = next(hidden)
    if version != _VERSION or not scope:
        raise ValueError("Hãy dùng file GMPO do WFX Smart xuất.")
    headers = next(visible)
    size_codes = next(hidden)[3:]
    size_headers = next(hidden)[3:]
    originals = {}
    for key, raw_identity, raw_reference, *qty in hidden:
        identity = json.loads(raw_identity)
        if key != row_key(identity) or key in originals:
            raise ValueError("Mã dòng trong file GMPO bị trùng hoặc không hợp lệ.")
        originals[key] = (
            identity,
            json.loads(raw_reference),
            dict(zip(size_codes, qty, strict=True)),
        )

    qty_columns = {
        index: header
        for index, header in enumerate(headers)
        if isinstance(header, str) and header.startswith("Order Qty - ")
    }
    if (
        len(qty_columns) != len(size_codes)
        or set(qty_columns.values()) != set(size_headers)
        or len(set(size_headers)) != len(size_codes)
        or len(set(size_codes)) != len(size_codes)
        or headers[:2] != ("Order ID", "Mã dòng")
    ):
        raise ValueError(
            "Các cột Order Qty đã thay đổi. Hãy dùng đúng cấu trúc file xuất."
        )
    size_for_header = dict(zip(size_headers, size_codes, strict=True))
    if any(headers.count(label) != 1 for label in _IDENTITY.values()):
        raise ValueError(
            "File GMPO thiếu cột nhận diện PO, Style hoặc Color. Hãy xuất lại file."
        )
    references = {key: headers.index(label) for key, label in _IDENTITY.items()}
    changes = []
    seen = set()
    for number, row in enumerate(visible, 2):
        if not any(value is not None for value in row):
            continue
        order, key = row[:2]
        if key not in originals or key in seen:
            raise ValueError(f"Dòng Excel {number} thiếu mã dòng hoặc bị trùng.")
        seen.add(key)
        identity, reference, original = originals[key]
        if str(order) != identity[0] or any(
            str(row[index] or "") != reference[key] for key, index in references.items()
        ):
            raise ValueError(
                f"Dòng Excel {number} đã đổi thông tin nhận diện PO, Style hoặc Color."
            )
        for index, header in qty_columns.items():
            size = size_for_header[header]
            value = row[index]
            if value is None:
                continue
            try:
                new = quantity(value)
                before = (
                    quantity(original[size]) if original[size] is not None else None
                )
            except ValueError as error:
                raise ValueError(
                    f"Dòng Excel {number}, {headers[index]}. {error}"
                ) from error
            if new != before:
                changes.append(
                    {
                        "key": key,
                        "size": size,
                        "before": before,
                        "value": new,
                        "label": f"dòng Excel {number}, {headers[index]}",
                    }
                )
    return scope, changes
