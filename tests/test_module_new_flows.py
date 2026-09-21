"""Ba lối vào màn New: Sale ASN, Sample và ba module click thẳng menu New.

`wfx_panel/automation/modules/creation.py` ở mức 44%. CLAUDE.md:

* "`New` chỉ được báo thành công khi thấy đúng trang đích đọc từ chính link menu
  (`.aspx` cuối cùng trong href hoặc `MenuName=`), hoặc khi đã đặt được dropdown
  mặc định của màn New. Một frame đổi document không đủ vì menu WFX cũng tự
  reload sau cú click."
* "QA Request, Advance Payment Request và Expense Invoice phải click trực tiếp
  menu `New` tương ứng, không yêu cầu mở List trước."
* "`Mở Sale ASN New trống`" phải xác nhận lại cả ASN Type và ASN Against.
"""

from __future__ import annotations

import pytest

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.modules import creation


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, creation, _common)


def _quiet():
    return lambda _line: None


class _Page:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


class _Context:
    def __init__(self, pages):
        self.pages = list(pages)


class _Browser:
    def __init__(self, context):
        self.contexts = [context]


def _frame(clock, url="https://wfx.test/x.aspx", children=()):
    return MiniFrame(Element("body", children=list(children)), url=url, clock=clock)


# --- Sale ASN New ---------------------------------------------------------


def _sale_asn_frame(clock, *, asn_type="1", against="BuyerOrderDispatch"):
    return _frame(
        clock,
        url="https://wfx.test/WFXSalesASN.aspx",
        children=[
            element("select", id="ddlASNType", value=asn_type),
            element("select", id="ddlASNAgainst", value=against),
        ],
    )


def _wire_sale_asn(monkeypatch, clock, frame, *, chrome_ready=True):
    world = WfxWorld(clock)
    wire_automation(
        monkeypatch, creation, world, chrome_ready=chrome_ready, clock=clock
    )
    page = _Page(clock, [frame])
    monkeypatch.setattr(
        creation, "_active_wfx_page", lambda _p, _log: (world.browser, page)
    )
    monkeypatch.setattr(creation, "_click_module_menu_on_page", lambda *a: None)
    monkeypatch.setattr(
        creation, "_wait_frame_with_selectors", lambda *a, **kw: frame
    )
    monkeypatch.setattr(creation, "_ensure_select_value", lambda *a: None)
    return world


def test_sale_asn_new_confirms_both_dropdowns(clock, monkeypatch):
    frame = _sale_asn_frame(clock)
    world = _wire_sale_asn(monkeypatch, clock, frame)

    result = creation.open_sale_asn_new('//*[@id="x"]/a', _quiet())

    assert result["code"] == "SALE_ASN_NEW_READY"
    assert result["asn_type"] == "1"
    assert result["asn_against"] == "BuyerOrderDispatch"
    assert world.driver_stops == 1


@pytest.mark.parametrize(
    ("asn_type", "against"),
    [("2", "BuyerOrderDispatch"), ("1", "Other"), ("", "")],
)
def test_sale_asn_new_refuses_a_form_wfx_did_not_set(
    clock, monkeypatch, asn_type, against
):
    frame = _sale_asn_frame(clock, asn_type=asn_type, against=against)
    _wire_sale_asn(monkeypatch, clock, frame)

    result = creation.open_sale_asn_new('//*[@id="x"]/a', _quiet())

    assert result["code"] == "SALE_ASN_NEW_NOT_READY"


def test_sale_asn_new_reports_an_unexpected_failure(clock, monkeypatch):
    frame = _sale_asn_frame(clock)
    _wire_sale_asn(monkeypatch, clock, frame)
    monkeypatch.setattr(
        creation,
        "_ensure_select_value",
        lambda *a: (_ for _ in ()).throw(ValueError("selector lạ")),
    )

    result = creation.open_sale_asn_new('//*[@id="x"]/a', _quiet())

    assert result["code"] == "SALE_ASN_NEW_FAILED"
    assert "ValueError" in result["message"]


def test_sale_asn_new_maps_a_closed_browser(clock, monkeypatch):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, creation, world, chrome_ready=False, clock=clock)

    assert creation.open_sale_asn_new('//*[@id="x"]/a', _quiet())["code"] == (
        "CHROME_CLOSED"
    )


# --- Sample New -----------------------------------------------------------


def _wire_sample(monkeypatch, clock, frames, *, chrome_ready=True):
    world = WfxWorld(clock)
    wire_automation(
        monkeypatch, creation, world, chrome_ready=chrome_ready, clock=clock
    )
    page = _Page(clock, list(frames))
    monkeypatch.setattr(
        creation, "_active_wfx_page", lambda _p, _log: (world.browser, page)
    )
    monkeypatch.setattr(creation, "_click_module_menu_on_page", lambda *a: None)
    return world, page


def test_sample_new_needs_the_exact_new_url(clock, monkeypatch):
    frame = _frame(clock, url="https://wfx.test/WFXSR.aspx?Action=New")
    _wire_sample(monkeypatch, clock, [frame])

    assert creation.open_sample_new('//*[@id="x"]/a', _quiet())["code"] == (
        "SAMPLE_NEW_READY"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://wfx.test/WFXSR.aspx?Action=Edit",
        "https://wfx.test/WFXSRList.aspx?Action=New",
    ],
)
def test_sample_new_refuses_a_url_that_is_not_the_new_screen(
    clock, monkeypatch, url
):
    frame = _frame(clock, url=url)
    _wire_sample(monkeypatch, clock, [frame])

    assert creation.open_sample_new('//*[@id="x"]/a', _quiet())["code"] == (
        "SAMPLE_NEW_NOT_READY"
    )


def test_sample_new_reports_an_unexpected_failure(clock, monkeypatch):
    _wire_sample(monkeypatch, clock, [])
    monkeypatch.setattr(
        creation,
        "_click_module_menu_on_page",
        lambda *a: (_ for _ in ()).throw(ValueError("xpath hỏng")),
    )

    result = creation.open_sample_new('//*[@id="x"]/a', _quiet())

    assert result["code"] == "SAMPLE_NEW_FAILED"


# --- chờ đúng trang New ---------------------------------------------------


def test_the_new_page_is_the_one_whose_frame_url_matches_a_marker(clock):
    other = _Page(clock, [_frame(clock, url="https://wfx.test/menu.aspx")])
    wanted = _Page(
        clock, [_frame(clock, url="https://wfx.test/WFXQAInspection.aspx?x=1")]
    )
    browser = _Browser(_Context([other, wanted]))

    assert (
        creation._wait_module_new_page(
            browser, other, ("wfxqainspection.aspx",), 5
        )
        is wanted
    )


def test_no_marker_means_no_page_is_ever_accepted(clock):
    page = _Page(clock, [_frame(clock)])
    browser = _Browser(_Context([page]))

    assert creation._wait_module_new_page(browser, page, (), 5) is None


def test_a_page_that_never_shows_the_marker_times_out(clock):
    page = _Page(clock, [_frame(clock, url="https://wfx.test/menu.aspx")])
    browser = _Browser(_Context([page]))

    assert (
        creation._wait_module_new_page(browser, page, ("wfxqa.aspx",), 1) is None
    )


def test_a_browser_that_lost_its_context_falls_back_to_the_known_page(clock):
    frame = _frame(clock, url="https://wfx.test/WFXQAInspection.aspx")
    page = _Page(clock, [frame])

    class Broken:
        contexts: list = []

    assert (
        creation._wait_module_new_page(
            Broken(), page, ("wfxqainspection.aspx",), 5
        )
        is page
    )


# --- New trực tiếp từ menu ------------------------------------------------


QA = "0063_0030_0020"
ADVANCE = "0065_0880_0010_0020"
EXPENSE = "0065_0880_0030_0020"


def test_a_module_without_a_direct_new_is_refused(clock):
    assert creation.open_module_new("khong-co")["code"] == "INVALID_FILTER"


def _wire_new(
    monkeypatch,
    clock,
    *,
    markers=("wfxqainspection.aspx",),
    new_page=True,
    frame_changed=True,
    chrome_ready=True,
):
    world = WfxWorld(clock)
    wire_automation(
        monkeypatch, creation, world, chrome_ready=chrome_ready, clock=clock
    )
    menu_frame = _frame(clock, url="https://wfx.test/menu.aspx")
    page = _Page(clock, [menu_frame])
    browser = _Browser(_Context([page]))
    monkeypatch.setattr(
        creation, "_active_wfx_page", lambda _p, _log: (browser, page)
    )
    monkeypatch.setattr(creation, "_mark_document", lambda frame, _tag: (frame, "m"))
    monkeypatch.setattr(
        creation, "_document_changed", lambda _f, _s: frame_changed
    )
    monkeypatch.setattr(creation, "_menu_target_markers", lambda *a: markers)
    monkeypatch.setattr(creation, "_click_module_menu_on_page", lambda *a: None)
    monkeypatch.setattr(
        creation,
        "_wait_module_new_page",
        lambda *a: page if new_page else None,
    )
    selections: list[tuple] = []
    monkeypatch.setattr(
        creation,
        "_ensure_select_value",
        lambda _page, selector, value, label, _log: selections.append(
            (selector, value)
        ),
    )
    return world, page, selections


def test_qa_request_new_is_confirmed_by_its_target_page(clock, monkeypatch):
    _world, _page, selections = _wire_new(monkeypatch, clock)

    result = creation.open_module_new(QA, _quiet())

    assert result["code"] == "MODULE_NEW_READY"
    assert result["module"] == "QA Request"
    assert selections == []


@pytest.mark.parametrize(
    ("module_id", "selector", "value", "label"),
    [
        (ADVANCE, "#ddlRequestType", "RMPO", "Against RMPO"),
        (EXPENSE, "#ddlInvoiceType", "GeneralExpense", "General Expense"),
    ],
)
def test_a_module_with_a_default_dropdown_sets_it(
    clock, monkeypatch, module_id, selector, value, label
):
    _world, _page, selections = _wire_new(monkeypatch, clock)

    result = creation.open_module_new(module_id, _quiet())

    assert result["code"] == "MODULE_NEW_READY"
    assert selections == [(selector, value)]
    assert label in result["message"]


def test_a_default_dropdown_is_evidence_even_without_the_target_page(
    clock, monkeypatch
):
    """Đặt được dropdown của màn New cũng là bằng chứng độc lập."""
    _world, _page, _selections = _wire_new(monkeypatch, clock, new_page=False)

    assert creation.open_module_new(ADVANCE, _quiet())["code"] == (
        "MODULE_NEW_READY"
    )


def test_a_module_without_a_dropdown_needs_its_target_page(clock, monkeypatch):
    """CLAUDE.md: một frame đổi document không đủ để báo thành công."""
    _world, _page, _selections = _wire_new(monkeypatch, clock, new_page=False)

    result = creation.open_module_new(QA, _quiet())

    assert result["code"] == "MODULE_FAILED"
    assert "wfxqainspection.aspx" in result["message"]


def test_an_unreadable_menu_target_is_reported_in_the_message(
    clock, monkeypatch
):
    _world, _page, _selections = _wire_new(
        monkeypatch, clock, markers=(), new_page=False
    )

    result = creation.open_module_new(QA, _quiet())

    assert result["code"] == "MODULE_FAILED"
    assert "không đọc được trang đích" in result["message"]


def test_a_click_wfx_never_answered_is_reported(clock, monkeypatch):
    _world, _page, _selections = _wire_new(
        monkeypatch, clock, frame_changed=False
    )

    result = creation.open_module_new(QA, _quiet())

    assert result["code"] == "MODULE_FAILED"
    assert "chưa xác nhận màn New" in result["message"]


def test_a_new_tab_counts_as_navigation(clock, monkeypatch):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, creation, world, clock=clock)
    page = _Page(clock, [_frame(clock, url="https://wfx.test/menu.aspx")])
    context = _Context([page])
    browser = _Browser(context)
    monkeypatch.setattr(
        creation, "_active_wfx_page", lambda _p, _log: (browser, page)
    )
    monkeypatch.setattr(creation, "_mark_document", lambda frame, _tag: (frame, "m"))
    monkeypatch.setattr(creation, "_document_changed", lambda _f, _s: False)
    monkeypatch.setattr(
        creation, "_menu_target_markers", lambda *a: ("wfxqainspection.aspx",)
    )
    opened = _Page(
        clock, [_frame(clock, url="https://wfx.test/WFXQAInspection.aspx")]
    )
    monkeypatch.setattr(
        creation,
        "_click_module_menu_on_page",
        lambda *a: context.pages.append(opened),
    )
    monkeypatch.setattr(creation, "_wait_module_new_page", lambda *a: opened)

    assert creation.open_module_new(QA, _quiet())["code"] == "MODULE_NEW_READY"


def test_an_unexpected_failure_keeps_the_module_name(clock, monkeypatch):
    _world, _page, _selections = _wire_new(monkeypatch, clock)
    monkeypatch.setattr(
        creation,
        "_click_module_menu_on_page",
        lambda *a: (_ for _ in ()).throw(ValueError("xpath hỏng")),
    )

    result = creation.open_module_new(QA, _quiet())

    assert result["code"] == "MODULE_FAILED"
    assert result["module"] == "QA Request"
    assert "ValueError" in result["message"]


def test_a_closed_browser_is_mapped_by_the_shared_boundary(clock, monkeypatch):
    _wire_new(monkeypatch, clock, chrome_ready=False)
    world = WfxWorld(clock)
    wire_automation(monkeypatch, creation, world, chrome_ready=False, clock=clock)

    assert creation.open_module_new(QA, _quiet())["code"] == "CHROME_CLOSED"
