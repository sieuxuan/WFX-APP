"""Lịch sử automation bền vững, không lưu credential hoặc URL nhạy cảm."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from wfx_panel import log_bridge
from wfx_panel.atomic_io import write_json_atomic

MAX_JOBS = 200
RETENTION_DAYS = 7
_LOCK = threading.Lock()
_SENSITIVE_REQUEST_KEYS = frozenset(
    {
        "password",
        "user_id",
        "query",
        "article_code",
        "style_code",
        "buyer_reference",
        "url",
        "cookie",
        "token",
    }
)
_RETRYABLE_METHODS = frozenset(
    {
        "login",
        "check_session",
        "open_module",
        "prepare_catalog",
        "scan_catalog_folders",
        "browse_catalog",
    }
)
_PERSISTED_JOB_KEYS = frozenset(
    {
        "run_id",
        "method",
        "request",
        "ok",
        "code",
        "message",
        "started_at",
        "elapsed_ms",
        "screenshot",
    }
)


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _history_path(base_dir: Path) -> Path:
    return Path(base_dir) / "jobs.json"


def screenshot_dir(base_dir: Path) -> Path:
    return Path(base_dir) / "job-screenshots"


def _safe_limit(limit: object, default: int = 30) -> int:
    """WebView truyền limit qua JSON bridge; ``int("30")`` hay ``int(None)``
    raise ValueError/TypeError và giết cả lời gọi get_job_history."""
    try:
        value = int(limit)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, MAX_JOBS))


def _load(base_dir: Path) -> list[dict[str, Any]]:
    path = _history_path(base_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write(base_dir: Path, rows: list[dict[str, Any]]) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    # Đây là nơi trần MAX_JOBS thật sự cắt danh sách trong luồng append: _prune
    # chạy TRƯỚC khi chèn dòng mới nên không bao giờ thấy dòng thứ 201. Ghi đè
    # mà không nhả ảnh ở đây là bỏ lại ảnh mồ côi không dòng nào trỏ tới nữa.
    for dropped in rows[MAX_JOBS:]:
        _remove_screenshot(base_dir, dropped)
    write_json_atomic(_history_path(base_dir), rows[:MAX_JOBS], indent=2)


def _now() -> datetime:
    return datetime.now().astimezone()


def _expired(row: dict[str, Any], now: datetime) -> bool:
    try:
        started = datetime.fromisoformat(str(row.get("started_at") or ""))
    except ValueError:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=now.tzinfo)
    return started < now - timedelta(days=RETENTION_DAYS)


def _remove_screenshot(base_dir: Path, row: dict[str, Any]) -> None:
    raw = str(row.get("screenshot") or "")
    if not raw:
        return
    try:
        path = Path(raw).resolve()
        allowed = screenshot_dir(base_dir).resolve()
    except OSError:
        return
    if path.parent == allowed and path.suffix.casefold() == ".png":
        try:
            path.unlink()
        except OSError:
            # PermissionError rất thực tế trên Windows: người dùng đang mở ảnh
            # lỗi trong Photos. Dọn rác thất bại không được làm việc ghi lịch
            # sử / đọc danh sách job thất bại theo.
            pass


def _prune(
    base_dir: Path,
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    now = _now()
    kept: list[dict[str, Any]] = []
    changed = False
    for row in rows:
        if not isinstance(row, dict) or _expired(row, now):
            if isinstance(row, dict):
                _remove_screenshot(base_dir, row)
            changed = True
            continue
        safe_row = _safe_job(row)
        kept.append(safe_row)
        changed = changed or safe_row != row
    trimmed = kept[:MAX_JOBS]
    # Dòng bị cắt vì vượt trần cũng phải nhả ảnh của nó. Trước đây chỉ dòng quá
    # RETENTION_DAYS mới gọi _remove_screenshot, nên máy chạy hơn MAX_JOBS job
    # trong vòng 7 ngày sẽ bỏ lại ảnh mồ côi vĩnh viễn trong job-screenshots:
    # không còn dòng nào trỏ tới chúng để lần dọn sau tìm ra.
    for dropped in kept[MAX_JOBS:]:
        _remove_screenshot(base_dir, dropped)
    return trimmed, changed or len(trimmed) != len(rows)


def _safe_request(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if str(key).casefold() not in _SENSITIVE_REQUEST_KEYS
        and isinstance(item, (str, int, float, bool, type(None)))
    }


def _safe_job(job: dict[str, Any]) -> dict[str, Any]:
    safe = {key: value for key, value in job.items() if key in _PERSISTED_JOB_KEYS}
    safe["request"] = _safe_request(job.get("request"))
    safe["message"] = log_bridge.sanitize_log_text(job.get("message") or "")
    return safe


def can_retry(job: dict[str, Any]) -> bool:
    return str(job.get("method") or "") in _RETRYABLE_METHODS


def append(base_dir: Path, job: dict[str, Any]) -> None:
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        rows, _ = _prune(base_dir, _load(base_dir))
        rows.insert(0, _safe_job(job))
        _write(base_dir, rows)


def list_jobs(base_dir: Path, limit: int = 30) -> list[dict[str, Any]]:
    safe_limit = _safe_limit(limit)
    base_dir = Path(base_dir)
    with _LOCK:
        rows, changed = _prune(base_dir, _load(base_dir))
        if changed:
            _write(base_dir, rows)
        rows = rows[:safe_limit]
    return [
        {
            "run_id": row.get("run_id"),
            "method": row.get("method"),
            "ok": bool(row.get("ok")),
            "code": row.get("code"),
            "message": row.get("message"),
            "started_at": row.get("started_at"),
            "elapsed_ms": row.get("elapsed_ms"),
            "has_screenshot": bool(
                row.get("screenshot") and Path(str(row["screenshot"])).is_file()
            ),
            "retryable": not bool(row.get("ok")) and can_retry(row),
        }
        for row in rows
    ]


def get_job(base_dir: Path, run_id: str) -> dict[str, Any] | None:
    base_dir = Path(base_dir)
    with _LOCK:
        rows, changed = _prune(base_dir, _load(base_dir))
        if changed:
            _write(base_dir, rows)
        return next(
            (row for row in rows if row.get("run_id") == run_id),
            None,
        )


def clear(base_dir: Path) -> None:
    """Xóa history và ảnh lỗi do app tạo, giới hạn trong DATA_DIR."""
    base_dir = Path(base_dir).resolve()
    path = _history_path(base_dir)
    shots = screenshot_dir(base_dir).resolve()
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    if shots.is_dir() and shots.parent == base_dir:
        for item in shots.iterdir():
            if item.is_file() and item.suffix.lower() == ".png":
                try:
                    item.unlink()
                except OSError:
                    # Một ảnh đang bị giữ không được chặn việc xóa các ảnh còn
                    # lại; nút "Xóa lịch sử" phải luôn hoàn tất.
                    continue
        try:
            shots.rmdir()
        except OSError:
            pass
