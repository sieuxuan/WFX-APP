"""Bridge `PanelAPI` chuyển đúng lời gọi sang controller sở hữu nó.

CLAUDE.md: `panel_api.py` chỉ giữ hạ tầng dùng chung và là delegator mỏng sang
controller; `tests/test_bridge_contract.py` canh tên method tồn tại, nhưng một
delegator trỏ nhầm controller hoặc đánh rơi tham số thì không test nào khác đỏ.
File này canh chính việc chuyển tiếp đó.
"""

from __future__ import annotations

import pytest

from wfx_panel import prefs
from wfx_panel.panel_api import PanelAPI


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def run(self, *_args, **_kwargs):
        return {"ok": True, "code": "LOGGED_IN", "message": "ok"}


@pytest.fixture
def api(tmp_path):
    return PanelAPI(login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path)


class Recorder:
    """Ghi lại lời gọi và trả một giá trị nhận dạng được."""

    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return f"ket-qua-{name}"

        return record


DELEGATIONS = [
    ("_engine", "_progress", "_progress", ("open_module", "po", "1/2", 1, 2), {}),
    ("_engine", "_action_in_progress", "_action_in_progress", (), {}),
    ("_engine", "_enter_run", "_enter_run", (), {}),
    ("_engine", "_exit_run", "_exit_run", (), {}),
    (
        "_engine",
        "_normalised_result",
        "_normalised_result",
        ("open_module", lambda: {"ok": True}),
        {},
    ),
    (
        "_engine",
        "_wants_failure_screenshot",
        "_wants_failure_screenshot",
        ("open_module", "CHROME_CLOSED"),
        {},
    ),
    (
        "_engine",
        "_capture_failure_screenshot",
        "_capture_failure_screenshot",
        ("run-1",),
        {},
    ),
    (
        "_engine",
        "_announce_finish",
        "_announce_finish",
        ("open_module", {"ok": True}, 1.0, True),
        {},
    ),
    (
        "_engine",
        "_report_automation_error",
        "_report_automation_error",
        ("open_module", {"ok": False}, None, "PANEL_ERROR", "run-1", 1.0),
        {},
    ),
    (
        "_engine",
        "_append_job_history",
        "_append_job_history",
        ("run-1", "open_module", None, {"ok": True}, "2026-01-01", 1.0, None),
        {},
    ),
    ("_session", "_login_run", "_login_run", ("tester", "mat-khau"), {}),
    (
        "_session",
        "_restore_expired_session",
        "_restore_expired_session",
        (),
        {},
    ),
    (
        "_reports",
        "_saved_report_parameters",
        "_saved_report_parameters",
        ("0004_0110",),
        {},
    ),
    (
        "_sale_asn",
        "_discard_sale_asn_create_review",
        "_discard_sale_asn_create_review",
        ("token-1",),
        {},
    ),
    (
        "_sale_asn",
        "_discard_sale_asn_document_export",
        "_discard_sale_asn_document_export",
        ("token-1",),
        {},
    ),
    (
        "_oc",
        "_discard_oc_upload_review",
        "_discard_oc_upload_review",
        ("token-1",),
        {},
    ),
    ("_catalog", "sync_article_library", "sync_article_library", (), {}),
    ("_settings", "save_sync_admin_key", "save_sync_admin_key", ("khoa",), {}),
    ("_settings", "publish_reference_data", "publish_reference_data", (), {}),
]


@pytest.mark.parametrize(
    ("owner", "target", "bridge_method", "args", "kwargs"),
    DELEGATIONS,
    ids=[item[2] for item in DELEGATIONS],
)
def test_the_bridge_forwards_to_the_controller_that_owns_the_work(
    api, monkeypatch, owner, target, bridge_method, args, kwargs
):
    recorder = Recorder()
    monkeypatch.setattr(api, owner, recorder)

    result = getattr(api, bridge_method)(*args, **kwargs)

    assert result == f"ket-qua-{target}"
    assert recorder.calls[0][0] == target
    assert recorder.calls[0][1] == args


def test_a_run_is_started_through_the_engine_with_all_of_its_options(
    api, monkeypatch
):
    recorder = Recorder()
    monkeypatch.setattr(api, "_engine", recorder)
    action = lambda: {"ok": True}  # noqa: E731 - đối số của bridge

    api._run_unlocked(
        "open_module",
        action,
        {"module_id": "oc"},
        record_job=False,
        record_job_on_failure=True,
        announce=False,
        emit_result=False,
    )

    name, args, kwargs = recorder.calls[0]
    assert name == "_run_unlocked"
    assert args == ("open_module", action, {"module_id": "oc"})
    assert kwargs == {
        "record_job": False,
        "record_job_on_failure": True,
        "announce": False,
        "emit_result": False,
    }


def test_a_sale_asn_run_carries_the_rows_the_user_picked(api, monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(api, "_sale_asn", recorder)

    api._run_sale_asn_create_review(
        "token-1", continue_existing=True, selected_candidate_ids=["r1", "r2"]
    )

    name, args, kwargs = recorder.calls[0]
    assert name == "_run_sale_asn_create_review"
    assert args == ("token-1",)
    assert kwargs == {
        "continue_existing": True,
        "selected_candidate_ids": ["r1", "r2"],
    }


def test_refreshing_the_status_reads_the_same_state_the_panel_shows(
    api, monkeypatch
):
    monkeypatch.setattr(api, "get_status", lambda: {"ok": True, "code": "STATUS"})

    assert api.refresh_status() == {"ok": True, "code": "STATUS"}


# --- hạ tầng dùng chung --------------------------------------------------


def test_the_technical_log_keeps_only_the_most_recent_lines(api):
    for index in range(320):
        api._log(f"dong {index}")

    assert len(api._logs) == 300
    assert "dong 319" in api._logs[-1]


def test_a_log_line_carries_the_run_it_belongs_to(api):
    api._current_run_id = "run-42"

    api._log("Đang mở Catalog")

    assert "[run-42]" in api._logs[-1]


def test_a_ui_sink_that_throws_never_breaks_logging(api):
    def refuse(_line):
        raise RuntimeError("WebView đã đóng")

    api._sink = refuse

    api._log("Đang mở Catalog")

    assert api._logs[-1].endswith("Đang mở Catalog")


def test_the_ui_sink_receives_every_log_line(api):
    seen: list[str] = []
    api._sink = seen.append

    api._log("Đang mở Catalog")

    assert seen == [api._logs[-1]]


# --- chủ phiên Chrome ----------------------------------------------------


def test_the_session_owner_is_remembered_across_restarts(tmp_path):
    prefs.save_prefs(base_dir=tmp_path, session_user_id="tester")

    api = PanelAPI(
        login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path
    )

    assert api._session_user_id == "tester"


def test_a_prefs_file_that_cannot_be_read_leaves_no_session_owner(
    tmp_path, monkeypatch
):
    api = PanelAPI(
        login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path
    )

    def refuse(**_kwargs):
        raise OSError("ổ đĩa lỗi")

    monkeypatch.setattr(api._prefs, "load_prefs", refuse)

    assert api._session_user_id in (None, "")


def test_the_session_owner_is_only_read_from_disk_once(tmp_path, monkeypatch):
    prefs.save_prefs(base_dir=tmp_path, session_user_id="tester")
    api = PanelAPI(
        login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path
    )
    reads: list[int] = []
    real_load = api._prefs.load_prefs

    def counting(**kwargs):
        reads.append(1)
        return real_load(**kwargs)

    monkeypatch.setattr(api._prefs, "load_prefs", counting)

    assert api._session_user_id == api._session_user_id

    assert len(reads) <= 1
