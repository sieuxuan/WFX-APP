"""WebView2 chết giữa chừng: phát hiện, gỡ thread đang kẹt, tự mở lại app.

Đo trên máy thật (04/11/2026): kill browser process của WebView2 làm bubble
thành ô một màu `#0f9fb2`, `evaluate_js` treo vĩnh viễn và pywebview không hề
báo gì. Log/progress/kết quả đều gọi `evaluate_js` trên automation worker, nên
flow đang chạy cũng treo theo.
"""

import json
import threading
import time
import types

import pytest

from wfx_panel.app import webview2_recovery, webview2_watchdog
from wfx_panel.app.webview2_watchdog import WebView2Watchdog


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


def _fake_edgechromium(ready_args=None):
    class EdgeChrome:
        def __init__(self, title="WFX Smart"):
            self.pywebview_window = types.SimpleNamespace(title=title)
            self.ready_calls = 0

        def on_webview_ready(self, sender, args):
            self.ready_calls += 1

    return types.SimpleNamespace(EdgeChrome=EdgeChrome, Semaphore=threading.Semaphore)


def _ready_args(success=True, error=None):
    return types.SimpleNamespace(IsSuccess=success, InitializationException=error)


def _sender():
    return types.SimpleNamespace(
        CoreWebView2=types.SimpleNamespace(ProcessFailed=_Event())
    )


def _failure(kind, reason="Crashed", exit_code=-1):
    return types.SimpleNamespace(
        ProcessFailedKind=kind,
        Reason=reason,
        ExitCode=exit_code,
        ProcessDescription="",
    )


def _installed(module=None):
    calls = []
    watchdog = WebView2Watchdog(calls.append)
    module = module or _fake_edgechromium()
    assert watchdog.install(module) is True
    return watchdog, module, calls


def _fire(module, title, kind):
    edge = module.EdgeChrome(title)
    sender = _sender()
    edge.on_webview_ready(sender, _ready_args())
    (handler,) = sender.CoreWebView2.ProcessFailed.handlers
    handler(sender, _failure(kind))


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_install_keeps_pywebview_ready_handler_and_subscribes_process_failed():
    _watchdog, module, _calls = _installed()
    edge = module.EdgeChrome()
    sender = _sender()

    edge.on_webview_ready(sender, _ready_args())

    assert edge.ready_calls == 1
    assert len(sender.CoreWebView2.ProcessFailed.handlers) == 1


def test_install_refuses_a_pywebview_it_does_not_recognise():
    watchdog = WebView2Watchdog(lambda _info: None)

    assert watchdog.install(types.SimpleNamespace()) is False


def test_failed_initialisation_is_logged_without_triggering_a_restart(monkeypatch):
    records = []
    monkeypatch.setattr(
        webview2_watchdog.crash_log,
        "record",
        lambda event, **details: records.append((event, details)),
    )
    _watchdog, module, calls = _installed()
    edge = module.EdgeChrome("WFX Smart Bubble")
    sender = _sender()

    edge.on_webview_ready(sender, _ready_args(False, ValueError("no runtime")))

    assert [event for event, _details in records] == ["WEBVIEW2_INIT_FAILED"]
    assert records[0][1]["window"] == "WFX Smart Bubble"
    assert sender.CoreWebView2.ProcessFailed.handlers == []
    assert calls == []


@pytest.mark.parametrize(
    ("title", "kind"),
    [
        ("WFX Smart", "BrowserProcessExited"),
        ("Hướng dẫn sử dụng", "BrowserProcessExited"),
        ("WFX Smart", "RenderProcessExited"),
        ("WFX Smart Bubble", "RenderProcessExited"),
    ],
)
def test_fatal_failures_reach_recovery(title, kind):
    watchdog, module, calls = _installed()

    _fire(module, title, kind)

    assert _wait_for(lambda: len(calls) == 1)
    assert calls[0]["kind"] == kind
    assert calls[0]["window"] == title
    assert watchdog.dead.is_set()


@pytest.mark.parametrize(
    ("title", "kind"),
    [
        ("WFX Smart", "GpuProcessExited"),
        ("WFX Smart", "RenderProcessUnresponsive"),
        ("WFX Smart", "FrameRenderProcessExited"),
        ("WFX Smart", "UtilityProcessExited"),
        # Menu và Manual là phụ: renderer của chúng chết không đáng restart
        # cả app đang dùng bình thường.
        ("WFX Smart Bubble Menu", "RenderProcessExited"),
        ("Hướng dẫn sử dụng", "RenderProcessExited"),
    ],
)
def test_recoverable_failures_are_logged_but_do_not_restart(monkeypatch, title, kind):
    records = []
    monkeypatch.setattr(
        webview2_watchdog.crash_log,
        "record",
        lambda event, **details: records.append(event),
    )
    watchdog, module, calls = _installed()

    _fire(module, title, kind)

    time.sleep(0.05)
    assert calls == []
    assert not watchdog.dead.is_set()
    assert records == ["WEBVIEW2_PROCESS_FAILED"]


def test_every_window_reports_browser_exit_but_recovery_runs_once():
    _watchdog, module, calls = _installed()

    _fire(module, "WFX Smart", "BrowserProcessExited")
    _fire(module, "WFX Smart Bubble", "BrowserProcessExited")

    assert _wait_for(lambda: len(calls) >= 1)
    time.sleep(0.05)
    assert len(calls) == 1


def test_handler_returns_without_waiting_for_recovery():
    """ProcessFailed chạy trên UI thread; chặn ở đây là đóng băng cả WinForms."""
    release = threading.Event()
    watchdog = WebView2Watchdog(lambda _info: release.wait(5))
    module = _fake_edgechromium()
    watchdog.install(module)

    started = time.monotonic()
    _fire(module, "WFX Smart", "BrowserProcessExited")
    elapsed = time.monotonic() - started
    release.set()

    assert elapsed < 1


def test_thread_stuck_in_evaluate_js_is_released_when_webview_dies():
    """Đúng dạng `EdgeChrome.evaluate_js`: Semaphore cục bộ không ai nhả."""
    watchdog, module, _calls = _installed()
    finished = threading.Event()

    def stuck_evaluate_js():
        semaphore = module.Semaphore(0)
        semaphore.acquire()
        finished.set()

    threading.Thread(target=stuck_evaluate_js, daemon=True).start()
    assert not finished.wait(0.1)

    _fire(module, "WFX Smart", "BrowserProcessExited")

    assert finished.wait(2)
    assert watchdog.dead.is_set()


def test_evaluate_js_after_death_does_not_wait_at_all():
    _watchdog, module, _calls = _installed()
    _fire(module, "WFX Smart", "BrowserProcessExited")

    started = time.monotonic()
    assert module.Semaphore(0).acquire() is False

    assert time.monotonic() - started < 0.1


def test_healthy_semaphore_still_waits_for_its_release():
    _watchdog, module, _calls = _installed()
    semaphore = module.Semaphore(0)
    threading.Timer(0.05, semaphore.release).start()

    assert semaphore.acquire() is True
    assert semaphore.acquire(blocking=False) is False
    assert semaphore.acquire(timeout=0.01) is False


# -- Giới hạn tự mở lại -------------------------------------------------------


def test_restart_budget_blocks_a_crash_loop(tmp_path):
    now = 10_000.0

    for offset in range(webview2_recovery.MAX_RESTARTS):
        assert webview2_recovery.claim_restart(tmp_path, now + offset) is True

    assert webview2_recovery.claim_restart(tmp_path, now + 10) is False


def test_restart_budget_recovers_after_the_window(tmp_path):
    now = 10_000.0
    for offset in range(webview2_recovery.MAX_RESTARTS):
        webview2_recovery.claim_restart(tmp_path, now + offset)

    later = now + webview2_recovery.RESTART_WINDOW_SECONDS + 10

    assert webview2_recovery.claim_restart(tmp_path, later) is True


def test_corrupt_restart_history_is_not_a_reason_to_stay_broken(tmp_path):
    (tmp_path / webview2_recovery.HISTORY_NAME).write_text("{oops", encoding="utf-8")

    assert webview2_recovery.claim_restart(tmp_path, 10_000.0) is True
    saved = json.loads(
        (tmp_path / webview2_recovery.HISTORY_NAME).read_text(encoding="utf-8")
    )
    assert saved == [10_000.0]


# -- Lệnh mở lại --------------------------------------------------------------


def test_packaged_relaunch_runs_the_exe_with_the_recovered_flag(monkeypatch):
    monkeypatch.setattr(webview2_recovery.sys, "frozen", True, raising=False)
    monkeypatch.setattr(webview2_recovery.sys, "executable", r"C:\App\WFX-Panel.exe")
    monkeypatch.setattr(webview2_recovery.sys, "argv", [r"C:\App\WFX-Panel.exe"])

    assert webview2_recovery.relaunch_command() == [
        r"C:\App\WFX-Panel.exe",
        webview2_recovery.RECOVERED_ARG,
    ]


def test_source_relaunch_keeps_the_script_and_does_not_stack_the_flag(monkeypatch):
    monkeypatch.delattr(webview2_recovery.sys, "frozen", raising=False)
    monkeypatch.setattr(webview2_recovery.sys, "executable", "python.exe")
    monkeypatch.setattr(
        webview2_recovery.sys,
        "argv",
        ["panel_app.py", webview2_recovery.RECOVERED_ARG],
    )

    assert webview2_recovery.relaunch_command() == [
        "python.exe",
        "panel_app.py",
        webview2_recovery.RECOVERED_ARG,
    ]


# -- Trình tự khôi phục -------------------------------------------------------


class _FakeApp:
    def __init__(self, tmp_path, *, running=()):
        self._quitting = False
        self._stop_status = threading.Event()
        self.base_dir = tmp_path
        self.notifications = []
        self.events = []
        self.running = list(running)
        self.api = types.SimpleNamespace(
            is_action_running=self._is_running,
            _base_dir=tmp_path,
        )

    def _is_running(self):
        return self.running.pop(0) if self.running else False

    def _notify_native(self, message, title):
        self.notifications.append((message, title))
        return True

    def release_for_exit(self, reason, close_browser=False):
        self.events.append(("release", reason, close_browser))


@pytest.fixture
def recovery(monkeypatch, tmp_path):
    spawned = []
    exits = []
    enqueued = []
    monkeypatch.setattr(
        webview2_recovery.subprocess,
        "Popen",
        lambda command, **kwargs: spawned.append((command, kwargs)),
    )
    monkeypatch.setattr(webview2_recovery.os, "_exit", exits.append)
    monkeypatch.setattr(
        webview2_recovery.telemetry,
        "enqueue",
        lambda _base, event: enqueued.append(event),
    )
    monkeypatch.setattr(webview2_recovery, "IDLE_POLL_SECONDS", 0.001)
    return types.SimpleNamespace(spawned=spawned, exits=exits, enqueued=enqueued)


INFO = {
    "kind": "BrowserProcessExited",
    "window": "WFX Smart Bubble",
    "reason": "Crashed",
    "exit_code": -1,
}


def test_recovery_releases_everything_then_relaunches_and_exits(recovery, tmp_path):
    app = _FakeApp(tmp_path)

    webview2_recovery.WebView2Recovery(app).handle(INFO)

    assert app.events == [("release", "webview2_restart", False)]
    assert len(recovery.spawned) == 1
    assert recovery.spawned[0][0][-1] == webview2_recovery.RECOVERED_ARG
    assert recovery.exits == [0]


def test_recovery_reports_the_failure_for_the_support_team(recovery, tmp_path):
    app = _FakeApp(tmp_path)

    webview2_recovery.WebView2Recovery(app).handle(INFO)

    (event,) = recovery.enqueued
    assert event["event_type"] == "automation_error"
    assert event["code"] == "WEBVIEW2_PROCESS_FAILED"
    assert event["method"] == "webview2_watchdog"
    assert event["error_detail"].startswith("BrowserProcessExited")


def test_recovery_never_cuts_a_running_flow(recovery, tmp_path):
    """Kill giữa Save/Create Transaction là mất trạng thái không idempotent."""
    app = _FakeApp(tmp_path, running=[True, True, True])

    webview2_recovery.WebView2Recovery(app).handle(INFO)

    assert app.running == []
    assert recovery.exits == [0]
    assert "tác vụ" in app.notifications[0][0]


def test_user_quitting_during_the_wait_cancels_the_restart(recovery, tmp_path):
    app = _FakeApp(tmp_path, running=[True] * 1000)
    app._stop_status.set()

    webview2_recovery.WebView2Recovery(app).handle(INFO)

    assert recovery.spawned == []
    assert recovery.exits == []


def test_failure_during_normal_quit_is_ignored(recovery, tmp_path):
    """Đóng app cũng làm WebView2 thoát; không được coi đó là sự cố."""
    app = _FakeApp(tmp_path)
    app._quitting = True

    webview2_recovery.WebView2Recovery(app).handle(INFO)

    assert recovery.spawned == []
    assert recovery.enqueued == []


def test_crash_loop_stops_restarting_and_tells_the_user(recovery, tmp_path):
    for offset in range(webview2_recovery.MAX_RESTARTS):
        webview2_recovery.claim_restart(tmp_path, time.time() + offset)
    app = _FakeApp(tmp_path)

    webview2_recovery.WebView2Recovery(app).handle(INFO)

    assert recovery.spawned == []
    assert recovery.exits == []
    assert app.events == []
    assert "Thoát" in app.notifications[-1][0]


def test_relaunch_failure_still_exits_instead_of_leaving_a_dead_ui(
    recovery, monkeypatch, tmp_path
):
    def broken(_command, **_kwargs):
        raise OSError("blocked")

    monkeypatch.setattr(webview2_recovery.subprocess, "Popen", broken)
    app = _FakeApp(tmp_path)

    webview2_recovery.WebView2Recovery(app).handle(INFO)

    assert recovery.exits == [1]
