from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
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

from wfx_panel.constants import DIVISIONS


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


def _style_status_suffix(style: dict[str, Any] | None) -> str:
    """Chuỗi ngắn để đưa Season/CostSheet lên status của panel."""
    style = style or {}
    season = str(style.get("season") or "—").strip()
    cost_status = str(style.get("internal_costsheet_status") or "—").strip()
    return f" Season: {season} · CostSheet: {cost_status}."


@dataclass(frozen=True)
class BrowserExecutable:
    name: str
    path: Path


def detect_browser() -> BrowserExecutable | None:
    """Tìm Chromium browser có hỗ trợ CDP trên Windows 10/11.

    Ưu tiên đường dẫn do người dùng cấu hình, sau đó Chrome Stable và các
    channel Chrome/Edge/Brave/Chromium thường gặp.
    """
    configured_path = os.getenv("WFX_CHROME_PATH")
    roots = [
        Path(value)
        for value in (
            os.getenv("PROGRAMFILES"),
            os.getenv("PROGRAMFILES(X86"),
            os.getenv("LOCALAPPDATA"),
        )
        if value
    ]
    candidates: list[tuple[str, str | Path | None]] = [
        ("Trình duyệt đã cấu hình", configured_path),
        ("Google Chrome", shutil.which("chrome") or shutil.which("chrome.exe")),
    ]
    relative_paths = [
        ("Google Chrome", "Google/Chrome/Application/chrome.exe"),
        ("Google Chrome Beta", "Google/Chrome Beta/Application/chrome.exe"),
        ("Google Chrome Dev", "Google/Chrome Dev/Application/chrome.exe"),
        ("Google Chrome Canary", "Google/Chrome SxS/Application/chrome.exe"),
        ("Microsoft Edge", "Microsoft/Edge/Application/msedge.exe"),
        ("Microsoft Edge Beta", "Microsoft/Edge Beta/Application/msedge.exe"),
        ("Microsoft Edge Dev", "Microsoft/Edge Dev/Application/msedge.exe"),
        ("Microsoft Edge Canary", "Microsoft/Edge SxS/Application/msedge.exe"),
        ("Brave", "BraveSoftware/Brave-Browser/Application/brave.exe"),
        ("Chromium", "Chromium/Application/chrome.exe"),
    ]
    candidates.extend(
        (name, root / relative)
        for name, relative in relative_paths
        for root in roots
    )
    seen: set[str] = set()
    for name, candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return BrowserExecutable(name=name, path=path)
    return None


def _find_chrome() -> Path:
    """Alias tương thích ngược cho caller/test cũ."""
    browser = detect_browser()
    if browser is not None:
        return browser.path
    raise FileNotFoundError(
        "Không tìm thấy Chrome, Edge, Brave hoặc Chromium. "
        "Hãy cài một trình duyệt Chromium hoặc đặt WFX_CHROME_PATH tới file .exe."
    )


def _chrome_is_ready() -> bool:
    try:
        with urlopen(f"{CDP_URL}/json/version", timeout=1) as response:
            info = json.load(response)
        return bool(info.get("webSocketDebuggerUrl"))
    except (OSError, URLError, ValueError):
        return False


def _disable_password_manager(profile_dir: Path) -> None:
    """Tắt Password Manager chỉ trong profile automation của WFX.

    Không thay đổi profile Chrome/Edge cá nhân. Chromium đọc các preference
    này trước khi tạo cửa sổ đầu tiên, vì vậy popup Save/Remember password
    không xuất hiện sau thao tác login tự động.
    """
    preferences_path = profile_dir / "Default" / "Preferences"
    preferences_path.parent.mkdir(parents=True, exist_ok=True)
    preferences: dict[str, Any] = {}
    if preferences_path.is_file():
        try:
            loaded = json.loads(preferences_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                preferences = loaded
        except (OSError, json.JSONDecodeError):
            preferences = {}

    profile = preferences.setdefault("profile", {})
    if not isinstance(profile, dict):
        profile = {}
        preferences["profile"] = profile
    profile["password_manager_enabled"] = False
    preferences["credentials_enable_service"] = False
    preferences["password_manager_leak_detection"] = False

    temporary = preferences_path.with_name(preferences_path.name + ".tmp")
    temporary.write_text(
        json.dumps(preferences, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(preferences_path)


def _start_persistent_chrome(log: Callable[[str], None]) -> None:
    """Mở Chrome độc lập để Chrome không đóng khi app hoặc Playwright kết thúc."""
    if _chrome_is_ready():
        return

    browser = detect_browser()
    if browser is None:
        raise FileNotFoundError(
            "Không tìm thấy trình duyệt Chromium tương thích. "
            "Cài Chrome/Edge/Brave/Chromium hoặc đặt WFX_CHROME_PATH."
        )
    chrome_path = browser.path
    local_app_data = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    profile_dir = local_app_data / "WFX-Automation" / "ChromeProfile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    _disable_password_manager(profile_dir)

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
            "--disable-save-password-bubble",
            "--disable-features=PasswordManagerOnboarding,PasswordManagerEnableAccountStorage,PasswordLeakDetection",
            "--start-maximized",
            URL,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    _write_log(
        log,
        f"Đang mở {browser.name} với profile automation riêng.",
    )

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _chrome_is_ready():
            return
        time.sleep(0.25)
    raise TimeoutError(f"Chrome không mở cổng điều khiển {CDP_URL} sau 15 giây.")


def start_chrome(log: Callable[[str], None] = print) -> dict[str, Any]:
    """Mở/focus Chrome automation mà không tự đăng nhập hay đổi trang WFX."""
    try:
        was_ready = _chrome_is_ready()
        browser = detect_browser()
        if not was_ready and browser is None:
            return _result(
                False,
                "BROWSER_NOT_FOUND",
                "Không tìm thấy Chrome, Edge, Brave hoặc Chromium. "
                "Cài một trình duyệt tương thích hoặc cấu hình WFX_CHROME_PATH.",
                chrome_alive=False,
                browser_available=False,
            )
        _start_persistent_chrome(log)
        return _result(
            True,
            "CHROME_ALREADY_OPEN" if was_ready else "CHROME_OPENED",
            (
                "Trình duyệt automation đã sẵn sàng."
                if was_ready
                else f"{browser.name} automation đã sẵn sàng."
            ),
            chrome_alive=True,
            browser_available=True,
            browser_name=browser.name if browser else "Chromium",
        )
    except Exception as exc:
        message = f"Không mở được Chrome: {type(exc).__name__}: {exc}"
        _write_log(log, message)
        return _result(
            False,
            "CHROME_OPEN_FAILED",
            message,
            chrome_alive=False,
        )


def browser_status() -> dict[str, Any]:
    browser = detect_browser()
    return {
        "chrome_alive": _chrome_is_ready(),
        "browser_available": browser is not None,
        "browser_name": browser.name if browser else None,
    }


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

    # Catalog là menu phổ thông. Không dùng một menu Admin làm điều kiện login:
    # tài khoản thường có thể đăng nhập hợp lệ nhưng không có System Coding.
    page.locator(f"xpath={CATALOG_XPATH}").wait_for(state="attached")


def _session_is_active(page: Page) -> bool:
    try:
        return page.locator('xpath=//*[@id="0003_6200"]/a').count() > 0
    except PlaywrightError:
        return False


def _division_for_text(value: str | None) -> dict[str, str] | None:
    normalized = " ".join(str(value or "").split()).casefold()
    if not normalized:
        return None
    for division in DIVISIONS.values():
        if str(division["name"]).casefold() in normalized:
            return {
                "current_division": str(division["key"]),
                "division_label": str(division["label"]),
                "division_name": str(division["name"]),
            }
    return None


def _division_state_for_page(page: Page) -> dict[str, str | None]:
    """Đọc Division từ CompanyName ở bất kỳ frame nào của WFX."""
    for frame in page.frames:
        try:
            company = frame.locator("#CompanyName")
            if company.count() == 0:
                continue
            value = " ".join(
                (
                    company.first.get_attribute("title")
                    or company.first.inner_text(timeout=700)
                    or ""
                ).split()
            )
            matched = _division_for_text(value)
            if matched:
                return matched
        except PlaywrightError:
            continue
    return {
        "current_division": None,
        "division_label": None,
        "division_name": None,
    }


def get_division_state(
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Đọc Division hiện tại mà không điều hướng trang WFX."""
    if not _chrome_is_ready():
        return _result(
            False,
            "CHROME_CLOSED",
            "Chrome automation chưa được mở.",
            **_division_state_for_page_placeholder(),
        )
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Chưa có phiên WFX đăng nhập.",
                **_division_state_for_page_placeholder(),
            )
        state = _division_state_for_page(page)
        _write_log(
            log,
            f"[DIVISION] Hiện tại: {state.get('division_label') or 'không xác định'}.",
        )
        return _result(
            True,
            "DIVISION_DETECTED",
            "Đã nhận diện Division hiện tại.",
            **state,
        )
    except Exception as exc:
        return _result(
            False,
            "DIVISION_DETECT_FAILED",
            f"{type(exc).__name__}: {exc}",
            **_division_state_for_page_placeholder(),
        )
    finally:
        if playwright is not None:
            playwright.stop()


def _division_state_for_page_placeholder() -> dict[str, None]:
    return {
        "current_division": None,
        "division_label": None,
        "division_name": None,
    }


def switch_division(
    division_key: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Chuyển Base Setting bằng đúng bookmark Division của WFX."""
    key = str(division_key or "").strip().casefold()
    target = DIVISIONS.get(key)
    if target is None:
        return _result(
            False,
            "DIVISION_UNKNOWN",
            f"Division không hỗ trợ: {division_key}",
            **_division_state_for_page_placeholder(),
        )
    if not _chrome_is_ready():
        return _result(
            False,
            "CHROME_CLOSED",
            "Chrome automation chưa được mở.",
            **_division_state_for_page_placeholder(),
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
                "Phiên chưa đăng nhập hoặc đã hết hạn.",
                **_division_state_for_page_placeholder(),
            )

        current = _division_state_for_page(page)
        if current.get("current_division") == key:
            return _result(
                True,
                "DIVISION_ALREADY_ACTIVE",
                f"Bạn đang ở Division {target['label']}.",
                **current,
            )

        selector = (
            'a.hasbookmark[href*="ChangeBaseSetting=1"]'
            f'[href*="MemberCompanyCode={target["member_company_code"]}"]'
            f'[href*="folderID={target["folder_id"]}"]'
        )
        actionable = None
        for frame in page.frames:
            try:
                candidate = frame.locator(selector)
                if candidate.count() > 0:
                    actionable = candidate.first
                    break
            except PlaywrightError:
                continue
        if actionable is None:
            return _result(
                False,
                "DIVISION_OPTION_NOT_FOUND",
                f"Không tìm thấy Division {target['label']} trong menu WFX.",
                **current,
            )

        _write_log(log, f"[DIVISION] Đang chuyển sang {target['label']}...")
        actionable.evaluate("element => element.click()")
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            state = _division_state_for_page(page)
            if state.get("current_division") == key:
                _write_log(log, f"[DIVISION] Đã chuyển sang {target['label']}.")
                return _result(
                    True,
                    "DIVISION_CHANGED",
                    f"Đã chuyển sang Division {target['label']}.",
                    **state,
                )
            page.wait_for_timeout(250)
        return _result(
            False,
            "DIVISION_CHANGE_NOT_CONFIRMED",
            f"WFX chưa xác nhận Division {target['label']}.",
            **_division_state_for_page(page),
        )
    except Exception as exc:
        return _result(
            False,
            "DIVISION_CHANGE_FAILED",
            f"{type(exc).__name__}: {exc}",
            **_division_state_for_page_placeholder(),
        )
    finally:
        if playwright is not None:
            playwright.stop()


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
            return _result(
                True,
                "SESSION_ACTIVE",
                "Đã kết nối phiên WFX đang mở.",
                **_division_state_for_page(page),
            )
        return _result(False, "NOT_LOGGED_IN", "Chưa có phiên WFX đăng nhập.")
    except Exception as exc:
        return _result(False, "SESSION_CHECK_FAILED", f"{type(exc).__name__}: {exc}")
    finally:
        if playwright is not None:
            playwright.stop()


def check_module_access(
    module_specs: list[dict[str, str]],
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Đọc menu WFX thực tế để xác định module nào tài khoản được cấp quyền.

    Chỉ kiểm tra anchor menu đang tồn tại trong trang home, không click và
    không làm thay đổi màn hình đang làm việc.
    """
    if not _chrome_is_ready():
        return _result(
            False,
            "CHROME_CLOSED",
            "Chrome automation chưa được mở.",
            accessible_module_ids=[],
        )
    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Chưa có phiên WFX đăng nhập.",
                accessible_module_ids=[],
            )
        accessible: list[str] = []
        for spec in module_specs:
            module_id = str(spec.get("id") or "")
            xpath = str(spec.get("xpath") or "")
            if not module_id or not xpath:
                continue
            try:
                if page.locator(f"xpath={xpath}").count() > 0:
                    accessible.append(module_id)
            except PlaywrightError:
                continue
        _write_log(
            log,
            f"[ACCESS] Đã xác minh {len(accessible)}/{len(module_specs)} module Admin.",
        )
        return _result(
            True,
            "MODULE_ACCESS_CHECKED",
            "Đã xác minh quyền module WFX.",
            accessible_module_ids=accessible,
        )
    except Exception as exc:
        return _result(
            False,
            "MODULE_ACCESS_CHECK_FAILED",
            f"{type(exc).__name__}: {exc}",
            accessible_module_ids=[],
        )
    finally:
        if playwright is not None:
            playwright.stop()


def capture_failure_screenshot(
    path: str | Path,
    log: Callable[[str], None] = print,
) -> bool:
    """Chụp tab WFX hiện tại sau lỗi; không đọc cookie/storage."""
    if not _chrome_is_ready():
        return False
    playwright: Playwright | None = None
    try:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        page.screenshot(path=str(destination), full_page=False)
        _write_log(log, "[DIAGNOSTIC] Đã lưu ảnh lỗi cục bộ.")
        return destination.is_file()
    except Exception as error:
        _write_log(
            log,
            f"[DIAGNOSTIC] Không chụp được ảnh lỗi: {type(error).__name__}",
        )
        return False
    finally:
        if playwright is not None:
            playwright.stop()


def automation_browser_pid() -> int | None:
    """PID đang listen CDP, dùng để panel bám đúng browser automation."""
    if os.name != "nt" or CDP_HOST not in {"127.0.0.1", "localhost", "::1"}:
        return None
    try:
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in completed.stdout.splitlines():
            columns = line.split()
            if len(columns) < 5 or columns[-2].upper() != "LISTENING":
                continue
            local_address = columns[1].strip("[]")
            if local_address.rsplit(":", 1)[-1] == str(CDP_PORT):
                pid = int(columns[-1])
                return pid if pid > 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


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
                **_division_state_for_page(page),
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
            **_division_state_for_page(page),
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


if __name__ == "__main__":
    outcome = run()
    print(outcome)
    raise SystemExit(0 if outcome["ok"] else 1)
