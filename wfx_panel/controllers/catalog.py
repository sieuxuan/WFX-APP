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

from collections.abc import Mapping
from dataclasses import dataclass
from heapq import nsmallest
from typing import TYPE_CHECKING

from wfx_panel import constants
from wfx_panel.coercion import bounded_int
from wfx_panel.controllers.catalog_files import ArticleFileController
from wfx_panel.controllers.catalog_folders import CatalogFolderController
from wfx_panel.controllers.catalog_style import StyleImportController
from wfx_panel.controllers.costing import CostingController
from wfx_panel.stores import article_library


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
        # URL tải thật không đưa ra WebView. UI chỉ nhận token ngẫu nhiên và
        # metadata; khi click tải, token được resolve lại trong process Python.
        # Kết quả Sample nhiều dòng cũng chỉ đưa token ra UI. Row key dùng để
        # click tiếp trên grid WFX được giữ hoàn toàn trong backend.
        # Luồng file Costing sống trong controller riêng; nó đọc lại kết quả
        # Catalog hiện tại thay vì chạy lại cả luồng tìm Style.
        self.folders = CatalogFolderController(self)
        self.costing = CostingController(self)
        self.style = StyleImportController(self)
        self.files_view = ArticleFileController(self)
        # Workbook Style chỉ tồn tại trong process qua token ngẫu nhiên. Mỗi
        # lần chạy chỉ chuẩn bị một dòng và luôn dừng trước Save.

    # -- state hooks do panel gọi -----------------------------------------
    def reset_context(self) -> None:
        """Mất phiên / đổi Division / login lại: kết quả & Master cũ hết hiệu lực."""
        self.result = None
        self.active_article_destination = None
        self.prepared_category = None
        self.files_view.tokens.clear()
        self.files_view.sample_choices.clear()
        self.costing.plans.clear()
        self.style.imports.clear()

    def reset_for_account_change(self) -> None:
        """Đổi tài khoản: cache cây folder theo user cũ cũng không còn dùng được."""
        self.folders.cache.clear()
        self.result = None
        self.active_article_destination = None
        self.prepared_category = None
        self.files_view.tokens.clear()
        self.files_view.sample_choices.clear()
        self.costing.plans.clear()
        self.style.imports.clear()

    def default_folder_for_account(self, preferences: Mapping | None=None) -> dict | None:
        return self.folders.default_folder_for_account(preferences)

    def _master_folder(self, category_name: str) -> dict:
        return self.folders._master_folder(category_name)

    def _cached_folders(self, category_name: str) -> list[dict] | None:
        return self.folders._cached_folders(category_name)

    def _scan_open_article_files(self, article_code: str) -> dict:
        return self.files_view._scan_open_article_files(article_code)

    def _invalidate_catalog_search_only(self) -> None:
        """Sample đã đổi trang WFX; bỏ Catalog context nhưng giữ token file."""
        self.result = None
        self.active_article_destination = None
        self.prepared_category = None

    def scan_folders(self, category_name: str, force: bool=False) -> dict:
        return self.folders.scan_folders(category_name, force)

    def set_default_folder(self, category_name: str, node_id: str) -> dict:
        return self.folders.set_default_folder(category_name, node_id)

    def browse(self, category_name: str) -> dict:
        """Mở Category để duyệt; riêng Apparel dùng folder mặc định đã lưu."""
        panel = self._panel

        def action() -> dict:
            # Reset context sau khi giành run lock, không phải ở đầu method:
            # tránh xóa Catalog đang chuẩn bị khi lần gọi này bị ACTION_IN_PROGRESS.
            self.result = None
            self.active_article_destination = None
            self.prepared_category = None
            self.files_view.tokens.clear()
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
            self.files_view.tokens.clear()
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
            self.files_view.tokens.clear()
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
            self.files_view.tokens.clear()

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
