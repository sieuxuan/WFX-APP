"""Catalog Grid: chỉ nhận grid đang nhìn thấy, và đã thật sự có dữ liệu.

CLAUDE.md: header và Floating Filter xuất hiện trước datasource nên không tính
là grid ready; `#showfloatingfilter` là toggle nên chỉ được click một lần trên
cùng một grid, và fast-path dùng lại Master chỉ được nhận khi đúng Category,
grid còn tương tác, filter đang bật và dữ liệu đã ổn định.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation._common as common
import wfx_panel.automation.catalog.grid as grid_module
from tests.fakes.automation_boundary import FakePage
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import (
    CODE_FILTER,
    FakeCatalogGrid,
    FakeNode,
    FilterNode,
    StyleRow,
    install_fake_clock,
)
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, grid_module, common)


def _grid(clock, **kwargs):
    kwargs.setdefault("rows", [StyleRow("ABC123")])
    kwargs.setdefault("filters", [FilterNode(CODE_FILTER)])
    return FakeCatalogGrid(clock, **kwargs)


def _ready_grid(clock, **kwargs):
    return _grid(clock, filter_row_visible=True, **kwargs)


def _page(clock, *frames):
    return FakePage(clock, frames=list(frames))


def _quiet(_line):
    return None


class OtherFrame:
    """Frame của module khác: đúng là frame, nhưng không phải Catalog."""

    url = "https://wfx.test/wfx/WFXSampleList.aspx"

    def is_detached(self):
        return False

    def locator(self, _selector):
        raise AssertionError("frame ngoài Catalog không được probe")


class EmptyCatalogFrame:
    """URL Catalog nhưng AG Grid chưa dựng — hoặc đã dựng hai root."""

    def __init__(self, roots=0):
        self.url = "https://wfx.test/wfx/wfxcataloglist.aspx"
        self.roots = roots

    def is_detached(self):
        return False

    def locator(self, _selector):
        from tests.fakes.wfx_dom import FakeLocator

        return FakeLocator([FakeNode() for _ in range(self.roots)], _selector)


# --- nhận đúng grid ------------------------------------------------------


def test_a_frame_of_another_module_is_never_taken_for_the_catalog_grid(clock):
    # Quét từ frame mới nhất trở về trước, nên frame module khác phải đứng sau
    # mới chứng minh được nó bị bỏ qua thay vì chưa được xét tới.
    page = _page(clock, _grid(clock), OtherFrame())

    assert grid_module._catalog_grid_frame(page) is page.frames[0]


def test_a_catalog_frame_the_user_already_left_is_not_used(clock):
    stale = _grid(clock, detached=True)

    with pytest.raises(PlaywrightTimeoutError, match="AG Grid"):
        grid_module._catalog_grid_frame(_page(clock, stale), timeout_seconds=1)


def test_a_catalog_page_whose_grid_is_not_built_yet_is_not_interactive(clock):
    assert grid_module._catalog_grid_is_interactive(EmptyCatalogFrame()) is False


def test_a_grid_in_a_hidden_pane_is_not_interactive(clock):
    assert grid_module._catalog_grid_is_interactive(
        _grid(clock, interactive=False)
    ) is False


def test_a_grid_whose_frame_element_is_hidden_is_not_interactive(clock):
    assert grid_module._catalog_grid_is_interactive(
        _grid(clock, frame_element_visible=False)
    ) is False


def test_the_main_frame_has_no_frame_element_and_still_counts(clock):
    assert grid_module._catalog_grid_is_interactive(_grid(clock)) is True


def test_a_frame_element_is_always_released_after_the_probe(clock):
    frame = _grid(clock, frame_element_visible=True)

    grid_module._catalog_grid_is_interactive(frame)

    assert frame.frame_elements[0].disposed is True


def test_a_frame_element_that_cannot_be_released_is_not_fatal(clock):
    frame = _grid(clock, frame_element_visible=True)
    real_frame_element = frame.frame_element

    def refusing():
        node = real_frame_element()
        node.dispose = _raise_playwright
        return node

    frame.frame_element = refusing

    assert grid_module._catalog_grid_is_interactive(frame) is True


def _raise_playwright(*_args, **_kwargs):
    raise PlaywrightError("frame was detached")


def test_a_frame_that_throws_while_being_probed_is_not_interactive(clock):
    frame = _grid(clock)
    frame.locator = _raise_playwright

    assert grid_module._catalog_grid_is_interactive(frame) is False


# --- dữ liệu đã ổn định --------------------------------------------------


def test_a_grid_with_rows_that_stop_changing_is_ready(clock):
    grid_module._wait_catalog_grid_data_ready(_ready_grid(clock))


def test_an_empty_grid_must_stay_empty_longer_before_it_counts(clock):
    empty = _ready_grid(clock, rows=[], no_rows=True)

    grid_module._wait_catalog_grid_data_ready(empty)

    # No-rows phải ổn định lâu hơn có dữ liệu, nên tốn nhiều lượt poll hơn.
    assert empty.poll_count > 4


def test_a_grid_still_loading_its_datasource_is_never_called_ready(clock):
    loading = _ready_grid(clock, loading=True)

    with pytest.raises(PlaywrightTimeoutError, match="chưa sẵn sàng"):
        grid_module._wait_catalog_grid_data_ready(loading, timeout_seconds=2)


def test_a_grid_that_binds_its_rows_late_is_waited_out(clock):
    def bind_late(grid, poll):
        if poll >= 3:
            grid.loading = False

    late = _ready_grid(clock, loading=True, on_poll=bind_late)

    grid_module._wait_catalog_grid_data_ready(late, timeout_seconds=10)


# --- hàng Floating Filter ------------------------------------------------


def test_a_filter_row_with_a_usable_box_counts_as_active(clock):
    assert grid_module._catalog_filter_row_active(_ready_grid(clock)) is True


def test_a_grid_without_a_filter_row_is_not_active(clock):
    assert grid_module._catalog_filter_row_active(_grid(clock)) is False


def test_a_grid_that_went_away_reads_as_no_filter_row(clock):
    frame = _grid(clock)
    frame.locator = _raise_playwright

    assert grid_module._catalog_filter_row_active(frame) is False


# --- bật Floating Filter -------------------------------------------------


def test_a_filter_row_already_on_is_reused_instead_of_toggled_off(clock):
    grid = _ready_grid(clock)
    lines: list[str] = []

    result = grid_module._show_catalog_floating_filter(_page(clock, grid), lines.append)

    assert result is grid
    assert grid.show_filter_clicks == 0
    assert any("dùng lại grid" in line for line in lines)


def test_reusing_a_filter_row_still_waits_for_the_data_when_asked(clock):
    grid = _ready_grid(clock)

    grid_module._show_catalog_floating_filter(
        _page(clock, grid), _quiet, require_data_ready=True
    )

    assert grid.poll_count > 0


def test_a_filter_row_that_is_off_is_switched_on_exactly_once(clock):
    grid = _grid(clock)
    lines: list[str] = []

    result = grid_module._show_catalog_floating_filter(
        _page(clock, grid), lines.append
    )

    assert result is grid
    # Nút là toggle: bấm lần hai sẽ TẮT filter rồi phải chờ và retry.
    assert grid.show_filter_clicks == 1
    assert any("Show Floating Filters" in line for line in lines)


def test_switching_the_filter_row_on_still_waits_for_the_data_when_asked(clock):
    grid = _grid(clock)

    grid_module._show_catalog_floating_filter(
        _page(clock, grid), _quiet, require_data_ready=True
    )

    assert grid.poll_count > 0


def test_a_grid_without_the_toggle_button_reports_the_last_error(clock):
    grid = _grid(clock, show_button=False)

    with pytest.raises(PlaywrightTimeoutError, match="Floating Filter chưa sẵn sàng"):
        grid_module._show_catalog_floating_filter(
            _page(clock, grid), _quiet, timeout_seconds=2
        )


def test_a_page_with_no_catalog_grid_at_all_reports_the_last_error(clock):
    with pytest.raises(PlaywrightTimeoutError, match="Floating Filter chưa sẵn sàng"):
        grid_module._show_catalog_floating_filter(
            _page(clock), _quiet, timeout_seconds=2
        )


# --- dùng lại Master đang mở ---------------------------------------------


class TreeFrame:
    def __init__(self, value="01", error=None):
        self.value = value
        self.error = error

    def locator(self, _selector):
        from tests.fakes.wfx_dom import FakeLocator

        if self.error is not None:
            raise self.error
        return FakeLocator([FakeNode(value=self.value)], _selector)


def test_a_prepared_master_on_the_right_category_is_reused(clock, monkeypatch):
    grid = _ready_grid(clock)
    patch_automation(
        monkeypatch,
        grid_module,
        "_catalog_tree_frame_now",
        lambda _page: TreeFrame("01"),
    )
    lines: list[str] = []

    assert grid_module._reuse_prepared_catalog_master(
        _page(clock, grid), "01", lines.append
    ) is True
    assert any("dùng lại context" in line for line in lines)


def test_no_catalog_tree_at_all_means_the_master_must_be_opened_again(
    clock, monkeypatch
):
    patch_automation(
        monkeypatch, grid_module, "_catalog_tree_frame_now", lambda _page: None
    )

    assert grid_module._reuse_prepared_catalog_master(
        _page(clock), "01", _quiet
    ) is False


def test_a_tree_on_another_category_means_the_master_must_be_opened_again(
    clock, monkeypatch
):
    patch_automation(
        monkeypatch,
        grid_module,
        "_catalog_tree_frame_now",
        lambda _page: TreeFrame("05"),
    )

    assert grid_module._reuse_prepared_catalog_master(
        _page(clock, _ready_grid(clock)), "01", _quiet
    ) is False


def test_a_grid_whose_filter_row_is_off_means_the_master_must_be_reopened(
    clock, monkeypatch
):
    patch_automation(
        monkeypatch,
        grid_module,
        "_catalog_tree_frame_now",
        lambda _page: TreeFrame("01"),
    )

    assert grid_module._reuse_prepared_catalog_master(
        _page(clock, _grid(clock)), "01", _quiet
    ) is False


def test_a_tree_that_throws_means_the_master_must_be_reopened(clock, monkeypatch):
    patch_automation(
        monkeypatch,
        grid_module,
        "_catalog_tree_frame_now",
        lambda _page: TreeFrame(error=PlaywrightError("frame was detached")),
    )

    assert grid_module._reuse_prepared_catalog_master(
        _page(clock), "01", _quiet
    ) is False


def test_a_grid_whose_data_never_settles_means_the_master_must_be_reopened(
    clock, monkeypatch
):
    patch_automation(
        monkeypatch,
        grid_module,
        "_catalog_tree_frame_now",
        lambda _page: TreeFrame("01"),
    )

    assert grid_module._reuse_prepared_catalog_master(
        _page(clock, _ready_grid(clock, loading=True)), "01", _quiet
    ) is False
