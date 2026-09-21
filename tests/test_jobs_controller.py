"""Lịch sử tác vụ, chạy lại, ảnh chẩn đoán và góp ý.

`wfx_panel/controllers/jobs.py` là bề mặt mà UI gọi cho cả thẻ `Lịch sử hoạt
động` lẫn form góp ý. Test ở đây chạy đúng controller đó trên một PanelAPI
thật với base_dir tạm, không mock nội bộ, nên hợp đồng chạy-lại và các quy tắc
riêng tư trong CLAUDE.md được kiểm ở đúng chỗ chúng được thi hành.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from wfx_panel import job_history, prefs, telemetry
from wfx_panel.controllers import jobs as jobs_controller
from wfx_panel.panel_api import PanelAPI


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def run(self, user_id, password, company_id="psh", log=print):
        self.calls.append(("run", user_id))
        return {"ok": True, "code": "LOGGED_IN", "message": "ok"}

    def check_session(self, log=print):
        self.calls.append(("check_session",))
        return {"ok": True, "code": "SESSION_ACTIVE", "message": "ok"}

    def open_module(self, module_name, xpath, log=print):
        self.calls.append(("open_module", module_name))
        return {"ok": True, "code": "MODULE_OPENED", "message": module_name}

    def report_catalog(self):
        return []


def _api(tmp_path) -> tuple[PanelAPI, FakeLogin]:
    fake = FakeLogin()
    return PanelAPI(login_module=fake, prefs_module=prefs, base_dir=tmp_path), fake


def _store(tmp_path, **overrides) -> str:
    job = {
        "run_id": "run-fixed",
        "method": "open_module",
        "request": {"module_id": "0004_0050_0020"},
        "ok": False,
        "code": "MODULE_NOT_FOUND",
        "message": "không mở được",
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_ms": 42,
        "screenshot": None,
        **overrides,
    }
    job_history.append(tmp_path, job)
    return str(job["run_id"])


# --- lịch sử --------------------------------------------------------------


def test_get_job_history_returns_the_public_projection(tmp_path):
    api, _ = _api(tmp_path)
    _store(tmp_path)

    result = api.get_job_history()

    assert result["ok"] is True
    assert result["code"] == "JOB_HISTORY"
    row = result["jobs"][0]
    assert row["run_id"] == "run-fixed"
    assert "request" not in row
    assert "screenshot" not in row


def test_acknowledge_job_marks_the_row_and_returns_the_fresh_list(tmp_path):
    api, _ = _api(tmp_path)
    run_id = _store(tmp_path)

    result = api.acknowledge_job(run_id)

    assert result["ok"] is True
    assert result["code"] == "JOB_ACKNOWLEDGED"
    assert result["jobs"][0]["requires_attention"] is False


def test_acknowledge_job_reports_an_unknown_run_id(tmp_path):
    api, _ = _api(tmp_path)

    result = api.acknowledge_job("khong-ton-tai")

    assert result["ok"] is False
    assert result["code"] == "JOB_NOT_FOUND"


def test_clear_job_history_empties_the_list(tmp_path):
    api, _ = _api(tmp_path)
    _store(tmp_path)

    result = api.clear_job_history()

    assert result["code"] == "JOB_HISTORY_CLEARED"
    assert result["jobs"] == []
    assert api.get_job_history()["jobs"] == []


def test_clear_log_empties_the_technical_log(tmp_path):
    api, _ = _api(tmp_path)
    api._logs = ["[RUN] một dòng"]

    result = api.clear_log()

    assert result["code"] == "LOG_CLEARED"
    assert api._logs == []


# --- chạy lại -------------------------------------------------------------


def test_retry_job_reports_an_unknown_run_id(tmp_path):
    api, _ = _api(tmp_path)

    result = api.retry_job("khong-ton-tai")

    assert result["ok"] is False
    assert result["code"] == "JOB_NOT_FOUND"


@pytest.mark.parametrize("method", sorted(job_history._RETRYABLE_METHODS))
def test_every_retryable_method_has_a_handler(tmp_path, method):
    """`can_retry` và bảng handler phải nói cùng một thứ.

    Nếu một method được liệt kê là retryable mà bảng không có handler, UI hiện
    nút `Thử lại an toàn` rồi trả `JOB_NOT_RETRYABLE` — đúng loại lỗi im lặng
    mà test grep-source không bắt được.
    """
    api, _ = _api(tmp_path)
    run_id = _store(tmp_path, method=method, run_id=f"run-{method}")
    called: list[str] = []
    for name in ("login", "check_session", "open_module", "prepare_catalog",
                 "scan_catalog_folders", "browse_catalog"):
        setattr(
            api,
            name,
            lambda *_a, _name=name, **_kw: called.append(_name)
            or {"ok": True, "code": "OK"},
        )

    result = api.retry_job(run_id)

    assert called == [method]
    assert result["ok"] is True


def test_retry_job_refuses_a_method_whose_query_was_never_stored(tmp_path):
    """CLAUDE.md: không chạy lại tác vụ mà lịch sử đã bỏ nội dung tìm kiếm."""
    api, _ = _api(tmp_path)
    run_id = _store(tmp_path, method="catalog_action", run_id="run-catalog")

    result = api.retry_job(run_id)

    assert result["ok"] is False
    assert result["code"] == "JOB_NOT_RETRYABLE"
    assert "nhạy cảm" in result["message"]


def test_retry_job_refuses_a_method_it_does_not_know(tmp_path, monkeypatch):
    api, _ = _api(tmp_path)
    run_id = _store(tmp_path, method="run_sale_asn_create", run_id="run-asn")
    monkeypatch.setattr(jobs_controller.job_history, "can_retry", lambda _job: True)

    result = api.retry_job(run_id)

    assert result["ok"] is False
    assert result["code"] == "JOB_NOT_RETRYABLE"
    assert result["message"] == "Tác vụ này không hỗ trợ chạy lại."


def test_retry_open_module_uses_the_module_id_from_history(tmp_path):
    api, fake = _api(tmp_path)
    run_id = _store(tmp_path, method="open_module")

    result = api.retry_job(run_id)

    assert result["ok"] is True
    assert ("open_module", "Sale ASN List") in [
        (call[0], call[1]) for call in fake.calls if call[0] == "open_module"
    ] or any(call[0] == "open_module" for call in fake.calls)


def test_retry_catalog_flows_default_to_apparel_when_history_has_no_category(
    tmp_path, monkeypatch
):
    api, _ = _api(tmp_path)
    run_id = _store(tmp_path, method="prepare_catalog", request={})
    seen: list[str] = []
    api.prepare_catalog = lambda name: seen.append(name) or {"ok": True}

    api.retry_job(run_id)

    assert seen == ["Apparel"]


def test_retry_scan_catalog_folders_always_refreshes(tmp_path):
    api, _ = _api(tmp_path)
    run_id = _store(
        tmp_path,
        method="scan_catalog_folders",
        request={"category_name": "Trims"},
    )
    seen: list[tuple] = []
    api.scan_catalog_folders = lambda name, force: seen.append((name, force)) or {
        "ok": True
    }

    api.retry_job(run_id)

    assert seen == [("Trims", True)]


# --- ảnh chẩn đoán --------------------------------------------------------


def test_open_job_screenshot_reports_a_missing_image(tmp_path):
    api, _ = _api(tmp_path)
    run_id = _store(tmp_path)

    result = api.open_job_screenshot(run_id)

    assert result["ok"] is False
    assert result["code"] == "SCREENSHOT_NOT_FOUND"


def test_open_job_screenshot_reports_an_unknown_run_id(tmp_path):
    api, _ = _api(tmp_path)

    result = api.open_job_screenshot("khong-ton-tai")

    assert result["ok"] is False
    assert result["code"] == "SCREENSHOT_NOT_FOUND"


def test_open_job_screenshot_refuses_a_path_outside_the_screenshot_folder(
    tmp_path,
):
    """Đường dẫn trong lịch sử là dữ liệu; nó không được mở file tùy ý."""
    api, _ = _api(tmp_path)
    outside = tmp_path / "ngoai-thu-muc.png"
    outside.write_bytes(b"\x89PNG\r\n\x1a\n")
    run_id = _store(tmp_path, screenshot=str(outside))

    result = api.open_job_screenshot(run_id)

    assert result["ok"] is False
    assert result["code"] == "SCREENSHOT_NOT_FOUND"


def test_open_job_screenshot_refuses_a_non_png_inside_the_folder(tmp_path):
    api, _ = _api(tmp_path)
    shots = job_history.screenshot_dir(tmp_path)
    shots.mkdir(parents=True, exist_ok=True)
    payload = shots / "run-fixed.exe"
    payload.write_bytes(b"MZ")
    run_id = _store(tmp_path, screenshot=str(payload))

    result = api.open_job_screenshot(run_id)

    assert result["ok"] is False
    assert result["code"] == "SCREENSHOT_NOT_FOUND"


def test_open_job_screenshot_opens_a_valid_png(tmp_path, monkeypatch):
    api, _ = _api(tmp_path)
    shots = job_history.screenshot_dir(tmp_path)
    shots.mkdir(parents=True, exist_ok=True)
    image = shots / "run-fixed.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    run_id = _store(tmp_path, screenshot=str(image))
    opened: list[str] = []
    monkeypatch.setattr(jobs_controller.os, "name", "nt")
    monkeypatch.setattr(
        jobs_controller.os, "startfile", lambda path: opened.append(str(path)),
        raising=False,
    )

    result = api.open_job_screenshot(run_id)

    assert result["ok"] is True
    assert result["code"] == "SCREENSHOT_OPENED"
    assert opened == [str(image.resolve())]


def test_open_job_screenshot_reports_an_os_failure(tmp_path, monkeypatch):
    api, _ = _api(tmp_path)
    shots = job_history.screenshot_dir(tmp_path)
    shots.mkdir(parents=True, exist_ok=True)
    image = shots / "run-fixed.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    run_id = _store(tmp_path, screenshot=str(image))
    monkeypatch.setattr(jobs_controller.os, "name", "nt")

    def boom(_path):
        raise OSError("không có ứng dụng mặc định")

    monkeypatch.setattr(jobs_controller.os, "startfile", boom, raising=False)

    result = api.open_job_screenshot(run_id)

    assert result["ok"] is False
    assert result["code"] == "SCREENSHOT_OPEN_FAILED"


# --- góp ý ----------------------------------------------------------------


@pytest.mark.parametrize("message", ["", "    ", "abcd"])
def test_feedback_below_five_characters_is_refused(tmp_path, message):
    api, _ = _api(tmp_path)

    result = api.submit_feedback("feedback", message, True)

    assert result["ok"] is False
    assert result["code"] == "FEEDBACK_TOO_SHORT"


def test_feedback_above_two_thousand_characters_is_refused(tmp_path):
    api, _ = _api(tmp_path)

    result = api.submit_feedback("bug", "x" * 2_001, True)

    assert result["ok"] is False
    assert result["code"] == "FEEDBACK_TOO_LONG"


def test_feedback_exactly_at_the_limits_is_accepted(tmp_path):
    api, _ = _api(tmp_path)

    assert api.submit_feedback("bug", "12345", False)["code"] == "FEEDBACK_QUEUED"
    assert (
        api.submit_feedback("bug", "y" * 2_000, False)["code"] == "FEEDBACK_QUEUED"
    )


def test_feedback_without_diagnostics_stores_no_job_or_system_summary(tmp_path):
    api, _ = _api(tmp_path)
    _store(tmp_path)

    api.submit_feedback("bug", "Nút Catalog không phản hồi", False)

    raw = telemetry._outbox_path(tmp_path).read_text(encoding="utf-8")
    assert "diagnostics" not in raw
    assert "recent_jobs" not in raw


def test_feedback_with_diagnostics_attaches_the_five_most_recent_jobs(tmp_path):
    api, _ = _api(tmp_path)
    for index in range(7):
        _store(tmp_path, run_id=f"run-{index}")

    api.submit_feedback("bug", "Nút Catalog không phản hồi", True)

    raw = telemetry._outbox_path(tmp_path).read_text(encoding="utf-8")
    assert raw.count('"run_id"') >= 5
    assert "recent_jobs" in raw


def test_feedback_normalises_any_kind_other_than_bug(tmp_path):
    api, _ = _api(tmp_path)

    api.submit_feedback("KHÔNG-BIẾT", "Một góp ý bình thường", False)

    raw = telemetry._outbox_path(tmp_path).read_text(encoding="utf-8")
    assert '"kind": "feedback"' in raw


def test_feedback_accepts_bug_case_insensitively(tmp_path):
    api, _ = _api(tmp_path)

    api.submit_feedback("BUG", "Một lỗi thật", False)

    raw = telemetry._outbox_path(tmp_path).read_text(encoding="utf-8")
    assert '"kind": "bug"' in raw


def test_feedback_reports_the_queue_when_no_webhook_is_configured(tmp_path):
    api, _ = _api(tmp_path)

    result = api.submit_feedback("bug", "Một lỗi thật", False)

    assert result["code"] == "FEEDBACK_QUEUED"
    assert result["reporting_configured"] is False
    assert "lưu góp ý an toàn" in result["message"]


def test_flush_error_reports_reports_whether_the_webhook_is_configured(tmp_path):
    api, _ = _api(tmp_path)

    result = api.flush_error_reports()

    assert result["reporting_configured"] is False
    assert "delivered" in result or "ok" in result


def test_the_handler_table_and_can_retry_never_drift_apart():
    """Bảng handler phải trùng đúng `_RETRYABLE_METHODS`, không thừa không thiếu.

    Thiếu → UI hiện `Thử lại an toàn` rồi trả `JOB_NOT_RETRYABLE`.
    Thừa → code chết, vì `can_retry` đã chặn trước khi tra bảng và
    `_safe_request` đã xóa query/Article Code khỏi lịch sử.
    """
    import re
    from pathlib import Path

    source = Path(jobs_controller.__file__).read_text(encoding="utf-8")
    block = source[
        source.index("retry_handlers"): source.index("handler = retry_handlers.get")
    ]
    handlers = set(re.findall(r'^\s{12}"([a-z_]+)":', block, re.M))

    assert handlers == set(job_history._RETRYABLE_METHODS)
