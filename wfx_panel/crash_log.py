"""Nhật ký tối giản cho crash/hang của tiến trình desktop.

File nằm trong DATA_DIR, không chứa credential hay dữ liệu nghiệp vụ. Một
marker phiên chạy giúp lần khởi động kế tiếp nhận biết lần trước bị Windows
đóng do crash/hang kể cả khi Python không kịp phát sinh exception.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

LOG_NAME = "crash.log"
MARKER_NAME = "wfx-running.json"
MAX_LOG_BYTES = 2 * 1024 * 1024
_LOCK = threading.Lock()
_BASE_DIR: Path | None = None
_CLEAN = False


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _rotate(path: Path) -> None:
    try:
        if path.stat().st_size < MAX_LOG_BYTES:
            return
        backup = path.with_suffix(".1.log")
        path.replace(backup)
    except (FileNotFoundError, OSError):
        pass


def _append(base_dir: Path, event: str, **details: Any) -> None:
    base_dir = Path(base_dir)
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        path = base_dir / LOG_NAME
        with _LOCK:
            _rotate(path)
            payload = " ".join(
                f"{key}={json.dumps(value, ensure_ascii=False)}"
                for key, value in details.items()
                if value not in (None, "")
            )
            with path.open("a", encoding="utf-8") as stream:
                stream.write(
                    f"[{_timestamp()}] [{event}]"
                    f"{(' ' + payload) if payload else ''}\n"
                )
    except OSError:
        pass


def record(event: str, **details: Any) -> None:
    if _BASE_DIR is not None:
        _append(_BASE_DIR, event, **details)


def _exception_text(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: Any,
) -> str:
    return "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)
    )[-16_000:]


def dump_threads(event: str) -> None:
    """Ghi stack Python của mọi thread khi một thao tác bị treo quá lâu."""
    frames = sys._current_frames()
    stacks = []
    for thread in threading.enumerate():
        frame = frames.get(thread.ident or -1)
        if frame is None:
            continue
        stacks.append(
            f"--- {thread.name} ({thread.ident}) ---\n"
            + "".join(traceback.format_stack(frame))[-8_000:]
        )
    record(event, stacks="\n".join(stacks)[-24_000:])


def watch_for_hang(
    completed: threading.Event,
    event: str,
    timeout: float = 3.0,
) -> None:
    if not completed.wait(timeout):
        dump_threads(event)


def install(base_dir: Path, *, app_version: str) -> Path:
    """Cài hooks và tạo marker phiên chạy; gọi một lần khi process bắt đầu."""
    global _BASE_DIR, _CLEAN
    _BASE_DIR = Path(base_dir)
    _CLEAN = False
    _BASE_DIR.mkdir(parents=True, exist_ok=True)
    marker = _BASE_DIR / MARKER_NAME
    if marker.is_file():
        try:
            previous = json.loads(marker.read_text(encoding="utf-8"))
            previous_pid = int(previous.get("pid") or 0)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            previous_pid = 0
            previous = {}
        if previous_pid != os.getpid() and not _pid_is_running(previous_pid):
            _append(
                _BASE_DIR,
                "PREVIOUS_UNCLEAN_EXIT",
                previous_pid=previous_pid,
                previous_started_at=previous.get("started_at"),
            )
    marker.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "started_at": _timestamp(),
                "app_version": app_version,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _append(
        _BASE_DIR,
        "PROCESS_STARTED",
        pid=os.getpid(),
        app_version=app_version,
        frozen=bool(getattr(sys, "frozen", False)),
    )

    original_sys_hook = sys.excepthook
    original_thread_hook = threading.excepthook

    def process_hook(exc_type, exc_value, exc_traceback):
        record(
            "UNHANDLED_PROCESS_EXCEPTION",
            exception=_exception_text(exc_type, exc_value, exc_traceback),
        )
        original_sys_hook(exc_type, exc_value, exc_traceback)

    def thread_hook(args):
        record(
            "UNHANDLED_THREAD_EXCEPTION",
            thread=getattr(args.thread, "name", "unknown"),
            exception=_exception_text(
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
            ),
        )
        original_thread_hook(args)

    sys.excepthook = process_hook
    threading.excepthook = thread_hook
    return _BASE_DIR / LOG_NAME


def clean_shutdown(reason: str = "normal") -> None:
    global _CLEAN
    if _CLEAN or _BASE_DIR is None:
        return
    _CLEAN = True
    record("PROCESS_STOPPED", pid=os.getpid(), reason=reason)
    marker = _BASE_DIR / MARKER_NAME
    try:
        marker.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass
