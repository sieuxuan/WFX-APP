import threading
import time

import pytest

from wfx_panel.automation import runtime


def test_runtime_releases_connections_after_each_flow(monkeypatch):
    # Không giữ CDP attach giữa các flow: mỗi flow một driver riêng và bị nhả
    # ngay khi xong. Nhờ vậy tab người dùng tự mở trong Chrome không bị
    # auto-attach pause ("Debugger paused in another tab") hay treo khi đóng.
    factory = FakeFactory()
    worker = runtime.AutomationRuntime()
    monkeypatch.setattr(runtime, "_sync_playwright", lambda: factory)
    try:
        worker.execute(lambda: worker.playwright_start())
        worker.execute(lambda: worker.playwright_start())
        assert len(factory.instances) == 2
        assert factory.instances[0].stop_calls == 1
        assert factory.instances[1].stop_calls == 1
    finally:
        worker.shutdown()


class FakePlaywright:
    def __init__(self):
        self.chromium = object()
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


class FakeFactory:
    def __init__(self):
        self.instances = []

    def start(self):
        playwright = FakePlaywright()
        self.instances.append(playwright)
        return playwright


class FakeBrowser:
    def is_connected(self):
        return True


class FakeChromium:
    def __init__(self):
        self.calls = []

    def connect_over_cdp(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeBrowser()


def test_runtime_reuses_one_playwright_within_a_flow(monkeypatch):
    factory = FakeFactory()
    worker = runtime.AutomationRuntime()
    monkeypatch.setattr(runtime, "_sync_playwright", lambda: factory)
    try:
        def flow():
            return worker.playwright_start(), worker.playwright_start()

        first, second = worker.execute(flow)
        # Trong cùng một flow, các lease dùng chung một driver.
        assert first._playwright is second._playwright
        assert len(factory.instances) == 1
        # Nhả ngay khi flow xong: driver của flow bị stop.
        assert factory.instances[0].stop_calls == 1
    finally:
        worker.shutdown()


def test_runtime_recycles_playwright_within_a_flow(monkeypatch):
    factory = FakeFactory()
    worker = runtime.AutomationRuntime()
    monkeypatch.setattr(runtime, "_sync_playwright", lambda: factory)
    try:
        def flow():
            first = worker.playwright_start()
            second = worker.recycle_playwright(first)
            return first, second

        first, second = worker.execute(flow)
        # recycle giữa flow: stop driver cũ + start driver mới, không song song.
        assert len(factory.instances) == 2
        assert first._playwright is factory.instances[0]
        assert second._playwright is factory.instances[1]
        assert factory.instances[0].stop_calls == 1
        # Driver mới bị nhả khi flow kết thúc.
        assert factory.instances[1].stop_calls == 1
    finally:
        worker.shutdown()


def test_persistent_factory_keeps_sync_playwright_call_shape():
    assert runtime.sync_playwright() is runtime.sync_playwright


def test_runtime_stop_raises_only_at_checkpoint():
    worker = runtime.AutomationRuntime()
    entered = threading.Event()
    outcome = []

    def action():
        entered.set()
        while True:
            worker.checkpoint()
            time.sleep(0.01)

    def caller():
        try:
            worker.execute(action)
        except runtime.AutomationCancelled:
            outcome.append("cancelled")

    thread = threading.Thread(target=caller)
    thread.start()
    assert entered.wait(timeout=1)
    assert worker.request_cancel() is True
    thread.join(timeout=1)
    worker.shutdown()

    assert outcome == ["cancelled"]
    assert not thread.is_alive()


def test_runtime_reuses_one_cdp_browser_within_a_flow():
    worker = runtime.AutomationRuntime()
    chromium = FakeChromium()
    playwright = type("FakePlaywrightClient", (), {"chromium": chromium})()
    try:
        def flow():
            return (
                worker.connect_browser(playwright, "http://127.0.0.1:9222"),
                worker.connect_browser(playwright, "http://127.0.0.1:9222"),
            )

        first, second = worker.execute(flow)
    finally:
        worker.shutdown()

    # Trong cùng một flow chỉ connect_over_cdp một lần rồi dùng lại.
    assert first is second
    assert chromium.calls == [
        (
            "http://127.0.0.1:9222",
            {"timeout": runtime.CDP_CONNECT_TIMEOUT_MS},
        )
    ]


def test_cancellation_survives_workflow_except_exception_handlers():
    """Mọi workflow kết thúc bằng ``except Exception`` để đổi lỗi kỹ thuật thành
    mã nghiệp vụ. Stop không được bị các handler đó nuốt, nếu không người dùng
    thấy lỗi giả và telemetry gửi lỗi không tồn tại ra webhook production."""
    worker = runtime.AutomationRuntime()
    worker._cancel.set()
    finalised = []

    def workflow():
        try:
            worker.checkpoint()
            return {"code": "MODULE_OPENED"}
        except Exception as exc:  # noqa: BLE001 - đúng dạng handler trong automation
            return {"code": "MODULE_FAILED", "message": str(exc)}
        finally:
            finalised.append("playwright.stop")

    with pytest.raises(runtime.AutomationCancelled):
        workflow()
    # finally vẫn phải chạy để nhả Playwright/CDP lease.
    assert finalised == ["playwright.stop"]
    assert not issubclass(runtime.AutomationCancelled, Exception)


def test_execute_recovers_when_worker_stopped_before_task_ran():
    """shutdown() có thể tiêu thụ worker ngay giữa _ensure_thread() và put().
    Task đã xếp hàng vẫn phải chạy chứ không treo caller vĩnh viễn."""
    worker = runtime.AutomationRuntime()
    worker.execute(lambda: None)
    worker.shutdown()
    assert worker.execute(lambda: "ran-after-shutdown") == "ran-after-shutdown"
    worker.shutdown()


def test_critical_section_defers_stop_until_next_checkpoint():
    worker = runtime.AutomationRuntime()
    worker._cancel.set()
    with worker.defer_cancellation():
        worker.checkpoint()
    with pytest.raises(runtime.AutomationCancelled):
        worker.checkpoint()
