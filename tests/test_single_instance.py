import os
import socket
import threading
import time
import uuid

import pytest

from wfx_panel.single_instance import SingleInstance


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def port() -> int:
    return _free_port()


@pytest.fixture
def mutex_name() -> str:
    return f"Local\\WFX-Smart-Test-{uuid.uuid4()}"


def test_first_instance_acquires(port, mutex_name):
    first = SingleInstance(lambda: None, port=port, mutex_name=mutex_name)
    try:
        assert first.acquire() is True
    finally:
        first.close()


def test_second_instance_cannot_acquire(port, mutex_name):
    first = SingleInstance(lambda: None, port=port, mutex_name=mutex_name)
    second = SingleInstance(lambda: None, port=port, mutex_name=mutex_name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        second.close()
        first.close()


def test_second_instance_activates_the_first(port, mutex_name):
    activated = threading.Event()
    first = SingleInstance(
        lambda: activated.set(),
        port=port,
        mutex_name=mutex_name,
    )
    second = SingleInstance(lambda: None, port=port, mutex_name=mutex_name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
        assert second.signal_existing() is True
        # Callback chạy trên listener thread của instance đầu.
        assert activated.wait(timeout=3) is True
    finally:
        second.close()
        first.close()


def test_new_mutex_instance_yields_to_legacy_socket_instance(port):
    """1.0.12 không chạy chồng khi bản cũ chỉ giữ socket đang còn mở."""
    activated = threading.Event()
    legacy = SingleInstance(
        lambda: activated.set(),
        port=port,
        mutex_name=f"Local\\WFX-Legacy-Test-{uuid.uuid4()}",
    )
    new_mutex_name = f"Local\\WFX-New-Test-{uuid.uuid4()}"
    current = SingleInstance(
        lambda: None,
        port=port,
        mutex_name=new_mutex_name,
    )
    try:
        assert legacy.acquire() is True
        assert current.acquire() is False
        assert activated.wait(timeout=3) is True

        # acquire() thất bại phải thả mutex mới tạo, không để khoá mồ côi.
        probe = SingleInstance(
            lambda: None,
            port=_free_port(),
            mutex_name=new_mutex_name,
        )
        try:
            assert probe.acquire() is True
        finally:
            probe.close()
    finally:
        current.close()
        legacy.close()


def test_windows_mutex_still_allows_one_app_if_ipc_port_is_busy(
    port,
    mutex_name,
):
    """Trên Windows, cổng IPC bận không được làm mất khoá single-instance."""
    intruder = socket.socket()
    intruder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    intruder.bind(("127.0.0.1", port))
    intruder.listen(1)

    instance = SingleInstance(
        lambda: None,
        port=port,
        mutex_name=mutex_name,
    )
    try:
        assert instance.acquire() is (os.name == "nt")
        if os.name != "nt":
            assert instance.signal_existing() is False
    finally:
        instance.close()
        intruder.close()


def test_close_releases_port_for_a_later_instance(port, mutex_name):
    first = SingleInstance(lambda: None, port=port, mutex_name=mutex_name)
    assert first.acquire() is True
    first.close()
    time.sleep(0.05)

    second = SingleInstance(lambda: None, port=port, mutex_name=mutex_name)
    try:
        assert second.acquire() is True
    finally:
        second.close()


def _handshake(port: int, payload: bytes | None) -> bytes:
    """Nói chuyện thô với server IPC để test đúng nhánh handshake."""
    with socket.create_connection(("127.0.0.1", port), timeout=1) as client:
        client.settimeout(1)
        if payload is not None:
            client.sendall(payload)
        try:
            return client.recv(64)
        except OSError:
            return b""


def test_server_rejects_a_stranger_that_grabbed_the_port(port, mutex_name):
    activations: list[int] = []
    instance = SingleInstance(
        lambda: activations.append(1), port=port, mutex_name=mutex_name
    )
    assert instance.acquire() is True
    try:
        assert _handshake(port, b"NOT-OUR-TOKEN-XXXXXXX") == b""
        time.sleep(0.05)
        assert activations == []
    finally:
        instance.close()


def test_handshake_without_activate_does_not_show_the_panel(port, mutex_name):
    activations: list[int] = []
    instance = SingleInstance(
        lambda: activations.append(1), port=port, mutex_name=mutex_name
    )
    assert instance.acquire() is True
    try:
        from wfx_panel.single_instance import TOKEN

        assert _handshake(port, TOKEN) == TOKEN
        time.sleep(0.05)
        assert activations == []
    finally:
        instance.close()


def test_a_failing_on_activate_never_kills_the_accept_thread(port, mutex_name):
    calls: list[int] = []

    def broken() -> None:
        calls.append(1)
        raise RuntimeError("Win32 lỗi")

    instance = SingleInstance(broken, port=port, mutex_name=mutex_name)
    assert instance.acquire() is True
    try:
        second = SingleInstance(lambda: None, port=port, mutex_name=mutex_name)
        assert second.signal_existing() is True
        time.sleep(0.1)
        # Lần thứ hai chỉ chạy được nếu thread accept còn sống.
        assert second.signal_existing() is True
        time.sleep(0.1)
        assert len(calls) == 2
    finally:
        instance.close()


def test_signal_existing_is_false_when_nobody_is_listening(port):
    lonely = SingleInstance(lambda: None, port=port)

    assert lonely.signal_existing() is False


def test_acquiring_twice_reuses_the_same_mutex_handle(port, mutex_name):
    instance = SingleInstance(lambda: None, port=port, mutex_name=mutex_name)
    if os.name != "nt":
        pytest.skip("named mutex chỉ có trên Windows")
    try:
        assert instance._acquire_windows_mutex() is True
        handle = instance._mutex_handle
        assert instance._acquire_windows_mutex() is True
        assert instance._mutex_handle == handle
    finally:
        instance.close()


def test_releasing_a_mutex_that_was_never_taken_is_a_no_op():
    instance = SingleInstance(lambda: None)

    instance._release_windows_mutex()  # không raise

    assert instance._mutex_handle is None


def test_close_is_idempotent(port, mutex_name):
    instance = SingleInstance(lambda: None, port=port, mutex_name=mutex_name)
    assert instance.acquire() is True

    instance.close()
    instance.close()  # không raise

    assert instance._server is None
    assert instance._mutex_handle is None


def test_legacy_window_activation_is_skipped_on_a_custom_port(port):
    instance = SingleInstance(lambda: None, port=port)

    assert instance._activate_legacy_window() is False


class _FakeUser32:
    """user32 giả cho nhánh đánh thức bản cũ qua HWND."""

    def __init__(self, *, hwnd: int, pid: int) -> None:
        self._hwnd = hwnd
        self._pid = pid
        self.restored: list[tuple[int, int]] = []
        self.foreground: list[int] = []

    class _Stub:
        def __init__(self, call):
            self._call = call
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self._call(*args)

    def __getattr__(self, name):

        if name == "FindWindowW":
            return self._Stub(lambda _cls, title: self._hwnd if title else 0)
        if name == "GetWindowThreadProcessId":
            def _pid(_hwnd, pointer):
                pointer._obj.value = self._pid
                return 1

            return self._Stub(_pid)
        if name == "ShowWindow":
            return self._Stub(
                lambda hwnd, cmd: self.restored.append((hwnd, cmd)) or 1
            )
        if name == "SetForegroundWindow":
            return self._Stub(lambda hwnd: self.foreground.append(hwnd) or 1)
        raise AttributeError(name)


def test_legacy_window_activation_restores_and_fronts_another_process(
    monkeypatch,
):
    import ctypes

    if os.name != "nt":
        pytest.skip("HWND chỉ có trên Windows")
    user32 = _FakeUser32(hwnd=4242, pid=os.getpid() + 1)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_a, **_kw: user32)
    instance = SingleInstance(lambda: None)

    assert instance._activate_legacy_window() is True
    assert user32.restored == [(4242, 9)]
    assert user32.foreground == [4242]


def test_legacy_window_activation_ignores_a_window_of_this_process(monkeypatch):
    import ctypes

    if os.name != "nt":
        pytest.skip("HWND chỉ có trên Windows")
    user32 = _FakeUser32(hwnd=99, pid=os.getpid())
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_a, **_kw: user32)
    instance = SingleInstance(lambda: None)

    assert instance._activate_legacy_window() is False
    assert user32.foreground == []


def test_legacy_window_activation_swallows_a_win32_failure(monkeypatch):
    import ctypes

    if os.name != "nt":
        pytest.skip("HWND chỉ có trên Windows")

    def boom(*_args, **_kwargs):
        raise OSError("user32 không nạp được")

    monkeypatch.setattr(ctypes, "WinDLL", boom)
    instance = SingleInstance(lambda: None)

    assert instance._activate_legacy_window() is False
