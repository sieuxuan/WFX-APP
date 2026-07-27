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
    assert "min_size=(COMPACT_SIZE, COMPACT_SIZE)" in source


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


def test_activate_brings_native_window_to_front(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    shown = []
    fronted = []

    class FakeWindow:
        def show(self):
            shown.append(True)

        def evaluate_js(self, script):
            shown.append(script)

    app.window = FakeWindow()
    monkeypatch.setattr(
        module,
        "_bring_process_window_to_front",
        lambda **_kwargs: fronted.append(True) or True,
    )
    app.activate()
    assert shown[0] is True
    assert "wfxFocusModuleSearch" in shown[1]
    assert fronted == [True]
    assert app._visible is True


def test_panel_no_longer_has_browser_docking_behavior():
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    assert not hasattr(app, "_dock_to_browser")
    assert not hasattr(app, "_apply_stick_to_browser")
    assert not hasattr(app, "_stick_to_browser")


def test_notification_is_anchored_above_compact_icon(monkeypatch):
    import wfx_panel.panel_app as module

    monkeypatch.setattr(
        module,
        "_window_rect_for_process",
        lambda _pid: (900, 500, 948, 548),
    )
    x, y = module._notification_position()
    assert x == 900 + (module.COMPACT_SIZE - module.NOTIFICATION_WIDTH) // 2
    assert y == 500 - module.NOTIFICATION_HEIGHT - 8


def test_notification_is_anchored_to_top_of_open_panel(monkeypatch):
    import wfx_panel.panel_app as module

    monkeypatch.setattr(
        module,
        "_window_rect_for_process",
        lambda _pid: (700, 200, 1140, 820),
    )
    x, y = module._notification_position()
    assert x == 1140 - module.NOTIFICATION_WIDTH
    assert y == 200 - module.NOTIFICATION_HEIGHT - 8


def test_hold_to_drag_starts_native_mouse_tracking_thread(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._compact = True
    started = []

    class FakeLogin:
        @staticmethod
        def automation_browser_pid():
            return 922200

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            self.target = target
            self.args = args
            self.daemon = daemon

        def is_alive(self):
            return False

        def start(self):
            started.append((self.target, self.args, self.daemon))

    app.api._login = FakeLogin()
    monkeypatch.setattr(module, "_native_left_button_down", lambda: True)
    monkeypatch.setattr(module, "_native_cursor_position", lambda: (800, 700))
    monkeypatch.setattr(
        module,
        "_window_rect_for_process",
        lambda pid: (
            (100, 50, 1500, 900)
            if pid == 922200
            else (720, 690, 768, 738)
        ),
    )
    monkeypatch.setattr(module.threading, "Thread", FakeThread)

    result = app.begin_compact_drag()
    assert result["code"] == "PANEL_DRAG_STARTED"
    assert started == [
        (
            app._compact_drag_loop,
            ((800, 700), (720, 690, 768, 738)),
            True,
        )
    ]


def test_native_drag_loop_clamps_then_snaps_to_nearest_edge_and_saves(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._compact = True
    mouse_states = iter([True, False])
    own_rect = [720, 690, 768, 738]
    moved = []
    saved = []

    monkeypatch.setattr(
        module, "_native_left_button_down", lambda: next(mouse_states)
    )
    monkeypatch.setattr(
        module, "_native_cursor_position", lambda: (850, 740)
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_process_window",
        lambda _pid: (0, 0, 1920, 1080),
    )

    def move_window(_pid, x, y, *_size):
        width = own_rect[2] - own_rect[0]
        height = own_rect[3] - own_rect[1]
        own_rect[:] = [x, y, x + width, y + height]
        moved.append((x, y))
        return True

    monkeypatch.setattr(module, "_set_process_window_bounds", move_window)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        module.prefs,
        "save_prefs",
        lambda **kwargs: saved.append(kwargs) or {},
    )

    app._compact_drag_loop(
        (800, 700),
        (720, 690, 768, 738),
    )

    # Bước kéo giữ đúng con trỏ (770, 730); khi thả dính mép dưới gần nhất
    # (1080 - 48 - COMPACT_EDGE_MARGIN = 1020), giữ nguyên trục x.
    assert moved == [(770, 730), (770, 1020)]
    assert app._compact_offset == (770, 1020)
    assert saved == [{"compact_offset_x": 770, "compact_offset_y": 1020}]


def test_native_drag_loop_keeps_icon_inside_screen_when_dragged_past_edge(
    monkeypatch,
):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._compact = True
    mouse_states = iter([True, False])
    moved = []

    monkeypatch.setattr(
        module, "_native_left_button_down", lambda: next(mouse_states)
    )
    # Con trỏ nhảy ra ngoài mép phải-dưới màn hình.
    monkeypatch.setattr(
        module, "_native_cursor_position", lambda: (5000, 5000)
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_process_window",
        lambda _pid: (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(
        module, "_set_process_window_bounds", lambda *_a: moved.append(_a[1:3]) or True
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(module.prefs, "save_prefs", lambda **_kwargs: {})

    app._compact_drag_loop((800, 700), (720, 690, 768, 738))

    # Không toạ độ nào được phép vượt work area (icon 48px).
    for x, y in moved:
        assert 0 <= x <= 1920 - module.COMPACT_SIZE
        assert 0 <= y <= 1080 - module.COMPACT_SIZE


def test_collapse_and_expand_resize_the_same_window(monkeypatch):
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

    class FakeLogin:
        @staticmethod
        def automation_browser_pid():
            return 922200

    app.window = FakeWindow()
    app.api._login = FakeLogin()
    app._visible = True
    monkeypatch.setattr(
        module,
        "_window_rect_for_process",
        lambda _pid: (100, 50, 1500, 900),
    )
    monkeypatch.setattr(
        module, "_set_process_window_bounds", lambda *_args: False
    )
    monkeypatch.setattr(
        module,
        "_bring_process_window_to_front",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(module.prefs, "save_prefs", lambda **_kwargs: {})

    collapsed = app.collapse_to_browser_icon()
    assert collapsed["code"] == "PANEL_COMPACT"
    assert app._compact is True
    assert ("resize", module.COMPACT_SIZE, module.COMPACT_SIZE) in calls

    expanded = app.expand_from_browser_icon()
    assert expanded["code"] == "PANEL_EXPANDED"
    assert app._compact is False
    assert ("resize", module.WINDOW_WIDTH, module.WINDOW_HEIGHT) in calls


def test_expand_clamps_panel_fully_on_screen_from_corner_icon(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._compact = True
    app._visible = True
    app._full_window_size = (module.WINDOW_WIDTH, module.WINDOW_HEIGHT)
    bounds_calls = []

    class FakeWindow:
        on_top = False

        def resize(self, width, height):
            pass

        def move(self, x, y):
            pass

        def evaluate_js(self, script):
            pass

        def show(self):
            pass

    app.window = FakeWindow()
    # Icon nằm sát góc phải-dưới màn hình.
    monkeypatch.setattr(
        module,
        "_window_rect_for_process",
        lambda _pid: (1880, 1040, 1928, 1088),
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_process_window",
        lambda _pid: (0, 0, 1920, 1080),
    )

    def set_bounds(_pid, x, y, width, height):
        bounds_calls.append((x, y, width, height))
        return True

    monkeypatch.setattr(module, "_set_process_window_bounds", set_bounds)
    monkeypatch.setattr(
        module, "_bring_process_window_to_front", lambda **_kwargs: True
    )
    monkeypatch.setattr(module.prefs, "save_prefs", lambda **_kwargs: {})

    result = app.expand_from_browser_icon()

    assert result["code"] == "PANEL_EXPANDED"
    # Panel 440×620 bị đẩy vào trong: x=1920-440=1480, y=1080-620=460.
    assert bounds_calls == [(1480, 460, module.WINDOW_WIDTH, module.WINDOW_HEIGHT)]
    assert app._panel_offset == (1480, 460)


def test_collapse_anchors_icon_to_panel_top_right_and_clamps(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._visible = True
    app._compact_offset = None
    bounds_calls = []

    class FakeWindow:
        on_top = False

        def resize(self, width, height):
            pass

        def move(self, x, y):
            pass

        def evaluate_js(self, script):
            pass

    app.window = FakeWindow()
    # Panel dock góc trên-phải: right = 1896 (sát mép).
    monkeypatch.setattr(
        module,
        "_window_rect_for_process",
        lambda _pid: (1456, 24, 1896, 644),
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_process_window",
        lambda _pid: (0, 0, 1920, 1080),
    )

    def set_bounds(_pid, x, y, width, height):
        bounds_calls.append((x, y, width, height))
        return True

    monkeypatch.setattr(module, "_set_process_window_bounds", set_bounds)
    monkeypatch.setattr(module.prefs, "save_prefs", lambda **_kwargs: {})

    result = app.collapse_to_browser_icon()

    assert result["code"] == "PANEL_COMPACT"
    # Icon neo góc trên-phải panel: x = 1896 - 48 = 1848 (nằm gọn), y = 24.
    assert bounds_calls == [(1848, 24, module.COMPACT_SIZE, module.COMPACT_SIZE)]
    assert app._compact_offset == (1848, 24)


def test_compact_context_menu_can_hide_to_tray(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []

    class FakeWindow:
        def evaluate_js(self, script):
            calls.append(("js", script))

        def hide(self):
            calls.append(("hide",))

    app.window = FakeWindow()
    app._compact = True
    app._visible = True
    monkeypatch.setattr(module, "_native_compact_context_choice", lambda _value: "hide")
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = app.show_compact_context_menu()

    assert result["code"] == "PANEL_HIDDEN"
    assert ("hide",) in calls
    assert app._visible is False


def test_compact_context_menu_can_toggle_on_top(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._compact = True
    app._always_on_top = True
    applied = []
    monkeypatch.setattr(
        module, "_native_compact_context_choice", lambda _value: "toggle_on_top"
    )
    app.api.set_always_on_top = lambda value: applied.append(value) or {
        "ok": True,
        "always_on_top": value,
    }

    result = app.show_compact_context_menu()

    assert result["always_on_top"] is False
    assert applied == [False]


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


def test_taskbar_minimize_or_restore_expands_compact_panel(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []

    class FakeWindow:
        def restore(self):
            calls.append("restore")

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    app.window = FakeWindow()
    app._compact = True
    app.expand_from_browser_icon = lambda: calls.append("expand") or {"ok": True}
    monkeypatch.setattr(module.threading, "Thread", ImmediateThread)

    app._on_window_minimized()
    app._on_window_restored()

    assert calls == ["restore", "expand", "restore", "expand"]


def test_custom_notification_window_is_created_and_taskbar_events_are_bound():
    source = Path(panel_app.__file__).read_text(encoding="utf-8")
    assert "url=str(NOTIFICATION_INDEX)" in source
    assert "focus=False" in source
    assert "hidden=True" in source
    assert "self.window.events.minimized += self._on_window_minimized" in source
    assert "self.window.events.restored += self._on_window_restored" in source
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
