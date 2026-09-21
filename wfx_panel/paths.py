"""Nơi ứng dụng đọc tài nguyên đóng gói và ghi dữ liệu người dùng.

File này PHẢI nằm ngay trong ``wfx_panel/``: ``RESOURCE_DIR`` neo theo
``__file__.parent.parent`` để bản PyInstaller tìm đúng ``ui/`` và ``assets/``.
Dời nó xuống một thư mục con là hỏng bản đóng gói mà test không bắt được.

``RESOURCE_DIR`` là tài nguyên CHỈ ĐỌC, ``DATA_DIR`` mới là nơi ghi. Lẫn lộn
hai thứ này là ghi thẳng vào thư mục cài đặt.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

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
    thư mục dist sẽ xóa sạch tài khoản đã lưu, (2) zip thư mục dist để chia sẻ
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

def _catalog_cache_path(base_dir: Path) -> Path:
    return Path(base_dir) / "catalog-folders.json"

def _costing_article_cache_path(base_dir: Path) -> Path:
    return Path(base_dir) / "costing-article-options.json"

def _costing_special_options_cache_path(base_dir: Path) -> Path:
    return Path(base_dir) / "costing-special-options.json"
