"""Payload webhook phải đủ để chẩn đoán mà không cần hỏi lại người dùng.

Câu lỗi hiện cho người dùng cố ý bỏ selector và lỗi Playwright gốc; chúng chỉ
nằm trong log của Run ID. Vì vậy lỗi automation TỰ ĐỘNG cũng phải mang đuôi
log, bước hỏng, trạng thái trình duyệt/phiên và các lần chạy trước như Báo lỗi
một chạm — nhưng vẫn giữ nguyên luật riêng tư trong CLAUDE.md: không URL đầy
đủ, không query, không câu progress có số chứng từ. Fixture autouse trong
conftest đã tắt mọi webhook thật; thread flush chỉ gặp endpoint rỗng.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from wfx_panel import job_history, prefs, telemetry
from wfx_panel.panel_api import PanelAPI

ROOT = Path(__file__).resolve().parent.parent


class FakeLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = '//*[@id="0003_6200"]/a'

    def browser_status(self) -> dict:
        return {
            "chrome_alive": True,
            "browser_available": True,
            "browser_name": "Google Chrome",
            "debugger_secret": "không-được-gửi",
        }

    def report_catalog(self):
        return []


def _api(tmp_path) -> PanelAPI:
    return PanelAPI(login_module=FakeLogin(), prefs_module=prefs, base_dir=tmp_path)


def _automation_events(tmp_path) -> list[dict]:
    return [
        event
        for event in telemetry._load_outbox(tmp_path)
        if event.get("event_type") == "automation_error"
    ]


def test_automatic_error_carries_the_log_of_its_own_run(tmp_path):
    api = _api(tmp_path)

    def broken() -> dict:
        api._log("[MODULE SEARCH] Sample List dừng ở bước field: TimeoutError: x")
        api._log("mở https://wfx.example.com/wfx/WFXSample.aspx?SessionID=abc")
        api._log("query='STYLE-SECRET-99'")
        return {
            "ok": False,
            "code": "MODULE_SEARCH_NOT_READY",
            "message": "Không thấy ô lọc Style trên Sample List.",
        }

    result = api._run(
        "search_sample",
        broken,
        {"filter_kind": "style", "query": "STYLE-SECRET-99"},
    )

    event = _automation_events(tmp_path)[-1]
    assert event["run_id"] == result["run_id"]
    assert event["started_at"]
    assert event["has_screenshot"] is False
    assert any("dừng ở bước field" in line for line in event["log_tail"])
    assert any(
        line.endswith("[URL đã ẩn: WFXSample.aspx]") for line in event["log_tail"]
    )
    serialized = json.dumps(event, ensure_ascii=False)
    assert "STYLE-SECRET-99" not in serialized
    assert "SessionID" not in serialized
    assert "wfx.example.com" not in serialized
    assert "debugger_secret" not in serialized


def test_automatic_error_reports_browser_session_and_recent_runs(tmp_path):
    api = _api(tmp_path)
    api._session_active = True
    api._last_login_at = "08:00:00"
    api._run("open_module", lambda: {"ok": True, "code": "MODULE_OPENED"})

    api._run(
        "open_module",
        lambda: {"ok": False, "code": "MODULE_NOT_FOUND", "message": "x"},
        {"module_id": "0004_0050_0020"},
    )

    diagnostics = _automation_events(tmp_path)[-1]["diagnostics"]
    assert diagnostics["chrome_alive"] is True
    assert diagnostics["browser_name"] == "Google Chrome"
    assert diagnostics["session_active"] is True
    assert diagnostics["last_login_at"] == "08:00:00"
    assert diagnostics["os"]
    codes = [row["code"] for row in diagnostics["recent_jobs"]]
    assert codes[:2] == ["MODULE_NOT_FOUND", "MODULE_OPENED"]


def test_panel_error_logs_where_the_exception_was_raised(tmp_path):
    api = _api(tmp_path)

    def explode() -> dict:
        raise KeyError("thiếu-khóa")

    api._run("open_module", explode)

    event = _automation_events(tmp_path)[-1]
    assert event["code"] == "PANEL_ERROR"
    location = next(line for line in event["log_tail"] if "Vị trí lỗi" in line)
    assert "test_telemetry_payload.py:" in location
    assert "in explode" in location
    # Chỉ tên file, không đường dẫn: đường dẫn lộ tên tài khoản Windows.
    assert str(ROOT) not in location


def test_failed_stage_comes_from_the_last_progress_without_its_message(tmp_path):
    api = _api(tmp_path)

    def broken() -> dict:
        api._progress("run_sale_asn_create", "po", "Đang thêm PO 779123 2/5", 2, 5)
        return {"ok": False, "code": "SALE_ASN_PO_ADD_FAILED", "message": "x"}

    api._run("run_sale_asn_create", broken)

    event = _automation_events(tmp_path)[-1]
    assert event["failed_stage"] == "po"
    assert event["failed_step"] == 2
    assert event["progress_total"] == 5
    assert "779123" not in json.dumps(event, ensure_ascii=False)


def test_a_flow_reported_stage_wins_and_survives_into_the_one_click_report(
    tmp_path,
):
    api = _api(tmp_path)

    def broken() -> dict:
        api._progress("gdn_dispatch", "report", "Đang mở báo cáo…", 1, 6)
        return {
            "ok": False,
            "code": "MODULE_FAILED",
            "message": "x",
            "failed_stage": "package",
            "failed_step": 5,
        }

    result = api._run("gdn_dispatch", broken)

    automatic = _automation_events(tmp_path)[-1]
    assert automatic["failed_stage"] == "package"
    assert automatic["failed_step"] == 5
    assert "progress_total" not in automatic
    stored = job_history.get_job(tmp_path, result["run_id"])
    assert stored["failed_stage"] == "package"

    api.report_job(result["run_id"])
    one_click = telemetry._load_outbox(tmp_path)[-1]
    assert one_click["source"] == "one_click"
    assert one_click["failed_stage"] == "package"
    assert one_click["failed_step"] == 5


def test_a_stage_that_is_not_a_plain_identifier_is_dropped():
    assert telemetry.failure_stage({"failed_stage": "PO 779 lỗi"}) == {}
    assert telemetry.failure_stage({}, {"stage": "", "step": 3}) == {}


def test_one_click_and_automatic_reports_share_the_same_diagnostics(tmp_path):
    api = _api(tmp_path)
    result = api._run(
        "open_module",
        lambda: {"ok": False, "code": "MODULE_NOT_FOUND", "message": "x"},
    )
    api.report_job(result["run_id"])

    automatic, one_click = telemetry._load_outbox(tmp_path)[-2:]
    assert set(automatic["diagnostics"]) == set(one_click["diagnostics"])
    assert "debugger_secret" not in one_click["diagnostics"]


def test_one_click_report_keeps_the_stored_stage_of_an_old_job(tmp_path):
    api = _api(tmp_path)
    job_history.append(
        tmp_path,
        {
            "run_id": "run-old",
            "method": "run_sale_asn_create",
            "ok": False,
            "code": "SALE_ASN_PO_ADD_FAILED",
            "message": "x",
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "elapsed_ms": 10,
            "failed_stage": "po",
            "failed_step": 3,
            "progress_total": 5,
        },
    )

    api.report_job("run-old")

    event = telemetry._load_outbox(tmp_path)[-1]
    assert (event["failed_stage"], event["failed_step"], event["progress_total"]) == (
        "po",
        3,
        5,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://wfx.test/wfx/WFXSalesASN.aspx?SessionID=1&ID=9",
            "[URL đã ẩn: WFXSalesASN.aspx]",
        ),
        ("https://wfx.test/wfx/wfx_Home.aspx#top", "[URL đã ẩn: wfx_Home.aspx]"),
        ("(https://wfx.test/a/List.aspx).", "([URL đã ẩn: List.aspx]"),
        # Path REST có thể mang mã Style: không phải tên trang thì ẩn cả URL.
        ("https://wfx.test/api/article/SWV1234", "[URL đã ẩn]"),
        ("https://wfx.test/", "[URL đã ẩn]"),
    ],
)
def test_urls_keep_only_the_wfx_page_name(raw, expected):
    redacted = telemetry.redact_telemetry_text(raw)

    assert redacted.startswith(expected)
    assert "wfx.test" not in redacted


def test_long_log_lines_keep_the_playwright_call_log():
    line = "[10:00:00] TimeoutError: " + "waiting for locator " * 30

    assert len(telemetry.redact_log_lines([line])[0]) == 500


def test_discord_embed_carries_the_newest_log_lines(monkeypatch):
    payload = telemetry._discord_payload(
        {
            "event_type": "automation_error",
            "failed_stage": "po",
            "log_tail": [f"dòng {index} " + "x" * 90 for index in range(40)]
            + ["lỗi gốc cuối cùng"],
        }
    )

    fields = {field["name"]: field["value"] for field in payload["embeds"][0]["fields"]}
    assert fields["Failed Stage"] == "po"
    assert fields["Log cuối"].endswith("lỗi gốc cuối cùng")
    assert len(fields["Log cuối"]) <= 1024


@pytest.mark.skipif(shutil.which("node") is None, reason="cần Node để chạy node n8n")
def test_n8n_notification_keeps_the_newest_log_lines_within_telegram_limit(
    tmp_path,
):
    """Tin Telegram cắt ở 4.000 ký tự từ ĐẦU log cũ, không phải từ cuối."""
    script = tmp_path / "run.js"
    script.write_text(
        """
const fs = require('fs');
const code = fs.readFileSync(process.argv[2], 'utf8');
const payload = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = new Function('$json', code)({ body: payload })[0].json;
process.stdout.write(JSON.stringify(out));
""",
        encoding="utf-8",
    )
    payload = tmp_path / "payload.json"
    payload.write_text(
        json.dumps(
            {
                "event_type": "automation_error",
                "method": "search_sample",
                "code": "MODULE_SEARCH_NOT_READY",
                "run_id": "run-1",
                "started_at": "2026-10-29T10:00:00",
                "elapsed_ms": 1200,
                "failed_stage": "po",
                "failed_step": 2,
                "progress_total": 5,
                "log_tail": [f"[10:00:{i:02d}] " + "x" * 280 for i in range(40)]
                + ["[10:01:00] mở https://wfx.test/wfx/WFXSample.aspx?SessionID=1"],
                "diagnostics": {
                    "chrome_alive": True,
                    "browser_name": "Google Chrome",
                    "session_active": False,
                    "recent_jobs": [{"run_id": "run-0", "method": "login", "ok": True}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["node", str(script), str(ROOT / "n8n" / "wfx-app-normalize-code.js"), str(payload)],
        capture_output=True,
        check=True,
        timeout=30,
    )
    output = json.loads(completed.stdout.decode("utf-8"))

    text = output["notification_text"]
    assert len(text) <= 4000
    assert text.endswith("[URL đã ẩn: WFXSample.aspx]")
    assert "SessionID" not in text
    assert "🧭 Bước hỏng: po (bước 2/5)" in text
    assert "(Google Chrome)" in text
    assert "login ✓" in text
    assert output["failed_stage"] == "po"
    assert output["started_at"] == "2026-10-29T10:00:00"
    assert len(output["log_tail"]) == 41
