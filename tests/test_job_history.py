import json
from datetime import datetime, timedelta

from wfx_panel import job_history


def _job(**overrides):
    return {
        "run_id": "run-1",
        "method": "catalog_action",
        "request": {
            "category_name": "Apparel",
            "query": "SECRET-STYLE",
            "article_code": "SECRET-STYLE",
        },
        "ok": False,
        "code": "FAILED",
        "message": "query=SECRET-STYLE",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_ms": 120,
        "screenshot": None,
        **overrides,
    }


def test_history_never_persists_or_exposes_business_query(tmp_path):
    job_history.append(tmp_path, _job())

    raw = (tmp_path / "jobs.json").read_text(encoding="utf-8")
    assert "SECRET-STYLE" not in raw
    public = job_history.list_jobs(tmp_path)[0]
    assert "request" not in public
    assert "screenshot" not in public
    assert public["retryable"] is False


def test_history_and_screenshot_expire_after_seven_days(tmp_path, monkeypatch):
    now = datetime.now().astimezone()
    monkeypatch.setattr(job_history, "_now", lambda: now)
    shots = job_history.screenshot_dir(tmp_path)
    shots.mkdir()
    screenshot = shots / "old.png"
    screenshot.write_bytes(b"png")
    old = (now - timedelta(days=8)).isoformat(timespec="seconds")
    job_history.append(
        tmp_path,
        _job(started_at=old, screenshot=str(screenshot)),
    )

    assert job_history.list_jobs(tmp_path) == []
    assert not screenshot.exists()


def test_failed_non_sensitive_job_can_still_be_retried(tmp_path):
    job_history.append(
        tmp_path,
        _job(
            method="open_module",
            request={"module_id": "0004_0050_0020"},
            message="Module chưa mở",
        ),
    )

    public = job_history.list_jobs(tmp_path)[0]
    stored = job_history.get_job(tmp_path, "run-1")
    assert public["retryable"] is True
    assert stored["request"] == {"module_id": "0004_0050_0020"}


def test_loading_legacy_history_rewrites_sensitive_and_extra_fields(tmp_path):
    legacy = _job(
        request={"module_id": "0004", "query": "LEGACY-SECRET"},
        message="query=LEGACY-SECRET",
        debug_payload={"page_html": "LEGACY-SECRET"},
    )
    (tmp_path / "jobs.json").write_text(
        json.dumps([legacy]),
        encoding="utf-8",
    )

    assert job_history.list_jobs(tmp_path)

    persisted = (tmp_path / "jobs.json").read_text(encoding="utf-8")
    assert "LEGACY-SECRET" not in persisted
    assert "debug_payload" not in persisted


def test_screenshots_of_jobs_pushed_past_the_cap_are_deleted(tmp_path):
    """Vượt trần MAX_JOBS trong vòng 7 ngày vẫn phải nhả ảnh của dòng bị cắt.

    Dòng bị cắt biến mất khỏi jobs.json nên không lần dọn nào sau đó tìm lại
    được ảnh của nó; nếu không xóa ngay tại đây thì ảnh nằm lại vĩnh viễn.
    """
    shots = job_history.screenshot_dir(tmp_path)
    shots.mkdir(parents=True)
    now = datetime.now().astimezone()
    screenshots = []
    for index in range(job_history.MAX_JOBS + 3):
        screenshot = shots / f"run-{index}.png"
        screenshot.write_bytes(b"png")
        screenshots.append(screenshot)
        job_history.append(
            tmp_path,
            _job(
                run_id=f"run-{index}",
                # Mới nhất nằm đầu danh sách, nên dòng cũ nhất bị đẩy khỏi trần.
                started_at=(now - timedelta(minutes=index)).isoformat(
                    timespec="seconds"
                ),
                screenshot=str(screenshot),
            ),
        )

    stored = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))
    assert len(stored) == job_history.MAX_JOBS
    surviving = {row["run_id"] for row in stored}
    for index, screenshot in enumerate(screenshots):
        assert screenshot.exists() is (f"run-{index}" in surviving)


def test_trimming_never_deletes_a_screenshot_outside_the_data_dir(tmp_path):
    """Đường dẫn lạ trong history không được biến việc dọn thành xóa file người dùng."""
    outsider = tmp_path / "anh-cua-user.png"
    outsider.write_bytes(b"png")
    now = datetime.now().astimezone()
    for index in range(job_history.MAX_JOBS + 1):
        job_history.append(
            tmp_path,
            _job(
                run_id=f"run-{index}",
                started_at=(now - timedelta(minutes=index)).isoformat(
                    timespec="seconds"
                ),
                screenshot=str(outsider),
            ),
        )

    assert outsider.exists()
