"""Điều kiện tìm gần đây của các form Tìm module, theo User ID + nhóm form.

Giống hàng `Gần đây` của Catalog: người dùng tìm lại cùng vài OC, RMPO hay
Supplier nhiều lần trong ngày, nhớ chúng để bấm một chạm thay vì gõ lại. Mỗi
mục chỉ giữ danh sách giá trị đúng thứ tự ô của form, ``kind`` (kiểu lọc,
Category hoặc module) và thời điểm; luôn lọc theo User ID để tài khoản khác
dùng chung máy không thấy danh sách của nhau. JSON hỏng thì coi như rỗng.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from pathlib import Path

from wfx_panel.atomic_io import write_json_atomic

FILE_NAME = "search-recent.json"
PER_SCOPE = 6
MAX_ENTRIES = 300
MAX_FIELDS = 4

_LOCK = threading.Lock()


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _values(raw: object) -> list[str]:
    if not isinstance(raw, list | tuple):
        return []
    return [_clean(value, 120) for value in list(raw)[:MAX_FIELDS]]


def _key(entry: Mapping[str, object]) -> tuple[str, ...]:
    values = entry.get("values")
    return (
        str(entry.get("kind") or "").casefold(),
        *(str(value).casefold() for value in (values if isinstance(values, list) else [])),
    )


def _entries(raw: object) -> list[dict[str, object]]:
    items = raw.get("searches") if isinstance(raw, Mapping) else None
    if not isinstance(items, list):
        return []
    cleaned: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        entry = {
            "user_id": _clean(item.get("user_id"), 120).casefold(),
            "group": _clean(item.get("group"), 40),
            "kind": _clean(item.get("kind"), 60),
            "values": _values(item.get("values")),
            "searched_at": item.get("searched_at")
            if isinstance(item.get("searched_at"), int | float)
            else 0,
        }
        if entry["user_id"] and entry["group"] and any(entry["values"]):
            cleaned.append(entry)
    return cleaned


class SearchRecentStore:
    def __init__(self, base_dir: Path) -> None:
        self.path = Path(base_dir) / FILE_NAME

    def _read(self) -> list[dict[str, object]]:
        try:
            return _entries(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return []

    def load(self, user_id: str, group: str) -> list[dict[str, object]]:
        """Mới nhất trước, tối đa ``PER_SCOPE`` lượt tìm của đúng tài khoản."""
        owner = _clean(user_id, 120).casefold()
        scope = _clean(group, 40)
        if not owner or not scope:
            return []
        return [
            {"kind": str(entry["kind"]), "values": list(entry["values"])}
            for entry in self._read()
            if entry["user_id"] == owner and entry["group"] == scope
        ][:PER_SCOPE]

    def remember(
        self,
        user_id: str,
        group: str,
        values: list[str],
        kind: str = "",
    ) -> list[dict[str, object]]:
        owner = _clean(user_id, 120).casefold()
        scope = _clean(group, 40)
        cleaned = _values(values)
        if not owner or not scope or not any(cleaned):
            return self.load(user_id, group)
        entry: dict[str, object] = {
            "user_id": owner,
            "group": scope,
            "kind": _clean(kind, 60),
            "values": cleaned,
            "searched_at": time.time(),
        }
        with _LOCK:
            kept = [
                item
                for item in self._read()
                if not (
                    item["user_id"] == owner
                    and item["group"] == scope
                    and _key(item) == _key(entry)
                )
            ]
            kept.insert(0, entry)
            per_scope: dict[tuple[str, str], int] = {}
            trimmed: list[dict[str, object]] = []
            for item in kept:
                scope_key = (str(item["user_id"]), str(item["group"]))
                per_scope[scope_key] = per_scope.get(scope_key, 0) + 1
                if per_scope[scope_key] <= PER_SCOPE:
                    trimmed.append(item)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(
                self.path,
                {"searches": trimmed[:MAX_ENTRIES]},
                indent=2,
            )
        return self.load(user_id, group)
