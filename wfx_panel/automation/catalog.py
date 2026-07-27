"""Workflow Catalog: mở Master, floating filter, lọc Code/Buyer Reference.

Tách nguyên văn từ login.py — không đổi logic.
"""

from __future__ import annotations

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
    _style_status_suffix,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
    _start_persistent_chrome,
)
from wfx_panel.automation.session import _session_is_active, login


def _catalog_left_frame(page: Page, previous_frame: Frame | None = None) -> Frame:
    """Chờ và trả về frame left của màn Catalog."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        frame = page.frame(name="left")
        if frame is not None and frame != previous_frame:
            try:
                if frame.locator("#ddlCategory").count() > 0:
                    return frame
            except PlaywrightError:
                pass
        page.wait_for_timeout(250)
    raise PlaywrightTimeoutError("Không tìm thấy frame left hoặc #ddlCategory của Catalog.")


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
            page.wait_for_timeout(250)
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
        page.wait_for_timeout(250)
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
            page.wait_for_timeout(300)
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
        current_frame = page.frame(name="left")
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
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError(f"WFX không xác nhận Category {category_name}.")


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
    grid.wait_for_timeout(1_000)

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
        grid.wait_for_timeout(200)
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
) -> str:
    targets = {
        "costsheet": ("Costsheet", "#CostSheet"),
        "bom": ("BOM", "#BOMMaster"),
    }
    if destination not in targets:
        raise ValueError(f"Article destination không hỗ trợ: {destination}")
    label, selector = targets[destination]
    started = time.monotonic()
    deadline = started + 40
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
        time.sleep(0.25)
    raise PlaywrightTimeoutError(f"Không tìm thấy nút {label} trong ArticleTop.")


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

        previous_left = page.frame(name="left")
        previous_grid = next(
            (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
            None,
        )
        _write_log(log, "[QUICK SEARCH] Đang mở Catalog...")
        catalog = page.locator(f"xpath={CATALOG_XPATH}")
        catalog.wait_for(state="attached", timeout=8_000)
        _click(catalog)

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
            time.sleep(0.8)
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
            current_frame = page.frame(name="left")
            if current_frame is not None:
                try:
                    selected_value = current_frame.locator("#ddlCategory").input_value(
                        timeout=500
                    )
                    if selected_value == category_value:
                        break
                except PlaywrightTimeoutError:
                    pass
            page.wait_for_timeout(200)
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
        grid.wait_for_timeout(1_000)

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
            grid.wait_for_timeout(300)

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
