"""Khởi động, hotkey, đóng cửa sổ và thoát app.

CLAUDE.md: bootstrap do `PanelApp._startup()` inject một lần; đóng panel bằng
Alt+F4/nút X chỉ thu vào khay hệ thống chứ không thoát app; hai lựa chọn thoát
ở tray phải giải phóng đúng thứ; và startup lỗi không được làm sập app — footer
phải nói rõ thay vì treo ở "Đang kiểm tra...".
"""

from __future__ import annotations

import pytest

import wfx_panel.panel_app as panel_app


class FakeWindow:
    def __init__(self):
        self.scripts: list[str] = []

    def evaluate_js(self, script):
        self.scripts.append(script)


class FakeApi:
    def __init__(self, *, session=None, login=None, state=None):
        self.calls: list[str] = []
        self._session = session or {"ok": False, "message": "chưa đăng nhập"}
        self._login = login or {"ok": True, "message": "Đã đăng nhập"}
        self._state = state if state is not None else {}
        self.logs: list[str] = []

    def get_initial_state(self):
        self.calls.append("get_initial_state")
        if isinstance(self._state, Exception):
            raise self._state
        return self._state

    def flush_error_reports(self):
        self.calls.append("flush_error_reports")

    def check_session(self):
        self.calls.append("check_session")
        return self._session

    def login(self):
        self.calls.append("login")
        return self._login

    def _log(self, line):
        self.logs.append(line)

    def _session_status(self):
        return {"session_active": True}

    def _division_state(self):
        return {"current_division": "woven"}


@pytest.fixture
def app(monkeypatch):
    instance = panel_app.PanelApp()
    monkeypatch.setattr(
        instance._bubble, "_schedule_bubble_native_bounds", lambda: None
    )
    instance._hotkey_ready.set()
    instance._start_hidden = True
    instance.window = FakeWindow()
    instance.api = FakeApi()
    instance._placement.show_panel = lambda: {"ok": True}
    monkeypatch.setattr(
        panel_app.prefs, "load_account", lambda: {"user_id": "", "password": ""}
    )
    monkeypatch.setattr(panel_app.updater, "consume_update_result", lambda: None)
    return instance


def _statuses(app, monkeypatch):
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(
        app, "_set_status", lambda tone, message: seen.append((tone, message))
    )
    return seen


def _logs(app, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(app, "_push_log", seen.append)
    return seen


# --- khởi động ----------------------------------------------------------


def test_a_saved_account_is_logged_in_automatically(app, monkeypatch):
    monkeypatch.setattr(
        panel_app.prefs,
        "load_account",
        lambda: {"user_id": "tester", "password": "mat-khau"},
    )
    statuses = _statuses(app, monkeypatch)
    logs = _logs(app, monkeypatch)

    app._startup()

    assert "login" in app.api.calls
    assert "check_session" not in app.api.calls
    assert statuses[-1][0] == "success"
    assert any("Tự động đăng nhập" in line for line in logs)


def test_an_account_without_a_password_only_checks_the_session(app, monkeypatch):
    statuses = _statuses(app, monkeypatch)

    app._startup()

    assert "check_session" in app.api.calls
    assert "login" not in app.api.calls
    assert statuses[-1][0] == "warning"


def test_the_result_of_the_last_update_is_shown_after_the_session_status(
    app, monkeypatch
):
    monkeypatch.setattr(
        panel_app.updater,
        "consume_update_result",
        lambda: {"ok": True, "code": "UPDATE_INSTALLED", "message": "Đã cập nhật."},
    )
    statuses = _statuses(app, monkeypatch)
    logs = _logs(app, monkeypatch)

    app._startup()

    assert statuses[-1] == ("success", "Đã cập nhật.")
    assert any("[UPDATE] UPDATE_INSTALLED" in line for line in logs)


def test_a_failed_update_is_reported_as_needing_attention(app, monkeypatch):
    monkeypatch.setattr(
        panel_app.updater,
        "consume_update_result",
        lambda: {"ok": False, "code": "UPDATE_FAILED", "message": "Không cài được."},
    )
    statuses = _statuses(app, monkeypatch)

    app._startup()

    assert statuses[-1] == ("warning", "Không cài được.")


def test_a_startup_that_fails_says_so_instead_of_hanging_on_checking(
    app, monkeypatch
):
    app.api = FakeApi(state=RuntimeError("WebView2 chưa sẵn sàng"))
    statuses = _statuses(app, monkeypatch)
    logs = _logs(app, monkeypatch)

    app._startup()

    assert statuses[-1][0] == "error"
    assert "Lỗi khởi động" in statuses[-1][1]
    assert any("[ERROR] Startup lỗi" in line for line in logs)


def test_a_startup_that_fails_still_shows_the_panel_the_user_expected(
    app, monkeypatch
):
    app._start_hidden = False
    app.api = FakeApi(state=RuntimeError("WebView2 chưa sẵn sàng"))
    shown: list[int] = []
    app._placement.show_panel = lambda: shown.append(1) or {"ok": True}
    _statuses(app, monkeypatch)
    _logs(app, monkeypatch)

    app._startup()

    assert shown == [1]


def test_a_startup_that_fails_while_hidden_does_not_pop_the_panel_open(
    app, monkeypatch
):
    app.api = FakeApi(state=RuntimeError("WebView2 chưa sẵn sàng"))
    shown: list[int] = []
    app._placement.show_panel = lambda: shown.append(1) or {"ok": True}
    _statuses(app, monkeypatch)
    _logs(app, monkeypatch)

    app._startup()

    assert shown == []


def test_a_hotkey_that_windows_refused_is_reported_once_the_panel_is_ready(
    app, monkeypatch
):
    app._hotkey_error = "phím bị chiếm"
    statuses = _statuses(app, monkeypatch)
    logs = _logs(app, monkeypatch)

    app._startup()

    assert statuses[-1][0] == "error"
    assert app._hotkey.upper() in statuses[-1][1]
    assert "Administrator" in statuses[-1][1]
    assert any("[ERROR]" in line for line in logs)


def test_the_bootstrap_state_is_injected_exactly_once(app):
    app._startup()

    injected = [line for line in app.window.scripts if "wfxBootstrap" in line]
    assert len(injected) == 1


def test_loading_the_window_starts_the_background_startup(app, monkeypatch):
    started: list[object] = []

    class FakeThread:
        def __init__(self, target=None, daemon=None, **_kwargs):
            self.target = target

        def start(self):
            started.append(self.target)

    monkeypatch.setattr(panel_app.threading, "Thread", FakeThread)

    app.on_loaded()

    assert started == [app._startup]


# --- hotkey -------------------------------------------------------------


def test_registering_a_new_hotkey_replaces_the_old_one(app, monkeypatch):
    previous = app._hotkey
    removed: list[str] = []
    added: list[str] = []
    monkeypatch.setattr(
        panel_app.keyboard, "remove_hotkey", lambda spec: removed.append(spec)
    )
    monkeypatch.setattr(
        panel_app.keyboard,
        "add_hotkey",
        lambda spec, _handler: added.append(spec),
    )

    assert app._apply_hotkey("ctrl+alt+j") is None
    assert removed == [previous]
    assert added == ["ctrl+alt+j"]


def test_a_hotkey_that_was_never_registered_is_simply_replaced(app, monkeypatch):
    def refuse(_spec):
        raise KeyError("chưa đăng ký")

    monkeypatch.setattr(panel_app.keyboard, "remove_hotkey", refuse)
    monkeypatch.setattr(panel_app.keyboard, "add_hotkey", lambda *_a: None)

    assert app._apply_hotkey("ctrl+alt+j") is None


def test_the_hotkey_toggles_the_panel(app, monkeypatch):
    toggles: list[int] = []
    monkeypatch.setattr(app, "toggle_panel", lambda: toggles.append(1))

    app.toggle()

    assert toggles == [1]


# --- đóng cửa sổ và thoát ------------------------------------------------


def test_closing_the_panel_only_hides_it(app, monkeypatch):
    hidden: list[int] = []
    monkeypatch.setattr(app, "hide_panel", lambda: hidden.append(1))

    assert app._on_closing() is False
    assert hidden == [1]


def test_closing_the_panel_while_quitting_really_closes_it(app, monkeypatch):
    app._quitting = True
    monkeypatch.setattr(
        app, "hide_panel", lambda: pytest.fail("đang thoát thì không thu panel")
    )

    assert app._on_closing() is None


def test_quitting_releases_the_hotkey_the_lock_and_the_tray(app, monkeypatch):
    released: list[str] = []

    class FakeLock:
        def close(self):
            released.append("lock")

    class FakeTray:
        def stop(self):
            released.append("tray")

    app.lock = FakeLock()
    app.tray = FakeTray()
    app.api = type(
        "Api",
        (),
        {"shutdown": lambda _self, close_browser=False: released.append("api")},
    )()
    monkeypatch.setattr(
        panel_app.keyboard, "remove_hotkey", lambda _spec: released.append("hotkey")
    )
    monkeypatch.setattr(panel_app.webview, "windows", [])

    app.quit()

    assert released == ["api", "hotkey", "lock", "tray"]
    assert app._quitting is True


def test_quitting_without_a_registered_hotkey_still_shuts_down(app, monkeypatch):
    def refuse(_spec):
        raise ValueError("hotkey không hợp lệ")

    app.lock = None
    app.tray = None
    app.api = type("Api", (), {})()
    monkeypatch.setattr(panel_app.keyboard, "remove_hotkey", refuse)
    monkeypatch.setattr(panel_app.webview, "windows", [])

    app.quit()

    assert app._quitting is True


# --- delegator sang controller của lớp vỏ --------------------------------


class Recorder:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, args))
            return f"ket-qua-{name}"

        return record


SHELL_DELEGATIONS = [
    ("_placement", "toggle_panel", ()),
    ("_placement", "_focus_module_search", ()),
    ("_placement", "focus_automation_browser", ()),
    ("_placement", "_taskbar_activation_loop", ()),
    ("_bubble", "_bubble_menu_position", ()),
    ("_bubble", "_on_bubble_taskbar_event", ()),
    ("_bubble", "_on_bubble_closing", ()),
    ("_bubble", "_on_bubble_menu_closing", ()),
    ("_manual", "get_manual_entry_for_module", ("catalog",)),
    ("_manual", "close_manual_window", ()),
    ("_manual", "print_manual", ()),
    ("_manual", "open_wfx_manual", ("catalog",)),
    ("_manual", "_on_manual_closed", ()),
    ("_notifications", "_hide_notification", ()),
    ("_notifications", "set_toast_enabled_state", (True,)),
    ("_background", "_apply_update", ({"version": "1.1.0"},)),
]


@pytest.mark.parametrize(
    ("owner", "method", "args"),
    SHELL_DELEGATIONS,
    ids=[item[1] for item in SHELL_DELEGATIONS],
)
def test_the_shell_forwards_to_the_controller_that_owns_the_window(
    app, monkeypatch, owner, method, args
):
    recorder = Recorder()
    monkeypatch.setattr(app, owner, recorder)

    result = getattr(app, method)(*args)

    assert result == f"ket-qua-{method}"
    assert recorder.calls == [(method, args)]


# --- bản đóng gói --------------------------------------------------------


def test_a_packaged_build_seeds_the_article_library_from_its_own_resource(
    monkeypatch, tmp_path
):
    seeded: list[tuple] = []
    monkeypatch.setattr(panel_app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        panel_app.article_library,
        "seed_bundled",
        lambda base_dir, source: seeded.append((base_dir, source)),
    )

    instance = panel_app.PanelApp()
    instance._bubble._schedule_bubble_native_bounds = lambda: None

    assert len(seeded) == 1
    assert seeded[0][1].name == "Article List.csv"


def test_a_source_checkout_never_seeds_the_article_library(monkeypatch):
    monkeypatch.delattr(panel_app.sys, "frozen", raising=False)
    monkeypatch.setattr(
        panel_app.article_library,
        "seed_bundled",
        lambda *_args: pytest.fail("bản source không được ghi cache vào workspace"),
    )

    instance = panel_app.PanelApp()
    instance._bubble._schedule_bubble_native_bounds = lambda: None


# --- kết quả gửi sang UI -------------------------------------------------


def test_saving_sale_asn_documents_without_a_folder_says_so_in_the_log(
    app, monkeypatch
):
    monkeypatch.setattr(app, "_handle_downloaded_excel", lambda _path: False)
    monkeypatch.setattr(app._dialogs, "reveal_download", lambda _path: False)

    app._on_result(
        "save_sale_asn_documents",
        {"ok": True, "download_path": "C:/Downloads/Invoice.xlsx"},
        1.0,
    )

    assert any("[SALE ASN]" in line for line in app.api.logs)
