from wfx_panel import win32_window


def test_logical_size_scales_to_physical_pixels_for_common_windows_dpi():
    assert win32_window._scale_logical_size(440, 620, 96) == (440, 620)
    assert win32_window._scale_logical_size(440, 620, 120) == (550, 775)
    assert win32_window._scale_logical_size(440, 620, 144) == (660, 930)
    assert win32_window._scale_logical_size(440, 620, 192) == (880, 1240)
    assert win32_window._scale_logical_size(440, 620, 0) == (440, 620)
    assert win32_window._unscale_physical_size(550, 775, 120) == (440, 620)
    assert win32_window._unscale_physical_size(660, 930, 144) == (440, 620)


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
