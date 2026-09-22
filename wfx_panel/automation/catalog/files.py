"""Quét bốn tab file đính kèm của Article."""

from __future__ import annotations

import html
import re
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from wfx_panel.automation._common import (
    Any,
    Callable,
    Frame,
    Page,
    Playwright,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _document_marker,
    _first_line,
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
from wfx_panel.automation.catalog.article import (
    _article_page_for_code,
    _refresh_article_context,
)
from wfx_panel.automation.session import _session_is_active

ARTICLE_FILE_TAB_INDEXES = (5, 6, 8, 9)


_ATTACHMENT_TABLE_SELECTOR = (
    'table[id^="gridFileUploadDownload"][id$="_tblGridContent"]'
)


_ATTACHMENT_ROWS_JS = """table => [...table.querySelectorAll(
    'tbody tr.trContent, tbody tr[rowid]'
)].map(row => {
    const text = selector => (
        row.querySelector(selector)?.getAttribute('title')
        || row.querySelector(selector)?.textContent
        || ''
    ).replace(/\\s+/g, ' ').trim();
    const view = row.querySelector(
        'td[id="ColView"] a[id="lnkView"], '
        + 'a[id="lnkView"], a[onclick*="ViewAttachmentFile"]'
    );
    return {
        row_id: row.getAttribute('rowid') || row.id || '',
        file_name: text('[id="lblUserFileName"]'),
        comments: text('[id="lblComments"]'),
        uploaded_on: text('[id="lblUploadedOn"]'),
        uploaded_by: text('[id="lblUploadedBY"]'),
        href: view?.getAttribute('href') || '',
        onclick: view?.getAttribute('onclick') || ''
    };
}).filter(row => row.file_name)"""


def _article_file_tab(
    page: Page,
    article_top: Frame,
    index: int,
    timeout_seconds: float = 5,
) -> tuple[Frame, Any, Any] | None:
    """Resolve ``li`` và control có hành động bên trong sau mỗi lần đổi frame."""
    selector = f'xpath=//*[@id="0"]/li[{index}]'
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        current_top = page.frame(name="ArticleTop")
        frames = [
            frame
            for frame in (
                current_top,
                article_top,
                *page.frames,
            )
            if frame is not None
        ]
        seen_frames: set[Any] = set()
        for frame in frames:
            if frame in seen_frames:
                continue
            seen_frames.add(frame)
            try:
                tab = frame.locator(selector)
                if tab.count() > 0:
                    tab = tab.first
                    actionable = tab.locator(
                        "a[onclick], button[onclick], a[href], "
                        "button, [role='button'], [onclick]"
                    )
                    if actionable.count() > 0:
                        return frame, tab, actionable.first
                    if tab.get_attribute("onclick"):
                        return frame, tab, tab
            except PlaywrightError:
                continue
        _wait(page, 200)
    return None


def _ensure_article_techpack(
    page: Page,
    article_top: Frame,
    log: Callable[[str], None],
    timeout_seconds: float = 15,
) -> Frame:
    """Đưa popup về Techpack trước khi đọc File, kể cả vừa mở Costing/BOM."""
    def techpack_ready() -> bool:
        left = page.frame(name="ArticleLeft")
        return bool(
            left is not None
            and "wfxarticletechpack" in str(left.url or "").casefold()
        )

    if techpack_ready():
        return article_top

    _write_log(log, "[ARTICLE FILE] Đang chuyển về Techpack...")
    target = article_top.locator("#Versions")
    target.wait_for(state="attached", timeout=3_000)
    target.evaluate("element => element.click()")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        current_top = page.frame(name="ArticleTop")
        if current_top is not None and techpack_ready():
            _write_log(log, "[ARTICLE FILE] Techpack đã sẵn sàng.")
            return current_top
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        "Không thể chuyển popup Article về Techpack để đọc File."
    )


def _mark_article_documents(page: Page) -> list[tuple[Frame, str]]:
    """Đánh dấu document hiện tại để xác nhận click tab thật sự điều hướng."""
    snapshots: list[tuple[Frame, str]] = []
    for index, frame in enumerate(page.frames):
        marker = _document_marker(f"article-file-{index}")
        try:
            frame.evaluate(
                "marker => { window.__wfxArticleFileMarker = marker; }",
                marker,
            )
            snapshots.append((frame, marker))
        except PlaywrightError:
            continue
    return snapshots


def _article_documents_changed(
    page: Page,
    snapshots: list[tuple[Frame, str]],
) -> bool:
    current_frames = set(page.frames)
    for frame, marker in snapshots:
        if frame not in current_frames:
            return True
        try:
            current = frame.evaluate(
                "() => window.__wfxArticleFileMarker || ''"
            )
            if current != marker:
                return True
        except PlaywrightError:
            return True
    return False


def _article_tab_selected(tab: Any) -> bool:
    try:
        return bool(
            tab.evaluate(
                """element => {
                    const item = element.closest('li') || element;
                    const state = [
                        item.getAttribute('aria-selected') || '',
                        item.getAttribute('aria-current') || '',
                        item.className || '',
                    ].join(' ').toLowerCase();
                    return /(^|\\s)(true|active|current|selected)(\\s|$)/
                        .test(state)
                        || /(active|current|selected)/.test(state);
                }"""
            )
        )
    except PlaywrightError:
        return False


def _visible_attachment_tables(page: Page) -> list[dict[str, Any]]:
    """Đọc các bảng file đang hiển thị trong mọi frame của popup Article."""
    payload: list[dict[str, Any]] = []
    for frame in page.frames:
        try:
            tables = frame.locator(_ATTACHMENT_TABLE_SELECTOR)
            count = tables.count()
        except PlaywrightError:
            continue
        for index in range(count):
            table = tables.nth(index)
            try:
                if not table.is_visible():
                    continue
                payload.append(
                    {
                        "table_id": table.get_attribute("id") or "",
                        "frame_url": frame.url,
                        "rows": table.evaluate(_ATTACHMENT_ROWS_JS),
                    }
                )
            except PlaywrightError:
                continue
    return payload


def _attachment_url(row: dict[str, Any]) -> str:
    """Lấy URL từ href hoặc ``ViewAttachmentFile(this, '...')``."""
    href = html.unescape(str(row.get("href") or "")).strip()
    onclick = html.unescape(str(row.get("onclick") or "")).strip()
    raw = href
    if not raw and onclick:
        match = re.search(
            r"ViewAttachmentFile\s*\(\s*this\s*,\s*(['\"])(.*?)\1",
            onclick,
            flags=re.IGNORECASE,
        )
        raw = match.group(2).strip() if match else ""
    if not raw:
        return ""
    absolute = urljoin("https://prosports.worldfashionexchange.com/", raw)
    parsed = urlsplit(absolute)
    if parsed.scheme.casefold() != "https":
        return ""
    host = (parsed.hostname or "").casefold()
    if host != "worldfashionexchange.com" and not host.endswith(
        ".worldfashionexchange.com"
    ):
        return ""
    normalized_path = quote(
        re.sub(r"/{2,}", "/", parsed.path),
        safe="/%:@-._~!$&'()*+,;=",
    )
    return urlunsplit(
        (
            "https",
            parsed.netloc,
            normalized_path,
            parsed.query,
            "",
        )
    )


def _scan_article_file_tabs(
    page: Page,
    article_top: Frame,
    log: Callable[[str], None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Click bốn mục Article đã chỉ định và gom file đính kèm đang hiển thị."""
    files: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for tab_index in ARTICLE_FILE_TAB_INDEXES:
        resolved = _article_file_tab(page, article_top, tab_index)
        if resolved is None:
            _write_log(
                log,
                f"[ARTICLE FILE] Không tìm thấy mục li[{tab_index}], bỏ qua.",
            )
            sections.append(
                {
                    "index": tab_index,
                    "name": f"Mục {tab_index}",
                    "available": False,
                    "file_count": 0,
                }
            )
            continue

        _frame, tab, action = resolved
        try:
            label = " ".join((tab.inner_text(timeout=1_000) or "").split())
        except PlaywrightError:
            label = ""
        label = label or f"Mục {tab_index}"
        before_ids = {
            str(table.get("table_id") or "")
            for table in _visible_attachment_tables(page)
        }
        document_snapshots = _mark_article_documents(page)
        _write_log(
            log,
            f"[ARTICLE FILE] Đang kiểm tra {label} (li[{tab_index}])...",
        )
        try:
            _click(action)
        except PlaywrightError:
            sections.append(
                {
                    "index": tab_index,
                    "name": label,
                    "available": False,
                    "file_count": 0,
                }
            )
            continue

        started = time.monotonic()
        deadline = started + 6
        visible_tables: list[dict[str, Any]] = []
        confirmed_at: float | None = None
        while time.monotonic() < deadline:
            visible_tables = _visible_attachment_tables(page)
            current_ids = {
                str(table.get("table_id") or "")
                for table in visible_tables
            }
            current_tab = _article_file_tab(
                page, article_top, tab_index, timeout_seconds=0.3
            )
            selected = bool(
                current_tab and _article_tab_selected(current_tab[1])
            )
            changed = _article_documents_changed(
                page, document_snapshots
            ) or current_ids != before_ids
            if confirmed_at is None and (selected or changed):
                confirmed_at = time.monotonic()
                _write_log(
                    log,
                    f"[ARTICLE FILE] Đã vào {label}.",
                )
            if (
                confirmed_at is not None
                and time.monotonic() - confirmed_at >= 0.8
            ):
                break
            _wait(page, 250)

        if confirmed_at is None:
            _write_log(
                log,
                f"[ARTICLE FILE] Click {label} nhưng WFX không xác nhận chuyển mục.",
            )
            sections.append(
                {
                    "index": tab_index,
                    "name": label,
                    "available": False,
                    "file_count": 0,
                }
            )
            continue

        section_count = 0
        for table in visible_tables:
            for raw_row in table.get("rows") or []:
                if not isinstance(raw_row, dict):
                    continue
                download_url = _attachment_url(raw_row)
                key = download_url.casefold()
                if not download_url or key in seen_urls:
                    continue
                seen_urls.add(key)
                section_count += 1
                files.append(
                    {
                        "section": label,
                        "section_index": tab_index,
                        "table_id": str(table.get("table_id") or ""),
                        "row_id": str(raw_row.get("row_id") or ""),
                        "file_name": str(raw_row.get("file_name") or "").strip(),
                        "comments": str(raw_row.get("comments") or "").strip(),
                        "uploaded_on": str(
                            raw_row.get("uploaded_on") or ""
                        ).strip(),
                        "uploaded_by": str(
                            raw_row.get("uploaded_by") or ""
                        ).strip(),
                        "download_url": download_url,
                    }
                )
        sections.append(
            {
                "index": tab_index,
                "name": label,
                "available": True,
                "file_count": section_count,
            }
        )
        _write_log(
            log,
            f"[ARTICLE FILE] {label}: {section_count} file.",
        )
    return files, sections


def scan_catalog_files(
    article_code: str,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Quét file ở các mục 5, 6, 8, 9 của popup style đang mở."""
    article_code = str(article_code or "").strip()
    if not article_code:
        return _result(
            False,
            "CATALOG_RESULT_REQUIRED",
            "Hãy tìm và mở một Style Code trước.",
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
        browser, page = _connect_to_chrome(playwright)
        _attach_dialog_handler(page, log)
        if not _session_is_active(page):
            return _result(
                False,
                "NOT_LOGGED_IN",
                "Phiên WFX đã hết hạn. Hãy đăng nhập lại.",
            )
        def _read_article_files(current_browser: Any, probe_seconds: float):
            article, article_top = _article_page_for_code(
                current_browser.contexts[0],
                article_code,
                timeout_seconds=probe_seconds,
            )
            article.bring_to_front()
            article_top = _ensure_article_techpack(article, article_top, log)
            return _scan_article_file_tabs(article, article_top, log)

        # Đọc file trên CDP hiện tại trước; chỉ khi popup không với tới được mới
        # dựng lại driver/CDP đúng một lần rồi thử lại (tránh banner + re-attach
        # mọi tab mỗi lần bấm File).
        try:
            files, sections = _read_article_files(browser, 12)
        except (PlaywrightTimeoutError, PlaywrightError):
            playwright, browser, page = _refresh_article_context(
                playwright,
                browser,
                page,
                log,
            )
            files, sections = _read_article_files(browser, 20)
        available = sum(1 for section in sections if section["available"])
        if available == 0:
            return _result(
                False,
                "CATALOG_FILE_TABS_NOT_FOUND",
                "Không tìm thấy bốn mục File trong popup style.",
                article_code=article_code,
                sections=sections,
            )
        message = (
            f"Đã tìm thấy {len(files)} file đính kèm của style {article_code}."
            if files
            else f"Style {article_code} không có file đính kèm trong bốn mục."
        )
        return _result(
            True,
            "CATALOG_FILES_SCANNED",
            message,
            article_code=article_code,
            files=files,
            file_count=len(files),
            sections=sections,
        )
    except PlaywrightTimeoutError:
        return _result(
            False,
            "CATALOG_FILES_CONTEXT_EXPIRED",
            "Style đang chọn không còn mở. Hãy bấm File để tìm lại.",
            article_code=article_code,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {_first_line(exc)}"
        _write_log(log, message)
        return _result(
            False,
            "CATALOG_FILES_SCAN_FAILED",
            message,
            article_code=article_code,
        )
    finally:
        if playwright is not None:
            playwright.stop()
