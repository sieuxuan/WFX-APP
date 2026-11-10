"""Điền field, đọc option và Save form Style."""

from __future__ import annotations

from typing import Any

from wfx_panel.automation._common import (
    Callable,
    Frame,
    Page,
    PlaywrightError,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.bulk_style.constants import (
    _HYDRATE_STYLE_OPTIONS_JS,
    _READ_STYLE_OPTIONS_JS,
    _SET_STYLE_FIELD_JS,
    FIXED_STYLE_FIELDS,
    SAVE_STYLE_XPATH,
    STYLE_FIELDS,
)
from wfx_panel.automation.bulk_style.frames import _style_editor_frame
from wfx_panel.automation.runtime import cancellation_deferred


def _set_field(
    page: Page,
    label: str,
    value: str,
    ids: tuple[str, ...],
    labels: tuple[str, ...],
    log: Callable[[str], None],
) -> dict[str, Any]:
    deadline = time.monotonic() + 18
    last: dict[str, Any] = {"ok": False, "reason": "not-found"}
    hydrated = False
    while time.monotonic() < deadline:
        try:
            frame = _style_editor_frame(page, timeout_s=2)
            last = frame.evaluate(
                _SET_STYLE_FIELD_JS,
                {"ids": list(ids), "labels": list(labels), "value": value},
            )
            if last.get("ok"):
                _write_log(log, f"[STYLE] Đã điền {label}.")
                _wait(frame, 350)
                return last
            if last.get("reason") == "ambiguous-option":
                break
            if last.get("reason") == "option-not-found" and not hydrated:
                control_id = last.get("id")
                if not control_id:
                    break
                hydrated = bool(frame.evaluate(
                    _HYDRATE_STYLE_OPTIONS_JS, {"ids": [control_id]}
                ))
                if not hydrated:
                    break
        except PlaywrightError:
            pass
        _wait(page, 150)
    raise RuntimeError(f"STYLE_FIELD_NOT_AVAILABLE:{label}:{value}")


def _fill_style_editor(
    page: Page,
    row: dict[str, Any],
    log: Callable[[str], None],
) -> list[str]:
    kind = str(row.get("type") or "").strip().casefold()
    filled: list[str] = []
    for key, label, ids, labels in STYLE_FIELDS:
        value = str(row.get(key) or "").strip()
        if not value:
            if kind == "new":
                raise RuntimeError(f"STYLE_REQUIRED_FIELD_MISSING:{label}")
            continue
        _set_field(page, label, value, ids, labels, log)
        filled.append(label)
    for label, value, ids, labels in FIXED_STYLE_FIELDS:
        _set_field(page, label, value, ids, labels, log)
        filled.append(label)
    return filled


def _save_style(page: Page, log: Callable[[str], None]) -> None:
    """Click đúng Save của Article editor một lần khi user đã bật Auto Save."""
    frame = _style_editor_frame(page)
    save = frame.locator(f"xpath={SAVE_STYLE_XPATH}").first
    save.wait_for(state="visible", timeout=8_000)
    # Từ lúc click tới lúc WFX ghi xong là đoạn KHÔNG được ngắt. `_wait()` gọi
    # checkpoint(); nếu người dùng bấm Stop đúng lúc này, flow trả
    # ACTION_CANCELLED trong khi Style đã thật sự được tạo trên WFX — user tin
    # là chưa ghi gì, chạy lại dòng đó và sinh Style trùng.
    with cancellation_deferred():
        save.click()
        _write_log(log, "[STYLE] Đã bấm Save theo lựa chọn Tự động Save.")
        _wait(page, 800)


def _read_style_options(frame: Frame, ids: tuple[str, ...]) -> list[dict[str, str]]:
    raw = frame.evaluate(_READ_STYLE_OPTIONS_JS, {"ids": list(ids)}) or []
    seen: set[str] = set()
    options: list[dict[str, str]] = []
    for item in raw:
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        identity = label.casefold()
        if not label or identity in seen:
            continue
        seen.add(identity)
        options.append({"label": label, "value": value})
    return options


def _field_options_with_wait(
    page: Page,
    ids: tuple[str, ...],
    timeout_s: float = 8,
) -> list[dict[str, str]]:
    deadline = time.monotonic() + timeout_s
    hydrated = False
    while time.monotonic() < deadline:
        frame = _style_editor_frame(page, timeout_s=2)
        options = _read_style_options(frame, ids)
        if options:
            return options
        if not hydrated:
            try:
                hydrated = bool(
                    frame.evaluate(_HYDRATE_STYLE_OPTIONS_JS, {"ids": list(ids)})
                )
            except PlaywrightError:
                pass
        _wait(page, 180)
    return []
