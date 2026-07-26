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

import socket
import threading
from typing import Callable

HOST = "127.0.0.1"
PORT = 49731
# Handshake để phân biệt instance của ta với một chương trình lạ tình cờ giữ
# cổng. Thiếu nó, mọi phần mềm chiếm cổng đều làm app từ chối khởi động.
TOKEN = b"WFX-PANEL-SINGLETON-1"
ACTIVATE = b"ACTIVATE"


class SingleInstance:
    def __init__(
        self,
        on_activate: Callable[[], None],
        host: str = HOST,
        port: int = PORT,
    ) -> None:
        self._on_activate = on_activate
        self._host = host
        self._port = port
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def acquire(self) -> bool:
        """True nếu tiến trình này là instance chính."""
        server = socket.socket()
        # KHÔNG dùng SO_REUSEADDR: trên Windows nó cho phép hai tiến trình cùng
        # bind một cổng, đúng thứ ta cần ngăn.
        try:
            server.bind((self._host, self._port))
            server.listen(4)
        except OSError:
            server.close()
            return False
        server.settimeout(0.5)
        self._server = server
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return True

    def _serve(self) -> None:
        while not self._stop.is_set():
            server = self._server
            if server is None:
                return
            try:
                connection, _ = server.accept()
            except socket.timeout:
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
