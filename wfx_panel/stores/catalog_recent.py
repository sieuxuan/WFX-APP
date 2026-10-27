"""Style vừa mở gần đây trong Catalog, theo User ID + Category.

Người dùng mở lại vài Style quen nhiều lần trong ngày; nhớ chúng để bấm một
chạm thay vì gõ lại Code. Chỉ lưu Code, tên hiển thị và thời điểm — không có gì
nhạy cảm — và luôn lọc theo User ID để tài khoản khác dùng chung máy không thấy
danh sách của nhau. JSON hỏng thì coi như rỗng.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from pathlib import Path

from wfx_panel.atomic_io import write_json_atomic

FILE_NAME = "catalog-recent.json"
PER_SCOPE = 8
MAX_ENTRIES = 200

_LOCK = threading.Lock()


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _entries(raw: object) -> list[dict[str, object]]:
    items = raw.get("styles") if isinstance(raw, Mapping) else None
    if not isinstance(items, list):
        return []
    cleaned: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        entry = {
            "user_id": _clean(item.get("user_id"), 120).casefold(),
            "category": _clean(item.get("category"), 60),
            "code": _clean(item.get("code"), 80),
            "label": _clean(item.get("label"), 160),
            "opened_at": item.get("opened_at")
            if isinstance(item.get("opened_at"), int | float)
            else 0,
        }
        if entry["user_id"] and entry["category"] and entry["code"]:
            cleaned.append(entry)
    return cleaned


class CatalogRecentStore:
    def __init__(self, base_dir: Path) -> None:
        self.path = Path(base_dir) / FILE_NAME

    def _read(self) -> list[dict[str, object]]:
        try:
            return _entries(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return []

    def load(self, user_id: str, category: str) -> list[dict[str, str]]:
        """Mới nhất trước, tối đa ``PER_SCOPE`` Style của đúng tài khoản."""
        owner = _clean(user_id, 120).casefold()
        scope = _clean(category, 60)
        if not owner or not scope:
            return []
        return [
            {"code": str(entry["code"]), "label": str(entry["label"])}
            for entry in self._read()
            if entry["user_id"] == owner and entry["category"] == scope
        ][:PER_SCOPE]

    def remember(
        self,
        user_id: str,
        category: str,
        code: str,
        label: str = "",
    ) -> list[dict[str, str]]:
        owner = _clean(user_id, 120).casefold()
        scope = _clean(category, 60)
        style = _clean(code, 80)
        if not owner or not scope or not style:
            return self.load(user_id, category)
        with _LOCK:
            kept = [
                entry
                for entry in self._read()
                if not (
                    entry["user_id"] == owner
                    and entry["category"] == scope
                    and str(entry["code"]).casefold() == style.casefold()
                )
            ]
            kept.insert(
                0,
                {
                    "user_id": owner,
                    "category": scope,
                    "code": style,
                    "label": _clean(label, 160),
                    "opened_at": time.time(),
                },
            )
            per_scope: dict[tuple[str, str], int] = {}
            trimmed: list[dict[str, object]] = []
            for entry in kept:
                key = (str(entry["user_id"]), str(entry["category"]))
                per_scope[key] = per_scope.get(key, 0) + 1
                if per_scope[key] <= PER_SCOPE:
                    trimmed.append(entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(
                self.path,
                {"styles": trimmed[:MAX_ENTRIES]},
                indent=2,
            )
        return self.load(user_id, category)
