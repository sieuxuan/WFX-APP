import socket
import threading
import time

import pytest

from wfx_panel.single_instance import SingleInstance


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def port() -> int:
    return _free_port()


def test_first_instance_acquires(port):
    first = SingleInstance(lambda: None, port=port)
    try:
        assert first.acquire() is True
    finally:
        first.close()


def test_second_instance_cannot_acquire(port):
    first = SingleInstance(lambda: None, port=port)
    second = SingleInstance(lambda: None, port=port)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        second.close()
        first.close()


def test_second_instance_activates_the_first(port):
    activated = threading.Event()
    first = SingleInstance(lambda: activated.set(), port=port)
    second = SingleInstance(lambda: None, port=port)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
        assert second.signal_existing() is True
        # Callback chạy trên listener thread của instance đầu.
        assert activated.wait(timeout=3) is True
    finally:
        second.close()
        first.close()


def test_port_held_by_a_foreign_process_does_not_block_startup(port):
    """Cổng bị chương trình khác chiếm KHÔNG được làm app từ chối khởi động.

    Nếu chỉ dựa vào 'bind thất bại = đã có instance', bất kỳ phần mềm nào tình
    cờ giữ cổng cũng khiến người dùng không mở được app và không hiểu vì sao.
    Handshake token phân biệt 'đúng instance của ta' với 'ai đó lạ'.
    """
    intruder = socket.socket()
    intruder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    intruder.bind(("127.0.0.1", port))
    intruder.listen(1)

    instance = SingleInstance(lambda: None, port=port)
    try:
        assert instance.acquire() is False
        # Không phải instance của ta -> không ack -> caller được phép chạy tiếp.
        assert instance.signal_existing() is False
    finally:
        instance.close()
        intruder.close()


def test_close_releases_port_for_a_later_instance(port):
    first = SingleInstance(lambda: None, port=port)
    assert first.acquire() is True
    first.close()
    time.sleep(0.05)

    second = SingleInstance(lambda: None, port=port)
    try:
        assert second.acquire() is True
    finally:
        second.close()
