from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# RESOURCE_DIR: nơi chứa asset chỉ-đọc được đóng gói cùng ứng dụng (ui/, assets/).
# Khi build bằng PyInstaller (frozen), __file__ nằm trong dist/WFX-Panel/_internal/,
# đây vẫn là vị trí ĐÚNG để tìm index.html/wfx.ico — không được đổi biến này.
RESOURCE_DIR = Path(__file__).resolve().parent.parent

# APP_DIR: alias tương thích ngược cho code cũ còn import prefs.APP_DIR mong đợi
# thư mục tài nguyên (KHÔNG phải nơi ghi dữ liệu người dùng).
APP_DIR = RESOURCE_DIR

DEFAULT_HOTKEY_LABEL = "Ctrl + Shift + X"


def _resolve_data_dir() -> Path:
    """Nơi đọc/ghi dữ liệu người dùng (.env, prefs.json).

    Ở bản build đóng gói (frozen), RESOURCE_DIR nằm trong thư mục dist của ứng
    dụng — ghi .env (mật khẩu plaintext) vào đó nghĩa là: (1) rebuild/ghi đè
    thư mục dist sẽ xoá sạch tài khoản đã lưu, (2) zip thư mục dist để chia sẻ
    app vô tình phát tán luôn mật khẩu người dùng. Vì vậy khi frozen, dữ liệu
    phải đi vào %LOCALAPPDATA%/WFX-Panel, tách khỏi thư mục cài đặt.
    """
    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        data_dir = base / "WFX-Panel"
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return data_dir
    return RESOURCE_DIR


DATA_DIR = _resolve_data_dir()


def _env_path(base_dir: Path) -> Path:
    return Path(base_dir) / ".env"


def _prefs_path(base_dir: Path) -> Path:
    return Path(base_dir) / "prefs.json"


def load_account(base_dir: Path | None = None) -> dict:
    base_dir = DATA_DIR if base_dir is None else base_dir
    path = _env_path(base_dir)
    values: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            try:
                values[key.strip()] = json.loads(value) if value.startswith('"') else value
            except json.JSONDecodeError:
                values[key.strip()] = value.strip('"')
    return {
        "user_id": values.get("WFX_USER_ID", ""),
        "password": values.get("WFX_PASSWORD", ""),
    }


def save_account(user_id: str, password: str, base_dir: Path | None = None) -> None:
    base_dir = DATA_DIR if base_dir is None else base_dir
    content = (
        f"WFX_USER_ID={json.dumps(user_id, ensure_ascii=False)}\n"
        f"WFX_PASSWORD={json.dumps(password, ensure_ascii=False)}\n"
    )
    path = _env_path(base_dir)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)
    os.environ["WFX_USER_ID"] = user_id
    os.environ["WFX_PASSWORD"] = password


def load_prefs(base_dir: Path | None = None) -> dict:
    base_dir = DATA_DIR if base_dir is None else base_dir
    path = _prefs_path(base_dir)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    return {
        "theme": "dark" if data.get("theme") == "dark" else "light",
        "close_after_module": data.get("close_after_module", True) is not False,
        "hotkey_label": str(data.get("hotkey_label") or DEFAULT_HOTKEY_LABEL),
    }


def save_prefs(
    base_dir: Path | None = None,
    *,
    theme: str | None = None,
    close_after_module: bool | None = None,
    hotkey_label: str | None = None,
) -> dict:
    base_dir = DATA_DIR if base_dir is None else base_dir
    current = load_prefs(base_dir)
    if theme is not None:
        current["theme"] = "dark" if theme == "dark" else "light"
    if close_after_module is not None:
        current["close_after_module"] = bool(close_after_module)
    if hotkey_label is not None:
        current["hotkey_label"] = str(hotkey_label)
    path = _prefs_path(base_dir)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return current
