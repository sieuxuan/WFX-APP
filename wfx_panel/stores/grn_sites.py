"""Danh sách Site nhận kho GRN, theo User ID + Division.

Site là master data ít đổi của từng Division. Nhớ lại danh sách lần gần nhất
đọc được trên GRN Pending để user chọn Site ngay trong app trước khi chạy,
thay vì phải chờ automation đọc dropdown WFX ở mỗi lượt. Chỉ lưu tên Site;
JSON hỏng thì coi như rỗng.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterable, Mapping
from pathlib import Path

from wfx_panel.atomic_io import write_json_atomic

FILE_NAME = "grn-sites.json"
MAX_SITES = 100
MAX_SCOPES = 40

_LOCK = threading.Lock()


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _scope_key(user_id: str, division: str) -> str:
    # Không có User ID thì không ghi: tài khoản khác dùng chung máy không được
    # thấy Site của nhau. Division chưa đọc được vẫn có scope riêng ("").
    owner = _clean(user_id, 120).casefold()
    scope = _clean(division, 60).casefold()
    return f"{owner}|{scope}" if owner else ""


def clean_sites(sites: Iterable[object]) -> list[str]:
    """Bỏ trống và trùng không phân biệt hoa/thường, giữ thứ tự WFX."""
    unique: dict[str, str] = {}
    for item in sites or ():
        site = _clean(item, 160)
        if site:
            unique.setdefault(site.casefold(), site)
    return list(unique.values())[:MAX_SITES]


class GrnSiteStore:
    def __init__(self, base_dir: Path) -> None:
        self.path = Path(base_dir) / FILE_NAME

    def _read(self) -> dict[str, dict[str, object]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        scopes = raw.get("scopes") if isinstance(raw, Mapping) else None
        if not isinstance(scopes, Mapping):
            return {}
        kept: dict[str, dict[str, object]] = {}
        for key, entry in scopes.items():
            if not isinstance(key, str) or not isinstance(entry, Mapping):
                continue
            sites = entry.get("sites")
            if not isinstance(sites, list):
                continue
            updated = entry.get("updated_at")
            kept[key] = {
                "sites": clean_sites(sites),
                "updated_at": updated if isinstance(updated, int | float) else 0,
            }
        return kept

    def load(self, user_id: str, division: str) -> list[str]:
        key = _scope_key(user_id, division)
        if not key:
            return []
        entry = self._read().get(key) or {}
        return list(entry.get("sites") or [])

    def remember(self, user_id: str, division: str, sites: Iterable[object]) -> list[str]:
        """Thay toàn bộ danh sách của đúng tài khoản + Division."""
        key = _scope_key(user_id, division)
        cleaned = clean_sites(sites)
        if not key or not cleaned:
            return self.load(user_id, division)
        with _LOCK:
            scopes = self._read()
            scopes[key] = {"sites": cleaned, "updated_at": time.time()}
            newest = sorted(
                scopes.items(),
                key=lambda item: float(item[1].get("updated_at") or 0),
                reverse=True,
            )[:MAX_SCOPES]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(self.path, {"scopes": dict(newest)}, indent=2)
        return cleaned
