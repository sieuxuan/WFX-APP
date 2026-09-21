import json
import os
import sys
import threading

from wfx_panel import crash_log


def test_crash_log_detects_previous_unclean_exit(tmp_path, monkeypatch):
    marker = tmp_path / crash_log.MARKER_NAME
    marker.write_text(
        json.dumps({"pid": 987654, "started_at": "2026-07-28T15:00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(crash_log, "_pid_is_running", lambda _pid: False)
    original_sys_hook = sys.excepthook
    original_thread_hook = threading.excepthook

    try:
        path = crash_log.install(tmp_path, app_version="1.0.14")
        text = path.read_text(encoding="utf-8")
        assert "PREVIOUS_UNCLEAN_EXIT" in text
        assert "PROCESS_STARTED" in text
        crash_log.clean_shutdown("test")
        assert not marker.exists()
        assert "PROCESS_STOPPED" in path.read_text(encoding="utf-8")
    finally:
        sys.excepthook = original_sys_hook
        threading.excepthook = original_thread_hook
        crash_log._BASE_DIR = None


def test_crash_log_redacts_secrets_queries_and_url_queries(tmp_path):
    crash_log._append(
        tmp_path,
        "UNHANDLED_PROCESS_EXCEPTION",
        exception=(
            "RuntimeError: password=SECRET query='STYLE-99' "
            "https://wfx.test/list?SessionID=ABC"
        ),
    )

    text = (tmp_path / crash_log.LOG_NAME).read_text(encoding="utf-8")
    assert "SECRET" not in text
    assert "STYLE-99" not in text
    assert "SessionID=ABC" not in text
    assert "REDACTED" in text


def _isolate_hooks(monkeypatch, tmp_path):
    """Cài crash_log vào tmp_path và luôn trả lại hook gốc sau test."""
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setattr(crash_log, "_BASE_DIR", None, raising=False)
    monkeypatch.setattr(crash_log, "_CLEAN", False, raising=False)
    return crash_log.install(tmp_path, app_version="test")


def test_record_is_a_no_op_before_install(tmp_path, monkeypatch):
    monkeypatch.setattr(crash_log, "_BASE_DIR", None, raising=False)

    crash_log.record("IGNORED", detail="x")

    assert not (tmp_path / crash_log.LOG_NAME).exists()


def test_append_skips_empty_details_and_keeps_the_event_line(tmp_path):
    crash_log._append(tmp_path, "EVENT", kept="value", dropped=None, blank="")

    line = (tmp_path / crash_log.LOG_NAME).read_text(encoding="utf-8")
    assert "[EVENT]" in line
    assert "kept=" in line
    assert "dropped" not in line
    assert "blank" not in line


def test_append_sanitizes_nested_details(tmp_path):
    crash_log._append(
        tmp_path,
        "EVENT",
        detail={"inner": ["password=TOPSECRET"], "number": 7},
    )

    text = (tmp_path / crash_log.LOG_NAME).read_text(encoding="utf-8")
    assert "TOPSECRET" not in text
    assert "REDACTED" in text
    assert '"number": 7' in text or '"number":7' in text


def test_append_never_raises_when_the_directory_cannot_be_created(
    tmp_path, monkeypatch
):
    def boom(*_args, **_kwargs):
        raise OSError("ổ đĩa chỉ đọc")

    monkeypatch.setattr(crash_log.Path, "mkdir", boom)

    crash_log._append(tmp_path / "nested", "EVENT", detail="x")  # không raise


def test_log_rotates_once_it_passes_the_size_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(crash_log, "MAX_LOG_BYTES", 64)
    path = tmp_path / crash_log.LOG_NAME
    path.write_text("x" * 200, encoding="utf-8")

    crash_log._append(tmp_path, "AFTER_ROTATE")

    assert path.with_suffix(".1.log").read_text(encoding="utf-8") == "x" * 200
    assert "AFTER_ROTATE" in path.read_text(encoding="utf-8")


def test_rotate_is_silent_when_the_log_does_not_exist_yet(tmp_path):
    crash_log._rotate(tmp_path / "missing.log")  # không raise


def test_pid_is_running_rejects_non_positive_and_dead_pids():
    assert crash_log._pid_is_running(0) is False
    assert crash_log._pid_is_running(-5) is False
    assert crash_log._pid_is_running(os.getpid()) is True


def test_install_tolerates_a_corrupt_marker(tmp_path, monkeypatch):
    (tmp_path / crash_log.MARKER_NAME).write_text("{ khong phai json", encoding="utf-8")
    monkeypatch.setattr(crash_log, "_pid_is_running", lambda _pid: False)

    path = _isolate_hooks(monkeypatch, tmp_path)

    text = path.read_text(encoding="utf-8")
    assert "PREVIOUS_UNCLEAN_EXIT" in text
    assert "PROCESS_STARTED" in text
    crash_log.clean_shutdown("test")


def test_install_ignores_a_marker_whose_process_is_still_alive(
    tmp_path, monkeypatch
):
    (tmp_path / crash_log.MARKER_NAME).write_text(
        json.dumps({"pid": 4242, "started_at": "2026-01-01T00:00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(crash_log, "_pid_is_running", lambda _pid: True)

    path = _isolate_hooks(monkeypatch, tmp_path)

    assert "PREVIOUS_UNCLEAN_EXIT" not in path.read_text(encoding="utf-8")
    crash_log.clean_shutdown("test")


def test_installed_hooks_log_then_delegate_to_the_original(tmp_path, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: seen.append("process"))
    monkeypatch.setattr(threading, "excepthook", lambda a: seen.append("thread"))
    monkeypatch.setattr(crash_log, "_BASE_DIR", None, raising=False)
    monkeypatch.setattr(crash_log, "_CLEAN", False, raising=False)
    path = crash_log.install(tmp_path, app_version="test")

    try:
        error = RuntimeError("password=LEAK")
        sys.excepthook(RuntimeError, error, error.__traceback__)

        class Args:
            thread = threading.current_thread()
            exc_type = RuntimeError
            exc_value = error
            exc_traceback = error.__traceback__

        threading.excepthook(Args)
    finally:
        crash_log.clean_shutdown("test")

    text = path.read_text(encoding="utf-8")
    assert seen == ["process", "thread"]
    assert "UNHANDLED_PROCESS_EXCEPTION" in text
    assert "UNHANDLED_THREAD_EXCEPTION" in text
    assert "LEAK" not in text


def test_dump_threads_writes_a_stack_for_the_current_thread(tmp_path, monkeypatch):
    path = _isolate_hooks(monkeypatch, tmp_path)
    try:
        crash_log.dump_threads("HANG_SUSPECTED")
    finally:
        crash_log.clean_shutdown("test")

    text = path.read_text(encoding="utf-8")
    assert "HANG_SUSPECTED" in text
    assert "MainThread" in text


def test_watch_for_hang_stays_silent_when_the_work_finishes_in_time(
    tmp_path, monkeypatch
):
    path = _isolate_hooks(monkeypatch, tmp_path)
    completed = threading.Event()
    completed.set()
    try:
        crash_log.watch_for_hang(completed, "SHOULD_NOT_APPEAR", timeout=0.01)
    finally:
        crash_log.clean_shutdown("test")

    assert "SHOULD_NOT_APPEAR" not in path.read_text(encoding="utf-8")


def test_watch_for_hang_dumps_threads_once_the_timeout_passes(
    tmp_path, monkeypatch
):
    path = _isolate_hooks(monkeypatch, tmp_path)
    try:
        crash_log.watch_for_hang(threading.Event(), "SAVE_HUNG", timeout=0.01)
    finally:
        crash_log.clean_shutdown("test")

    assert "SAVE_HUNG" in path.read_text(encoding="utf-8")


def test_clean_shutdown_is_idempotent_and_survives_a_missing_marker(
    tmp_path, monkeypatch
):
    path = _isolate_hooks(monkeypatch, tmp_path)
    (tmp_path / crash_log.MARKER_NAME).unlink()

    crash_log.clean_shutdown("first")
    crash_log.clean_shutdown("second")

    assert path.read_text(encoding="utf-8").count("PROCESS_STOPPED") == 1
    assert "second" not in path.read_text(encoding="utf-8")


def test_clean_shutdown_before_install_does_nothing(monkeypatch):
    monkeypatch.setattr(crash_log, "_BASE_DIR", None, raising=False)
    monkeypatch.setattr(crash_log, "_CLEAN", False, raising=False)

    crash_log.clean_shutdown("no-install")  # không raise
