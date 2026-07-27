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
        module, "_move_hwnd", lambda _hwnd, x, y: moved.append((x, y)) or True
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(module.prefs, "save_prefs", lambda **_kwargs: {})

    app._bubble_drag_loop(4242, (800, 700), (720, 690, 768, 738))

    # Icon 48px không được vượt work area dù kéo ra ngoài màn hình.
    for x, y in moved:
        assert 0 <= x <= 1920 - 48
        assert 0 <= y <= 1080 - 48


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
