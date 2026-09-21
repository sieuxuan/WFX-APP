"""Mini-DOM khai báo cho các flow Playwright thao tác trên cây phần tử.

`tests/fakes/wfx_dom.py` map *một selector → một danh sách node*, đủ cho Catalog
nhưng không đủ cho Costing/GRN/OC: những flow đó đi theo **cấu trúc** — lấy
`:scope > tbody > tr` của một grid, rồi trong từng dòng tìm `#chkSelector`,
`[id="imgSplitterForUsage"]`, đọc `class` của dòng để nhận header section…
Không có quan hệ cha–con thì không mô phỏng được, nên phần lớn thân hàm của
`costing/articles.py`, `costing/dependencies.py`, `costing/inventory.py` chưa
từng chạy trong test.

Fake này dựng đúng cái còn thiếu: một cây `Element` với id/class/tag/thuộc
tính, và một bộ resolve CSS **tối giản** chỉ hỗ trợ đúng cú pháp mà code sản
phẩm dùng:

* tổ hợp: ``tag``, ``#id``, ``.class``, ``[attr]``, ``[attr="value"]``
* quan hệ: khoảng trắng (hậu duệ), ``>`` (con), ``:scope`` (chính node hiện tại)
* pseudo ``:visible``
* ``xpath=...`` tra đúng khóa mà test đã khai báo

Nguyên tắc giữ nguyên như các fake khác: cú pháp lạ thì ``AssertionError``, để
không có nhánh nào xanh nhờ một giá trị mặc định im lặng.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from playwright.sync_api import Error as PlaywrightError

_TOKEN = re.compile(
    r"""
    (?P<tag>^[A-Za-z][\w-]*)
  | \#(?P<id>[\w-]+)
  | \.(?P<cls>[\w-]+)
  | \[(?P<attr>[\w-]+)
      (?:\s*(?P<op>[\^$*]?=)\s*(?P<quote>["'])(?P<value>[^"']*)(?P=quote)
          (?:\s+(?P<flag>[iI]))?)?\s*\]
  | :not\((?P<negate>[^()]*(?:\([^()]*\))?[^()]*)\)
  | :(?P<pseudo>visible|scope|checked)
    """,
    re.VERBOSE,
)


class Element:
    """Một phần tử DOM khai báo, có cha–con thật."""

    def __init__(
        self,
        tag: str = "div",
        *,
        id: str = "",
        css_class: str = "",
        text: str = "",
        value: str = "",
        visible: bool = True,
        enabled: bool = True,
        checked: bool = False,
        attrs: dict[str, str] | None = None,
        children: Sequence[Element] = (),
        options: Sequence[tuple[str, str]] = (),
        on_click: Any = None,
        on_fill: Any = None,
        scripts: dict[str, Any] | None = None,
    ) -> None:
        self.tag = tag
        self.id = id
        self.css_class = css_class
        self.text = text
        self.value = value
        self.visible = visible
        self.enabled = enabled
        self.checked = checked
        self.attrs = dict(attrs or {})
        self.options = [(str(label), str(val)) for label, val in options]
        self.on_click = on_click
        self.on_fill = on_fill
        self.scripts = dict(scripts or {})
        self.markers: dict[str, str] = {}
        self.parent: Element | None = None
        self.children: list[Element] = []
        self.clicks = 0
        self.fills: list[str] = []
        self.selected: list[str] = []
        self.checks = 0
        self.keys: list[str] = []
        self.dispatched: list[str] = []
        for child in children:
            self.append(child)

    # --- dựng cây --------------------------------------------------------

    def append(self, child: Element) -> Element:
        child.parent = self
        self.children.append(child)
        return child

    def descendants(self) -> Iterator[Element]:
        for child in self.children:
            yield child
            yield from child.descendants()

    # --- thuộc tính ------------------------------------------------------

    def attribute(self, name: str) -> str | None:
        if name == "id":
            return self.id or None
        if name == "class":
            return self.css_class or None
        if name == "value":
            return self.value or self.attrs.get("value") or None
        return self.attrs.get(name)

    def matches(self, token: str) -> bool:
        position = 0
        matched_anything = False
        while position < len(token):
            match = _TOKEN.match(token, position)
            if match is None:
                raise AssertionError(f"mini_dom chưa hỗ trợ selector: {token!r}")
            position = match.end()
            matched_anything = True
            if match.group("tag") and self.tag != match.group("tag"):
                return False
            if match.group("id") and self.id != match.group("id"):
                return False
            if match.group("cls"):
                classes = str(self.css_class or "").split()
                if match.group("cls") not in classes:
                    return False
            if match.group("attr"):
                name = match.group("attr")
                actual = self.attribute(name)
                if actual is None:
                    return False
                wanted = match.group("value")
                if wanted is not None:
                    if match.group("flag"):
                        actual = actual.casefold()
                        wanted = wanted.casefold()
                    operator = match.group("op") or "="
                    if operator == "=" and actual != wanted:
                        return False
                    if operator == "^=" and not actual.startswith(wanted):
                        return False
                    if operator == "$=" and not actual.endswith(wanted):
                        return False
                    if operator == "*=" and wanted not in actual:
                        return False
            negated = match.group("negate")
            if negated is not None and self.matches(negated):
                return False
            if match.group("pseudo") == "visible" and not self.visible:
                return False
            if match.group("pseudo") == "checked":
                # `option:checked` = option đang được select giữ giá trị.
                parent = self.parent
                selected = (
                    str(parent.value or "") if parent is not None else ""
                )
                if str(self.attribute("value") or "") != selected:
                    return False
        if not matched_anything:
            raise AssertionError(f"mini_dom chưa hỗ trợ selector: {token!r}")
        return True

    # --- bề mặt Playwright sau khi resolve -------------------------------

    def is_visible(self, timeout: float | None = None) -> bool:
        return self.visible

    def is_enabled(self, timeout: float | None = None) -> bool:
        return self.enabled

    def is_checked(self, timeout: float | None = None) -> bool:
        return self.checked

    def inner_text(self, timeout: float | None = None) -> str:
        return self.text

    def text_content(self, timeout: float | None = None) -> str:
        return self.text

    def input_value(self, timeout: float | None = None) -> str:
        return self.value

    def get_attribute(self, name: str, timeout: float | None = None) -> str | None:
        return self.attribute(name)

    def click(self, timeout: float | None = None, **_kwargs: Any) -> None:
        if not self.enabled:
            raise PlaywrightError(f"Element is not enabled: #{self.id}")
        self.clicks += 1
        self._toggle_if_checkbox()
        if callable(self.on_click):
            self.on_click(self)

    def _toggle_if_checkbox(self) -> None:
        """Click vào checkbox/radio thật sự đổi trạng thái, như trình duyệt."""
        kind = str(self.attrs.get("type") or "").casefold()
        if kind == "checkbox":
            self.checked = not self.checked
        elif kind == "radio":
            self.checked = True

    def check(self, timeout: float | None = None, **_kwargs: Any) -> None:
        self.checked = True
        self.checks += 1

    def uncheck(self, timeout: float | None = None, **_kwargs: Any) -> None:
        self.checked = False

    def fill(self, value: str, timeout: float | None = None, **_kwargs: Any) -> None:
        self.value = str(value)
        self.fills.append(str(value))
        if callable(self.on_fill):
            self.on_fill(self, str(value))

    def press(self, key: str, timeout: float | None = None) -> None:
        self.keys.append(key)

    def dispatch_event(self, event: str, timeout: float | None = None) -> None:
        self.dispatched.append(event)

    def select_option(self, value: Any = None, **_kwargs: Any) -> None:
        self.selected.append(str(value))
        self.value = str(value)

    def wait_for(self, state: str | None = None, timeout: float | None = None) -> None:
        if state == "visible" and not self.visible:
            raise PlaywrightError(f"Element is not visible: #{self.id}")
        if state == "hidden" and self.visible:
            raise PlaywrightError(f"Element is still visible: #{self.id}")

    def scroll_into_view_if_needed(self, timeout: float | None = None) -> None:
        return None

    def evaluate(self, script: str, arg: Any = None) -> Any:
        for marker, value in self.scripts.items():
            if marker in script:
                return value(arg) if callable(value) else value
        # Marker gắn thẳng lên phần tử (AG Grid root), ghi rồi đọc lại.
        if "__wfxPanelGridMarker" in script:
            if "=" in script.split("__wfxPanelGridMarker", 1)[1][:4]:
                self.markers["grid"] = str(arg)
                return None
            return self.markers.get("grid", "")
        if script.strip() in {
            "element => element.tagName",
            "element => element.tagName || ''",
        }:
            return self.tag.upper()
        if script.strip() in {
            "element => element.value || ''",
            "element => element.value",
        }:
            return self.value
        if "element.click()" in script or "new MouseEvent('click'" in script:
            self.clicks += 1
            self._toggle_if_checkbox()
            if callable(self.on_click):
                self.on_click(self)
            return None
        if "dispatchEvent(new Event('change'" in script:
            if str(arg) not in {value for _label, value in self.options}:
                return False
            self.value = str(arg)
            self.selected.append(str(arg))
            return True
        if (
            "querySelectorAll(':scope > tbody > tr')" in script
            and "row_id" in script
            and "article_code" in script
        ):
            # Đọc grid Material Search: tính lại đúng ngữ nghĩa của đoạn JS
            # từ chính cây đã khai báo, không phải một hằng số test dựng sẵn.
            return [
                {
                    "row_id": str(
                        row.attribute("rowid") or row.attribute("id") or ""
                    ).strip(),
                    "article_code": _text_of(row, "lblArticleCode"),
                    "article_name": _text_of(row, "lblArticleName"),
                }
                for row in _child_rows(self)
            ]
        if "previousElementSibling" in script and "id" in script:
            siblings = self.parent.children if self.parent else []
            index = siblings.index(self) if self in siblings else 0
            previous = siblings[index - 1] if index > 0 else None
            return previous.id if previous is not None else ""
        if "hasDatepicker" in script:
            # Ô ngày của ReportViewer: type=date, class hasDatepicker, hoặc ô
            # cùng cell có icon lịch.
            cell = self.parent
            while cell is not None and cell.tag not in {"td", "th"}:
                cell = cell.parent
            has_trigger = bool(
                cell is not None
                and any(
                    "calendar" in str(node.attribute("src") or "").casefold()
                    or "calendar" in str(node.id or "").casefold()
                    or "ui-datepicker-trigger" in str(node.css_class or "")
                    for node in cell.descendants()
                )
            )
            if "removeAttribute('readonly')" in script:
                self.value = str(arg)
                self.fills.append(str(arg))
                return None
            return (
                str(self.attrs.get("type") or "").casefold() == "date"
                or "hasDatepicker" in str(self.css_class or "").split()
                or has_trigger
            )
        if ".options" in script and "label" in script:
            # Đọc option của một <select> từ chính con của nó. Một số script
            # còn lọc bỏ option không có nhãn — giữ đúng khác biệt đó.
            rows = [
                {
                    "label": " ".join(str(option.text or "").split()).strip(),
                    "value": str(option.attribute("value") or "").strip(),
                }
                for option in self.children
                if option.tag == "option"
            ]
            if "filter(option => option.label)" in script:
                rows = [row for row in rows if row["label"]]
            return rows
        if "ViewAttachmentFile" in script and "file_name" in script:
            # Bảng file đính kèm của popup Article.
            rows = [
                node
                for node in self.descendants()
                if node.tag == "tr"
                and ("trContent" in str(node.css_class or "").split()
                     or node.attribute("rowid"))
            ]
            payload = []
            for row in rows:
                view = next(
                    (node for node in row.descendants() if node.id == "lnkView"),
                    None,
                )
                payload.append(
                    {
                        "row_id": row.attribute("rowid") or row.id or "",
                        "file_name": _text_of(row, "lblUserFileName"),
                        "comments": _text_of(row, "lblComments"),
                        "uploaded_on": _text_of(row, "lblUploadedOn"),
                        "uploaded_by": _text_of(row, "lblUploadedBY"),
                        "href": (view.attribute("href") or "") if view else "",
                        "onclick": (view.attribute("onclick") or "") if view else "",
                    }
                )
            return [row for row in payload if row["file_name"]]
        if "checkbox?.checked" in script or "input[type=\"checkbox\"]" in script:
            raise AssertionError("dùng evaluate_all cho danh sách option")
        if "aria-selected" in script and "closest('li')" in script:
            item = self
            while item is not None and item.tag != "li":
                item = item.parent
            item = item or self
            state = " ".join(
                [
                    str(item.attribute("aria-selected") or ""),
                    str(item.attribute("aria-current") or ""),
                    str(item.css_class or ""),
                ]
            ).casefold()
            return any(
                token in state
                for token in ("true", "active", "current", "selected")
            )
        raise AssertionError(f"mini_dom chưa hỗ trợ script: {script[:140]}")



def _child_rows(table: Element) -> list[Element]:
    """`:scope > tbody > tr` tính trên cây thật."""
    rows: list[Element] = []
    for body in table.children:
        if body.tag == "tbody":
            rows.extend(child for child in body.children if child.tag == "tr")
    return rows


def _text_of(row: Element, dom_id: str) -> str:
    for node in row.descendants():
        if node.id == dom_id:
            return str(node.text or "").strip()
    return ""


def _top_level_split(selector: str, separators: str) -> list[str]:
    """Cắt selector nhưng bỏ qua mọi dấu nằm trong ``[...]`` hoặc ``(...)``."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for character in selector:
        if character in "([":
            depth += 1
        elif character in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and character in separators:
            parts.append("".join(current))
            current = []
            parts.append(character)
            continue
        current.append(character)
    parts.append("".join(current))
    return parts


def _split_combinators(selector: str) -> list[tuple[str, str]]:
    """``"#a > tbody tr"`` → ``[("", "#a"), (">", "tbody"), (" ", "tr")]``."""
    parts: list[tuple[str, str]] = []
    combinator = ""
    pending_child = False
    for chunk in _top_level_split(selector.strip(), "> \t\n"):
        if chunk == ">":
            pending_child = True
            continue
        token = chunk.strip()
        if not token:
            continue
        parts.append((">" if pending_child else combinator, token))
        pending_child = False
        combinator = " "
    return parts


def _resolve(roots: Sequence[Element], selector: str) -> list[Element]:
    if "," in _top_level_split(selector, ","):
        # Selector list: hợp nhất kết quả nhưng giữ thứ tự tài liệu, đúng như
        # querySelectorAll — automation dựa vào `.first` của danh sách này.
        matched: list[Element] = []
        for part in _top_level_split(selector, ","):
            part = part.strip()
            if part == ",":
                continue
            if not part:
                continue
            for node in _resolve(roots, part):
                if node not in matched:
                    matched.append(node)
        order = {
            id(node): index
            for index, node in enumerate(
                node for root in roots for node in root.descendants()
            )
        }
        return sorted(matched, key=lambda node: order.get(id(node), 0))
    current: list[Element] = list(roots)
    for index, (combinator, token) in enumerate(_split_combinators(selector)):
        if token == ":scope":
            assert index == 0, ":scope chỉ hợp lệ ở đầu selector"
            continue
        pool: list[Element] = []
        for node in current:
            candidates = (
                node.children if combinator == ">" else list(node.descendants())
            )
            for candidate in candidates:
                if candidate.matches(token) and candidate not in pool:
                    pool.append(candidate)
        current = pool
    return current


class Locator:
    """Bề mặt Locator tối giản, chạy trên cây Element."""

    def __init__(self, nodes: Sequence[Element], selector: str) -> None:
        self._nodes = list(nodes)
        self.selector = selector

    # --- điều hướng ------------------------------------------------------

    @property
    def first(self) -> Locator:
        return Locator(self._nodes[:1], self.selector)

    @property
    def last(self) -> Locator:
        return Locator(self._nodes[-1:], self.selector)

    def nth(self, index: int) -> Locator:
        try:
            return Locator([self._nodes[index]], self.selector)
        except IndexError:
            return Locator([], self.selector)

    def count(self) -> int:
        return len(self._nodes)

    def all(self) -> list[Locator]:
        return [Locator([node], self.selector) for node in self._nodes]

    def all_inner_texts(self) -> list[str]:
        return [str(node.text or "") for node in self._nodes]

    def locator(self, selector: str) -> Locator:
        if selector in {"xpath=..", ".."}:
            parents = [node.parent for node in self._nodes if node.parent is not None]
            return Locator(parents, f"{self.selector} > ..")
        ancestor = re.fullmatch(
            r"xpath=ancestor::([A-Za-z][\w-]*)\[1\]", selector
        )
        if ancestor is not None:
            found: list[Element] = []
            for node in self._nodes:
                current = node.parent
                while current is not None and current.tag != ancestor.group(1):
                    current = current.parent
                if current is not None and current not in found:
                    found.append(current)
            return Locator(found, selector)
        if selector.startswith("xpath="):
            raise AssertionError(f"mini_dom chưa hỗ trợ xpath lồng: {selector}")
        return Locator(_resolve(self._nodes, selector), selector)

    def evaluate_all(self, script: str, arg: Any = None) -> list[Any]:
        """Tính lại đúng ngữ nghĩa của các script lọc trong `costing/constants`.

        Chúng đều là `elements => elements.filter(...).map(index)`; fake không
        chạy JS nên tính lại từ thuộc tính khai báo. Script lạ thì báo lỗi.
        """
        if script.strip() == "elements => elements.map(element => element.value)":
            return [node.attribute("value") or "" for node in self._nodes]
        if "element.parentElement?.textContent" in script:
            # Danh sách option của popup ReportViewer: nhãn nằm ở phần tử cha.
            rows = [
                {
                    "value": node.id,
                    "label": " ".join(
                        str((node.parent.text if node.parent else "") or "").split()
                    ).strip(),
                    "selected": bool(node.checked),
                }
                for node in self._nodes
            ]
            return [
                row
                for row in rows
                if row["value"] and row["label"] and row["label"] != "(Select All)"
            ]
        if "checkbox?.checked" in script:
            snapshot = []
            for index, node in enumerate(self._nodes):
                anchor = next(
                    (item for item in node.descendants() if item.tag == "a"), None
                )
                checkbox = next(
                    (
                        item
                        for item in node.descendants()
                        if item.attribute("type") == "checkbox"
                    ),
                    None,
                )
                snapshot.append(
                    {
                        "index": index,
                        "label": str(
                            (anchor.attribute("title") if anchor else "")
                            or node.text
                            or ""
                        ).strip(),
                        "code": str(
                            (checkbox.attribute("value") if checkbox else "") or ""
                        ).strip(),
                        "checked": bool(checkbox.checked) if checkbox else False,
                    }
                )
            return snapshot
        if "option.textContent" in script and "option.value" in script:
            wanted = str(arg or "").strip().casefold()
            return [
                str(node.attribute("value") or "").strip()
                for node in self._nodes
                if wanted
                in {
                    str(node.text or "").strip().casefold(),
                    str(node.attribute("value") or "").strip().casefold(),
                }
            ]
        if "value: element.value, checked: element.checked" in script:
            return [
                {"value": node.attribute("value") or "", "checked": node.checked}
                for node in self._nodes
            ]
        if "filter(element => element.checked)" in script:
            for node in self._nodes:
                if node.checked:
                    node.click()
            return None
        if "values.includes(String(element.value))" in script:
            wanted = {str(value) for value in (arg or ())}
            for node in self._nodes:
                if str(node.attribute("value") or "") in wanted and not node.checked:
                    node.click()
            return None
        if ".all_inner_texts" in script:
            return [node.text for node in self._nodes]
        wants_id = "wantedId" in script
        wants_enabled = "':disabled'" in script
        checks_visibility = "getBoundingClientRect" in script
        if not checks_visibility:
            raise AssertionError(f"mini_dom chưa hỗ trợ evaluate_all: {script[:140]}")
        indexes = []
        for index, node in enumerate(self._nodes):
            if wants_id and node.attribute("id") != str(arg):
                continue
            if not node.visible:
                continue
            if wants_enabled and not node.enabled:
                continue
            indexes.append(index)
        return indexes

    @property
    def node(self) -> Element:
        return self._node

    @property
    def _node(self) -> Element:
        if not self._nodes:
            raise PlaywrightError(f"Locator không khớp phần tử nào: {self.selector}")
        return self._nodes[0]

    # --- ủy nhiệm --------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._node, name)


class MiniFrame:
    """Frame chạy trên một cây Element, cộng thêm map xpath và script."""

    def __init__(
        self,
        root: Element,
        *,
        url: str = "https://wfx.test/WFX_Costing.aspx",
        name: str = "",
        clock: Any = None,
        xpaths: dict[str, Sequence[Element]] | None = None,
        scripts: dict[str, Any] | None = None,
        page: Any = None,
    ) -> None:
        self.root = root
        # Frame resolve từ một document bọc ngoài, nên `locator("body")` tìm
        # thấy chính root — đúng như trình duyệt, nơi `body` là một phần tử.
        self._document = Element("#document", children=[root])
        self.page = page
        self.url = url
        self.name = name
        self.clock = clock
        self.xpaths = {key: list(value) for key, value in (xpaths or {}).items()}
        self.scripts = dict(scripts or {})
        self.detached = False
        self.evaluated: list[str] = []
        self.markers: dict[str, str] = {}

    def is_detached(self) -> bool:
        return self.detached

    def wait_for_timeout(self, milliseconds: float) -> None:
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)

    def locator(self, selector: str) -> Locator:
        # Playwright tự nhận diện selector bắt đầu bằng `//` hoặc `/html` là
        # xpath, không cần tiền tố `xpath=`.
        if selector.startswith(("xpath=", "//", "/html")):
            key = selector.removeprefix("xpath=")
            if key in self.xpaths:
                return Locator(self.xpaths[key], selector)
            # `//*[@id="0"]/li[3]` là xpath vị trí: con thứ 3 (1-based) đúng
            # tag, tính trên cây thật — không phải một khóa test khai báo sẵn.
            positional = re.fullmatch(
                r'//\*\[@id="([^"]+)"\]/([A-Za-z]+)\[(\d+)\]', key
            )
            if positional is not None:
                parent = next(
                    (
                        node
                        for node in self._document.descendants()
                        if node.id == positional.group(1)
                    ),
                    None,
                )
                if parent is None:
                    return Locator([], selector)
                same_tag = [
                    child
                    for child in parent.children
                    if child.tag == positional.group(2)
                ]
                index = int(positional.group(3)) - 1
                if 0 <= index < len(same_tag):
                    return Locator([same_tag[index]], selector)
                return Locator([], selector)
            raise AssertionError(f"MiniFrame chưa khai báo xpath: {key}")
        return Locator(_resolve([self._document], selector), selector)

    def evaluate(self, script: str, arg: Any = None) -> Any:
        self.evaluated.append(script)
        for marker, value in self.scripts.items():
            if marker in script:
                return value(arg) if callable(value) else value
        # Marker document: automation ghi rồi đọc lại để biết frame đã reload.
        for name in (
            "__wfxArticleFileMarker",
            "__wfxAutomationDocumentMarker",
            "__wfxPanelDocumentMarker",
        ):
            if name not in script:
                continue
            if "=" in script.split(name, 1)[1][:4]:
                self.markers[name] = str(arg)
                return None
            return self.markers.get(name, "")
        if "GetObjGrid" in script:
            # `typeof GetObjGrid === 'function' ? ... : []` — trang nào không
            # có API grid của WFX thì đoạn JS trả mảng rỗng, không ném lỗi.
            return []
        raise AssertionError(f"MiniFrame chưa hỗ trợ script: {script[:160]}")


def element(tag: str = "div", **kwargs: Any) -> Element:
    """Cú pháp gọn cho test."""
    return Element(tag, **kwargs)


def row(css_class: str, *children: Element, **kwargs: Any) -> Element:
    return Element("tr", css_class=css_class, children=children, **kwargs)


def grid(id: str, rows: Iterable[Element], **kwargs: Any) -> Element:
    body = Element("tbody", children=list(rows))
    return Element("table", id=id, children=[body], **kwargs)
