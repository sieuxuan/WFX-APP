"""Lập dry-run Costing thuần dữ liệu trước khi automation chạm WFX."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
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


ItemKey = tuple[str, str]
ItemIdentity = tuple[str, str]
FieldKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class _LiveCostingIndex:
    section_keys: frozenset[str]
    items_by_key: dict[ItemKey, dict[str, Any]]
    items_by_identity: dict[ItemIdentity, list[dict[str, Any]]]
    fields_by_key: dict[FieldKey, dict[str, Any]]
    fields_by_identity: dict[
        tuple[ItemIdentity, str],
        list[dict[str, Any]],
    ]


@dataclass
class _ItemPlan:
    imported_by_key: dict[ItemKey, dict[str, Any]] = field(default_factory=dict)
    live_by_imported_key: dict[ItemKey, dict[str, Any] | None] = field(
        default_factory=dict
    )
    exact_live_keys: set[ItemKey] = field(default_factory=set)
    deleted_keys: set[ItemKey] = field(default_factory=set)
    additions: list[dict[str, Any]] = field(default_factory=list)
    cost_line_additions: list[dict[str, Any]] = field(default_factory=list)
    splits: list[dict[str, Any]] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)
    deletes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    missing_sections: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class _FieldContext:
    item_plan: _ItemPlan
    live_index: _LiveCostingIndex


@dataclass
class _FieldPlan:
    fields_to_set: list[dict[str, Any]] = field(default_factory=list)
    unchanged_fields: list[dict[str, Any]] = field(default_factory=list)
    unsupported_fields: list[dict[str, Any]] = field(default_factory=list)


def _item_key(item: Mapping[str, Any]) -> ItemKey:
    return (
        _fold(item.get("section_key")),
        _fold(item.get("item_key")),
    )


def _build_live_index(live: Mapping[str, Any]) -> _LiveCostingIndex:
    items_by_key: dict[ItemKey, dict[str, Any]] = {}
    items_by_identity: dict[ItemIdentity, list[dict[str, Any]]] = {}
    for live_item in live["items"]:
        key = _item_key(live_item)
        items_by_key[key] = live_item
        identity = _identity(live_item)
        if all(identity):
            items_by_identity.setdefault(identity, []).append(live_item)

    fields_by_key = {_field_key(field): field for field in live["fields"]}
    fields_by_item: dict[ItemKey, dict[str, dict[str, Any]]] = {}
    for field_data in live["fields"]:
        if _fold(field_data.get("scope")) != "item":
            continue
        fields_by_item.setdefault(_item_key(field_data), {})[
            _fold(field_data.get("field_key"))
        ] = field_data

    fields_by_identity: dict[
        tuple[ItemIdentity, str],
        list[dict[str, Any]],
    ] = {}
    for identity, candidates in items_by_identity.items():
        for candidate in candidates:
            for field_name, field_data in fields_by_item.get(
                _item_key(candidate), {}
            ).items():
                fields_by_identity.setdefault(
                    (identity, field_name), []
                ).append(field_data)

    return _LiveCostingIndex(
        section_keys=frozenset(
            _fold(section["section_key"]) for section in live["sections"]
        ),
        items_by_key=items_by_key,
        items_by_identity=items_by_identity,
        fields_by_key=fields_by_key,
        fields_by_identity=fields_by_identity,
    )


def _validate_documents(
    imported: Mapping[str, Any],
    live: Mapping[str, Any],
) -> None:
    if _fold(imported["style_code"]) != _fold(live["style_code"]):
        raise CostingPlanError(
            "COSTING_STYLE_MISMATCH",
            "Style Code trong file không khớp style đang mở trên WFX.",
            file_style=imported["style_code"],
            live_style=live["style_code"],
        )
    if _fold(live.get("cost_sheet_status")) == OPEN_STATUS:
        return
    raise CostingPlanError(
        "COSTING_NOT_OPEN",
        "CostSheet phải ở trạng thái Open trước khi import.",
        costing_status=live.get("cost_sheet_status") or "Unknown",
    )


def _match_live_item(
    imported_item: Mapping[str, Any],
    live_index: _LiveCostingIndex,
    consumed_live_keys: set[ItemKey],
) -> tuple[dict[str, Any] | None, bool]:
    imported_key = _item_key(imported_item)
    exact_match = live_index.items_by_key.get(imported_key)
    if exact_match is not None:
        consumed_live_keys.add(_item_key(exact_match))
        return exact_match, True

    for candidate in live_index.items_by_identity.get(
        _identity(imported_item), ()
    ):
        candidate_key = _item_key(candidate)
        if candidate_key in consumed_live_keys:
            continue
        consumed_live_keys.add(candidate_key)
        return candidate, False
    return None, False


def _item_summary(
    imported_item: Mapping[str, Any],
    live_item: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "section_key": imported_item["section_key"],
        "section_name": imported_item["section_name"],
        "import_item_key": imported_item["item_key"],
        "live_item_key": _text((live_item or {}).get("item_key")),
        "article_code": imported_item["article_code"],
        "article_name": imported_item["article_name"],
        "row_order": imported_item["row_order"],
        "action": imported_item["action"],
        "item_type": imported_item["item_type"],
    }


def _classify_item_action(
    imported_item: Mapping[str, Any],
    live_item: Mapping[str, Any] | None,
    live_index: _LiveCostingIndex,
    plan: _ItemPlan,
    upsert_counts: dict[ItemIdentity, int],
) -> None:
    summary = _item_summary(imported_item, live_item)
    action = imported_item["action"]
    if action == "DELETE":
        if imported_item["item_type"] == "cost_line":
            plan.warnings.append(
                {**summary, "kind": "cost_line_delete_not_supported"}
            )
        elif live_item is None:
            plan.warnings.append(
                {**summary, "kind": "delete_target_not_found"}
            )
        else:
            plan.deletes.append(summary)
        return
    if imported_item["item_type"] == "cost_line":
        if live_item is None:
            plan.cost_line_additions.append(summary)
        else:
            plan.updates.append(summary)
        return

    identity = _identity(imported_item)
    occurrence = upsert_counts.get(identity, 0) + 1
    upsert_counts[identity] = occurrence
    if live_item is not None:
        plan.updates.append(summary)
        return
    candidates = live_index.items_by_identity.get(identity, [])
    if occurrence == 1 and not candidates:
        plan.additions.append(summary)
        return
    plan.splits.append(
        {
            **summary,
            "occurrence": occurrence,
            "source_item_key": _text((candidates or [{}])[-1].get("item_key")),
        }
    )


def _plan_items(
    imported_items: list[dict[str, Any]],
    live_index: _LiveCostingIndex,
) -> _ItemPlan:
    plan = _ItemPlan()
    consumed_live_keys: set[ItemKey] = set()
    upsert_counts: dict[ItemIdentity, int] = {}
    for imported_item in imported_items:
        imported_key = _item_key(imported_item)
        plan.imported_by_key[imported_key] = imported_item
        if imported_item["action"] == "DELETE":
            plan.deleted_keys.add(imported_key)

        live_item, is_exact_match = _match_live_item(
            imported_item,
            live_index,
            consumed_live_keys,
        )
        plan.live_by_imported_key[imported_key] = live_item
        if is_exact_match:
            plan.exact_live_keys.add(imported_key)

        section_key = _fold(imported_item["section_key"])
        if section_key not in live_index.section_keys:
            plan.missing_sections.add(imported_item["section_key"])
            plan.warnings.append(
                {
                    "kind": "section_not_found",
                    "section_key": imported_item["section_key"],
                    "article_code": imported_item["article_code"],
                }
            )
            continue
        _classify_item_action(
            imported_item,
            live_item,
            live_index,
            plan,
            upsert_counts,
        )
    return plan


def _target_field_value(imported_field: Mapping[str, Any]) -> tuple[bool, Any]:
    raw_value = imported_field.get("value")
    is_minutes = (
        _fold(imported_field.get("field_key")) == "minutes"
        or _fold(imported_field.get("label")) == "minutes"
    )
    if not is_minutes and _text(raw_value) == "":
        return False, None
    target_value = 1 if is_minutes else raw_value
    return True, "" if _text(target_value) == CLEAR_MARKER else target_value


def _resolve_live_field(
    imported_field: Mapping[str, Any],
    imported_key: ItemKey,
    mapped_item: Mapping[str, Any] | None,
    target_item_key: str,
    context: _FieldContext,
) -> tuple[dict[str, Any] | None, str]:
    field_name = _fold(imported_field["field_key"])
    lookup_key = (
        _fold(imported_field["scope"]),
        _fold(imported_field["section_key"]),
        _fold(target_item_key or imported_field["item_key"]),
        field_name,
    )
    live_field = context.live_index.fields_by_key.get(lookup_key)
    if (
        _fold(imported_field["scope"]) != "item"
        or imported_key in context.item_plan.exact_live_keys
        or mapped_item is None
    ):
        return live_field, target_item_key

    imported_item = context.item_plan.imported_by_key.get(imported_key, {})
    identity_matches = context.live_index.fields_by_identity.get(
        (_identity(imported_item), field_name),
        [],
    )
    if not identity_matches:
        return live_field, target_item_key
    # Workbook cũ từng gộp dòng ">>". Dòng cuối giữ giá trị exporter cũ.
    resolved_field = identity_matches[-1]
    return resolved_field, _text(resolved_field.get("item_key"))


def _classify_field_change(
    imported_field: Mapping[str, Any],
    target_value: Any,
    target_item_key: str,
    live_field: Mapping[str, Any] | None,
    plan: _FieldPlan,
) -> None:
    if live_field is None:
        plan.unsupported_fields.append(
            {
                **_display_field(imported_field, target_value),
                "reason": "not_found",
            }
        )
        return
    values_match = _same_value(
        live_field.get("value"),
        target_value,
        imported_field["data_type"],
    )
    if not live_field["editable"]:
        if not values_match:
            plan.unsupported_fields.append(
                {
                    **_display_field(imported_field, target_value),
                    "reason": "read_only",
                }
            )
        return
    entry = _display_field(imported_field, target_value)
    entry["item_key"] = target_item_key or imported_field["item_key"]
    entry["from_value"] = live_field.get("value", "")
    target = plan.unchanged_fields if values_match else plan.fields_to_set
    target.append(entry)


def _plan_fields(
    imported_fields: list[dict[str, Any]],
    item_plan: _ItemPlan,
    live_index: _LiveCostingIndex,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    context = _FieldContext(item_plan=item_plan, live_index=live_index)
    plan = _FieldPlan()
    ignored_item_keys = item_plan.deleted_keys
    for imported_field in imported_fields:
        should_apply, target_value = _target_field_value(imported_field)
        if not should_apply:
            continue
        imported_key = _item_key(imported_field)
        mapped_item = item_plan.live_by_imported_key.get(imported_key)
        target_item_key = ""
        if _fold(imported_field["scope"]) == "item":
            if imported_key in ignored_item_keys:
                continue
            target_item_key = _text((mapped_item or {}).get("item_key"))
            if not target_item_key:
                entry = _display_field(imported_field, target_value)
                entry["target_item_key"] = ""
                plan.fields_to_set.append(entry)
                continue
        live_field, target_item_key = _resolve_live_field(
            imported_field,
            imported_key,
            mapped_item,
            target_item_key,
            context,
        )
        _classify_field_change(
            imported_field,
            target_value,
            target_item_key,
            live_field,
            plan,
        )
    return plan.fields_to_set, plan.unchanged_fields, plan.unsupported_fields


def _purchase_values(fields: list[dict[str, Any]]) -> dict[ItemKey, str]:
    purchase_key = "colpurchaseofficer"
    return {
        _item_key(field_data): _text(field_data.get("value"))
        for field_data in fields
        if _fold(field_data.get("scope")) == "item"
        and _fold(field_data.get("field_key")).split("__", 1)[0]
        == purchase_key
    }


def _inherited_purchase_values(
    live_index: _LiveCostingIndex,
    live_purchase: Mapping[ItemKey, str],
) -> dict[ItemIdentity, str]:
    inherited: dict[ItemIdentity, str] = {}
    for identity, candidates in live_index.items_by_identity.items():
        for candidate in reversed(candidates):
            value = live_purchase.get(_item_key(candidate), "")
            if value:
                inherited[identity] = value
                break
    return inherited


def _validate_purchase_officer(
    imported_items: list[dict[str, Any]],
    imported_fields: list[dict[str, Any]],
    live_fields: list[dict[str, Any]],
    item_plan: _ItemPlan,
    live_index: _LiveCostingIndex,
) -> None:
    purchase_key = "colpurchaseofficer"
    is_required = any(
        _fold(field_data.get("scope")) == "item"
        and _fold(field_data.get("field_key")).split("__", 1)[0]
        == purchase_key
        and field_data.get("required")
        for field_data in live_fields
    )
    if not is_required:
        return
    imported_purchase = _purchase_values(imported_fields)
    live_purchase = _purchase_values(live_fields)
    inherited_purchase = _inherited_purchase_values(
        live_index,
        live_purchase,
    )
    missing_fields: list[dict[str, Any]] = []
    for imported_item in imported_items:
        if (
            imported_item["action"] != "UPSERT"
            or imported_item["item_type"] != "article"
        ):
            continue
        imported_key = _item_key(imported_item)
        mapped_item = item_plan.live_by_imported_key.get(imported_key)
        imported_value = imported_purchase.get(imported_key, "")
        mapped_value = live_purchase.get(
            _item_key(mapped_item or {}),
            "",
        )
        inherited_value = (
            inherited_purchase.get(_identity(imported_item), "")
            if mapped_item is None
            else ""
        )
        if (
            (imported_value and imported_value != CLEAR_MARKER)
            or mapped_value
            or inherited_value
        ):
            continue
        missing_fields.append(
            {
                "section_key": imported_item["section_key"],
                "item_key": imported_item["item_key"],
                "article_code": imported_item["article_code"],
                "article_name": imported_item["article_name"],
                "row_order": imported_item["row_order"],
                "field_key": "colPurchaseOfficer",
                "label": "Purchase Officer",
            }
        )
    if not missing_fields:
        return
    raise CostingPlanError(
        "COSTING_REQUIRED_FIELD_MISSING",
        (
            "Purchase Officer là bắt buộc. Hãy chọn trong dropdown "
            "của file Costing rồi kiểm tra lại."
        ),
        missing_required_fields=missing_fields,
    )


def _item_sort_key(item: Mapping[str, Any]) -> tuple[str, Any, str]:
    return (
        _fold(item["section_key"]),
        item["row_order"],
        _fold(item["article_code"] or item["article_name"]),
    )


def build_costing_plan(
    imported_document: Mapping[str, Any],
    live_document: Mapping[str, Any],
) -> dict[str, Any]:
    imported = normalize_document(imported_document)
    live = normalize_document(live_document)
    _validate_documents(imported, live)
    imported_items = list(imported["items"])
    live_index = _build_live_index(live)
    item_plan = _plan_items(imported_items, live_index)
    fields_to_set, unchanged_fields, unsupported_fields = _plan_fields(
        list(imported["fields"]),
        item_plan,
        live_index,
    )
    _validate_purchase_officer(
        imported_items,
        list(imported["fields"]),
        list(live["fields"]),
        item_plan,
        live_index,
    )
    ordered_additions = sorted(item_plan.additions, key=_item_sort_key)
    ordered_cost_line_additions = sorted(
        item_plan.cost_line_additions,
        key=_item_sort_key,
    )
    ordered_splits = sorted(item_plan.splits, key=_item_sort_key)

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
        "cost_line_additions": ordered_cost_line_additions,
        "splits": ordered_splits,
        "updates": item_plan.updates,
        "deletes": item_plan.deletes,
        "unsupported_fields": unsupported_fields,
        "warnings": item_plan.warnings,
        "missing_sections": sorted(item_plan.missing_sections),
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
            "additions": len(item_plan.additions),
            "cost_line_additions": len(item_plan.cost_line_additions),
            "splits": len(item_plan.splits),
            "updates": len(item_plan.updates),
            "deletes": len(item_plan.deletes),
            "unsupported_fields": len(unsupported_fields),
            "warnings": len(item_plan.warnings),
        },
    }
