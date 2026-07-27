from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from wfx_panel import hotkey as hotkey_spec
from wfx_panel import secret

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


class CredentialProtectionError(RuntimeError):
    """Không thể lưu credential an toàn bằng DPAPI trên Windows."""


def _env_path(base_dir: Path) -> Path:
    return Path(base_dir) / ".env"


def _prefs_path(base_dir: Path) -> Path:
    return Path(base_dir) / "prefs.json"


def _catalog_cache_path(base_dir: Path) -> Path:
    return Path(base_dir) / "catalog-folders.json"


def _normalise_catalog_folder(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    category_name = str(value.get("category_name") or "").strip()[:80]
    category_value = str(value.get("category_value") or "").strip()[:40]
    user_id = str(value.get("user_id") or "").strip()[:120]
    node_id = str(value.get("node_id") or "").strip()
    if node_id and not node_id.isdigit():
        return None
    raw_path = value.get("path")
    path = (
        [str(part).strip()[:120] for part in raw_path if str(part).strip()]
        if isinstance(raw_path, list)
        else []
    )
    path = path[:20]
    # Cây vị trí mặc định hiện chỉ có ý nghĩa nghiệp vụ với Apparel.
    # Loại luôn dữ liệu cũ của category khác để không tự động mở sai nơi.
    if category_name != "Apparel" or category_value != "01":
        return None
    if not node_id:
        return {
            "category_name": category_name,
            "category_value": category_value,
            "user_id": user_id,
            "node_id": "",
            "node_code": "Master",
            "name": "Master",
            "path": ["Master"],
            "path_label": "Master",
            "kind": "master",
            "depth": 0,
        }
    name = str(value.get("name") or (path[-1] if path else "")).strip()[:120]
    if not name or not path:
        return None
    return {
        "category_name": category_name,
        "category_value": category_value,
        "user_id": user_id,
        "node_id": node_id,
        "node_code": str(value.get("node_code") or "").strip()[:160],
        "name": name,
        "path": path,
        "path_label": " / ".join(path),
        "kind": "group" if value.get("kind") == "group" else "folder",
        "depth": len(path),
    }


def _normalise_catalog_tree_node(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    node_id = str(value.get("node_id") or "").strip()
    if not node_id.isdigit():
        return None
    raw_path = value.get("path")
    path = (
        [str(part).strip()[:120] for part in raw_path if str(part).strip()]
        if isinstance(raw_path, list)
        else []
    )[:20]
    name = str(value.get("name") or (path[-1] if path else "")).strip()[:120]
    if not name or not path:
        return None
    return {
        "node_id": node_id,
        "node_code": str(value.get("node_code") or "").strip()[:160],
        "name": name,
        "path": path,
        "path_label": " / ".join(path),
        "kind": "group" if value.get("kind") == "group" else "folder",
        "depth": len(path),
    }


def load_catalog_folder_cache(
    user_id: str,
    category_name: str = "Apparel",
    base_dir: Path | None = None,
) -> list[dict] | None:
    """Đọc cây Catalog đã scan, chỉ khi đúng account + Apparel."""
    base_dir = DATA_DIR if base_dir is None else base_dir
    path = _catalog_cache_path(base_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    owner = str(data.get("user_id") or "").strip()
    requested_user = str(user_id or "").strip()
    if (
        not requested_user
        or owner.casefold() != requested_user.casefold()
        or data.get("category_name") != "Apparel"
        or category_name != "Apparel"
    ):
        return None
    folders = []
    seen = set()
    raw_folders = data.get("folders")
    if not isinstance(raw_folders, list):
        return None
    for raw in raw_folders[:5000]:
        folder = _normalise_catalog_tree_node(raw)
        if folder is None or folder["node_id"] in seen:
            continue
        seen.add(folder["node_id"])
        folders.append(folder)
    return folders or None


def save_catalog_folder_cache(
    user_id: str,
    folders: list[dict],
    category_name: str = "Apparel",
    base_dir: Path | None = None,
) -> list[dict]:
    """Lưu riêng cây lớn để save prefs/vị trí cửa sổ luôn nhẹ."""
    base_dir = DATA_DIR if base_dir is None else base_dir
    owner = str(user_id or "").strip()
    if not owner or category_name != "Apparel":
        return []
    normalised = []
    seen = set()
    for raw in folders[:5000]:
        folder = _normalise_catalog_tree_node(raw)
        if folder is None or folder["node_id"] in seen:
            continue
        seen.add(folder["node_id"])
        normalised.append(folder)
    if not normalised:
        return []
    path = _catalog_cache_path(base_dir)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(
            {
                "user_id": owner,
                "category_name": "Apparel",
                "folders": normalised,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temp.replace(path)
    return normalised


# Các key account do prefs quản lý; mọi dòng .env khác (webhook, key tuỳ biến)
# phải được giữ nguyên khi save_account ghi lại file.
_ACCOUNT_ENV_KEYS = frozenset(
    {"WFX_USER_ID", "WFX_PASSWORD", "WFX_PASSWORD_ENC"}
)


def _parse_env_value(value: str) -> str:
    value = value.strip()
    try:
        return json.loads(value) if value.startswith('"') else value
    except json.JSONDecodeError:
        return value.strip('"')


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
            values[key.strip()] = _parse_env_value(value)
    encrypted = values.get("WFX_PASSWORD_ENC", "")
    if encrypted:
        # Không giải được (DPAPI vắng mặt, đổi máy/user, blob hỏng) => coi như
        # chưa có mật khẩu để buộc người dùng nhập lại, không lộ token.
        decrypted = secret.unprotect(encrypted)
        password = decrypted if decrypted is not None else ""
    else:
        # Tương thích ngược: bản cũ và file migrate còn WFX_PASSWORD plaintext.
        password = values.get("WFX_PASSWORD", "")
        if password and os.name == "nt":
            # Đọc legacy lần đầu là thời điểm migration: ghi lại ngay bằng DPAPI
            # để plaintext không tiếp tục nằm trên đĩa tới lần người dùng Save.
            save_account(
                values.get("WFX_USER_ID", ""),
                password,
                base_dir=base_dir,
            )
    return {
        "user_id": values.get("WFX_USER_ID", ""),
        "password": password,
    }


def save_account(user_id: str, password: str, base_dir: Path | None = None) -> None:
    base_dir = DATA_DIR if base_dir is None else base_dir
    path = _env_path(base_dir)
    preserved: list[str] = []
    if path.is_file():
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                stripped = raw.strip()
                key = (
                    stripped.split("=", 1)[0].strip()
                    if "=" in stripped and not stripped.startswith("#")
                    else ""
                )
                if key in _ACCOUNT_ENV_KEYS:
                    continue
                preserved.append(raw)
        except OSError:
            preserved = []

    protected = secret.protect(password)
    if protected is not None:
        password_line = (
            f"WFX_PASSWORD_ENC={json.dumps(protected, ensure_ascii=False)}"
        )
    else:
        if os.name == "nt" and password:
            # Trên Windows không bao giờ hạ cấp im lặng từ DPAPI xuống plaintext.
            raise CredentialProtectionError(
                "Windows không mã hoá được mật khẩu bằng DPAPI; chưa lưu thay đổi."
            )
        # Hỗ trợ môi trường phát triển không phải Windows.
        password_line = (
            f"WFX_PASSWORD={json.dumps(password, ensure_ascii=False)}"
        )
    lines = [
        f"WFX_USER_ID={json.dumps(user_id, ensure_ascii=False)}",
        password_line,
        *[line for line in preserved if line.strip()],
    ]
    content = "\n".join(lines) + "\n"
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)
    # Runtime (session.run) đọc mật khẩu plaintext qua env trong tiến trình; chỉ
    # bản trên đĩa được mã hoá.
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
    def optional_int(key: str) -> int | None:
        value = data.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    compact_offset_x = optional_int("compact_offset_x")
    compact_offset_y = optional_int("compact_offset_y")
    panel_offset_x = optional_int("panel_offset_x")
    panel_offset_y = optional_int("panel_offset_y")
    theme = data.get("theme")
    return {
        "theme": theme if theme in {"light", "dark", "system"} else "light",
        "close_after_module": data.get("close_after_module", True) is not False,
        "hotkey": stored_hotkey,
        "hotkey_label": hotkey_spec.format_label(stored_hotkey),
        "autostart": data.get("autostart", False) is True,
        "start_hidden": data.get("start_hidden", False) is True,
        "toast_enabled": data.get("toast_enabled", True) is not False,
        "focus_chrome_on_module": data.get(
            "focus_chrome_on_module", True
        ) is not False,
        "always_on_top": data.get("always_on_top", True) is not False,
        "admin_mode": data.get("admin_mode", False) is True,
        "update_channel": (
            "current"
            if data.get("update_channel") == "current"
            else "stable"
        ),
        "last_update_notice": str(data.get("last_update_notice") or ""),
        "compact_offset_x": compact_offset_x,
        "compact_offset_y": compact_offset_y,
        "panel_offset_x": panel_offset_x,
        "panel_offset_y": panel_offset_y,
        "catalog_default_folder": _normalise_catalog_folder(
            data.get("catalog_default_folder")
        ),
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
    focus_chrome_on_module: bool | None = None,
    always_on_top: bool | None = None,
    admin_mode: bool | None = None,
    update_channel: str | None = None,
    last_update_notice: str | None = None,
    compact_offset_x: int | None = None,
    compact_offset_y: int | None = None,
    panel_offset_x: int | None = None,
    panel_offset_y: int | None = None,
    catalog_default_folder: dict | None = None,
) -> dict:
    base_dir = DATA_DIR if base_dir is None else base_dir
    current = load_prefs(base_dir)
    if theme is not None:
        current["theme"] = theme if theme in {"light", "dark", "system"} else "light"
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
    if focus_chrome_on_module is not None:
        current["focus_chrome_on_module"] = bool(focus_chrome_on_module)
    if always_on_top is not None:
        current["always_on_top"] = bool(always_on_top)
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
    if panel_offset_x is not None:
        current["panel_offset_x"] = int(panel_offset_x)
    if panel_offset_y is not None:
        current["panel_offset_y"] = int(panel_offset_y)
    if catalog_default_folder is not None:
        current["catalog_default_folder"] = _normalise_catalog_folder(
            catalog_default_folder
        )
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
