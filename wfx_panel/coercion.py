"""Chuyển kiểu an toàn cho dữ liệu đi qua JSON/network boundary."""

from __future__ import annotations

import math


def nonnegative_float(value: object, default: float = 0.0) -> float:
    """Trả số hữu hạn >= 0; dữ liệu sai kiểu quay về default an toàn."""

    try:
        converted = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        converted = float(default)
    if not math.isfinite(converted) or converted < 0:
        converted = float(default)
    return converted if math.isfinite(converted) and converted >= 0 else 0.0


def boolean(value: object, default: bool = False) -> bool:
    """Đọc boolean từ JSON bridge mà không coi chuỗi ``"false"`` là True."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        cleaned = value.strip().casefold()
        if cleaned in {"true", "1", "yes", "on"}:
            return True
        if cleaned in {"false", "0", "no", "off", ""}:
            return False
    return bool(default)


def bounded_int(
    value: object,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    """Parse integer ở trust boundary và chặn giá trị ngoài khoảng."""

    try:
        converted = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        converted = int(default)
    return max(minimum, min(maximum, converted))
