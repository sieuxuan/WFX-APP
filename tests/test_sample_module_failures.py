"""Sample List khi WFX không hợp tác: grid lỗi, dòng đổi, Chrome đóng.

CLAUDE.md: Check File chạy đúng flow Search trước; nhiều dòng thì panel hiển
thị lựa chọn Sample và sau khi user chọn, app tiếp tục từ grid đang mở chứ
không tìm lại. Mọi flow phải nhả driver Playwright ở `finally`.
"""

from __future__ import annotations

import pytest

from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from tests.fakes.wfx_sample_grid import SampleGridFrame, SampleRow
from wfx_panel.automation import modules
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError

SAMPLE_XPATH = '//*[@id="0004_0056_4070"]/a'
FILTERS = {"sample_no": "SMP-001"}


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, modules)


def _log():
    lines: list[str] = []
    return lines, lines.append


def _world(clock, frame):
    return WfxWorld(clock, [FakePage(clock, frames=[frame], empty_selectors=[])])


def _grid(clock, **kwargs):
    return SampleGridFrame(clock, **kwargs)


# --- grid không chịu ổn định --------------------------------------------


def test_a_grid_that_never_appears_is_a_timeout_not_a_wrong_count(clock):
    frame = _grid(clock, rows=[SampleRow("0", style_code="ABC123")])
    frame.root_visible = False

    with pytest.raises(PlaywrightTimeoutError, match="chưa ổn định"):
        modules._sample_result_grid(frame, 3)


def test_a_grid_that_throws_while_being_read_reports_the_last_error(clock):
    class Broken(SampleGridFrame):
        def read_rows(self):
            raise PlaywrightError("execution context was destroyed")

    frame = Broken(clock, rows=[SampleRow("0", style_code="ABC123")])

    with pytest.raises(PlaywrightTimeoutError, match="lastError"):
        modules._sample_result_grid(frame, 3)


def test_a_grid_still_loading_rows_is_waited_out_not_counted_early(clock):
    def grow(frame, poll):
        if poll == 1:
            frame.rows = []
        elif poll == 2:
            frame.rows = [SampleRow("0", style_code="ABC123")]
        else:
            frame.rows = [
                SampleRow("0", style_code="ABC123"),
                SampleRow("1", style_code="XYZ999"),
            ]

    frame = _grid(clock, rows=[], no_rows=True, on_poll=grow)

    _root, payload = modules._sample_result_grid(frame, 3)

    assert len(payload["rows"]) == 2


class _DetachingRow:
    """Dòng biến mất giữa lúc đọc row-id và lúc click."""

    def get_attribute(self, name):
        return "0"

    def evaluate(self, _script, _arg=None):
        raise PlaywrightError("node is detached from document")


class _DetachingRoot:
    def __init__(self, root):
        self._root = root

    def is_visible(self):
        return self._root.is_visible()

    def evaluate(self, script, arg=None):
        return self._root.evaluate(script, arg)

    def locator(self, selector):
        original = self._root.locator(selector)
        return type(original)([_DetachingRow()], selector)


def test_a_row_that_detaches_between_reading_and_clicking_is_skipped(clock):
    class Fragile(SampleGridFrame):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.root = _DetachingRoot(self.root)

    frame = Fragile(clock, rows=[SampleRow("0", style_code="ABC123")])
    lines, log = _log()

    assert modules._click_sample_style_result(frame, "0", "ABC123", log) is False
    assert any("không còn trong kết quả" in line for line in lines)


# --- Search nhiều điều kiện ---------------------------------------------


def _explode(monkeypatch, error):
    def boom(*_args, **_kwargs):
        raise error

    patch_automation(monkeypatch, modules, "_apply_sample_filters", boom)


def test_a_search_wfx_never_confirmed_is_reported_as_such(clock, monkeypatch):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)
    _explode(monkeypatch, PlaywrightTimeoutError("WFX không xác nhận giá trị"))

    result = modules.search_sample_list_with_filters(
        SAMPLE_XPATH, FILTERS, _log()[1]
    )

    assert result["code"] in {
        "MODULE_SEARCH_NOT_CONFIRMED",
        "MODULE_SEARCH_NOT_READY",
    }
    assert result["module"] == "Sample List"
    assert world.driver_starts == world.driver_stops == 1


def test_an_unexpected_failure_while_searching_is_a_technical_error(
    clock, monkeypatch
):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)
    _explode(monkeypatch, ValueError("WFX trả về HTML lạ"))

    result = modules.search_sample_list_with_filters(
        SAMPLE_XPATH, FILTERS, _log()[1]
    )

    assert result["code"] == "MODULE_SEARCH_FAILED"
    assert "ValueError" in result["message"]
    assert world.driver_stops == 1


def test_a_browser_that_closed_mid_search_is_reported_as_a_boundary(
    clock, monkeypatch
):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)
    _explode(monkeypatch, RuntimeError("CHROME_CLOSED"))

    result = modules.search_sample_list_with_filters(
        SAMPLE_XPATH, FILTERS, _log()[1]
    )

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_stops == 1


# --- Check File ---------------------------------------------------------


def test_a_check_file_run_wfx_never_confirmed_is_reported_as_such(
    clock, monkeypatch
):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)
    _explode(monkeypatch, PlaywrightTimeoutError("WFX không xác nhận giá trị"))

    result = modules.find_sample_file_results_with_filters(
        SAMPLE_XPATH, FILTERS, _log()[1]
    )

    assert result["code"] in {
        "MODULE_SEARCH_NOT_CONFIRMED",
        "MODULE_SEARCH_NOT_READY",
    }
    assert "kiểm tra file" in result["message"]
    assert world.driver_stops == 1


def test_an_unexpected_failure_while_checking_files_is_a_technical_error(
    clock, monkeypatch
):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)
    _explode(monkeypatch, ValueError("WFX trả về HTML lạ"))

    result = modules.find_sample_file_results_with_filters(
        SAMPLE_XPATH, FILTERS, _log()[1]
    )

    assert result["code"] == "SAMPLE_FILE_SEARCH_FAILED"
    assert world.driver_stops == 1


def test_a_browser_that_closed_mid_check_file_is_reported_as_a_boundary(
    clock, monkeypatch
):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)
    _explode(monkeypatch, RuntimeError("CHROME_CLOSED"))

    result = modules.find_sample_file_results_with_filters(
        SAMPLE_XPATH, FILTERS, _log()[1]
    )

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_stops == 1


# --- mở một Sample người dùng đã chọn -----------------------------------


def test_a_grid_that_closed_before_the_user_picked_is_reported_as_expired(
    clock, monkeypatch
):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)

    def boom(*_args, **_kwargs):
        raise PlaywrightError("frame was detached")

    patch_automation(monkeypatch, modules, "_click_sample_style_result", boom)

    result = modules.open_sample_file_result("0", "ABC123", _log()[1])

    assert result["code"] == "SAMPLE_RESULT_EXPIRED"
    assert world.driver_stops == 1


def test_an_unexpected_failure_while_opening_a_sample_is_technical(
    clock, monkeypatch
):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)

    def boom(*_args, **_kwargs):
        raise ValueError("WFX trả về HTML lạ")

    patch_automation(monkeypatch, modules, "_click_sample_style_result", boom)

    result = modules.open_sample_file_result("0", "ABC123", _log()[1])

    assert result["code"] == "SAMPLE_FILE_OPEN_FAILED"
    assert "ValueError" in result["message"]
    assert world.driver_stops == 1


def test_a_browser_that_closed_before_opening_a_sample_is_a_boundary(
    clock, monkeypatch
):
    world = _world(clock, _grid(clock))
    wire_automation(monkeypatch, modules, world)

    def boom(*_args, **_kwargs):
        raise RuntimeError("CHROME_CLOSED")

    patch_automation(monkeypatch, modules, "_click_sample_style_result", boom)

    result = modules.open_sample_file_result("0", "ABC123", _log()[1])

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_stops == 1


def test_the_only_row_changing_before_the_click_is_reported_as_expired(clock):
    class Fragile(SampleGridFrame):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.root = _DetachingRoot(self.root)

    frame = Fragile(clock, rows=[SampleRow("0", style_code="ABC123")])

    result = modules._sample_file_result(frame, _log()[1])

    assert result["code"] == "SAMPLE_RESULT_EXPIRED"
    assert "trước khi mở Style Code" in result["message"]
