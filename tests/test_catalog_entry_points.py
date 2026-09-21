"""Vỏ 10 entry point Catalog: mã lỗi, thứ tự phục hồi và giải phóng driver.

`wfx_panel/automation/catalog/flows.py` ở mức 22%: phần state machine bên trong
(`navigation`, `grid`, `filters`) đã được `test_catalog_state_machine.py` phủ
kỹ, nhưng chính lớp vỏ — nơi sinh `CHROME_CLOSED`, `NOT_LOGGED_IN`,
`CATALOG_SEARCH_CONTEXT_LOST`, `APPAREL_ONLY`, `CATALOG_FOLDER_INVALID`… và
nơi quyết định có recycle CDP hay không — thì chưa từng chạy.

Ràng buộc CLAUDE.md được kiểm ở đây:

* "Tại ranh giới popup Article, KHÔNG dựng lại driver/CDP vô điều kiện… chỉ khi
  probe ngắn timeout mới `recycle_playwright` đúng một lần rồi thử lại."
* "nếu người dùng vừa chọn một dòng sau `MULTIPLE_RESULTS` và WFX tái sử dụng
  popup Style, phải recover popup rồi mở destination, không quay lại Catalog để
  search lần hai."
* "Costsheet và BOM chỉ hỗ trợ Category Apparel."
* "Tối đa một Playwright driver/CDP connection… runtime nhả driver/CDP ngay khi
  flow xong" — mọi entry point phải `playwright.stop()` trong `finally`.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import (
    FakeFrame,
    FakePage,
    WfxWorld,
    wire_automation,
)
from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import FakeNode, install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.catalog import flows


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, flows, _common)


def _quiet():
    return lambda _line: None


def _world(clock, *, frames=()) -> WfxWorld:
    page = FakePage(clock, frames=list(frames))
    return WfxWorld(clock, [page])


def _grid_frame(clock) -> FakeFrame:
    return FakeFrame(clock, url="https://wfx.test/wfxcataloglist.aspx", name="body")


def _stub(monkeypatch, name, value):
    monkeypatch.setattr(flows, name, value)


def _opened(**extra):
    return {
        "ok": True,
        "code": "RESULT_OPENED",
        "message": "ok",
        "article_code": "ABC123",
        **extra,
    }


# --- find_in_open_catalog -------------------------------------------------


def test_find_requires_a_query(clock):
    result = flows.find_in_open_catalog("Apparel", "code", "   ", _quiet())

    assert result["code"] == "QUERY_REQUIRED"
    assert result["ok"] is False


def test_find_reports_a_closed_browser_before_starting_playwright(
    clock, monkeypatch
):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, chrome_ready=False, clock=clock)

    result = flows.find_in_open_catalog("Apparel", "code", "ABC", _quiet())

    assert result["code"] == "CHROME_CLOSED"
    assert world.driver_starts == 0


def test_find_reports_an_expired_session(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, logged_in=False, clock=clock)

    result = flows.find_in_open_catalog("Apparel", "code", "ABC", _quiet())

    assert result["code"] == "NOT_LOGGED_IN"
    assert world.driver_starts == world.driver_stops == 1


def test_find_returns_the_filter_result_with_request_context(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    grid = _grid_frame(clock)
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: grid)
    _stub(
        monkeypatch,
        "_filter_grid_and_maybe_open",
        lambda *a, **kw: {"ok": True, "code": "NO_RESULTS", "message": "trống"},
    )

    result = flows.find_in_open_catalog("Trims", "code", "  ABC  ", _quiet())

    assert result["code"] == "NO_RESULTS"
    assert result["session_active"] is True
    assert result["category"] == "Trims"
    assert result["filter_kind"] == "code"
    assert result["query"] == "ABC"
    assert world.driver_stops == 1


def test_find_maps_a_lost_master_to_a_recoverable_code(clock, monkeypatch):
    """Controller dựa vào mã này để tự mở lại Catalog, nên nó phải riêng."""
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)

    def lost(*_args, **_kwargs):
        raise PlaywrightTimeoutError("grid Master đã biến mất")

    _stub(monkeypatch, "_show_catalog_floating_filter", lost)

    result = flows.find_in_open_catalog("Apparel", "code", "ABC", _quiet())

    assert result["code"] == "CATALOG_SEARCH_CONTEXT_LOST"
    assert world.driver_stops == 1


def test_find_reports_an_unexpected_failure_with_its_type(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)

    def boom(*_args, **_kwargs):
        raise PlaywrightError("CDP rơi")

    _stub(monkeypatch, "_show_catalog_floating_filter", boom)
    logs: list[str] = []

    result = flows.find_in_open_catalog("Apparel", "code", "ABC", logs.append)

    assert result["code"] == "CATALOG_SEARCH_FAILED"
    assert "Error" in result["message"]
    assert logs


# --- find_and_open_catalog_destination ------------------------------------


@pytest.mark.parametrize("destination", ["", "packing", "costsheet2"])
def test_destination_must_be_costsheet_or_bom(clock, destination):
    result = flows.find_and_open_catalog_destination(
        "Apparel", "code", "ABC", destination, _quiet()
    )

    assert result["code"] == "ARTICLE_DESTINATION_UNKNOWN"


def test_destination_opens_without_recycling_when_the_popup_answers(
    clock, monkeypatch
):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: None)
    _stub(monkeypatch, "_filter_grid_and_maybe_open", lambda *a, **kw: _opened())
    _stub(monkeypatch, "_article_navigation_states", lambda _ctx: [])
    _stub(monkeypatch, "_open_article_destination", lambda *a, **kw: "Costsheet")
    refreshes: list[int] = []
    _stub(
        monkeypatch,
        "_refresh_article_context",
        lambda *a, **kw: refreshes.append(1),
    )

    result = flows.find_and_open_catalog_destination(
        "Apparel", "code", "ABC", "costsheet", _quiet()
    )

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    assert result["destination"] == "costsheet"
    assert "→ Costsheet" in result["message"]
    assert refreshes == []


def test_destination_reclicks_the_style_then_recycles_exactly_once(
    clock, monkeypatch
):
    """Probe ngắn timeout → click lại Style trên grid → recycle → thử lại."""
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    grid = _grid_frame(clock)
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: grid)
    _stub(monkeypatch, "_filter_grid_and_maybe_open", lambda *a, **kw: _opened())
    _stub(monkeypatch, "_article_navigation_states", lambda _ctx: [])
    attempts: list[float] = []

    def destination(*_args, **kwargs):
        attempts.append(kwargs.get("timeout_seconds"))
        if len(attempts) == 1:
            raise PlaywrightTimeoutError("popup chưa publish")
        return "BOM"

    _stub(monkeypatch, "_open_article_destination", destination)
    clicks: list[str] = []
    _stub(
        monkeypatch,
        "_click_catalog_style",
        lambda _grid, code, _label, _log: clicks.append(code),
    )
    refreshed: list[int] = []

    def refresh(playwright, browser, page, _log):
        refreshed.append(1)
        return playwright, browser, page

    _stub(monkeypatch, "_refresh_article_context", refresh)

    result = flows.find_and_open_catalog_destination(
        "Apparel", "code", "ABC123", "bom", _quiet()
    )

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    assert clicks == ["ABC123"]
    assert refreshed == [1]
    assert attempts == [4, 18]


def test_destination_skips_the_style_reclick_when_a_popup_was_already_open(
    clock, monkeypatch
):
    """Popup Style đang mở sau MULTIPLE_RESULTS: phục hồi, không search lại."""
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: None)
    _stub(monkeypatch, "_filter_grid_and_maybe_open", lambda *a, **kw: _opened())
    _stub(
        monkeypatch,
        "_article_navigation_states",
        lambda _ctx: [(object(), "url", True)],
    )
    attempts: list[float] = []

    def destination(*_args, **kwargs):
        attempts.append(kwargs.get("timeout_seconds"))
        if len(attempts) == 1:
            raise PlaywrightTimeoutError("popup chưa phản hồi")
        return "Costsheet"

    _stub(monkeypatch, "_open_article_destination", destination)
    clicks: list[str] = []
    _stub(
        monkeypatch,
        "_click_catalog_style",
        lambda *a: clicks.append("clicked"),
    )
    _stub(
        monkeypatch,
        "_refresh_article_context",
        lambda playwright, browser, page, _log: (playwright, browser, page),
    )

    result = flows.find_and_open_catalog_destination(
        "Apparel", "code", "ABC123", "costsheet", _quiet()
    )

    assert result["code"] == "CATALOG_DESTINATION_OPENED"
    assert clicks == []
    assert attempts == [3, 18]


def test_destination_is_not_opened_when_the_filter_found_several_codes(
    clock, monkeypatch
):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: None)
    _stub(
        monkeypatch,
        "_filter_grid_and_maybe_open",
        lambda *a, **kw: {
            "ok": True,
            "code": "MULTIPLE_RESULTS",
            "message": "2 kết quả",
        },
    )
    _stub(monkeypatch, "_article_navigation_states", lambda _ctx: [])
    opened: list[int] = []
    _stub(
        monkeypatch,
        "_open_article_destination",
        lambda *a, **kw: opened.append(1) or "Costsheet",
    )

    result = flows.find_and_open_catalog_destination(
        "Apparel", "code", "ABC", "costsheet", _quiet()
    )

    assert result["code"] == "MULTIPLE_RESULTS"
    assert opened == []


# --- prepare_catalog_master -----------------------------------------------


def test_prepare_reuses_a_confirmed_master_without_reopening_it(
    clock, monkeypatch
):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_reuse_prepared_catalog_master", lambda *a: True)
    reopened: list[int] = []
    _stub(
        monkeypatch,
        "_open_catalog_tree_on_page",
        lambda *a: reopened.append(1),
    )

    result = flows.prepare_catalog_master("Apparel", "01", _quiet())

    assert result["code"] == "CATEGORY_SELECTED"
    assert result["value"] == "01"
    assert reopened == []


def test_prepare_opens_tree_master_and_filter_when_reuse_is_refused(
    clock, monkeypatch
):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_reuse_prepared_catalog_master", lambda *a: False)
    order: list[str] = []
    _stub(
        monkeypatch,
        "_open_catalog_tree_on_page",
        lambda *a: order.append("tree"),
    )
    _stub(monkeypatch, "_click_catalog_master", lambda *a: order.append("master"))
    _stub(
        monkeypatch,
        "_show_catalog_floating_filter",
        lambda *a, **kw: order.append(f"filter:{kw.get('require_data_ready')}"),
    )

    result = flows.prepare_catalog_master("Apparel", "01", _quiet())

    assert result["ok"] is True
    assert order == ["tree", "master", "filter:True"]


def test_prepare_maps_a_timeout_to_catalog_not_open(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_reuse_prepared_catalog_master", lambda *a: False)

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("cây Catalog không dựng")

    _stub(monkeypatch, "_open_catalog_tree_on_page", slow)

    result = flows.prepare_catalog_master("Apparel", "01", _quiet())

    assert result["code"] == "CATALOG_NOT_OPEN"
    assert world.driver_stops == 1


def test_prepare_maps_any_other_failure_to_category_failed(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_reuse_prepared_catalog_master", lambda *a: False)

    def boom(*_args, **_kwargs):
        raise ValueError("category value lạ")

    _stub(monkeypatch, "_open_catalog_tree_on_page", boom)

    result = flows.prepare_catalog_master("Apparel", "01", _quiet())

    assert result["code"] == "CATEGORY_FAILED"
    assert "ValueError" in result["message"]


@pytest.mark.parametrize(
    "entry",
    [
        lambda: flows.prepare_catalog_master("Apparel", "01", _quiet()),
        lambda: flows.scan_catalog_folders("Apparel", "01", _quiet()),
        lambda: flows.open_catalog_folder("Apparel", "01", "", _quiet()),
        lambda: flows.set_catalog_category("Apparel", "01", _quiet()),
        lambda: flows.open_catalog_master(_quiet()),
        lambda: flows.filter_and_open_catalog_code("ABC", _quiet()),
    ],
)
def test_every_entry_point_checks_chrome_before_starting_a_driver(
    clock, monkeypatch, entry
):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, chrome_ready=False, clock=clock)

    assert entry()["code"] == "CHROME_CLOSED"
    assert world.driver_starts == 0


# --- scan_catalog_folders -------------------------------------------------


def test_scan_folders_returns_every_folder_the_user_may_see(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    frame = _grid_frame(clock)
    _stub(monkeypatch, "_open_catalog_tree_on_page", lambda *a: frame)
    folders = [{"node_id": "12", "path_label": "Khách A"}]
    _stub(monkeypatch, "_catalog_folder_nodes", lambda _frame: folders)
    logs: list[str] = []

    result = flows.scan_catalog_folders("Apparel", "01", logs.append)

    assert result["code"] == "CATALOG_FOLDERS_SCANNED"
    assert result["folders"] == folders
    assert any("Đã quét 1 thư mục" in line for line in logs)


def test_scan_folders_reports_an_empty_tree_as_a_failure(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_open_catalog_tree_on_page", lambda *a: _grid_frame(clock))
    _stub(monkeypatch, "_catalog_folder_nodes", lambda _frame: [])

    result = flows.scan_catalog_folders("Apparel", "01", _quiet())

    assert result["code"] == "CATALOG_FOLDER_TREE_EMPTY"
    assert result["folders"] == []


def test_scan_folders_separates_timeout_from_other_failures(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)

    def slow(*_args):
        raise PlaywrightTimeoutError("cây chưa dựng")

    _stub(monkeypatch, "_open_catalog_tree_on_page", slow)
    assert (
        flows.scan_catalog_folders("Apparel", "01", _quiet())["code"]
        == "CATALOG_FOLDER_SCAN_TIMEOUT"
    )

    def boom(*_args):
        raise RuntimeError("frame lạ")

    _stub(monkeypatch, "_open_catalog_tree_on_page", boom)
    assert (
        flows.scan_catalog_folders("Apparel", "01", _quiet())["code"]
        == "CATALOG_FOLDER_SCAN_FAILED"
    )


# --- open_catalog_folder --------------------------------------------------


@pytest.mark.parametrize("node_id", ["abc", "12a", "-1", "1 2"])
def test_folder_node_id_must_be_digits(clock, node_id):
    result = flows.open_catalog_folder("Apparel", "01", node_id, _quiet())

    assert result["code"] == "CATALOG_FOLDER_INVALID"


def test_an_empty_node_id_opens_master(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_open_catalog_tree_on_page", lambda *a: _grid_frame(clock))
    order: list[str] = []
    _stub(monkeypatch, "_click_catalog_master", lambda *a: order.append("master"))
    _stub(
        monkeypatch,
        "_show_catalog_floating_filter",
        lambda *a, **kw: order.append("filter"),
    )

    result = flows.open_catalog_folder("Apparel", "01", "  ", _quiet())

    assert result["code"] == "CATALOG_FOLDER_OPENED"
    assert result["folder"]["kind"] == "master"
    assert order == ["master", "filter"]


def test_a_node_that_vanished_reports_a_stale_default_folder(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_open_catalog_tree_on_page", lambda *a: _grid_frame(clock))
    _stub(monkeypatch, "_catalog_folder_for_node", lambda _frame, _node: None)

    result = flows.open_catalog_folder("Apparel", "01", "42", _quiet())

    assert result["code"] == "CATALOG_FOLDER_STALE"


def test_folder_click_must_be_confirmed_by_wfx(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    node = FakeNode()
    frame = FakeFrame(
        clock,
        url="https://wfx.test/wfx_CatalogMain.aspx",
        nodes={'span[nodeid="42"][onclick]': [node]},
    )
    _stub(monkeypatch, "_open_catalog_tree_on_page", lambda *a: frame)
    _stub(
        monkeypatch,
        "_catalog_folder_for_node",
        lambda _frame, _node: {"path_label": "Khách A", "node_id": "42"},
    )
    _stub(monkeypatch, "_wait_catalog_folder_selected", lambda *a: False)

    result = flows.open_catalog_folder("Apparel", "01", "42", _quiet())

    assert result["code"] == "CATALOG_FOLDER_OPEN_TIMEOUT"
    assert node.clicks == 1


def test_a_confirmed_folder_click_returns_its_path(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    node = FakeNode()
    frame = FakeFrame(
        clock,
        url="https://wfx.test/wfx_CatalogMain.aspx",
        nodes={'span[nodeid="42"][onclick]': [node]},
    )
    folder = {"path_label": "Khách A > Xuân", "node_id": "42"}
    _stub(monkeypatch, "_open_catalog_tree_on_page", lambda *a: frame)
    _stub(monkeypatch, "_catalog_folder_for_node", lambda *a: folder)
    _stub(monkeypatch, "_wait_catalog_folder_selected", lambda *a: True)

    result = flows.open_catalog_folder("Apparel", "01", "42", _quiet())

    assert result["code"] == "CATALOG_FOLDER_OPENED"
    assert result["folder"] == folder
    assert "Khách A > Xuân" in result["message"]


def test_folder_open_reports_a_non_timeout_failure_separately(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)

    def boom(*_args):
        raise RuntimeError("frame lạ")

    _stub(monkeypatch, "_open_catalog_tree_on_page", boom)

    result = flows.open_catalog_folder("Apparel", "01", "42", _quiet())

    assert result["code"] == "CATALOG_FOLDER_OPEN_FAILED"


# --- quick_find_catalog ---------------------------------------------------


def test_quick_find_requires_a_query(clock):
    assert (
        flows.quick_find_catalog("Apparel", "01", "code", " ", "u", "p")["code"]
        == "QUERY_REQUIRED"
    )


def test_quick_find_refuses_costsheet_outside_apparel(clock):
    result = flows.quick_find_catalog(
        "Trims", "02", "code", "ABC", "u", "p", destination="costsheet"
    )

    assert result["code"] == "APPAREL_ONLY"


def test_quick_find_needs_credentials_when_there_is_no_session(
    clock, monkeypatch
):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, logged_in=False, clock=clock)
    _stub(monkeypatch, "_start_persistent_chrome", lambda _log: None)

    result = flows.quick_find_catalog("Apparel", "01", "code", "ABC", "  ", "")

    assert result["code"] == "MISSING_CREDENTIALS"
    assert world.driver_stops == 1


def test_quick_find_logs_in_then_filters(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, logged_in=False, clock=clock)
    _stub(monkeypatch, "_start_persistent_chrome", lambda _log: None)
    logins: list[tuple] = []
    _stub(
        monkeypatch,
        "login",
        lambda page, user, password, company: logins.append((user, company)),
    )
    _stub(monkeypatch, "_catalog_tree_frame_now", lambda _page: None)
    _stub(monkeypatch, "_open_catalog_menu_on_page", lambda *a, **kw: None)
    _stub(monkeypatch, "_select_catalog_category_on_page", lambda *a, **kw: None)
    _stub(monkeypatch, "_click_catalog_master", lambda *a: None)
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: None)
    _stub(
        monkeypatch,
        "_filter_grid_and_maybe_open",
        lambda *a, **kw: {"ok": True, "code": "NO_RESULTS", "message": "trống"},
    )
    world.page.nodes[f"xpath={flows.CATALOG_XPATH}"] = [FakeNode()]

    result = flows.quick_find_catalog("Apparel", "01", "code", "ABC", "user", "pw")

    assert result["code"] == "NO_RESULTS"
    assert logins == [("user", "psh")]
    assert result["session_active"] is True


def test_quick_find_reconnects_cdp_before_opening_the_destination(
    clock, monkeypatch
):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_start_persistent_chrome", lambda _log: None)
    _stub(monkeypatch, "_catalog_tree_frame_now", lambda _page: None)
    _stub(monkeypatch, "_open_catalog_menu_on_page", lambda *a, **kw: None)
    _stub(monkeypatch, "_select_catalog_category_on_page", lambda *a, **kw: None)
    _stub(monkeypatch, "_click_catalog_master", lambda *a: None)
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: None)
    _stub(monkeypatch, "_filter_grid_and_maybe_open", lambda *a, **kw: _opened())
    _stub(monkeypatch, "_open_article_destination", lambda *a, **kw: "BOM")
    world.page.nodes[f"xpath={flows.CATALOG_XPATH}"] = [FakeNode()]

    result = flows.quick_find_catalog(
        "Apparel", "01", "code", "ABC", "u", "p", destination="bom"
    )

    assert result["destination"] == "bom"
    assert "→ BOM" in result["message"]
    # Reconnect: driver được dựng hai lần và nhả đủ hai lần.
    assert world.driver_starts == 2
    assert world.driver_stops == 2


def test_quick_find_separates_timeout_from_other_failures(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    _stub(monkeypatch, "_start_persistent_chrome", lambda _log: None)
    _stub(monkeypatch, "_catalog_tree_frame_now", lambda _page: None)
    world.page.nodes[f"xpath={flows.CATALOG_XPATH}"] = [FakeNode()]

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("menu không mở")

    _stub(monkeypatch, "_open_catalog_menu_on_page", slow)
    assert (
        flows.quick_find_catalog("Apparel", "01", "code", "ABC", "u", "p")["code"]
        == "QUICK_SEARCH_TIMEOUT"
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("frame lạ")

    _stub(monkeypatch, "_open_catalog_menu_on_page", boom)
    assert (
        flows.quick_find_catalog("Apparel", "01", "code", "ABC", "u", "p")["code"]
        == "QUICK_SEARCH_FAILED"
    )


# --- set_catalog_category -------------------------------------------------


class _CategorySelect(Element):
    """`#ddlCategory`: chọn xong WFX mới xác nhận lại value sau postback."""

    def __init__(self, *, confirms: str) -> None:
        super().__init__(
            "select",
            id="ddlCategory",
            value="",
            children=[element("option", attrs={"value": "01"}, text="Apparel")],
        )
        self._confirms = confirms

    def select_option(self, value=None, **kwargs):
        self.selected.append(str(value))
        self.value = self._confirms


def _category_frame(confirms: str = "01") -> MiniFrame:
    select = _CategorySelect(confirms=confirms)
    return MiniFrame(Element("body", children=[select]), name="left")


def test_set_category_selects_then_opens_master(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    frame = _category_frame()
    _stub(monkeypatch, "_catalog_left_frame", lambda _page: frame)
    _stub(monkeypatch, "_catalog_tree_frame_now", lambda _page: frame)
    order: list[str] = []
    _stub(monkeypatch, "_click_catalog_master", lambda *a: order.append("master"))
    _stub(
        monkeypatch,
        "_show_catalog_floating_filter",
        lambda *a, **kw: order.append("filter"),
    )

    result = flows.set_catalog_category("Apparel", "01", _quiet())

    assert result["code"] == "CATEGORY_SELECTED"
    assert order == ["master", "filter"]


def test_set_category_fails_when_wfx_never_confirms_the_value(
    clock, monkeypatch
):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    frame = _category_frame(confirms="09")
    _stub(monkeypatch, "_catalog_left_frame", lambda _page: frame)
    _stub(monkeypatch, "_catalog_tree_frame_now", lambda _page: frame)

    result = flows.set_catalog_category("Apparel", "01", _quiet())

    assert result["code"] == "CATALOG_NOT_OPEN"


def test_set_category_reports_an_unexpected_failure(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)

    def boom(_page):
        raise RuntimeError("không có frame left")

    _stub(monkeypatch, "_catalog_left_frame", boom)

    result = flows.set_catalog_category("Apparel", "01", _quiet())

    assert result["code"] == "CATEGORY_FAILED"


# --- open_catalog_master --------------------------------------------------


def test_open_master_reports_success_only_after_the_filter_is_ready(
    clock, monkeypatch
):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    order: list[str] = []
    _stub(monkeypatch, "_click_catalog_master", lambda *a: order.append("master"))
    _stub(
        monkeypatch,
        "_show_catalog_floating_filter",
        lambda *a, **kw: order.append("filter"),
    )

    result = flows.open_catalog_master(_quiet())

    assert result["code"] == "MASTER_OPENED"
    assert order == ["master", "filter"]


def test_open_master_maps_timeout_and_other_failures(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)

    def slow(*_args):
        raise PlaywrightTimeoutError("không thấy Master")

    _stub(monkeypatch, "_click_catalog_master", slow)
    assert flows.open_catalog_master(_quiet())["code"] == "MASTER_NOT_FOUND"

    def boom(*_args):
        raise RuntimeError("frame lạ")

    _stub(monkeypatch, "_click_catalog_master", boom)
    assert flows.open_catalog_master(_quiet())["code"] == "MASTER_FAILED"


# --- filter_and_open_catalog_code -----------------------------------------


CODE_INPUT = 'input[aria-label="Code Filter Input"]'
CODE_CELLS = '[role="gridcell"][col-id="lnkArticleCode"] input[type="button"]'


def _code_grid(clock, codes, *, visible=True) -> FakeFrame:
    cells = [FakeNode(value=code, visible=visible) for code in codes]
    return FakeFrame(
        clock,
        url="https://wfx.test/wfxcataloglist.aspx",
        nodes={CODE_INPUT: [FakeNode()], CODE_CELLS: cells},
    )


def test_filter_code_requires_a_code(clock):
    assert flows.filter_and_open_catalog_code("   ")["code"] == "CODE_REQUIRED"


def test_filter_code_opens_the_exact_match(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    grid = _code_grid(clock, ["ABC123", "ABC1230"])
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: grid)

    result = flows.filter_and_open_catalog_code("abc123", _quiet())

    assert result["code"] == "CODE_OPENED"
    assert result["article_code"] == "abc123"
    assert grid.nodes[CODE_CELLS][0].clicks == 1
    assert grid.nodes[CODE_INPUT][0].value == "abc123"


def test_filter_code_reports_when_no_row_matches_exactly(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    grid = _code_grid(clock, ["ABC1230"])
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: grid)

    result = flows.filter_and_open_catalog_code("ABC123", _quiet())

    assert result["code"] == "CODE_NOT_FOUND"
    assert result["codes"] == ["ABC1230"]
    assert grid.nodes[CODE_CELLS][0].clicks == 0


def test_filter_code_skips_rows_that_are_not_rendered(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    grid = _code_grid(clock, ["ABC123"], visible=False)
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: grid)

    result = flows.filter_and_open_catalog_code("ABC123", _quiet())

    assert result["code"] == "CODE_NOT_FOUND"
    assert result["codes"] == []


def test_filter_code_ignores_a_row_that_detaches_mid_scan(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)
    grid = _code_grid(clock, ["GONE", "ABC123"])
    grid.nodes[CODE_CELLS][0].detached = True
    _stub(monkeypatch, "_show_catalog_floating_filter", lambda *a, **kw: grid)

    result = flows.filter_and_open_catalog_code("ABC123", _quiet())

    assert result["code"] == "CODE_OPENED"
    assert result["codes"] == ["ABC123"]


def test_filter_code_maps_timeout_and_other_failures(clock, monkeypatch):
    world = _world(clock)
    wire_automation(monkeypatch, flows, world, clock=clock)

    def slow(*_args, **_kwargs):
        raise PlaywrightTimeoutError("grid chưa sẵn sàng")

    _stub(monkeypatch, "_show_catalog_floating_filter", slow)
    assert (
        flows.filter_and_open_catalog_code("ABC", _quiet())["code"]
        == "CODE_FILTER_TIMEOUT"
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("frame lạ")

    _stub(monkeypatch, "_show_catalog_floating_filter", boom)
    assert (
        flows.filter_and_open_catalog_code("ABC", _quiet())["code"]
        == "CODE_FILTER_FAILED"
    )
