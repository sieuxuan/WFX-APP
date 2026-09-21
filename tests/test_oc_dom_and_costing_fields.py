"""Hai lớp DOM dùng chung: toolbar/dropdown của OC và field/Save của Costing.

`wfx_panel/automation/oc/dom.py` (48%) và `wfx_panel/automation/costing/fields.py`
(43%) là nơi thi hành hai luật rất cụ thể của CLAUDE.md:

* "`ddlBuyer` và `ddlPackage` của WFX chỉ bind đủ option sau `mousedown`;
  automation phải dispatch sự kiện này, tìm option theo label/title exact và xác
  nhận lại control sau postback trước khi đi tiếp."
* "Costing tuyệt đối không click `#colBodyType label span`, `#imgDeleteSection`,
  `#imgEditSection` hoặc `#imgCopySection`."
* "Save Cost Sheet chỉ dùng
  `//*[@id=\"titlebarCostSheet\"]/tbody/tr/td[3]/span/div[1]`" — và một alert lỗi
  của WFX phải thành lỗi của app, không được coi là Save thành công.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.costing import fields as costing_fields
from wfx_panel.automation.costing.constants import FORBIDDEN_CONTROL_IDS
from wfx_panel.automation.oc import dom as oc_dom

SAVE_XPATH = '//*[@id="titlebarCostSheet"]/tbody/tr/td[3]/span/div[1]'
GRID_ID = "gridCostSheetDetail_tblGridContent"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, oc_dom, _common)


def _quiet():
    return lambda _line: None


class _Page:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.listeners: list[tuple] = []

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)

    def on(self, event, handler):
        self.listeners.append((event, handler))

    def remove_listener(self, event, handler):
        if (event, handler) in self.listeners:
            self.listeners.remove((event, handler))

    def fire_dialog(self, message):
        class Dialog:
            def __init__(self, text):
                self.message = text

            def accept(self):
                return None

        for event, handler in list(self.listeners):
            if event == "dialog":
                handler(Dialog(message))


# --- tìm control trong mọi frame -----------------------------------------


def test_the_first_usable_control_wins(clock):
    hidden = MiniFrame(
        Element("body", children=[element("input", id="ctl", visible=False)]),
        clock=clock,
    )
    good = MiniFrame(
        Element("body", children=[element("input", id="ctl")]), clock=clock
    )
    page = _Page(clock, [hidden, good])

    frame, control = oc_dom._visible_in_frames(page, "#ctl")

    assert frame is good
    assert control.get_attribute("id") == "ctl"


def test_a_disabled_control_is_never_returned(clock):
    frame = MiniFrame(
        Element("body", children=[element("input", id="ctl", enabled=False)]),
        clock=clock,
    )

    with pytest.raises(PlaywrightTimeoutError, match="#ctl"):
        oc_dom._visible_in_frames(_Page(clock, [frame]), "#ctl", timeout_s=1)


def test_an_attached_control_does_not_need_to_be_visible(clock):
    frame = MiniFrame(
        Element("body", children=[element("input", id="ctl", visible=False)]),
        clock=clock,
    )

    _frame, control = oc_dom._attached_in_frames(_Page(clock, [frame]), "#ctl")

    assert control.get_attribute("id") == "ctl"


def test_a_missing_attached_control_times_out(clock):
    frame = MiniFrame(Element("body"), clock=clock)

    with pytest.raises(PlaywrightTimeoutError):
        oc_dom._attached_in_frames(_Page(clock, [frame]), "#ctl", timeout_s=1)


def test_a_frame_that_throws_never_stops_the_scan(clock):
    class Broken:
        url = "https://wfx.test/x"

        def locator(self, _selector):
            raise PlaywrightError("frame rơi")

    good = MiniFrame(
        Element("body", children=[element("input", id="ctl")]), clock=clock
    )

    _frame, control = oc_dom._visible_in_frames(
        _Page(clock, [Broken(), good]), "#ctl"
    )

    assert control.get_attribute("id") == "ctl"


# --- toolbar --------------------------------------------------------------


def _toolbar_frame(clock, entries):
    children = [
        Element(
            entry.get("tag", "a"),
            css_class=entry.get("css_class", "ToolLink"),
            id=entry.get("id", ""),
            text=entry.get("text", ""),
            visible=entry.get("visible", True),
            enabled=entry.get("enabled", True),
            attrs=entry.get("attrs", {}),
        )
        for entry in entries
    ]
    return MiniFrame(Element("body", children=children), clock=clock)


def test_a_toolbar_link_is_matched_by_its_exact_label(clock):
    frame = _toolbar_frame(
        clock,
        [{"id": "import", "text": "Import"}, {"id": "process", "text": "Process"}],
    )

    _frame, link = oc_dom._toolbar_link(_Page(clock, [frame]), "process")

    assert link.get_attribute("id") == "process"


def test_a_toolbar_link_is_matched_by_a_contained_label(clock):
    frame = _toolbar_frame(clock, [{"id": "pp", "text": "  Process   Package  "}])

    _frame, link = oc_dom._toolbar_link(_Page(clock, [frame]), "Process Package")

    assert link.get_attribute("id") == "pp"


def test_a_button_with_a_value_attribute_is_matched(clock):
    frame = _toolbar_frame(
        clock,
        [
            {
                "tag": "input",
                "css_class": "",
                "id": "btn",
                "attrs": {"type": "button", "value": "Create Transaction"},
            }
        ],
    )

    _frame, link = oc_dom._toolbar_link(_Page(clock, [frame]), "Create Transaction")

    assert link.get_attribute("id") == "btn"


@pytest.mark.parametrize(
    "state", [{"visible": False}, {"enabled": False}]
)
def test_a_toolbar_link_the_user_could_not_press_is_skipped(clock, state):
    frame = _toolbar_frame(clock, [{"id": "import", "text": "Import", **state}])

    with pytest.raises(PlaywrightTimeoutError, match="Import"):
        oc_dom._toolbar_link(_Page(clock, [frame]), "Import", timeout_s=1)


def test_an_unknown_toolbar_label_times_out(clock):
    frame = _toolbar_frame(clock, [{"id": "import", "text": "Import"}])

    with pytest.raises(PlaywrightTimeoutError):
        oc_dom._toolbar_link(_Page(clock, [frame]), "Reject", timeout_s=1)


# --- chọn option exact ----------------------------------------------------


class _Select(Element):
    def __init__(self, options, *, accepts=True, value=""):
        super().__init__(
            "select",
            id="ddlBuyer",
            value=value,
            children=[
                element(
                    "option",
                    text=label,
                    attrs={"value": option_value, "title": title},
                )
                for label, option_value, title in options
            ],
        )
        self._accepts = accepts

    def select_option(self, value=None, timeout=None, **_kwargs):
        self.selected.append(str(value))
        if self._accepts:
            self.value = str(value)


def _select_world(clock, select):
    frame = MiniFrame(Element("body", children=[select]), clock=clock)
    handle = frame.locator("#ddlBuyer").first
    for name in ("select_option", "input_value", "selected", "dispatched"):
        setattr(handle, name, getattr(select, name))
    return _Page(clock, [frame]), frame


def test_the_dropdown_is_woken_with_mousedown_before_it_is_read(clock):
    select = _Select([("J.LINDEBERG", "7", "")])
    page, _frame = _select_world(clock, select)

    assert oc_dom._select_exact_option(page, "#ddlBuyer", "", "J.LINDEBERG", "Buyer") == "7"
    assert "mousedown" in select.dispatched


def test_an_option_is_matched_by_its_value_first(clock):
    select = _Select([("Khác", "1", ""), ("J.LINDEBERG", "2", "")])
    page, _frame = _select_world(clock, select)

    assert oc_dom._select_exact_option(page, "#ddlBuyer", "2", "bất kỳ", "Buyer") == "2"


def test_an_option_is_matched_by_its_title_when_the_label_differs(clock):
    select = _Select([("...", "9", "J.LINDEBERG")])
    page, _frame = _select_world(clock, select)

    assert oc_dom._select_exact_option(page, "#ddlBuyer", "", "j.lindeberg", "Buyer") == "9"


def test_an_option_already_selected_is_not_set_again(clock):
    select = _Select([("J.LINDEBERG", "7", "")], value="7")
    page, _frame = _select_world(clock, select)

    oc_dom._select_exact_option(page, "#ddlBuyer", "", "J.LINDEBERG", "Buyer")

    assert select.selected == []


def test_a_label_the_dropdown_never_offers_is_reported(clock):
    select = _Select([("PRO SPORTS", "1", "")])
    page, _frame = _select_world(clock, select)

    with pytest.raises(PlaywrightTimeoutError, match="không có lựa chọn"):
        oc_dom._select_exact_option(
            page, "#ddlBuyer", "", "J.LINDEBERG", "Buyer", timeout_s=1
        )


def test_an_option_wfx_refuses_to_keep_is_reported(clock):
    select = _Select([("J.LINDEBERG", "7", "")], accepts=False)
    page, _frame = _select_world(clock, select)

    with pytest.raises(PlaywrightTimeoutError, match="chưa xác nhận Buyer"):
        oc_dom._select_exact_option(
            page, "#ddlBuyer", "", "J.LINDEBERG", "Buyer", timeout_s=1
        )


def test_a_detached_frame_while_selecting_is_retried_not_raised(clock):
    select = _Select([("J.LINDEBERG", "7", "")], accepts=False)

    def refuse(value=None, timeout=None, **_kwargs):
        raise PlaywrightError("Frame was detached")

    select.select_option = refuse
    page, _frame = _select_world(clock, select)

    with pytest.raises(PlaywrightTimeoutError) as error:
        oc_dom._select_exact_option(
            page, "#ddlBuyer", "", "J.LINDEBERG", "Buyer", timeout_s=1
        )

    assert "Lỗi gần nhất" in str(error.value)


def test_any_other_select_failure_is_raised_straight_away(clock):
    select = _Select([("J.LINDEBERG", "7", "")], accepts=False)

    def refuse(value=None, timeout=None, **_kwargs):
        raise PlaywrightError("element is not a <select>")

    select.select_option = refuse
    page, _frame = _select_world(clock, select)

    with pytest.raises(PlaywrightTimeoutError):
        oc_dom._select_exact_option(
            page, "#ddlBuyer", "", "J.LINDEBERG", "Buyer", timeout_s=1
        )


# --- index field live -----------------------------------------------------


def test_the_field_index_is_keyed_case_insensitively():
    document = {
        "fields": [
            {
                "scope": "Item",
                "section_key": "S1",
                "item_key": "I1",
                "field_key": "ColUsage",
            },
            "không phải field",
        ]
    }

    index = costing_fields._live_field_index(document)

    assert list(index) == [("item", "s1", "i1", "colusage")]


# --- resolve control ------------------------------------------------------


def _costing_frame(*, rows=2, dom_id="txtUsage", visible=True):
    grid_rows = [
        Element(
            "tr",
            css_class="cssGridRowDataRowType",
            children=(
                [element("input", id=dom_id, visible=visible)] if index == 1 else []
            ),
        )
        for index in range(rows)
    ]
    grid = Element(
        "table", id=GRID_ID, children=[Element("tbody", children=grid_rows)]
    )
    return MiniFrame(Element("body", children=[grid]))


def _field(**live):
    return {
        "scope": "item",
        "section_key": "s1",
        "item_key": "i1",
        "field_key": "colUsage",
        "_live": {"dom_id": "txtUsage", "region": "grid", "row_index": 1, **live},
    }


def test_a_grid_field_is_resolved_inside_its_own_row():
    frame = _costing_frame()

    control = costing_fields._resolve_live_field(frame, _field())

    assert control.get_attribute("id") == "txtUsage"


def test_a_field_outside_the_grid_is_resolved_on_the_frame():
    frame = MiniFrame(
        Element("body", children=[element("input", id="txtHeader")])
    )

    control = costing_fields._resolve_live_field(
        frame, _field(dom_id="txtHeader", region="header")
    )

    assert control.get_attribute("id") == "txtHeader"


@pytest.mark.parametrize("dom_id", sorted(FORBIDDEN_CONTROL_IDS))
def test_every_forbidden_control_is_refused(dom_id):
    frame = _costing_frame(dom_id=dom_id)

    with pytest.raises(RuntimeError, match="COSTING_FORBIDDEN_CONTROL"):
        costing_fields._resolve_live_field(frame, _field(dom_id=dom_id))


def test_a_forbidden_click_target_is_refused_even_with_a_safe_dom_id():
    forbidden = sorted(FORBIDDEN_CONTROL_IDS)[0]
    frame = _costing_frame()

    with pytest.raises(RuntimeError, match="COSTING_FORBIDDEN_CONTROL"):
        costing_fields._resolve_live_field(
            frame, _field(dom_id="txtUsage", click_dom_id=f"{forbidden}~")
        )


def test_a_field_without_a_visible_grid_is_detached():
    frame = MiniFrame(Element("body"))

    with pytest.raises(RuntimeError, match="COSTING_FIELD_DETACHED"):
        costing_fields._resolve_live_field(frame, _field())


def test_a_row_index_outside_the_grid_is_detached():
    frame = _costing_frame()

    with pytest.raises(RuntimeError, match="COSTING_FIELD_DETACHED"):
        costing_fields._resolve_live_field(frame, _field(row_index=99))


# --- ghi field ------------------------------------------------------------


def test_a_select_field_is_set_with_its_option_value():
    control = Element(
        "select",
        id="ddlUsage",
        children=[element("option", text="Pcs", attrs={"value": "1"})],
    )
    grid_row = Element("tr", css_class="cssGridRowDataRowType", children=[control])
    frame = MiniFrame(
        Element(
            "body",
            children=[
                Element(
                    "table",
                    id=GRID_ID,
                    children=[
                        Element(
                            "tbody",
                            children=[Element("tr"), grid_row],
                        )
                    ],
                )
            ],
        )
    )
    field = {
        **_field(dom_id="ddlUsage", tag="select"),
        "options": ["Pcs"],
        "_live": {
            "dom_id": "ddlUsage",
            "region": "grid",
            "row_index": 1,
            "tag": "select",
            "option_values": ["1"],
        },
    }

    costing_fields._set_live_field(frame, field, "Pcs")

    assert control.selected == ["1"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("true", True), ("Có", True), ("x", True), ("0", False), ("", False)],
)
def test_a_checkbox_field_reads_every_truthy_spelling(value, expected):
    frame = _costing_frame(dom_id="chkFlag")
    control = frame.locator("#chkFlag").node
    control.set_checked = lambda checked: setattr(control, "checked", checked)
    field = _field(dom_id="chkFlag", tag="input", input_type="checkbox")

    costing_fields._set_live_field(frame, field, value)

    assert control.checked is expected


def test_a_text_field_is_filled_then_blurred_with_tab():
    frame = _costing_frame()
    field = _field(tag="input", input_type="text")

    costing_fields._set_live_field(frame, field, 5)

    control = frame.locator("#txtUsage").node
    assert control.fills == ["5"]
    assert control.keys == ["Tab"]


def test_a_none_value_clears_a_text_field():
    frame = _costing_frame()

    costing_fields._set_live_field(
        frame, _field(tag="input", input_type="text"), None
    )

    assert frame.locator("#txtUsage").node.fills == [""]


def test_a_label_field_goes_through_the_wfx_inline_editor(monkeypatch):
    frame = _costing_frame(dom_id="lblUsage")
    edits: list[tuple] = []
    monkeypatch.setattr(
        costing_fields,
        "_edit_wfx_label",
        lambda _frame, _control, _field, value: edits.append(value),
    )

    costing_fields._set_live_field(frame, _field(dom_id="lblUsage", tag="span"), "5")

    assert edits == ["5"]


# --- so sánh giá trị ------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "expected", "data_type", "matches"),
    [
        ("5.00", "5", "number", True),
        ("5", "5.0", "decimal", True),
        ("abc", "5", "number", False),
        (" Pcs ", "Pcs", "text", True),
        (None, "", "text", True),
        ("5", "6", "number", False),
    ],
)
def test_value_comparison_follows_the_declared_data_type(
    actual, expected, data_type, matches
):
    assert (
        costing_fields._field_value_matches(actual, expected, data_type) is matches
    )


# --- thứ tự áp field ------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "priority"),
    [
        ({"field_key": "colMaterialColorList"}, 10),
        ({"field_key": "colMaterialSizeList"}, 10),
        ({"field_key": "colColorDependency"}, 10),
        ({"field_key": "colMinutes"}, 15),
        ({"field_key": "colProductionValue"}, 20),
        ({"field_key": "colSupplier"}, 25),
        ({"field_key": "colDeliveryTerm"}, 30),
        ({"field_key": "colCurrency"}, 30),
        ({"field_key": "colRate", "label": "Rate"}, 50),
        ({"field_key": "colPrice"}, 50),
        ({"field_key": "colUsage"}, 40),
    ],
)
def test_dependent_fields_are_applied_in_the_safe_wfx_order(field, priority):
    assert costing_fields._field_application_priority(field) == priority


def test_rate_must_stand_alone_before_it_delays_a_field():
    """`Corporate`/`Generate` không được bị coi là cột Rate và bị đẩy xuống cuối."""
    assert costing_fields._field_application_priority({"label": "Corporate"}) == 40
    assert costing_fields._field_application_priority({"label": "Rate"}) == 50


def test_the_order_puts_material_lists_before_rates():
    fields = [
        {"field_key": "colRate", "label": "Rate"},
        {"field_key": "colMaterialColorList"},
    ]

    assert sorted(fields, key=costing_fields._field_application_priority)[0][
        "field_key"
    ] == "colMaterialColorList"


# --- Save Cost Sheet ------------------------------------------------------


def _save_world(clock, *, messages=(), save=True):
    button = element("div", id="save")
    xpaths = {SAVE_XPATH: [button] if save else []}
    frame = MiniFrame(Element("body"), clock=clock, xpaths=xpaths)
    frame.custom = list(messages)
    frame.scripts = {
        "__codexCostingSaveMessages": lambda _a: (
            list(frame.custom)
            if "return messages" in _a
            else None
        )
    }

    def evaluate(script, arg=None):
        if "window.__codexCostingSaveMessages = []" in script:
            return None
        if "return messages" in script:
            return list(frame.custom)
        raise AssertionError(f"script lạ: {script[:80]}")

    frame.evaluate = evaluate
    page = _Page(clock, [frame])
    return page, frame, button


def test_save_clicks_the_exact_toolbar_control(clock):
    page, _frame, button = _save_world(clock)
    logs: list[str] = []

    costing_fields._save_costing(page, _frame, logs.append)

    assert button.clicks == 1
    assert page.listeners == []
    assert any("Đang Save Cost Sheet" in line for line in logs)


def test_a_missing_save_control_is_reported(clock):
    page, frame, _button = _save_world(clock, save=False)

    with pytest.raises(RuntimeError, match="COSTING_SAVE_NOT_FOUND"):
        costing_fields._save_costing(page, frame, _quiet())


def test_a_wfx_validation_dialog_becomes_a_save_alert(clock):
    page, frame, _button = _save_world(
        clock,
        messages=[
            {"kind": "dialog", "title": "Lỗi", "message": "Purchase Officer bắt buộc"}
        ],
    )

    with pytest.raises(RuntimeError) as error:
        costing_fields._save_costing(page, frame, _quiet())

    assert "COSTING_SAVE_ALERT" in str(error.value)
    assert "Purchase Officer" in str(error.value)


def test_a_wfx_saved_successfully_dialog_is_not_a_failure(clock):
    page, frame, _button = _save_world(
        clock,
        messages=[{"kind": "dialog", "title": "", "message": "Saved successfully"}],
    )

    costing_fields._save_costing(page, frame, _quiet())


def test_a_success_message_is_never_treated_as_a_failure(clock):
    page, frame, _button = _save_world(
        clock, messages=[{"kind": "success", "title": "", "message": "OK"}]
    )

    costing_fields._save_costing(page, frame, _quiet())


@pytest.mark.parametrize(
    "message",
    [
        "Error while saving",
        "Save failed",
        "Invalid value",
        "Purchase Officer is required",
        "Field missing",
        "Cannot save",
        "Record not saved",
    ],
)
def test_a_native_alert_that_sounds_like_a_failure_stops_the_save(
    clock, message
):
    page, frame, button = _save_world(clock)
    button.on_click = lambda _n: page.fire_dialog(message)

    with pytest.raises(RuntimeError, match="COSTING_SAVE_ALERT"):
        costing_fields._save_costing(page, frame, _quiet())


def test_a_harmless_native_alert_does_not_stop_the_save(clock):
    page, frame, button = _save_world(clock)
    button.on_click = lambda _n: page.fire_dialog("Đang lưu...")

    costing_fields._save_costing(page, frame, _quiet())

    assert page.listeners == []
