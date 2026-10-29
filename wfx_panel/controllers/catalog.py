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
from pathlib import Path
from typing import TYPE_CHECKING

from wfx_panel import constants
from wfx_panel.coercion import boolean, bounded_int
from wfx_panel.controllers import catalog_query
from wfx_panel.controllers.catalog_files import ArticleFileController
from wfx_panel.controllers.catalog_folders import CatalogFolderController
from wfx_panel.controllers.catalog_style import StyleImportController
from wfx_panel.controllers.costing import CostingController
from wfx_panel.stores import article_library, extracted_articles
from wfx_panel.stores.catalog_recent import CatalogRecentStore
from wfx_panel.version import APP_VERSION


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
    @property
    def recent(self) -> CatalogRecentStore:
        # Tạo khi dùng: store chỉ giữ đường dẫn, và panel giả trong test của
        # module khác không có ``_base_dir``.
        return CatalogRecentStore(self._panel._base_dir)

    def _forget_search(self) -> None:
        """Kết quả tìm, popup đang mở và Master đã chuẩn bị đều hết hiệu lực."""
        self.result = None
        self.active_article_destination = None
        self.prepared_category = None

    def _forget_search_and_files(self) -> None:
        """Flow sắp mở lại Catalog: token file của Style cũ cũng hết hiệu lực."""
        self._forget_search()
        self.files_view.tokens.clear()

    def reset_context(self) -> None:
        """Mất phiên / đổi Division / login lại: kết quả & Master cũ hết hiệu lực."""
        self._forget_search_and_files()
        self.files_view.sample_choices.clear()
        self.costing.plans.clear()
        self.style.imports.clear()

    def reset_for_account_change(self) -> None:
        """Đổi tài khoản: cache cây folder theo user cũ cũng không còn dùng được."""
        self.folders.cache.clear()
        self.reset_context()

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
        self._forget_search()

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
            self._forget_search_and_files()
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
            self._forget_search_and_files()
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

    def auto_prepare(self, category_name: str) -> dict:
        """Chuẩn bị Master khi người dùng vào module, chưa cần bấm Tìm.

        Chỉ chạy khi người dùng đã bật công tắc ``catalog_auto_prepare`` và
        phiên đang sống: không mở lại Chrome, không đăng nhập hộ
        (``auto_prepare_catalog`` nằm trong ``AUTO_RELOGIN_EXCLUDED_METHODS``),
        và automation tự bỏ qua nếu tab WFX đang có việc dở.
        """
        panel = self._panel
        category = str(category_name or "")
        value = constants.CATEGORIES.get(category)
        auto_prepare = getattr(panel._login, "auto_prepare_catalog_master", None)
        if not panel._prefs.load_prefs(panel._base_dir).get("catalog_auto_prepare"):
            reason = "Chưa bật tự mở Catalog."
        elif self.prepared_category == category:
            reason = "Catalog đã sẵn sàng."
        elif value is None:
            reason = f"Category lạ: {category}"
        elif not panel._session_active:
            reason = "Chưa có phiên WFX đang hoạt động."
        elif not callable(auto_prepare):
            reason = "Phiên bản tự động hóa chưa hỗ trợ tự mở Catalog."
        else:
            reason = ""
        if reason:
            return {
                "ok": True,
                "code": "CATALOG_AUTO_PREPARE_SKIPPED",
                "message": reason,
                "category": category,
                "prepared": self.prepared_category == category,
            }

        def action() -> dict:
            if self.prepared_category != category:
                self._forget_search_and_files()
            return auto_prepare(category, value, panel._log)

        # Lượt người dùng không bấm: không ghi lịch sử tác vụ, không đẩy kết
        # quả qua result sink (UI tự đọc giá trị trả về và không bật lỗi).
        result = panel._run(
            "auto_prepare_catalog",
            action,
            {"category_name": category},
            record_job=False,
            emit_result=False,
        )
        if result.get("code") == "CATEGORY_SELECTED":
            self.prepared_category = category
        return {**result, "prepared": self.prepared_category == category}

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
        # Popup Article không lên (CATALOG_DESTINATION_FAILED) vẫn là Style đã
        # tìm đúng: giữ lại để lần bấm Costing/BOM sau probe popup trước, thay vì
        # mở lại Catalog và lọc lần hai.
        if search_result.get("code") not in {
            "RESULT_OPENED",
            "CATALOG_DESTINATION_OPENED",
            "CATALOG_DESTINATION_FAILED",
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
            self.files_view._scan_open_article_files(
                article_code,
                popup_reused=bool(search_result.get("article_popup_reused")),
            )
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
        category = str(category_name or "")
        resolved_kind, resolved_query = self.resolve_query(
            category, filter_kind, query
        )
        request = CatalogActionRequest(
            category_name=category,
            filter_kind=resolved_kind,
            query=resolved_query,
            destination=str(destination or "").casefold() or None,
        )
        result = self._panel._run(
            method_name,
            lambda: self._with_style_details(
                request,
                self._execute_catalog_action(request),
            ),
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
            self._forget_search()
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

    def resolve_query(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
    ) -> tuple[str, str]:
        """Đổi kiểu ``auto`` của ô tìm gộp thành Code/Buyer Ref/Article Name."""
        kind = str(filter_kind or "").strip().casefold()
        value = str(query or "").strip()
        if kind != catalog_query.AUTO_KIND:
            return kind, value
        document = article_library.load_cached(self._panel._base_dir)
        resolved_kind, resolved_query, reason = catalog_query.resolve(
            str(category_name or ""), kind, value, document
        )
        if reason.startswith("library_") and reason != "library_code":
            self._panel._log(
                "[CATALOG] Thư viện Article: giá trị nhập khớp đúng một Code "
                f"{resolved_query}; tìm thẳng theo Code."
            )
        return resolved_kind, resolved_query

    def _library_details(
        self,
        category_name: str,
        codes: list[str],
    ) -> dict[str, tuple[str, str]]:
        """``code.casefold() -> (Article Name, Buyer Reference)`` từ thư viện."""
        wanted = {code.casefold() for code in codes if code}
        cached = article_library.load_cached(self._panel._base_dir) if wanted else None
        if not cached:
            return {}
        found: dict[str, tuple[str, str]] = {}
        for (
            _key,
            _searchable,
            code,
            name,
            buyer_reference,
            _category,
        ) in article_library.suggestion_index(cached, category_name, "article_code"):
            folded = code.casefold()
            if folded in wanted and folded not in found:
                found[folded] = (name, buyer_reference)
        return found

    def _with_style_details(
        self,
        request: CatalogActionRequest,
        result: dict,
    ) -> dict:
        """Gắn tên Style cho danh sách chọn và ghi nhớ Style vừa mở.

        Đường nhanh GetData đã có tên từ server; luồng DOM chỉ đọc được Code
        nên lấy từ Thư viện Article. Thiếu ở cả hai thì để trống.
        """
        code = result.get("code")
        if code == "MULTIPLE_RESULTS" and isinstance(result.get("styles"), list):
            styles = [dict(style) for style in result["styles"]]
            details = self._library_details(
                request.category_name,
                [str(style.get("code") or "") for style in styles],
            )
            for style in styles:
                name, buyer_reference = details.get(
                    str(style.get("code") or "").casefold(),
                    ("", ""),
                )
                style["article_name"] = str(style.get("article_name") or "") or name
                style["buyer_reference"] = (
                    str(style.get("buyer_reference") or "") or buyer_reference
                )
            return {**result, "styles": styles}
        article_code = str(result.get("article_code") or "").strip()
        if not (
            result.get("ok")
            and article_code
            and code in {"RESULT_OPENED", "CATALOG_DESTINATION_OPENED", "CATALOG_FILES_SCANNED"}
        ):
            return result
        name, buyer_reference = self._library_details(
            request.category_name, [article_code]
        ).get(article_code.casefold(), ("", ""))
        label = (
            buyer_reference or name
            if request.category_name == "Apparel"
            else name
        )
        user_id = str(self._panel._account().get("user_id") or "")
        try:
            recent = self.recent.remember(
                user_id, request.category_name, article_code, label
            )
        except OSError:
            recent = self.recent.load(user_id, request.category_name)
        return {**result, "recent_styles": recent}

    def recent_styles(self, category_name: str) -> dict:
        user_id = str(self._panel._account().get("user_id") or "")
        return {
            "ok": True,
            "code": "CATALOG_RECENT_STYLES",
            "category": str(category_name or ""),
            "recent_styles": self.recent.load(user_id, str(category_name or "")),
        }

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
        if kind == catalog_query.AUTO_KIND:
            kind = (
                "code"
                if catalog_query.looks_like_code(category, value)
                else catalog_query.secondary_kind(category)
            )
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

    def probe_data_source(self, category_name: str = "Apparel") -> dict:
        """Chẩn đoán quản trị: ghi request nạp dữ liệu của Catalog Grid.

        Chỉ đọc, kết quả là file JSON cục bộ trong ``diagnostics/``; không gửi
        telemetry nội dung. Flow mở lại Master nên kết quả tìm cũ hết hiệu lực
        giống ``prepare``.
        """
        panel = self._panel
        category_name = str(category_name or "Apparel").strip() or "Apparel"
        denied = panel._admin_mode_error()
        if denied:
            return denied

        def action() -> dict:
            self._forget_search_and_files()
            value = constants.CATEGORIES.get(category_name)
            if value is None:
                return {
                    "ok": False,
                    "code": "CATEGORY_UNKNOWN",
                    "message": f"Category lạ: {category_name}",
                }
            return panel._login.probe_catalog_data_source(
                category_name,
                value,
                Path(panel._base_dir) / "diagnostics",
                panel._log,
                app_version=APP_VERSION,
            )

        result = panel._run(
            "probe_catalog_data_source",
            action,
            {"category_name": category_name},
        )
        if result.get("code") == "CATALOG_DATA_SOURCE_PROBED":
            self.prepared_category = category_name
        return result

    def extract_articles(
        self,
        categories: list[str] | None = None,
        publish: bool = True,
    ) -> dict:
        """Quản trị: lấy toàn bộ Article từ WFX, thay thư viện rồi publish.

        Chỉ gọi ``fetch`` trong tab WFX, không điều hướng nên không làm mất
        Catalog/kết quả tìm đang mở. Danh sách rỗng nghĩa là mọi Category.
        Bước thay thư viện + publish là IO/HTTP thuần nên chạy SAU ``_run()``,
        không giữ automation worker.
        """
        result = self._run_article_extract(categories)
        if result.get("code") != "CATALOG_ARTICLES_EXTRACTED" or not result.get(
            "file_path"
        ):
            return result
        installed = extracted_articles.install_and_publish(
            self._panel._base_dir,
            result["file_path"],
            extracted_categories=result.get("categories") or {},
            all_categories=constants.CATEGORIES,
            publish=boolean(publish, True),
            log=self._panel._log,
        )
        return {
            **result,
            **installed,
            "extract_message": result.get("message"),
            "file_path": result["file_path"],
        }

    def _run_article_extract(self, categories: list[str] | None) -> dict:
        panel = self._panel
        denied = panel._admin_mode_error()
        if denied:
            return denied
        wanted = [
            str(name).strip()
            for name in (categories or ())
            if str(name or "").strip()
        ] or list(constants.CATEGORIES)
        unknown = [name for name in wanted if name not in constants.CATEGORIES]
        if unknown:
            return {
                "ok": False,
                "code": "CATEGORY_UNKNOWN",
                "message": f"Category lạ: {', '.join(unknown)}",
            }
        selected = {name: constants.CATEGORIES[name] for name in wanted}
        return panel._run(
            "extract_catalog_articles",
            lambda: panel._login.extract_catalog_articles(
                selected,
                Path(panel._base_dir) / "exports",
                panel._log,
                app_version=APP_VERSION,
            ),
            {"categories": wanted},
        )
