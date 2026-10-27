"""Nhận diện frame đang phục vụ đúng module.

OC/Sample/Sale ASN và Buyer/Supplier dùng selector trùng nhau, Supplier Inv và
Expense Inv còn dùng chung cả id grid. Frame chỉ được nhận khi có đủ bộ cột
filter riêng của đúng module — nếu không, automation sẽ Search nhầm màn."""

from __future__ import annotations

from wfx_panel.automation._common import (
    Any,
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _wait,
    time,
)
from wfx_panel.automation.modules.constants import (
    _MODULE_LOADING_SELECTOR,
    MODULE_GRID_POLL_MS,
)
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


# Selector loading khá rộng nên khớp nhiều node ẩn. Hỏi is_visible từng node
# tốn một round-trip CDP mỗi node, mỗi frame, mỗi nhịp poll; một lần
# evaluate_all trả lời cả frame. Luật hiển thị bám đúng Playwright: có kích
# thước và không visibility:hidden.
_ANY_VISIBLE_JS = """elements => elements.some(element => {
    if (!element.isConnected) return false;
    if (getComputedStyle(element).visibility === 'hidden') return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
})"""


def _module_search_is_loading(page: Page) -> bool:
    for frame in page.frames:
        try:
            if frame.locator(_MODULE_LOADING_SELECTOR).evaluate_all(
                _ANY_VISIBLE_JS
            ):
                return True
        except PlaywrightError:
            continue
    return False


def _wait_module_search_settled(
    page: Page,
    labels: list[str],
    timeout_s: float = 30,
) -> None:
    deadline = time.monotonic() + timeout_s
    stable_since = 0.0
    while time.monotonic() < deadline:
        if _module_search_is_loading(page):
            stable_since = 0.0
        elif stable_since <= 0:
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= 0.8:
            return
        _wait(page, 200)
    raise PlaywrightTimeoutError(
        "Kết quả search chưa ổn định cho: " + ", ".join(labels)
    )


# Chữ ký kết quả đang hiển thị của mọi AG Grid trong frame: overlay no-rows,
# số dòng và nội dung dòng đầu. Đủ để biết bảng đã đổi so với trước lúc gõ.
# Đo trên WFX: overlay no-rows bật trước, dòng cũ còn nằm trên DOM thêm gần một
# giây (hiệu ứng xóa dòng). AG Grid chỉ bật overlay khi không còn dòng dữ liệu,
# nên overlay là căn cứ; dòng đang mờ dần không được tính.
_GRID_SIGNATURE_JS = """roots => roots.map(root => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        if (getComputedStyle(element).visibility === 'hidden') return false;
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };
    if (!shown(root)) return '';
    const noRows = [...root.querySelectorAll(
        '.ag-overlay-no-rows-wrapper'
    )].some(shown);
    if (noRows) return 'empty';
    const rows = [...root.querySelectorAll(
        '.ag-center-cols-container .ag-row'
    )].filter(shown);
    const first = (rows[0]?.innerText || '').replace(/\\s+/g, ' ').slice(0, 120);
    return `rows:${rows.length}:${first}`;
}).join('|')"""


def _grid_signature(frame: Frame) -> str:
    """Chuỗi rỗng khi frame không có AG Grid hiển thị hoặc đã detach."""
    try:
        return str(
            frame.locator(".ag-root-wrapper").evaluate_all(_GRID_SIGNATURE_JS)
            or ""
        ).strip("|")
    except PlaywrightError:
        return ""


class _GridRequests:
    """Theo dõi request `GetData` mà AG Grid của đúng frame gửi đi.

    Đo trên WFX thật (Sample, Sale ASN): Floating Filter gửi `GetData` ~1 giây
    sau lượt gõ, và NGAY lúc gửi AG Grid đã xóa dòng, bật overlay no-rows. Kết
    quả thật về sau thêm 1–4,7 giây. Nhìn bảng thì "đang tải" và "rỗng thật"
    giống hệt nhau; chỉ request mới cho biết server đã trả lời chưa.

    Sự kiện chỉ được Playwright sync phát trong lúc đang chờ một lệnh (như
    `_wait`), nên không có tranh chấp thread. Page không có `on` (fake trong
    test, hoặc driver lỗi) thì `active` là False và caller dùng luật cũ.
    """

    def __init__(self, page: Page, frame: Frame) -> None:
        self._page = page
        self._frame = frame
        self.started = 0
        self.finished_at = 0.0
        self._pending: set[int] = set()
        self.active = False
        try:
            page.on("request", self._on_request)
            page.on("requestfinished", self._on_done)
            page.on("requestfailed", self._on_done)
            self.active = True
        except (AttributeError, PlaywrightError):
            self.close()

    def _owned(self, request: Any) -> bool:
        try:
            return (
                request.resource_type in {"xhr", "fetch"}
                and "getdata" in str(request.url or "").casefold()
                and request.frame == self._frame
            )
        except PlaywrightError:
            return False

    def _on_request(self, request: Any) -> None:
        if self._owned(request):
            self.started += 1
            self._pending.add(id(request))

    def _on_done(self, request: Any) -> None:
        if id(request) in self._pending:
            self._pending.discard(id(request))
            self.finished_at = time.monotonic()

    @property
    def pending(self) -> bool:
        return bool(self._pending)

    def close(self) -> None:
        for event, handler in (
            ("request", self._on_request),
            ("requestfinished", self._on_done),
            ("requestfailed", self._on_done),
        ):
            try:
                self._page.remove_listener(event, handler)
            except (AttributeError, PlaywrightError, ValueError, KeyError):
                pass
        self.active = False


def _wait_grid_reflects_search(
    page: Page,
    frame: Frame,
    before: str,
    *,
    requests: _GridRequests | None = None,
    change_timeout_s: float = 4.0,
    stable_s: float = 0.6,
    timeout_s: float = 8.0,
) -> bool:
    """Chờ AG Grid vẽ kết quả của lượt lọc vừa gõ; False nếu hết giờ khi chưa chắc.

    Có `requests` đang theo dõi thì căn cứ là request `GetData`: đã gửi và đã
    về hết, rồi bảng đứng yên `stable_s`. Không có request nào trong
    `change_timeout_s` nghĩa là WFX không lọc lại (giá trị không đổi), bảng hiện
    tại là kết quả. Request còn treo tới `timeout_s` thì trả False để caller
    không kết luận "không có dòng" từ overlay của lúc đang tải.

    Không theo dõi được request thì dùng luật chữ ký cũ: bảng đổi rồi đứng yên
    `stable_s`, hoặc không đổi sau `change_timeout_s` (chờ lâu hơn khi bảng đang
    rỗng từ lượt trước).
    """
    if not before:
        return True
    tracked = requests is not None and requests.active
    if tracked:
        timeout_s = max(timeout_s, 30.0)
    elif before == "empty" and change_timeout_s > 0:
        change_timeout_s = max(change_timeout_s, 4.5)
    started = time.monotonic()
    last = before
    last_change = started
    changed = False
    while time.monotonic() - started < timeout_s:
        current = _grid_signature(frame)
        if not current:
            return True
        now = time.monotonic()
        if current != last:
            last = current
            last_change = now
        if current != before:
            changed = True
        settled = now - last_change >= stable_s
        if tracked and requests.started:
            # Response về trước, WFX vẽ dòng sau ~0,1 giây: đứng yên tính từ
            # mốc muộn hơn trong hai mốc.
            if (
                not requests.pending
                and now - max(last_change, requests.finished_at) >= stable_s
            ):
                return True
        elif changed and settled:
            # Không theo dõi được request: bảng đổi rồi đứng yên là kết quả.
            # Có theo dõi mà chưa thấy request: chưa tin, có thể chỉ là bảng
            # tự vẽ lại; đợi tới change_timeout_s.
            if not tracked or now - started >= change_timeout_s:
                return True
        elif not changed and now - started >= change_timeout_s:
            return True
        _wait(page, MODULE_GRID_POLL_MS)
    return not (tracked and requests.pending)


# AG Grid chỉ hiện overlay no-rows khi datasource thật sự rỗng; header và ô lọc
# vẫn còn nên chỉ nhìn số dòng DOM là không đủ để kết luận. Không đòi DOM hết
# dòng: dòng cũ còn mờ dần gần một giây sau khi overlay đã bật.
_GRID_REPORTS_NO_ROWS_JS = """roots => roots.some(root => {
    const shown = element => {
        if (!element || !element.isConnected) return false;
        if (getComputedStyle(element).visibility === 'hidden') return false;
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };
    if (!shown(root)) return false;
    return [...root.querySelectorAll(
        '.ag-overlay-no-rows-wrapper, .ag-overlay-no-rows-center'
    )].some(shown);
})"""


def _grid_reports_no_rows(page: Page, frame: Frame) -> bool:
    """True khi AG Grid của chính frame List báo rỗng, đọc hai lần cách nhau.

    Lần đọc thứ hai chặn overlay no-rows còn sót của lượt trước, khi WFX chưa
    kịp vẽ dòng mới. Màn không dùng AG Grid luôn trả False: không đoán số dòng
    của bảng ASP.NET cổ điển.
    """
    for attempt in range(2):
        try:
            if not frame.locator(".ag-root-wrapper").evaluate_all(
                _GRID_REPORTS_NO_ROWS_JS
            ):
                return False
        except PlaywrightError:
            return False
        if attempt == 0:
            _wait(page, 400)
    return True
