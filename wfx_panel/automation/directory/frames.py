"""Nhận diện frame của Supplier/Buyer và chờ chúng sẵn sàng.

Buyer và Supplier dùng selector trùng nhau trên WFX, nên frame chỉ được nhận
khi đúng PartyType của flow đang chạy."""

from __future__ import annotations

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _document_changed,
    _wait,
    _write_log,
    time,
)


def _supplier_category_frame(page: Page) -> Frame | None:
    """Tìm đúng frame Supplier; không nhầm #ddlCategory của Catalog."""
    for frame in page.frames:
        try:
            if frame.locator("#ddlCategory").count() == 0:
                continue
            url = str(frame.url or "").casefold()
            if "wfxpartygroup" in url and "partytype=2" in url:
                return frame
            title = str(frame.evaluate("() => document.title || ''"))
            if "supplier" in title.casefold():
                return frame
        except PlaywrightError:
            continue
    return None


def _wait_supplier_left(
    page: Page,
    snapshot: tuple[Frame | None, str],
    timeout_s: float = 15,
) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = _supplier_category_frame(page)
        if frame is not None:
            try:
                if (
                    frame.locator("#ddlCategory").count() > 0
                    and _document_changed(frame, snapshot)
                ):
                    return frame
            except PlaywrightError:
                pass
        _wait(page, 200)
    raise PlaywrightTimeoutError("Không tìm thấy frame Supplier List.")


def _select_supplier_category(
    page: Page,
    category_name: str,
    category_value: str,
    log: Callable[[str], None],
) -> bool:
    frame = _wait_supplier_left(page, (None, ""), timeout_s=8)
    field = frame.locator("#ddlCategory")
    changed = field.input_value() != category_value
    if changed:
        # WFX chỉ nạp đủ 6 option khi dropdown nhận mousedown.
        # Trước đó DOM thường chỉ có [Select] + Apparel.
        field.dispatch_event("mousedown")
        field.locator(f'option[value="{category_value}"]').wait_for(
            state="attached", timeout=5_000
        )
        _write_log(log, f"[SUPPLIER] Đang chọn Category {category_name}...")
        try:
            field.select_option(value=category_value, timeout=5_000)
        except PlaywrightError as exc:
            message = str(exc).casefold()
            if not any(
                marker in message
                for marker in (
                    "frame was detached",
                    "execution context was destroyed",
                )
            ):
                raise
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current = _supplier_category_frame(page)
        try:
            if (
                current is not None
                and current.locator("#ddlCategory").input_value(timeout=500)
                == category_value
            ):
                _write_log(log, f"[SUPPLIER] Đã chọn {category_name}.")
                return changed
        except PlaywrightError:
            pass
        _wait(page, 200)
    raise PlaywrightTimeoutError(f"WFX không xác nhận Category {category_name}.")


def _actionable_master(frame: Frame) -> Any | None:
    nodes = frame.locator(
        'span[onclick], a, button, [role="button"], input[type="button"]'
    )
    for index in range(nodes.count()):
        node = nodes.nth(index)
        try:
            text = (
                node.input_value(timeout=300)
                if node.evaluate("element => element.tagName") == "INPUT"
                else node.inner_text(timeout=300)
            )
            if " ".join((text or "").split()).casefold() == "master":
                return node
        except PlaywrightError:
            continue
    return None


def _company_frame_marker(frame: Frame) -> str:
    return str(
        frame.evaluate(
            """() => {
                const partyType = [...document.querySelectorAll(
                    'input, select'
                )].filter(element => /party.?type/i.test(
                    `${element.id} ${element.name}`
                )).map(element => element.value).join(' ');
                const heading = document.querySelector(
                    'h1, h2, .page-title, .clsPageTitle, td.clsPageTitle'
                )?.textContent || '';
                return [
                    location.href,
                    document.title,
                    partyType,
                    heading
                ].join(' ');
            }"""
        )
    ).casefold()


def _company_marker_matches(marker: str, expected_kind: str) -> bool:
    marker = str(marker or "").casefold()
    supplier = "partytype=2" in marker or "supplier" in marker
    buyer = (
        "partytype=1" in marker
        or "party type 1" in marker
        or "buyer" in marker
    )
    if expected_kind == "supplier":
        return supplier and not buyer
    if expected_kind == "buyer":
        return buyer and not supplier
    return False


def _company_search_frame(
    page: Page,
    expected_kind: str,
    timeout_s: float = 4,
) -> Frame | None:
    """Resolve Company search theo đúng PartyType; không dùng frame generic."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                if (
                    frame.locator("#txtCompanyName").count() > 0
                    and _company_marker_matches(
                        _company_frame_marker(frame),
                        expected_kind,
                    )
                ):
                    return frame
            except PlaywrightError:
                continue
        _wait(page, 200)
    return None


def _buyer_search_frame(page: Page, timeout_s: float = 4) -> Frame | None:
    """Chỉ nhận frame Buyer, không dùng nhầm Supplier cùng #txtCompanyName."""
    return _company_search_frame(page, "buyer", timeout_s)


def _supplier_company_ready(
    frame: Frame,
    category_value: str,
) -> bool:
    try:
        search = frame.locator("#txtCompanyName")
        if (
            frame.locator("#ddlCategory").input_value(timeout=500)
            != category_value
            or search.count() == 0
            or not search.first.is_visible()
            or not search.first.is_enabled()
        ):
            return False
        return not bool(
            frame.evaluate(
                """() => [...document.querySelectorAll(
                    '.loading, .loader, [aria-busy="true"]'
                )].some(element => {
                    const rect = element.getBoundingClientRect();
                    const style = getComputedStyle(element);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                })"""
            )
        )
    except PlaywrightError:
        return False
