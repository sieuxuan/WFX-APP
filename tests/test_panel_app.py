import os
from pathlib import Path

from wfx_panel import panel_app, prefs


def test_icon_and_ui_paths_resolve_under_resource_dir():
    # Finding B: bundled read-only assets (ui/, assets/) must always resolve
    # from RESOURCE_DIR, both frozen and unfrozen — this is unrelated to where
    # user data (.env/prefs.json) is written.
    assert (
        panel_app.ICON_PATH == prefs.RESOURCE_DIR / "wfx_panel" / "assets" / "wfx.ico"
    )
    assert panel_app.UI_INDEX == prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "index.html"
    assert (
        panel_app.NOTIFICATION_INDEX
        == prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "notification.html"
    )
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
    # Khai báo min_size nhỏ để tránh mặc định 200×100 nhưng vẫn cho Win32 thu
    # về đúng 48 physical px trên màn hình DPI 125/150%.
    assert "min_size=(1, 1)" in source
    assert "_enforce_bubble_native_bounds" in source


def test_windows_build_excludes_unused_optional_gui_and_science_stacks():
    spec = (prefs.RESOURCE_DIR / "wfx_panel" / "wfx-panel.spec").read_text(
        encoding="utf-8"
    )
    for package in (
        '"PyQt5"',
        '"PyQt6"',
        '"PySide2"',
        '"PySide6"',
        '"numpy"',
        '"cryptography"',
    ):
        assert package in spec


def test_normal_startup_opens_full_panel(monkeypatch):
    app = panel_app.PanelApp()
    app._start_hidden = False
    app._hotkey_ready.set()
    calls = []

    class FakeWindow:
        def evaluate_js(self, script):
            calls.append(("js", script))

    class FakeApi:
        def get_initial_state(self):
            return {}

        def flush_error_reports(self):
            return None

        def check_session(self):
            return {"ok": False, "message": "no session"}

    app.window = FakeWindow()
    app.api = FakeApi()
    app.show_panel = lambda: calls.append(("show-panel",)) or {"ok": True}
    monkeypatch.setattr(
        panel_app.prefs,
        "load_account",
        lambda: {"user_id": "", "password": ""},
    )
    monkeypatch.setattr(panel_app.updater, "consume_update_result", lambda: None)

    app._startup()

    assert ("show-panel",) in calls


def test_start_hidden_preference_keeps_full_panel_hidden(monkeypatch):
    app = panel_app.PanelApp()
    app._start_hidden = True
    app._hotkey_ready.set()
    calls = []

    class FakeWindow:
        def evaluate_js(self, _script):
            pass

    class FakeApi:
        def get_initial_state(self):
            return {}

        def flush_error_reports(self):
            return None

        def check_session(self):
            return {"ok": False, "message": "no session"}

    app.window = FakeWindow()
    app.api = FakeApi()
    app.show_panel = lambda: calls.append("show") or {"ok": True}
    monkeypatch.setattr(
        panel_app.prefs,
        "load_account",
        lambda: {"user_id": "", "password": ""},
    )
    monkeypatch.setattr(panel_app.updater, "consume_update_result", lambda: None)

    app._startup()

    assert calls == []


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
    app._show_notification = lambda result, **context: sent.append((result, context))

    app._on_result("find_code", {"ok": True, "message": "xong"}, 0.2)
    app._on_result("switch_division", {"ok": True, "message": "đổi"}, 0.2)

    assert sent == [
        (
            {"ok": True, "message": "xong"},
            {"method": "find_code", "elapsed": 0.2},
        )
    ]


def test_download_result_opens_explorer_and_shows_toast(monkeypatch):
    app = panel_app.PanelApp()
    opened = []
    sent = []
    app.window = None
    app._show_notification = lambda result, **context: sent.append(
        (result, context)
    )
    monkeypatch.setattr(
        panel_app,
        "_reveal_downloaded_file",
        lambda path: opened.append(path) or True,
    )
    result = {
        "ok": True,
        "message": "Đã tải jacket.pdf vào thư mục Downloads.",
        "download_path": r"C:\Users\Admin\Downloads\jacket.pdf",
    }

    app._on_result("download_catalog_file", result, 2.5)

    assert opened == [r"C:\Users\Admin\Downloads\jacket.pdf"]
    assert sent == [
        (
            result,
            {"method": "download_catalog_file", "elapsed": 2.5},
        )
    ]


def test_reveal_downloaded_excel_opens_exact_parent_folder(tmp_path, monkeypatch):
    target = tmp_path / "Costing Report.xlsx"
    target.write_bytes(b"xlsx")
    opened = []
    monkeypatch.setattr(
        panel_app.os,
        "startfile",
        lambda path: opened.append(Path(path)),
    )

    assert panel_app._reveal_downloaded_file(target) is True
    assert opened == [target.parent.resolve()]


def test_notification_shows_full_action_detail_without_resizing_webview(
    monkeypatch,
):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    scripts = []
    moved = []
    native_calls = []

    class FakeWindow:
        def evaluate_js(self, script):
            scripts.append(script)

        def resize(self, width, height):
            moved.append(("resize", width, height))

        def move(self, x, y):
            moved.append((x, y))

        def show(self):
            pass

    class FakeTimer:
        daemon = False

        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            pass

    app.notification_window = FakeWindow()
    app._notification_ready.set()
    app._toast_enabled = True
    monkeypatch.setattr(
        module,
        "_native_notification_visibility",
        lambda *args: native_calls.append(args) or False,
    )
    monkeypatch.setattr(module, "_window_dpi_by_title", lambda _title: 96)
    monkeypatch.setattr(module.threading, "Timer", FakeTimer)

    app._show_notification(
        {
            "ok": True,
            "message": "Đã mở đầy đủ thông tin Costing cho style.",
            "article_code": "ABC123",
        },
        method="catalog_action",
        elapsed=2.5,
    )

    assert '"title": "Catalog · Hoàn thành"' in scripts[0]
    assert '"detail": "Style ABC123 · 2,5 giây"' in scripts[0]
    assert "Đã mở đầy đủ thông tin Costing cho style." in scripts[0]
    assert native_calls and native_calls[0][3:] == (
        module.NOTIFICATION_WIDTH,
        module.NOTIFICATION_HEIGHT,
    )
    assert (
        "resize",
        module.NOTIFICATION_WIDTH,
        module.NOTIFICATION_HEIGHT,
    ) in moved
    assert moved


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
    assert any(
        "wfxFocusModuleSearch" in item for item in shown if isinstance(item, str)
    )
    assert fronted == [True]
    assert app._panel_visible is True


def test_taskbar_activation_opens_full_ui_without_winforms_restore(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []

    def show_panel():
        calls.append("panel-show")
        app._panel_visible = True
        return {"ok": True}

    app.show_panel = show_panel
    app._schedule_bubble_native_bounds = lambda: calls.append("bubble-size")
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)

    app._open_panel_from_taskbar()

    assert calls == ["bubble-size", "panel-show"]
    assert app._panel_visible is True


def test_show_from_tray_repairs_hidden_bubble_before_opening_panel():
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []

    class FakeBubble:
        on_top = False

        def show(self):
            calls.append("bubble-show")

    app.bubble_window = FakeBubble()
    app._bubble_hidden = True
    app._schedule_bubble_native_bounds = lambda: calls.append("bubble-size")
    app.show_panel = lambda: calls.append("panel-show") or {"ok": True}

    app.show_from_tray()

    assert calls == ["bubble-show", "bubble-size", "panel-show"]
    assert app._bubble_hidden is False


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


def test_bubble_pointer_interaction_blocks_taskbar_until_mouseup(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []
    times = iter([100.0, 100.1, 100.2, 100.3])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(times))
    app.show_panel = lambda: calls.append("panel-show") or {"ok": True}

    app.begin_bubble_interaction()
    app._open_panel_from_taskbar()
    app.end_bubble_interaction()

    assert calls == []
    assert app._bubble_pointer_down is False


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
    app._bubble_direct_action_until = 999999.0

    app._on_bubble_minimized()
    app._on_bubble_restored()

    assert calls == ["open", "open"]
    assert app._bubble_direct_action_until == 0.0


def test_taskbar_foreground_transition_opens_only_for_bubble(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    waits = iter([False, False, True])
    process_ids = iter([99999, os.getpid()])
    foreground_windows = iter([111, 4242])
    calls = []

    monkeypatch.setattr(app._stop_status, "wait", lambda _seconds: next(waits))
    monkeypatch.setattr(module, "_foreground_process_id", lambda: next(process_ids))
    monkeypatch.setattr(
        module, "_foreground_window_hwnd", lambda: next(foreground_windows)
    )
    monkeypatch.setattr(module, "_find_window_hwnd", lambda _title: 4242)
    app._open_panel_from_taskbar = lambda: calls.append("open")

    app._taskbar_activation_loop()

    assert calls == ["open"]


def test_taskbar_foreground_transition_accepts_main_panel_hwnd(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    waits = iter([False, False, True])
    process_ids = iter([99999, os.getpid()])
    foreground_windows = iter([111, 5151])
    calls = []

    monkeypatch.setattr(app._stop_status, "wait", lambda _seconds: next(waits))
    monkeypatch.setattr(module, "_foreground_process_id", lambda: next(process_ids))
    monkeypatch.setattr(
        module, "_foreground_window_hwnd", lambda: next(foreground_windows)
    )
    monkeypatch.setattr(
        module,
        "_find_window_hwnd",
        lambda title: 4242 if title == module.BUBBLE_WINDOW_TITLE else 5151,
    )
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
    monkeypatch.setattr(module, "_foreground_process_id", lambda: next(process_ids))
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
    monkeypatch.setattr(module, "_window_dpi_by_title", lambda _title: 96)
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
    monkeypatch.setattr(module, "_window_dpi_by_title", lambda _title: 96)
    x, y = module._notification_position()
    assert x == 948 - module.NOTIFICATION_WIDTH
    assert y == 53 + 8


def test_notification_keeps_logical_size_at_150_percent_scale(monkeypatch):
    import wfx_panel.panel_app as module

    monkeypatch.setattr(
        module,
        "_window_rect_by_title",
        lambda _title: (900, 500, 948, 548),
    )
    monkeypatch.setattr(module, "_window_dpi_by_title", lambda _title: 144)

    x, y = module._notification_position()

    width, height = module._scale_logical_size(
        module.NOTIFICATION_WIDTH,
        module.NOTIFICATION_HEIGHT,
        144,
    )
    assert (width, height) == (348, 132)
    assert x == 948 - width
    assert y == 500 - height - 8


def test_native_drag_saves_final_bubble_position(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    saved = []

    monkeypatch.setattr(
        module,
        "_window_rect_by_title",
        lambda _title: (2160, 280, 2208, 328),
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_window_title",
        lambda _title: (1920, 0, 3840, 1080),
    )
    monkeypatch.setattr(
        module.prefs, "save_prefs", lambda **kwargs: saved.append(kwargs) or {}
    )

    result = app.save_bubble_position()

    assert result["code"] == "BUBBLE_POSITION_SAVED"
    assert app._bubble_offset == (2160, 280)
    assert saved == [{"compact_offset_x": 2160, "compact_offset_y": 280}]


def test_native_drag_clamps_bubble_before_saving(monkeypatch):
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

    result = app.save_bubble_position()

    assert result["ok"] is True
    assert moved == [
        (module.BUBBLE_WINDOW_TITLE, 1872, 1032, 48, 48)
    ]
    assert saved == [
        {"compact_offset_x": 1872, "compact_offset_y": 1032}
    ]


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
    monkeypatch.setattr(module, "_window_dpi_by_title", lambda _title: 96)
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


def test_panel_keeps_two_column_logical_width_at_125_percent_scale(
    monkeypatch,
):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []

    class FakeWindow:
        def resize(self, *_args):
            pass

        def move(self, *_args):
            pass

    app.window = FakeWindow()
    monkeypatch.setattr(module, "_window_dpi_by_title", lambda _title: 120)
    monkeypatch.setattr(
        module,
        "_window_rect_by_title",
        lambda _title: (1880, 500, 1928, 548),
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_window_title",
        lambda _title: (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(
        module,
        "_set_process_window_bounds",
        lambda _pid, x, y, width, height: (
            calls.append((x, y, width, height)) or True
        ),
    )

    app._position_panel_beside_bubble()

    physical_width, physical_height = module._scale_logical_size(
        module.WINDOW_WIDTH,
        module.WINDOW_HEIGHT,
        120,
    )
    assert (physical_width, physical_height) == (550, 775)
    assert calls == [(1320, 305, physical_width, physical_height)]
    assert round(physical_width * 96 / 120) == module.WINDOW_WIDTH


def test_panel_pywebview_fallback_uses_logical_size_at_high_dpi(monkeypatch):
    import wfx_panel.panel_app as module

    calls = []

    class FakeWindow:
        def resize(self, width, height):
            calls.append(("resize", width, height))

        def move(self, x, y):
            calls.append(("move", x, y))

    app = module.PanelApp()
    app.window = FakeWindow()
    monkeypatch.setattr(module, "_window_dpi_by_title", lambda _title: 144)
    monkeypatch.setattr(
        module,
        "_window_rect_by_title",
        lambda _title: (1800, 300, 1848, 348),
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_window_title",
        lambda _title: (0, 0, 1920, 1200),
    )
    monkeypatch.setattr(
        module,
        "_set_process_window_bounds",
        lambda *_args: False,
    )

    app._position_panel_beside_bubble()

    assert ("resize", module.WINDOW_WIDTH, module.WINDOW_HEIGHT) in calls


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
    monkeypatch.setattr(module, "_window_dpi_by_title", lambda _title: 96)
    monkeypatch.setattr(module, "_work_area_for_window_title", lambda _title: area)

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
    monkeypatch.setattr(module, "_window_dpi_by_title", lambda _title: 96)
    monkeypatch.setattr(
        module, "_window_rect_by_title", lambda _title: (372, 302, 420, 350)
    )
    monkeypatch.setattr(module, "_work_area_for_window_title", lambda _title: area)
    monkeypatch.setattr(
        module,
        "_set_process_window_bounds",
        lambda _pid, x, y, width, height: calls.append((x, y, width, height)) or True,
    )

    app._position_panel_beside_bubble()

    assert calls == [(100, 50, 320, 300)]


def test_bubble_loaded_repairs_an_offscreen_saved_position(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    moved = []
    saved = []
    rects = iter(
        [
            (1950, 1100, 1998, 1148),
            (1872, 1032, 1920, 1080),
        ]
    )
    monkeypatch.setattr(
        module, "_window_rect_by_title_any_state", lambda _title: next(rects)
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_window_title_any_state",
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
        module, "_set_smooth_corners_by_title", lambda *_args, **_kwargs: True
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
    rects = iter([(100, 100, 172, 172), (100, 100, 148, 148)])
    # Mô phỏng WebView bị DPI scale thành 72×72 dù create_window nhận 48.
    monkeypatch.setattr(
        module, "_window_rect_by_title_any_state", lambda _title: next(rects)
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_window_title_any_state",
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
        module, "_set_smooth_corners_by_title", lambda *_args, **_kwargs: True
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


def test_bubble_bounds_reject_false_success_until_rect_is_exact(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    monkeypatch.setattr(
        module,
        "_window_rect_by_title_any_state",
        lambda _title: (100, 100, 220, 139),
    )
    monkeypatch.setattr(
        module,
        "_work_area_for_window_title_any_state",
        lambda _title: (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(module, "_set_bounds_by_title", lambda *_args: True)
    monkeypatch.setattr(
        module, "_set_smooth_corners_by_title", lambda *_args, **_kwargs: True
    )

    assert app._enforce_bubble_native_bounds() is False


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
    monkeypatch.setattr(module, "_native_compact_context_choice", lambda *_a: "tray")

    result = app.bubble_context_menu()

    assert result["code"] == "HIDDEN_TO_TRAY"
    assert ("bubble-hide",) in calls
    assert app._bubble_hidden is True
    assert app._panel_visible is False


def test_bubble_context_menu_can_minimize_to_taskbar(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []

    class FakeWindow:
        def hide(self):
            calls.append("panel-hide")

    class FakeBubble:
        def minimize(self):
            calls.append("bubble-minimize")

    app.window = FakeWindow()
    app.bubble_window = FakeBubble()
    app._panel_visible = True
    monkeypatch.setattr(
        module, "_native_compact_context_choice", lambda *_a: "taskbar"
    )

    result = app.bubble_context_menu()

    assert result["code"] == "HIDDEN_TO_TASKBAR"
    assert calls == ["panel-hide", "bubble-minimize"]
    assert app._taskbar_minimize_requested is True
    assert app._bubble_hidden is False


def test_requested_taskbar_minimize_event_does_not_reopen_panel(monkeypatch):
    import wfx_panel.panel_app as module

    app = module.PanelApp()
    calls = []
    app._taskbar_minimize_requested = True
    monkeypatch.setattr(
        module.threading,
        "Thread",
        lambda **_kwargs: calls.append("thread"),
    )

    app._on_bubble_minimized()

    assert calls == []
    assert app._taskbar_minimize_requested is False


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
    assert "self.bubble_window.events.minimized += self._on_bubble_minimized" in source
    assert "self.bubble_window.events.restored += self._on_bubble_restored" in source
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


def test_packaged_startup_syncs_default_autostart(monkeypatch):
    import wfx_panel.panel_app as module

    calls = []
    monkeypatch.setattr(module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(module.prefs, "load_prefs", lambda: {"autostart": True})
    monkeypatch.setattr(
        module.autostart,
        "sync",
        lambda enabled: calls.append(enabled) or True,
    )
    monkeypatch.setattr(
        module.prefs,
        "save_prefs",
        lambda **kwargs: calls.append(kwargs),
    )

    assert module._sync_packaged_autostart() is True
    assert calls == [True]


def test_source_startup_never_registers_python_as_autostart(monkeypatch):
    import wfx_panel.panel_app as module

    monkeypatch.delattr(module.sys, "frozen", raising=False)
    monkeypatch.setattr(
        module.autostart,
        "sync",
        lambda _enabled: (_ for _ in ()).throw(AssertionError("must not sync")),
    )
    assert module._sync_packaged_autostart() is None


def test_packaged_autostart_failure_is_reflected_in_preferences(monkeypatch):
    import wfx_panel.panel_app as module

    saved = []
    monkeypatch.setattr(module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(module.prefs, "load_prefs", lambda: {"autostart": True})
    monkeypatch.setattr(module.autostart, "sync", lambda _enabled: False)
    monkeypatch.setattr(
        module.prefs,
        "save_prefs",
        lambda **kwargs: saved.append(kwargs),
    )

    assert module._sync_packaged_autostart() is False
    assert saved == [{"autostart": False}]


def test_webview_processes_are_capped_for_low_memory_machines():
    import wfx_panel.panel_app as module

    arguments = module.os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"]
    assert "--renderer-process-limit=3" in arguments
    assert "--process-per-site" in arguments
