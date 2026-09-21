"""Đặt panel cạnh bubble và cơ chế tự thu khi mất focus.

CLAUDE.md: panel tự thu khi mất focus kể cả lúc automation đang chạy; ngoài
`window.blur`, monitor foreground Win32 là fallback BẮT BUỘC vì WebView2 đôi khi
bỏ lỡ blur. Nhưng không được thu chỉ vì automation vừa đưa Chrome lên foreground
khi con trỏ vẫn đang thao tác trong UI.
"""

from __future__ import annotations

import os

import pytest

import wfx_panel.app.placement as placement
import wfx_panel.panel_app as panel_app
from tests.test_panel_app import patch_shell

MAIN = placement.MAIN_WINDOW_TITLE
BUBBLE = placement.BUBBLE_WINDOW_TITLE


@pytest.fixture
def app(monkeypatch):
    instance = panel_app.PanelApp()
    monkeypatch.setattr(
        instance._bubble, "_schedule_bubble_native_bounds", lambda: None
    )
    return instance


class FakeWindow:
    def __init__(self, *, fail=()):
        self.fail = set(fail)
        self.calls: list[tuple] = []
        self.on_top = False

    def _do(self, name, *args):
        self.calls.append((name, *args))
        if name in self.fail:
            raise RuntimeError(f"{name} thất bại")

    def show(self):
        self._do("show")

    def hide(self):
        self._do("hide")

    def minimize(self):
        self._do("minimize")

    def resize(self, *args):
        self._do("resize", *args)

    def move(self, *args):
        self._do("move", *args)

    def evaluate_js(self, script):
        self._do("js", script)


# --- mở panel -----------------------------------------------------------


def test_opening_a_panel_that_was_never_created_is_reported(app):
    app.window = None

    assert app._placement.show_panel()["code"] == "PANEL_NOT_READY"


def test_a_panel_win32_cannot_show_falls_back_to_pywebview(app, monkeypatch):
    window = FakeWindow()
    app.window = window
    app._panel_visible = False
    patch_shell(monkeypatch, "_native_window_visibility", lambda *_a, **_k: False)
    patch_shell(
        monkeypatch, "_bring_process_window_to_front", lambda **_k: True
    )
    monkeypatch.setattr(
        app._placement, "_position_panel_beside_bubble", lambda: None
    )

    result = app._placement.show_panel()

    assert result["code"] == "PANEL_OPENED"
    assert ("show",) in window.calls
    assert app._panel_visible is True


def test_a_pywebview_window_that_refuses_every_call_still_reports_opened(
    app, monkeypatch
):
    app.window = FakeWindow(fail={"show", "js"})
    app._panel_visible = False
    patch_shell(monkeypatch, "_native_window_visibility", lambda *_a, **_k: False)
    patch_shell(
        monkeypatch, "_bring_process_window_to_front", lambda **_k: True
    )
    monkeypatch.setattr(
        app._placement, "_position_panel_beside_bubble", lambda: None
    )

    assert app._placement.show_panel()["code"] == "PANEL_OPENED"


def test_an_unexpected_failure_while_opening_is_reported(app, monkeypatch):
    app.window = FakeWindow()
    patch_shell(monkeypatch, "_native_window_visibility", lambda *_a, **_k: True)

    def explode():
        raise ValueError("bounds sai")

    monkeypatch.setattr(
        app._placement, "_position_panel_beside_bubble", explode
    )

    result = app._placement.show_panel()

    assert result["code"] == "PANEL_OPEN_FAILED"
    assert "bounds sai" in result["message"]


def test_toggling_hides_an_open_panel_and_opens_a_hidden_one(app, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        app._placement, "hide_panel", lambda: seen.append("hide")
    )
    monkeypatch.setattr(
        app._placement,
        "show_from_tray",
        lambda: seen.append("show") or {"ok": True, "code": "PANEL_OPENED"},
    )

    app._panel_visible = True
    assert app._placement.toggle_panel()["code"] == "PANEL_HIDDEN"
    app._panel_visible = False
    assert app._placement.toggle_panel()["code"] == "PANEL_OPENED"
    assert seen == ["hide", "show"]


# --- đặt panel cạnh bubble ----------------------------------------------


def _wire_position(monkeypatch, *, bubble, area, dpi=96, bounds_ok=True):
    patch_shell(monkeypatch, "_window_rect_by_title", lambda _title: bubble)
    patch_shell(
        monkeypatch, "_work_area_for_window_title", lambda _title: area
    )
    patch_shell(
        monkeypatch, "_work_area_for_process_window", lambda _pid: area
    )
    patch_shell(monkeypatch, "_window_dpi_by_title", lambda _title: dpi)
    placed: list[tuple] = []
    patch_shell(
        monkeypatch,
        "_set_process_window_bounds",
        lambda _pid, *args: placed.append(args) or bounds_ok,
    )
    return placed


def test_a_bubble_on_the_right_puts_the_panel_on_its_left(app, monkeypatch):
    placed = _wire_position(
        monkeypatch, bubble=(1800, 200, 1848, 248), area=(0, 0, 1920, 1080)
    )

    app._placement._position_panel_beside_bubble()

    assert placed[0][0] < 1800


def test_a_bubble_on_the_left_puts_the_panel_on_its_right(app, monkeypatch):
    placed = _wire_position(
        monkeypatch, bubble=(10, 200, 58, 248), area=(0, 0, 1920, 1080)
    )

    app._placement._position_panel_beside_bubble()

    assert placed[0][0] > 58


def test_a_work_area_narrower_than_the_panel_shrinks_it(app, monkeypatch):
    placed = _wire_position(
        monkeypatch, bubble=(10, 10, 58, 58), area=(0, 0, 300, 400)
    )

    app._placement._position_panel_beside_bubble()

    _x, _y, width, height = placed[0]
    assert width <= 300
    assert height <= 400


def test_without_a_work_area_the_side_is_chosen_from_the_bubble_alone(
    app, monkeypatch
):
    placed = _wire_position(monkeypatch, bubble=(10, 200, 58, 248), area=None)

    app._placement._position_panel_beside_bubble()

    assert placed[0][0] > 58


def test_without_a_bubble_the_panel_goes_to_the_top_right(app, monkeypatch):
    placed = _wire_position(
        monkeypatch, bubble=None, area=(0, 0, 1920, 1080)
    )

    app._placement._position_panel_beside_bubble()

    assert placed, "vẫn phải đặt panel ở đâu đó"


def test_a_bubble_with_no_room_on_either_side_picks_the_wider_one(
    app, monkeypatch
):
    placed = _wire_position(
        monkeypatch, bubble=(600, 200, 648, 248), area=(500, 0, 700, 1080)
    )

    app._placement._position_panel_beside_bubble()

    assert placed[0][0] >= 500


def test_a_win32_placement_that_fails_falls_back_to_pywebview(
    app, monkeypatch
):
    window = FakeWindow()
    app.window = window
    _wire_position(
        monkeypatch,
        bubble=(10, 200, 58, 248),
        area=(0, 0, 1920, 1080),
        bounds_ok=False,
    )

    app._placement._position_panel_beside_bubble()

    assert any(call[0] == "resize" for call in window.calls)
    assert any(call[0] == "move" for call in window.calls)


def test_a_pywebview_fallback_that_also_fails_does_not_crash(app, monkeypatch):
    app.window = FakeWindow(fail={"resize"})
    _wire_position(
        monkeypatch,
        bubble=(10, 200, 58, 248),
        area=(0, 0, 1920, 1080),
        bounds_ok=False,
    )

    app._placement._position_panel_beside_bubble()


# --- tự thu khi mất focus -----------------------------------------------


def test_a_hidden_panel_needs_no_hiding(app):
    app._panel_visible = False

    assert app._placement.request_panel_hide()["code"] == "PANEL_ALREADY_HIDDEN"


def test_a_pointer_still_inside_the_panel_keeps_it_open(app):
    app._panel_visible = True
    app._panel_pointer_inside = True
    app._panel_hide_pending = True

    assert app._placement.request_panel_hide()["code"] == "PANEL_POINTER_KEPT"
    assert app._panel_hide_pending is False


def test_focus_that_is_still_inside_this_app_keeps_the_panel_open(
    app, monkeypatch
):
    app._panel_visible = True
    app._panel_pointer_inside = False
    patch_shell(monkeypatch, "_foreground_process_id", lambda: os.getpid())

    assert app._placement.request_panel_hide()["code"] == "PANEL_FOCUS_KEPT"


def test_focus_moving_to_another_app_hides_the_panel(app, monkeypatch):
    app._panel_visible = True
    app._panel_pointer_inside = False
    patch_shell(monkeypatch, "_foreground_process_id", lambda: os.getpid() + 1)
    patch_shell(monkeypatch, "_native_window_visibility", lambda *_a, **_k: True)

    assert app._placement.request_panel_hide()["code"] == "PANEL_HIDDEN_ON_BLUR"
    assert app._panel_visible is False


# --- fallback monitor foreground ----------------------------------------


def test_a_hidden_panel_resets_the_blur_timer(app):
    app._panel_visible = False
    app._panel_focus_lost_since = 5.0
    app._panel_hide_pending = True

    app._placement._track_panel_foreground(os.getpid() + 1)

    assert app._panel_focus_lost_since == 0.0
    assert app._panel_hide_pending is False


def test_the_pointer_being_inside_beats_chrome_taking_the_foreground(app):
    """Automation đưa Chrome lên trước không được thu panel khi user đang rê."""
    app._panel_visible = True
    app._panel_pointer_inside = True
    app._panel_focus_lost_since = 5.0

    app._placement._track_panel_foreground(os.getpid() + 1)

    assert app._panel_focus_lost_since == 0.0


@pytest.mark.parametrize("foreground", [None, "self"])
def test_focus_inside_this_app_resets_the_blur_timer(app, foreground):
    app._panel_visible = True
    app._panel_pointer_inside = False
    app._panel_focus_lost_since = 5.0

    app._placement._track_panel_foreground(
        os.getpid() if foreground == "self" else None
    )

    assert app._panel_focus_lost_since == 0.0


def test_the_first_lost_focus_only_starts_the_grace_timer(app, monkeypatch):
    app._panel_visible = True
    app._panel_pointer_inside = False
    app._panel_focus_lost_since = 0.0
    monkeypatch.setattr(placement.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        app._placement, "hide_panel", lambda: pytest.fail("chưa hết grace")
    )

    app._placement._track_panel_foreground(os.getpid() + 1)

    assert app._panel_focus_lost_since == 100.0


def test_focus_lost_longer_than_the_grace_window_hides_the_panel(
    app, monkeypatch
):
    app._panel_visible = True
    app._panel_pointer_inside = False
    app._panel_focus_lost_since = 100.0
    monkeypatch.setattr(
        placement.time,
        "monotonic",
        lambda: 100.0 + placement.PANEL_BLUR_GRACE_SECONDS + 1,
    )
    hidden: list[str] = []
    monkeypatch.setattr(
        app._placement, "hide_panel", lambda: hidden.append("hide")
    )
    recorded: list[str] = []
    monkeypatch.setattr(
        placement.crash_log, "record", lambda code, **_f: recorded.append(code)
    )

    app._placement._track_panel_foreground(os.getpid() + 1)

    assert hidden == ["hide"]
    assert "PANEL_HIDDEN_NATIVE_BLUR" in recorded
    assert app._panel_focus_lost_since == 0.0


def test_a_pending_hide_request_is_honoured_immediately(app, monkeypatch):
    app._panel_visible = True
    app._panel_pointer_inside = False
    app._panel_hide_pending = True
    hidden: list[str] = []
    monkeypatch.setattr(
        app._placement, "hide_panel", lambda: hidden.append("hide")
    )
    monkeypatch.setattr(placement.crash_log, "record", lambda *_a, **_k: None)

    app._placement._track_panel_foreground(os.getpid() + 1)

    assert hidden == ["hide"]


# --- thu xuống taskbar / khay -------------------------------------------


def test_minimising_without_a_bubble_is_reported(app, monkeypatch):
    app.bubble_window = None
    monkeypatch.setattr(app._placement, "hide_panel", lambda: None)

    result = app._placement.minimize_to_taskbar()

    assert result["code"] == "BUBBLE_NOT_READY"


def test_a_bubble_that_refuses_to_minimise_clears_the_request_flag(
    app, monkeypatch
):
    app.bubble_window = FakeWindow(fail={"minimize"})
    monkeypatch.setattr(app._placement, "hide_panel", lambda: None)

    result = app._placement.minimize_to_taskbar()

    assert result["code"] == "TASKBAR_MINIMIZE_FAILED"
    assert app._taskbar_minimize_requested is False


def test_minimising_closes_an_open_bubble_menu_first(app, monkeypatch):
    seen: list[str] = []
    app.bubble_window = FakeWindow()
    app._bubble_menu_visible = True
    monkeypatch.setattr(
        app, "dismiss_bubble_menu", lambda: seen.append("dismiss")
    )
    monkeypatch.setattr(app._placement, "hide_panel", lambda: None)

    assert app._placement.minimize_to_taskbar()["code"] == "HIDDEN_TO_TASKBAR"
    assert seen == ["dismiss"]
    assert app._taskbar_minimize_requested is True


def test_hiding_to_the_tray_hides_the_bubble_too(app, monkeypatch):
    window = FakeWindow()
    app.bubble_window = window
    monkeypatch.setattr(app._placement, "hide_panel", lambda: None)

    app._placement.hide_to_tray()

    assert ("hide",) in window.calls
    assert app._bubble_hidden is True


def test_a_bubble_that_refuses_to_hide_still_marks_it_hidden(app, monkeypatch):
    app.bubble_window = FakeWindow(fail={"hide"})
    monkeypatch.setattr(app._placement, "hide_panel", lambda: None)

    app._placement.hide_to_tray()

    assert app._bubble_hidden is True


def test_showing_from_the_tray_restores_the_bubble_before_the_panel(
    app, monkeypatch
):
    order: list[str] = []
    monkeypatch.setattr(
        app, "_restore_bubble", lambda: order.append("bubble")
    )
    monkeypatch.setattr(
        app._placement,
        "show_panel",
        lambda: order.append("panel") or {"ok": True, "code": "PANEL_OPENED"},
    )

    assert app._placement.show_from_tray()["code"] == "PANEL_OPENED"
    assert order == ["bubble", "panel"]


# --- focus ô tìm module -------------------------------------------------


def test_the_search_box_is_focused_after_the_panel_opens(app):
    window = FakeWindow()
    app.window = window

    app._placement._focus_module_search()

    assert any("wfxFocusModuleSearch" in str(call) for call in window.calls)


def test_focusing_a_panel_that_does_not_exist_is_a_no_op(app):
    app.window = None

    app._placement._focus_module_search()


# --- các nhánh chịu lỗi nhỏ --------------------------------------------


def test_a_panel_that_refuses_to_hide_is_still_marked_hidden(app, monkeypatch):
    app.window = FakeWindow(fail={"hide"})
    app._panel_visible = True
    patch_shell(monkeypatch, "_native_window_visibility", lambda *_a, **_k: False)

    app._placement.hide_panel()

    assert app._panel_visible is False
    assert app._panel_focus_lost_since == 0.0


def test_a_window_that_refuses_the_on_top_flag_does_not_fail_the_open(
    app, monkeypatch
):
    class Stubborn(FakeWindow):
        """WebView2 từ chối đặt always-on-top sau khi cửa sổ đã dựng."""

        @property
        def on_top(self):
            return False

        @on_top.setter
        def on_top(self, value):
            if value:
                raise RuntimeError("WebView2 chưa sẵn sàng")

    app.window = Stubborn()
    app._panel_visible = True
    patch_shell(monkeypatch, "_native_window_visibility", lambda *_a, **_k: False)
    patch_shell(
        monkeypatch, "_bring_process_window_to_front", lambda **_k: True
    )
    monkeypatch.setattr(
        app._placement, "_position_panel_beside_bubble", lambda: None
    )

    assert app._placement.show_panel()["code"] == "PANEL_OPENED"


def test_a_bubble_left_of_centre_opens_the_panel_to_its_right(app, monkeypatch):
    placed = _wire_position(
        monkeypatch, bubble=(700, 200, 748, 248), area=(0, 0, 3000, 1080)
    )

    app._placement._position_panel_beside_bubble()

    assert placed[0][0] > 748


def test_a_bubble_right_of_centre_opens_the_panel_to_its_left(app, monkeypatch):
    placed = _wire_position(
        monkeypatch, bubble=(2000, 200, 2048, 248), area=(0, 0, 3000, 1080)
    )

    app._placement._position_panel_beside_bubble()

    assert placed[0][0] < 2000


def test_a_window_that_refuses_the_always_on_top_change_is_skipped(
    app, monkeypatch
):
    class Stubborn(FakeWindow):
        """WebView2 từ chối đặt always-on-top sau khi cửa sổ đã dựng."""

        @property
        def on_top(self):
            return False

        @on_top.setter
        def on_top(self, value):
            if value:
                raise RuntimeError("WebView2 chưa sẵn sàng")

    app.window = Stubborn()
    app.bubble_window = None
    patch_shell(monkeypatch, "_native_window_visibility", lambda *_a, **_k: False)

    app._placement._apply_always_on_top(True)

    assert app._always_on_top is True


def test_the_taskbar_monitor_arms_only_after_focus_left_the_app(
    app, monkeypatch
):
    class FakeStop:
        count = 0

        def wait(self, _seconds):
            self.count += 1
            return self.count > 3

    app._stop_status = FakeStop()
    pids = iter([os.getpid() + 1, os.getpid(), os.getpid()])
    patch_shell(monkeypatch, "_foreground_process_id", lambda: next(pids))
    patch_shell(monkeypatch, "_foreground_window_hwnd", lambda: 123)
    patch_shell(monkeypatch, "_find_window_hwnd", lambda _title: 123)
    monkeypatch.setattr(
        app._placement, "_track_panel_foreground", lambda _pid: None
    )
    monkeypatch.setattr(app._bubble, "_bubble_interaction_active", lambda: False)
    opened: list[str] = []
    monkeypatch.setattr(
        app._placement, "_open_panel_from_taskbar", lambda: opened.append("open")
    )

    app._placement._taskbar_activation_loop()

    assert opened == ["open"]
    assert app._taskbar_focus_armed is False


def test_a_click_that_is_really_a_bubble_drag_does_not_open_the_panel(
    app, monkeypatch
):
    class FakeStop:
        count = 0

        def wait(self, _seconds):
            self.count += 1
            return self.count > 2

    app._stop_status = FakeStop()
    pids = iter([os.getpid() + 1, os.getpid()])
    patch_shell(monkeypatch, "_foreground_process_id", lambda: next(pids))
    patch_shell(monkeypatch, "_foreground_window_hwnd", lambda: 123)
    patch_shell(monkeypatch, "_find_window_hwnd", lambda _title: 123)
    monkeypatch.setattr(
        app._placement, "_track_panel_foreground", lambda _pid: None
    )
    monkeypatch.setattr(app._bubble, "_bubble_interaction_active", lambda: True)
    monkeypatch.setattr(
        app._placement,
        "_open_panel_from_taskbar",
        lambda: pytest.fail("đang kéo bubble thì không mở panel"),
    )

    app._placement._taskbar_activation_loop()


def test_a_win32_probe_that_throws_does_not_kill_the_monitor(app, monkeypatch):
    class FakeStop:
        count = 0

        def wait(self, _seconds):
            self.count += 1
            return self.count > 2

    app._stop_status = FakeStop()

    def explode():
        raise RuntimeError("Win32 không phản hồi")

    patch_shell(monkeypatch, "_foreground_process_id", explode)

    app._placement._taskbar_activation_loop()


def test_hiding_to_the_tray_closes_an_open_bubble_menu_first(app, monkeypatch):
    seen: list[str] = []
    app.bubble_window = FakeWindow()
    app._bubble_menu_visible = True
    monkeypatch.setattr(
        app, "dismiss_bubble_menu", lambda: seen.append("dismiss")
    )
    monkeypatch.setattr(app._placement, "hide_panel", lambda: None)

    app._placement.hide_to_tray()

    assert seen == ["dismiss"]
    assert app._bubble_hidden is True
