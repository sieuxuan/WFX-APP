"""Vỏ entry point và khâu tra Supplier của `(GRN) Nhập kho`.

`grn.py` ở mức 16% coverage vì bốn hàm người dùng gọi — `prepare_grn_receipt`,
`continue_grn_receipt`, `finalize_grn_receipt`, `search_grn_receipt` — đều tự mở
Playwright nên không có seam.

CLAUDE.md đặt ba ràng buộc an toàn cho module này, đều nằm ở phần chưa được test:

* Chỉ tiếp tục khi xác định được **duy nhất** Supplier của đúng Order No.; không
  đọc được Supplier thì dừng với `GRN_RMPO_SUPPLIER_NOT_FOUND`, **không đoán**.
* Số RMPO nhập thiếu chỉ được dùng khi RMPO List trả đúng một dòng chứa chuỗi đó.
* Status `Received` phải trả `GRN_ALREADY_RECEIVED` và **không** mở Sourcing
  ASN/GRN.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import grn

RMPO_XPATH = '//*[@id="0005_0105_1000"]/a'


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, grn)


@pytest.fixture
def world(clock):
    return WfxWorld(clock)


def _logs() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lines.append


def _quiet():
    return _logs()[1]


def _rmpo_list(monkeypatch, rows, *, ok: bool = True, code: str = "RMPO_ROWS_READY"):
    """Thay đúng lời gọi RMPO List mà `_resolve_rmpo` dùng."""
    patch_automation(
        monkeypatch, grn,
        "search_rmpo_list",
        lambda *_args, **_kwargs: {
            "ok": ok,
            "code": code,
            "rmpo_rows": list(rows),
        },
    )


def _row(order_no: str, supplier: str = "SUP-A", status: str = "Open") -> dict:
    return {"order_no": order_no, "supplier": supplier, "status": status}


def _prepare(mode: str = "domestic", rmpo: str = "RMPO-2345", supplier: str = ""):
    return grn.prepare_grn_receipt(RMPO_XPATH, rmpo, supplier, mode, _quiet())


# --- Lỗi nhập liệu: chặn trước khi chạm Chrome -------------------------


def test_a_missing_rmpo_never_opens_the_browser(monkeypatch, world):
    wire_automation(monkeypatch, grn, world)

    result = _prepare(rmpo="   ")

    assert result["code"] == "GRN_RMPO_REQUIRED"
    assert world.driver_starts == 0


@pytest.mark.parametrize("mode", ["", "import", "noi dia", "foreign domestic"])
def test_an_unknown_mode_never_opens_the_browser(monkeypatch, world, mode):
    wire_automation(monkeypatch, grn, world)

    result = _prepare(mode=mode)

    assert result["code"] == "GRN_MODE_INVALID"
    assert world.driver_starts == 0


@pytest.mark.parametrize("mode", ["Foreign ", " DOMESTIC", "Domestic"])
def test_mode_is_normalised_before_validation(monkeypatch, world, mode):
    """UI có thể gửi nhãn hoa/thường lẫn khoảng trắng."""
    wire_automation(monkeypatch, grn, world)
    patch_automation(monkeypatch, grn, "_prepare_sourcing_asn", lambda *_a, **_k: None)
    patch_automation(monkeypatch, grn, "_prepare_grn_pending", lambda *_a, **_k: ["HANOI"])

    result = _prepare(mode=mode, rmpo="PO-2345", supplier="SUP-A")

    assert result["ok"] is True
    assert result["mode"] == mode.strip().casefold()


def test_continue_without_a_supplier_is_an_expired_session(monkeypatch, world):
    wire_automation(monkeypatch, grn, world)

    result = grn.continue_grn_receipt("", _quiet())

    assert result["code"] == "GRN_SESSION_EXPIRED"
    assert world.driver_starts == 0


@pytest.mark.parametrize(
    ("rmpo", "site"),
    [("", "HANOI"), ("RMPO-1", ""), ("", "")],
)
def test_finalize_needs_both_rmpo_and_site(monkeypatch, world, rmpo, site):
    wire_automation(monkeypatch, grn, world)

    result = grn.finalize_grn_receipt(rmpo, site, _quiet())

    assert result["code"] == "GRN_SITE_REQUIRED"
    assert world.driver_starts == 0


@pytest.mark.parametrize("kind", ["", "order", "Invoice No."])
def test_an_unknown_search_filter_never_opens_the_browser(monkeypatch, world, kind):
    wire_automation(monkeypatch, grn, world)

    result = grn.search_grn_receipt(kind, "INV-1", _quiet())

    assert result["code"] == "INVALID_FILTER"
    assert world.driver_starts == 0


@pytest.mark.parametrize(
    ("kind", "label"),
    [("invoice", "Số Invoice"), ("rmpo", "RMPO No.")],
)
def test_a_blank_search_query_names_the_field(monkeypatch, world, kind, label):
    wire_automation(monkeypatch, grn, world)

    result = grn.search_grn_receipt(kind, "  ", _quiet())

    assert result["code"] == "QUERY_REQUIRED"
    assert label in result["message"]
    assert world.driver_starts == 0


# --- Tra Supplier từ RMPO List: tuyệt đối không đoán -------------------


def test_a_partial_rmpo_resolves_only_when_exactly_one_row_matches(
    monkeypatch,
    world,
):
    wire_automation(monkeypatch, grn, world)
    _rmpo_list(monkeypatch, [_row("PO-2345-A", "SUP-A")])
    prepared = {}
    patch_automation(
        monkeypatch, grn,
        "_prepare_grn_pending",
        lambda _ctx, _page, supplier, mode, _log: prepared.update(
            supplier=supplier, mode=mode
        )
        or ["HANOI"],
    )

    result = _prepare(rmpo="2345")

    assert result["code"] == "GRN_SITE_SELECTION_REQUIRED"
    assert result["rmpo_no"] == "PO-2345-A", "Phải dùng Order No. đầy đủ"
    assert result["supplier"] == "SUP-A"
    assert prepared == {"supplier": "SUP-A", "mode": "domestic"}


def test_a_partial_rmpo_matching_several_rows_asks_for_more_digits(
    monkeypatch,
    world,
):
    wire_automation(monkeypatch, grn, world)
    _rmpo_list(monkeypatch, [_row("PO-2345-A"), _row("PO-2345-B")])
    patch_automation(
        monkeypatch, grn,
        "_prepare_grn_pending",
        lambda *_a, **_k: pytest.fail("Không được mở GRN khi RMPO còn mơ hồ"),
    )

    result = _prepare(rmpo="2345")

    assert result["ok"] is False
    assert result["code"] == "GRN_RMPO_AMBIGUOUS"
    assert world.driver_starts == 0


def test_an_exact_order_no_wins_over_other_rows_containing_it(monkeypatch, world):
    wire_automation(monkeypatch, grn, world)
    _rmpo_list(monkeypatch, [_row("PO-2345", "SUP-EXACT"), _row("PO-23456", "SUP-X")])
    patch_automation(
        monkeypatch, grn,
        "_prepare_grn_pending",
        lambda *_a, **_k: ["HANOI"],
    )

    result = _prepare(rmpo="PO-2345")

    assert result["supplier"] == "SUP-EXACT"


def test_a_row_without_a_supplier_stops_instead_of_guessing(monkeypatch, world):
    """CLAUDE.md: không được đoán Supplier hay mở GRN khi chưa đọc được."""
    wire_automation(monkeypatch, grn, world)
    _rmpo_list(monkeypatch, [_row("PO-2345", supplier="")])
    patch_automation(
        monkeypatch, grn,
        "_prepare_grn_pending",
        lambda *_a, **_k: pytest.fail("Không được mở GRN khi thiếu Supplier"),
    )

    result = _prepare(rmpo="PO-2345")

    assert result["ok"] is False
    assert result["code"] == "GRN_RMPO_SUPPLIER_NOT_FOUND"
    assert "PO-2345" in result["message"]
    assert world.driver_starts == 0


@pytest.mark.parametrize("status", ["Received", "received", " RECEIVED "])
def test_an_already_received_rmpo_never_opens_sourcing_asn_or_grn(
    monkeypatch,
    world,
    status,
):
    wire_automation(monkeypatch, grn, world)
    _rmpo_list(monkeypatch, [_row("PO-2345", status=status)])
    patch_automation(
        monkeypatch, grn,
        "_prepare_sourcing_asn",
        lambda *_a, **_k: pytest.fail("RMPO đã Received thì không được mở ASN"),
    )
    patch_automation(
        monkeypatch, grn,
        "_prepare_grn_pending",
        lambda *_a, **_k: pytest.fail("RMPO đã Received thì không được mở GRN"),
    )

    result = _prepare(mode="foreign", rmpo="PO-2345")

    assert result["ok"] is False
    assert result["code"] == "GRN_ALREADY_RECEIVED"
    assert world.driver_starts == 0


def test_no_rmpo_row_at_all_is_reported_as_not_found(monkeypatch, world):
    wire_automation(monkeypatch, grn, world)
    patch_automation(
        monkeypatch, grn,
        "search_rmpo_list",
        lambda *_a, **_k: {"ok": False, "code": "RMPO_NO_RESULTS"},
    )

    result = _prepare(rmpo="PO-9999")

    assert result["code"] == "GRN_RMPO_NOT_FOUND"
    assert world.driver_starts == 0


def test_a_supplier_supplied_by_the_caller_skips_the_rmpo_lookup(
    monkeypatch,
    world,
):
    """Chuyển từ RMPO List sang thì Supplier đã biết, không tra lại."""
    wire_automation(monkeypatch, grn, world)
    patch_automation(
        monkeypatch, grn,
        "search_rmpo_list",
        lambda *_a, **_k: pytest.fail("Đã có Supplier thì không được tra lại"),
    )
    patch_automation(monkeypatch, grn, "_prepare_grn_pending", lambda *_a, **_k: ["HANOI"])

    result = _prepare(rmpo="PO-2345", supplier="SUP-A")

    assert result["code"] == "GRN_SITE_SELECTION_REQUIRED"
    assert result["supplier"] == "SUP-A"


# --- Checkpoint Sourcing ASN -------------------------------------------


def test_foreign_mode_stops_at_the_sourcing_asn_checkpoint(monkeypatch, world):
    """App không tự Confirm; phải trả về cho user nhập số lượng và Confirm."""
    wire_automation(monkeypatch, grn, world)
    patch_automation(monkeypatch, grn, "_prepare_sourcing_asn", lambda *_a, **_k: None)
    patch_automation(
        monkeypatch, grn,
        "_prepare_grn_pending",
        lambda *_a, **_k: pytest.fail("Chưa được mở GRN trước khi user Confirm"),
    )

    result = _prepare(mode="foreign", rmpo="PO-2345", supplier="SUP-A")

    assert result["code"] == "GRN_SOURCING_ASN_READY"
    assert result["mode"] == "foreign"
    assert "Confirm" in result["message"]
    assert world.driver_stops == 1


# --- Ranh giới trình duyệt / phân loại lỗi -----------------------------


@pytest.mark.parametrize(
    ("ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_prepare_reports_browser_boundary_codes(
    monkeypatch,
    world,
    ready,
    logged_in,
    expected,
):
    wire_automation(
        monkeypatch,
        grn,
        world,
        chrome_ready=ready,
        logged_in=logged_in,
    )

    result = _prepare(rmpo="PO-2345", supplier="SUP-A")

    assert result["code"] == expected
    assert result["module"] == "(GRN) Nhập kho"
    assert world.driver_stops == 1


def test_a_timeout_while_preparing_is_a_grn_prepare_failure(monkeypatch, world):
    wire_automation(monkeypatch, grn, world)

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("GRN Pending chưa render")

    patch_automation(monkeypatch, grn, "_prepare_grn_pending", slow)

    result = _prepare(rmpo="PO-2345", supplier="SUP-A")

    assert result["code"] == "GRN_PREPARE_FAILED"
    assert result["module"] == "(GRN) Nhập kho"
    assert world.driver_stops == 1


def test_continue_reports_browser_boundary_codes(monkeypatch, world):
    wire_automation(monkeypatch, grn, world, chrome_ready=False)

    result = grn.continue_grn_receipt("SUP-A", _quiet())

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_stops == 1


def test_continue_failure_is_reported_as_continue_failed(monkeypatch, world):
    wire_automation(monkeypatch, grn, world)

    def boom(*_args, **_kwargs):
        raise ValueError("WFX đổi DOM")

    patch_automation(monkeypatch, grn, "_prepare_grn_pending", boom)

    result = grn.continue_grn_receipt("SUP-A", _quiet())

    assert result["code"] == "GRN_CONTINUE_FAILED"
    assert world.driver_stops == 1
