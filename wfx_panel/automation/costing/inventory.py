"""Quét Costing live thành document workbook."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from wfx_panel.automation._common import Frame, PlaywrightError, _sleep, time
from wfx_panel.automation.costing.articles import _scan_costing_article_dropdowns
from wfx_panel.automation.costing.constants import (
    _COSTING_INVENTORY_JS,
    _SPECIAL_COST_SECTION_EDITORS,
    FORBIDDEN_CONTROL_IDS,
)
from wfx_panel.automation.costing.dependencies import (
    _dependency_scan_incomplete,
    _scan_costing_dependency_tables,
)
from wfx_panel.automation.costing.dom import _visible_costing_grid
from wfx_panel.automation.costing.keys import (
    _base_costing_field_key,
    _clean_key,
    _costing_semantic_token,
)
from wfx_panel.costing_planner import live_signature
from wfx_panel.costing_workbook import FORMAT_VERSION, normalize_document


def _inventory_to_document(
    payload: Mapping[str, Any],
    article_code: str,
    *,
    costing_status: str = "",
    season: str = "",
    style_name: str = "",
) -> dict[str, Any]:
    raw_sections = [
        raw for raw in payload.get("sections") or () if isinstance(raw, Mapping)
    ]
    raw_fields = [
        raw for raw in payload.get("fields") or () if isinstance(raw, Mapping)
    ]
    sections: list[dict[str, Any]] = []
    section_names: dict[str, str] = {}
    for index, raw in enumerate(raw_sections):
        key = _clean_key(raw.get("sectionKey"), f"section-{index + 1}")
        if key in section_names:
            continue
        name = str(raw.get("name") or key).strip()
        section_names[key] = name
        sections.append(
            {
                "section_key": key,
                "name": name,
                "row_order": int(raw.get("rowOrder") or index),
            }
        )

    items: list[dict[str, Any]] = []
    item_seen: set[tuple[str, str]] = set()
    fields: list[dict[str, Any]] = []
    field_seen: dict[tuple[str, str, str, str], int] = {}

    for index, raw in enumerate(raw_fields):
        dom_id = str(raw.get("domId") or "").strip()
        if dom_id in FORBIDDEN_CONTROL_IDS:
            continue
        raw_section = str(raw.get("sectionKey") or "").strip()
        section_key = _clean_key(raw_section, "") if raw_section else ""
        if section_key and section_key not in section_names:
            section_name = str(raw.get("sectionName") or section_key).strip()
            section_names[section_key] = section_name
            sections.append(
                {
                    "section_key": section_key,
                    "name": section_name,
                    "row_order": len(sections),
                }
            )
        raw_item = str(raw.get("itemKey") or "").strip()
        item_key = _clean_key(raw_item, "") if raw_item else ""
        article_item = bool(
            item_key
            or str(raw.get("articleCode") or "").strip()
            or str(raw.get("articleName") or "").strip()
        )
        scope = "item" if article_item else "section" if section_key else "cost_sheet"
        if scope == "item":
            if not item_key:
                item_key = _clean_key(
                    raw.get("articleCode") or raw.get("articleName"),
                    f"item-{index + 1}",
                )
            composite_item = (section_key.casefold(), item_key.casefold())
            if composite_item not in item_seen:
                item_seen.add(composite_item)
                items.append(
                    {
                        "section_key": section_key,
                        "section_name": section_names.get(section_key, section_key),
                        "item_key": item_key,
                        "row_order": int(raw.get("rowOrder") or len(items)),
                        "action": "UPSERT",
                        "item_type": str(raw.get("itemType") or "article")
                        .strip()
                        .casefold(),
                        "article_code": str(raw.get("articleCode") or "").strip(),
                        "article_name": str(raw.get("articleName") or "").strip(),
                    }
                )
        raw_label = str(raw.get("label") or "").strip()
        base_key = (
            "Minutes"
            if raw_label.casefold() == "minutes"
            else _clean_key(
                raw.get("dataField")
                or raw.get("domName")
                or dom_id
                or raw_label,
                f"field-{index + 1}",
            )
        )
        composite = (
            scope,
            section_key.casefold(),
            item_key.casefold(),
            base_key.casefold(),
        )
        ordinal = field_seen.get(composite, 0) + 1
        field_seen[composite] = ordinal
        field_key = base_key if ordinal == 1 else f"{base_key}__{ordinal}"
        fields.append(
            {
                "scope": scope,
                "section_key": section_key if scope != "cost_sheet" else "",
                "item_key": item_key if scope == "item" else "",
                "field_key": field_key,
                "label": raw_label or base_key,
                "value": raw.get("value", ""),
                "data_type": str(raw.get("dataType") or "text").casefold(),
                "editable": bool(raw.get("editable")),
                "required": bool(raw.get("required")),
                "options": list(raw.get("options") or ()),
                "row_order": int(raw.get("rowOrder") or index),
                # Live-only metadata; normalize_document drops these keys before
                # workbook export, nên selector không thể quay lại từ file.
                "_live": {
                    "dom_index": int(raw.get("domIndex") or index),
                    "dom_id": dom_id,
                    "click_dom_id": str(raw.get("clickDomId") or dom_id).strip(),
                    "tag": str(raw.get("tag") or "").casefold(),
                    "input_type": str(raw.get("inputType") or "").casefold(),
                    "option_values": list(raw.get("optionValues") or ()),
                    "visible": bool(raw.get("visible")),
                    "region": str(raw.get("region") or ""),
                    "row_index": int(raw.get("rowIndex") or 0),
                    "row_control_index": int(raw.get("rowControlIndex") or 0),
                    "cell_id": str(raw.get("cellId") or ""),
                    "row_signature": str(raw.get("rowSignature") or ""),
                },
            }
        )

    document = {
        "format_version": FORMAT_VERSION,
        "style_code": str(article_code or "").strip(),
        "style_name": str(style_name or "").strip(),
        "title": str(payload.get("title") or "").strip(),
        "cost_sheet_status": str(costing_status or "").strip(),
        "cost_sheet_type": "Internal Cost Sheets",
        "order_execution_type": "Trading",
        "season": str(season or "").strip(),
        "template": "FOB",
        "sections": sections,
        "items": items,
        "fields": fields,
    }
    normalized = normalize_document(document)
    live_by_key = {
        (
            field["scope"],
            field["section_key"].casefold(),
            field["item_key"].casefold(),
            field["field_key"].casefold(),
        ): field.get("_live", {})
        for field in fields
    }
    for field in normalized["fields"]:
        field["_live"] = live_by_key.get(
            (
                field["scope"],
                field["section_key"].casefold(),
                field["item_key"].casefold(),
                field["field_key"].casefold(),
            ),
            {},
        )
    normalized["signature"] = live_signature(normalized)
    return normalized


def _add_production_value_fields(document: dict[str, Any]) -> None:
    """Expose Production header fields on each selectable process row."""
    production_sections = {
        str(section.get("section_key") or "").casefold()
        for section in document.get("sections") or ()
        if "productioncosts"
        in _costing_semantic_token(
            f"{section.get('section_key', '')} {section.get('name', '')}"
        )
    }
    if not production_sections:
        return
    items = {
        (
            str(item.get("section_key") or "").casefold(),
            str(item.get("item_key") or "").casefold(),
        ): item
        for item in document.get("items") or ()
    }
    parent_fields: dict[str, dict[str, Mapping[str, Any]]] = {}
    for field in document.get("fields") or ():
        section_key = str(field.get("section_key") or "").casefold()
        if section_key not in production_sections:
            continue
        item = items.get(
            (section_key, str(field.get("item_key") or "").casefold()),
            {},
        )
        if _costing_semantic_token(item.get("article_name")) != "productioncosts":
            continue
        field_key = _base_costing_field_key(field)
        if field_key == "colvalue":
            parent_fields.setdefault(section_key, {})["ProductionValue"] = field
        elif field_key == "minutes":
            parent_fields.setdefault(section_key, {})[
                "ProductionHeaderMinutes"
            ] = field
    existing = {
        (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            str(field.get("field_key") or "").casefold(),
        )
        for field in document.get("fields") or ()
    }
    additions: list[dict[str, Any]] = []
    for (section_key, _item_key), item in items.items():
        if section_key not in parent_fields:
            continue
        identity = _costing_semantic_token(
            item.get("article_name") or item.get("item_key")
        )
        if identity in {"productioncosts", "otherprocessescost"}:
            continue
        for virtual_key, parent in parent_fields[section_key].items():
            composite = (
                section_key,
                str(item.get("item_key") or "").casefold(),
                virtual_key.casefold(),
            )
            if composite in existing:
                continue
            additions.append(
                {
                    **parent,
                    "item_key": str(item.get("item_key") or ""),
                    "field_key": virtual_key,
                    "label": (
                        "Value" if virtual_key == "ProductionValue" else "Minutes"
                    ),
                    "_live": dict(parent.get("_live") or {}),
                }
            )
    document.setdefault("fields", []).extend(additions)


def _special_section_options(
    frame: Frame,
    section: Mapping[str, Any],
) -> list[str]:
    token = _costing_semantic_token(
        f"{section.get('section_key', '')} {section.get('name', '')}"
    )
    config = next(
        (
            value
            for name, value in _SPECIAL_COST_SECTION_EDITORS.items()
            if name in token
        ),
        None,
    )
    if config is None:
        return []
    header = frame.locator(
        f"tr.cssGridRow{config['header_class']} #imgAdd:visible"
    )
    if header.count() != 1:
        return []
    row_selector = f"tr.cssGridRow{config['row_class']}"
    existing_checkboxes = frame.locator(f"{row_selector} #chkSelector")
    checkbox_state = existing_checkboxes.evaluate_all(
        "elements => elements.map(element => ({value: element.value, checked: element.checked}))"
    )
    before = {str(item.get("value") or "") for item in checkbox_state}
    checked_before = {
        str(item.get("value") or "")
        for item in checkbox_state
        if item.get("checked")
    }
    existing_checkboxes.evaluate_all(
        "elements => elements.filter(element => element.checked).forEach(element => element.click())"
    )
    temporary_value = ""
    row = None
    try:
        header.click(timeout=2_000)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and row is None:
            rows = frame.locator(row_selector)
            for index in range(rows.count()):
                candidate = rows.nth(index)
                checkbox = candidate.locator("#chkSelector")
                value = (
                    str(checkbox.get_attribute("value") or "")
                    if checkbox.count()
                    else ""
                )
                if value not in before and value.startswith("-10"):
                    row = candidate
                    temporary_value = value
                    break
            if row is None:
                _sleep(0.1)
        if row is None:
            raise RuntimeError("COSTING_SPECIAL_OPTION_ROW_NOT_FOUND")
        row.locator(str(config["label"])).click(timeout=2_000)
        editor = row.locator(str(config["editor"]))
        editor.wait_for(state="visible", timeout=3_000)
        editor.dispatch_event("mousedown")
        deadline = time.monotonic() + 5
        options: list[str] = []
        while time.monotonic() < deadline:
            options = [
                str(value).strip()
                for value in editor.locator("option").all_inner_texts()
                if str(value).strip() not in {"", "[Select]", "[ALL]"}
            ]
            if options:
                break
            _sleep(0.1)
        return list(dict.fromkeys(options))
    finally:
        try:
            frame.locator("body").press("Escape")
        except PlaywrightError:
            pass
        if row is not None and temporary_value:
            checkbox = row.locator("#chkSelector")
            try:
                if checkbox.count() and not checkbox.is_checked():
                    checkbox.evaluate("element => element.click()")
                delete = frame.locator(
                    f"tr.cssGridRow{config['header_class']} #imgDelete:visible"
                )
                if delete.count() == 1:
                    delete.evaluate("element => element.click()")
                    _sleep(0.25)
            except PlaywrightError as error:
                raise RuntimeError("COSTING_SPECIAL_OPTION_CLEANUP_FAILED") from error
        remaining = frame.locator(f"{row_selector} #chkSelector")
        remaining.evaluate_all(
            """(elements, values) => elements
                .filter(element => values.includes(String(element.value)) && !element.checked)
                .forEach(element => element.click())""",
            sorted(checked_before),
        )


def _scan_special_cost_options(
    frame: Frame,
    document: dict[str, Any],
) -> None:
    for section in document.get("sections") or ():
        options = _special_section_options(frame, section)
        if options:
            section["article_options"] = options


def _inventory_costing_frame(
    frame: Frame,
    article_code: str,
    *,
    costing_status: str = "",
    season: str = "",
    title: str = "",
    style_name: str = "",
    scan_details: bool = False,
    scan_article_options: bool = False,
    scan_special_cost_options: bool = True,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    grid = _visible_costing_grid(frame)
    if grid is None:
        return normalize_document(
            {
                "format_version": FORMAT_VERSION,
                "style_code": article_code,
                "style_name": style_name,
                "title": title,
                "cost_sheet_status": costing_status,
                "cost_sheet_type": "Internal Cost Sheets",
                "order_execution_type": "Trading",
                "season": season,
                "template": "FOB",
                "sections": [],
                "items": [],
                "fields": [],
            }
        )
    payload = grid.evaluate(_COSTING_INVENTORY_JS)
    payload["title"] = title
    if not costing_status and (
        str(payload.get("title") or "").strip()
        or payload.get("sections")
        or payload.get("fields")
    ):
        # Khi grid/tree không cung cấp status nhưng detail thật có dữ liệu,
        # đây là Costing đang mở. Detail rỗng không được tự suy diễn là Open.
        costing_status = "Open"
    document = _inventory_to_document(
        payload,
        article_code,
        costing_status=costing_status,
        season=season,
        style_name=style_name,
    )
    _add_production_value_fields(document)
    _ensure_dependency_mapping_fields(document)
    if scan_details:
        if scan_special_cost_options:
            _scan_special_cost_options(frame, document)
            # Marker phân biệt snapshot rỗng hợp lệ với lần scan bị bỏ qua.
            document["special_cost_options_scanned"] = True
        _scan_costing_item_options(frame, document)
        _scan_costing_dependency_tables(frame, document)
        if _dependency_scan_incomplete(document):
            raise RuntimeError("COSTING_DEPENDENCY_SCAN_INCOMPLETE")
    if scan_article_options:
        _scan_costing_article_dropdowns(frame, document, log)
    document["signature"] = live_signature(document)
    return document


def _ensure_dependency_mapping_fields(document: dict[str, Any]) -> None:
    """Thêm field logic cho nội dung bên trong popup Dependency Table."""
    definitions = {
        "colcolordependency": (
            "colColorDependencyMapping",
            "Color Mapping",
            "Color",
        ),
        "colsizedependency": (
            "colSizeDependencyMapping",
            "Size Mapping",
            "Size",
        ),
    }
    fields = document.get("fields") or []
    existing = {
        (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            _base_costing_field_key(field),
        )
        for field in fields
    }
    additions = []
    for field in list(fields):
        definition = definitions.get(_base_costing_field_key(field))
        if definition is None or str(field.get("scope") or "") != "item":
            continue
        field_key, label, kind = definition
        identity = (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            field_key.casefold(),
        )
        if identity in existing:
            continue
        live = dict(field.get("_live") or {})
        live["dependency_kind"] = kind
        live["dependency_mode"] = str(field.get("value") or "")
        additions.append(
            {
                "scope": "item",
                "section_key": str(field.get("section_key") or ""),
                "item_key": str(field.get("item_key") or ""),
                "field_key": field_key,
                "label": label,
                "value": "",
                "data_type": "text",
                "editable": True,
                "required": False,
                "options": [],
                "row_order": int(field.get("row_order") or 0),
                "_live": live,
            }
        )
        existing.add(identity)
    fields.extend(additions)


def _scan_costing_item_options(
    frame: Frame,
    document: dict[str, Any],
) -> None:
    fields = [
        field
        for field in document.get("fields") or ()
        if _base_costing_field_key(field)
        in {"colmaterialcolorlist", "colmaterialsizelist"}
    ]
    if not fields:
        return
    requests = [
        {
            "row_index": int((field.get("_live") or {}).get("row_index") or 0),
            "kind": (
                "Color"
                if _base_costing_field_key(field) == "colmaterialcolorlist"
                else "Size"
            ),
        }
        for field in fields
    ]
    try:
        results = frame.evaluate(
            """requests => {
                const rows = GetObjGrid('CostSheetDetail')?.[0]?.data || [];
                return requests.map(request => {
                    const row = rows[request.row_index];
                    if (!row) return {...request, options: [], values: []};
                    const data = GetBindDDLData(
                        GUID,
                        request.kind,
                        gFromPage,
                        `ArticleID|${row.ArticleID}~Group|${row.GroupCounter}~`,
                        undefined,
                        undefined,
                        false
                    ) || [];
                    return {
                        ...request,
                        options: data.map(option => (
                            option[request.kind]
                            || `${option[request.kind + 'Name'] || ''} `
                                + `(${option[request.kind + 'Code'] || ''})`
                        ).trim()),
                        values: data.map(option => (
                            option[request.kind + 'Code']
                            || option[request.kind]
                            || ''
                        )),
                    };
                });
            }""",
            requests,
        )
    except (PlaywrightError, RuntimeError, TypeError, ValueError):
        results = []
    result_by_key = {
        (int(result.get("row_index") or 0), str(result.get("kind") or "")): result
        for result in results or ()
    }
    for field in fields:
        live = field.get("_live") or {}
        row_index = int(live.get("row_index") or 0)
        kind = (
            "Color"
            if _base_costing_field_key(field) == "colmaterialcolorlist"
            else "Size"
        )
        result = result_by_key.get((row_index, kind)) or {}
        options = [
            str(value).strip()
            for value in result.get("options") or ()
            if str(value).strip()
        ]
        values = [str(value).strip() for value in result.get("values") or ()]
        if options:
            field["options"] = list(dict.fromkeys(options))
            live["option_values"] = values
