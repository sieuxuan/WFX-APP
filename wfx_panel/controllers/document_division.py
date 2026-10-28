"""Số chứng từ WFX mang sẵn Division trong tiền tố.

``PSG-ONL-26-170`` thuộc PSSG, ``PSW-JLD-26-6242`` thuộc Woven,
``PSK-PARAGON-26-3374`` thuộc Knit — cùng một quy ước cho Sample Order No.,
OC No. và RMPO No. Các List của WFX chỉ hiện chứng từ của Division đang chọn,
nên tìm một số chứng từ của Division khác luôn ra "không có kết quả" dù chứng
từ có thật. Flow tìm vì thế đổi Division trước, ngay trong cùng flow."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wfx_panel.panel_api import PanelAPI

from wfx_panel import constants

DOCUMENT_NO_DIVISIONS = {"PSG": "pssg", "PSW": "woven", "PSK": "knit"}

_DOCUMENT_NO_PREFIX = re.compile(r"^\s*(PS[GWK])\s*-", re.IGNORECASE)

_DIVISION_FIELDS = ("current_division", "division_label", "division_name")

# Lỗi phiên/Chrome giữ nguyên code và message để run engine tự login lại hoặc
# mở lại Chrome rồi chạy lại cả flow như mọi flow khác.
_PASSTHROUGH_CODES = {"CHROME_CLOSED", "NOT_LOGGED_IN"}


def document_no_division(document_no: str) -> str | None:
    """Division key theo tiền tố số chứng từ, hoặc None nếu không nhận ra."""
    match = _DOCUMENT_NO_PREFIX.match(str(document_no or ""))
    if match is None:
        return None
    return DOCUMENT_NO_DIVISIONS[match.group(1).upper()]


def align_division(
    panel: PanelAPI,
    key: str | None,
    *,
    reason: str,
    module: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Đổi sang Division ``key`` nếu cần.

    Trả ``(lỗi, trạng_thái)``: ``lỗi`` khác None thì flow phải dừng — chạy tiếp
    ở Division sai chỉ ra "không có kết quả" sai sự thật. ``trạng_thái`` là các
    field Division để caller gộp vào kết quả cuối, nhờ đó footer và bộ chọn
    Division trên panel đổi theo ngay cả khi lượt tìm sau đó không ra dòng nào.
    ``reason`` mở đầu câu lỗi, ví dụ ``"RMPO No. PSW-JLD-26-6242"``.
    """
    switcher = getattr(panel._login, "switch_division", None)
    if key not in constants.DIVISIONS or not callable(switcher):
        return None, {}
    result = switcher(key, panel._log)
    code = str(result.get("code") or "")
    state = {
        name: result[name] for name in _DIVISION_FIELDS if name in result
    }
    if code == "DIVISION_ALREADY_ACTIVE":
        return None, state
    if code == "DIVISION_CHANGED":
        # WFX vừa nạp lại toàn bộ trang: route menu đã cache và context Catalog
        # thuộc Division cũ. Run engine chỉ tự dọn khi CHÍNH kết quả cuối là
        # DIVISION_CHANGED, còn ở đây kết quả cuối là của lượt tìm.
        reset_menu_cache = getattr(panel._login, "reset_menu_route_cache", None)
        if callable(reset_menu_cache):
            reset_menu_cache()
        panel._catalog.reset_context()
        return None, {**state, "division_switched": True}
    if code in _PASSTHROUGH_CODES:
        return dict(result), {}
    label = constants.DIVISIONS[key]["label"]
    detail = str(result.get("message") or "").strip()
    return {
        **result,
        "ok": False,
        "code": code or "DIVISION_CHANGE_FAILED",
        "message": (
            f"{reason} thuộc Division {label} "
            f"nhưng chưa đổi được Division. {detail}"
        ).strip(),
        "module": module,
    }, {}


def align_document_division(
    panel: PanelAPI,
    document_no: str,
    *,
    label: str,
    module: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Đổi sang Division theo tiền tố ``document_no``; không tiền tố thì giữ."""
    return align_division(
        panel,
        document_no_division(document_no),
        reason=f"{label} {str(document_no or '').strip()}",
        module=module,
    )


def with_document_division_state(
    result: dict[str, Any],
    state: dict[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    """Gộp trạng thái Division vào kết quả và báo rõ khi app vừa tự đổi."""
    if not state:
        return result
    merged = {**result, **state}
    if state.get("division_switched"):
        division = str(state.get("division_label") or "").strip()
        notice = (
            f"Đã tự chuyển sang Division {division}."
            if division
            else f"Đã tự chuyển Division theo {label.rstrip('.')}."
        )
        message = str(result.get("message") or "").strip()
        merged["message"] = f"{notice} {message}".strip()
    return merged
