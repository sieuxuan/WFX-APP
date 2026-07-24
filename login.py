from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import (
    Browser,
    Error as PlaywrightError,
    Frame,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.sync_api import sync_playwright


URL = "https://prosports.worldfashionexchange.com/wfx_Home.aspx"
COMPANY_ID = "psh"
CDP_HOST = os.getenv("WFX_CDP_HOST", "127.0.0.1")
CDP_PORT = int(os.getenv("WFX_CDP_PORT", "9222"))
CDP_URL = f"http://{CDP_HOST}:{CDP_PORT}"
DEFAULT_TIMEOUT_MS = 20_000
CATALOG_XPATH = '//*[@id="0003_6200"]/a'


def _write_log(log: Callable[[str], None], message: str) -> None:
    """Không để lỗi encoding của console làm hỏng thao tác browser."""
    try:
        log(message)
    except UnicodeEncodeError:
        log(message.encode("ascii", errors="backslashreplace").decode("ascii"))


def _result(
    ok: bool,
    code: str,
    message: str,
    **data: Any,
) -> dict[str, Any]:
    return {"ok": ok, "code": code, "message": message, **data}


def _find_chrome() -> Path:
    configured_path = os.getenv("WFX_CHROME_PATH")
    candidates = [
        configured_path,
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        str(Path(os.getenv("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe"),
        str(
            Path(os.getenv("PROGRAMFILES(X86)", ""))
            / "Google/Chrome/Application/chrome.exe"
        ),
        str(
            Path(os.getenv("LOCALAPPDATA", ""))
            / "Google/Chrome/Application/chrome.exe"
        ),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise FileNotFoundError(
        "Không tìm thấy Google Chrome. Hãy đặt WFX_CHROME_PATH tới chrome.exe."
    )


def _chrome_is_ready() -> bool:
    try:
        with urlopen(f"{CDP_URL}/json/version", timeout=1) as response:
            info = json.load(response)
        return bool(info.get("webSocketDebuggerUrl"))
    except (OSError, URLError, ValueError):
        return False


def _start_persistent_chrome(log: Callable[[str], None]) -> None:
    """Mở Chrome độc lập để Chrome không đóng khi app hoặc Playwright kết thúc."""
    if _chrome_is_ready():
        return

    chrome_path = _find_chrome()
    local_app_data = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    profile_dir = local_app_data / "WFX-Automation" / "ChromeProfile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    subprocess.Popen(
        [
            str(chrome_path),
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
            URL,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    _write_log(log, f"Đang mở Chrome với profile automation: {profile_dir}")

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _chrome_is_ready():
            return
        time.sleep(0.25)
    raise TimeoutError(f"Chrome không mở cổng điều khiển {CDP_URL} sau 15 giây.")


def _connect_to_chrome(playwright: Playwright) -> tuple[Browser, Page]:
    browser = playwright.chromium.connect_over_cdp(CDP_URL)
    if not browser.contexts:
        raise RuntimeError("Đã kết nối Chrome nhưng không tìm thấy browser context.")

    context = browser.contexts[0]
    context.set_default_timeout(DEFAULT_TIMEOUT_MS)
    # Luôn ưu tiên tab WFX chính, tránh bám nhầm popup Article Detail.
    page = next(
        (p for p in context.pages if "/wfx/default.aspx" in p.url.lower()),
        None,
    )
    if page is None:
        page = next(
            (p for p in context.pages if "worldfashionexchange.com" in p.url),
            None,
        )
    if page is None:
        page = next((p for p in context.pages if p.url in ("", "about:blank")), None)
    if page is None:
        page = context.new_page()
    page.bring_to_front()
    return browser, page


def _attach_dialog_handler(page: Page, log: Callable[[str], None]) -> None:
    def accept_dialog(dialog: Any) -> None:
        text = (dialog.message or "").strip().replace("\n", " ")
        _write_log(log, f"Đã chấp nhận thông báo: {text[:100]}")
        dialog.accept()

    page.on("dialog", accept_dialog)


def _click(locator: Any) -> None:
    """Click menu ASP.NET, dùng JavaScript fallback nếu menu đang bị ẩn."""
    locator.wait_for(state="attached")
    try:
        locator.click(timeout=3_000)
    except PlaywrightTimeoutError:
        locator.evaluate("element => element.click()")


def login(
    page: Page,
    user_id: str,
    password: str,
    company_id: str = COMPANY_ID,
) -> None:
    page.goto(URL, wait_until="domcontentloaded")
    page.locator("#txtUserID").fill(user_id)
    page.locator("#txtCompany").fill(company_id)
    _click(page.locator("#btlLogin[value='Next']"))

    password_input = page.locator("#txtPassword")
    password_input.wait_for(state="visible")
    password_input.fill(password)
    _click(page.locator("#btlLogin[value='Log In']"))

    # Một menu chính xuất hiện đồng nghĩa trang home đã load sau khi login.
    page.locator('xpath=//*[@id="0090_0250"]/a').wait_for(state="attached")


def _session_is_active(page: Page) -> bool:
    try:
        return page.locator('xpath=//*[@id="0003_6200"]/a').count() > 0
    except PlaywrightError:
        return False


def check_session(log: Callable[[str], None] = print) -> dict[str, Any]:
    """Kiểm tra Chrome hiện tại mà không điều hướng hoặc login lại."""
    if not _chrome_is_ready():
        return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        if _session_is_active(page):
            _write_log(log, "[SESSION] Đang sử dụng phiên WFX đã login.")
            return _result(True, "SESSION_ACTIVE", "Đã kết nối phiên WFX đang mở.")
        return _result(False, "NOT_LOGGED_IN", "Chưa có phiên WFX đăng nhập.")
    except Exception as exc:
        return _result(False, "SESSION_CHECK_FAILED", f"{type(exc).__name__}: {exc}")
    finally:
        if playwright is not None:
            playwright.stop()


def run(
    user_id: str | None = None,
    password: str | None = None,
    company_id: str = COMPANY_ID,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Chỉ đăng nhập WFX. Không tự mở module và không đóng Chrome."""
    user_id = (user_id or os.getenv("WFX_USER_ID", "")).strip()
    password = password or os.getenv("WFX_PASSWORD", "")
    playwright: Playwright | None = None
    try:
        _start_persistent_chrome(log)
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if _session_is_active(page):
            _write_log(log, "[SESSION] Phiên WFX vẫn còn hiệu lực, không login lại.")
            return _result(
                True,
                "SESSION_REUSED",
                "Đã dùng lại phiên WFX đang đăng nhập.",
                url=page.url,
            )
        if not user_id or not password:
            return _result(
                False,
                "MISSING_CREDENTIALS",
                "Chưa lưu User ID và Password trong Settings.",
            )
        login(page, user_id, password, company_id)
        _write_log(log, "Đăng nhập thành công.")
        return _result(
            True,
            "LOGGED_IN",
            "Đăng nhập thành công. Chrome vẫn đang mở.",
            url=page.url,
        )
    except PlaywrightTimeoutError:
        message = "Đăng nhập không thành công hoặc trang WFX phản hồi quá chậm."
        _write_log(log, message)
        return _result(False, "LOGIN_TIMEOUT", message)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _write_log(log, message)
        return _result(False, "LOGIN_FAILED", message)
    finally:
        # Chỉ ngắt Playwright; Chrome là tiến trình độc lập và tiếp tục chạy.
        if playwright is not None:
            playwright.stop()


def open_module(
    module_name: str,
    xpath: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Kết nối lại tab WFX đang login và mở module được yêu cầu."""
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Chrome automation chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        _write_log(log, f"[MODULE] Đang tìm menu: {module_name}")

        login_form = page.locator("#txtUserID")
        if login_form.is_visible(timeout=1_500):
            return _result(False, "NOT_LOGGED_IN", "Phiên chưa đăng nhập hoặc đã hết hạn.")

        previous_left = page.frame(name="left") if module_name == "Catalog" else None
        previous_grid = (
            next((f for f in page.frames if "wfxcataloglist" in f.url.lower()), None)
            if module_name == "Catalog"
            else None
        )
        target = page.locator(f"xpath={xpath}")
        target.wait_for(state="attached", timeout=8_000)
        _write_log(log, f"[MODULE] Đã tìm thấy {module_name}, đang click...")
        _click(target)

        if module_name == "Catalog":
            _write_log(log, "[CATALOG] Đang chờ frame left...")
            _click_catalog_master(page, log, previous_frame=previous_left)
            _show_catalog_floating_filter(page, log, previous_frame=previous_grid)
            _write_log(log, "[CATALOG] Đã mở Master và Floating Filter")
            message = "Đã mở Catalog > Master và Floating Filter."
        else:
            _write_log(log, f"[MODULE] Đã mở: {module_name}")
            message = f"Đã mở {module_name}."

        return _result(
            True,
            "MODULE_OPENED",
            message,
            module=module_name,
            url=page.url,
        )
    except PlaywrightTimeoutError as exc:
        detail = str(exc).splitlines()[0]
        message = f"Timeout khi mở {module_name}: {detail}"
        _write_log(log, message)
        return _result(False, "MODULE_NOT_FOUND", message, module=module_name)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _write_log(log, message)
        return _result(False, "MODULE_FAILED", message, module=module_name)
    finally:
        if playwright is not None:
            playwright.stop()


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
    grid.wait_for_timeout(1_000)

    value_cells = grid.locator(f'[role="gridcell"][col-id="{value_column}"]')
    code_buttons = grid.locator(
        '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'
    )
    deadline = time.monotonic() + 20
    codes: list[str] = []
    values: list[str] = []
    while time.monotonic() < deadline:
        values = []
        for index in range(value_cells.count()):
            cell = value_cells.nth(index)
            try:
                if not cell.is_visible():
                    continue
                if value_column == "lnkArticleCode":
                    item = cell.locator('input[type="button"]')
                    value = item.input_value(timeout=500).strip() if item.count() else ""
                else:
                    value = cell.inner_text(timeout=500).strip()
                if value:
                    values.append(value)
            except PlaywrightError:
                continue

        codes = []
        for index in range(code_buttons.count()):
            button = code_buttons.nth(index)
            try:
                if button.is_visible():
                    value = button.input_value(timeout=500).strip()
                    if value:
                        codes.append(value)
            except PlaywrightError:
                continue

        filter_applied = bool(values) and all(
            query.casefold() in value.casefold() for value in values
        )
        if filter_applied:
            break
        grid.wait_for_timeout(300)

    _write_log(log, f"[{label.upper()}] Giá trị khớp: {values if values else 'không có'}")
    _write_log(log, f"[{label.upper()}] Code kết quả: {codes if codes else 'không có'}")
    if not codes:
        return _result(
            False,
            "NO_RESULTS",
            f"Không tìm thấy kết quả cho {label}: {query}.",
            codes=[],
        )
    if len(codes) >= 2:
        return _result(
            True,
            "MULTIPLE_RESULTS",
            f"Có {len(codes)} kết quả; giữ danh sách để bạn tự chọn.",
            codes=codes,
            matches=values,
        )

    target_code = codes[0]
    clicked = False
    for index in range(code_buttons.count()):
        item = code_buttons.nth(index)
        try:
            if item.is_visible() and item.input_value(timeout=500).strip() == target_code:
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
        f"Đã tìm và mở style {target_code}.",
        article_code=target_code,
        codes=codes,
        matches=values,
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


if __name__ == "__main__":
    outcome = run()
    print(outcome)
    raise SystemExit(0 if outcome["ok"] else 1)
