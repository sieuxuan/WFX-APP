from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from wfx_panel import hotkey as hotkey_spec

# RESOURCE_DIR: nơi chứa asset chỉ-đọc được đóng gói cùng ứng dụng (ui/, assets/).
# Khi build bằng PyInstaller (frozen), __file__ nằm trong dist/WFX-Panel/_internal/,
# đây vẫn là vị trí ĐÚNG để tìm index.html/wfx.ico — không được đổi biến này.
RESOURCE_DIR = Path(__file__).resolve().parent.parent

# APP_DIR: alias tương thích ngược cho code cũ còn import prefs.APP_DIR mong đợi
# thư mục tài nguyên (KHÔNG phải nơi ghi dữ liệu người dùng).
APP_DIR = RESOURCE_DIR


def _legacy_data_candidates() -> list[Path]:
    executable_dir = Path(sys.executable).resolve().parent
    candidates = [
        executable_dir,
        RESOURCE_DIR,
    ]
    # Layout dev/build: <repo>/dist/WFX-Panel/WFX-Panel.exe.
    if len(executable_dir.parents) >= 2:
        candidates.append(executable_dir.parents[1])
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _migrate_legacy_files(
    data_dir: Path,
    candidates: list[Path] | None = None,
) -> None:
    """Sao chép settings cũ một lần; không bao giờ ghi đè bản LOCALAPPDATA."""
    for filename in (".env", "prefs.json"):
        target = data_dir / filename
        if target.exists():
            continue
        for candidate in candidates or _legacy_data_candidates():
            source = Path(candidate) / filename
            if source.is_file() and source.resolve() != target.resolve():
                try:
                    shutil.copy2(source, target)
                except OSError:
                    pass
                break


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
            _migrate_legacy_files(data_dir)
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
    path = _env_path(base_dir)
    webhook_line = ""
    if path.is_file():
        try:
            webhook_line = next(
                (
                    line
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip().startswith("WFX_ERROR_WEBHOOK_URL=")
                ),
                "",
            )
        except OSError:
            webhook_line = ""
    content = (
        f"WFX_USER_ID={json.dumps(user_id, ensure_ascii=False)}\n"
        f"WFX_PASSWORD={json.dumps(password, ensure_ascii=False)}\n"
        f"{webhook_line + chr(10) if webhook_line else ''}"
    )
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
    stored_hotkey = str(data.get("hotkey") or hotkey_spec.DEFAULT)
    if not hotkey_spec.is_valid(stored_hotkey):
        stored_hotkey = hotkey_spec.DEFAULT
    else:
        stored_hotkey = hotkey_spec.normalize(stored_hotkey)
    compact_offset_x = data.get("compact_offset_x")
    compact_offset_y = data.get("compact_offset_y")
    if isinstance(compact_offset_x, bool) or not isinstance(compact_offset_x, int):
        compact_offset_x = None
    if isinstance(compact_offset_y, bool) or not isinstance(compact_offset_y, int):
        compact_offset_y = None
    return {
        "theme": "dark" if data.get("theme") == "dark" else "light",
        "close_after_module": data.get("close_after_module", True) is not False,
        "hotkey": stored_hotkey,
        "hotkey_label": hotkey_spec.format_label(stored_hotkey),
        "autostart": data.get("autostart", False) is True,
        "start_hidden": data.get("start_hidden", False) is True,
        "toast_enabled": data.get("toast_enabled", True) is not False,
        "always_on_top": data.get("always_on_top", True) is not False,
        "stick_to_browser": data.get("stick_to_browser", True) is True,
        "admin_mode": data.get("admin_mode", False) is True,
        "update_channel": (
            "current"
            if data.get("update_channel") == "current"
            else "stable"
        ),
        "last_update_notice": str(data.get("last_update_notice") or ""),
        "compact_offset_x": compact_offset_x,
        "compact_offset_y": compact_offset_y,
    }


def save_prefs(
    base_dir: Path | None = None,
    *,
    theme: str | None = None,
    close_after_module: bool | None = None,
    hotkey_label: str | None = None,
    hotkey: str | None = None,
    autostart: bool | None = None,
    start_hidden: bool | None = None,
    toast_enabled: bool | None = None,
    always_on_top: bool | None = None,
    stick_to_browser: bool | None = None,
    admin_mode: bool | None = None,
    update_channel: str | None = None,
    last_update_notice: str | None = None,
    compact_offset_x: int | None = None,
    compact_offset_y: int | None = None,
) -> dict:
    base_dir = DATA_DIR if base_dir is None else base_dir
    current = load_prefs(base_dir)
    if theme is not None:
        current["theme"] = "dark" if theme == "dark" else "light"
    if close_after_module is not None:
        current["close_after_module"] = bool(close_after_module)
    if hotkey is not None:
        current["hotkey"] = hotkey_spec.normalize(hotkey)
        current["hotkey_label"] = hotkey_spec.format_label(current["hotkey"])
    if autostart is not None:
        current["autostart"] = bool(autostart)
    if start_hidden is not None:
        current["start_hidden"] = bool(start_hidden)
    if toast_enabled is not None:
        current["toast_enabled"] = bool(toast_enabled)
    if always_on_top is not None:
        current["always_on_top"] = bool(always_on_top)
    if stick_to_browser is not None:
        current["stick_to_browser"] = bool(stick_to_browser)
    if admin_mode is not None:
        current["admin_mode"] = bool(admin_mode)
    if update_channel is not None:
        current["update_channel"] = (
            "current" if update_channel == "current" else "stable"
        )
    if last_update_notice is not None:
        current["last_update_notice"] = str(last_update_notice)
    if compact_offset_x is not None:
        current["compact_offset_x"] = int(compact_offset_x)
    if compact_offset_y is not None:
        current["compact_offset_y"] = int(compact_offset_y)
    # Nhận tham số cũ để không phá caller, nhưng nhãn luôn được dẫn xuất từ
    # hotkey thật và không được ghi riêng xuống prefs.json.
    _ = hotkey_label

    payload = {key: value for key, value in current.items() if key != "hotkey_label"}
    path = _prefs_path(base_dir)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temp.replace(path)
    return current
