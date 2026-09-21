"""Vỏ vòng đời app: bridge tới window, delegator, `run()` và `main()`.

`wfx_panel/panel_app.py` ở mức 66%. Phần chưa chạy là đúng những chỗ quyết định
app có khởi động được hay không:

* `run()` — nơi gắn toàn bộ bề mặt JS lên `PanelAPI`, tạo hai cửa sổ pywebview
  và dựng năm thread nền. Một tên bị sót ở đây làm nút trong panel im lặng.
* `main()` — khóa single-instance, đồng bộ autostart cho bản đóng gói và ghi
  crash log. CLAUDE.md: "Chạy source development không được tự đăng ký
  Python/Pythonw vào startup"; instance thứ hai phải đánh thức instance cũ rồi
  thoát ngay.
* các bridge `_push_log`/`_set_status`/`_on_progress`: "một lỗi native tạm thời"
  không được làm sập app.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from wfx_panel import panel_app


class FakeWindow:
    def __init__(self, *, error=None):
        self.scripts: list[str] = []
        self.error = error
        self.events = type(
            "Events",
            (),
            {
                "loaded": _Signal(),
                "closing": _Signal(),
                "minimized": _Signal(),
                "restored": _Signal(),
            },
        )()

    def evaluate_js(self, script):
        if self.error is not None:
            raise self.error
        self.scripts.append(script)


class _Signal:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


def _app(tmp_path) -> panel_app.PanelApp:
    app = panel_app.PanelApp()
    app._base_dir = tmp_path
    return app


# --- bridge tới cửa sổ ----------------------------------------------------


def test_the_log_bridge_escapes_the_line_it_sends(tmp_path):
    app = _app(tmp_path)
    app.window = FakeWindow()

    app._push_log('[RUN] "ABC"\nsau')

    assert len(app.window.scripts) == 1
    assert app.window.scripts[0].startswith("window.wfxPushLog(")
    assert "\n" not in app.window.scripts[0]


def test_the_status_bridge_sends_tone_and_message(tmp_path):
    app = _app(tmp_path)
    app.window = FakeWindow()

    app._set_status("error", "Không mở được")

    assert "window.wfxSetStatus(" in app.window.scripts[0]
    assert "error" in app.window.scripts[0]


def test_the_update_bridge_sends_json(tmp_path):
    app = _app(tmp_path)
    app.window = FakeWindow()

    app._push_update_state({"can_update": True, "tag": "v9"})

    assert json.dumps({"can_update": True, "tag": "v9"}) in app.window.scripts[0]


def test_the_progress_bridge_sends_json(tmp_path):
    app = _app(tmp_path)
    app.window = FakeWindow()

    app._on_progress({"method": "run_sale_asn_create", "stage": "po"})

    assert "window.wfxHandleBackendProgress(" in app.window.scripts[0]
    assert "run_sale_asn_create" in app.window.scripts[0]


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("_push_log", ("x",)),
        ("_set_status", ("ok", "x")),
        ("_push_update_state", ({},)),
        ("_on_progress", ({},)),
    ],
)
def test_no_bridge_call_touches_a_window_that_is_not_there(
    tmp_path, method, args
):
    app = _app(tmp_path)
    app.window = None

    getattr(app, method)(*args)  # không raise


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("_push_log", ("x",)),
        ("_set_status", ("ok", "x")),
        ("_push_update_state", ({},)),
        ("_on_progress", ({},)),
    ],
)
def test_a_webview_failure_never_escapes_a_bridge_call(tmp_path, method, args):
    app = _app(tmp_path)
    app.window = FakeWindow(error=RuntimeError("WebView2 chưa sẵn sàng"))

    getattr(app, method)(*args)  # không raise


# --- delegator ------------------------------------------------------------


DELEGATIONS = {
    "_dialogs": [
        ("choose_costing_import_file", ()),
        ("choose_costing_export_file", ("S", "xlsx")),
        ("choose_report_export_dir", ()),
        ("open_report_export_dir", ("C:/x",)),
        ("choose_oc_upload_file", ("new",)),
        ("choose_oc_upload_export_file", ("f",)),
        ("choose_sale_asn_export_file", ("INV",)),
        ("choose_sale_asn_price_check_export_file", ("INV",)),
        ("export_sale_asn_price_check", ({}, "p")),
        ("choose_sale_asn_import_file", ()),
        ("choose_style_import_file", ()),
        ("download_style_template", ("g",)),
        ("_style_copy_article_names", ()),
        ("download_oc_template", ()),
        ("download_sale_asn_template", ()),
        ("save_sale_asn_continue_template", ([],)),
        ("_handle_downloaded_excel", ("p",)),
    ],
    "_background": [
        ("_status_loop", ()),
        ("_check_update_once", ()),
        ("_update_loop", ()),
        ("_article_library_loop", ()),
    ],
    "_bubble": [
        ("_enforce_bubble_native_bounds", ()),
        ("_schedule_bubble_native_bounds", ()),
        ("_on_bubble_loaded", ()),
        ("_on_bubble_menu_loaded", ()),
    ],
}


@pytest.mark.parametrize(
    ("controller", "method", "args"),
    [
        (controller, method, args)
        for controller, methods in DELEGATIONS.items()
        for method, args in methods
    ],
)
def test_every_shell_method_delegates_to_its_controller(
    tmp_path, monkeypatch, controller, method, args
):
    """Một delegator bị sót không làm test nào khác đỏ, nên canh ở đây."""
    app = _app(tmp_path)
    seen: list[tuple] = []
    monkeypatch.setattr(
        getattr(app, controller),
        method,
        lambda *call_args, **kwargs: seen.append(call_args) or "ok",
    )

    assert getattr(app, method)(*args) == "ok"
    assert seen == [args]


def test_the_manual_window_property_reads_and_writes_the_controller(tmp_path):
    app = _app(tmp_path)

    app.manual_window = "cửa sổ"

    assert app.manual_window == "cửa sổ"
    assert app._manual.window == "cửa sổ"


# --- run() ----------------------------------------------------------------


class _FakeWebview:
    """`webview` giả: ghi lại hai cửa sổ được tạo và callback nền."""

    OPEN_DIALOG = 10
    SAVE_DIALOG = 20
    FOLDER_DIALOG = 30

    def __init__(self):
        self.windows: list[tuple[str, dict]] = []
        self.started = None
        self.private_mode = None
        self.screens = [type("Screen", (), {"width": 1920})()]

    def create_window(self, title, **kwargs):
        self.windows.append((title, kwargs))
        return FakeWindow()

    def start(self, background, private_mode=False):
        self.started = background
        self.private_mode = private_mode


@pytest.fixture
def running_app(tmp_path, monkeypatch):
    app = _app(tmp_path)
    fake = _FakeWebview()
    # `_top_right_position()` đọc `webview.screens` từ namespace của helpers.
    from wfx_panel.app import helpers as app_helpers

    monkeypatch.setattr(panel_app, "webview", fake)
    monkeypatch.setattr(app_helpers, "webview", fake)
    monkeypatch.setattr(panel_app, "build_icon", lambda _path: None)
    hotkeys: list[str] = []
    monkeypatch.setattr(
        panel_app.keyboard,
        "add_hotkey",
        lambda combo, handler: hotkeys.append(combo),
    )
    threads: list[str] = []

    class Thread:
        def __init__(self, target=None, name="", daemon=False):
            self.target = target
            self.name = name

        def start(self):
            threads.append(self.name or getattr(self.target, "__name__", "?"))

    monkeypatch.setattr(panel_app.threading, "Thread", Thread)
    monkeypatch.setattr(app, "_build_tray", lambda: threads.append("tray"))
    app.fake = fake
    app.hotkeys = hotkeys
    app.threads = threads
    return app


def test_run_creates_the_panel_hidden_and_the_bubble_on_top(running_app):
    running_app.run()

    titles = [title for title, _kwargs in running_app.fake.windows]
    assert titles == [panel_app.MAIN_WINDOW_TITLE, panel_app.BUBBLE_WINDOW_TITLE]
    panel_kwargs = running_app.fake.windows[0][1]
    bubble_kwargs = running_app.fake.windows[1][1]
    assert panel_kwargs["hidden"] is True
    assert panel_kwargs["frameless"] is True
    assert bubble_kwargs["on_top"] is True
    assert bubble_kwargs["min_size"] == (1, 1)
    assert running_app._panel_visible is False


def test_run_uses_a_private_webview_profile(running_app):
    running_app.run()

    assert running_app.fake.private_mode is True


def test_run_exposes_every_window_control_the_panel_calls(running_app):
    running_app.run()

    for name in (
        "hide_panel",
        "show_panel",
        "toggle_panel",
        "request_panel_hide",
        "set_panel_pointer_inside",
        "open_wfx_manual",
        "get_manual_entry_for_module",
        "focus_automation_browser",
        "show_test_notification",
    ):
        assert callable(getattr(running_app.api, name)), name


def test_run_exposes_every_file_dialog_the_panel_calls(running_app):
    running_app.run()

    for name in (
        "choose_costing_import_file",
        "choose_costing_export_file",
        "choose_report_export_dir",
        "open_report_export_dir",
        "choose_oc_upload_file",
        "choose_oc_upload_export_file",
        "choose_sale_asn_export_file",
        "choose_sale_asn_price_check_export_file",
        "export_sale_asn_price_check",
        "choose_sale_asn_import_file",
        "choose_style_import_file",
        "download_style_template",
        "download_oc_template",
        "download_sale_asn_template",
        "save_sale_asn_continue_template",
    ):
        assert callable(getattr(running_app.api, name)), name


def test_the_initial_state_is_wrapped_with_the_manual_flags(running_app):
    running_app.run()

    state = running_app.api.get_initial_state()

    assert "manual_error_codes" in state
    assert "manual_has_news" in state


def test_toggling_toast_through_the_bridge_also_updates_the_shell(running_app):
    running_app.run()
    seen: list[bool] = []
    running_app.set_toast_enabled_state = lambda enabled: seen.append(enabled)

    result = running_app.api.set_toast_enabled(False)

    assert result["toast_enabled"] is False
    assert seen == [False]


def test_toggling_focus_chrome_through_the_bridge_also_updates_the_shell(
    running_app,
):
    running_app.run()
    seen: list[bool] = []
    running_app.set_focus_chrome_on_module_state = lambda enabled: seen.append(
        enabled
    )

    result = running_app.api.set_focus_chrome_on_module(False)

    assert result["focus_chrome_on_module"] is False
    assert seen == [False]


def test_the_background_callback_registers_the_hotkey_and_every_loop(
    running_app,
):
    running_app.run()

    running_app.fake.started()

    assert running_app.hotkeys == [running_app._hotkey]
    assert running_app._hotkey_ready.is_set()
    assert running_app._hotkey_error is None
    assert "wfx-bubble-context-menu" in running_app.threads
    assert "wfx-article-library-sync" in running_app.threads
    assert "tray" in running_app.threads
    assert len(running_app.threads) == 6


def test_a_hotkey_the_os_refuses_is_recorded_instead_of_crashing(
    running_app, monkeypatch
):
    monkeypatch.setattr(
        panel_app.keyboard,
        "add_hotkey",
        lambda *_a: (_ for _ in ()).throw(ValueError("phím đã bị chiếm")),
    )
    running_app.run()

    running_app.fake.started()

    assert "phím đã bị chiếm" in str(running_app._hotkey_error)
    assert running_app._hotkey_ready.is_set()


def test_run_builds_the_icon_only_when_it_is_missing(running_app, monkeypatch):
    built: list[Path] = []
    monkeypatch.setattr(panel_app, "build_icon", lambda path: built.append(path))
    monkeypatch.setattr(
        panel_app.ICON_PATH.__class__, "exists", lambda _self: False
    )

    running_app.run()

    assert built == [panel_app.ICON_PATH]


# --- autostart cho bản đóng gói ------------------------------------------


def test_a_development_checkout_never_registers_windows_startup(monkeypatch):
    """CLAUDE.md: chạy source không được tự thêm pythonw vào Run key."""
    monkeypatch.delattr(panel_app.sys, "frozen", raising=False)
    calls: list[bool] = []
    monkeypatch.setattr(
        panel_app.autostart, "sync", lambda wanted: calls.append(wanted)
    )

    assert panel_app._sync_packaged_autostart() is None
    assert calls == []


def test_a_packaged_build_syncs_the_run_key_with_the_saved_preference(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(panel_app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        panel_app.prefs, "load_prefs", lambda *_a, **_kw: {"autostart": True}
    )
    monkeypatch.setattr(panel_app.autostart, "sync", lambda wanted: wanted)
    saved: list[dict] = []
    monkeypatch.setattr(
        panel_app.prefs, "save_prefs", lambda **kwargs: saved.append(kwargs)
    )

    assert panel_app._sync_packaged_autostart() is True
    assert saved == []


def test_a_run_key_windows_refused_is_written_back_to_prefs(monkeypatch):
    monkeypatch.setattr(panel_app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        panel_app.prefs, "load_prefs", lambda *_a, **_kw: {"autostart": True}
    )
    monkeypatch.setattr(panel_app.autostart, "sync", lambda _wanted: False)
    saved: list[dict] = []
    monkeypatch.setattr(
        panel_app.prefs, "save_prefs", lambda **kwargs: saved.append(kwargs)
    )

    assert panel_app._sync_packaged_autostart() is False
    assert saved == [{"autostart": False}]


# --- main() ---------------------------------------------------------------


class _Lock:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.signalled = 0

    def acquire(self):
        return self.acquired

    def signal_existing(self):
        self.signalled += 1
        return True


@pytest.fixture
def main_world(monkeypatch, tmp_path):
    events: list[tuple] = []
    monkeypatch.setattr(
        panel_app.crash_log,
        "install",
        lambda base, app_version: events.append(("install", app_version)),
    )
    monkeypatch.setattr(
        panel_app.crash_log,
        "clean_shutdown",
        lambda reason: events.append(("clean", reason)),
    )
    monkeypatch.setattr(
        panel_app.crash_log,
        "record",
        lambda event, **details: events.append(("record", event)),
    )
    monkeypatch.setattr(panel_app, "_sync_packaged_autostart", lambda: None)
    monkeypatch.setattr(panel_app.PanelApp, "run", lambda _self: events.append(("run",)))
    return events


def test_main_installs_the_crash_log_before_anything_else(
    monkeypatch, main_world
):
    lock = _Lock()
    monkeypatch.setattr(panel_app, "SingleInstance", lambda _activate: lock)

    panel_app.main()

    assert main_world[0] == ("install", panel_app.APP_VERSION)
    assert ("run",) in main_world
    assert ("clean", "main_loop_returned") in main_world


def test_a_second_instance_wakes_the_first_one_and_exits(monkeypatch, main_world):
    lock = _Lock(acquired=False)
    monkeypatch.setattr(panel_app, "SingleInstance", lambda _activate: lock)

    panel_app.main()

    assert lock.signalled == 1
    assert ("run",) not in main_world
    assert ("clean", "secondary_instance") in main_world


def test_a_crash_in_the_main_loop_is_recorded_and_re_raised(
    monkeypatch, main_world
):
    lock = _Lock()
    monkeypatch.setattr(panel_app, "SingleInstance", lambda _activate: lock)
    monkeypatch.setattr(
        panel_app.PanelApp,
        "run",
        lambda _self: (_ for _ in ()).throw(RuntimeError("WebView2 chết")),
    )

    with pytest.raises(RuntimeError, match="WebView2 chết"):
        panel_app.main()

    assert ("record", "MAIN_LOOP_EXCEPTION") in main_world
    assert not any(event[0] == "clean" for event in main_world)


def test_main_syncs_autostart_only_after_the_lock_is_held(
    monkeypatch, main_world
):
    order: list[str] = []
    lock = _Lock()
    monkeypatch.setattr(panel_app, "SingleInstance", lambda _activate: lock)
    monkeypatch.setattr(
        panel_app, "_sync_packaged_autostart", lambda: order.append("autostart")
    )
    monkeypatch.setattr(
        panel_app.PanelApp, "run", lambda _self: order.append("run")
    )

    panel_app.main()

    assert order == ["autostart", "run"]


def test_a_second_instance_never_touches_the_windows_run_key(
    monkeypatch, main_world
):
    lock = _Lock(acquired=False)
    monkeypatch.setattr(panel_app, "SingleInstance", lambda _activate: lock)
    calls: list[int] = []
    monkeypatch.setattr(
        panel_app, "_sync_packaged_autostart", lambda: calls.append(1)
    )

    panel_app.main()

    assert calls == []


# --- hằng số hiển thị -----------------------------------------------------


def test_the_window_titles_match_the_ones_win32_looks_for():
    from wfx_panel import win32_window

    assert panel_app.MAIN_WINDOW_TITLE == win32_window.MAIN_WINDOW_TITLE
    assert panel_app.BUBBLE_WINDOW_TITLE == win32_window.BUBBLE_WINDOW_TITLE


def test_the_default_hotkey_is_the_documented_one(tmp_path):
    app = _app(tmp_path)

    assert re.fullmatch(r"ctrl\+shift\+x", app._hotkey, re.IGNORECASE)
