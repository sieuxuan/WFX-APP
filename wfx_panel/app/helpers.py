"""Tiện ích nhỏ của lớp vỏ desktop: mở file đã tải và in qua WebView2."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import webview

from wfx_panel.app.layout import WINDOW_MARGIN, WINDOW_WIDTH


def _reveal_downloaded_file(value: object) -> bool:
    """Mở Explorer và chọn chính xác file vừa tải."""
    if os.name != "nt":
        return False
    try:
        target = Path(str(value or "")).resolve()
    except (OSError, ValueError):
        return False
    if not target.is_file():
        return False
    try:
        subprocess.Popen(["explorer.exe", "/select,", str(target)])
        return True
    except (OSError, ValueError):
        try:
            os.startfile(target.parent)  # type: ignore[attr-defined]
            return True
        except (OSError, ValueError):
            return False


def _open_downloaded_file(value: object) -> bool:
    """Mở file bằng ứng dụng mặc định của Windows."""
    if os.name != "nt":
        return False
    try:
        target = Path(str(value or "")).resolve()
        if not target.is_file():
            return False
        os.startfile(target)  # type: ignore[attr-defined]
        return True
    except (OSError, ValueError):
        return False


_EXCEL_FILE_SUFFIXES = frozenset({".xlsx", ".xls", ".xlsm", ".xlsb"})


def _is_excel_file(value: object) -> bool:
    try:
        return Path(str(value or "")).suffix.casefold() in _EXCEL_FILE_SUFFIXES
    except (OSError, ValueError):
        return False


def _safe_costing_file_stem(value: object) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(value or "").strip())
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return stem[:120].rstrip(" .") or "Costing"


def _dialog_selected_path(selected: object) -> Path:
    """Chuẩn hóa kết quả pywebview: Windows có thể trả str hoặc list[str]."""
    value = selected
    if not isinstance(selected, (str, Path)):
        try:
            value = selected[0]  # type: ignore[index]
        except (IndexError, KeyError, TypeError) as error:
            raise ValueError("File dialog không trả về đường dẫn.") from error
    return Path(str(value)).expanduser().resolve()


def _webview2_print_bindings():
    """Nạp kiểu .NET trễ, sau khi backend WebView2 đã khởi tạo."""
    from Microsoft.Web.WebView2.Core import CoreWebView2PrintDialogKind
    from System import Action

    return Action, CoreWebView2PrintDialogKind.System


def _show_webview2_print_dialog(window: object) -> bool:
    """Mở hộp thoại in hệ thống trên đúng luồng giao diện của WebView2."""
    try:
        native = window.native
        action_type, system_dialog = _webview2_print_bindings()
        opened = [False]

        def show_print_dialog() -> None:
            core = native.browser.webview.CoreWebView2
            if core is None:
                return
            core.ShowPrintUI(system_dialog)
            opened[0] = True

        native.Invoke(action_type(show_print_dialog))
        return opened[0]
    except Exception:
        return False


def _top_right_position() -> tuple[int, int]:
    """Tọa độ mở panel gần góc trên-phải màn hình chính.

    pywebview không nhận x/y sẽ tự canh giữa cửa sổ, sai với thiết kế (panel
    phải neo góc trên-phải). webview.screens chỉ khả dụng SAU khi GUI backend
    đã khởi tạo nên phải gọi hàm này bên trong run()/create_window(), không
    phải ở module scope; bọc try/except vì backend hoặc thuộc tính có thể
    thiếu tuỳ môi trường — không được để lỗi ở đây làm sập khởi động app.
    """
    try:
        screen = webview.screens[0]
        screen_width = int(screen.width)
    except Exception:
        screen_width = 1920
    x = max(WINDOW_MARGIN, screen_width - WINDOW_WIDTH - WINDOW_MARGIN)
    y = WINDOW_MARGIN
    return x, y
