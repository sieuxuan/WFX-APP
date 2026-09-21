"""Xác định page/frame Costing đang hoạt động và đọc định danh Style.

WFX có thể mở nhiều tab/popup Costing; module này chọn đúng target hoạt động
gần nhất thay vì thứ tự tạo trong ``context.pages``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _sleep,
    time,
)
from wfx_panel.automation.costing.constants import (
    _ARTICLE_LEFT_STYLE_RE,
    _ARTICLE_NAME_CODE_RE,
    _ARTICLE_NAME_VALUE_RE,
    _COSTING_NO_OPEN_RE,
    _COSTING_STATUS_RE,
    _STYLE_CODE_CONTROL_SELECTORS,
    _STYLE_CODE_RE,
    COSTING_DETAIL_SELECTOR,
    COSTING_GRID_SELECTOR,
    COSTING_NEW_SELECTOR,
    COSTING_TREE_SELECTOR,
)


def _status_from_tree(frame: Frame) -> str:
    texts: list[str] = []
    for selector in (
        COSTING_TREE_SELECTOR,
        "#titlebarCostSheet .clsPageTitleBarTitle",
    ):
        locator = frame.locator(selector)
        try:
            for index in range(locator.count()):
                item = locator.nth(index) if hasattr(locator, "nth") else locator
                text = item.inner_text(timeout=1_000).strip()
                if text:
                    texts.append(text)
        except PlaywrightError:
            continue
        text = " ".join(texts)
        no_open = _COSTING_NO_OPEN_RE.search(text)
        if no_open:
            return no_open.group(1).title()
        match = _COSTING_STATUS_RE.search(text)
        if match:
            return match.group(1).title()
    return ""


def _costing_frame(
    context: Any,
    timeout_seconds: float = 20,
    *,
    pages: Sequence[Page] | None = None,
) -> tuple[Page, Frame]:
    deadline = time.monotonic() + timeout_seconds
    fixed_pages = list(pages) if pages is not None else None
    while time.monotonic() < deadline:
        candidates: list[tuple[int, Page, Frame]] = []
        source_pages = fixed_pages if fixed_pages is not None else list(context.pages)
        for page in reversed(source_pages):
            for frame in page.frames:
                try:
                    grid_score = 0
                    grids = frame.locator(COSTING_GRID_SELECTOR)
                    for index in range(grids.count()):
                        if grids.nth(index).is_visible():
                            grid_score = 100
                            break
                    detail_score = 0
                    details = frame.locator(COSTING_DETAIL_SELECTOR)
                    for index in range(details.count()):
                        if details.nth(index).is_visible():
                            detail_score = 20
                            break
                    tree_score = (
                        10 if frame.locator(COSTING_TREE_SELECTOR).count() else 0
                    )
                    new_score = 5 if frame.locator(COSTING_NEW_SELECTOR).count() else 0
                    score = grid_score + detail_score + tree_score + new_score
                    if score:
                        candidates.append((score, page, frame))
                except PlaywrightError:
                    continue
        if candidates:
            _score, page, frame = max(candidates, key=lambda candidate: candidate[0])
            return page, frame
        _sleep(0.2)
    raise PlaywrightTimeoutError("COSTING_CONTEXT_NOT_FOUND")


def _selected_costing_title(
    context: Any,
    *,
    pages: Sequence[Page] | None = None,
) -> str:
    """Đọc title node đang chọn trong Cost Sheet tree, không click."""
    matches: list[str] = []
    source_pages = list(pages) if pages is not None else list(context.pages)
    for page in reversed(source_pages):
        for frame in page.frames:
            try:
                selected = frame.locator("#treeCostSheet .clsTreeSelectedNode")
                for index in range(selected.count()):
                    text = (selected.nth(index).inner_text() or "").strip()
                    if text:
                        matches.append(text)
            except PlaywrightError:
                continue
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else ""


def _page_activity(page: Page) -> tuple[bool, bool]:
    """Trả ``(visible, focused)`` mà không activate hoặc đổi tab."""
    try:
        state = page.evaluate(
            """() => ({
                visible: document.visibilityState === 'visible',
                focused: document.hasFocus()
            })"""
        )
    except PlaywrightError:
        return False, False
    return bool(state.get("visible")), bool(state.get("focused"))


def _page_has_costing_context(page: Page) -> bool:
    """Nhận diện Costing chỉ trong một Page, không thao tác lên DOM."""
    for frame in page.frames:
        try:
            if (
                frame.locator(COSTING_GRID_SELECTOR).count()
                or frame.locator(COSTING_DETAIL_SELECTOR).count()
                or frame.locator(COSTING_TREE_SELECTOR).count()
            ):
                return True
        except PlaywrightError:
            continue
    return False


def _active_costing_page(context: Any) -> Page:
    """Chọn duy nhất tab Costing đang hiển thị; tuyệt đối không focus tab."""
    candidates: list[tuple[Page, bool]] = []
    for page in list(context.pages):
        visible, focused = _page_activity(page)
        if visible and _page_has_costing_context(page):
            candidates.append((page, focused))
    focused = [page for page, has_focus in candidates if has_focus]
    if len(focused) == 1:
        return focused[0]
    if len(candidates) == 1:
        return candidates[0][0]
    if len(candidates) > 1:
        # document.hasFocus()/visibilityState không đáng tin với popup WFX:
        # Chrome có thể báo mọi popup trong cùng cửa sổ đều visible + focused.
        # Target.getTargets được Chrome trả theo thứ tự tab hoạt động gần nhất,
        # khác với context.pages vốn giữ thứ tự tạo tab và dễ chọn nhầm tab cũ.
        # Chỉ đọc metadata CDP; không activate target hoặc bring_to_front.
        pages = [page for page, _focused in candidates]
        try:
            target_ids: dict[int, str] = {}
            target_order: dict[str, int] = {}
            for page in pages:
                session = context.new_cdp_session(page)
                try:
                    info = session.send("Target.getTargetInfo")
                    target_id = str(info.get("targetInfo", {}).get("targetId") or "")
                    if target_id:
                        target_ids[id(page)] = target_id
                    if not target_order:
                        targets = session.send("Target.getTargets")
                        target_order = {
                            str(item.get("targetId") or ""): index
                            for index, item in enumerate(
                                targets.get("targetInfos") or ()
                            )
                            if item.get("type") == "page"
                        }
                finally:
                    session.detach()
            ranked = [
                (target_order[target_ids[id(page)]], page)
                for page in pages
                if target_ids.get(id(page)) in target_order
            ]
            if ranked:
                ranked.sort(key=lambda item: item[0])
                if len(ranked) == 1 or ranked[0][0] != ranked[1][0]:
                    return ranked[0][1]
        except (AttributeError, KeyError, PlaywrightError):
            pass
        raise PlaywrightTimeoutError("COSTING_ACTIVE_TAB_AMBIGUOUS")
    raise PlaywrightTimeoutError("COSTING_ACTIVE_TAB_NOT_FOUND")


def _style_codes_from_text(value: Any) -> list[str]:
    return [
        match.group(1).upper() for match in _STYLE_CODE_RE.finditer(str(value or ""))
    ]


def _article_code_from_page(page: Page) -> str:
    """Đọc Style Code từ chính tab Article; không quét các tab khác."""
    # Đây là nguồn chính xác nhất. URL của WFX có GUID chứa các đoạn giống
    # Style Code (ví dụ BCA4-D53A...), nên không được ưu tiên URL trước header.
    for frame in getattr(page, "frames", ()) or ():
        try:
            controls = frame.locator("#lblArticleNameValue")
            for index in range(controls.count()):
                control = controls.nth(index)
                text = str(
                    control.get_attribute("title")
                    or control.inner_text(timeout=1_000)
                    or ""
                ).strip()
                match = _ARTICLE_NAME_CODE_RE.search(text)
                codes = _style_codes_from_text(match.group(1) if match else "")
                if len(codes) == 1:
                    return codes[0]
        except (AssertionError, PlaywrightError):
            continue

    trusted: list[str] = []
    try:
        trusted.extend(_style_codes_from_text(page.url))
        trusted.extend(_style_codes_from_text(page.title()))
    except PlaywrightError:
        pass
    for frame in page.frames:
        try:
            trusted.extend(_style_codes_from_text(frame.url))
        except PlaywrightError:
            continue
    unique_trusted = list(dict.fromkeys(trusted))
    if len(unique_trusted) == 1:
        return unique_trusted[0]

    # ArticleLeft là cây điều hướng riêng của đúng popup Article hiện tại. WFX
    # đặt Style Code trong header dạng "(SKN0000188/Tên style)", kể cả khi
    # page.title() và URL chỉ chứa ID nội bộ.
    for frame in page.frames:
        try:
            frame_name = str(getattr(frame, "name", "") or "").casefold()
            frame_url = str(getattr(frame, "url", "") or "").casefold()
            if "articleleft" not in frame_name and "articleleft" not in frame_url:
                continue
            body_text = frame.locator("body").inner_text(timeout=1_500)
        except (AttributeError, PlaywrightError):
            continue
        header_match = _ARTICLE_LEFT_STYLE_RE.search(str(body_text or ""))
        if header_match:
            return header_match.group(1).upper()
        left_codes = list(dict.fromkeys(_style_codes_from_text(body_text)))
        if len(left_codes) == 1:
            return left_codes[0]

    controls: list[str] = []
    selector = ",".join(_STYLE_CODE_CONTROL_SELECTORS)
    for frame in page.frames:
        try:
            values = frame.locator(selector).evaluate_all(
                """elements => elements.map(element => {
                    if (element.closest(
                        '#sectionCostSheetDetail,#sectionArticleList,#gridArticleList'
                    )) return '';
                    return String(
                        element.value || element.title || element.textContent || ''
                    ).trim();
                }).filter(Boolean)"""
            )
        except PlaywrightError:
            continue
        for value in values:
            controls.extend(_style_codes_from_text(value))
    unique_controls = list(dict.fromkeys(controls))
    if len(unique_controls) == 1:
        return unique_controls[0]

    # Fallback cuối: nút Style vừa mở trong Catalog của chính popup này.
    # Không dùng làm nguồn chính vì activeElement ở opener có thể đổi sau đó.
    try:
        opener_value = page.evaluate(
            """() => {
                try {
                    const opener = window.opener;
                    if (!opener || opener.closed) return '';
                    const element = opener.document.activeElement;
                    return String(
                        element?.value || element?.title ||
                        element?.textContent || ''
                    ).trim();
                } catch (_) {
                    return '';
                }
            }"""
        )
    except PlaywrightError:
        opener_value = ""
    opener_codes = list(dict.fromkeys(_style_codes_from_text(opener_value)))
    return opener_codes[0] if len(opener_codes) == 1 else ""


def _style_name_from_page(page: Page) -> str:
    """Lấy tên Style chuẩn sau dấu / trong ``#lblArticleNameValue``."""
    for frame in getattr(page, "frames", ()) or ():
        try:
            controls = frame.locator("#lblArticleNameValue")
            for index in range(controls.count()):
                control = controls.nth(index)
                text = str(
                    control.get_attribute("title")
                    or control.inner_text(timeout=1_000)
                    or ""
                ).strip()
                match = _ARTICLE_NAME_VALUE_RE.search(text)
                if match and match.group(1).strip():
                    return match.group(1).strip()
        except PlaywrightError:
            continue
    return ""
