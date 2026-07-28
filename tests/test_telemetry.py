import ast
import json
from pathlib import Path

from wfx_panel import telemetry
from wfx_panel.panel_api import NON_REPORTABLE_FAILURES


def test_default_feedback_webhook_is_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("WFX_ERROR_WEBHOOK_URL", raising=False)

    assert telemetry.webhook_url(tmp_path) == (
        "https://n8n.itx.io.vn/webhook/wfx-app"
    )
    assert telemetry.is_configured(tmp_path) is True


def test_submit_delivers_when_hidden_webhook_is_configured(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "WFX_ERROR_WEBHOOK_URL",
        "https://hooks.example.test/private",
    )
    delivered = []
    monkeypatch.setattr(
        telemetry,
        "_post",
        lambda url, event, timeout=5.0: delivered.append((url, event)),
    )
    result = telemetry.submit(
        tmp_path,
        {"event_type": "user_feedback", "message": "Xin thêm module QA"},
    )
    assert result["delivery"] == "sent"
    assert delivered[0][0].endswith("/private")
    assert not (tmp_path / "telemetry-outbox.json").exists()


def test_automatic_error_payload_can_omit_sensitive_business_data(tmp_path):
    telemetry.enqueue(
        tmp_path,
        {
            "event_type": "automation_error",
            "method": "find_code",
            "code": "FILTER_RESULTS_NOT_READY",
            "run_id": "run-1",
            "elapsed_ms": 1000,
        },
    )
    payload = json.loads(
        (tmp_path / "telemetry-outbox.json").read_text(encoding="utf-8")
    )[0]
    serialized = json.dumps(payload)
    assert "password" not in serialized.casefold()
    assert "cookie" not in serialized.casefold()
    assert "query" not in serialized.casefold()


def test_automation_error_context_explains_generic_codes():
    context = telemetry.automation_error_context(
        "search_sample",
        {
            "code": "MODULE_SEARCH_NOT_READY",
            "message": "Không tìm thấy ô Created By.",
            "module": "Sample List",
            "filter_kind": "Created By",
        },
    )
    assert context["method_label"] == "Tìm trong Sample List"
    assert context["error_title"] == "Ô tìm kiếm của module chưa sẵn sàng"
    assert "Không tìm thấy ô Created By" in context["message"]
    assert "Bấm List" in context["suggestion"]
    assert context["module"] == "Sample List"


def test_module_failed_context_names_the_affected_module():
    context = telemetry.automation_error_context(
        "open_module",
        {
            "code": "MODULE_FAILED",
            "message": "PlaywrightError: frame đã đổi.",
            "module": "QA List",
        },
    )
    assert context["error_title"] == "Không thể thao tác module QA List"
    assert context["error_detail"] == "PlaywrightError: frame đã đổi."


def test_every_reportable_failure_code_has_a_human_description():
    codes = set()
    source_root = Path(__file__).resolve().parent.parent / "wfx_panel"
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            function_name = (
                getattr(node.func, "id", "")
                or getattr(node.func, "attr", "")
            )
            if function_name != "_result":
                continue
            ok_node, code_node = node.args[:2]
            if (
                isinstance(ok_node, ast.Constant)
                and ok_node.value is False
                and isinstance(code_node, ast.Constant)
                and isinstance(code_node.value, str)
            ):
                codes.add(code_node.value)
    reportable = codes - set(NON_REPORTABLE_FAILURES)
    assert reportable - set(telemetry.ERROR_CODE_INFO) == set()


def test_automation_error_detail_redacts_url_query_and_secrets():
    raw = (
        "Timeout at https://wfx.test/list?query=ABC "
        "password=secret query='STYLE-99' article_code=ABC123"
    )
    redacted = telemetry.redact_telemetry_text(raw)
    assert "https://" not in redacted
    assert "secret" not in redacted
    assert "STYLE-99" not in redacted
    assert "ABC123" not in redacted
    assert "[đã ẩn]" in redacted


def test_n8n_workflow_uses_current_normalizer_without_raw_payload():
    root = Path(__file__).resolve().parent.parent
    workflow = json.loads(
        (root / "n8n" / "wfx-app-webhook.json").read_text(encoding="utf-8")
    )
    code = next(
        node["parameters"]["jsCode"]
        for node in workflow["nodes"]
        if node["type"] == "n8n-nodes-base.code"
    )
    telegram = next(
        node
        for node in workflow["nodes"]
        if node["type"] == "n8n-nodes-base.telegram"
    )
    for hook in (
        "notification_text",
        "source.account",
        "error_title",
        "suggestion",
        "const redact",
    ):
        assert hook in code
    assert "raw_payload" not in code
    assert telegram["parameters"]["text"] == "={{ $json.notification_text }}"

    standalone = (root / "n8n" / "wfx-app-normalize-code.js").read_text(
        encoding="utf-8"
    )
    assert "raw_payload" not in standalone
    assert "redactAutomationText" in standalone
