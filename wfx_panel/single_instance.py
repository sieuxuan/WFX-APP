"""Khoá một-instance cho WFX Panel.

App sống trong system tray và mở/ẩn bằng hotkey, nên người dùng rất dễ bấm lại
shortcut khi tưởng app đã tắt — nếu không chặn, sẽ có nhiều tiến trình cùng
giành hotkey Ctrl+Shift+X và cùng vẽ tray icon.

Dùng socket localhost thay vì file khoá: file khoá còn sót lại sau khi app bị
kill sẽ chặn nhầm lần mở kế tiếp, còn socket được HĐH thu hồi ngay khi tiến
trình chết. Socket đồng thời làm kênh IPC: lần mở thứ hai báo cho instance đang
chạy hiện panel lên rồi tự thoát, đúng với kỳ vọng "bấm lại thì thấy app".
"""

from __future__ import annotations

import os
import socket
import threading
from collections.abc import Callable

HOST = "127.0.0.1"
PORT = 49731
# Handshake để phân biệt instance của ta với một chương trình lạ tình cờ giữ
# cổng. Thiếu nó, mọi phần mềm chiếm cổng đều làm app từ chối khởi động.
TOKEN = b"WFX-PANEL-SINGLETON-1"
ACTIVATE = b"ACTIVATE"
WINDOWS_MUTEX_NAME = "Local\\WFX-Smart-SingleInstance-7F75C963"
ERROR_ALREADY_EXISTS = 183
LEGACY_WINDOW_TITLES = ("WFX Smart Bubble", "WFX Smart")


class SingleInstance:
    def __init__(
        self,
        on_activate: Callable[[], None],
        host: str = HOST,
        port: int = PORT,
        mutex_name: str = WINDOWS_MUTEX_NAME,
    ) -> None:
        self._on_activate = on_activate
        self._host = host
        self._port = port
        self._mutex_name = mutex_name
        self._mutex_handle: int | None = None
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def acquire(self) -> bool:
        """True nếu tiến trình này là instance chính."""
        has_windows_mutex = False
        if os.name == "nt":
            has_windows_mutex = self._acquire_windows_mutex()
            if not has_windows_mutex:
                return False

        server = socket.socket()
        # KHÔNG dùng SO_REUSEADDR: trên Windows nó cho phép hai tiến trình cùng
        # bind một cổng, đúng thứ ta cần ngăn.
        try:
            server.bind((self._host, self._port))
            server.listen(4)
        except OSError:
            server.close()
            # Named mutex mới là khoá độc quyền trên Windows. Socket chỉ là
            # kênh IPC để lần mở thứ hai yêu cầu instance cũ hiện panel.
            # Bản <=1.0.11 chưa có mutex, nên nếu handshake socket đúng WFX thì
            # phải nhường cho bản cũ và thả mutex vừa tạo.
            if has_windows_mutex and self.signal_existing():
                self._release_windows_mutex()
                return False
            return has_windows_mutex
        server.settimeout(0.5)
        self._server = server
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return True

    def _acquire_windows_mutex(self) -> bool:
        """Giữ named mutex tới khi app thoát; False nếu đã có WFX đang chạy."""
        if self._mutex_handle is not None:
            return True
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        create_mutex.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        ctypes.set_last_error(0)
        handle = create_mutex(None, False, self._mutex_name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            close_handle(handle)
            return False
        self._mutex_handle = int(handle)
        return True

    def _release_windows_mutex(self) -> None:
        handle, self._mutex_handle = self._mutex_handle, None
        if handle is None or os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

            close_handle = ctypes.WinDLL(
                "kernel32",
                use_last_error=True,
            ).CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL
            close_handle(wintypes.HANDLE(handle))
        except (AttributeError, OSError):
            pass

    def _serve(self) -> None:
        while not self._stop.is_set():
            server = self._server
            if server is None:
                return
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                try:
                    connection.settimeout(1)
                    if connection.recv(len(TOKEN)) != TOKEN:
                        continue
                    connection.sendall(TOKEN)
                    if connection.recv(len(ACTIVATE)) == ACTIVATE:
                        self._on_activate()
                except OSError:
                    continue

    def signal_existing(self) -> bool:
        """Yêu cầu instance đang chạy hiện panel. False nếu bên kia không phải ta."""
        try:
            with socket.create_connection((self._host, self._port), timeout=1) as client:
                client.settimeout(1)
                client.sendall(TOKEN)
                if client.recv(len(TOKEN)) != TOKEN:
                    return False
                client.sendall(ACTIVATE)
                return True
        except OSError:
            return self._activate_legacy_window()

    def _activate_legacy_window(self) -> bool:
        """Nhận diện bản cũ bị mất socket qua HWND và đưa nó lên trước."""
        if os.name != "nt" or self._port != PORT:
            return False
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            find_window = user32.FindWindowW
            find_window.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            find_window.restype = wintypes.HWND
            get_pid = user32.GetWindowThreadProcessId
            get_pid.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            get_pid.restype = wintypes.DWORD
            show_window = user32.ShowWindow
            show_window.argtypes = [wintypes.HWND, ctypes.c_int]
            show_window.restype = wintypes.BOOL
            set_foreground = user32.SetForegroundWindow
            set_foreground.argtypes = [wintypes.HWND]
            set_foreground.restype = wintypes.BOOL

            for title in LEGACY_WINDOW_TITLES:
                hwnd = find_window(None, title)
                if not hwnd:
                    continue
                pid = wintypes.DWORD()
                get_pid(hwnd, ctypes.byref(pid))
                if int(pid.value) in (0, os.getpid()):
                    continue
                show_window(hwnd, 9)  # SW_RESTORE
                set_foreground(hwnd)
                return True
        except (AttributeError, OSError):
            pass
        return False

    def close(self) -> None:
        self._stop.set()
        server, self._server = self._server, None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
        self._release_windows_mutex()
