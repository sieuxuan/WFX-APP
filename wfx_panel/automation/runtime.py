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
CDP_CONNECT_TIMEOUT_MS = 10_000


class AutomationCancelled(BaseException):
    """Người dùng yêu cầu dừng tại một checkpoint an toàn.

    Kế thừa ``BaseException``, KHÔNG phải ``Exception``: mọi workflow automation
    đều kết thúc bằng ``except Exception as exc`` để đổi lỗi kỹ thuật thành mã
    nghiệp vụ. Nếu cancel là ``Exception``, những handler đó nuốt luôn yêu cầu
    Stop và trả về mã lỗi thật (``LOGIN_FAILED``, ``CATALOG_SEARCH_FAILED``,
    ``COSTING_APPLY_FAILED``…). Hệ quả: người dùng thấy lỗi giả, và vì các mã đó
    nằm ngoài ``NON_REPORTABLE_FAILURES`` nên telemetry gửi một lỗi không tồn
    tại ra webhook production. Với ``BaseException``, checkpoint xuyên qua các
    handler đó nhưng ``finally`` vẫn chạy, và ``PanelAPI._run_unlocked`` bắt
    riêng để trả đúng ``ACTION_CANCELLED``.
    """


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
    def __init__(self) -> None:
        self._queue: queue.Queue[_Task | None] = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._state_lock = threading.Lock()
        self._cancel = threading.Event()
        self._active = False
        self._defer_depth = 0
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._closed = False

    def _ensure_thread(self) -> None:
        """Bảo đảm có worker sống. Trả về sau khi thread đã được xếp hàng chạy.

        Chỉ coi thread là dùng được khi nó CHƯA nhận sentinel dừng. Một worker
        đang trên đường thoát vẫn báo ``is_alive()`` True trong khoảnh khắc giữa
        ``return`` và lúc thread thật sự kết thúc; nếu tin vào cờ đó, task kế
        tiếp sẽ nằm lại trong queue mãi mãi và ``execute()`` treo vô hạn.
        """
        with self._state_lock:
            alive = (
                self._thread is not None
                and self._thread.is_alive()
                and not self._closed
            )
            if alive:
                return
            self._closed = False
            self._thread = threading.Thread(
                target=self._worker,
                name="wfx-automation",
                daemon=True,
            )
            # Gán thread_id ngay tại thread tạo, không chờ worker tự set: nếu
            # worker cũ kết thúc SAU khi worker mới đã set id, dòng dọn dẹp của
            # nó sẽ xóa id của worker mới. Khi đó playwright_start() tưởng mình
            # đang chạy ngoài worker và tự mở driver riêng — runtime mất quyền
            # sở hữu lifecycle, driver không bao giờ được stop.
            self._thread_id = self._thread.ident
            self._thread.start()
            self._thread_id = self._thread.ident

    def _worker(self) -> None:
        my_id = threading.get_ident()
        self._thread_id = my_id
        try:
            while True:
                task = self._queue.get()
                if task is None:
                    with self._state_lock:
                        self._closed = True
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
                    # Nhả driver/CDP trước khi mở khóa caller. Nếu báo flow đã
                    # xong rồi mới cleanup, workflow kế tiếp có thể được xếp
                    # vào đúng lúc driver cũ còn detach và trông như không phản
                    # hồi. Result sink đã cập nhật UI ngay khi action kết thúc;
                    # caller chỉ được hoàn tất sau khi runtime thật sự sẵn sàng.
                    self._release_connections()
                    task.done.set()
        finally:
            self._release_connections()
            if self._thread_id == my_id:
                self._thread_id = None

    def _release_connections(self) -> None:
        """Nhả driver sau mỗi flow; Chrome ngoài vẫn mở và giữ phiên đăng nhập."""
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
        # Không dùng wait() vô hạn. Nếu worker nhận sentinel dừng ngay giữa
        # _ensure_thread() và put(), task này không còn ai chạy; UI thread sẽ
        # treo vĩnh viễn và app không đóng được. Chờ theo lát rồi hồi sinh
        # worker để task vẫn được thực thi đúng một lần.
        while not task.done.wait(0.25):
            thread = self._thread
            if thread is not None and thread.is_alive():
                continue
            if task.done.is_set():
                break
            self._ensure_thread()
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
            return playwright.chromium.connect_over_cdp(
                cdp_url,
                timeout=CDP_CONNECT_TIMEOUT_MS,
            )
        self.checkpoint()
        if self._browser is not None:
            try:
                if self._browser.is_connected():
                    return self._browser
            except Exception:
                pass
        self._browser = playwright.chromium.connect_over_cdp(
            cdp_url,
            timeout=CDP_CONNECT_TIMEOUT_MS,
        )
        return self._browser

    def invalidate_browser(self, browser: Browser | None = None) -> None:
        if browser is None or browser is self._browser:
            self._browser = None

    def recycle_playwright(
        self,
        playwright: Playwright | _PlaywrightLease,
    ) -> Playwright | _PlaywrightLease:
        """Tạo driver mới khi CDP cũ mất frame, không đóng Chrome ngoài."""
        if threading.get_ident() != self._thread_id:
            try:
                playwright.stop()
            except Exception:
                pass
            return _sync_playwright().start()
        self._release_connections()
        self.checkpoint()
        self._playwright = _sync_playwright().start()
        return _PlaywrightLease(self._playwright)

    def shutdown(self, timeout: float = 3.0) -> None:
        self.request_cancel()
        with self._state_lock:
            self._closed = True
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


def recycle_playwright(
    playwright: Playwright | _PlaywrightLease,
) -> Playwright | _PlaywrightLease:
    return RUNTIME.recycle_playwright(playwright)


def shutdown() -> None:
    RUNTIME.shutdown()


@contextmanager
def cancellation_deferred() -> Iterator[None]:
    with RUNTIME.defer_cancellation():
        yield
