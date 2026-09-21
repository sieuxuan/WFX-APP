"""Cửa sổ Hướng dẫn sử dụng và các js_api của cửa sổ con.

CLAUDE.md: Manual chạy offline hoàn toàn — không gọi mạng, không cần Chrome,
không cần phiên WFX. Bấm lần hai đưa cửa sổ đang mở lên trước chứ không tạo
cửa sổ trùng, và sau khi tự cập nhật thì mở thẳng phần Có gì mới.
"""

from __future__ import annotations

import pytest

import wfx_panel.app.bridges as bridges_module
import wfx_panel.app.manual_window as manual_window
import wfx_panel.panel_app as panel_app
from wfx_panel.app.layout import WFX_MANUAL_URL
from wfx_panel.version import APP_VERSION


class FakeWindow:
    def __init__(self, *, show_error=None, events_error=None):
        self.show_error = show_error
        self.shown = 0
        self.destroyed = 0
        self.scripts: list[str] = []
        self.destroy_error = None
        if events_error is None:
            self.events = type("Events", (), {"closed": _Signal()})()
        else:
            self.events = _BrokenEvents(events_error)

    def show(self):
        self.shown += 1
        if self.show_error is not None:
            raise self.show_error

    def destroy(self):
        self.destroyed += 1
        if self.destroy_error is not None:
            raise self.destroy_error

    def evaluate_js(self, script):
        self.scripts.append(script)


class _Signal:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _BrokenEvents:
    def __init__(self, error):
        self._error = error

    @property
    def closed(self):
        raise self._error


@pytest.fixture
def app(monkeypatch, tmp_path):
    instance = panel_app.PanelApp()
    monkeypatch.setattr(
        instance._bubble, "_schedule_bubble_native_bounds", lambda: None
    )
    monkeypatch.setattr(instance, "hide_panel", lambda: None)
    monkeypatch.setattr(manual_window.prefs, "save_prefs", lambda **_kw: None)
    monkeypatch.setattr(
        manual_window.prefs, "load_prefs", lambda **_kw: {"theme": "light"}
    )
    return instance


@pytest.fixture
def manual(app):
    return app._manual


def _no_windows(monkeypatch):
    monkeypatch.setattr(manual_window.webview, "windows", [])


def _creates(monkeypatch, window, error=None):
    def create_window(*_args, **_kwargs):
        if error is not None:
            raise error
        return window

    monkeypatch.setattr(manual_window.webview, "create_window", create_window)


# --- nội dung sách hướng dẫn --------------------------------------------


def test_the_manual_is_built_once_and_reused(manual, monkeypatch):
    calls = []

    def build():
        calls.append(1)
        return {"order": [], "entries": {}, "error_table": []}

    monkeypatch.setattr(manual_window.manual_book, "load_book", build)

    manual.book()
    manual.book()

    assert calls == [1]


def test_the_payload_carries_the_theme_without_touching_the_cached_book(
    manual, monkeypatch
):
    book = {"order": [], "entries": {}, "error_table": []}
    monkeypatch.setattr(manual_window.manual_book, "load_book", lambda: book)

    payload = manual.manual_payload()

    assert payload["theme"] == "light"
    assert payload["manual_url"] == WFX_MANUAL_URL
    assert "theme" not in book


def test_each_module_question_mark_opens_the_entry_that_covers_it(
    manual, monkeypatch
):
    monkeypatch.setattr(
        manual_window.manual_book,
        "load_book",
        lambda: {
            "order": ["catalog", "oc"],
            "entries": {
                "catalog": {"covers": {"modules": ["catalog"]}},
                "oc": {"covers": {"modules": ["oc", "catalog"]}},
            },
            "error_table": [],
        },
    )

    assert manual.manual_entry_for_module("oc") == "oc"
    # Mục đầu tiên khai báo phủ module mới là mục được mở.
    assert manual.manual_entry_for_module("catalog") == "catalog"
    assert manual.get_manual_entry_for_module("khong-co")["entry"] == ""


def test_only_error_codes_with_a_real_entry_get_a_help_button(
    manual, monkeypatch
):
    monkeypatch.setattr(
        manual_window.manual_book,
        "load_book",
        lambda: {
            "order": [],
            "entries": {},
            "error_table": [
                {"code": "CHROME_CLOSED", "entry": "bat-dau"},
                {"code": "PANEL_ERROR", "entry": ""},
            ],
        },
    )

    assert manual.manual_error_codes() == ["CHROME_CLOSED"]


# --- badge Có gì mới ----------------------------------------------------


def test_a_version_the_user_already_read_shows_no_badge(manual, monkeypatch):
    monkeypatch.setattr(
        manual_window.prefs,
        "load_prefs",
        lambda **_kw: {"manual_seen_version": APP_VERSION},
    )

    assert manual.manual_has_news() is False


def test_a_release_with_its_own_news_entry_shows_the_badge(manual, monkeypatch):
    monkeypatch.setattr(
        manual_window.manual_book,
        "load_whats_new",
        lambda: [{"version": APP_VERSION}],
    )

    assert manual.manual_has_news() is True


def test_a_release_with_no_news_entry_shows_no_badge(manual, monkeypatch):
    monkeypatch.setattr(
        manual_window.manual_book, "load_whats_new", lambda: [{"version": "0.0.1"}]
    )

    assert manual.manual_has_news() is False


def test_a_damaged_news_file_never_blocks_the_manual_button(manual, monkeypatch):
    def boom():
        raise manual_window.manual_book.ManualContentError("thiếu file")

    monkeypatch.setattr(manual_window.manual_book, "load_whats_new", boom)

    assert manual.manual_has_news() is False


# --- mở và đóng cửa sổ --------------------------------------------------


def test_the_first_press_opens_the_manual_window(manual, monkeypatch):
    window = FakeWindow()
    _no_windows(monkeypatch)
    _creates(monkeypatch, window)
    monkeypatch.setattr(manual, "manual_has_news", lambda: False)

    result = manual.open_wfx_manual()

    assert result["code"] == "MANUAL_OPENED"
    assert manual.window is window
    assert window.shown == 1


def test_a_second_press_brings_the_open_window_forward_and_jumps_to_a_section(
    manual, monkeypatch
):
    window = FakeWindow()
    manual.window = window
    monkeypatch.setattr(manual_window.webview, "windows", [window])
    monkeypatch.setattr(
        manual_window.webview,
        "create_window",
        lambda *_a, **_k: pytest.fail("không được tạo cửa sổ trùng"),
    )

    result = manual.open_wfx_manual("catalog")

    assert result["code"] == "MANUAL_FOCUSED"
    assert window.scripts == ['window.wfxManualGoTo("catalog")']


def test_a_window_the_user_closed_behind_our_back_is_recreated(
    manual, monkeypatch
):
    stale = FakeWindow()
    fresh = FakeWindow()
    manual.window = stale
    monkeypatch.setattr(manual_window.webview, "windows", [fresh])
    _creates(monkeypatch, fresh)
    monkeypatch.setattr(manual, "manual_has_news", lambda: False)

    assert manual.open_wfx_manual()["code"] == "MANUAL_OPENED"
    assert manual.window is fresh


def test_a_window_that_refuses_to_come_forward_is_replaced(manual, monkeypatch):
    broken = FakeWindow(show_error=RuntimeError("cửa sổ đã bị hủy"))
    fresh = FakeWindow()
    manual.window = broken
    _no_windows(monkeypatch)
    _creates(monkeypatch, fresh)
    monkeypatch.setattr(manual, "manual_has_news", lambda: False)

    assert manual.open_wfx_manual()["code"] == "MANUAL_OPENED"
    assert manual.window is fresh


def test_after_an_update_the_manual_opens_straight_at_the_news_section(
    manual, monkeypatch
):
    window = FakeWindow()
    _no_windows(monkeypatch)
    _creates(monkeypatch, window)
    monkeypatch.setattr(manual, "manual_has_news", lambda: True)

    manual.open_wfx_manual()

    assert manual._target == "co-gi-moi"


def test_a_window_pywebview_refuses_to_create_is_reported(manual, monkeypatch):
    _no_windows(monkeypatch)
    _creates(monkeypatch, None, error=RuntimeError("WebView2 chưa cài"))
    monkeypatch.setattr(manual, "manual_has_news", lambda: False)

    result = manual.open_wfx_manual()

    assert result["code"] == "MANUAL_OPEN_FAILED"
    assert "WebView2" in result["message"]
    assert manual.window is None


def test_a_new_window_that_will_not_show_is_reported(manual, monkeypatch):
    _no_windows(monkeypatch)
    _creates(monkeypatch, FakeWindow(show_error=RuntimeError("màn hình mất")))
    monkeypatch.setattr(manual, "manual_has_news", lambda: False)

    result = manual.open_wfx_manual()

    assert result["code"] == "MANUAL_OPEN_FAILED"
    assert manual.window is None


def test_a_window_whose_close_event_cannot_be_hooked_still_opens(
    manual, monkeypatch
):
    window = FakeWindow(events_error=RuntimeError("không có events"))
    _no_windows(monkeypatch)
    _creates(monkeypatch, window)
    monkeypatch.setattr(manual, "manual_has_news", lambda: False)

    assert manual.open_wfx_manual()["code"] == "MANUAL_OPENED"
    assert manual.window is window


def test_closing_the_window_from_its_own_title_bar_clears_the_reference(
    manual,
):
    manual.window = FakeWindow()

    manual._on_manual_closed()

    assert manual.window is None


def test_closing_the_manual_destroys_the_window_once(manual):
    window = FakeWindow()
    manual.window = window

    manual.close_manual_window()
    manual.close_manual_window()

    assert window.destroyed == 1
    assert manual.window is None


def test_a_window_that_cannot_be_destroyed_still_clears_the_reference(manual):
    window = FakeWindow()
    window.destroy_error = RuntimeError("cửa sổ đã đóng")
    manual.window = window

    manual.close_manual_window()

    assert manual.window is None


# --- in / lưu PDF -------------------------------------------------------


def test_printing_without_an_open_manual_is_refused(manual):
    manual.window = None

    assert manual.print_manual()["code"] == "MANUAL_PRINT_FAILED"


def test_a_print_dialog_the_webview_refuses_is_reported(manual, monkeypatch):
    manual.window = FakeWindow()
    monkeypatch.setattr(
        manual_window, "_show_webview2_print_dialog", lambda _window: False
    )

    result = manual.print_manual()

    assert result["code"] == "MANUAL_PRINT_FAILED"
    assert "hộp thoại in" in result["message"]


def test_a_print_dialog_that_opens_is_reported_as_success(manual, monkeypatch):
    manual.window = FakeWindow()
    monkeypatch.setattr(
        manual_window, "_show_webview2_print_dialog", lambda _window: True
    )

    assert manual.print_manual()["code"] == "MANUAL_PRINT_OPENED"


# --- js_api của các cửa sổ con ------------------------------------------


class Recorder:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, args))
            return {"ok": True, "code": name.upper(), "message": ""}

        return record


@pytest.mark.parametrize(
    "method",
    [
        "toggle_panel",
        "save_bubble_position",
        "note_bubble_interaction",
        "begin_bubble_interaction",
        "end_bubble_interaction",
        "bubble_context_menu",
    ],
)
def test_the_bubble_window_only_forwards_to_the_panel(method):
    app = Recorder()

    getattr(bridges_module._BubbleBridge(app), method)()

    assert app.calls == [(method, ())]


def test_the_bubble_menu_window_only_forwards_to_the_panel():
    app = Recorder()
    bridge = bridges_module._BubbleMenuBridge(app)

    bridge.choose("settings")
    bridge.dismiss()

    assert app.calls == [
        ("choose_bubble_menu", ("settings",)),
        ("dismiss_bubble_menu", ()),
    ]


def test_the_manual_window_reads_content_and_closes_through_the_panel():
    app = Recorder()
    bridge = bridges_module._ManualBridge(app)

    bridge.get_manual_book()
    bridge.print_manual()

    assert bridge.close_manual() == {
        "ok": True,
        "code": "MANUAL_CLOSED",
        "message": "",
    }
    assert [name for name, _args in app.calls] == [
        "manual_payload",
        "print_manual",
        "close_manual_window",
    ]


def test_the_official_wfx_manual_opens_in_the_users_own_browser(monkeypatch):
    opened: list[tuple[str, int]] = []

    def open_url(url, new=0):
        opened.append((url, new))
        return True

    monkeypatch.setattr(bridges_module.webbrowser, "open", open_url)

    result = bridges_module._ManualBridge(Recorder()).open_manual_external()

    assert result["code"] == "MANUAL_OPENED"
    assert opened == [(WFX_MANUAL_URL, 2)]


def test_a_machine_with_no_browser_is_told_so_plainly(monkeypatch):
    monkeypatch.setattr(bridges_module.webbrowser, "open", lambda *_a, **_k: False)

    result = bridges_module._ManualBridge(Recorder()).open_manual_external()

    assert result["code"] == "MANUAL_OPEN_FAILED"
    assert "trình duyệt" in result["message"]


def test_a_browser_that_throws_does_not_crash_the_manual_window(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("không có handler cho https")

    monkeypatch.setattr(bridges_module.webbrowser, "open", boom)

    result = bridges_module._ManualBridge(Recorder()).open_manual_external()

    assert result["code"] == "MANUAL_OPEN_FAILED"
    assert "không có handler" in result["message"]
