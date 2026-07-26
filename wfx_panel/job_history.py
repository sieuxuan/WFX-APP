"""Lịch sử automation bền vững, không lưu credential hoặc URL nhạy cảm."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

MAX_JOBS = 200
_LOCK = threading.Lock()


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _history_path(base_dir: Path) -> Path:
    return Path(base_dir) / "jobs.json"


def screenshot_dir(base_dir: Path) -> Path:
    return Path(base_dir) / "job-screenshots"


def _load(base_dir: Path) -> list[dict[str, Any]]:
    path = _history_path(base_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def append(base_dir: Path, job: dict[str, Any]) -> None:
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        rows = _load(base_dir)
        rows.insert(0, job)
        rows = rows[:MAX_JOBS]
        path = _history_path(base_dir)
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(path)


def list_jobs(base_dir: Path, limit: int = 30) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), MAX_JOBS))
    rows = _load(Path(base_dir))[:safe_limit]
    return [
        {
            **row,
            "has_screenshot": bool(
                row.get("screenshot")
                and Path(str(row["screenshot"])).is_file()
            ),
        }
        for row in rows
    ]


def get_job(base_dir: Path, run_id: str) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in _load(Path(base_dir))
            if row.get("run_id") == run_id
        ),
        None,
    )


def clear(base_dir: Path) -> None:
    """Xóa history và ảnh lỗi do app tạo, giới hạn trong DATA_DIR."""
    base_dir = Path(base_dir).resolve()
    path = _history_path(base_dir)
    shots = screenshot_dir(base_dir).resolve()
    if path.is_file():
        path.unlink()
    if shots.is_dir() and shots.parent == base_dir:
        for item in shots.iterdir():
            if item.is_file() and item.suffix.lower() == ".png":
                item.unlink()
        try:
            shots.rmdir()
        except OSError:
            pass
