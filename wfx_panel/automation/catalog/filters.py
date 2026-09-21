"""Điền Floating Filter và quy kết quả về số Code duy nhất.

AG Grid giữ virtual buffer, pinned column và có thể clone row, nên số kết quả
phải đếm theo Code đã khử trùng — không đếm node DOM."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    PlaywrightError,
    PlaywrightTimeoutError,
    _horizontal_grid_positions,
    _horizontal_grid_state,
    _result,
    _scroll_horizontal_grid,
    _style_status_suffix,
    _wait,
    _write_log,
    time,
)


@dataclass(frozen=True)
class _CatalogFilterSpec:
    label: str
    input_selector: str
    value_column: str


@dataclass(frozen=True)
class _CatalogGridPoll:
    grid: Frame
    root: Any
    read_rows_js: str
    search_input: Any
    query: str
    spec: _CatalogFilterSpec
    log: Callable[[str], None]


_CATALOG_FILTER_SPECS = {
    "code": _CatalogFilterSpec(
        "Code",
        'input[aria-label="Code Filter Input"]',
        "lnkArticleCode",
    ),
    "buyer_reference": _CatalogFilterSpec(
        "Buyer Reference",
        'input[aria-label="Buyer Reference Filter Input"]',
        "lblBuyerReference",
    ),
    "article_name": _CatalogFilterSpec(
        "Article Name",
        (
            'input[aria-label="Article Name Filter Input"], '
            'input[aria-label="Name Filter Input"]'
        ),
        "lblArticleName",
    ),
}


_CATALOG_FILTER_INPUT_SELECTORS = (
    'input[aria-label="Code Filter Input"]',
    'input[aria-label="Buyer Reference Filter Input"]',
    'input[aria-label="Article Name Filter Input"]',
    'input[aria-label="Name Filter Input"]',
)


def _visible_catalog_filter(grid: Frame, selector: str) -> Any | None:
    candidates = grid.locator(selector)
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        try:
            if candidate.is_visible() and candidate.is_enabled():
                return candidate
        except PlaywrightError:
            continue
    return None


def _resolve_catalog_filter(
    grid: Frame,
    spec: _CatalogFilterSpec,
) -> Any:
    """Quét/clear mọi Floating Filter kể cả cột bị virtualize ngang."""
    root = grid.locator(".ag-root-wrapper").first
    state = _horizontal_grid_state(root)
    original = max(0, int(float(state.get("current") or 0)))
    target_position: int | None = None
    try:
        for position in _horizontal_grid_positions(state):
            _scroll_horizontal_grid(root, position)
            _wait(grid, 150)
            for selector in _CATALOG_FILTER_INPUT_SELECTORS:
                field = _visible_catalog_filter(grid, selector)
                if field is None:
                    continue
                if field.input_value(timeout=500):
                    field.fill("", timeout=3_000)
            if _visible_catalog_filter(grid, spec.input_selector) is not None:
                target_position = position
    except PlaywrightError:
        target_position = None

    if target_position is None:
        _scroll_horizontal_grid(root, original)
        raise PlaywrightTimeoutError(
            f"Không tìm thấy Floating Filter {spec.label} sau khi quét ngang."
        )
    _scroll_horizontal_grid(root, target_position)
    _wait(grid, 150)
    search_input = _visible_catalog_filter(grid, spec.input_selector)
    if search_input is None:
        raise PlaywrightTimeoutError(
            f"Floating Filter {spec.label} vừa thay đổi sau khi quét ngang."
        )
    return search_input


def _catalog_grid_state_key(state: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        state["loading"],
        state["noRows"],
        tuple(
            (
                row["code"].casefold(),
                row["season"],
                row["internalCostSheetStatus"],
            )
            for row in state["rows"]
        ),
    )


def _catalog_grid_result_ready(
    state: Mapping[str, Any],
    query: str,
) -> bool:
    values = [row["value"] for row in state["rows"] if row["value"]]
    filter_applied = bool(values) and all(
        query.casefold() in value.casefold() for value in values
    )
    return not state["loading"] and (filter_applied or state["noRows"])


def _refill_catalog_filter(
    grid: Frame,
    search_input: Any,
    query: str,
    spec: _CatalogFilterSpec,
) -> dict[str, Any] | None:
    search_input.fill("", timeout=3_000)
    _wait(grid, 1_000)
    search_input.fill(query, timeout=3_000)
    if search_input.input_value(timeout=1_000) == query:
        return None
    return _result(
        False,
        "FILTER_VALUE_NOT_CONFIRMED",
        f"WFX chưa xác nhận lại giá trị {spec.label}.",
    )


def _wait_catalog_grid_rows(
    poll: _CatalogGridPoll,
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    deadline = time.monotonic() + 25
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    empty_since: float | None = None
    filter_reapplied = False
    rows: list[dict[str, str]] = []
    while time.monotonic() < deadline:
        state = poll.root.evaluate(
            poll.read_rows_js,
            {"valueColumn": poll.spec.value_column},
        )
        rows = state["rows"]
        now = time.monotonic()
        phantom_empty = not state["loading"] and not state["noRows"] and not rows
        empty_since = empty_since or now if phantom_empty else None
        if (
            phantom_empty
            and not filter_reapplied
            and empty_since is not None
            and now - empty_since >= 2
        ):
            _write_log(
                poll.log,
                "[FILTER] Grid chưa phản hồi, đang áp dụng lại bộ lọc...",
            )
            error = _refill_catalog_filter(
                poll.grid,
                poll.search_input,
                poll.query,
                poll.spec,
            )
            if error is not None:
                return rows, error
            filter_reapplied = True
            empty_since = None
            stable_key = None
            stable_since = now
            deadline = now + 15
            _wait(poll.grid, 500)
            continue
        state_key = _catalog_grid_state_key(state)
        if (
            _catalog_grid_result_ready(state, poll.query)
            and state_key == stable_key
        ):
            required_stable = 1.8 if state["noRows"] else 0.6
            if now - stable_since >= required_stable:
                return rows, None
        else:
            stable_key = state_key
            stable_since = now
        _wait(poll.grid, 200)
    return rows, _result(
        False,
        "FILTER_RESULTS_NOT_READY",
        f"Kết quả lọc {poll.spec.label} chưa ổn định.",
    )


def _catalog_styles_from_rows(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    unique: dict[str, dict[str, str]] = {}
    for row in rows:
        code = row["code"].strip()
        if not code:
            continue
        style = unique.setdefault(
            code.casefold(),
            {"code": code, "season": "", "internal_costsheet_status": ""},
        )
        style["season"] = style["season"] or row["season"].strip()
        style["internal_costsheet_status"] = (
            style["internal_costsheet_status"]
            or row["internalCostSheetStatus"].strip()
        )
    return list(unique.values())[:20]


def _click_catalog_style(
    grid: Frame,
    target_code: str,
    label: str,
    log: Callable[[str], None],
) -> bool:
    buttons = grid.locator(
        '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'
    )
    for index in range(buttons.count()):
        button = buttons.nth(index)
        try:
            if not button.is_visible():
                continue
            if (
                button.input_value(timeout=500).strip().casefold()
                != target_code.casefold()
            ):
                continue
            _write_log(
                log,
                f"[{label.upper()}] Một kết quả, đang mở {target_code}...",
            )
            button.click(timeout=5_000)
            return True
        except PlaywrightError:
            continue
    return False


def _catalog_result_from_rows(
    grid: Frame,
    query: str,
    rows: list[dict[str, str]],
    spec: _CatalogFilterSpec,
    log: Callable[[str], None],
) -> dict[str, Any]:
    styles = _catalog_styles_from_rows(rows)
    codes = [style["code"] for style in styles]
    values = [row["value"] for row in rows if row["value"]]
    _write_log(
        log,
        f"[{spec.label.upper()}] unique Code={len(codes)}; "
        f"renderedRows={len(rows)}; codes={codes}",
    )
    if not styles:
        return _result(
            False,
            "NO_RESULTS",
            f"Không tìm thấy kết quả cho {spec.label}: {query}.",
            codes=[],
            styles=[],
        )
    exact_style = next(
        (
            style
            for style in styles
            if spec.value_column == "lnkArticleCode"
            and style["code"].casefold() == query.casefold()
        ),
        None,
    )
    if len(styles) >= 2 and exact_style is None:
        return _result(
            True,
            "MULTIPLE_RESULTS",
            f"Có {len(styles)} Code; giữ danh sách để bạn tự chọn.",
            codes=codes,
            matches=values,
            styles=styles,
        )
    style_status = exact_style or styles[0]
    target_code = style_status["code"]
    if not _click_catalog_style(grid, target_code, spec.label, log):
        return _result(
            False,
            "RESULT_DETACHED",
            "Kết quả vừa thay đổi trước khi click.",
        )
    return _result(
        True,
        "RESULT_OPENED",
        f"Đã tìm và mở style {target_code}."
        f"{_style_status_suffix(style_status)}",
        article_code=target_code,
        codes=codes,
        matches=values,
        styles=styles,
        style_status=style_status,
        season=style_status["season"],
        internal_costsheet_status=style_status["internal_costsheet_status"],
    )


def _filter_grid_and_maybe_open(
    grid: Frame,
    filter_kind: str,
    query: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    spec = _CATALOG_FILTER_SPECS.get(filter_kind)
    if spec is None:
        return _result(False, "INVALID_FILTER", f"Filter không hỗ trợ: {filter_kind}")

    # Không để điều kiện cũ ở cột ngoài viewport chồng lên lần tìm mới.
    search_input = _resolve_catalog_filter(grid, spec)
    _write_log(log, f"[{spec.label.upper()}] Đang lọc gần đúng: {query}")
    search_input.fill(query, timeout=3_000)
    if search_input.input_value(timeout=1_000) != query:
        return _result(
            False,
            "FILTER_VALUE_NOT_CONFIRMED",
            f"WFX chưa xác nhận giá trị {spec.label}.",
        )

    root = grid.locator(".ag-root-wrapper").first
    read_rows_js = """(root, args) => {
        const shown = element => {
            if (!element || !element.isConnected) return false;
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                Number(style.opacity || 1) !== 0 &&
                rect.width > 0 && rect.height > 0;
        };
        const loading = [
            '.ag-overlay-loading-wrapper', '.ag-loading', '.ag-row-loading'
        ].some(selector => [...root.querySelectorAll(selector)].some(shown));
        const noRows = [
            '.ag-overlay-no-rows-wrapper', '.ag-overlay-no-rows-center'
        ].some(selector => [...root.querySelectorAll(selector)].some(shown));
        const rows = [...root.querySelectorAll(
            '.ag-center-cols-container .ag-row[row-index], ' +
            '.ag-center-cols-container [role="row"][row-index]'
        )].filter(row => {
            if (!shown(row) || row.classList.contains('ag-row-loading') ||
                row.classList.contains('ag-row-ghost') ||
                row.getAttribute('aria-hidden') === 'true') return false;
            const viewport = row.closest(
                '.ag-center-cols-viewport, .ag-body-viewport'
            );
            if (!viewport) return true;
            const r = row.getBoundingClientRect();
            const v = viewport.getBoundingClientRect();
            return r.bottom > v.top + 0.5 && r.top < v.bottom - 0.5;
        }).map(row => {
            const rowIndex = row.getAttribute('row-index') || '';
            const rowParts = [...root.querySelectorAll(
                `.ag-row[row-index="${rowIndex}"], ` +
                `[role="row"][row-index="${rowIndex}"]`
            )];
            const find = selector => {
                for (const part of rowParts) {
                    const match = part.querySelector(selector);
                    if (match) return match;
                }
                return null;
            };
            const cellValue = cell => (
                cell?.querySelector('input, textarea')?.value ||
                cell?.textContent || ''
            ).replace(/\\s+/g, ' ').trim();
            const text = colId => cellValue(
                find(`[role="gridcell"][col-id="${colId}"]`)
            );
            const textByToken = token => {
                for (const part of rowParts) {
                    for (const cell of part.querySelectorAll(
                        '[role="gridcell"][col-id]'
                    )) {
                        const colId = (cell.getAttribute('col-id') || '')
                            .replace(/[^a-z0-9]/gi, '').toLowerCase();
                        if (colId.includes(token)) return cellValue(cell);
                    }
                }
                return '';
            };
            const code = (
                find(
                    '[role="gridcell"][col-id="lnkArticleCode"] ' +
                    'input[type="button"]'
                )?.value || ''
            ).trim();
            return {
                code,
                value: args.valueColumn === 'lnkArticleCode'
                    ? code
                    : (
                        text(args.valueColumn)
                        || (
                            args.valueColumn === 'lblArticleName'
                                ? textByToken('articlename')
                                : ''
                        )
                    ),
                season: text('lblSeason'),
                internalCostSheetStatus: text('lblInternalCostSheetStatus')
            };
        });
        return {loading, noRows, rows};
    }"""

    rows, polling_error = _wait_catalog_grid_rows(
        _CatalogGridPoll(
            grid=grid,
            root=root,
            read_rows_js=read_rows_js,
            search_input=search_input,
            query=query,
            spec=spec,
            log=log,
        )
    )
    if polling_error is not None:
        return polling_error

    return _catalog_result_from_rows(grid, query, rows, spec, log)
