"""Tín hiệu dừng giữa chừng: chờ user chọn PO, và popup bị WFX thay frame."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any

from wfx_panel.automation._common import _result


class _POAddUnconfirmed(RuntimeError):
    def __init__(self, row: dict, candidates: Sequence[dict]) -> None:
        super().__init__("SALE_ASN_PO_ADD_UNCONFIRMED")
        self.row = row
        self.candidates = candidates


_FAILURE_REASONS = {
    "ACTION_CANCELLED": "Bạn đã dừng tác vụ.",
    "CHROME_CLOSED": "Trình duyệt làm việc đã đóng.",
    "NOT_LOGGED_IN": "Phiên đăng nhập WFX đã hết hạn.",
    "SALE_ASN_DRAFT_UNAVAILABLE": "Không tìm thấy đúng form đang làm. Hãy mở lại form Sale ASN còn dang dở để tiếp tục.",
    "SALE_ASN_BUYER_NOT_FOUND": "WFX không có Buyer đã chọn.",
    "SALE_ASN_BUYER_NOT_CONFIRMED": "WFX chưa xác nhận Buyer đã chọn.",
    "SALE_ASN_ACTION_NOT_READY": "Nút thao tác trên WFX chưa sẵn sàng.",
    "SALE_ASN_PO_SEARCH_NOT_READY": "WFX chưa trả kết quả tìm PO.",
    "SALE_ASN_PO_SELECTION_NOT_CONFIRMED": "WFX chưa xác nhận được dòng PO đã chọn. Hãy thử tìm lại PO này.",
    "SALE_ASN_PO_ADD_UNCONFIRMED": "WFX chưa xác nhận PO đã vào Order Details. Hãy kiểm tra và thêm dòng còn thiếu trên WFX rồi bấm Thử lại bước này để app xác nhận.",
    "SALE_ASN_ORDER_ROWS_NOT_FOUND": "Order Details đang thiếu PO: {detail}",
    "SALE_ASN_ORDER_GRID_NOT_READY": "WFX chưa tải đủ các dòng trong Order Details.",
    "SALE_ASN_FIELD_NOT_EDITABLE": "WFX không cho sửa ô này.",
    "SALE_ASN_FIELD_VALUE_NOT_CONFIRMED": "Giá trị WFX ghi nhận là “{detail}”, khác dữ liệu cần điền.",
    "SALE_ASN_STYLE_HS_CODE_CONFLICT": "Các dòng cùng Style có HS Code khác nhau.",
    "SALE_ASN_STYLE_GOODS_DESCRIPTION_CONFLICT": "Các dòng cùng Style có Goods Description khác nhau.",
    "SALE_ASN_SHIPMENT_DETAILS_EMPTY": "Bảng Shipment Details chưa có dòng để đối chiếu.",
    "SALE_ASN_SUMMARY_TOTAL_EMPTY": "WFX chưa hiển thị số liệu Summary Total.",
    "style-not-found": "Không tìm thấy Style này trong Style Details.",
    "style-grid-not-found": "WFX chưa hiển thị bảng Style Details.",
    "style-row-ambiguous": "Có nhiều Style gần giống nên chưa xác định được dòng cần điền.",
    "style-row-count-changed": "Các dòng Style trên WFX đã thay đổi trong lúc điền.",
    "style-row-index-changed": "Các dòng Style trên WFX đã thay đổi trong lúc điền.",
    "order-grid-not-found": "WFX chưa hiển thị bảng Order Details.",
    "row-not-found": "Không tìm thấy dòng WFX khớp PO và Style.",
    "row-ambiguous": "Có nhiều dòng WFX khớp PO và Style.",
    "cell-not-found": "Không tìm thấy ô cần điền trên WFX.",
    "hts-cell-not-found": "Không tìm thấy ô cần điền trên WFX.",
    "cargo-ready-date-cell-not-found": "Không tìm thấy đủ ô Cargo Ready Date trên WFX.",
    "cargo-ready-date-ambiguous": "Có nhiều ngày cho cùng dòng WFX nên chưa xác định được ngày cần điền.",
}


def _failure_reason(code: str, detail: str) -> str:
    if code == "SALE_ASN_TABLE_MAPPING_FAILED":
        return _FAILURE_REASONS.get(detail, detail or "Chưa xác định được dòng cần điền trên WFX.")
    return _FAILURE_REASONS.get(code, detail or code).replace("{detail}", detail or "(trống)")


def _row_label(row: dict) -> str:
    parts = []
    if row.get("source_row"):
        parts.append(f"Dòng Excel {row['source_row']}")
    if row.get("po_no"):
        parts.append(f"PO {row['po_no']}")
    if row.get("style_no"):
        parts.append(f"Style {row['style_no']}")
    return " · ".join(parts)


class _CellFillError(RuntimeError):
    def __init__(self, error: Exception, row: dict, field: str) -> None:
        super().__init__(str(error))
        self.error = error
        self.location = " · ".join(filter(None, (_row_label(row), field)))


@contextmanager
def _filling_cell(row: dict, field: str):
    try:
        yield
    except Exception as error:
        raise _CellFillError(error, row, field) from error


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
    row_label = _row_label(row)
    if row.get("_separate_line"):
        row_label += f" · Qty {row.get('qty')}"
        if row.get("fob_price"):
            row_label += f" · FOB Price {row['fob_price']}"
    if not rendered_candidates:
        message = (
            f"{row_label}: WFX không tìm thấy dòng khớp các tiêu chí tìm PO. "
            "Kiểm tra Buyer, PO, Style, Destination và số lượng đã xuất trên WFX rồi thử lại."
        )
        return _result(
            False,
            "SALE_ASN_PO_NOT_FOUND",
            message,
            resumable=True,
            resume_stage="po",
            stage_label="Thêm PO",
            resume_index=pending_index,
            can_skip=False,
        )
    if reason.startswith(("qty_mismatch:", "qty_unavailable:")):
        detail = reason.split(":", 1)[1]
        message = (
            f"{row_label}: {detail}. "
            "Hãy chọn các dòng cần thêm ngay trong ứng dụng; automation sẽ tự "
            "tick và tiếp tục trên WFX."
        )
    else:
        message = (
            f"{row_label} có nhiều lựa chọn. "
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
