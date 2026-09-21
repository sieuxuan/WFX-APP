"""Điền 7 cột Order Details và giữ grid WFX đồng bộ với file.

CLAUDE.md yêu cầu: sau khi WFX tự đóng popup giữa hai PO, automation phải xác
nhận các dòng vừa thêm rồi mở lại Add Order Details và tiếp đúng dòng kế — không
được thêm lại dòng đã có, cũng không được bỏ dòng bị rơi.
"""

from __future__ import annotations

from typing import Any

import pytest

import wfx_panel.automation.sale_asn_create.order_details as order_details
from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError
from wfx_panel.automation.sale_asn_create.constants import ORDER_GRID_SELECTOR
from wfx_panel.automation.sale_asn_create.errors import _POSelectionRequired

EDITOR_SELECTOR = "input:not([type='hidden']), textarea, [contenteditable='true']"
LABEL_SELECTOR = ".lblEditable, .lblEditDatePicker, [contenteditable='true']"
TARGET_SELECTOR = "[data-wfx-sale-asn-target='1']"


class Editor:
    def __init__(self, *, count=1, wait_error=None, fill_error=None):
        self._count = count
        self.wait_error = wait_error
        self.fill_error = fill_error
        self.fills: list[str] = []
        self.keys: list[str] = []

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def wait_for(self, **_kwargs):
        if self.wait_error is not None:
            raise self.wait_error

    def fill(self, value, **_kwargs):
        if self.fill_error is not None:
            raise self.fill_error
        self.fills.append(value)

    def press(self, key, **_kwargs):
        self.keys.append(key)


class LabelAction:
    def __init__(self, *, count=1, on_click=None):
        self._count = count
        self.on_click = on_click
        self.clicks = 0

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def click(self, **_kwargs):
        self.clicks += 1
        if self.on_click is not None:
            self.on_click()


class MarkedCell:
    """Ô đã được đánh dấu `data-wfx-sale-asn-target`."""

    def __init__(self, *, editor=None, label=None, values=None):
        self.editor = editor if editor is not None else Editor()
        self.label = label if label is not None else LabelAction(count=0)
        self.values = list(values or [])
        self.scrolled = 0

    @property
    def first(self):
        return self

    def scroll_into_view_if_needed(self, **_kwargs):
        self.scrolled += 1

    def locator(self, selector):
        if selector == EDITOR_SELECTOR:
            return self.editor
        if selector == LABEL_SELECTOR:
            return self.label
        raise AssertionError(f"selector lạ: {selector}")

    def evaluate(self, _script, _arg=None):
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0] if self.values else ""


class GridFrame:
    def __init__(self, nodes=None, *, clock=None, mark=None):
        self.nodes = dict(nodes or {})
        self.clock = clock
        self.mark = mark
        self.marks: list[dict[str, Any]] = []

    def locator(self, selector):
        # Nút Add Order Details chỉ cần tồn tại; `_click_dom_action` mới là
        # nơi quyết định click được hay không.
        return self.nodes.get(selector) or LabelAction()

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)

    def evaluate(self, script, arg=None):
        if "order-grid-not-found" in script:
            self.marks.append(dict(arg))
            if callable(self.mark):
                return self.mark(arg)
            return self.mark or {"ok": True}
        raise AssertionError(f"script lạ: {script[:60]}")


# --- sửa một ô đã đánh dấu ----------------------------------------------


def test_editing_a_cell_scrolls_to_it_then_confirms_what_wfx_kept(monkeypatch):
    clock = install_fake_clock(monkeypatch, order_details)
    editor = Editor()
    cell = MarkedCell(editor=editor, values=["", "12"])
    frame = GridFrame({TARGET_SELECTOR: cell}, clock=clock)

    assert order_details._edit_marked_table_cell(frame, "12") == "12"
    assert cell.scrolled == 1
    assert editor.fills == ["12"]
    assert editor.keys == ["Tab"]


def test_a_read_only_label_is_clicked_once_to_reveal_its_editor(monkeypatch):
    clock = install_fake_clock(monkeypatch, order_details)
    editor = Editor(count=0)

    def reveal():
        editor._count = 1

    cell = MarkedCell(
        editor=editor, label=LabelAction(on_click=reveal), values=["7"]
    )

    assert order_details._edit_marked_table_cell(
        GridFrame({TARGET_SELECTOR: cell}, clock=clock), "7"
    ) == "7"
    assert cell.label.clicks == 1


def test_a_cell_with_neither_editor_nor_label_is_reported_as_not_editable(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, order_details)
    cell = MarkedCell(editor=Editor(count=0), label=LabelAction(count=0))

    with pytest.raises(
        RuntimeError, match="SALE_ASN_FIELD_NOT_EDITABLE:editor-not-found"
    ):
        order_details._edit_marked_table_cell(
            GridFrame({TARGET_SELECTOR: cell}, clock=clock), "7"
        )


def test_a_value_wfx_silently_rewrites_is_reported_with_what_it_kept(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, order_details)
    cell = MarkedCell(values=["0.00"])

    with pytest.raises(
        RuntimeError, match="SALE_ASN_FIELD_VALUE_NOT_CONFIRMED:0.00"
    ):
        order_details._edit_marked_table_cell(
            GridFrame({TARGET_SELECTOR: cell}, clock=clock), "12.5"
        )


def test_a_number_wfx_reformats_with_thousand_separators_still_matches(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, order_details)
    cell = MarkedCell(values=["1,250.00"])

    assert order_details._edit_marked_table_cell(
        GridFrame({TARGET_SELECTOR: cell}, clock=clock), "1250"
    ) == "1,250.00"


# --- đánh dấu ô theo PO + Style -----------------------------------------


def test_a_cell_is_marked_by_po_and_style_before_it_is_edited(monkeypatch):
    clock = install_fake_clock(monkeypatch, order_details)
    cell = MarkedCell(values=["5"])
    frame = GridFrame({TARGET_SELECTOR: cell}, clock=clock, mark={"ok": True})

    order_details._set_order_grid_cell(
        frame, "779", "M ACEL JACKET", "colTotalNoOfCartons", "5"
    )

    assert frame.marks == [
        {
            "table": ORDER_GRID_SELECTOR,
            "po_no": "779",
            "style_no": "M ACEL JACKET",
            "column_id": "colTotalNoOfCartons",
        }
    ]


def test_a_row_the_grid_does_not_contain_is_named_not_edited_blindly(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, order_details)
    frame = GridFrame(
        {}, clock=clock, mark={"ok": False, "reason": "row-not-found"}
    )

    with pytest.raises(
        RuntimeError, match="SALE_ASN_TABLE_MAPPING_FAILED:row-not-found"
    ):
        order_details._set_order_grid_cell(
            frame, "779", "M ACEL JACKET", "colTotalVolume", "1.2"
        )


# --- so khớp Style ------------------------------------------------------


@pytest.mark.parametrize(
    ("wanted", "actual", "expected"),
    [
        ("", "m acel jacket", False),
        ("m acel jacket", "", False),
        ("m acel jacket", "m acel jacket", True),
        ("m acel jacket", "jld smow17905 m acel jacket men", True),
        ("jld smow17905 m acel jacket men", "m acel jacket", True),
        ("m acel jacket", "w acel jacket", False),
    ],
)
def test_style_matching_accepts_the_longer_wfx_label(wanted, actual, expected):
    assert order_details._order_style_matches(wanted, actual) is expected


def test_a_row_without_a_style_matches_any_line_of_the_same_po():
    present = {("779", "m acel jacket")}

    assert order_details._order_row_is_present({"po_no": "779"}, present) is True
    assert order_details._order_row_is_present({"po_no": "780"}, present) is False


def test_missing_rows_ignore_lines_that_have_no_po_at_all():
    rows = [{"po_no": "779"}, {"po_no": ""}, {"po_no": "780"}]

    assert order_details._missing_order_rows(rows, {("779", "")}) == [
        {"po_no": "780"}
    ]


# --- chờ grid Order Details --------------------------------------------


class GridTable:
    def __init__(self, batches, *, wait_error=None):
        self.batches = list(batches)
        self.wait_error = wait_error

    @property
    def first(self):
        return self

    def wait_for(self, **_kwargs):
        if self.wait_error is not None:
            raise self.wait_error

    def evaluate(self, _script, _arg=None):
        if len(self.batches) > 1:
            outcome = self.batches.pop(0)
        else:
            outcome = self.batches[0] if self.batches else []
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _grid(batches, clock, **kwargs):
    return GridFrame(
        {ORDER_GRID_SELECTOR: GridTable(batches, **kwargs)}, clock=clock
    )


def test_the_grid_is_accepted_once_every_expected_po_is_present(monkeypatch):
    clock = install_fake_clock(monkeypatch, order_details)
    frame = _grid(
        [
            [],
            [{"po_no": "779", "style_no": "M ACEL JACKET"}],
            [
                {"po_no": "779", "style_no": "M ACEL JACKET"},
                {"po_no": "780", "style_no": "W ACEL JACKET"},
            ],
        ],
        clock,
    )

    present = order_details._wait_order_grid(
        frame,
        [{"po_no": "779", "style_no": "M ACEL"}, {"po_no": "780"}],
        timeout_s=10,
    )

    assert ("780", "w acel jacket") in present


def test_a_grid_that_swaps_its_tbody_mid_poll_is_read_again(monkeypatch):
    clock = install_fake_clock(monkeypatch, order_details)
    frame = _grid(
        [
            PlaywrightError("Execution context was destroyed"),
            [{"po_no": "779", "style_no": ""}],
        ],
        clock,
    )

    assert order_details._wait_order_grid(
        frame, [{"po_no": "779"}], timeout_s=10
    ) == {("779", "")}


def test_a_grid_that_never_shows_the_po_is_reported_not_assumed(monkeypatch):
    clock = install_fake_clock(monkeypatch, order_details)
    frame = _grid([[{"po_no": "111", "style_no": ""}]], clock)

    with pytest.raises(RuntimeError, match="SALE_ASN_ORDER_GRID_NOT_READY"):
        order_details._wait_order_grid(frame, [{"po_no": "779"}], timeout_s=3)


def test_an_incomplete_grid_can_be_returned_when_the_caller_will_repair_it(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, order_details)
    frame = _grid([[{"po_no": "111", "style_no": ""}]], clock)

    assert order_details._wait_order_grid(
        frame, [{"po_no": "779"}], timeout_s=3, allow_incomplete=True
    ) == {("111", "")}


def test_a_wait_with_nothing_expected_still_runs_out_its_deadline(monkeypatch):
    clock = install_fake_clock(monkeypatch, order_details)
    frame = _grid([[]], clock)

    with pytest.raises(RuntimeError, match="SALE_ASN_ORDER_GRID_NOT_READY"):
        order_details._wait_order_grid(frame, [], timeout_s=2)


# --- mở lại popup giữa hai PO -------------------------------------------


def test_a_popup_that_is_still_open_is_reused_as_is(monkeypatch):
    install_fake_clock(monkeypatch, order_details)
    patch_automation(
        monkeypatch,
        order_details,
        "_frame_with_selector",
        lambda *_a, **_k: ("page", "popup-frame"),
    )

    assert order_details._ensure_po_popup_for_next_row(
        object(), [{"po_no": "779"}], lambda _line: None
    ) == "popup-frame"


def test_a_popup_wfx_closed_is_reopened_only_after_the_grid_caught_up(
    monkeypatch,
):
    install_fake_clock(monkeypatch, order_details)
    calls: list[str] = []

    def frame_with_selector(_context, selector, **_kwargs):
        calls.append(selector)
        if selector == "#wfx_GMPOAsnSearch" and len(calls) == 1:
            raise PlaywrightTimeoutError("popup đã đóng")
        if selector == "#sectionOrderDetails":
            return "page", GridFrame()
        return "page", "popup-frame"

    patch_automation(
        monkeypatch, order_details, "_frame_with_selector", frame_with_selector
    )
    waited: list[Any] = []
    patch_automation(
        monkeypatch,
        order_details,
        "_wait_order_grid",
        lambda _frame, rows, **_k: waited.append(list(rows)),
    )
    clicked: list[Any] = []
    patch_automation(
        monkeypatch,
        order_details,
        "_click_dom_action",
        lambda node, **_k: clicked.append(node),
    )
    lines: list[str] = []

    popup = order_details._ensure_po_popup_for_next_row(
        object(), [{"po_no": "779"}], lines.append
    )

    assert popup == "popup-frame"
    assert waited == [[{"po_no": "779"}]]
    assert clicked, "phải bấm Add Order Details để mở lại popup"
    assert any("đang chờ Order Details cập nhật" in line for line in lines)
    assert any("đã mở lại Add Order Details" in line for line in lines)


# --- vá lại các PO bị rơi -----------------------------------------------


def test_a_complete_grid_needs_no_repair_at_all(monkeypatch):
    install_fake_clock(monkeypatch, order_details)
    patch_automation(
        monkeypatch,
        order_details,
        "_wait_order_grid",
        lambda *_a, **_k: {("779", "")},
    )
    patch_automation(
        monkeypatch,
        order_details,
        "_frame_with_selector",
        lambda *_a, **_k: pytest.fail("Grid đủ PO thì không được mở lại popup"),
    )

    assert order_details._ensure_order_grid_rows(
        object(), "main", [{"po_no": "779"}], lambda _line: None
    ) == "main"


def test_only_the_missing_pos_are_added_again_and_the_last_one_closes_the_popup(
    monkeypatch,
):
    install_fake_clock(monkeypatch, order_details)
    patch_automation(
        monkeypatch,
        order_details,
        "_wait_order_grid",
        lambda *_a, **_k: {("779", "")},
    )
    patch_automation(
        monkeypatch,
        order_details,
        "_frame_with_selector",
        lambda _context, selector, **_k: ("page", f"frame:{selector}"),
    )
    attempts: list[tuple[str, bool]] = []

    def auto_add(_context, popup_frame, row, _log, *, final, search_fields):
        attempts.append((row["po_no"], final))
        return True, [], "PO No.", popup_frame

    patch_automation(
        monkeypatch, order_details, "_auto_add_po_with_frame_retry", auto_add
    )
    lines: list[str] = []

    refreshed = order_details._ensure_order_grid_rows(
        object(),
        "main",
        [{"po_no": "779"}, {"po_no": "780"}, {"po_no": "781"}],
        lines.append,
    )

    assert attempts == [("780", False), ("781", True)]
    assert refreshed == "frame:#sectionOrderDetails"
    assert any("còn thiếu 2 PO" in line for line in lines)
    assert lines[-1] == "[SALE ASN] Đã xác nhận đủ PO trong Order Details."


def test_repair_reopens_the_popup_when_wfx_already_closed_it(monkeypatch):
    install_fake_clock(monkeypatch, order_details)
    patch_automation(
        monkeypatch, order_details, "_wait_order_grid", lambda *_a, **_k: set()
    )
    seen: list[float] = []

    def frame_with_selector(_context, selector, *, timeout_s):
        seen.append(timeout_s)
        if selector == "#wfx_GMPOAsnSearch" and timeout_s == 0.8:
            raise PlaywrightTimeoutError("popup đã đóng")
        return "page", f"frame:{selector}"

    patch_automation(
        monkeypatch, order_details, "_frame_with_selector", frame_with_selector
    )
    clicked: list[Any] = []
    patch_automation(
        monkeypatch,
        order_details,
        "_click_dom_action",
        lambda node, **_k: clicked.append(node),
    )
    patch_automation(
        monkeypatch,
        order_details,
        "_auto_add_po_with_frame_retry",
        lambda _c, popup, _row, _log, **_k: (True, [], "PO No.", popup),
    )
    order_details._ensure_order_grid_rows(
        object(), GridFrame(), [{"po_no": "779"}], lambda _line: None
    )

    assert clicked, "popup đã đóng thì phải bấm lại Add Order Details"


def test_a_po_that_needs_the_user_to_choose_keeps_the_popup_open(monkeypatch):
    install_fake_clock(monkeypatch, order_details)
    patch_automation(
        monkeypatch, order_details, "_wait_order_grid", lambda *_a, **_k: set()
    )
    patch_automation(
        monkeypatch,
        order_details,
        "_frame_with_selector",
        lambda _context, selector, **_k: ("page", f"frame:{selector}"),
    )
    candidates = [{"po_no": "779", "row_index": 0}]
    patch_automation(
        monkeypatch,
        order_details,
        "_auto_add_po_with_frame_retry",
        lambda _c, popup, _row, _log, **_k: (
            False,
            candidates,
            "ambiguous",
            popup,
        ),
    )

    with pytest.raises(_POSelectionRequired) as error:
        order_details._ensure_order_grid_rows(
            object(), "main", [{"po_no": "779"}], lambda _line: None
        )

    assert error.value.candidates == candidates
    assert error.value.reason == "ambiguous"
    assert error.value.final is True


# --- điền 7 cột ---------------------------------------------------------


def test_only_the_columns_with_a_value_are_written(monkeypatch):
    install_fake_clock(monkeypatch, order_details)
    written: list[tuple[str, str]] = []
    patch_automation(
        monkeypatch,
        order_details,
        "_set_order_grid_cell",
        lambda _frame, _po, _style, column_id, value: written.append(
            (column_id, value)
        ),
    )
    stages: list[tuple] = []
    lines: list[str] = []

    order_details._fill_order_details(
        "frame",
        [
            {
                "po_no": "779",
                "style_no": "M ACEL",
                "carton": "5",
                "nw": "",
                "cbm": "1.25",
                "cargo_ready_date": "2026-03-01",
            }
        ],
        lines.append,
        lambda *args, **kwargs: stages.append((args, kwargs)),
    )

    assert written == [
        ("colTotalNoOfCartons", "5"),
        ("colTotalVolume", "1.25"),
        ("colFFDate1", "01 Mar 2026"),
    ]
    assert stages[0][0][0] == "order_details"
    # UI đọc hậu tố n/m để hiện bộ đếm, nên định dạng này là hợp đồng.
    assert stages[0][0][1].endswith("1/1")
    assert stages[0][0][2:] == (2, 5)
    assert stages[0][1] == {"state": "active"}
    assert lines == ["[SALE ASN] Đã điền Order Details cho 779."]


# --- xuất Order Details đang mở ----------------------------------------


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, order_details)


def test_scanning_reads_every_po_from_the_open_grid(monkeypatch, clock):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, order_details, world)
    rows = [{"po_no": "779", "carton": "5"}, {"po_no": "780", "carton": "2"}]
    frame = GridFrame({})
    frame.evaluate = lambda _script, _arg=None: rows
    patch_automation(
        monkeypatch,
        order_details,
        "_frame_with_selector",
        lambda *_a, **_k: ("page", frame),
    )

    result = order_details.scan_sale_asn_order_details(print)

    assert result["code"] == "SALE_ASN_ORDER_DETAILS_SCANNED"
    assert result["rows"] == rows
    assert result["po_count"] == 2
    assert world.driver_stops == 1


def test_scanning_an_empty_grid_names_the_business_error(monkeypatch, clock):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, order_details, world)
    frame = GridFrame({})
    frame.evaluate = lambda _script, _arg=None: []
    patch_automation(
        monkeypatch,
        order_details,
        "_frame_with_selector",
        lambda *_a, **_k: ("page", frame),
    )
    lines: list[str] = []

    result = order_details.scan_sale_asn_order_details(lines.append)

    assert result["code"] == "SALE_ASN_ORDER_GRID_EMPTY"
    assert lines[-1] == result["message"]


def test_scanning_without_the_order_grid_open_is_a_timing_error(
    monkeypatch, clock
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, order_details, world)

    def explode(*_args, **_kwargs):
        raise PlaywrightTimeoutError("Không tìm thấy vùng Sale ASN")

    patch_automation(
        monkeypatch, order_details, "_frame_with_selector", explode
    )

    result = order_details.scan_sale_asn_order_details(print)

    assert result["code"] == "SALE_ASN_ORDER_SCAN_FAILED"
    assert "chưa sẵn sàng" in result["message"]
    assert world.driver_stops == 1


@pytest.mark.parametrize(
    ("chrome_ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_the_browser_boundary_codes_survive_the_scan_wrapper(
    monkeypatch, clock, chrome_ready, logged_in, expected
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(
        monkeypatch,
        order_details,
        world,
        chrome_ready=chrome_ready,
        logged_in=logged_in,
    )

    result = order_details.scan_sale_asn_order_details(print)

    assert result["code"] == expected
