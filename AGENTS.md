# WFX Catalog automation — nguồn chuẩn để sửa Chrome Extension

## Mục tiêu

File này là đặc tả bắt buộc cho AI sửa `wfx-tampermonkey.user.js` và build lại
`chrome-extension`. Nguồn hành vi chuẩn là Playwright Python trong `login.py`.
Không được coi việc “đã click”, “đã tìm thấy frame” hoặc “đã thấy input” là thành
công nếu trạng thái thật trên UI chưa được xác nhận.

## Kết luận từ log 1.7.1 lúc 23:01:30

1. `Catalog` và Category `Apparel` đã mở đúng.
2. Lần click `Master` đầu tiên làm frame `left` reload/chuyển trạng thái
   (`FromRefresh=1` thành `FromRefresh=`), nhưng chưa tạo Catalog Grid.
3. Script tiếp tục thử `img` và `li` là sai hướng. Tới lần 4, khi nó lấy lại document
   mới và click lại đúng `span` có `onclick`, `wfxcataloglist` mới được tạo.
4. Sau khi `.ag-root-wrapper` xuất hiện, log ghi:
   `rawRows=0`, `rawButtons=0`, `renderedButtons=0`.
5. Dù chưa có row và chưa có bằng chứng nút `#showfloatingfilter` đã được click,
   script vẫn báo `Code Filter đã sẵn sàng` rồi kết thúc mode `prepare`.

Vì vậy có hai lỗi độc lập:

- **Master:** giữ candidate/document cũ quá lâu và thử cả node không có action đúng.
- **Floating Filter:** chỉ kiểm tra input tồn tại/usable, không kiểm tra grid đã nạp
  dữ liệu và filter thật sự đang hiển thị trong grid mới.

## State machine bắt buộc

```text
HOME
  -> click Catalog
  -> NEW_LEFT_FRAME
  -> CATEGORY_CONFIRMED
  -> click exact actionable "Master"
  -> nếu left document reload: reacquire left rồi click lại exact Master
  -> NEW_CATALOG_GRID
  -> GRID_DATA_SETTLED
  -> click #showfloatingfilter nếu Code Filter chưa visible
  -> FILTER_VISIBLE
  -> fill query
  -> FILTER_VALUE_CONFIRMED
  -> FILTER_RESULTS_SETTLED
  -> 0 / 1 / nhiều unique Code
  -> chỉ click Article khi đúng 1 unique Code
```

Không được nhảy state. Mode `prepare` chỉ thành công tại `FILTER_VISIBLE` sau khi
`GRID_DATA_SETTLED`, không phải ngay khi tìm thấy một input ẩn hoặc input thuộc grid cũ.

## Điều kiện xác nhận

### Mở Master

- Trước khi click Catalog, snapshot document của frame `left` và Catalog Grid cũ.
- Sau khi click Catalog, chỉ dùng frame `left` có `#ddlCategory` thuộc document mới.
- Chỉ click node có text chuẩn hóa đúng bằng `Master` và có action trực tiếp
  (`onclick`, `a`, `button`, hoặc `role=button`).
- Ưu tiên đúng node `span[onclick]` như log; không click `img` collapse và không click
  container `li` chỉ vì nó chứa text Master.
- Sau mỗi click, chờ tối đa 4–5 giây:
  - nếu grid mới xuất hiện thì sang bước kế tiếp;
  - nếu document `left` đổi thì lấy lại frame/document và click lại đúng Master;
  - nếu không đổi gì thì retry đúng Master, không chuyển sang node cha/con ngẫu nhiên.
- Chỉ log `MASTER_OPENED` khi grid mới, URL chứa `wfxcataloglist`, đã xuất hiện.

### Grid mới và dữ liệu đã ổn định

Grid hợp lệ phải đồng thời thỏa:

- thuộc frame/document mới so với snapshot trước khi click Catalog;
- URL chứa `wfxcataloglist`;
- có `.ag-root-wrapper`;
- không còn loading overlay hiển thị;
- có ít nhất một row dữ liệu thật, **hoặc** no-rows overlay đang hiển thị ổn định.

Không dùng tổng số node trong DOM làm số kết quả. AG Grid giữ virtual buffer, pinned
column và có thể clone row. Chỉ lấy row cắt với viewport hiện tại rồi deduplicate theo
Code không phân biệt hoa/thường.

### Floating Filter

- Tìm Code Filter bên trong chính `.ag-root-wrapper` đã xác nhận, không quét toàn bộ
  mọi frame rồi lấy input có score cao nhất.
- Nếu Code Filter chưa visible, click `#showfloatingfilter` trong cùng grid frame.
- Sau click, resolve lại grid/frame vì Angular có thể thay document.
- Xác nhận `Code Filter Input` visible, enabled và thuộc grid mới.
- Không log thành công nếu `rawRows=0` mà cũng không có no-rows overlay.

### Lọc

- Xóa cả Code Filter và Buyer Reference Filter bằng thao tác tương đương
  Playwright `locator.fill("")`.
- Điền query bằng thao tác tương đương `locator.fill(query)`, không chỉ gán `.value`.
- Xác nhận `input.value === query`.
- Chờ debounce và chờ loading kết thúc.
- Với Code: mọi Code đang render phải chứa query.
- Với Buyer Reference: mọi Buyer Reference đang render phải chứa query.
- Đếm `unique Code`, không đếm DOM button.
- `0`: không click.
- `1`: resolve lại button của đúng Code ngay trước click rồi mới click.
- `>=2`: giữ grid mở để người dùng chọn.

## Python tham chiếu đầy đủ

Đây là mã tham chiếu độc lập cho riêng pipeline Catalog. Nó dùng Chrome CDP giống
`login.py`, không chứa mật khẩu cứng. Chrome cần được mở với
`--remote-debugging-port=9222`; nếu chưa có session thì truyền `WFX_USER_ID` và
`WFX_PASSWORD`.

```python
from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Frame,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


HOME_URL = "https://prosports.worldfashionexchange.com/wfx_Home.aspx"
CDP_URL = os.getenv("WFX_CDP_URL", "http://127.0.0.1:9222")
COMPANY_ID = os.getenv("WFX_COMPANY_ID", "psh")
CATALOG_XPATH = '//*[@id="0003_6200"]/a'
TIMEOUT_MS = 20_000


def emit(stage: str, message: str, **data: Any) -> None:
    payload = {
        "time": time.strftime("%H:%M:%S"),
        "stage": stage,
        "message": message,
    }
    if data:
        payload["data"] = data
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def result(ok: bool, code: str, message: str, **data: Any) -> dict[str, Any]:
    return {"ok": ok, "code": code, "message": message, **data}


def normalize(value: str | None) -> str:
    return " ".join((value or "").split())


def connect(playwright: Playwright) -> tuple[Browser, BrowserContext, Page]:
    browser = playwright.chromium.connect_over_cdp(CDP_URL)
    if not browser.contexts:
        raise RuntimeError("CDP_NO_CONTEXT")
    context = browser.contexts[0]
    context.set_default_timeout(TIMEOUT_MS)
    page = next(
        (p for p in context.pages if "/wfx/default.aspx" in p.url.lower()),
        None,
    )
    page = page or next(
        (p for p in context.pages if "worldfashionexchange.com" in p.url.lower()),
        None,
    )
    page = page or context.new_page()
    page.bring_to_front()
    return browser, context, page


def click(locator: Any) -> None:
    locator.wait_for(state="attached")
    try:
        locator.click(timeout=3_000)
    except PlaywrightTimeoutError:
        locator.evaluate("element => element.click()")


def session_active(page: Page) -> bool:
    try:
        return page.locator(f"xpath={CATALOG_XPATH}").count() > 0
    except PlaywrightError:
        return False


def login_if_needed(page: Page) -> None:
    if session_active(page):
        emit("SESSION", "Dùng lại phiên WFX đang đăng nhập")
        return
    user_id = os.getenv("WFX_USER_ID", "").strip()
    password = os.getenv("WFX_PASSWORD", "")
    if not user_id or not password:
        raise RuntimeError("MISSING_CREDENTIALS")
    page.goto(HOME_URL, wait_until="domcontentloaded")
    page.locator("#txtUserID").fill(user_id)
    page.locator("#txtCompany").fill(COMPANY_ID)
    click(page.locator("#btlLogin[value='Next']"))
    page.locator("#txtPassword").fill(password)
    click(page.locator("#btlLogin[value='Log In']"))
    page.locator(f"xpath={CATALOG_XPATH}").wait_for(state="attached")
    emit("SESSION", "Đăng nhập thành công")


@dataclass
class DocumentSnapshot:
    frame: Frame | None
    url: str
    marker: str


def mark_document(frame: Frame | None, prefix: str) -> DocumentSnapshot:
    marker = f"{prefix}-{time.monotonic_ns()}"
    if frame is None:
        return DocumentSnapshot(None, "", marker)
    try:
        frame.evaluate(
            "(marker) => { window.__wfxAutomationDocumentMarker = marker; }",
            marker,
        )
    except PlaywrightError:
        pass
    return DocumentSnapshot(frame, frame.url, marker)


def document_is_new(frame: Frame, old: DocumentSnapshot | None) -> bool:
    if old is None or old.frame is None:
        return True
    if frame != old.frame:
        return True
    try:
        marker = frame.evaluate("() => window.__wfxAutomationDocumentMarker || ''")
        return marker != old.marker
    except PlaywrightError:
        return True


def current_grid_frame(page: Page) -> Frame | None:
    for frame in page.frames:
        if "wfxcataloglist" not in frame.url.lower():
            continue
        try:
            if frame.locator(".ag-root-wrapper").count() > 0:
                return frame
        except PlaywrightError:
            continue
    return None


def wait_new_left(page: Page, old: DocumentSnapshot, timeout_s: float = 15) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = page.frame(name="left")
        if frame is not None:
            try:
                if (
                    document_is_new(frame, old)
                    and frame.locator("#ddlCategory").count() > 0
                ):
                    emit("LEFT_READY", "Đã nhận frame left mới", url=frame.url)
                    return frame
            except PlaywrightError:
                pass
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError("CATALOG_LEFT_NOT_FOUND")


def select_category(
    page: Page,
    frame: Frame,
    category_name: str,
    category_value: str,
) -> None:
    selector = frame.locator("#ddlCategory")
    if selector.input_value() != category_value:
        selector.dispatch_event("mousedown")
        selector.locator(f'option[value="{category_value}"]').wait_for(
            state="attached",
            timeout=5_000,
        )
        selector.select_option(value=category_value, timeout=5_000)

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        current = page.frame(name="left")
        try:
            if (
                current is not None
                and current.locator("#ddlCategory").input_value(timeout=500)
                == category_value
            ):
                emit(
                    "CATEGORY_CONFIRMED",
                    f"Đã chọn {category_name}",
                    value=category_value,
                )
                return
        except PlaywrightError:
            pass
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError("CATEGORY_NOT_CONFIRMED")


def exact_actionable_master(frame: Frame):
    # WFX hiện dùng span text Master có onclick. Chỉ fallback sang action trực tiếp
    # khác; tuyệt đối không click img collapse hoặc li/div container.
    direct = frame.locator(
        'span[onclick], a, button, [role="button"], input[type="button"]'
    ).filter(has_text=re.compile(r"^\s*Master\s*$", re.IGNORECASE))
    for index in range(direct.count()):
        node = direct.nth(index)
        try:
            text = normalize(node.inner_text(timeout=500))
            if text.casefold() == "master":
                return node
        except PlaywrightError:
            continue
    return None


def wait_new_grid(
    page: Page,
    old_grid: DocumentSnapshot,
    timeout_s: float,
) -> Frame | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            if "wfxcataloglist" not in frame.url.lower():
                continue
            try:
                if (
                    document_is_new(frame, old_grid)
                    and frame.locator(".ag-root-wrapper").count() > 0
                ):
                    return frame
            except PlaywrightError:
                continue
        page.wait_for_timeout(200)
    return None


def click_master_until_grid(
    page: Page,
    old_grid: DocumentSnapshot,
    timeout_s: float = 50,
) -> Frame:
    deadline = time.monotonic() + timeout_s
    attempt = 0
    last_left_marker = ""

    while time.monotonic() < deadline:
        frame = page.frame(name="left")
        if frame is None:
            page.wait_for_timeout(200)
            continue
        try:
            if frame.locator("#ddlCategory").count() == 0:
                page.wait_for_timeout(200)
                continue
            marker = frame.evaluate(
                """() => {
                    if (!window.__wfxMasterAttemptMarker) {
                        window.__wfxMasterAttemptMarker =
                            'left-' + Date.now() + '-' + Math.random();
                    }
                    return window.__wfxMasterAttemptMarker;
                }"""
            )
            if marker != last_left_marker:
                last_left_marker = marker
                emit("MASTER_FRAME", "Đã resolve document left", url=frame.url)

            master = exact_actionable_master(frame)
            if master is None:
                page.wait_for_timeout(250)
                continue

            attempt += 1
            emit(
                "MASTER_CLICK",
                "Click exact actionable Master",
                attempt=attempt,
                tag=master.evaluate("e => e.tagName"),
                onclick=bool(master.get_attribute("onclick")),
                left_marker=marker,
            )
            master.evaluate("element => element.click()")

            # Click đầu có thể chỉ reload left. Khi đó vòng sau sẽ resolve document
            # mới và click lại đúng Master. Không thử IMG/LI.
            grid = wait_new_grid(
                page,
                old_grid,
                timeout_s=min(4.5, max(0.2, deadline - time.monotonic())),
            )
            if grid is not None:
                emit(
                    "MASTER_OPENED",
                    "Master đã tạo Catalog Grid mới",
                    attempt=attempt,
                    grid_url=grid.url,
                )
                return grid
        except PlaywrightError as exc:
            emit("MASTER_RETRY", "Frame/node đổi trong lúc click", error=str(exc))
        page.wait_for_timeout(250)

    raise PlaywrightTimeoutError("MASTER_CLICK_NO_NAVIGATION")


def visible(locator: Any) -> bool:
    try:
        return locator.count() > 0 and locator.first.is_visible()
    except PlaywrightError:
        return False


def grid_state(grid: Frame) -> dict[str, Any]:
    return grid.locator(".ag-root-wrapper").first.evaluate(
        """root => {
            const shown = element => {
                if (!element || !element.isConnected) return false;
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    Number(style.opacity || 1) !== 0 &&
                    rect.width > 0 && rect.height > 0;
            };
            const loadingSelectors = [
                '.ag-overlay-loading-wrapper',
                '.ag-loading',
                '.ag-row-loading'
            ];
            const noRowSelectors = [
                '.ag-overlay-no-rows-wrapper',
                '.ag-overlay-no-rows-center'
            ];
            const loading = loadingSelectors.some(selector =>
                [...root.querySelectorAll(selector)].some(shown)
            );
            const noRows = noRowSelectors.some(selector =>
                [...root.querySelectorAll(selector)].some(shown)
            );
            const rows = [...root.querySelectorAll(
                '.ag-center-cols-container .ag-row[row-index], ' +
                '.ag-center-cols-container [role="row"][row-index]'
            )].filter(row => {
                if (!shown(row)) return false;
                if (row.classList.contains('ag-row-loading') ||
                    row.classList.contains('ag-row-ghost') ||
                    row.getAttribute('aria-hidden') === 'true') return false;
                const viewport = row.closest(
                    '.ag-center-cols-viewport, .ag-body-viewport'
                );
                if (!viewport) return true;
                const r = row.getBoundingClientRect();
                const v = viewport.getBoundingClientRect();
                return r.bottom > v.top + 0.5 && r.top < v.bottom - 0.5;
            });
            return {loading, noRows, renderedRows: rows.length};
        }"""
    )


def wait_grid_settled(grid: Frame, timeout_s: float = 35) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    stable_key = None
    stable_since = 0.0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last = grid_state(grid)
            ready = (
                not last["loading"]
                and (last["renderedRows"] > 0 or last["noRows"])
            )
            key = (
                last["loading"],
                last["noRows"],
                last["renderedRows"],
            )
            if ready and key == stable_key:
                if time.monotonic() - stable_since >= 0.7:
                    emit("GRID_SETTLED", "Grid đã ổn định", **last)
                    return last
            else:
                stable_key = key
                stable_since = time.monotonic()
        except PlaywrightError:
            pass
        grid.wait_for_timeout(200)
    emit("GRID_TIMEOUT", "Grid chưa ổn định", **last)
    raise PlaywrightTimeoutError("CATALOG_DATA_NOT_READY")


def ensure_floating_filter(page: Page, grid: Frame) -> Frame:
    deadline = time.monotonic() + 25
    last_click = 0.0
    while time.monotonic() < deadline:
        try:
            code_input = grid.locator('input[aria-label="Code Filter Input"]')
            if visible(code_input) and code_input.first.is_enabled():
                emit("FILTER_VISIBLE", "Code Filter hiển thị và enabled")
                return grid

            button = grid.locator("#showfloatingfilter")
            if visible(button) and time.monotonic() - last_click >= 2:
                last_click = time.monotonic()
                emit("FILTER_CLICK", "Click Show Floating Filters")
                button.first.click(timeout=3_000)
        except PlaywrightError:
            # Angular có thể thay document sau click. Chỉ nhận lại đúng Catalog Grid.
            candidate = current_grid_frame(page)
            if candidate is not None:
                grid = candidate
        page.wait_for_timeout(200)
    raise PlaywrightTimeoutError("FLOATING_FILTER_NOT_READY")


READ_RESULTS_JS = """(root, filterKind) => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            Number(style.opacity || 1) !== 0 &&
            rect.width > 0 && rect.height > 0;
    };
    const rendered = element => {
        if (!shown(element)) return false;
        const row = element.closest('.ag-row, [role="row"]');
        if (!row || row.classList.contains('ag-row-loading') ||
            row.classList.contains('ag-row-ghost') ||
            row.getAttribute('aria-hidden') === 'true') return false;
        const viewport = row.closest(
            '.ag-center-cols-viewport, .ag-body-viewport, ' +
            '.ag-pinned-left-cols-viewport, .ag-pinned-right-cols-viewport'
        );
        if (!viewport) return true;
        const r = row.getBoundingClientRect();
        const v = viewport.getBoundingClientRect();
        return r.bottom > v.top + 0.5 && r.top < v.bottom - 0.5;
    };
    const valueColumn =
        filterKind === 'buyer_reference' ? 'lblBuyerReference' : 'lnkArticleCode';
    const valueNodes = [...root.querySelectorAll(
        `[role="gridcell"][col-id="${valueColumn}"]`
    )].filter(rendered);
    const buttonNodes = [...root.querySelectorAll(
        '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'
    )].filter(rendered);
    const values = valueNodes.map(cell => {
        if (valueColumn === 'lnkArticleCode') {
            return (cell.querySelector('input[type="button"]')?.value || '').trim();
        }
        return (cell.textContent || '').trim();
    }).filter(Boolean);
    const codes = buttonNodes.map(button => (button.value || '').trim()).filter(Boolean);
    const unique = values => [...new Map(
        values.map(value => [value.toLocaleLowerCase('vi'), value])
    ).values()];
    return {
        values: unique(values),
        codes: unique(codes),
        rawValueNodes: valueNodes.length,
        rawButtonNodes: buttonNodes.length
    };
}"""


def read_results(grid: Frame, filter_kind: str) -> dict[str, Any]:
    root = grid.locator(".ag-root-wrapper").first
    return root.evaluate(READ_RESULTS_JS, filter_kind)


def filter_catalog(
    grid: Frame,
    filter_kind: str,
    query: str,
) -> dict[str, Any]:
    definitions = {
        "code": ("Code", 'input[aria-label="Code Filter Input"]'),
        "buyer_reference": (
            "Buyer Reference",
            'input[aria-label="Buyer Reference Filter Input"]',
        ),
    }
    if filter_kind not in definitions:
        return result(False, "INVALID_FILTER", f"Filter không hỗ trợ: {filter_kind}")
    label, selector = definitions[filter_kind]

    for field_selector in (
        'input[aria-label="Code Filter Input"]',
        'input[aria-label="Buyer Reference Filter Input"]',
    ):
        field = grid.locator(field_selector)
        if visible(field):
            field.first.fill("")

    field = grid.locator(selector).first
    field.wait_for(state="visible")
    field.fill(query)
    if field.input_value() != query:
        raise RuntimeError("FILTER_VALUE_NOT_CONFIRMED")
    emit("FILTER_FILLED", f"Đã điền {label}", query=query)

    grid.wait_for_timeout(1_000)
    deadline = time.monotonic() + 25
    last: dict[str, Any] = {}
    query_folded = query.casefold()
    while time.monotonic() < deadline:
        state = grid_state(grid)
        last = read_results(grid, filter_kind)
        values = last["values"]
        applied = bool(values) and all(
            query_folded in value.casefold() for value in values
        )
        if not state["loading"] and (applied or state["noRows"]):
            break
        grid.wait_for_timeout(250)
    else:
        emit("FILTER_TIMEOUT", "Kết quả filter chưa ổn định", results=last)
        raise PlaywrightTimeoutError("FILTER_RESULTS_NOT_READY")

    codes = last["codes"]
    emit(
        "FILTER_RESULTS",
        "Đã đọc kết quả đang render",
        unique_count=len(codes),
        codes=codes,
        diagnostics=last,
    )
    if not codes:
        return result(False, "NO_RESULTS", f"Không tìm thấy {label}: {query}", codes=[])
    if len(codes) > 1:
        return result(
            True,
            "MULTIPLE_RESULTS",
            f"Có {len(codes)} kết quả; giữ grid để người dùng chọn.",
            codes=codes,
        )

    target_code = codes[0]
    buttons = grid.locator(
        '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'
    )
    for index in range(buttons.count()):
        button = buttons.nth(index)
        try:
            if (
                button.is_visible()
                and normalize(button.input_value(timeout=500)).casefold()
                == target_code.casefold()
            ):
                button.click(timeout=5_000)
                emit("ARTICLE_CLICK", "Đã click unique Code", code=target_code)
                return result(
                    True,
                    "RESULT_OPENED",
                    f"Đã mở style {target_code}.",
                    article_code=target_code,
                    codes=codes,
                )
        except PlaywrightError:
            continue
    return result(False, "RESULT_DETACHED", "Row đổi trước thời điểm click.")


def open_destination(
    context: BrowserContext,
    destination: str,
    old_states: list[tuple[Page, str, str]],
) -> str:
    label, selector = {
        "costsheet": ("Costsheet", "#CostSheet"),
        "bom": ("BOM", "#BOMMaster"),
    }[destination]
    started = time.monotonic()
    deadline = started + 40
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            top = page.frame(name="ArticleTop")
            if top is None:
                continue
            old = next((item for item in old_states if item[0] is page), None)
            changed = old is None or page.url != old[1] or top.url != old[2]
            if not changed and time.monotonic() - started < 4:
                continue
            target = top.locator(selector)
            try:
                if target.count() > 0:
                    target.wait_for(state="attached", timeout=1_000)
                    page.bring_to_front()
                    target.evaluate("element => element.click()")
                    emit("DESTINATION_OPENED", f"Đã mở {label}")
                    return label
            except PlaywrightError:
                continue
        time.sleep(0.25)
    raise PlaywrightTimeoutError("ARTICLE_DESTINATION_NOT_FOUND")


def run_catalog(
    category_name: str,
    category_value: str,
    filter_kind: str | None = None,
    query: str | None = None,
    destination: str | None = None,
) -> dict[str, Any]:
    with sync_playwright() as playwright:
        _browser, context, page = connect(playwright)
        page.on(
            "dialog",
            lambda dialog: (
                emit("DIALOG", "Tự động accept", text=dialog.message[:120]),
                dialog.accept(),
            ),
        )
        login_if_needed(page)

        old_left = mark_document(page.frame(name="left"), "old-left")
        old_grid = mark_document(current_grid_frame(page), "old-grid")
        old_article_states = [
            (p, p.url, p.frame(name="ArticleTop").url)
            for p in context.pages
            if p.frame(name="ArticleTop") is not None
        ]

        catalog = page.locator(f"xpath={CATALOG_XPATH}")
        catalog.wait_for(state="attached", timeout=8_000)
        click(catalog)
        emit("CATALOG_CLICK", "Đã click Catalog")

        left = wait_new_left(page, old_left)
        select_category(page, left, category_name, category_value)
        grid = click_master_until_grid(page, old_grid)
        wait_grid_settled(grid)
        grid = ensure_floating_filter(page, grid)

        if not query:
            return result(
                True,
                "CATALOG_PREPARED",
                "Catalog, Master, grid data và Floating Filter đã sẵn sàng.",
            )

        filtered = filter_catalog(grid, filter_kind or "code", query.strip())
        if destination and filtered.get("code") == "RESULT_OPENED":
            label = open_destination(context, destination, old_article_states)
            filtered["destination"] = destination
            filtered["message"] = (
                f"Đã mở style {filtered['article_code']} → {label}."
            )
        return filtered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category-name", default="Apparel")
    parser.add_argument("--category-value", default="01")
    parser.add_argument("--filter", choices=["code", "buyer_reference"])
    parser.add_argument("--query")
    parser.add_argument("--destination", choices=["costsheet", "bom"])
    args = parser.parse_args()
    output = run_catalog(
        category_name=args.category_name,
        category_value=args.category_value,
        filter_kind=args.filter,
        query=args.query,
        destination=args.destination,
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(0 if output["ok"] else 1)


if __name__ == "__main__":
    main()
```

Ví dụ:

```powershell
python wfx_catalog_reference.py
python wfx_catalog_reference.py --filter code --query "ABC123"
python wfx_catalog_reference.py --filter buyer_reference --query "PO-99"
python wfx_catalog_reference.py --filter code --query "ABC123" --destination bom
```

## Yêu cầu log của Chrome Extension

Mỗi run phải có `runId`. Mỗi event ghi tối thiểu:

- timestamp, version, runId, stage, elapsedMs;
- frame name và URL đã loại query nhạy cảm;
- document generation/marker;
- selector/action đã dùng;
- Master attempt và lý do retry;
- grid loading/noRows/renderedRows;
- filter visible/enabled/value;
- raw node count, rendered node count, unique Code count;
- danh sách unique Code tối đa 20 item;
- error code riêng cho từng state.

Không ghi password, cookie, SessionID, LoginID, IP hoặc toàn bộ URL có query nhạy cảm.

Các error code tối thiểu:

```text
CATALOG_MENU_NOT_FOUND
CATALOG_LEFT_NOT_FOUND
CATEGORY_OPTION_NOT_FOUND
CATEGORY_NOT_CONFIRMED
MASTER_NOT_FOUND
MASTER_CLICK_NO_NAVIGATION
CATALOG_GRID_NOT_FOUND
CATALOG_DATA_NOT_READY
FLOATING_FILTER_NOT_READY
FILTER_VALUE_NOT_CONFIRMED
FILTER_RESULTS_NOT_READY
RESULT_DETACHED
ARTICLE_OPEN_NOT_CONFIRMED
ARTICLE_DESTINATION_NOT_FOUND
```

## Hotkey Chrome Extension

Manifest không được đặt lại `"default": "Ctrl+Alt+X"` vì Chrome từ chối manifest
trên máy này. Chỉ khai báo command `toggle-panel` không có `suggested_key`.
Người dùng tự gán `Ctrl+Alt+X` tại `chrome://extensions/shortcuts`. Background service
worker phải nhận `chrome.commands.onCommand` và gửi message toggle tới tab WFX đang
active; nếu chưa có tab WFX thì mở/focus WFX trước.

## Tiêu chí nghiệm thu

1. Master có thể cần click lại sau frame reload, nhưng không click IMG/LI và không báo
   lỗi trước timeout tổng.
2. Mode prepare không báo thành công khi `rawRows=0`, trừ khi no-rows overlay thật sự
   visible và ổn định.
3. Nếu filter chưa mở, UI/log phải nói đang click `#showfloatingfilter`; chỉ báo xong
   khi input visible + enabled.
4. UI hiển thị 1 Code thì kết quả phải là 1, dù DOM giữ 32 node clone/buffer.
5. Code và Buyer Reference đều fill được và có xác nhận giá trị.
6. Một unique Code tự mở Article; nhiều Code không tự mở.
7. Costsheet/BOM chờ đúng popup `ArticleTop`.
8. `Ctrl+Alt+X` gán từ trang Chrome shortcuts hoạt động.
9. Build extension lấy từ `src`, không sửa trực tiếp chỉ mỗi file trong `dist`.
