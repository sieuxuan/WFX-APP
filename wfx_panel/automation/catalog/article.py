"""Mở và xác nhận popup Article, rồi mở Costing/BOM trong đó.

Mỗi connect_over_cdp mới re-attach mọi tab và làm Chrome nháy banner đang bị
điều khiển, nên phải probe popup trên CDP hiện tại trước khi recycle."""

from __future__ import annotations

import re

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _first_line,
    _result,
    _sleep,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
    invalidate_browser,
)
from wfx_panel.automation.runtime import recycle_playwright
from wfx_panel.automation.session import _session_is_active


def _article_page_has_code(candidate: Page, article_code: str) -> bool:
    """Xác nhận popup Article đã tải đúng code trước khi click destination."""
    expected = str(article_code or "").strip().upper()
    if not expected:
        return True
    pattern = re.compile(
        rf"(?<![A-Z0-9]){re.escape(expected)}(?![A-Z0-9])"
    )
    for frame in getattr(candidate, "frames", ()) or ():
        try:
            values = frame.locator("#lblArticleNameValue").evaluate_all(
                """elements => elements.map(element => String(
                    element.title || element.textContent || ''
                ).trim()).filter(Boolean)"""
            )
        except (AttributeError, PlaywrightError):
            continue
        if any(pattern.search(str(value).upper()) for value in values):
            return True
    return False


def _open_article_destination(
    context: Any,
    destination: str,
    previous_states: list[tuple[Page, str, str]],
    log: Callable[[str], None],
    timeout_seconds: float = 40,
    expected_article_code: str = "",
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
    focused_pages: set[int] = set()

    while time.monotonic() < deadline:
        for candidate in reversed(context.pages):
            old_state = next(
                (state for state in previous_states if state[0] is candidate),
                None,
            )
            candidate_key = id(candidate)
            # Popup Article mới chạy nền có thể chưa tạo ArticleTop cho tới khi
            # được activate. Chỉ focus Page mới sinh sau click Article Code;
            # không đụng các tab WFX khác đã có từ trước.
            if (
                previous_states
                and old_state is None
                and candidate_key not in focused_pages
            ):
                try:
                    candidate.bring_to_front()
                    focused_pages.add(candidate_key)
                    _write_log(
                        log,
                        "[ARTICLE] Đã nhận tab Article mới, đang chuyển sang tab đó...",
                    )
                except PlaywrightError:
                    continue
            article_top = candidate.frame(name="ArticleTop")
            if article_top is None:
                continue
            navigation_changed = (
                old_state is None
                or candidate.url != old_state[1]
                or article_top.url != old_state[2]
            )
            code_confirmed = bool(expected_article_code) and (
                _article_page_has_code(
                    candidate,
                    expected_article_code,
                )
            )
            if expected_article_code and not code_confirmed:
                continue
            # Nếu click lại đúng style đang mở thì URL có thể không đổi; chờ đủ
            # thời gian tối thiểu khi caller cũ chưa truyền code. Luồng Costing
            # mới xác nhận trực tiếp header Article nên không phải chờ cứng 4s.
            same_style_grace_elapsed = time.monotonic() - started >= 1.5
            if (
                not navigation_changed
                and not code_confirmed
                and not same_style_grace_elapsed
            ):
                continue
            target = article_top.locator(selector)
            try:
                if target.count() == 0:
                    continue
                target.wait_for(state="attached", timeout=1_000)
                if candidate_key not in focused_pages:
                    candidate.bring_to_front()
                    focused_pages.add(candidate_key)
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


def _article_navigation_states(
    context: Any,
) -> list[tuple[Page, str, str]]:
    """Chụp trạng thái popup trước khi click style để nhận đúng lần điều hướng."""
    states: list[tuple[Page, str, str]] = []
    for candidate in list(getattr(context, "pages", ()) or ()):
        article_top = candidate.frame(name="ArticleTop")
        states.append(
            (
                candidate,
                str(candidate.url or ""),
                str(article_top.url or "") if article_top is not None else "",
            )
        )
    return states


def _refresh_article_context(
    playwright: Playwright,
    browser: Any,
    page: Page,
    log: Callable[[str], None],
) -> tuple[Any, Any, Page]:
    """Tạo driver/CDP mới để nhận popup Article bị driver cũ bỏ lỡ.

    WFX có thể đã tạo native popup nhưng target đó chưa xuất hiện trong
    ``context.pages`` của kết nối CDP hiện tại. Vì caller chỉ gọi primitive này
    sau khi probe ArticleTop timeout, luôn recycle đúng một lần thay vì dựa vào
    chính danh sách target đang bị stale để quyết định có recycle hay không.
    """
    _write_log(
        log,
        "[ARTICLE] Đang đồng bộ popup bằng driver mới...",
    )
    invalidate_browser(browser)
    playwright = recycle_playwright(playwright)
    refreshed_browser, refreshed_page = _connect_to_chrome(
        playwright,
        bring_to_front=False,
    )
    _attach_dialog_handler(refreshed_page, log)
    return playwright, refreshed_browser, refreshed_page


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
            "Trình duyệt làm việc chưa được mở.",
        )

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        browser, page = _connect_to_chrome(
            playwright,
            bring_to_front=False,
        )
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        # Ưu tiên popup Article đang mở trên CDP hiện tại. Chỉ khi probe này
        # timeout (WFX đã detach ArticleTop khỏi driver hiện tại) mới dựng đúng
        # một driver/CDP mới. Trước đây flow luôn recycle vô điều kiện, khiến
        # Chrome nhấp banner "đang bị điều khiển" và re-attach mọi tab mỗi lần
        # bấm Costing/BOM — nguồn gốc của lag và banner nhấp nháy.
        try:
            label = _open_article_destination(
                browser.contexts[0],
                destination,
                [],
                log,
                timeout_seconds=4,
                expected_article_code=article_code,
            )
        except PlaywrightTimeoutError:
            playwright, browser, page = _refresh_article_context(
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
                # Popup Article có thể được WFX tái sử dụng rồi detach/attach
                # lại ArticleTop. Sau probe nhanh, recovery chỉ chờ đúng frame
                # và exact code thay vì giữ user ở vòng chờ cứng.
                timeout_seconds=18,
                expected_article_code=article_code,
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
        message = f"{type(exc).__name__}: {_first_line(exc)}"
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


def _article_page_for_code(
    context: Any,
    article_code: str,
    timeout_seconds: float = 20,
) -> tuple[Page, Frame]:
    """Chờ đúng popup Article của Style Code, không nhận nhầm popup cũ."""
    expected = str(article_code or "").strip()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for candidate in reversed(context.pages):
            article_top = candidate.frame(name="ArticleTop")
            if article_top is None or not _article_page_has_code(
                candidate,
                expected,
            ):
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
    raise PlaywrightTimeoutError(
        f"Không tìm thấy popup ArticleTop của style {expected}."
    )
