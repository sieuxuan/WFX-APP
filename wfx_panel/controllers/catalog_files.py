"""File đính kèm của Article và kết quả file của Sample.

URL tải thật KHÔNG được đưa ra WebView: UI chỉ nhận token ngẫu nhiên kèm
metadata, và token được resolve lại trong process Python lúc bấm tải."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.controllers.catalog import CatalogController

from wfx_panel import constants


class ArticleFileController:
    def __init__(self, catalog: CatalogController) -> None:
        self._catalog = catalog
        self._panel = catalog._panel
        # UI chỉ nhận token; URL tải và row key WFX ở lại backend.
        self.tokens: dict[str, dict] = {}
        self.sample_choices: dict[str, dict] = {}

    def _publish_file_scan(self, result: dict) -> dict:
        """Giữ URL trong backend, chỉ trả token + metadata an toàn cho UI."""
        if result.get("code") != "CATALOG_FILES_SCANNED":
            return result
        self.tokens.clear()
        public_files: list[dict] = []
        for raw in result.get("files") or []:
            if not isinstance(raw, dict) or not raw.get("download_url"):
                continue
            file_id = uuid.uuid4().hex
            stored = dict(raw)
            stored["file_id"] = file_id
            self.tokens[file_id] = stored
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
        self.sample_choices.clear()
        public_samples: list[dict] = []
        for raw in result.get("samples") or []:
            if not isinstance(raw, dict):
                continue
            style_code = str(raw.get("style_code") or "").strip()
            row_key = str(raw.get("row_key") or "").strip()
            if not style_code or not row_key:
                continue
            choice_id = uuid.uuid4().hex
            self.sample_choices[choice_id] = {
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

    def download_file(self, file_id: str) -> dict:
        """Tải một file đã quét; WebView không được tự truyền URL tùy ý."""
        panel = self._panel
        file_id = str(file_id or "").strip()

        def action() -> dict:
            file_info = self.tokens.get(file_id)
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

    def check_sample_files_with_filters(
        self,
        values: Mapping[str, str],
    ) -> dict:
        """Check File Sample theo các filter mà người dùng đã nhập."""
        catalog = self._catalog
        panel = self._panel
        cleaned_values = {
            name: str(values.get(name) or "").strip()
            for name in ("sample_no", "style", "created_by", "buyer")
        }
        active_filters = [
            name for name, value in cleaned_values.items() if value
        ]

        def action() -> dict:
            catalog._invalidate_catalog_search_only()
            self.tokens.clear()
            self.sample_choices.clear()
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
            choice = self.sample_choices.get(choice_id)
            if choice is None:
                return {
                    "ok": False,
                    "code": "SAMPLE_RESULT_EXPIRED",
                    "source": "sample",
                    "message": (
                        "Lựa chọn Sample đã hết hiệu lực. "
                        "Hãy bấm Xem file đính kèm lại."
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
                if opened.get("code") == "SAMPLE_RESULT_EXPIRED":
                    # Grid đã khác lúc phát token, nên CẢ danh sách đang hiện
                    # đều trỏ vào dòng cũ — không riêng dòng vừa bấm. Giữ lại
                    # token là mời người dùng bấm tiếp vào dòng đã chết.
                    self.sample_choices.clear()
                return {**opened, "source": "sample"}
            self.sample_choices.clear()
            return self._sample_files_result(choice["style_code"])

        return panel._run(
            "open_sample_file_choice",
            action,
            {"choice_id": choice_id},
        )
