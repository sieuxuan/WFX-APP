"""Outbox telemetry và payload gửi đi: đúng định dạng, không kèm dữ liệu nhạy cảm.

CLAUDE.md: không gửi password, cookie, SessionID, LoginID, URL WFX đầy đủ hay
nội dung tìm kiếm; mọi mô tả lỗi phải đi qua `redact_telemetry_text`. Fixture
autouse của conftest đã tắt `DEFAULT_WEBHOOK_URL`, nên không test nào chạm
webhook production.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from wfx_panel import telemetry

DISCORD = "https://discord.com/api/webhooks/123/abc"
PLAIN = "https://n8n.example/webhook/wfx"


class FakeResponse:
    def __init__(self, status=204):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _wire_urlopen(monkeypatch, outcome=None):
    sent: list[dict] = []

    def urlopen(request, timeout=None):
        sent.append(
            {
                "url": request.full_url,
                "headers": dict(request.headers),
                "payload": json.loads(request.data.decode("utf-8")),
            }
        )
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome or FakeResponse()

    monkeypatch.setattr(telemetry, "urlopen", urlopen)
    return sent


def _event(**overrides):
    event = {
        "event_type": "automation_error",
        "kind": "automation",
        "code": "CATALOG_DATA_NOT_READY",
        "method": "prepare_catalog",
        "run_id": "20260101-000000-abcdef",
        "message": "Grid Catalog chưa ổn định.",
        "account": {
            "user_id": "tester",
            "company_id": "psh",
            "division_label": "WOVEN",
            "division_name": "PRO SPORTS - WOVEN HANOI",
        },
    }
    event.update(overrides)
    return event


# --- mô tả suy ra từ mã lỗi --------------------------------------------


@pytest.mark.parametrize(
    ("code", "method", "module", "filter_kind", "expected"),
    [
        (
            "MODULE_LIST_NOT_OPEN",
            "search_oc",
            "OC List",
            "OC No.",
            "Không tìm thấy ô OC No. trong OC List; màn List chưa sẵn sàng.",
        ),
        (
            "MODULE_SEARCH_NOT_READY",
            "search_oc",
            "OC List",
            "",
            "Không tìm thấy ô tìm kiếm trong OC List sau khi app tự mở List.",
        ),
        (
            "MODULE_SEARCH_NOT_CONFIRMED",
            "search_oc",
            "OC List",
            "Style",
            "WFX chưa xác nhận kết quả tìm kiếm theo Style trong OC List.",
        ),
        (
            "MODULE_SEARCH_NOT_CONFIRMED",
            "search_oc",
            "",
            "",
            "WFX chưa xác nhận kết quả tìm kiếm.",
        ),
    ],
)
def test_a_missing_message_is_derived_from_the_code_not_left_generic(
    code, method, module, filter_kind, expected
):
    assert (
        telemetry._fallback_error_detail(
            method, code, "Tìm OC", module, filter_kind, ""
        )
        == expected
    )


def test_a_module_that_could_not_open_names_the_module(monkeypatch):
    detail = telemetry._fallback_error_detail(
        "open_module", "MODULE_MENU_NOT_FOUND", "Mở module", "OC List", "", ""
    )

    assert "OC List" in detail
    assert "MODULE_MENU_NOT_FOUND" in detail


def test_a_module_open_without_a_name_still_reads_sensibly():
    detail = telemetry._fallback_error_detail(
        "open_module_new", "MODULE_MENU_NOT_FOUND", "Mở New", "", "", ""
    )

    assert "module được chọn" in detail


def test_a_division_switch_names_the_division_it_was_going_to():
    detail = telemetry._fallback_error_detail(
        "switch_division", "DIVISION_NOT_CONFIRMED", "Đổi Division", "", "", "WOVEN"
    )

    assert "WOVEN" in detail


def test_a_code_with_no_special_rule_still_mentions_the_flow_and_the_code():
    detail = telemetry._fallback_error_detail(
        "apply_costing", "COSTING_APPLY_FAILED", "Áp dụng Costing", "", "", ""
    )

    assert "Áp dụng Costing" in detail
    assert "COSTING_APPLY_FAILED" in detail


# --- đọc endpoint từ .env ----------------------------------------------


def test_a_missing_env_file_yields_no_endpoint(tmp_path):
    assert telemetry._read_env_value(tmp_path / "khong-co.env", "KEY") == ""


def test_an_env_file_that_cannot_be_read_yields_no_endpoint(
    tmp_path, monkeypatch
):
    path = tmp_path / ".env"
    path.write_text("KEY=value", encoding="utf-8")
    real_read = type(path).read_text

    def refuse(self, **kwargs):
        if self == path:
            raise PermissionError("file đang bị khóa")
        return real_read(self, **kwargs)

    monkeypatch.setattr(type(path), "read_text", refuse)

    assert telemetry._read_env_value(path, "KEY") == ""


def test_comments_blank_lines_and_other_keys_are_skipped(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "\n# ghi chu\nKHONG_CO_DAU_BANG\nKHAC=x\nKEY=https://a.example/hook\n",
        encoding="utf-8",
    )

    assert telemetry._read_env_value(path, "KEY") == "https://a.example/hook"


def test_a_json_quoted_value_is_unwrapped(tmp_path):
    path = tmp_path / ".env"
    path.write_text('KEY="https://a.example/hook"\n', encoding="utf-8")

    assert telemetry._read_env_value(path, "KEY") == "https://a.example/hook"


def test_a_value_that_is_not_json_keeps_its_own_quotes_stripped(tmp_path):
    path = tmp_path / ".env"
    path.write_text("KEY='https://a.example/hook'\n", encoding="utf-8")

    assert telemetry._read_env_value(path, "KEY") == "https://a.example/hook"


# --- outbox -------------------------------------------------------------


def test_a_missing_outbox_reads_as_empty(tmp_path):
    assert telemetry._load_outbox(tmp_path) == []


def test_a_corrupt_outbox_reads_as_empty_instead_of_crashing(tmp_path):
    telemetry._outbox_path(tmp_path).write_text("{", encoding="utf-8")

    assert telemetry._load_outbox(tmp_path) == []


def test_an_outbox_that_is_not_a_list_reads_as_empty(tmp_path):
    telemetry._outbox_path(tmp_path).write_text('{"a": 1}', encoding="utf-8")

    assert telemetry._load_outbox(tmp_path) == []


def test_writing_an_empty_outbox_removes_the_file(tmp_path):
    path = telemetry._outbox_path(tmp_path)
    telemetry._write_outbox(tmp_path, [_event()])
    assert path.is_file()

    telemetry._write_outbox(tmp_path, [])

    assert not path.is_file()


def test_removing_an_outbox_that_is_locked_does_not_raise(
    tmp_path, monkeypatch
):
    telemetry._write_outbox(tmp_path, [_event()])
    path = telemetry._outbox_path(tmp_path)

    def refuse(self, **_kwargs):
        raise PermissionError("file đang bị khóa")

    monkeypatch.setattr(type(path), "unlink", refuse)

    telemetry._write_outbox(tmp_path, [])


def test_the_outbox_never_grows_past_its_cap(tmp_path):
    for index in range(telemetry.MAX_OUTBOX + 10):
        size = telemetry.enqueue(tmp_path, _event(run_id=f"run-{index}"))

    assert size == telemetry.MAX_OUTBOX
    rows = telemetry._load_outbox(tmp_path)
    assert len(rows) == telemetry.MAX_OUTBOX
    # Giữ lại các dòng mới nhất, bỏ dòng cũ.
    assert rows[-1]["run_id"] == f"run-{telemetry.MAX_OUTBOX + 9}"


def test_an_event_carrying_an_object_json_cannot_encode_is_stringified(tmp_path):
    class Weird:
        def __str__(self):
            return "doi-tuong-la"

    telemetry.enqueue(tmp_path, _event(diagnostics={"probe": Weird()}))

    rows = telemetry._load_outbox(tmp_path)
    assert rows[0]["diagnostics"]["probe"] == "doi-tuong-la"
    assert rows[0]["schema"] == telemetry.SCHEMA_VERSION
    assert rows[0]["timestamp"]


def test_nested_lists_and_tuples_survive_the_json_pass(tmp_path):
    telemetry.enqueue(tmp_path, _event(errors=("a", ["b", 1], None, True)))

    assert telemetry._load_outbox(tmp_path)[0]["errors"] == [
        "a",
        ["b", 1],
        None,
        True,
    ]


# --- payload gửi đi -----------------------------------------------------


def test_a_discord_webhook_gets_an_embed_not_the_raw_event(monkeypatch):
    sent = _wire_urlopen(monkeypatch)

    telemetry._post(DISCORD, _event())

    payload = sent[0]["payload"]
    assert payload["username"] == "WFX Smart Reporter"
    assert payload["allowed_mentions"] == {"parse": []}
    embed = payload["embeds"][0]
    assert embed["title"] == "WFX Smart · Báo lỗi"
    assert embed["description"] == "Grid Catalog chưa ổn định."
    names = {field["name"] for field in embed["fields"]}
    assert {"Code", "Method", "Run Id", "User Id", "Division Name"} <= names


def test_a_feedback_event_uses_its_own_title(monkeypatch):
    sent = _wire_urlopen(monkeypatch)

    telemetry._post(DISCORD, _event(event_type="feedback"))

    assert sent[0]["payload"]["embeds"][0]["title"] == "WFX Smart · Góp ý"


def test_empty_fields_are_left_out_of_the_embed(monkeypatch):
    sent = _wire_urlopen(monkeypatch)

    telemetry._post(
        DISCORD,
        _event(method="", run_id=None, account={"user_id": "t", "company_id": ""}),
    )

    names = {field["name"] for field in sent[0]["payload"]["embeds"][0]["fields"]}
    assert "Method" not in names
    assert "Run Id" not in names
    assert "Company Id" not in names


def test_an_account_that_is_not_an_object_is_simply_ignored(monkeypatch):
    sent = _wire_urlopen(monkeypatch)

    telemetry._post(DISCORD, _event(account="khong phai dict"))

    names = {field["name"] for field in sent[0]["payload"]["embeds"][0]["fields"]}
    assert "User Id" not in names


def test_an_event_without_a_message_still_says_something_useful(monkeypatch):
    sent = _wire_urlopen(monkeypatch)

    telemetry._post(DISCORD, _event(message=""))

    description = sent[0]["payload"]["embeds"][0]["description"]
    assert "không kèm dữ liệu nghiệp vụ" in description


def test_long_values_are_truncated_before_they_leave_the_machine(monkeypatch):
    sent = _wire_urlopen(monkeypatch)

    telemetry._post(
        DISCORD, _event(message="x" * 6_000, code="y" * 2_000)
    )

    embed = sent[0]["payload"]["embeds"][0]
    assert len(embed["description"]) == 4_000
    code_field = next(
        field for field in embed["fields"] if field["name"] == "Code"
    )
    assert len(code_field["value"]) == 1_000


def test_a_plain_webhook_receives_the_event_exactly_as_queued(monkeypatch):
    sent = _wire_urlopen(monkeypatch)
    event = _event()

    telemetry._post(PLAIN, event)

    assert sent[0]["payload"] == event
    assert sent[0]["url"] == PLAIN


def test_the_request_identifies_the_app_and_sends_json(monkeypatch):
    sent = _wire_urlopen(monkeypatch)

    telemetry._post(PLAIN, _event())

    headers = {key.casefold(): value for key, value in sent[0]["headers"].items()}
    assert headers["content-type"] == "application/json"
    assert headers["user-agent"] == "WFX-Smart-Reporter/1"


def test_a_webhook_that_answers_with_an_error_status_is_a_failure(monkeypatch):
    _wire_urlopen(monkeypatch, FakeResponse(status=500))

    with pytest.raises(HTTPError):
        telemetry._post(PLAIN, _event())


def test_a_discordapp_host_is_also_treated_as_discord(monkeypatch):
    sent = _wire_urlopen(monkeypatch)

    telemetry._post(
        "https://discordapp.com/api/webhooks/1/x", _event()
    )

    assert "embeds" in sent[0]["payload"]
