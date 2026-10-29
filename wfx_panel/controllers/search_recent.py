"""Hàng `Gần đây` cho các form Tìm module, giống Catalog.

Mỗi nhóm form trùng tên nhóm validation phía UI (`INPUT_VALIDATION_GROUPS`) và
lưu giá trị đúng thứ tự các ô của form đó. Chỉ lượt tìm thành công mới được
nhớ: lượt không có kết quả hoặc lỗi không đáng để bấm lại một chạm.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel.stores.search_recent import SearchRecentStore

# Nhóm form → số ô điều kiện. Nhóm lạ bị từ chối để bridge không thành nơi ghi
# tùy ý xuống đĩa.
SEARCH_RECENT_GROUPS: dict[str, int] = {
    "oc": 1,
    "sample": 4,
    "sale-asn": 1,
    "rmpo": 2,
    "grn-search": 1,
    "indent": 4,
    "advance-pr": 4,
    "supplier-invoice": 4,
    "expense-invoice": 4,
    "supplier": 1,
    "buyer": 1,
}


class SearchRecentController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel

    @property
    def store(self) -> SearchRecentStore:
        # Tạo khi dùng: store chỉ giữ đường dẫn, và panel giả trong test của
        # module khác không có ``_base_dir``.
        return SearchRecentStore(self._panel._base_dir)

    def _user_id(self) -> str:
        return str(self._panel._account().get("user_id") or "")

    def remember(
        self,
        group: str,
        values: list[str],
        result: dict,
        kind: str = "",
    ) -> dict:
        """Gắn danh sách Gần đây mới vào kết quả của một lượt tìm thành công."""
        size = SEARCH_RECENT_GROUPS.get(group)
        if size is None or not isinstance(result, dict) or not result.get("ok"):
            return result
        cleaned = [str(value or "").strip() for value in list(values)[:size]]
        if not any(cleaned):
            return result
        user_id = self._user_id()
        try:
            items = self.store.remember(user_id, group, cleaned, kind)
        except OSError:
            items = self.store.load(user_id, group)
        return {**result, "recent_searches": {"group": group, "items": items}}

    def load(self, group: str) -> dict:
        name = str(group or "")
        items = (
            self.store.load(self._user_id(), name)
            if name in SEARCH_RECENT_GROUPS
            else []
        )
        return {
            "ok": True,
            "code": "SEARCH_RECENT",
            "message": "",
            "recent_searches": {"group": name, "items": items},
        }
