"""Lịch sử hoạt động: file hỏng, trần 200 dòng, và dọn ảnh lỗi.

CLAUDE.md: `Lịch sử hoạt động` chỉ gồm `Tất cả tác vụ` và `Log kỹ thuật`; trần
200 dòng phải dành cho job thật. App chạy cả ngày ở khay hệ thống nên việc dọn
rác không được phép làm hỏng lượt ghi hay lượt đọc lịch sử.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from wfx_panel import job_history


def _job(index=0, **overrides):
    return {
        "run_id": f"run-{index}",
        "method": "catalog_action",
        "ok": False,
        "code": "CATALOG_GRID_NOT_FOUND",
        "message": "Không mở được grid.",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_ms": 120,
        **overrides,
    }


def _shot(tmp_path, name="run-0.png"):
    shots = job_history.screenshot_dir(tmp_path)
    shots.mkdir(parents=True, exist_ok=True)
    path = shots / name
    path.write_bytes(b"PNG")
    return path


def _write_rows(tmp_path, rows):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "jobs.json").write_text(json.dumps(rows), encoding="utf-8")


# --- limit đến từ JSON bridge -------------------------------------------


@pytest.mark.parametrize(
    ("limit", "expected"),
    [
        (None, 30),
        ("ba muoi", 30),
        ([], 30),
        ("5", 5),
        (0, 1),
        (-9, 1),
        (10_000, job_history.MAX_JOBS),
    ],
)
def test_a_limit_the_webview_sent_as_text_never_breaks_the_list(limit, expected):
    assert job_history._safe_limit(limit) == expected


def test_a_limit_the_webview_sent_as_text_still_limits_the_rows(tmp_path):
    for index in range(4):
        job_history.append(tmp_path, _job(index))

    assert len(job_history.list_jobs(tmp_path, "2")) == 2


# --- file lịch sử hỏng --------------------------------------------------


def test_a_history_file_that_is_not_json_reads_as_an_empty_history(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "jobs.json").write_text("{khong phai json", encoding="utf-8")

    assert job_history.list_jobs(tmp_path) == []


def test_a_history_file_that_is_not_a_list_reads_as_an_empty_history(tmp_path):
    _write_rows(tmp_path, {"run_id": "run-1"})

    assert job_history.list_jobs(tmp_path) == []


def test_a_history_file_that_does_not_exist_yet_reads_as_empty(tmp_path):
    assert job_history.list_jobs(tmp_path) == []
    assert job_history.get_job(tmp_path, "run-1") is None


def test_a_row_without_a_readable_start_time_is_dropped(tmp_path):
    _write_rows(tmp_path, [_job(0, started_at="hom qua"), _job(1)])

    rows = job_history.list_jobs(tmp_path)

    assert [row["run_id"] for row in rows] == ["run-1"]


def test_a_row_that_is_not_a_job_at_all_is_dropped(tmp_path):
    _write_rows(tmp_path, ["hong", None, _job(1)])

    rows = job_history.list_jobs(tmp_path)

    assert [row["run_id"] for row in rows] == ["run-1"]


def test_a_row_written_before_timezones_were_recorded_is_still_kept(tmp_path):
    naive = datetime.now().replace(microsecond=0).isoformat()
    _write_rows(tmp_path, [_job(0, started_at=naive)])

    assert len(job_history.list_jobs(tmp_path)) == 1


# --- trần 200 dòng ------------------------------------------------------


def test_the_two_hundredth_job_pushes_the_oldest_one_out(tmp_path):
    for index in range(job_history.MAX_JOBS + 5):
        job_history.append(tmp_path, _job(index))

    rows = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))

    assert len(rows) == job_history.MAX_JOBS
    assert rows[0]["run_id"] == f"run-{job_history.MAX_JOBS + 4}"


def test_a_screenshot_of_a_job_pushed_out_by_the_cap_is_released(tmp_path):
    rows = [_job(index) for index in range(job_history.MAX_JOBS + 1)]
    orphan = _shot(tmp_path, "run-cu.png")
    rows[-1]["screenshot"] = str(orphan)
    _write_rows(tmp_path, rows)

    job_history.list_jobs(tmp_path)

    assert not orphan.exists()


def test_a_screenshot_of_a_job_still_in_the_list_is_kept(tmp_path):
    kept = _shot(tmp_path)
    job_history.append(tmp_path, _job(0, screenshot=str(kept)))

    assert job_history.list_jobs(tmp_path)[0]["has_screenshot"] is True
    assert kept.exists()


# --- dọn ảnh lỗi --------------------------------------------------------


def test_a_job_without_a_screenshot_needs_no_cleanup(tmp_path):
    job_history._remove_screenshot(tmp_path, {"screenshot": ""})


def test_a_file_outside_the_screenshot_folder_is_never_deleted(tmp_path):
    outsider = tmp_path / "bao-cao.png"
    outsider.write_bytes(b"PNG")

    job_history._remove_screenshot(tmp_path, {"screenshot": str(outsider)})

    assert outsider.exists()


def test_a_file_that_is_not_a_png_is_never_deleted(tmp_path):
    document = _shot(tmp_path, "ghi-chu.txt")

    job_history._remove_screenshot(tmp_path, {"screenshot": str(document)})

    assert document.exists()


def test_a_screenshot_the_user_has_open_does_not_break_the_cleanup(
    tmp_path, monkeypatch
):
    locked = _shot(tmp_path)

    def refuse(self, **_kwargs):
        raise PermissionError("ảnh đang mở trong Photos")

    monkeypatch.setattr(type(locked), "unlink", refuse)

    job_history._remove_screenshot(tmp_path, {"screenshot": str(locked)})


def test_a_screenshot_path_windows_cannot_resolve_is_ignored(
    tmp_path, monkeypatch
):
    def refuse(self, **_kwargs):
        raise OSError("đường dẫn không hợp lệ")

    monkeypatch.setattr(job_history.Path, "resolve", refuse)

    job_history._remove_screenshot(tmp_path, {"screenshot": "Z:/anh.png"})


# --- đọc một job --------------------------------------------------------


def test_one_job_is_read_back_by_its_run_id(tmp_path):
    job_history.append(tmp_path, _job(0))
    job_history.append(tmp_path, _job(1))

    assert job_history.get_job(tmp_path, "run-0")["code"] == (
        "CATALOG_GRID_NOT_FOUND"
    )


def test_a_run_id_that_is_no_longer_in_the_history_reads_as_nothing(tmp_path):
    job_history.append(tmp_path, _job(0))

    assert job_history.get_job(tmp_path, "run-99") is None


def test_reading_one_job_also_writes_back_a_history_it_had_to_clean(tmp_path):
    _write_rows(tmp_path, [_job(0, started_at="hom qua"), _job(1)])

    job_history.get_job(tmp_path, "run-1")

    rows = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))
    assert [row["run_id"] for row in rows] == ["run-1"]


# --- xác nhận đã xem ----------------------------------------------------


def test_acknowledging_a_warning_clears_it_but_keeps_the_audit_row(tmp_path):
    job_history.append(tmp_path, _job(0))

    assert job_history.acknowledge(tmp_path, "run-0") is True

    row = job_history.list_jobs(tmp_path)[0]
    assert row["requires_attention"] is False
    assert row["run_id"] == "run-0"


def test_acknowledging_a_run_that_is_gone_reports_that_it_was_not_found(tmp_path):
    job_history.append(tmp_path, _job(0))

    assert job_history.acknowledge(tmp_path, "run-99") is False


def test_acknowledging_survives_a_history_that_needed_cleaning_first(tmp_path):
    _write_rows(tmp_path, ["hong", _job(1)])

    assert job_history.acknowledge(tmp_path, "run-1") is True


# --- xóa lịch sử --------------------------------------------------------


def test_clearing_removes_the_history_and_its_screenshots(tmp_path):
    shot = _shot(tmp_path)
    job_history.append(tmp_path, _job(0, screenshot=str(shot)))

    job_history.clear(tmp_path)

    assert not (tmp_path / "jobs.json").exists()
    assert not shot.exists()


def test_clearing_an_empty_history_is_harmless(tmp_path):
    job_history.clear(tmp_path)

    assert job_history.list_jobs(tmp_path) == []


def test_clearing_leaves_files_that_are_not_screenshots_alone(tmp_path):
    keep = _shot(tmp_path, "ghi-chu.txt")

    job_history.clear(tmp_path)

    assert keep.exists()


def test_a_history_file_the_user_has_open_does_not_stop_the_clear(
    tmp_path, monkeypatch
):
    shot = _shot(tmp_path)
    job_history.append(tmp_path, _job(0, screenshot=str(shot)))
    history = tmp_path / "jobs.json"
    real_unlink = type(history).unlink

    def refuse(self, **kwargs):
        if self.name == "jobs.json":
            raise PermissionError("file đang bị khóa")
        return real_unlink(self, **kwargs)

    monkeypatch.setattr(type(history), "unlink", refuse)

    job_history.clear(tmp_path)

    assert not shot.exists()


def test_one_locked_screenshot_does_not_stop_the_others_from_being_cleared(
    tmp_path, monkeypatch
):
    locked = _shot(tmp_path, "dang-mo.png")
    free = _shot(tmp_path, "roi-ranh.png")
    real_unlink = type(locked).unlink

    def refuse(self, **kwargs):
        if self.name == "dang-mo.png":
            raise PermissionError("ảnh đang mở trong Photos")
        return real_unlink(self, **kwargs)

    monkeypatch.setattr(type(locked), "unlink", refuse)

    job_history.clear(tmp_path)

    assert locked.exists()
    assert not free.exists()


# --- job thành công -----------------------------------------------------


def test_a_job_that_finished_fine_never_raises_the_warning_badge(tmp_path):
    job_history.append(tmp_path, _job(0, ok=True, code="MODULE_OPENED"))

    row = job_history.list_jobs(tmp_path)[0]

    assert row["ok"] is True
    assert row["requires_attention"] is False
    assert row["attention_action"] == ""


def test_every_run_gets_its_own_id():
    first = job_history.new_run_id()
    second = job_history.new_run_id()

    assert first != second
    assert len(first.split("-")) == 3
