"""Nhận diện và chờ frame của Sourcing ASN / GRN Pending / Tìm GRN."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from wfx_panel.automation._common import (
    Frame,
    Page,
    PlaywrightError,
    PlaywrightTimeoutError,
    _click,
    _document_changed,
    _mark_document,
    _result,
    _wait,
    _write_log,
    time,
)
from wfx_panel.automation.modules import search_rmpo_list


def _fold(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _resolve_rmpo(
    rmpo_xpath: str,
    rmpo_no: str,
    log: Callable[[str], None],
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    result = search_rmpo_list(rmpo_xpath, "", rmpo_no, log)
    if not result.get("ok"):
        if result.get("code") == "RMPO_NO_RESULTS":
            return None, None, _result(
                False,
                "GRN_RMPO_NOT_FOUND",
                "Không tìm thấy RMPO để lấy Supplier.",
            )
        return None, None, result
    matching_rows = [
        row
        for row in result.get("rmpo_rows") or []
        if isinstance(row, dict)
        and _fold(rmpo_no) in _fold(row.get("order_no"))
    ]
    exact_rows = [
        row
        for row in matching_rows
        if _fold(row.get("order_no")) == _fold(rmpo_no)
    ]
    candidates = exact_rows or matching_rows
    if len(candidates) != 1:
        code = "GRN_RMPO_NOT_FOUND" if not candidates else "GRN_RMPO_AMBIGUOUS"
        message = (
            "Không tìm thấy RMPO phù hợp để lấy Supplier."
            if not candidates
            else "Có nhiều RMPO chứa số đã nhập; hãy nhập thêm ký tự để xác định đúng PO."
        )
        return None, None, _result(False, code, message)
    selected = candidates[0]
    canonical_rmpo = " ".join(str(selected.get("order_no") or "").split())
    supplier = " ".join(str(selected.get("supplier") or "").split())
    if not supplier:
        _write_log(
            log,
            "[GRN] Đã tìm thấy đúng RMPO nhưng chưa đọc được Supplier ở dòng đó.",
        )
        return None, None, _result(
            False,
            "GRN_RMPO_SUPPLIER_NOT_FOUND",
            f"Đã tìm thấy RMPO {canonical_rmpo}, nhưng chưa đọc được Supplier.",
        )
    status = _fold(selected.get("status"))
    if status == "received":
        return None, None, _result(
            False,
            "GRN_ALREADY_RECEIVED",
            f"RMPO {canonical_rmpo} đã nhập kho hết, không thể nhập thêm.",
        )
    _write_log(
        log,
        "[GRN] Đã xác định RMPO đầy đủ và Supplier từ kết quả duy nhất.",
    )
    return canonical_rmpo, supplier, None


def _context_frames(context: Any) -> list[Frame]:
    return [
        frame
        for page in reversed(context.pages)
        for frame in reversed(page.frames)
    ]


def _frame_has_context(frame: Frame, selectors: Sequence[str]) -> bool:
    try:
        return all(frame.locator(selector).count() for selector in selectors)
    except PlaywrightError:
        return False


def _snapshot_context(
    context: Any,
    prefix: str,
) -> tuple[set[int], dict[int, tuple[Frame | None, str]]]:
    page_ids = {id(page) for page in context.pages}
    snapshots: dict[int, tuple[Frame | None, str]] = {}
    for page_index, page in enumerate(context.pages):
        for frame_index, frame in enumerate(page.frames):
            snapshots[id(frame)] = _mark_document(
                frame,
                f"{prefix}-{page_index}-{frame_index}",
            )
    return page_ids, snapshots


def _wait_new_context_frame(
    context: Any,
    page_ids: set[int],
    snapshots: dict[int, tuple[Frame | None, str]],
    selectors: Sequence[str],
    *,
    timeout_s: float = 40,
) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in _context_frames(context):
            if not _frame_has_context(frame, selectors):
                continue
            snapshot = snapshots.get(id(frame))
            if (
                id(frame.page) not in page_ids
                or snapshot is None
                or _document_changed(frame, snapshot)
            ):
                return frame
        frames = _context_frames(context)
        _wait(frames[0] if frames else context.pages[0], 150)
    raise PlaywrightTimeoutError(
        "WFX chưa mở đúng màn hình sau khi click menu."
    )


def _find_context_frame(
    context: Any,
    selectors: Sequence[str],
    *,
    timeout_s: float = 15,
) -> Frame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in _context_frames(context):
            if _frame_has_context(frame, selectors):
                return frame
        frames = _context_frames(context)
        _wait(frames[0] if frames else context.pages[0], 150)
    raise PlaywrightTimeoutError("Không tìm thấy màn hình WFX đang thao tác.")


def _open_menu_form(
    context: Any,
    page: Page,
    xpath: str,
    selectors: Sequence[str],
    label: str,
    log: Callable[[str], None],
) -> Frame:
    page_ids, snapshots = _snapshot_context(context, f"grn-{label}")
    target = page.locator(f"xpath={xpath}")
    target.wait_for(state="attached", timeout=8_000)
    _write_log(log, f"[GRN] Đang mở {label}...")
    _click(target)
    frame = _wait_new_context_frame(
        context,
        page_ids,
        snapshots,
        selectors,
        timeout_s=45,
    )
    try:
        frame.page.bring_to_front()
    except PlaywrightError:
        pass
    return frame
