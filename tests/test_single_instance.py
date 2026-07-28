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
