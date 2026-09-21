"""Nguồn option Article cho form Costing: cache, snapshot và quét lại.

Ba danh sách dùng chung của CM Costs / Production Costs / Indirect Costs chỉ
quét một lần trong 7 ngày, cache theo User ID + Division. Công tắc quét lại
mặc định off, chỉ ép đúng lần Export/Import kế tiếp rồi tự off sau khi quét
và lưu cache thành công — và KHÔNG được bỏ qua scan Color/Size hay dependency."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wfx_panel.controllers.costing import CostingController

from wfx_panel.coercion import boolean
from wfx_panel.stores import article_library

_SPECIAL_COST_SECTION_KEYS = frozenset(
    {"cmcosts", "productioncosts", "indirectcosts"}
)


class CostingOptionController:
    def __init__(self, costing: CostingController) -> None:
        self._costing = costing
        self._panel = costing._panel

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
