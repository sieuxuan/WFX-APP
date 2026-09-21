"""Bổ sung Material Color/Size còn thiếu qua Article Color/Size List."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _sleep,
    _write_log,
    time,
)
from wfx_panel.automation.costing.constants import (
    _MATERIAL_VARIANT_CARD_XPATH,
    _MATERIAL_VARIANT_CLOSE_XPATH,
    _MATERIAL_VARIANT_FIELDS,
    _MATERIAL_VARIANT_SAVE_XPATH,
    _MATERIAL_VARIANT_SEARCH_AND_ADD_XPATH,
    _MATERIAL_VARIANT_SEARCH_XPATH,
)
from wfx_panel.automation.costing.dom import (
    _close_inline_editor,
    _select_options,
    _visible_controls,
    _visible_costing_grid,
)
from wfx_panel.automation.costing.fields import _resolve_live_field
from wfx_panel.automation.costing.keys import (
    _base_costing_field_key,
    _costing_semantic_token,
)
from wfx_panel.automation.runtime import cancellation_deferred, checkpoint


def _material_variant_config(
    field: Mapping[str, Any],
) -> Mapping[str, str] | None:
    return _MATERIAL_VARIANT_FIELDS.get(_base_costing_field_key(field))


def _material_variant_tokens(value: Any) -> set[str]:
    """Match a WFX Color/Size by exact label, code, or ``Name (Code)``."""
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return set()
    tokens = {text.casefold(), _costing_semantic_token(text)}
    match = re.search(r"\(([^()]*)\)\s*$", text)
    if match and match.group(1).strip():
        code = " ".join(match.group(1).split()).strip()
        tokens.update({code.casefold(), _costing_semantic_token(code)})
    return {token for token in tokens if token}


def _material_variant_option_matches(
    option: Mapping[str, Any],
    wanted: Any,
) -> bool:
    wanted_tokens = _material_variant_tokens(wanted)
    if not wanted_tokens:
        return False
    option_tokens = set()
    for key in ("label", "value"):
        option_tokens.update(_material_variant_tokens(option.get(key)))
    return bool(wanted_tokens & option_tokens)


def _costing_row_for_field(frame: Frame, field: Mapping[str, Any]) -> Any:
    live = field.get("_live") or {}
    if str(live.get("region") or "") != "grid":
        raise RuntimeError("COSTING_MATERIAL_VARIANT_ROW_NOT_FOUND")
    grid = _visible_costing_grid(frame)
    if grid is None:
        raise RuntimeError("COSTING_MATERIAL_VARIANT_ROW_NOT_FOUND")
    rows = grid.locator(":scope > tbody > tr")
    row_index = int(live.get("row_index") or 0)
    if row_index < 0 or row_index >= rows.count():
        raise RuntimeError("COSTING_MATERIAL_VARIANT_ROW_NOT_FOUND")
    return rows.nth(row_index)


def _open_material_variant_editor(
    frame: Frame,
    field: Mapping[str, Any],
    config: Mapping[str, str],
) -> tuple[Any, Any]:
    control = _resolve_live_field(frame, field)
    row = _costing_row_for_field(frame, field)
    try:
        control.click(timeout=2_000)
    except PlaywrightError:
        control.evaluate("element => element.click()")
    editor_id = str(config["editor_id"])
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        checkpoint()
        editors = _visible_controls(row, f'[id="{editor_id}"]')
        if len(editors) == 1:
            return row, editors[0]
        _sleep(0.1)
    raise RuntimeError("COSTING_MATERIAL_VARIANT_EDITOR_NOT_FOUND")


def _material_variant_is_available(
    frame: Frame,
    field: Mapping[str, Any],
    value: Any,
) -> bool:
    config = _material_variant_config(field)
    if config is None:
        return True
    _row, editor = _open_material_variant_editor(frame, field, config)
    try:
        return any(
            _material_variant_option_matches(option, value)
            for option in _select_options(editor)
        )
    finally:
        _close_inline_editor(editor)


def _material_variant_list_frame(
    context: Any,
    config: Mapping[str, str],
    previous_pages: set[int],
    timeout_seconds: float = 10,
) -> tuple[Page, Frame]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        candidates: list[tuple[int, Page, Frame]] = []
        for page in reversed(list(context.pages)):
            for frame in page.frames:
                try:
                    show = _visible_controls(frame, "#btnShow")
                    add = _visible_controls(frame, "#btnAdd")
                    if len(show) != 1 or len(add) != 1:
                        continue
                    url = str(frame.url or "").casefold()
                    score = (
                        (20 if id(page) not in previous_pages else 0)
                        + (10 if str(config["list_url"]) in url else 0)
                    )
                    if score:
                        candidates.append((score, page, frame))
                except PlaywrightError:
                    continue
        if candidates:
            best_score = max(item[0] for item in candidates)
            best = [item for item in candidates if item[0] == best_score]
            if len(best) == 1:
                return best[0][1], best[0][2]
        _sleep(0.1)
    raise PlaywrightTimeoutError("COSTING_MATERIAL_VARIANT_LIST_NOT_FOUND")


def _material_variant_card_select(frame: Frame) -> Any | None:
    row = frame.locator(f"xpath={_MATERIAL_VARIANT_CARD_XPATH}")
    if row.count() != 1:
        return None
    controls = _visible_controls(row, "select")
    return controls[0] if len(controls) == 1 else None


def _select_material_variant_card(frame: Frame, card_name: str) -> bool:
    card = _material_variant_card_select(frame)
    if card is None:
        return False
    wanted = str(card_name or "").strip().casefold()
    options = _select_options(card)
    matches = [
        option["value"]
        for option in options
        if str(option.get("label") or "").strip().casefold() == wanted
        or str(option.get("value") or "").strip().casefold() == wanted
    ]
    if len(matches) != 1:
        return False
    card.select_option(value=matches[0])
    return True


def _material_variant_search_input(frame: Frame) -> Any:
    row = frame.locator(f"xpath={_MATERIAL_VARIANT_SEARCH_XPATH}")
    if row.count() != 1:
        raise RuntimeError("COSTING_MATERIAL_VARIANT_SEARCH_NOT_FOUND")
    inputs = _visible_controls(
        row,
        "input:not([type='hidden']):not([type='button']):not([type='submit'])",
    )
    if len(inputs) != 1:
        raise RuntimeError("COSTING_MATERIAL_VARIANT_SEARCH_NOT_FOUND")
    return inputs[0]


def _material_variant_candidate_select(frame: Frame) -> Any:
    candidates = _visible_controls(frame, "select[multiple],select[size]")
    card = _material_variant_card_select(frame)
    if card is not None:
        card_id = str(card.get_attribute("id") or "")
        candidates = [
            candidate
            for candidate in candidates
            if not card_id
            or str(candidate.get_attribute("id") or "") != card_id
        ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"COSTING_MATERIAL_VARIANT_RESULTS_NOT_UNIQUE:{len(candidates)}"
        )
    return candidates[0]


def _search_material_variant(
    frame: Frame,
    value: Any,
) -> tuple[Any, list[dict[str, str]]]:
    search = _material_variant_search_input(frame)
    show = _visible_controls(frame, "#btnShow")
    if len(show) != 1:
        raise RuntimeError("COSTING_MATERIAL_VARIANT_SHOW_NOT_FOUND")
    search.fill(str(value or "").strip())
    show[0].click()
    previous: list[dict[str, str]] | None = None
    stable_reads = 0
    select = _material_variant_candidate_select(frame)
    latest: list[dict[str, str]] = []
    deadline = time.monotonic() + 7
    while time.monotonic() < deadline:
        checkpoint()
        latest = _select_options(select)
        if latest == previous:
            stable_reads += 1
        else:
            stable_reads = 0
        if stable_reads >= 2:
            break
        previous = latest
        _sleep(0.15)
    matches = [
        option
        for option in latest
        if _material_variant_option_matches(option, value)
    ]
    return select, matches


def _choose_and_add_material_variant(
    frame: Frame,
    value: Any,
) -> bool:
    select, matches = _search_material_variant(frame, value)
    if not matches:
        return False
    if len(matches) != 1:
        raise RuntimeError("COSTING_MATERIAL_VARIANT_AMBIGUOUS")
    select.select_option(value=str(matches[0].get("value") or ""))
    add = _visible_controls(frame, "#btnAdd")
    if len(add) != 1:
        raise RuntimeError("COSTING_MATERIAL_VARIANT_ADD_NOT_FOUND")
    with cancellation_deferred():
        add[0].click()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            remaining = _select_options(select)
            if not any(
                _material_variant_option_matches(option, value)
                for option in remaining
            ):
                return True
            _sleep(0.1)
    raise RuntimeError("COSTING_MATERIAL_VARIANT_ADD_NOT_CONFIRMED")


def _save_material_variant_list(frame: Frame) -> None:
    save = frame.locator(f"xpath={_MATERIAL_VARIANT_SAVE_XPATH}")
    if save.count() != 1 or not save.is_visible():
        raise RuntimeError("COSTING_MATERIAL_VARIANT_SAVE_NOT_FOUND")
    with cancellation_deferred():
        save.click()
        _sleep(0.25)


def _close_material_variant_list(page: Page, frame: Frame) -> None:
    try:
        close = frame.locator(f"xpath={_MATERIAL_VARIANT_CLOSE_XPATH}")
        if close.count() == 1 and close.is_visible():
            close.click(timeout=2_000)
            return
    except PlaywrightError:
        pass
    try:
        if not page.is_closed():
            page.close()
    except PlaywrightError:
        pass


def _add_material_variant_to_card(
    context: Any,
    list_page: Page,
    list_frame: Frame,
    config: Mapping[str, str],
    value: Any,
) -> None:
    link = list_frame.locator(
        f"xpath={_MATERIAL_VARIANT_SEARCH_AND_ADD_XPATH}"
    )
    if link.count() != 1 or not link.is_visible():
        raise RuntimeError("COSTING_MATERIAL_VARIANT_SEARCH_ADD_NOT_FOUND")
    previous_pages = {id(page) for page in list(context.pages)}
    link.click()
    range_page, range_frame = _material_variant_list_frame(
        context,
        config,
        previous_pages,
    )
    if range_page == list_page and range_frame == list_frame:
        raise RuntimeError("COSTING_MATERIAL_VARIANT_RANGE_NOT_OPENED")
    try:
        if not _choose_and_add_material_variant(range_frame, value):
            raise RuntimeError("COSTING_MATERIAL_VARIANT_NOT_FOUND")
        save = range_frame.locator(f"xpath={_MATERIAL_VARIANT_SAVE_XPATH}")
        if save.count() == 1 and save.is_visible():
            with cancellation_deferred():
                save.click()
                _sleep(0.25)
    finally:
        _close_material_variant_list(range_page, range_frame)


def _add_missing_material_variant(
    context: Any,
    frame: Frame,
    field: Mapping[str, Any],
    value: Any,
    log: Callable[[str], None],
) -> bool:
    config = _material_variant_config(field)
    if config is None:
        return False
    row, editor = _open_material_variant_editor(frame, field, config)
    if any(
        _material_variant_option_matches(option, value)
        for option in _select_options(editor)
    ):
        _close_inline_editor(editor)
        return False

    previous_pages = {id(page) for page in list(context.pages)}
    add_controls = _visible_controls(row, f'[id="{config["add_id"]}"]')
    if len(add_controls) != 1:
        # The active WFX editor can render its Add icon outside the row.
        # This fallback is safe only while the exact row editor stays open.
        add_controls = _visible_controls(
            frame,
            f'[id="{config["add_id"]}"]',
        )
    if len(add_controls) != 1:
        _close_inline_editor(editor)
        raise RuntimeError("COSTING_MATERIAL_VARIANT_BUTTON_NOT_FOUND")
    add_controls[0].click()
    list_page, list_frame = _material_variant_list_frame(
        context,
        config,
        previous_pages,
    )
    try:
        found = _choose_and_add_material_variant(list_frame, value)
        fallback_card = str(config.get("fallback_card") or "")
        if not found and fallback_card:
            if not _select_material_variant_card(list_frame, fallback_card):
                raise RuntimeError("COSTING_MATERIAL_VARIANT_CARD_NOT_FOUND")
            found = _choose_and_add_material_variant(list_frame, value)
        if not found:
            _add_material_variant_to_card(
                context,
                list_page,
                list_frame,
                config,
                value,
            )
            found = _choose_and_add_material_variant(list_frame, value)
        if not found:
            raise RuntimeError("COSTING_MATERIAL_VARIANT_NOT_FOUND")
        _save_material_variant_list(list_frame)
        _write_log(
            log,
            "[COSTING] Đã bổ sung "
            f"{config['kind']} {str(value or '').strip()} vào Article card.",
        )
    finally:
        _close_inline_editor(editor)
        _close_material_variant_list(list_page, list_frame)

    if not _material_variant_is_available(frame, field, value):
        raise RuntimeError("COSTING_MATERIAL_VARIANT_REFRESH_NOT_CONFIRMED")
    return True
