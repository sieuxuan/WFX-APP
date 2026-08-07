"""Báo cáo Color Combination - Production: cascade tham số và tải hàng loạt."""

from __future__ import annotations

import re
from collections.abc import Mapping

REPORT_ID = "color_combination_production"
REPORT_NAME = "Color Combination - Production"
POSTBACK_TIMEOUT_SECONDS = 45.0
LEVEL_LABELS = {
    "division": "OC Division",
    "buyer": "Buyer",
    "season": "Season",
    "style_ref": "BuyerStyleReference",
}
CASCADE_KEYS = ("division", "buyer", "season")
STYLE_CODE_LABEL = "StyleCode"
SIZE_VISIBILITY_LABEL = "SizeVisibility"

_TRAILING_DIGITS = re.compile(r"(\d+)\s*$")


def _style_code_rank(label: str) -> int | None:
    match = _TRAILING_DIGITS.search(str(label or ""))
    return int(match.group(1)) if match else None


def pick_style_code(
    options: list[Mapping[str, str]],
) -> dict[str, str] | None:
    """Chọn style mới nhất: mã có số đuôi lớn nhất, hòa thì lấy option sau."""
    cleaned = [dict(option) for option in options or () if option]
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    ranked = [
        (rank, index, option)
        for index, option in enumerate(cleaned)
        if (rank := _style_code_rank(option.get("label", ""))) is not None
    ]
    if not ranked:
        return cleaned[-1]
    return max(ranked, key=lambda item: (item[0], item[1]))[2]
