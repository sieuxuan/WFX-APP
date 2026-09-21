"""Vỏ `(GDN) Dispatch`: sáu bước tiến độ và ranh giới Create Transaction.

CLAUDE.md coi `Create Transaction` là ranh giới KHÔNG idempotent: sau khi click,
tuyệt đối không tự retry; mất xác nhận thì trả `GDN_TRANSACTION_UNCONFIRMED` và
hướng người dùng đi kiểm tra EDI, không gợi ý Submit lại.
"""

from __future__ import annotations

from typing import Any

import pytest

import wfx_panel.automation.dispatch.flows as flows
from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import FakeClock
from wfx_panel.automation._common import PlaywrightTimeoutError
from wfx_panel.automation.dispatch.constants import PACKAGE_LABEL
from wfx_panel.automation.dispatch.status import DispatchFlowError

INVOICE = "18.26.PSTT.DT"


@pytest.fixture
def clock():
    return FakeClock()


class EdiPage(FakePage):
    """FakePage + đăng ký listener dialog như Playwright Page thật."""

    def __init__(self, clock, **kwargs):
        super().__init__(clock, **kwargs)
        self.listeners: list[tuple[str, Any]] = []
        self.remove_error: BaseException | None = None

    def on(self, event, handler):
        self.listeners.append((event, handler))

    def remove_listener(self, event, handler):
        if self.remove_error is not None:
            raise self.remove_error
        self.listeners.remove((event, handler))


def _wire(monkeypatch, clock, **overrides):
    page = EdiPage(clock)
    world = WfxWorld(clock, [page])
    wire_automation(monkeypatch, flows, world)
    defaults = {
        "_prepare_dispatch_workbook": (
            lambda _context, _invoice, folder, _log, _stage: folder / "gdn.xlsx"
        ),
        "_open_edi": lambda _page, _log: "edi-frame",
        "_edi_rows": lambda _frame: [{"row_id": "cu"}],
        "_process_package": (
            lambda *_a, **_k: {"row_id": "moi", "transaction_detail": "Pending"}
        ),
        "_select_transaction": lambda *_a, **_k: None,
        "_create_transaction_link": lambda _frame: "link",
        "_click": lambda _target: None,
        "_wait_transaction_result": lambda *_a, **_k: (True, ["Success"]),
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        patch_automation(monkeypatch, flows, name, value)
    return world, page


def _run(monkeypatch, clock, invoice=INVOICE, **overrides):
    stages: list[tuple] = []
    world, page = _wire(monkeypatch, clock, **overrides)
    result = flows.run_gdn_dispatch(
        invoice,
        lambda _line: None,
        lambda *args, **kwargs: stages.append((args, kwargs)),
    )
    return result, stages, world, page


# --- kiểm tra Invoice ---------------------------------------------------


@pytest.mark.parametrize(
    ("invoice", "code"),
    [
        ("   ", "GDN_INVOICE_REQUIRED"),
        ("", "GDN_INVOICE_REQUIRED"),
        ("X" * 101, "GDN_INVOICE_INVALID"),
        ("INV\x01-1", "GDN_INVOICE_INVALID"),
    ],
)
def test_a_bad_invoice_never_opens_the_browser(
    monkeypatch, clock, invoice, code
):
    result, _stages, world, _page = _run(monkeypatch, clock, invoice)

    assert result["code"] == code
    assert world.driver_starts == 0


# --- đường đi thành công ------------------------------------------------


def test_a_successful_run_streams_all_six_steps_in_order(monkeypatch, clock):
    result, stages, _world, _page = _run(monkeypatch, clock)

    assert result["code"] == "GDN_DISPATCH_COMPLETED"
    assert result["transaction_submitted"] is True
    assert result["confirmations"] == ["Success"]
    assert result["safe_to_retry"] is False
    assert [args[0] for args, _kwargs in stages] == [
        "report",
        "edi",
        "package",
        "transaction",
        "transaction",
    ]
    assert stages[-1][1]["state"] == "completed"


def test_only_the_package_row_created_by_this_run_is_selected(
    monkeypatch, clock
):
    seen: list[set[str]] = []

    def process(_page, _frame, _upload, known_ids, _log):
        seen.append(set(known_ids))
        return {"row_id": "moi"}

    _result, _stages, _world, _page = _run(
        monkeypatch, clock, _process_package=process
    )

    assert seen == [{"cu"}]


def test_the_dialog_listener_is_removed_once_the_transaction_settles(
    monkeypatch, clock
):
    _result, _stages, _world, page = _run(monkeypatch, clock)

    assert page.listeners == []


def test_a_listener_that_cannot_be_removed_does_not_fail_the_run(
    monkeypatch, clock
):
    stages: list[tuple] = []
    world, page = _wire(monkeypatch, clock)
    page.remove_error = RuntimeError("target đã đóng")

    result = flows.run_gdn_dispatch(
        INVOICE, lambda _line: None, lambda *a, **k: stages.append((a, k))
    )

    assert result["code"] == "GDN_DISPATCH_COMPLETED"
    assert world.driver_stops == 1


def test_a_wfx_dialog_is_accepted_and_kept_as_evidence(monkeypatch, clock):
    captured: list[list[str]] = []

    class Dialog:
        message = "  Transaction created  successfully  "

        def __init__(self):
            self.accepted = 0

        def accept(self):
            self.accepted += 1

    dialog = Dialog()

    def wait_result(_page, _frame, _row_id, dialog_messages):
        captured.append(list(dialog_messages))
        return True, ["Success"]

    world, page = _wire(
        monkeypatch, clock, _wait_transaction_result=wait_result
    )

    def click(_target):
        for event, handler in page.listeners:
            if event == "dialog":
                handler(dialog)

    patch_automation(monkeypatch, flows, "_click", click)

    flows.run_gdn_dispatch(INVOICE, lambda _line: None)

    assert dialog.accepted == 1
    assert captured == [["Transaction created successfully"]]
    del world


# --- transaction không được xác nhận ------------------------------------


def test_an_unconfirmed_transaction_is_never_offered_for_a_retry(
    monkeypatch, clock
):
    result, stages, _world, _page = _run(
        monkeypatch,
        clock,
        _wait_transaction_result=lambda *_a, **_k: (False, ["In Progress"]),
    )

    assert result["code"] == "GDN_TRANSACTION_UNCONFIRMED"
    assert result["safe_to_retry"] is False
    assert result["checkpoint"] == "inspect_edi"
    assert "Không tự chạy lại" in result["message"]
    assert stages[-1][1]["state"] == "pending"


def test_a_transaction_wfx_rejected_is_reported_as_a_failure(monkeypatch, clock):
    result, stages, _world, _page = _run(
        monkeypatch,
        clock,
        _wait_transaction_result=lambda *_a, **_k: (False, ["Fail"]),
    )

    assert result["code"] == "GDN_TRANSACTION_FAILED"
    assert result["errors"] == ["Fail"]
    assert stages[-1][1]["state"] == "failed"
    assert result["safe_to_retry"] is False


# --- lỗi trước khi chạm EDI --------------------------------------------


def test_a_report_that_fails_is_still_safe_to_retry(monkeypatch, clock):
    def explode(*_args, **_kwargs):
        raise DispatchFlowError(
            "GDN_REPORT_NOT_READY",
            "Report chưa load xong.",
            errors=["Doc No. trống"],
        )

    result, stages, _world, _page = _run(
        monkeypatch, clock, _prepare_dispatch_workbook=explode
    )

    assert result["code"] == "GDN_REPORT_NOT_READY"
    assert result["errors"] == ["Doc No. trống"]
    assert result["safe_to_retry"] is True
    assert result["checkpoint"] == "restart_safe"
    assert stages[-1][1]["state"] == "failed"


def test_a_package_that_is_still_pending_shows_a_pending_step(monkeypatch, clock):
    def explode(*_args, **_kwargs):
        raise DispatchFlowError(
            "GDN_PENDING_NOT_FOUND", "Chưa thấy dòng Pending mới."
        )

    result, stages, _world, _page = _run(
        monkeypatch, clock, _process_package=explode
    )

    assert result["code"] == "GDN_PENDING_NOT_FOUND"
    assert stages[-1][1]["state"] == "pending"
    # Từ bước Process Package trở đi là checkpoint phải kiểm tra EDI.
    assert result["checkpoint"] == "inspect_edi"
    assert result["safe_to_retry"] is False


@pytest.mark.parametrize(
    ("chrome_ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_the_browser_boundary_codes_keep_their_own_message(
    monkeypatch, clock, chrome_ready, logged_in, expected
):
    world = WfxWorld(clock, [EdiPage(clock)])
    wire_automation(
        monkeypatch,
        flows,
        world,
        chrome_ready=chrome_ready,
        logged_in=logged_in,
    )
    stages: list[tuple] = []

    result = flows.run_gdn_dispatch(
        INVOICE, lambda _line: None, lambda *a, **k: stages.append((a, k))
    )

    assert result["code"] == expected
    assert result["transaction_submitted"] is False
    assert result["safe_to_retry"] is True
    assert stages[-1][1]["state"] == "failed"


def test_an_unexpected_runtime_error_is_not_swallowed(monkeypatch, clock):
    def explode(*_args, **_kwargs):
        raise RuntimeError("DIVISION_LOCKED")

    _world, _page = _wire(monkeypatch, clock, _open_edi=explode)

    with pytest.raises(RuntimeError, match="DIVISION_LOCKED"):
        flows.run_gdn_dispatch(INVOICE, lambda _line: None)


def test_a_timeout_before_the_transaction_is_an_edi_readiness_problem(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise PlaywrightTimeoutError("EDI chưa render")

    result, stages, _world, _page = _run(
        monkeypatch, clock, _open_edi=explode
    )

    assert result["code"] == "GDN_EDI_NOT_READY"
    assert result["errors"] == ["EDI chưa render"]
    assert stages[-1][1]["state"] == "failed"


def test_a_timeout_after_the_transaction_became_unconfirmed(monkeypatch, clock):
    def explode(*_args, **_kwargs):
        raise PlaywrightTimeoutError("WFX không phản hồi")

    result, stages, _world, _page = _run(
        monkeypatch, clock, _wait_transaction_result=explode
    )

    assert result["code"] == "GDN_TRANSACTION_UNCONFIRMED"
    assert result["transaction_submitted"] is True
    assert "Không tự chạy lại" in result["message"]
    assert stages[-1][1]["state"] == "pending"


def test_an_unexpected_error_before_the_transaction_is_a_plain_failure(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise ValueError("selector lạ")

    result, stages, _world, _page = _run(
        monkeypatch, clock, _open_edi=explode
    )

    assert result["code"] == "GDN_DISPATCH_FAILED"
    assert result["errors"] == ["ValueError: selector lạ"]
    assert stages[-1][1]["state"] == "failed"


def test_an_unexpected_error_after_the_transaction_stays_unconfirmed(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise ValueError("DOM đổi giữa chừng")

    result, _stages, _world, _page = _run(
        monkeypatch, clock, _wait_transaction_result=explode
    )

    assert result["code"] == "GDN_TRANSACTION_UNCONFIRMED"
    assert result["transaction_submitted"] is True
    assert result["safe_to_retry"] is False


# --- mở EDI ở chế độ chỉ đọc -------------------------------------------


def _wire_status(monkeypatch, clock, rows, **overrides):
    world = WfxWorld(clock, [EdiPage(clock)])
    wire_automation(monkeypatch, flows, world)
    patch_automation(monkeypatch, flows, "_open_edi", lambda *_a: "edi-frame")
    patch_automation(monkeypatch, flows, "_edi_rows", lambda _frame: rows)
    for name, value in overrides.items():
        patch_automation(monkeypatch, flows, name, value)
    return world


def _package_row(detail="Pending", processed="03/01/2026 10:00:00", name=None):
    return {
        "package_name": PACKAGE_LABEL if name is None else name,
        "transaction_detail": detail,
        "processed_on": processed,
    }


def test_opening_the_status_screen_reports_the_latest_gdn_package(
    monkeypatch, clock
):
    world = _wire_status(
        monkeypatch,
        clock,
        [
            _package_row("Completed", "03/01/2026 09:00:00"),
            _package_row("Pending", "03/01/2026 11:00:00"),
            _package_row(name="Mot package khac"),
        ],
    )

    result = flows.open_gdn_status(lambda _line: None)

    assert result["code"] == "GDN_STATUS_READY"
    assert result["package_count"] == 2
    assert result["latest_status"] == "Pending"
    assert "Pending" in result["message"]
    assert world.driver_stops == 1


def test_a_screen_without_any_gdn_package_still_opens_cleanly(
    monkeypatch, clock
):
    _wire_status(monkeypatch, clock, [_package_row(name="Khac")])

    result = flows.open_gdn_status(lambda _line: None)

    assert result["package_count"] == 0
    assert result["latest_status"] == ""
    assert "để kiểm tra package GDN" in result["message"]


def test_the_status_screen_never_creates_a_transaction(monkeypatch, clock):
    _wire_status(monkeypatch, clock, [_package_row()])
    patch_automation(
        monkeypatch,
        flows,
        "_click",
        lambda _target: pytest.fail("Màn chỉ đọc không được click gì"),
    )

    assert flows.open_gdn_status(lambda _line: None)["ok"] is True


def test_a_dispatch_error_while_opening_the_status_keeps_its_code(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise DispatchFlowError(
            "GDN_EDI_MENU_NOT_FOUND",
            "Không thấy menu EDI.",
            errors=["xpath sai"],
        )

    _wire_status(monkeypatch, clock, [], _open_edi=explode)

    result = flows.open_gdn_status(lambda _line: None)

    assert result["code"] == "GDN_EDI_MENU_NOT_FOUND"
    assert result["errors"] == ["xpath sai"]


def test_an_unexpected_error_while_opening_the_status_is_named(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise ValueError("frame lạ")

    _wire_status(monkeypatch, clock, [], _open_edi=explode)

    result = flows.open_gdn_status(lambda _line: None)

    assert result["code"] == "GDN_EDI_NOT_READY"
    assert result["errors"] == ["ValueError: frame lạ"]


@pytest.mark.parametrize(
    ("chrome_ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_the_status_screen_maps_the_browser_boundary_codes(
    monkeypatch, clock, chrome_ready, logged_in, expected
):
    world = WfxWorld(clock, [EdiPage(clock)])
    wire_automation(
        monkeypatch,
        flows,
        world,
        chrome_ready=chrome_ready,
        logged_in=logged_in,
    )

    assert flows.open_gdn_status(lambda _line: None)["code"] == expected
    assert world.driver_stops == 1
