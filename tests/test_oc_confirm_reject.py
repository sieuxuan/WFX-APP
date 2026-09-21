"""Confirm New/Revision và Reject All trên EDI Buyer PO.

`wfx_panel/automation/oc/confirm.py` ở mức 51%. Đây là hai flow ghi dữ liệu
không idempotent nhất của module OC, và CLAUDE.md nói rất rõ:

* "Mỗi Style được bấm Confirm tối đa hai lượt… Sau Confirm phải chờ Style biến
  mất khỏi tab New/Revision và bảng ổn định tối đa 180 giây rồi mới chuyển
  Style tiếp theo. Nếu kết quả chưa rõ hoặc quá thời gian, dừng toàn bộ flow và
  không tự retry."
* "Revision kiểm tra từng dòng trong Style: … có nhiều option thì dừng trước
  Confirm để user chọn thủ công."
* "`Reject All · tab đang mở` chỉ xử lý tab New hoặc Revision hiện đang được
  chọn trên WFX, không tự chuyển tab… sau khi đã dispatch Reject tuyệt đối
  không tự retry."
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.oc import confirm


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, confirm, _common)


def _quiet():
    return lambda _line: None


class _Page:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.listeners: list[tuple] = []

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)

    def locator(self, selector):
        return self.frames[0].locator(selector)

    def on(self, event, handler):
        self.listeners.append((event, handler))

    def remove_listener(self, event, handler):
        if (event, handler) in self.listeners:
            self.listeners.remove((event, handler))

    def fire_dialog(self):
        class Dialog:
            message = "Confirm reject?"
            accepted = False

            def accept(self):
                type(self).accepted = True

        dialog = Dialog()
        for event, handler in list(self.listeners):
            if event == "dialog":
                handler(dialog)
        return dialog


def _confirm_frame(clock, *, styles=(), loading=False, selector=True):
    """Frame EDI Buyer PO; `styles` giữ nguyên dạng thô mà JS trả về."""
    children = [element("div", id="gridEDIBuyerPO_divFocus")]
    if selector:
        children.append(
            Element(
                "div",
                attrs={"data-wfx-oc-confirm-row": "1"},
                children=[
                    Element(
                        "td",
                        id="colSelector",
                        children=[
                            element("input", id="sel", attrs={"type": "radio"})
                        ],
                    )
                ],
            )
        )
    if loading:
        children.append(element("div", id="gridEDIBuyerPO_divGridLoading"))
    frame = MiniFrame(Element("body", children=children), clock=clock)
    frame.styles = list(styles)
    frame.prepared = {"ok": True, "selected_count": 1}
    frame.marked = {"ok": True}
    frame.active_tab = "new"
    frame.scripts = {
        "groups": lambda _a: list(frame.styles),
        "prepare": lambda _key: frame.prepared,
        "mark": lambda _key: dict(frame.marked),
        "activeTab": lambda _a: frame.active_tab,
    }
    return frame


def _style(key="S1", label="Style 1"):
    return {"key": key, "label": label}


# --- đọc Style ------------------------------------------------------------


def test_only_rows_that_carry_a_key_are_treated_as_styles(clock, monkeypatch):
    frame = _confirm_frame(clock, styles=[_style(), {"label": "rác"}, "chuỗi"])
    monkeypatch.setattr(confirm, "_CONFIRM_GROUPS_JS", "groups")

    assert confirm._read_confirm_styles(frame) == [_style()]


# --- focus grid -----------------------------------------------------------


def test_the_grid_focus_helper_clicks_the_frame_target_first(clock):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])

    confirm._focus_confirm_grid(page, frame)

    assert frame.locator("#gridEDIBuyerPO_divFocus").node.clicks == 1


def test_the_grid_focus_helper_is_silent_without_a_target(clock):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _Page(clock, [frame])

    confirm._focus_confirm_grid(page, frame)  # không raise


# --- chọn Style -----------------------------------------------------------


def test_selecting_a_style_ticks_its_own_control(clock, monkeypatch):
    frame = _confirm_frame(clock)
    monkeypatch.setattr(confirm, "_MARK_CONFIRM_STYLE_JS", "mark")

    confirm._select_confirm_style(frame, "S1")

    assert frame.locator("#sel").node.checked is True


def test_a_style_that_changed_before_selection_stops_the_flow(clock, monkeypatch):
    frame = _confirm_frame(clock)
    frame.marked = {"ok": False}
    monkeypatch.setattr(confirm, "_MARK_CONFIRM_STYLE_JS", "mark")

    with pytest.raises(PlaywrightTimeoutError, match="Style đã thay đổi"):
        confirm._select_confirm_style(frame, "S1")


def test_a_row_without_a_selector_control_stops_the_flow(clock, monkeypatch):
    frame = _confirm_frame(clock, selector=False)
    monkeypatch.setattr(confirm, "_MARK_CONFIRM_STYLE_JS", "mark")

    with pytest.raises(PlaywrightTimeoutError, match="ô chọn"):
        confirm._select_confirm_style(frame, "S1")


# --- Revision -------------------------------------------------------------


def test_a_revision_style_with_several_sales_orders_is_reported(clock, monkeypatch):
    frame = _confirm_frame(clock)
    frame.prepared = {
        "ok": False,
        "reason": "multiple-sales-orders",
        "options": ["SO-1", "SO-2"],
    }
    monkeypatch.setattr(confirm, "_PREPARE_REVISION_STYLE_JS", "prepare")

    assert confirm._prepare_revision_style(frame, "S1")["reason"] == (
        "multiple-sales-orders"
    )


def test_a_non_dict_preparation_result_is_treated_as_a_changed_style(
    clock, monkeypatch
):
    frame = _confirm_frame(clock)
    frame.prepared = "hỏng"
    monkeypatch.setattr(confirm, "_PREPARE_REVISION_STYLE_JS", "prepare")

    assert confirm._prepare_revision_style(frame, "S1") == {
        "ok": False,
        "reason": "style-changed",
    }


# --- toolbar --------------------------------------------------------------


def test_confirm_falls_back_to_the_toolbar_label(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    link = element("a", id="confirm")
    monkeypatch.setattr(
        confirm,
        "_visible_in_frames",
        lambda *a, **kw: (_ for _ in ()).throw(PlaywrightTimeoutError("chưa có")),
    )
    monkeypatch.setattr(
        confirm, "_toolbar_link", lambda _page, label, timeout_s=0: (frame, link)
    )

    confirm._click_confirm_toolbar(page)

    assert link.clicks == 1


def test_confirm_uses_the_exact_toolbar_position_when_it_is_there(
    clock, monkeypatch
):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    link = element("a", id="confirm")
    monkeypatch.setattr(
        confirm, "_visible_in_frames", lambda *a, **kw: (frame, link)
    )
    fallbacks: list[int] = []
    monkeypatch.setattr(
        confirm,
        "_toolbar_link",
        lambda *a, **kw: fallbacks.append(1) or (frame, element("a")),
    )

    confirm._click_confirm_toolbar(page)

    assert link.clicks == 1
    assert fallbacks == []


def test_reject_accepts_the_native_confirmation_and_removes_its_listener(
    clock, monkeypatch
):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    link = element("a", id="reject")
    link.on_click = lambda _n: page.fire_dialog()
    monkeypatch.setattr(
        confirm, "_visible_in_frames", lambda *a, **kw: (frame, link)
    )

    confirm._click_reject_toolbar(page)

    assert link.clicks == 1
    assert page.listeners == []


# --- nhận diện tab đang mở ------------------------------------------------


def test_the_active_tab_is_read_from_the_only_frame_that_knows_it(
    clock, monkeypatch
):
    frame = _confirm_frame(clock)
    frame.active_tab = "revision"
    page = _Page(clock, [frame])
    monkeypatch.setattr(confirm, "_ACTIVE_CONFIRM_TAB_JS", "activeTab")

    assert confirm._active_confirm_mode(page) == "revision"


def test_two_frames_claiming_different_tabs_stop_reject_all(clock, monkeypatch):
    first = _confirm_frame(clock)
    second = _confirm_frame(clock)
    second.active_tab = "revision"
    page = _Page(clock, [first, second])
    monkeypatch.setattr(confirm, "_ACTIVE_CONFIRM_TAB_JS", "activeTab")

    with pytest.raises(PlaywrightTimeoutError, match="đúng tab New hoặc Revision"):
        confirm._active_confirm_mode(page)


def test_no_frame_knowing_the_tab_stops_reject_all(clock, monkeypatch):
    frame = _confirm_frame(clock)
    frame.active_tab = ""
    page = _Page(clock, [frame])
    monkeypatch.setattr(confirm, "_ACTIVE_CONFIRM_TAB_JS", "activeTab")

    with pytest.raises(PlaywrightTimeoutError):
        confirm._active_confirm_mode(page)


# --- chờ Style rời tab ----------------------------------------------------


def _wire_styles(monkeypatch, sequence):
    queue = list(sequence)
    monkeypatch.setattr(
        confirm,
        "_read_confirm_styles",
        lambda _frame: queue[0] if len(queue) == 1 else queue.pop(0),
    )


def test_a_style_is_only_processed_once_it_stays_gone(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    _wire_styles(monkeypatch, [[_style()], []])

    assert confirm._wait_style_processed(page, frame, "S1", timeout_s=30) is True


def test_a_style_that_never_leaves_is_a_timeout(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    _wire_styles(monkeypatch, [[_style()]])

    assert confirm._wait_style_processed(page, frame, "S1", timeout_s=3) is False


def test_a_visible_loading_layer_blocks_the_processed_signal(clock, monkeypatch):
    frame = _confirm_frame(clock, loading=True)
    frame.root.append(element("div", css_class="loading"))
    page = _Page(clock, [frame])
    _wire_styles(monkeypatch, [[]])

    assert confirm._wait_style_processed(page, frame, "S1", timeout_s=3) is False


def test_a_frame_that_dies_mid_wait_is_resolved_again(clock, monkeypatch):
    good = _confirm_frame(clock)
    page = _Page(clock, [good])
    reads: list[int] = []

    def read(_frame):
        reads.append(1)
        if len(reads) == 1:
            raise PlaywrightError("frame rơi")
        return []

    monkeypatch.setattr(confirm, "_read_confirm_styles", read)
    monkeypatch.setattr(confirm, "_confirm_frame", lambda *a, **kw: good)

    assert confirm._wait_style_processed(page, good, "S1", timeout_s=30) is True


# --- Confirm tất cả -------------------------------------------------------


def _wire_confirm(monkeypatch, styles_sequence, *, processed=True):
    _wire_styles(monkeypatch, styles_sequence)
    monkeypatch.setattr(confirm, "_focus_confirm_grid", lambda *a: None)
    monkeypatch.setattr(confirm, "_select_confirm_style", lambda *a: None)
    clicks: list[int] = []
    monkeypatch.setattr(
        confirm, "_click_confirm_toolbar", lambda _page: clicks.append(1)
    )
    monkeypatch.setattr(
        confirm, "_wait_style_processed", lambda *a, **kw: processed
    )
    return clicks


def test_an_empty_tab_reports_nothing_to_confirm(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    _wire_confirm(monkeypatch, [[]])

    result = confirm._confirm_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_FAST_CONFIRM_COMPLETED"
    assert result["confirmed_styles"] == 0
    assert result["confirmation_submitted"] is False


def test_every_style_is_confirmed_one_by_one(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    clicks = _wire_confirm(
        monkeypatch,
        [[_style("S1"), _style("S2")], [_style("S2")], []],
    )

    result = confirm._confirm_all_pending(page, frame, "new", _quiet())

    assert result["confirmed_styles"] == 2
    assert result["confirmation_submitted"] is True
    assert len(clicks) == 2


def test_a_style_that_never_processes_stops_the_whole_run(clock, monkeypatch):
    """CLAUDE.md: dừng toàn bộ flow, không sang Style tiếp theo."""
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    clicks = _wire_confirm(monkeypatch, [[_style()]], processed=False)

    result = confirm._confirm_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_FAST_CONFIRM_PROCESS_TIMEOUT"
    assert result["stopped_style"] == "Style 1"
    assert result["confirmation_submitted"] is True
    # Tối đa hai lượt Confirm cho cùng một Style.
    assert len(clicks) == 2


def test_a_failure_after_the_click_never_retries_automatically(
    clock, monkeypatch
):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    _wire_styles(monkeypatch, [[_style()]])
    monkeypatch.setattr(confirm, "_focus_confirm_grid", lambda *a: None)
    monkeypatch.setattr(confirm, "_select_confirm_style", lambda *a: None)
    monkeypatch.setattr(confirm, "_click_confirm_toolbar", lambda _page: None)
    monkeypatch.setattr(
        confirm,
        "_wait_style_processed",
        lambda *a, **kw: (_ for _ in ()).throw(PlaywrightError("frame rơi")),
    )

    result = confirm._confirm_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_FAST_CONFIRM_UNCONFIRMED"
    assert result["confirmation_submitted"] is True
    assert result["errors"]


def test_a_failure_before_the_click_is_raised_not_swallowed(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    _wire_styles(monkeypatch, [[_style()]])
    monkeypatch.setattr(confirm, "_focus_confirm_grid", lambda *a: None)
    monkeypatch.setattr(
        confirm,
        "_select_confirm_style",
        lambda *a: (_ for _ in ()).throw(PlaywrightTimeoutError("ô chọn mất")),
    )

    with pytest.raises(PlaywrightTimeoutError):
        confirm._confirm_all_pending(page, frame, "new", _quiet())


def test_a_revision_style_with_several_sales_orders_stops_before_confirm(
    clock, monkeypatch
):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    clicks = _wire_confirm(monkeypatch, [[_style()]])
    monkeypatch.setattr(
        confirm,
        "_prepare_revision_style",
        lambda *a: {
            "ok": False,
            "reason": "multiple-sales-orders",
            "options": ["SO-1", "SO-2"],
            "row_number": 3,
        },
    )

    result = confirm._confirm_all_pending(page, frame, "revision", _quiet())

    assert result["code"] == "OC_FAST_CONFIRM_MULTIPLE_SALES_ORDERS"
    assert result["sales_order_options"] == ["SO-1", "SO-2"]
    assert result["stopped_row"] == 3
    assert clicks == []


def test_a_revision_style_that_changed_stops_the_run(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    _wire_confirm(monkeypatch, [[_style()]])
    monkeypatch.setattr(
        confirm,
        "_prepare_revision_style",
        lambda *a: {"ok": False, "reason": "style-changed"},
    )

    with pytest.raises(PlaywrightTimeoutError, match="WFX Sales Order"):
        confirm._confirm_all_pending(page, frame, "revision", _quiet())


def test_revision_counts_the_sales_orders_it_selected(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    _wire_confirm(monkeypatch, [[_style()], []])
    monkeypatch.setattr(
        confirm,
        "_prepare_revision_style",
        lambda *a: {"ok": True, "selected_count": 2},
    )

    result = confirm._confirm_all_pending(page, frame, "revision", _quiet())

    assert result["selected_sales_orders"] == 2


# --- Reject All -----------------------------------------------------------


def _wire_reject(monkeypatch, styles_sequence, *, processed=True):
    _wire_styles(monkeypatch, styles_sequence)
    monkeypatch.setattr(confirm, "_focus_confirm_grid", lambda *a: None)
    monkeypatch.setattr(confirm, "_select_confirm_style", lambda *a: None)
    clicks: list[int] = []
    monkeypatch.setattr(
        confirm, "_click_reject_toolbar", lambda _page: clicks.append(1)
    )
    monkeypatch.setattr(
        confirm, "_wait_style_processed", lambda *a, **kw: processed
    )
    return clicks


def test_an_empty_tab_reports_nothing_to_reject(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    _wire_reject(monkeypatch, [[]])

    result = confirm._reject_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_REJECT_ALL_COMPLETED"
    assert result["rejected_rows"] == 0
    assert result["rejection_submitted"] is False


def test_every_pending_row_is_rejected_once(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    clicks = _wire_reject(
        monkeypatch, [[_style("R1"), _style("R2")], [_style("R2")], []]
    )

    result = confirm._reject_all_pending(page, frame, "new", _quiet())

    assert result["rejected_rows"] == 2
    assert len(clicks) == 2


def test_a_row_that_does_not_leave_stops_the_reject_run(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    clicks = _wire_reject(monkeypatch, [[_style()]], processed=False)

    result = confirm._reject_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_REJECT_ALL_PROCESS_TIMEOUT"
    assert result["rejection_submitted"] is True
    # Reject chỉ được dispatch đúng một lần.
    assert len(clicks) == 1


def test_a_failure_after_the_reject_click_never_retries(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    _wire_styles(monkeypatch, [[_style()]])
    monkeypatch.setattr(confirm, "_focus_confirm_grid", lambda *a: None)
    monkeypatch.setattr(confirm, "_select_confirm_style", lambda *a: None)
    monkeypatch.setattr(confirm, "_click_reject_toolbar", lambda _page: None)
    monkeypatch.setattr(
        confirm,
        "_wait_style_processed",
        lambda *a, **kw: (_ for _ in ()).throw(PlaywrightError("frame rơi")),
    )

    result = confirm._reject_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_REJECT_ALL_UNCONFIRMED"
    assert result["rejection_submitted"] is True


def test_a_failure_before_the_reject_click_is_raised(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    _wire_styles(monkeypatch, [[_style()]])
    monkeypatch.setattr(
        confirm,
        "_focus_confirm_grid",
        lambda *a: (_ for _ in ()).throw(PlaywrightTimeoutError("grid mất")),
    )

    with pytest.raises(PlaywrightTimeoutError):
        confirm._reject_all_pending(page, frame, "new", _quiet())


# --- resolve frame grid ---------------------------------------------------


def test_the_confirm_frame_prefers_the_grid_over_the_focus_target(
    clock, monkeypatch
):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    seen: list[str] = []

    def attached(_page, selector, timeout_s=0):
        seen.append(selector)
        return frame, element("div")

    monkeypatch.setattr(confirm, "_attached_in_frames", attached)

    assert confirm._confirm_frame(page) is frame
    assert seen == [confirm.CONFIRM_GRID_SELECTOR]


def test_the_confirm_frame_falls_back_to_the_focus_target(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    seen: list[str] = []

    def attached(_page, selector, timeout_s=0):
        seen.append(selector)
        if len(seen) == 1:
            raise PlaywrightTimeoutError("grid chưa dựng")
        return frame, element("div")

    monkeypatch.setattr(confirm, "_attached_in_frames", attached)

    assert confirm._confirm_frame(page) is frame
    assert seen[1] == "#gridEDIBuyerPO_divFocus"


# --- chờ grid sau khi đổi page size --------------------------------------


def _ready_frame(clock, *, controls=True, loading=False, grid=True):
    children = []
    if grid:
        grid_children = []
        if controls:
            grid_children.append(
                Element(
                    "td",
                    id="colSelector",
                    children=[element("input", id="sel", attrs={"type": "radio"})],
                )
            )
        children.append(
            Element(
                "table", id="gridEDIBuyerPO_tblGridContent", children=grid_children
            )
        )
    if loading:
        children.append(element("div", id="gridEDIBuyerPO_divGridLoading"))
    return MiniFrame(Element("body", children=children), clock=clock)


def test_a_grid_with_usable_controls_is_ready(clock, monkeypatch):
    monkeypatch.setattr(
        confirm, "CONFIRM_GRID_SELECTOR", "#gridEDIBuyerPO_tblGridContent"
    )
    frame = _ready_frame(clock)
    page = _Page(clock, [frame])

    assert confirm._wait_confirm_grid_ready(page, frame) is frame


def test_a_grid_still_showing_its_loading_layer_is_not_ready(clock, monkeypatch):
    monkeypatch.setattr(
        confirm, "CONFIRM_GRID_SELECTOR", "#gridEDIBuyerPO_tblGridContent"
    )
    frame = _ready_frame(clock, loading=True)
    page = _Page(clock, [frame])

    with pytest.raises(PlaywrightTimeoutError, match="vẫn đang tải"):
        confirm._wait_confirm_grid_ready(page, frame, timeout_s=2)


def test_an_empty_grid_is_accepted_after_it_stays_empty(clock, monkeypatch):
    """Tab đã Confirm hết vẫn phải trả về frame, không được timeout."""
    monkeypatch.setattr(
        confirm, "CONFIRM_GRID_SELECTOR", "#gridEDIBuyerPO_tblGridContent"
    )
    frame = _ready_frame(clock, controls=False)
    page = _Page(clock, [frame])

    assert confirm._wait_confirm_grid_ready(page, frame) is frame


def test_a_frame_without_the_grid_at_all_times_out(clock, monkeypatch):
    monkeypatch.setattr(
        confirm, "CONFIRM_GRID_SELECTOR", "#gridEDIBuyerPO_tblGridContent"
    )
    frame = _ready_frame(clock, grid=False)
    page = _Page(clock, [frame])

    with pytest.raises(PlaywrightTimeoutError):
        confirm._wait_confirm_grid_ready(page, frame, timeout_s=2)


# --- đổi số dòng hiển thị -------------------------------------------------


class _PageSizeSelect(Element):
    def __init__(self, value="20", *, accepts=True):
        super().__init__(
            "select",
            id="ddlPageSize",
            value=value,
            children=[
                element("option", text="20", attrs={"value": "20"}),
                element("option", text="100", attrs={"value": "100"}),
            ],
        )
        self._accepts = accepts

    def select_option(self, value=None, label=None, timeout=None, **_kwargs):
        self.selected.append(str(label or value))
        if self._accepts:
            self.value = "100"


def _size_world(monkeypatch, select):
    frame = MiniFrame(Element("body", children=[select]))
    # Code sản phẩm đọc lại nhãn option đang chọn qua chính locator của select.
    handle = frame.locator("#ddlPageSize").first
    for name in ("select_option", "input_value", "selected"):
        setattr(handle, name, getattr(select, name))
    monkeypatch.setattr(
        confirm, "_visible_in_frames", lambda *a, **kw: (frame, handle)
    )
    monkeypatch.setattr(
        confirm, "_wait_confirm_grid_ready", lambda _page, ready, **kw: ready
    )
    monkeypatch.setattr(confirm, "_wait", lambda *a: None)
    return frame


def test_the_page_size_is_set_to_one_hundred(clock, monkeypatch):
    select = _PageSizeSelect()
    frame = _size_world(monkeypatch, select)
    page = _Page(clock, [frame])

    assert confirm._set_confirm_page_size(page) is frame
    assert select.selected == ["100"]


def test_a_page_size_that_is_already_one_hundred_is_left_alone(
    clock, monkeypatch
):
    select = _PageSizeSelect(value="100")
    frame = _size_world(monkeypatch, select)
    page = _Page(clock, [frame])

    confirm._set_confirm_page_size(page)

    assert select.selected == []


def test_a_page_size_wfx_refuses_stops_the_flow(clock, monkeypatch):
    select = _PageSizeSelect(accepts=False)
    frame = _size_world(monkeypatch, select)
    page = _Page(clock, [frame])

    with pytest.raises(PlaywrightTimeoutError, match="số dòng hiển thị thành 100"):
        confirm._set_confirm_page_size(page)


# --- mở tab ---------------------------------------------------------------


def _open_world(monkeypatch, *, tab_visible=True):
    tab = element("a", id="tab")
    menu = element("a", id="menu")
    frame = MiniFrame(Element("body", children=[tab, menu]))
    calls: list[str] = []

    def visible(_page, selector, timeout_s=0):
        calls.append(selector)
        if selector == confirm.EDI_MENU_SELECTOR:
            return frame, menu
        if not tab_visible and len(calls) == 1:
            raise PlaywrightTimeoutError("tab chưa có")
        return frame, tab

    monkeypatch.setattr(confirm, "_visible_in_frames", visible)
    monkeypatch.setattr(
        confirm, "_attached_in_frames", lambda *a, **kw: (frame, menu)
    )
    monkeypatch.setattr(
        confirm, "_set_confirm_page_size", lambda _page: frame
    )
    return frame, tab, menu


@pytest.mark.parametrize(
    ("mode", "label"), [("new", "New"), ("revision", "Revision")]
)
def test_an_open_tab_is_reused_without_touching_the_menu(
    clock, monkeypatch, mode, label
):
    frame, tab, menu = _open_world(monkeypatch)
    page = _Page(clock, [frame])
    logs: list[str] = []

    assert confirm._open_confirm_grid(page, mode, logs.append) is frame
    assert tab.clicks == 1
    assert menu.clicks == 0
    assert any(f"Đã mở tab {label}" in line for line in logs)
    assert any("thành 100" in line for line in logs)


def test_a_missing_tab_is_reached_through_the_edi_menu(clock, monkeypatch):
    frame, tab, menu = _open_world(monkeypatch, tab_visible=False)
    page = _Page(clock, [frame])

    confirm._open_confirm_grid(page, "new", _quiet())

    assert menu.clicks == 1
    assert tab.clicks == 1


# --- nhánh WFX không hợp tác ---------------------------------------------


class _Exploding:
    """Frame/page mà mọi lời gọi locator đều ném, như khi frame vừa detach."""

    def __init__(self, clock=None):
        self.clock = clock

    def locator(self, _selector):
        raise PlaywrightError("frame was detached")

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


def test_focusing_the_grid_moves_on_when_a_frame_has_gone_away(clock):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])

    confirm._focus_confirm_grid(page, _Exploding(clock))

    assert frame.locator("#gridEDIBuyerPO_divFocus").node.clicks == 1


def test_a_checkbox_that_refuses_check_is_clicked_instead(clock, monkeypatch):
    frame = _confirm_frame(clock)
    monkeypatch.setattr(confirm, "_MARK_CONFIRM_STYLE_JS", "mark")
    control = frame.locator("#sel").node

    def refuse(self):
        raise PlaywrightError("element is not stable")

    monkeypatch.setattr(type(control), "is_checked", refuse)

    confirm._select_confirm_style(frame, "S1")

    assert control.clicks == 1


def test_reject_falls_back_to_the_toolbar_label(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    link = element("a", id="reject")
    monkeypatch.setattr(
        confirm,
        "_visible_in_frames",
        lambda *a, **kw: (_ for _ in ()).throw(PlaywrightTimeoutError("chưa có")),
    )
    monkeypatch.setattr(
        confirm, "_toolbar_link", lambda _page, label, timeout_s=0: (frame, link)
    )

    confirm._click_reject_toolbar(page)

    assert link.clicks == 1


def test_a_page_that_cannot_drop_the_dialog_listener_is_not_an_error(
    clock, monkeypatch
):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    link = element("a", id="reject")
    monkeypatch.setattr(
        confirm, "_visible_in_frames", lambda *a, **kw: (frame, link)
    )

    def refuse(_event, _handler):
        raise RuntimeError("page đã đóng")

    page.remove_listener = refuse

    confirm._click_reject_toolbar(page)

    assert link.clicks == 1


def test_a_frame_that_cannot_report_its_tab_is_skipped(clock, monkeypatch):
    frame = _confirm_frame(clock)
    monkeypatch.setattr(confirm, "_ACTIVE_CONFIRM_TAB_JS", "activeTab")

    class NoTab(MiniFrame):
        def evaluate(self, script, arg=None):
            raise PlaywrightError("execution context was destroyed")

    page = _Page(clock, [NoTab(Element("body"), clock=clock), frame])

    assert confirm._active_confirm_mode(page) == "new"


def test_the_page_size_is_read_as_unknown_when_the_select_refuses(
    clock, monkeypatch
):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    select = _FlakyPageSize(read_error=PlaywrightError("detached"))
    monkeypatch.setattr(
        confirm, "_visible_in_frames", lambda *a, **kw: (frame, select)
    )
    monkeypatch.setattr(
        confirm, "_wait_confirm_grid_ready", lambda _page, current: current
    )

    assert confirm._set_confirm_page_size(page) is frame
    assert select.selected == [("label", "100")]


def test_a_select_without_a_hundred_label_is_set_by_its_value(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    select = _FlakyPageSize(label_error=PlaywrightError("option không có label"))
    monkeypatch.setattr(
        confirm, "_visible_in_frames", lambda *a, **kw: (frame, select)
    )
    monkeypatch.setattr(
        confirm, "_wait_confirm_grid_ready", lambda _page, current: current
    )

    confirm._set_confirm_page_size(page)

    assert select.selected == [("value", "100")]


class _FlakyPageSize:
    """`#ddlPageSize` của WFX: đọc/ghi được, có thể từ chối từng cách một."""

    def __init__(self, *, read_error=None, label_error=None, value="10"):
        self.value = value
        self.read_error = read_error
        self.label_error = label_error
        self.selected: list[tuple[str, str]] = []

    def input_value(self, timeout=None):
        if self.read_error is not None and not self.selected:
            raise self.read_error
        return self.value

    def select_option(self, label=None, value=None, timeout=None):
        if label is not None:
            if self.label_error is not None:
                raise self.label_error
            self.selected.append(("label", str(label)))
        else:
            self.selected.append(("value", str(value)))
        self.value = "100"

    def locator(self, _selector):
        raise AssertionError("không cần đọc option khi input_value đã là 100")


def test_the_edi_menu_is_opened_even_when_it_is_only_attached(clock, monkeypatch):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])
    menu = element("a", id="edi-menu")
    tab = element("a", id="tab-new")
    visible_calls = {"n": 0}

    def visible(_page, selector, timeout_s=0):
        visible_calls["n"] += 1
        if visible_calls["n"] <= 2:
            raise PlaywrightTimeoutError("chưa hiện")
        return frame, tab

    monkeypatch.setattr(confirm, "_visible_in_frames", visible)
    monkeypatch.setattr(
        confirm, "_attached_in_frames", lambda *a, **kw: (frame, menu)
    )
    monkeypatch.setattr(
        confirm, "_set_confirm_page_size", lambda _page: frame
    )
    lines: list[str] = []

    assert confirm._open_confirm_grid(page, "new", lines.append) is frame
    assert menu.clicks == 1
    assert tab.clicks == 1


def test_a_frame_that_never_comes_back_stops_the_wait_at_its_deadline(
    clock, monkeypatch
):
    frame = _confirm_frame(clock)
    page = _Page(clock, [frame])

    def gone(_frame):
        raise PlaywrightError("frame was detached")

    def never(*_args, **_kwargs):
        raise PlaywrightTimeoutError("EDI Buyer PO chưa mở lại")

    monkeypatch.setattr(confirm, "_read_confirm_styles", gone)
    monkeypatch.setattr(confirm, "_confirm_frame", never)

    assert confirm._wait_style_processed(page, frame, "S1", timeout_s=2) is False


def test_a_control_that_is_not_clickable_yet_does_not_count_as_ready(
    clock, monkeypatch
):
    monkeypatch.setattr(
        confirm, "CONFIRM_GRID_SELECTOR", "#gridEDIBuyerPO_tblGridContent"
    )
    frame = _ready_frame(clock)
    page = _Page(clock, [frame])
    # `trial=True` là phép thử actionability: WFX còn lớp chặn thì nó ném, và
    # đó không được coi là grid đã sẵn sàng.
    monkeypatch.setattr(Element, "check", _refuse_check)

    with pytest.raises(PlaywrightTimeoutError, match="vẫn đang tải"):
        confirm._wait_confirm_grid_ready(page, frame, timeout_s=2)


def _refuse_check(self, timeout=None, **_kwargs):
    raise PlaywrightError("element is covered by the loading layer")


def test_a_grid_frame_that_dies_while_waiting_is_resolved_again(
    clock, monkeypatch
):
    monkeypatch.setattr(
        confirm, "CONFIRM_GRID_SELECTOR", "#gridEDIBuyerPO_tblGridContent"
    )
    good = _ready_frame(clock)
    page = _Page(clock, [good])

    assert confirm._wait_confirm_grid_ready(
        page, _Exploding(clock), timeout_s=10
    ) is good


def test_a_grid_frame_that_never_comes_back_times_out(clock, monkeypatch):
    monkeypatch.setattr(
        confirm, "CONFIRM_GRID_SELECTOR", "#gridEDIBuyerPO_tblGridContent"
    )
    page = _Page(clock, [_ready_frame(clock)])

    def never(*_args, **_kwargs):
        raise PlaywrightTimeoutError("EDI Buyer PO chưa mở lại")

    monkeypatch.setattr(confirm, "_confirm_frame", never)

    with pytest.raises(PlaywrightTimeoutError, match="vẫn đang tải"):
        confirm._wait_confirm_grid_ready(page, _Exploding(clock), timeout_s=2)
