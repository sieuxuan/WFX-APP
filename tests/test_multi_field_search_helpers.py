"""Bốn helper điền filter dùng chung của mọi form Search nhiều điều kiện.

Indent List, User Indent, Advance PR, Supplier Inv và Expense Inv đều đi qua
đúng `_resolve` → `_clear` → `_fill` → `_submit`. Trước đây cả bốn ở mức chưa
được test, dù chúng giữ hai ràng buộc của CLAUDE.md:

* xóa filter cũ ở TẤT CẢ các ô, không chỉ ô đang nhập, để hai lần Search không
  âm thầm kết hợp điều kiện;
* chỉ đi tiếp khi WFX xác nhận đúng giá trị vừa nhập.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from wfx_panel.automation import modules
from wfx_panel.automation.search_specs import (
    EXPENSE_INVOICE_SEARCH_SPEC,
    INDENT_SEARCH_SPECS,
)

INDENT_SPEC = INDENT_SEARCH_SPECS["Indent List"]


class _Field:
    """Ô filter giả: input text hoặc select, ghi lại mọi thao tác."""

    def __init__(
        self,
        *,
        tag: str = "INPUT",
        visible: bool = True,
        enabled: bool = True,
        value: str = "",
        option_text: str = "",
        reject_value: bool = False,
    ) -> None:
        self.tag = tag
        self.visible = visible
        self.enabled = enabled
        self.value = value
        self.option_text = option_text
        self.reject_value = reject_value
        self.events: list[str] = []
        self.typed: list[str] = []
        self.keys: list[str] = []

    def is_visible(self) -> bool:
        return self.visible

    def is_enabled(self) -> bool:
        return self.enabled

    def evaluate(self, script):
        if "tagName" in script:
            return self.tag
        if "selectedOptions" in script:
            return self.option_text
        raise AssertionError(f"Script chưa khai báo: {script}")

    def fill(self, value):
        self.value = value

    def type(self, value, delay=None):
        self.typed.append(value)
        self.value = "" if self.reject_value else value

    def select_option(self, value=None, label=None, index=None):
        if value is not None:
            self.value = value
        elif label is not None:
            self.value = label
        else:
            self.value = ""

    def input_value(self, timeout=None):
        return self.value

    def dispatch_event(self, name):
        self.events.append(name)

    def press(self, key, timeout=None):
        self.keys.append(key)


class _Frame:
    def __init__(self, fields: dict[str, _Field]) -> None:
        self.fields = fields

    def locator(self, selector: str):
        for key, field in self.fields.items():
            if key in selector:
                return _Candidates([field])
        return _Candidates([])


class _Candidates:
    def __init__(self, items) -> None:
        self.items = items

    def count(self) -> int:
        return len(self.items)

    @property
    def first(self):
        return self.items[0]


def _indent_frame(**overrides) -> _Frame:
    fields = {
        "txtSupplier": _Field(),
        "txtArticle": _Field(),
        "txtIndentNo": _Field(),
        "txtStyle": _Field(),
    }
    fields.update(overrides)
    return _Frame(fields)


# --- resolve ------------------------------------------------------------


def test_every_declared_field_must_be_present():
    resolved = modules._resolve_multi_search_fields(_indent_frame(), INDENT_SPEC)

    assert set(resolved) == set(INDENT_SPEC.fields)


@pytest.mark.parametrize("broken", [{"visible": False}, {"enabled": False}])
def test_a_field_that_is_hidden_or_disabled_stops_the_search(broken):
    frame = _indent_frame(txtStyle=_Field(**broken))

    with pytest.raises(PlaywrightTimeoutError) as error:
        modules._resolve_multi_search_fields(frame, INDENT_SPEC)

    assert "Style" in str(error.value)
    assert "Indent List" in str(error.value)


# --- clear --------------------------------------------------------------


def test_clearing_touches_every_field_not_just_the_one_being_typed():
    """Bỏ sót một ô là hai lần Search âm thầm cộng dồn điều kiện."""
    frame = _indent_frame()
    for field in frame.fields.values():
        field.value = "giá trị cũ"
    fields = modules._resolve_multi_search_fields(frame, INDENT_SPEC)

    modules._clear_multi_search_fields(fields)

    assert [field.value for field in frame.fields.values()] == [""] * 4
    assert all(field.events == ["change"] for field in frame.fields.values())


def test_clearing_a_dropdown_falls_back_to_the_first_option():
    class _PickySelect(_Field):
        def select_option(self, value=None, label=None, index=None):
            if value == "":
                raise PlaywrightError("WFX không có option rỗng")
            super().select_option(value=value, label=label, index=index)
            if index == 0:
                self.value = "__first__"

    field = _PickySelect(tag="SELECT", value="Open")
    modules._clear_multi_search_fields({"status": field})

    assert field.value == "__first__"


# --- fill ---------------------------------------------------------------


def test_only_the_active_fields_are_typed():
    frame = _indent_frame()
    fields = modules._resolve_multi_search_fields(frame, INDENT_SPEC)

    labels, last = modules._fill_multi_search_fields(
        fields,
        {"supplier": "", "article": "", "indent_no": "IND-9", "style": "ST-1"},
        ["indent_no", "style"],
        INDENT_SPEC,
        lambda _line: None,
    )

    assert labels == ["Indent No.", "Style"]
    assert last is frame.fields["txtStyle"]
    assert frame.fields["txtIndentNo"].typed == ["IND-9"]
    assert frame.fields["txtSupplier"].typed == []


def test_a_value_wfx_refuses_to_keep_stops_the_search():
    frame = _indent_frame(txtIndentNo=_Field(reject_value=True))
    fields = modules._resolve_multi_search_fields(frame, INDENT_SPEC)

    with pytest.raises(PlaywrightTimeoutError) as error:
        modules._fill_multi_search_fields(
            fields,
            {"indent_no": "IND-9"},
            ["indent_no"],
            INDENT_SPEC,
            lambda _line: None,
        )

    assert "Indent No." in str(error.value)


def test_a_dropdown_is_confirmed_by_its_selected_label():
    """Expense Inv có Status dạng select: value nội bộ khác text hiển thị."""
    status = _Field(tag="SELECT", option_text="Open")

    def select_by_label(value=None, label=None, index=None):
        if value is not None:
            raise PlaywrightError("option value không khớp")
        status.value = "1"

    status.select_option = select_by_label

    labels, last = modules._fill_multi_search_fields(
        {"status": status},
        {"status": "Open"},
        ["status"],
        EXPENSE_INVOICE_SEARCH_SPEC,
        lambda _line: None,
    )

    assert labels == ["Status"]
    assert last is status


# --- submit -------------------------------------------------------------


def test_submitting_presses_enter_on_the_last_field_filled():
    field = _Field()

    modules._submit_multi_search(field)

    assert field.keys == ["Enter"]
    assert field.events == ["change"]


def test_submitting_nothing_is_a_no_op():
    modules._submit_multi_search(None)


def test_a_field_that_refuses_enter_still_gets_a_change_event():
    """WFX vẫn lọc bằng onchange, nên Enter hỏng không được làm hỏng cả lượt."""
    field = _Field()

    def refuse(_key, timeout=None):
        raise PlaywrightError("không nhận phím")

    field.press = refuse
    modules._submit_multi_search(field)

    assert field.events == ["change"]
