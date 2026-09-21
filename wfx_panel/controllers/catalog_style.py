"""Tạo Style hàng loạt cho Apparel từ workbook Excel.

User phải quét/chọn một node đúng loại Group rồi mới Import được. Mỗi lần
chỉ chuẩn bị MỘT dòng và luôn dừng trước Save khi `Tự động Save` tắt —
workbook chỉ sống trong process dưới dạng token ngẫu nhiên."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.controllers.catalog import CatalogController

from wfx_panel import constants
from wfx_panel.stores import style_options
from wfx_panel.workbooks.style import StyleWorkbookError, read_style_workbook

STYLE_IMPORT_TTL_SECONDS = 30 * 60


class StyleImportController:
    def __init__(self, catalog: CatalogController) -> None:
        self._catalog = catalog
        self._panel = catalog._panel
        # Workbook Style chỉ tồn tại trong process qua token ngẫu nhiên.
        self.imports: dict[str, dict] = {}

    def _style_group(self, group_id: str) -> dict | None:
        catalog = self._catalog
        group_id = str(group_id or "").strip()
        return next(
            (
                item
                for item in catalog.folder_cache.get("Apparel", [])
                if str(item.get("node_id") or "") == group_id
                and str(item.get("kind") or "").casefold() == "group"
            ),
            None,
        )

    def _active_style_import(self, token: str) -> dict | None:
        now = time.monotonic()
        for old_token, review in tuple(self.imports.items()):
            if now - float(review.get("created_at") or 0) > STYLE_IMPORT_TTL_SECONDS:
                self.imports.pop(old_token, None)
        return self.imports.get(str(token or "").strip())

    def review_style_import(self, file_path: str, group_id: str) -> dict:
        """Validate file local và tạo queue; chưa mở hoặc thay đổi WFX."""
        source = Path(str(file_path or "")).expanduser().resolve()
        group = self._style_group(group_id)
        if group is None:
            return {
                "ok": False,
                "code": "STYLE_GROUP_REQUIRED",
                "message": "Hãy quét cây và chọn đúng một Group Apparel.",
            }

        def action() -> dict:
            try:
                rows = read_style_workbook(source)
            except StyleWorkbookError as error:
                return {
                    "ok": False,
                    "code": error.code,
                    "message": error.message,
                    "errors": list(error.errors),
                    "file_name": source.name,
                }
            self.imports.clear()
            token = uuid.uuid4().hex
            self.imports[token] = {
                "created_at": time.monotonic(),
                "group": dict(group),
                "rows": [row.automation_payload() for row in rows],
                "file_name": source.name,
            }
            public_rows = [
                {
                    "source_row": row.source_row,
                    "type": row.type,
                    "style_copy": row.style_copy,
                    "buyer_style_ref": row.buyer_style_ref,
                    "internal_style_ref": row.internal_style_ref,
                }
                for row in rows
            ]
            return {
                "ok": True,
                "code": "STYLE_IMPORT_REVIEW_READY",
                "message": (
                    f"File hợp lệ: {len(rows)} dòng. App sẽ chuẩn bị từng dòng "
                    "theo chế độ Save đang chọn."
                ),
                "review_token": token,
                "file_name": source.name,
                "group": {
                    "node_id": str(group.get("node_id") or ""),
                    "name": str(group.get("name") or ""),
                    "path_label": str(group.get("path_label") or ""),
                },
                "row_count": len(rows),
                "rows": public_rows,
                "requires_manual_save": True,
            }

        return self._panel._run(
            "review_catalog_style_import",
            action,
            {"file_name": source.name, "group_id": str(group_id or "")},
        )

    def clear_style_import(self, token: str) -> dict:
        self.imports.pop(str(token or "").strip(), None)
        return {
            "ok": True,
            "code": "STYLE_IMPORT_CANCELLED",
            "message": "Đã hủy danh sách Tạo Style; WFX chưa được Save.",
        }

    def ensure_style_options(self, group_id: str, force: bool = False) -> dict:
        """Lấy dropdown server/cache; chỉ quét WFX khi snapshot đã quá 30 ngày."""
        group = self._style_group(group_id)
        if group is None:
            return {
                "ok": False,
                "code": "STYLE_GROUP_REQUIRED",
                "message": "Hãy quét cây và chọn đúng một Group Apparel.",
            }
        cached = style_options.load_cached(self._panel._base_dir)
        if not force and cached is not None and style_options.status(
            self._panel._base_dir
        )["fresh"]:
            return {
                "ok": True,
                "code": "STYLE_OPTIONS_CACHED",
                "message": "Đang dùng danh sách dropdown Style trong tháng này.",
                "options": cached,
                **style_options.status(self._panel._base_dir),
            }
        if not force:
            remote = style_options.sync_remote(self._panel._base_dir)
            if remote is not None and style_options.status(
                self._panel._base_dir
            )["fresh"]:
                return {
                    "ok": True,
                    "code": "STYLE_OPTIONS_SERVER",
                "message": "Đã lấy danh sách dropdown Style từ GitHub.",
                    "options": remote,
                    **style_options.status(self._panel._base_dir),
                }

        panel = self._panel

        def action() -> dict:
            scanner = getattr(panel._login, "scan_catalog_style_options", None)
            if not callable(scanner):
                return {
                    "ok": False,
                    "code": "STYLE_OPTIONS_SCAN_UNSUPPORTED",
                    "message": "Phiên bản automation chưa hỗ trợ quét dropdown Style.",
                }
            result = scanner(
                constants.CATEGORIES["Apparel"],
                str(group.get("node_id") or ""),
                panel._log,
            )
            if not result.get("ok"):
                return result
            account = panel._account()
            snapshot = style_options.save_snapshot(
                panel._base_dir,
                {
                    "generated_at": time.time(),
                    "source": "wfx-scan",
                    "company_id": str(account.get("company_id") or ""),
                    "division_key": str(panel._current_division or ""),
                    "group_id": str(group.get("node_id") or ""),
                    "fields": result.get("fields") or {},
                    "subcategories_by_product_group": result.get(
                        "subcategories_by_product_group"
                    )
                    or {},
                },
            )
            uploaded = style_options.publish_snapshot(snapshot)
            return {
                "ok": True,
                "code": "STYLE_OPTIONS_SCANNED",
                "message": (
                    "Đã quét dropdown Style và cập nhật snapshot trên GitHub."
                    if uploaded
                    else "Đã quét dropdown Style và lưu cache tháng trên máy."
                ),
                "uploaded": uploaded,
                "options": snapshot,
                **style_options.status(panel._base_dir),
            }

        result = panel._run(
            "scan_catalog_style_options",
            action,
            {"group_id": str(group_id or ""), "force": bool(force)},
        )
        if not result.get("ok") and cached is not None:
            return {
                "ok": True,
                "code": "STYLE_OPTIONS_STALE_CACHE",
                "message": (
                    "Chưa quét mới được; form Excel dùng danh sách gần nhất trên máy."
                ),
                "warning": result.get("message") or "",
                "options": cached,
                **style_options.status(panel._base_dir),
            }
        return result

    def prepare_style_row(
        self,
        token: str,
        source_row: int,
        copy_choice: int | None = None,
        auto_save: bool = False,
    ) -> dict:
        """Mở/điền một dòng; mặc định trả quyền Save cho người dùng."""
        review = self._active_style_import(token)
        if review is None:
            return {
                "ok": False,
                "code": "STYLE_IMPORT_EXPIRED",
                "message": "Danh sách Tạo Style đã hết hạn; hãy chọn lại file.",
            }
        group = review["group"]
        current_group = self._style_group(str(group.get("node_id") or ""))
        if current_group is None:
            return {
                "ok": False,
                "code": "STYLE_GROUP_STALE",
                "message": "Group đã đổi hoặc không còn quyền; hãy quét và chọn lại.",
            }
        try:
            wanted_row = int(source_row)
        except (TypeError, ValueError):
            wanted_row = -1
        row = next(
            (
                item
                for item in review["rows"]
                if int(item.get("source_row") or 0) == wanted_row
            ),
            None,
        )
        if row is None:
            return {
                "ok": False,
                "code": "STYLE_ROW_INVALID",
                "message": "Không tìm thấy dòng Excel cần chuẩn bị.",
            }
        if copy_choice is not None:
            try:
                copy_choice = int(copy_choice)
            except (TypeError, ValueError, OverflowError):
                return {
                    "ok": False,
                    "code": "STYLE_COPY_CHOICE_INVALID",
                    "message": "Lựa chọn Style nguồn không hợp lệ.",
                }

        panel = self._panel

        def action() -> dict:
            preparer = getattr(panel._login, "prepare_catalog_style_row", None)
            if not callable(preparer):
                return {
                    "ok": False,
                    "code": "STYLE_PREPARE_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ Tạo Style.",
                }
            return preparer(
                constants.CATEGORIES["Apparel"],
                str(group.get("node_id") or ""),
                dict(row),
                copy_choice,
                bool(auto_save),
                panel._log,
            )

        return panel._run(
            "prepare_catalog_style_row",
            action,
            {
                "source_row": wanted_row,
                "style_type": str(row.get("type") or ""),
                "group_id": str(group.get("node_id") or ""),
                "auto_save": bool(auto_save),
            },
        )
