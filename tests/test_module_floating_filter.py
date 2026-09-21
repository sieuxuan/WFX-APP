"""Bật và xác nhận Floating Filter của grid module.

`wfx_panel/automation/modules/grid.py` ở mức 19%. Đây là nơi thi hành đúng hai
câu của CLAUDE.md mà chưa dòng nào được kiểm:

* "Poll trạng thái grid ở 150 ms, nhưng chỉ chấp nhận Floating Filter sau khi
  visible/enabled ổn định ít nhất 0,5 giây và đúng context để vừa nhanh vừa
  tránh grid cũ."
* "Mọi flow `List` chỉ trả thành công sau khi WFX đổi page/frame/document thật"
  — grid cũ còn trong DOM không được nhận là grid mới.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.modules import grid as module_grid

GRID_STATE_MARKER = "ag-overlay-loading-wrapper"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, module_grid, _common)


def _quiet():
    return lambda _line: None


def _state(**overrides):
    base = {
        "loading": False,
        "noRows": False,
        "renderedRows": 5,
        "filterVisible": True,
        "filterInputCount": 3,
        "headerHeight": 60,
        "filterRowHeight": 24,
    }
    base.update(overrides)
    return base


class _Page:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


def _grid_frame(
    clock,
    *,
    url="https://wfx.test/wfx_CatalogList.aspx",
    states=None,
    filter_inputs=1,
    filter_enabled=True,
    button=True,
    visible=True,
):
    """Một frame có đúng một `.ag-root-wrapper` trả trạng thái khai báo."""
    queue = list(states or [_state()])

    def next_state(_arg):
        return queue[0] if len(queue) == 1 else queue.pop(0)

    inputs = [
        Element(
            "div",
            css_class="ag-floating-filter",
            children=[
                element("input", id=f"flt{index}", enabled=filter_enabled)
            ],
        )
        for index in range(filter_inputs)
    ]
    root = Element(
        "div",
        css_class="ag-root-wrapper",
        visible=visible,
        children=inputs,
        scripts={GRID_STATE_MARKER: next_state},
    )
    children = [root]
    if button:
        children.append(element("div", id="showfloatingfilter"))
    return MiniFrame(Element("body", children=children), url=url, clock=clock)


# --- đánh dấu grid cũ -----------------------------------------------------


def test_marking_records_one_marker_per_existing_grid(clock):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])

    snapshots = module_grid._mark_grid_roots(page)

    assert len(snapshots) == 1
    assert snapshots[0][0] is frame


def test_a_grid_in_a_frame_that_had_none_is_always_new(clock):
    frame = _grid_frame(clock)
    root = frame.locator(".ag-root-wrapper").first

    assert module_grid._grid_root_is_new(frame, root, []) is True


def test_the_same_grid_is_not_treated_as_new(clock):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    snapshots = module_grid._mark_grid_roots(page)
    root = frame.locator(".ag-root-wrapper").first

    assert module_grid._grid_root_is_new(frame, root, snapshots) is False


def test_a_grid_rebuilt_in_place_counts_as_new(clock):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    snapshots = module_grid._mark_grid_roots(page)
    frame.locator(".ag-root-wrapper").node.markers.clear()
    root = frame.locator(".ag-root-wrapper").first

    assert module_grid._grid_root_is_new(frame, root, snapshots) is True


def test_marking_survives_a_frame_that_throws(clock):
    class Broken:
        url = "https://wfx.test/x"

        def locator(self, _selector):
            raise PlaywrightError("frame đã rơi")

    page = _Page(clock, [Broken()])

    assert module_grid._mark_grid_roots(page) == []


# --- grid đã ổn định ------------------------------------------------------


def test_a_grid_is_only_settled_after_it_holds_still(clock):
    frame = _grid_frame(clock)
    state = module_grid._FloatingFilterState()

    assert module_grid._module_grid_settled(frame, _state(), state) is False
    clock.advance(0.8)
    assert module_grid._module_grid_settled(frame, _state(), state) is True


def test_a_loading_grid_is_never_settled(clock):
    frame = _grid_frame(clock)
    state = module_grid._FloatingFilterState()

    module_grid._module_grid_settled(frame, _state(loading=True), state)
    clock.advance(5)

    assert (
        module_grid._module_grid_settled(frame, _state(loading=True), state) is False
    )


def test_an_empty_grid_with_a_no_rows_overlay_is_settled(clock):
    frame = _grid_frame(clock)
    state = module_grid._FloatingFilterState()
    empty = _state(renderedRows=0, noRows=True)

    module_grid._module_grid_settled(frame, empty, state)
    clock.advance(0.8)

    assert module_grid._module_grid_settled(frame, empty, state) is True


def test_an_empty_grid_without_an_overlay_is_not_settled(clock):
    frame = _grid_frame(clock)
    state = module_grid._FloatingFilterState()
    phantom = _state(renderedRows=0, noRows=False)

    module_grid._module_grid_settled(frame, phantom, state)
    clock.advance(5)

    assert module_grid._module_grid_settled(frame, phantom, state) is False


def test_a_row_count_that_keeps_changing_restarts_the_stability_window(clock):
    frame = _grid_frame(clock)
    state = module_grid._FloatingFilterState()

    module_grid._module_grid_settled(frame, _state(renderedRows=5), state)
    clock.advance(0.6)
    module_grid._module_grid_settled(frame, _state(renderedRows=9), state)
    clock.advance(0.6)

    assert (
        module_grid._module_grid_settled(frame, _state(renderedRows=9), state)
        is False
    )


# --- hàng filter ----------------------------------------------------------


def test_a_filter_row_that_is_not_visible_is_never_ready(clock):
    frame = _grid_frame(clock)
    root = frame.locator(".ag-root-wrapper").first
    state = module_grid._FloatingFilterState()

    assert (
        module_grid._floating_filter_input_ready(
            root, _state(filterVisible=False), state, _quiet()
        )
        is False
    )
    assert state.filter_stable_since == 0.0


def test_a_filter_row_must_stay_visible_before_it_counts(clock):
    frame = _grid_frame(clock)
    root = frame.locator(".ag-root-wrapper").first
    state = module_grid._FloatingFilterState()

    assert (
        module_grid._floating_filter_input_ready(root, _state(), state, _quiet())
        is False
    )
    clock.advance(module_grid.MODULE_FILTER_VISIBLE_STABLE_SECONDS + 0.1)
    logs: list[str] = []
    assert (
        module_grid._floating_filter_input_ready(root, _state(), state, logs.append)
        is True
    )
    assert any("Hàng filter đã hiển thị" in line for line in logs)


def test_a_disabled_filter_input_is_not_ready(clock):
    frame = _grid_frame(clock, filter_enabled=False)
    root = frame.locator(".ag-root-wrapper").first
    state = module_grid._FloatingFilterState()
    module_grid._floating_filter_input_ready(root, _state(), state, _quiet())
    clock.advance(module_grid.MODULE_FILTER_VISIBLE_STABLE_SECONDS + 0.1)

    assert (
        module_grid._floating_filter_input_ready(root, _state(), state, _quiet())
        is False
    )


def test_a_filter_row_without_any_input_is_not_ready(clock):
    frame = _grid_frame(clock, filter_inputs=0)
    root = frame.locator(".ag-root-wrapper").first
    state = module_grid._FloatingFilterState()
    module_grid._floating_filter_input_ready(root, _state(), state, _quiet())
    clock.advance(module_grid.MODULE_FILTER_VISIBLE_STABLE_SECONDS + 0.1)

    assert (
        module_grid._floating_filter_input_ready(root, _state(), state, _quiet())
        is False
    )


# --- click nút bật filter -------------------------------------------------


def test_the_filter_button_is_clicked_at_most_once_per_second_and_a_half(clock):
    frame = _grid_frame(clock)
    button = frame.locator("#showfloatingfilter").node
    state = module_grid._FloatingFilterState()

    module_grid._click_floating_filter_if_due(frame, state, _quiet())
    module_grid._click_floating_filter_if_due(frame, state, _quiet())
    assert button.clicks == 1

    clock.advance(1.6)
    module_grid._click_floating_filter_if_due(frame, state, _quiet())
    assert button.clicks == 2


def test_no_button_means_no_click(clock):
    frame = _grid_frame(clock, button=False)
    state = module_grid._FloatingFilterState()

    module_grid._click_floating_filter_if_due(frame, state, _quiet())  # không raise


# --- vòng chờ đầy đủ ------------------------------------------------------


def test_the_loop_returns_the_frame_once_the_filter_row_is_confirmed(clock):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    logs: list[str] = []

    result = module_grid._show_module_floating_filter(page, logs.append)

    assert result is frame
    assert any("Grid đã ổn định" in line for line in logs)


def test_the_loop_clicks_the_button_when_the_filter_row_is_still_hidden(clock):
    states = [
        _state(filterVisible=False),
        _state(filterVisible=False),
        _state(filterVisible=False),
        _state(),
    ]
    frame = _grid_frame(clock, states=states)
    page = _Page(clock, [frame])

    module_grid._show_module_floating_filter(page, _quiet())

    assert frame.locator("#showfloatingfilter").node.clicks >= 1


def test_the_loop_ignores_a_grid_that_was_already_open(clock):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    previous = module_grid._mark_grid_roots(page)

    with pytest.raises(PlaywrightTimeoutError) as error:
        module_grid._show_module_floating_filter(
            page, _quiet(), previous, timeout_s=1
        )

    assert "Show Floating Filter chưa sẵn sàng" in str(error.value)


def test_the_loop_ignores_a_hidden_grid(clock):
    frame = _grid_frame(clock, visible=False)
    page = _Page(clock, [frame])

    with pytest.raises(PlaywrightTimeoutError):
        module_grid._show_module_floating_filter(page, _quiet(), timeout_s=1)


def test_the_loop_ignores_a_frame_of_another_module(clock, monkeypatch):
    """Selector của OC/Sample/Sale ASN trùng nhau; context mới là thứ phân biệt."""
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    monkeypatch.setattr(
        module_grid,
        "_frame_matches_module_context",
        lambda _frame, name: name != "Sale ASN List",
    )

    with pytest.raises(PlaywrightTimeoutError):
        module_grid._show_module_floating_filter(
            page, _quiet(), timeout_s=1, module_name="Sale ASN List"
        )

    assert module_grid._show_module_floating_filter(
        page, _quiet(), module_name="OC List"
    ) is frame


def test_the_timeout_message_carries_the_last_grid_state_and_error(clock):
    frame = _grid_frame(clock, states=[_state(loading=True)])
    page = _Page(clock, [frame])

    with pytest.raises(PlaywrightTimeoutError) as error:
        module_grid._show_module_floating_filter(page, _quiet(), timeout_s=1)

    assert "gridState=" in str(error.value)
    assert "'loading': True" in str(error.value)


def test_the_loop_survives_a_frame_that_throws_mid_poll(clock):
    class Broken:
        url = "https://wfx.test/x"

        def locator(self, _selector):
            raise PlaywrightError("frame vừa navigate")

    good = _grid_frame(clock)
    page = _Page(clock, [Broken(), good])

    assert module_grid._show_module_floating_filter(page, _quiet()) is good


# --- entry point ----------------------------------------------------------


def _wire(monkeypatch, clock, *, chrome_ready=True, logged_in=True):
    world = WfxWorld(clock)
    wire_automation(
        monkeypatch,
        module_grid,
        world,
        chrome_ready=chrome_ready,
        logged_in=logged_in,
        clock=clock,
    )
    return world


def test_open_module_reports_success_after_the_filter_is_ready(
    clock, monkeypatch
):
    world = _wire(monkeypatch, clock)
    monkeypatch.setattr(module_grid, "_mark_grid_roots", lambda _page: [])
    order: list[str] = []
    monkeypatch.setattr(
        module_grid,
        "_click_module_menu_on_page",
        lambda *a: order.append("menu"),
    )
    monkeypatch.setattr(
        module_grid,
        "_show_module_floating_filter",
        lambda *a, **kw: order.append("filter"),
    )

    result = module_grid.open_module_with_floating_filter(
        "OC List", '//*[@id="x"]/a', _quiet()
    )

    assert result["code"] == "MODULE_FILTER_READY"
    assert result["module"] == "OC List"
    assert order == ["menu", "filter"]
    assert world.driver_starts == world.driver_stops == 1


def test_open_module_maps_a_timeout_to_the_filter_error_code(clock, monkeypatch):
    world = _wire(monkeypatch, clock)
    monkeypatch.setattr(module_grid, "_mark_grid_roots", lambda _page: [])
    monkeypatch.setattr(module_grid, "_click_module_menu_on_page", lambda *a: None)

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("grid không dựng")

    monkeypatch.setattr(module_grid, "_show_module_floating_filter", slow)

    result = module_grid.open_module_with_floating_filter(
        "OC List", '//*[@id="x"]/a', _quiet()
    )

    assert result["code"] == "FLOATING_FILTER_NOT_READY"
    assert world.driver_stops == 1


def test_open_module_reports_a_closed_browser_through_the_shared_boundary(
    clock, monkeypatch
):
    _wire(monkeypatch, clock, chrome_ready=False)

    result = module_grid.open_module_with_floating_filter(
        "OC List", '//*[@id="x"]/a', _quiet()
    )

    assert result["code"] == "CHROME_CLOSED"


def test_open_module_reports_an_expired_session_through_the_shared_boundary(
    clock, monkeypatch
):
    _wire(monkeypatch, clock, logged_in=False)

    result = module_grid.open_module_with_floating_filter(
        "OC List", '//*[@id="x"]/a', _quiet()
    )

    assert result["code"] == "NOT_LOGGED_IN"


def test_open_module_reports_any_other_failure_as_module_failed(
    clock, monkeypatch
):
    _wire(monkeypatch, clock)
    monkeypatch.setattr(module_grid, "_mark_grid_roots", lambda _page: [])

    def boom(*_args):
        raise ValueError("xpath hỏng")

    monkeypatch.setattr(module_grid, "_click_module_menu_on_page", boom)

    result = module_grid.open_module_with_floating_filter(
        "OC List", '//*[@id="x"]/a', _quiet()
    )

    assert result["code"] == "MODULE_FAILED"
    assert "ValueError" in result["message"]
