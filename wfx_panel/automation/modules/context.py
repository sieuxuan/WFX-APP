"""Nhận diện frame đang phục vụ đúng module.

OC/Sample/Sale ASN và Buyer/Supplier dùng selector trùng nhau, Supplier Inv và
Expense Inv còn dùng chung cả id grid. Frame chỉ được nhận khi có đủ bộ cột
filter riêng của đúng module — nếu không, automation sẽ Search nhầm màn."""

from __future__ import annotations

from wfx_panel.automation._common import (
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _wait,
    time,
)
from wfx_panel.automation.modules.constants import _MODULE_LOADING_SELECTOR
from wfx_panel.automation.modules.text import _normalise_search_text
from wfx_panel.automation.search_specs import ModuleSearchSpec

_FRAME_MARKER_JS = """() => [
    location.href,
    document.title,
    document.querySelector(
        'h1, h2, .page-title, .clsPageTitle, td.clsPageTitle'
    )?.textContent || ''
].join(' ')"""


def _frame_context_marker(frame: Frame) -> str:
    try:
        return str(frame.evaluate(_FRAME_MARKER_JS) or "").casefold()
    except PlaywrightError:
        return ""


def _frame_has_every_search_field(
    frame: Frame,
    search_spec: ModuleSearchSpec,
) -> bool:
    """Bộ cột filter riêng là cách phân biệt hai màn dùng chung id DOM.

    Supplier Inv List và Expense Inv List cùng dùng #titlebarAPInvoiceList và
    #gridAPInvoiceList, nên context selector một mình sẽ nhận nhầm màn đang mở.
    """
    for field_spec in search_spec.fields.values():
        try:
            candidates = frame.locator(", ".join(field_spec.selectors))
            if not candidates.count() or not candidates.first.is_visible():
                return False
        except PlaywrightError:
            return False
    return True


def _frame_serves_search_spec(
    frame: Frame,
    search_spec: ModuleSearchSpec | None,
) -> bool:
    if search_spec is None:
        return True
    if search_spec.foreign_markers:
        marker = _frame_context_marker(frame)
        if any(token in marker for token in search_spec.foreign_markers):
            return False
    return _frame_has_every_search_field(frame, search_spec)


def _frame_with_visible_context(
    page: Page,
    context_selector: str,
    module_name: str | None = None,
    timeout_s: float = 4,
    search_spec: ModuleSearchSpec | None = None,
) -> Frame:
    """Chỉ nhận frame có marker riêng của đúng màn List đang mở."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                context = frame.locator(context_selector)
                if (
                    context.count()
                    and context.first.is_visible()
                    and _frame_matches_module_context(frame, module_name)
                    and _frame_serves_search_spec(frame, search_spec)
                ):
                    return frame
            except PlaywrightError:
                continue
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        f"Không tìm thấy context List: {context_selector}"
    )


def _frame_matches_module_context(
    frame: Frame,
    module_name: str | None,
) -> bool:
    """Phân biệt các màn dùng chung toàn bộ selector, nhất là hai Indent List."""
    if module_name == "Sale ASN":
        # Invoice input xuất hiện ở nhiều module WFX. Chỉ URL Sale ASN chưa đủ
        # vì form New cũng dùng cùng họ URL; List phải có AG Grid đang hiển thị.
        try:
            if "salesasn" not in str(frame.url or "").casefold():
                return False
            roots = frame.locator(".ag-root-wrapper")
            return any(
                roots.nth(index).is_visible()
                for index in range(roots.count())
            )
        except PlaywrightError:
            return False
    if module_name not in {"Indent List", "User Indent"}:
        return True
    try:
        titles = frame.locator("title")
        title = (
            _normalise_search_text(titles.first.text_content(timeout=500))
            if titles.count()
            else ""
        )
    except PlaywrightError:
        return False
    if module_name == "User Indent":
        return "user indent" in title
    return "indent list" in title and "user indent" not in title


def _wait_module_search_settled(
    page: Page,
    labels: list[str],
) -> None:
    deadline = time.monotonic() + 30
    stable_since = 0.0
    while time.monotonic() < deadline:
        loading = False
        for frame in page.frames:
            try:
                overlays = frame.locator(_MODULE_LOADING_SELECTOR)
                if any(
                    overlays.nth(index).is_visible()
                    for index in range(overlays.count())
                ):
                    loading = True
                    break
            except PlaywrightError:
                continue
        if loading:
            stable_since = 0.0
        elif stable_since <= 0:
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= 0.8:
            return
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        "Kết quả search chưa ổn định cho: " + ", ".join(labels)
    )
