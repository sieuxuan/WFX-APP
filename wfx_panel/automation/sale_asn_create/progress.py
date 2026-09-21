"""Bắn tiến độ từng bước lên UI.

Message của bước chạy theo vòng lặp phải kết thúc bằng n/m — UI đọc đúng
hậu tố đó để hiện bộ đếm."""

from __future__ import annotations

from collections.abc import Callable

SALE_ASN_STAGE_LABELS = {
    "po": "Thêm PO",
    "order_details": "Order Details",
    "style_details": "Style Details",
    "shipping_info": "Shipping Info",
    "price_check": "Check giá / Qty",
}


SALE_ASN_STAGE_ORDER = tuple(SALE_ASN_STAGE_LABELS)


def _emit_stage_progress(
    progress: Callable[..., None] | None,
    stage: str,
    message: str,
    *,
    state: str = "active",
) -> None:
    """Bắn tiến độ cho UI; lỗi ở đây không được ảnh hưởng flow automation."""
    if progress is None:
        return
    try:
        progress(
            stage,
            message,
            SALE_ASN_STAGE_ORDER.index(stage) + 1,
            len(SALE_ASN_STAGE_ORDER),
            state=state,
        )
    except Exception:
        pass
