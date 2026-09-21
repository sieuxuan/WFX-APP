"""Vỏ `run_gdn_dispatch` — nơi quyết định người dùng có được Submit lại không.

`dispatch.py` ở mức 19% coverage vì entry point duy nhất tự mở Playwright.
Chính vỏ đó quyết định hai thứ CLAUDE.md ràng buộc chặt:

* `Create Transaction` là ranh giới **không idempotent**: mất xác nhận phải trả
  `GDN_TRANSACTION_UNCONFIRMED` và **không tự retry**.
* Lỗi từ bước `Process Package` trở đi là checkpoint **cần kiểm tra EDI**, không
  được gợi ý Submit lại — thể hiện qua `checkpoint`/`safe_to_retry`.

Thẻ tiến độ sáu bước (`report`/`download`/`workbook`/`edi`/`package`/
`transaction`) cũng phải phản ánh đúng bước đang hỏng.
"""

from __future__ import annotationsimport pytestfrom playwright.sync_api import TimeoutError as PlaywrightTimeoutErrorfrom tests.fakes.automation_boundary import WfxWorld, wire_automationfrom tests.fakes.wfx_dom import install_fake_clockfrom wfx_panel.automation import dispatch@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, dispatch)


@pytest.fixture
def world(clock):
    return WfxWorld(clock)


def _quiet():
    return lambda _line: None


class Progress:
    """Ghi lại đúng chuỗi bước mà UI nhận được."""

    def __init__(self) -> None:
        self.events: list[tuple[str, int, str]] = []

    def __call__(
        self,
        stage: str,
        message: str,
        step: int,
        total: int | None = None,
        *,
        state: str = "active",
    ) -> None:
        self.events.append((stage, step, state))

    @property
    def stages(self) -> list[str]:
        return [name for name, _step, _state in self.events]

    def failed_stage(self) -> str | None:
        return next(
            (name for name, _s, state in reversed(self.events) if state == "failed"),
            None,
        )


def _run(world: WfxWorld, invoice: str = "INV-001", progress=None) -> dict:
    return dispatch.run_gdn_dispatch(invoice, _quiet(), progress)


# --- Lỗi nhập liệu: chặn trước khi chạm Chrome -------------------------


@pytest.mark.parametrize("invoice", ["", "   ", None])
def test_a_missing_invoice_never_opens_the_browser(monkeypatch, world, invoice):
    wire_automation(monkeypatch, dispatch, world)

    result = _run(world, invoice)

    assert result["code"] == "GDN_INVOICE_REQUIRED"
    assert world.driver_starts == 0


@pytest.mark.parametrize(
    "invoice",
    ["X" * 101, "INV\x00001", "INV\x1b001"],
    ids=["too-long", "nul", "escape"],
)
def test_a_malformed_invoice_never_opens_the_browser(monkeypatch, world, invoice):
    wire_automation(monkeypatch, dispatch, world)

    result = _run(world, invoice)

    assert result["code"] == "GDN_INVOICE_INVALID"
    assert world.driver_starts == 0


# --- Hỏng trước Process Package: an toàn để chạy lại -------------------


def test_a_failure_while_building_the_workbook_is_safe_to_retry(
    monkeypatch,
    world,
):
    wire_automation(monkeypatch, dispatch, world)
    progress = Progress()

    def boom(*_args, **_kwargs):
        raise dispatch.DispatchFlowError(
            "GDN_REPORT_NOT_READY",
            "Report Buyer Dispatch chưa tải xong.",
        )

    monkeypatch.setattr(dispatch, "_prepare_dispatch_workbook", boom)

    result = dispatch.run_gdn_dispatch("INV-001", _quiet(), progress)

    assert result["code"] == "GDN_REPORT_NOT_READY"
    assert result["transaction_submitted"] is False
    assert result["safe_to_retry"] is True
    assert result["checkpoint"] == "restart_safe"
    assert progress.stages[0] == "report"


def test_browser_boundary_before_any_upload_is_safe_to_retry(monkeypatch, world):
    wire_automation(monkeypatch, dispatch, world, chrome_ready=False)

    result = _run(world)

    assert result["code"] == "CHROME_CLOSED"
    assert result["transaction_submitted"] is False
    assert result["safe_to_retry"] is True
    assert world.driver_stops == 1


def test_an_expired_session_before_any_upload_is_safe_to_retry(monkeypatch, world):
    wire_automation(monkeypatch, dispatch, world, logged_in=False)

    result = _run(world)

    assert result["code"] == "NOT_LOGGED_IN"
    assert result["safe_to_retry"] is True


# --- Từ Process Package trở đi: phải đi kiểm tra EDI -------------------


def _reach_package(monkeypatch, *, fail_with):
    monkeypatch.setattr(
        dispatch,
        "_prepare_dispatch_workbook",
        lambda _ctx, _inv, _tmp, _log, stage: stage(
            "workbook", "Đã tạo workbook", 3
        )
        or "upload.xlsx",
    )
    monkeypatch.setattr(dispatch, "_open_edi", lambda *_a, **_k: "frame")
    monkeypatch.setattr(dispatch, "_edi_rows", lambda *_a, **_k: [])

    def boom(*_args, **_kwargs):
        raise fail_with

    monkeypatch.setattr(dispatch, "_process_package", boom)


def test_a_package_failure_sends_the_user_to_inspect_edi(monkeypatch, world):
    """CLAUDE.md: từ Process Package trở đi không được gợi ý Submit lại."""
    wire_automation(monkeypatch, dispatch, world)
    progress = Progress()
    _reach_package(
        monkeypatch,
        fail_with=dispatch.DispatchFlowError(
            "GDN_PACKAGE_PROCESS_FAILED",
            "Package bị Fail ở Mapping.",
        ),
    )

    result = dispatch.run_gdn_dispatch("INV-001", _quiet(), progress)

    assert result["code"] == "GDN_PACKAGE_PROCESS_FAILED"
    assert result["checkpoint"] == "inspect_edi"
    assert result["safe_to_retry"] is False, (
        "Gợi ý Submit lại sau khi package đã vào EDI sẽ tạo chứng từ trùng"
    )
    assert result["failed_stage"] == "package"
    assert progress.failed_stage() == "package"


def test_a_pending_row_not_found_is_a_pending_checkpoint(monkeypatch, world):
    wire_automation(monkeypatch, dispatch, world)
    progress = Progress()
    _reach_package(
        monkeypatch,
        fail_with=dispatch.DispatchFlowError(
            "GDN_PENDING_NOT_FOUND",
            "Chưa thấy dòng Pending mới.",
        ),
    )

    result = dispatch.run_gdn_dispatch("INV-001", _quiet(), progress)

    assert result["code"] == "GDN_PENDING_NOT_FOUND"
    assert result["checkpoint"] == "inspect_edi"
    assert result["safe_to_retry"] is False
    assert progress.events[-1][2] == "pending", (
        "Dòng Pending chưa xuất hiện là trạng thái chờ, không phải hỏng hẳn"
    )


def test_a_boundary_code_after_upload_is_no_longer_safe_to_retry(
    monkeypatch,
    world,
):
    """Trình duyệt đóng SAU khi package đã lên EDI vẫn phải đi kiểm tra EDI."""
    wire_automation(monkeypatch, dispatch, world)
    _reach_package(monkeypatch, fail_with=RuntimeError("CHROME_CLOSED"))

    result = dispatch.run_gdn_dispatch("INV-001", _quiet(), Progress())

    assert result["code"] == "CHROME_CLOSED"
    assert result["checkpoint"] == "inspect_edi"
    assert result["safe_to_retry"] is False


def test_a_timeout_at_the_package_stage_keeps_the_inspect_checkpoint(
    monkeypatch,
    world,
):
    wire_automation(monkeypatch, dispatch, world)
    _reach_package(monkeypatch, fail_with=PlaywrightTimeoutError("EDI chưa phản hồi"))

    result = dispatch.run_gdn_dispatch("INV-001", _quiet(), Progress())

    assert result["ok"] is False
    assert result["checkpoint"] == "inspect_edi"
    assert result["safe_to_retry"] is False
    assert world.driver_stops == 1


# --- Thứ tự sáu bước ----------------------------------------------------


def test_the_six_stages_are_streamed_in_order(monkeypatch, world):
    wire_automation(monkeypatch, dispatch, world)
    progress = Progress()
    monkeypatch.setattr(
        dispatch,
        "_prepare_dispatch_workbook",
        lambda _ctx, _inv, _tmp, _log, stage: [
            stage("download", "Đang tải Excel…", 2),
            stage("workbook", "Đang chuẩn hoá XLSX…", 3),
        ]
        and "upload.xlsx",
    )
    monkeypatch.setattr(dispatch, "_open_edi", lambda *_a, **_k: "frame")
    monkeypatch.setattr(dispatch, "_edi_rows", lambda *_a, **_k: [])

    def boom(*_args, **_kwargs):
        raise dispatch.DispatchFlowError("GDN_PACKAGE_PROCESS_FAILED", "Fail")

    monkeypatch.setattr(dispatch, "_process_package", boom)

    dispatch.run_gdn_dispatch("INV-001", _quiet(), progress)

    assert progress.stages[:5] == [
        "report",
        "download",
        "workbook",
        "edi",
        "package",
    ]
