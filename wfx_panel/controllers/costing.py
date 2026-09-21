"""Luong file Costing: export, kiem tra, dry-run va apply.

Costing luon thao tac tren Article ma Catalog vua mo, nen controller nay
nhan CatalogController lam cong tac vien: no doc lai ket qua tim va man
Article dang mo thay vi chay lai ca luong Catalog.

Plan import chi song trong process Python duoi dang token ngau nhien va tu
het han sau 15 phut; WebView khong bao gio nhan selector hay DOM index."""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.controllers.catalog import CatalogController

from wfx_panel import article_library
from wfx_panel.coercion import boolean
from wfx_panel.costing_planner import CostingPlanError, build_costing_plan
from wfx_panel.costing_workbook import (
    CostingWorkbookError,
    costing_file_summary,
    read_costing_file,
    write_costing_file,
)

COSTING_PLAN_TTL_SECONDS = 15 * 60
_SPECIAL_COST_SECTION_KEYS = frozenset(
    {"cmcosts", "productioncosts", "indirectcosts"}
)


class CostingController:
    def __init__(self, catalog: CatalogController) -> None:
        self._catalog = catalog
        self._panel = catalog._panel
        # Plan import chua document/diff doc lap selector o process Python.
        # WebView chi nhan token ngau nhien; plan tu het han sau 15 phut.
        self.plans: dict[str, dict] = {}

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

    def special_options_state(
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

    def set_special_options_rescan(self, value: bool) -> dict:
        preferences = self._panel._prefs.save_prefs(
            base_dir=self._panel._base_dir,
            costing_special_options_rescan=boolean(value),
        )
        state = self.special_options_state(preferences)
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
        state = self.special_options_state()
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
        return self.special_options_state()

    def _open_for_file_action(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
    ) -> dict:
        catalog = self._catalog
        if str(category_name or "") != "Apparel":
            return {
                "ok": False,
                "code": "APPAREL_ONLY",
                "message": "Import/export Costing chỉ hỗ trợ Category Apparel.",
            }
        query = str(query or "").strip()
        current = catalog.result
        if (
            current
            and catalog.active_article_destination
            and catalog.active_article_destination[1] == "costsheet"
            and str(current.get("category_name") or "") == "Apparel"
            and str(current.get("filter_kind") or "").casefold()
            == str(filter_kind or "").casefold()
            and str(current.get("query") or "").casefold() == query.casefold()
            and catalog.active_article_destination[0]
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
        return catalog.action(
            category_name,
            filter_kind,
            query,
            "costsheet",
        )

    def export(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
        scan_article_options: bool = False,
    ) -> dict:
        """Xuất XLSX từ kết quả app hoặc từ riêng tab Costing đang chọn."""
        return self._panel.run_composite(
            lambda: self._export_steps(
                category_name,
                filter_kind,
                query,
                file_path,
                scan_article_options,
            )
        )

    def _export_steps(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
        scan_article_options: bool = False,
    ) -> dict:
        catalog = self._catalog
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
            opened = self._open_for_file_action(
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
            catalog.result = {
                "article_code": detected_code,
                "category_name": category_name,
                "filter_kind": "code",
                "query": detected_code,
                "style_status": result.get("style_status"),
            }
            catalog.active_article_destination = (
                detected_code.casefold(),
                "costsheet",
            )
        return result

    def inspect_active(self, category_name: str) -> dict:
        """Đọc nhanh identity của đúng tab Costing trước khi mở file dialog."""
        catalog = self._catalog
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
            catalog.result = {
                "article_code": article_code,
                "category_name": "Apparel",
                "filter_kind": "code",
                "query": article_code,
                "style_status": result.get("style_status"),
            }
            catalog.active_article_destination = (
                article_code.casefold(),
                "costsheet",
            )
        return result

    def validate_file(self, file_path: str) -> dict:
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

    def _expire_plans(self) -> None:
        cutoff = time.monotonic() - COSTING_PLAN_TTL_SECONDS
        self.plans = {
            token: plan
            for token, plan in self.plans.items()
            if float(plan.get("created_at") or 0) >= cutoff
        }

    def prepare_import(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
    ) -> dict:
        """Đọc file + live Costing và trả dry-run; chưa ghi bất kỳ field nào."""
        return self._panel.run_composite(
            lambda: self._prepare_import_steps(
                category_name, filter_kind, query, file_path
            )
        )

    def _prepare_import_steps(
        self,
        category_name: str,
        filter_kind: str,
        query: str,
        file_path: str,
    ) -> dict:
        catalog = self._catalog
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
            opened = self._open_for_file_action(
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
            self._expire_plans()
            token = uuid.uuid4().hex
            self.plans[token] = {
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
            catalog.result = {
                "article_code": detected_code,
                "category_name": category_name,
                "filter_kind": "code",
                "query": detected_code,
                "style_status": result.get("style_status"),
            }
            catalog.active_article_destination = (
                detected_code.casefold(),
                "costsheet",
            )
        return result

    def clear_plan(self, plan_token: str) -> dict:
        token = str(plan_token or "").strip()
        existed = self.plans.pop(token, None) is not None
        return {
            "ok": True,
            "code": "COSTING_PLAN_CLEARED",
            "message": "Đã hủy bản xem trước Costing." if existed else "Bản xem trước đã hết hạn.",
        }

    def apply(
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
            lambda: self._apply_steps(plan_token, article_resolutions)
        )

    def _apply_steps(
        self,
        plan_token: str,
        article_resolutions: dict | None = None,
    ) -> dict:
        panel = self._panel
        token = str(plan_token or "").strip()
        self._expire_plans()
        cached = self.plans.get(token)
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
            reopened = self._open_for_file_action(
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
                self.plans.pop(token, None)
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

    def clear_active_dependencies(self) -> dict:
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
