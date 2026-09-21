"""Quyết định Cancel/Delete Supplier Invoice — nhánh phá hủy dữ liệu.

`prepare_supplier_invoice_cancel` nhận đúng một Invoice No. từ người dùng rồi
tự bấm Delete (Status `Save`) hoặc Cancel (Status `Confirm`) trên WFX. Search
của WFX là tìm *chứa chuỗi*, nên một dòng kết quả duy nhất chưa chắc là invoice
người dùng gõ: `SI-102` có thể chỉ trả về `SI-1024`. Form trong app hứa "Nhập
chính xác Invoice No.", vì vậy lớp automation phải khớp exact trước khi bấm.
"""

from __future__ import annotations

import pytest

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import modules

CANCEL_XPATH = '//*[@id="0065_0880_0020_0020"]/a'


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, modules)


@pytest.fixture
def world(clock):
    return WfxWorld(clock)


def _row(invoice_no: str, *, status: str = "Confirm", key: str = "") -> dict:
    return {
        "row_key": key or f"row-{invoice_no}",
        "invoice_no": invoice_no,
        "supplier": "ACME",
        "po_no": "PO-1",
        "asn_grn_no": "GRN-1",
        "status": status,
    }


@pytest.fixture
def submitted(monkeypatch):
    """Chặn đúng bước bấm nút WFX và ghi lại dòng được chọn."""
    calls: list[dict] = []

    def fake_submit(_page, _frame, row, _log):
        calls.append(dict(row))
        return {"ok": True, "code": "SUPPLIER_INVOICE_CANCEL_SUBMITTED"}

    monkeypatch.setattr(modules, "_submit_supplier_invoice_cancel", fake_submit)
    return calls


def _stub_search(monkeypatch, rows: list[dict]) -> None:
    monkeypatch.setattr(
        modules, "_open_multi_field_search_context", lambda *_a, **_k: "frame"
    )
    monkeypatch.setattr(
        modules, "_resolve_multi_search_fields", lambda *_a, **_k: {"invoice_no": "field"}
    )
    monkeypatch.setattr(modules, "_clear_multi_search_fields", lambda *_a, **_k: None)
    monkeypatch.setattr(
        modules, "_fill_multi_search_fields", lambda *_a, **_k: (["Invoice No."], "field")
    )
    monkeypatch.setattr(modules, "_submit_multi_search", lambda *_a, **_k: None)
    monkeypatch.setattr(modules, "_wait_module_search_settled", lambda *_a, **_k: None)
    monkeypatch.setattr(modules, "_supplier_invoice_rows", lambda _frame: list(rows))


def _cancel(invoice_no: str) -> dict:
    return modules.prepare_supplier_invoice_cancel(
        CANCEL_XPATH, invoice_no, lambda _line: None
    )


def test_a_lone_near_match_is_never_deleted(monkeypatch, world, submitted):
    """`SI-102` không được bấm Delete/Cancel lên `SI-1024`."""
    wire_automation(monkeypatch, modules, world)
    _stub_search(monkeypatch, [_row("SI-1024", status="Save")])

    result = _cancel("SI-102")

    assert submitted == [], "Đã bấm nút WFX trên một invoice khác invoice user gõ"
    assert result["code"] != "SUPPLIER_INVOICE_CANCEL_SUBMITTED"
    assert result["code"] != "SUPPLIER_INVOICE_DELETE_SUBMITTED"


def test_a_lone_near_match_is_offered_as_a_choice(monkeypatch, world, submitted):
    """Không khớp exact thì trả danh sách để user tự chọn, không im lặng bỏ."""
    wire_automation(monkeypatch, modules, world)
    _stub_search(monkeypatch, [_row("SI-1024")])

    result = _cancel("SI-102")

    assert result["code"] == "SUPPLIER_INVOICE_MULTIPLE_RESULTS"
    assert [row["invoice_no"] for row in result["invoices"]] == ["SI-1024"]


def test_the_exact_invoice_is_submitted(monkeypatch, world, submitted):
    wire_automation(monkeypatch, modules, world)
    _stub_search(monkeypatch, [_row("SI-102")])

    result = _cancel("SI-102")

    assert [row["invoice_no"] for row in submitted] == ["SI-102"]
    assert result["ok"] is True


@pytest.mark.parametrize("typed", [" si-102 ", "SI-102", "Si-102"])
def test_exact_match_ignores_case_and_padding(monkeypatch, world, submitted, typed):
    wire_automation(monkeypatch, modules, world)
    _stub_search(monkeypatch, [_row("SI-102")])

    assert _cancel(typed)["ok"] is True
    assert [row["invoice_no"] for row in submitted] == ["SI-102"]


def test_the_only_exact_row_wins_over_its_near_matches(monkeypatch, world, submitted):
    """WFX tìm chứa chuỗi nên luôn kèm dòng thừa; exact duy nhất vẫn chạy được."""
    wire_automation(monkeypatch, modules, world)
    _stub_search(
        monkeypatch,
        [_row("SI-1024"), _row("SI-102"), _row("SI-1025")],
    )

    result = _cancel("SI-102")

    assert [row["invoice_no"] for row in submitted] == ["SI-102"]
    assert result["ok"] is True


def test_several_rows_without_an_exact_match_stay_a_choice(
    monkeypatch, world, submitted
):
    wire_automation(monkeypatch, modules, world)
    _stub_search(monkeypatch, [_row("SI-1024"), _row("SI-1025")])

    result = _cancel("SI-102")

    assert submitted == []
    assert result["code"] == "SUPPLIER_INVOICE_MULTIPLE_RESULTS"
    assert result["result_count"] == 2


def test_an_empty_grid_reports_not_found(monkeypatch, world, submitted):
    wire_automation(monkeypatch, modules, world)
    _stub_search(monkeypatch, [])

    result = _cancel("SI-102")

    assert submitted == []
    assert result["code"] == "SUPPLIER_INVOICE_NOT_FOUND"


def test_a_near_match_list_is_flagged_as_not_exact(monkeypatch, world, submitted):
    """UI phải đổi tiêu đề thẻ; danh sách gần đúng không được trông như trùng khớp."""
    wire_automation(monkeypatch, modules, world)
    _stub_search(monkeypatch, [_row("SI-1024"), _row("SI-1025")])

    result = _cancel("SI-102")

    assert result["exact_match"] is False
    assert "SI-102" in result["message"]


def test_several_exact_duplicates_are_flagged_as_exact(monkeypatch, world, submitted):
    wire_automation(monkeypatch, modules, world)
    _stub_search(
        monkeypatch,
        [_row("SI-102", key="a"), _row("SI-102", key="b"), _row("SI-1024")],
    )

    result = _cancel("SI-102")

    assert submitted == []
    assert result["exact_match"] is True
    assert [row["invoice_no"] for row in result["invoices"]] == ["SI-102", "SI-102"]
