"""Mở form Sale ASN New, đặt giá trị control và quét Buyer.

CLAUDE.md đặt hai ràng buộc ngay ở đây: form `WFXSalesASN.aspx` đang mở phải
được reload trước mỗi lượt để không dùng datasource PO cũ, và `scan_sale_asn_buyers`
là thao tác nặng chỉ chạy khi người dùng tự bấm.
"""

from __future__ import annotations

from typing import Any

import pytest

import wfx_panel.automation.sale_asn_create.buyers as buyers_module
import wfx_panel.automation.sale_asn_create.form as form
from tests.fakes.automation_boundary import FakePage, WfxWorld, wire_automation
from tests.fakes.mini_dom import Element, MiniFrame
from tests.fakes.module_reflection import patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError


class FormFrame(MiniFrame):
    """Frame form Sale ASN: thêm `goto` và hàng đợi kết quả `_SET_CONTROL_JS`."""

    def __init__(self, *args, goto_error=None, results=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.goto_error = goto_error
        self.goto_calls: list[str] = []
        self.results = list(results or [])
        self.specs: list[dict[str, Any]] = []

    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)
        if self.goto_error is not None:
            raise self.goto_error

    def evaluate(self, script, arg=None):
        if script == form._SET_CONTROL_JS:
            self.specs.append(dict(arg))
            outcome = (
                self.results.pop(0)
                if len(self.results) > 1
                else (self.results[0] if self.results else {"ok": False})
            )
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return super().evaluate(script, arg)


class Pages:
    def __init__(self, *pages):
        self.pages = list(pages)


class HostPage:
    """Page tối giản: chỉ cần `.context` và `.frames` cho `_frame_with_selector`."""

    def __init__(self, *frames, clock=None):
        self.frames = list(frames)
        self.clock = clock
        self.context = Pages(self)

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


class BrokenFrame:
    url = "https://wfx.test/detached"

    def locator(self, _selector):
        raise PlaywrightError("frame đã detach")


def _buyer_cell(*, visible=True) -> Element:
    return Element(
        "body",
        children=[Element("td", id="Cell_Buyer", visible=visible)],
    )


def _form_frame(clock=None, *, url="https://wfx.test/WFXSalesASN.aspx", **kwargs):
    return FormFrame(_buyer_cell(), url=url, clock=clock, **kwargs)


# --- tìm frame form -----------------------------------------------------


def test_the_form_frame_is_searched_from_the_newest_page_backwards(monkeypatch):
    clock = install_fake_clock(monkeypatch, form)
    stale = _form_frame(clock)
    fresh = _form_frame(clock)
    page = HostPage(BrokenFrame(), stale, fresh, clock=clock)

    found_page, found_frame = form._frame_with_selector(
        page.context, "#Cell_Buyer"
    )

    assert (found_page, found_frame) == (page, fresh)


def test_a_cell_that_is_present_but_hidden_does_not_count_as_the_form(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, form)
    hidden = FormFrame(_buyer_cell(visible=False), clock=clock)
    # BrokenFrame đứng cùng page: frame đã detach không được làm hỏng vòng quét.
    page = HostPage(BrokenFrame(), hidden, clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="#Cell_Buyer"):
        form._frame_with_selector(page.context, "#Cell_Buyer", timeout_s=1)


def test_a_context_without_any_page_stops_instead_of_spinning():
    # Không gắn FakeClock: nhánh này không có `_wait` nào để đẩy đồng hồ ảo,
    # nó dựa hẳn vào `time.monotonic()` thật để thoát.
    with pytest.raises(PlaywrightTimeoutError):
        form._frame_with_selector(Pages(), "#Cell_Buyer", timeout_s=0.05)


# --- mở form từ menu ----------------------------------------------------


def test_opening_the_form_sets_both_asn_dropdowns_before_reading_the_buyer(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(clock)
    page = HostPage(frame, clock=clock)
    menu: list[tuple[str, str]] = []
    selects: list[tuple[str, str]] = []
    patch_automation(
        monkeypatch,
        form,
        "_click_module_menu_on_page",
        lambda _page, label, xpath, _log: menu.append((label, xpath)),
    )
    patch_automation(
        monkeypatch,
        form,
        "_ensure_select_value",
        lambda _page, selector, value, _label, _log: selects.append(
            (selector, value)
        ),
    )

    assert form._open_new_form(page, '//*[@id="0005"]/a', print) is frame
    assert menu == [("Sale ASN > New", '//*[@id="0005"]/a')]
    assert selects == [
        ("#ddlASNType", "1"),
        ("#ddlASNAgainst", "BuyerOrderDispatch"),
    ]


# --- refresh form đang mở -----------------------------------------------


def test_nothing_to_refresh_when_no_sale_asn_form_is_open(monkeypatch):
    clock = install_fake_clock(monkeypatch, form)
    page = HostPage(clock=clock)

    assert form._refresh_existing_new_form(page, print) is None


def test_a_buyer_cell_from_another_wfx_screen_is_not_the_sale_asn_form(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, form)
    # `#Cell_Buyer` cũng có trên các màn khác của WFX; chỉ URL mới phân biệt
    # được, nếu không app sẽ reload nhầm màn người dùng đang làm.
    other = _form_frame(clock, url="https://wfx.test/WFXBuyerMaster.aspx")
    page = HostPage(other, clock=clock)

    assert form._refresh_existing_new_form(page, print) is None
    assert other.goto_calls == []


def test_refreshing_reloads_the_same_url_and_resets_the_asn_dropdowns(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(clock)
    page = HostPage(frame, clock=clock)
    selects: list[tuple[str, str]] = []
    patch_automation(
        monkeypatch,
        form,
        "_ensure_select_value",
        lambda _page, selector, value, _label, _log: selects.append(
            (selector, value)
        ),
    )
    lines: list[str] = []

    assert form._refresh_existing_new_form(page, lines.append) is frame
    assert frame.goto_calls == ["https://wfx.test/WFXSalesASN.aspx"]
    assert [selector for selector, _value in selects] == [
        "#ddlASNType",
        "#ddlASNAgainst",
    ]
    assert lines == [
        "[SALE ASN] Đã refresh form New đang mở trước khi chọn Buyer."
    ]


def test_a_form_that_cannot_be_reloaded_falls_back_to_opening_it_from_the_menu(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(clock, goto_error=PlaywrightError("navigation bị hủy"))
    page = HostPage(frame, clock=clock)
    lines: list[str] = []

    assert form._refresh_existing_new_form(page, lines.append) is None
    assert lines == [
        "[SALE ASN] Không refresh được form New đang mở; sẽ mở lại từ menu."
    ]


def test_a_reload_that_never_brings_the_buyer_cell_back_is_also_a_fallback(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(clock)
    page = HostPage(frame, clock=clock)

    def vanish(_page, selector, _value, _label, _log):
        # WFX trả về màn trắng sau reload: cell biến mất khỏi DOM.
        frame.root.children.clear()

    patch_automation(monkeypatch, form, "_ensure_select_value", vanish)
    lines: list[str] = []

    assert form._refresh_existing_new_form(page, lines.append) is None
    assert lines == [
        "[SALE ASN] Không refresh được form New đang mở; sẽ mở lại từ menu."
    ]


# --- đặt giá trị control ------------------------------------------------


def test_setting_a_control_returns_as_soon_as_wfx_confirms_the_value(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(clock, results=[{"ok": True, "value": "J.LINDEBERG"}])

    outcome = form._set_control(frame, "#Cell_Buyer", "J.LINDEBERG", "exact")

    assert outcome == {"ok": True, "value": "J.LINDEBERG"}
    assert frame.specs == [
        {"selector": "#Cell_Buyer", "value": "J.LINDEBERG", "mode": "exact"}
    ]


def test_a_control_that_never_accepts_the_value_reports_the_last_reason(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(clock, results=[{"ok": False, "reason": "host-not-found"}])

    outcome = form._set_control(
        frame, "#Cell_Buyer", "J.LINDEBERG", "exact", timeout_s=1
    )

    assert outcome == {"ok": False, "reason": "host-not-found"}
    assert len(frame.specs) > 1


def test_a_document_swap_mid_write_is_retried_not_reported_as_a_crash(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(
        clock,
        results=[
            PlaywrightError("Execution context was destroyed"),
            {"ok": True, "value": "SEA"},
        ],
    )

    outcome = form._set_control(frame, "#ddlShipmentMode", "SEA", "exact")

    assert outcome == {"ok": True, "value": "SEA"}


def test_a_document_that_never_settles_reports_the_document_change(monkeypatch):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(
        clock, results=[PlaywrightError("Execution context was destroyed")]
    )

    outcome = form._set_control(
        frame, "#ddlShipmentMode", "SEA", "exact", timeout_s=1
    )

    assert outcome == {"ok": False, "reason": "document-changed"}


def test_a_closest_match_reads_the_options_then_picks_one_exactly(monkeypatch):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(
        clock,
        results=[
            {
                "ok": False,
                "reason": "option-not-found",
                "options": [
                    "BILL-ADD - PSHK",
                    "SHIP-TO - J.LINDEBERG AB",
                    "SHIP-TO - J.LINDEBERG US",
                ],
            },
            {"ok": True, "value": "SHIP-TO - J.LINDEBERG AB"},
        ],
    )

    outcome = form._set_control(
        frame, "#Cell_ShipTo", "J.LINDEBERG AB", "closest"
    )

    assert outcome["ok"] is True
    # Lượt đầu chỉ đọc option, lượt sau mới ghi đúng nhãn WFX đang có.
    assert [spec["mode"] for spec in frame.specs] == ["options", "exact"]
    assert frame.specs[1]["value"] == "SHIP-TO - J.LINDEBERG AB"


def test_a_factory_match_ignores_options_that_end_with_a_dot(monkeypatch):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(
        clock,
        results=[
            {
                "ok": False,
                "reason": "option-not-found",
                "options": ["PSHK VIETNAM CO., LTD.", "PSHK VIETNAM"],
            },
            {"ok": True, "value": "PSHK VIETNAM"},
        ],
    )

    outcome = form._set_control(
        frame, "#Cell_Factory", "pshk vietnam", "factory_first"
    )

    assert outcome["ok"] is True
    assert frame.specs[1]["value"] == "PSHK VIETNAM"


def test_a_closest_match_with_no_usable_option_keeps_asking_for_the_list(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, form)
    frame = _form_frame(
        clock,
        results=[
            {"ok": False, "reason": "option-not-found", "options": ["HÀ NỘI"]}
        ],
    )

    outcome = form._set_control(
        frame, "#Cell_ShipTo", "KHÔNG CÓ", "closest", timeout_s=1
    )

    assert outcome["reason"] == "option-not-found"
    assert {spec["mode"] for spec in frame.specs} == {"options"}


# --- quét Buyer ---------------------------------------------------------


class BuyerCell:
    def __init__(self, batches, *, select2_error=None, native_error=None):
        self.batches = list(batches)
        self.select2_error = select2_error
        self.native_error = native_error
        self.waited = False
        self.clicks: list[str] = []

    @property
    def first(self):
        return self

    def wait_for(self, **_kwargs):
        self.waited = True

    def evaluate(self, _script, _arg=None):
        if len(self.batches) > 1:
            return self.batches.pop(0)
        return self.batches[0] if self.batches else []

    def locator(self, selector):
        self._selector = selector
        return self

    def click(self, **_kwargs):
        self.clicks.append(self._selector)
        if ".select2-selection" in self._selector and self.select2_error:
            raise self.select2_error
        if "ddlBuyer" in self._selector and self.native_error:
            raise self.native_error


class BuyerFrame:
    url = "https://wfx.test/WFXSalesASN.aspx"

    def __init__(self, cell, clock):
        self.cell = cell
        self.clock = clock

    def locator(self, selector):
        assert selector == "#Cell_Buyer"
        return self.cell

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


def _raw(*labels):
    return [{"label": label, "value": label.lower()} for label in labels]


def test_buyer_options_drop_placeholders_and_duplicate_names():
    options = buyers_module._normalise_buyer_options(
        [
            {"label": "  J.LINDEBERG  ", "value": "1"},
            {"label": "j.lindeberg", "value": "2"},
            {"label": "", "value": "3"},
            {"label": "TRUEWERK", "value": ""},
            {"label": "TRUEWERK", "value": "4"},
        ]
    )

    assert options == [
        {"label": "J.LINDEBERG", "value": "1"},
        {"label": "TRUEWERK", "value": "4"},
    ]


def test_buyer_options_handle_wfx_returning_nothing_at_all():
    assert buyers_module._normalise_buyer_options(None) == []


def test_reading_buyers_waits_for_the_cell_before_touching_the_dropdown(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, buyers_module)
    cell = BuyerCell([_raw("J.LINDEBERG")])
    frame = BuyerFrame(cell, clock)

    assert buyers_module._buyer_options(frame) == [
        {"label": "J.LINDEBERG", "value": "j.lindeberg"}
    ]
    assert cell.waited is True
    # Danh sách bind ngay nên không được mở dropdown một cách thừa thãi.
    assert cell.clicks == []


def test_a_lazy_dropdown_is_opened_once_to_trigger_the_bind(monkeypatch):
    clock = install_fake_clock(monkeypatch, buyers_module)
    cell = BuyerCell([[]] * 6 + [_raw("TRUEWERK")])
    frame = BuyerFrame(cell, clock)

    assert buyers_module._buyer_options(frame) == [
        {"label": "TRUEWERK", "value": "truewerk"}
    ]
    assert cell.clicks == [".select2-selection"]


def test_a_dropdown_without_select2_falls_back_to_the_native_select(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, buyers_module)
    cell = BuyerCell(
        [[]] * 6 + [_raw("TRUEWERK")],
        select2_error=PlaywrightError("select2 không tồn tại"),
    )

    assert buyers_module._buyer_options(BuyerFrame(cell, clock))
    assert cell.clicks == [".select2-selection", "select#ddlBuyer, select"]


def test_a_dropdown_that_cannot_be_opened_at_all_returns_an_empty_list(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, buyers_module)
    cell = BuyerCell(
        [[]],
        select2_error=PlaywrightError("select2 không tồn tại"),
        native_error=PlaywrightError("select bị che"),
    )

    assert buyers_module._buyer_options(BuyerFrame(cell, clock), timeout_s=3) == []


def test_selecting_a_buyer_needs_exactly_one_case_insensitive_match(monkeypatch):
    clock = install_fake_clock(monkeypatch, buyers_module)
    cell = BuyerCell([_raw("J.LINDEBERG", "TRUEWERK")])
    frame = BuyerFrame(cell, clock)
    written: list[tuple] = []
    patch_automation(
        monkeypatch,
        buyers_module,
        "_set_control",
        lambda _frame, selector, value, mode: (
            written.append((selector, value, mode)) or {"ok": True}
        ),
    )

    buyers_module._select_buyer(frame, "j.lindeberg")

    assert written == [("#Cell_Buyer", "J.LINDEBERG", "exact")]


def test_a_buyer_missing_from_wfx_stops_before_any_write(monkeypatch):
    clock = install_fake_clock(monkeypatch, buyers_module)
    frame = BuyerFrame(BuyerCell([_raw("TRUEWERK")]), clock)
    patch_automation(
        monkeypatch,
        buyers_module,
        "_set_control",
        lambda *_a, **_k: pytest.fail("Buyer chưa khớp thì không được ghi"),
    )

    with pytest.raises(RuntimeError, match="SALE_ASN_BUYER_NOT_FOUND"):
        buyers_module._select_buyer(frame, "J.LINDEBERG")


def test_a_buyer_that_wfx_refuses_to_keep_is_reported_with_its_reason(
    monkeypatch,
):
    clock = install_fake_clock(monkeypatch, buyers_module)
    frame = BuyerFrame(BuyerCell([_raw("J.LINDEBERG")]), clock)
    patch_automation(
        monkeypatch,
        buyers_module,
        "_set_control",
        lambda *_a, **_k: {"ok": False, "reason": "editor-not-found"},
    )

    with pytest.raises(
        RuntimeError, match="SALE_ASN_BUYER_NOT_CONFIRMED:editor-not-found"
    ):
        buyers_module._select_buyer(frame, "J.LINDEBERG")


# --- entry point quét Buyer ---------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, buyers_module)


def _wire_scan(monkeypatch, clock, *, refreshed, options):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, buyers_module, world)
    patch_automation(
        monkeypatch,
        buyers_module,
        "_refresh_existing_new_form",
        lambda *_a, **_k: refreshed,
    )
    patch_automation(
        monkeypatch,
        buyers_module,
        "_open_new_form",
        lambda *_a, **_k: "menu-frame",
    )
    patch_automation(
        monkeypatch, buyers_module, "_buyer_options", lambda *_a, **_k: options
    )
    return world


def test_scanning_reuses_the_open_form_instead_of_clicking_the_menu_again(
    monkeypatch, clock
):
    world = _wire_scan(
        monkeypatch,
        clock,
        refreshed="open-frame",
        options=[{"label": "J.LINDEBERG", "value": "1"}],
    )
    patch_automation(
        monkeypatch,
        buyers_module,
        "_open_new_form",
        lambda *_a, **_k: pytest.fail("Form đang mở thì không mở lại từ menu"),
    )

    result = buyers_module.scan_sale_asn_buyers('//*[@id="0005"]/a', print)

    assert result["code"] == "SALE_ASN_BUYERS_SCANNED"
    assert result["buyers"] == [{"label": "J.LINDEBERG", "value": "1"}]
    assert "1 Buyer" in result["message"]
    assert world.driver_stops == 1


def test_scanning_opens_the_form_from_the_menu_when_none_is_open(
    monkeypatch, clock
):
    _wire_scan(
        monkeypatch,
        clock,
        refreshed=None,
        options=[{"label": "TRUEWERK", "value": "2"}],
    )

    result = buyers_module.scan_sale_asn_buyers('//*[@id="0005"]/a', print)

    assert result["ok"] is True
    assert result["buyers"][0]["label"] == "TRUEWERK"


def test_a_dropdown_that_never_binds_is_a_scan_failure_not_an_empty_list(
    monkeypatch, clock
):
    _wire_scan(monkeypatch, clock, refreshed="open-frame", options=[])
    lines: list[str] = []

    result = buyers_module.scan_sale_asn_buyers('//*[@id="0005"]/a', lines.append)

    assert result["code"] == "SALE_ASN_BUYER_SCAN_FAILED"
    assert "chưa bind dữ liệu" in result["message"]
    assert lines[-1] == result["message"]


@pytest.mark.parametrize(
    ("chrome_ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_the_browser_boundary_codes_pass_through_untouched(
    monkeypatch, clock, chrome_ready, logged_in, expected
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(
        monkeypatch,
        buyers_module,
        world,
        chrome_ready=chrome_ready,
        logged_in=logged_in,
    )

    result = buyers_module.scan_sale_asn_buyers('//*[@id="0005"]/a', print)

    assert result["code"] == expected
    assert world.driver_stops == 1


def test_an_unexpected_runtime_error_is_reported_as_a_session_problem(
    monkeypatch, clock
):
    world = WfxWorld(clock, [FakePage(clock)])
    wire_automation(monkeypatch, buyers_module, world)

    def explode(*_args, **_kwargs):
        raise RuntimeError("DIVISION_LOCKED")

    patch_automation(
        monkeypatch, buyers_module, "_refresh_existing_new_form", explode
    )
    lines: list[str] = []

    result = buyers_module.scan_sale_asn_buyers('//*[@id="0005"]/a', lines.append)

    assert result["code"] == "SALE_ASN_BUYER_SCAN_FAILED"
    assert "DIVISION_LOCKED" in result["message"]
    assert world.driver_stops == 1
