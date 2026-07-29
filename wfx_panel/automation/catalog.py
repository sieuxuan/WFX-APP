"""Workflow Catalog: mở Master, floating filter, lọc Code/Buyer Reference.

Tách nguyên văn từ login.py — không đổi logic.
"""

from __future__ import annotations

import html
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlsplit, urlunsplit

from wfx_panel.automation._common import (
    CATALOG_XPATH,
    COMPANY_ID,
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _result,
    _sleep,
    _style_status_suffix,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
    _start_persistent_chrome,
    invalidate_browser,
)
from wfx_panel.automation.session import _session_is_active, login

ARTICLE_FILE_TAB_INDEXES = (5, 6, 8, 9)
_ATTACHMENT_TABLE_SELECTOR = (
    'table[id^="gridFileUploadDownload"][id$="_tblGridContent"]'
)
_ATTACHMENT_ROWS_JS = """table => [...table.querySelectorAll(
    'tbody tr.trContent, tbody tr[rowid]'
)].map(row => {
    const text = selector => (
        row.querySelector(selector)?.getAttribute('title')
        || row.querySelector(selector)?.textContent
        || ''
    ).replace(/\\s+/g, ' ').trim();
    const view = row.querySelector(
        'td[id="ColView"] a[id="lnkView"], '
        + 'a[id="lnkView"], a[onclick*="ViewAttachmentFile"]'
    );
    return {
        row_id: row.getAttribute('rowid') || row.id || '',
        file_name: text('[id="lblUserFileName"]'),
        comments: text('[id="lblComments"]'),
        uploaded_on: text('[id="lblUploadedOn"]'),
        uploaded_by: text('[id="lblUploadedBY"]'),
        href: view?.getAttribute('href') || '',
        onclick: view?.getAttribute('onclick') || ''
    };
}).filter(row => row.file_name)"""


def _catalog_tree_frame_now(page: Page) -> Frame | None:
    """Tìm frame cây Catalog theo nội dung, không phụ thuộc tên ``left``."""
    named_left = page.frame(name="left")
    candidates = ([named_left] if named_left is not None else []) + list(page.frames)
    seen: set[int] = set()
    for frame in candidates:
        identity = id(frame)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            if frame.locator("#ddlCategory").count() > 0:
                return frame
        except PlaywrightError:
            continue
    return None


def _catalog_left_frame(
    page: Page,
    previous_frame: Frame | None = None,
    timeout_s: float = 10,
) -> Frame:
    """Chờ frame cây Catalog; hỗ trợ cả WFX đổi tên frame ``left``."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = _catalog_tree_frame_now(page)
        if frame is not None and frame != previous_frame:
            return frame
        _wait(page, 250)
    raise PlaywrightTimeoutError("Không tìm thấy frame left hoặc #ddlCategory của Catalog.")


def _catalog_direct_url(page: Page, catalog: Any) -> str | None:
    """Lấy URL Catalog đích từ RedirURL và chỉ chấp nhận cùng WFX origin."""
    try:
        href = str(catalog.get_attribute("href") or "").strip()
    except PlaywrightError:
        return None
    if not href:
        return None
    wrapper_url = urljoin(page.url, href)
    redirect_values = parse_qs(urlsplit(wrapper_url).query).get("RedirURL", [])
    if not redirect_values:
        return None
    direct_url = urljoin(wrapper_url, redirect_values[0])
    page_parts = urlsplit(page.url)
    direct_parts = urlsplit(direct_url)
    if (
        direct_parts.scheme.casefold() != page_parts.scheme.casefold()
        or direct_parts.netloc.casefold() != page_parts.netloc.casefold()
        or not direct_parts.path.casefold().endswith("/wfx_catalogmain.aspx")
    ):
        return None
    return direct_url


def _open_catalog_menu_on_page(
    page: Page,
    catalog: Any,
    log: Callable[[str], None],
    previous_frame: Frame | None = None,
) -> Frame:
    """Mở Catalog; bỏ qua BaseSetting nếu endpoint trung gian bị treo."""
    direct_url = _catalog_direct_url(page, catalog)
    _click(catalog)
    try:
        return _catalog_left_frame(
            page,
            previous_frame=previous_frame,
            timeout_s=3,
        )
    except PlaywrightTimeoutError:
        if direct_url is None:
            raise

    body_element = page.locator(
        'frame[name="body"], iframe[name="body"]'
    ).first
    body_element.wait_for(state="attached", timeout=3_000)
    _write_log(
        log,
        "[CATALOG] Menu phản hồi chậm; đang mở trực tiếp trang Catalog...",
    )
    body_element.evaluate("(element, url) => { element.src = url; }", direct_url)
    return _catalog_left_frame(
        page,
        previous_frame=previous_frame,
        timeout_s=12,
    )


def _click_catalog_master(
    page: Page,
    log: Callable[[str], None],
    previous_frame: Frame | None = None,
) -> None:
    """Click Master và tự retry nếu WFX thay frame trong lúc load."""
    deadline = time.monotonic() + 20
    last_error: Exception | None = None
    old_frame = previous_frame
    while time.monotonic() < deadline:
        try:
            frame = _catalog_left_frame(page, previous_frame=old_frame)
            master = frame.get_by_text("Master", exact=True)
            master.wait_for(state="attached", timeout=2_000)
            _write_log(log, "[CATALOG] Đã tìm thấy Master, đang click...")
            master.evaluate("element => element.click()")
            return
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            last_error = exc
            old_frame = None
            _wait(page, 250)
    raise PlaywrightTimeoutError(f"Không click được Master: {last_error}")


def _catalog_grid_frame(page: Page, previous_frame: Frame | None = None) -> Frame:
    """Chờ Angular AG Grid nằm trong frame right của Catalog."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        for frame in page.frames:
            if frame != previous_frame and "wfxcataloglist" in frame.url.lower():
                try:
                    if frame.locator(".ag-root-wrapper").count() > 0:
                        return frame
                except PlaywrightError:
                    pass
        _wait(page, 250)
    raise PlaywrightTimeoutError("Không tìm thấy AG Grid của Catalog.")


def _show_catalog_floating_filter(
    page: Page,
    log: Callable[[str], None],
    previous_frame: Frame | None = None,
) -> Frame:
    deadline = time.monotonic() + 20
    excluded_frame = previous_frame
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            grid = _catalog_grid_frame(page, previous_frame=excluded_frame)
            show_button = grid.locator("#showfloatingfilter")
            if show_button.count() > 0 and show_button.is_visible():
                _write_log(log, "[FILTER] Đang bật Show Floating Filters...")
                show_button.click(timeout=3_000)
            code_input = grid.locator('input[aria-label="Code Filter Input"]')
            code_input.wait_for(state="visible", timeout=4_000)
            _write_log(log, "[FILTER] Đã sẵn sàng ô lọc cột Code.")
            return grid
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            last_error = exc
            # Angular/WFX có thể thay frame một lần nữa sau khi Master load.
            excluded_frame = None
            _wait(page, 300)
    raise PlaywrightTimeoutError(f"Floating Filter chưa sẵn sàng: {last_error}")


def _select_catalog_category_on_page(
    page: Page,
    category_name: str,
    category_value: str,
    log: Callable[[str], None],
    previous_frame: Frame | None = None,
) -> None:
    frame = _catalog_left_frame(page, previous_frame=previous_frame)
    category = frame.locator("#ddlCategory")
    current_value = category.input_value()
    if current_value == category_value:
        _write_log(log, f"[CATEGORY] Đã ở sẵn Category: {category_name}")
        return

    _write_log(log, f"[CATEGORY] Đang tải và chọn: {category_name}")
    category.dispatch_event("mousedown")
    category.locator(f'option[value="{category_value}"]').wait_for(
        state="attached",
        timeout=5_000,
    )
    category.select_option(value=category_value, timeout=5_000)

    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current_frame = _catalog_tree_frame_now(page)
        if current_frame is not None:
            try:
                if (
                    current_frame.locator("#ddlCategory").input_value(timeout=500)
                    == category_value
                ):
                    _write_log(log, f"[CATEGORY] Đã chọn: {category_name}")
                    return
            except PlaywrightError:
                pass
        _wait(page, 200)
    raise PlaywrightTimeoutError(f"WFX không xác nhận Category {category_name}.")


def _open_catalog_tree_on_page(
    page: Page,
    category_name: str,
    category_value: str,
    log: Callable[[str], None],
) -> Frame:
    """Mở cây Catalog và chọn Category, nhưng không tự click Master."""
    previous_left = _catalog_tree_frame_now(page)
    catalog = page.locator(f"xpath={CATALOG_XPATH}")
    catalog.wait_for(state="attached", timeout=8_000)
    _write_log(log, "[CATALOG] Đang mở cây thư mục...")
    _open_catalog_menu_on_page(
        page,
        catalog,
        log,
        previous_frame=previous_left,
    )
    _select_catalog_category_on_page(
        page,
        category_name,
        category_value,
        log,
        previous_frame=previous_left,
    )
    return _catalog_left_frame(page)


def _catalog_folder_nodes(frame: Frame) -> list[dict[str, Any]]:
    """Đọc toàn bộ cây con bên dưới Master từ DOM đã được WFX nạp."""
    nodes = frame.evaluate(
        """() => {
            const clean = value =>
                String(value || '').replace(/\\s+/g, ' ').trim();
            const roots = [...document.querySelectorAll('ul[nodecode]')];
            const root = roots.find(
                element => clean(element.getAttribute('nodecode')) === 'Master'
            );
            if (!root) return [];
            const directSpan = element =>
                [...element.children].find(child =>
                    child.matches?.('span[nodeid][onclick]')
                ) || null;
            return [...root.querySelectorAll('li > span[nodeid][onclick]')]
                .map(span => {
                    const li = span.closest('li');
                    if (!li) return null;
                    const path = [];
                    let current = li;
                    while (current && root.contains(current)) {
                        const own = directSpan(current);
                        if (own) path.unshift(clean(own.textContent));
                        current = current.parentElement?.closest('li') || null;
                    }
                    const childTree = [...li.children].find(child =>
                        child.matches?.('ul[nodecode]')
                    );
                    const nodeId = clean(span.getAttribute('nodeid'));
                    if (!nodeId || !path.length) return null;
                    return {
                        node_id: nodeId,
                        node_code: clean(childTree?.getAttribute('nodecode')),
                        name: path[path.length - 1],
                        path,
                        path_label: path.join(' / '),
                        kind: li.classList.contains('GroupNode')
                            ? 'group'
                            : 'folder',
                        depth: path.length,
                    };
                })
                .filter(Boolean);
        }"""
    )
    return nodes if isinstance(nodes, list) else []


def _catalog_folder_for_node(
    frame: Frame,
    node_id: str,
) -> dict[str, Any] | None:
    for folder in _catalog_folder_nodes(frame):
        if str(folder.get("node_id") or "") == node_id:
            return folder
    return None


def _wait_catalog_folder_selected(
    page: Page,
    node_id: str,
    timeout_s: float = 10,
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = _catalog_tree_frame_now(page)
        if frame is not None:
            try:
                selected = frame.locator(
                    f'span.clsTreeSelectedNode[nodeid="{node_id}"]'
                )
                if selected.count() > 0:
                    return True
            except PlaywrightError:
                pass
        _wait(page, 200)
    return False


def _filter_grid_and_maybe_open(
    grid: Frame,
    filter_kind: str,
    query: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    definitions = {
        "code": ("Code", 'input[aria-label="Code Filter Input"]', "lnkArticleCode"),
        "buyer_reference": (
            "Buyer Reference",
            'input[aria-label="Buyer Reference Filter Input"]',
            "lblBuyerReference",
        ),
    }
    if filter_kind not in definitions:
        return _result(False, "INVALID_FILTER", f"Filter không hỗ trợ: {filter_kind}")
    label, input_selector, value_column = definitions[filter_kind]

    # Không để điều kiện cũ ở hai cột chồng lên lần tìm mới.
    for selector in (
        'input[aria-label="Code Filter Input"]',
        'input[aria-label="Buyer Reference Filter Input"]',
    ):
        field = grid.locator(selector)
        if field.count() and field.is_visible():
            field.fill("", timeout=3_000)

    search_input = grid.locator(input_selector)
    search_input.wait_for(state="visible", timeout=5_000)
    _write_log(log, f"[{label.upper()}] Đang lọc gần đúng: {query}")
    search_input.fill(query, timeout=3_000)
    if search_input.input_value(timeout=1_000) != query:
        return _result(
            False,
            "FILTER_VALUE_NOT_CONFIRMED",
            f"WFX chưa xác nhận giá trị {label}.",
        )
    _wait(grid, 1_000)

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
            const text = colId => (
                find(`[role="gridcell"][col-id="${colId}"]`)?.textContent || ''
            ).replace(/\\s+/g, ' ').trim();
            const code = (
                find(
                    '[role="gridcell"][col-id="lnkArticleCode"] ' +
                    'input[type="button"]'
                )?.value || ''
            ).trim();
            return {
                code,
                value: args.valueColumn === 'lnkArticleCode'
                    ? code : text(args.valueColumn),
                season: text('lblSeason'),
                internalCostSheetStatus: text('lblInternalCostSheetStatus')
            };
        });
        return {loading, noRows, rows};
    }"""

    deadline = time.monotonic() + 25
    rows: list[dict[str, str]] = []
    stable_key: tuple[Any, ...] | None = None
    stable_since = 0.0
    while time.monotonic() < deadline:
        state = root.evaluate(
            read_rows_js,
            {"valueColumn": value_column},
        )
        rows = state["rows"]
        values = [row["value"] for row in rows if row["value"]]
        applied = bool(values) and all(
            query.casefold() in value.casefold() for value in values
        )
        key = (
            state["loading"],
            state["noRows"],
            tuple(
                (
                    row["code"].casefold(),
                    row["season"],
                    row["internalCostSheetStatus"],
                )
                for row in rows
            ),
        )
        ready = not state["loading"] and (applied or state["noRows"])
        if ready and key == stable_key:
            # AG Grid có thể chớp no-rows trong lúc debounce dù loading overlay
            # không hiện. Giữ no-rows lâu hơn trước khi kết luận 0 kết quả.
            required_stable = 1.8 if state["noRows"] else 0.6
            if time.monotonic() - stable_since >= required_stable:
                break
        else:
            stable_key = key
            stable_since = time.monotonic()
        _wait(grid, 200)
    else:
        return _result(
            False,
            "FILTER_RESULTS_NOT_READY",
            f"Kết quả lọc {label} chưa ổn định.",
        )

    unique: dict[str, dict[str, str]] = {}
    for row in rows:
        code = row["code"].strip()
        if not code:
            continue
        key = code.casefold()
        current = unique.setdefault(
            key,
            {
                "code": code,
                "season": "",
                "internal_costsheet_status": "",
            },
        )
        current["season"] = current["season"] or row["season"].strip()
        current["internal_costsheet_status"] = (
            current["internal_costsheet_status"]
            or row["internalCostSheetStatus"].strip()
        )

    styles = list(unique.values())[:20]
    codes = [style["code"] for style in styles]
    values = [row["value"] for row in rows if row["value"]]
    _write_log(
        log,
        f"[{label.upper()}] unique Code={len(codes)}; "
        f"renderedRows={len(rows)}; codes={codes}",
    )
    if not styles:
        return _result(
            False,
            "NO_RESULTS",
            f"Không tìm thấy kết quả cho {label}: {query}.",
            codes=[],
            styles=[],
        )
    if len(styles) >= 2:
        return _result(
            True,
            "MULTIPLE_RESULTS",
            f"Có {len(styles)} Code; giữ danh sách để bạn tự chọn.",
            codes=codes,
            matches=values,
            styles=styles,
        )

    style_status = styles[0]
    target_code = style_status["code"]
    code_buttons = grid.locator(
        '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'
    )
    clicked = False
    for index in range(code_buttons.count()):
        item = code_buttons.nth(index)
        try:
            if (
                item.is_visible()
                and item.input_value(timeout=500).strip().casefold()
                == target_code.casefold()
            ):
                _write_log(log, f"[{label.upper()}] Một kết quả, đang mở {target_code}...")
                item.click(timeout=5_000)
                clicked = True
                break
        except PlaywrightError:
            continue
    if not clicked:
        return _result(False, "RESULT_DETACHED", "Kết quả vừa thay đổi trước khi click.")
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


def _open_article_destination(
    context: Any,
    destination: str,
    previous_states: list[tuple[Page, str, str]],
    log: Callable[[str], None],
    timeout_seconds: float = 40,
) -> str:
    targets = {
        "costsheet": ("Costsheet", "#CostSheet"),
        "bom": ("BOM", "#BOMMaster"),
    }
    if destination not in targets:
        raise ValueError(f"Article destination không hỗ trợ: {destination}")
    label, selector = targets[destination]
    started = time.monotonic()
    deadline = started + timeout_seconds
    _write_log(log, f"[ARTICLE] Đang chờ ArticleTop để mở {label}...")
    slow_notice_written = False

    while time.monotonic() < deadline:
        for candidate in reversed(context.pages):
            article_top = candidate.frame(name="ArticleTop")
            if article_top is None:
                continue
            old_state = next(
                (state for state in previous_states if state[0] is candidate),
                None,
            )
            navigation_changed = (
                old_state is None
                or candidate.url != old_state[1]
                or article_top.url != old_state[2]
            )
            # Nếu click lại đúng style đang mở thì URL có thể không đổi; chờ đủ
            # thời gian để popup nhận focus/load rồi mới dùng lại.
            same_style_grace_elapsed = time.monotonic() - started >= 4
            if not navigation_changed and not same_style_grace_elapsed:
                continue
            target = article_top.locator(selector)
            try:
                if target.count() == 0:
                    continue
                target.wait_for(state="attached", timeout=1_000)
                candidate.bring_to_front()
                _write_log(log, f"[ARTICLE] Đang mở {label}...")
                target.evaluate("element => element.click()")
                _write_log(log, f"[ARTICLE] Đã mở {label}.")
                return label
            except PlaywrightError:
                continue
        if not slow_notice_written and time.monotonic() - started >= 15:
            _write_log(log, "[ARTICLE] WFX đang tải chậm, tiếp tục chờ ArticleTop...")
            slow_notice_written = True
        _sleep(0.25)
    raise PlaywrightTimeoutError(f"Không tìm thấy nút {label} trong ArticleTop.")


def _refresh_article_context(
    playwright: Playwright,
    browser: Any,
    page: Page,
    log: Callable[[str], None],
) -> tuple[Any, Page]:
    """Làm mới CDP tại ranh giới popup Article để tránh frame cache bị detach."""
    context = (getattr(browser, "contexts", None) or [None])[0]
    article_seen = False
    for candidate in list(getattr(context, "pages", ()) or ()):
        article_top = candidate.frame(name="ArticleTop")
        if article_top is None:
            if "wfx_articledetail" in str(candidate.url or "").casefold():
                article_seen = True
            continue
        article_seen = True
        # Không trả lại frame hiện tại dù đang đọc được: khi click lại cùng
        # style, WFX detach ArticleTop ngay sau nhịp kiểm tra này.
        break

    if not article_seen:
        return browser, page

    _write_log(
        log,
        "[ARTICLE] Đang đồng bộ popup bằng kết nối CDP mới...",
    )
    invalidate_browser(browser)
    refreshed_browser, refreshed_page = _connect_to_chrome(playwright)
    _attach_dialog_handler(refreshed_page, log)
    return refreshed_browser, refreshed_page


def open_catalog_destination(
    article_code: str,
    destination: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở Costsheet/BOM từ popup style đang có, không chạy lại Catalog/search."""
    article_code = str(article_code or "").strip()
    if not article_code:
        return _result(
            False,
            "CATALOG_RESULT_REQUIRED",
            "Hãy tìm và mở một Style Code trước.",
        )
    if destination not in {"costsheet", "bom"}:
        return _result(
            False,
            "ARTICLE_DESTINATION_UNKNOWN",
            f"Đích Article không hỗ trợ: {destination}",
        )
    if not _chrome_is_ready():
        return _result(
            False,
            "CHROME_CLOSED",
            "Chrome automation chưa được mở.",
        )

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        browser, page = _refresh_article_context(
            playwright,
            browser,
            page,
            log,
        )
        label = _open_article_destination(
            browser.contexts[0],
            destination,
            [],
            log,
            timeout_seconds=8,
        )
        return _result(
            True,
            "CATALOG_DESTINATION_OPENED",
            f"Đã mở style {article_code} → {label}.",
            article_code=article_code,
            destination=destination,
        )
    except PlaywrightTimeoutError:
        return _result(
            False,
            "CATALOG_RESULT_EXPIRED",
            "Style đang chọn không còn mở. Hãy bấm Tìm lại rồi chọn Costing/BOM.",
            article_code=article_code,
            destination=destination,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(
            False,
            "CATALOG_DESTINATION_FAILED",
            message,
            article_code=article_code,
            destination=destination,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def _article_page(
    context: Any,
    timeout_seconds: float = 20,
) -> tuple[Page, Frame]:
    """Chờ popup Article và frame điều hướng ``ArticleTop`` của style."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for candidate in reversed(context.pages):
            article_top = candidate.frame(name="ArticleTop")
            if article_top is None:
                continue
            try:
                article_top.locator("body").wait_for(
                    state="attached",
                    timeout=500,
                )
                return candidate, article_top
            except PlaywrightError:
                continue
        _sleep(0.2)
    raise PlaywrightTimeoutError("Không tìm thấy popup ArticleTop của style.")


def _article_file_tab(
    page: Page,
    article_top: Frame,
    index: int,
    timeout_seconds: float = 5,
) -> tuple[Frame, Any, Any] | None:
    """Resolve ``li`` và control có hành động bên trong sau mỗi lần đổi frame."""
    selector = f'xpath=//*[@id="0"]/li[{index}]'
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        current_top = page.frame(name="ArticleTop")
        frames = [
            frame
            for frame in (
                current_top,
                article_top,
                *page.frames,
            )
            if frame is not None
        ]
        seen_frames: set[Any] = set()
        for frame in frames:
            if frame in seen_frames:
                continue
            seen_frames.add(frame)
            try:
                tab = frame.locator(selector)
                if tab.count() > 0:
                    tab = tab.first
                    actionable = tab.locator(
                        "a[onclick], button[onclick], a[href], "
                        "button, [role='button'], [onclick]"
                    )
                    if actionable.count() > 0:
                        return frame, tab, actionable.first
                    if tab.get_attribute("onclick"):
                        return frame, tab, tab
            except PlaywrightError:
                continue
        _wait(page, 200)
    return None


def _mark_article_documents(page: Page) -> list[tuple[Frame, str]]:
    """Đánh dấu document hiện tại để xác nhận click tab thật sự điều hướng."""
    snapshots: list[tuple[Frame, str]] = []
    for index, frame in enumerate(page.frames):
        marker = f"article-file-{time.monotonic_ns()}-{index}"
        try:
            frame.evaluate(
                "marker => { window.__wfxArticleFileMarker = marker; }",
                marker,
            )
            snapshots.append((frame, marker))
        except PlaywrightError:
            continue
    return snapshots


def _article_documents_changed(
    page: Page,
    snapshots: list[tuple[Frame, str]],
) -> bool:
    current_frames = set(page.frames)
    for frame, marker in snapshots:
        if frame not in current_frames:
            return True
        try:
            current = frame.evaluate(
                "() => window.__wfxArticleFileMarker || ''"
            )
            if current != marker:
                return True
        except PlaywrightError:
            return True
    return False


def _article_tab_selected(tab: Any) -> bool:
    try:
        return bool(
            tab.evaluate(
                """element => {
                    const item = element.closest('li') || element;
                    const state = [
                        item.getAttribute('aria-selected') || '',
                        item.getAttribute('aria-current') || '',
                        item.className || '',
                    ].join(' ').toLowerCase();
                    return /(^|\\s)(true|active|current|selected)(\\s|$)/
                        .test(state)
                        || /(active|current|selected)/.test(state);
                }"""
            )
        )
    except PlaywrightError:
        return False


def _visible_attachment_tables(page: Page) -> list[dict[str, Any]]:
    """Đọc các bảng file đang hiển thị trong mọi frame của popup Article."""
    payload: list[dict[str, Any]] = []
    for frame in page.frames:
        try:
            tables = frame.locator(_ATTACHMENT_TABLE_SELECTOR)
            count = tables.count()
        except PlaywrightError:
            continue
        for index in range(count):
            table = tables.nth(index)
            try:
                if not table.is_visible():
                    continue
                payload.append(
                    {
                        "table_id": table.get_attribute("id") or "",
                        "frame_url": frame.url,
                        "rows": table.evaluate(_ATTACHMENT_ROWS_JS),
                    }
                )
            except PlaywrightError:
                continue
    return payload


def _attachment_url(row: dict[str, Any]) -> str:
    """Lấy URL từ href hoặc ``ViewAttachmentFile(this, '...')``."""
    href = html.unescape(str(row.get("href") or "")).strip()
    onclick = html.unescape(str(row.get("onclick") or "")).strip()
    raw = href
    if not raw and onclick:
        match = re.search(
            r"ViewAttachmentFile\s*\(\s*this\s*,\s*(['\"])(.*?)\1",
            onclick,
            flags=re.IGNORECASE,
        )
        raw = match.group(2).strip() if match else ""
    if not raw:
        return ""
    absolute = urljoin("https://prosports.worldfashionexchange.com/", raw)
    parsed = urlsplit(absolute)
    if parsed.scheme.casefold() != "https":
        return ""
    host = (parsed.hostname or "").casefold()
    if host != "worldfashionexchange.com" and not host.endswith(
        ".worldfashionexchange.com"
    ):
        return ""
    normalized_path = quote(
        re.sub(r"/{2,}", "/", parsed.path),
        safe="/%:@-._~!$&'()*+,;=",
    )
    return urlunsplit(
        (
            "https",
            parsed.netloc,
            normalized_path,
            parsed.query,
            "",
        )
    )


def _scan_article_file_tabs(
    page: Page,
    article_top: Frame,
    log: Callable[[str], None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Click bốn mục Article đã chỉ định và gom file đính kèm đang hiển thị."""
    files: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for tab_index in ARTICLE_FILE_TAB_INDEXES:
        resolved = _article_file_tab(page, article_top, tab_index)
        if resolved is None:
            _write_log(
                log,
                f"[ARTICLE FILE] Không tìm thấy mục li[{tab_index}], bỏ qua.",
            )
            sections.append(
                {
                    "index": tab_index,
                    "name": f"Mục {tab_index}",
                    "available": False,
                    "file_count": 0,
                }
            )
            continue

        _frame, tab, action = resolved
        try:
            label = " ".join((tab.inner_text(timeout=1_000) or "").split())
        except PlaywrightError:
            label = ""
        label = label or f"Mục {tab_index}"
        before_ids = {
            str(table.get("table_id") or "")
            for table in _visible_attachment_tables(page)
        }
        document_snapshots = _mark_article_documents(page)
        _write_log(
            log,
            f"[ARTICLE FILE] Đang kiểm tra {label} (li[{tab_index}])...",
        )
        try:
            _click(action)
        except PlaywrightError:
            sections.append(
                {
                    "index": tab_index,
                    "name": label,
                    "available": False,
                    "file_count": 0,
                }
            )
            continue

        started = time.monotonic()
        deadline = started + 6
        visible_tables: list[dict[str, Any]] = []
        confirmed_at: float | None = None
        while time.monotonic() < deadline:
            visible_tables = _visible_attachment_tables(page)
            current_ids = {
                str(table.get("table_id") or "")
                for table in visible_tables
            }
            current_tab = _article_file_tab(
                page, article_top, tab_index, timeout_seconds=0.3
            )
            selected = bool(
                current_tab and _article_tab_selected(current_tab[1])
            )
            changed = _article_documents_changed(
                page, document_snapshots
            ) or current_ids != before_ids
            if confirmed_at is None and (selected or changed):
                confirmed_at = time.monotonic()
                _write_log(
                    log,
                    f"[ARTICLE FILE] Đã vào {label}.",
                )
            if (
                confirmed_at is not None
                and time.monotonic() - confirmed_at >= 0.8
            ):
                break
            _wait(page, 250)

        if confirmed_at is None:
            _write_log(
                log,
                f"[ARTICLE FILE] Click {label} nhưng WFX không xác nhận chuyển mục.",
            )
            sections.append(
                {
                    "index": tab_index,
                    "name": label,
                    "available": False,
                    "file_count": 0,
                }
            )
            continue

        section_count = 0
        for table in visible_tables:
            for raw_row in table.get("rows") or []:
                if not isinstance(raw_row, dict):
                    continue
                download_url = _attachment_url(raw_row)
                key = download_url.casefold()
                if not download_url or key in seen_urls:
                    continue
                seen_urls.add(key)
                section_count += 1
                files.append(
                    {
                        "section": label,
                        "section_index": tab_index,
                        "table_id": str(table.get("table_id") or ""),
                        "row_id": str(raw_row.get("row_id") or ""),
                        "file_name": str(raw_row.get("file_name") or "").strip(),
                        "comments": str(raw_row.get("comments") or "").strip(),
                        "uploaded_on": str(
                            raw_row.get("uploaded_on") or ""
                        ).strip(),
                        "uploaded_by": str(
                            raw_row.get("uploaded_by") or ""
                        ).strip(),
                        "download_url": download_url,
                    }
                )
        sections.append(
            {
                "index": tab_index,
                "name": label,
                "available": True,
                "file_count": section_count,
            }
        )
        _write_log(
            log,
            f"[ARTICLE FILE] {label}: {section_count} file.",
        )
    return files, sections


def scan_catalog_files(
    article_code: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Quét file ở các mục 5, 6, 8, 9 của popup style đang mở."""
    article_code = str(article_code or "").strip()
    if not article_code:
        return _result(
            False,
            "CATALOG_RESULT_REQUIRED",
            "Hãy tìm và mở một Style Code trước.",
        )
    if not _chrome_is_ready():
        return _result(
            False,
            "CHROME_CLOSED",
            "Chrome automation chưa được mở.",
        )

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        browser, page = _refresh_article_context(
            playwright,
            browser,
            page,
            log,
        )
        article, article_top = _article_page(browser.contexts[0])
        article.bring_to_front()
        files, sections = _scan_article_file_tabs(article, article_top, log)
        available = sum(1 for section in sections if section["available"])
        if available == 0:
            return _result(
                False,
                "CATALOG_FILE_TABS_NOT_FOUND",
                "Không tìm thấy bốn mục File trong popup style.",
                article_code=article_code,
                sections=sections,
            )
        message = (
            f"Đã tìm thấy {len(files)} file đính kèm của style {article_code}."
            if files
            else f"Style {article_code} không có file đính kèm trong bốn mục."
        )
        return _result(
            True,
            "CATALOG_FILES_SCANNED",
            message,
            article_code=article_code,
            files=files,
            file_count=len(files),
            sections=sections,
        )
    except PlaywrightTimeoutError:
        return _result(
            False,
            "CATALOG_FILES_CONTEXT_EXPIRED",
            "Style đang chọn không còn mở. Hãy bấm File để tìm lại.",
            article_code=article_code,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(
            False,
            "CATALOG_FILES_SCAN_FAILED",
            message,
            article_code=article_code,
        )
    finally:
        if playwright is not None:
            playwright.stop()


def _safe_attachment_name(value: str) -> str:
    name = Path(str(value or "").replace("\\", "/")).name
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name).strip(" .")
    if not name:
        name = "wfx-attachment"
    stem = Path(name).stem[:150].rstrip(" .")
    suffix = Path(name).suffix[:20]
    return (stem or "wfx-attachment") + suffix


def _available_download_path(directory: Path, file_name: str) -> Path:
    """Không ghi đè: file trùng tên được thêm ``(1)``, ``(2)``..."""
    wanted = directory / _safe_attachment_name(file_name)
    if not wanted.exists():
        return wanted
    for index in range(1, 10_000):
        candidate = wanted.with_name(
            f"{wanted.stem} ({index}){wanted.suffix}"
        )
        if not candidate.exists():
            return candidate
    raise OSError("Không tạo được tên file tải xuống không trùng.")


_DOWNLOAD_CHUNK_SIZE = 4 * 1024 * 1024
_CONTENT_RANGE_RE = re.compile(
    r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$",
    flags=re.IGNORECASE,
)


def _download_attachment_in_chunks(
    request: Any,
    download_url: str,
    target_handle: Any,
    log: Callable[[str], None],
    *,
    chunk_size: int = _DOWNLOAD_CHUNK_SIZE,
) -> int:
    """Tải file WFX theo Range để file lớn không timeout khi buffer một lần."""
    offset = 0
    total: int | None = None
    last_logged_percent = -1

    while total is None or offset < total:
        end = offset + chunk_size - 1
        if total is not None:
            end = min(end, total - 1)
        response = None
        try:
            response = request.get(
                download_url,
                headers={
                    "Accept": "*/*",
                    "Accept-Encoding": "identity",
                    "Range": f"bytes={offset}-{end}",
                },
                timeout=60_000,
                fail_on_status_code=False,
            )
            status = int(response.status)
            body = response.body()

            # Server nhỏ/không hỗ trợ Range: vẫn chấp nhận response đầy đủ.
            if status == 200 and offset == 0:
                if not body:
                    raise RuntimeError("WFX trả về file rỗng.")
                target_handle.write(body)
                return len(body)

            if status != 206:
                raise RuntimeError(
                    f"WFX trả về HTTP {status} khi tải file."
                )
            match = _CONTENT_RANGE_RE.match(
                str(response.headers.get("content-range") or "").strip()
            )
            if match is None or match.group(3) == "*":
                raise RuntimeError(
                    "WFX không trả về Content-Range hợp lệ."
                )
            chunk_start = int(match.group(1))
            chunk_end = int(match.group(2))
            current_total = int(match.group(3))
            expected_size = chunk_end - chunk_start + 1
            if (
                chunk_start != offset
                or current_total <= 0
                or len(body) != expected_size
            ):
                raise RuntimeError(
                    "Dữ liệu file WFX trả về không đầy đủ."
                )
            if total is not None and total != current_total:
                raise RuntimeError(
                    "Kích thước file WFX thay đổi trong lúc tải."
                )
            total = current_total
            target_handle.write(body)
            offset += len(body)

            percent = min(100, int(offset * 100 / total))
            if percent == 100 or percent - last_logged_percent >= 20:
                _write_log(
                    log,
                    f"[ARTICLE FILE] Đã tải {percent}%...",
                )
                last_logged_percent = percent
        finally:
            if response is not None:
                try:
                    response.dispose()
                except PlaywrightError:
                    pass

    return offset


def download_catalog_file(
    file_info: dict[str, Any],
    log: Callable[[str], None] = print,
    download_dir: Path | None = None,
) -> dict[str, Any]:
    """Tải file bằng cookie của BrowserContext và lưu an toàn vào Downloads."""
    file_name = _safe_attachment_name(str(file_info.get("file_name") or ""))
    download_url = _attachment_url(
        {
            "href": str(file_info.get("download_url") or ""),
            "onclick": "",
        }
    )
    if not download_url:
        return _result(
            False,
            "CATALOG_FILE_URL_INVALID",
            "Đường dẫn file không hợp lệ hoặc không thuộc WFX.",
        )
    if not _chrome_is_ready():
        return _result(
            False,
            "CHROME_CLOSED",
            "Chrome automation chưa được mở.",
        )

    playwright: Playwright | None = None
    part_path: Path | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        _write_log(log, f"[ARTICLE FILE] Đang tải {file_name}...")
        target_dir = Path(download_dir or (Path.home() / "Downloads"))
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _available_download_path(target_dir, file_name)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.stem}-",
            suffix=".wfx-part",
            dir=target_dir,
            delete=False,
        ) as part:
            part_path = Path(part.name)
            file_size = _download_attachment_in_chunks(
                browser.contexts[0].request,
                download_url,
                part,
                log,
            )
        part_path.replace(target)
        part_path = None
        _write_log(log, f"[ARTICLE FILE] Đã lưu {target.name}.")
        return _result(
            True,
            "CATALOG_FILE_DOWNLOADED",
            f"Đã tải {target.name} vào thư mục Downloads.",
            file_name=target.name,
            download_path=str(target),
            file_size=file_size,
        )
    except OSError as exc:
        return _result(
            False,
            "CATALOG_FILE_SAVE_FAILED",
            f"Không lưu được file: {exc}",
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "CATALOG_FILE_DOWNLOAD_FAILED", message)
    finally:
        if part_path is not None:
            try:
                part_path.unlink(missing_ok=True)
            except OSError:
                pass
        if playwright is not None:
            playwright.stop()


def find_in_open_catalog(
    category_name: str,
    filter_kind: str,
    query: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Lọc grid Catalog đã chuẩn bị; không mở lại menu/category/master."""
    query = str(query or "").strip()
    if not query:
        return _result(False, "QUERY_REQUIRED", "Vui lòng nhập nội dung cần tìm.")
    if not _chrome_is_ready():
        return _result(
            False,
            "CHROME_CLOSED",
            "Chrome automation chưa được mở.",
        )

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        _write_log(log, "[CATALOG] Dùng grid Master đang mở, không tải lại Catalog.")
        grid = _show_catalog_floating_filter(page, log)
        result = _filter_grid_and_maybe_open(
            grid,
            filter_kind,
            query,
            log,
        )
        result["session_active"] = True
        result["category"] = category_name
        result["filter_kind"] = filter_kind
        result["query"] = query
        return result
    except PlaywrightTimeoutError:
        return _result(
            False,
            "CATALOG_SEARCH_CONTEXT_LOST",
            "Catalog không còn ở bước Master. Hãy bấm Mở Catalog lại.",
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "CATALOG_SEARCH_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def prepare_catalog_master(
    category_name: str,
    category_value: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở Catalog/Category/Master cho luồng Tìm, Costing và BOM."""
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên chưa đăng nhập hoặc đã hết hạn.",
            )

        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        _open_catalog_tree_on_page(
            page,
            category_name,
            category_value,
            log,
        )
        _write_log(log, "[CATALOG] Đang chuẩn bị Master cho tìm kiếm...")
        _click_catalog_master(page, log)
        _show_catalog_floating_filter(
            page,
            log,
            previous_frame=previous_grid,
        )
        return _result(
            True,
            "CATEGORY_SELECTED",
            f"Đã chuẩn bị {category_name} > Master để tìm kiếm.",
            category=category_name,
            value=category_value,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Catalog Master chưa sẵn sàng: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "CATALOG_NOT_OPEN", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "CATEGORY_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def scan_catalog_folders(
    category_name: str,
    category_value: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở cây Catalog và trả về mọi folder/group user được nhìn thấy."""
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên chưa đăng nhập hoặc đã hết hạn.",
            )

        frame = _open_catalog_tree_on_page(
            page,
            category_name,
            category_value,
            log,
        )
        folders = _catalog_folder_nodes(frame)
        if not folders:
            return _result(
                False,
                "CATALOG_FOLDER_TREE_EMPTY",
                "WFX chưa trả về cây thư mục Catalog.",
                category=category_name,
                value=category_value,
                folders=[],
            )
        _write_log(
            log,
            f"[CATALOG FOLDER] Đã quét {len(folders)} thư mục user được quyền xem.",
        )
        return _result(
            True,
            "CATALOG_FOLDERS_SCANNED",
            f"Đã quét {len(folders)} thư mục Catalog.",
            category=category_name,
            value=category_value,
            folders=folders,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Không quét được cây Catalog: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "CATALOG_FOLDER_SCAN_TIMEOUT", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "CATALOG_FOLDER_SCAN_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def open_catalog_folder(
    category_name: str,
    category_value: str,
    node_id: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Mở một folder user theo node ID; node rỗng nghĩa là Master."""
    node_id = str(node_id or "").strip()
    if node_id and not node_id.isdigit():
        return _result(
            False,
            "CATALOG_FOLDER_INVALID",
            "Thư mục Catalog không hợp lệ.",
        )

    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên chưa đăng nhập hoặc đã hết hạn.",
            )

        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        frame = _open_catalog_tree_on_page(
            page,
            category_name,
            category_value,
            log,
        )
        if not node_id:
            _click_catalog_master(page, log)
            _show_catalog_floating_filter(
                page,
                log,
                previous_frame=previous_grid,
            )
            return _result(
                True,
                "CATALOG_FOLDER_OPENED",
                f"Đã mở {category_name} > Master.",
                category=category_name,
                value=category_value,
                folder={
                    "node_id": "",
                    "node_code": "Master",
                    "name": "Master",
                    "path": ["Master"],
                    "path_label": "Master",
                    "kind": "master",
                    "depth": 0,
                },
            )

        folder = _catalog_folder_for_node(frame, node_id)
        if folder is None:
            return _result(
                False,
                "CATALOG_FOLDER_STALE",
                "Folder mặc định không còn tồn tại hoặc user không còn quyền xem.",
                category=category_name,
                value=category_value,
            )

        target = frame.locator(f'span[nodeid="{node_id}"][onclick]').first
        target.wait_for(state="attached", timeout=3_000)
        _write_log(
            log,
            f"[CATALOG FOLDER] Đang mở {folder['path_label']}...",
        )
        target.evaluate("element => element.click()")
        if not _wait_catalog_folder_selected(page, node_id):
            raise PlaywrightTimeoutError("WFX không xác nhận folder đã chọn.")
        return _result(
            True,
            "CATALOG_FOLDER_OPENED",
            f"Đã mở Catalog > {folder['path_label']}.",
            category=category_name,
            value=category_value,
            folder=folder,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Không mở được folder Catalog: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "CATALOG_FOLDER_OPEN_TIMEOUT", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "CATALOG_FOLDER_OPEN_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def quick_find_catalog(
    category_name: str,
    category_value: str,
    filter_kind: str,
    query: str,
    user_id: str,
    password: str,
    company_id: str = COMPANY_ID,
    log: Callable[[str], None] = print,
    destination: str | None = None,
) -> dict[str, Any]:
    """Tự login, vào Catalog/Category/Master rồi lọc và mở khi chỉ có một dòng."""
    query = query.strip()
    if not query:
        return _result(False, "QUERY_REQUIRED", "Vui lòng nhập nội dung cần tìm.")
    if destination and category_value != "01":
        return _result(
            False,
            "APPAREL_ONLY",
            "Costsheet và BOM chỉ hỗ trợ Category Apparel.",
        )

    playwright: Playwright | None = None
    try:
        _start_persistent_chrome(log)
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)

        if _session_is_active(page):
            _write_log(log, "[SESSION] Dùng lại phiên WFX đang login.")
        else:
            if not user_id.strip() or not password:
                return _result(
                    False,
                    "MISSING_CREDENTIALS",
                    "Chưa có tài khoản. Hãy lưu trong Settings.",
                )
            _write_log(log, "[SESSION] Chưa login, đang tự đăng nhập...")
            login(page, user_id.strip(), password, company_id)
            _write_log(log, "[SESSION] Tự đăng nhập thành công.")

        previous_left = _catalog_tree_frame_now(page)
        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        _write_log(log, "[QUICK SEARCH] Đang mở Catalog...")
        catalog = page.locator(f"xpath={CATALOG_XPATH}")
        catalog.wait_for(state="attached", timeout=8_000)
        _open_catalog_menu_on_page(
            page,
            catalog,
            log,
            previous_frame=previous_left,
        )

        _select_catalog_category_on_page(
            page,
            category_name,
            category_value,
            log,
            previous_frame=previous_left,
        )
        _write_log(log, "[QUICK SEARCH] Đang mở Master...")
        _click_catalog_master(page, log)
        grid = _show_catalog_floating_filter(page, log, previous_frame=previous_grid)
        result = _filter_grid_and_maybe_open(
            grid,
            filter_kind,
            query,
            log,
        )
        if destination and result.get("code") == "RESULT_OPENED":
            # Popup WFX cũ đôi khi chỉ được CDP nhận đầy đủ sau khi reconnect.
            _write_log(log, "[ARTICLE] Đang kết nối lại để nhận popup Article...")
            playwright.stop()
            playwright = None
            _sleep(0.8)
            playwright = sync_playwright().start()
            browser_after_popup, _main_page = _connect_to_chrome(playwright)
            destination_label = _open_article_destination(
                browser_after_popup.contexts[0],
                destination,
                [],
                log,
            )
            result["destination"] = destination
            result["message"] = (
                f"Đã mở style {result['article_code']} → {destination_label}."
                f"{_style_status_suffix(result.get('style_status'))}"
            )
        result["session_active"] = True
        result["category"] = category_name
        result["filter_kind"] = filter_kind
        result["query"] = query
        return result
    except PlaywrightTimeoutError as exc:
        message = f"Quick Search timeout: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "QUICK_SEARCH_TIMEOUT", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "QUICK_SEARCH_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def set_catalog_category(
    category_name: str,
    category_value: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Chọn Category trong frame left của Catalog."""
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        _write_log(log, "[CATEGORY] Đang tìm frame left và dropdown...")
        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        frame = _catalog_left_frame(page)
        category = frame.locator("#ddlCategory")
        current_value = category.input_value()
        _write_log(
            log,
            f"[CATEGORY] Giá trị hiện tại={current_value or '[Select]'}, cần chọn={category_value}",
        )

        # WFX chỉ nạp đủ option sau mousedown qua hàm BindDDL.
        _write_log(log, "[CATEGORY] Đang tải danh sách Category từ WFX...")
        category.dispatch_event("mousedown")
        option = category.locator(f'option[value="{category_value}"]')
        option.wait_for(state="attached", timeout=5_000)
        _write_log(log, f"[CATEGORY] Đã tải option {category_name}, đang chọn...")
        category.select_option(value=category_value, timeout=5_000)

        # Xác nhận lại sau onchange; WFX có thể reload nội dung frame.
        deadline = time.monotonic() + 8
        selected_value = ""
        while time.monotonic() < deadline:
            current_frame = _catalog_tree_frame_now(page)
            if current_frame is not None:
                try:
                    selected_value = current_frame.locator("#ddlCategory").input_value(
                        timeout=500
                    )
                    if selected_value == category_value:
                        break
                except PlaywrightTimeoutError:
                    pass
            _wait(page, 200)
        if selected_value != category_value:
            raise PlaywrightTimeoutError(
                f"WFX không xác nhận Category value={category_value}."
            )

        _write_log(log, f"[CATEGORY] Đã chọn thành công: {category_name}")
        _write_log(log, "[CATEGORY] Đang tự động mở Master...")
        _click_catalog_master(page, log)
        _show_catalog_floating_filter(page, log, previous_frame=previous_grid)
        return _result(
            True,
            "CATEGORY_SELECTED",
            f"Đã chọn {category_name}, mở Master và Floating Filter.",
            category=category_name,
            value=category_value,
        )
    except PlaywrightTimeoutError:
        message = "Không tìm thấy Category. Hãy mở Catalog trước."
        _write_log(log, message)
        return _result(False, "CATALOG_NOT_OPEN", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _write_log(log, message)
        return _result(False, "CATEGORY_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def open_catalog_master(log: Callable[[str], None] = print) -> dict[str, Any]:
    """Click node Master trong frame left của Catalog."""
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        _click_catalog_master(page, log)
        _show_catalog_floating_filter(page, log, previous_frame=previous_grid)
        _write_log(log, "Đã mở Catalog > Master và Floating Filter")
        return _result(
            True,
            "MASTER_OPENED",
            "Đã mở Catalog > Master và Floating Filter.",
        )
    except PlaywrightTimeoutError:
        message = "Không tìm thấy nút Master. Hãy mở Catalog trước."
        _write_log(log, message)
        return _result(False, "MASTER_NOT_FOUND", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _write_log(log, message)
        return _result(False, "MASTER_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()


def filter_and_open_catalog_code(
    article_code: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Lọc chính xác cột Code, cào kết quả rồi click mở style tương ứng."""
    article_code = article_code.strip()
    if not article_code:
        return _result(False, "CODE_REQUIRED", "Vui lòng nhập Code cần tìm.")

    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        grid = _show_catalog_floating_filter(page, log)

        code_input = grid.locator('input[aria-label="Code Filter Input"]')
        _write_log(log, f"[CODE] Đang lọc chính xác: {article_code}")
        code_input.fill(article_code, timeout=3_000)
        # AG Grid debounce trước khi áp dụng floating filter.
        _wait(grid, 1_000)

        code_cells = grid.locator(
            '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'
        )
        deadline = time.monotonic() + 12
        codes: list[str] = []
        exact_target = None
        while time.monotonic() < deadline:
            codes = []
            exact_target = None
            for index in range(code_cells.count()):
                item = code_cells.nth(index)
                try:
                    if not item.is_visible():
                        continue
                    value = item.input_value(timeout=500).strip()
                    if value:
                        codes.append(value)
                    if value.casefold() == article_code.casefold():
                        exact_target = item
                except PlaywrightError:
                    continue
            filter_applied = bool(codes) and all(
                article_code.casefold() in value.casefold() for value in codes
            )
            if exact_target is not None and filter_applied:
                break
            _wait(grid, 300)

        _write_log(log, f"[CODE] Kết quả grid: {codes if codes else 'không có'}")
        if exact_target is None:
            return _result(
                False,
                "CODE_NOT_FOUND",
                f"Không tìm thấy Code chính xác: {article_code}.",
                codes=codes,
            )

        _write_log(log, f"[CODE] Đã tìm thấy {article_code}, đang click mở style...")
        exact_target.click(timeout=5_000)
        _write_log(log, f"[CODE] Đã mở style: {article_code}")
        return _result(
            True,
            "CODE_OPENED",
            f"Đã lọc và mở style {article_code}.",
            article_code=article_code,
            codes=codes,
        )
    except PlaywrightTimeoutError as exc:
        message = f"Timeout khi lọc Code: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "CODE_FILTER_TIMEOUT", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        _write_log(log, message)
        return _result(False, "CODE_FILTER_FAILED", message)
    finally:
        if playwright is not None:
            playwright.stop()
