"""Material Search, thêm/xoá Article và tách dòng ``>>`` trong Costing."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _sleep,
    _write_log,
    time,
)
from wfx_panel.automation.costing.constants import _SPECIAL_COST_SECTION_EDITORS
from wfx_panel.automation.costing.dom import (
    _apply_inline_select_option,
    _visible_costing_grid,
    _visible_unique,
)
from wfx_panel.automation.costing.keys import _clean_key, _costing_semantic_token
from wfx_panel.automation.runtime import checkpoint


def _section_row_index(grid: Any, section_key: str) -> int:
    rows = grid.locator(":scope > tbody > tr")
    section_number = 0
    matches = []
    for index in range(rows.count()):
        row = rows.nth(index)
        classes = str(row.get_attribute("class") or "")
        if not re.search(
            r"\bcssGridRow(?:BOMCodeMainHeader|CMCostHeader|"
            r"ProdProcessHeader|ICHeader)RowType\b",
            classes,
            re.IGNORECASE,
        ):
            continue
        section_number += 1
        label = row.locator("#lblBOMCodeTranslated")
        if label.count():
            name = label.first.inner_text()
        else:
            name = row.locator("#colArticle").first.inner_text()
        live_key = _clean_key(
            f"section-{section_number}-{str(name or '').strip()}",
            f"section-{section_number}",
        )
        if live_key.casefold() == str(section_key or "").casefold():
            matches.append(index)
    if len(matches) != 1:
        raise RuntimeError(f"COSTING_SECTION_NOT_FOUND:{section_key}:{len(matches)}")
    return matches[0]


def _section_action(
    frame: Frame,
    section_key: str,
    control_id: str,
) -> Any:
    grid = _visible_costing_grid(frame)
    if grid is None:
        raise RuntimeError("COSTING_GRID_NOT_FOUND")
    rows = grid.locator(":scope > tbody > tr")
    start = _section_row_index(grid, section_key)
    matches = []
    for index in range(start, rows.count()):
        if index > start:
            classes = str(rows.nth(index).get_attribute("class") or "")
            if re.search(
                r"\bcssGridRow(?:BOMCodeMainHeader|CMCostHeader|"
                r"ProdProcessHeader|ICHeader)RowType\b",
                classes,
                re.IGNORECASE,
            ):
                break
        candidates = rows.nth(index).locator(f'[id="{control_id}"]')
        for candidate_index in range(candidates.count()):
            candidate = candidates.nth(candidate_index)
            try:
                if candidate.is_visible() and candidate.is_enabled():
                    matches.append(candidate)
            except PlaywrightError:
                continue
    if len(matches) != 1:
        raise RuntimeError(
            f"COSTING_SECTION_ACTION_NOT_UNIQUE:{section_key}:"
            f"{control_id}:{len(matches)}"
        )
    return matches[0]


def _material_search_frame(
    context: Any,
    timeout_seconds: float = 10,
) -> tuple[Page, Frame]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        matches = []
        for page in reversed(list(context.pages)):
            for frame in page.frames:
                try:
                    code = frame.locator("#txtSearchArticleCode")
                    name = frame.locator("#txtSearchArticleName")
                    grid = frame.locator("#gridArticleList_tblGridContent")
                    if (
                        code.count() == 1
                        and name.count() == 1
                        and grid.count() == 1
                        and code.is_visible()
                        and name.is_visible()
                        and grid.is_visible()
                    ):
                        matches.append((page, frame))
                except PlaywrightError:
                    continue
        if len(matches) == 1:
            return matches[0]
        _sleep(0.1)
    raise PlaywrightTimeoutError("COSTING_MATERIAL_SEARCH_NOT_FOUND")


def _close_material_search(frame: Frame) -> None:
    close = _visible_unique(
        frame,
        "#sectionArticleList .clsSectionTitleBarToolClose",
        "COSTING_MATERIAL_CLOSE_NOT_UNIQUE",
    )
    close.click()


def _material_rows(frame: Frame) -> list[dict[str, Any]]:
    grid = frame.locator("#gridArticleList_tblGridContent")
    if grid.count() != 1:
        return []
    return list(
        grid.evaluate(
            """element => [...element.querySelectorAll(':scope > tbody > tr')]
                .map(row => ({
                    row_id: String(
                        row.getAttribute('rowid') || row.id || ''
                    ).trim(),
                    article_code: String(
                        row.querySelector('#lblArticleCode')?.textContent || ''
                    ).trim(),
                    article_name: String(
                        row.querySelector('#lblArticleName')?.textContent || ''
                    ).trim()
                }))"""
        )
        or ()
    )


def _material_option_rows(frame: Frame) -> list[dict[str, Any]]:
    """Read the already-bound Material Search data in one browser call."""
    try:
        rows = frame.evaluate(
            """() => {
                const data = (
                    typeof GetObjGrid === 'function'
                        ? (GetObjGrid('ArticleList')?.[0]?.data || [])
                        : []
                );
                return data.slice(0, 5000).map(row => ({
                    row_id: String(
                        row.ID || row.ArticleID || row.RowID || ''
                    ).trim(),
                    article_code: String(
                        row.ArticleCode || row.Code || ''
                    ).trim(),
                    article_name: String(
                        row.ArticleName || row.Name || ''
                    ).trim()
                })).filter(row => row.article_code || row.article_name);
            }"""
        )
    except (PlaywrightError, RuntimeError, TypeError):
        rows = []
    return list(rows or _material_rows(frame))[:5000]


def _scan_material_option_rows(frame: Frame) -> list[dict[str, Any]]:
    code_input = frame.locator("#txtSearchArticleCode")
    name_input = frame.locator("#txtSearchArticleName")
    if code_input.count() == 1:
        code_input.fill("")
    if name_input.count() == 1:
        name_input.fill("")
    # Material Search normally binds its initial data when opened. Enter on an
    # empty Code field is the lightweight fallback for builds that wait for
    # the first search action before binding the grid.
    if code_input.count() == 1 and not _material_option_rows(frame):
        code_input.press("Enter")
    previous: list[dict[str, Any]] | None = None
    stable_reads = 0
    latest: list[dict[str, Any]] = []
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        checkpoint()
        latest = _material_option_rows(frame)
        if latest == previous:
            stable_reads += 1
        else:
            stable_reads = 0
        if stable_reads >= 2:
            break
        previous = latest
        _sleep(0.15)
    unique = {}
    for row in latest:
        identity = (
            str(row.get("article_code") or "").casefold(),
            str(row.get("article_name") or "").casefold(),
        )
        if any(identity):
            unique.setdefault(identity, row)
    return list(unique.values())[:5000]


def _scan_costing_article_dropdowns(
    frame: Frame,
    document: dict[str, Any],
    log: Callable[[str], None],
) -> None:
    """Opt-in scan for Article Code/Name dropdowns, one Material section at a time."""
    context = frame.page.context
    special_tokens = set(_SPECIAL_COST_SECTION_EDITORS)
    total = 0
    for section in document.get("sections") or ():
        semantic = _costing_semantic_token(
            f"{section.get('section_key', '')} {section.get('name', '')}"
        )
        if any(token in semantic for token in special_tokens):
            continue
        checkpoint()
        section_key = str(section.get("section_key") or "")
        search_frame = None
        try:
            _section_action(frame, section_key, "imgAdd").click()
            _page, search_frame = _material_search_frame(context)
            rows = _scan_material_option_rows(search_frame)
        except (PlaywrightError, PlaywrightTimeoutError, RuntimeError) as error:
            _write_log(
                log,
                "[COSTING] Không quét được dropdown Article cho "
                f"{section.get('name') or section_key}: {_first_line(error)[:120]}",
            )
            rows = []
        finally:
            try:
                if search_frame is not None:
                    _close_material_search(search_frame)
            except (PlaywrightError, RuntimeError):
                pass
        if not rows:
            continue
        section["article_code_options"] = list(
            dict.fromkeys(
                str(row.get("article_code") or "").strip()
                for row in rows
                if str(row.get("article_code") or "").strip()
            )
        )
        section["article_name_options"] = list(
            dict.fromkeys(
                str(row.get("article_name") or "").strip()
                for row in rows
                if str(row.get("article_name") or "").strip()
            )
        )
        total += len(rows)
    document["article_dropdown_option_count"] = total
    _write_log(
        log,
        f"[COSTING] Đã quét {total} lựa chọn Article cho dropdown XLSX.",
    )


def _search_material(
    frame: Frame,
    *,
    article_code: str = "",
    article_name: str = "",
) -> list[dict[str, Any]]:
    code = str(article_code or "").strip()
    name = str(article_name or "").strip()
    if not code and not name:
        return []
    code_input = frame.locator("#txtSearchArticleCode")
    name_input = frame.locator("#txtSearchArticleName")
    if code_input.count() != 1 or name_input.count() != 1:
        raise RuntimeError("COSTING_MATERIAL_SEARCH_INPUT_NOT_UNIQUE")
    code_input.fill("")
    name_input.fill("")
    search = code_input if code else name_input
    wanted = code or name
    search.fill(wanted)
    search.press("Enter")

    deadline = time.monotonic() + 8
    previous: list[dict[str, Any]] | None = None
    stable_reads = 0
    latest: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        checkpoint()
        latest = _material_rows(frame)
        searchable = [
            row["article_code"] if code else row["article_name"] for row in latest
        ]
        filtered = not latest or all(
            value.casefold() == wanted.casefold() for value in searchable
        )
        if filtered and latest == previous:
            stable_reads += 1
        else:
            stable_reads = 0
        if filtered and stable_reads >= 1:
            break
        previous = latest
        _sleep(0.15)
    return [
        row
        for row in latest
        if (
            row["article_code"].casefold() == code.casefold()
            if code
            else row["article_name"].casefold() == name.casefold()
        )
    ]


def _resolved_search(
    addition: Mapping[str, Any],
    resolutions: Mapping[str, str],
) -> tuple[str, str]:
    item_key = str(addition.get("import_item_key") or "").strip()
    resolution = str(resolutions.get(item_key) or "").strip()
    return (
        resolution or str(addition.get("article_code") or "").strip(),
        "" if resolution else str(addition.get("article_name") or "").strip(),
    )


def _preflight_article_additions(
    context: Any,
    frame: Frame,
    additions: Sequence[Mapping[str, Any]],
    resolutions: Mapping[str, str],
    log: Callable[[str], None],
) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for addition in additions:
        grouped.setdefault(str(addition.get("section_key") or ""), []).append(addition)
    for section_key, section_items in grouped.items():
        _section_action(frame, section_key, "imgAdd").click()
        _page, search_frame = _material_search_frame(context)
        try:
            for addition in section_items:
                code, name = _resolved_search(addition, resolutions)
                matches = _search_material(
                    search_frame,
                    article_code=code,
                    article_name=name,
                )
                if not matches:
                    missing.append(dict(addition))
                    continue
                if len(matches) > 1:
                    ambiguous.append(
                        {
                            **dict(addition),
                            "candidates": matches[:50],
                        }
                    )
                    continue
                found.append(
                    {
                        **dict(addition),
                        "resolved_code": matches[0]["article_code"],
                        "resolved_name": matches[0]["article_name"],
                    }
                )
        finally:
            _close_material_search(search_frame)
    if missing:
        _write_log(
            log,
            f"[COSTING] Bỏ qua {len(missing)} Article không tìm thấy.",
        )
    return {
        "found": found,
        "missing": missing,
        "ambiguous": ambiguous,
    }


def _select_material_match(
    frame: Frame,
    match: Mapping[str, Any],
) -> None:
    rows = frame.locator("#gridArticleList_tblGridContent > tbody > tr")
    candidates = []
    for index in range(rows.count()):
        row = rows.nth(index)
        row_id = str(
            row.get_attribute("rowid") or row.get_attribute("id") or ""
        ).strip()
        if row_id == str(match.get("row_id") or ""):
            candidates.append(row)
    if len(candidates) != 1:
        raise RuntimeError("COSTING_MATERIAL_RESULT_DETACHED")
    checkbox = candidates[0].locator("#chkSelector")
    if checkbox.count() != 1 or not checkbox.is_visible():
        raise RuntimeError("COSTING_MATERIAL_SELECTOR_NOT_UNIQUE")
    checkbox.check()


def _add_articles(
    context: Any,
    frame: Frame,
    preflight: Mapping[str, Any],
    log: Callable[[str], None],
) -> list[dict[str, Any]]:
    found = list(preflight.get("found") or ())
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for addition in found:
        grouped.setdefault(str(addition.get("section_key") or ""), []).append(addition)
    added = []
    for section_key, section_items in grouped.items():
        _section_action(frame, section_key, "imgAdd").click()
        _page, search_frame = _material_search_frame(context)
        for index, addition in enumerate(section_items):
            matches = _search_material(
                search_frame,
                article_code=str(addition.get("resolved_code") or ""),
            )
            if len(matches) != 1:
                _close_material_search(search_frame)
                raise RuntimeError("COSTING_MATERIAL_RESULT_CHANGED")
            _select_material_match(search_frame, matches[0])
            last = index == len(section_items) - 1
            selector = (
                "#sectionArticleList .clsSectionTitleBarToolAddnClose"
                if last
                else "#sectionArticleList .clsSectionTitleBarToolAddnContinue"
            )
            action = _visible_unique(
                search_frame,
                selector,
                "COSTING_MATERIAL_ACTION_NOT_UNIQUE",
            )
            action.click()
            added.append(dict(addition))
            _sleep(0.25)
    if added:
        _write_log(log, f"[COSTING] Đã thêm {len(added)} Article.")
    return added


def _special_cost_config(request: Mapping[str, Any]) -> Mapping[str, str]:
    semantic = _costing_semantic_token(
        f"{request.get('section_key', '')} {request.get('section_name', '')}"
    )
    matches = [
        config
        for token, config in _SPECIAL_COST_SECTION_EDITORS.items()
        if token in semantic
    ]
    if len(matches) != 1:
        raise RuntimeError("COSTING_SPECIAL_SECTION_NOT_SUPPORTED")
    return matches[0]


def _new_special_cost_row(
    frame: Frame,
    request: Mapping[str, Any],
) -> Any:
    config = _special_cost_config(request)
    row_selector = f"tr.cssGridRow{config['row_class']}"
    before = set(
        frame.locator(f"{row_selector} #chkSelector").evaluate_all(
            "elements => elements.map(element => element.value)"
        )
    )
    _section_action(
        frame,
        str(request.get("section_key") or ""),
        "imgAdd",
    ).click(timeout=2_000)
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        rows = frame.locator(row_selector)
        for index in range(rows.count()):
            row = rows.nth(index)
            checkbox = row.locator("#chkSelector")
            value = (
                str(checkbox.get_attribute("value") or "")
                if checkbox.count()
                else ""
            )
            if value not in before and value.startswith("-10"):
                return row
        _sleep(0.1)
    raise RuntimeError("COSTING_SPECIAL_ROW_NOT_ADDED")


def _select_special_cost_article(
    row: Any,
    request: Mapping[str, Any],
) -> None:
    config = _special_cost_config(request)
    wanted = str(request.get("article_name") or "").strip()
    if not wanted:
        raise RuntimeError("COSTING_SPECIAL_ARTICLE_REQUIRED")
    row.locator(str(config["label"])).click(timeout=2_000)
    editor = row.locator(str(config["editor"]))
    editor.wait_for(state="visible", timeout=3_000)
    editor.dispatch_event("mousedown")
    deadline = time.monotonic() + 5
    matched_values: list[str] = []
    while time.monotonic() < deadline:
        matched_values = editor.locator("option").evaluate_all(
            """(options, wanted) => options
                .filter(option => [option.textContent, option.value]
                    .some(value => String(value || '').trim().toLowerCase()
                        === wanted.trim().toLowerCase()))
                .map(option => String(option.value || '').trim())""",
            wanted,
        )
        if matched_values:
            break
        _sleep(0.1)
    if len(matched_values) != 1:
        raise RuntimeError("COSTING_SPECIAL_ARTICLE_NOT_FOUND")
    _apply_inline_select_option(editor, matched_values[0])
    editor.press("Tab")


def _add_special_cost_lines(
    frame: Frame,
    additions: Sequence[Mapping[str, Any]],
    log: Callable[[str], None],
) -> list[dict[str, Any]]:
    added: list[dict[str, Any]] = []
    for addition in additions:
        checkpoint()
        row = _new_special_cost_row(frame, addition)
        try:
            _select_special_cost_article(row, addition)
        except Exception:
            try:
                checkbox = row.locator("#chkSelector")
                if checkbox.count() == 1 and not checkbox.is_checked():
                    checkbox.evaluate("element => element.click()")
                _section_action(
                    frame,
                    str(addition.get("section_key") or ""),
                    "imgDelete",
                ).evaluate("element => element.click()")
            except PlaywrightError:
                pass
            raise
        added.append(dict(addition))
    if added:
        _write_log(log, f"[COSTING] Đã thêm {len(added)} dòng chi phí.")
    return added


def _delete_row_index(
    live: Mapping[str, Any],
    deletion: Mapping[str, Any],
) -> int:
    section_key = str(deletion.get("section_key") or "").casefold()
    item_key = str(
        deletion.get("live_item_key") or deletion.get("import_item_key") or ""
    ).casefold()
    indices = {
        int((field.get("_live") or {}).get("row_index") or 0)
        for field in live.get("fields") or ()
        if str(field.get("scope") or "").casefold() == "item"
        and str(field.get("section_key") or "").casefold() == section_key
        and str(field.get("item_key") or "").casefold() == item_key
    }
    if len(indices) != 1:
        raise RuntimeError("COSTING_DELETE_TARGET_NOT_UNIQUE")
    return indices.pop()


def _delete_articles(
    page: Page,
    frame: Frame,
    live: Mapping[str, Any],
    deletions: Sequence[Mapping[str, Any]],
    log: Callable[[str], None],
) -> list[dict[str, Any]]:
    if not deletions:
        return []
    grid = _visible_costing_grid(frame)
    if grid is None:
        raise RuntimeError("COSTING_GRID_NOT_FOUND")
    grouped: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
    for deletion in deletions:
        row_index = _delete_row_index(live, deletion)
        grouped.setdefault(
            str(deletion.get("section_key") or ""),
            [],
        ).append((row_index, deletion))
    ordered_groups = sorted(
        grouped.items(),
        key=lambda entry: max(row for row, _item in entry[1]),
        reverse=True,
    )
    deleted: list[dict[str, Any]] = []
    for section_key, targets in ordered_groups:
        rows = grid.locator(":scope > tbody > tr")
        for row_index, deletion in targets:
            if row_index < 0 or row_index >= rows.count():
                raise RuntimeError("COSTING_DELETE_TARGET_DETACHED")
            row = rows.nth(row_index)
            article_text = (
                row.locator("#lblArticle").first.inner_text()
                if row.locator("#lblArticle").count()
                else ""
            )
            code = str(deletion.get("article_code") or "").strip()
            name = str(deletion.get("article_name") or "").strip()
            if code and f"({code})".casefold() not in str(article_text).casefold():
                raise RuntimeError("COSTING_DELETE_TARGET_CHANGED")
            if (
                not code
                and name
                and name.casefold() not in str(article_text).casefold()
            ):
                raise RuntimeError("COSTING_DELETE_TARGET_CHANGED")
            checkbox = row.locator("#chkSelector")
            if checkbox.count() != 1 or not checkbox.is_visible():
                raise RuntimeError("COSTING_DELETE_SELECTOR_NOT_UNIQUE")
            checkbox.check()
            deleted.append(dict(deletion))

        delete = _section_action(frame, section_key, "imgDelete")
        native_dialog_seen = False

        def accept_delete(dialog: Any) -> None:
            nonlocal native_dialog_seen
            native_dialog_seen = True
            dialog.accept()

        page.on("dialog", accept_delete)
        try:
            delete.click()
            _sleep(0.35)
            popups = frame.locator("div#sectionCostSheetDeletionReason")
            visible_popups = [
                popups.nth(index)
                for index in range(popups.count())
                if popups.nth(index).is_visible()
            ]
            if len(visible_popups) != 1:
                raise RuntimeError("COSTING_DELETE_REASON_NOT_FOUND")
            popup = visible_popups[0]
            comments = popup.locator("#txtActionRemarks")
            if comments.count() != 1 or not comments.is_visible():
                raise RuntimeError("COSTING_DELETE_REASON_NOT_FOUND")
            comments.fill("Updated via Costing import")
            ok = popup.locator(".clsSectionTitleBarToolOk")
            visible_ok = [
                ok.nth(index)
                for index in range(ok.count())
                if ok.nth(index).is_visible()
            ]
            if len(visible_ok) != 1:
                raise RuntimeError("COSTING_DELETE_REASON_OK_NOT_FOUND")
            visible_ok[0].click()
            _sleep(0.35)
        finally:
            page.remove_listener("dialog", accept_delete)
        current_rows = grid.locator(":scope > tbody > tr")
        remaining_text = [
            (
                current_rows.nth(index).locator("#lblArticle").first.inner_text()
                if current_rows.nth(index).locator("#lblArticle").count()
                else ""
            )
            for index in range(current_rows.count())
        ]
        for _row_index, deletion in targets:
            code = str(deletion.get("article_code") or "").strip()
            if code and any(
                f"({code})".casefold() in text.casefold() for text in remaining_text
            ):
                raise RuntimeError("COSTING_DELETE_NOT_CONFIRMED")
        _write_log(
            log,
            f"[COSTING] Đã xóa {len(targets)} Article trong {section_key}"
            f"{' (đã xác nhận WFX)' if native_dialog_seen else ''}.",
        )
    return deleted


def _article_identity(item: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("section_key") or "").casefold(),
        str(item.get("article_code") or item.get("article_name") or "").casefold(),
    )


def _split_article_row(
    frame: Frame,
    live_document: Mapping[str, Any],
    request: Mapping[str, Any],
) -> None:
    """Tạo đúng một continuation row bằng Splitter của Article hiện hữu."""
    wanted = _article_identity(request)
    candidates = [
        item
        for item in live_document.get("items") or ()
        if isinstance(item, Mapping) and _article_identity(item) == wanted
    ]
    if not candidates:
        raise RuntimeError("COSTING_SPLIT_SOURCE_NOT_FOUND")
    source = max(
        candidates,
        key=lambda item: int(item.get("row_order") or 0),
    )
    source_item_key = str(source.get("item_key") or "").casefold()
    source_fields = [
        field
        for field in live_document.get("fields") or ()
        if (
            isinstance(field, Mapping)
            and str(field.get("section_key") or "").casefold() == wanted[0]
            and str(field.get("item_key") or "").casefold() == source_item_key
            and str((field.get("_live") or {}).get("region") or "") == "grid"
        )
    ]
    if not source_fields:
        raise RuntimeError("COSTING_SPLIT_SOURCE_NOT_FOUND")
    row_index = int((source_fields[0].get("_live") or {}).get("row_index") or 0)
    grid = _visible_costing_grid(frame)
    if grid is None:
        raise RuntimeError("COSTING_SPLIT_SOURCE_NOT_FOUND")
    rows = grid.locator(":scope > tbody > tr")
    if row_index < 0 or row_index >= rows.count():
        raise RuntimeError("COSTING_SPLIT_SOURCE_NOT_FOUND")
    row = rows.nth(row_index)
    splitters = row.locator('#colSplitterForUsage [id="imgSplitterForUsage"]')
    visible = [
        splitters.nth(index)
        for index in range(splitters.count())
        if splitters.nth(index).is_visible()
    ]
    if len(visible) != 1:
        raise RuntimeError("COSTING_SPLITTER_NOT_FOUND")
    before = rows.count()
    try:
        visible[0].click(timeout=3_000)
    except PlaywrightError:
        visible[0].evaluate("element => element.click()")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        checkpoint()
        current = _visible_costing_grid(frame)
        if (
            current is not None
            and current.locator(":scope > tbody > tr").count() > before
        ):
            return
        _sleep(0.1)
    raise RuntimeError("COSTING_SPLIT_NOT_CONFIRMED")
