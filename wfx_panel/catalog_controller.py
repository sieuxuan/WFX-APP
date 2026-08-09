"""Điều phối riêng luồng Catalog (browse/prepare/find/Costing/BOM + cây folder).

Tách khỏi ``PanelAPI`` để bridge không còn là god-object: toàn bộ state Catalog
(kết quả tìm hiện tại, category đã chuẩn bị, cache cây folder) và logic sống ở
đây. Controller mượn hạ tầng chung của panel (``_run`` khóa + lịch sử, ``_account``,
``_prefs``, ``_log``, ``_login``) qua tham chiếu ``panel`` — cùng package nên coupling
chặt là chấp nhận được, đổi lại panel gọn và luồng Catalog test được độc lập.

Hành vi giữ NGUYÊN so với bản cũ trong panel_api: cùng method_name cho ``_run``
(job history/screenshot/retry phụ thuộc), cùng thứ tự set/observe state.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from heapq import nsmallest
from pathlib import Path
from typing import TYPE_CHECKING

from wfx_panel import article_library, constants, style_options
from wfx_panel.coercion import boolean, bounded_int
from wfx_panel.costing_planner import CostingPlanError, build_costing_plan
from wfx_panel.costing_workbook import (
    CostingWorkbookError,
    costing_file_summary,
    read_costing_file,
    write_costing_file,
)
from wfx_panel.style_workbook import StyleWorkbookError, read_style_workbook

COSTING_PLAN_TTL_SECONDS = 15 * 60
STYLE_IMPORT_TTL_SECONDS = 30 * 60
_SPECIAL_COST_SECTION_KEYS = frozenset(
    {"cmcosts", "productioncosts", "indirectcosts"}
)


@dataclass(frozen=True)
class CatalogActionRequest:
    category_name: str
    filter_kind: str
    query: str
    destination: str | None

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI


class CatalogController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel
        # Kết quả Catalog duy nhất vừa được mở. Costing/BOM phải dùng đúng
        # popup này, không được chạy lại toàn bộ Catalog từ đầu.
        self.result: dict[str, object] | None = None
        # Ghi nhớ đúng màn Article mà chính panel vừa mở. File Costing dùng lại
        # context này để không click Costsheet/reload/chuyển tab lần nữa.
        self.active_article_destination: tuple[str, str] | None = None
        self.prepared_category: str | None = None
        self.folder_cache: dict[str, list[dict]] = {}
        # URL tải thật không đưa ra WebView. UI chỉ nhận token ngẫu nhiên và
        # metadata; khi click tải, token được resolve lại trong process Python.
        self.files: dict[str, dict] = {}
        # Kết quả Sample nhiều dòng cũng chỉ đưa token ra UI. Row key dùng để
        # click tiếp trên grid WFX được giữ hoàn toàn trong backend.
        self.sample_file_choices: dict[str, dict] = {}
        # Plan import chứa document/selector-independent diff ở process Python.
        # WebView chỉ nhận token ngẫu nhiên; plan tự hết hạn sau 15 phút.
        self.costing_plans: dict[str, dict] = {}
        # Workbook Style chỉ tồn tại trong process qua token ngẫu nhiên. Mỗi
        # lần chạy chỉ chuẩn bị một dòng và luôn dừng trước Save.
        self.style_imports: dict[str, dict] = {}

    # -- state hooks do panel gọi -----------------------------------------
    def reset_context(self) -> None:
        """Mất phiên / đổi Division / login lại: kết quả & Master cũ hết hiệu lực."""
        self.result = None
        self.active_article_destination = None
        self.prepared_category = None
        self.files.clear()
        self.sample_file_choices.clear()
        self.costing_plans.clear()
        self.style_imports.clear()

    def reset_for_account_change(self) -> None:
        """Đổi tài khoản: cache cây folder theo user cũ cũng không còn dùng được."""
        self.folder_cache.clear()
        self.result = None
        self.active_article_destination = None
        self.prepared_category = None
        self.files.clear()
        self.sample_file_choices.clear()
        self.costing_plans.clear()
        self.style_imports.clear()

    # -- helpers -----------------------------------------------------------
    def default_folder_for_account(
        self,
        preferences: Mapping | None = None,
    ) -> dict | None:
        panel = self._panel
        if preferences is None:
            preferences = panel._prefs.load_prefs(base_dir=panel._base_dir)
        folder = preferences["catalog_default_folder"]
        if not folder:
            return None
        user_id = str(panel._account().get("user_id") or "").strip()
        owner = str(folder.get("user_id") or "").strip()
        if not user_id or owner.casefold() != user_id.casefold():
            return None
        return folder

    def _master_folder(self, category_name: str) -> dict:
        return {
            "category_name": category_name,
            "category_value": constants.CATEGORIES.get(category_name, ""),
            "user_id": str(self._panel._account().get("user_id") or "").strip(),
            "node_id": "",
            "node_code": "Master",
            "name": "Master",
            "path": ["Master"],
            "path_label": "Master",
            "kind": "master",
            "depth": 0,
        }

    def _cached_folders(self, category_name: str) -> list[dict] | None:
        cached = self.folder_cache.get(category_name)
        if cached:
            return cached
        panel = self._panel
        account = panel._account()
        loader = getattr(panel._prefs, "load_catalog_folder_cache", None)
        if not callable(loader):
            return None
        persisted = loader(
            str(account.get("user_id") or ""),
            category_name,
            base_dir=panel._base_dir,
        )
        if persisted:
            self.folder_cache[category_name] = persisted
            return persisted
        return None

    def _publish_file_scan(self, result: dict) -> dict:
        """Giữ URL trong backend, chỉ trả token + metadata an toàn cho UI."""
        if result.get("code") != "CATALOG_FILES_SCANNED":
            return result
        self.files.clear()
        public_files: list[dict] = []
        for raw in result.get("files") or []:
            if not isinstance(raw, dict) or not raw.get("download_url"):
                continue
            file_id = uuid.uuid4().hex
            stored = dict(raw)
            stored["file_id"] = file_id
            self.files[file_id] = stored
            public_files.append(
                {
                    "file_id": file_id,
                    "section": str(raw.get("section") or ""),
                    "section_index": int(raw.get("section_index") or 0),
                    "file_name": str(raw.get("file_name") or ""),
                    "comments": str(raw.get("comments") or ""),
                    "uploaded_on": str(raw.get("uploaded_on") or ""),
                    "uploaded_by": str(raw.get("uploaded_by") or ""),
                }
            )
        return {
            **result,
            "files": public_files,
            "file_count": len(public_files),
        }

    def _scan_open_article_files(self, article_code: str) -> dict:
        scanner = getattr(self._panel._login, "scan_catalog_files", None)
        if not callable(scanner):
            return {
                "ok": False,
                "code": "CATALOG_FILES_UNSUPPORTED",
                "message": "Phiên bản tự động hóa chưa hỗ trợ kiểm tra file Style.",
            }
        return self._publish_file_scan(
            scanner(article_code, self._panel._log)
        )

    def _publish_sample_file_choices(self, result: dict) -> dict:
        """Ẩn row key của grid Sample sau token ngẫu nhiên cho WebView."""
        if result.get("code") != "SAMPLE_MULTIPLE_RESULTS":
            return result
        self.sample_file_choices.clear()
        public_samples: list[dict] = []
        for raw in result.get("samples") or []:
            if not isinstance(raw, dict):
                continue
            style_code = str(raw.get("style_code") or "").strip()
            row_key = str(raw.get("row_key") or "").strip()
            if not style_code or not row_key:
                continue
            choice_id = uuid.uuid4().hex
            self.sample_file_choices[choice_id] = {
                "row_key": row_key,
                "style_code": style_code,
            }
            public_samples.append(
                {
                    "choice_id": choice_id,
                    "style_code": style_code,
                    "sample_no": str(raw.get("sample_no") or ""),
                    "created_by": str(raw.get("created_by") or ""),
                    "buyer": str(raw.get("buyer") or ""),
                }
            )
        return {
            **result,
            "samples": public_samples,
            "source": "sample",
        }

    def _sample_files_result(self, article_code: str) -> dict:
        scanned = self._scan_open_article_files(article_code)
        return {
            **scanned,
            "source": "sample",
            "article_code": article_code,
        }

    def _invalidate_catalog_search_only(self) -> None:
        """Sample đã đổi trang WFX; bỏ Catalog context nhưng giữ token file."""
        self.result = None
        self.active_article_destination = None
        self.prepared_category = None

    def _style_group(self, group_id: str) -> dict | None:
        group_id = str(group_id or "").strip()
        return next(
            (
                item
                for item in self.folder_cache.get("Apparel", [])
                if str(item.get("node_id") or "") == group_id
                and str(item.get("kind") or "").casefold() == "group"
            ),
            None,
        )

    def _active_style_import(self, token: str) -> dict | None:
        now = time.monotonic()
        for old_token, review in tuple(self.style_imports.items()):
            if now - float(review.get("created_at") or 0) > STYLE_IMPORT_TTL_SECONDS:
                self.style_imports.pop(old_token, None)
        return self.style_imports.get(str(token or "").strip())

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
            self.style_imports.clear()
            token = uuid.uuid4().hex
            self.style_imports[token] = {
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
        self.style_imports.pop(str(token or "").strip(), None)
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

    # -- workflows ---------------------------------------------------------
    def scan_folders(self, category_name: str, force: bool = False) -> dict:
        """Quét cây folder user được quyền xem, không mở Master."""
        panel = self._panel
        if category_name != "Apparel":
            return {
                "ok": False,
                "code": "CATALOG_DEFAULT_APPAREL_ONLY",
                "message": "Vị trí mặc định chỉ áp dụng cho Apparel.",
            }
        if not force:
            cached = self._cached_folders(category_name)
            if cached:
                return {
                    "ok": True,
                    "code": "CATALOG_FOLDERS_CACHED",
                    "message": "Đã tải cây Catalog đã lưu.",
                    "category": category_name,
                    "value": constants.CATEGORIES[category_name],
                    "folders": cached,
                    "default_folder": self.default_folder_for_account(),
                    **panel._session_status(),
                    **panel._division_state(),
                }
        scan_user_id = str(panel._account().get("user_id") or "").strip()

        def action() -> dict:
            # Reset context CHỈ sau khi đã giành được run lock (bên trong _run).
            # Nếu đặt ở đầu method, một lần gọi bị từ chối ACTION_IN_PROGRESS vẫn
            # xóa mất Catalog đang chuẩn bị của workflow đang chạy.
            self.result = None
            self.active_article_destination = None
            self.prepared_category = None
            self.files.clear()
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            scanner = getattr(panel._login, "scan_catalog_folders", None)
            if not callable(scanner):
                return {
                    "ok": False,
                    "code": "CATALOG_FOLDER_SCAN_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ quét thư mục Catalog.",
                }
            return scanner(category_name, value, panel._log)

        result = panel._run(
            "scan_catalog_folders",
            action,
            {
                "category_name": category_name,
                "force": bool(force),
            },
        )
        if result.get("code") == "CATALOG_FOLDERS_SCANNED":
            current_user_id = str(panel._account().get("user_id") or "").strip()
            if scan_user_id.casefold() != current_user_id.casefold():
                return {
                    "ok": False,
                    "code": "CATALOG_SCAN_ACCOUNT_CHANGED",
                    "message": (
                        "Tài khoản đã đổi trong lúc tải Catalog. "
                        "Hãy mở Catalog lại."
                    ),
                    **panel._session_status(),
                    **panel._division_state(),
                }
            folders = [
                folder
                for folder in result.get("folders", [])
                if isinstance(folder, dict)
                and str(folder.get("node_id") or "").isdigit()
            ]
            self.folder_cache[category_name] = folders
            saver = getattr(panel._prefs, "save_catalog_folder_cache", None)
            if callable(saver):
                try:
                    persisted = saver(
                        scan_user_id,
                        folders,
                        category_name,
                        base_dir=panel._base_dir,
                    )
                    if persisted:
                        folders = persisted
                        result["folders"] = folders
                        self.folder_cache[category_name] = folders
                except OSError:
                    # Cache chỉ là tối ưu UX; scan thành công không được biến
                    # thành lỗi chỉ vì ổ đĩa tạm thời không ghi được.
                    pass
            saved = self.default_folder_for_account()
            if (
                saved
                and saved.get("category_name") == category_name
                and saved.get("node_id")
                and not any(
                    folder.get("node_id") == saved.get("node_id")
                    for folder in folders
                )
            ):
                master = self._master_folder(category_name)
                panel._prefs.save_prefs(
                    base_dir=panel._base_dir,
                    catalog_default_folder=master,
                )
                result["default_folder"] = master
                # `+=` trên key có thể vắng: automation chỉ bảo đảm ok/code,
                # còn `message` là tuỳ chọn. KeyError ở đây xảy ra NGOÀI _run
                # nên không có handler nào biến nó thành PANEL_ERROR.
                result["message"] = (
                    f"{str(result.get('message') or '').rstrip()} "
                    "Folder mặc định cũ không còn quyền truy cập; "
                    "đã chuyển về Master."
                ).strip()
            else:
                result["default_folder"] = saved
        return result

    def set_default_folder(self, category_name: str, node_id: str) -> dict:
        panel = self._panel
        if category_name != "Apparel":
            return {
                "ok": False,
                "code": "CATALOG_DEFAULT_APPAREL_ONLY",
                "message": "Vị trí mặc định chỉ áp dụng cho Apparel.",
            }
        value = constants.CATEGORIES.get(category_name)
        if value is None:
            return {
                "ok": False,
                "code": "CATEGORY_UNKNOWN",
                "message": f"Category lạ: {category_name}",
            }
        node_id = str(node_id or "").strip()
        if not node_id:
            folder = self._master_folder(category_name)
        else:
            folder = next(
                (
                    item
                    for item in self.folder_cache.get(category_name, [])
                    if str(item.get("node_id") or "") == node_id
                ),
                None,
            )
            if folder is None:
                return {
                    "ok": False,
                    "code": "CATALOG_FOLDER_NOT_SCANNED",
                    "message": "Hãy quét lại cây Catalog trước khi chọn folder.",
                }
            folder = {
                **folder,
                "category_name": category_name,
                "category_value": value,
                "user_id": str(panel._account().get("user_id") or "").strip(),
            }
        saved = panel._prefs.save_prefs(
            base_dir=panel._base_dir,
            catalog_default_folder=folder,
        )["catalog_default_folder"]
        panel._log(
            f"[SETTINGS] Folder Catalog mặc định: "
            f"{saved['path_label'] if saved else 'Master'}"
        )
        return {
            "ok": True,
            "code": "CATALOG_DEFAULT_FOLDER_SAVED",
            "message": (
                f"Đã đặt folder mặc định: {saved['path_label']}."
                if saved
                else "Đã đặt folder mặc định: Master."
            ),
            "default_folder": saved,
        }

    def browse(self, category_name: str) -> dict:
        """Mở Category để duyệt; riêng Apparel dùng folder mặc định đã lưu."""
        panel = self._panel

        def action() -> dict:
            # Reset context sau khi giành run lock, không phải ở đầu method:
            # tránh xóa Catalog đang chuẩn bị khi lần gọi này bị ACTION_IN_PROGRESS.
            self.result = None
            self.active_article_destination = None
            self.prepared_category = None
            self.files.clear()
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            opener = getattr(panel._login, "open_catalog_folder", None)
            if not callable(opener):
                return {
                    "ok": False,
                    "code": "CATALOG_FOLDER_OPEN_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ mở thư mục mặc định.",
                }
            saved = (
                self.default_folder_for_account()
                if category_name == "Apparel"
                else None
            )
            node_id = (
                str(saved.get("node_id") or "")
                if saved and saved.get("category_name") == category_name
                else ""
            )
            result = opener(category_name, value, node_id, panel._log)
            if result.get("code") != "CATALOG_FOLDER_STALE":
                return result

            master = self._master_folder(category_name)
            if category_name == "Apparel":
                panel._prefs.save_prefs(
                    base_dir=panel._base_dir,
                    catalog_default_folder=master,
                )
            fallback = opener(category_name, value, "", panel._log)
            if fallback.get("ok"):
                return {
                    **fallback,
                    "code": "CATALOG_FOLDER_FALLBACK",
                    "message": (
                        (
                            "Folder mặc định không còn tồn tại hoặc đã mất quyền. "
                            "Đã chuyển về Master."
                        )
                        if category_name == "Apparel"
                        else f"Đã mở Category {category_name}."
                    ),
                    **(
                        {"default_folder": master}
                        if category_name == "Apparel"
                        else {}
                    ),
                }
            return result

        return panel._run(
            "browse_catalog",
            action,
            {"category_name": category_name},
        )

    def prepare(self, category_name: str) -> dict:
        panel = self._panel

        def action() -> dict:
            # Reset context sau khi giành run lock (bên trong _run). Đặt ở đầu
            # method sẽ xóa Catalog đang chuẩn bị ngay cả khi lần gọi này bị
            # từ chối ACTION_IN_PROGRESS vì một workflow khác đang chạy.
            self.result = None
            self.active_article_destination = None
            self.prepared_category = None
            self.files.clear()
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            if hasattr(panel._login, "prepare_catalog_master"):
                return panel._login.prepare_catalog_master(
                    category_name,
                    value,
                    panel._log,
                )
            opened = panel._login.open_module(
                "Catalog", panel._login.CATALOG_XPATH, panel._log
            )
            if not opened.get("ok"):
                return opened
            return panel._login.set_catalog_category(
                category_name, value, panel._log
            )

        result = panel._run(
            "prepare_catalog", action, {"category_name": category_name}
        )
        if result.get("code") == "CATEGORY_SELECTED":
            self.prepared_category = str(category_name)
        return result

    def find(
        self,
        method_name: str,
        category_name: str,
        filter_kind: str,
        query: str,
        destination,
    ) -> dict:
        panel = self._panel

        def action() -> dict:
            self.files.clear()
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            if self.prepared_category != category_name:
                return {
                    "ok": False,
                    "code": "CATALOG_PREPARE_REQUIRED",
                    "message": (
                        f"Hãy bấm Mở Catalog để chuẩn bị Category {category_name} "
                        "trước khi tìm."
                    ),
                }
            if not hasattr(panel._login, "find_in_open_catalog"):
                return {
                    "ok": False,
                    "code": "CATALOG_SEARCH_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ tìm theo từng bước.",
                }
            return panel._login.find_in_open_catalog(
                category_name,
                filter_kind,
                query,
                panel._log,
            )

        result = panel._run(
            method_name,
            action,
            {
                "category_name": category_name,
                "query": query,
                "destination": destination,
            },
        )
        if result.get("code") == "RESULT_OPENED" and result.get("article_code"):
            self.active_article_destination = None
            self.result = {
                "article_code": str(result["article_code"]),
                "category_name": str(category_name),
                "filter_kind": str(filter_kind),
                "query": str(query).strip(),
                "style_status": result.get("style_status"),
            }
        else:
            self.result = None
            self.active_article_destination = None
            if result.get("code") == "CATALOG_SEARCH_CONTEXT_LOST":
                self.prepared_category = None
        return result

    def _validate_catalog_action(
        self,
        request: CatalogActionRequest,
    ) -> dict | None:
        if request.category_name not in constants.CATEGORIES:
            return {
                "ok": False,
                "code": "CATEGORY_UNKNOWN",
                "message": f"Category lạ: {request.category_name}",
            }
        if request.filter_kind not in {
            "code",
            "buyer_reference",
            "article_name",
        }:
            return {
                "ok": False,
                "code": "INVALID_FILTER",
                "message": "Kiểu tìm Catalog không hợp lệ.",
            }
        if (
            request.filter_kind == "buyer_reference"
            and request.category_name != "Apparel"
        ) or (
            request.filter_kind == "article_name"
            and request.category_name == "Apparel"
        ):
            return {
                "ok": False,
                "code": "INVALID_FILTER",
                "message": (
                    "Apparel tìm theo Buyer Reference; "
                    "Category khác tìm theo Article Name."
                ),
            }
        if not request.query:
            return {
                "ok": False,
                "code": "QUERY_REQUIRED",
                "message": "Vui lòng nhập nội dung cần tìm.",
            }
        if request.destination not in {None, "costsheet", "bom", "files"}:
            return {
                "ok": False,
                "code": "ARTICLE_DESTINATION_UNKNOWN",
                "message": "Chỉ hỗ trợ mở Costing, BOM hoặc File.",
            }
        if (
            request.destination in {"costsheet", "bom"}
            and request.category_name != "Apparel"
        ):
            return {
                "ok": False,
                "code": "APPAREL_ONLY",
                "message": "Costing và BOM chỉ hỗ trợ Category Apparel.",
            }
        return None

    def _matches_current_result(self, request: CatalogActionRequest) -> bool:
        current = self.result
        return bool(
            current
            and current["category_name"] == request.category_name
            and current["filter_kind"] == request.filter_kind
            and current["query"].casefold() == request.query.casefold()
        )

    def _remember_search_result(
        self,
        search_result: dict,
        request: CatalogActionRequest,
    ) -> None:
        self.active_article_destination = None
        article_code = str(search_result.get("article_code") or "").strip()
        if search_result.get("code") not in {
            "RESULT_OPENED",
            "CATALOG_DESTINATION_OPENED",
        } or not article_code:
            self.result = None
            return
        self.result = {
            "article_code": article_code,
            "category_name": request.category_name,
            "filter_kind": request.filter_kind,
            "query": request.query,
            "style_status": search_result.get("style_status"),
        }

    def _reuse_current_catalog_result(
        self,
        request: CatalogActionRequest,
    ) -> dict | None:
        if not request.destination or not self._matches_current_result(request):
            return None
        current = self.result
        if current is None:
            return None
        article_code = str(current["article_code"])
        direct_result = (
            self._scan_open_article_files(article_code)
            if request.destination == "files"
            else self._panel._login.open_catalog_destination(
                article_code,
                request.destination,
                self._panel._log,
            )
        )
        if direct_result.get("code") in {
            "CATALOG_RESULT_EXPIRED",
            "CATALOG_FILES_CONTEXT_EXPIRED",
        }:
            self.result = None
            self.active_article_destination = None
            return None
        return {
            **direct_result,
            "article_code": article_code,
            "style_status": current.get("style_status"),
            "category": request.category_name,
            "filter_kind": request.filter_kind,
            "query": request.query,
        }

    def _run_catalog_finder(self, request: CatalogActionRequest) -> dict:
        combined_finder = getattr(
            self._panel._login,
            "find_and_open_catalog_destination",
            None,
        )
        if (
            request.destination in {"costsheet", "bom"}
            and callable(combined_finder)
        ):
            return combined_finder(
                request.category_name,
                request.filter_kind,
                request.query,
                request.destination,
                self._panel._log,
            )
        return self._panel._login.find_in_open_catalog(
            request.category_name,
            request.filter_kind,
            request.query,
            self._panel._log,
        )

    def _prepare_catalog_search(self, request: CatalogActionRequest) -> dict:
        login = self._panel._login
        category_value = constants.CATEGORIES[request.category_name]
        if hasattr(login, "prepare_catalog_master"):
            return login.prepare_catalog_master(
                request.category_name,
                category_value,
                self._panel._log,
            )
        prepared = login.open_module(
            "Catalog",
            login.CATALOG_XPATH,
            self._panel._log,
        )
        if not prepared.get("ok"):
            return prepared
        return login.set_catalog_category(
            request.category_name,
            category_value,
            self._panel._log,
        )

    def _find_catalog_result(
        self,
        request: CatalogActionRequest,
    ) -> tuple[dict, bool]:
        can_reuse_master = (
            self.prepared_category == request.category_name
            and hasattr(self._panel._login, "find_in_open_catalog")
        )
        if can_reuse_master:
            search_result = self._run_catalog_finder(request)
            if search_result.get("code") != "CATALOG_SEARCH_CONTEXT_LOST":
                return search_result, True
            self.prepared_category = None
            self.active_article_destination = None

        prepared = self._prepare_catalog_search(request)
        if not prepared.get("ok"):
            return prepared, False
        self.prepared_category = request.category_name
        return self._run_catalog_finder(request), True

    def _open_destination_after_search(
        self,
        search_result: dict,
        request: CatalogActionRequest,
    ) -> dict:
        article_code = str(search_result["article_code"])
        opened = (
            self._scan_open_article_files(article_code)
            if request.destination == "files"
            else self._panel._login.open_catalog_destination(
                article_code,
                request.destination,
                self._panel._log,
            )
        )
        if not opened.get("ok"):
            return opened
        return {
            **search_result,
            **opened,
            "style_status": search_result.get("style_status"),
            "article_code": search_result.get("article_code"),
            "category": request.category_name,
            "filter_kind": request.filter_kind,
            "query": request.query,
        }

    def _execute_catalog_action(self, request: CatalogActionRequest) -> dict:
        validation_error = self._validate_catalog_action(request)
        if validation_error is not None:
            return validation_error
        if request.destination != "files":
            self.files.clear()

        reused_result = self._reuse_current_catalog_result(request)
        if reused_result is not None:
            return reused_result

        search_result, search_performed = self._find_catalog_result(request)
        if not search_performed:
            return search_result
        self._remember_search_result(search_result, request)
        if search_result.get("code") == "CATALOG_DESTINATION_OPENED":
            return search_result
        if (
            search_result.get("code") != "RESULT_OPENED"
            or not request.destination
        ):
            return search_result
        return self._open_destination_after_search(search_result, request)

    def action(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        destination: str | None = None,
        *,
        method_name: str = "catalog_action",
    ) -> dict:
        """Một nút cho Tìm/Costing/BOM/File, luôn tìm trong Master."""
        request = CatalogActionRequest(
            category_name=str(category_name or ""),
            filter_kind=str(filter_kind or "").casefold(),
            query=str(query or "").strip(),
            destination=str(destination or "").casefold() or None,
        )
        result = self._panel._run(
            method_name,
            lambda: self._execute_catalog_action(request),
            {
                "category_name": request.category_name,
                "filter_kind": request.filter_kind,
                "query": request.query,
                "destination": request.destination,
            },
        )
        if result.get("code") in {
            "CATALOG_SEARCH_CONTEXT_LOST",
            "CATALOG_RESULT_EXPIRED",
            "CATALOG_FILES_CONTEXT_EXPIRED",
        }:
            self.prepared_category = None
            self.result = None
            self.active_article_destination = None
        elif (
            result.get("ok")
            and request.destination in {"costsheet", "bom"}
            and str(result.get("article_code") or "").strip()
        ):
            self.active_article_destination = (
                str(result["article_code"]).strip().casefold(),
                request.destination,
            )
        elif (
            result.get("code") == "RESULT_OPENED"
            and not request.destination
        ):
            self.active_article_destination = None
        return result

    def _open_costing_for_file_action(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
    ) -> dict:
        if str(category_name or "") != "Apparel":
            return {
                "ok": False,
                "code": "APPAREL_ONLY",
                "message": "Import/export Costing chỉ hỗ trợ Category Apparel.",
            }
        query = str(query or "").strip()
        current = self.result
        if (
            current
            and self.active_article_destination
            and self.active_article_destination[1] == "costsheet"
            and str(current.get("category_name") or "") == "Apparel"
            and str(current.get("filter_kind") or "").casefold()
            == str(filter_kind or "").casefold()
            and str(current.get("query") or "").casefold() == query.casefold()
            and self.active_article_destination[0]
            == str(current.get("article_code") or "").casefold()
        ):
            return {
                "ok": True,
                "code": "COSTING_CONTEXT_REUSED",
                "message": "Dùng lại Costing đang mở; không chuyển tab hoặc reload.",
                "article_code": str(current.get("article_code") or ""),
                "style_status": current.get("style_status"),
                "category": "Apparel",
                "filter_kind": str(filter_kind or ""),
                "query": query,
            }
        return self.action(
            category_name,
            filter_kind,
            query,
            "costsheet",
        )

    def export_costing(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
        scan_article_options: bool = False,
    ) -> dict:
        """Xuất XLSX từ kết quả app hoặc từ riêng tab Costing đang chọn."""
        return self._panel.run_composite(
            lambda: self._export_costing_steps(
                category_name,
                filter_kind,
                query,
                file_path,
                scan_article_options,
            )
        )

    @staticmethod
    def _article_cache_sections(document: Mapping) -> list[dict]:
        sections = []
        for section in document.get("sections") or ():
            codes = list(section.get("article_code_options") or ())
            names = list(section.get("article_name_options") or ())
            options = [
                {
                    "article_code": str(codes[index] if index < len(codes) else ""),
                    "article_name": str(names[index] if index < len(names) else ""),
                }
                for index in range(max(len(codes), len(names)))
                if (index < len(codes) and str(codes[index]).strip())
                or (index < len(names) and str(names[index]).strip())
            ]
            if options:
                sections.append(
                    {
                        "section_key": str(section.get("section_key") or ""),
                        "section_name": str(section.get("name") or ""),
                        "options": options,
                    }
                )
        return sections

    @staticmethod
    def _server_options_for_costing_section(
        section: Mapping,
        options: list[Mapping],
    ) -> list[dict]:
        section_identity = " ".join(
            (
                str(section.get("section_key") or ""),
                str(section.get("name") or ""),
            )
        ).casefold()
        if "fabric" in section_identity:
            category = "textiles/fabric"
            prefix = "f"
        elif "trim" in section_identity:
            category = "trims"
            prefix = "t"
        else:
            return []
        return [
            dict(option)
            for option in options
            if str(option.get("article_code") or "")
            .strip()
            .casefold()
            .startswith(prefix)
            and str(option.get("article_category") or "").strip().casefold()
            == category
        ]

    def _merge_cached_article_options(
        self,
        document: dict,
        *,
        scanned: bool,
    ) -> tuple[int, str]:
        panel = self._panel
        user_id = str(panel._account().get("user_id") or "").strip()
        sections = self._article_cache_sections(document)
        server_cache = article_library.load_cached(panel._base_dir)
        source = "server" if server_cache else ""
        if server_cache:
            cached = list(server_cache.get("sections") or ())
        elif scanned and sections:
            saver = getattr(panel._prefs, "save_costing_article_cache", None)
            if callable(saver):
                sections = saver(
                    user_id,
                    sections,
                    base_dir=panel._base_dir,
                )
            return sum(len(section["options"]) for section in sections), "scan"
        else:
            loader = getattr(panel._prefs, "load_costing_article_cache", None)
            cached = (
                loader(user_id, base_dir=panel._base_dir)
                if callable(loader)
                else None
            )
            source = "cache" if cached else ""
        if not cached:
            return 0, "none"
        by_key = {
            str(section.get("section_key") or "").casefold(): section
            for section in cached
        }
        by_name = {
            str(section.get("section_name") or "").casefold(): section
            for section in cached
        }
        wildcard = by_key.get("*")
        count = 0
        for section in document.get("sections") or ():
            match = by_key.get(
                str(section.get("section_key") or "").casefold()
            ) or by_name.get(
                str(section.get("name") or "").casefold()
            ) or wildcard
            if not match:
                continue
            options = list(match.get("options") or ())
            if source == "server":
                options = self._server_options_for_costing_section(
                    section,
                    options,
                )
            if not options:
                continue
            section["article_lookup_options"] = [
                {
                    "article_code": str(
                        option.get("article_code") or ""
                    ).strip(),
                    "article_name": str(
                        option.get("article_name") or ""
                    ).strip(),
                }
                for option in options
            ]
            section["article_code_options"] = list(
                dict.fromkeys(
                    str(option.get("article_code") or "").strip()
                    for option in options
                    if str(option.get("article_code") or "").strip()
                )
            )
            section["article_name_options"] = list(
                dict.fromkeys(
                    str(option.get("article_name") or "").strip()
                    for option in options
                    if str(option.get("article_name") or "").strip()
                )
            )
            count += len(options)
        return count, source if count else "none"

    @staticmethod
    def _special_cost_section_key(section: Mapping) -> str:
        for value in (section.get("section_key"), section.get("name")):
            token = "".join(
                character
                for character in str(value or "").casefold()
                if character.isalnum()
            )
            if token in _SPECIAL_COST_SECTION_KEYS:
                return token
        return ""

    @classmethod
    def _special_cost_sections(cls, document: Mapping) -> list[dict]:
        sections: dict[str, dict] = {}
        for section in document.get("sections") or ():
            key = cls._special_cost_section_key(section)
            if not key:
                continue
            sections[key] = {
                "section_key": key,
                "options": list(section.get("article_options") or ()),
            }
        if set(sections) != _SPECIAL_COST_SECTION_KEYS:
            return []
        return [sections[key] for key in sorted(sections)]

    def costing_special_options_state(
        self,
        preferences: Mapping | None = None,
    ) -> dict:
        panel = self._panel
        if preferences is None:
            preferences = panel._prefs.load_prefs(base_dir=panel._base_dir)
        loader = getattr(
            panel._prefs,
            "load_costing_special_options_cache",
            None,
        )
        user_id = str(panel._account().get("user_id") or "").strip()
        division_key = str(panel._current_division or "").strip()
        cache = (
            loader(user_id, division_key, base_dir=panel._base_dir)
            if callable(loader) and user_id and division_key
            else None
        )
        return {
            "available": cache is not None,
            "saved_at": float((cache or {}).get("saved_at") or 0),
            "expires_at": float((cache or {}).get("expires_at") or 0),
            "rescan_next": preferences.get(
                "costing_special_options_rescan", False
            )
            is True,
        }

    def set_costing_special_options_rescan(self, value: bool) -> dict:
        preferences = self._panel._prefs.save_prefs(
            base_dir=self._panel._base_dir,
            costing_special_options_rescan=boolean(value),
        )
        state = self.costing_special_options_state(preferences)
        return {
            "ok": True,
            "code": "COSTING_SPECIAL_OPTIONS_RESCAN_UPDATED",
            "message": (
                "Lần Costing kế tiếp sẽ quét lại ba danh sách chi phí."
                if state["rescan_next"]
                else "Đã dùng lại cache ba danh sách chi phí khi còn hạn."
            ),
            "costing_special_options": state,
        }

    def _special_cost_scan_plan(self) -> dict:
        state = self.costing_special_options_state()
        panel = self._panel
        loader = getattr(
            panel._prefs,
            "load_costing_special_options_cache",
            None,
        )
        user_id = str(panel._account().get("user_id") or "").strip()
        division_key = str(panel._current_division or "").strip()
        cache = (
            loader(user_id, division_key, base_dir=panel._base_dir)
            if callable(loader) and user_id and division_key
            else None
        )
        return {
            "scan": state["rescan_next"] or cache is None,
            "forced": state["rescan_next"],
            "cache": cache,
        }

    def _merge_special_cost_options(
        self,
        document: dict,
        plan: Mapping,
    ) -> dict:
        panel = self._panel
        cache = plan.get("cache")
        if document.get("special_cost_options_scanned") is True:
            sections = self._special_cost_sections(document)
            saver = getattr(
                panel._prefs,
                "save_costing_special_options_cache",
                None,
            )
            user_id = str(panel._account().get("user_id") or "").strip()
            division_key = str(panel._current_division or "").strip()
            cache = (
                saver(
                    user_id,
                    division_key,
                    sections,
                    base_dir=panel._base_dir,
                )
                if callable(saver) and sections
                else None
            )
            if cache is not None and plan.get("forced"):
                panel._prefs.save_prefs(
                    base_dir=panel._base_dir,
                    costing_special_options_rescan=False,
                )
        if cache:
            options_by_key = {
                str(section.get("section_key") or "").casefold(): list(
                    section.get("options") or ()
                )
                for section in cache.get("sections") or ()
            }
            for section in document.get("sections") or ():
                key = self._special_cost_section_key(section)
                if key in options_by_key:
                    section["article_options"] = options_by_key[key]
        return self.costing_special_options_state()

    def article_library_status(self) -> dict:
        return article_library.status(self._panel._base_dir)

    def sync_article_library(self) -> dict:
        return article_library.sync(
            self._panel._base_dir,
            self._panel._log,
        )

    def suggest_articles(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        limit: int = 20,
    ) -> dict:
        category = str(category_name or "").strip()
        kind = str(filter_kind or "").strip().casefold()
        value = str(query or "").strip()
        if len(value) < 2:
            return {
                "ok": True,
                "code": "ARTICLE_SUGGESTIONS",
                "query": value,
                "suggestions": [],
                **self.article_library_status(),
            }
        cached = article_library.load_cached(self._panel._base_dir)
        if not cached:
            return {
                "ok": True,
                "code": "ARTICLE_SUGGESTIONS",
                "query": value,
                "suggestions": [],
                **self.article_library_status(),
            }
        needle = value.casefold()
        maximum = bounded_int(limit, 20, minimum=1, maximum=50)
        field_by_kind = {
            "code": "article_code",
            "buyer_reference": "buyer_reference",
            "article_name": "article_name",
        }
        search_field = field_by_kind.get(kind)
        if (
            search_field is None
            or (kind == "buyer_reference" and category != "Apparel")
        ):
            return {
                "ok": True,
                "code": "ARTICLE_SUGGESTIONS",
                "query": value,
                "suggestions": [],
                **self.article_library_status(),
            }

        # Chuẩn hóa + khử trùng đã làm sẵn một lần trong article_library; ở đây
        # chỉ còn so khớp chuỗi để mỗi ký tự gõ không phải quét lại cả kho.
        index = article_library.suggestion_index(cached, category, search_field)

        def candidates():
            for (
                searchable_key,
                searchable,
                code,
                name,
                buyer_reference,
                article_category,
            ) in index:
                if searchable_key.startswith(needle):
                    score = 0
                elif needle in searchable_key:
                    score = 1
                else:
                    continue
                yield (
                    score,
                    len(searchable),
                    searchable_key,
                    code,
                    name,
                    buyer_reference,
                    article_category,
                    searchable,
                )

        ranked = nsmallest(maximum, candidates())
        suggestions = [
            {
                "article_code": code,
                "article_name": name,
                "buyer_reference": buyer_reference,
                "article_category": article_category,
                "value": searchable,
            }
            for (
                _score,
                _length,
                _key,
                code,
                name,
                buyer_reference,
                article_category,
                searchable,
            ) in ranked
        ]
        return {
            "ok": True,
            "code": "ARTICLE_SUGGESTIONS",
            "query": value,
            "suggestions": suggestions,
            **self.article_library_status(),
        }

    def _export_costing_steps(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
        scan_article_options: bool = False,
    ) -> dict:
        panel = self._panel
        category_name = str(category_name or "")
        filter_kind = str(filter_kind or "")
        cleaned_query = str(query or "").strip()
        if category_name != "Apparel":
            return {
                "ok": False,
                "code": "APPAREL_ONLY",
                "message": "Import/export Costing chỉ hỗ trợ Category Apparel.",
            }
        try:
            # Validate extension trước khi mở/chạm màn WFX.
            target = Path(str(file_path or "")).expanduser()
            if target.suffix.casefold() != ".xlsx":
                raise CostingWorkbookError(
                    "COSTING_FILE_TYPE_UNSUPPORTED",
                    "Costing chỉ hỗ trợ file .xlsx.",
                )
        except CostingWorkbookError as error:
            return error.as_result()

        article_code = ""
        style_status = None
        if cleaned_query:
            opened = self._open_costing_for_file_action(
                category_name,
                filter_kind,
                cleaned_query,
            )
            if not opened.get("ok"):
                return opened
            article_code = str(opened.get("article_code") or "").strip()
            style_status = opened.get("style_status")

        def action() -> dict:
            special_options_plan = self._special_cost_scan_plan()
            if cleaned_query:
                scanner = getattr(panel._login, "scan_open_costing", None)
            else:
                scanner = getattr(
                    panel._login,
                    "scan_active_open_costing",
                    None,
                )
            if not callable(scanner):
                return {
                    "ok": False,
                    "code": "COSTING_EXPORT_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ đọc Costing.",
                }
            if cleaned_query:
                scan_kwargs = {
                    "style_status": style_status,
                    "require_open": False,
                    "scan_details": True,
                    "log": panel._log,
                    "scan_special_cost_options": special_options_plan["scan"],
                }
                if scan_article_options:
                    scan_kwargs["scan_article_options"] = True
                scanned = scanner(
                    article_code,
                    **scan_kwargs,
                )
            else:
                scan_kwargs = {
                    "require_open": False,
                    "scan_details": True,
                    "log": panel._log,
                    "scan_special_cost_options": special_options_plan["scan"],
                }
                if scan_article_options:
                    scan_kwargs["scan_article_options"] = True
                scanned = scanner(**scan_kwargs)
            if not scanned.get("ok"):
                return scanned
            try:
                document = scanned["costing"]
                special_options_state = self._merge_special_cost_options(
                    document,
                    special_options_plan,
                )
                article_option_count, article_option_source = (
                    self._merge_cached_article_options(
                        document,
                        scanned=bool(scan_article_options),
                    )
                )
                scanned_article_code = str(
                    scanned.get("article_code")
                    or document.get("style_code")
                    or ""
                ).strip()
                output = write_costing_file(document, target)
            except CostingWorkbookError as error:
                return error.as_result()
            summary = costing_file_summary(document, output)
            dropdown_message = {
                "server": (
                    f" Đã dùng {article_option_count} Article từ thư viện server."
                ),
                "scan": (
                    f" Đã quét {article_option_count} Article và lưu cache 7 ngày."
                ),
                "cache": (
                    f" Đã dùng {article_option_count} Article từ cache cho dropdown."
                ),
            }.get(article_option_source, "")
            return {
                "ok": True,
                "code": "COSTING_EXPORTED",
                "message": (
                    f"Đã tải Costing {scanned_article_code} thành {output.name}."
                    f"{dropdown_message}"
                ),
                "article_code": scanned_article_code,
                "export_path": str(output),
                "style_status": {
                    "code": scanned_article_code,
                    "season": str(document.get("season") or ""),
                    "internal_costsheet_status": str(
                        document.get("cost_sheet_status") or ""
                    ),
                },
                "article_option_count": article_option_count,
                "article_option_source": article_option_source,
                "costing_special_options": special_options_state,
                **summary,
            }

        result = panel._run(
            "export_catalog_costing",
            action,
            {
                "category_name": category_name,
                "filter_kind": filter_kind,
                "query": cleaned_query,
                "file_name": target.name,
                "file_format": target.suffix.casefold().lstrip("."),
                "scan_article_options": bool(scan_article_options),
            },
        )
        if result.get("ok") and result.get("article_code"):
            detected_code = str(result["article_code"]).strip()
            self.result = {
                "article_code": detected_code,
                "category_name": category_name,
                "filter_kind": "code",
                "query": detected_code,
                "style_status": result.get("style_status"),
            }
            self.active_article_destination = (
                detected_code.casefold(),
                "costsheet",
            )
        return result

    def inspect_active_costing(self, category_name: str) -> dict:
        """Đọc nhanh identity của đúng tab Costing trước khi mở file dialog."""
        panel = self._panel
        if str(category_name or "") != "Apparel":
            return {
                "ok": False,
                "code": "APPAREL_ONLY",
                "message": "Import/export Costing chỉ hỗ trợ Category Apparel.",
            }

        def action() -> dict:
            inspector = getattr(panel._login, "inspect_active_costing", None)
            if not callable(inspector):
                return {
                    "ok": False,
                    "code": "COSTING_EXPORT_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ đọc thẻ Costing.",
                }
            return inspector(log=panel._log)

        result = panel._run(
            "inspect_active_catalog_costing",
            action,
            {"category_name": "Apparel"},
        )
        if result.get("ok") and result.get("article_code"):
            article_code = str(result["article_code"]).strip()
            self.result = {
                "article_code": article_code,
                "category_name": "Apparel",
                "filter_kind": "code",
                "query": article_code,
                "style_status": result.get("style_status"),
            }
            self.active_article_destination = (
                article_code.casefold(),
                "costsheet",
            )
        return result

    def validate_costing_file(self, file_path: str) -> dict:
        """Validate workbook độc lập; không scan WFX và không tạo dry-run."""
        panel = self._panel
        target = Path(str(file_path or "")).expanduser()

        def action() -> dict:
            try:
                document = read_costing_file(target)
            except CostingWorkbookError as error:
                return error.as_result()
            return {
                "ok": True,
                "code": "COSTING_FILE_VALID",
                "message": (
                    f"File {target.name} hợp lệ; có thể tạo dry-run."
                ),
                "file_name": target.name,
                "style_code": str(document.get("style_code") or ""),
                "section_count": len(document.get("sections") or ()),
                "item_count": len(document.get("items") or ()),
                "field_count": len(document.get("fields") or ()),
                "validation_errors": [],
            }

        return panel._run(
            "validate_catalog_costing_file",
            action,
            {
                "file_name": target.name,
                "file_format": target.suffix.casefold().lstrip("."),
            },
        )

    def _expire_costing_plans(self) -> None:
        cutoff = time.monotonic() - COSTING_PLAN_TTL_SECONDS
        self.costing_plans = {
            token: plan
            for token, plan in self.costing_plans.items()
            if float(plan.get("created_at") or 0) >= cutoff
        }

    def prepare_costing_import(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
    ) -> dict:
        """Đọc file + live Costing và trả dry-run; chưa ghi bất kỳ field nào."""
        return self._panel.run_composite(
            lambda: self._prepare_costing_import_steps(
                category_name, filter_kind, query, file_path
            )
        )

    def _prepare_costing_import_steps(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
    ) -> dict:
        panel = self._panel
        category_name = str(category_name or "")
        filter_kind = str(filter_kind or "")
        cleaned_query = str(query or "").strip()
        if category_name != "Apparel":
            return {
                "ok": False,
                "code": "APPAREL_ONLY",
                "message": "Import/export Costing chỉ hỗ trợ Category Apparel.",
            }
        try:
            imported = read_costing_file(file_path)
        except CostingWorkbookError as error:
            return error.as_result()
        if (
            cleaned_query
            and filter_kind.casefold() == "code"
            and cleaned_query.casefold()
            != str(imported.get("style_code") or "").casefold()
        ):
            return {
                "ok": False,
                "code": "COSTING_STYLE_MISMATCH",
                "message": (
                    "Style Code trong file không khớp Style Code đang nhập."
                ),
                "file_style": str(imported.get("style_code") or ""),
                "query_style": cleaned_query,
            }

        active_tab_only = not cleaned_query
        article_code = ""
        style_status = None
        if not active_tab_only:
            opened = self._open_costing_for_file_action(
                category_name,
                filter_kind,
                cleaned_query,
            )
            if not opened.get("ok"):
                return opened
            article_code = str(opened.get("article_code") or "").strip()
            style_status = opened.get("style_status")

        def action() -> dict:
            special_options_plan = self._special_cost_scan_plan()
            if active_tab_only:
                scanner = getattr(
                    panel._login,
                    "scan_active_open_costing",
                    None,
                )
            else:
                scanner = getattr(panel._login, "scan_open_costing", None)
            if not callable(scanner):
                return {
                    "ok": False,
                    "code": "COSTING_IMPORT_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ đọc Costing.",
                }
            if active_tab_only:
                scanned = scanner(
                    require_open=True,
                    scan_details=True,
                    scan_special_cost_options=special_options_plan["scan"],
                    log=panel._log,
                )
            else:
                scanned = scanner(
                    article_code,
                    style_status=style_status,
                    require_open=True,
                    scan_details=True,
                    scan_special_cost_options=special_options_plan["scan"],
                    log=panel._log,
                )
            if not scanned.get("ok"):
                return scanned
            live_document = scanned["costing"]
            special_options_state = self._merge_special_cost_options(
                live_document,
                special_options_plan,
            )
            live_article_code = str(
                scanned.get("article_code")
                or live_document.get("style_code")
                or ""
            ).strip()
            file_article_code = str(imported.get("style_code") or "").strip()
            if live_article_code.casefold() != file_article_code.casefold():
                return {
                    "ok": False,
                    "code": "COSTING_STYLE_MISMATCH",
                    "message": (
                        "Style Code trong file không khớp tab Costing đang chọn."
                    ),
                    "file_style": file_article_code,
                    "live_style": live_article_code,
                }
            try:
                plan = build_costing_plan(imported, live_document)
            except CostingPlanError as error:
                return error.as_result()
            self._expire_costing_plans()
            token = uuid.uuid4().hex
            self.costing_plans[token] = {
                "created_at": time.monotonic(),
                "article_code": live_article_code,
                "category_name": category_name,
                "filter_kind": filter_kind,
                "query": cleaned_query,
                "active_tab_only": active_tab_only,
                "file_name": Path(str(file_path or "")).name,
                "imported": imported,
                "plan": plan,
            }
            return {
                **plan,
                "plan_token": token,
                "costing_special_options": special_options_state,
                "article_code": live_article_code,
                "style_status": {
                    "code": live_article_code,
                    "season": str(live_document.get("season") or ""),
                    "internal_costsheet_status": "Open",
                },
                "file_name": Path(str(file_path or "")).name,
            }

        result = panel._run(
            "prepare_catalog_costing_import",
            action,
            {
                "category_name": category_name,
                "filter_kind": filter_kind,
                "query": cleaned_query,
                "file_name": Path(str(file_path or "")).name,
                "file_format": Path(str(file_path or "")).suffix.casefold().lstrip("."),
            },
        )
        if result.get("ok") and result.get("article_code"):
            detected_code = str(result["article_code"]).strip()
            self.result = {
                "article_code": detected_code,
                "category_name": category_name,
                "filter_kind": "code",
                "query": detected_code,
                "style_status": result.get("style_status"),
            }
            self.active_article_destination = (
                detected_code.casefold(),
                "costsheet",
            )
        return result

    def clear_costing_plan(self, plan_token: str) -> dict:
        token = str(plan_token or "").strip()
        existed = self.costing_plans.pop(token, None) is not None
        return {
            "ok": True,
            "code": "COSTING_PLAN_CLEARED",
            "message": "Đã hủy bản xem trước Costing." if existed else "Bản xem trước đã hết hạn.",
        }

    def apply_costing(
        self,
        plan_token: str,
        article_resolutions: dict | None = None,
    ) -> dict:
        """Áp dụng đúng plan server-side; WebView không được gửi selector/field."""
        if article_resolutions is not None and not isinstance(
            article_resolutions,
            Mapping,
        ):
            return {
                "ok": False,
                "code": "COSTING_ARTICLE_RESOLUTIONS_INVALID",
                "message": "Danh sách Article đã chọn không hợp lệ.",
            }
        return self._panel.run_composite(
            lambda: self._apply_costing_steps(plan_token, article_resolutions)
        )

    def _apply_costing_steps(
        self,
        plan_token: str,
        article_resolutions: dict | None = None,
    ) -> dict:
        panel = self._panel
        token = str(plan_token or "").strip()
        self._expire_costing_plans()
        cached = self.costing_plans.get(token)
        if cached is None:
            return {
                "ok": False,
                "code": "COSTING_PLAN_EXPIRED",
                "message": "Dry-run Costing đã hết hạn. Hãy import lại file.",
            }
        # Dành cho phase Material Search: chỉ nhận mapping key → Article Code,
        # không nhận selector hay DOM index từ UI.
        resolutions = {
            str(key): str(value).strip()
            for key, value in dict(article_resolutions or {}).items()
            if str(key).strip() and str(value).strip()
        }
        cached["article_resolutions"] = resolutions
        expected_code = str(cached["article_code"])
        active_tab_only = bool(cached.get("active_tab_only"))
        if not active_tab_only:
            reopened = self._open_costing_for_file_action(
                str(cached["category_name"]),
                str(cached["filter_kind"]),
                str(cached["query"]),
            )
            if not reopened.get("ok"):
                return reopened
            reopened_code = str(reopened.get("article_code") or "").strip()
            if reopened_code.casefold() != expected_code.casefold():
                return {
                    "ok": False,
                    "code": "COSTING_STYLE_MISMATCH",
                    "message": (
                        "Style đang mở không còn khớp dry-run. Hãy import lại file."
                    ),
                    "file_style": expected_code,
                    "live_style": reopened_code,
                }

        def action() -> dict:
            applier = getattr(panel._login, "apply_costing_plan", None)
            if not callable(applier):
                return {
                    "ok": False,
                    "code": "COSTING_IMPORT_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ ghi Costing.",
                }
            result = applier(
                expected_code,
                cached["plan"],
                source_document=cached["imported"],
                article_resolutions=resolutions,
                active_tab_only=active_tab_only,
                log=panel._log,
            )
            if result.get("code") == "COSTING_ARTICLE_AMBIGUOUS":
                result = {**result, "plan_token": token}
            if result.get("ok"):
                self.costing_plans.pop(token, None)
            return result

        return panel._run(
            "apply_catalog_costing",
            action,
            {
                "article_code": str(cached["article_code"]),
                "file_name": str(cached.get("file_name") or ""),
                "resolution_count": len(resolutions),
            },
        )

    def download_file(self, file_id: str) -> dict:
        """Tải một file đã quét; WebView không được tự truyền URL tùy ý."""
        panel = self._panel
        file_id = str(file_id or "").strip()

        def action() -> dict:
            file_info = self.files.get(file_id)
            if file_info is None:
                return {
                    "ok": False,
                    "code": "CATALOG_FILE_EXPIRED",
                    "message": "Danh sách file đã hết hiệu lực. Hãy bấm File lại.",
                }
            downloader = getattr(panel._login, "download_catalog_file", None)
            if not callable(downloader):
                return {
                    "ok": False,
                    "code": "CATALOG_FILE_DOWNLOAD_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ tải file.",
                }
            result = downloader(file_info, panel._log)
            if result.get("ok"):
                result["file_id"] = file_id
                result["section"] = str(file_info.get("section") or "")
            return result

        return panel._run(
            "download_catalog_file",
            action,
            {"file_id": file_id},
        )

    def clear_active_costing_dependencies(self) -> dict:
        """Clear mọi dependency của đúng Costing đang chọn và Save."""
        panel = self._panel

        def action() -> dict:
            clearer = getattr(
                panel._login,
                "clear_active_costing_dependencies",
                None,
            )
            if not callable(clearer):
                return {
                    "ok": False,
                    "code": "COSTING_CLEAR_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ Clear All Dependency.",
                }
            return clearer(log=panel._log)

        return panel._run(
            "clear_catalog_costing_dependencies",
            action,
            {"active_tab_only": True},
        )

    def check_sample_files(self, filter_kind: str, query: str) -> dict:
        """Tìm Sample, tự mở Style duy nhất rồi quét file như Catalog."""
        panel = self._panel
        filter_kind = str(filter_kind or "").casefold()
        query = str(query or "").strip()

        def action() -> dict:
            self._invalidate_catalog_search_only()
            self.files.clear()
            self.sample_file_choices.clear()
            finder = getattr(panel._login, "find_sample_file_results", None)
            if not callable(finder):
                return {
                    "ok": False,
                    "code": "SAMPLE_FILES_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ Check File ở Sample List.",
                }
            sample = constants.MODULE_BY_ID["0004_0056_4070"]
            found = finder(
                sample["xpath"],
                filter_kind,
                query,
                panel._log,
            )
            if found.get("code") == "SAMPLE_MULTIPLE_RESULTS":
                return self._publish_sample_file_choices(found)
            if found.get("code") != "SAMPLE_STYLE_OPENED":
                return {**found, "source": "sample"}
            article_code = str(found.get("article_code") or "").strip()
            return self._sample_files_result(article_code)

        return panel._run(
            "check_sample_files",
            action,
            {"filter_kind": filter_kind, "query": query},
        )

    def check_sample_files_with_filters(
        self,
        values: Mapping[str, str],
    ) -> dict:
        """Check File Sample theo các filter mà người dùng đã nhập."""
        panel = self._panel
        cleaned_values = {
            name: str(values.get(name) or "").strip()
            for name in ("sample_no", "style", "created_by", "buyer")
        }
        active_filters = [
            name for name, value in cleaned_values.items() if value
        ]

        def action() -> dict:
            self._invalidate_catalog_search_only()
            self.files.clear()
            self.sample_file_choices.clear()
            finder = getattr(
                panel._login,
                "find_sample_file_results_with_filters",
                None,
            )
            if not callable(finder):
                return {
                    "ok": False,
                    "code": "SAMPLE_FILES_UNSUPPORTED",
                    "message": (
                        "Phiên bản tự động hóa chưa hỗ trợ lọc nhiều điều kiện "
                        "ở Sample List."
                    ),
                }
            sample = constants.MODULE_BY_ID["0004_0056_4070"]
            found = finder(sample["xpath"], cleaned_values, panel._log)
            if found.get("code") == "SAMPLE_MULTIPLE_RESULTS":
                return self._publish_sample_file_choices(found)
            if found.get("code") != "SAMPLE_STYLE_OPENED":
                return {**found, "source": "sample"}
            article_code = str(found.get("article_code") or "").strip()
            return self._sample_files_result(article_code)

        return panel._run(
            "check_sample_files",
            action,
            {"filter_kind": "multiple", "filter_kinds": active_filters},
        )

    def open_sample_file_choice(self, choice_id: str) -> dict:
        """Mở lựa chọn Sample đã token hóa và tiếp tục quét file."""
        panel = self._panel
        choice_id = str(choice_id or "").strip()

        def action() -> dict:
            choice = self.sample_file_choices.get(choice_id)
            if choice is None:
                return {
                    "ok": False,
                    "code": "SAMPLE_RESULT_EXPIRED",
                    "message": (
                        "Lựa chọn Sample đã hết hiệu lực. "
                        "Hãy bấm Check File lại."
                    ),
                }
            opener = getattr(panel._login, "open_sample_file_result", None)
            if not callable(opener):
                return {
                    "ok": False,
                    "code": "SAMPLE_FILES_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ mở Style từ Sample.",
                }
            opened = opener(
                choice["row_key"],
                choice["style_code"],
                panel._log,
            )
            if opened.get("code") != "SAMPLE_STYLE_OPENED":
                return opened
            self.sample_file_choices.clear()
            return self._sample_files_result(choice["style_code"])

        return panel._run(
            "open_sample_file_choice",
            action,
            {"choice_id": choice_id},
        )

    def open_destination(self, destination: str, article_code: str) -> dict:
        """Mở Costing/BOM từ kết quả tìm hiện tại, không search Catalog lại."""
        panel = self._panel

        def action() -> dict:
            current = self.result
            expected = str(article_code or "").strip()
            if current is None or not expected:
                return {
                    "ok": False,
                    "code": "CATALOG_RESULT_REQUIRED",
                    "message": "Hãy bấm Tìm và mở một style trước.",
                }
            if current["article_code"].casefold() != expected.casefold():
                self.result = None
                self.active_article_destination = None
                return {
                    "ok": False,
                    "code": "CATALOG_RESULT_CHANGED",
                    "message": "Kết quả tìm đã thay đổi. Hãy bấm Tìm lại.",
                }
            if current["category_name"] != "Apparel":
                return {
                    "ok": False,
                    "code": "APPAREL_ONLY",
                    "message": "Costing và BOM chỉ hỗ trợ Category Apparel.",
                }
            if not hasattr(panel._login, "open_catalog_destination"):
                return {
                    "ok": False,
                    "code": "CATALOG_DESTINATION_UNSUPPORTED",
                    "message": "Phiên bản tự động hóa chưa hỗ trợ bước này.",
                }
            return panel._login.open_catalog_destination(
                expected,
                str(destination or "").casefold(),
                panel._log,
            )

        result = panel._run(
            "open_catalog_destination",
            action,
            {
                "destination": str(destination or "").casefold(),
                "article_code": str(article_code or "").strip(),
            },
        )
        if (
            result.get("ok")
            and str(result.get("article_code") or "").strip()
            and str(destination or "").casefold() in {"costsheet", "bom"}
        ):
            self.active_article_destination = (
                str(result["article_code"]).strip().casefold(),
                str(destination).casefold(),
            )
        return result
