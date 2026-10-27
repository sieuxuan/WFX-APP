"""Mở Catalog, nhận frame cây và chọn Category/Master.

Click Master lần đầu có thể chỉ reload frame cây. Khi đó phải lấy lại document
rồi click ĐÚNG node span[onclick] có text Master — tuyệt đối không click
icon collapse hay container li chỉ vì nó chứa chữ Master."""

from __future__ import annotations

from urllib.parse import parse_qs, urljoin, urlsplit

from wfx_panel.automation._common import (
    CATALOG_XPATH,
    Any,
    Callable,
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _document_changed,
    _mark_document,
    _wait,
    _write_log,
    time,
)

# Một lần click Master phải sinh grid mới trong khoảng này; quá hạn thì lấy lại
# cây và click lại đúng Master. Tổng ngân sách theo tiêu chí nghiệm thu 1.
_MASTER_CLICK_WAIT_S = 4.5
_MASTER_TIMEOUT_S = 50


class CatalogStepError(PlaywrightTimeoutError):
    """Timeout của một bước state machine, kèm mã nghiệp vụ riêng cho UI.

    Kế thừa ``PlaywrightTimeoutError`` để mọi ``except`` hiện có vẫn bắt được;
    entry point đọc ``code`` thay vì gom tất cả về ``CATALOG_NOT_OPEN``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _is_catalog_tree_frame(frame: Frame) -> bool:
    """Reject look-alike module trees such as Supplier's ``#ddlCategory``."""
    try:
        path = urlsplit(str(frame.url or "")).path.casefold()
        if "catalog" not in path:
            return False
        return frame.locator("#ddlCategory").count() > 0
    except PlaywrightError:
        return False


def _catalog_tree_frame_now(page: Page) -> Frame | None:
    """Find the actual Catalog tree by route and DOM, not frame name alone."""
    named_left = page.frame(name="left")
    candidates = ([named_left] if named_left is not None else []) + list(page.frames)
    seen: set[int] = set()
    for frame in candidates:
        identity = id(frame)
        if identity in seen:
            continue
        seen.add(identity)
        if _is_catalog_tree_frame(frame):
            return frame
    return None


def _catalog_left_frame(
    page: Page,
    previous_frame: Frame | None = None,
    timeout_s: float = 10,
) -> Frame:
    """Wait for a Catalog tree, including an in-place frame document reload."""
    # Playwright can preserve the Frame object when WFX replaces its document.
    # ``previous_frame`` therefore cannot be used as a freshness condition.
    _ = previous_frame
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frame = _catalog_tree_frame_now(page)
        if frame is not None:
            return frame
        _wait(page, 250)
    raise PlaywrightTimeoutError("Không tìm thấy frame left hoặc #ddlCategory của Catalog.")


def _navigate_catalog_body_direct(page: Page, direct_url: str) -> None:
    """Navigate the live body frame; assigning ``src`` alone loses stale races."""
    frame_resolver = getattr(page, "frame", None)
    body_frame = frame_resolver(name="body") if callable(frame_resolver) else None
    if body_frame is not None:
        try:
            body_frame.goto(
                direct_url,
                wait_until="domcontentloaded",
                timeout=15_000,
            )
            return
        except PlaywrightTimeoutError:
            # Navigation was dispatched; the Catalog tree waiter owns the
            # remaining cold-load budget.
            return
        except PlaywrightError:
            pass
    body_element = page.locator(
        'frame[name="body"], iframe[name="body"]'
    ).first
    body_element.wait_for(state="attached", timeout=3_000)
    body_element.evaluate("(element, url) => { element.src = url; }", direct_url)


def _catalog_direct_url(page: Page, catalog: Any) -> str | None:
    """Lấy URL Catalog đích từ RedirURL và chỉ chấp nhận cùng WFX origin."""
    try:
        href = str(catalog.get_attribute("href") or "").strip()
    except PlaywrightError:
        return None
    if not href:
        return None
    wrapper_url = urljoin(page.url, href)
    redirect_values = parse_qs(urlsplit(wrapper_url).query).get("RedirURL", [])
    if not redirect_values:
        return None
    direct_url = urljoin(wrapper_url, redirect_values[0])
    page_parts = urlsplit(page.url)
    direct_parts = urlsplit(direct_url)
    if (
        direct_parts.scheme.casefold() != page_parts.scheme.casefold()
        or direct_parts.netloc.casefold() != page_parts.netloc.casefold()
        or not direct_parts.path.casefold().endswith("/wfx_catalogmain.aspx")
    ):
        return None
    return direct_url


def _open_catalog_menu_on_page(
    page: Page,
    catalog: Any,
    log: Callable[[str], None],
    previous_frame: Frame | None = None,
) -> Frame:
    """Mở Catalog; bỏ qua BaseSetting nếu endpoint trung gian bị treo."""
    direct_url = _catalog_direct_url(page, catalog)
    _click(catalog)
    try:
        return _catalog_left_frame(
            page,
            previous_frame=previous_frame,
            timeout_s=3,
        )
    except PlaywrightTimeoutError:
        if direct_url is None:
            raise

    _write_log(
        log,
        "[CATALOG] Menu phản hồi chậm; đang mở trực tiếp trang Catalog...",
    )
    _navigate_catalog_body_direct(page, direct_url)
    return _catalog_left_frame(
        page,
        previous_frame=previous_frame,
        timeout_s=30,
    )


def _catalog_grid_document_now(page: Page) -> Frame | None:
    for frame in page.frames:
        if "wfxcataloglist" in str(frame.url or "").lower():
            return frame
    return None


def _wait_new_catalog_grid(
    page: Page,
    old_grid: tuple[Frame | None, str],
    timeout_s: float,
) -> tuple[Frame | None, bool]:
    """Chờ grid thuộc document mới so với snapshot trước click.

    Trả ``(grid, navigated)``: ``navigated`` nghĩa là document grid đã đổi nhưng
    AG Grid chưa render xong — click lại lúc này chỉ làm WFX tải lại từ đầu.
    """
    deadline = time.monotonic() + max(0.1, timeout_s)
    navigated = False
    while True:
        for frame in page.frames:
            if "wfxcataloglist" not in str(frame.url or "").lower():
                continue
            if not _document_changed(frame, old_grid):
                continue
            navigated = True
            try:
                if frame.locator(".ag-root-wrapper").count() > 0:
                    return frame, True
            except PlaywrightError:
                continue
        if time.monotonic() >= deadline:
            return None, navigated
        _wait(page, 200)


def _click_catalog_master(
    page: Page,
    log: Callable[[str], None],
    previous_frame: Frame | None = None,
    timeout_s: float = _MASTER_TIMEOUT_S,
) -> Frame:
    """Click Master tới khi WFX tạo Catalog Grid mới (``MASTER_OPENED``).

    Click đầu có thể chỉ reload frame cây; khi đó lấy lại document và click
    lại đúng Master. Không coi một cú click là thành công khi grid chưa đổi.
    """
    deadline = time.monotonic() + timeout_s
    old_grid = _mark_document(_catalog_grid_document_now(page), "old-grid")
    last_error: Exception | None = None
    old_frame = previous_frame
    attempt = 0
    while time.monotonic() < deadline:
        try:
            frame = _catalog_left_frame(
                page,
                previous_frame=old_frame,
                timeout_s=max(0.1, min(10, deadline - time.monotonic())),
            )
            master = frame.get_by_text("Master", exact=True)
            master.wait_for(state="attached", timeout=2_000)
            attempt += 1
            _write_log(log, f"[CATALOG] Đang click Master (lần {attempt})...")
            master.evaluate("element => element.click()")
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            last_error = exc
            old_frame = None
            _wait(page, 250)
            continue
        grid, navigated = _wait_new_catalog_grid(
            page,
            old_grid,
            min(_MASTER_CLICK_WAIT_S, max(0.1, deadline - time.monotonic())),
        )
        if grid is None and navigated:
            # Grid đang tải document mới: chờ nốt trong ngân sách tổng.
            grid, _ = _wait_new_catalog_grid(
                page,
                old_grid,
                deadline - time.monotonic(),
            )
        if grid is not None:
            _write_log(
                log,
                f"[CATALOG] MASTER_OPENED: Master đã tạo Catalog Grid mới (lần {attempt}).",
            )
            return grid
        _write_log(
            log,
            f"[CATALOG] Master chưa tạo grid mới sau lần {attempt}; "
            "lấy lại cây và click lại đúng Master...",
        )
    if attempt == 0:
        raise CatalogStepError(
            "MASTER_NOT_FOUND",
            f"Không click được Master: {last_error}",
        )
    raise CatalogStepError(
        "MASTER_FAILED",
        f"MASTER_CLICK_NO_NAVIGATION: đã click Master {attempt} lần "
        "nhưng WFX không tạo Catalog Grid mới.",
    )


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
    try:
        category.locator(f'option[value="{category_value}"]').wait_for(
            state="attached",
            timeout=5_000,
        )
    except PlaywrightTimeoutError as exc:
        raise CatalogStepError(
            "CATEGORY_FAILED",
            f"CATEGORY_OPTION_NOT_FOUND: WFX không có Category {category_name}.",
        ) from exc
    category.select_option(value=category_value, timeout=5_000)

    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current_frame = _catalog_tree_frame_now(page)
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
        _wait(page, 200)
    raise CatalogStepError(
        "CATEGORY_FAILED",
        f"CATEGORY_NOT_CONFIRMED: WFX không xác nhận Category {category_name}.",
    )


def _open_catalog_tree_on_page(
    page: Page,
    category_name: str,
    category_value: str,
    log: Callable[[str], None],
) -> Frame:
    """Mở cây Catalog và chọn Category, nhưng không tự click Master."""
    previous_left = _catalog_tree_frame_now(page)
    if previous_left is not None:
        _write_log(
            log,
            "[CATALOG] Cây Catalog đã mở; dùng lại context hiện tại.",
        )
        _select_catalog_category_on_page(
            page,
            category_name,
            category_value,
            log,
        )
        return _catalog_left_frame(page)
    catalog = page.locator(f"xpath={CATALOG_XPATH}")
    catalog.wait_for(state="attached", timeout=8_000)
    _write_log(log, "[CATALOG] Đang mở cây thư mục...")
    _open_catalog_menu_on_page(
        page,
        catalog,
        log,
        previous_frame=previous_left,
    )
    _select_catalog_category_on_page(
        page,
        category_name,
        category_value,
        log,
        previous_frame=previous_left,
    )
    return _catalog_left_frame(page)
