import threading
import time

import pytest

from wfx_panel.automation import runtime


def test_production_runtime_releases_after_one_idle_minute():
    assert runtime.RUNTIME_IDLE_RELEASE_SECONDS == 60.0


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

    def connect_over_cdp(self, url):
        self.calls.append(url)
        return FakeBrowser()


def test_runtime_reuses_one_playwright_on_its_worker(monkeypatch):
    factory = FakeFactory()
    worker = runtime.AutomationRuntime()
    monkeypatch.setattr(runtime, "_sync_playwright", lambda: factory)
    try:
        first = worker.execute(lambda: worker.playwright_start())
        first.stop()
        second = worker.execute(lambda: worker.playwright_start())
        second.stop()

        assert first._playwright is second._playwright
        assert len(factory.instances) == 1
        assert factory.instances[0].stop_calls == 0
    finally:
        worker.shutdown()
    assert factory.instances[0].stop_calls == 1


def test_runtime_recycles_playwright_without_starting_parallel_driver(monkeypatch):
    factory = FakeFactory()
    worker = runtime.AutomationRuntime()
    monkeypatch.setattr(runtime, "_sync_playwright", lambda: factory)
    try:
        first = worker.execute(lambda: worker.playwright_start())
        second = worker.execute(lambda: worker.recycle_playwright(first))

        assert len(factory.instances) == 2
        assert first._playwright is factory.instances[0]
        assert second._playwright is factory.instances[1]
        assert factory.instances[0].stop_calls == 1
        assert factory.instances[1].stop_calls == 0
    finally:
        worker.shutdown()
    assert factory.instances[1].stop_calls == 1


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


def test_runtime_reuses_one_cdp_browser_connection():
    worker = runtime.AutomationRuntime()
    chromium = FakeChromium()
    playwright = type("FakePlaywrightClient", (), {"chromium": chromium})()
    try:
        first = worker.execute(
            lambda: worker.connect_browser(playwright, "http://127.0.0.1:9222")
        )
        second = worker.execute(
            lambda: worker.connect_browser(playwright, "http://127.0.0.1:9222")
        )
    finally:
        worker.shutdown()

    assert first is second
    assert chromium.calls == ["http://127.0.0.1:9222"]


def test_runtime_releases_playwright_after_idle_timeout(monkeypatch):
    factory = FakeFactory()
    worker = runtime.AutomationRuntime(idle_seconds=0.05)
    monkeypatch.setattr(runtime, "_sync_playwright", lambda: factory)
    try:
        worker.execute(lambda: worker.playwright_start())
        deadline = time.monotonic() + 1
        while factory.instances[0].stop_calls == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert factory.instances[0].stop_calls == 1
    finally:
        worker.shutdown()


def test_critical_section_defers_stop_until_next_checkpoint():
    worker = runtime.AutomationRuntime()
    worker._cancel.set()
    with worker.defer_cancellation():
        worker.checkpoint()
    with pytest.raises(runtime.AutomationCancelled):
        worker.checkpoint()
