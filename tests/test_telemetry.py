import json

from wfx_panel import telemetry


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
