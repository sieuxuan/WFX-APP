"""Cache cạnh panel: cây folder Catalog và option Article của Costing.

Cả ba họ cache đều khoá theo User ID (option đặc biệt còn theo Division), vì
đổi tài khoản là cây folder và quyền đọc đều khác. Mọi lần ghi đi qua
``write_json_atomic`` để một lần crash giữa chừng không để lại file hỏng.

Đọc luôn phải chịu được file hỏng hoặc thiếu trường: trả về rỗng rồi quét lại
còn hơn ném lỗi ra giữa một flow người dùng đang chạy.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from wfx_panel.atomic_io import write_json_atomic
from wfx_panel.coercion import nonnegative_float
from wfx_panel.paths import (
    DATA_DIR,
    _catalog_cache_path,
    _costing_article_cache_path,
    _costing_special_options_cache_path,
)

# Ghi cache là read-modify-write nên cần khóa riêng, giống prefs: hai lần ghi
# song song từ UI thread và automation worker sẽ mất một trong hai thay đổi.
_WRITE_LOCK = threading.RLock()


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
    if not isinstance(data, dict):
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
    with _WRITE_LOCK:
        write_json_atomic(
            _catalog_cache_path(base_dir),
            {
                "user_id": owner,
                "category_name": "Apparel",
                "folders": normalised,
            },
            separators=(",", ":"),
        )
    return normalised

def _normalise_costing_article_section(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    section_key = str(value.get("section_key") or "").strip()[:180]
    section_name = str(value.get("section_name") or "").strip()[:180]
    raw_options = value.get("options")
    if not section_key or not section_name or not isinstance(raw_options, list):
        return None
    options = []
    seen = set()
    for raw in raw_options[:5000]:
        if not isinstance(raw, dict):
            continue
        article_code = str(raw.get("article_code") or "").strip()[:160]
        article_name = str(raw.get("article_name") or "").strip()[:300]
        identity = (article_code.casefold(), article_name.casefold())
        if not any(identity) or identity in seen:
            continue
        seen.add(identity)
        options.append(
            {
                "article_code": article_code,
                "article_name": article_name,
            }
        )
    if not options:
        return None
    return {
        "section_key": section_key,
        "section_name": section_name,
        "options": options,
    }

def load_costing_article_cache(
    user_id: str,
    base_dir: Path | None = None,
    *,
    max_age_seconds: int = 7 * 24 * 60 * 60,
) -> list[dict] | None:
    """Đọc dropdown Article đã scan, tách riêng theo account và section."""
    base_dir = DATA_DIR if base_dir is None else base_dir
    try:
        data = json.loads(
            _costing_article_cache_path(base_dir).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    owner = str(data.get("user_id") or "").strip()
    requested_user = str(user_id or "").strip()
    saved_at = nonnegative_float(data.get("saved_at"))
    if (
        not requested_user
        or owner.casefold() != requested_user.casefold()
        or saved_at <= 0
        or time.time() - saved_at > max(0, int(max_age_seconds))
    ):
        return None
    raw_sections = data.get("sections")
    if not isinstance(raw_sections, list):
        return None
    sections = [
        section
        for raw in raw_sections[:100]
        if (section := _normalise_costing_article_section(raw)) is not None
    ]
    return sections or None

def save_costing_article_cache(
    user_id: str,
    sections: list[dict],
    base_dir: Path | None = None,
) -> list[dict]:
    """Lưu dropdown Article riêng để các lần Export sau không phải scan lại."""
    base_dir = DATA_DIR if base_dir is None else base_dir
    owner = str(user_id or "").strip()
    if not owner:
        return []
    normalised = [
        section
        for raw in sections[:100]
        if (section := _normalise_costing_article_section(raw)) is not None
    ]
    if not normalised:
        return []
    with _WRITE_LOCK:
        write_json_atomic(
            _costing_article_cache_path(base_dir),
            {
                "user_id": owner,
                "saved_at": time.time(),
                "sections": normalised,
            },
            separators=(",", ":"),
        )
    return normalised

_SPECIAL_COST_SECTION_KEYS = frozenset(
    {"cmcosts", "productioncosts", "indirectcosts"}
)

def _normalise_costing_special_section(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    section_key = str(value.get("section_key") or "").strip().casefold()
    if section_key not in _SPECIAL_COST_SECTION_KEYS:
        return None
    raw_options = value.get("options")
    if not isinstance(raw_options, list):
        return None
    options: list[str] = []
    seen: set[str] = set()
    for raw in raw_options[:5000]:
        option = str(raw or "").strip()[:300]
        identity = option.casefold()
        if not option or identity in seen:
            continue
        seen.add(identity)
        options.append(option)
    return {"section_key": section_key, "options": options}

def load_costing_special_options_cache(
    user_id: str,
    division_key: str,
    base_dir: Path | None = None,
    *,
    max_age_seconds: int = 7 * 24 * 60 * 60,
) -> dict | None:
    """Đọc ba dropdown chi phí, giới hạn theo account + Division + 7 ngày."""
    base_dir = DATA_DIR if base_dir is None else base_dir
    try:
        data = json.loads(
            _costing_special_options_cache_path(base_dir).read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    owner = str(data.get("user_id") or "").strip()
    division = str(data.get("division_key") or "").strip()
    requested_user = str(user_id or "").strip()
    requested_division = str(division_key or "").strip()
    saved_at = nonnegative_float(data.get("saved_at"))
    if (
        not requested_user
        or not requested_division
        or owner.casefold() != requested_user.casefold()
        or division.casefold() != requested_division.casefold()
        or saved_at <= 0
        or time.time() - saved_at > max(0, int(max_age_seconds))
    ):
        return None
    raw_sections = data.get("sections")
    if not isinstance(raw_sections, list):
        return None
    sections = [
        section
        for raw in raw_sections[:10]
        if (section := _normalise_costing_special_section(raw)) is not None
    ]
    if {section["section_key"] for section in sections} != (
        _SPECIAL_COST_SECTION_KEYS
    ):
        return None
    return {
        "saved_at": saved_at,
        "expires_at": saved_at + max(0, int(max_age_seconds)),
        "sections": sections,
    }

def save_costing_special_options_cache(
    user_id: str,
    division_key: str,
    sections: list[dict],
    base_dir: Path | None = None,
) -> dict | None:
    """Lưu snapshot đầy đủ của CM/Production/Indirect dropdown."""
    base_dir = DATA_DIR if base_dir is None else base_dir
    owner = str(user_id or "").strip()
    division = str(division_key or "").strip()
    normalised = [
        section
        for raw in sections[:10]
        if (section := _normalise_costing_special_section(raw)) is not None
    ]
    if (
        not owner
        or not division
        or {section["section_key"] for section in normalised}
        != _SPECIAL_COST_SECTION_KEYS
    ):
        return None
    saved_at = time.time()
    with _WRITE_LOCK:
        write_json_atomic(
            _costing_special_options_cache_path(base_dir),
            {
                "user_id": owner,
                "division_key": division,
                "saved_at": saved_at,
                "sections": normalised,
            },
            separators=(",", ":"),
        )
    return {
        "saved_at": saved_at,
        "expires_at": saved_at + 7 * 24 * 60 * 60,
        "sections": normalised,
    }
