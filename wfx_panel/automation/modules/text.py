"""Chuẩn hoá chuỗi trước khi so khớp giá trị ô tìm kiếm."""

from __future__ import annotations

from wfx_panel.automation._common import Any


def _normalise_search_text(value: Any) -> str:
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in str(value or "").casefold()
        ).split()
    )
