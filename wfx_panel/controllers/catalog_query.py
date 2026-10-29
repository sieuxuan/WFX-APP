"""Một ô tìm Catalog: tự nhận ra người dùng đang gõ Article Code hay tên/ref.

Panel từng bắt chọn trước `Article Code` hoặc `Buyer Reference`/`Article Name`.
Đó là một bước thừa: Code Apparel luôn là `SWV`/`SKN` (vài mã cũ `PSW`/`PSK`/
`PSG`) + số, Code các Category khác là chữ + dãy số (`T0000001`, `F0000001`,
`FD0000001`, `DIE0000001`), còn người dùng hay gõ tắt 4 số cuối của Code.
Buyer Reference Apparel thì có cả dạng chữ + số (`GMPA08941`) nên Apparel KHÔNG
được dùng luật "chữ + số" chung.

Thư viện Article đã đồng bộ nên phần còn lại tra ngay trong máy: chuỗi khớp
exact một Code, hoặc khớp exact một Buyer Reference/Article Name chỉ thuộc
đúng một Code, thì tìm luôn bằng Code đó để WFX mở thẳng Style thay vì trả
danh sách bắt chọn thêm lần nữa.
"""

from __future__ import annotations

import re
from typing import Any

from wfx_panel.stores import article_library

AUTO_KIND = "auto"
EXPLICIT_KINDS = frozenset({"code", "buyer_reference", "article_name"})

_APPAREL_CODE = re.compile(r"(?:SWV|SKN|PS[WKG]\d)\S*", re.IGNORECASE)
_OTHER_CODE = re.compile(r"[A-Za-z]+\d{4,}")
_CODE_DIGITS = re.compile(r"\d{4}")


def secondary_kind(category_name: str) -> str:
    return "buyer_reference" if category_name == "Apparel" else "article_name"


def looks_like_code(category_name: str, query: str) -> bool:
    value = str(query or "").strip()
    if _CODE_DIGITS.fullmatch(value):
        return True
    pattern = _APPAREL_CODE if category_name == "Apparel" else _OTHER_CODE
    return bool(pattern.fullmatch(value))


def _exact_codes(
    document: dict[str, Any] | None,
    category_name: str,
    field: str,
    query: str,
) -> list[str]:
    if not document:
        return []
    needle = query.casefold()
    codes: dict[str, str] = {}
    for key, _value, code, *_rest in article_library.suggestion_index(
        document, category_name, field
    ):
        if key == needle and code:
            codes.setdefault(code.casefold(), code)
    return list(codes.values())


def resolve(
    category_name: str,
    filter_kind: str,
    query: str,
    document: dict[str, Any] | None,
) -> tuple[str, str, str]:
    """``(filter_kind, query, lý do)`` cụ thể cho automation.

    Kiểu tìm đã chọn rõ (Gần đây, dòng gợi ý, bản UI cũ) giữ nguyên.
    """
    kind = str(filter_kind or "").strip().casefold()
    value = str(query or "").strip()
    if kind != AUTO_KIND or not value:
        return kind, value, ""
    exact_code = _exact_codes(document, category_name, "article_code", value)
    if len(exact_code) == 1:
        return "code", exact_code[0], "library_code"
    if looks_like_code(category_name, value):
        return "code", value, "code_pattern"
    other = secondary_kind(category_name)
    matches = _exact_codes(document, category_name, other, value)
    if len(matches) == 1:
        return "code", matches[0], f"library_{other}"
    return other, value, ""
