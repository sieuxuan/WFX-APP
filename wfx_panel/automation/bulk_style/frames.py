"""Mở form New Style và tìm đúng frame editor.

Không dùng ``expect_page`` chờ blocking: WFX đặt tên cửa sổ ``CatalogDetail``
nên từ dòng thứ hai trở đi ``window.open`` tái dùng cửa sổ đang mở và Chromium
không phát page event — mỗi dòng sẽ mất trọn timeout. Frame scan mới là nguồn
xác nhận và nhận được cả hai trường hợp."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from wfx_panel.automation._common import (
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _wait,
    time,
)
from wfx_panel.automation.bulk_style.constants import (
    _COPY_RESULTS_JS,
    COPY_AS_VARIANT_XPATH,
    NEW_STYLE_XPATH,
)


def _frame_with_visible_locator(
    context: Any,
    selector: str,
    timeout_s: float,
) -> tuple[Page, Frame, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    locator = frame.locator(selector)
                    for index in range(locator.count()):
                        candidate = locator.nth(index)
                        if candidate.is_visible():
                            return page, frame, candidate
                except PlaywrightError:
                    continue
        if context.pages:
            _wait(context.pages[0], 120)
    raise PlaywrightTimeoutError(f"Không tìm thấy control: {selector}")


def _article_left_frame(context: Any, timeout_s: float = 20) -> Frame:
    _page, frame, _locator = _frame_with_visible_locator(
        context,
        f"xpath={NEW_STYLE_XPATH}",
        timeout_s,
    )
    return frame


def _new_style_link(context: Any, timeout_s: float = 15) -> tuple[Page, Frame, Any]:
    """Lấy đúng toolbar New; WFX dùng cùng class cho nhiều action khác."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    links = frame.locator("a.clsNavLinkNew")
                    for index in range(links.count()):
                        candidate = links.nth(index)
                        if (
                            candidate.is_visible()
                            and candidate.inner_text().strip().casefold() == "new"
                        ):
                            return page, frame, candidate
                except PlaywrightError:
                    continue
        if context.pages:
            _wait(context.pages[0], 120)
    raise PlaywrightTimeoutError("Không tìm thấy nút New của Catalog Group.")


def _open_style_choice(context: Any, link: Any, timeout_s: float = 12) -> Frame:
    """Mở popup New rồi chờ frame chọn New/Copy, dù WFX tái dùng cửa sổ cũ.

    KHÔNG chờ blocking bằng ``expect_page``: WFX đặt tên cửa sổ ``CatalogDetail``
    nên từ dòng thứ hai trở đi ``window.open`` tái dùng đúng cửa sổ đang mở và
    Chromium không phát page event nào. Chờ cứng ở đây làm MỖI dòng mất trọn
    timeout dù popup đã sẵn sàng ngay. Frame scan vốn đã là nguồn xác nhận cuối
    cùng và tự nhận cả page mới lẫn page tái dùng, nên poll thẳng frame đích.
    """
    # WFX gắn onclick vào TD. Click chuột Playwright thường rơi vào anchor con
    # và không bubble ổn định trên trang legacy này.
    link.locator("xpath=..").evaluate("element => element.click()")
    try:
        return _article_left_frame(context, timeout_s=timeout_s)
    except PlaywrightTimeoutError:
        pass

    # Một số phiên Chrome giữ target đã đóng theo tên CatalogDetail: hàm
    # window.open của WFX không báo lỗi nhưng cũng không sinh page event. Đọc
    # URL từ chính hàm New() trong CatalogBottom để mở bằng cùng browser context.
    target_url = ""
    for page in reversed(context.pages):
        for frame in reversed(page.frames):
            try:
                relative = frame.evaluate(
                    """() => {
                        if (typeof New !== 'function') return '';
                        const source = New.toString();
                        const match = source.match(/FullScreenForChrome\\('([^']+)'/);
                        return match ? match[1] : '';
                    }"""
                )
                if relative:
                    target_url = urljoin(frame.url, str(relative))
                    break
            except PlaywrightError:
                continue
        if target_url:
            break
    if not target_url:
        raise PlaywrightTimeoutError("Không đọc được URL New của Catalog Group.")
    popup = context.new_page()
    popup.goto(target_url, wait_until="domcontentloaded", timeout=20_000)
    return _article_left_frame(context, timeout_s=20)


def _close_pages_opened_since(context: Any, known: set) -> None:
    """Đóng đúng những popup chính flow này mở ra, không đụng tab của user.

    Chỉ dùng cho lượt quét dropdown: nó để lại một form New Style đã điền dở
    (Material Type/Buyer/Division/Product Group cuối vòng lặp) mà người dùng
    không hề yêu cầu. So sánh với snapshot page trước khi mở nên nếu WFX tái
    dùng một cửa sổ đã có sẵn thì cửa sổ đó được giữ nguyên.
    """
    for page in list(context.pages):
        if page in known:
            continue
        try:
            page.close(run_before_unload=False)
        except PlaywrightError:
            # Popup đã tự đóng hoặc Chrome giữ target: không được để việc dọn
            # dẹp làm hỏng kết quả quét đã đọc xong.
            continue


def _style_editor_frame(context: Any, timeout_s: float = 35) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    title = frame.locator("#titlebarArticle")
                    material = frame.locator(
                        "#ddlMaterialType, #select2-ddlMaterialType-container"
                    )
                    if title.count() and material.count():
                        return frame
                except PlaywrightError:
                    continue
        if context.pages:
            _wait(context.pages[0], 150)
    raise PlaywrightTimeoutError("Form Article chưa sẵn sàng.")


def _copy_result_frame(context: Any, timeout_s: float = 25) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for page in reversed(context.pages):
            for frame in reversed(page.frames):
                try:
                    candidates = frame.evaluate(_COPY_RESULTS_JS)
                    if candidates:
                        return frame
                    if frame.locator(f"xpath={COPY_AS_VARIANT_XPATH}").count():
                        return frame
                except PlaywrightError:
                    continue
        if context.pages:
            _wait(context.pages[0], 150)
    raise PlaywrightTimeoutError("Kết quả tìm Style nguồn chưa sẵn sàng.")
