from pathlib import Path

from wfx_panel import panel_app, prefs


def test_icon_and_ui_paths_resolve_under_resource_dir():
    # Finding B: bundled read-only assets (ui/, assets/) must always resolve
    # from RESOURCE_DIR, both frozen and unfrozen — this is unrelated to where
    # user data (.env/prefs.json) is written.
    assert panel_app.ICON_PATH == prefs.RESOURCE_DIR / "wfx_panel" / "assets" / "wfx.ico"
    assert panel_app.UI_INDEX == prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "index.html"
    assert panel_app.UI_INDEX.exists()


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


def test_toast_only_when_hidden_enabled_and_slow(monkeypatch):
    from wfx_panel.panel_app import PanelApp, TOAST_MIN_SECONDS

    app = PanelApp()
    sent = []

    class FakeTray:
        def notify(self, message, title=None):
            sent.append((message, title))

    app.tray = FakeTray()
    app.window = None
    app._toast_enabled = True

    app._visible = True
    app._on_result(
        "find_code", {"ok": True, "message": "xong"}, TOAST_MIN_SECONDS + 1
    )
    assert sent == []

    app._visible = False
    app._on_result("find_code", {"ok": True, "message": "xong"}, 0.2)
    assert sent == []

    app._on_result(
        "find_code", {"ok": True, "message": "xong"}, TOAST_MIN_SECONDS + 1
    )
    assert len(sent) == 1

    app._toast_enabled = False
    app._on_result(
        "find_code", {"ok": True, "message": "xong"}, TOAST_MIN_SECONDS + 1
    )
    assert len(sent) == 1


def test_toast_failure_never_breaks_the_result_flow():
    from wfx_panel.panel_app import PanelApp, TOAST_MIN_SECONDS

    app = PanelApp()

    class ExplodingTray:
        def notify(self, message, title=None):
            raise RuntimeError("tray hỏng")

    app.tray = ExplodingTray()
    app.window = None
    app._visible = False
    app._toast_enabled = True
    app._on_result(
        "find_code", {"ok": True, "message": "xong"}, TOAST_MIN_SECONDS + 1
    )


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

    app.window = FakeWindow()
    monkeypatch.setattr(
        module,
        "_bring_process_window_to_front",
        lambda **_kwargs: fronted.append(True) or True,
    )
    app.activate()
    assert shown == [True]
    assert fronted == [True]
    assert app._visible is True


def test_dock_targets_only_automation_browser_pid(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    moved = []

    class FakeWindow:
        def move(self, x, y):
            moved.append((x, y))

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
        lambda pid: (100, 50, 1500, 900) if pid == 922200 else None,
    )
    monkeypatch.setattr(
        module, "_set_process_window_bounds", lambda *_args: False
    )
    assert app._dock_to_browser() is True
    assert moved == [
        (
            1500 - module.WINDOW_WIDTH - module.BROWSER_DOCK_GAP,
            50 + module.BROWSER_DOCK_TOP,
        )
    ]


def test_full_panel_keeps_manual_drag_position_and_saves_offset(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    browser_rect = (100, 50, 1500, 900)
    user_rect = (460, 150, 900, 770)
    app._visible = True
    app._panel_offset = None
    app._last_panel_browser_rect = browser_rect
    app._last_panel_window_rect = (1048, 122, 1488, 742)
    moved = []
    saved = []

    class FakeWindow:
        def move(self, x, y):
            moved.append((x, y))

    class FakeLogin:
        @staticmethod
        def automation_browser_pid():
            return 922200

    app.window = FakeWindow()
    app.api._login = FakeLogin()
    monkeypatch.setattr(
        module,
        "_window_rect_for_process",
        lambda pid: browser_rect if pid == 922200 else user_rect,
    )
    monkeypatch.setattr(
        module, "_set_process_window_bounds", lambda *_args: False
    )
    monkeypatch.setattr(
        module.prefs,
        "save_prefs",
        lambda **kwargs: saved.append(kwargs) or {},
    )

    assert app._dock_to_browser() is True
    assert moved == []
    assert app._panel_offset == (360, 100)
    assert saved == [{"panel_offset_x": 360, "panel_offset_y": 100}]


def test_compact_launcher_docks_inside_browser_bottom_right(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    moved = []

    class FakeWindow:
        def move(self, x, y):
            moved.append((x, y))

    class FakeLogin:
        @staticmethod
        def automation_browser_pid():
            return 922200

    app.window = FakeWindow()
    app.api._login = FakeLogin()
    app._visible = True
    app._compact = True
    monkeypatch.setattr(
        module,
        "_window_rect_for_process",
        lambda pid: (
            (100, 50, 1500, 900)
            if pid == 922200
            else (
                100,
                50,
                100 + module.COMPACT_SIZE,
                50 + module.COMPACT_SIZE,
            )
        ),
    )
    monkeypatch.setattr(
        module, "_set_process_window_bounds", lambda *_args: False
    )
    assert app._dock_to_browser() is True
    assert moved == [
        (
            1500 - module.COMPACT_SIZE - module.BROWSER_DOCK_GAP,
            900 - module.COMPACT_SIZE - module.BROWSER_DOCK_GAP,
        )
    ]


def test_compact_launcher_keeps_user_drag_position_while_browser_is_still(
    monkeypatch,
):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    browser_rect = (100, 50, 1500, 900)
    app._last_compact_browser_rect = browser_rect
    app._compact = True
    app._visible = True
    moved = []

    class FakeWindow:
        def move(self, x, y):
            moved.append((x, y))

    class FakeLogin:
        @staticmethod
        def automation_browser_pid():
            return 922200

    app.window = FakeWindow()
    app.api._login = FakeLogin()
    monkeypatch.setattr(
        module,
        "_window_rect_for_process",
        lambda pid: browser_rect if pid == 922200 else (820, 700, 868, 748),
    )
    monkeypatch.setattr(
        module, "_set_process_window_bounds", lambda *_args: False
    )

    assert app._dock_to_browser() is True
    assert moved == []


def test_compact_launcher_restores_saved_browser_relative_position(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    app._compact_offset = (520, 610)
    app._compact = True
    app._visible = True
    moved = []

    class FakeWindow:
        def move(self, x, y):
            moved.append((x, y))

    class FakeLogin:
        @staticmethod
        def automation_browser_pid():
            return 922200

    app.window = FakeWindow()
    app.api._login = FakeLogin()
    monkeypatch.setattr(
        module,
        "_window_rect_for_process",
        lambda pid: (
            (100, 50, 1500, 900)
            if pid == 922200
            else (200, 200, 248, 248)
        ),
    )
    monkeypatch.setattr(
        module, "_set_process_window_bounds", lambda *_args: False
    )

    assert app._dock_to_browser() is True
    assert moved == [(620, 660)]


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
            ((800, 700), (720, 690, 768, 738), 922200),
            True,
        )
    ]


def test_native_drag_loop_moves_until_release_and_saves_position(monkeypatch):
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

    def rect_for(pid):
        if pid == 922200:
            return (100, 50, 1500, 900)
        return tuple(own_rect)

    def move_window(_pid, x, y, *_size):
        width = own_rect[2] - own_rect[0]
        height = own_rect[3] - own_rect[1]
        own_rect[:] = [x, y, x + width, y + height]
        moved.append((x, y))
        return True

    monkeypatch.setattr(module, "_window_rect_for_process", rect_for)
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
        922200,
    )

    assert moved == [(770, 730)]
    assert app._compact_offset == (670, 680)
    assert saved == [{"compact_offset_x": 670, "compact_offset_y": 680}]


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
    app._stick_to_browser = True
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


def test_runtime_on_top_setting_updates_pywebview_window():
    from wfx_panel.panel_app import PanelApp

    app = PanelApp()

    class FakeWindow:
        on_top = True

    app.window = FakeWindow()
    app._apply_always_on_top(False)
    assert app.window.on_top is False
    assert app._always_on_top is False


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
