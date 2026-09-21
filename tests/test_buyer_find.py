"""Buyer List: tìm Buyer rồi mở Edit của dòng đầu tiên khớp.

`wfx_panel/automation/directory/buyer.py` ở mức 24%. CLAUDE.md:

* "Buyer List: tự mở đúng Buyer List khi cần rồi mở Edit đầu tiên."
* "Search và Đổi FOC không được trả `*_LIST_NOT_OPEN` hay hướng dẫn bấm List."
* "Buyer/Supplier chỉ được resolve lại frame cùng PartyType với flow ban đầu."

Và luật chung của dự án: đã click không có nghĩa là đã mở — màn Edit phải được
WFX xác nhận bằng tab mới, document đổi, hoặc chính nút Edit biến mất.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.directory import buyer


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, buyer, _common)


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


def _row(text, *, edit=True, edit_visible=True, visible=True, search=False):
    children = []
    if search:
        children.append(element("input", id="txtCompanyName"))
    if edit:
        children.append(element("a", id="lnkEdit", visible=edit_visible))
    return Element("tr", text=text, visible=visible, children=children)


def _list_frame(clock, rows):
    return MiniFrame(
        Element("body", children=[Element("table", children=list(rows))]),
        clock=clock,
        url="https://wfx.test/buyerlist.aspx",
    )


# --- chọn dòng Edit -------------------------------------------------------


def test_the_first_matching_row_is_chosen(clock):
    frame = _list_frame(
        clock,
        [_row("PRO SPORTS"), _row("J.LINDEBERG HK"), _row("J.LINDEBERG SE")],
    )

    target = buyer._first_buyer_edit_target(frame, "j.lindeberg")

    assert target is not None
    assert target.name == "J.LINDEBERG HK"


def test_the_search_row_itself_is_never_treated_as_a_result(clock):
    """Hàng chứa `#txtCompanyName` là ô tìm, không phải một Buyer."""
    frame = _list_frame(
        clock,
        [_row("J.LINDEBERG", search=True), _row("J.LINDEBERG HK")],
    )

    assert buyer._first_buyer_edit_target(frame, "lindeberg").name == (
        "J.LINDEBERG HK"
    )


def test_a_hidden_row_is_skipped(clock):
    frame = _list_frame(
        clock, [_row("J.LINDEBERG HK", visible=False), _row("J.LINDEBERG SE")]
    )

    assert buyer._first_buyer_edit_target(frame, "lindeberg").name == (
        "J.LINDEBERG SE"
    )


def test_a_row_without_a_visible_edit_link_is_skipped(clock):
    frame = _list_frame(
        clock,
        [_row("J.LINDEBERG HK", edit_visible=False), _row("J.LINDEBERG SE")],
    )

    assert buyer._first_buyer_edit_target(frame, "lindeberg").name == (
        "J.LINDEBERG SE"
    )


def test_a_query_that_matches_nothing_yields_no_target(clock):
    frame = _list_frame(clock, [_row("PRO SPORTS")])

    assert buyer._first_buyer_edit_target(frame, "lindeberg") is None


def test_a_matching_row_with_no_edit_link_yields_no_target(clock):
    frame = _list_frame(clock, [_row("J.LINDEBERG HK", edit=False)])

    assert buyer._first_buyer_edit_target(frame, "lindeberg") is None


# --- xác nhận đã mở Edit --------------------------------------------------


def _edit_world(clock, *, rows=None):
    frame = _list_frame(clock, rows or [_row("J.LINDEBERG HK")])
    page = _Page(clock, [frame])
    context = _Context([page])
    target = buyer._first_buyer_edit_target(frame, "lindeberg")
    return context, page, frame, target


def test_a_new_tab_confirms_the_edit_screen(clock):
    context, page, frame, target = _edit_world(clock)
    target.control.node.on_click = lambda _n: context.pages.append(object())

    assert buyer._open_and_confirm_buyer_edit(
        context, page, frame, target, _quiet()
    )


def test_a_reloaded_document_confirms_the_edit_screen(clock, monkeypatch):
    context, page, frame, target = _edit_world(clock)
    monkeypatch.setattr(buyer, "_document_changed", lambda _f, _s: True)

    assert buyer._open_and_confirm_buyer_edit(
        context, page, frame, target, _quiet()
    )


def test_an_edit_link_that_disappeared_confirms_the_edit_screen(clock):
    context, page, frame, target = _edit_world(clock)
    target.control.node.on_click = lambda node: setattr(node, "visible", False)

    assert buyer._open_and_confirm_buyer_edit(
        context, page, frame, target, _quiet()
    )


def test_a_click_that_changes_nothing_is_never_reported_as_opened(clock):
    context, page, frame, target = _edit_world(clock)

    assert (
        buyer._open_and_confirm_buyer_edit(context, page, frame, target, _quiet())
        is False
    )
    assert target.control.node.clicks == 1


def test_the_buyer_name_is_logged_before_the_click(clock):
    context, page, frame, target = _edit_world(clock)
    target.control.node.on_click = lambda _n: context.pages.append(object())
    logs: list[str] = []

    buyer._open_and_confirm_buyer_edit(context, page, frame, target, logs.append)

    assert any("J.LINDEBERG HK" in line for line in logs)


# --- quyết định kết quả ---------------------------------------------------


def _request(clock, *, rows=None, state=None):
    frame = _list_frame(clock, rows or [_row("J.LINDEBERG HK")])
    page = _Page(clock, [frame])
    return buyer._BuyerSearchResultRequest(
        context=_Context([page]),
        page=page,
        frame=frame,
        query="lindeberg",
        state=state
        or {"rows": [{"company": "J.LINDEBERG HK", "matches": True}]},
        log=_quiet(),
    )


def test_no_matching_company_reports_buyer_not_found(clock):
    request = _request(
        clock, state={"rows": [{"company": "PRO SPORTS", "matches": False}]}
    )

    result = buyer._open_first_matching_buyer(request)

    assert result["code"] == "BUYER_NOT_FOUND"
    assert "lindeberg" in result["message"]


def test_a_match_without_an_edit_link_has_its_own_code(clock):
    request = _request(clock, rows=[_row("J.LINDEBERG HK", edit=False)])

    assert (
        buyer._open_first_matching_buyer(request)["code"]
        == "BUYER_EDIT_NOT_FOUND"
    )


def test_an_unconfirmed_edit_screen_has_its_own_code(clock):
    request = _request(clock)

    assert (
        buyer._open_first_matching_buyer(request)["code"]
        == "BUYER_EDIT_NOT_CONFIRMED"
    )


def test_a_confirmed_edit_returns_the_buyer_and_the_first_ten_matches(
    clock, monkeypatch
):
    monkeypatch.setattr(buyer, "_open_and_confirm_buyer_edit", lambda *a: True)
    state = {
        "rows": [
            {"company": f"J.LINDEBERG {index}", "matches": True}
            for index in range(15)
        ]
    }
    request = _request(clock, state=state)

    result = buyer._open_first_matching_buyer(request)

    assert result["code"] == "BUYER_EDIT_OPENED"
    assert result["buyer"] == "J.LINDEBERG 0"
    assert len(result["matches"]) == 10


# --- entry point ----------------------------------------------------------


def _wire(monkeypatch, clock, frame, *, chrome_ready=True, opens_after_menu=True):
    world = WfxWorld(clock)
    wire_automation(
        monkeypatch, buyer, world, chrome_ready=chrome_ready, clock=clock
    )
    page = _Page(clock, [frame]) if frame is not None else _Page(clock, [])
    browser = _Browser(_Context([page]))
    monkeypatch.setattr(
        buyer, "_active_wfx_page", lambda _playwright, _log: (browser, page)
    )
    monkeypatch.setattr(
        buyer,
        "_filter_company_rows",
        lambda _page, current, _query, _log, _kind: (
            current,
            {"rows": [{"company": "J.LINDEBERG HK", "matches": True}]},
        ),
    )
    monkeypatch.setattr(buyer, "_open_and_confirm_buyer_edit", lambda *a: True)
    return world


def test_a_search_without_a_query_is_refused(clock):
    assert buyer.find_and_open_buyer('//*[@id="x"]/a', "   ")["code"] == (
        "QUERY_REQUIRED"
    )


def test_an_open_buyer_list_is_used_as_is(clock, monkeypatch):
    frame = _list_frame(clock, [_row("J.LINDEBERG HK")])
    _wire(monkeypatch, clock, frame)
    monkeypatch.setattr(buyer, "_buyer_search_frame", lambda *a, **kw: frame)
    opened: list[int] = []
    monkeypatch.setattr(
        buyer, "_click_module_menu_on_page", lambda *a: opened.append(1)
    )

    result = buyer.find_and_open_buyer('//*[@id="x"]/a', "lindeberg", _quiet())

    assert result["code"] == "BUYER_EDIT_OPENED"
    assert opened == []


def test_a_closed_buyer_list_is_opened_by_the_app_itself(clock, monkeypatch):
    """CLAUDE.md: không bắt người dùng bấm List trước."""
    frame = _list_frame(clock, [_row("J.LINDEBERG HK")])
    _wire(monkeypatch, clock, frame)
    frames = [None, frame]
    monkeypatch.setattr(
        buyer,
        "_buyer_search_frame",
        lambda *a, **kw: frames.pop(0) if len(frames) > 1 else frames[0],
    )
    opened: list[int] = []
    monkeypatch.setattr(
        buyer, "_click_module_menu_on_page", lambda *a: opened.append(1)
    )
    logs: list[str] = []

    result = buyer.find_and_open_buyer('//*[@id="x"]/a', "lindeberg", logs.append)

    assert result["code"] == "BUYER_EDIT_OPENED"
    assert opened == [1]
    assert any("đang tự mở List" in line for line in logs)


def test_a_list_the_app_could_not_open_reports_a_technical_error(
    clock, monkeypatch
):
    _wire(monkeypatch, clock, None)
    monkeypatch.setattr(buyer, "_buyer_search_frame", lambda *a, **kw: None)
    monkeypatch.setattr(buyer, "_click_module_menu_on_page", lambda *a: None)

    result = buyer.find_and_open_buyer('//*[@id="x"]/a', "lindeberg", _quiet())

    assert result["code"] == "BUYER_SEARCH_NOT_READY"
    assert "LIST_NOT_OPEN" not in result["code"]


def test_an_unexpected_failure_keeps_its_own_code(clock, monkeypatch):
    frame = _list_frame(clock, [_row("J.LINDEBERG HK")])
    _wire(monkeypatch, clock, frame)
    monkeypatch.setattr(buyer, "_buyer_search_frame", lambda *a, **kw: frame)
    monkeypatch.setattr(
        buyer,
        "_filter_company_rows",
        lambda *a: (_ for _ in ()).throw(PlaywrightError("frame rơi")),
    )

    result = buyer.find_and_open_buyer('//*[@id="x"]/a', "lindeberg", _quiet())

    assert result["code"] == "BUYER_SEARCH_FAILED"
    assert "Error" in result["message"]


def test_a_closed_browser_is_mapped_by_the_shared_boundary(clock, monkeypatch):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, buyer, world, chrome_ready=False, clock=clock)

    assert (
        buyer.find_and_open_buyer('//*[@id="x"]/a', "lindeberg", _quiet())["code"]
        == "CHROME_CLOSED"
    )


def test_the_driver_is_always_released(clock, monkeypatch):
    frame = _list_frame(clock, [_row("J.LINDEBERG HK")])
    world = _wire(monkeypatch, clock, frame)
    monkeypatch.setattr(buyer, "_buyer_search_frame", lambda *a, **kw: frame)

    buyer.find_and_open_buyer('//*[@id="x"]/a', "lindeberg", _quiet())

    assert world.driver_starts == world.driver_stops == 1
