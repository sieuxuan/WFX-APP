"""Đọc trạng thái dòng package và chọn đúng dòng của lượt chạy này.

Chỉ được chọn dòng MỚI có ``Transaction Detail=Pending``; dòng đầu đang
``InProgress`` phải bỏ qua và lấy Pending mới nhất theo ``Processed ON``."""

from __future__ import annotations

import re
from datetime import datetime

from wfx_panel.automation.dispatch.constants import PACKAGE_LABEL


class DispatchFlowError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        errors: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.errors = list(errors or ())


def _normalise_status(value: object) -> str:
    return re.sub(r"[^a-z]", "", str(value or "").casefold())


def _status_failed(*values: object) -> bool:
    text = " ".join(_normalise_status(value) for value in values)
    return any(
        marker in text
        for marker in (
            "fail",
            "error",
            "false",
            "invalid",
            "reject",
            "cancel",
            "notprocessed",
        )
    )


def _status_complete(*values: object) -> bool:
    text = " ".join(_normalise_status(value) for value in values)
    return any(
        marker in text
        for marker in ("success", "complete", "created", "processed")
    ) and not _status_failed(*values)


def _processed_sort_key(row: dict[str, str]) -> tuple[float, int, str]:
    raw = str(row.get("processed_on") or "").strip()
    timestamp = 0.0
    for pattern in (
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            timestamp = datetime.strptime(raw, pattern).timestamp()
            break
        except ValueError:
            continue
    row_id = str(row.get("row_id") or "")
    numeric_id = int(row_id) if row_id.isdigit() else 0
    return timestamp, numeric_id, row_id


def choose_latest_pending_row(
    rows: list[dict[str, str]],
    *,
    excluded_ids: set[str] | None = None,
) -> dict[str, str] | None:
    """Chọn đúng package Dispatch Pending mới nhất theo Processed ON."""
    excluded = excluded_ids or set()
    candidates = [
        row
        for row in rows
        if str(row.get("row_id") or "") not in excluded
        and str(row.get("package_name") or "").casefold()
        == PACKAGE_LABEL.casefold()
        and _normalise_status(row.get("transaction_detail")) == "pending"
    ]
    return max(candidates, key=_processed_sort_key) if candidates else None
