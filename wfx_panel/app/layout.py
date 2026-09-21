"""Kích thước cửa sổ, khoảng cách và nhịp poll của lớp vỏ desktop.

Tách khỏi ``panel_app`` để các controller trong ``wfx_panel/app`` dùng chung
mà không tạo vòng import ngược về orchestrator.
"""

from __future__ import annotations

from wfx_panel import prefs

TASKBAR_ACTIVATION_POLL_SECONDS = 0.25

PANEL_BLUR_GRACE_SECONDS = 0.35

BUBBLE_CONTEXT_POLL_SECONDS = 0.04

BUBBLE_DIRECT_ACTION_SUPPRESS_SECONDS = 0.75

WFX_MANUAL_URL = (
    "https://wfx.pro-sports.com.vn/wfx-digital-dictionary/system-manual"
)

BUBBLE_MENU_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "bubble_menu.html"

MANUAL_INDEX = prefs.RESOURCE_DIR / "wfx_panel" / "ui" / "manual.html"

MANUAL_WINDOW_TITLE = "WFX Smart · Hướng dẫn sử dụng"

MANUAL_WINDOW_WIDTH = 1000

MANUAL_WINDOW_HEIGHT = 720

MANUAL_WINDOW_MIN = (720, 520)

WINDOW_WIDTH = 440

WINDOW_HEIGHT = 620

WINDOW_MARGIN = 24

# Khôi phục đúng kích thước launcher cũ; bubble chỉ tách thành cửa sổ riêng.
BUBBLE_SIZE = 48

BUBBLE_PANEL_GAP = 10

BUBBLE_MENU_WIDTH = 184

BUBBLE_MENU_HEIGHT = 82

BUBBLE_MENU_GAP = 8
