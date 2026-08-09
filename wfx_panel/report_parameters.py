from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from wfx_panel.atomic_io import write_json_atomic

# Nhiều PanelAPI có thể cùng tồn tại trong test hoặc khi WebView được tạo lại.
# Khóa module bảo vệ trọn chu trình read-modify-write dùng chung một file.
_STORE_LOCK = threading.RLock()


def _clean_values(
    values: Mapping[object, object],
    *,
    stringify_scalars: bool,
) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        clean_key = str(key).strip()[:240]
        if not clean_key:
            continue
        if isinstance(value, bool):
            cleaned[clean_key] = value
        elif isinstance(value, (str, int, float)):
            cleaned[clean_key] = (
                str(value)[:2_000] if stringify_scalars else value
            )
        elif isinstance(value, list):
            cleaned[clean_key] = [
                str(item)[:500]
                for item in value[:500]
                if isinstance(item, (str, int, float))
            ]
    return cleaned


class ReportParameterStore:
    """Kho tham số Reports theo tài khoản, ghi nguyên tử và chống lost update."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self, account_key: str, report_id: str) -> dict[str, Any]:
        if not account_key:
            return {}
        with _STORE_LOCK:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
            if not isinstance(raw, dict):
                return {}
            account_reports = raw.get(account_key)
            if not isinstance(account_reports, dict):
                return {}
            values = account_reports.get(str(report_id))
            if not isinstance(values, dict):
                return {}
            return _clean_values(values, stringify_scalars=False)

    def save(
        self,
        account_key: str,
        report_id: str,
        values: Mapping[object, object],
    ) -> dict[str, Any]:
        cleaned = _clean_values(values, stringify_scalars=True)
        with _STORE_LOCK:
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                stored = {}
            if not isinstance(stored, dict):
                stored = {}
            account_reports = stored.get(account_key)
            if not isinstance(account_reports, dict):
                account_reports = {}
                stored[account_key] = account_reports
            account_reports[str(report_id)] = cleaned
            write_json_atomic(self.path, stored, separators=(",", ":"))
        return cleaned
