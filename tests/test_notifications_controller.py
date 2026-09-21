"""Toast báo xong việc: native khi tray sẵn sàng, giữ lại khi chưa.

CLAUDE.md: tray sẵn sàng thì dùng notification native để không tốn thêm một
WebView2 hidden và vẫn lưu ở Notification Center; tray chưa sẵn sàng thì giữ
thông báo mới nhất rồi phát ngay sau callback setup. Toast không lấy focus và
tắt công tắc thì phải gỡ toast đang hiện.
"""

from __future__ import annotations

import pytest

import wfx_panel.panel_app as panel_app
from wfx_panel.app.layout import NOTIFICATION_ACTION_LABELS


class FakeTray:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.sent: list[tuple[str, str]] = []
        self.removed = 0

    def notify(self, message, title):
        if self.fail:
            raise OSError("shell_notifyicon thất bại")
        self.sent.append((message, title))

    def remove_notification(self):
        self.removed += 1
        if self.fail:
            raise OSError("không gỡ được toast")


@pytest.fixture
def app(monkeypatch):
    instance = panel_app.PanelApp()
    monkeypatch.setattr(
        instance._bubble, "_schedule_bubble_native_bounds", lambda: None
    )
    instance._toast_enabled = True
    return instance


# --- phát toast ---------------------------------------------------------


def test_a_ready_tray_sends_the_toast_natively(app):
    app.tray = FakeTray()
    app._tray_ready.set()

    assert app._show_notification({"ok": True, "message": "Đã xong."}) is True

    assert app.tray.sent == [("Đã xong.", "WFX Smart · Hoàn thành")]
    assert app._pending_native_notification is None


def test_a_tray_that_is_not_ready_yet_keeps_the_latest_toast(app):
    app.tray = FakeTray()

    assert app._show_notification({"ok": True, "message": "Xong lượt 1"}) is True
    assert app._show_notification({"ok": True, "message": "Xong lượt 2"}) is True

    assert app.tray.sent == []
    assert app._pending_native_notification == (
        "Xong lượt 2",
        "WFX Smart · Hoàn thành",
    )


def test_a_failed_toast_is_reported_and_written_to_the_technical_log(app):
    app.tray = FakeTray(fail=True)
    app._tray_ready.set()
    logged: list[str] = []
    app.api._log = logged.append

    assert app._show_notification({"ok": True, "message": "Đã xong."}) is False

    assert any("[NOTIFICATION]" in line and "OSError" in line for line in logged)


def test_a_failed_run_is_labelled_as_needing_a_check(app):
    app.tray = FakeTray()
    app._tray_ready.set()

    app._show_notification({"ok": False, "message": "Không mở được Catalog."})

    assert app.tray.sent == [
        ("Không mở được Catalog.", "WFX Smart · Cần kiểm tra"),
    ]


def test_the_toast_title_names_the_flow_that_finished(app):
    app.tray = FakeTray()
    app._tray_ready.set()
    method = next(iter(NOTIFICATION_ACTION_LABELS))

    app._show_notification({"ok": True, "message": "Đã xong."}, method=method)

    assert app.tray.sent[0][1].startswith(NOTIFICATION_ACTION_LABELS[method])


def test_a_result_without_a_message_still_says_something(app):
    app.tray = FakeTray()
    app._tray_ready.set()

    app._show_notification({"ok": True})

    assert app.tray.sent == [("Đã xong.", "WFX Smart · Hoàn thành")]


def test_no_toast_is_sent_while_the_setting_is_off(app):
    app.tray = FakeTray()
    app._tray_ready.set()
    app._toast_enabled = False

    assert app._show_notification({"ok": True, "message": "Đã xong."}) is False

    assert app.tray.sent == []


# --- gỡ toast -----------------------------------------------------------


def test_turning_the_setting_off_removes_the_toast_on_screen(app):
    app.tray = FakeTray()
    app._tray_ready.set()
    app._show_notification({"ok": True, "message": "Đã xong."})

    app.set_toast_enabled_state(False)

    assert app._toast_enabled is False
    assert app.tray.removed == 1


def test_turning_the_setting_on_leaves_the_current_toast_alone(app):
    app.tray = FakeTray()

    app.set_toast_enabled_state(True)

    assert app._toast_enabled is True
    assert app.tray.removed == 0


def test_a_tray_that_refuses_to_remove_the_toast_does_not_break_settings(app):
    app.tray = FakeTray(fail=True)
    app._pending_native_notification = ("Đã xong.", "WFX Smart · Hoàn thành")

    app.set_toast_enabled_state(False)

    assert app._pending_native_notification is None


def test_removing_a_toast_without_a_tray_is_harmless(app):
    app.tray = None
    app._pending_native_notification = ("Đã xong.", "WFX Smart · Hoàn thành")

    app.set_toast_enabled_state(False)

    assert app._pending_native_notification is None


# --- nút thử toast trong Settings ---------------------------------------


def test_the_settings_test_button_sends_a_real_toast(app):
    app.tray = FakeTray()
    app._tray_ready.set()

    result = app.show_test_notification()

    assert result["code"] == "TOAST_TESTED"
    assert result["ok"] is True
    assert len(app.tray.sent) == 1


def test_the_settings_test_button_asks_the_user_to_turn_toasts_on_first(app):
    app._toast_enabled = False

    result = app.show_test_notification()

    assert result["code"] == "TOAST_DISABLED"
    assert result["ok"] is False


def test_the_settings_test_button_reports_a_toast_that_did_not_appear(app):
    app.tray = FakeTray(fail=True)
    app._tray_ready.set()
    app.api._log = lambda _line: None

    result = app.show_test_notification()

    assert result["code"] == "TOAST_DISPLAY_FAILED"
    assert result["ok"] is False
