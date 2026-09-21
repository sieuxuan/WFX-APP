"""Ép giá trị file về đúng dạng WFX nhận, và so khớp gần đúng.

Style trong file là từ khoá gần đúng chứ không phải mã exact, nên phần so khớp
chấm điểm tương đồng thay vì so bằng."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation

from wfx_panel.automation.sale_asn_create.constants import (
    _WFX_MONTH_NUMBERS,
    _WFX_MONTHS,
)


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def _style_similarity(source: str, candidate: str) -> int:
    left, right = _fold(source), _fold(candidate)
    if not left or not right:
        return 0
    if left == right:
        return 10_000
    if left in right or right in left:
        return 8_000 + min(len(left), len(right))
    left_tokens, right_tokens = set(left.split()), set(right.split())
    shared = left_tokens & right_tokens
    return len(shared) * 100 - abs(len(left_tokens) - len(right_tokens))


def _best_dropdown_label(options: Sequence[str], query: str) -> str | None:
    """Chọn duy nhất option gần query nhất; đồng hạng/không liên quan thì bỏ qua."""

    cleaned = list(dict.fromkeys(" ".join(str(item or "").split()) for item in options))
    scored = [(_style_similarity(query, option), option) for option in cleaned if option]
    best_score = max((score for score, _option in scored), default=0)
    best = [option for score, option in scored if score == best_score and score > 0]
    return best[0] if len(best) == 1 else None


def _best_factory_label(options: Sequence[str], query: str) -> str | None:
    """Lấy option FTY gần nhất, không phân biệt hoa/thường và bỏ dòng có dấu chấm."""

    query_folded = _fold(query)
    eligible = []
    for option in options:
        cleaned = " ".join(str(option or "").split())
        option_folded = _fold(cleaned)
        if not cleaned or cleaned.endswith("."):
            continue
        if option_folded != query_folded and option_folded in query_folded:
            continue
        eligible.append(cleaned)
    scored = [(_style_similarity(query, option), option) for option in eligible]
    best_score = max((score for score, _option in scored), default=0)
    if best_score <= 0:
        return None
    return next(option for score, option in scored if score == best_score)


def _date_for_wfx(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        return f"{parsed.day:02d} {_WFX_MONTHS[parsed.month - 1]} {parsed.year:04d}"
    except ValueError:
        return value


def _number_for_wfx(value: str, *, integer: bool = False) -> str:
    # quantize() cũng ném InvalidOperation khi phần nguyên vượt precision của
    # Decimal context, nên nó phải nằm trong cùng try với việc dựng Decimal.
    try:
        number = Decimal(value.replace(",", "").strip())
        number = number.quantize(Decimal("1") if integer else Decimal("0.0001"))
    except InvalidOperation:
        return value
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _table_value_matches(expected: str, actual: str) -> bool:
    expected_clean = str(expected or "").replace(",", "").strip()
    actual_clean = str(actual or "").replace(",", "").strip()
    try:
        left, right = Decimal(expected_clean), Decimal(actual_clean)
        return abs(left - right) <= Decimal("0.0001")
    except InvalidOperation:
        pass
    expected_date = _parse_supported_date(expected_clean)
    actual_date = _parse_supported_date(actual_clean)
    if expected_date is not None and actual_date is not None:
        return expected_date == actual_date
    if _fold(expected_clean) == _fold(actual_clean):
        return True
    # Một số editor WFX tự bỏ apostrophe/quote khi blur ("Men's" → "Mens").
    # Đây là chuẩn hóa hiển thị của WFX, không phải dữ liệu bị đổi; chỉ bỏ các
    # ký tự quote ở nhánh fallback, còn dấu câu khác vẫn giữ ranh giới từ.
    return _wfx_text_value_key(expected_clean) == _wfx_text_value_key(actual_clean)


def _decimal_or_none(value: object) -> Decimal | None:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _decimal_display(value: Decimal | None) -> str:
    if value is None:
        return ""
    rendered = format(value.quantize(Decimal("0.0001")), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _wfx_text_value_key(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"['`\u2018\u2019\u02bc]+", "", text.casefold())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _try_date(value: str, pattern: str) -> datetime | None:
    try:
        return datetime.strptime(value, pattern)
    except ValueError:
        return None


def _parse_supported_date(value: str) -> datetime | None:
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        if (parsed := _try_date(value, pattern)) is not None:
            return parsed
    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", value)
    if match is None:
        return None
    month = _WFX_MONTH_NUMBERS.get(match.group(2).casefold())
    if month is None:
        return None
    try:
        return datetime(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None
