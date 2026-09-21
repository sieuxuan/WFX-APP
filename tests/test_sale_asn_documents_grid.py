"""Chọn đúng dòng Sale ASN trong AG Grid trước khi bấm Docs.

Grid Sale ASN vừa virtualize theo chiều ngang vừa có debounce Floating Filter,
nên `grid.py` phải quét mọi vị trí cuộn và chỉ tin DOM đã đứng yên. Các test ở
đây mô phỏng đúng hai đặc tính đó.
"""

from __future__ import annotations

from typing import Any

import pytest

import wfx_panel.automation.sale_asn_documents.grid as grid
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError
from wfx_panel.automation.sale_asn_documents.constants import (
    _CLICK_SALE_ASN_DOCS_JS,
    _SALE_ASN_ROWS_JS,
    _SALE_ASN_SCROLL_STATE_JS,
    _SALE_ASN_SCROLL_TO_JS,
)


def _row(row_key, invoice_no="", buyer="", selected=False):
    return {
        "row_key": str(row_key),
        "invoice_no": invoice_no,
        "buyer": buyer,
        "selected": selected,
    }


def _payload(*rows, no_rows=False):
    return {"rows": list(rows), "noRows": no_rows}


class GridRoot:
    """Một `.ag-root-wrapper`: trả row theo vị trí cuộn ngang đang đứng."""

    def __init__(
        self,
        *,
        visible=True,
        rows_by_position=None,
        payloads=None,
        state=None,
        docs_at=None,
        rows_error=None,
    ):
        self.visible = visible
        self.rows_by_position = rows_by_position or {}
        self.payloads = list(payloads or [])
        self.state = state or {"current": 0, "maximum": 0, "viewport": 0}
        self.docs_at = docs_at
        self.rows_error = rows_error
        self.position = int(self.state.get("current") or 0)
        self.scrolled: list[int] = []
        self.clicked: list[dict[str, Any]] = []

    def is_visible(self):
        return self.visible

    def evaluate(self, script, argument=None):
        if script == _SALE_ASN_SCROLL_STATE_JS:
            return dict(self.state)
        if script == _SALE_ASN_SCROLL_TO_JS:
            self.position = int(argument)
            self.scrolled.append(self.position)
            return True
        if script == _SALE_ASN_ROWS_JS:
            if self.rows_error is not None:
                raise self.rows_error
            if self.rows_by_position:
                return self.rows_by_position.get(self.position, _payload())
            if len(self.payloads) > 1:
                return self.payloads.pop(0)
            return self.payloads[0] if self.payloads else _payload()
        if script == _CLICK_SALE_ASN_DOCS_JS:
            self.clicked.append(argument)
            return self.docs_at is not None and self.position == self.docs_at
        raise AssertionError(f"script lạ: {script[:60]}")


class RootLocator:
    def __init__(self, roots):
        self._roots = list(roots)

    def count(self):
        return len(self._roots)

    def nth(self, index):
        return self._roots[index]


class GridFrame:
    def __init__(self, *roots, clock=None):
        self.roots = list(roots)
        self.clock = clock

    def locator(self, selector):
        assert selector == ".ag-root-wrapper"
        return RootLocator(self.roots)

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


# --- chờ grid ổn định ---------------------------------------------------


def test_the_grid_is_only_accepted_after_the_rows_stop_changing(monkeypatch):
    clock = install_fake_clock(monkeypatch, grid)
    root = GridRoot(payloads=[_payload(_row(0, "INV-1"))])
    frame = GridFrame(root, clock=clock)
    started = clock.monotonic()

    found_root, payload = grid._sale_asn_result_grid(frame, timeout_s=20)

    assert found_root is root
    assert [row["invoice_no"] for row in payload["rows"]] == ["INV-1"]
    assert clock.monotonic() - started >= 0.8


def test_a_grid_whose_rows_keep_churning_never_settles(monkeypatch):
    clock = install_fake_clock(monkeypatch, grid)
    churning = GridRoot(
        payloads=[_payload(_row(index, f"INV-{index}")) for index in range(200)]
    )

    with pytest.raises(PlaywrightTimeoutError, match="chưa ổn định"):
        grid._sale_asn_result_grid(GridFrame(churning, clock=clock), timeout_s=5)


def test_a_hidden_grid_from_the_previous_screen_is_skipped(monkeypatch):
    clock = install_fake_clock(monkeypatch, grid)
    hidden = GridRoot(visible=False, payloads=[_payload(_row(0, "CŨ"))])
    live = GridRoot(payloads=[_payload(_row(0, "INV-9"))])

    found_root, payload = grid._sale_asn_result_grid(
        GridFrame(hidden, live, clock=clock), timeout_s=20
    )

    assert found_root is live
    assert payload["rows"][0]["invoice_no"] == "INV-9"


def test_an_empty_result_is_a_valid_answer_when_no_invoice_was_asked_for(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, grid)
    empty = GridRoot(payloads=[_payload(no_rows=True)])

    _root, payload = grid._sale_asn_result_grid(
        GridFrame(empty, clock=clock), timeout_s=20
    )

    assert payload["rows"] == []
    assert payload["noRows"] is True


def test_an_empty_grid_is_handed_back_so_the_error_names_the_invoice(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, grid)
    empty = GridRoot(payloads=[_payload(no_rows=True)])

    # Khi người dùng đã nhập Invoice No., timeout chung chung không giúp gì.
    # Hàm trả ứng viên cuối để `_select_sale_asn_row` báo đúng lỗi nghiệp vụ.
    _root, payload = grid._sale_asn_result_grid(
        GridFrame(empty, clock=clock), "INV-7", timeout_s=5
    )

    assert payload["rows"] == []
    with pytest.raises(RuntimeError, match="SALE_ASN_INVOICE_NOT_FOUND"):
        grid._select_sale_asn_row(payload, "invoice_no", "INV-7")


def test_the_debounced_filter_must_produce_the_exact_invoice_before_it_counts(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, grid)
    # DOM còn kết quả của lượt lọc trước; hàm phải trả về ứng viên cuối chứ
    # không được nhận nó như bản khớp exact.
    stale = GridRoot(payloads=[_payload(_row(0, "INV-OLD"))])

    _root, payload = grid._sale_asn_result_grid(
        GridFrame(stale, clock=clock), "INV-NEW", timeout_s=5
    )

    assert [row["invoice_no"] for row in payload["rows"]] == ["INV-OLD"]


def test_a_grid_that_throws_while_being_read_is_retried_until_the_deadline(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, grid)
    broken = GridRoot(rows_error=PlaywrightError("frame đã detach"))

    with pytest.raises(PlaywrightTimeoutError, match="chưa ổn định"):
        grid._sale_asn_result_grid(GridFrame(broken, clock=clock), timeout_s=3)


def test_a_screen_without_any_grid_at_all_times_out(monkeypatch):
    clock = install_fake_clock(monkeypatch, grid)

    with pytest.raises(PlaywrightTimeoutError, match="chưa ổn định"):
        grid._sale_asn_result_grid(GridFrame(clock=clock), timeout_s=3)


def test_the_settled_grid_is_rescanned_across_every_horizontal_position(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, grid)
    # Invoice No. chỉ render ở đầu grid, Buyer chỉ render sau khi cuộn hết
    # sang phải: đúng cách AG Grid virtualize cột.
    root = GridRoot(
        state={"current": 0, "maximum": 600, "viewport": 400},
        rows_by_position={
            0: _payload(_row(0, invoice_no="INV-5")),
            300: _payload(_row(0)),
            600: _payload(_row(0, buyer="J.LINDEBERG", selected=True)),
        },
    )

    _found, payload = grid._sale_asn_result_grid(
        GridFrame(root, clock=clock), "INV-5", timeout_s=20
    )

    assert payload["rows"] == [
        _row(0, invoice_no="INV-5", buyer="J.LINDEBERG", selected=True)
    ]
    assert root.position == 0


# --- quét ngang ---------------------------------------------------------


def test_scanning_visits_every_position_and_puts_the_grid_back(monkeypatch):
    clock = install_fake_clock(monkeypatch, grid)
    root = GridRoot(
        state={"current": 240, "maximum": 800, "viewport": 400},
        rows_by_position={
            240: _payload(_row(1, invoice_no="INV-1")),
            0: _payload(_row(1)),
            300: _payload(_row(1, buyer="TRUEWERK")),
            600: _payload(_row(1)),
            800: _payload(_row(1, selected=True)),
        },
    )
    frame = GridFrame(root, clock=clock)

    payload = grid._scan_sale_asn_rows(frame, root)

    assert root.scrolled == [240, 0, 300, 600, 800, 240]
    assert payload["rows"] == [
        _row(1, invoice_no="INV-1", buyer="TRUEWERK", selected=True)
    ]


def test_scanning_restores_the_original_position_even_when_a_read_fails(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, grid)
    root = GridRoot(
        state={"current": 120, "maximum": 400, "viewport": 200},
        rows_error=PlaywrightError("grid bị dispose giữa lúc quét"),
    )

    with pytest.raises(PlaywrightError):
        grid._scan_sale_asn_rows(GridFrame(root, clock=clock), root)

    assert root.scrolled[-1] == 120


def test_a_grid_that_does_not_scroll_is_read_exactly_once(monkeypatch):
    clock = install_fake_clock(monkeypatch, grid)
    root = GridRoot(payloads=[_payload(_row(0, "INV-1"))])

    payload = grid._scan_sale_asn_rows(GridFrame(root, clock=clock), root)

    assert root.scrolled == [0, 0]
    assert payload["rows"][0]["invoice_no"] == "INV-1"


def test_merging_keeps_the_first_order_and_never_drops_a_value():
    merged = grid._merge_sale_asn_row_payloads(
        [
            _payload(_row("b", invoice_no="INV-B"), _row("a")),
            _payload(_row("a", buyer="TRUEWERK"), _row("b", selected=True)),
            _payload(_row("a", invoice_no="INV-A", buyer="")),
        ]
    )

    assert merged["rows"] == [
        _row("b", invoice_no="INV-B", selected=True),
        _row("a", invoice_no="INV-A", buyer="TRUEWERK"),
    ]
    assert merged["noRows"] is False


def test_merging_only_reports_no_rows_when_every_position_agreed():
    assert grid._merge_sale_asn_row_payloads([])["noRows"] is False
    assert (
        grid._merge_sale_asn_row_payloads(
            [_payload(no_rows=True), _payload(no_rows=True)]
        )["noRows"]
        is True
    )
    assert (
        grid._merge_sale_asn_row_payloads(
            [_payload(no_rows=True), _payload(_row(0))]
        )["noRows"]
        is False
    )


# --- bấm Docs -----------------------------------------------------------


def test_clicking_docs_stops_at_the_position_where_the_column_is_visible(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, grid)
    root = GridRoot(
        state={"current": 0, "maximum": 900, "viewport": 400},
        docs_at=600,
    )
    logs: list[str] = []

    assert grid._click_sale_asn_docs(
        GridFrame(root, clock=clock), root, "3", logs.append
    ) is True
    assert root.scrolled == [0, 300, 600]
    assert root.clicked[-1] == {"rowKey": "3"}
    assert logs == [
        "[SALE ASN DOCS] Đã tìm thấy cột Docs sau khi quét ngang grid."
    ]


def test_a_grid_without_a_docs_column_is_left_exactly_where_it_was(monkeypatch):
    clock = install_fake_clock(monkeypatch, grid)
    root = GridRoot(state={"current": 450, "maximum": 900, "viewport": 400})
    logs: list[str] = []

    assert grid._click_sale_asn_docs(
        GridFrame(root, clock=clock), root, "3", logs.append
    ) is False
    assert root.scrolled[-1] == 450
    assert logs == []


# --- chọn dòng ----------------------------------------------------------


def test_an_empty_grid_means_the_invoice_was_not_found():
    with pytest.raises(RuntimeError, match="SALE_ASN_INVOICE_NOT_FOUND"):
        grid._select_sale_asn_row(_payload(), "invoice_no", "INV-1")


def test_an_exact_invoice_wins_over_the_rows_around_it():
    payload = _payload(
        _row(0, invoice_no="INV-10"),
        _row(1, invoice_no="INV-1"),
        _row(2, invoice_no="INV-100"),
    )

    assert grid._select_sale_asn_row(payload, "invoice_no", "inv-1") == _row(
        1, invoice_no="INV-1"
    )


def test_two_identical_invoices_are_resolved_by_what_the_user_selected():
    payload = _payload(
        _row(0, invoice_no="INV-1"),
        _row(1, invoice_no="INV-1", selected=True),
    )

    assert grid._select_sale_asn_row(payload, "invoice_no", "INV-1")[
        "row_key"
    ] == "1"


def test_two_identical_invoices_with_nothing_selected_stop_the_flow():
    payload = _payload(
        _row(0, invoice_no="INV-1"), _row(1, invoice_no="INV-1")
    )

    with pytest.raises(RuntimeError, match="SALE_ASN_MULTIPLE_RESULTS"):
        grid._select_sale_asn_row(payload, "invoice_no", "INV-1")


def test_two_identical_invoices_both_selected_also_stop_the_flow():
    payload = _payload(
        _row(0, invoice_no="INV-1", selected=True),
        _row(1, invoice_no="INV-1", selected=True),
    )

    with pytest.raises(RuntimeError, match="SALE_ASN_MULTIPLE_RESULTS"):
        grid._select_sale_asn_row(payload, "invoice_no", "INV-1")


def test_an_invoice_that_is_not_in_the_grid_is_not_silently_replaced():
    payload = _payload(_row(0, invoice_no="INV-2"))

    with pytest.raises(RuntimeError, match="SALE_ASN_INVOICE_NOT_FOUND"):
        grid._select_sale_asn_row(payload, "invoice_no", "INV-1")


def test_without_an_invoice_the_single_selected_row_is_used():
    payload = _payload(_row(0), _row(1, selected=True))

    assert grid._select_sale_asn_row(payload, "", "")["row_key"] == "1"


def test_without_an_invoice_two_selected_rows_are_ambiguous():
    payload = _payload(_row(0, selected=True), _row(1, selected=True))

    with pytest.raises(RuntimeError, match="SALE_ASN_MULTIPLE_RESULTS"):
        grid._select_sale_asn_row(payload, "", "")


def test_a_search_that_left_exactly_one_row_needs_no_manual_selection():
    assert grid._select_sale_asn_row(
        _payload(_row(0, invoice_no="INV-1")), "buyer_order_ref", "PO-9"
    )["row_key"] == "0"


def test_several_unselected_rows_hand_the_choice_back_to_the_user():
    payload = _payload(_row(0), _row(1))

    with pytest.raises(RuntimeError, match="SALE_ASN_SELECTION_REQUIRED"):
        grid._select_sale_asn_row(payload, "buyer_order_ref", "PO-9")


def test_a_single_row_with_no_query_still_needs_the_user_to_pick_it():
    with pytest.raises(RuntimeError, match="SALE_ASN_SELECTION_REQUIRED"):
        grid._select_sale_asn_row(_payload(_row(0)), "", "")


# --- vị trí cuộn --------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"current": 0, "maximum": 0, "viewport": 0}, [0]),
        ({"current": 250, "maximum": 1000, "viewport": 400}, [250, 0, 300, 600, 900, 1000]),
        # Viewport hẹp vẫn phải dùng bước tối thiểu 160px, không sinh hàng nghìn
        # lần cuộn.
        ({"current": 0, "maximum": 400, "viewport": 10}, [0, 160, 320, 400]),
        # Giá trị âm hoặc dạng chuỗi từ JS không được làm vỡ phép tính.
        ({"current": "-5", "maximum": "320.0", "viewport": None}, [0, 160, 320]),
    ],
)
def test_horizontal_positions_cover_the_grid_without_duplicates(state, expected):
    assert grid._sale_asn_horizontal_positions(state) == expected


def test_a_position_past_the_maximum_is_clamped_not_dropped():
    positions = grid._sale_asn_horizontal_positions(
        {"current": 5_000, "maximum": 300, "viewport": 400}
    )

    assert positions == [300, 0]


def test_the_poll_interval_is_the_shared_module_grid_interval():
    # Nếu ai đó đổi riêng nhịp poll của Sale ASN, grid sẽ lệch nhịp với các
    # module khác dùng chung AG Grid.
    assert grid.MODULE_GRID_POLL_MS == 150
