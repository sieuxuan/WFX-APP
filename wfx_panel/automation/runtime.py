"""Runtime tuần tự giữ một Playwright/CDP connection cho mọi flow WFX.

Playwright sync API có thread affinity. Worker riêng bảo đảm mọi object browser
được tạo và sử dụng trên cùng một thread, đồng thời cung cấp checkpoint hủy an
toàn cho các workflow dài.
"""

from __future__ import annotations

import os
import queue
import shutil
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from playwright.sync_api import Browser, Playwright
from playwright.sync_api import sync_playwright as _sync_playwright

T = TypeVar("T")
CDP_CONNECT_TIMEOUT_MS = 10_000
NATIVE_DOWNLOAD_TIMEOUT_SECONDS = 180


def _user_downloads_dir() -> Path:
    """Thư mục Downloads thật của người dùng, nơi Chrome vốn lưu file."""

    profile = os.getenv("USERPROFILE") or str(Path.home())
    return Path(profile) / "Downloads"


DownloadSnapshot = dict[Path, tuple[int, int]]


def snapshot_downloads() -> DownloadSnapshot:
    """Ghi nhận file hiện có để nhận đúng file Chrome vừa tải sau một click."""

    directory = _user_downloads_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return {}
    snapshot: DownloadSnapshot = {}
    try:
        files = list(directory.iterdir())
    except OSError:
        return snapshot
    for path in files:
        try:
            if path.is_file():
                stat = path.stat()
                snapshot[path] = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            continue
    return snapshot


def _matches_chrome_download_name(path: Path, suggested_name: str) -> bool:
    """Nhận cả tên gốc và hậu tố chống trùng ``(1)``, ``(2)`` của Chrome."""

    if path.name.casefold() == suggested_name.casefold():
        return True
    suggested = Path(suggested_name)
    name = path.name
    if suggested.suffix and not name.casefold().endswith(suggested.suffix.casefold()):
        return False
    without_suffix = name[: -len(suggested.suffix)] if suggested.suffix else name
    prefix = f"{suggested.stem} ("
    if not without_suffix.casefold().startswith(prefix.casefold()):
        return False
    number = without_suffix[len(prefix) :]
    return number.endswith(")") and number[:-1].isdigit()


def save_native_download(
    download: Any,
    target: str | Path,
    before: DownloadSnapshot | None = None,
) -> Path:
    """Sao chép file Chrome tải native tới nơi flow cần dùng.

    ``no_defaults=True`` giữ file gốc trong Downloads để nút Mở/Hiện trong thư
    mục của Chrome hoạt động. Những flow cần một đường dẫn riêng nhận bản sao,
    thay vì buộc Chrome tải vào thư mục artifact rồi xóa khi CDP ngắt.
    """

    claim_download(download)
    directory = _user_downloads_dir()
    suggested_name = str(download.suggested_filename or "").strip()
    deadline = time.monotonic() + NATIVE_DOWNLOAD_TIMEOUT_SECONDS
    stable: tuple[Path, tuple[int, int]] | None = None
    source: Path | None = None
    while time.monotonic() < deadline:
        try:
            files = list(directory.iterdir())
        except OSError as error:
            raise FileNotFoundError("Không đọc được thư mục Downloads.") from error
        candidates: list[tuple[int, Path, tuple[int, int]]] = []
        for path in files:
            try:
                if not path.is_file() or not _matches_chrome_download_name(
                    path, suggested_name
                ):
                    continue
                stat = path.stat()
                current = (stat.st_size, stat.st_mtime_ns)
                if before is not None and before.get(path) == current:
                    continue
                candidates.append((stat.st_mtime_ns, path, current))
            except OSError:
                continue
        if candidates:
            _, candidate, current = max(candidates, key=lambda item: item[0])
            if stable == (candidate, current):
                source = candidate
                break
            stable = (candidate, current)
        time.sleep(0.1)
    if source is None:
        raise FileNotFoundError(
            f"Không tìm thấy file Chrome vừa tải: {suggested_name or 'download'}."
        )
    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        same_file = source.resolve() == destination.resolve()
    except OSError:
        same_file = False
    if not same_file:
        shutil.copy2(source, destination)
    return destination


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
        # Kết nối CDP dùng no_defaults=True nên Chrome tự quản lý Downloads.
        # Ta vẫn theo dõi để log file người dùng tự tải và phân biệt với file
        # mà flow đã claim để xử lý tiếp.
        self._unclaimed_downloads: list[Any] = []
        self._tracked_contexts: set[int] = set()
        self.log_sink: Callable[[str], None] | None = None

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

    def _log(self, message: str) -> None:
        sink = self.log_sink
        if sink is None:
            return
        try:
            sink(message)
        except Exception:
            pass

    def _track_downloads(self, browser: Browser) -> None:
        for context in browser.contexts:
            key = id(context)
            if key in self._tracked_contexts:
                continue
            try:
                context.on("download", self._on_download)
            except Exception:
                continue
            self._tracked_contexts.add(key)

    def _on_download(self, download: Any) -> None:
        # Không bind thẳng list.append: hàm cứu phải xóa tại chỗ, còn nếu gán
        # list mới thì listener sẽ ghi vào list cũ đã tách rời và mất file.
        self._unclaimed_downloads.append(download)

    def claim_download(self, download: Any) -> None:
        """Flow báo download này là của nó, đừng cứu về Downloads."""
        for index, pending in enumerate(self._unclaimed_downloads):
            if pending is download:
                del self._unclaimed_downloads[index]
                return

    def _finish_unclaimed_downloads(self) -> None:
        """Ghi log download native; Chrome tự hoàn tất sau khi CDP đã nhả."""
        pending = list(self._unclaimed_downloads)
        self._unclaimed_downloads.clear()
        self._tracked_contexts.clear()
        directory = _user_downloads_dir()
        for download in pending:
            try:
                name = str(download.suggested_filename or "").strip()
                self._log(
                    "[DOWNLOAD] Chrome đã lưu file bạn tải về "
                    f"{directory / (name or 'wfx-download')}."
                )
            except Exception:
                continue

    def _release_connections(self) -> None:
        """Nhả driver sau mỗi flow; Chrome ngoài vẫn mở và giữ phiên đăng nhập."""
        # Không chờ Download.path(): ở native mode, Chrome có thể tiếp tục tải
        # bình thường sau khi CDP ngắt và Playwright không sở hữu artifact.
        try:
            self._finish_unclaimed_downloads()
        except Exception:
            pass
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
                no_defaults=True,
            )
        self.checkpoint()
        if self._browser is not None:
            try:
                if self._browser.is_connected():
                    self._track_downloads(self._browser)
                    return self._browser
            except Exception:
                pass
        self._browser = playwright.chromium.connect_over_cdp(
            cdp_url,
            timeout=CDP_CONNECT_TIMEOUT_MS,
            no_defaults=True,
        )
        self._track_downloads(self._browser)
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


def claim_download(download: Any) -> None:
    """Đánh dấu download thuộc về flow, không cứu về Downloads."""
    RUNTIME.claim_download(download)


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
