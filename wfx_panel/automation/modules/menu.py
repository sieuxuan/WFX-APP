"""Mở màn hình WFX từ menu — lối vào chung cho mọi flow.

Click node đầu tiên khớp selector, chờ xác nhận navigation 5 giây, rồi mở thẳng
href trong frame target nếu click im lặng. Route đã phải fallback được cache
theo xpath cho tới khi login/Division đổi."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _document_changed,
    _first_line,
    _mark_document,
    _result,
    _wait,
    _write_log,
    sync_playwright,
    time,
)
from wfx_panel.automation.browser import (
    _attach_dialog_handler,
    _chrome_is_ready,
    _connect_to_chrome,
)
from wfx_panel.automation.catalog import (
    _catalog_tree_frame_now,
    _click_catalog_master,
    _open_catalog_menu_on_page,
    _show_catalog_floating_filter,
)
from wfx_panel.automation.modules.constants import MODULE_DIRECT_ROUTE_TIMEOUT_MS

_MENU_ROUTE_CACHE: dict[str, tuple[str, str]] = {}


def reset_menu_route_cache() -> None:
    """Xóa route chỉ sống trong phiên khi login/Division thay đổi."""
    _MENU_ROUTE_CACHE.clear()


def _same_origin(page_url: str, target_url: str) -> bool:
    try:
        current = urlsplit(page_url)
        target = urlsplit(target_url)
    except ValueError:
        return False
    return bool(
        current.scheme in {"http", "https"}
        and target.scheme == current.scheme
        and target.hostname
        and target.hostname == current.hostname
        and target.port == current.port
    )


def open_module(
    module_name: str,
    xpath: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Kết nối lại tab WFX đang login và mở module được yêu cầu."""
    playwright: Playwright | None = None
    try:
        if not _chrome_is_ready():
            return _result(False, "CHROME_CLOSED", "Trình duyệt làm việc chưa được mở.")

        playwright = sync_playwright().start()
        _browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        _write_log(log, f"[MODULE] Đang tìm menu: {module_name}")

        login_form = page.locator("#txtUserID")
        if login_form.is_visible(timeout=1_500):
            return _result(False, "NOT_LOGGED_IN", "Phiên chưa đăng nhập hoặc đã hết hạn.")

        if module_name == "Catalog":
            previous_left = _catalog_tree_frame_now(page)
            previous_grid = next(
                (f for f in page.frames if "wfxcataloglist" in f.url.lower()),
                None,
            )
            target = page.locator(f"xpath={xpath}").first
            target.wait_for(state="attached", timeout=8_000)
            _write_log(log, f"[MODULE] Đã tìm thấy {module_name}, đang click...")
            _open_catalog_menu_on_page(
                page,
                target,
                log,
                previous_frame=previous_left,
            )
            _write_log(log, "[CATALOG] Đang chờ frame left...")
            _click_catalog_master(page, log, previous_frame=previous_left)
            _show_catalog_floating_filter(page, log, previous_frame=previous_grid)
            _write_log(log, "[CATALOG] Đã mở Master và Floating Filter")
            message = "Đã mở Catalog > Master và Floating Filter."
        else:
            opened = _open_module_menu(page, module_name, xpath, log)
            cache_hit = opened.cache_hit
            if not opened.confirmed:
                raise PlaywrightTimeoutError(
                    "MODULE_OPEN_NOT_CONFIRMED:"
                    f"WFX chưa xác nhận navigation tới {module_name}."
                )
            _write_log(log, f"[MODULE] Đã mở: {module_name}")
            message = f"Đã mở {module_name}."

        return _result(
            True,
            "MODULE_OPENED",
            message,
            module=module_name,
            url=page.url,
            menu_cache_hit=(cache_hit if module_name != "Catalog" else False),
        )
    except PlaywrightTimeoutError as exc:
        detail = _first_line(exc)
        code = (
            "MODULE_OPEN_NOT_CONFIRMED"
            if detail.startswith("MODULE_OPEN_NOT_CONFIRMED:")
            else "MODULE_NOT_FOUND"
        )
        detail = detail.removeprefix("MODULE_OPEN_NOT_CONFIRMED:")
        message = f"Timeout khi mở {module_name}: {detail}"
        _write_log(log, message)
        return _result(False, code, message, module=module_name)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _write_log(log, message)
        return _result(False, "MODULE_FAILED", message, module=module_name)
    finally:
        if playwright is not None:
            playwright.stop()


def _active_wfx_page(playwright: Playwright, log: Callable[[str], None]) -> tuple[Any, Page]:
    if not _chrome_is_ready():
        raise RuntimeError("CHROME_CLOSED")
    browser, page = _connect_to_chrome(playwright)
    _attach_dialog_handler(page, log)
    login_form = page.locator("#txtUserID")
    if login_form.count() and login_form.is_visible(timeout=1_500):
        raise RuntimeError("NOT_LOGGED_IN")
    return browser, page


@dataclass(frozen=True)
class _MenuOpenResult:
    confirmed: bool
    cache_hit: bool


def _context_pages(page: Page) -> list[Page]:
    try:
        return list(page.context.pages)
    except (PlaywrightError, AttributeError):
        return [page]


def _open_module_menu(
    page: Page,
    module_name: str,
    xpath: str,
    log: Callable[[str], None],
) -> _MenuOpenResult:
    """Click menu WFX rồi xác nhận navigation thật, fallback href nếu im lặng.

    Mọi lối vào List/New đều dùng chung hàm này để cùng được route cache và
    fallback `target=body`, thay vì mỗi flow tự chờ hết timeout của mình.
    """
    # .first: các menu bắt theo @title/@href có thể khớp nhiều node; strict
    # locator sẽ ném lỗi thay vì mở được màn hình.
    target = page.locator(f"xpath={xpath}").first
    target.wait_for(state="attached", timeout=8_000)
    _write_log(log, f"[MODULE] Đang mở {module_name}...")

    snapshots = _mark_page_documents(page, "module-open")
    old_frame_ids = {
        id(snapshot[0]) for snapshot in snapshots if snapshot[0] is not None
    }
    page_count = len(_context_pages(page))
    target_href = str(target.evaluate("element => element.href || ''") or "")
    target_frame_name = str(target.get_attribute("target") or "")

    cached_route = _MENU_ROUTE_CACHE.get(xpath)
    cache_hit = False
    if cached_route is not None:
        cached_href, cached_target = cached_route
        cache_hit = _open_menu_href_in_target_frame(
            page,
            cached_href,
            cached_target,
        )
        if cache_hit:
            _write_log(
                log,
                f"[MODULE] Dùng route cache để mở {module_name} trực tiếp, "
                "bỏ qua thời gian chờ menu không phản hồi.",
            )
            return _MenuOpenResult(True, True)
        _MENU_ROUTE_CACHE.pop(xpath, None)

    _click(target)
    if _wait_for_module_navigation(
        page,
        snapshots,
        old_frame_ids,
        page_count,
        timeout_s=5,
    ):
        return _MenuOpenResult(True, False)

    _write_log(
        log,
        "[MODULE] Menu chưa phản hồi sau 5 giây; đang thử route trực tiếp...",
    )
    if not _open_menu_href_in_target_frame(page, target_href, target_frame_name):
        return _MenuOpenResult(False, False)
    if _same_origin(page.url, target_href):
        _MENU_ROUTE_CACHE[xpath] = (target_href, target_frame_name)
    _write_log(
        log,
        f"[MODULE] Menu không phản hồi click; đã mở {module_name} trực tiếp "
        f"trong frame {target_frame_name}.",
    )
    return _MenuOpenResult(True, False)


def _click_module_menu_on_page(
    page: Page,
    module_name: str,
    xpath: str,
    log: Callable[[str], None],
) -> bool:
    return _open_module_menu(page, module_name, xpath, log).confirmed


def _mark_page_documents(
    page: Page,
    prefix: str,
) -> list[tuple[Frame | None, str]]:
    return [
        _mark_document(frame, f"{prefix}-{index}")
        for index, frame in enumerate(page.frames)
    ]


def _wait_for_module_navigation(
    page: Page,
    snapshots: list[tuple[Frame | None, str]],
    old_frame_ids: set[int],
    page_count: int,
    *,
    timeout_s: float = 20,
) -> bool:
    """Chỉ báo mở module khi WFX thật sự đổi page/frame/document."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if len(_context_pages(page)) > page_count:
                return True
            current_frames = list(page.frames)
            current_frame_ids = {id(frame) for frame in current_frames}
            if any(id(frame) not in old_frame_ids for frame in current_frames):
                return True
            if any(
                snapshot[0] is not None
                and id(snapshot[0]) in current_frame_ids
                and _document_changed(snapshot[0], snapshot)
                for snapshot in snapshots
            ):
                return True
        except PlaywrightError:
            # Frame detach/navigation cũng là bằng chứng WFX đã nhận click.
            return True
        _wait(page, 150)
    return False


def _open_menu_href_in_target_frame(
    page: Page,
    href: str,
    target_name: str,
) -> bool:
    """Fallback cho menu WFX có target=body nhưng click không navigation."""
    page_url = str(getattr(page, "url", "") or "")
    if (
        not href.lower().startswith(("http://", "https://"))
        or not target_name
        or (page_url and not _same_origin(page_url, href))
    ):
        return False
    target_frame = next(
        (frame for frame in page.frames if frame.name == target_name),
        None,
    )
    if target_frame is None:
        return False
    try:
        target_frame.goto(
            href,
            wait_until="domcontentloaded",
            timeout=MODULE_DIRECT_ROUTE_TIMEOUT_MS,
        )
    except PlaywrightError:
        return False
    return True


def _menu_target_markers(page: Page, xpath: str) -> tuple[str, ...]:
    """Trang đích + MenuName đọc từ chính link menu, dùng để xác nhận màn New.

    Link menu WFX có dạng wrapper `...aspx?...RedirURL=<trang đích>.aspx...`
    nên trang đích là `.aspx` cuối cùng trong href.
    """
    try:
        href = str(
            page.locator(f"xpath={xpath}").first.evaluate(
                "element => element.href || ''"
            )
            or ""
        ).casefold()
    except PlaywrightError:
        return ()
    markers: list[str] = []
    pages = re.findall(r"([a-z0-9_]+\.aspx)", href)
    if pages:
        markers.append(pages[-1])
    menu_name = re.search(r"menuname=([a-z0-9_]+)", href)
    if menu_name is not None:
        markers.append(f"menuname={menu_name.group(1)}")
    return tuple(dict.fromkeys(markers))
