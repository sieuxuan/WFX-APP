"""Đọc, ghi, đối chiếu field live và Save Cost Sheet."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from wfx_panel.automation._common import Frame, Page, PlaywrightError, _wait, _write_log
from wfx_panel.automation.costing.constants import FORBIDDEN_CONTROL_IDS
from wfx_panel.automation.costing.dom import (
    _edit_wfx_label,
    _option_value,
    _unique_visible_by_id,
    _visible_costing_grid,
)
from wfx_panel.automation.runtime import cancellation_deferred


def _live_field_index(
    document: Mapping[str, Any],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    return {
        (
            str(field.get("scope") or "").casefold(),
            str(field.get("section_key") or "").casefold(),
            str(field.get("item_key") or "").casefold(),
            str(field.get("field_key") or "").casefold(),
        ): field
        for field in document.get("fields") or ()
        if isinstance(field, Mapping)
    }


def _resolve_live_field(frame: Frame, field: Mapping[str, Any]) -> Any:
    live = field.get("_live") or {}
    dom_id = str(live.get("dom_id") or "")
    if dom_id in FORBIDDEN_CONTROL_IDS:
        raise RuntimeError("COSTING_FORBIDDEN_CONTROL")
    click_dom_id = str(live.get("click_dom_id") or dom_id)
    if click_dom_id.rstrip("~") in FORBIDDEN_CONTROL_IDS:
        raise RuntimeError("COSTING_FORBIDDEN_CONTROL")
    region = str(live.get("region") or "")
    if region == "grid":
        grid = _visible_costing_grid(frame)
        if grid is None:
            raise RuntimeError("COSTING_FIELD_DETACHED")
        rows = grid.locator(":scope > tbody > tr")
        row_index = int(live.get("row_index") or 0)
        if row_index < 0 or row_index >= rows.count():
            raise RuntimeError("COSTING_FIELD_DETACHED")
        return _unique_visible_by_id(rows.nth(row_index), click_dom_id)
    return _unique_visible_by_id(frame, click_dom_id)


def _set_live_field(
    frame: Frame,
    live_field: Mapping[str, Any],
    value: Any,
) -> None:
    control = _resolve_live_field(frame, live_field)
    live = live_field.get("_live") or {}
    tag = str(live.get("tag") or "").casefold()
    input_type = str(live.get("input_type") or "").casefold()
    if tag == "select":
        control.select_option(value=_option_value(live_field, value))
    elif tag == "input" and input_type in {"checkbox", "radio"}:
        checked = str(value or "").strip().casefold() in {
            "1",
            "true",
            "yes",
            "y",
            "x",
            "có",
        }
        control.set_checked(checked)
    elif tag in {"input", "textarea"}:
        control.fill(str(value if value is not None else ""))
        control.press("Tab")
    else:
        _edit_wfx_label(frame, control, live_field, value)


def _field_value_matches(actual: Any, expected: Any, data_type: str) -> bool:
    if str(data_type or "").casefold() in {
        "number",
        "numeric",
        "decimal",
        "integer",
    }:
        try:
            return float(str(actual).strip() or 0) == float(str(expected).strip() or 0)
        except ValueError:
            pass
    return (
        str(actual if actual is not None else "").strip()
        == str(expected if expected is not None else "").strip()
    )


def _field_application_priority(field: Mapping[str, Any]) -> int:
    """Apply dependent Article fields in WFX's safe order."""
    semantic = " ".join(
        str(field.get(key) or "") for key in ("field_key", "label")
    ).casefold()
    if re.search(
        r"material.?size|material.?color|color.?dependency|size.?dependency",
        semantic,
    ):
        return 10
    if "minutes" in semantic:
        return 15
    if "productionvalue" in semantic:
        return 20
    if "supplier" in semantic:
        return 25
    if re.search(r"delivery.?term|currency", semantic):
        return 30
    if re.search(r"(?:^|[^a-z])rate(?:[^a-z]|$)|price", semantic):
        return 50
    return 40


def _save_costing(
    page: Page,
    frame: Frame,
    log: Callable[[str], None],
) -> None:
    save = frame.locator(
        'xpath=//*[@id="titlebarCostSheet"]/tbody/tr/td[3]/span/div[1]'
    )
    if save.count() != 1:
        raise RuntimeError("COSTING_SAVE_NOT_FOUND")
    _write_log(log, "[COSTING] Đang Save Cost Sheet...")
    dialog_messages: list[str] = []
    frame.evaluate(
        """() => {
            window.__codexCostingSaveMessages = [];
            window.__codexCostingOldDialog = window.showDialogMessage;
            window.__codexCostingOldSuccess = window.showSuccessMessage;
            if (typeof window.showDialogMessage === 'function') {
                window.showDialogMessage = function(type, title, message) {
                    window.__codexCostingSaveMessages.push({
                        kind: 'dialog',
                        title: String(title || ''),
                        message: String(message || '')
                    });
                    // Validation already returns false after showing this
                    // dialog.  Suppress WFX's blocking overlay while the
                    // automation returns the exact failure to the panel.
                    return false;
                };
            }
            if (typeof window.showSuccessMessage === 'function') {
                window.showSuccessMessage = function() {
                    window.__codexCostingSaveMessages.push({
                        kind: 'success',
                        title: '',
                        message: Array.from(arguments).join(' | ')
                    });
                    return window.__codexCostingOldSuccess.apply(this, arguments);
                };
            }
        }"""
    )

    def accept_save_dialog(dialog: Any) -> None:
        dialog_messages.append(str(dialog.message or "").strip())
        dialog.accept()

    page.on("dialog", accept_save_dialog)
    with cancellation_deferred():
        try:
            try:
                save.click(timeout=5_000)
            except PlaywrightError:
                save.evaluate("element => element.click()")
            _wait(page, 1_000)
        finally:
            page.remove_listener("dialog", accept_save_dialog)
    custom_messages = frame.evaluate(
        """() => {
            const messages = window.__codexCostingSaveMessages || [];
            if (window.__codexCostingOldDialog) {
                window.showDialogMessage = window.__codexCostingOldDialog;
            }
            if (window.__codexCostingOldSuccess) {
                window.showSuccessMessage = window.__codexCostingOldSuccess;
            }
            delete window.__codexCostingSaveMessages;
            delete window.__codexCostingOldDialog;
            delete window.__codexCostingOldSuccess;
            return messages;
        }"""
    )
    custom_failures = [
        " | ".join(
            token
            for token in (
                str(message.get("title") or "").strip(),
                str(message.get("message") or "").strip(),
            )
            if token
        )
        for message in custom_messages
        if (
            isinstance(message, Mapping)
            and message.get("kind") == "dialog"
            and not re.search(
                r"\bsav(?:e|ed)\b.*\bsuccess",
                " ".join(
                    (
                        str(message.get("title") or ""),
                        str(message.get("message") or ""),
                    )
                ),
                re.IGNORECASE,
            )
        )
    ]
    if custom_failures:
        raise RuntimeError(f"COSTING_SAVE_ALERT:{custom_failures[0][:160]}")
    failure_tokens = re.compile(
        r"\b(error|failed|invalid|required|missing|cannot|can't|not saved)\b",
        re.IGNORECASE,
    )
    failures = [
        message for message in dialog_messages if failure_tokens.search(message)
    ]
    if failures:
        raise RuntimeError(f"COSTING_SAVE_ALERT:{failures[0][:160]}")
    _write_log(
        log,
        "[COSTING] Đã Save; đang xác nhận trên màn hình hiện tại (không reload).",
    )
