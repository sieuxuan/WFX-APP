"""Indent List và User Indent dùng chung TOÀN BỘ selector.

Hai module này cùng grid `gridMOLList`, cùng bốn ô filter, cùng context field.
Khác với cặp Supplier/Expense Inv — nơi bộ cột filter riêng còn phân biệt được —
ở đây `_frame_has_every_search_field` không phân biệt được gì cả: dấu hiệu duy
nhất là `<title>` của frame. Vì vậy phần này cần test hành vi thật, không chỉ
test riêng hàm so tiêu đề.
"""

from __future__ import annotations

import pytest

from wfx_panel import constants
from wfx_panel.automation import modules
from wfx_panel.automation.search_specs import INDENT_SEARCH_SPECS

INDENT_FIELD_SELECTORS = (
    "#gridMOLList_tblGridHeader_trSearch_td_ColSupplier input#txtSupplier",
    "#gridMOLList_tblGridHeader_trSearch_td_ColArticle input#txtArticle",
    "#gridMOLList_tblGridHeader_trSearch_td_ColIndentNo input#txtIndentNo",
    "#gridMOLList_tblGridHeader_trSearch_td_ColStyle input#txtStyle",
    "#gridMOLList_tblGridHeader_trSearch_td_ColIndentNo",
)


class _IndentFrame:
    """Frame giả: mọi selector Indent đều có, chỉ `<title>` là khác nhau."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.url = "https://wfx.example/WFXIndentList.aspx"

    def locator(self, selector: str):
        if selector == "title":
            return _Nodes([self.title])
        present = any(
            token.strip() in INDENT_FIELD_SELECTORS
            for token in selector.split(",")
        )
        return _Nodes([self.title] if present else [])

    def evaluate(self, _script):
        return self.title


class _Nodes:
    def __init__(self, values: list[str]) -> None:
        self.values = values

    def count(self) -> int:
        return len(self.values)

    @property
    def first(self):
        value = self.values[0]

        class _Node:
            def is_visible(self_inner) -> bool:
                return True

            def is_enabled(self_inner) -> bool:
                return True

            def text_content(self_inner, timeout=None) -> str:
                return value

        return _Node()


def _page(monkeypatch, frames):
    monkeypatch.setattr(modules, "MODULE_CONTEXT_PROBE_SECONDS", 0.05)
    monkeypatch.setattr(modules, "_wait", lambda *_a, **_k: None)

    class _Page:
        def __init__(self) -> None:
            self.frames = list(frames)

    return _Page()


def test_the_two_indent_modules_are_declared_with_identical_filters():
    """Nếu một ngày hai spec khác nhau thì nhận diện theo tiêu đề không còn là
    điểm yếu duy nhất — test này sẽ nhắc cập nhật lại lập luận ở đây."""
    indent = INDENT_SEARCH_SPECS["Indent List"]
    user_indent = INDENT_SEARCH_SPECS["User Indent"]

    assert indent.fields is user_indent.fields
    assert indent.context_field.selectors == user_indent.context_field.selectors
    assert indent.foreign_markers == user_indent.foreign_markers == ()


@pytest.mark.parametrize(
    ("module_name", "module_id", "open_title"),
    [
        ("User Indent", "user_indent_list", "Indent List"),
        ("Indent List", "0005_0080_0020", "User Indent List"),
    ],
)
def test_search_opens_its_own_list_instead_of_the_other_indent(
    monkeypatch, module_name, module_id, open_title
):
    """Đang mở màn Indent kia thì phải tự click đúng menu của mình."""
    wanted_title = (
        "User Indent List" if module_name == "User Indent" else "Indent List"
    )
    page = _page(monkeypatch, [_IndentFrame(open_title)])
    wanted = _IndentFrame(wanted_title)
    clicks = []

    def click_menu(_page, name, xpath, _log):
        clicks.append((name, xpath))
        page.frames = [_IndentFrame(open_title), wanted]

    monkeypatch.setattr(modules, "_click_module_menu_on_page", click_menu)

    frame = modules._open_multi_field_search_context(
        page,
        INDENT_SEARCH_SPECS[module_name],
        constants.MODULE_BY_ID[module_id]["xpath"],
        lambda _line: None,
    )

    assert frame is wanted
    assert clicks == [(module_name, constants.MODULE_BY_ID[module_id]["xpath"])]


@pytest.mark.parametrize("module_name", ["Indent List", "User Indent"])
def test_the_right_list_is_reused_without_clicking_the_menu_again(
    monkeypatch, module_name
):
    title = "User Indent List" if module_name == "User Indent" else "Indent List"
    open_frame = _IndentFrame(title)
    page = _page(monkeypatch, [open_frame])
    monkeypatch.setattr(
        modules,
        "_click_module_menu_on_page",
        lambda *_a: pytest.fail("Đã mở đúng List thì không được click lại"),
    )

    frame = modules._open_multi_field_search_context(
        page,
        INDENT_SEARCH_SPECS[module_name],
        constants.MODULE_BY_ID["0005_0080_0020"]["xpath"],
        lambda _line: None,
    )

    assert frame is open_frame


@pytest.mark.parametrize("module_name", ["Indent List", "User Indent"])
def test_a_frame_without_a_title_is_never_accepted(monkeypatch, module_name):
    """Tiêu đề là bằng chứng duy nhất; không đọc được thì không được đoán."""
    assert not modules._frame_matches_module_context(
        _IndentFrame(""), module_name
    )
