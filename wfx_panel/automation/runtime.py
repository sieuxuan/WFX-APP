"""Runtime tuần tự giữ một Playwright/CDP connection cho mọi flow WFX.

Playwright sync API có thread affinity. Worker riêng bảo đảm mọi object browser
được tạo và sử dụng trên cùng một thread, đồng thời cung cấp checkpoint hủy an
toàn cho các workflow dài.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

from playwright.sync_api import Browser, Playwright
from playwright.sync_api import sync_playwright as _sync_playwright

T = TypeVar("T")
RUNTIME_IDLE_RELEASE_SECONDS = 60.0


class AutomationCancelled(RuntimeError):
    """Người dùng yêu cầu dừng tại một checkpoint an toàn."""


@dataclass
class _Task:
    action: Callable[[], Any]
    done: threading.Event
    result: Any = None
    error: BaseException | None = None


class _PlaywrightLease:
    """Giữ tương thích với code cũ gọi ``playwright.stop()`` mỗi flow."""

    def __init__(self, playwright: Playwright):
        self._playwright = playwright

    def __getattr__(self, name: str) -> Any:
        return getattr(self._playwright, name)

    def stop(self) -> None:
        # Runtime sở hữu lifecycle; flow chỉ mượn connection.
        return None


class AutomationRuntime:
    def __init__(
        self,
        idle_seconds: float = RUNTIME_IDLE_RELEASE_SECONDS,
    ) -> None:
        self._queue: queue.Queue[_Task | None] = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._state_lock = threading.Lock()
        self._cancel = threading.Event()
        self._active = False
        self._defer_depth = 0
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._idle_seconds = max(0.01, float(idle_seconds))

    def _ensure_thread(self) -> None:
        with self._state_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._worker,
                name="wfx-automation",
                daemon=True,
            )
            self._thread.start()

    def _worker(self) -> None:
        self._thread_id = threading.get_ident()
        try:
            while True:
                try:
                    task = self._queue.get(timeout=self._idle_seconds)
                except queue.Empty:
                    self._release_connections()
                    continue
                if task is None:
                    return
                self._cancel.clear()
                self._defer_depth = 0
                with self._state_lock:
                    self._active = True
                try:
                    task.result = task.action()
                except BaseException as error:
                    task.error = error
                finally:
                    with self._state_lock:
                        self._active = False
                    self._cancel.clear()
                    task.done.set()
        finally:
            self._release_connections()
            self._thread_id = None

    def _release_connections(self) -> None:
        """Nhả driver lúc idle; Chrome ngoài vẫn mở và giữ phiên đăng nhập."""
        self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def execute(self, action: Callable[[], T]) -> T:
        if threading.get_ident() == self._thread_id:
            return action()
        self._ensure_thread()
        task = _Task(action=action, done=threading.Event())
        self._queue.put(task)
        task.done.wait()
        if task.error is not None:
            raise task.error
        return task.result

    def request_cancel(self) -> bool:
        with self._state_lock:
            active = self._active
        if active:
            self._cancel.set()
        return active

    def checkpoint(self) -> None:
        if self._cancel.is_set() and self._defer_depth <= 0:
            raise AutomationCancelled("ACTION_CANCELLED")

    @contextmanager
    def defer_cancellation(self) -> Iterator[None]:
        """Hoãn Stop trong đoạn không được ngắt, ví dụ click/chờ Save."""
        self._defer_depth += 1
        try:
            yield
        finally:
            self._defer_depth = max(0, self._defer_depth - 1)

    def playwright_start(self) -> Playwright | _PlaywrightLease:
        # Các helper được gọi độc lập ngoài PanelAPI (CLI/test) vẫn giữ lifecycle
        # cũ. Chỉ worker production dùng connection bền vững.
        if threading.get_ident() != self._thread_id:
            return _sync_playwright().start()
        self.checkpoint()
        if self._playwright is None:
            self._playwright = _sync_playwright().start()
        return _PlaywrightLease(self._playwright)

    def connect_browser(self, playwright: Any, cdp_url: str) -> Browser:
        if threading.get_ident() != self._thread_id:
            return playwright.chromium.connect_over_cdp(cdp_url)
        self.checkpoint()
        if self._browser is not None:
            try:
                if self._browser.is_connected():
                    return self._browser
            except Exception:
                pass
        self._browser = playwright.chromium.connect_over_cdp(cdp_url)
        return self._browser

    def invalidate_browser(self, browser: Browser | None = None) -> None:
        if browser is None or browser is self._browser:
            self._browser = None

    def shutdown(self, timeout: float = 3.0) -> None:
        self.request_cancel()
        thread = self._thread
        if thread is None or not thread.is_alive():
            return
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            # Task hiện tại sẽ thấy cờ cancel; caller có thể gọi shutdown lại.
            return
        thread.join(timeout=timeout)


RUNTIME = AutomationRuntime()


class _PersistentPlaywrightFactory:
    def __call__(self) -> _PersistentPlaywrightFactory:
        return self

    def start(self) -> Playwright | _PlaywrightLease:
        return RUNTIME.playwright_start()


sync_playwright = _PersistentPlaywrightFactory()


def run(action: Callable[[], T]) -> T:
    return RUNTIME.execute(action)


def request_cancel() -> bool:
    return RUNTIME.request_cancel()


def checkpoint() -> None:
    RUNTIME.checkpoint()


def connect_browser(playwright: Any, cdp_url: str) -> Browser:
    return RUNTIME.connect_browser(playwright, cdp_url)


def invalidate_browser(browser: Browser | None = None) -> None:
    RUNTIME.invalidate_browser(browser)


def shutdown() -> None:
    RUNTIME.shutdown()


@contextmanager
def cancellation_deferred() -> Iterator[None]:
    with RUNTIME.defer_cancellation():
        yield
