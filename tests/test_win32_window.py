from wfx_panel import win32_window


def test_clamp_keeps_rect_inside_work_area():
    area = (0, 0, 1920, 1080)
    # Tràn phải-dưới → đẩy vào trong.
    assert win32_window._clamp_to_work_area(1900, 1060, 440, 620, area) == (1480, 460)
    # Tràn trái-trên → kéo về (0, 0).
    assert win32_window._clamp_to_work_area(-50, -50, 440, 620, area) == (0, 0)
    # Đã nằm gọn → giữ nguyên.
    assert win32_window._clamp_to_work_area(100, 100, 440, 620, area) == (100, 100)
    # Không xác định màn hình → không đoán bừa.
    assert win32_window._clamp_to_work_area(100, 100, 440, 620, None) == (100, 100)


def test_clamp_anchors_top_left_when_window_bigger_than_work_area():
    area = (0, 0, 800, 600)
    assert win32_window._clamp_to_work_area(300, 300, 1000, 900, area) == (0, 0)


def test_snap_moves_icon_to_nearest_edge_only_on_that_axis():
    area = (0, 0, 1920, 1080)
    margin = win32_window.COMPACT_EDGE_MARGIN
    size = 48
    # Gần mép trái nhất → dính trái, giữ nguyên y.
    assert win32_window._snap_to_nearest_edge(30, 400, size, size, area) == (
        margin,
        400,
    )
    # Gần mép phải nhất → dính phải, giữ nguyên y.
    assert win32_window._snap_to_nearest_edge(1800, 400, size, size, area) == (
        1920 - size - margin,
        400,
    )
    # Gần mép dưới nhất → dính dưới, giữ nguyên x.
    assert win32_window._snap_to_nearest_edge(900, 1000, size, size, area) == (
        900,
        1080 - size - margin,
    )


def test_focus_does_not_restore_a_non_minimized_window():
    class FakeUser32:
        calls = []

        @staticmethod
        def IsIconic(_hwnd):
            return False

        @classmethod
        def ShowWindow(cls, hwnd, command):
            cls.calls.append((hwnd, command))

    win32_window._restore_window_only_if_minimized(FakeUser32(), 123)
    assert FakeUser32.calls == []


def test_focus_restores_a_minimized_window_only():
    class FakeUser32:
        calls = []

        @staticmethod
        def IsIconic(_hwnd):
            return True

        @classmethod
        def ShowWindow(cls, hwnd, command):
            cls.calls.append((hwnd, command))

    win32_window._restore_window_only_if_minimized(FakeUser32(), 123)
    assert FakeUser32.calls == [(123, 9)]
