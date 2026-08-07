"""Báo cáo Color Combination - Production: cascade tham số và tải hàng loạt."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

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
_FORBIDDEN_FILE_CHARS = re.compile(r'[\\/:*?"<>|]')


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


def safe_file_stem(style_ref: str, style_code: str) -> str:
    """Tên file theo style; ký tự Windows cấm được thay bằng gạch dưới."""
    reference = str(style_ref or "").strip()
    code = str(style_code or "").strip()
    stem = f"{reference} - {code}" if reference and code else (reference or code)
    stem = _FORBIDDEN_FILE_CHARS.sub("_", stem).strip().rstrip(" .")
    return stem or "report"


def unique_target(
    directory: Path, stem: str, suffix: str = ".xlsx"
) -> Path:
    """Không ghi đè file đã có: thêm hậu tố (2), (3)... như Chrome."""
    target = Path(directory) / f"{stem}{suffix}"
    index = 2
    while target.exists():
        target = Path(directory) / f"{stem} ({index}){suffix}"
        index += 1
    return target
