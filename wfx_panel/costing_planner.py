"""Lập dry-run Costing thuần dữ liệu trước khi automation chạm WFX."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from wfx_panel.costing_workbook import CLEAR_MARKER, normalize_document

OPEN_STATUS = "open"


class CostingPlanError(ValueError):
    def __init__(self, code: str, message: str, **data: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def as_result(self) -> dict[str, Any]:
        return {
            "ok": False,
            "code": self.code,
            "message": self.message,
            **self.data,
        }


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _fold(value: Any) -> str:
    return _text(value).casefold()


def _same_value(left: Any, right: Any, data_type: str = "text") -> bool:
    if data_type in {"number", "numeric", "decimal", "integer"}:
        try:
            return float(_text(left) or 0) == float(_text(right) or 0)
        except ValueError:
            pass
    if data_type in {"boolean", "bool", "checkbox"}:
        truthy = {"1", "true", "yes", "y", "x", "có"}
        return (_fold(left) in truthy) == (_fold(right) in truthy)
    return _text(left) == _text(right)


def _identity(item: Mapping[str, Any]) -> tuple[str, str]:
    if _fold(item.get("item_type")) == "cost_line":
        return (
            _fold(item.get("section_key")),
            _fold(item.get("article_name") or item.get("item_key")),
        )
    return (
        _fold(item.get("section_key")),
        _fold(item.get("article_code") or item.get("article_name")),
    )


def live_signature(document: Mapping[str, Any]) -> str:
    normalized = normalize_document(document)
    payload = {
        "style_code": normalized["style_code"],
        "cost_sheet_status": normalized["cost_sheet_status"],
        "title": normalized["title"],
        "sections": [
            (
                section["section_key"],
                section["name"],
                section["row_order"],
            )
            for section in normalized["sections"]
        ],
        "items": [
            (
                item["section_key"],
                item["item_key"],
                item["item_type"],
                item["article_code"],
                item["article_name"],
                item["row_order"],
            )
            for item in normalized["items"]
        ],
        "fields": [
            (
                field["scope"],
                field["section_key"],
                field["item_key"],
                field["field_key"],
                field["value"],
                field["editable"],
            )
            for field in normalized["fields"]
            if _fold(field.get("field_key")) not in {
                "colcolordependencymapping",
                "colsizedependencymapping",
            }
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _field_key(field: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _fold(field.get("scope")),
        _fold(field.get("section_key")),
        _fold(field.get("item_key")),
        _fold(field.get("field_key")),
    )


def _display_field(field: Mapping[str, Any], value: Any) -> dict[str, Any]:
    return {
        "scope": _text(field.get("scope")),
        "section_key": _text(field.get("section_key")),
        "item_key": _text(field.get("item_key")),
        "field_key": _text(field.get("field_key")),
        "label": _text(field.get("label") or field.get("field_key")),
        "from_value": field.get("from_value", ""),
        "value": value,
        "data_type": _text(field.get("data_type") or "text"),
    }


def build_costing_plan(
    imported_document: Mapping[str, Any],
    live_document: Mapping[str, Any],
) -> dict[str, Any]:
    imported = normalize_document(imported_document)
    live = normalize_document(live_document)
    if _fold(imported["style_code"]) != _fold(live["style_code"]):
        raise CostingPlanError(
            "COSTING_STYLE_MISMATCH",
            "Style Code trong file không khớp style đang mở trên WFX.",
            file_style=imported["style_code"],
            live_style=live["style_code"],
        )

    status = _fold(live.get("cost_sheet_status"))
    if status != OPEN_STATUS:
        raise CostingPlanError(
            "COSTING_NOT_OPEN",
            "CostSheet phải ở trạng thái Open trước khi import.",
            costing_status=live.get("cost_sheet_status") or "Unknown",
        )
    live_sections = {
        _fold(section["section_key"]): section for section in live["sections"]
    }
    imported_items = list(imported["items"])
    live_item_candidates_by_identity: dict[
        tuple[str, str, str],
        list[dict[str, Any]],
    ] = {}
    for live_item in live["items"]:
        identity = _identity(live_item)
        if not all(identity):
            continue
        live_item_candidates_by_identity.setdefault(identity, []).append(
            live_item
        )
    live_items_by_key = {
        (
            _fold(item["section_key"]),
            _fold(item["item_key"]),
        ): item
        for item in live["items"]
    }

    item_mapping: dict[tuple[str, str], dict[str, Any] | None] = {}
    exact_item_keys: set[tuple[str, str]] = set()
    imported_items_by_key = {
        (_fold(item["section_key"]), _fold(item["item_key"])): item
        for item in imported_items
    }
    additions: list[dict[str, Any]] = []
    splits: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    deletes: list[dict[str, Any]] = []
    skips: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    missing_sections: set[str] = set()
    consumed_live_keys: set[tuple[str, str]] = set()
    seen_upsert_identities: dict[tuple[str, str], int] = {}

    for item in imported_items:
        section_key = _fold(item["section_key"])
        imported_key = (section_key, _fold(item["item_key"]))
        live_item = live_items_by_key.get(imported_key)
        if live_item is not None:
            exact_item_keys.add(imported_key)
            consumed_live_keys.add(
                (section_key, _fold(live_item.get("item_key")))
            )
        else:
            candidates = live_item_candidates_by_identity.get(
                _identity(item),
                [],
            )
            live_item = next(
                (
                    candidate
                    for candidate in candidates
                    if (
                        section_key,
                        _fold(candidate.get("item_key")),
                    )
                    not in consumed_live_keys
                ),
                None,
            )
            if live_item is not None:
                consumed_live_keys.add(
                    (section_key, _fold(live_item.get("item_key")))
                )
        item_mapping[imported_key] = live_item
        if section_key not in live_sections:
            missing_sections.add(item["section_key"])
            warnings.append(
                {
                    "kind": "section_not_found",
                    "section_key": item["section_key"],
                    "article_code": item["article_code"],
                }
            )
            continue
        action = item["action"]
        summary = {
            "section_key": item["section_key"],
            "section_name": item["section_name"],
            "import_item_key": item["item_key"],
            "live_item_key": _text((live_item or {}).get("item_key")),
            "article_code": item["article_code"],
            "article_name": item["article_name"],
            "row_order": item["row_order"],
            "action": action,
            "item_type": item["item_type"],
        }
        if action == "SKIP":
            skips.append(summary)
        elif action == "DELETE":
            if item["item_type"] == "cost_line":
                warnings.append(
                    {
                        **summary,
                        "kind": "cost_line_delete_not_supported",
                    }
                )
                continue
            if live_item is None:
                warnings.append(
                    {
                        **summary,
                        "kind": "delete_target_not_found",
                    }
                )
            else:
                deletes.append(summary)
        elif item["item_type"] == "cost_line":
            if live_item is not None:
                updates.append(summary)
            else:
                warnings.append(
                    {
                        **summary,
                        "kind": "cost_line_not_found",
                    }
                )
        elif live_item is None:
            identity = _identity(item)
            occurrence = seen_upsert_identities.get(identity, 0) + 1
            if occurrence > 1 or live_item_candidates_by_identity.get(identity):
                splits.append(
                    {
                        **summary,
                        "occurrence": occurrence,
                        "source_item_key": _text(
                            (
                                live_item_candidates_by_identity.get(identity)
                                or [{}]
                            )[-1].get("item_key")
                        ),
                    }
                )
            else:
                additions.append(summary)
            seen_upsert_identities[identity] = occurrence
        else:
            updates.append(summary)
            identity = _identity(item)
            seen_upsert_identities[identity] = (
                seen_upsert_identities.get(identity, 0) + 1
            )

    live_field_index = {_field_key(field): field for field in live["fields"]}
    fields_to_set: list[dict[str, Any]] = []
    unchanged_fields: list[dict[str, Any]] = []
    unsupported_fields: list[dict[str, Any]] = []
    skipped_item_keys = {
        (_fold(item["section_key"]), _fold(item["item_key"]))
        for item in imported_items
        if item["action"] == "SKIP"
    }
    delete_item_keys = {
        (_fold(item["section_key"]), _fold(item["item_key"]))
        for item in imported_items
        if item["action"] == "DELETE"
    }

    for imported_field in imported["fields"]:
        raw_value = imported_field.get("value")
        is_minutes = (
            _fold(imported_field.get("field_key")) == "minutes"
            or _fold(imported_field.get("label")) == "minutes"
        )
        if _text(raw_value) == "" and not is_minutes:
            continue
        target_value = 1 if is_minutes else raw_value
        if _text(target_value) == CLEAR_MARKER:
            target_value = ""

        source_item_key = (
            _fold(imported_field["section_key"]),
            _fold(imported_field["item_key"]),
        )
        if imported_field["scope"] == "item":
            if source_item_key in skipped_item_keys or source_item_key in delete_item_keys:
                continue
            mapped_item = item_mapping.get(source_item_key)
            target_item_key = _text((mapped_item or {}).get("item_key"))
            if not target_item_key:
                # Article mới: metadata field của file sẽ được áp dụng sau Add.
                entry = _display_field(imported_field, target_value)
                entry["target_item_key"] = ""
                fields_to_set.append(entry)
                continue
        else:
            target_item_key = ""

        live_key = (
            imported_field["scope"],
            _fold(imported_field["section_key"]),
            _fold(target_item_key or imported_field["item_key"]),
            _fold(imported_field["field_key"]),
        )
        live_field = live_field_index.get(live_key)
        if (
            imported_field["scope"] == "item"
            and source_item_key not in exact_item_keys
            and mapped_item is not None
        ):
            imported_item = imported_items_by_key.get(source_item_key)
            candidates = live_item_candidates_by_identity.get(
                _identity(imported_item or {}),
                [],
            )
            matching_fields = [
                candidate_field
                for candidate in candidates
                if (
                    candidate_field := live_field_index.get(
                        (
                            "item",
                            _fold(imported_field["section_key"]),
                            _fold(candidate["item_key"]),
                            _fold(imported_field["field_key"]),
                        )
                    )
                )
                is not None
            ]
            if matching_fields:
                # Workbook cũ từng gộp các dòng ">>" của cùng Article.
                # Ghép từng field về dòng thực sự chứa field đó; nếu field
                # xuất hiện ở nhiều dòng thì dòng cuối khớp cách exporter cũ
                # đã giữ giá trị cuối cùng.
                live_field = matching_fields[-1]
                target_item_key = _text(live_field.get("item_key"))
        if live_field is None:
            unsupported_fields.append(
                {
                    **_display_field(imported_field, target_value),
                    "reason": "not_found",
                }
            )
            continue
        if not live_field["editable"]:
            if not _same_value(
                live_field.get("value"),
                target_value,
                imported_field["data_type"],
            ):
                unsupported_fields.append(
                    {
                        **_display_field(imported_field, target_value),
                        "reason": "read_only",
                    }
                )
            continue
        entry = _display_field(imported_field, target_value)
        entry["item_key"] = target_item_key or imported_field["item_key"]
        entry["from_value"] = live_field.get("value", "")
        if _same_value(
            live_field.get("value"),
            target_value,
            imported_field["data_type"],
        ):
            unchanged_fields.append(entry)
        else:
            fields_to_set.append(entry)

    ordered_additions = sorted(
        additions,
        key=lambda item: (
            _fold(item["section_key"]),
            item["row_order"],
            _fold(item["article_code"] or item["article_name"]),
        ),
    )
    ordered_splits = sorted(
        splits,
        key=lambda item: (
            _fold(item["section_key"]),
            item["row_order"],
            _fold(item["article_code"] or item["article_name"]),
        ),
    )

    # WFX chỉ báo Purchase Officer bắt buộc ở bước Save. Chặn ngay trong
    # dry-run để không thay đổi nửa chừng rồi mới thất bại.
    purchase_key = "colpurchaseofficer"
    purchase_required = any(
        field["scope"] == "item"
        and _fold(field.get("field_key")).split("__", 1)[0] == purchase_key
        and field.get("required")
        for field in live["fields"]
    )
    if purchase_required:
        imported_purchase = {
            (
                _fold(field.get("section_key")),
                _fold(field.get("item_key")),
            ): _text(field.get("value"))
            for field in imported["fields"]
            if field["scope"] == "item"
            and _fold(field.get("field_key")).split("__", 1)[0] == purchase_key
        }
        live_purchase = {
            (
                _fold(field.get("section_key")),
                _fold(field.get("item_key")),
            ): _text(field.get("value"))
            for field in live["fields"]
            if field["scope"] == "item"
            and _fold(field.get("field_key")).split("__", 1)[0] == purchase_key
        }
        missing_purchase: list[dict[str, Any]] = []
        for item in imported_items:
            if item["action"] != "UPSERT" or item["item_type"] != "article":
                continue
            source_key = (
                _fold(item["section_key"]),
                _fold(item["item_key"]),
            )
            mapped = item_mapping.get(source_key)
            imported_value = imported_purchase.get(source_key, "")
            mapped_value = live_purchase.get(
                (
                    _fold(item["section_key"]),
                    _fold((mapped or {}).get("item_key")),
                ),
                "",
            )
            inherited_value = ""
            if mapped is None:
                for candidate in reversed(
                    live_item_candidates_by_identity.get(_identity(item), [])
                ):
                    inherited_value = live_purchase.get(
                        (
                            _fold(candidate.get("section_key")),
                            _fold(candidate.get("item_key")),
                        ),
                        "",
                    )
                    if inherited_value:
                        break
            if (
                imported_value
                and imported_value != CLEAR_MARKER
            ) or mapped_value or inherited_value:
                continue
            missing_purchase.append(
                {
                    "section_key": item["section_key"],
                    "item_key": item["item_key"],
                    "article_code": item["article_code"],
                    "article_name": item["article_name"],
                    "row_order": item["row_order"],
                    "field_key": "colPurchaseOfficer",
                    "label": "Purchase Officer",
                }
            )
        if missing_purchase:
            raise CostingPlanError(
                "COSTING_REQUIRED_FIELD_MISSING",
                (
                    "Purchase Officer là bắt buộc. Hãy chọn trong dropdown "
                    "của file Costing rồi kiểm tra lại."
                ),
                missing_required_fields=missing_purchase,
            )

    return {
        "ok": True,
        "code": "COSTING_DRY_RUN_READY",
        "message": (
            "Dry-run Costing đã sẵn sàng. Kiểm tra thay đổi trước khi áp dụng."
        ),
        "style_code": imported["style_code"],
        "costing_status": live.get("cost_sheet_status") or "",
        "new_required": False,
        "live_signature": live_signature(live),
        "fields_to_set": fields_to_set,
        "unchanged_fields": unchanged_fields,
        "additions": ordered_additions,
        "splits": ordered_splits,
        "updates": updates,
        "deletes": deletes,
        "skips": skips,
        "unsupported_fields": unsupported_fields,
        "warnings": warnings,
        "missing_sections": sorted(missing_sections),
        "article_searches": [
            {
                "section_key": item["section_key"],
                "item_key": item["import_item_key"],
                "article_code": item["article_code"],
                "article_name": item["article_name"],
            }
            for item in ordered_additions
        ],
        "counts": {
            "fields_to_set": len(fields_to_set),
            "unchanged_fields": len(unchanged_fields),
            "additions": len(additions),
            "splits": len(splits),
            "updates": len(updates),
            "deletes": len(deletes),
            "skips": len(skips),
            "unsupported_fields": len(unsupported_fields),
            "warnings": len(warnings),
        },
    }
