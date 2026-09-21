"""Luồng nhập kho GRN: Sourcing ASN → checkpoint người dùng → GRN Pending.

CLAUDE.md đặt một checkpoint bắt buộc ở giữa: app KHÔNG tự Confirm Sourcing ASN,
và chỉ mở GRN sau khi user bấm "Tiếp tục làm GRN". Trước mọi luồng, RMPO đã
Received phải dừng ngay với GRN_ALREADY_RECEIVED.
"""

from __future__ import annotations

from typing import Any

import pytest

import wfx_panel.automation.grn.frames as grn_frames
import wfx_panel.automation.grn.receipt as receipt
from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError
from wfx_panel.automation.grn.constants import _GRN_CONTEXT, _SOURCING_CONTEXT


@pytest.fixture
def clock(monkeypatch):
    # `grn/frames.py` đọc `time` từ namespace của chính nó; fake clock phải là
    # cùng một đồng hồ mà `wait_for_timeout` của frame/page đẩy tới.
    return install_fake_clock(monkeypatch, grn_frames)


RMPO_XPATH = '//*[@id="0050_0020_0050"]/a'


def _rmpo_row(order_no="RMPO/2345", supplier="PSHK", status="Open"):
    return {"order_no": order_no, "supplier": supplier, "status": status}


def _search_result(*rows, ok=True, code="RMPO_SEARCHED"):
    return {
        "ok": ok,
        "code": code,
        "message": "ok",
        "rmpo_rows": list(rows),
    }


# --- xác định RMPO + Supplier -------------------------------------------


def _resolve(monkeypatch, outcome, rmpo_no="2345"):
    patch_automation(
        monkeypatch, grn_frames, "search_rmpo_list", lambda *_a, **_k: outcome
    )
    lines: list[str] = []
    return grn_frames._resolve_rmpo(RMPO_XPATH, rmpo_no, lines.append), lines


def test_a_partial_number_matching_exactly_one_row_gives_the_full_order_no(
    monkeypatch,
):
    (rmpo, supplier, error), lines = _resolve(
        monkeypatch,
        _search_result(_rmpo_row("RMPO/2345", "PSHK VIETNAM")),
    )

    assert (rmpo, supplier, error) == ("RMPO/2345", "PSHK VIETNAM", None)
    assert any("RMPO đầy đủ và Supplier" in line for line in lines)


def test_an_exact_order_no_wins_over_the_rows_that_merely_contain_it(
    monkeypatch,
):
    (rmpo, _supplier, error), _lines = _resolve(
        monkeypatch,
        _search_result(
            _rmpo_row("RMPO/23450", "A"),
            _rmpo_row("RMPO/2345", "B"),
        ),
        rmpo_no="RMPO/2345",
    )

    assert error is None
    assert rmpo == "RMPO/2345"


def test_a_partial_number_matching_several_rows_asks_for_more_characters(
    monkeypatch,
):
    (_rmpo, _supplier, error), _lines = _resolve(
        monkeypatch,
        _search_result(_rmpo_row("RMPO/2345"), _rmpo_row("RMPO/23456")),
    )

    assert error["code"] == "GRN_RMPO_AMBIGUOUS"
    assert "nhập thêm ký tự" in error["message"]


def test_a_number_that_matches_nothing_is_reported_as_not_found(monkeypatch):
    (_rmpo, _supplier, error), _lines = _resolve(
        monkeypatch, _search_result(_rmpo_row("RMPO/9999"))
    )

    assert error["code"] == "GRN_RMPO_NOT_FOUND"


def test_an_empty_rmpo_list_is_reported_as_not_found(monkeypatch):
    (_rmpo, _supplier, error), _lines = _resolve(
        monkeypatch, _search_result(ok=False, code="RMPO_NO_RESULTS")
    )

    assert error["code"] == "GRN_RMPO_NOT_FOUND"


def test_a_failing_rmpo_search_is_handed_back_untouched(monkeypatch):
    failure = {
        "ok": False,
        "code": "RMPO_LIST_NOT_OPEN",
        "message": "Chưa mở List.",
    }
    (_rmpo, _supplier, error), _lines = _resolve(monkeypatch, failure)

    assert error is failure


def test_a_row_without_a_supplier_stops_instead_of_guessing(monkeypatch):
    (_rmpo, _supplier, error), lines = _resolve(
        monkeypatch, _search_result(_rmpo_row(supplier="   "))
    )

    assert error["code"] == "GRN_RMPO_SUPPLIER_NOT_FOUND"
    assert "RMPO/2345" in error["message"]
    assert any("chưa đọc được Supplier" in line for line in lines)


def test_an_already_received_rmpo_never_reaches_sourcing_asn(monkeypatch):
    (_rmpo, _supplier, error), _lines = _resolve(
        monkeypatch, _search_result(_rmpo_row(status="Received"))
    )

    assert error["code"] == "GRN_ALREADY_RECEIVED"
    assert "đã nhập kho hết" in error["message"]


def test_a_part_received_rmpo_is_still_allowed_through(monkeypatch):
    (_rmpo, supplier, error), _lines = _resolve(
        monkeypatch, _search_result(_rmpo_row(status="Part Received"))
    )

    assert error is None
    assert supplier == "PSHK"


# --- tìm frame ----------------------------------------------------------


class ContextFrame:
    def __init__(self, selectors, clock, *, page=None, broken=False):
        self.selectors = set(selectors)
        self.clock = clock
        self.page = page
        self.broken = broken
        self.markers: dict[str, str] = {}

    def locator(self, selector):
        if self.broken:
            raise PlaywrightError("frame đã detach")
        return _Count(1 if selector in self.selectors else 0)

    def evaluate(self, script, arg=None):
        if self.broken:
            raise PlaywrightError("frame đã detach")
        name = "__wfxPanelDocumentMarker"
        if name in script:
            if "=" in script.split(name, 1)[1][:4]:
                self.markers[name] = str(arg)
                return None
            return self.markers.get(name, "")
        raise AssertionError(f"script lạ: {script[:60]}")

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


class _Count:
    def __init__(self, value):
        self._value = value

    def count(self):
        return self._value


class ContextPage:
    def __init__(self, *frames, clock=None):
        self.frames = list(frames)
        self.clock = clock
        self.fronted = 0
        for frame in self.frames:
            frame.page = self

    def bring_to_front(self):
        self.fronted += 1

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


class Context:
    def __init__(self, *pages):
        self.pages = list(pages)


def test_a_detached_frame_never_breaks_the_context_scan(clock):
    broken = ContextFrame((), clock, broken=True)
    good = ContextFrame(_GRN_CONTEXT, clock)
    context = Context(ContextPage(good, broken, clock=clock))

    assert grn_frames._find_context_frame(context, _GRN_CONTEXT) is good


def test_a_screen_that_never_appears_times_out_with_a_readable_message(clock):
    context = Context(ContextPage(ContextFrame((), clock), clock=clock))

    with pytest.raises(PlaywrightTimeoutError, match="đang thao tác"):
        grn_frames._find_context_frame(context, _GRN_CONTEXT, timeout_s=1)


def test_a_context_without_any_frame_still_stops_at_the_deadline(clock):
    context = Context(ContextPage(clock=clock))

    with pytest.raises(PlaywrightTimeoutError):
        grn_frames._find_context_frame(context, _GRN_CONTEXT, timeout_s=1)


def test_a_frame_that_was_already_open_does_not_count_as_newly_opened(clock):
    existing = ContextFrame(_GRN_CONTEXT, clock)
    context = Context(ContextPage(existing, clock=clock))
    page_ids, snapshots = grn_frames._snapshot_context(context, "grn-test")

    with pytest.raises(PlaywrightTimeoutError, match="sau khi click menu"):
        grn_frames._wait_new_context_frame(
            context, page_ids, snapshots, _GRN_CONTEXT, timeout_s=1
        )


def test_a_frame_that_reloaded_counts_as_the_new_screen(clock):
    frame = ContextFrame(_GRN_CONTEXT, clock)
    context = Context(ContextPage(frame, clock=clock))
    page_ids, snapshots = grn_frames._snapshot_context(context, "grn-test")
    frame.markers.clear()

    assert grn_frames._wait_new_context_frame(
        context, page_ids, snapshots, _GRN_CONTEXT, timeout_s=5
    ) is frame


def test_a_brand_new_popup_counts_as_the_new_screen(clock):
    old_page = ContextPage(ContextFrame((), clock), clock=clock)
    context = Context(old_page)
    page_ids, snapshots = grn_frames._snapshot_context(context, "grn-test")
    popup_frame = ContextFrame(("#sectionRMPOList",), clock)
    # Frame rỗng đứng sau nên được quét TRƯỚC (reversed): nó phải bị bỏ qua
    # thay vì được nhận nhầm là màn vừa mở.
    context.pages.append(
        ContextPage(popup_frame, ContextFrame((), clock), clock=clock)
    )

    assert grn_frames._wait_new_context_frame(
        context, page_ids, snapshots, ("#sectionRMPOList",), timeout_s=5
    ) is popup_frame


# --- mở form từ menu ----------------------------------------------------


class MenuTarget:
    def __init__(self):
        self.waits = 0
        self.clicks = 0

    def wait_for(self, **_kwargs):
        self.waits += 1

    def click(self, **_kwargs):
        self.clicks += 1


class MenuPage(ContextPage):
    def __init__(self, *frames, clock=None, target=None):
        super().__init__(*frames, clock=clock)
        self.target = target or MenuTarget()

    def locator(self, _selector):
        return self.target


def test_opening_a_form_clicks_the_menu_then_waits_for_the_new_screen(
    clock, monkeypatch
):
    opened = ContextFrame(_GRN_CONTEXT, clock)
    page = MenuPage(clock=clock)
    context = Context(page)
    patch_automation(
        monkeypatch, grn_frames, "_click", lambda target: target.click()
    )
    patch_automation(
        monkeypatch,
        grn_frames,
        "_wait_new_context_frame",
        lambda *_a, **_k: opened,
    )
    opened.page = page
    lines: list[str] = []

    assert grn_frames._open_menu_form(
        context, page, RMPO_XPATH, _GRN_CONTEXT, "GRN Pending", lines.append
    ) is opened
    assert page.target.clicks == 1
    assert page.fronted == 1
    assert any("Đang mở GRN Pending" in line for line in lines)


def test_a_popup_that_cannot_be_fronted_does_not_fail_the_flow(
    clock, monkeypatch
):
    page = MenuPage(clock=clock)
    context = Context(page)

    class Stubborn(ContextFrame):
        @property
        def page(self):
            class Dead:
                @staticmethod
                def bring_to_front():
                    raise PlaywrightError("target đã đóng")

            return Dead()

        @page.setter
        def page(self, _value):
            return None

    opened = Stubborn(_GRN_CONTEXT, clock)
    patch_automation(monkeypatch, grn_frames, "_click", lambda target: None)
    patch_automation(
        monkeypatch,
        grn_frames,
        "_wait_new_context_frame",
        lambda *_a, **_k: opened,
    )

    assert grn_frames._open_menu_form(
        context, page, RMPO_XPATH, _GRN_CONTEXT, "GRN Pending", print
    ) is opened


# --- chuẩn bị nhập kho --------------------------------------------------


def _wire_receipt(monkeypatch, clock, **overrides):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, receipt, world)
    defaults = {
        "_open_menu_form": lambda *_a, **_k: "frame",
        "_set_exact": lambda *_a, **_k: None,
        "_select_imported": lambda *_a, **_k: None,
        "_click_action": lambda *_a, **_k: None,
        "_wait_loading_finished": lambda *_a, **_k: None,
        "_find_context_frame": lambda *_a, **_k: "frame",
        "_snapshot_context": lambda *_a, **_k: (set(), {}),
        "_wait_new_context_frame": lambda *_a, **_k: "popup",
        "_select_po_row": lambda *_a, **_k: None,
        "_read_control_options": lambda *_a, **_k: ["HANOI", "HAIPHONG"],
        "_wait": lambda *_a, **_k: None,
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        patch_automation(monkeypatch, receipt, name, value)
    return world


@pytest.mark.parametrize(
    ("rmpo_no", "mode", "code"),
    [
        ("   ", "foreign", "GRN_RMPO_REQUIRED"),
        ("RMPO/1", "khong-ton-tai", "GRN_MODE_INVALID"),
        ("RMPO/1", "", "GRN_MODE_INVALID"),
    ],
)
def test_bad_input_never_opens_the_browser(
    monkeypatch, clock, rmpo_no, mode, code
):
    world = _wire_receipt(monkeypatch, clock)

    result = receipt.prepare_grn_receipt(RMPO_XPATH, rmpo_no, "PSHK", mode)

    assert result["code"] == code
    assert world.driver_starts == 0


def test_a_missing_supplier_is_looked_up_before_anything_is_opened(
    monkeypatch, clock
):
    _wire_receipt(monkeypatch, clock)
    patch_automation(
        monkeypatch,
        receipt,
        "_resolve_rmpo",
        lambda *_a, **_k: ("RMPO/2345", "PSHK VIETNAM", None),
    )

    result = receipt.prepare_grn_receipt(RMPO_XPATH, "2345", "", "domestic")

    assert result["code"] == "GRN_SITE_SELECTION_REQUIRED"
    assert result["rmpo_no"] == "RMPO/2345"
    assert result["supplier"] == "PSHK VIETNAM"


def test_an_rmpo_lookup_failure_stops_before_the_browser_is_opened(
    monkeypatch, clock
):
    world = _wire_receipt(monkeypatch, clock)
    patch_automation(
        monkeypatch,
        receipt,
        "_resolve_rmpo",
        lambda *_a, **_k: (
            None,
            None,
            {"ok": False, "code": "GRN_ALREADY_RECEIVED", "message": "Đã nhận."},
        ),
    )

    result = receipt.prepare_grn_receipt(RMPO_XPATH, "2345", "", "foreign")

    assert result["code"] == "GRN_ALREADY_RECEIVED"
    assert world.driver_starts == 0


def test_a_foreign_receipt_stops_at_the_sourcing_asn_checkpoint(
    monkeypatch, clock
):
    actions: list[str] = []
    _wire_receipt(
        monkeypatch,
        clock,
        _click_action=lambda _frame, _selector, label: actions.append(label),
        _read_control_options=lambda *_a, **_k: pytest.fail(
            "Luồng nước ngoài chưa được mở GRN Pending ở bước này"
        ),
    )
    lines: list[str] = []

    result = receipt.prepare_grn_receipt(
        RMPO_XPATH, "RMPO/2345", "PSHK", "foreign", lines.append
    )

    assert result["code"] == "GRN_SOURCING_ASN_READY"
    assert "Confirm trên WFX" in result["message"]
    assert actions == ["Add", "Add & Close"]
    assert any("Đã Add RMPO vào Sourcing ASN" in line for line in lines)


def test_a_domestic_receipt_goes_straight_to_choosing_a_site(
    monkeypatch, clock
):
    values: list[tuple[str, str]] = []
    _wire_receipt(
        monkeypatch,
        clock,
        _set_exact=lambda _frame, _selector, value, label, _log: values.append(
            (label, value)
        ),
    )

    result = receipt.prepare_grn_receipt(
        RMPO_XPATH, "RMPO/2345", "PSHK", "domestic"
    )

    assert result["code"] == "GRN_SITE_SELECTION_REQUIRED"
    assert result["sites"] == ["HANOI", "HAIPHONG"]
    assert values == [
        ("Receipt Type", "ASN from Supplier - Against PO"),
        ("From", "PSHK"),
    ]


def test_a_foreign_grn_uses_against_asn_and_ticks_imported(monkeypatch, clock):
    values: list[tuple[str, str]] = []
    imported: list[str] = []
    _wire_receipt(
        monkeypatch,
        clock,
        _set_exact=lambda _frame, _selector, value, label, _log: values.append(
            (label, value)
        ),
        _select_imported=lambda _frame, _log: imported.append("imported"),
    )

    result = receipt.continue_grn_receipt("PSHK")

    assert result["code"] == "GRN_SITE_SELECTION_REQUIRED"
    assert values[0] == ("Receipt Type", "ASN from Supplier - Against ASN")
    assert imported == ["imported"]


def test_a_grn_screen_without_any_site_is_reported_not_left_empty(
    monkeypatch, clock
):
    _wire_receipt(monkeypatch, clock, _read_control_options=lambda *_a, **_k: [])

    result = receipt.prepare_grn_receipt(
        RMPO_XPATH, "RMPO/2345", "PSHK", "domestic"
    )

    assert result["code"] == "GRN_PREPARE_FAILED"
    assert "danh sách Site" in result["message"]
    assert result["module"] == "(GRN) Nhập kho"


def test_an_unexpected_failure_while_preparing_names_its_type(
    monkeypatch, clock
):
    def explode(*_args, **_kwargs):
        raise ValueError("selector lạ")

    _wire_receipt(monkeypatch, clock, _open_menu_form=explode)
    lines: list[str] = []

    result = receipt.prepare_grn_receipt(
        RMPO_XPATH, "RMPO/2345", "PSHK", "domestic", lines.append
    )

    assert result["code"] == "GRN_PREPARE_FAILED"
    assert result["message"].startswith("ValueError: ")
    assert lines[-1] == result["message"]


@pytest.mark.parametrize(
    ("chrome_ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_the_browser_boundary_codes_survive_every_grn_step(
    monkeypatch, clock, chrome_ready, logged_in, expected
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(
        monkeypatch,
        receipt,
        world,
        chrome_ready=chrome_ready,
        logged_in=logged_in,
    )

    assert (
        receipt.prepare_grn_receipt(RMPO_XPATH, "RMPO/1", "PSHK", "domestic")[
            "code"
        ]
        == expected
    )
    assert receipt.continue_grn_receipt("PSHK")["code"] == expected
    assert receipt.finalize_grn_receipt("RMPO/1", "HANOI")["code"] == expected


# --- tiếp tục sau checkpoint --------------------------------------------


def test_continuing_without_a_supplier_says_the_session_expired(clock):
    assert (
        receipt.continue_grn_receipt("   ")["code"] == "GRN_SESSION_EXPIRED"
    )


def test_a_failure_while_continuing_has_its_own_code(monkeypatch, clock):
    def explode(*_args, **_kwargs):
        raise PlaywrightTimeoutError("GRN Pending chưa mở")

    _wire_receipt(monkeypatch, clock, _open_menu_form=explode)
    lines: list[str] = []

    result = receipt.continue_grn_receipt("PSHK", lines.append)

    assert result["code"] == "GRN_CONTINUE_FAILED"
    assert "GRN Pending chưa mở" in result["message"]


# --- chọn Site và mở New ------------------------------------------------


@pytest.mark.parametrize(
    ("rmpo_no", "site"), [("", "HANOI"), ("RMPO/1", ""), ("", "")]
)
def test_finalising_without_an_rmpo_or_a_site_is_refused(
    monkeypatch, clock, rmpo_no, site
):
    world = _wire_receipt(monkeypatch, clock)

    result = receipt.finalize_grn_receipt(rmpo_no, site)

    assert result["code"] == "GRN_SITE_REQUIRED"
    assert world.driver_starts == 0


def test_finalising_selects_the_site_then_the_exact_po_then_clicks_new(
    monkeypatch, clock
):
    steps: list[tuple[str, Any]] = []
    _wire_receipt(
        monkeypatch,
        clock,
        _set_exact=lambda _frame, _selector, value, label, _log: steps.append(
            (label, value)
        ),
        _select_po_row=lambda _frame, section, rmpo: steps.append(
            (section, rmpo)
        ),
        _click_action=lambda _frame, _selector, label: steps.append(
            ("click", label)
        ),
    )
    lines: list[str] = []

    result = receipt.finalize_grn_receipt("RMPO/2345", "HANOI", lines.append)

    assert result["code"] == "GRN_NEW_READY"
    assert steps == [
        ("Site", "HANOI"),
        ("#sectionOrderShipment", "RMPO/2345"),
        ("click", "New"),
    ]
    assert any("chọn đúng PO No. và click New" in line for line in lines)


def test_a_failure_while_finalising_has_its_own_code(monkeypatch, clock):
    def explode(*_args, **_kwargs):
        raise RuntimeError("Không thấy dòng PO")

    _wire_receipt(monkeypatch, clock, _select_po_row=explode)
    lines: list[str] = []

    result = receipt.finalize_grn_receipt("RMPO/2345", "HANOI", lines.append)

    assert result["code"] == "GRN_FINALIZE_FAILED"
    assert "Không thấy dòng PO" in result["message"]
    assert result["module"] == "(GRN) Nhập kho"


def test_the_sourcing_and_grn_context_selectors_stay_distinct():
    # Hai màn dùng chung nhiều id; nếu bộ selector trùng nhau thì automation sẽ
    # thao tác nhầm màn của bước kia.
    assert set(_SOURCING_CONTEXT) != set(_GRN_CONTEXT)
