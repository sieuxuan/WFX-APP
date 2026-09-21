"""Lớp Win32 của panel chạy trên một desktop giả.

`wfx_panel/win32_window.py` ở mức 31%: `tests/test_win32_window.py` đã phủ các
hàm hình học thuần, nhưng mọi nhánh thật sự gọi `ctypes.windll.user32` thì chưa.
Đó lại là nơi giữ những ràng buộc đắt nhất của CLAUDE.md:

* "native bounds phải scale theo DPI của HWND … kể cả khi cửa sổ đang hidden."
* "Bubble/menu bị loại khỏi việc chọn cửa sổ chính" — nếu không, mọi helper
  rect/bounds/front sẽ nhắm nhầm cửa sổ.
* "Menu chuột phải là tool-window pywebview riêng … không dùng
  `TrackPopupMenu`"; toast và menu không được lấy focus.
* "Mọi hàm trả giá trị an toàn khi Win32 lỗi — không được ném lỗi làm sập app."
"""

from __future__ import annotations

import ctypes

import pytest

from tests.fakes.win32 import Desktop, Monitor, Window, install
from wfx_panel import win32_window as win32

PID = 4242
OTHER_PID = 777


def _desktop(monkeypatch, windows=(), monitors=None, **kwargs) -> Desktop:
    desktop = Desktop(
        windows=list(windows),
        monitors=dict(monitors or {1: Monitor(1, (0, 0, 1920, 1040))}),
        **kwargs,
    )
    return install(monkeypatch, desktop, pid=PID)


def _panel(**kwargs) -> Window:
    return Window(hwnd=10, pid=PID, title=win32.MAIN_WINDOW_TITLE, **kwargs)


def _bubble(**kwargs) -> Window:
    return Window(hwnd=20, pid=PID, title=win32.BUBBLE_WINDOW_TITLE, **kwargs)


def _menu(**kwargs) -> Window:
    return Window(hwnd=30, pid=PID, title=win32.BUBBLE_MENU_TITLE, **kwargs)


# --- ưu tiên cửa sổ -------------------------------------------------------


def test_the_main_panel_wins_over_any_other_window_of_this_process():
    assert win32._window_priority(win32.os.getpid(), win32.MAIN_WINDOW_TITLE) == 0


@pytest.mark.parametrize(
    "title", [win32.BUBBLE_WINDOW_TITLE, win32.BUBBLE_MENU_TITLE]
)
def test_the_bubble_and_its_menu_are_never_the_main_window(title):
    assert win32._window_priority(win32.os.getpid(), title) is None


def test_another_process_is_always_the_lowest_priority():
    assert win32._window_priority(win32.os.getpid() + 1, "Chrome") == 1


def test_an_unknown_window_of_this_process_is_the_last_resort():
    assert win32._window_priority(win32.os.getpid(), "Hộp thoại") == 2


# --- đọc tiêu đề ----------------------------------------------------------


def test_window_text_is_read_through_the_length_prefixed_api(monkeypatch):
    _desktop(monkeypatch, [_panel()])
    user32 = ctypes.windll.user32

    assert win32._native_window_text(user32, 10) == win32.MAIN_WINDOW_TITLE
    assert win32._native_window_text(user32, 99) == ""


def test_window_text_returns_empty_when_win32_fails(monkeypatch):
    _desktop(monkeypatch, [_panel()])

    class Broken:
        def GetWindowTextLengthW(self, _hwnd):
            raise OSError("user32 lỗi")

    assert win32._native_window_text(Broken(), 10) == ""


# --- DPI ------------------------------------------------------------------


def test_dpi_comes_from_the_window_even_while_it_is_hidden(monkeypatch):
    _desktop(
        monkeypatch,
        [_panel(visible=False)],
        dpi={10: 144},
    )

    assert win32._window_dpi_by_title(win32.MAIN_WINDOW_TITLE) == 144


def test_dpi_falls_back_to_the_system_when_the_window_has_none(monkeypatch):
    _desktop(monkeypatch, [_panel()], system_dpi=120)

    assert win32._window_dpi_by_title(win32.MAIN_WINDOW_TITLE) == 120


def test_dpi_falls_back_to_96_when_nothing_answers(monkeypatch):
    _desktop(monkeypatch, [], system_dpi=0)

    assert win32._window_dpi_by_title("Không có") == win32.DEFAULT_DPI


def test_dpi_is_96_off_windows(monkeypatch):
    monkeypatch.setattr(win32.os, "name", "posix")

    assert win32._window_dpi_by_title(win32.MAIN_WINDOW_TITLE) == 96


# --- tìm HWND -------------------------------------------------------------


def test_find_window_matches_this_process_and_the_exact_title(monkeypatch):
    _desktop(
        monkeypatch,
        [
            Window(hwnd=5, pid=OTHER_PID, title=win32.MAIN_WINDOW_TITLE),
            _panel(),
        ],
    )

    assert win32._find_window_hwnd(win32.MAIN_WINDOW_TITLE) == 10


def test_find_window_skips_a_hidden_window_but_any_state_does_not(monkeypatch):
    _desktop(monkeypatch, [_panel(visible=False)])

    assert win32._find_window_hwnd(win32.MAIN_WINDOW_TITLE) is None
    assert win32._find_window_hwnd_any_state(win32.MAIN_WINDOW_TITLE) == 10


def test_find_window_without_a_title_is_none(monkeypatch):
    _desktop(monkeypatch, [_panel()])

    assert win32._find_window_hwnd("") is None


def test_find_window_is_none_off_windows(monkeypatch):
    monkeypatch.setattr(win32.os, "name", "posix")

    assert win32._find_window_hwnd(win32.MAIN_WINDOW_TITLE) is None


# --- đưa lên trước --------------------------------------------------------


def test_bring_to_front_picks_the_panel_over_bubble_and_menu(monkeypatch):
    desktop = _desktop(monkeypatch, [_menu(), _bubble(), _panel()])

    assert win32._bring_process_window_to_front() is True
    assert ("SetForegroundWindow", 10) in desktop.calls


def test_bring_to_front_restores_only_a_minimized_window(monkeypatch):
    desktop = _desktop(monkeypatch, [_panel(minimized=True)])

    win32._bring_process_window_to_front()

    assert ("ShowWindow", 10, 9) in desktop.calls


def test_bring_to_front_never_restores_a_maximized_window(monkeypatch):
    desktop = _desktop(monkeypatch, [_panel(minimized=False)])

    win32._bring_process_window_to_front()

    assert not any(call[0] == "ShowWindow" for call in desktop.calls)


@pytest.mark.parametrize(
    ("on_top", "expected"), [(True, -1), (False, -2)]
)
def test_bring_to_front_applies_the_requested_topmost_state(
    monkeypatch, on_top, expected
):
    desktop = _desktop(monkeypatch, [_panel()])

    win32._bring_process_window_to_front(on_top=on_top)

    positions = [call for call in desktop.calls if call[0] == "SetWindowPos"]
    assert positions and positions[0][2] == expected


def test_bring_to_front_leaves_topmost_alone_when_asked_to(monkeypatch):
    desktop = _desktop(monkeypatch, [_panel()])

    win32._bring_process_window_to_front(on_top=None)

    assert not any(call[0] == "SetWindowPos" for call in desktop.calls)


def test_bring_to_front_detaches_every_thread_it_attached(monkeypatch):
    desktop = _desktop(
        monkeypatch,
        [_panel(), Window(hwnd=5, pid=OTHER_PID, title="Chrome")],
        foreground=5,
    )

    win32._bring_process_window_to_front()

    attaches = [call for call in desktop.calls if call[0] == "AttachThreadInput"]
    assert attaches.count(("AttachThreadInput", True)) == attaches.count(
        ("AttachThreadInput", False)
    )


def test_bring_to_front_is_false_when_the_process_has_no_window(monkeypatch):
    _desktop(monkeypatch, [_bubble()])

    assert win32._bring_process_window_to_front() is False


def test_bring_to_front_is_false_off_windows(monkeypatch):
    monkeypatch.setattr(win32.os, "name", "posix")

    assert win32._bring_process_window_to_front() is False


# --- work area ------------------------------------------------------------


def test_work_area_follows_the_monitor_of_the_panel(monkeypatch):
    _desktop(
        monkeypatch,
        [_panel(monitor=2)],
        monitors={
            1: Monitor(1, (0, 0, 1920, 1040)),
            2: Monitor(2, (1920, 0, 3840, 1080)),
        },
    )

    assert win32._work_area_for_process_window(PID) == (1920, 0, 3840, 1080)


def test_work_area_is_none_without_a_process_id(monkeypatch):
    _desktop(monkeypatch, [_panel()])

    assert win32._work_area_for_process_window(None) is None


def test_work_area_is_none_when_the_process_has_no_window(monkeypatch):
    _desktop(monkeypatch, [_bubble()])

    assert win32._work_area_for_process_window(PID) is None


def test_work_area_by_hwnd_works_for_a_bubble_while_the_panel_is_hidden(
    monkeypatch,
):
    _desktop(
        monkeypatch,
        [_panel(visible=False), _bubble(monitor=2)],
        monitors={2: Monitor(2, (0, 0, 1280, 960))},
    )

    assert win32._work_area_for_hwnd(20) == (0, 0, 1280, 960)


def test_work_area_by_hwnd_is_none_without_a_monitor(monkeypatch):
    _desktop(monkeypatch, [_panel(monitor=0)])

    assert win32._work_area_for_hwnd(10) is None


def test_work_area_by_hwnd_is_none_when_monitor_info_fails(monkeypatch):
    _desktop(monkeypatch, [_panel()], fail={"GetMonitorInfoW"})

    assert win32._work_area_for_hwnd(10) is None


def test_work_area_by_hwnd_is_none_without_an_hwnd(monkeypatch):
    _desktop(monkeypatch, [])

    assert win32._work_area_for_hwnd(None) is None


def test_work_area_by_title_uses_the_visible_window_only(monkeypatch):
    _desktop(
        monkeypatch,
        [_panel(visible=False)],
        monitors={1: Monitor(1, (0, 0, 800, 600))},
    )

    assert win32._work_area_for_window_title(win32.MAIN_WINDOW_TITLE) is None
    assert win32._work_area_for_window_title_any_state(
        win32.MAIN_WINDOW_TITLE
    ) == (0, 0, 800, 600)


# --- đặt bounds -----------------------------------------------------------


def test_process_bounds_move_and_resize_the_panel(monkeypatch):
    desktop = _desktop(monkeypatch, [_panel(), _bubble()])

    assert win32._set_process_window_bounds(PID, 100, 50, 440, 620) is True
    assert desktop.window(10).rect == (100, 50, 540, 670)
    assert desktop.window(20).rect == (0, 0, 100, 100)


def test_process_bounds_without_a_size_keep_the_current_one(monkeypatch):
    desktop = _desktop(monkeypatch, [_panel(rect=(0, 0, 440, 620))])

    win32._set_process_window_bounds(PID, 300, 200)

    positions = [call for call in desktop.calls if call[0] == "SetWindowPos"]
    assert positions[0][7] & 0x0001  # NOSIZE
    assert desktop.window(10).rect == (300, 200, 740, 820)


def test_process_bounds_are_false_without_a_window(monkeypatch):
    _desktop(monkeypatch, [_bubble()])

    assert win32._set_process_window_bounds(PID, 0, 0) is False


def test_process_bounds_are_false_off_windows(monkeypatch):
    monkeypatch.setattr(win32.os, "name", "posix")

    assert win32._set_process_window_bounds(PID, 0, 0) is False


def test_bounds_by_title_never_shows_a_hidden_window(monkeypatch):
    """`start_hidden=True` vẫn phải đặt được vị trí mà không hiện panel."""
    desktop = _desktop(monkeypatch, [_panel(visible=False)])

    assert win32._set_bounds_by_title(win32.MAIN_WINDOW_TITLE, 10, 20, 48, 48)
    assert desktop.window(10).visible is False
    assert desktop.window(10).rect == (10, 20, 58, 68)


def test_bounds_by_title_keep_the_size_when_none_is_given(monkeypatch):
    desktop = _desktop(monkeypatch, [_panel(rect=(0, 0, 48, 48))])

    win32._set_bounds_by_title(win32.MAIN_WINDOW_TITLE, 5, 6)

    positions = [call for call in desktop.calls if call[0] == "SetWindowPos"]
    assert positions[0][7] & 0x0001


def test_bounds_by_title_are_false_for_an_unknown_window(monkeypatch):
    _desktop(monkeypatch, [])

    assert win32._set_bounds_by_title("Không có", 0, 0) is False


def test_bounds_by_title_report_a_win32_failure(monkeypatch):
    _desktop(monkeypatch, [_panel()], fail={"SetWindowPos"})

    assert win32._set_bounds_by_title(win32.MAIN_WINDOW_TITLE, 0, 0) is False


# --- rect -----------------------------------------------------------------


def test_rect_by_title_reads_the_live_rect(monkeypatch):
    _desktop(monkeypatch, [_panel(rect=(11, 22, 33, 44))])

    assert win32._window_rect_by_title(win32.MAIN_WINDOW_TITLE) == (11, 22, 33, 44)


def test_rect_by_title_any_state_also_reads_a_hidden_window(monkeypatch):
    _desktop(monkeypatch, [_panel(rect=(1, 2, 3, 4), visible=False)])

    assert win32._window_rect_by_title(win32.MAIN_WINDOW_TITLE) is None
    assert win32._window_rect_by_title_any_state(win32.MAIN_WINDOW_TITLE) == (
        1,
        2,
        3,
        4,
    )


def test_rect_is_none_without_an_hwnd(monkeypatch):
    _desktop(monkeypatch, [])

    assert win32._window_rect_for_hwnd(None) is None


def test_rect_is_none_when_win32_refuses(monkeypatch):
    _desktop(monkeypatch, [_panel()], fail={"GetWindowRect"})

    assert win32._window_rect_for_hwnd(10) is None


# --- hiện/ẩn --------------------------------------------------------------


def test_visibility_hides_a_window_and_confirms_it(monkeypatch):
    desktop = _desktop(monkeypatch, [_panel()])

    assert win32._native_window_visibility(win32.MAIN_WINDOW_TITLE, False) is True
    assert desktop.window(10).visible is False


def test_visibility_restores_a_minimized_window_instead_of_showing_it(
    monkeypatch,
):
    desktop = _desktop(monkeypatch, [_panel(minimized=True, visible=False)])

    win32._native_window_visibility(win32.MAIN_WINDOW_TITLE, True)

    assert ("ShowWindow", 10, 9) in desktop.calls


def test_visibility_shows_a_normal_window_with_sw_show(monkeypatch):
    desktop = _desktop(monkeypatch, [_panel(visible=False)])

    win32._native_window_visibility(win32.MAIN_WINDOW_TITLE, True)

    assert ("ShowWindow", 10, 5) in desktop.calls


@pytest.mark.parametrize(("on_top", "expected"), [(True, -1), (False, -2)])
def test_visibility_can_set_the_topmost_state(monkeypatch, on_top, expected):
    desktop = _desktop(monkeypatch, [_panel()])

    win32._native_window_visibility(
        win32.MAIN_WINDOW_TITLE, True, on_top=on_top
    )

    positions = [call for call in desktop.calls if call[0] == "SetWindowPos"]
    assert positions and positions[0][2] == expected


def test_visibility_is_false_for_an_unknown_window(monkeypatch):
    _desktop(monkeypatch, [])

    assert win32._native_window_visibility("Không có", True) is False


# --- popup tool-window ----------------------------------------------------


TOOLWINDOW = 0x00000080
APPWINDOW = 0x00040000
NOACTIVATE = 0x08000000


def test_a_popup_becomes_a_tool_window_without_a_taskbar_button(monkeypatch):
    desktop = _desktop(
        monkeypatch, [_menu(style=APPWINDOW, visible=False)]
    )

    assert win32._native_popup_visibility(
        win32.BUBBLE_MENU_TITLE, True, 10, 20, 180, 90
    )

    style = desktop.window(30).style
    assert style & TOOLWINDOW
    assert not style & APPWINDOW


def test_a_popup_that_must_not_steal_focus_keeps_noactivate(monkeypatch):
    desktop = _desktop(monkeypatch, [_menu(visible=False)])

    win32._native_popup_visibility(win32.BUBBLE_MENU_TITLE, True)

    assert desktop.window(30).style & NOACTIVATE
    assert ("ShowWindow", 30, 4) in desktop.calls
    assert not any(call[0] == "SetForegroundWindow" for call in desktop.calls)


def test_a_popup_asked_to_activate_takes_focus(monkeypatch):
    desktop = _desktop(monkeypatch, [_menu(visible=False)])

    win32._native_popup_visibility(
        win32.BUBBLE_MENU_TITLE, True, activate=True
    )

    assert not desktop.window(30).style & NOACTIVATE
    assert ("ShowWindow", 30, 5) in desktop.calls
    assert ("SetForegroundWindow", 30) in desktop.calls
    assert ("SetFocus", 30) in desktop.calls


def test_hiding_a_popup_does_not_move_it(monkeypatch):
    desktop = _desktop(monkeypatch, [_menu(rect=(7, 8, 9, 10))])

    assert win32._native_popup_visibility(win32.BUBBLE_MENU_TITLE, False) is True
    assert desktop.window(30).visible is False
    assert desktop.window(30).rect == (7, 8, 9, 10)


def test_a_popup_is_false_for_an_unknown_window(monkeypatch):
    _desktop(monkeypatch, [])

    assert win32._native_popup_visibility("Không có", True) is False


def test_a_popup_is_false_when_win32_refuses_to_move_it(monkeypatch):
    _desktop(monkeypatch, [_menu(visible=False)], fail={"SetWindowPos"})

    assert win32._native_popup_visibility(win32.BUBBLE_MENU_TITLE, True) is False


def test_a_popup_is_false_off_windows(monkeypatch):
    monkeypatch.setattr(win32.os, "name", "posix")

    assert win32._native_popup_visibility(win32.BUBBLE_MENU_TITLE, True) is False


# --- foreground -----------------------------------------------------------


def test_foreground_process_id_reads_the_owner_of_the_active_window(
    monkeypatch,
):
    _desktop(
        monkeypatch,
        [Window(hwnd=5, pid=OTHER_PID, title="Chrome")],
        foreground=5,
    )

    assert win32._foreground_process_id() == OTHER_PID
    assert win32._foreground_window_hwnd() == 5


def test_foreground_is_none_when_nothing_is_active(monkeypatch):
    _desktop(monkeypatch, [_panel()], foreground=None)

    assert win32._foreground_process_id() is None
    assert win32._foreground_window_hwnd() is None


def test_foreground_is_none_off_windows(monkeypatch):
    monkeypatch.setattr(win32.os, "name", "posix")

    assert win32._foreground_process_id() is None
    assert win32._foreground_window_hwnd() is None


# --- chuột ----------------------------------------------------------------


def test_the_pointer_over_the_window_itself_counts_as_inside(monkeypatch):
    _desktop(monkeypatch, [_bubble()], cursor_hwnd=20)

    assert win32._right_mouse_state_over_hwnd(20) == (False, True)


def test_the_pointer_over_a_child_window_still_counts_as_inside(monkeypatch):
    _desktop(
        monkeypatch,
        [_bubble(), Window(hwnd=21, pid=PID, title="WebView", parent=20)],
        cursor_hwnd=21,
    )

    assert win32._right_mouse_state_over_hwnd(20)[1] is True


def test_the_pointer_over_another_window_is_outside(monkeypatch):
    _desktop(
        monkeypatch,
        [_bubble(), Window(hwnd=5, pid=OTHER_PID, title="Chrome")],
        cursor_hwnd=5,
    )

    assert win32._right_mouse_state_over_hwnd(20)[1] is False


def test_a_held_right_button_is_reported(monkeypatch):
    _desktop(monkeypatch, [_bubble()], cursor_hwnd=20, pressed_keys={0x02})

    assert win32._right_mouse_state_over_hwnd(20) == (True, True)


def test_both_buttons_are_watched_when_closing_a_popup(monkeypatch):
    _desktop(monkeypatch, [_bubble()], cursor_hwnd=20, pressed_keys={0x01})

    assert win32._mouse_buttons_state_over_hwnd(20)[0] is True
    assert win32._right_mouse_state_over_hwnd(20)[0] is False


def test_mouse_state_is_false_for_a_window_that_no_longer_exists(monkeypatch):
    _desktop(monkeypatch, [])

    assert win32._mouse_state_over_hwnd(99, (0x02,)) == (False, False)


def test_mouse_state_is_false_without_an_hwnd(monkeypatch):
    _desktop(monkeypatch, [_bubble()])

    assert win32._mouse_state_over_hwnd(None, (0x02,)) == (False, False)


def test_mouse_state_is_false_when_the_cursor_cannot_be_read(monkeypatch):
    _desktop(monkeypatch, [_bubble()], fail={"GetCursorPos"})

    assert win32._mouse_state_over_hwnd(20, (0x02,)) == (False, False)


# --- bo góc DWM -----------------------------------------------------------


def test_smooth_corners_ask_dwm_for_a_rounded_borderless_window(monkeypatch):
    desktop = _desktop(monkeypatch, [_bubble()])

    assert win32._set_smooth_corners_by_title(win32.BUBBLE_WINDOW_TITLE) is True
    assert ("DwmSetWindowAttribute", 20, 33) in desktop.calls
    assert ("DwmSetWindowAttribute", 20, 34) in desktop.calls


def test_smooth_corners_report_false_on_an_older_windows(monkeypatch):
    _desktop(
        monkeypatch, [_bubble()], fail={"DwmSetWindowAttribute"}
    )

    assert win32._set_smooth_corners_by_title(win32.BUBBLE_WINDOW_TITLE) is False


def test_smooth_corners_are_false_for_an_unknown_window(monkeypatch):
    _desktop(monkeypatch, [])

    assert win32._set_smooth_corners_by_title("Không có") is False
