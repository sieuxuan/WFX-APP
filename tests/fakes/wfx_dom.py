"""Fake DOM WFX/AG Grid để test state machine Catalog mà không cần Chrome.

Lớp automation chỉ chạm Playwright qua một tập selector và một tập script JS
hữu hạn. Fake này mô phỏng đúng *ngữ nghĩa* mà các script đó tính ra, điều khiển
bằng một model khai báo — row nào đang render, Floating Filter đã bật chưa, cột
nào còn nằm ngoài viewport ngang — thay vì dựng DOM thật.

Nguyên tắc bắt buộc: gặp selector hoặc script chưa biết thì raise
``AssertionError``. Fake không được im lặng trả giá trị mặc định, vì như vậy
test sẽ xanh cho một nhánh chưa bao giờ chạy — đúng cái bẫy mà các test
grep-source hiện tại đang mắc.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Error as PlaywrightError

ROOT_SELECTOR = ".ag-root-wrapper"
SHOW_FILTER_SELECTOR = "#showfloatingfilter"
STYLE_BUTTON_SELECTOR = (
    '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'
)
CATEGORY_SELECTOR = "#ddlCategory"

CODE_FILTER = "Code Filter Input"
BUYER_REFERENCE_FILTER = "Buyer Reference Filter Input"
ARTICLE_NAME_FILTER = "Article Name Filter Input"


class FakeClock:
    """Đồng hồ ảo: ``_wait()`` đẩy thời gian thay vì ngủ thật.

    ``catalog.py`` đọc ``time.monotonic()`` từ namespace của chính module, nên
    monkeypatch ``catalog.time`` bằng instance này là đủ để mọi vòng chờ chạy
    tức thì mà vẫn giữ nguyên logic deadline/stability thật.
    """

    def __init__(self, start: float = 1_000.0) -> None:
        self._now = float(start)

    def monotonic(self) -> float:
        return self._now

    def time(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)

    def advance(self, seconds: float) -> None:
        self._now += max(0.0, float(seconds))


def install_fake_clock(monkeypatch, *modules: Any) -> FakeClock:
    """Gắn một FakeClock chung cho các module automation được liệt kê."""
    clock = FakeClock()
    for module in modules:
        monkeypatch.setattr(module, "time", clock)
    return clock


class FakeNode:
    """Một phần tử DOM đã resolve."""

    def __init__(
        self,
        *,
        visible: bool = True,
        enabled: bool = True,
        value: str = "",
        detached: bool = False,
    ) -> None:
        self.visible = visible
        self.enabled = enabled
        self.value = value
        self.detached = detached
        self.clicks = 0
        self.fills: list[str] = []
        self.text = ""
        self.checked = False
        self.check_calls = 0
        self.parent: FakeNode | None = None

    def _guard(self) -> None:
        if self.detached:
            raise PlaywrightError("Element is not attached to the DOM")

    def is_visible(self) -> bool:
        self._guard()
        return self.visible

    def is_enabled(self) -> bool:
        self._guard()
        return self.enabled

    def input_value(self, timeout: float | None = None) -> str:
        self._guard()
        return self.value

    def fill(self, value: str, timeout: float | None = None) -> None:
        self._guard()
        self.fills.append(value)
        self.value = value

    def click(self, timeout: float | None = None) -> None:
        self._guard()
        self.clicks += 1

    def wait_for(self, state: str | None = None, timeout: float | None = None) -> None:
        self._guard()

    def get_attribute(self, name: str) -> str | None:
        self._guard()
        return None

    def inner_text(self, timeout: float | None = None) -> str:
        self._guard()
        return self.text

    def is_checked(self) -> bool:
        self._guard()
        return self.checked

    def check(self, timeout: float | None = None) -> None:
        self._guard()
        self.checked = True
        self.check_calls += 1

    def dispatch_event(self, event: str) -> None:
        self._guard()

    def evaluate(self, script: str, arg: Any = None) -> Any:
        self._guard()
        if "element.click()" in script or "new MouseEvent('click'" in script:
            self.clicks += 1
            return None
        raise AssertionError(f"Fake DOM chưa hỗ trợ script: {script[:120]}")


class FakeLocator:
    """Bề mặt Locator của Playwright, giới hạn ở những gì catalog.py dùng."""

    def __init__(self, nodes: Sequence[FakeNode], selector: str) -> None:
        self._nodes = list(nodes)
        self.selector = selector

    @property
    def first(self) -> FakeLocator:
        return FakeLocator(self._nodes[:1], self.selector)

    def nth(self, index: int) -> FakeLocator:
        return FakeLocator(self._nodes[index : index + 1], self.selector)

    def count(self) -> int:
        return len(self._nodes)

    @property
    def _node(self) -> FakeNode:
        if not self._nodes:
            raise PlaywrightError(
                f"Locator không khớp phần tử nào: {self.selector}"
            )
        return self._nodes[0]

    @property
    def node(self) -> FakeNode:
        """Phần tử đứng sau locator — để test khẳng định đúng node nào."""
        return self._node

    def is_visible(self) -> bool:
        return self._node.is_visible()

    def is_enabled(self) -> bool:
        return self._node.is_enabled()

    def input_value(self, timeout: float | None = None) -> str:
        return self._node.input_value(timeout)

    def fill(self, value: str, timeout: float | None = None) -> None:
        self._node.fill(value, timeout)

    def click(self, timeout: float | None = None) -> None:
        self._node.click(timeout)

    def wait_for(self, state: str | None = None, timeout: float | None = None) -> None:
        self._node.wait_for(state, timeout)

    def get_attribute(self, name: str) -> str | None:
        return self._node.get_attribute(name)

    def dispatch_event(self, event: str) -> None:
        self._node.dispatch_event(event)

    def evaluate(self, script: str, arg: Any = None) -> Any:
        return self._node.evaluate(script, arg)

    def inner_text(self, timeout: float | None = None) -> str:
        return self._node.inner_text(timeout)

    def is_checked(self) -> bool:
        return self._node.is_checked()

    def check(self, timeout: float | None = None) -> None:
        self._node.check(timeout)

    def evaluate_all(self, script: str, arg: Any = None) -> list[Any]:
        if not self._nodes:
            return []
        raise AssertionError(
            f"Fake DOM chưa hỗ trợ evaluate_all trên {self.selector}"
        )

    def locator(self, selector: str) -> FakeLocator:
        # WFX gắn onclick vào TD cha của anchor, nên automation phải leo lên
        # một bậc: `link.locator("xpath=..")`.
        if selector in {"xpath=..", ".."}:
            parent = self._node.parent
            assert parent is not None, (
                f"Node {self.selector} chưa khai báo parent trong fake"
            )
            return FakeLocator([parent], f"{self.selector} > xpath=..")
        raise AssertionError(f"Fake DOM chưa hỗ trợ locator lồng: {selector}")


@dataclass
class StyleRow:
    """Một dòng Catalog như ``read_rows_js`` đọc được."""

    code: str
    value: str | None = None
    season: str = ""
    costsheet_status: str = ""

    def as_payload(self, value_column: str) -> dict[str, str]:
        if value_column == "lnkArticleCode":
            value = self.code
        else:
            value = self.code if self.value is None else self.value
        return {
            "code": self.code,
            "value": value,
            "season": self.season,
            "internalCostSheetStatus": self.costsheet_status,
        }


class FilterNode(FakeNode):
    """Ô Floating Filter; chỉ ``visible`` khi cột nằm trong viewport ngang."""

    def __init__(
        self,
        aria_label: str,
        *,
        value: str = "",
        visible_from: int = 0,
        visible_to: int | None = None,
        accepts_fill: bool = True,
    ) -> None:
        super().__init__(value=value)
        self.aria_label = aria_label
        self.visible_from = visible_from
        self.visible_to = visible_to
        self.accepts_fill = accepts_fill
        self.grid: FakeCatalogGrid | None = None

    def is_visible(self) -> bool:
        self._guard()
        grid = self.grid
        if grid is None or not grid.filter_row_visible:
            return False
        left = grid.scroll_current
        if left < self.visible_from:
            return False
        return self.visible_to is None or left <= self.visible_to

    def fill(self, value: str, timeout: float | None = None) -> None:
        self._guard()
        self.fills.append(value)
        if self.accepts_fill:
            self.value = value


class StyleButtonNode(FakeNode):
    """Nút Article Code trong grid; click ghi lại vào model."""

    def __init__(self, grid: FakeCatalogGrid, code: str) -> None:
        super().__init__(value=code, detached=grid.style_buttons_detached)
        self.grid = grid
        self.visible = grid.style_buttons_visible

    def click(self, timeout: float | None = None) -> None:
        self._guard()
        self.clicks += 1
        self.grid.clicked_codes.append(self.value)


class RootNode(FakeNode):
    """``.ag-root-wrapper``: router cho toàn bộ script JS của catalog.py."""

    def __init__(self, grid: FakeCatalogGrid) -> None:
        super().__init__()
        self.grid = grid

    def evaluate(self, script: str, arg: Any = None) -> Any:
        grid = self.grid
        # Thứ tự kiểm tra quan trọng: setter scroll và read_rows đều chứa cùng
        # selector/khối return với script khác, nên nhận diện bằng dấu hiệu
        # riêng trước.
        if "scroller.scrollLeft = Number" in script:
            grid.scroll_to(int(arg or 0))
            return None
        if "Number(scroller.scrollLeft || 0)" in script:
            return {
                "current": grid.scroll_current,
                "maximum": grid.scroll_maximum,
                "viewport": grid.scroll_viewport,
            }
        if "args.valueColumn" in script:
            return grid.read_rows(str(arg["valueColumn"]))
        if "return {loading, noRows, rows}" in script:
            return grid.read_data_state()
        if ".ag-floating-filter input" in script:
            return grid.filter_row_active()
        if "document.visibilityState" in script:
            return grid.interactive
        raise AssertionError(f"Fake DOM chưa hỗ trợ script: {script[:160]}")


class FrameElementNode(FakeNode):
    """``HTMLFrameElement`` ở document cha — dùng để loại grid trong pane ẩn."""

    def __init__(self, visible: bool) -> None:
        super().__init__(visible=visible)
        self.disposed = False

    def evaluate(self, script: str, arg: Any = None) -> Any:
        if "getComputedStyle(element)" in script:
            return self.visible
        return super().evaluate(script, arg)

    def dispose(self) -> None:
        self.disposed = True


class FakeCatalogGrid:
    """Frame AG Grid của Catalog kèm model trạng thái điều khiển được."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        rows: Iterable[StyleRow] = (),
        filters: Iterable[FilterNode] = (),
        url: str = "https://wfx.test/wfx/wfxcataloglist.aspx?CatalogType=1",
        loading: bool = False,
        no_rows: bool = False,
        filter_row_visible: bool = False,
        interactive: bool = True,
        detached: bool = False,
        frame_element_visible: bool | None = None,
        scroll_current: int = 0,
        scroll_maximum: int = 0,
        scroll_viewport: int = 800,
        show_button: bool = True,
        style_buttons_visible: bool = True,
        style_buttons_detached: bool = False,
        on_poll: Callable[[FakeCatalogGrid, int], None] | None = None,
    ) -> None:
        self.clock = clock
        self.url = url
        self.rows = list(rows)
        self.loading = loading
        self.no_rows = no_rows
        self.filter_row_visible = filter_row_visible
        self.interactive = interactive
        self.detached = detached
        self.frame_element_visible = frame_element_visible
        self.scroll_current = scroll_current
        self.scroll_maximum = scroll_maximum
        self.scroll_viewport = scroll_viewport
        self.style_buttons_visible = style_buttons_visible
        self.style_buttons_detached = style_buttons_detached
        self.on_poll = on_poll

        self.filters: dict[str, FilterNode] = {}
        for node in filters:
            node.grid = self
            self.filters[node.aria_label] = node

        self.show_filter_button = FakeNode() if show_button else None
        self.root = RootNode(self)

        # Ghi lại để test khẳng định hành vi, không chỉ kết quả.
        self.poll_count = 0
        self.poll_times: list[float] = []
        self.show_filter_clicks = 0
        self.clicked_codes: list[str] = []
        self.scroll_history: list[int] = [scroll_current]
        self.frame_elements: list[FrameElementNode] = []

    # --- model ---------------------------------------------------------

    def scroll_to(self, left: int) -> None:
        self.scroll_current = max(0, min(self.scroll_maximum, int(left)))
        self.scroll_history.append(self.scroll_current)

    def filter_row_active(self) -> bool:
        return bool(
            self.filter_row_visible
            and any(node.is_visible() for node in self.filters.values())
        )

    def _tick(self) -> None:
        self.poll_count += 1
        self.poll_times.append(self.clock.monotonic())
        if self.on_poll is not None:
            self.on_poll(self, self.poll_count)

    def read_data_state(self) -> dict[str, Any]:
        self._tick()
        return {
            "loading": self.loading,
            "noRows": self.no_rows,
            "rows": 0 if (self.loading or self.no_rows) else len(self.rows),
        }

    def read_rows(self, value_column: str) -> dict[str, Any]:
        self._tick()
        rendered = [] if self.loading else self.rows
        return {
            "loading": self.loading,
            "noRows": self.no_rows,
            "rows": [row.as_payload(value_column) for row in rendered],
        }

    # --- bề mặt Frame --------------------------------------------------

    def is_detached(self) -> bool:
        return self.detached

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def frame_element(self) -> FrameElementNode:
        if self.frame_element_visible is None:
            raise PlaywrightError("Frame chính không có frame element")
        node = FrameElementNode(self.frame_element_visible)
        self.frame_elements.append(node)
        return node

    def locator(self, selector: str) -> FakeLocator:
        if selector == ROOT_SELECTOR:
            return FakeLocator([self.root], selector)
        if selector == SHOW_FILTER_SELECTOR:
            button = self.show_filter_button
            return FakeLocator(
                [_ShowFilterProxy(self)] if button is not None else [],
                selector,
            )
        if selector == STYLE_BUTTON_SELECTOR:
            return FakeLocator(
                [StyleButtonNode(self, row.code) for row in self.rows],
                selector,
            )
        if "Filter Input" in selector:
            labels = [
                part.strip().removeprefix('input[aria-label="').removesuffix('"]')
                for part in selector.split(",")
            ]
            return FakeLocator(
                [
                    node
                    for label in labels
                    if (node := self.filters.get(label)) is not None
                ],
                selector,
            )
        raise AssertionError(f"Fake DOM chưa hỗ trợ selector grid: {selector}")


class _ShowFilterProxy(FakeNode):
    """Nút Show Floating Filters: mỗi lần dispatch là một lần toggle."""

    def __init__(self, grid: FakeCatalogGrid) -> None:
        super().__init__()
        self.grid = grid

    def evaluate(self, script: str, arg: Any = None) -> Any:
        if "new MouseEvent('click'" in script or "element.click()" in script:
            self.grid.show_filter_clicks += 1
            self.grid.filter_row_visible = not self.grid.filter_row_visible
            return None
        return super().evaluate(script, arg)


class MasterNode(FakeNode):
    """Node ``Master`` trong cây Catalog, có thể giả lập frame bị thay."""

    def __init__(self, *, fail_wait_times: int = 0) -> None:
        super().__init__()
        self.fail_wait_times = fail_wait_times
        self.wait_calls = 0

    def wait_for(self, state: str | None = None, timeout: float | None = None) -> None:
        self.wait_calls += 1
        if self.wait_calls <= self.fail_wait_times:
            raise PlaywrightError("Execution context was destroyed")


class FakeCatalogTree:
    """Frame cây Catalog (``left``) với ``#ddlCategory`` và node Master."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        category_value: str = "01",
        url: str = "https://wfx.test/wfx/WFX_CatalogTree.aspx?CatalogType=1",
        master: MasterNode | None = None,
    ) -> None:
        self.clock = clock
        self.url = url
        self.category = FakeNode(value=category_value)
        self.master = master if master is not None else MasterNode()
        self.text_queries: list[tuple[str, bool]] = []
        self.selectors: list[str] = []

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def is_detached(self) -> bool:
        return False

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        self.text_queries.append((text, exact))
        return FakeLocator([self.master], f"text={text}")

    def locator(self, selector: str) -> FakeLocator:
        self.selectors.append(selector)
        if selector == CATEGORY_SELECTOR:
            return FakeLocator([self.category], selector)
        # Đặc tả cấm click IMG collapse hoặc container LI chỉ vì nó chứa chữ
        # Master. Bất kỳ selector nào khác đều là hồi quy.
        raise AssertionError(
            f"Cây Catalog không được truy vấn selector này: {selector}"
        )


@dataclass
class FakePage:
    """Trang WFX tối giản: chỉ danh sách frame và bộ đếm thời gian."""

    clock: FakeClock
    frames: list[Any] = field(default_factory=list)
    named_frames: dict[str, Any] = field(default_factory=dict)
    url: str = "https://wfx.test/wfx/default.aspx"

    def frame(self, name: str | None = None, **_kwargs: Any) -> Any | None:
        return self.named_frames.get(name or "")

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def locator(self, selector: str) -> FakeLocator:
        raise AssertionError(f"Fake page chưa hỗ trợ selector: {selector}")
