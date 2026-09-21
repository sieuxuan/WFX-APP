"""Bộ lọc control của Costing: lọc một lượt nhưng phải giữ nguyên hành vi.

Các hàm này gom `is_visible()`/`is_enabled()`/`get_attribute()`/`tagName` của
từng phần tử vào một `evaluate_all` duy nhất, vì mỗi lời gọi Playwright là một
lượt CDP riêng và một dòng Costing có vài chục control, còn dropdown Article có
thể vài trăm option.

Đây là đường ghi dữ liệu lên WFX, nên cái phải khoá không phải tốc độ mà là
ngữ nghĩa: control ẩn/disabled không được chọn, `type` bị chặn không phải ô
nhập, id trùng nhau thì dừng chứ không đoán, và option phải khớp **exact**.

`tests/fakes/wfx_costing_dom.py` tính lại đúng ngữ nghĩa đó từ thuộc tính khai
báo của mỗi control; nó không chạy JS, nên test này khoá phần Python và hợp
đồng lọc, không thay cho một lượt chạy thật trên WFX.
"""

from __future__ import annotations

import pytest

from tests.fakes.wfx_costing_dom import Control, ControlFrame, ControlLocator
from tests.fakes.wfx_dom import install_fake_clock, patch_automation
from wfx_panel.automation import _common, costing


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, costing, _common)


def _frame(clock, controls, **selectors) -> ControlFrame:
    return ControlFrame(clock, controls, selectors=selectors or None)


# --- _visible_controls --------------------------------------------------


def test_only_controls_that_are_visible_and_enabled_are_returned(clock):
    wanted = Control(dom_id="txtQty")
    frame = _frame(
        clock,
        [
            Control(dom_id="txtHidden", visible=False),
            wanted,
            Control(dom_id="txtLocked", enabled=False),
            Control(dom_id="txtGone", connected=False),
        ],
    )

    controls = costing._visible_controls(frame, "input,select,textarea")

    assert len(controls) == 1
    assert controls[0].node is wanted


def test_the_returned_handle_acts_on_the_right_control(clock):
    first = Control(dom_id="txtA")
    second = Control(dom_id="txtB")
    frame = _frame(clock, [first, second])

    costing._visible_controls(frame, "input,select,textarea")[1].fill("9")

    assert second.fills == ["9"]
    assert first.fills == []


def test_the_whole_row_is_filtered_in_a_single_call(clock):
    frame = _frame(clock, [Control(dom_id=f"txt{n}") for n in range(40)])

    costing._visible_controls(frame, "input,select,textarea")

    assert frame.locators[0].evaluate_all_calls == 1, (
        "Hỏi từng control tốn một lượt CDP mỗi node; cả dòng phải gọn một lượt"
    )


def test_a_frame_that_detaches_mid_scan_yields_nothing(clock):
    frame = _frame(clock, [Control(dom_id="txtA")])
    original = ControlFrame.locator

    def detached(self, selector):
        locator = original(self, selector)
        locator.detached = True
        return locator

    ControlFrame.locator = detached
    try:
        assert costing._visible_controls(frame, "input,select,textarea") == []
    finally:
        ControlFrame.locator = original


def test_every_scan_passes_a_cancellation_checkpoint(clock, monkeypatch):
    """Nút Stop chỉ phản hồi ở checkpoint; quét cả dòng mà không có là kẹt."""
    calls: list[int] = []
    patch_automation(monkeypatch, costing, "checkpoint", lambda: calls.append(1))
    frame = _frame(clock, [Control(dom_id="txtA")])

    costing._visible_controls(frame, "input,select,textarea")

    assert calls, "Mỗi lượt quét phải cho người dùng cơ hội huỷ"


def test_a_cancelled_run_stops_before_touching_the_dom(clock, monkeypatch):
    def cancelled():
        raise RuntimeError("ACTION_CANCELLED")

    patch_automation(monkeypatch, costing, "checkpoint", cancelled)
    frame = _frame(clock, [Control(dom_id="txtA")])

    with pytest.raises(RuntimeError, match="ACTION_CANCELLED"):
        costing._visible_controls(frame, "input,select,textarea")

    assert frame.locators[0].evaluate_all_calls == 0


# --- _visible_costing_grid ----------------------------------------------


def _grid_frame(clock, grids) -> ControlFrame:
    return ControlFrame(clock, selectors={costing.COSTING_GRID_SELECTOR: grids})


def test_exactly_one_visible_grid_is_used(clock):
    wanted = Control(dom_id="grid", tag="table")
    frame = _grid_frame(clock, [Control(visible=False), wanted])

    assert costing._visible_costing_grid(frame).node is wanted


def test_two_visible_grids_are_refused(clock):
    """Hai popup Costing chồng nhau thì đoán bừa là ghi nhầm style."""
    frame = _grid_frame(clock, [Control(dom_id="a"), Control(dom_id="b")])

    assert costing._visible_costing_grid(frame) is None


def test_no_visible_grid_is_refused(clock):
    frame = _grid_frame(clock, [Control(visible=False)])

    assert costing._visible_costing_grid(frame) is None


# --- _unique_visible_by_id ----------------------------------------------


def _id_frame(clock, controls) -> ControlFrame:
    return ControlFrame(clock, selectors={"row": controls})


def test_a_single_visible_control_with_that_id_is_returned(clock):
    wanted = Control(dom_id="lblRate")
    frame = _id_frame(clock, [Control(dom_id="lblQty"), wanted])

    assert costing._unique_visible_by_id(frame, "lblRate").node is wanted


def test_two_visible_controls_with_the_same_id_are_refused(clock):
    """WFX lặp id trên nhiều dòng; chọn bừa là điền sai Article."""
    frame = _id_frame(clock, [Control(dom_id="lblRate"), Control(dom_id="lblRate")])

    with pytest.raises(RuntimeError, match="COSTING_FIELD_DETACHED"):
        costing._unique_visible_by_id(frame, "lblRate")


def test_a_hidden_control_does_not_count_as_the_target(clock):
    frame = _id_frame(clock, [Control(dom_id="lblRate", visible=False)])

    with pytest.raises(RuntimeError, match="COSTING_FIELD_DETACHED"):
        costing._unique_visible_by_id(frame, "lblRate")


def test_a_hidden_twin_lets_the_visible_one_through(clock):
    wanted = Control(dom_id="lblRate")
    frame = _id_frame(clock, [Control(dom_id="lblRate", visible=False), wanted])

    assert costing._unique_visible_by_id(frame, "lblRate").node is wanted


# --- _resolve_live_field ------------------------------------------------


def _field(dom_id: str, *, click_dom_id: str = "", region: str = "") -> dict:
    live = {"dom_id": dom_id, "region": region}
    if click_dom_id:
        live["click_dom_id"] = click_dom_id
    return {"_live": live}


@pytest.mark.parametrize("dom_id", sorted(costing.FORBIDDEN_CONTROL_IDS))
def test_a_forbidden_control_is_never_resolved(clock, dom_id):
    """CLAUDE.md: Costing tuyệt đối không click bốn control này."""
    frame = _id_frame(clock, [Control(dom_id=dom_id)])

    with pytest.raises(RuntimeError, match="COSTING_FORBIDDEN_CONTROL"):
        costing._resolve_live_field(frame, _field(dom_id))


@pytest.mark.parametrize("dom_id", sorted(costing.FORBIDDEN_CONTROL_IDS))
def test_a_forbidden_click_target_is_refused_even_with_a_suffix(clock, dom_id):
    frame = _id_frame(clock, [Control(dom_id=dom_id)])
    field = _field("lblSafe", click_dom_id=f"{dom_id}~")

    with pytest.raises(RuntimeError, match="COSTING_FORBIDDEN_CONTROL"):
        costing._resolve_live_field(frame, field)


def test_a_field_resolves_through_its_click_target(clock):
    wanted = Control(dom_id="colRate")
    frame = _id_frame(clock, [Control(dom_id="lblRate"), wanted])

    resolved = costing._resolve_live_field(
        frame,
        _field("lblRate", click_dom_id="colRate"),
    )

    assert resolved.node is wanted


# --- _edit_wfx_label ----------------------------------------------------


def _edit(clock, controls, *, dom_id="txtQty", value="7", region=""):
    frame = _frame(clock, controls)
    control = Control(dom_id=dom_id)
    costing._edit_wfx_label(
        frame,
        control,
        {"_live": {"dom_id": dom_id, "region": region}},
        value,
    )
    return frame, control


def test_a_lone_editor_is_filled_and_committed(clock):
    editor = Control(dom_id="txtQty")

    _edit(clock, [editor])

    assert editor.fills == ["7"]
    assert editor.keys == ["Tab"], "Không Tab thì WFX chưa chạy onchange"


def test_the_editor_matching_the_field_wins_over_its_neighbours(clock):
    other = Control(dom_id="txtRate")
    wanted = Control(dom_id="txtQty")

    _edit(clock, [other, wanted], dom_id="lblQty")

    assert wanted.fills == ["7"]
    assert other.fills == []


def test_several_editors_with_no_clear_match_are_refused(clock):
    """Điền bừa vào ô cạnh bên là ghi sai dữ liệu Costing."""
    left = Control(dom_id="txtRate")
    right = Control(dom_id="txtValue")

    with pytest.raises(RuntimeError, match="COSTING_INLINE_EDITOR_NOT_FOUND"):
        _edit(clock, [left, right], dom_id="lblTotal")

    assert left.fills == [] and right.fills == []


@pytest.mark.parametrize("blocked", sorted({"hidden", "checkbox", "radio", "button"}))
def test_a_non_text_input_is_not_treated_as_the_editor(clock, blocked):
    editor = Control(dom_id="txtQty")
    noise = Control(dom_id="chkPick", input_type=blocked)

    _edit(clock, [noise, editor])

    assert editor.fills == ["7"]


def test_a_disabled_control_is_not_treated_as_the_editor(clock):
    editor = Control(dom_id="txtQty")

    _edit(clock, [Control(dom_id="txtLocked", enabled=False), editor])

    assert editor.fills == ["7"]


def test_no_editor_at_all_is_reported(clock):
    with pytest.raises(RuntimeError, match="COSTING_INLINE_EDITOR_NOT_FOUND"):
        _edit(clock, [Control(dom_id="txtQty", visible=False)])


# --- _edit_wfx_label: dropdown -----------------------------------------


def _select(**kwargs) -> Control:
    return Control(
        dom_id="ddlSupplier",
        tag="select",
        options=[("Alpha Ltd", "1"), ("Beta Co", "2"), ("Alpha Ltd Extra", "3")],
        **kwargs,
    )


def test_a_dropdown_is_matched_by_its_label(clock):
    editor = _select()

    _edit(clock, [editor], value="Alpha Ltd")

    assert editor.selected == ["1"]


def test_a_dropdown_is_matched_by_its_value(clock):
    editor = _select()

    _edit(clock, [editor], value="2")

    assert editor.selected == ["2"]


def test_a_partial_label_is_refused(clock):
    """`Alpha` trùng một phần hai option; đoán là chọn nhầm nhà cung cấp."""
    editor = _select()

    with pytest.raises(RuntimeError, match="COSTING_INLINE_OPTION_NOT_FOUND"):
        _edit(clock, [editor], value="Alpha")

    assert editor.selected == []


def test_a_label_matching_two_options_is_refused(clock):
    editor = Control(
        dom_id="ddlSupplier",
        tag="select",
        options=[("Alpha Ltd", "1"), ("Alpha Ltd", "9")],
    )

    with pytest.raises(RuntimeError, match="COSTING_INLINE_OPTION_NOT_FOUND"):
        _edit(clock, [editor], value="Alpha Ltd")


def test_a_select2_backing_control_uses_a_native_change_event(clock):
    """CLAUDE.md: không dùng select_option cho backing select 1×1 của Select2."""
    editor = _select(css_class="select2-hidden-accessible")

    _edit(clock, [editor], value="Beta Co")

    assert editor.change_events == 1
    assert editor.value == "2"


def test_a_plain_select_still_uses_select_option(clock):
    editor = _select()

    _edit(clock, [editor], value="Beta Co")

    assert editor.change_events == 0
    assert editor.selected == ["2"]


def test_the_whole_dropdown_is_read_in_a_single_call(clock):
    editor = Control(
        dom_id="ddlArticle",
        tag="select",
        options=[(f"Article {n}", str(n)) for n in range(300)],
    )
    frame = _frame(clock, [editor])
    counters: list[ControlLocator] = []
    original = ControlLocator.evaluate_all

    def counting(self, script, arg=None):
        counters.append(self)
        return original(self, script, arg)

    ControlLocator.evaluate_all = counting
    try:
        costing._edit_wfx_label(
            frame,
            Control(dom_id="lblArticle"),
            {"_live": {"dom_id": "ddlArticle", "region": ""}},
            "Article 250",
        )
    finally:
        ControlLocator.evaluate_all = original

    assert editor.selected == ["250"]
    assert len(counters) == 2, (
        "Đúng hai lượt: một lọc editor, một khớp option — "
        f"không phải {len(counters)}"
    )
