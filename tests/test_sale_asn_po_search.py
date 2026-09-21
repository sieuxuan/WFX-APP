"""Tìm PO trong popup Add Order Details và phục hồi khi WFX thay document.

Popup này là chỗ WFX hay tự reload nhất: click Search có thể thay cả document,
và mọi thứ đã submit vẫn phải được nhận lại thay vì tìm lại từ đầu. Các test ở
đây mô phỏng đúng những tình huống đó cùng luật chọn dòng theo Dispatched Qty.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

import wfx_panel.automation.sale_asn_create.po as po
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError
from wfx_panel.automation.sale_asn_create.constants import (
    PO_CONTINUE_SELECTOR,
    PO_OK_SELECTOR,
    PO_RESULTS_TABLE_SELECTOR,
    PO_SEARCH_SELECTOR,
)
from wfx_panel.automation.sale_asn_create.errors import (
    _is_transient_frame_error,
    _POFrameChanged,
)

TRANSIENT = PlaywrightError("Execution context was destroyed")
FATAL = PlaywrightError("Target closed")


class Node:
    """Một locator đã resolve: đủ bề mặt cho các helper của `po.py`."""

    def __init__(
        self,
        *,
        count=1,
        value="",
        visible=True,
        enabled=True,
        wait_error=None,
        fill_error=None,
        read_error=None,
        evaluate_result=None,
        evaluate_error=None,
        keeps_value=True,
    ):
        self._count = count
        self.value = value
        self.visible = visible
        self.enabled = enabled
        self.wait_error = wait_error
        self.fill_error = fill_error
        self.read_error = read_error
        self.evaluate_result = evaluate_result
        self.evaluate_error = evaluate_error
        self.keeps_value = keeps_value
        self.fills: list[str] = []
        self.waits = 0
        self.evaluations: list[Any] = []

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def is_visible(self):
        return self.visible

    def wait_for(self, **_kwargs):
        self.waits += 1
        if self.wait_error is not None:
            raise self.wait_error

    def input_value(self, **_kwargs):
        if self.read_error is not None:
            # WFX chỉ chặn lần đọc đầu; lần sau frame đã ổn định trở lại.
            error, self.read_error = self.read_error, None
            raise error
        return self.value

    def fill(self, value, **_kwargs):
        if self.fill_error is not None:
            raise self.fill_error
        self.fills.append(value)
        if self.keeps_value:
            self.value = value

    def evaluate(self, script, arg=None):
        self.evaluations.append((script, arg))
        if self.evaluate_error is not None:
            raise self.evaluate_error
        if callable(self.evaluate_result):
            return self.evaluate_result(arg)
        return self.evaluate_result


class PopupFrame:
    """Frame popup: map selector → Node, và script monitor của Search."""

    url = "https://wfx.test/GMPOAsnSearch.aspx"

    def __init__(
        self,
        nodes=None,
        *,
        clock=None,
        monitor=True,
        monitor_error=None,
        poll_states=None,
        poll_error=None,
        cleanup_error=None,
    ):
        self.nodes = dict(nodes or {})
        self.clock = clock
        self.monitor = monitor
        self.monitor_error = monitor_error
        self.poll_states = list(poll_states or [])
        self.poll_error = poll_error
        self.cleanup_error = cleanup_error
        self.cleanups = 0
        self.polls = 0

    def locator(self, selector):
        return self.nodes.get(selector, Node(count=0))

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)

    def evaluate(self, script, _arg=None):
        if "new MutationObserver" in script:
            if self.monitor_error is not None:
                raise self.monitor_error
            return self.monitor
        if "delete window.__wfxPoSearchMonitor" in script:
            self.cleanups += 1
            if self.cleanup_error is not None:
                raise self.cleanup_error
            return None
        if "const monitor" in script:
            self.polls += 1
            if self.poll_error is not None:
                raise self.poll_error
            if len(self.poll_states) > 1:
                return self.poll_states.pop(0)
            return self.poll_states[0] if self.poll_states else {}
        raise AssertionError(f"script lạ: {script[:60]}")


# --- điền ô popup -------------------------------------------------------


def test_a_selector_that_does_not_exist_on_this_tenant_is_skipped_instantly():
    frame = PopupFrame({"#txtStyle": Node(count=0)})

    assert po._fill_popup_input(frame, "#txtStyle", "ACEL") is False


def test_an_input_that_never_becomes_visible_is_treated_as_absent():
    node = Node(wait_error=PlaywrightTimeoutError("không hiện"))

    assert po._fill_popup_input(PopupFrame({"#txtOCNo": node}), "#txtOCNo", "779") is False
    assert node.fills == []


def test_an_input_already_holding_the_value_is_left_alone():
    node = Node(value="779")

    assert po._fill_popup_input(PopupFrame({"#txtOCNo": node}), "#txtOCNo", "779") is True
    assert node.fills == []


def test_an_input_whose_value_cannot_be_read_is_filled_anyway():
    node = Node(value="779", read_error=PlaywrightError("value không đọc được"))

    # Đọc hỏng thì không kết luận được gì; điền lại là lựa chọn an toàn, rồi
    # mới xác nhận giá trị đã vào ô.
    assert po._fill_popup_input(
        PopupFrame({"#txtOCNo": node}), "#txtOCNo", "779"
    ) is True
    assert node.fills == ["779"]


def test_filling_confirms_the_value_actually_stuck():
    node = Node()

    assert po._fill_popup_input(PopupFrame({"#txtOCNo": node}), "#txtOCNo", "779") is True
    assert node.fills == ["779"]


def test_an_input_that_silently_drops_the_value_is_not_reported_as_filled():
    node = Node(keeps_value=False)

    assert po._fill_popup_input(PopupFrame({"#txtOCNo": node}), "#txtOCNo", "779") is False


# --- Destination --------------------------------------------------------


DESTINATION_SELECTOR = (
    "#wfx_GMPOAsnSearch select[name='cboDestination'], "
    "#wfx_GMPOAsnSearch #cboDestination"
)


def test_a_popup_without_a_destination_dropdown_simply_skips_it():
    frame = PopupFrame({DESTINATION_SELECTOR: Node(count=0)})

    assert po._select_popup_destination(frame, "VIETNAM") is False


def test_a_hidden_destination_dropdown_is_not_touched():
    node = Node(visible=False)

    assert po._select_popup_destination(
        PopupFrame({DESTINATION_SELECTOR: node}), "VIETNAM"
    ) is False
    assert node.evaluations == []


def test_the_destination_is_chosen_inside_the_dom_in_one_call():
    node = Node(evaluate_result=True)

    assert po._select_popup_destination(
        PopupFrame({DESTINATION_SELECTOR: node}), "  VIETNAM  "
    ) is True
    # Danh sách quốc gia rất dài nên chỉ được gọi Playwright đúng một lần.
    assert len(node.evaluations) == 1
    assert node.evaluations[0][1] == "VIETNAM"


def test_a_destination_wfx_does_not_offer_is_reported_as_not_set():
    node = Node(evaluate_result=False)

    assert po._select_popup_destination(
        PopupFrame({DESTINATION_SELECTOR: node}), "SAO HỎA"
    ) is False


# --- click action -------------------------------------------------------


def test_a_disabled_action_is_named_instead_of_being_clicked_blindly():
    node = Node(evaluate_result={"ok": False, "reason": "action-disabled"})

    with pytest.raises(
        RuntimeError, match="SALE_ASN_ACTION_NOT_READY:action-disabled"
    ):
        po._click_dom_action(node)


def test_an_action_failure_without_a_reason_still_produces_a_code():
    node = Node(evaluate_result={"ok": False})

    with pytest.raises(RuntimeError, match="SALE_ASN_ACTION_NOT_READY:unknown"):
        po._click_dom_action(node)


def test_a_successful_action_returns_what_wfx_actually_clicked():
    node = Node(evaluate_result={"ok": True, "tag": "INPUT", "id": "btnSearch"})

    assert po._click_dom_action(node) == {
        "ok": True,
        "tag": "INPUT",
        "id": "btnSearch",
    }


# --- click Search -------------------------------------------------------


def _search_frame(monkeypatch, clock, **kwargs):
    search = Node(evaluate_result={"ok": True, "tag": "INPUT", "id": "btnSearch"})
    frame = PopupFrame({PO_SEARCH_SELECTOR: search}, clock=clock, **kwargs)
    return frame, search


def test_a_popup_without_the_mutation_root_falls_back_to_a_flat_wait(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, po)
    frame, search = _search_frame(monkeypatch, clock, monitor=False)
    started = clock.monotonic()

    po._click_search(frame)

    assert search.evaluations, "vẫn phải click Search"
    assert clock.monotonic() - started == pytest.approx(0.7)
    assert frame.polls == 0


def test_a_frame_that_refuses_the_observer_still_clicks_and_waits(monkeypatch):
    clock = install_fake_clock(monkeypatch, po)
    frame, search = _search_frame(
        monkeypatch, clock, monitor_error=PlaywrightError("CSP chặn script")
    )

    po._click_search(frame)

    assert search.evaluations
    assert frame.polls == 0


def test_search_returns_as_soon_as_the_dom_changed_and_went_quiet(monkeypatch):
    clock = install_fake_clock(monkeypatch, po)
    frame, _search = _search_frame(
        monkeypatch,
        clock,
        poll_states=[
            {"changed": False, "quietMs": 0, "busy": True},
            {"changed": True, "quietMs": 30, "busy": False},
            {"changed": True, "quietMs": 200, "busy": False},
        ],
    )
    started = clock.monotonic()

    po._click_search(frame)

    assert frame.polls == 3
    assert clock.monotonic() - started < 0.7
    assert frame.cleanups == 1


def test_a_search_whose_results_are_identical_waits_out_the_flat_fallback(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, po)
    frame, _search = _search_frame(
        monkeypatch,
        clock,
        poll_states=[{"changed": False, "quietMs": 0, "busy": False}],
    )
    started = clock.monotonic()

    po._click_search(frame)

    assert clock.monotonic() - started >= 0.7


def test_a_blocking_overlay_keeps_search_waiting_until_it_clears(monkeypatch):
    clock = install_fake_clock(monkeypatch, po)
    frame, _search = _search_frame(
        monkeypatch,
        clock,
        poll_states=[{"changed": True, "quietMs": 900, "busy": True}],
    )

    po._click_search(frame)

    # blockUI không bao giờ tắt: phải chạy hết 5 giây rồi mới bỏ cuộc, không
    # được nhận kết quả trong lúc WFX còn đang chặn UI.
    assert frame.polls > 50
    assert frame.cleanups == 1


def test_a_document_swap_during_search_is_reported_as_already_submitted(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, po)
    frame, _search = _search_frame(monkeypatch, clock, poll_error=TRANSIENT)

    with pytest.raises(_POFrameChanged) as error:
        po._click_search(frame)

    assert error.value.search_submitted is True
    assert frame.cleanups == 1


def test_a_real_playwright_failure_during_search_is_not_swallowed(monkeypatch):
    clock = install_fake_clock(monkeypatch, po)
    frame, _search = _search_frame(monkeypatch, clock, poll_error=FATAL)

    with pytest.raises(PlaywrightError, match="Target closed"):
        po._click_search(frame)


def test_a_cleanup_that_fails_never_hides_the_search_result(monkeypatch):
    clock = install_fake_clock(monkeypatch, po)
    frame, _search = _search_frame(
        monkeypatch,
        clock,
        poll_states=[{"changed": True, "quietMs": 200, "busy": False}],
        cleanup_error=TRANSIENT,
    )

    po._click_search(frame)

    assert frame.cleanups == 1


def test_search_falls_back_to_the_xpath_button_when_the_id_is_missing(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, po)
    fallback = Node(evaluate_result={"ok": True, "tag": "INPUT", "id": ""})
    frame = PopupFrame(
        {
            PO_SEARCH_SELECTOR: Node(count=0),
            "xpath=//*[@id='wfx_GMPOAsnSearch']/table[3]/tbody/tr/td[2]/input": (
                fallback
            ),
        },
        clock=clock,
        monitor=False,
    )

    po._click_search(frame)

    assert fallback.evaluations


# --- một lượt search ----------------------------------------------------


def _row(**overrides):
    row = {
        "source_row": 2,
        "po_no": "779",
        "style_no": "M ACEL JACKET",
        "destination": "VIETNAM",
    }
    row.update(overrides)
    return row


def test_a_popup_that_lost_its_po_field_is_a_frame_change_not_a_failure(
    monkeypatch,
):
    install_fake_clock(monkeypatch, po)
    patch_automation(
        monkeypatch, po, "_fill_popup_input", lambda *_a, **_k: False
    )

    with pytest.raises(_POFrameChanged) as error:
        po._search_po(PopupFrame(), _row(), fields=("po", "style"))

    assert error.value.search_submitted is False
    assert error.value.fields == ("po", "style")


def test_a_frame_change_raised_deeper_inherits_the_fields_of_this_attempt(
    monkeypatch,
):
    install_fake_clock(monkeypatch, po)
    patch_automation(
        monkeypatch, po, "_fill_popup_input", lambda *_a, **_k: True
    )
    patch_automation(
        monkeypatch, po, "_select_popup_destination", lambda *_a, **_k: True
    )

    def explode(_frame):
        raise _POFrameChanged(search_submitted=True)

    patch_automation(monkeypatch, po, "_click_search", explode)

    with pytest.raises(_POFrameChanged) as error:
        po._search_po(PopupFrame(), _row(), fields=("po", "destination"))

    assert error.value.fields == ("po", "destination")
    assert error.value.search_submitted is True


def test_a_transient_error_after_submitting_search_keeps_that_fact(monkeypatch):
    install_fake_clock(monkeypatch, po)
    patch_automation(
        monkeypatch, po, "_fill_popup_input", lambda *_a, **_k: True
    )
    patch_automation(
        monkeypatch, po, "_select_popup_destination", lambda *_a, **_k: True
    )
    patch_automation(monkeypatch, po, "_click_search", lambda _frame: None)

    class Exploding(PopupFrame):
        def locator(self, _selector):
            raise TRANSIENT

    with pytest.raises(_POFrameChanged) as error:
        po._search_po(Exploding(), _row(), fields=("po",))

    assert error.value.search_submitted is True


def test_a_fatal_error_while_searching_is_left_for_the_caller(monkeypatch):
    install_fake_clock(monkeypatch, po)
    patch_automation(
        monkeypatch, po, "_fill_popup_input", lambda *_a, **_k: True
    )
    patch_automation(
        monkeypatch, po, "_select_popup_destination", lambda *_a, **_k: True
    )
    patch_automation(monkeypatch, po, "_click_search", lambda _frame: None)

    class Exploding(PopupFrame):
        def locator(self, _selector):
            raise FATAL

    with pytest.raises(PlaywrightError, match="Target closed"):
        po._search_po(Exploding(), _row(), fields=("po",))


def test_a_search_reads_the_results_table_of_the_popup(monkeypatch):
    install_fake_clock(monkeypatch, po)
    rows = [{"po_no": "779", "row_index": 0}]
    table = Node(evaluate_result=rows)
    filled: list[tuple[str, str]] = []
    patch_automation(
        monkeypatch,
        po,
        "_fill_popup_input",
        lambda _frame, selector, value: (
            filled.append((selector, value)) or selector == "#txtOCNo"
        ),
    )
    patch_automation(
        monkeypatch, po, "_select_popup_destination", lambda *_a, **_k: True
    )
    patch_automation(monkeypatch, po, "_click_search", lambda _frame: None)
    frame = PopupFrame({PO_RESULTS_TABLE_SELECTOR: table})

    assert po._search_po(frame, _row(), fields=("po",)) == rows
    # Chỉ bật tiêu chí PO thì Style phải được xóa trắng, không kế thừa dòng cũ.
    assert filled[0] == ("#txtOCNo", "779")
    assert all(value == "" for selector, value in filled[1:])


# --- phục hồi sau khi document đổi --------------------------------------


class RecoveryPage:
    def __init__(self, *frames, clock=None):
        self.frames = list(frames)
        self.clock = clock

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


class RecoveryContext:
    def __init__(self, *pages):
        self.pages = list(pages)


class RecoveryFrame:
    def __init__(self, node):
        self.node = node

    def locator(self, selector):
        assert selector == PO_RESULTS_TABLE_SELECTOR
        return self.node


def test_recovery_takes_the_results_from_the_newest_frame_that_has_them(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, po)
    rows = [{"po_no": "779"}]
    stale = RecoveryFrame(Node(evaluate_result=[{"po_no": "CŨ"}]))
    fresh = RecoveryFrame(Node(evaluate_result=rows))
    context = RecoveryContext(RecoveryPage(stale, fresh, clock=clock))

    recovered = po._recover_submitted_po_results(context, timeout_s=5)

    assert recovered == (fresh, rows)


def test_recovery_ignores_tables_that_are_absent_hidden_or_empty(monkeypatch):
    clock = install_fake_clock(monkeypatch, po)
    absent = RecoveryFrame(Node(count=0))
    hidden = RecoveryFrame(Node(visible=False))
    empty = RecoveryFrame(Node(evaluate_result=[]))
    context = RecoveryContext(RecoveryPage(absent, hidden, empty, clock=clock))

    assert po._recover_submitted_po_results(context, timeout_s=2) is None


def test_recovery_walks_past_a_frame_that_detaches_mid_scan(monkeypatch):
    clock = install_fake_clock(monkeypatch, po)
    rows = [{"po_no": "779"}]
    broken = RecoveryFrame(Node(evaluate_error=TRANSIENT))
    good = RecoveryFrame(Node(evaluate_result=rows))
    # Frame mới nhất đứng cuối và được quét trước: đúng frame vừa bị WFX thay
    # document, nên nó phải được bỏ qua chứ không làm hỏng cả vòng quét.
    context = RecoveryContext(RecoveryPage(good, broken, clock=clock))

    assert po._recover_submitted_po_results(context, timeout_s=5) == (good, rows)


def test_recovery_gives_up_cleanly_when_no_page_is_left(monkeypatch):
    install_fake_clock(monkeypatch, po)

    assert (
        po._recover_submitted_po_results(RecoveryContext(), timeout_s=0.0)
        is None
    )


# --- vòng retry quanh popup --------------------------------------------


def test_the_retry_loop_hands_recovered_results_back_to_the_next_attempt(
    monkeypatch,
):
    install_fake_clock(monkeypatch, po)
    recovered_rows = [{"po_no": "779", "row_index": 0}]
    attempts: list[dict] = []

    def auto_add(_frame, _row, _log, **kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise _POFrameChanged(fields=("po",), search_submitted=True)
        return True, recovered_rows, "PO No."

    patch_automation(monkeypatch, po, "_auto_add_po", auto_add)
    new_frame = object()
    patch_automation(
        monkeypatch,
        po,
        "_recover_submitted_po_results",
        lambda _context, **_k: (new_frame, recovered_rows),
    )
    lines: list[str] = []

    added, candidates, reason, frame = po._auto_add_po_with_frame_retry(
        RecoveryContext(),
        "old-frame",
        _row(),
        lines.append,
        final=False,
        search_fields=("po", "style"),
    )

    assert (added, candidates, reason) == (True, recovered_rows, "PO No.")
    assert frame is new_frame
    assert attempts[1]["recovered_search"] == (("po",), recovered_rows)
    assert any("tải lại" in line for line in lines)
    assert any("1 kết quả PO" in line for line in lines)


def test_the_retry_loop_reopens_the_popup_when_nothing_could_be_recovered(
    monkeypatch,
):
    install_fake_clock(monkeypatch, po)
    attempts: list[dict] = []

    def auto_add(_frame, _row, _log, **kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise _POFrameChanged(fields=("po",), search_submitted=True)
        return True, [], "PO No."

    patch_automation(monkeypatch, po, "_auto_add_po", auto_add)
    patch_automation(
        monkeypatch, po, "_recover_submitted_po_results", lambda *_a, **_k: None
    )
    reopened = object()
    patch_automation(
        monkeypatch,
        po,
        "_frame_with_selector",
        lambda *_a, **_k: ("page", reopened),
    )

    added, _candidates, _reason, frame = po._auto_add_po_with_frame_retry(
        RecoveryContext(),
        "old-frame",
        _row(),
        lambda _line: None,
        final=False,
        search_fields=("po",),
    )

    assert added is True
    assert frame is reopened
    assert "recovered_search" not in attempts[1]


def test_a_popup_that_keeps_reloading_forever_stops_with_a_clear_code(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, po)

    def always_changes(*_args, **_kwargs):
        clock.advance(5)
        raise _POFrameChanged(fields=("po",), search_submitted=False)

    patch_automation(monkeypatch, po, "_auto_add_po", always_changes)
    patch_automation(
        monkeypatch,
        po,
        "_frame_with_selector",
        lambda *_a, **_k: ("page", "frame"),
    )

    with pytest.raises(RuntimeError, match="SALE_ASN_PO_SEARCH_NOT_READY"):
        po._auto_add_po_with_frame_retry(
            RecoveryContext(),
            "old-frame",
            _row(),
            lambda _line: None,
            final=False,
            search_fields=("po",),
        )


# --- tick dòng và bấm Add ----------------------------------------------


def _candidate(index, value, **extra):
    row = {
        "row_index": index,
        "selection_name": "optShipmentId",
        "selection_value": value,
        "selection_order_id": "",
    }
    row.update(extra)
    return row


def test_adding_with_no_candidate_asks_the_user_instead_of_clicking_ok():
    with pytest.raises(RuntimeError, match="SALE_ASN_PO_SELECTION_REQUIRED"):
        po._add_selected_po_candidates(
            PopupFrame(), _row(), [], lambda _line: None, final=True
        )


def test_every_chosen_row_is_ticked_before_the_final_ok_is_clicked(monkeypatch):
    clock = install_fake_clock(monkeypatch, po)
    table = Node(
        evaluate_result=lambda spec: {
            "ok": True,
            "value": spec["selection_value"],
        }
    )
    ok_button = Node(evaluate_result={"ok": True, "tag": "A", "id": "lnkOK"})
    frame = PopupFrame(
        {PO_RESULTS_TABLE_SELECTOR: table, PO_OK_SELECTOR: ok_button},
        clock=clock,
    )
    lines: list[str] = []

    po._add_selected_po_candidates(
        frame,
        _row(),
        [_candidate(0, "11"), _candidate(1, "12")],
        lines.append,
        final=True,
    )

    assert [spec["selection_value"] for _script, spec in table.evaluations] == [
        "11",
        "12",
    ]
    assert any("đã chọn 2 dòng (11, 12)" in line for line in lines)
    assert any("link OK" in line for line in lines)


def test_a_row_that_cannot_be_ticked_stops_before_any_add(monkeypatch):
    clock = install_fake_clock(monkeypatch, po)
    table = Node(
        evaluate_result={"ok": False, "reason": "checkbox-identity-ambiguous"}
    )
    frame = PopupFrame({PO_RESULTS_TABLE_SELECTOR: table}, clock=clock)

    with pytest.raises(
        RuntimeError,
        match="SALE_ASN_PO_SELECTION_NOT_CONFIRMED:checkbox-identity-ambiguous",
    ):
        po._add_selected_po_candidates(
            frame, _row(), [_candidate(0, "11")], lambda _line: None, final=True
        )


def test_a_missing_add_and_continue_link_is_reported_not_ignored(monkeypatch):
    clock = install_fake_clock(monkeypatch, po)
    table = Node(evaluate_result={"ok": True, "value": "11"})
    button = Node(evaluate_result={"ok": False, "reason": "action-not-found"})
    frame = PopupFrame(
        {PO_RESULTS_TABLE_SELECTOR: table, PO_CONTINUE_SELECTOR: button},
        clock=clock,
    )

    with pytest.raises(
        RuntimeError,
        match="SALE_ASN_PO_SELECTION_NOT_CONFIRMED:action-not-found",
    ):
        po._add_selected_po_candidates(
            frame, _row(), [_candidate(0, "11")], lambda _line: None, final=False
        )


def test_a_non_final_po_uses_add_and_continue_and_waits_for_the_grid(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, po)
    table = Node(evaluate_result={"ok": True, "value": "11"})
    button = Node(evaluate_result={"ok": True, "tag": "A", "id": "lnkContinue"})
    frame = PopupFrame(
        {PO_RESULTS_TABLE_SELECTOR: table, PO_CONTINUE_SELECTOR: button},
        clock=clock,
    )
    lines: list[str] = []
    started = clock.monotonic()

    po._add_selected_po_candidates(
        frame, _row(), [_candidate(0, "11")], lines.append, final=False
    )

    assert button.evaluations
    assert not any("link OK" in line for line in lines)
    assert clock.monotonic() - started == pytest.approx(0.25)


# --- tổ hợp Dispatched Qty ---------------------------------------------


def _qty(*values):
    return [
        _candidate(index, str(index), dispatched_qty=value)
        for index, value in enumerate(values)
    ]


@pytest.mark.parametrize(
    ("expected", "candidates"),
    [
        (None, _qty("10")),
        (Decimal("0"), _qty("10")),
        (Decimal("-5"), _qty("10")),
        (Decimal("10"), []),
        # Thiếu Dispatched Qty ở một dòng thì không được đoán tổ hợp nào cả.
        (Decimal("10"), _qty("10", "")),
        (Decimal("10"), _qty("10", "0")),
    ],
)
def test_no_qty_subset_is_guessed_without_complete_data(expected, candidates):
    assert po._unique_dispatched_qty_subset(candidates, expected) is None


def test_a_single_combination_matching_the_file_qty_is_returned():
    subset = po._unique_dispatched_qty_subset(
        _qty("30", "70", "5"), Decimal("100")
    )

    assert [item["selection_value"] for item in subset] == ["0", "1"]


def test_two_combinations_with_the_same_total_are_refused():
    assert (
        po._unique_dispatched_qty_subset(_qty("50", "50", "100"), Decimal("100"))
        is None
    )


def test_a_total_nobody_can_reach_is_refused():
    assert po._unique_dispatched_qty_subset(_qty("30", "40"), Decimal("100")) is None


def test_the_whole_result_set_is_itself_a_valid_answer():
    subset = po._unique_dispatched_qty_subset(_qty("40", "60"), Decimal("100"))

    assert len(subset) == 2


def test_a_combination_search_that_explodes_is_abandoned_not_run_forever():
    # 13 giá trị lũy thừa 2 tạo đủ 8192 tổng khác nhau: quá ngưỡng an toàn nên
    # hàm phải bỏ cuộc thay vì kéo dài vô hạn trên grid lớn.
    quantities = [str(2**index) for index in range(13)]

    assert (
        po._unique_dispatched_qty_subset(_qty(*quantities), Decimal("8191"))
        is None
    )


# --- lỗi frame tạm thời -------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Execution context was destroyed",
        "Frame was detached",
        "Cannot find context with specified id",
    ],
)
def test_the_known_transient_frame_errors_are_recognised(message):
    assert _is_transient_frame_error(PlaywrightError(message)) is True


def test_a_real_failure_is_not_mistaken_for_a_frame_reload():
    assert _is_transient_frame_error(PlaywrightError("Target closed")) is False


# --- chọn bộ tiêu chí ---------------------------------------------------


def _wire_auto_add(monkeypatch, results, *, added=None):
    """`_auto_add_po` chạy thật; chỉ Search và Add là ranh giới Playwright."""

    searched: list[tuple[str, ...]] = []

    def search(_frame, _row, *, fields):
        searched.append(tuple(fields))
        if isinstance(results, dict):
            return list(results.get(tuple(fields), []))
        return list(results)

    patch_automation(monkeypatch, po, "_search_po", search)
    picked: list[list[dict]] = []
    patch_automation(
        monkeypatch,
        po,
        "_add_selected_po_candidates",
        lambda _frame, _row, candidates, _log, **_k: picked.append(
            list(candidates)
        ),
    )
    return searched, picked


def test_a_row_without_a_destination_falls_back_to_searching_by_po(monkeypatch):
    install_fake_clock(monkeypatch, po)
    searched, picked = _wire_auto_add(monkeypatch, [_candidate(0, "11", po_no="779")])
    lines: list[str] = []

    added, _candidates, label = po._auto_add_po(
        PopupFrame(),
        _row(destination="   "),
        lines.append,
        search_fields=("destination",),
    )

    assert added is True
    assert searched == [("po",)]
    assert label == "PO"
    assert picked == [[_candidate(0, "11", po_no="779")]]
    assert any("Destination trống" in line for line in lines)


def test_recovered_results_for_another_criteria_set_are_not_reused(monkeypatch):
    install_fake_clock(monkeypatch, po)
    searched, picked = _wire_auto_add(
        monkeypatch,
        {("po",): [_candidate(0, "11", po_no="779")]},
    )

    added, _candidates, _label = po._auto_add_po(
        PopupFrame(),
        _row(style_no="", destination=""),
        lambda _line: None,
        search_fields=("po",),
        # Kết quả phục hồi thuộc bộ tiêu chí khác hẳn: phải Search lại từ đầu
        # thay vì dùng bảng của lượt trước.
        recovered_search=(("style",), [_candidate(9, "99", po_no="999")]),
    )

    assert added is True
    assert searched == [("po",)]
    assert picked == [[_candidate(0, "11", po_no="779")]]


def test_a_single_row_whose_qty_differs_from_the_file_stops_the_flow(
    monkeypatch,
):
    install_fake_clock(monkeypatch, po)
    _searched, picked = _wire_auto_add(
        monkeypatch,
        [_candidate(0, "11", po_no="779", dispatched_qty="120")],
    )

    with pytest.raises(RuntimeError, match=r"SALE_ASN_PO_QTY_MISMATCH:.*120"):
        po._auto_add_po(
            PopupFrame(),
            _row(qty="100", style_no="", destination=""),
            lambda _line: None,
            search_fields=("po",),
        )

    assert picked == [], "Qty lệch thì tuyệt đối không được thêm PO"


def test_a_single_row_whose_qty_matches_is_added_with_a_confirmation_log(
    monkeypatch,
):
    install_fake_clock(monkeypatch, po)
    _searched, picked = _wire_auto_add(
        monkeypatch,
        [_candidate(0, "11", po_no="779", dispatched_qty="100")],
    )
    lines: list[str] = []

    added, _candidates, _label = po._auto_add_po(
        PopupFrame(),
        _row(qty="100", style_no="", destination=""),
        lines.append,
        search_fields=("po",),
    )

    assert added is True
    assert len(picked) == 1
    assert any("khớp Dispatched Qty" in line for line in lines)
