import os
from pathlib import Path

from wfx_panel import panel_app, prefs


def test_icon_and_ui_paths_resolve_under_resource_dir():
    # Finding B: bundled read-only assets (ui/, assets/) must always resolve
    # from RESOURCE_DIR, both frozen and unfrozen — this is unrelated to where
    # user data (.env/prefs.json) is written.
    assert panel_app.ICON_PATH == prefs.RESOURCE_DIR / "wfx_panel" / "assets" / "wfx.ico"
    assert panel_app.UI_INDEX == prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "index.html"
    assert panel_app.NOTIFICATION_INDEX == prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "notification.html"
    assert panel_app.UI_INDEX.exists()
    assert panel_app.NOTIFICATION_INDEX.exists()


def test_legacy_app_entrypoint_uses_the_same_panel_ui():
    import app

    assert app.main is panel_app.main


def test_webview_uses_fresh_ui_cache():
    source = Path(panel_app.__file__).read_text(encoding="utf-8")
    assert "webview.start(background, private_mode=True)" in source
    # Bubble là cửa sổ riêng, thường trực (chat-head).
    assert "url=str(BUBBLE_INDEX)" in source
    # pywebview mặc định ép cửa sổ nhỏ thành khoảng 200×100 nếu không khai báo
    # min_size; launcher 48px khi đó chỉ nằm giữa một khung xanh rất lớn.
    assert "min_size=(BUBBLE_SIZE, BUBBLE_SIZE)" in source


def test_top_right_position_places_window_near_top_right(monkeypatch):
    class FakeScreen:
        width = 1920

    monkeypatch.setattr(panel_app.webview, "screens", [FakeScreen()], raising=False)
    x, y = panel_app._top_right_position()
    assert y == panel_app.WINDOW_MARGIN
    assert x == 1920 - panel_app.WINDOW_WIDTH - panel_app.WINDOW_MARGIN
    assert x > 0


def test_top_right_position_falls_back_safely_when_screens_unavailable(monkeypatch):
    # webview.screens can raise/be unavailable depending on backend/platform
    # readiness. This must never crash startup — fall back to a sane default.
    class ExplodingScreens:
        def __getitem__(self, index):
            raise RuntimeError("no GUI backend yet")

    monkeypatch.setattr(panel_app.webview, "screens", ExplodingScreens(), raising=False)
    x, y = panel_app._top_right_position()
    assert isinstance(x, int) and isinstance(y, int)
    assert x >= 0 and y >= 0


def test_module_results_route_to_external_notification():
    from wfx_panel.panel_app import PanelApp

    app = PanelApp()
    sent = []
    app.window = None
    app._show_notification = sent.append

    app._on_result("find_code", {"ok": True, "message": "xong"}, 0.2)
    app._on_result("switch_division", {"ok": True, "message": "đổi"}, 0.2)

    assert sent == [{"ok": True, "message": "xong"}]


def test_external_notification_failure_never_breaks_result_flow(monkeypatch):
    import wfx_panel.panel_app as module
    from wfx_panel.panel_app import PanelApp

    app = PanelApp()

    class ExplodingWindow:
        def evaluate_js(self, _script):
            raise RuntimeError("webview hỏng")

    app.notification_window = ExplodingWindow()
    app._notification_ready.set()
    app._toast_enabled = True
    monkeypatch.setattr(module, "_native_notification_visibility", lambda *_args: False)
    app._show_notification({"ok": True, "message": "xong"})


def test_apply_hotkey_returns_error_message_on_failure(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()

    def boom(spec, callback):
        raise ValueError("phím bị chiếm")

    monkeypatch.setattr(module.keyboard, "add_hotkey", boom)
    monkeypatch.setattr(module.keyboard, "remove_hotkey", lambda spec: None)
    assert "phím bị chiếm" in (app._apply_hotkey("ctrl+alt+j") or "")


def test_apply_hotkey_returns_none_on_success(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    registered = []
    monkeypatch.setattr(
        module.keyboard,
        "add_hotkey",
        lambda spec, callback: registered.append(spec),
    )
    monkeypatch.setattr(module.keyboard, "remove_hotkey", lambda spec: None)
    assert app._apply_hotkey("ctrl+alt+j") is None
    assert registered == ["ctrl+alt+j"]


def test_activate_shows_panel_and_fronts_window(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._bubble_hidden = False
    shown = []
    fronted = []

    class FakeWindow:
        on_top = False

        def show(self):
            shown.append(True)

        def resize(self, *_args):
            pass

        def move(self, *_args):
            pass

        def evaluate_js(self, script):
            shown.append(script)

    app.window = FakeWindow()
    monkeypatch.setattr(
        module, "_work_area_for_process_window", lambda _pid: (0, 0, 1920, 1080)
    )
    monkeypatch.setattr(module, "_window_rect_by_title", lambda _title: None)
    monkeypatch.setattr(module, "_set_process_window_bounds", lambda *_a: True)
    monkeypatch.setattr(
        module,
        "_bring_process_window_to_front",
        lambda **_kwargs: fronted.append(True) or True,
    )
    app.activate()
    assert shown[0] is True
    assert any("wfxFocusModuleSearch" in item for item in shown if isinstance(item, str))
    assert fronted == [True]
    assert app._panel_visible is True


def test_taskbar_activation_restores_bubble_and_opens_full_ui(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []

    class FakeBubble:
        def restore(self):
            calls.append("restore")

        def show(self):
            calls.append("bubble-show")

    app.bubble_window = FakeBubble()

    def show_panel():
        calls.append("panel-show")
        app._panel_visible = True
        return {"ok": True}

    app.show_panel = show_panel
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)

    app._open_panel_from_taskbar()

    assert calls == ["restore", "bubble-show", "panel-show"]
    assert app._panel_visible is True


def test_direct_bubble_click_does_not_double_toggle_from_taskbar(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []
    times = iter([100.0, 100.1, 101.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(times))
    app.show_panel = lambda: calls.append("panel-show") or {"ok": True}

    app.note_bubble_interaction()
    app._open_panel_from_taskbar()
    assert calls == []

    app._open_panel_from_taskbar()
    assert calls == ["panel-show"]


def test_taskbar_minimize_and_restore_events_open_panel(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    monkeypatch.setattr(module.threading, "Thread", ImmediateThread)
    app._open_panel_from_taskbar = lambda: calls.append("open")

    app._on_bubble_taskbar_event()
    app._on_bubble_taskbar_event()

    assert calls == ["open", "open"]


def test_taskbar_foreground_transition_opens_only_for_bubble(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    waits = iter([False, False, True])
    process_ids = iter([99999, os.getpid()])
    foreground_windows = iter([111, 4242])
    calls = []

    monkeypatch.setattr(app._stop_status, "wait", lambda _seconds: next(waits))
    monkeypatch.setattr(
        module, "_foreground_process_id", lambda: next(process_ids)
    )
    monkeypatch.setattr(
        module, "_foreground_window_hwnd", lambda: next(foreground_windows)
    )
    monkeypatch.setattr(module, "_find_window_hwnd", lambda _title: 4242)
    app._open_panel_from_taskbar = lambda: calls.append("open")

    app._taskbar_activation_loop()

    assert calls == ["open"]


def test_tray_foreground_window_cancels_taskbar_activation(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    waits = iter([False, False, False, True])
    process_ids = iter([99999, os.getpid(), os.getpid()])
    foreground_windows = iter([111, 7000, 4242])
    calls = []

    monkeypatch.setattr(app._stop_status, "wait", lambda _seconds: next(waits))
    monkeypatch.setattr(
        module, "_foreground_process_id", lambda: next(process_ids)
    )
    monkeypatch.setattr(
        module, "_foreground_window_hwnd", lambda: next(foreground_windows)
    )
    monkeypatch.setattr(module, "_find_window_hwnd", lambda _title: 4242)
    app._open_panel_from_taskbar = lambda: calls.append("open")

    app._taskbar_activation_loop()

    assert calls == []


def test_panel_no_longer_has_browser_docking_behavior():
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    assert not hasattr(app, "_dock_to_browser")
    assert not hasattr(app, "_apply_stick_to_browser")
    assert not hasattr(app, "_stick_to_browser")


def test_notification_is_anchored_above_bubble(monkeypatch):
    import wfx_panel.panel_app as module

    monkeypatch.setattr(
        module, "_window_rect_by_title", lambda _title: (900, 500, 948, 548)
    )
    x, y = module._notification_position()
    # Canh phải mép bubble, nổi phía trên.
    assert x == 948 - module.NOTIFICATION_WIDTH
    assert y == 500 - module.NOTIFICATION_HEIGHT - 8


def test_notification_drops_below_bubble_when_no_room_above(monkeypatch):
    import wfx_panel.panel_app as module

    # Bubble sát đỉnh màn hình → không đủ chỗ phía trên → nổi ngay dưới bubble.
    monkeypatch.setattr(
        module, "_window_rect_by_title", lambda _title: (900, 5, 948, 53)
    )
    x, y = module._notification_position()
    assert x == 948 - module.NOTIFICATION_WIDTH
    assert y == 53 + 8


def test_hold_to_drag_starts_bubble_drag_thread(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    started = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            self.target = target
            self.args = args
            self.daemon = daemon

        def is_alive(self):
            return False

        def start(self):
            started.append((self.target, self.args, self.daemon))

    monkeypatch.setattr(module, "_find_window_hwnd", lambda _title: 4242)
    monkeypatch.setattr(module, "_native_left_button_down", lambda: True)
    monkeypatch.setattr(module, "_native_cursor_position", lambda: (800, 700))
    monkeypatch.setattr(
        module, "_window_rect_by_title", lambda _title: (720, 690, 768, 738)
    )
    monkeypatch.setattr(module.threading, "Thread", FakeThread)

    result = app.begin_bubble_drag()
    assert result["code"] == "BUBBLE_DRAG_STARTED"
    assert started == [
        (
            app._bubble_drag_loop,
            (4242, (800, 700), (720, 690, 768, 738)),
            True,
        )
    ]


def test_bubble_drag_loop_moves_and_saves_without_snapping(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    mouse_states = iter([True, False])
    moved = []
    saved = []

    monkeypatch.setattr(
        module, "_native_left_button_down", lambda: next(mouse_states)
    )
    monkeypatch.setattr(module, "_native_cursor_position", lambda: (850, 740))
    monkeypatch.setattr(
        module, "_work_area_for_process_window", lambda _pid: (0, 0, 1920, 1080)
    )
    monkeypatch.setattr(
        module, "_work_area_for_point", lambda _x, _y: (0, 0, 1920, 1080)
    )
    monkeypatch.setattr(
        module, "_move_hwnd", lambda _hwnd, x, y: moved.append((x, y)) or True
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        module.prefs, "save_prefs", lambda **kwargs: saved.append(kwargs) or {}
    )

    app._bubble_drag_loop(4242, (800, 700), (720, 690, 768, 738))

    # Cho đặt đâu cũng được → KHÔNG dính mép; icon nằm đúng chỗ thả (770, 730).
    assert moved == [(770, 730)]
    assert app._bubble_offset == (770, 730)
    assert saved == [{"compact_offset_x": 770, "compact_offset_y": 730}]


def test_bubble_drag_loop_keeps_icon_inside_screen_when_dragged_past_edge(
    monkeypatch,
):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    mouse_states = iter([True, False])
    moved = []

    monkeypatch.setattr(
        module, "_native_left_button_down", lambda: next(mouse_states)
    )
    # Con trỏ nhảy ra ngoài mép phải-dưới màn hình.
    monkeypatch.setattr(module, "_native_cursor_position", lambda: (5000, 5000))
    monkeypatch.setattr(
        module, "_work_area_for_process_window", lambda _pid: (0, 0, 1920, 1080)
    )
    monkeypatch.setattr(
        module, "_work_area_for_point", lambda _x, _y: (0, 0, 1920, 1080)
    )
    monkeypatch.setattr(
        module, "_move_hwnd", lambda _hwnd, x, y: moved.append((x, y)) or True
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(module.prefs, "save_prefs", lambda **_kwargs: {})

    app._bubble_drag_loop(4242, (800, 700), (720, 690, 768, 738))

    # Icon 48px không được vượt work area dù kéo ra ngoài màn hình.
    for x, y in moved:
        assert 0 <= x <= 1920 - 48
        assert 0 <= y <= 1080 - 48


def test_bubble_drag_loop_can_cross_to_another_monitor(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    mouse_states = iter([True, False])
    moved = []
    saved = []

    monkeypatch.setattr(
        module, "_native_left_button_down", lambda: next(mouse_states)
    )
    monkeypatch.setattr(module, "_native_cursor_position", lambda: (2200, 300))
    monkeypatch.setattr(
        module,
        "_work_area_for_window_title",
        lambda _title: (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_point",
        lambda x, _y: (1920, 0, 3840, 1080) if x >= 1920 else (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(
        module, "_move_hwnd", lambda _hwnd, x, y: moved.append((x, y)) or True
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        module.prefs, "save_prefs", lambda **kwargs: saved.append(kwargs) or {}
    )

    app._bubble_drag_loop(4242, (1800, 300), (1760, 280, 1808, 328))

    assert moved == [(2160, 280)]
    assert saved == [{"compact_offset_x": 2160, "compact_offset_y": 280}]


def test_show_panel_shows_window_and_hide_panel_hides_it(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []

    class FakeWindow:
        on_top = False

        def resize(self, width, height):
            calls.append(("resize", width, height))

        def move(self, x, y):
            calls.append(("move", x, y))

        def evaluate_js(self, script):
            calls.append(("js", script))

        def show(self):
            calls.append(("show",))

        def hide(self):
            calls.append(("hide",))

    app.window = FakeWindow()
    monkeypatch.setattr(
        module, "_work_area_for_process_window", lambda _pid: (0, 0, 1920, 1080)
    )
    monkeypatch.setattr(module, "_window_rect_by_title", lambda _title: None)
    monkeypatch.setattr(module, "_set_process_window_bounds", lambda *_a: True)
    monkeypatch.setattr(
        module, "_bring_process_window_to_front", lambda **_kwargs: True
    )

    opened = app.show_panel()
    assert opened["code"] == "PANEL_OPENED"
    assert app._panel_visible is True
    assert ("show",) in calls

    app.hide_panel()
    assert app._panel_visible is False
    assert ("hide",) in calls


def test_show_panel_positions_beside_bubble_and_clamps(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    bounds_calls = []

    class FakeWindow:
        on_top = False

        def resize(self, *_args):
            pass

        def move(self, *_args):
            pass

        def evaluate_js(self, script):
            pass

        def show(self):
            pass

    app.window = FakeWindow()
    # Bubble sát góc phải-dưới → panel phải bung sang TRÁI và clamp vào trong.
    monkeypatch.setattr(
        module, "_window_rect_by_title", lambda _title: (1880, 1040, 1934, 1094)
    )
    monkeypatch.setattr(
        module, "_work_area_for_process_window", lambda _pid: (0, 0, 1920, 1080)
    )

    def set_bounds(_pid, x, y, width, height):
        bounds_calls.append((x, y, width, height))
        return True

    monkeypatch.setattr(module, "_set_process_window_bounds", set_bounds)
    monkeypatch.setattr(
        module, "_bring_process_window_to_front", lambda **_kwargs: True
    )

    app.show_panel()

    # Bubble ở nửa phải (x=1880 > 960) → panel bên trái: 1880-440-10=1430.
    # y=1040 bị clamp xuống 1080-620=460 để thấy đủ.
    assert bounds_calls == [(1430, 460, module.WINDOW_WIDTH, module.WINDOW_HEIGHT)]


def test_panel_stays_inside_bubble_monitor_at_all_four_corners(monkeypatch):
    import wfx_panel.panel_app as module

    # Màn hình phụ nằm bên trái màn hình chính để bắt cả toạ độ âm.
    area = (-1600, 0, 0, 900)
    corners = (
        (-1600, 0, -1552, 48),
        (-48, 0, 0, 48),
        (-1600, 852, -1552, 900),
        (-48, 852, 0, 900),
    )

    class FakeWindow:
        def resize(self, *_args):
            pass

        def move(self, *_args):
            pass

    app = module.PanelApp()
    app.window = FakeWindow()
    monkeypatch.setattr(
        module, "_work_area_for_window_title", lambda _title: area
    )

    for bubble in corners:
        calls = []
        monkeypatch.setattr(
            module, "_window_rect_by_title", lambda _title, rect=bubble: rect
        )
        monkeypatch.setattr(
            module,
            "_set_process_window_bounds",
            lambda _pid, x, y, width, height, output=calls: (
                output.append((x, y, width, height)) or True
            ),
        )

        app._position_panel_beside_bubble()

        assert len(calls) == 1
        x, y, width, height = calls[0]
        assert area[0] <= x <= area[2] - width
        assert area[1] <= y <= area[3] - height
        assert (width, height) == (module.WINDOW_WIDTH, module.WINDOW_HEIGHT)


def test_panel_shrinks_to_fit_a_small_work_area(monkeypatch):
    import wfx_panel.panel_app as module

    area = (100, 50, 420, 350)
    calls = []

    class FakeWindow:
        def resize(self, *_args):
            pass

        def move(self, *_args):
            pass

    app = module.PanelApp()
    app.window = FakeWindow()
    monkeypatch.setattr(
        module, "_window_rect_by_title", lambda _title: (372, 302, 420, 350)
    )
    monkeypatch.setattr(
        module, "_work_area_for_window_title", lambda _title: area
    )
    monkeypatch.setattr(
        module,
        "_set_process_window_bounds",
        lambda _pid, x, y, width, height: (
            calls.append((x, y, width, height)) or True
        ),
    )

    app._position_panel_beside_bubble()

    assert calls == [(100, 50, 320, 300)]


def test_bubble_loaded_repairs_an_offscreen_saved_position(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    moved = []
    saved = []
    monkeypatch.setattr(
        module, "_window_rect_by_title", lambda _title: (1950, 1100, 1998, 1148)
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_window_title",
        lambda _title: (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(
        module,
        "_set_bounds_by_title",
        lambda title, x, y, width, height: (
            moved.append((title, x, y, width, height)) or True
        ),
    )
    monkeypatch.setattr(
        module.prefs, "save_prefs", lambda **kwargs: saved.append(kwargs) or {}
    )

    app._on_bubble_loaded()

    assert moved == [
        (
            module.BUBBLE_WINDOW_TITLE,
            1920 - module.BUBBLE_SIZE,
            1080 - module.BUBBLE_SIZE,
            module.BUBBLE_SIZE,
            module.BUBBLE_SIZE,
        )
    ]
    assert saved == [
        {
            "compact_offset_x": 1920 - module.BUBBLE_SIZE,
            "compact_offset_y": 1080 - module.BUBBLE_SIZE,
        }
    ]


def test_bubble_loaded_always_enforces_native_main_size(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    moved = []
    # Mô phỏng WebView bị DPI scale thành 72×72 dù create_window nhận 48.
    monkeypatch.setattr(
        module, "_window_rect_by_title", lambda _title: (100, 100, 172, 172)
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_window_title",
        lambda _title: (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(
        module,
        "_set_bounds_by_title",
        lambda title, x, y, width, height: (
            moved.append((title, x, y, width, height)) or True
        ),
    )
    monkeypatch.setattr(module.prefs, "save_prefs", lambda **_kwargs: {})

    app._on_bubble_loaded()

    assert moved == [
        (
            module.BUBBLE_WINDOW_TITLE,
            100,
            100,
            module.BUBBLE_SIZE,
            module.BUBBLE_SIZE,
        )
    ]


def test_bubble_context_menu_can_hide_to_tray(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []

    class FakeWindow:
        def hide(self):
            calls.append(("panel-hide",))

    class FakeBubble:
        def hide(self):
            calls.append(("bubble-hide",))

    app.window = FakeWindow()
    app.bubble_window = FakeBubble()
    app._panel_visible = True
    monkeypatch.setattr(
        module, "_native_compact_context_choice", lambda *_a: "hide"
    )

    result = app.bubble_context_menu()

    assert result["code"] == "HIDDEN_TO_TRAY"
    assert ("bubble-hide",) in calls
    assert app._bubble_hidden is True
    assert app._panel_visible is False


def test_bubble_context_menu_can_toggle_on_top(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._always_on_top = True
    applied = []
    monkeypatch.setattr(
        module, "_native_compact_context_choice", lambda *_a: "toggle_on_top"
    )
    app.api.set_always_on_top = lambda value: applied.append(value) or {
        "ok": True,
        "always_on_top": value,
    }

    result = app.bubble_context_menu()

    assert result["always_on_top"] is False
    assert applied == [False]


def test_bubble_context_menu_can_exit(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []
    monkeypatch.setattr(
        module, "_native_compact_context_choice", lambda *_a: "exit"
    )
    app.quit = lambda: calls.append("quit")

    result = app.bubble_context_menu()

    assert result["code"] == "APP_EXITING"
    assert calls == ["quit"]


def test_tray_menu_has_commands_without_a_default_open_action(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    items = []
    menu_values = []

    def menu_item(label, action, **options):
        item = (label, action, options)
        items.append(item)
        return item

    class FakeIcon:
        def __init__(self, _name, _image, _title, menu, **_options):
            menu_values.extend(menu)

        def run(self):
            pass

    monkeypatch.setattr(module.Image, "open", lambda _path: object())
    monkeypatch.setattr(module.pystray, "MenuItem", menu_item)
    monkeypatch.setattr(module.pystray, "Menu", lambda *values: values)
    monkeypatch.setattr(module, "_WfxTrayIcon", FakeIcon)

    app._build_tray()

    assert [label for label, _action, _options in items] == [
        "Hiện WFX Smart",
        "Thoát",
    ]
    assert all(options.get("default") is not True for _, _, options in items)
    assert len(menu_values) == 2


def test_tray_right_click_suppresses_taskbar_activation(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._taskbar_focus_armed = True
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)

    app._note_tray_context_menu()

    assert app._taskbar_focus_armed is False
    assert app._bubble_direct_action_until == (
        100.0 + module.BUBBLE_DIRECT_ACTION_SUPPRESS_SECONDS
    )


def test_native_tray_icon_reports_right_click_before_backend(monkeypatch):
    import wfx_panel.panel_app as module

    calls = []
    monkeypatch.setattr(
        module.pystray.Icon,
        "_on_notify",
        lambda _self, wparam, lparam: calls.append(("backend", wparam, lparam)),
        raising=False,
    )
    icon = object.__new__(module._WfxTrayIcon)
    icon._running = False
    icon._icon_handle = None
    icon._on_context_menu = lambda: calls.append(("context",))

    icon._on_notify(12, module.TRAY_RIGHT_BUTTON_UP)

    assert calls == [
        ("context",),
        ("backend", 12, module.TRAY_RIGHT_BUTTON_UP),
    ]


def test_wfx_manual_opens_the_configured_url(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []
    monkeypatch.setattr(
        module.webbrowser,
        "open",
        lambda url, *, new: calls.append((url, new)) or True,
    )

    result = app.open_wfx_manual()

    assert result["code"] == "MANUAL_OPENED"
    assert calls == [(module.WFX_MANUAL_URL, 2)]


def test_runtime_on_top_setting_updates_pywebview_window():
    from wfx_panel.panel_app import PanelApp

    app = PanelApp()

    class FakeWindow:
        on_top = True

    app.window = FakeWindow()
    app._apply_always_on_top(False)
    assert app.window.on_top is False
    assert app._always_on_top is False


def test_focus_automation_browser_respects_default_on_setting(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    focused = []

    class FakeLogin:
        @staticmethod
        def automation_browser_pid():
            return 922200

    app.api._login = FakeLogin()
    monkeypatch.setattr(
        module,
        "_bring_process_window_to_front",
        lambda pid, *, on_top: focused.append((pid, on_top)) or True,
    )

    assert app.focus_automation_browser()["code"] == "CHROME_FOCUSED"
    assert focused == [(922200, None)]

    app.set_focus_chrome_on_module_state(False)
    assert app.focus_automation_browser()["code"] == "CHROME_FOCUS_DISABLED"
    assert focused == [(922200, None)]


def test_bubble_and_notification_windows_are_created():
    source = Path(panel_app.__file__).read_text(encoding="utf-8")
    assert "url=str(NOTIFICATION_INDEX)" in source
    assert "url=str(BUBBLE_INDEX)" in source
    assert "focus=False" in source
    # Bubble bắt sự kiện đóng để thu vào tray thay vì huỷ.
    assert "self.bubble_window.events.closing += self._on_bubble_closing" in source
    # Click taskbar phải mở đầy đủ UI, cả khi Windows phát minimize/restore
    # hoặc chỉ chuyển foreground về bubble.
    assert "self.bubble_window.events.minimized += self._on_bubble_taskbar_event" in source
    assert "self.bubble_window.events.restored += self._on_bubble_taskbar_event" in source
    assert "target=self._taskbar_activation_loop" in source
    # Panel tự thu khi mất focus qua kiểm tra foreground.
    assert "_foreground_process_id()" in source


def test_update_notification_is_automatic_but_only_once_per_release(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._last_update_notice = ""
    app._toast_enabled = True
    app.window = None
    notices = []
    saved = []

    class FakeTray:
        def notify(self, message, title=None):
            notices.append((message, title))

    app.tray = FakeTray()
    app.api.check_for_updates = lambda: {
        "ok": True,
        "code": "UPDATE_AVAILABLE",
        "can_update": True,
        "notice_id": "release-110",
        "version": "1.1.0",
    }
    monkeypatch.setattr(
        module.prefs,
        "save_prefs",
        lambda **kwargs: saved.append(kwargs) or {},
    )

    app._check_update_once()
    app._check_update_once()
    assert len(notices) == 1
    assert "Cập nhật ngay" in notices[0][0]
    assert saved == [{"last_update_notice": "release-110"}]
