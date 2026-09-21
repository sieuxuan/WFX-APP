"""DOM giả cho màn Supplier List của WFX.

Màn này KHÔNG giống Catalog: cùng một frame vừa chứa ``#ddlCategory`` (cây
Category), vừa chứa node ``Master``, vừa chứa ô ``#txtCompanyName`` và bảng
công ty. ``_supplier_company_ready()`` đọc cả ``#ddlCategory`` lẫn
``#txtCompanyName`` trên cùng frame, nên fake phải giữ đúng hình dạng đó.

Hai chi tiết nghiệp vụ được mô phỏng thật vì đặc tả phụ thuộc vào chúng:

* WFX chỉ bind đủ option Category **sau ``mousedown``**; trước đó DOM chỉ có
  ``[Select]`` + ``Apparel``.
* Bảng công ty được WFX lọc **phía server**: điền query xong thì chỉ những dòng
  khớp mới còn lại. ``extra_rows`` mô phỏng dòng phụ (tổng/phân trang) mà WFX
  vẫn giữ lại dù không khớp query.

Gặp selector hoặc script chưa khai báo thì raise ``AssertionError`` — fake
không được im lặng trả giá trị mặc định.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

SUPPLIER_URL = "https://wfx.test/wfx/wfxPartyGroup.aspx?PartyType=2"
BUYER_URL = "https://wfx.test/wfx/wfxPartyGroup.aspx?PartyType=1"
CATALOG_TREE_URL = "https://wfx.test/wfx/WFX_CatalogTree.aspx?CatalogType=1"

CATEGORY_SELECTOR = "#ddlCategory"
COMPANY_SELECTOR = "#txtCompanyName"
# Đúng selector `_actionable_master()` dùng: chỉ node có action trực tiếp.
MASTER_SELECTOR = 'span[onclick], a, button, [role="button"], input[type="button"]'

_OPTION_PATTERN = re.compile(r'option\[value="(?P<value>.*)"\]')


class Node:
    """Phần tử DOM giả, chỉ có bề mặt mà `directory.py` thật sự chạm tới."""

    def __init__(
        self,
        *,
        tag: str = "SPAN",
        text: str = "",
        value: str = "",
        visible: bool = True,
        enabled: bool = True,
        detached: bool = False,
        options: Iterable[str] = (),
        bound_options: Iterable[str] = (),
        on_click: Callable[[], None] | None = None,
        on_value: Callable[[str], None] | None = None,
    ) -> None:
        self.tag = tag
        self.text = text
        self.value = value
        self.visible = visible
        self.enabled = enabled
        self.detached = detached
        self.all_options = set(options)
        self.bound_options = set(bound_options)
        self.on_click = on_click
        self.on_value = on_value
        self.clicks = 0
        self.mousedowns = 0
        self.tag_reads = 0
        self.text_reads = 0
        self.presses: list[str] = []

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
        self.text_reads += 1
        return self.value

    def inner_text(self, timeout: float | None = None) -> str:
        self._guard()
        self.text_reads += 1
        return self.text

    def wait_for(self, state: str | None = None, timeout: float | None = None) -> None:
        self._guard()

    def _set_value(self, value: str) -> None:
        self.value = value
        if self.on_value is not None:
            self.on_value(value)

    def fill(self, value: str, timeout: float | None = None) -> None:
        self._guard()
        self._set_value(value)

    def type(self, text: str, delay: float | None = None) -> None:
        self._guard()
        self._set_value(self.value + text)

    def press(self, key: str, timeout: float | None = None) -> None:
        self._guard()
        self.presses.append(key)

    def dispatch_event(self, event: str) -> None:
        self._guard()
        if event == "mousedown":
            # Đây là lý do `_select_supplier_category` phải dispatch trước khi
            # chờ option: WFX bind đủ 6 Category đúng ở thời điểm này.
            self.mousedowns += 1
            self.bound_options = set(self.all_options)
            return
        raise AssertionError(f"Node chưa hỗ trợ sự kiện: {event}")

    def select_option(
        self,
        value: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._guard()
        if value not in self.bound_options:
            raise PlaywrightError(f"Option chưa được bind: {value}")
        self.clicks += 1
        self._set_value(str(value))

    def click(self, timeout: float | None = None) -> None:
        self._guard()
        self.clicks += 1
        if self.on_click is not None:
            self.on_click()

    def evaluate(self, script: str, arg: Any = None) -> Any:
        self._guard()
        if "element.tagName" in script:
            self.tag_reads += 1
            return self.tag
        if "element.click()" in script:
            return self.click()
        raise AssertionError(f"Node chưa hỗ trợ script: {script[:120]}")


class Loc:
    """Bề mặt Locator tối thiểu, đủ cho nửa Supplier của `directory.py`."""

    def __init__(self, nodes: Sequence[Node], selector: str) -> None:
        self._nodes = list(nodes)
        self.selector = selector

    @property
    def first(self) -> Loc:
        return Loc(self._nodes[:1], self.selector)

    def nth(self, index: int) -> Loc:
        return Loc(self._nodes[index : index + 1], self.selector)

    def count(self) -> int:
        return len(self._nodes)

    @property
    def node(self) -> Node:
        if not self._nodes:
            raise PlaywrightTimeoutError(
                f"Locator không khớp phần tử nào: {self.selector}"
            )
        return self._nodes[0]

    def is_visible(self) -> bool:
        return self.node.is_visible()

    def is_enabled(self) -> bool:
        return self.node.is_enabled()

    def input_value(self, timeout: float | None = None) -> str:
        return self.node.input_value(timeout)

    def inner_text(self, timeout: float | None = None) -> str:
        return self.node.inner_text(timeout)

    def fill(self, value: str, timeout: float | None = None) -> None:
        self.node.fill(value, timeout)

    def type(self, text: str, delay: float | None = None) -> None:
        self.node.type(text, delay)

    def press(self, key: str, timeout: float | None = None) -> None:
        self.node.press(key, timeout)

    def click(self, timeout: float | None = None) -> None:
        self.node.click(timeout)

    def wait_for(self, state: str | None = None, timeout: float | None = None) -> None:
        self.node.wait_for(state, timeout)

    def dispatch_event(self, event: str) -> None:
        self.node.dispatch_event(event)

    def select_option(
        self,
        value: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.node.select_option(value, timeout)

    def evaluate(self, script: str, arg: Any = None) -> Any:
        return self.node.evaluate(script, arg)

    def get_attribute(self, name: str) -> str | None:
        self.node._guard()
        return None

    def locator(self, selector: str) -> Loc:
        match = _OPTION_PATTERN.fullmatch(selector)
        if match is None:
            raise AssertionError(f"Loc chưa hỗ trợ selector lồng: {selector}")
        value = match.group("value")
        found = (
            [Node(tag="OPTION", value=value)]
            if value in self.node.bound_options
            else []
        )
        return Loc(found, selector)


def default_tree(master: Node) -> list[Node]:
    """Cây Supplier như selector thật trả về: Master nằm giữa các node nhiễu.

    Các node nhiễu đều KHỚP selector nhưng text không đúng bằng ``Master``, nên
    chúng phải bị bỏ qua. Nếu ai nới điều kiện thành `in`/`startswith`, test sẽ
    click nhầm và đỏ ngay.
    """
    return [
        Node(tag="A", text="Master Data"),
        Node(tag="INPUT", value="Search"),
        Node(tag="SPAN", text="Group Master"),
        master,
    ]


class SupplierFrame:
    """Frame Supplier List: Category + Master + ô tìm + bảng công ty."""

    def __init__(
        self,
        clock: Any,
        *,
        url: str = SUPPLIER_URL,
        title: str = "Supplier List",
        name: str = "left",
        category: str = "01",
        options: Iterable[str] = ("01", "03", "04", "05", "06", "12"),
        rows_by_category: Mapping[str, Sequence[str]] | None = None,
        extra_rows: Sequence[str] = (),
        master_opens_after: int = 0,
        busy: bool = False,
        has_category: bool = True,
        tree: Sequence[Node] | None = None,
    ) -> None:
        self.clock = clock
        self.url = url
        self.title_text = title
        self.name = name
        self.busy = busy
        self.has_category = has_category
        self.rows_by_category = {
            key: list(value) for key, value in (rows_by_category or {}).items()
        }
        self.extra_rows = list(extra_rows)
        self.master_opens_after = master_opens_after
        self.master_clicks = 0
        self.applied_query = ""
        self.row_reads = 0
        self.selectors: list[str] = []
        self.detached = False

        self.category = Node(
            tag="SELECT",
            value=category,
            options=options,
            # Trước mousedown WFX chỉ có [Select] + Apparel.
            bound_options={"", "01"},
            on_value=self._on_category,
        )
        self.master = Node(tag="SPAN", text="Master", on_click=self._on_master)
        self.company = Node(tag="INPUT", on_value=self._on_query)
        self.tree = list(tree) if tree is not None else default_tree(self.master)

    # --- model ---------------------------------------------------------

    def _on_master(self) -> None:
        self.master_clicks += 1

    def _on_category(self, _value: str) -> None:
        # Đổi Category là reload grid: query cũ và Master cũ đều mất.
        self.applied_query = ""
        self.master_clicks = 0

    def _on_query(self, value: str) -> None:
        self.applied_query = value

    @property
    def company_ready(self) -> bool:
        return self.master_clicks >= self.master_opens_after

    def read_rows(self, query: str) -> dict[str, Any]:
        self.row_reads += 1
        folded = str(query or "").casefold()
        applied = self.applied_query.casefold()
        names = [
            name
            for name in self.rows_by_category.get(self.category.value, [])
            if not applied or applied in name.casefold()
        ] + list(self.extra_rows)
        rows = [
            {
                "company": name,
                "matches": folded in name.casefold(),
                "hasEdit": True,
            }
            for name in names
        ]
        return {"rows": rows, "noRows": not rows, "loading": self.busy}

    # --- bề mặt Frame ---------------------------------------------------

    def is_detached(self) -> bool:
        return self.detached

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def locator(self, selector: str) -> Loc:
        self.selectors.append(selector)
        if selector == CATEGORY_SELECTOR:
            return Loc([self.category] if self.has_category else [], selector)
        if selector == COMPANY_SELECTOR:
            return Loc([self.company] if self.company_ready else [], selector)
        if selector == MASTER_SELECTOR:
            return Loc(self.tree, selector)
        raise AssertionError(f"SupplierFrame chưa khai báo selector: {selector}")

    def evaluate(self, script: str, arg: Any = None) -> Any:
        # Thứ tự quan trọng: script marker PartyType cũng chứa `document.title`.
        if "party.?type" in script:
            return f"{self.url} {self.title_text}".casefold()
        if "document.title" in script:
            return self.title_text
        if ".loading, .loader" in script:
            return self.busy
        if "args.query" in script:
            return self.read_rows(str((arg or {}).get("query", "")))
        if "__wfxPanelDocumentMarker" in script:
            return ""
        raise AssertionError(f"SupplierFrame chưa hỗ trợ script: {script[:140]}")


class CatalogTreeFrame:
    """Cây Catalog: cũng có `#ddlCategory` nên là bẫy nhận nhầm frame."""

    def __init__(self, clock: Any, *, category: str = "01") -> None:
        self.clock = clock
        self.url = CATALOG_TREE_URL
        self.name = "left"
        self.category = Node(tag="SELECT", value=category)
        self.detached = False

    def is_detached(self) -> bool:
        return self.detached

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.advance(float(milliseconds) / 1_000.0)

    def locator(self, selector: str) -> Loc:
        if selector == CATEGORY_SELECTOR:
            return Loc([self.category], selector)
        if selector == COMPANY_SELECTOR:
            # Cây Catalog không có ô tìm công ty; phải trả rỗng chứ không nổ,
            # vì `_company_search_frame` quét MỌI frame của tab.
            return Loc([], selector)
        raise AssertionError(
            f"Cây Catalog không được truy vấn selector Supplier: {selector}"
        )

    def evaluate(self, script: str, arg: Any = None) -> Any:
        if "party.?type" in script:
            return f"{self.url} catalog".casefold()
        if "document.title" in script:
            return "Catalog"
        raise AssertionError(f"CatalogTreeFrame chưa hỗ trợ script: {script[:140]}")
