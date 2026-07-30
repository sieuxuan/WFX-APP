"""Điều phối riêng luồng Catalog (browse/prepare/find/Costing/BOM + cây folder).

Tách khỏi ``PanelAPI`` để bridge không còn là god-object: toàn bộ state Catalog
(kết quả tìm hiện tại, category đã chuẩn bị, cache cây folder) và logic sống ở
đây. Controller mượn hạ tầng chung của panel (``_run`` khoá + lịch sử, ``_account``,
``_prefs``, ``_log``, ``_login``) qua tham chiếu ``panel`` — cùng package nên coupling
chặt là chấp nhận được, đổi lại panel gọn và luồng Catalog test được độc lập.

Hành vi giữ NGUYÊN so với bản cũ trong panel_api: cùng method_name cho ``_run``
(job history/screenshot/retry phụ thuộc), cùng thứ tự set/observe state.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from wfx_panel import constants
from wfx_panel.costing_planner import CostingPlanError, build_costing_plan
from wfx_panel.costing_workbook import (
    CostingWorkbookError,
    costing_file_summary,
    read_costing_file,
    write_costing_file,
)

COSTING_PLAN_TTL_SECONDS = 15 * 60

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
        # Plan import chứa document/selector-independent diff ở process Python.
        # WebView chỉ nhận token ngẫu nhiên; plan tự hết hạn sau 15 phút.
        self.costing_plans: dict[str, dict] = {}

    # -- state hooks do panel gọi -----------------------------------------
    def reset_context(self) -> None:
        """Mất phiên / đổi Division / login lại: kết quả & Master cũ hết hiệu lực."""
        self.result = None
        self.active_article_destination = None
        self.prepared_category = None
        self.files.clear()
        self.costing_plans.clear()

    def reset_for_account_change(self) -> None:
        """Đổi tài khoản: cache cây folder theo user cũ cũng không còn dùng được."""
        self.folder_cache.clear()
        self.result = None
        self.active_article_destination = None
        self.prepared_category = None
        self.files.clear()
        self.costing_plans.clear()

    # -- helpers -----------------------------------------------------------
    def default_for_account(self) -> dict | None:
        panel = self._panel
        folder = panel._prefs.load_prefs(
            base_dir=panel._base_dir
        )["catalog_default_folder"]
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
                "message": "Bản automation chưa hỗ trợ kiểm tra file style.",
            }
        return self._publish_file_scan(
            scanner(article_code, self._panel._log)
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
                    "default_folder": self.default_for_account(),
                    **panel._session_status(),
                    **panel._division_state(),
                }
        scan_user_id = str(panel._account().get("user_id") or "").strip()

        def action() -> dict:
            # Reset context CHỈ sau khi đã giành được run lock (bên trong _run).
            # Nếu đặt ở đầu method, một lần gọi bị từ chối ACTION_IN_PROGRESS vẫn
            # xoá mất Catalog đang chuẩn bị của workflow đang chạy.
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
                    "message": "Bản automation chưa hỗ trợ quét folder Catalog.",
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
            saved = self.default_for_account()
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
                result["message"] += (
                    " Folder mặc định cũ không còn quyền truy cập; "
                    "đã chuyển về Master."
                )
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
            # tránh xoá Catalog đang chuẩn bị khi lần gọi này bị ACTION_IN_PROGRESS.
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
                    "message": "Bản automation chưa hỗ trợ mở folder mặc định.",
                }
            saved = (
                self.default_for_account()
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
            # method sẽ xoá Catalog đang chuẩn bị ngay cả khi lần gọi này bị
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
                    "message": "Bản automation chưa hỗ trợ tìm theo từng bước.",
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
        panel = self._panel
        category_name = str(category_name or "")
        filter_kind = str(filter_kind or "").casefold()
        query = str(query or "").strip()
        destination = str(destination or "").casefold() or None

        def matches_current() -> bool:
            current = self.result
            return bool(
                current
                and current["category_name"] == category_name
                and current["filter_kind"] == filter_kind
                and current["query"].casefold() == query.casefold()
            )

        def remember(search: dict) -> None:
            self.active_article_destination = None
            article_code = str(search.get("article_code") or "").strip()
            if search.get("code") in {
                "RESULT_OPENED",
                "CATALOG_DESTINATION_OPENED",
            } and article_code:
                self.result = {
                    "article_code": article_code,
                    "category_name": category_name,
                    "filter_kind": filter_kind,
                    "query": query,
                    "style_status": search.get("style_status"),
                }
            else:
                self.result = None

        def action() -> dict:
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            if filter_kind not in {"code", "buyer_reference"}:
                return {
                    "ok": False,
                    "code": "INVALID_FILTER",
                    "message": "Kiểu tìm Catalog không hợp lệ.",
                }
            if not query:
                return {
                    "ok": False,
                    "code": "QUERY_REQUIRED",
                    "message": "Vui lòng nhập nội dung cần tìm.",
                }
            if destination not in {None, "costsheet", "bom", "files"}:
                return {
                    "ok": False,
                    "code": "ARTICLE_DESTINATION_UNKNOWN",
                    "message": "Chỉ hỗ trợ mở Costing, BOM hoặc File.",
                }
            if destination in {"costsheet", "bom"} and category_name != "Apparel":
                return {
                    "ok": False,
                    "code": "APPAREL_ONLY",
                    "message": "Costing và BOM chỉ hỗ trợ Category Apparel.",
                }
            if destination != "files":
                self.files.clear()

            if destination and matches_current():
                direct = (
                    self._scan_open_article_files(self.result["article_code"])
                    if destination == "files"
                    else panel._login.open_catalog_destination(
                        self.result["article_code"],
                        destination,
                        panel._log,
                    )
                )
                expired_codes = {
                    "CATALOG_RESULT_EXPIRED",
                    "CATALOG_FILES_CONTEXT_EXPIRED",
                }
                if direct.get("code") not in expired_codes:
                    return {
                        **direct,
                        "article_code": self.result["article_code"],
                        "style_status": self.result.get("style_status"),
                        "category": category_name,
                        "filter_kind": filter_kind,
                        "query": query,
                    }
                self.result = None
                self.active_article_destination = None

            search: dict | None = None
            if (
                self.prepared_category == category_name
                and hasattr(panel._login, "find_in_open_catalog")
            ):
                combined_finder = getattr(
                    panel._login,
                    "find_and_open_catalog_destination",
                    None,
                )
                if (
                    destination in {"costsheet", "bom"}
                    and callable(combined_finder)
                ):
                    search = combined_finder(
                        category_name,
                        filter_kind,
                        query,
                        destination,
                        panel._log,
                    )
                else:
                    search = panel._login.find_in_open_catalog(
                        category_name,
                        filter_kind,
                        query,
                        panel._log,
                    )
                if search.get("code") == "CATALOG_SEARCH_CONTEXT_LOST":
                    search = None
                    self.prepared_category = None
                    self.active_article_destination = None

            if search is None:
                if hasattr(panel._login, "prepare_catalog_master"):
                    prepared = panel._login.prepare_catalog_master(
                        category_name,
                        value,
                        panel._log,
                    )
                else:
                    prepared = panel._login.open_module(
                        "Catalog",
                        panel._login.CATALOG_XPATH,
                        panel._log,
                    )
                    if prepared.get("ok"):
                        prepared = panel._login.set_catalog_category(
                            category_name,
                            value,
                            panel._log,
                        )
                if not prepared.get("ok"):
                    return prepared
                self.prepared_category = category_name
                combined_finder = getattr(
                    panel._login,
                    "find_and_open_catalog_destination",
                    None,
                )
                if (
                    destination in {"costsheet", "bom"}
                    and callable(combined_finder)
                ):
                    search = combined_finder(
                        category_name,
                        filter_kind,
                        query,
                        destination,
                        panel._log,
                    )
                else:
                    search = panel._login.find_in_open_catalog(
                        category_name,
                        filter_kind,
                        query,
                        panel._log,
                    )

            remember(search)
            if search.get("code") == "CATALOG_DESTINATION_OPENED":
                return search
            if search.get("code") != "RESULT_OPENED" or not destination:
                return search

            opened = (
                self._scan_open_article_files(str(search["article_code"]))
                if destination == "files"
                else panel._login.open_catalog_destination(
                    str(search["article_code"]),
                    destination,
                    panel._log,
                )
            )
            if opened.get("ok"):
                return {
                    **search,
                    **opened,
                    "style_status": search.get("style_status"),
                    "article_code": search.get("article_code"),
                    "category": category_name,
                    "filter_kind": filter_kind,
                    "query": query,
                }
            return opened

        result = panel._run(
            method_name,
            action,
            {
                "category_name": category_name,
                "filter_kind": filter_kind,
                "query": query,
                "destination": destination,
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
            and destination in {"costsheet", "bom"}
            and str(result.get("article_code") or "").strip()
        ):
            self.active_article_destination = (
                str(result["article_code"]).strip().casefold(),
                destination,
            )
        elif result.get("code") == "RESULT_OPENED" and not destination:
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
    ) -> dict:
        """Xuất XLSX từ kết quả app hoặc từ riêng tab Costing đang chọn."""
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
                    "message": "Bản automation chưa hỗ trợ đọc Costing.",
                }
            if cleaned_query:
                scanned = scanner(
                    article_code,
                    style_status=style_status,
                    require_open=False,
                    scan_details=True,
                    log=panel._log,
                )
            else:
                scanned = scanner(
                    require_open=False,
                    scan_details=True,
                    log=panel._log,
                )
            if not scanned.get("ok"):
                return scanned
            try:
                document = scanned["costing"]
                scanned_article_code = str(
                    scanned.get("article_code")
                    or document.get("style_code")
                    or ""
                ).strip()
                output = write_costing_file(document, target)
            except CostingWorkbookError as error:
                return error.as_result()
            summary = costing_file_summary(document, output)
            return {
                "ok": True,
                "code": "COSTING_EXPORTED",
                "message": (
                    f"Đã tải Costing {scanned_article_code} thành {output.name}."
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
                    "message": "Bản automation chưa hỗ trợ đọc tab Costing.",
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
                    "message": "Bản automation chưa hỗ trợ đọc Costing.",
                }
            if active_tab_only:
                scanned = scanner(
                    require_open=True,
                    scan_details=True,
                    log=panel._log,
                )
            else:
                scanned = scanner(
                    article_code,
                    style_status=style_status,
                    require_open=True,
                    scan_details=True,
                    log=panel._log,
                )
            if not scanned.get("ok"):
                return scanned
            live_document = scanned["costing"]
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
            "message": "Đã huỷ dry-run Costing." if existed else "Dry-run đã hết hạn.",
        }

    def apply_costing(
        self,
        plan_token: str,
        article_resolutions: dict | None = None,
    ) -> dict:
        """Áp dụng đúng plan server-side; WebView không được gửi selector/field."""
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
                    "message": "Bản automation chưa hỗ trợ ghi Costing.",
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
                    "message": "Bản automation chưa hỗ trợ tải file.",
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
                    "message": "Bản automation chưa hỗ trợ bước này.",
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
