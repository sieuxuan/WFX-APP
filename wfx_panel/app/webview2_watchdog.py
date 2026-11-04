"""Phát hiện WebView2 chết và gỡ các thread đang chờ nó.

pywebview 5.4 không đăng ký `CoreWebView2.ProcessFailed`. Khi browser process
của WebView2 chết, cửa sổ WinForms vẫn sống nên bubble thành một ô màu
`background_color` trống trơn, còn `evaluate_js` chờ mãi trên một `Semaphore`
cục bộ không ai nhả. Log, progress và kết quả đều gọi `evaluate_js` ngay trên
automation worker, nên flow đang chạy treo theo.

Module này thay hai thứ trong `webview.platforms.edgechromium`:

- `EdgeChrome.on_webview_ready`: đăng ký `ProcessFailed` cho từng cửa sổ và ghi
  lại lần khởi tạo thất bại vốn chỉ đi vào logger của pywebview.
- `Semaphore`: tên global mà `evaluate_js` dùng, nên subclass này gỡ được cả
  thread đang kẹt lẫn lời gọi về sau mà không phải sửa từng nơi gọi.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from wfx_panel import crash_log
from wfx_panel.win32_window import BUBBLE_WINDOW_TITLE, MAIN_WINDOW_TITLE

WAIT_SLICE_SECONDS = 0.25
BROWSER_EXITED = "BrowserProcessExited"
RENDER_EXITED = "RenderProcessExited"
# Menu và Manual là cửa sổ phụ: renderer của chúng chết không đáng restart cả
# app. Browser process thì dùng chung nên cửa sổ nào báo cũng là chết hết.
CORE_WINDOW_TITLES = frozenset({MAIN_WINDOW_TITLE, BUBBLE_WINDOW_TITLE})


def is_fatal(kind: str, window: str) -> bool:
    if kind == BROWSER_EXITED:
        return True
    return kind == RENDER_EXITED and window in CORE_WINDOW_TITLES


def _read(args: Any, name: str) -> str:
    """Thuộc tính .NET của event args có thể ném tùy loại lỗi."""
    try:
        return str(getattr(args, name))
    except Exception:
        return ""


def _watched_semaphore(base: type, dead: threading.Event) -> type:
    class WatchedSemaphore(base):  # type: ignore[misc, valid-type]
        def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
            if not blocking or timeout is not None:
                return super().acquire(blocking, timeout)
            while not dead.is_set():
                if super().acquire(True, WAIT_SLICE_SECONDS):
                    return True
            return super().acquire(False)

    return WatchedSemaphore


class WebView2Watchdog:
    def __init__(self, on_fatal: Callable[[dict], None]) -> None:
        self._on_fatal = on_fatal
        self._fatal_lock = threading.Lock()
        self.dead = threading.Event()

    def install(self, edgechromium: Any) -> bool:
        """Trả `False` nếu pywebview đổi cấu trúc; app vẫn chạy, chỉ mất watchdog."""
        edge_chrome = getattr(edgechromium, "EdgeChrome", None)
        original = getattr(edge_chrome, "on_webview_ready", None)
        semaphore = getattr(edgechromium, "Semaphore", None)
        if original is None or semaphore is None:
            return False
        watchdog = self

        def on_webview_ready(chrome: Any, sender: Any, args: Any) -> None:
            original(chrome, sender, args)
            window = str(getattr(chrome.pywebview_window, "title", ""))
            if not args.IsSuccess:
                crash_log.record(
                    "WEBVIEW2_INIT_FAILED",
                    window=window,
                    error=_read(args, "InitializationException"),
                )
                return
            sender.CoreWebView2.ProcessFailed += watchdog._handler(window)

        edge_chrome.on_webview_ready = on_webview_ready
        edgechromium.Semaphore = _watched_semaphore(semaphore, self.dead)
        return True

    def _handler(self, window: str) -> Callable[[Any, Any], None]:
        def on_process_failed(_sender: Any, args: Any) -> None:
            # Exception thoát khỏi đây sẽ rơi vào CLR trên UI thread.
            try:
                self._failed(
                    {
                        "kind": _read(args, "ProcessFailedKind"),
                        "window": window,
                        "reason": _read(args, "Reason"),
                        "exit_code": _read(args, "ExitCode"),
                        "description": _read(args, "ProcessDescription"),
                    }
                )
            except Exception as error:  # noqa: BLE001 - callback CLR
                crash_log.record(
                    "WEBVIEW2_WATCHDOG_ERROR", error=type(error).__name__
                )

        return on_process_failed

    def _failed(self, info: dict) -> None:
        crash_log.record("WEBVIEW2_PROCESS_FAILED", **info)
        if not is_fatal(info["kind"], info["window"]):
            return
        # Mọi cửa sổ đều báo cùng một lần browser exit; chỉ khôi phục một lần.
        with self._fatal_lock:
            if self.dead.is_set():
                return
            self.dead.set()
        # ProcessFailed chạy trên UI thread; khôi phục có thể chờ flow rất lâu.
        threading.Thread(
            target=self._on_fatal,
            args=(info,),
            name="wfx-webview2-recovery",
            daemon=True,
        ).start()
