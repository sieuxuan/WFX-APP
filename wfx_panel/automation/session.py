"""Đăng nhập, phiên, division và điều phối run() cho automation WFX.

Tách nguyên văn từ login.py — không đổi logic.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from wfx_panel.automation._common import (
    CATALOG_XPATH,
    COMPANY_ID,
    DIVISIONS,
    URL,
    Any,
    Callable,
    Page,
    Path,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _result,
    _wait,
    _write_log,
    os,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
    _start_persistent_chrome,
)

DIVISION_CONFIRM_TIMEOUT_SECONDS = 8
DIVISION_RETRY_AFTER_SECONDS = 2.5
DIVISION_ROUTE_SETTLE_SECONDS = 0.75
LOGIN_PAGE_TIMEOUT_MS = 45_000
AUTH_SURFACE_WAIT_SECONDS = 15


def login(
    page: Page,
    user_id: str,
    password: str,
    company_id: str = COMPANY_ID,
) -> None:
    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=LOGIN_PAGE_TIMEOUT_MS,
    )
    user_input = page.locator("#txtUserID")
    user_input.wait_for(state="visible", timeout=LOGIN_PAGE_TIMEOUT_MS)
    user_input.fill(user_id)
    page.locator("#txtCompany").fill(company_id)
    _click(page.locator("#btlLogin[value='Next']"))

    password_input = page.locator("#txtPassword")
    password_input.wait_for(state="visible", timeout=LOGIN_PAGE_TIMEOUT_MS)
    password_input.fill(password)
    _click(page.locator("#btlLogin[value='Log In']"))

    # Catalog là menu phổ thông. Không dùng một menu Admin làm điều kiện login:
    # tài khoản thường có thể đăng nhập hợp lệ nhưng không có System Coding.
    page.locator(f"xpath={CATALOG_XPATH}").wait_for(
        state="attached",
        timeout=LOGIN_PAGE_TIMEOUT_MS,
    )


def _session_is_active(page: Page) -> bool:
    try:
        return page.locator('xpath=//*[@id="0003_6200"]/a').count() > 0
    except PlaywrightError:
        return False


def _wait_for_auth_surface(page: Page, timeout_s: float) -> str:
    """Wait through a cold Chrome restore for session menu or login form."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _session_is_active(page):
            return "session"
        try:
            user_input = page.locator("#txtUserID")
            if user_input.count() and user_input.first.is_visible():
                return "login"
        except PlaywrightError:
            pass
        _wait(page, 250)
    return "unknown"


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


def _division_for_base_setting_url(value: str | None) -> dict[str, str] | None:
    """Nhận diện Division từ route Base Setting bằng query exact.

    WFX điều hướng riêng frame ``body`` khi đổi Division. Trong một số lần tải
    chậm, route đã đổi và server đã nhận lựa chọn nhưng ``#CompanyName`` trên
    frame cha chưa refresh, khiến flow cũ chờ đủ 25 giây rồi báo lỗi giả.
    """
    try:
        parsed = urlparse(str(value or ""))
        if not parsed.path.casefold().endswith("/wfx_basesetting.aspx"):
            return None
        query = {
            key.casefold(): values[-1]
            for key, values in parse_qs(parsed.query).items()
            if values
        }
        if query.get("changebasesetting") != "1":
            return None
        member = query.get("membercompanycode")
        folder = query.get("folderid")
        for division in DIVISIONS.values():
            if (
                member == str(division["member_company_code"])
                and folder == str(division["folder_id"])
            ):
                return {
                    "current_division": str(division["key"]),
                    "division_label": str(division["label"]),
                    "division_name": str(division["name"]),
                }
    except (TypeError, ValueError):
        return None
    return None


def _division_route_state_for_page(page: Page) -> dict[str, str] | None:
    """Đọc route Base Setting hiện tại từ frame ``body`` của WFX."""
    for frame in page.frames:
        try:
            if str(frame.name or "").casefold() != "body":
                continue
            matched = _division_for_base_setting_url(frame.url)
            if matched:
                return matched
        except PlaywrightError:
            continue
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
        started_wait = time.monotonic()
        deadline = started_wait + DIVISION_CONFIRM_TIMEOUT_SECONDS
        retry_at = started_wait + DIVISION_RETRY_AFTER_SECONDS
        route_observed_at: float | None = None
        retried = False
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
            now = time.monotonic()
            route_state = _division_route_state_for_page(page)
            if route_state and route_state.get("current_division") == key:
                if route_observed_at is None:
                    route_observed_at = now
                elif now - route_observed_at >= DIVISION_ROUTE_SETTLE_SECONDS:
                    _write_log(
                        log,
                        f"[DIVISION] Đã xác nhận {target['label']} qua Base Setting.",
                    )
                    return _result(
                        True,
                        "DIVISION_CHANGED",
                        f"Đã chuyển sang Division {target['label']}.",
                        **route_state,
                    )
            else:
                route_observed_at = None
                if not retried and now >= retry_at:
                    _write_log(
                        log,
                        f"[DIVISION] WFX phản hồi chậm, thử lại {target['label']}...",
                    )
                    actionable.evaluate("element => element.click()")
                    retried = True
            _wait(page, 250)
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
    page: Page | None = None
    try:
        _start_persistent_chrome(log)
        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        _write_log(log, "[SESSION] Đang chờ trang WFX sẵn sàng...")
        auth_surface = _wait_for_auth_surface(
            page,
            AUTH_SURFACE_WAIT_SECONDS,
        )
        if auth_surface == "session":
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
        if auth_surface == "unknown":
            _write_log(
                log,
                "[SESSION] Trang cũ không phản hồi; đang tải lại màn đăng nhập...",
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
    except PlaywrightTimeoutError as exc:
        if page is not None and _wait_for_auth_surface(page, 10) == "session":
            _write_log(
                log,
                "[SESSION] WFX phản hồi trễ nhưng đã xác nhận đăng nhập.",
            )
            return _result(
                True,
                "LOGGED_IN_AFTER_DELAY",
                "Đăng nhập thành công sau khi WFX tải chậm.",
                url=page.url,
                **_division_state_for_page(page),
            )
        detail = str(exc).splitlines()[0][:160]
        message = (
            "Đăng nhập không thành công hoặc trang WFX phản hồi quá chậm."
            f" Chi tiết: {detail}"
        )
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
