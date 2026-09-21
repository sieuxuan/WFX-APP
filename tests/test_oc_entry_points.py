"""Vỏ entry point của module OC — phần `try/except` trước nay chưa từng chạy.

`tests/test_oc_automation.py` đã phủ rất tốt phần *lõi* (`_confirm_all_pending`,
`_reject_all_pending`, `_create_transaction`, `_wait_statuses`). Nhưng bốn hàm
người dùng thật sự gọi — `confirm_oc_pending`, `reject_all_oc_pending`,
`upload_oc_edi`, `open_oc_revision_report` — đều tự mở Playwright nên không có
seam để test, và ở lại mức 2–4% coverage.

Chính vỏ này quyết định hai thứ quan trọng nhất của OC:

* mã trả về khi trình duyệt đóng / phiên hết hạn, vì `PanelAPI` dựa vào đúng mã
  đó để tự mở lại Chrome và đăng nhập lại;
* cờ `transaction_submitted` / `confirmation_submitted` / `rejection_submitted`,
  vì `Create Transaction`, `Confirm` và `Reject` đều KHÔNG idempotent — báo sai
  cờ này là tạo chứng từ trùng.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import (
    FakePage,
    WfxWorld,
    wire_automation,
)
from tests.fakes.wfx_dom import FakeClock, FakeNode, install_fake_clock
from wfx_panel.automation import oc


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, oc)


@pytest.fixture
def world(clock):
    return WfxWorld(clock)


def _logs() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lines.append


def _quiet():
    return _logs()[1]


# --- Confirm New / Revision --------------------------------------------


@pytest.mark.parametrize("mode", ["new", "revision", "revise"])
def test_confirm_delegates_to_the_tested_core_for_valid_modes(
    monkeypatch,
    world,
    mode,
):
    wire_automation(monkeypatch, oc, world)
    seen = {}
    monkeypatch.setattr(oc, "_open_confirm_grid", lambda page, m, log: ("frame", m))

    def record_confirm(_page, _frame, resolved_mode, _log):
        seen["mode"] = resolved_mode
        return {"ok": True, "code": "OC_FAST_CONFIRM_DONE"}

    monkeypatch.setattr(oc, "_confirm_all_pending", record_confirm)

    result = oc.confirm_oc_pending(mode, log=_quiet())

    assert result["code"] == "OC_FAST_CONFIRM_DONE"
    assert seen["mode"] == ("revision" if mode in {"revision", "revise"} else "new")
    assert world.driver_stops == 1


@pytest.mark.parametrize("mode", ["", "Reject", "all", None])
def test_an_unknown_confirm_mode_never_opens_the_browser(monkeypatch, world, mode):
    wire_automation(monkeypatch, oc, world)

    result = oc.confirm_oc_pending(mode, log=_quiet())

    assert result["ok"] is False
    assert result["code"] == "OC_MODE_INVALID"
    assert world.driver_starts == 0, "Mode sai thì không được chạm Chrome"


@pytest.mark.parametrize(
    ("ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_confirm_reports_browser_boundary_codes_for_auto_recovery(
    monkeypatch,
    world,
    ready,
    logged_in,
    expected,
):
    """PanelAPI dựa vào đúng hai mã này để mở lại Chrome / đăng nhập lại."""
    wire_automation(
        monkeypatch,
        oc,
        world,
        chrome_ready=ready,
        logged_in=logged_in,
    )

    result = oc.confirm_oc_pending("new", log=_quiet())

    assert result["ok"] is False
    assert result["code"] == expected
    assert world.driver_stops == 1


def test_confirm_timeout_says_nothing_was_submitted(monkeypatch, world):
    wire_automation(monkeypatch, oc, world)

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("grid Confirm chưa render")

    monkeypatch.setattr(oc, "_open_confirm_grid", slow)

    result = oc.confirm_oc_pending("new", log=_quiet())

    assert result["code"] == "OC_FAST_CONFIRM_NOT_READY"
    assert result["confirmation_submitted"] is False, (
        "Báo sai cờ này khiến người dùng Confirm lại một Style đã Confirm"
    )
    assert result["mode"] == "new"


def test_confirm_unexpected_error_keeps_the_mode_and_the_flag(monkeypatch, world):
    wire_automation(monkeypatch, oc, world)

    def boom(*_args, **_kwargs):
        raise ValueError("WFX đổi DOM")

    monkeypatch.setattr(oc, "_open_confirm_grid", boom)

    result = oc.confirm_oc_pending("revision", log=_quiet())

    assert result["code"] == "OC_FAST_CONFIRM_FAILED"
    assert result["confirmation_submitted"] is False
    assert result["mode"] == "revision"
    assert world.driver_stops == 1


# --- Reject All · tab đang mở ------------------------------------------


def test_reject_all_uses_the_tab_currently_open_on_wfx(monkeypatch, world):
    """Nút chỉ xử lý tab đang chọn, không được tự chuyển tab."""
    wire_automation(monkeypatch, oc, world)
    seen = {}
    monkeypatch.setattr(oc, "_active_confirm_mode", lambda _page: "revision")
    monkeypatch.setattr(oc, "_set_confirm_page_size", lambda _page: "frame")

    def record_reject(_page, _frame, resolved_mode, _log):
        seen["mode"] = resolved_mode
        return {"ok": True, "code": "OC_REJECT_ALL_DONE"}

    monkeypatch.setattr(oc, "_reject_all_pending", record_reject)
    lines, log = _logs()

    result = oc.reject_all_oc_pending(log=log)

    assert result["code"] == "OC_REJECT_ALL_DONE"
    assert seen["mode"] == "revision"
    assert any("Revision" in line and "100" in line for line in lines), (
        "Phải đổi page size thành 100 và ghi rõ đang xử lý tab nào"
    )


def test_reject_all_timeout_says_nothing_was_rejected(monkeypatch, world):
    wire_automation(monkeypatch, oc, world)
    monkeypatch.setattr(oc, "_active_confirm_mode", lambda _page: "new")

    def slow(_page):
        raise PlaywrightTimeoutError("page size chưa đổi")

    monkeypatch.setattr(oc, "_set_confirm_page_size", slow)

    result = oc.reject_all_oc_pending(log=_quiet())

    assert result["code"] == "OC_REJECT_ALL_NOT_READY"
    assert result["rejection_submitted"] is False


def test_reject_all_reports_browser_boundary_codes(monkeypatch, world):
    wire_automation(monkeypatch, oc, world, chrome_ready=False)

    result = oc.reject_all_oc_pending(log=_quiet())

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_stops == 1


# --- Upload EDI: ranh giới không idempotent -----------------------------


def test_upload_refuses_a_missing_workbook_before_touching_chrome(
    monkeypatch,
    world,
    tmp_path,
):
    wire_automation(monkeypatch, oc, world)

    result = oc.upload_oc_edi(tmp_path / "khong-ton-tai.xlsx", "BUYER", "new", _quiet())

    assert result["code"] == "OC_UPLOAD_FILE_MISSING"
    assert world.driver_starts == 0


def test_upload_refuses_a_non_xlsx_file(monkeypatch, world, tmp_path):
    wire_automation(monkeypatch, oc, world)
    sneaky = tmp_path / "oc.xlsm"
    sneaky.write_bytes(b"PK\x03\x04")

    result = oc.upload_oc_edi(sneaky, "BUYER", "new", _quiet())

    assert result["code"] == "OC_UPLOAD_FILE_MISSING"
    assert world.driver_starts == 0


def _workbook(tmp_path):
    path = tmp_path / "oc.xlsx"
    path.write_bytes(b"PK\x03\x04")
    return path


def test_upload_reports_browser_boundary_codes(monkeypatch, world, tmp_path):
    wire_automation(monkeypatch, oc, world, logged_in=False)

    result = oc.upload_oc_edi(_workbook(tmp_path), "BUYER", "new", _quiet())

    assert result["code"] == "NOT_LOGGED_IN"
    assert world.driver_stops == 1


def test_upload_that_fails_before_submit_is_safe_to_retry(
    monkeypatch,
    world,
    tmp_path,
):
    wire_automation(monkeypatch, oc, world)

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("EDI Buyer PO chưa mở")

    monkeypatch.setattr(oc, "_open_edi_form", slow)

    result = oc.upload_oc_edi(_workbook(tmp_path), "BUYER", "new", _quiet())

    assert result["code"] == "OC_EDI_NOT_READY"
    assert result["transaction_submitted"] is False


def test_upload_failure_before_submit_never_reports_unconfirmed(
    monkeypatch,
    world,
    tmp_path,
):
    wire_automation(monkeypatch, oc, world)

    def boom(*_args, **_kwargs):
        raise ValueError("WFX đổi DOM")

    monkeypatch.setattr(oc, "_open_edi_form", boom)

    result = oc.upload_oc_edi(_workbook(tmp_path), "BUYER", "new", _quiet())

    assert result["code"] == "OC_EDI_FAILED"
    assert result["transaction_submitted"] is False, (
        "Báo UNCONFIRMED khi chưa hề submit sẽ khiến người dùng đi tìm một "
        "transaction không tồn tại"
    )


# --- Mở report Revise OC ------------------------------------------------


def _report_world(clock: FakeClock, *, node_ids, texts):
    candidates = []
    for node_id, text in zip(node_ids, texts, strict=True):
        node = FakeNode()
        node.text = text
        node.get_attribute = lambda name, value=node_id: (  # type: ignore[method-assign]
            value if name == "nodeid" else None
        )
        candidates.append(node)
    menu = FakeNode()
    tree = FakeNode()
    page = FakePage(
        clock,
        nodes={f"xpath={oc.REVISION_REPORT_MENU_XPATH}": [menu]},
    )
    page.report_nodes = candidates  # type: ignore[attr-defined]
    page.tree_node = tree  # type: ignore[attr-defined]
    page.menu_node = menu  # type: ignore[attr-defined]
    return WfxWorld(clock, [page])


def _wire_report_tree(monkeypatch, world):
    page = world.page
    tree_locator = _TreeLocator(page.report_nodes)  # type: ignore[attr-defined]
    monkeypatch.setattr(
        oc,
        "_visible_in_frames",
        lambda _page, _selector, **_kwargs: ("frame", tree_locator),
    )


class _TreeLocator:
    def __init__(self, nodes):
        self.nodes = nodes

    def locator(self, selector):
        assert selector == oc.REVISION_REPORT_SELECTOR
        return _Matches(self.nodes)


class _Matches:
    def __init__(self, nodes):
        self.nodes = nodes

    def count(self):
        return len(self.nodes)

    def nth(self, index):
        return self.nodes[index]


def test_revision_report_opens_node_258(monkeypatch, clock):
    world = _report_world(
        clock,
        node_ids=["101", "258"],
        texts=["Báo cáo khác", "Upload OC from OC_Sale"],
    )
    wire_automation(monkeypatch, oc, world)
    _wire_report_tree(monkeypatch, world)

    result = oc.open_oc_revision_report(log=_quiet())

    assert result["code"] == "OC_REVISION_REPORT_READY"
    assert result["report_node_id"] == "258"
    assert world.page.report_nodes[1].clicks == 1
    assert world.page.report_nodes[0].clicks == 0, "Không được mở nhầm report khác"


def test_revision_report_matches_by_name_when_the_node_id_moved(
    monkeypatch,
    clock,
):
    world = _report_world(
        clock,
        node_ids=["900"],
        texts=["Upload OC from OC_Sale"],
    )
    wire_automation(monkeypatch, oc, world)
    _wire_report_tree(monkeypatch, world)

    result = oc.open_oc_revision_report(log=_quiet())

    assert result["code"] == "OC_REVISION_REPORT_READY"
    assert world.page.report_nodes[0].clicks == 1


def test_revision_report_missing_is_reported_without_clicking(monkeypatch, clock):
    world = _report_world(clock, node_ids=["101"], texts=["Báo cáo khác"])
    wire_automation(monkeypatch, oc, world)
    _wire_report_tree(monkeypatch, world)

    result = oc.open_oc_revision_report(log=_quiet())

    assert result["ok"] is False
    assert result["code"] == "OC_REVISION_REPORT_NOT_READY"
    assert world.page.report_nodes[0].clicks == 0


def test_revision_report_reports_browser_boundary_codes(monkeypatch, clock):
    world = _report_world(clock, node_ids=["258"], texts=["Upload OC from OC_Sale"])
    wire_automation(monkeypatch, oc, world, chrome_ready=False)

    result = oc.open_oc_revision_report(log=_quiet())

    assert result["code"] == "CHROME_CLOSED"


def test_an_unrelated_runtime_error_is_not_disguised_as_a_browser_code(
    monkeypatch,
    clock,
):
    """Chỉ CHROME_CLOSED/NOT_LOGGED_IN mới được map sang mã ranh giới.

    Trước đây handler gán thẳng `code = str(error)` nên một RuntimeError khác
    biến thành "mã lỗi" là cả một câu tiếng Việt: không có trong
    ERROR_CODE_INFO lẫn NON_REPORTABLE_FAILURES.
    """
    world = _report_world(clock, node_ids=["258"], texts=["Upload OC from OC_Sale"])
    wire_automation(monkeypatch, oc, world)

    def boom(*_args, **_kwargs):
        raise RuntimeError("Đã kết nối Chrome nhưng không tìm thấy browser context.")

    monkeypatch.setattr(oc, "_visible_in_frames", boom)

    result = oc.open_oc_revision_report(log=_quiet())

    assert result["code"] == "OC_REVISION_REPORT_FAILED"
    assert "browser context" in result["message"]
