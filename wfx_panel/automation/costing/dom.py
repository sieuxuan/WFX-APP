"""Trợ giúp DOM chung cho Costing: lọc control hiển thị và sửa nhãn WFX.

Các hàm ở đây không biết gì về nghiệp vụ Costing ngoài selector grid."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from wfx_panel.automation._common import Frame, PlaywrightError, _sleep, time
from wfx_panel.automation.costing.constants import (
    _INLINE_EDITOR_JS,
    _MATCHING_OPTION_VALUES_JS,
    _USABLE_CONTROL_JS,
    _VISIBLE_JS,
    _VISIBLE_WITH_ID_JS,
    COSTING_GRID_SELECTOR,
)
from wfx_panel.automation.runtime import checkpoint


def _visible_costing_grid(frame: Frame) -> Any | None:
    grids = frame.locator(COSTING_GRID_SELECTOR)
    visible = _filtered_indexes(grids, _VISIBLE_JS)
    return grids.nth(visible[0]) if len(visible) == 1 else None


def _visible_unique(frame: Frame, selector: str, error_code: str) -> Any:
    matches = _visible_controls(frame, selector)
    if len(matches) != 1:
        raise RuntimeError(f"{error_code}:{len(matches)}")
    return matches[0]


def _evaluate_all(locator: Any, script: str, arg: Any = None) -> list[Any]:
    """Lọc/đọc trong trình duyệt một lượt, thay vì hỏi từng phần tử.

    Mỗi `count()`/`is_visible()`/`is_enabled()`/`get_attribute()` là một lượt
    gọi CDP riêng, nên lọc kiểu `1 + 2N` làm một dòng Costing vài chục control
    tốn hàng trăm lượt. Caller vẫn dựng lại handle Playwright bằng `nth()` theo
    index trả về, nên click/fill không đổi.
    """
    checkpoint()
    try:
        return list(locator.evaluate_all(script, arg) or ())
    except PlaywrightError:
        return []


def _filtered_indexes(
    locator: Any,
    script: str,
    arg: Any = None,
) -> list[int]:
    return [int(index) for index in _evaluate_all(locator, script, arg)]


def _visible_controls(frame: Frame, selector: str) -> list[Any]:
    locator = frame.locator(selector)
    return [
        locator.nth(index)
        for index in _filtered_indexes(locator, _USABLE_CONTROL_JS)
    ]


def _unique_visible_by_id(scope: Any, dom_id: str) -> Any:
    candidates = scope.locator(f'[id="{dom_id}"]')
    matches = _filtered_indexes(candidates, _VISIBLE_WITH_ID_JS, dom_id)
    if len(matches) != 1:
        raise RuntimeError("COSTING_FIELD_DETACHED")
    return candidates.nth(matches[0])


def _select_options(control: Any) -> list[dict[str, str]]:
    return list(
        control.evaluate(
            r"""select => [...select.options].map(option => ({
                label: String(option.textContent || '').replace(/\s+/g, ' ').trim(),
                value: String(option.value || '').trim()
            }))"""
        )
        or ()
    )


def _close_inline_editor(editor: Any) -> None:
    try:
        if editor.count() and editor.is_visible():
            editor.press("Tab")
    except PlaywrightError:
        pass


def _option_value(field: Mapping[str, Any], value: Any) -> str:
    labels = [str(item) for item in field.get("options") or ()]
    values = [
        str(item) for item in (field.get("_live") or {}).get("option_values") or ()
    ]
    wanted = str(value or "").strip().casefold()
    matches = [
        values[index] if index < len(values) else labels[index]
        for index, label in enumerate(labels)
        if label.strip().casefold() == wanted
        or (index < len(values) and values[index].strip().casefold() == wanted)
    ]
    if len(matches) != 1:
        raise RuntimeError("COSTING_FIELD_OPTION_NOT_FOUND")
    return matches[0]


def _apply_inline_select_option(editor: Any, option_value: str) -> None:
    """Chọn option cho select thường hoặc backing select ẩn của Select2."""
    classes = str(editor.get_attribute("class") or "")
    if "select2-hidden-accessible" in classes.split():
        changed = editor.evaluate(
            """(element, value) => {
                element.value = String(value);
                if (element.value !== String(value)) return false;
                element.dispatchEvent(new Event('change', {bubbles: true}));
                return true;
            }""",
            option_value,
        )
        if not changed:
            raise RuntimeError("COSTING_INLINE_OPTION_NOT_APPLIED")
        return
    editor.select_option(value=option_value)


def _edit_wfx_label(
    frame: Frame,
    control: Any,
    field: Mapping[str, Any],
    value: Any,
) -> None:
    try:
        control.click(timeout=2_000)
    except PlaywrightError:
        # WFX's frozen left columns can visually cover a valid cell after a
        # horizontal scroll.  Dispatch only on the already verified target;
        # _resolve_live_field has blocked every forbidden control beforehand.
        control.evaluate("element => element.click()")
    live = field.get("_live") or {}
    dom_id = str(live.get("dom_id") or "")
    suffix = re.sub(r"^(?:lbl|txt|cbo|ddl)", "", dom_id).rstrip("~").casefold()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        root: Any = frame
        if str(live.get("region") or "") == "grid":
            grid = _visible_costing_grid(frame)
            if grid is None:
                raise RuntimeError("COSTING_INLINE_EDITOR_NOT_FOUND")
            rows = grid.locator(":scope > tbody > tr")
            row_index = int(live.get("row_index") or 0)
            if row_index < 0 or row_index >= rows.count():
                raise RuntimeError("COSTING_INLINE_EDITOR_NOT_FOUND")
            root = rows.nth(row_index)
        controls = root.locator("input,select,textarea")
        editors = _evaluate_all(controls, _INLINE_EDITOR_JS, suffix)
        preferred = [item for item in editors if item.get("matches_suffix")]
        if len(preferred) == 1:
            editors = preferred
        if len(editors) == 1:
            editor = controls.nth(int(editors[0]["index"]))
            tag = str(editors[0]["tag"])
            if tag == "select":
                matched = _evaluate_all(
                    editor.locator("option"),
                    _MATCHING_OPTION_VALUES_JS,
                    str(value or "").strip().casefold(),
                )
                if len(matched) != 1:
                    raise RuntimeError("COSTING_INLINE_OPTION_NOT_FOUND")
                # WFX dùng select 1×1 làm backing control cho Select2.
                # select_option có thể chờ actionability tới default timeout
                # dù option đã tồn tại.
                _apply_inline_select_option(editor, matched[0])
                editor.press("Tab")
            else:
                editor.fill(str(value if value is not None else ""))
                editor.press("Tab")
            return
        _sleep(0.1)
    raise RuntimeError("COSTING_INLINE_EDITOR_NOT_FOUND")
