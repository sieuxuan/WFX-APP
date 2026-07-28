import json
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
        path = crash_log.install(tmp_path, app_version="1.0.13")
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
