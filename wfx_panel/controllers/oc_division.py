"""OC No. mang sẵn Division trong tiền tố.

OC List chỉ hiện OC của Division đang chọn, nên tìm theo OC No. đổi Division
trước khi tìm. Tìm theo Style không có tiền tố nên giữ nguyên Division hiện
tại. Luật tiền tố dùng chung với Sample/RMPO nằm ở ``document_division``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel.controllers.document_division import (
    DOCUMENT_NO_DIVISIONS,
    align_document_division,
    document_no_division,
    with_document_division_state,
)

OC_NO_DIVISIONS = DOCUMENT_NO_DIVISIONS

_LABEL = "OC No."


def oc_no_division(oc_no: str) -> str | None:
    """Division key theo tiền tố OC No., hoặc None nếu không nhận ra."""
    return document_no_division(oc_no)


def align_oc_division(
    panel: PanelAPI,
    oc_no: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Đổi sang Division của OC No. nếu cần; xem ``align_division``."""
    return align_document_division(panel, oc_no, label=_LABEL, module="OC List")


def with_oc_division_state(
    result: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Gộp trạng thái Division vào kết quả và báo rõ khi app vừa tự đổi."""
    return with_document_division_state(result, state, label=_LABEL)
