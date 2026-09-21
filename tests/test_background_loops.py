"""Bốn vòng lặp nền của lớp vỏ desktop.

CLAUDE.md đặc tả rất chặt về chúng — heartbeat thành công phải im lặng tuyệt
đối, heartbeat nền không tự mở lại Chrome, vòng cập nhật chỉ đẩy trạng thái
chứ không tự cài — nhưng `wfx_panel/app/background.py` trước đây chưa có test
nào chạm tới thân hàm. Test ở đây chạy đúng các vòng lặp đó với một
``PanelApp`` thật, chỉ thay `api`/`window`/`tray` bằng fake.
"""

from __future__ import annotations

import threading

import pytest

from wfx_panel import panel_app, prefs
from wfx_panel.app import background as app_background
from wfx_panel.app.background import BackgroundLoopController


class FakeWindow:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def evaluate_js(self, script: str) -> None:
        self.scripts.append(script)


class FakeTray:
    def __init__(self, *, fail: bool = False) -> None:
        self.notifications: list[tuple[str, str]] = []
        self._fail = fail

    def notify(self, message: str, title: str) -> None:
        if self._fail:
            raise RuntimeError("tray chưa sẵn sàng")
        self.notifications.append((message, title))


class FakeApi:
    """Chỉ những method mà vòng lặp nền thực sự gọi."""

    def __init__(self, **overrides: object) -> None:
        self.calls: list[str] = []
        self._overrides = overrides
        self.maintain_calls = 0

    def should_maintain_session(self) -> bool:
        self.calls.append("should_maintain_session")
        return bool(self._overrides.get("should_maintain", True))

    def is_action_running(self) -> bool:
        self.calls.append("is_action_running")
        return bool(self._overrides.get("action_running", False))

    def maintain_session(self) -> dict:
        self.calls.append("maintain_session")
        self.maintain_calls += 1
        return {"ok": True, "code": "SESSION_ACTIVE"}

    def check_for_updates(self) -> dict:
        self.calls.append("check_for_updates")
        state = self._overrides.get("update_state")
        if isinstance(state, Exception):
            raise state
        return dict(state or {"ok": True, "can_update": False})

    def sync_reference_data(self, force: bool = False) -> dict:
        self.calls.append(f"sync_reference_data:{force}")
        result = self._overrides.get("reference_result")
        if isinstance(result, Exception):
            raise result
        return dict(result or {"ok": True, "code": "REFERENCE_SYNCED"})

    def sync_article_library(self) -> dict:
        self.calls.append("sync_article_library")
        return dict(self._overrides.get("article_result") or {"ok": True})


def _app(monkeypatch, api: FakeApi, *, window: FakeWindow | None = None):
    monkeypatch.setattr(prefs, "DATA_DIR", prefs.DATA_DIR)
    app = panel_app.PanelApp()
    app.api = api  # type: ignore[assignment]
    app.window = window  # type: ignore[assignment]
    return app


class ImmediateEvent:
    """``threading.Event`` giả: wait() trả False đúng ``ticks`` lần rồi True.

    Vòng lặp nền dùng ``_stop_status.wait(seconds)`` làm cả sleep lẫn tín hiệu
    dừng; fake này cho test chạy đúng N vòng mà không tốn một giây thật nào.
    """

    def __init__(self, ticks: int) -> None:
        self._remaining = ticks
        self.waits: list[float] = []
        self._set = False

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append(float(timeout or 0))
        if self._remaining <= 0:
            return True
        self._remaining -= 1
        return False

    def is_set(self) -> bool:
        return self._set or self._remaining <= 0

    def set(self) -> None:
        self._set = True
        self._remaining = 0


# --- vòng trạng thái ------------------------------------------------------


def test_status_loop_pushes_chrome_status_only_when_it_changes(monkeypatch):
    api = FakeApi()
    window = FakeWindow()
    app = _app(monkeypatch, api, window=window)
    app._stop_status = ImmediateEvent(3)  # type: ignore[assignment]
    app._chrome_alive = None
    states = iter([True, True, False])
    monkeypatch.setattr(app_background.status, "chrome_alive", lambda: next(states))
    # Giữ heartbeat ngoài tầm với để test này chỉ nói về badge Chrome.
    monkeypatch.setattr(app_background, "SESSION_MAINTENANCE_INITIAL_DELAY_SECONDS", 10_000)

    BackgroundLoopController(app)._status_loop()

    assert app._chrome_alive is False
    assert [s for s in window.scripts if "wfxSetChromeStatus" in s] == [
        "window.wfxSetChromeStatus(true)",
        "window.wfxSetChromeStatus(false)",
    ]


def test_status_loop_survives_an_evaluate_js_failure(monkeypatch):
    """Một lỗi native tạm thời không được giết thread trạng thái."""

    class BrokenWindow(FakeWindow):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def evaluate_js(self, script: str) -> None:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("WebView2 chưa sẵn sàng")
            super().evaluate_js(script)

    api = FakeApi()
    window = BrokenWindow()
    app = _app(monkeypatch, api, window=window)
    app._stop_status = ImmediateEvent(3)  # type: ignore[assignment]
    app._chrome_alive = None
    states = iter([True, False, True])
    monkeypatch.setattr(app_background.status, "chrome_alive", lambda: next(states))
    monkeypatch.setattr(app_background, "SESSION_MAINTENANCE_INITIAL_DELAY_SECONDS", 10_000)

    BackgroundLoopController(app)._status_loop()

    assert window.calls == 3
    assert app._chrome_alive is True


def test_status_loop_runs_heartbeat_when_chrome_is_idle(monkeypatch):
    api = FakeApi()
    app = _app(monkeypatch, api)
    app._stop_status = ImmediateEvent(2)  # type: ignore[assignment]
    app._chrome_alive = True
    monkeypatch.setattr(app_background.status, "chrome_alive", lambda: True)
    monkeypatch.setattr(app_background, "SESSION_MAINTENANCE_INITIAL_DELAY_SECONDS", -1)
    monkeypatch.setattr(app_background, "SESSION_MAINTENANCE_SECONDS", 10_000)

    BackgroundLoopController(app)._status_loop()

    assert api.maintain_calls == 1


def test_heartbeat_is_skipped_while_a_user_action_is_running(monkeypatch):
    api = FakeApi(action_running=True)
    app = _app(monkeypatch, api)
    app._stop_status = ImmediateEvent(2)  # type: ignore[assignment]
    app._chrome_alive = True
    monkeypatch.setattr(app_background.status, "chrome_alive", lambda: True)
    monkeypatch.setattr(app_background, "SESSION_MAINTENANCE_INITIAL_DELAY_SECONDS", -1)

    BackgroundLoopController(app)._status_loop()

    assert api.maintain_calls == 0


def test_heartbeat_never_reopens_chrome_the_user_closed(monkeypatch):
    """CLAUDE.md: heartbeat nền không tự mở lại Chrome."""
    api = FakeApi()
    app = _app(monkeypatch, api)
    app._stop_status = ImmediateEvent(2)  # type: ignore[assignment]
    app._chrome_alive = True
    monkeypatch.setattr(app_background.status, "chrome_alive", lambda: False)
    monkeypatch.setattr(app_background, "SESSION_MAINTENANCE_INITIAL_DELAY_SECONDS", -1)

    BackgroundLoopController(app)._status_loop()

    assert api.maintain_calls == 0
    assert "maintain_session" not in api.calls


# --- vòng cập nhật --------------------------------------------------------


def test_update_check_notifies_once_per_new_release(monkeypatch, tmp_path):
    api = FakeApi(
        update_state={"ok": True, "can_update": True, "notice_id": "v9.9.9"}
    )
    app = _app(monkeypatch, api)
    app.tray = FakeTray()  # type: ignore[assignment]
    app._toast_enabled = True
    app._last_update_notice = ""
    saved: list[dict] = []
    monkeypatch.setattr(
        app_background.prefs, "save_prefs", lambda **kw: saved.append(kw)
    )

    controller = BackgroundLoopController(app)
    controller._check_update_once()
    controller._check_update_once()

    assert app._last_update_notice == "v9.9.9"
    assert len(app.tray.notifications) == 1
    assert saved == [{"last_update_notice": "v9.9.9"}]


def test_update_check_falls_back_to_tag_then_version_for_the_notice_id(
    monkeypatch,
):
    app = _app(monkeypatch, FakeApi(update_state={"can_update": True, "tag": "v2"}))
    app.tray = FakeTray()  # type: ignore[assignment]
    app._toast_enabled = True
    app._last_update_notice = ""
    monkeypatch.setattr(app_background.prefs, "save_prefs", lambda **kw: None)

    BackgroundLoopController(app)._check_update_once()

    assert app._last_update_notice == "v2"


def test_update_check_stays_silent_when_toasts_are_disabled(monkeypatch):
    app = _app(
        monkeypatch,
        FakeApi(update_state={"can_update": True, "version": "3.0.0"}),
    )
    app.tray = FakeTray()  # type: ignore[assignment]
    app._toast_enabled = False
    app._last_update_notice = ""
    monkeypatch.setattr(app_background.prefs, "save_prefs", lambda **kw: None)

    BackgroundLoopController(app)._check_update_once()

    assert app.tray.notifications == []
    # Vẫn ghi nhớ notice để lần sau không lặp lại quyết định.
    assert app._last_update_notice == "3.0.0"


def test_update_check_survives_a_failing_tray(monkeypatch):
    app = _app(monkeypatch, FakeApi(update_state={"can_update": True, "tag": "v4"}))
    app.tray = FakeTray(fail=True)  # type: ignore[assignment]
    app._toast_enabled = True
    app._last_update_notice = ""
    monkeypatch.setattr(app_background.prefs, "save_prefs", lambda **kw: None)

    BackgroundLoopController(app)._check_update_once()  # không được raise

    assert app._last_update_notice == "v4"


def test_update_loop_logs_failures_and_keeps_going(monkeypatch):
    api = FakeApi(update_state=RuntimeError("mạng hỏng"))
    app = _app(monkeypatch, api)
    app._stop_status = ImmediateEvent(2)  # type: ignore[assignment]
    logs: list[str] = []
    monkeypatch.setattr(app, "_push_log", logs.append)

    BackgroundLoopController(app)._update_loop()

    assert logs and all("[UPDATE]" in line for line in logs)
    assert all("RuntimeError" in line for line in logs)


def test_update_loop_exits_immediately_when_stopped_during_initial_delay(
    monkeypatch,
):
    api = FakeApi()
    app = _app(monkeypatch, api)
    app._stop_status = ImmediateEvent(0)  # type: ignore[assignment]

    BackgroundLoopController(app)._update_loop()

    assert "check_for_updates" not in api.calls


# --- vòng Article Library -------------------------------------------------


def test_article_library_loop_pushes_both_status_hooks(monkeypatch):
    api = FakeApi(reference_result={"ok": True, "version": "20260101T000000Z"})
    window = FakeWindow()
    app = _app(monkeypatch, api, window=window)
    app._stop_status = ImmediateEvent(2)  # type: ignore[assignment]

    BackgroundLoopController(app)._article_library_loop()

    assert len(window.scripts) == 1
    script = window.scripts[0]
    assert "wfxSetReferenceSyncStatus" in script
    assert "wfxSetArticleLibraryStatus" in script
    assert "20260101T000000Z" in script


def test_article_library_loop_falls_back_to_github_when_postgres_fails(monkeypatch):
    api = FakeApi(
        reference_result={"ok": False, "code": "REFERENCE_SYNC_FAILED"},
        article_result={"ok": True, "code": "ARTICLE_LIBRARY_SYNCED"},
    )
    window = FakeWindow()
    app = _app(monkeypatch, api, window=window)
    app._stop_status = ImmediateEvent(2)  # type: ignore[assignment]

    BackgroundLoopController(app)._article_library_loop()

    assert "sync_article_library" in api.calls
    assert "ARTICLE_LIBRARY_SYNCED" in window.scripts[0]


def test_article_library_loop_keeps_the_failure_when_the_fallback_also_fails(
    monkeypatch,
):
    api = FakeApi(
        reference_result={"ok": False, "code": "REFERENCE_SYNC_FAILED"},
        article_result={"ok": False, "code": "ARTICLE_LIBRARY_FAILED"},
    )
    window = FakeWindow()
    app = _app(monkeypatch, api, window=window)
    app._stop_status = ImmediateEvent(2)  # type: ignore[assignment]

    BackgroundLoopController(app)._article_library_loop()

    assert "REFERENCE_SYNC_FAILED" in window.scripts[0]


def test_article_library_loop_logs_and_survives_an_exception(monkeypatch):
    api = FakeApi(reference_result=OSError("đĩa hỏng"))
    app = _app(monkeypatch, api)
    app._stop_status = ImmediateEvent(2)  # type: ignore[assignment]
    logs: list[str] = []
    monkeypatch.setattr(app, "_push_log", logs.append)

    BackgroundLoopController(app)._article_library_loop()

    assert logs == ["[ARTICLE LIBRARY] Không kiểm tra tự động được: OSError"]


def test_article_library_loop_exits_when_stopped_during_initial_delay(monkeypatch):
    api = FakeApi()
    app = _app(monkeypatch, api)
    app._stop_status = ImmediateEvent(0)  # type: ignore[assignment]

    BackgroundLoopController(app)._article_library_loop()

    assert api.calls == []


# --- cài đặt bản cập nhật -------------------------------------------------


def test_apply_update_refuses_to_install_from_a_development_checkout(monkeypatch):
    app = _app(monkeypatch, FakeApi())
    monkeypatch.delattr(app_background.sys, "frozen", raising=False)

    message = BackgroundLoopController(app)._apply_update({"tag": "v1"})

    assert message is not None
    assert "development" in message


def test_apply_update_schedules_helper_and_quits_the_app(monkeypatch, tmp_path):
    app = _app(monkeypatch, FakeApi())
    monkeypatch.setattr(app_background.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        app_background.sys, "executable", str(tmp_path / "WFX-Panel.exe")
    )
    scheduled: list[tuple] = []
    monkeypatch.setattr(
        app_background.updater,
        "schedule_update",
        lambda state, current_pid, executable: scheduled.append(
            (state, current_pid, executable)
        ),
    )
    timers: list[threading.Timer] = []

    class CapturingTimer:
        def __init__(self, delay, function):
            self.delay = delay
            self.function = function
            timers.append(self)  # type: ignore[arg-type]

        def start(self) -> None:
            self.started = True

    monkeypatch.setattr(app_background.threading, "Timer", CapturingTimer)

    message = BackgroundLoopController(app)._apply_update({"tag": "v5"})

    assert message is None
    assert scheduled and scheduled[0][0] == {"tag": "v5"}
    assert scheduled[0][2].name == "WFX-Panel.exe"
    assert timers and timers[0].function == app.quit


def test_apply_update_reports_a_scheduling_failure_instead_of_raising(monkeypatch):
    app = _app(monkeypatch, FakeApi())
    monkeypatch.setattr(app_background.sys, "frozen", True, raising=False)

    def boom(*_args, **_kwargs):
        raise OSError("không ghi được helper")

    monkeypatch.setattr(app_background.updater, "schedule_update", boom)

    message = BackgroundLoopController(app)._apply_update({"tag": "v6"})

    assert message is not None
    assert message.startswith("Không lên lịch được cập nhật:")


# --- panel_app vẫn là bề mặt công khai của bốn vòng lặp -------------------


@pytest.mark.parametrize(
    "method",
    ["_status_loop", "_check_update_once", "_update_loop", "_article_library_loop"],
)
def test_panel_app_delegates_every_background_loop(monkeypatch, method):
    app = _app(monkeypatch, FakeApi())
    seen: list[str] = []
    monkeypatch.setattr(
        app._background, method, lambda: seen.append(method) or "ok"
    )

    assert getattr(app, method)() == "ok"
    assert seen == [method]
