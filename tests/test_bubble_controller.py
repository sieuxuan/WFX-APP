"""Bubble launcher: menu chuột phải, vị trí, và các callback cửa sổ.

CLAUDE.md: menu chuột phải là tool-window pywebview riêng, CHỈ tạo khi người
dùng mở lần đầu chứ không tạo sẵn lúc startup; bubble bị đóng ngoài ý muốn thì
thu vào khay hệ thống chứ không hủy cửa sổ.
"""

from __future__ import annotations

import threading

import pytest

import wfx_panel.app.bubble as bubble_module
import wfx_panel.panel_app as panel_app
from tests.test_panel_app import patch_shell

MENU_TITLE = bubble_module.BUBBLE_MENU_TITLE
BUBBLE_TITLE = bubble_module.BUBBLE_WINDOW_TITLE


@pytest.fixture
def app(monkeypatch):
    instance = panel_app.PanelApp()
    # Không để lượt ép kích thước bubble spawn thread nền trong test.
    monkeypatch.setattr(
        instance._bubble, "_schedule_bubble_native_bounds", lambda: None
    )
    return instance


@pytest.fixture
def scheduling_app():
    """Như `app` nhưng giữ nguyên `_schedule_bubble_native_bounds` thật."""
    return panel_app.PanelApp()


class FakeWindow:
    def __init__(self, *, fail=()):
        self.fail = set(fail)
        self.calls: list[str] = []
        self.on_top = False
        self.events = type(
            "Events",
            (),
            {"loaded": _Signal(), "closing": _Signal()},
        )()

    def _do(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise RuntimeError(f"{name} thất bại")

    def show(self):
        self._do("show")

    def hide(self):
        self._do("hide")

    def destroy(self):
        self._do("destroy")

    def resize(self, *_args):
        self._do("resize")

    def move(self, *_args):
        self._do("move")


class _Signal:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


# --- hiện lại bubble ----------------------------------------------------


def test_showing_the_bubble_falls_back_to_pywebview_when_win32_fails(
    app, monkeypatch
):
    window = FakeWindow()
    app.bubble_window = window
    app._bubble_hidden = True
    app._always_on_top = True
    patch_shell(monkeypatch, "_native_window_visibility", lambda *_a, **_k: False)

    app._bubble._restore_bubble()

    assert window.calls == ["show"]
    assert window.on_top is True
    assert app._bubble_hidden is False


def test_a_pywebview_window_that_refuses_to_show_does_not_crash(
    app, monkeypatch
):
    app.bubble_window = FakeWindow(fail={"show"})
    app._bubble_hidden = True
    patch_shell(monkeypatch, "_native_window_visibility", lambda *_a, **_k: False)

    app._bubble._restore_bubble()

    assert app._bubble_hidden is False


# --- theo dõi thao tác chuột --------------------------------------------


def test_an_interaction_that_never_ends_times_itself_out(app, monkeypatch):
    app.begin_bubble_interaction()
    assert app._bubble._bubble_interaction_active() is True

    monkeypatch.setattr(
        bubble_module.time, "monotonic", lambda: app._bubble_pointer_started + 31
    )

    assert app._bubble._bubble_interaction_active() is False
    assert app._bubble_pointer_down is False


def test_an_interaction_that_ends_normally_releases_the_monitor(app):
    app.begin_bubble_interaction()

    assert app.end_bubble_interaction()["code"] == "BUBBLE_INTERACTION_ENDED"
    assert app._bubble._bubble_interaction_active() is False


# --- lưu vị trí ---------------------------------------------------------


def test_a_position_that_cannot_be_read_is_reported(app, monkeypatch):
    patch_shell(monkeypatch, "_window_rect_by_title", lambda _title: None)
    patch_shell(
        monkeypatch, "_work_area_for_window_title", lambda _title: (0, 0, 1920, 1080)
    )

    result = app.save_bubble_position()

    assert result["code"] == "BUBBLE_POSITION_UNAVAILABLE"


def test_a_bubble_dragged_outside_the_work_area_is_pulled_back(app, monkeypatch):
    moved: list[tuple] = []
    saved: list[dict] = []
    patch_shell(
        monkeypatch, "_window_rect_by_title", lambda _title: (1900, 1060, 1948, 1108)
    )
    patch_shell(
        monkeypatch, "_work_area_for_window_title", lambda _title: (0, 0, 1920, 1080)
    )
    patch_shell(
        monkeypatch,
        "_set_bounds_by_title",
        lambda *args: moved.append(args) or True,
    )
    monkeypatch.setattr(
        bubble_module.prefs, "save_prefs", lambda **kwargs: saved.append(kwargs)
    )

    result = app.save_bubble_position()

    assert result["code"] == "BUBBLE_POSITION_SAVED"
    assert moved, "bubble ra ngoài màn hình phải được kéo về"
    assert saved[0]["compact_offset_x"] == result["x"]


# --- vị trí menu --------------------------------------------------------


def test_the_menu_opens_to_the_right_of_the_bubble_when_there_is_room(
    app, monkeypatch
):
    patch_shell(
        monkeypatch, "_window_rect_by_title", lambda _title: (100, 200, 148, 248)
    )
    patch_shell(
        monkeypatch, "_work_area_for_window_title", lambda _title: (0, 0, 1920, 1080)
    )
    patch_shell(monkeypatch, "_window_dpi_by_title", lambda _title: 96)

    x, _y, width, _height = app._bubble._bubble_menu_position()

    assert x > 148
    assert width == bubble_module.BUBBLE_MENU_WIDTH


def test_the_menu_flips_to_the_left_when_the_right_edge_is_too_close(
    app, monkeypatch
):
    patch_shell(
        monkeypatch,
        "_window_rect_by_title",
        lambda _title: (1860, 200, 1908, 248),
    )
    patch_shell(
        monkeypatch, "_work_area_for_window_title", lambda _title: (0, 0, 1920, 1080)
    )
    patch_shell(monkeypatch, "_window_dpi_by_title", lambda _title: 96)

    x, _y, _width, _height = app._bubble._bubble_menu_position()

    assert x < 1860


def test_a_bubble_win32_cannot_locate_puts_the_menu_at_the_margin(
    app, monkeypatch
):
    patch_shell(monkeypatch, "_window_rect_by_title", lambda _title: None)
    patch_shell(monkeypatch, "_work_area_for_window_title", lambda _title: None)
    patch_shell(monkeypatch, "_window_dpi_by_title", lambda _title: 96)

    x, y, _width, _height = app._bubble._bubble_menu_position()

    assert (x, y) == (
        bubble_module.WINDOW_MARGIN,
        bubble_module.WINDOW_MARGIN,
    )


# --- mở menu chuột phải -------------------------------------------------


def _wire_menu(app, monkeypatch, *, native=True, ensure=True):
    patch_shell(
        monkeypatch, "_native_popup_visibility", lambda *_a, **_k: native
    )
    patch_shell(
        monkeypatch, "_set_smooth_corners_by_title", lambda *_a, **_k: True
    )
    monkeypatch.setattr(
        app._bubble, "_bubble_menu_position", lambda: (10, 20, 200, 300)
    )
    monkeypatch.setattr(
        app._bubble, "_ensure_bubble_menu_window", lambda: ensure
    )


def test_the_menu_is_shown_through_win32_when_that_works(app, monkeypatch):
    _wire_menu(app, monkeypatch)
    app.bubble_menu_window = FakeWindow()

    result = app.bubble_context_menu()

    assert result["code"] == "MENU_OPENED"
    assert app._bubble_menu_visible is True
    assert app.bubble_menu_window.calls == []


def test_the_menu_falls_back_to_pywebview_when_win32_cannot_show_it(
    app, monkeypatch
):
    _wire_menu(app, monkeypatch, native=False)
    window = FakeWindow()
    app.bubble_menu_window = window

    result = app.bubble_context_menu()

    assert result["code"] == "MENU_OPENED"
    assert window.calls == ["resize", "move", "show"]


def test_a_menu_neither_path_can_show_is_reported(app, monkeypatch):
    _wire_menu(app, monkeypatch, native=False)
    app.bubble_menu_window = FakeWindow(fail={"show"})

    result = app.bubble_context_menu()

    assert result["code"] == "MENU_OPEN_FAILED"
    assert app._bubble_menu_visible is False


def test_a_menu_window_that_cannot_be_created_is_reported(app, monkeypatch):
    _wire_menu(app, monkeypatch, ensure=False)

    assert app.bubble_context_menu()["code"] == "MENU_NOT_READY"


def test_a_second_click_while_the_menu_is_open_does_not_reopen_it(
    app, monkeypatch
):
    _wire_menu(app, monkeypatch)
    app.bubble_menu_window = FakeWindow()
    app.bubble_context_menu()

    result = app.bubble_context_menu()

    assert result["code"] == "MENU_ALREADY_OPEN"


def test_a_menu_already_being_opened_elsewhere_is_left_alone(app):
    app._bubble_menu_lock.acquire()
    try:
        assert app.bubble_context_menu()["code"] == "MENU_ALREADY_OPEN"
    finally:
        app._bubble_menu_lock.release()


# --- tạo cửa sổ menu ----------------------------------------------------


def test_an_existing_menu_window_is_reused(app):
    app.bubble_menu_window = FakeWindow()

    assert app._bubble._ensure_bubble_menu_window() is True


def test_a_menu_still_being_destroyed_blocks_a_new_one(app):
    app.bubble_menu_window = None
    app._bubble_menu_destroyed.clear()

    assert app._bubble._ensure_bubble_menu_window() is False


def test_a_menu_window_is_created_on_demand_not_at_startup(app, monkeypatch):
    created: list[dict] = []
    window = FakeWindow()

    def create_window(title, **kwargs):
        created.append({"title": title, **kwargs})
        return window

    monkeypatch.setattr(bubble_module.webview, "create_window", create_window)
    app.bubble_menu_window = None
    app._bubble_menu_destroyed.set()

    assert app._bubble._ensure_bubble_menu_window() is True
    assert app.bubble_menu_window is window
    assert created[0]["title"] == MENU_TITLE
    assert created[0]["hidden"] is True
    assert created[0]["frameless"] is True
    assert window.events.loaded.handlers
    assert window.events.closing.handlers


def test_a_menu_window_pywebview_refuses_to_create_is_logged(app, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("GUI chưa sẵn sàng")

    monkeypatch.setattr(bubble_module.webview, "create_window", explode)
    lines: list[str] = []
    monkeypatch.setattr(app.api, "_log", lines.append)
    app.bubble_menu_window = None
    app._bubble_menu_destroyed.set()

    assert app._bubble._ensure_bubble_menu_window() is False
    assert any("Không tạo được menu" in line for line in lines)


# --- đóng menu ----------------------------------------------------------


def test_dismissing_the_menu_hides_then_destroys_it_off_the_gui_thread(
    app, monkeypatch
):
    patch_shell(monkeypatch, "_native_popup_visibility", lambda *_a, **_k: True)
    window = FakeWindow()
    app.bubble_menu_window = window
    app._bubble_menu_visible = True

    result = app._bubble.dismiss_bubble_menu()

    assert result["code"] == "MENU_DISMISSED"
    assert app.bubble_menu_window is None
    assert app._bubble_menu_visible is False
    assert app._bubble_menu_destroyed.wait(timeout=2)
    assert window.calls[:1] == ["hide"]
    assert "destroy" in window.calls


def test_a_menu_window_that_refuses_to_close_still_clears_the_state(
    app, monkeypatch
):
    patch_shell(monkeypatch, "_native_popup_visibility", lambda *_a, **_k: True)
    app.bubble_menu_window = FakeWindow(fail={"hide", "destroy"})

    app._bubble.dismiss_bubble_menu()

    assert app.bubble_menu_window is None
    assert app._bubble_menu_destroyed.wait(timeout=2)
    assert app._bubble_menu_destroying is False


def test_dismissing_a_menu_that_was_never_created_is_still_clean(
    app, monkeypatch
):
    patch_shell(monkeypatch, "_native_popup_visibility", lambda *_a, **_k: True)
    app.bubble_menu_window = None

    assert app._bubble.dismiss_bubble_menu()["code"] == "MENU_DISMISSED"


# --- lựa chọn trong menu ------------------------------------------------


def test_an_unknown_menu_choice_is_refused(app, monkeypatch):
    monkeypatch.setattr(app._bubble, "dismiss_bubble_menu", lambda: None)

    result = app.choose_bubble_menu("khong-ton-tai")

    assert result["code"] == "MENU_ACTION_INVALID"


# --- vị trí khởi động ---------------------------------------------------


def test_a_saved_offset_is_used_as_the_start_position(app):
    app._bubble_offset = (300, 400)

    assert app._bubble._bubble_start_position() == (300, 400)


def test_without_a_saved_offset_the_bubble_starts_top_right(app, monkeypatch):
    app._bubble_offset = None
    monkeypatch.setattr(
        bubble_module.webview,
        "screens",
        [type("Screen", (), {"width": 2560})()],
    )

    x, y = app._bubble._bubble_start_position()

    assert x == 2560 - bubble_module.BUBBLE_SIZE - bubble_module.WINDOW_MARGIN
    assert y == 120


def test_a_machine_whose_screen_size_cannot_be_read_falls_back_to_1920(
    app, monkeypatch
):
    app._bubble_offset = None

    class Broken(list):
        def __getitem__(self, index):
            raise RuntimeError("chưa có màn hình")

    monkeypatch.setattr(bubble_module.webview, "screens", Broken())

    x, _y = app._bubble._bubble_start_position()

    assert x == 1920 - bubble_module.BUBBLE_SIZE - bubble_module.WINDOW_MARGIN


# --- callback cửa sổ ----------------------------------------------------


def test_closing_the_bubble_hides_it_to_the_tray_instead_of_destroying_it(app):
    hidden: list[str] = []
    app.hide_to_tray = lambda: hidden.append("tray")

    assert app._bubble._on_bubble_closing() is False
    assert hidden == ["tray"]


def test_closing_the_bubble_while_quitting_lets_it_close(app):
    app._quitting = True
    app.hide_to_tray = lambda: pytest.fail("Đang thoát thì không thu vào tray")

    assert app._bubble._on_bubble_closing() is None


def test_closing_the_menu_window_dismisses_it_instead_of_destroying(app, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        app._bubble, "dismiss_bubble_menu", lambda: seen.append("dismiss")
    )

    assert app._bubble._on_bubble_menu_closing() is False
    assert seen == ["dismiss"]


@pytest.mark.parametrize("flag", ["_quitting", "_bubble_menu_destroying"])
def test_the_menu_closing_callback_steps_aside_while_shutting_down(app, flag):
    setattr(app, flag, True)
    app._bubble.dismiss_bubble_menu = lambda: pytest.fail("không được gọi lại")

    assert app._bubble._on_bubble_menu_closing() is None


def test_a_minimize_the_menu_itself_asked_for_does_not_reopen_the_panel(
    app, monkeypatch
):
    app._taskbar_minimize_requested = True
    monkeypatch.setattr(
        app._bubble,
        "_on_bubble_taskbar_event",
        lambda: pytest.fail("menu tự thu nhỏ thì không mở lại panel"),
    )

    app._bubble._on_bubble_minimized()

    assert app._taskbar_minimize_requested is False


def test_a_taskbar_minimize_opens_the_panel_again(app, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        app._bubble, "_on_bubble_taskbar_event", lambda: seen.append("open")
    )
    app._taskbar_minimize_requested = False

    app._bubble._on_bubble_minimized()

    assert seen == ["open"]


def test_a_restore_clears_the_debounce_so_the_first_click_works(app, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        app._bubble, "_on_bubble_taskbar_event", lambda: seen.append("open")
    )
    app._taskbar_minimize_requested = True
    app._bubble_direct_action_until = 9_999.0

    app._bubble._on_bubble_restored()

    assert seen == ["open"]
    assert app._bubble_direct_action_until == 0.0
    assert app._taskbar_minimize_requested is False


def test_the_taskbar_callback_returns_immediately_and_works_off_thread(app):
    done = threading.Event()
    app._open_panel_from_taskbar = lambda: done.set()

    app._bubble._on_bubble_taskbar_event()

    assert done.wait(timeout=2)


def test_the_menu_loaded_callback_only_rounds_its_corners(app, monkeypatch):
    seen: list[str] = []
    patch_shell(
        monkeypatch,
        "_set_smooth_corners_by_title",
        lambda title, *_a, **_k: seen.append(title),
    )

    app._bubble._on_bubble_menu_loaded()

    assert seen == [MENU_TITLE]


# --- lịch ép kích thước 48px logical ------------------------------------


def _wire_bounds(monkeypatch, rects, *, dpi=96, resized=True):
    values = list(rects)

    def rect(_title):
        return values.pop(0) if len(values) > 1 else values[0]

    patch_shell(monkeypatch, "_window_rect_by_title_any_state", rect)
    patch_shell(
        monkeypatch,
        "_work_area_for_window_title_any_state",
        lambda _title: (0, 0, 1920, 1080),
    )
    patch_shell(monkeypatch, "_window_dpi_by_title", lambda _title: dpi)
    patch_shell(monkeypatch, "_set_bounds_by_title", lambda *_a: resized)
    patch_shell(
        monkeypatch, "_set_smooth_corners_by_title", lambda *_a, **_k: True
    )
    monkeypatch.setattr(bubble_module.prefs, "save_prefs", lambda **_k: {})


def test_a_bubble_win32_cannot_locate_is_not_resized(app, monkeypatch):
    patch_shell(
        monkeypatch, "_window_rect_by_title_any_state", lambda _title: None
    )
    patch_shell(
        monkeypatch,
        "_work_area_for_window_title_any_state",
        lambda _title: (0, 0, 1920, 1080),
    )

    assert app._bubble._enforce_bubble_native_bounds() is False


def test_a_resize_win32_refuses_is_reported_as_not_done(app, monkeypatch):
    _wire_bounds(monkeypatch, [(100, 100, 148, 148)], resized=False)

    assert app._bubble._enforce_bubble_native_bounds() is False


def test_the_scheduler_does_nothing_more_when_the_first_try_worked(
    scheduling_app, monkeypatch
):
    monkeypatch.setattr(
        scheduling_app._bubble, "_enforce_bubble_native_bounds", lambda: True
    )
    started: list[str] = []
    monkeypatch.setattr(
        bubble_module.threading,
        "Thread",
        lambda **_kwargs: pytest.fail("không được spawn thread khi đã xong"),
    )

    scheduling_app._bubble._schedule_bubble_native_bounds()

    assert started == []


def test_the_scheduler_retries_in_the_background_until_the_bounds_stick(
    scheduling_app, monkeypatch
):
    attempts = {"n": 0}

    def enforce():
        attempts["n"] += 1
        return attempts["n"] >= 3

    monkeypatch.setattr(scheduling_app._bubble, "_enforce_bubble_native_bounds", enforce)
    monkeypatch.setattr(bubble_module.time, "sleep", lambda _seconds: None)

    scheduling_app._bubble._schedule_bubble_native_bounds()
    scheduling_app._bubble_size_thread.join(timeout=5)

    assert attempts["n"] == 3
    assert scheduling_app._bubble_size_thread.is_alive() is False


def test_a_retry_that_raises_is_recorded_instead_of_killing_the_thread(
    scheduling_app, monkeypatch
):
    """Thread nền không ai join; một OSError ở đây không được chết im lặng."""
    recorded: list[tuple] = []
    monkeypatch.setattr(
        bubble_module.crash_log,
        "record",
        lambda code, **fields: recorded.append((code, fields)),
    )
    monkeypatch.setattr(bubble_module.time, "sleep", lambda _seconds: None)
    calls = {"n": 0}

    def enforce():
        calls["n"] += 1
        if calls["n"] == 1:
            return False
        raise PermissionError("prefs.json đang bị khóa")

    monkeypatch.setattr(scheduling_app._bubble, "_enforce_bubble_native_bounds", enforce)

    scheduling_app._bubble._schedule_bubble_native_bounds()
    scheduling_app._bubble_size_thread.join(timeout=5)

    assert scheduling_app._bubble_size_thread.is_alive() is False
    assert recorded[-1][0] == "BUBBLE_NATIVE_SIZE_FAILED"
    assert "PermissionError" in recorded[-1][1]["exception"]


def test_the_monitor_waits_for_the_bubble_hwnd_before_watching_the_mouse(
    app, monkeypatch
):
    """Bubble chưa có HWND thì vòng poll bỏ lượt, không đọc trạng thái chuột."""

    class FakeStop:
        count = 0

        def wait(self, _seconds):
            self.count += 1
            return self.count > 2

    app._stop_status = FakeStop()
    hwnds = iter([None, 123])
    patch_shell(monkeypatch, "_find_window_hwnd", lambda _title: next(hwnds))
    probes: list[int] = []
    patch_shell(
        monkeypatch,
        "_right_mouse_state_over_hwnd",
        lambda hwnd: probes.append(hwnd) or (False, False),
    )

    app._bubble_context_menu_loop()

    assert probes == [123], "lượt đầu chưa có HWND thì phải bỏ qua"
