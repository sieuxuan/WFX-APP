"""Fake AG Grid của Sample List để chạy thật logic trong `modules.py`.

Cùng nguyên tắc với `tests/fakes/wfx_dom.py`: mô phỏng *ngữ nghĩa* mà các script
JS của Sample tính ra (gom dòng theo `row-id`, chấm điểm nút Style Code, quét
ngang Floating Filter) bằng một model khai báo, và raise ``AssertionError`` khi
gặp selector/script chưa biết — fake không được im lặng trả mặc định.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from tests.fakes.wfx_dom import FakeClock
from wfx_panel.automation.search_specs import SAMPLE_SEARCH_SPEC

ROOT_SELECTOR = ".ag-root-wrapper"
ROW_SELECTOR = ".ag-row[row-index], [role='row'][row-index]"
LOADING_SELECTOR = (
    ".ag-overlay-loading-wrapper, .ag-loading, .blockUI, .blockOverlay, "
    ".ui-widget-overlay, .loading, .loader, [aria-busy='true'], "
    "[id*='loading' i], [id*='progress' i], "
    "[class*='loading' i], [class*='progress' i]"
)

# Selector hợp lệ mà flow Sample được phép hỏi tới. Bất kỳ selector nào khác là
# hồi quy: nó có nghĩa flow đang dò một màn khác.
KNOWN_INPUT_SELECTORS = (
    frozenset(SAMPLE_SEARCH_SPEC.field_selectors)
    | frozenset(SAMPLE_SEARCH_SPEC.context_field.selectors)
    | {"input"}
)


@dataclass
class SampleRow:
    """Một dòng Sample như `_SAMPLE_RESULT_ROWS_JS` đọc được."""

    row_key: str
    style_code: str = ""
    sample_no: str = ""
    created_by: str = ""
    buyer: str = ""

    def as_payload(self) -> dict[str, str]:
        return {
            "row_key": self.row_key,
            "row_index": self.row_key,
            "style_code": self.style_code,
            "sample_no": self.sample_no,
            "created_by": self.created_by,
            "buyer": self.buyer,
        }


@dataclass(eq=False)
class SampleFilter:
    """Ô Floating Filter; chỉ visible khi cột nằm trong viewport ngang."""

    label: str
    selectors: tuple[str, ...]
    value: str = ""
    visible_from: int = 0
    visible_to: int | None = None
    frame: Any = None
    fills: list[str] = field(default_factory=list)
    presses: list[str] = field(default_factory=list)

    def is_visible(self) -> bool:
        frame = self.frame
        if frame is None or not frame.filter_row_visible:
            return False
        left = frame.scroll_current
        if left < self.visible_from:
            return False
        return self.visible_to is None or left <= self.visible_to

    def is_enabled(self) -> bool:
        return True

    def input_value(self, timeout: float | None = None) -> str:
        return self.value

    def fill(self, value: str, timeout: float | None = None) -> None:
        self.fills.append(value)
        self.value = value
        if self.frame is not None:
            self.frame.fill_log.append((self.label, value))

    def press(self, key: str, timeout: float | None = None) -> None:
        self.presses.append(key)

    def dispatch_event(self, event: str) -> None:
        return None

    def evaluate(self, script: str, arg: Any = None) -> Any:
        if "element.closest(" in script:
            return self.label
        raise AssertionError(f"Filter chưa hỗ trợ script: {script[:120]}")


def sample_filters(
    *,
    hidden_beyond: dict[str, int] | None = None,
) -> list[SampleFilter]:
    """Bốn ô filter thật của Sample, mặc định luôn nằm trong viewport."""
    limits = hidden_beyond or {}
    return [
        SampleFilter(
            label=spec.label,
            selectors=spec.selectors,
            visible_to=limits.get(name),
        )
        for name, spec in SAMPLE_SEARCH_SPEC.fields.items()
    ]


class _Locator:
    def __init__(self, nodes: Sequence[Any], selector: str) -> None:
        self._nodes = list(nodes)
        self.selector = selector

    def count(self) -> int:
        return len(self._nodes)

    def nth(self, index: int) -> _Locator:
        return _Locator(self._nodes[index : index + 1], self.selector)

    @property
    def first(self) -> _Locator:
        return _Locator(self._nodes[:1], self.selector)

    @property
    def node(self) -> Any:
        if not self._nodes:
            raise PlaywrightError(f"Locator rỗng: {self.selector}")
        return self._nodes[0]

    def is_visible(self) -> bool:
        return self.node.is_visible()

    def is_enabled(self) -> bool:
        return self.node.is_enabled()

    def input_value(self, timeout: float | None = None) -> str:
        return self.node.input_value(timeout)

    def fill(self, value: str, timeout: float | None = None) -> None:
        self.node.fill(value, timeout)

    def press(self, key: str, timeout: float | None = None) -> None:
        self.node.press(key, timeout)

    def dispatch_event(self, event: str) -> None:
        self.node.dispatch_event(event)

    def get_attribute(self, name: str) -> str | None:
        return self.node.get_attribute(name)

    def evaluate(self, script: str, arg: Any = None) -> Any:
        return self.node.evaluate(script, arg)

    def locator(self, selector: str) -> _Locator:
        return self.node.locator(selector)


class _RowNode:
    def __init__(self, frame: SampleGridFrame, row: SampleRow) -> None:
        self.frame = frame
        self.row = row

    def get_attribute(self, name: str) -> str | None:
        if name in {"row-id", "row-index"}:
            return self.row.row_key
        raise AssertionError(f"Row chưa hỗ trợ attribute: {name}")

    def evaluate(self, script: str, arg: Any = None) -> Any:
        if "bestScore = -100" not in script:
            raise AssertionError(f"Row chưa hỗ trợ script: {script[:120]}")
        expected = str(arg or "").strip().casefold()
        code = self.row.style_code
        if not code:
            return ""
        if expected and code.casefold() != expected:
            return ""
        self.frame.clicked.append((self.row.row_key, code))
        return code


class _RootNode:
    def __init__(self, frame: SampleGridFrame) -> None:
        self.frame = frame

    def is_visible(self) -> bool:
        return self.frame.root_visible

    def evaluate(self, script: str, arg: Any = None) -> Any:
        frame = self.frame
        if "scroller.scrollLeft = Number" in script:
            frame.scroll_to(int(arg or 0))
            return None
        if "Number(scroller.scrollLeft || 0)" in script:
            return {
                "current": frame.scroll_current,
                "maximum": frame.scroll_maximum,
                "viewport": frame.scroll_viewport,
            }
        if "const rowNodes" in script:
            return frame.read_rows()
        raise AssertionError(f"Root chưa hỗ trợ script: {script[:160]}")

    def locator(self, selector: str) -> _Locator:
        if selector != ROW_SELECTOR:
            raise AssertionError(f"Root chưa hỗ trợ selector: {selector}")
        return _Locator(
            [_RowNode(self.frame, row) for row in self.frame.rows],
            selector,
        )


class SampleGridFrame:
    """Frame Sample List: grid AG Grid + Floating Filter quét ngang được."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        rows: Iterable[SampleRow] = (),
        filters: Iterable[SampleFilter] | None = None,
        no_rows: bool = False,
        url: str = "https://wfx.test/wfx/WFXSampleList.aspx",
        name: str = "body",
        filter_row_visible: bool = True,
        root_visible: bool = True,
        scroll_current: int = 0,
        scroll_maximum: int = 0,
        scroll_viewport: int = 800,
        on_poll: Callable[[SampleGridFrame, int], None] | None = None,
    ) -> None:
        self.clock = clock
        self.url = url
        self.name = name
        self.rows = list(rows)
        self.no_rows = no_rows
        self.filter_row_visible = filter_row_visible
        self.root_visible = root_visible
        self.scroll_current = scroll_current
        self.scroll_maximum = scroll_maximum
        self.scroll_viewport = scroll_viewport
        self.on_poll = on_poll
        self.root = _RootNode(self)

        self.inputs: list[SampleFilter] = list(
            sample_filters() if filters is None else filters
        )
        for node in self.inputs:
            node.frame = self

        self.poll_count = 0
        self.clicked: list[tuple[str, str]] = []
        self.fill_log: list[tuple[str, str]] = []
        self.scroll_history: list[int] = [scroll_current]

    # --- model ---------------------------------------------------------

    def scroll_to(self, left: int) -> None:
        self.scroll_current = max(0, min(self.scroll_maximum, int(left)))
        self.scroll_history.append(self.scroll_current)

    def read_rows(self) -> dict[str, Any]:
        self.poll_count += 1
        if self.on_poll is not None:
            self.on_poll(self, self.poll_count)
        return {
            "rows": [row.as_payload() for row in self.rows],
            "noRows": bool(self.no_rows and not self.rows),
            "totalRows": len(self.rows),
        }

    # --- bề mặt Frame ---------------------------------------------------

    def is_detached(self) -> bool:
        return False

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def locator(self, selector: str) -> _Locator:
        if selector == ROOT_SELECTOR:
            return _Locator([self.root], selector)
        if selector == LOADING_SELECTOR:
            return _Locator([], selector)
        parts = [part.strip() for part in selector.split(",") if part.strip()]
        unknown = [part for part in parts if part not in KNOWN_INPUT_SELECTORS]
        if unknown:
            raise AssertionError(
                f"Sample frame chưa hỗ trợ selector: {', '.join(unknown)}"
            )
        nodes: list[SampleFilter] = []
        for part in parts:
            for node in self.inputs:
                if node in nodes:
                    continue
                if part == "input" or part in node.selectors:
                    nodes.append(node)
        return _Locator(nodes, selector)
