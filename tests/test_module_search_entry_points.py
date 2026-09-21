"""Lớp Search dùng chung của `modules.py` — vỏ chưa từng chạy trong test.

`_search_module_list` và `_search_module_fields` là đường đi của *mọi* nút Tìm
trong app (OC, Sample, Sale ASN, RMPO, Advance PR, Supplier/Expense Invoice…).
Cả hai tự mở Playwright nên trước đây không có seam, và ở lại mức 2% coverage —
tức toàn bộ phần phân loại lỗi và thông điệp gửi tới người dùng chưa được kiểm.

Quy tắc CLAUDE.md mà lớp này phải giữ:

* Search **không được** trả `*_LIST_NOT_OPEN` hay bảo người dùng bấm List. Nếu
  đã tự mở mà vẫn không sẵn sàng thì phải trả lỗi kỹ thuật cụ thể, nói rõ là app
  đã tự mở rồi.
* Thiếu điều kiện tìm là lỗi người dùng: phải chặn trước khi chạm Chrome.
* Phân biệt được "chưa nhập gì" (`NOT_READY`) với "đã nhập nhưng WFX chưa xác
  nhận" (`NOT_CONFIRMED`), vì hai tình huống này người dùng xử lý khác nhau.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import modules
from wfx_panel.automation.search_specs import (
    OC_SEARCH_SPEC,
    RMPO_SEARCH_SPEC,
)

LIST_XPATH = '//*[@id="0003_1000"]/a'


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, modules)


@pytest.fixture
def world(clock):
    return WfxWorld(clock)


def _logs() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lines.append


def _search(query: str = "OC-1", kind: str = "oc_no", log=None) -> dict:
    return modules._search_module_list(
        OC_SEARCH_SPEC,
        LIST_XPATH,
        kind,
        query,
        log or _logs()[1],
    )


def _stub_context(monkeypatch, *, frame: object = "frame") -> None:
    monkeypatch.setattr(
        modules,
        "_open_list_search_context",
        lambda *_args, **_kwargs: frame,
    )
    monkeypatch.setattr(
        modules,
        "_clear_list_search_fields",
        lambda *_args, **_kwargs: None,
    )


# --- Lỗi người dùng: chặn trước khi chạm Chrome -------------------------


def test_an_unknown_filter_kind_never_opens_the_browser(monkeypatch, world):
    wire_automation(monkeypatch, modules, world)

    result = _search(kind="khong_ton_tai")

    assert result["ok"] is False
    assert result["code"] == "INVALID_FILTER"
    assert world.driver_starts == 0


@pytest.mark.parametrize("query", ["", "   ", None])
def test_a_blank_query_never_opens_the_browser(monkeypatch, world, query):
    wire_automation(monkeypatch, modules, world)

    result = _search(query=query)

    assert result["code"] == "QUERY_REQUIRED"
    assert "OC No." in result["message"]
    assert world.driver_starts == 0


def test_multi_field_search_needs_at_least_one_condition(monkeypatch, world):
    """Form nhiều điều kiện: trống hết thì nêu đủ nhãn cho người dùng biết."""
    wire_automation(monkeypatch, modules, world)

    result = modules._search_module_fields(
        RMPO_SEARCH_SPEC,
        LIST_XPATH,
        dict.fromkeys(RMPO_SEARCH_SPEC.fields, ""),
        _logs()[1],
    )

    assert result["code"] == "QUERY_REQUIRED"
    for field_spec in RMPO_SEARCH_SPEC.fields.values():
        assert field_spec.label in result["message"]
    assert world.driver_starts == 0


# --- Đường thành công ---------------------------------------------------


def test_a_successful_search_names_the_module_and_the_filter(monkeypatch, world):
    wire_automation(monkeypatch, modules, world)
    _stub_context(monkeypatch)
    monkeypatch.setattr(
        modules,
        "_search_input_in_frame",
        lambda *_args, **_kwargs: "field",
    )
    applied = {}

    def record(_page, _field, query, label, _log):
        applied["query"] = query
        applied["label"] = label

    monkeypatch.setattr(modules, "_apply_module_search", record)

    result = _search(query="OC-99")

    assert result["code"] == "MODULE_SEARCH_APPLIED"
    assert result["module"] == "OC List"
    assert result["filter_kind"] == "OC No."
    assert applied == {"query": "OC-99", "label": "OC No."}
    assert world.driver_stops == 1


# --- Phân loại lỗi kỹ thuật --------------------------------------------


def test_a_field_that_never_appears_says_the_app_already_opened_the_list(
    monkeypatch,
    world,
):
    """CLAUDE.md: không được trả *_LIST_NOT_OPEN hay bảo người dùng bấm List."""
    wire_automation(monkeypatch, modules, world)
    _stub_context(monkeypatch)

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("ô tìm chưa render")

    monkeypatch.setattr(modules, "_search_input_in_frame", slow)

    result = _search()

    assert result["code"] == "MODULE_SEARCH_NOT_READY"
    assert "App đã tự mở" in result["message"]
    assert result["module"] == "OC List"
    assert result["filter_kind"] == "OC No."


def test_a_search_that_was_typed_but_not_confirmed_is_reported_differently(
    monkeypatch,
    world,
):
    wire_automation(monkeypatch, modules, world)
    _stub_context(monkeypatch)
    monkeypatch.setattr(
        modules,
        "_search_input_in_frame",
        lambda *_args, **_kwargs: "field",
    )

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("grid chưa ổn định")

    monkeypatch.setattr(modules, "_apply_module_search", slow)

    result = _search()

    assert result["code"] == "MODULE_SEARCH_NOT_CONFIRMED"
    assert "chưa xác nhận" in result["message"]


def test_an_unexpected_error_falls_back_to_module_search_failed(
    monkeypatch,
    world,
):
    wire_automation(monkeypatch, modules, world)
    _stub_context(monkeypatch)

    def boom(*_args, **_kwargs):
        raise ValueError("WFX đổi DOM")

    monkeypatch.setattr(modules, "_search_input_in_frame", boom)

    result = _search()

    assert result["code"] == "MODULE_SEARCH_FAILED"
    assert result["module"] == "OC List"
    assert world.driver_stops == 1


@pytest.mark.parametrize(
    ("ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_search_reports_browser_boundary_codes(
    monkeypatch,
    world,
    ready,
    logged_in,
    expected,
):
    wire_automation(
        monkeypatch,
        modules,
        world,
        chrome_ready=ready,
        logged_in=logged_in,
    )

    result = _search()

    assert result["code"] == expected
    assert result["module"] == "OC List"


# --- Hợp đồng: Search không bao giờ đổ lỗi "chưa mở List" ---------------


@pytest.mark.parametrize(
    "failure",
    [
        PlaywrightTimeoutError("ô tìm chưa render"),
        ValueError("WFX đổi DOM"),
        RuntimeError("CHROME_CLOSED"),
        RuntimeError("NOT_LOGGED_IN"),
    ],
    ids=["timeout", "unexpected", "chrome-closed", "session-lost"],
)
def test_search_never_tells_the_user_to_open_the_list_first(
    monkeypatch,
    world,
    failure,
):
    wire_automation(monkeypatch, modules, world)
    _stub_context(monkeypatch)

    def boom(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(modules, "_search_input_in_frame", boom)

    result = _search()

    assert not result["code"].endswith("_LIST_NOT_OPEN")
    lowered = result["message"].casefold()
    assert "bấm list" not in lowered
    assert "mở list trước" not in lowered


def test_an_unrelated_runtime_error_is_not_disguised_as_a_browser_code(
    monkeypatch,
    world,
):
    """Chỉ CHROME_CLOSED/NOT_LOGGED_IN mới được map sang mã ranh giới."""
    wire_automation(monkeypatch, modules, world)
    _stub_context(monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("Đã kết nối Chrome nhưng không tìm thấy browser context.")

    monkeypatch.setattr(modules, "_search_input_in_frame", boom)

    result = _search()

    assert result["code"] == "MODULE_SEARCH_FAILED"
    assert result["module"] == "OC List"


def test_multi_field_search_also_keeps_unrelated_runtime_errors_distinct(
    monkeypatch,
    world,
):
    wire_automation(monkeypatch, modules, world)
    monkeypatch.setattr(
        modules,
        "_open_multi_field_search_context",
        lambda *_a, **_k: "frame",
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("Đã kết nối Chrome nhưng không tìm thấy browser context.")

    monkeypatch.setattr(modules, "_resolve_multi_search_fields", boom)

    result = modules._search_module_fields(
        RMPO_SEARCH_SPEC,
        LIST_XPATH,
        {"order_no": "2345"},
        _logs()[1],
    )

    assert result["code"] == "MODULE_SEARCH_FAILED"
