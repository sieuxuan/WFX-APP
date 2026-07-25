from __future__ import annotations

import json
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_HOTKEY_LABEL = "Ctrl + Shift + X"


def _env_path(base_dir: Path) -> Path:
    return Path(base_dir) / ".env"


def _prefs_path(base_dir: Path) -> Path:
    return Path(base_dir) / "prefs.json"


def load_account(base_dir: Path = APP_DIR) -> dict:
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


def save_account(user_id: str, password: str, base_dir: Path = APP_DIR) -> None:
    content = (
        f"WFX_USER_ID={json.dumps(user_id, ensure_ascii=False)}\n"
        f"WFX_PASSWORD={json.dumps(password, ensure_ascii=False)}\n"
    )
    path = _env_path(base_dir)
    temp = path.with_suffix(".env.tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)
    os.environ["WFX_USER_ID"] = user_id
    os.environ["WFX_PASSWORD"] = password


def load_prefs(base_dir: Path = APP_DIR) -> dict:
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
    base_dir: Path = APP_DIR,
    *,
    theme: str | None = None,
    close_after_module: bool | None = None,
    hotkey_label: str | None = None,
) -> dict:
    current = load_prefs(base_dir)
    if theme is not None:
        current["theme"] = "dark" if theme == "dark" else "light"
    if close_after_module is not None:
        current["close_after_module"] = bool(close_after_module)
    if hotkey_label is not None:
        current["hotkey_label"] = str(hotkey_label)
    path = _prefs_path(base_dir)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return current
