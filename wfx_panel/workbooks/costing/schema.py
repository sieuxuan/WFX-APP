"""Hình dạng workbook Costing: cột, giới hạn, chuẩn hoá và validate.

Mọi ô đọc vào đều đi qua đây trước: chặn công thức nguy hiểm, cắt độ dài, ép
kiểu và kiểm tra trần số section/item/field. Không import openpyxl cho việc ghi
nên nạp được độc lập."""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from openpyxl.styles import Border, Font, PatternFill, Side

FORMAT_VERSION = "2.1"


SUPPORTED_EXTENSIONS = {".xlsx"}


MAX_FILE_BYTES = 12 * 1024 * 1024


MAX_XLSX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024


MAX_XLSX_MEMBERS = 5_000


MAX_SECTIONS = 250


MAX_ITEMS = 20_000


MAX_FIELDS = 120_000


MAX_CELL_CHARS = 20_000


CLEAR_MARKER = "__CLEAR__"


DEFAULT_NEW_ITEM_ROWS_PER_SECTION = 3


GUIDE_SHEET = "Hướng dẫn"


FORM_SHEET = "Costing"


FIELD_SCOPES = {"cost_sheet", "section", "item"}


ITEM_ACTIONS = {"UPSERT", "DELETE"}


ITEM_TYPES = {"article", "cost_line"}


FORM_BASE_COLUMNS = [
    "Section",
    "Action",
    "Article Code",
    "Article Name",
]


FORM_TECH_COLUMNS = [
    "__Section Key",
    "__Item Key",
    "__Row Order",
    "__Item Type",
]


STANDARD_ITEM_FIELDS = (
    {
        "field_key": "colMaterialSizeList",
        "label": "Material Size",
        "data_type": "text",
    },
    {
        "field_key": "colMaterialColorList",
        "label": "Material Color",
        "data_type": "text",
    },
    {
        "field_key": "colColorDependency",
        "label": "Color Dep.",
        "data_type": "text",
    },
    {
        "field_key": "colColorDependencyMapping",
        "label": "Color Mapping",
        "data_type": "text",
    },
    {
        "field_key": "colSizeDependency",
        "label": "Size Dep.",
        "data_type": "text",
    },
    {
        "field_key": "colSizeDependencyMapping",
        "label": "Size Mapping",
        "data_type": "text",
    },
    {
        "field_key": "colShrinkagePerRemarks",
        "label": "Shrinkage %(LxW)",
        "data_type": "text",
    },
    {
        "field_key": "colConsQty",
        "label": "Cons. Qty.",
        "data_type": "number",
    },
    {
        "field_key": "colWastagePer",
        "label": "Waste %",
        "data_type": "number",
    },
    {
        "field_key": "Minutes",
        "label": "Minutes",
        "data_type": "number",
    },
    {
        "field_key": "colConsPlusWastageQty",
        "label": "Cons. Qty. Incl. Waste",
        "data_type": "number",
        "read_only": True,
    },
    {
        "field_key": "colSupplierCompanyName",
        "label": "Supplier",
        "data_type": "text",
    },
    {
        "field_key": "colCurrencyCode",
        "label": "Curr.",
        "data_type": "text",
    },
    {
        "field_key": "colRate1",
        "label": "Rate",
        "data_type": "number",
    },
    {
        "field_key": "colValue",
        "label": "Value",
        "data_type": "number",
    },
    {
        "field_key": "colValueInCSCurr",
        "label": "Value in (USD)",
        "data_type": "number",
        "read_only": True,
    },
    {
        "field_key": "colRemarks",
        "label": "Remarks",
        "data_type": "text",
    },
    {
        "field_key": "colPlacement",
        "label": "Placement",
        "data_type": "text",
    },
    {
        "field_key": "colPurchaseOfficer",
        "label": "Purchase Officer",
        "data_type": "text",
    },
)


FORM_COLUMNS = [
    *FORM_BASE_COLUMNS,
    *[str(field["label"]) for field in STANDARD_ITEM_FIELDS],
    *FORM_TECH_COLUMNS,
]


OPTIONAL_FORM_COLUMNS = {
    "Color Mapping",
    "Size Mapping",
    "Cons. Qty. Incl. Waste",
    "Value in (USD)",
}


_HEADER_FILL = PatternFill("solid", fgColor="0F766E")


_SUBHEADER_FILL = PatternFill("solid", fgColor="DFF4F2")


_INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")


_TEMPLATE_INPUT_FILL = PatternFill("solid", fgColor="FFE699")


_META_FILL = PatternFill("solid", fgColor="E8EEF5")


_READ_ONLY_FILL = PatternFill("solid", fgColor="F4CCCC")


_READ_ONLY_HEADER_FILL = PatternFill("solid", fgColor="B91C1C")


_HEADER_FONT = Font(color="FFFFFF", bold=True)


_TITLE_FONT = Font(color="0F5660", bold=True, size=16)


_THIN_GRAY = Side(style="thin", color="D4DEE5")


_SECTION_SIDE = Side(style="medium", color="0F766E")


_STRUCTURE_BORDER = Border(bottom=_THIN_GRAY)


_SECTION_BORDER = Border(top=_SECTION_SIDE, bottom=_THIN_GRAY)


_DANGEROUS_EXCEL_PREFIXES = ("=", "+", "-", "@")


STANDARD_SECTIONS = (
    ("fabricshell", "FABRIC- SHELL"),
    ("fabriclining", "FABRIC - LINING"),
    ("fabricinterlining", "FABRIC - INTERLINING"),
    ("fabricpadding", "FABRIC - PADDING"),
    ("sewingtrims", "SEWING TRIMS"),
    ("packingtrims", "PACKING TRIMS"),
    ("cmcosts", "CM Costs"),
    ("productioncosts", "Production Costs"),
    ("indirectcosts", "Indirect Costs"),
)


ARTICLE_SECTION_TOKENS = frozenset(token for token, _name in STANDARD_SECTIONS[:6])


SPECIAL_COST_SECTION_ROWS = {
    "cmcosts": 1,
    "productioncosts": 1,
    "indirectcosts": 2,
}


_EXCLUDED_FIELD_TOKENS = {
    "deliveryterms",
    "processrequired",
    "bomsno",
    "bomdtsno",
    "rolllotavg",
    "destinationcountry",
    "desspecific",
    "destinationspecific",
    "materialcostincludedin",
}


_EXCLUDED_FIELD_KEYS = {
    "colbom",
    "colsno",
    "colrolllot",
    "colavg",
    "coldes",
    "colspecific",
    "colmaterialcost",
    "colincludedin",
}


_EXCLUDED_FIELD_LABELS = {
    "deliveryterms",
    "processrequired",
    "bom",
    "sno",
    "rolllot",
    "avg",
    "destinationcountry",
    "des",
    "specific",
    "materialcost",
    "includedin",
}


class CostingWorkbookError(ValueError):
    """Lỗi file có mã ổn định để UI/telemetry phân loại."""

    def __init__(self, code: str, message: str, *, details: Sequence[str] = ()):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = [str(item) for item in details]

    def as_result(self) -> dict[str, Any]:
        return {
            "ok": False,
            "code": self.code,
            "message": self.message,
            "validation_errors": list(self.details),
        }


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).casefold() in {"1", "true", "yes", "y", "x", "có"}


def _order(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(_text(value)))
    except (TypeError, ValueError):
        return fallback


def _options(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [_text(item) for item in value if _text(item)]
    raw = _text(value)
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [_text(item) for item in parsed if _text(item)]
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return [_text(item) for item in raw.split("|") if _text(item)]


def _excel_safe(value: Any) -> Any:
    """Giữ identifier là text và vô hiệu hóa formula injection khi export."""
    if not isinstance(value, str):
        return value
    if value.startswith(_DANGEROUS_EXCEL_PREFIXES):
        return "'" + value
    return value


def _excel_unescape(value: Any) -> Any:
    if (
        isinstance(value, str)
        and len(value) >= 2
        and value[0] == "'"
        and value[1] in _DANGEROUS_EXCEL_PREFIXES
    ):
        return value[1:]
    return value


def _reject_formula(value: Any, location: str) -> None:
    if isinstance(value, str) and value.startswith("="):
        raise CostingWorkbookError(
            "COSTING_FORMULA_NOT_ALLOWED",
            "File Costing không được chứa công thức trong vùng dữ liệu.",
            details=[location],
        )


def _clean_cell(value: Any, location: str) -> Any:
    _reject_formula(value, location)
    value = _excel_unescape(value)
    if isinstance(value, str) and len(value) > MAX_CELL_CHARS:
        raise CostingWorkbookError(
            "COSTING_VALIDATION_FAILED",
            "Một ô trong file Costing dài hơn giới hạn cho phép.",
            details=[location],
        )
    return value


def _normalized_field(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    scope = _text(raw.get("scope")).casefold()
    return {
        "scope": scope,
        "section_key": _text(raw.get("section_key")),
        "item_key": _text(raw.get("item_key")),
        "field_key": _text(raw.get("field_key")),
        "label": _text(raw.get("label") or raw.get("field_label")),
        "value": raw.get("value", ""),
        "data_type": _text(raw.get("data_type") or "text").casefold(),
        "editable": _bool(raw.get("editable")),
        "required": _bool(raw.get("required")),
        "options": _options(raw.get("options")),
        "row_order": _order(raw.get("row_order"), index),
    }


def _article_lookup_options(value: object) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)):
        return []
    options = []
    seen = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        code = _text(raw.get("article_code"))
        name = _text(raw.get("article_name"))
        if not code or not name:
            continue
        identity = code.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        options.append({"article_code": code, "article_name": name})
    return options


def _normalized_section(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "section_key": _text(raw.get("section_key")),
        "name": _text(raw.get("name") or raw.get("section_name")),
        "row_order": _order(raw.get("row_order"), index),
        "article_options": _options(raw.get("article_options")),
        "article_code_options": _options(raw.get("article_code_options")),
        "article_name_options": _options(raw.get("article_name_options")),
        "article_lookup_options": _article_lookup_options(
            raw.get("article_lookup_options")
        ),
    }


def _normalized_item(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    action = _text(raw.get("action") or "UPSERT").upper()
    item_type = _text(raw.get("item_type") or "article").casefold()
    return {
        "section_key": _text(raw.get("section_key")),
        "section_name": _text(raw.get("section_name")),
        "item_key": _text(raw.get("item_key")),
        "row_order": _order(raw.get("row_order"), index),
        "action": action,
        "item_type": item_type,
        "article_code": _text(raw.get("article_code")),
        "article_name": _text(raw.get("article_name")),
    }


def normalize_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Chuẩn hóa và validate document trước khi ghi file hoặc lập dry-run."""
    fields = [
        _normalized_field(field, index)
        for index, field in enumerate(document.get("fields") or ())
        if isinstance(field, Mapping)
    ]
    sections = [
        _normalized_section(section, index)
        for index, section in enumerate(document.get("sections") or ())
        if isinstance(section, Mapping)
    ]
    items = [
        _normalized_item(item, index)
        for index, item in enumerate(document.get("items") or ())
        if isinstance(item, Mapping)
    ]
    normalized = {
        "format_version": _text(
            document.get("format_version") or FORMAT_VERSION
        ),
        "style_code": _text(document.get("style_code")),
        "style_name": _text(document.get("style_name")),
        "title": _text(document.get("title")),
        "cost_sheet_status": _text(document.get("cost_sheet_status")),
        "cost_sheet_type": _text(
            document.get("cost_sheet_type") or "Internal Cost Sheets"
        ),
        "order_execution_type": _text(
            document.get("order_execution_type") or "Trading"
        ),
        "season": _text(document.get("season")),
        "template": _text(document.get("template") or "FOB"),
        "signature": _text(document.get("signature")),
        "fields": fields,
        "sections": sections,
        "items": items,
    }
    _validate_document(normalized)
    return normalized


def _semantic_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _text(value).casefold())


def _standard_section(
    section: Mapping[str, Any],
) -> tuple[int, str] | None:
    semantics = {
        _semantic_token(section.get("section_key")),
        _semantic_token(section.get("name")),
    }
    for index, (token, name) in enumerate(STANDARD_SECTIONS):
        if any(token in semantic for semantic in semantics):
            return index, name
    # Tương thích export cũ/test từng gọi section đầu tiên là "Fabric".
    if "fabric" in semantics:
        return 0, STANDARD_SECTIONS[0][1]
    return None


def _standard_section_token(section: Mapping[str, Any]) -> str:
    standard = _standard_section(section)
    return "" if standard is None else STANDARD_SECTIONS[standard[0]][0]


def _section_item_type(section: Mapping[str, Any]) -> str:
    return (
        "article"
        if _standard_section_token(section) in ARTICLE_SECTION_TOKENS
        else "cost_line"
    )


def _template_row_count(section: Mapping[str, Any]) -> int:
    return SPECIAL_COST_SECTION_ROWS.get(
        _standard_section_token(section),
        DEFAULT_NEW_ITEM_ROWS_PER_SECTION,
    )


def _production_summary_item(item: Mapping[str, Any]) -> bool:
    identity = _semantic_token(
        item.get("article_name") or item.get("item_key")
    )
    return identity in {"productioncosts", "otherprocessescost"}


def _form_field_key(
    definition: Mapping[str, Any],
    section: Mapping[str, Any],
) -> str:
    if (
        definition.get("label") == "Value"
        and _standard_section_token(section) == "productioncosts"
    ):
        return "ProductionValue"
    return str(definition["field_key"])


def _field_is_excluded(field: Mapping[str, Any]) -> bool:
    field_key = _semantic_token(
        re.sub(r"__\d+$", "", _text(field.get("field_key")))
    )
    label = _semantic_token(field.get("label"))
    return (
        any(token in field_key for token in _EXCLUDED_FIELD_TOKENS)
        or field_key in _EXCLUDED_FIELD_KEYS
        or label in _EXCLUDED_FIELD_LABELS
        or label in _EXCLUDED_FIELD_TOKENS
    )


def workbook_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Giữ đúng các dòng và ô người dùng được phép sửa trong file Costing."""
    normalized = normalize_document(document)
    selected_sections: dict[int, dict[str, Any]] = {}
    for section in normalized["sections"]:
        standard = _standard_section(section)
        if standard is None:
            continue
        index, name = standard
        selected_sections.setdefault(
            index,
            {
                **section,
                "name": name,
                "row_order": index + 1,
            },
        )
    for index, (token, name) in enumerate(STANDARD_SECTIONS):
        selected_sections.setdefault(
            index,
            {
                "section_key": f"standard:{token}",
                "name": name,
                "row_order": index + 1,
            },
        )
    sections = [
        selected_sections[index]
        for index in sorted(selected_sections)
    ]
    allowed_section_keys = {
        section["section_key"].casefold() for section in sections
    }
    section_by_key = {
        section["section_key"].casefold(): section for section in sections
    }
    items = [
        item
        for item in normalized["items"]
        if item["section_key"].casefold() in allowed_section_keys
        and item["item_type"]
        == _section_item_type(section_by_key[item["section_key"].casefold()])
        and not (
            _standard_section_token(
                section_by_key[item["section_key"].casefold()]
            )
            == "productioncosts"
            and _production_summary_item(item)
        )
    ]
    allowed_item_keys = {
        (item["section_key"].casefold(), item["item_key"].casefold())
        for item in items
    }
    fields = []
    standard_keys = {
        str(field["field_key"]).casefold()
        for field in STANDARD_ITEM_FIELDS
    } | {"productionvalue", "productionheaderminutes"}
    read_only_keys = {
        str(field["field_key"]).casefold()
        for field in STANDARD_ITEM_FIELDS
        if field.get("read_only")
    }
    for field in normalized["fields"]:
        base_field_key = re.sub(
            r"__\d+$",
            "",
            field["field_key"],
        ).casefold()
        if (
            field["scope"] != "item"
            or (
                not field["editable"]
                and base_field_key not in read_only_keys
            )
            or _field_is_excluded(field)
            or base_field_key not in standard_keys
        ):
            continue
        section_key = field["section_key"].casefold()
        if (
            field["scope"] in {"section", "item"}
            and allowed_section_keys
            and section_key not in allowed_section_keys
        ):
            continue
        if field["scope"] == "item" and (
            section_key,
            field["item_key"].casefold(),
        ) not in allowed_item_keys:
            continue
        fields.append(field)
    return normalize_document(
        {
            **normalized,
            "sections": sections,
            "items": items,
            "fields": fields,
        }
    )


def _document_size_errors(
    sections: Sequence[Mapping[str, Any]],
    items: Sequence[Mapping[str, Any]],
    fields: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if len(sections) > MAX_SECTIONS:
        errors.append(f"Quá {MAX_SECTIONS} section.")
    if len(items) > MAX_ITEMS:
        errors.append(f"Quá {MAX_ITEMS} Article.")
    if len(fields) > MAX_FIELDS:
        errors.append(f"Quá {MAX_FIELDS} field.")
    return errors


def _section_validation_errors(
    sections: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    section_keys: set[str] = set()
    for section in sections:
        key = _text(section.get("section_key"))
        if not key:
            errors.append("Section thiếu Section Key.")
        elif key in section_keys:
            errors.append(f"Section Key trùng: {key}.")
        section_keys.add(key)
    return errors


def _item_validation_errors(
    items: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    item_keys: set[tuple[str, str]] = set()
    for item in items:
        section_key = _text(item.get("section_key"))
        item_key = _text(item.get("item_key"))
        action = _text(item.get("action") or "UPSERT").upper()
        if not section_key:
            errors.append("Article thiếu Section Key.")
        if not item_key:
            errors.append(
                f"Article {_text(item.get('article_code')) or '(trống)'} "
                "thiếu Item Key."
            )
        composite = (section_key.casefold(), item_key.casefold())
        if all(composite) and composite in item_keys:
            errors.append(f"Item Key trùng trong section: {item_key}.")
        item_keys.add(composite)
        if action not in ITEM_ACTIONS:
            errors.append(f"Action không hợp lệ: {action}.")
        item_type = _text(item.get("item_type") or "article").casefold()
        if item_type not in ITEM_TYPES:
            errors.append(f"Item Type không hợp lệ: {item_type}.")
        if item_type == "article" and not (
            _text(item.get("article_code"))
            or _text(item.get("article_name"))
        ):
            errors.append(f"Article {item_key or '(trống)'} thiếu Code/Name.")
        if item_type == "cost_line" and not _text(item.get("article_name")):
            errors.append(f"Dòng chi phí {item_key or '(trống)'} thiếu tên.")
    return errors


def _field_validation_errors(
    fields: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    field_keys: set[tuple[str, str, str, str]] = set()
    for field in fields:
        scope = _text(field.get("scope")).casefold()
        field_key = _text(field.get("field_key"))
        if scope not in FIELD_SCOPES:
            errors.append(f"Field scope không hợp lệ: {scope or '(trống)'}.")
        if not field_key:
            errors.append("Field thiếu Field Key.")
        composite = (
            scope,
            _text(field.get("section_key")).casefold(),
            _text(field.get("item_key")).casefold(),
            field_key.casefold(),
        )
        if field_key and composite in field_keys:
            errors.append(
                "Field Key trùng trong cùng scope: "
                + " / ".join(part or "-" for part in composite)
            )
        field_keys.add(composite)
        if scope in {"section", "item"} and not _text(
            field.get("section_key")
        ):
            errors.append(f"Field {field_key or '(trống)'} thiếu Section Key.")
        if scope == "item" and not _text(field.get("item_key")):
            errors.append(f"Item field {field_key or '(trống)'} thiếu Item Key.")
        _reject_formula(field.get("value"), f"Field {field_key or '(trống)'}")
    return errors


def _validate_document(document: Mapping[str, Any]) -> None:
    if document.get("format_version") != FORMAT_VERSION:
        raise CostingWorkbookError(
            "COSTING_FORMAT_UNSUPPORTED",
            "Phiên bản file Costing không được hỗ trợ.",
            details=[
                f"Nhận {document.get('format_version') or 'trống'}; "
                f"cần {FORMAT_VERSION}."
            ],
        )
    sections = list(document.get("sections") or ())
    items = list(document.get("items") or ())
    fields = list(document.get("fields") or ())
    errors = [] if _text(document.get("style_code")) else ["Thiếu Style Code."]
    errors.extend(_document_size_errors(sections, items, fields))
    errors.extend(_section_validation_errors(sections))
    errors.extend(_item_validation_errors(items))
    errors.extend(_field_validation_errors(fields))

    if errors:
        raise CostingWorkbookError(
            "COSTING_VALIDATION_FAILED",
            "File Costing có dữ liệu chưa hợp lệ.",
            details=errors[:100],
        )


def _preflight_path(path: str | Path, *, must_exist: bool) -> Path:
    raw_path = str(path or "").strip()
    if not raw_path:
        raise CostingWorkbookError(
            "COSTING_FILE_REQUIRED",
            "Chưa chọn file Costing.",
        )
    target = Path(raw_path).expanduser()
    suffix = target.suffix.casefold()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise CostingWorkbookError(
            "COSTING_FILE_TYPE_UNSUPPORTED",
            "Costing chỉ hỗ trợ file .xlsx.",
        )
    if must_exist:
        if not target.is_file():
            raise CostingWorkbookError(
                "COSTING_FILE_REQUIRED",
                "File Costing không còn tồn tại.",
            )
        if target.stat().st_size > MAX_FILE_BYTES:
            raise CostingWorkbookError(
                "COSTING_FILE_TOO_LARGE",
                "File Costing lớn hơn giới hạn 12 MB.",
            )
        if suffix == ".xlsx":
            _preflight_xlsx_archive(target)
    return target


def _preflight_xlsx_archive(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_XLSX_MEMBERS:
                raise CostingWorkbookError(
                    "COSTING_FILE_TOO_LARGE",
                    "Workbook có quá nhiều thành phần.",
                )
            total = sum(max(0, member.file_size) for member in members)
            if total > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise CostingWorkbookError(
                    "COSTING_FILE_TOO_LARGE",
                    "Workbook giải nén lớn hơn giới hạn an toàn.",
                )
    except CostingWorkbookError:
        raise
    except (OSError, zipfile.BadZipFile) as error:
        raise CostingWorkbookError(
            "COSTING_VALIDATION_FAILED",
            "File XLSX bị hỏng hoặc không đúng định dạng.",
        ) from error
