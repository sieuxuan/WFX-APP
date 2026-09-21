"""Quét và áp bảng Dependency Color/Size của Costing."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from wfx_panel.automation._common import Frame, PlaywrightError, _sleep
from wfx_panel.automation.costing.constants import (
    _DEPENDENCY_OPTIONS_JS,
    DEPENDENCY_TABLE_ATTEMPTS,
)
from wfx_panel.automation.costing.dom import _edit_wfx_label, _visible_costing_grid
from wfx_panel.automation.costing.fields import _resolve_live_field
from wfx_panel.automation.costing.keys import _base_costing_field_key


def _scan_dependency_table(
    frame: Frame,
    mapping_field: dict[str, Any],
    known_options: Sequence[str] = (),
) -> tuple[str, list[str]]:
    live = mapping_field.get("_live") or {}
    kind = str(live.get("dependency_kind") or "")
    if kind not in {"Color", "Size"}:
        return "", []
    grid = _visible_costing_grid(frame)
    if grid is None:
        return "", []
    rows = grid.locator(":scope > tbody > tr")
    row_index = int(live.get("row_index") or 0)
    if row_index < 0 or row_index >= rows.count():
        return "", []
    link = rows.nth(row_index).locator(f'[id="lnk{kind}Dependency"]:visible')
    if link.count() != 1:
        return "", []
    popup = frame.locator(f"div#section{kind}DepUsage.Targetblock:visible")
    try:
        link.click(timeout=3_000)
        popup.wait_for(state="visible", timeout=3_000)
        mapping_rows = popup.locator(f"#grid{kind}DepUsage_tblGridContent > tbody > tr")
        lines: list[str] = []
        all_options: list[str] = list(known_options)
        editor_id = f"ddlStyle{kind}ListSDU"
        for index in range(mapping_rows.count()):
            mapping_row = mapping_rows.nth(index)
            source_cell = mapping_row.locator("#colMaterialArticleSDU")
            source_node = source_cell.locator("[title]")
            source = str(
                (
                    source_node.first.get_attribute("title")
                    if source_node.count()
                    else ""
                )
                or source_cell.inner_text()
                or ""
            ).strip()
            target_cell = mapping_row.locator("#colStyleSDU")
            editable = target_cell.locator(".lblEditable")
            if not source or editable.count() != 1:
                continue
            selected_text = str(
                editable.get_attribute("title") or editable.inner_text() or ""
            ).strip()
            selected = _split_dependency_display_values(selected_text)
            if not all_options:
                editable.click(timeout=2_000)
                editor = target_cell.locator(f"#{editor_id}:visible")
                editor.wait_for(state="visible", timeout=2_000)
                editor.click(timeout=2_000)
                option_list = frame.locator(f"#{editor_id}ListItems:visible")
                option_list.wait_for(state="visible", timeout=2_000)
                options = option_list.locator("li.clsMultiSelectContent")
                for option_index in range(options.count()):
                    option = options.nth(option_index)
                    anchor = option.locator("a")
                    label = str(
                        (anchor.get_attribute("title") if anchor.count() else "")
                        or option.inner_text()
                        or ""
                    ).strip()
                    if label:
                        all_options.append(label)
                editor.press("Tab")
                try:
                    option_list.wait_for(state="hidden", timeout=1_000)
                except PlaywrightError:
                    frame.locator("body").press("Escape")
            lines.append(f"{source} => {' | '.join(selected)}")
        return "\n".join(lines), list(dict.fromkeys(all_options))
    finally:
        try:
            frame.locator("body").press("Escape")
            cancel = popup.locator(".clsSectionTitleBarToolCancel")
            if cancel.count() and cancel.is_visible():
                try:
                    cancel.click(timeout=1_000)
                except PlaywrightError:
                    cancel.evaluate("element => element.click()")
                popup.wait_for(state="hidden", timeout=2_000)
        except PlaywrightError:
            pass


def _scan_dependency_tables_from_page_data(
    frame: Frame,
    mapping_fields: Sequence[dict[str, Any]],
) -> tuple[dict[tuple[int, str], str], dict[str, list[str]]]:
    """Read dependency grids from WFX's already-loaded page data.

    ``bindDependencyUsageData`` is the same function used by the Color/Size
    dependency popup.  Calling it without displaying the popup builds the
    hidden grid immediately, avoiding one modal round-trip for every item.
    """
    requests = [
        {
            "row_index": int((field.get("_live") or {}).get("row_index") or 0),
            "kind": str((field.get("_live") or {}).get("dependency_kind") or ""),
        }
        for field in mapping_fields
    ]
    payload = frame.evaluate(
        """requests => {
            const output = {results: [], options: {Color: [], Size: []}};
            const styleKey = (
                typeof gArticleID === 'undefined'
                    ? ''
                    : `WFXCostSheet|ArticleID|${gArticleID}~`
            );
            for (const kind of ['Color', 'Size']) {
                const cache = (
                    typeof gobjDDLHashData === 'undefined'
                        ? null
                        : gobjDDLHashData?.[kind]?.[styleKey]
                ) || [];
                output.options[kind] = cache.map(row => (
                    row[kind]
                    || `${row[kind + 'Name'] || ''} (${row[kind + 'Code'] || ''})`
                ).trim()).filter(Boolean);
            }
            for (const request of requests) {
                try {
                    costSheetData.rowIndexForClickedRow = request.row_index;
                    bindDependencyUsageData(request.kind);
                    const grid = GetObjGrid(request.kind + 'DepUsage');
                    const rows = grid?.[0]?.data || [];
                    output.results.push({
                        row_index: request.row_index,
                        kind: request.kind,
                        rows: rows.map(row => ({
                            source: row['Material' + request.kind] || '',
                            target: row[request.kind + 'Name'] || '',
                        })),
                    });
                    if (typeof HideDiv === 'function') {
                        HideDiv('section' + request.kind + 'DepUsage', 1);
                    }
                } catch (error) {
                    output.results.push({
                        row_index: request.row_index,
                        kind: request.kind,
                        error: String(error),
                        rows: [],
                    });
                }
            }
            return output;
        }""",
        requests,
    )
    values: dict[tuple[int, str], str] = {}
    for result in payload.get("results") or ():
        row_index = int(result.get("row_index") or 0)
        kind = str(result.get("kind") or "")
        lines: list[str] = []
        for row in result.get("rows") or ():
            source = str(row.get("source") or "").strip()
            targets = _split_dependency_display_values(
                str(row.get("target") or "").strip()
            )
            if source:
                lines.append(f"{source} => {' | '.join(targets)}")
        if lines:
            values[(row_index, kind)] = "\n".join(lines)
    raw_options = payload.get("options") or {}
    options = {
        kind: list(
            dict.fromkeys(
                str(value).strip()
                for value in raw_options.get(kind) or ()
                if str(value).strip()
            )
        )
        for kind in ("Color", "Size")
    }
    return values, options


def _scan_costing_dependency_tables(
    frame: Frame,
    document: dict[str, Any],
) -> None:
    outer_modes = {
        (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            "Color"
            if _base_costing_field_key(field) == "colcolordependency"
            else "Size",
        ): str(field.get("value") or "")
        for field in document.get("fields") or ()
        if _base_costing_field_key(field)
        in {
            "colcolordependency",
            "colsizedependency",
        }
    }
    option_cache: dict[str, list[str]] = {"Color": [], "Size": []}
    mapping_fields = [
        field
        for field in document.get("fields") or ()
        if _base_costing_field_key(field)
        in {
            "colcolordependencymapping",
            "colsizedependencymapping",
        }
    ]
    table_fields: list[dict[str, Any]] = []
    for field in mapping_fields:
        base = _base_costing_field_key(field)
        if base not in {
            "colcolordependencymapping",
            "colsizedependencymapping",
        }:
            continue
        kind = "Color" if "color" in base else "Size"
        mode = outer_modes.get(
            (
                str(field.get("section_key") or "").casefold(),
                str(field.get("item_key") or "").casefold(),
                kind,
            ),
            "",
        )
        if mode.casefold() != "[table]":
            continue
        table_fields.append(field)

    direct_values: dict[tuple[int, str], str] = {}
    if table_fields:
        try:
            direct_values, option_cache = _scan_dependency_tables_from_page_data(
                frame,
                table_fields,
            )
        except (PlaywrightError, RuntimeError, TypeError, ValueError):
            direct_values = {}

    for field in table_fields:
        live = field.get("_live") or {}
        kind = str(live.get("dependency_kind") or "")
        row_index = int(live.get("row_index") or 0)
        direct_value = direct_values.get((row_index, kind), "")
        if direct_value:
            field["value"] = direct_value
            field["options"] = list(option_cache[kind])
            continue
        # Popup Dependency mở chậm một nhịp là đủ để lượt đầu hỏng; thiếu lần
        # thử lại thì `_dependency_scan_incomplete()` bật và đổ cả lượt Export.
        for attempt in range(DEPENDENCY_TABLE_ATTEMPTS):
            try:
                value, options = _scan_dependency_table(
                    frame,
                    field,
                    option_cache[kind],
                )
                field["value"] = value
                field["options"] = options
                option_cache[kind] = options
                break
            except (PlaywrightError, RuntimeError):
                try:
                    frame.locator("body").press("Escape")
                except PlaywrightError:
                    pass
                if attempt < DEPENDENCY_TABLE_ATTEMPTS - 1:
                    _sleep(0.2)
    for field in mapping_fields:
        kind = "Color" if "color" in _base_costing_field_key(field) else "Size"
        if not field.get("options"):
            field["options"] = list(option_cache[kind])


def _dependency_scan_incomplete(document: Mapping[str, Any]) -> bool:
    fields = list(document.get("fields") or ())
    values = {
        (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            _base_costing_field_key(field),
        ): str(field.get("value") or "").strip()
        for field in fields
    }
    for field in fields:
        base = _base_costing_field_key(field)
        if base not in {
            "colcolordependencymapping",
            "colsizedependencymapping",
        }:
            continue
        prefix = "color" if "color" in base else "size"
        identity = (
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
        )
        mode = values.get((*identity, f"col{prefix}dependency"), "")
        material = values.get((*identity, f"colmaterial{prefix}list"), "")
        mapping = str(field.get("value") or "").strip()
        if mode.casefold() == "[table]" and material and not mapping:
            return True
    return False


def _dependency_kind(
    field: Mapping[str, Any],
    value: Any,
) -> str:
    field_key = re.sub(
        r"__\d+$",
        "",
        str(field.get("field_key") or ""),
    ).casefold()
    text = str(value or "").strip()
    if not text or text.startswith("["):
        return ""
    if field_key in {
        "colcolordependency",
        "colcolordependencymapping",
    }:
        return "Color"
    if field_key in {
        "colsizedependency",
        "colsizedependencymapping",
    }:
        return "Size"
    return ""


def _dependency_values(value: Any) -> list[str]:
    return list(
        dict.fromkeys(
            token.strip()
            for token in re.split(r"[|;\n]+", str(value or ""))
            if token.strip()
        )
    )


def _split_dependency_display_values(value: Any) -> list[str]:
    text = str(value or "").strip()
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


def _dependency_match_tokens(value: Any) -> set[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
    if not text:
        return set()
    tokens = {text, re.sub(r"[^a-z0-9]+", "", text)}
    code = re.search(r"\(([^()]*)\)\s*$", text)
    if code and code.group(1).strip():
        raw_code = code.group(1).strip()
        tokens.update({raw_code, re.sub(r"[^a-z0-9]+", "", raw_code)})
    return {token for token in tokens if token}


def _dependency_mapping_rules(
    value: Any,
) -> list[tuple[str | None, list[str]]]:
    text = str(value or "").strip()
    lines = [line.strip() for line in re.split(r"[;\n]+", text) if line.strip()]
    rules: list[tuple[str | None, list[str]]] = []
    for line in lines:
        match = re.match(r"^(.*?)\s*(?:=>|->|→)\s*(.*)$", line)
        if not match:
            continue
        source = match.group(1).strip()
        targets = _dependency_values(match.group(2))
        if source:
            rules.append((source, targets))
    if rules:
        return rules
    # Tương thích workbook trước đây: một danh sách đích áp cho mọi dòng nguồn.
    targets = _dependency_values(text)
    return [(None, targets)] if targets else []


def _ensure_table_dependency_mode(
    frame: Frame,
    live_field: Mapping[str, Any],
    value: Any,
) -> str:
    dependency_kind = _dependency_kind(live_field, value)
    if not dependency_kind:
        raise RuntimeError("COSTING_DEPENDENCY_VALUE_INVALID")
    live_metadata = live_field.get("_live") or {}
    current_mode = str(
        live_metadata.get("dependency_mode") or live_field.get("value") or ""
    ).strip()
    if current_mode.casefold() == "[table]":
        return dependency_kind
    control = _resolve_live_field(frame, live_field)
    _edit_wfx_label(frame, control, live_field, "[Table]")
    _sleep(0.2)
    return dependency_kind


def _open_dependency_popup(
    frame: Frame,
    live_field: Mapping[str, Any],
    dependency_kind: str,
) -> Any:
    row_index = int((live_field.get("_live") or {}).get("row_index") or 0)
    grid = _visible_costing_grid(frame)
    if grid is None:
        raise RuntimeError("COSTING_DEPENDENCY_ROW_NOT_FOUND")
    rows = grid.locator(":scope > tbody > tr")
    if row_index < 0 or row_index >= rows.count():
        raise RuntimeError("COSTING_DEPENDENCY_ROW_NOT_FOUND")
    links = rows.nth(row_index).locator(
        f'[id="lnk{dependency_kind}Dependency"]:visible'
    )
    if links.count() != 1:
        raise RuntimeError("COSTING_DEPENDENCY_LINK_NOT_FOUND")
    try:
        links.first.click(timeout=3_000)
    except PlaywrightError:
        links.first.evaluate("element => element.click()")
    popup = frame.locator(f"div#section{dependency_kind}DepUsage.Targetblock:visible")
    popup.wait_for(state="visible", timeout=3_000)
    return popup


def _dependency_source_label(mapping_row: Any) -> str:
    source_cell = mapping_row.locator("#colMaterialArticleSDU")
    source_node = source_cell.locator("[title]")
    return str(
        (source_node.first.get_attribute("title") if source_node.count() else "")
        or source_cell.inner_text()
        or ""
    ).strip()


def _matching_dependency_rule(
    source_label: str,
    rules: Sequence[tuple[str | None, list[str]]],
) -> tuple[int, list[str]] | None:
    source_tokens = _dependency_match_tokens(source_label)
    matches = [
        (rule_index, targets)
        for rule_index, (source, targets) in enumerate(rules)
        if source is None or source_tokens & _dependency_match_tokens(source)
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise RuntimeError("COSTING_DEPENDENCY_SOURCE_AMBIGUOUS")
    return matches[0]


def _dependency_option_indexes(
    option_snapshot: Sequence[Mapping[str, Any]],
    wanted_values: Sequence[str],
) -> set[int]:
    matched_indexes: dict[str, int] = {}
    for option in option_snapshot:
        label = str(option.get("label") or "").casefold()
        code = str(option.get("code") or "").casefold()
        for wanted_value in wanted_values:
            normalized_value = wanted_value.casefold()
            if normalized_value not in {label, code}:
                continue
            if normalized_value in matched_indexes:
                raise RuntimeError("COSTING_DEPENDENCY_OPTION_AMBIGUOUS")
            matched_indexes[normalized_value] = int(option["index"])
    missing_values = [
        value for value in wanted_values if value.casefold() not in matched_indexes
    ]
    if missing_values:
        raise RuntimeError(
            "COSTING_DEPENDENCY_OPTION_NOT_FOUND:" + ",".join(missing_values[:3])
        )
    return {matched_indexes[value.casefold()] for value in wanted_values}


def _set_dependency_row_options(
    frame: Frame,
    mapping_row: Any,
    dependency_kind: str,
    wanted_values: Sequence[str],
) -> None:
    target_cell = mapping_row.locator("#colStyleSDU")
    editable = target_cell.locator(".lblEditable")
    if editable.count() != 1:
        raise RuntimeError("COSTING_DEPENDENCY_TARGET_NOT_FOUND")
    editable.click(timeout=2_000)
    editor_id = f"ddlStyle{dependency_kind}ListSDU"
    editor = target_cell.locator(f"#{editor_id}:visible")
    editor.wait_for(state="visible", timeout=2_000)
    editor.click(timeout=2_000)
    option_list = frame.locator(f"#{editor_id}ListItems:visible")
    option_list.wait_for(state="visible", timeout=2_000)
    options = option_list.locator("li.clsMultiSelectContent")
    option_snapshot = options.evaluate_all(_DEPENDENCY_OPTIONS_JS)
    wanted_indexes = _dependency_option_indexes(
        option_snapshot,
        wanted_values,
    )
    for option in option_snapshot:
        option_index = int(option["index"])
        should_check = option_index in wanted_indexes
        if bool(option.get("checked")) == should_check:
            continue
        options.nth(option_index).locator("input[type='checkbox']").click(timeout=2_000)
    confirmed_snapshot = options.evaluate_all(_DEPENDENCY_OPTIONS_JS)
    confirmed_indexes = {
        int(option["index"]) for option in confirmed_snapshot if option.get("checked")
    }
    if confirmed_indexes != wanted_indexes:
        raise RuntimeError("COSTING_DEPENDENCY_NOT_CONFIRMED")
    editor.press("Tab")


def _apply_dependency_rules(
    frame: Frame,
    popup: Any,
    dependency_kind: str,
    rules: Sequence[tuple[str | None, list[str]]],
) -> None:
    mapping_rows = popup.locator(
        f"#grid{dependency_kind}DepUsage_tblGridContent > tbody > tr"
    )
    if mapping_rows.count() < 1:
        raise RuntimeError("COSTING_DEPENDENCY_TABLE_EMPTY")
    matched_rule_indexes: set[int] = set()
    for row_index in range(mapping_rows.count()):
        mapping_row = mapping_rows.nth(row_index)
        matching_rule = _matching_dependency_rule(
            _dependency_source_label(mapping_row),
            rules,
        )
        if matching_rule is None:
            continue
        rule_index, wanted_values = matching_rule
        matched_rule_indexes.add(rule_index)
        _set_dependency_row_options(
            frame,
            mapping_row,
            dependency_kind,
            wanted_values,
        )
    missing_sources = [
        source
        for rule_index, (source, _targets) in enumerate(rules)
        if source is not None and rule_index not in matched_rule_indexes
    ]
    if missing_sources:
        raise RuntimeError(
            "COSTING_DEPENDENCY_SOURCE_NOT_FOUND:" + ",".join(missing_sources[:3])
        )


def _cancel_dependency_popup(popup: Any) -> None:
    try:
        cancel = popup.locator(".clsSectionTitleBarToolCancel")
        if cancel.count() and cancel.is_visible():
            cancel.click(timeout=1_000)
    except PlaywrightError:
        pass


def _set_dependency_mapping(
    frame: Frame,
    live_field: Mapping[str, Any],
    value: Any,
) -> None:
    """Chọn mapping thật trong popup Table thay vì chỉ ghi chữ ``[Table]``."""
    rules = _dependency_mapping_rules(value)
    if not rules:
        raise RuntimeError("COSTING_DEPENDENCY_VALUE_INVALID")
    dependency_kind = _ensure_table_dependency_mode(frame, live_field, value)
    popup = _open_dependency_popup(frame, live_field, dependency_kind)
    try:
        _apply_dependency_rules(frame, popup, dependency_kind, rules)
        popup.locator(".clsSectionTitleBarToolOk").click(timeout=3_000)
        popup.wait_for(state="hidden", timeout=3_000)
    except Exception:
        _cancel_dependency_popup(popup)
        raise
