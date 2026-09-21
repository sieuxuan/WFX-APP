"""Tín hiệu dừng giữa chừng: chờ user chọn PO, và popup bị WFX thay frame."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from wfx_panel.automation._common import _result


class _POSelectionRequired(Exception):
    """PO cần user tự chọn trên WFX.

    Dùng cho các nhánh nằm sâu trong flow (ví dụ khi thêm lại PO bị rơi lúc
    đóng popup). Nếu chỉ raise ``RuntimeError`` thì user nhận một lỗi kỹ thuật
    trong khi popup vẫn đang mở chờ họ chọn dòng.
    """

    def __init__(
        self,
        row: dict,
        candidates: Sequence[dict],
        reason: str,
        *,
        final: bool,
    ) -> None:
        super().__init__("SALE_ASN_PO_SELECTION_REQUIRED")
        self.row = dict(row)
        self.candidates = list(candidates)
        self.reason = reason
        self.final = final


class _POFrameChanged(Exception):
    """Popup Add PO thay document trong lúc đang tìm, trước khi chọn dòng."""

    def __init__(
        self,
        *,
        fields: Sequence[str] = (),
        search_submitted: bool = False,
    ) -> None:
        super().__init__("SALE_ASN_PO_FRAME_CHANGED")
        self.fields = tuple(fields)
        self.search_submitted = search_submitted


def _is_transient_frame_error(error: BaseException) -> bool:
    message = str(error).casefold()
    return any(
        marker in message
        for marker in (
            "execution context was destroyed",
            "frame was detached",
            "cannot find context with specified id",
        )
    )


def _po_selection_result(
    row: dict,
    candidates: Sequence[dict],
    reason: str,
    *,
    final: bool,
    pending_index: int,
    next_index: int,
    completed: int,
    total: int,
) -> dict[str, Any]:
    rendered_candidates = [
        {**dict(candidate), "candidate_id": str(index)}
        for index, candidate in enumerate(candidates[:20])
    ]
    if reason.startswith(("qty_mismatch:", "qty_unavailable:")):
        detail = reason.split(":", 1)[1]
        message = (
            f"Dòng {row.get('source_row')} · PO {row.get('po_no')}: {detail}. "
            "Hãy chọn các dòng cần thêm ngay trong ứng dụng; automation sẽ tự "
            "tick và tiếp tục trên WFX."
        )
    else:
        message = (
            f"Dòng {row.get('source_row')} · PO {row.get('po_no')} có nhiều lựa chọn. "
            "Hãy chọn dòng cần thêm ngay trong ứng dụng."
        )
    return _result(
        True,
        "SALE_ASN_PO_SELECTION_REQUIRED",
        message,
        pending_index=pending_index,
        next_index=next_index,
        source_row=row.get("source_row"),
        po_no=row.get("po_no"),
        style_no=row.get("style_no"),
        reason=reason,
        candidates=rendered_candidates,
        final=final,
        completed=completed,
        total=total,
    )


def _shipping_warning(label: str, value: str, result: dict[str, Any]) -> str:
    reason = str(result.get("reason") or "không thể điền")
    if reason == "option-not-found":
        return f'{label}: WFX không có lựa chọn "{value}"'
    if reason == "host-not-found":
        return f"{label}: WFX không có trường này"
    if reason == "editor-not-found":
        return f"{label}: trường không thể chỉnh sửa"
    if reason == "document-changed":
        return f"{label}: trang WFX đã thay đổi khi đang điền"
    return f"{label}: {reason}"
