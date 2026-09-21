"""Tìm và điền ô Floating Filter của một màn List bất kỳ.

CLAUDE.md: layout cột lưu riêng theo user nên automation phải quét toàn bộ
scroll ngang để tìm cột dù user đã kéo đổi thứ tự, và phải xác nhận đúng
context module trong cùng frame — OC/Sample/Sale ASN dùng selector trùng nhau.
Điền xong phải xác nhận giá trị chứ không coi "đã gõ" là "đã tìm".
"""

from __future__ import annotations

import pytest

import wfx_panel.automation.modules.inputs as inputs
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import FakeLocator, FakeNode, install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, inputs)


class HeaderInput(FakeNode):
    """Input có metadata header như script của `_visible_search_input` đọc."""

    def __init__(self, metadata="", **kwargs):
        super().__init__(**kwargs)
        self.metadata = metadata

    def evaluate(self, script, arg=None):
        if "closest(" in script:
            self._guard()
            return self.metadata
        return super().evaluate(script, arg)


class SearchFrame:
    def __init__(self, nodes=None, *, clock=None, error=None, url="https://wfx.test/list"):
        self.nodes = dict(nodes or {})
        self.clock = clock
        self.error = error
        self.url = url

    def locator(self, selector):
        if self.error is not None:
            raise self.error
        return FakeLocator(self.nodes.get(selector, []), selector)

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


class SearchPage:
    def __init__(self, *frames, clock=None):
        self.frames = list(frames)
        self.clock = clock

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


@pytest.fixture(autouse=True)
def _any_module_context(monkeypatch):
    patch_automation(
        monkeypatch,
        inputs,
        "_frame_matches_module_context",
        lambda _frame, _module: True,
    )


# --- chờ một control bất kể nó nằm frame nào ----------------------------


def test_a_control_is_found_in_whichever_frame_wfx_put_it_in(clock):
    target = FakeNode()
    page = SearchPage(
        SearchFrame({"#btnSave": []}, clock=clock),
        SearchFrame({"#btnSave": [target]}, clock=clock),
        clock=clock,
    )

    frame, locator = inputs._visible_locator_in_frames(page, "#btnSave")

    assert frame is page.frames[1]
    assert locator.node is target


def test_a_hidden_control_is_not_the_one_the_user_can_press(clock):
    page = SearchPage(
        SearchFrame({"#btnSave": [FakeNode(visible=False)]}, clock=clock),
        clock=clock,
    )

    with pytest.raises(PlaywrightTimeoutError, match="#btnSave"):
        inputs._visible_locator_in_frames(page, "#btnSave", 1)


def test_a_frame_that_detaches_mid_scan_does_not_stop_the_search(clock):
    target = FakeNode()
    page = SearchPage(
        SearchFrame(error=PlaywrightError("frame was detached"), clock=clock),
        SearchFrame({"#btnSave": [target]}, clock=clock),
        clock=clock,
    )

    _frame, locator = inputs._visible_locator_in_frames(page, "#btnSave")

    assert locator.node is target


# --- click điều hướng ASP.NET -------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Frame was detached",
        "Execution context was destroyed, most likely because of a navigation",
        "Target page, context or browser has been closed",
    ],
)
def test_a_frame_that_detaches_right_after_the_click_means_it_navigated(
    monkeypatch, message
):
    def detach(_locator):
        raise PlaywrightError(message)

    patch_automation(monkeypatch, inputs, "_click", detach)

    inputs._click_navigation_control(FakeLocator([FakeNode()], "#lnkList"))


def test_a_click_that_failed_for_another_reason_is_still_an_error(monkeypatch):
    def refuse(_locator):
        raise PlaywrightError("Element is outside of the viewport")

    patch_automation(monkeypatch, inputs, "_click", refuse)

    with pytest.raises(PlaywrightError, match="viewport"):
        inputs._click_navigation_control(object())


# --- tìm ô filter theo selector rồi theo header -------------------------


SELECTORS = ('input[aria-label="OC No. Filter Input"]',)
ALIASES = ("oc no", "oc number")


def test_the_declared_selector_wins_over_guessing_from_the_header():
    declared = FakeNode()
    frame = SearchFrame({SELECTORS[0]: [declared]})

    found = inputs._visible_search_input(frame, SELECTORS, ALIASES)

    assert found.node is declared


def test_a_disabled_filter_box_is_not_used():
    frame = SearchFrame(
        {SELECTORS[0]: [FakeNode(enabled=False)], "input": []}
    )

    assert inputs._visible_search_input(frame, SELECTORS, ALIASES) is None


def test_a_filter_box_is_recognised_by_its_column_header_when_the_id_changed():
    wrong = HeaderInput("txtStyle Style Code")
    right = HeaderInput("txtOC OC No.")
    frame = SearchFrame({SELECTORS[0]: [], "input": [wrong, right]})

    found = inputs._visible_search_input(frame, SELECTORS, ALIASES)

    assert found.node is right


def test_the_header_that_matches_most_of_the_alias_wins():
    short = HeaderInput("OC No.")
    long = HeaderInput("OC Number")
    frame = SearchFrame({SELECTORS[0]: [], "input": [short, long]})

    found = inputs._visible_search_input(frame, SELECTORS, ALIASES)

    assert found.node is long


def test_a_header_that_matches_nothing_is_never_filled_by_accident():
    frame = SearchFrame(
        {SELECTORS[0]: [], "input": [HeaderInput("Created By")]}
    )

    assert inputs._visible_search_input(frame, SELECTORS, ALIASES) is None


def test_hidden_or_disabled_boxes_are_skipped_while_scoring_headers():
    frame = SearchFrame(
        {
            SELECTORS[0]: [],
            "input": [
                HeaderInput("OC No.", visible=False),
                HeaderInput("OC No.", enabled=False),
            ],
        }
    )

    assert inputs._visible_search_input(frame, SELECTORS, ALIASES) is None


def test_a_selector_that_throws_falls_through_to_the_header_scan():
    class Picky(SearchFrame):
        def locator(self, selector):
            if selector == SELECTORS[0]:
                raise PlaywrightError("frame was detached")
            return super().locator(selector)

    target = HeaderInput("OC No.")
    frame = Picky({"input": [target]})

    found = inputs._visible_search_input(frame, SELECTORS, ALIASES)

    assert found.node is target


def test_a_frame_that_goes_away_during_the_header_scan_yields_nothing():
    class Vanishing(SearchFrame):
        def locator(self, selector):
            if selector == "input":
                raise PlaywrightError("execution context was destroyed")
            return super().locator(selector)

    frame = Vanishing({SELECTORS[0]: []})

    assert inputs._visible_search_input(frame, SELECTORS, ALIASES) is None


# --- cột bị AG Grid virtualize ngoài viewport ----------------------------


@pytest.fixture
def horizontal(monkeypatch):
    """Grid ngang giả: cuộn tới `reveal_at` mới lộ ra ô filter."""
    scrolls: list[float] = []

    def state(_root):
        return {"current": 120, "max": 600}

    def positions(_state):
        return [0, 300, 600]

    def scroll(_root, position):
        scrolls.append(position)

    patch_automation(monkeypatch, inputs, "_horizontal_grid_state", state)
    patch_automation(monkeypatch, inputs, "_horizontal_grid_positions", positions)
    patch_automation(monkeypatch, inputs, "_scroll_horizontal_grid", scroll)
    return scrolls


def test_a_column_the_user_dragged_out_of_view_is_still_found(
    clock, horizontal, monkeypatch
):
    target = FakeNode()
    seen: list[int] = []

    def probe(_frame, _selectors, _aliases):
        seen.append(len(seen))
        return target if len(seen) >= 3 else None

    patch_automation(monkeypatch, inputs, "_visible_search_input", probe)
    frame = SearchFrame({".ag-root-wrapper": [FakeNode()]}, clock=clock)

    assert inputs._search_input_across_horizontal_grid(
        frame, SELECTORS, ALIASES
    ) is target
    assert horizontal == [0, 300, 600]


def test_the_grid_is_scrolled_back_when_the_column_is_nowhere_to_be_found(
    clock, horizontal, monkeypatch
):
    patch_automation(
        monkeypatch, inputs, "_visible_search_input", lambda *_a: None
    )
    frame = SearchFrame({".ag-root-wrapper": [FakeNode()]}, clock=clock)

    assert inputs._search_input_across_horizontal_grid(
        frame, SELECTORS, ALIASES
    ) is None
    assert horizontal[-1] == 120


def test_a_grid_that_is_not_on_screen_is_skipped(clock, horizontal):
    frame = SearchFrame(
        {".ag-root-wrapper": [FakeNode(visible=False)]}, clock=clock
    )

    assert inputs._search_input_across_horizontal_grid(
        frame, SELECTORS, ALIASES
    ) is None
    assert horizontal == []


def test_a_grid_that_re_renders_mid_scan_does_not_crash_the_search(
    clock, monkeypatch
):
    def boom(_root):
        raise PlaywrightError("Element is not attached to the DOM")

    patch_automation(monkeypatch, inputs, "_horizontal_grid_state", boom)
    frame = SearchFrame({".ag-root-wrapper": [FakeNode()]}, clock=clock)

    assert inputs._search_input_across_horizontal_grid(
        frame, SELECTORS, ALIASES
    ) is None


# --- chọn frame đúng module ---------------------------------------------


def test_a_frame_belonging_to_another_module_is_never_filled(clock, monkeypatch):
    other = SearchFrame({SELECTORS[0]: [FakeNode()]}, clock=clock)
    patch_automation(
        monkeypatch,
        inputs,
        "_frame_matches_module_context",
        lambda frame, _module: frame is not other,
    )
    page = SearchPage(other, clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="oc no"):
        inputs._search_input_in_frames(
            page, SELECTORS, ALIASES, 1, module_name="oc"
        )


def test_the_first_frame_that_owns_the_filter_box_is_the_one_used(clock):
    target = FakeNode()
    page = SearchPage(
        SearchFrame({SELECTORS[0]: []}, clock=clock),
        SearchFrame({SELECTORS[0]: [target]}, clock=clock),
        clock=clock,
    )

    frame, found = inputs._search_input_in_frames(page, SELECTORS, ALIASES, 5)

    assert frame is page.frames[1]
    assert found.node is target


def test_the_horizontal_scan_only_runs_when_the_module_asked_for_it(
    clock, horizontal, monkeypatch
):
    target = FakeNode()
    patch_automation(
        monkeypatch,
        inputs,
        "_search_input_across_horizontal_grid",
        lambda *_a: target,
    )
    page = SearchPage(SearchFrame({SELECTORS[0]: []}, clock=clock), clock=clock)

    _frame, found = inputs._search_input_in_frames(
        page, SELECTORS, ALIASES, 5, scan_horizontal=True
    )

    assert found is target


def test_the_horizontal_scan_also_respects_the_module_context(
    clock, monkeypatch
):
    patch_automation(
        monkeypatch,
        inputs,
        "_frame_matches_module_context",
        lambda _frame, _module: False,
    )
    patch_automation(
        monkeypatch,
        inputs,
        "_search_input_across_horizontal_grid",
        lambda *_a: pytest.fail("frame sai module vẫn bị quét ngang"),
    )
    page = SearchPage(SearchFrame({SELECTORS[0]: []}, clock=clock), clock=clock)

    with pytest.raises(PlaywrightTimeoutError):
        inputs._search_input_in_frames(
            page, SELECTORS, ALIASES, 1, scan_horizontal=True, module_name="oc"
        )


# --- tìm trong đúng một frame đã biết -----------------------------------


def test_a_filter_box_in_the_known_list_frame_is_used_directly(clock):
    target = FakeNode()
    frame = SearchFrame({SELECTORS[0]: [target]}, clock=clock)
    page = SearchPage(frame, clock=clock)

    found = inputs._search_input_in_frame(page, frame, SELECTORS, ALIASES)

    assert found.node is target


def test_a_known_frame_also_gets_the_horizontal_scan_when_asked(
    clock, monkeypatch
):
    target = FakeNode()
    patch_automation(
        monkeypatch,
        inputs,
        "_search_input_across_horizontal_grid",
        lambda *_a: target,
    )
    frame = SearchFrame({SELECTORS[0]: []}, clock=clock)
    page = SearchPage(frame, clock=clock)

    found = inputs._search_input_in_frame(
        page, frame, SELECTORS, ALIASES, 5, scan_horizontal=True
    )

    assert found is target


def test_a_list_frame_without_the_column_reports_the_alias_it_looked_for(clock):
    frame = SearchFrame({SELECTORS[0]: []}, clock=clock)
    page = SearchPage(frame, clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="đúng màn List"):
        inputs._search_input_in_frame(page, frame, SELECTORS, ALIASES, 1)


# --- lớp loading của WFX ------------------------------------------------


def test_the_search_is_not_settled_while_wfx_shows_its_loading_layer(clock):
    overlay = FakeNode()
    frame = SearchFrame({inputs._MODULE_LOADING_SELECTOR: [overlay]}, clock=clock)
    page = SearchPage(frame, clock=clock)

    assert inputs._module_search_is_loading(page) is True
    with pytest.raises(PlaywrightTimeoutError, match="chưa ổn định"):
        inputs._wait_module_search_stable(page, "OC No.")


def test_a_frame_that_detaches_while_probing_loading_is_ignored(clock):
    page = SearchPage(
        SearchFrame(error=PlaywrightError("frame was detached"), clock=clock),
        clock=clock,
    )

    assert inputs._module_search_is_loading(page) is False


def test_a_grid_that_stays_quiet_long_enough_counts_as_settled(clock):
    page = SearchPage(
        SearchFrame({inputs._MODULE_LOADING_SELECTOR: []}, clock=clock),
        clock=clock,
    )

    inputs._wait_module_search_stable(page, "OC No.")


# --- điền và xác nhận ---------------------------------------------------


def _quiet_page(clock):
    return SearchPage(
        SearchFrame({inputs._MODULE_LOADING_SELECTOR: []}, clock=clock),
        clock=clock,
    )


def test_a_query_is_filled_then_confirmed_then_submitted(clock):
    field = FakeNode()
    logged: list[str] = []

    inputs._apply_module_search(
        _quiet_page(clock), field, "OC-1234", "OC No.", logged.append
    )

    assert field.fills == ["OC-1234"]
    assert field.keys == ["Enter"]
    assert any("[MODULE SEARCH]" in line for line in logged)


def test_a_filter_box_that_kept_only_part_of_the_query_is_an_error(clock):
    class Partial(FakeNode):
        def fill(self, value, timeout=None):
            super().fill(value, timeout)
            self.value = value[:3]

    with pytest.raises(PlaywrightTimeoutError, match="không xác nhận"):
        inputs._apply_module_search(
            _quiet_page(clock), Partial(), "OC-1234", "OC No.", lambda _line: None
        )


def test_a_filter_box_that_re_rendered_after_enter_still_counts_as_submitted(
    clock,
):
    class Rerendering(FakeNode):
        def press(self, key, timeout=None):
            raise PlaywrightError("Element is not attached to the DOM")

        def dispatch_event(self, event):
            raise PlaywrightError("Element is not attached to the DOM")

    inputs._apply_module_search(
        _quiet_page(clock), Rerendering(), "OC-1234", "OC No.", lambda _line: None
    )
