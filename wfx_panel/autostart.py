"""Bật/tắt khởi động cùng Windows qua Run key của người dùng hiện tại."""

from __future__ import annotations

import os
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "WFXPanel"

_IS_WINDOWS = os.name == "nt"
if _IS_WINDOWS:
    import winreg


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpreter}" -m wfx_panel.panel_app'


def is_enabled(*, key_path: str = RUN_KEY, value_name: str = VALUE_NAME) -> bool:
    if not _IS_WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
        return bool(str(value).strip())
    except OSError:
        return False


def enable(
    command: str | None = None,
    *,
    key_path: str = RUN_KEY,
    value_name: str = VALUE_NAME,
) -> None:
    if not _IS_WINDOWS:
        return
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(
            key, value_name, 0, winreg.REG_SZ, command or launch_command()
        )


def disable(*, key_path: str = RUN_KEY, value_name: str = VALUE_NAME) -> None:
    if not _IS_WINDOWS:
        return
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, value_name)
    except OSError:
        pass


def sync(
    enabled: bool,
    *,
    key_path: str = RUN_KEY,
    value_name: str = VALUE_NAME,
) -> bool:
    """Đặt trạng thái rồi đọc lại, trả về trạng thái thật trong registry."""
    try:
        if enabled:
            enable(key_path=key_path, value_name=value_name)
        else:
            disable(key_path=key_path, value_name=value_name)
    except OSError:
        pass
    return is_enabled(key_path=key_path, value_name=value_name)
