"""Tìm kết hợp nhiều điều kiện trên một màn List (Indent, Advance PR, Expense…).

CLAUDE.md: Search phải tự mở List khi context chưa sẵn sàng và KHÔNG được trả
`*_LIST_NOT_OPEN`; mọi filter cũ phải bị xóa trước khi điền để hai lần Search
không âm thầm kết hợp điều kiện.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation.modules.search as module_search
from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import FakeClock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError
from wfx_panel.automation.search_specs import (
    ADVANCE_PR_SEARCH_SPEC,
    EXPENSE_INVOICE_SEARCH_SPEC,
    INDENT_SEARCH_SPECS,
    SUPPLIER_INVOICE_SEARCH_SPEC,
)

XPATH = '//*[@id="0050_0020_0010"]/a'


@pytest.fixture
def clock():
    return FakeClock()


class Field:
    """Một ô search; `tag` quyết định đi nhánh input hay select."""

    def __init__(
        self,
        *,
        tag="INPUT",
        value="",
        selected_text="",
        select_errors=(),
        press_error=None,
        change_error=None,
        keeps_value=True,
    ):
        self.tag = tag
        self.value = value
        self.selected_text = selected_text
        self.select_errors = list(select_errors)
        self.press_error = press_error
        self.change_error = change_error
        self.keeps_value = keeps_value
        self.fills: list[str] = []
        self.typed: list[str] = []
        self.selects: list[dict] = []
        self.events: list[str] = []
        self.keys: list[str] = []

    def evaluate(self, script):
        if "tagName" in script:
            return self.tag
        return self.selected_text

    def fill(self, value, **_kwargs):
        self.fills.append(value)
        self.value = value

    def type(self, value, **_kwargs):
        self.typed.append(value)
        if self.keeps_value:
            self.value = value

    def select_option(self, **kwargs):
        self.selects.append(dict(kwargs))
        # Lỗi chỉ mô phỏng lúc chọn giá trị thật; `select_option(value="")` của
        # bước xóa filter luôn đi qua được.
        if kwargs.get("value") and self.select_errors:
            error = self.select_errors.pop(0)
            if error is not None:
                raise error
        if self.keeps_value and "value" in kwargs:
            self.value = kwargs["value"]

    def input_value(self, **_kwargs):
        return self.value

    def dispatch_event(self, event, **_kwargs):
        if self.change_error is not None:
            raise self.change_error
        self.events.append(event)

    def press(self, key, **_kwargs):
        if self.press_error is not None:
            raise self.press_error
        self.keys.append(key)


def _spec():
    return INDENT_SEARCH_SPECS["Indent List"]


def _fields(spec, **overrides):
    fields = {name: Field() for name in spec.fields}
    fields.update(overrides)
    return fields


def _wire(monkeypatch, clock, fields, **overrides):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, module_search, world)
    defaults = {
        "_open_multi_field_search_context": lambda *_a, **_k: "frame",
        "_resolve_multi_search_fields": lambda *_a, **_k: fields,
        "_wait_module_search_settled": lambda *_a, **_k: None,
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        patch_automation(monkeypatch, module_search, name, value)
    return world


def _run(spec, values, log=None):
    return module_search._search_module_fields(
        spec, XPATH, values, log or (lambda _line: None)
    )


# --- kiểm tra điều kiện -------------------------------------------------


def test_a_search_without_any_condition_lists_every_field_it_accepts(
    monkeypatch, clock
):
    spec = _spec()
    world = _wire(monkeypatch, clock, _fields(spec))

    result = _run(spec, dict.fromkeys(spec.fields, "   "))

    assert result["code"] == "QUERY_REQUIRED"
    for field_spec in spec.fields.values():
        assert field_spec.label in result["message"]
    assert world.driver_starts == 0


def test_only_the_conditions_the_user_filled_are_applied(monkeypatch, clock):
    spec = _spec()
    fields = _fields(spec)
    _wire(monkeypatch, clock, fields)
    first, second = list(spec.fields)[:2]
    lines: list[str] = []

    result = _run(spec, {first: " PSHK ", second: "F0001"}, lines.append)

    assert result["code"] == "MODULE_SEARCH_APPLIED"
    assert result["filter_kinds"] == [first, second]
    assert fields[first].typed == ["PSHK"]
    assert fields[second].typed == ["F0001"]
    # Ô không nhập vẫn phải được xóa trắng.
    for name in list(spec.fields)[2:]:
        assert fields[name].fills == [""]


def test_every_field_is_cleared_before_anything_is_typed(monkeypatch, clock):
    spec = _spec()
    order: list[tuple[str, str]] = []

    class Tracking(Field):
        def __init__(self, name):
            super().__init__()
            self.name = name

        def fill(self, value, **kwargs):
            order.append(("clear", self.name))
            super().fill(value, **kwargs)

        def type(self, value, **kwargs):
            order.append(("type", self.name))
            super().type(value, **kwargs)

    fields = {name: Tracking(name) for name in spec.fields}
    _wire(monkeypatch, clock, fields)
    first = next(iter(spec.fields))

    _run(spec, {first: "PSHK"})

    assert [action for action, _name in order] == ["clear"] * len(
        spec.fields
    ) + ["type"]


def test_a_dropdown_condition_is_selected_by_value_then_confirmed(
    monkeypatch, clock
):
    spec = EXPENSE_INVOICE_SEARCH_SPEC
    name = next(iter(spec.fields))
    field = Field(tag="SELECT")
    fields = _fields(spec, **{name: field})
    _wire(monkeypatch, clock, fields)

    assert _run(spec, {name: "Open"})["code"] == "MODULE_SEARCH_APPLIED"
    assert field.selects[-1] == {"value": "Open"}


def test_a_dropdown_that_only_matches_by_label_is_still_accepted(
    monkeypatch, clock
):
    spec = EXPENSE_INVOICE_SEARCH_SPEC
    name = next(iter(spec.fields))
    field = Field(
        tag="SELECT",
        selected_text="  Open  ",
        select_errors=[PlaywrightError("không có option value")],
        keeps_value=False,
    )
    fields = _fields(spec, **{name: field})
    _wire(monkeypatch, clock, fields)

    assert _run(spec, {name: "open"})["code"] == "MODULE_SEARCH_APPLIED"
    assert field.selects[-1] == {"label": "open"}


def test_a_value_wfx_silently_drops_stops_the_search(monkeypatch, clock):
    spec = _spec()
    name = next(iter(spec.fields))
    fields = _fields(spec, **{name: Field(keeps_value=False)})
    _wire(monkeypatch, clock, fields)
    lines: list[str] = []

    result = _run(spec, {name: "PSHK"}, lines.append)

    assert result["code"] == "MODULE_SEARCH_NOT_CONFIRMED"
    assert "chưa xác nhận" in result["message"]
    assert result["module"] == spec.module_name


# --- xóa filter cũ ------------------------------------------------------


def test_a_dropdown_without_an_empty_option_falls_back_to_the_first_one():
    field = Field(tag="SELECT")

    def refuse_empty(**kwargs):
        Field.select_option(field, **kwargs)
        if kwargs.get("value") == "":
            raise PlaywrightError("không có option rỗng")

    field.select_option = refuse_empty

    module_search._clear_multi_search_fields({"status": field})

    assert field.selects == [{"value": ""}, {"index": 0}]


def test_a_field_that_refuses_the_change_event_does_not_stop_clearing():
    field = Field(change_error=PlaywrightError("node đã bị thay"))

    module_search._clear_multi_search_fields({"supplier": field})

    assert field.fills == [""]
    assert field.events == []


# --- gửi Search ---------------------------------------------------------


def test_nothing_is_submitted_when_no_field_was_filled():
    module_search._submit_multi_search(None)


def test_the_last_field_gets_enter_then_a_change_event():
    field = Field()

    module_search._submit_multi_search(field)

    assert field.keys == ["Enter"]
    assert field.events == ["change"]


def test_a_field_that_cannot_take_enter_still_gets_the_change_event():
    field = Field(press_error=PlaywrightError("ô đã mất focus"))

    module_search._submit_multi_search(field)

    assert field.keys == []
    assert field.events == ["change"]


def test_a_field_that_refuses_both_is_left_alone():
    field = Field(
        press_error=PlaywrightError("ô đã mất focus"),
        change_error=PlaywrightError("node đã bị thay"),
    )

    module_search._submit_multi_search(field)

    assert field.events == []


# --- lỗi của cả lượt ----------------------------------------------------


def test_the_search_fields_not_being_ready_is_told_apart_from_a_lost_result(
    monkeypatch, clock
):
    spec = _spec()

    def explode(*_args, **_kwargs):
        raise PlaywrightTimeoutError("Không thấy ô Supplier")

    _wire(
        monkeypatch,
        clock,
        _fields(spec),
        _resolve_multi_search_fields=explode,
    )
    lines: list[str] = []

    result = _run(spec, {next(iter(spec.fields)): "PSHK"}, lines.append)

    assert result["code"] == "MODULE_SEARCH_NOT_READY"
    assert "App đã tự mở" in result["message"]
    assert lines[-1] == result["message"]


def test_a_timeout_after_the_fields_were_found_is_a_confirmation_problem(
    monkeypatch, clock
):
    spec = _spec()

    def explode(*_args, **_kwargs):
        raise PlaywrightTimeoutError("grid chưa ổn định")

    _wire(
        monkeypatch,
        clock,
        _fields(spec),
        _wait_module_search_settled=explode,
    )

    result = _run(spec, {next(iter(spec.fields)): "PSHK"})

    assert result["code"] == "MODULE_SEARCH_NOT_CONFIRMED"
    assert "Đã nhập filter" in result["message"]


def test_an_unexpected_runtime_error_is_reported_as_a_search_failure(
    monkeypatch, clock
):
    spec = _spec()

    def explode(*_args, **_kwargs):
        raise RuntimeError("DIVISION_LOCKED")

    _wire(
        monkeypatch,
        clock,
        _fields(spec),
        _open_multi_field_search_context=explode,
    )
    lines: list[str] = []

    result = _run(spec, {next(iter(spec.fields)): "PSHK"}, lines.append)

    assert result["code"] == "MODULE_SEARCH_FAILED"
    assert "DIVISION_LOCKED" in result["message"]
    assert lines[-1] == result["message"]


def test_an_unexpected_error_names_its_type(monkeypatch, clock):
    spec = _spec()

    def explode(*_args, **_kwargs):
        raise ValueError("selector lạ")

    _wire(
        monkeypatch,
        clock,
        _fields(spec),
        _open_multi_field_search_context=explode,
    )

    result = _run(spec, {next(iter(spec.fields)): "PSHK"})

    assert result["code"] == "MODULE_SEARCH_FAILED"
    assert "ValueError: selector lạ" in result["message"]


@pytest.mark.parametrize(
    ("chrome_ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_the_browser_boundary_codes_keep_the_module_name(
    monkeypatch, clock, chrome_ready, logged_in, expected
):
    spec = _spec()
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(
        monkeypatch,
        module_search,
        world,
        chrome_ready=chrome_ready,
        logged_in=logged_in,
    )

    result = _run(spec, {next(iter(spec.fields)): "PSHK"})

    assert result["code"] == expected
    assert result["module"] == spec.module_name


# --- các entry point mỏng ----------------------------------------------


def _capture(monkeypatch):
    seen: list[tuple] = []
    patch_automation(
        monkeypatch,
        module_search,
        "_search_module_fields",
        lambda spec, xpath, values, _log: (
            seen.append((spec, xpath, dict(values))) or {"ok": True}
        ),
    )
    return seen


def test_an_unknown_indent_module_is_refused_without_opening_anything(
    monkeypatch
):
    seen = _capture(monkeypatch)

    result = module_search.search_indent_list(
        XPATH, "Khong Ton Tai", "A", "B", "C", "D"
    )

    assert result["code"] == "INVALID_FILTER"
    assert seen == []


def test_the_indent_entry_point_passes_all_four_conditions(monkeypatch):
    seen = _capture(monkeypatch)

    module_search.search_indent_list(
        XPATH, "Indent List", "PSHK", "F0001", "IND-1", "ACEL"
    )

    assert seen[0][0] is INDENT_SEARCH_SPECS["Indent List"]
    assert set(seen[0][2].values()) == {"PSHK", "F0001", "IND-1", "ACEL"}


def test_the_advance_pr_entry_point_uses_its_own_spec(monkeypatch):
    seen = _capture(monkeypatch)

    module_search.search_advance_pr_list(XPATH, "B", "S", "INV", "OC")

    assert seen[0][0] is ADVANCE_PR_SEARCH_SPEC
    assert seen[0][2] == {
        "buyer": "B",
        "supplier": "S",
        "invoice_no": "INV",
        "order_no": "OC",
    }


def test_supplier_and_expense_invoice_never_share_a_spec(monkeypatch):
    """Hai màn dùng chung `#txtSupplier`; chỉ bộ cột filter phân biệt được."""
    seen = _capture(monkeypatch)

    module_search.search_supplier_invoice_list(XPATH, "S", "INV", "PO", "ASN")
    module_search.search_expense_invoice_list(XPATH, "S", "INV", "U", "Open")

    assert seen[0][0] is SUPPLIER_INVOICE_SEARCH_SPEC
    assert seen[1][0] is EXPENSE_INVOICE_SEARCH_SPEC
    assert set(seen[0][2]) != set(seen[1][2])


def test_the_oc_and_sale_asn_entry_points_use_the_single_field_search(
    monkeypatch,
):
    from wfx_panel.automation.search_specs import (
        OC_SEARCH_SPEC,
        SALE_ASN_SEARCH_SPEC,
    )

    seen: list[tuple] = []
    patch_automation(
        monkeypatch,
        module_search,
        "_search_module_list",
        lambda spec, xpath, kind, query, _log: (
            seen.append((spec, kind, query)) or {"ok": True}
        ),
    )

    module_search.search_oc_list(XPATH, "oc_no", "OC-1")
    module_search.search_sale_asn_list(XPATH, "invoice_no", "INV-1")

    assert seen[0][0] is OC_SEARCH_SPEC
    assert seen[1][0] is SALE_ASN_SEARCH_SPEC
    assert [item[2] for item in seen] == ["OC-1", "INV-1"]


# --- xóa filter cũ trên AG Grid cuộn ngang ------------------------------


class GridInput:
    def __init__(
        self, *, value="", visible=True, enabled=True, error=None, change_error=None
    ):
        self.value = value
        self.visible = visible
        self.enabled = enabled
        self.error = error
        self.change_error = change_error
        self.fills: list[str] = []
        self.events: list[str] = []

    def is_visible(self):
        return self.visible

    def is_enabled(self):
        return self.enabled

    def input_value(self, **_kwargs):
        if self.error is not None:
            raise self.error
        return self.value

    def fill(self, value, **_kwargs):
        self.fills.append(value)
        self.value = value

    def dispatch_event(self, event, **_kwargs):
        if self.change_error is not None:
            raise self.change_error
        self.events.append(event)


class GridRoot:
    def __init__(self, *, visible=True, state=None, error=None):
        self.visible = visible
        self.state = state or {"current": 0, "maximum": 0, "viewport": 0}
        self.error = error
        self.scrolled: list[int] = []

    def is_visible(self):
        if self.error is not None:
            raise self.error
        return self.visible


class ListLocator:
    def __init__(self, items):
        self.items = list(items)

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class ListFrame:
    def __init__(self, inputs, roots=(), clock=None):
        self.inputs = list(inputs)
        self.roots = list(roots)
        self.clock = clock

    def locator(self, selector):
        if selector == ".ag-root-wrapper":
            return ListLocator(self.roots)
        return ListLocator(self.inputs)

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


def test_only_filters_that_actually_hold_a_value_are_cleared():
    filled = GridInput(value="CŨ")
    empty = GridInput()
    hidden = GridInput(value="X", visible=False)
    disabled = GridInput(value="X", enabled=False)
    broken = GridInput(value="X", error=PlaywrightError("node đã bị thay"))
    # WFX đôi khi tháo node ngay sau khi nhận `fill`; giá trị đã xóa vẫn tính.
    no_change = GridInput(
        value="X", change_error=PlaywrightError("node đã bị thay")
    )
    frame = ListFrame([filled, empty, hidden, disabled, broken, no_change])

    module_search._clear_list_search_fields(frame, ("input",))

    assert filled.fills == [""]
    assert filled.events == ["change"]
    assert empty.fills == []
    assert hidden.fills == []
    assert disabled.fills == []
    assert broken.fills == []
    assert no_change.fills == [""]
    assert no_change.events == []


def test_clearing_stops_at_the_viewport_unless_a_horizontal_scan_is_asked_for(
    clock, monkeypatch
):
    root = GridRoot(state={"current": 0, "maximum": 600, "viewport": 400})
    frame = ListFrame([GridInput(value="CŨ")], [root], clock=clock)

    module_search._clear_list_search_fields(frame, ("input",))

    assert root.scrolled == []


def test_a_horizontal_scan_clears_filters_hidden_outside_the_viewport(
    clock, monkeypatch
):
    root = GridRoot(state={"current": 240, "maximum": 600, "viewport": 400})
    filled = GridInput(value="CŨ")
    frame = ListFrame([filled], [root], clock=clock)
    patch_automation(
        monkeypatch,
        module_search,
        "_horizontal_grid_state",
        lambda target: target.state,
    )
    patch_automation(
        monkeypatch,
        module_search,
        "_scroll_horizontal_grid",
        lambda target, position: target.scrolled.append(position),
    )

    module_search._clear_list_search_fields(
        frame, ("input",), scan_horizontal=True
    )

    # Quét hết các vị trí rồi trả grid về đúng chỗ người dùng đang xem.
    assert root.scrolled[0] == 240
    assert root.scrolled[-1] == 240
    assert len(root.scrolled) > 2


def test_a_grid_that_is_hidden_or_broken_is_skipped_during_the_scan(
    clock, monkeypatch
):
    hidden = GridRoot(visible=False)
    broken = GridRoot(error=PlaywrightError("grid đã bị dispose"))
    frame = ListFrame([GridInput(value="CŨ")], [hidden, broken], clock=clock)
    patch_automation(
        monkeypatch,
        module_search,
        "_scroll_horizontal_grid",
        lambda target, position: pytest.fail("không được cuộn grid đã hỏng"),
    )

    module_search._clear_list_search_fields(
        frame, ("input",), scan_horizontal=True
    )


# --- tự mở List khi context chưa sẵn sàng -------------------------------


def test_a_list_that_is_not_open_yet_is_opened_by_the_search_itself(
    monkeypatch, clock
):
    """CLAUDE.md: Search không được trả `*_LIST_NOT_OPEN`, phải tự mở List."""
    from wfx_panel.automation.search_specs import SALE_ASN_SEARCH_SPEC

    spec = SALE_ASN_SEARCH_SPEC
    attempts: list[float] = []
    opened: list[str] = []

    def probe(_page, _selectors, _aliases, *, timeout_s, **_kwargs):
        attempts.append(timeout_s)
        if len(attempts) == 1:
            raise PlaywrightTimeoutError("chưa thấy context")
        return "frame-moi", "context-field"

    patch_automation(monkeypatch, module_search, "_search_input_in_frames", probe)
    patch_automation(
        monkeypatch,
        module_search,
        "_click_module_menu_on_page",
        lambda _page, name, _xpath, _log: opened.append(name),
    )
    patch_automation(
        monkeypatch, module_search, "_mark_grid_roots", lambda _page: ["grid-cu"]
    )
    shown: list[list[str]] = []
    patch_automation(
        monkeypatch,
        module_search,
        "_show_module_floating_filter",
        lambda _page, _log, previous, **_kwargs: shown.append(list(previous)),
    )
    lines: list[str] = []

    frame = module_search._open_list_search_context(
        FakePage(clock), spec, XPATH, lines.append
    )

    assert frame == "frame-moi"
    assert opened == [spec.module_name]
    assert shown == [["grid-cu"]], "Floating Filter phải bật trên grid mới"
    assert attempts[1] == 30
    assert any("đang tự mở List" in line for line in lines)
