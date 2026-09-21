"""Vỏ `run_sale_asn_create`, Shipping Info và bước Check giá / Qty.

Flow này dừng giữa chừng rất nhiều lần — chờ user chọn PO, bỏ qua một bước,
hoặc lỗi ở đúng một tab — nên mỗi kết quả trả về phải nói rõ bước nào đang dở
để lượt Tiếp tục không chạy lại từ đầu.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

import wfx_panel.automation.sale_asn_create.flow as flow
import wfx_panel.automation.sale_asn_create.price_check as price_check
import wfx_panel.automation.sale_asn_create.shipping as shipping
from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import FakeClock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError
from wfx_panel.automation.sale_asn_create.errors import (
    _POSelectionRequired,
    _shipping_warning,
)
from wfx_panel.automation.sale_asn_create.values import (
    _date_for_wfx,
    _decimal_display,
    _decimal_or_none,
    _number_for_wfx,
    _table_value_matches,
)


@pytest.fixture
def clock():
    # `flow.py` không bind `time`: mọi chờ đều đi qua `_wait(frame, ...)` nên
    # đồng hồ chỉ cần cho FakePage của WfxWorld.
    return FakeClock()


class _AddOrderButton:
    @property
    def first(self):
        return self


class StubFrame:
    """Frame form Sale ASN New: chỉ cần trả nút Add Order Details."""

    def locator(self, _selector):
        return _AddOrderButton()


def _rows(count=1):
    return [
        {
            "source_row": index + 2,
            "po_no": f"PO-{index}",
            "style_no": "M ACEL JACKET",
            "invoice_no": "INV-1",
            "shipping_mode": "SEA",
        }
        for index in range(count)
    ]


def _wire_flow(monkeypatch, clock, **overrides):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, flow, world)
    defaults = {
        "_refresh_existing_new_form": lambda *_a, **_k: StubFrame(),
        "_open_new_form": lambda *_a, **_k: StubFrame(),
        "_select_buyer": lambda *_a, **_k: None,
        "_click_dom_action": lambda *_a, **_k: {"ok": True},
        "_frame_with_selector": lambda *_a, **_k: ("page", "frame"),
        "_auto_add_po_with_frame_retry": (
            lambda _c, popup, _row, _log, **_k: (True, [], "PO No.", popup)
        ),
        "_ensure_po_popup_for_next_row": lambda *_a, **_k: "popup",
        "_add_selected_po_candidates": lambda *_a, **_k: None,
        "_ensure_order_grid_rows": lambda _c, frame, *_a, **_k: frame,
        "_wait_order_grid": lambda *_a, **_k: set(),
        "_missing_order_rows": lambda *_a, **_k: [],
        "_fill_order_details": lambda *_a, **_k: None,
        "_fill_style_details": lambda *_a, **_k: None,
        "_fill_shipping": lambda *_a, **_k: [],
        "_check_sale_asn_price_on_page": lambda *_a, **_k: {
            "ok": True,
            "message": "Đã check 1 PO + Style: 1 khớp. Summary Total: khớp.",
        },
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        patch_automation(monkeypatch, flow, name, value)
    return world


def _run(**kwargs):
    arguments = {
        "xpath": '//*[@id="0005"]/a',
        "buyer": "J.LINDEBERG",
        "rows": _rows(),
        "log": lambda _line: None,
    }
    arguments.update(kwargs)
    return flow.run_sale_asn_create(**arguments)


# --- kiểm tra đầu vào ---------------------------------------------------


def test_adding_po_without_a_buyer_never_opens_the_browser(monkeypatch, clock):
    world = _wire_flow(monkeypatch, clock)

    result = _run(buyer="   ")

    assert result["code"] == "SALE_ASN_BUYER_REQUIRED"
    assert world.driver_starts == 0


def test_an_empty_file_is_refused_before_anything_is_opened(monkeypatch, clock):
    world = _wire_flow(monkeypatch, clock)

    result = _run(rows=[])

    assert result["code"] == "SALE_ASN_FILE_EMPTY"
    assert world.driver_starts == 0


def test_a_corrupt_checkpoint_asks_the_user_to_pick_the_file_again(
    monkeypatch, clock
):
    world = _wire_flow(monkeypatch, clock)

    result = _run(stage="khong_ton_tai")

    assert result["code"] == "SALE_ASN_CREATE_STAGE_INVALID"
    assert world.driver_starts == 0


def test_resuming_a_later_stage_does_not_require_a_buyer(monkeypatch, clock):
    _wire_flow(monkeypatch, clock)

    result = _run(buyer="", stage="shipping_info")

    assert result["code"] == "SALE_ASN_FORM_COMPLETED"
    assert result["add_po_selected"] is False


# --- bước thêm PO -------------------------------------------------------


def test_a_fresh_run_reloads_the_form_picks_the_buyer_and_opens_add_po(
    monkeypatch, clock
):
    opened: list[str] = []
    _wire_flow(
        monkeypatch,
        clock,
        _refresh_existing_new_form=lambda *_a, **_k: (
            opened.append("refresh") or StubFrame()
        ),
        _select_buyer=lambda _frame, buyer: opened.append(f"buyer:{buyer}"),
        _click_dom_action=lambda *_a, **_k: opened.append("add") or {"ok": True},
    )
    lines: list[str] = []

    result = _run(log=lines.append)

    assert result["code"] == "SALE_ASN_FORM_COMPLETED"
    assert opened == ["refresh", "buyer:J.LINDEBERG", "add"]
    assert any("mở Add Order Details" in line for line in lines)


def test_a_missing_new_form_is_opened_from_the_menu_instead(monkeypatch, clock):
    opened: list[str] = []
    _wire_flow(
        monkeypatch,
        clock,
        _refresh_existing_new_form=lambda *_a, **_k: None,
        _open_new_form=lambda *_a, **_k: opened.append("menu") or StubFrame(),
    )

    assert _run()["code"] == "SALE_ASN_FORM_COMPLETED"
    assert opened == ["menu"]


def test_a_po_needing_the_user_to_choose_reports_where_to_resume(
    monkeypatch, clock
):
    candidates = [{"po_no": "PO-1", "row_index": 0}]
    _wire_flow(
        monkeypatch,
        clock,
        _auto_add_po_with_frame_retry=(
            lambda _c, popup, row, _log, **_k: (
                (True, [], "PO No.", popup)
                if row["po_no"] == "PO-0"
                else (False, candidates, "ambiguous", popup)
            )
        ),
    )

    result = _run(rows=_rows(3))

    assert result["code"] == "SALE_ASN_PO_SELECTION_REQUIRED"
    assert result["pending_index"] == 1
    assert result["next_index"] == 2
    assert result["completed"] == 1
    assert result["total"] == 3
    assert result["final"] is False
    assert [item["candidate_id"] for item in result["candidates"]] == ["0"]


def test_the_popup_is_reopened_between_pos_but_not_after_the_last_one(
    monkeypatch, clock
):
    reopened: list[int] = []
    _wire_flow(
        monkeypatch,
        clock,
        _ensure_po_popup_for_next_row=(
            lambda _c, added, _log: reopened.append(len(added)) or "popup"
        ),
    )

    assert _run(rows=_rows(3))["code"] == "SALE_ASN_FORM_COMPLETED"
    assert reopened == [1, 2]


def test_rows_the_user_chose_in_the_app_are_ticked_then_the_run_continues(
    monkeypatch, clock
):
    ticked: list[tuple] = []
    _wire_flow(
        monkeypatch,
        clock,
        _add_selected_po_candidates=(
            lambda _frame, row, candidates, _log, *, final: ticked.append(
                (row.get("po_no"), len(candidates), final)
            )
        ),
        _refresh_existing_new_form=lambda *_a, **_k: pytest.fail(
            "Lượt Tiếp tục không được mở lại form từ đầu"
        ),
    )

    result = _run(
        rows=_rows(2),
        start_index=0,
        selected_po_row={"po_no": "PO-0"},
        selected_po_candidates=[{"row_index": 0}],
        selected_po_final=False,
    )

    assert result["code"] == "SALE_ASN_FORM_COMPLETED"
    assert ticked == [("PO-0", 1, False)]


def test_the_last_chosen_row_finishes_the_po_stage_without_reopening_the_popup(
    monkeypatch, clock
):
    _wire_flow(
        monkeypatch,
        clock,
        _ensure_po_popup_for_next_row=lambda *_a, **_k: pytest.fail(
            "PO cuối đã đóng popup thì không được mở lại"
        ),
    )

    result = _run(
        rows=_rows(1),
        selected_po_row={"po_no": "PO-0"},
        selected_po_candidates=[{"row_index": 0}],
        selected_po_final=True,
    )

    assert result["code"] == "SALE_ASN_FORM_COMPLETED"


# --- các bước sau -------------------------------------------------------


def test_a_skipped_stage_is_announced_and_its_frame_is_never_resolved(
    monkeypatch, clock
):
    resolved: list[str] = []
    _wire_flow(
        monkeypatch,
        clock,
        _frame_with_selector=(
            lambda _c, selector, **_k: (resolved.append(selector), ("page", "frame"))[1]
        ),
        _fill_style_details=lambda *_a, **_k: pytest.fail("Bước đã bỏ qua"),
    )
    stages: list[tuple] = []
    lines: list[str] = []

    result = _run(
        stage="style_details",
        skip_stages=("style_details", "shipping_info"),
        progress=lambda *args, **kwargs: stages.append((args, kwargs)),
        log=lines.append,
    )

    assert result["code"] == "SALE_ASN_FORM_COMPLETED"
    assert resolved == [], "Bỏ qua cả hai bước thì không được chờ tab nào"
    assert any("Đã bỏ qua bước Style Details" in line for line in lines)
    assert [kwargs.get("state") for _args, kwargs in stages] == [
        "skipped",
        "skipped",
        "active",
        "completed",
    ]


def test_running_order_details_without_the_po_stage_verifies_the_grid_first(
    monkeypatch, clock
):
    _wire_flow(
        monkeypatch,
        clock,
        _missing_order_rows=lambda *_a, **_k: [
            {"po_no": "PO-7"},
            {"po_no": "PO-8"},
        ],
        _ensure_order_grid_rows=lambda *_a, **_k: pytest.fail(
            "Không chạy bước PO thì không được tự thêm PO"
        ),
    )
    lines: list[str] = []

    result = _run(stage="order_details", log=lines.append)

    assert result["code"] == "SALE_ASN_ORDER_ROWS_NOT_FOUND"
    assert "PO-7, PO-8" in result["message"]
    assert result["resume_stage"] == "order_details"
    assert result["can_skip"] is True


def test_shipping_warnings_are_carried_into_the_final_message(
    monkeypatch, clock
):
    _wire_flow(
        monkeypatch,
        clock,
        _fill_shipping=lambda *_a, **_k: [
            "Ship To: WFX không có lựa chọn \"ABC\"",
            "Notify 1: file không có dữ liệu",
        ],
    )

    result = _run()

    assert result["warning_count"] == 2
    assert "đã bỏ qua 2 trường" in result["message"]
    assert result["save_required"] is True
    assert result["invoice_no"] == "INV-1"


def test_a_price_check_failure_is_a_stage_that_cannot_be_skipped(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise RuntimeError("SALE_ASN_SHIPMENT_DETAILS_EMPTY")

    _wire_flow(monkeypatch, clock, _check_sale_asn_price_on_page=explode)
    lines: list[str] = []

    result = _run(log=lines.append)

    assert result["code"] == "SALE_ASN_SHIPMENT_DETAILS_EMPTY"
    assert result["resume_stage"] == "price_check"
    assert result["can_skip"] is False
    assert lines[-1] == result["message"]


def test_a_playwright_timeout_names_the_stage_that_was_running(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise PlaywrightTimeoutError("Không tìm thấy vùng Sale ASN")

    _wire_flow(monkeypatch, clock, _fill_style_details=explode)

    result = _run(stage="style_details")

    assert result["code"] == "SALE_ASN_CREATE_FAILED"
    assert result["resume_stage"] == "style_details"
    assert result["stage_label"] == "Style Details"
    assert result["resumable"] is True


def test_an_unexpected_error_still_says_which_stage_to_resume(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise ZeroDivisionError("division by zero")

    _wire_flow(monkeypatch, clock, _fill_shipping=explode)
    lines: list[str] = []

    result = _run(stage="shipping_info", log=lines.append)

    assert result["code"] == "SALE_ASN_CREATE_FAILED"
    assert result["message"].startswith("ZeroDivisionError: ")
    assert result["resume_stage"] == "shipping_info"
    assert lines[-1] == result["message"]


def test_a_selection_needed_deep_in_the_repair_resumes_after_the_last_row(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise _POSelectionRequired(
            {"po_no": "PO-9", "source_row": 4},
            [{"row_index": 1}],
            "qty_mismatch:tổng Dispatched Qty khác Qty file",
            final=True,
        )

    _wire_flow(monkeypatch, clock, _ensure_order_grid_rows=explode)

    result = _run(rows=_rows(2))

    assert result["code"] == "SALE_ASN_PO_SELECTION_REQUIRED"
    # Lượt Tiếp tục phải bỏ qua hẳn vòng PO; `_ensure_order_grid_rows` sẽ tự dò
    # lại đúng dòng còn thiếu.
    assert result["pending_index"] == 2
    assert result["next_index"] == 2
    assert "tổng Dispatched Qty khác Qty file" in result["message"]


# --- Shipping Info ------------------------------------------------------


class ShippingTab:
    def __init__(self):
        self.clicks = 0

    @property
    def first(self):
        return self

    def wait_for(self, **_kwargs):
        return None

    def click(self, **_kwargs):
        self.clicks += 1


class ShippingFrame:
    def __init__(self, clock):
        self.clock = clock
        self.tab = ShippingTab()

    def locator(self, selector):
        assert selector in {"#tabShippingInfo", "#tabStyleDetails"}
        return self.tab

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


def _fill(monkeypatch, row, outcomes):
    clock = FakeClock()
    written: list[tuple[str, str]] = []

    def set_control(_frame, selector, value, _mode, timeout_s=3):
        written.append((selector, value))
        outcome = outcomes(selector, value)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    patch_automation(monkeypatch, shipping, "_set_control", set_control)
    lines: list[str] = []
    warnings = shipping._fill_shipping(ShippingFrame(clock), row, lines.append)
    return warnings, written, lines


def test_an_unsupported_shipping_mode_is_a_warning_not_a_crash(monkeypatch):
    warnings, _written, lines = _fill(
        monkeypatch,
        {"shipping_mode": "THUYỀN THÚNG", "invoice_no": "INV-1"},
        lambda _selector, _value: {"ok": True},
    )

    assert 'Shipping Mode: không hỗ trợ "THUYỀN THÚNG"' in warnings
    assert any("chưa bấm Save" in line for line in lines)


def test_a_blank_shipping_mode_is_named_as_empty_in_the_warning(monkeypatch):
    warnings, _written, _lines = _fill(
        monkeypatch,
        {"invoice_no": "INV-1"},
        lambda _selector, _value: {"ok": True},
    )

    assert 'Shipping Mode: không hỗ trợ "(trống)"' in warnings


def test_sea_fills_haiphong_and_its_delivery_terms(monkeypatch):
    _warnings, written, _lines = _fill(
        monkeypatch,
        {"shipping_mode": "SEA", "invoice_no": "INV-1"},
        lambda _selector, _value: {"ok": True},
    )

    values = dict(written)
    assert values["#ddlShipmentMode"] == "SEA"
    assert "HPH - Haiphong" in written[[item[0] for item in written].index(
        "#Cell_AWBLoadingPort"
    )][1]
    assert values["#ddlDeliveryTerms"] == "FOB HAIPHONG, VIETNAM"


def test_a_blank_destination_leaves_both_country_fields_untouched(monkeypatch):
    _warnings, written, _lines = _fill(
        monkeypatch,
        {"shipping_mode": "AIR", "invoice_no": "INV-1", "destination": "  "},
        lambda _selector, _value: {"ok": True},
    )

    touched = {selector for selector, _value in written}
    assert "#Cell_DestinationCountry" not in touched
    assert "#Cell_FinalDestination" not in touched


def test_a_country_wfx_does_not_know_keeps_final_destination_as_it_was(
    monkeypatch,
):
    def outcomes(selector, _value):
        if selector == "#Cell_DestinationCountry":
            return {"ok": False, "reason": "option-not-found"}
        return {"ok": True}

    warnings, written, lines = _fill(
        monkeypatch,
        {"shipping_mode": "AIR", "invoice_no": "INV-1", "destination": "VN"},
        outcomes,
    )

    touched = {selector for selector, _value in written}
    assert "#Cell_FinalDestination" not in touched
    assert any("Giữ nguyên Final Destination" in line for line in lines)
    assert any(warning.startswith("Destination Country") for warning in warnings)


def test_a_port_of_loading_is_accepted_when_either_host_takes_it(monkeypatch):
    def outcomes(selector, _value):
        if selector == "#Cell_AWBLoadingPort":
            return {"ok": False, "reason": "host-not-found"}
        return {"ok": True}

    warnings, written, _lines = _fill(
        monkeypatch,
        {"shipping_mode": "AIR", "invoice_no": "INV-1"},
        outcomes,
    )

    touched = [selector for selector, _value in written]
    assert "#Cell_AWBLoadingPort" in touched
    assert "#Cell_BLMotherLoadingPort" in touched
    assert not any("Port of Loading" in warning for warning in warnings)


def test_a_field_that_throws_reports_the_error_text_as_its_warning(monkeypatch):
    def outcomes(selector, _value):
        if "ConsigneeAddress" in selector:
            return PlaywrightError("Execution context was destroyed")
        return {"ok": True}

    warnings, _written, _lines = _fill(
        monkeypatch,
        {
            "shipping_mode": "AIR",
            "invoice_no": "INV-1",
            "consignee_address": "ABC",
        },
        outcomes,
    )

    assert any("Execution context was destroyed" in item for item in warnings)


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("option-not-found", 'Ship To: WFX không có lựa chọn "ABC"'),
        ("host-not-found", "Ship To: WFX không có trường này"),
        ("editor-not-found", "Ship To: trường không thể chỉnh sửa"),
        ("document-changed", "Ship To: trang WFX đã thay đổi khi đang điền"),
        ("", "Ship To: không thể điền"),
        ("la-lam", "Ship To: la-lam"),
    ],
)
def test_every_shipping_failure_reason_has_a_readable_warning(reason, expected):
    assert _shipping_warning("Ship To", "ABC", {"reason": reason}) == expected


# --- giá trị ------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-03-01", "01 Mar 2026"),
        ("01/03/2026", "01/03/2026"),
        ("", ""),
    ],
)
def test_dates_are_only_rewritten_when_they_are_iso(value, expected):
    assert _date_for_wfx(value) == expected


@pytest.mark.parametrize(
    ("value", "integer", "expected"),
    [
        ("1,250.5000", False, "1250.5"),
        ("12.34567", False, "12.3457"),
        ("12.9", True, "13"),
        ("khong phai so", False, "khong phai so"),
        ("0.00001", False, "0"),
    ],
)
def test_numbers_are_normalised_without_losing_the_original_on_failure(
    value, integer, expected
):
    assert _number_for_wfx(value, integer=integer) == expected


@pytest.mark.parametrize(
    ("expected", "actual", "matches"),
    [
        ("1250", "1,250.00", True),
        ("1250", "1250.0001", True),
        ("1250", "1251", False),
        ("2026-03-01", "01 Mar 2026", True),
        ("2026-03-01", "02 Mar 2026", False),
        ("Men's Jacket", "Mens Jacket", True),
        ("Men's Jacket", "Women Jacket", False),
        ("", "", True),
    ],
)
def test_table_values_match_the_way_wfx_reformats_them(expected, actual, matches):
    assert _table_value_matches(expected, actual) is matches


def test_a_date_wfx_renders_with_an_unknown_month_is_not_parsed():
    assert _table_value_matches("2026-03-01", "01 Thg3 2026") is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1,250.50", Decimal("1250.50")), ("", None), ("abc", None)],
)
def test_decimals_are_read_leniently_but_never_guessed(value, expected):
    assert _decimal_or_none(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, ""), (Decimal("1250.5000"), "1250.5"), (Decimal("12"), "12")],
)
def test_decimals_are_displayed_without_trailing_zeros(value, expected):
    assert _decimal_display(value) == expected


# --- Check giá / Qty ----------------------------------------------------


def _file_row(po_no="PO-1", style_no="M ACEL", qty="10", price="2.5", row=2):
    return {
        "source_row": row,
        "po_no": po_no,
        "style_no": style_no,
        "qty": qty,
        "price": price,
    }


def _shipment(order_no="SO-1/PO-1", article="M ACEL", qty="10", price="2.5"):
    return {
        "order_no": order_no,
        "article": article,
        "qty": qty,
        "price": price,
    }


def test_file_rows_without_both_a_po_and_a_style_are_not_compared():
    grouped = price_check._group_file_rows(
        [
            _file_row(),
            _file_row(po_no="", row=3),
            _file_row(style_no="", row=4),
        ]
    )

    assert list(grouped) == [("po 1", "m acel")]


def test_shipment_rows_without_a_readable_po_are_indexed_out():
    index = price_check._shipment_rows_by_po(
        [_shipment(), _shipment(order_no="")]
    )

    assert list(index) == ["po 1"]


@pytest.mark.parametrize(
    ("file_row", "shipment_rows", "status"),
    [
        (_file_row(qty=""), [_shipment()], "file_value_missing"),
        (_file_row(price=""), [_shipment()], "file_value_missing"),
        (_file_row(), [_shipment(order_no="SO-9/PO-9")], "shipment_not_found"),
        (_file_row(), [_shipment(qty="")], "system_value_missing"),
        (_file_row(), [_shipment(price="")], "system_value_missing"),
        (
            _file_row(),
            [_shipment(qty="4"), _shipment(qty="6", price="3.0")],
            "system_price_ambiguous",
        ),
        (_file_row(), [_shipment()], "ok"),
    ],
)
def test_every_comparison_outcome_is_named_for_the_user(
    file_row, shipment_rows, status
):
    comparisons, _totals = price_check._price_check_rows(
        [file_row], shipment_rows
    )

    assert comparisons[0]["status"] == status
    assert comparisons[0]["message"]


# --- phần còn lại của Shipping Info -------------------------------------


def test_the_shipping_field_table_only_uses_the_two_kinds_of_key_it_handles():
    """Sentinel mới mà quên xử lý sẽ bị điền thẳng tên khóa vào form WFX."""

    from wfx_panel.automation.sale_asn_create.constants import SHIPPING_FIELDS

    for _selector, key, _mode in SHIPPING_FIELDS:
        if key.startswith("__"):
            assert key[2:].strip(), f"hằng số rỗng: {key!r}"
        else:
            assert not key.startswith("_"), f"khóa lạ: {key!r}"


def test_a_complete_row_fills_shipping_info_without_a_single_warning(
    monkeypatch,
):
    complete = {
        "shipping_mode": "COURIER",
        "invoice_no": "INV-1",
        "invoice_date": "2026-03-01",
        "shipping_bill_no": "SB-1",
        "shipping_bill_date": "2026-03-02",
        "destination": "VIETNAM",
        "consignee_address": "ABC",
        "ship_to": "XYZ",
        "factory": "PSHK VIETNAM",
    }

    warnings, written, lines = _fill(
        monkeypatch, complete, lambda _selector, _value: {"ok": True}
    )

    assert warnings == []
    assert lines[-1] == "[SALE ASN] Đã điền Shipping Info; chưa bấm Save."
    values = dict(written)
    assert values["#ddlConsignorAddress"] == "BILL-ADD - PSHK"
    assert values["#ddlDeliveryTerms"] == "EXW"
    assert values["#Cell_InvoiceDate"] == "01 Mar 2026"


# --- phần còn lại của values -------------------------------------------


def test_a_style_with_nothing_comparable_scores_zero():
    from wfx_panel.automation.sale_asn_create.values import _style_similarity

    assert _style_similarity("", "M ACEL JACKET") == 0
    assert _style_similarity("!!!", "M ACEL JACKET") == 0


@pytest.mark.parametrize(
    "value",
    [
        "01 Abc 2026",  # tháng không thuộc bảng tiếng Anh của WFX
        "01 Thg3 2026",  # không khớp định dạng "dd MMM yyyy" của WFX
        "32 Mar 2026",  # ngày không tồn tại
        "01 Feb 20260",  # năm sai định dạng
    ],
)
def test_an_unparseable_wfx_date_is_never_guessed(value):
    from wfx_panel.automation.sale_asn_create.values import (
        _parse_supported_date,
    )

    assert _parse_supported_date(value) is None


# --- Check giá / Qty trên form đang mở ---------------------------------


class PriceNode:
    def __init__(self, payload=None, *, wait_error=None):
        self.payload = payload
        self.wait_error = wait_error

    @property
    def first(self):
        return self

    def wait_for(self, **_kwargs):
        if self.wait_error is not None:
            raise self.wait_error

    def evaluate(self, _script, _arg=None):
        return self.payload


class PriceFrame:
    def __init__(self, nodes, clock):
        self.nodes = dict(nodes)
        self.clock = clock

    def locator(self, selector):
        return self.nodes[selector]

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


class PricePage:
    context = object()


def _price_frame(clock, *, shipment_rows, summary):
    from wfx_panel.automation.sale_asn_create.constants import (
        SHIPMENT_DETAILS_GRID_SELECTOR,
        SHIPMENT_DETAILS_TAB_SELECTOR,
        SUMMARY_TOTAL_GRID_SELECTOR,
    )

    return PriceFrame(
        {
            SHIPMENT_DETAILS_TAB_SELECTOR: PriceNode(),
            SHIPMENT_DETAILS_GRID_SELECTOR: PriceNode(shipment_rows),
            SUMMARY_TOTAL_GRID_SELECTOR: PriceNode(summary),
        },
        clock,
    )


def _wire_price(monkeypatch, frame):
    patch_automation(
        monkeypatch,
        price_check,
        "_frame_with_selector",
        lambda *_a, **_k: ("page", frame),
    )
    patch_automation(
        monkeypatch, price_check, "_click_dom_action", lambda *_a, **_k: {"ok": True}
    )


def test_the_price_check_refuses_to_run_on_an_empty_file(monkeypatch):
    with pytest.raises(RuntimeError, match="SALE_ASN_PRICE_FILE_EMPTY"):
        price_check._check_sale_asn_price_on_page(
            PricePage(), [], lambda _line: None
        )


def test_an_empty_shipment_details_tab_is_named_not_reported_as_matching(
    monkeypatch, clock
):
    frame = _price_frame(clock, shipment_rows=[], summary={})
    _wire_price(monkeypatch, frame)

    with pytest.raises(RuntimeError, match="SALE_ASN_SHIPMENT_DETAILS_EMPTY"):
        price_check._check_sale_asn_price_on_page(
            PricePage(), [_file_row()], lambda _line: None
        )


def test_a_summary_total_wfx_could_not_render_stops_the_check(
    monkeypatch, clock
):
    frame = _price_frame(clock, shipment_rows=[_shipment()], summary=None)
    _wire_price(monkeypatch, frame)

    with pytest.raises(RuntimeError, match="SALE_ASN_SUMMARY_TOTAL_EMPTY"):
        price_check._check_sale_asn_price_on_page(
            PricePage(), [_file_row()], lambda _line: None
        )


def test_a_matching_invoice_reports_how_many_lines_were_checked(
    monkeypatch, clock
):
    frame = _price_frame(
        clock,
        shipment_rows=[_shipment()],
        summary={
            "total_quantity": "10",
            "value_in_doc_currency": "25",
            "net_value_in_doc_currency": "25",
        },
    )
    _wire_price(monkeypatch, frame)
    lines: list[str] = []

    result = price_check._check_sale_asn_price_on_page(
        PricePage(), [_file_row()], lines.append
    )

    assert result["code"] == "SALE_ASN_PRICE_CHECKED"
    assert "1 khớp" in result["message"]
    assert "Summary Total: khớp" in result["message"]
    assert lines[-1].endswith(result["message"])


def test_a_mismatched_line_is_counted_as_needing_attention(monkeypatch, clock):
    frame = _price_frame(
        clock,
        shipment_rows=[_shipment(qty="9")],
        summary={
            "total_quantity": "9",
            "value_in_doc_currency": "22.5",
            "net_value_in_doc_currency": "22.5",
        },
    )
    _wire_price(monkeypatch, frame)

    result = price_check._check_sale_asn_price_on_page(
        PricePage(), [_file_row()], lambda _line: None
    )

    assert "1 cần kiểm tra" in result["message"]
    assert "Summary Total: cần kiểm tra" in result["message"]


# --- Style Details ------------------------------------------------------


def test_a_style_wfx_does_not_show_is_named_not_skipped(monkeypatch):
    import wfx_panel.automation.sale_asn_create.style_details as style_details

    frame = object()
    patch_automation(
        monkeypatch,
        style_details,
        "_edit_marked_table_cell",
        lambda *_a, **_k: pytest.fail("Chưa đánh dấu được ô thì không được sửa"),
    )

    class MarkFrame:
        def evaluate(self, _script, _arg=None):
            return {"ok": False, "reason": "style-not-found"}

    with pytest.raises(
        RuntimeError, match="SALE_ASN_TABLE_MAPPING_FAILED:style-not-found"
    ):
        style_details._set_style_hts_cell(MarkFrame(), "M ACEL", "6203")

    del frame


def test_a_grid_that_changes_row_count_mid_write_stops_instead_of_guessing(
    monkeypatch,
):
    import wfx_panel.automation.sale_asn_create.style_details as style_details

    counts = [3, 2]
    patch_automation(
        monkeypatch, style_details, "_edit_marked_table_cell", lambda *_a: ""
    )

    class ShiftingFrame:
        def evaluate(self, _script, _arg=None):
            return {
                "ok": True,
                "target_count": counts.pop(0) if len(counts) > 1 else counts[0],
            }

    with pytest.raises(
        RuntimeError,
        match="SALE_ASN_TABLE_MAPPING_FAILED:style-row-count-changed",
    ):
        style_details._set_style_hts_cell(ShiftingFrame(), "M ACEL", "6203")


def _style_rows(**overrides):
    base = {
        "style_no": "M ACEL",
        "hs_code": "6203",
        "goods_description": "JACKET",
    }
    base.update(overrides)
    return base


def test_one_style_with_two_different_hs_codes_is_a_file_error(monkeypatch):
    import wfx_panel.automation.sale_asn_create.style_details as style_details

    clock = FakeClock()

    with pytest.raises(RuntimeError, match="SALE_ASN_STYLE_HS_CODE_CONFLICT"):
        style_details._fill_style_details(
            ShippingFrame(clock),
            [_style_rows(), _style_rows(hs_code="6204")],
            lambda _line: None,
        )


def test_one_style_with_two_different_descriptions_is_a_file_error(monkeypatch):
    import wfx_panel.automation.sale_asn_create.style_details as style_details

    clock = FakeClock()

    with pytest.raises(
        RuntimeError, match="SALE_ASN_STYLE_GOODS_DESCRIPTION_CONFLICT"
    ):
        style_details._fill_style_details(
            ShippingFrame(clock),
            [_style_rows(), _style_rows(goods_description="COAT")],
            lambda _line: None,
        )
