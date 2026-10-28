"""Sample Order No. mang sẵn Division trong tiền tố.

Sample List chỉ hiện Sample của Division đang chọn, nên Search và Xem file
đính kèm đổi Division trước khi tìm. Luật tiền tố dùng chung với OC/RMPO nằm ở
``document_division``."""

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

SAMPLE_NO_DIVISIONS = DOCUMENT_NO_DIVISIONS

_LABEL = "Sample No."


def sample_no_division(sample_no: str) -> str | None:
    """Division key theo tiền tố Sample No., hoặc None nếu không nhận ra."""
    return document_no_division(sample_no)


def align_sample_division(
    panel: PanelAPI,
    sample_no: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Đổi sang Division của Sample No. nếu cần; xem ``align_division``."""
    return align_document_division(
        panel, sample_no, label=_LABEL, module="Sample List"
    )


def with_division_state(
    result: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Gộp trạng thái Division vào kết quả và báo rõ khi app vừa tự đổi."""
    return with_document_division_state(result, state, label=_LABEL)
