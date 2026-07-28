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

import uuid
from typing import TYPE_CHECKING

from wfx_panel import constants

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI


class CatalogController:
    def __init__(self, panel: PanelAPI) -> None:
        self._panel = panel
        # Kết quả Catalog duy nhất vừa được mở. Costing/BOM phải dùng đúng
        # popup này, không được chạy lại toàn bộ Catalog từ đầu.
        self.result: dict[str, str] | None = None
        self.prepared_category: str | None = None
        self.folder_cache: dict[str, list[dict]] = {}
        # URL tải thật không đưa ra WebView. UI chỉ nhận token ngẫu nhiên và
        # metadata; khi click tải, token được resolve lại trong process Python.
        self.files: dict[str, dict] = {}

    # -- state hooks do panel gọi -----------------------------------------
    def reset_context(self) -> None:
        """Mất phiên / đổi Division / login lại: kết quả & Master cũ hết hiệu lực."""
        self.result = None
        self.prepared_category = None
        self.files.clear()

    def reset_for_account_change(self) -> None:
        """Đổi tài khoản: cache cây folder theo user cũ cũng không còn dùng được."""
        self.folder_cache.clear()
        self.result = None
        self.prepared_category = None
        self.files.clear()

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
            self.result = {
                "article_code": str(result["article_code"]),
                "category_name": str(category_name),
                "filter_kind": str(filter_kind),
                "query": str(query).strip(),
            }
        else:
            self.result = None
            if result.get("code") == "CATALOG_SEARCH_CONTEXT_LOST":
                self.prepared_category = None
        return result

    def action(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        destination: str | None = None,
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
            article_code = str(search.get("article_code") or "").strip()
            if search.get("code") == "RESULT_OPENED" and article_code:
                self.result = {
                    "article_code": article_code,
                    "category_name": category_name,
                    "filter_kind": filter_kind,
                    "query": query,
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
                        "category": category_name,
                        "filter_kind": filter_kind,
                        "query": query,
                    }
                self.result = None

            search: dict | None = None
            if (
                self.prepared_category == category_name
                and hasattr(panel._login, "find_in_open_catalog")
            ):
                search = panel._login.find_in_open_catalog(
                    category_name,
                    filter_kind,
                    query,
                    panel._log,
                )
                if search.get("code") == "CATALOG_SEARCH_CONTEXT_LOST":
                    search = None
                    self.prepared_category = None

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
                search = panel._login.find_in_open_catalog(
                    category_name,
                    filter_kind,
                    query,
                    panel._log,
                )

            remember(search)
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
            "catalog_action",
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
        return result

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

        return panel._run(
            "open_catalog_destination",
            action,
            {
                "destination": str(destination or "").casefold(),
                "article_code": str(article_code or "").strip(),
            },
        )
