"""Chuẩn hoá khoá field/item Costing.

Workbook và DOM live phải sinh ra cùng một khoá thì planner mới ghép được
dòng file với dòng WFX."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from wfx_panel.automation.costing.constants import _KEY_CLEAN_RE


def _clean_key(value: Any, fallback: str) -> str:
    cleaned = _KEY_CLEAN_RE.sub("_", str(value or "").strip()).strip("_")
    return cleaned or fallback


def _costing_semantic_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _base_costing_field_key(field: Mapping[str, Any]) -> str:
    return re.sub(
        r"__\d+$",
        "",
        str(field.get("field_key") or ""),
    ).casefold()
