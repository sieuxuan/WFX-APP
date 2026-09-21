"""RMPO List: tìm, đọc dòng và mở đúng cột của dòng người dùng đã chọn.

`wfx_panel/automation/modules/rmpo.py` ở mức 21%. CLAUDE.md đặc tả:

* "RMPO List: tìm kết hợp theo Supplier và RMPO No. trên đúng grid `gridRMPO`,
  sau đó đưa các dòng về app với Status, Supplier, Order No., Last Created và
  Qty để user chọn."
* "`Kiểm tra PO` click `#colOCNo` của đúng dòng; `Sửa PO` click `#colOrderNo`,
  chờ cửa sổ tải tối đa 3 phút rồi click Revise."
* "Received và Part Received hiện `Check Received` để click `#colRecv`."
* "phải nhận diện lớp loading WFX (`blockUI`/progress) và chờ bảng RMPO hoặc
  trạng thái No records ổn định."
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.mini_dom import Element, MiniFrame
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.modules import rmpo


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, rmpo, _common)


def _quiet():
    return lambda _line: None


def _row(**overrides) -> dict:
    return {
        "row_key": "r1",
        "status": "Open",
        "supplier": "Nhà máy A",
        "order_no": "RMPO-2345",
        "last_created": "2026-09-01",
        "qty": "100",
        **overrides,
    }


class _Page:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        for frame in self.frames:
            frame.page = self

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


class _Context:
    def __init__(self, pages):
        self.pages = list(pages)


class _Browser:
    def __init__(self, context):
        self.contexts = [context]


def _grid_frame(clock, *, payload=None, header=True, grid=True, wrapper=True):
    """Frame RMPO List: grid + kết quả đọc grid được khai báo."""
    payloads = list(payload or [{"rows": [_row()], "noRows": False, "loading": False}])

    def read(_arg):
        return payloads[0] if len(payloads) == 1 else payloads.pop(0)

    children = []
    if grid:
        node = Element(
            "table",
            id="gridRMPO_tblGridContent" if wrapper else "gridRMPO_other",
            scripts={"colOrderNo": read},
        )
        children.append(node)
    if header:
        children.append(
            Element("td", id="gridRMPO_tblGridHeader_trSearch_td_colOrderNo")
        )
    body = Element("body", children=children, scripts={"colOrderNo": read})
    frame = MiniFrame(body, clock=clock, url="https://wfx.test/rmpo.aspx")
    frame.payloads = payloads
    return frame


# --- validate đầu vào -----------------------------------------------------


def test_a_search_without_any_condition_is_refused(clock):
    result = rmpo.search_rmpo_list('//*[@id="x"]/a', "  ", "", _quiet())

    assert result["code"] == "QUERY_REQUIRED"
    assert "Supplier" in result["message"]


# --- đọc grid -------------------------------------------------------------


def test_rows_are_normalised_to_the_six_columns_the_panel_shows(clock):
    frame = _grid_frame(
        clock,
        payload=[
            {
                "rows": [{"row_key": "r1", "order_no": "  RMPO-1 ", "qty": 5}],
                "noRows": False,
                "loading": False,
            }
        ],
    )

    rows, no_rows, loading = rmpo._read_rmpo_rows(frame)

    assert rows == [
        {
            "row_key": "r1",
            "status": "",
            "supplier": "",
            "order_no": "RMPO-1",
            "last_created": "",
            "qty": "5",
        }
    ]
    assert (no_rows, loading) == (False, False)


def test_a_non_dict_payload_is_treated_as_no_rows(clock):
    frame = _grid_frame(clock, payload=[[]])

    assert rmpo._read_rmpo_rows(frame) == ([], False, False)


def test_a_grid_rendered_as_two_independent_tables_is_still_read(clock):
    """CLAUDE.md: không báo thiếu `gridRMPO` khi WFX tách Header/Content."""
    frame = _grid_frame(clock, wrapper=False)

    rows, _no_rows, _loading = rmpo._read_rmpo_rows(frame)

    assert rows[0]["order_no"] == "RMPO-2345"


def test_a_frame_without_any_rmpo_grid_is_reported(clock):
    frame = MiniFrame(Element("body"), clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="gridRMPO"):
        rmpo._read_rmpo_rows(frame)


# --- chờ kết quả ổn định --------------------------------------------------


def test_rows_are_returned_once_they_stop_changing(clock):
    frame = _grid_frame(clock)

    assert rmpo._wait_rmpo_rows(frame)[0]["order_no"] == "RMPO-2345"


def test_a_loading_overlay_blocks_the_result(clock):
    frame = _grid_frame(
        clock, payload=[{"rows": [_row()], "noRows": False, "loading": True}]
    )

    with pytest.raises(PlaywrightTimeoutError, match="chưa ổn định"):
        rmpo._wait_rmpo_rows(frame, timeout_s=2)


def test_an_empty_grid_with_a_no_records_message_settles(clock):
    frame = _grid_frame(
        clock, payload=[{"rows": [], "noRows": True, "loading": False}]
    )

    assert rmpo._wait_rmpo_rows(frame) == []


def test_rows_that_do_not_yet_match_the_filter_are_not_accepted(clock):
    """Grid cũ vẫn còn dữ liệu của lượt trước thì chưa được trả về."""
    frame = _grid_frame(clock)

    with pytest.raises(PlaywrightTimeoutError):
        rmpo._wait_rmpo_rows(
            frame, timeout_s=2, expected_values={"order_no": "RMPO-9999"}
        )


def test_rows_matching_the_filter_are_accepted(clock):
    frame = _grid_frame(clock)

    rows = rmpo._wait_rmpo_rows(
        frame, expected_values={"order_no": "2345", "supplier": ""}
    )

    assert len(rows) == 1


# --- click đúng ô ---------------------------------------------------------


def _click_frame(clock, result=True):
    calls: list[dict] = []
    grid = Element(
        "table",
        id="gridRMPO_tblGridContent",
        scripts={"expected.row_key": lambda spec: calls.append(dict(spec)) or result},
    )
    frame = MiniFrame(Element("body", children=[grid]), clock=clock)
    frame.calls = calls
    return frame


def test_a_cell_click_passes_the_row_identity_to_the_browser(clock):
    frame = _click_frame(clock)

    assert rmpo._click_rmpo_cell(frame, "r1", "RMPO-1", "colOCNo") is True
    assert frame.calls == [
        {"row_key": "r1", "order_no": "RMPO-1", "column_id": "colOCNo"}
    ]


def test_a_cell_click_is_false_when_the_row_moved(clock):
    frame = _click_frame(clock, result=False)

    assert rmpo._click_rmpo_cell(frame, "r1", "RMPO-1", "colOCNo") is False


def test_a_cell_click_is_false_without_a_grid(clock):
    frame = MiniFrame(Element("body"), clock=clock)

    assert rmpo._click_rmpo_cell(frame, "r1", "RMPO-1", "colOCNo") is False


# --- nút Revise -----------------------------------------------------------


REVISE_XPATH = '//*[@id="titlebarRMPO"]/tbody/tr/td[2]/span/div[9]'


def test_the_revise_button_is_taken_from_a_document_that_changed(
    clock, monkeypatch
):
    button = Element("div", id="revise")
    frame = MiniFrame(
        Element("body"), clock=clock, xpaths={REVISE_XPATH: [button]}
    )
    page = _Page(clock, [frame])
    browser = _Browser(_Context([page]))
    monkeypatch.setattr(rmpo, "_document_changed", lambda _f, _s: True)

    resolved = rmpo._wait_rmpo_revision_button(browser, set(), [(frame, (frame, "x"))])

    assert resolved.node is button


def test_the_revise_button_is_never_read_from_an_unchanged_document(
    clock, monkeypatch
):
    button = Element("div", id="revise")
    frame = MiniFrame(
        Element("body"), clock=clock, xpaths={REVISE_XPATH: [button]}
    )
    page = _Page(clock, [frame])
    browser = _Browser(_Context([page]))
    monkeypatch.setattr(rmpo, "_document_changed", lambda _f, _s: False)

    with pytest.raises(PlaywrightTimeoutError, match="sau 3 phút"):
        rmpo._wait_rmpo_revision_button(
            browser, {id(page)}, [(frame, (frame, "x"))], timeout_s=2
        )


def test_the_snapshot_covers_every_frame_of_every_open_page(clock):
    frames = [MiniFrame(Element("body"), clock=clock) for _ in range(3)]
    page = _Page(clock, frames)
    browser = _Browser(_Context([page]))

    page_ids, snapshots = rmpo._snapshot_browser_documents(browser)

    assert page_ids == {id(page)}
    assert len(snapshots) == 3


# --- tìm ------------------------------------------------------------------


def _wire_search(monkeypatch, clock, frame, *, chrome_ready=True):
    world = WfxWorld(clock)
    wire_automation(
        monkeypatch, rmpo, world, chrome_ready=chrome_ready, clock=clock
    )
    monkeypatch.setattr(
        rmpo, "_open_multi_field_search_context", lambda *a, **kw: frame
    )
    monkeypatch.setattr(rmpo, "_resolve_multi_search_fields", lambda *a: {})
    monkeypatch.setattr(rmpo, "_clear_multi_search_fields", lambda *a: None)
    monkeypatch.setattr(
        rmpo,
        "_fill_multi_search_fields",
        lambda *a, **kw: (["RMPO No."], object()),
    )
    monkeypatch.setattr(rmpo, "_submit_multi_search", lambda *a: None)
    monkeypatch.setattr(rmpo, "_wait_module_search_settled", lambda *a: None)
    monkeypatch.setattr(rmpo, "_find_rmpo_frame", lambda *a, **kw: frame)
    return world


def test_a_search_returns_every_row_for_the_user_to_choose_from(
    clock, monkeypatch
):
    frame = _grid_frame(clock)
    world = _wire_search(monkeypatch, clock, frame)
    logs: list[str] = []

    result = rmpo.search_rmpo_list('//*[@id="x"]/a', "", "2345", logs.append)

    assert result["code"] == "RMPO_RESULTS_READY"
    assert result["result_count"] == 1
    assert result["filter_kinds"] == ["order_no"]
    assert result["rmpo_rows"][0]["status"] == "Open"
    assert any("rows=1" in line for line in logs)
    assert world.driver_stops == 1


def test_a_search_with_no_match_has_its_own_code(clock, monkeypatch):
    frame = _grid_frame(
        clock, payload=[{"rows": [], "noRows": True, "loading": False}]
    )
    _wire_search(monkeypatch, clock, frame)

    result = rmpo.search_rmpo_list('//*[@id="x"]/a', "Nhà máy A", "", _quiet())

    assert result["code"] == "RMPO_NO_RESULTS"
    assert result["rmpo_rows"] == []


def test_a_form_that_never_becomes_ready_is_told_apart_from_a_slow_result(
    clock, monkeypatch
):
    frame = _grid_frame(clock)
    _wire_search(monkeypatch, clock, frame)
    monkeypatch.setattr(
        rmpo,
        "_open_multi_field_search_context",
        lambda *a, **kw: (_ for _ in ()).throw(PlaywrightTimeoutError("chậm")),
    )

    assert (
        rmpo.search_rmpo_list('//*[@id="x"]/a', "", "1", _quiet())["code"]
        == "MODULE_SEARCH_NOT_READY"
    )


def test_a_result_that_never_settles_reports_the_search_was_already_sent(
    clock, monkeypatch
):
    frame = _grid_frame(
        clock, payload=[{"rows": [], "noRows": False, "loading": True}]
    )
    _wire_search(monkeypatch, clock, frame)

    result = rmpo.search_rmpo_list('//*[@id="x"]/a', "", "1", _quiet())

    assert result["code"] == "MODULE_SEARCH_NOT_CONFIRMED"


def test_a_search_failure_keeps_its_module_name(clock, monkeypatch):
    frame = _grid_frame(clock)
    _wire_search(monkeypatch, clock, frame)
    monkeypatch.setattr(
        rmpo,
        "_resolve_multi_search_fields",
        lambda *a: (_ for _ in ()).throw(ValueError("selector lạ")),
    )

    result = rmpo.search_rmpo_list('//*[@id="x"]/a', "", "1", _quiet())

    assert result["code"] == "MODULE_SEARCH_FAILED"
    assert result["module"] == "RMPO List"


def test_a_closed_browser_is_mapped_by_the_shared_boundary(clock, monkeypatch):
    frame = _grid_frame(clock)
    _wire_search(monkeypatch, clock, frame, chrome_ready=False)

    assert (
        rmpo.search_rmpo_list('//*[@id="x"]/a', "", "1", _quiet())["code"]
        == "CHROME_CLOSED"
    )


# --- mở thao tác ----------------------------------------------------------


def test_an_unknown_action_is_refused(clock):
    result = rmpo.open_rmpo_result_action("r1", "RMPO-1", "A", "Open", "khac")

    assert result["code"] == "RMPO_ACTION_INVALID"


@pytest.mark.parametrize("status", ["Open", "Cancelled", ""])
def test_check_received_is_refused_outside_received_statuses(clock, status):
    result = rmpo.open_rmpo_result_action(
        "r1", "RMPO-1", "A", status, "check_received"
    )

    assert result["code"] == "RMPO_ACTION_INVALID"
    assert "Received" in result["message"]


def _wire_action(monkeypatch, clock, frame, *, rows=None):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, rmpo, world, clock=clock)
    page = _Page(clock, [frame])
    browser = _Browser(_Context([page]))
    monkeypatch.setattr(
        rmpo, "_active_wfx_page", lambda _playwright, _log: (browser, page)
    )
    monkeypatch.setattr(rmpo, "_find_rmpo_frame", lambda *a, **kw: frame)
    monkeypatch.setattr(
        rmpo, "_wait_rmpo_rows", lambda *a, **kw: list(rows or [_row()])
    )
    return world


@pytest.mark.parametrize(
    ("action", "column", "code", "status"),
    [
        ("check_po", "colOCNo", "RMPO_PO_OPENED", "Open"),
        ("check_received", "colRecv", "RMPO_RECEIVED_OPENED", "Received"),
        ("check_received", "colRecv", "RMPO_RECEIVED_OPENED", "Part Received"),
    ],
)
def test_each_read_only_action_clicks_its_own_column(
    clock, monkeypatch, action, column, code, status
):
    frame = _click_frame(clock)
    _wire_action(monkeypatch, clock, frame, rows=[_row(status=status)])

    result = rmpo.open_rmpo_result_action(
        "r1", "RMPO-2345", "Nhà máy A", status, action, _quiet()
    )

    assert result["code"] == code
    assert result["action"] == action
    assert frame.calls[0]["column_id"] == column


def test_edit_po_clicks_the_order_column_then_revise(clock, monkeypatch):
    frame = _click_frame(clock)
    _wire_action(monkeypatch, clock, frame)
    button = Element("div", id="revise")
    monkeypatch.setattr(
        rmpo,
        "_wait_rmpo_revision_button",
        lambda *a, **kw: button,
    )
    logs: list[str] = []

    result = rmpo.open_rmpo_result_action(
        "r1", "RMPO-2345", "Nhà máy A", "Open", "edit_po", logs.append
    )

    assert result["code"] == "RMPO_REVISE_CLICKED"
    assert frame.calls[0]["column_id"] == "colOrderNo"
    assert button.clicks == 1
    assert any("Đã click Revise" in line for line in logs)


def test_a_row_whose_status_changed_is_refused(clock, monkeypatch):
    frame = _click_frame(clock)
    _wire_action(monkeypatch, clock, frame, rows=[_row(status="Cancelled")])

    result = rmpo.open_rmpo_result_action(
        "r1", "RMPO-2345", "Nhà máy A", "Open", "check_po", _quiet()
    )

    assert result["code"] == "RMPO_RESULT_EXPIRED"
    assert frame.calls == []


def test_a_column_that_is_no_longer_there_is_refused(clock, monkeypatch):
    frame = _click_frame(clock, result=False)
    _wire_action(monkeypatch, clock, frame)

    result = rmpo.open_rmpo_result_action(
        "r1", "RMPO-2345", "Nhà máy A", "Open", "check_po", _quiet()
    )

    assert result["code"] == "RMPO_RESULT_EXPIRED"
    assert "cột cần mở" in result["message"]


def test_an_action_timeout_has_its_own_code(clock, monkeypatch):
    frame = _click_frame(clock)
    _wire_action(monkeypatch, clock, frame)
    monkeypatch.setattr(
        rmpo,
        "_wait_rmpo_rows",
        lambda *a, **kw: (_ for _ in ()).throw(PlaywrightTimeoutError("chậm")),
    )

    result = rmpo.open_rmpo_result_action(
        "r1", "RMPO-2345", "A", "Open", "check_po", _quiet()
    )

    assert result["code"] == "RMPO_ACTION_NOT_READY"


def test_an_unexpected_action_failure_keeps_the_module_name(clock, monkeypatch):
    frame = _click_frame(clock)
    _wire_action(monkeypatch, clock, frame)
    monkeypatch.setattr(
        rmpo,
        "_click_rmpo_cell",
        lambda *a: (_ for _ in ()).throw(PlaywrightError("frame rơi")),
    )

    result = rmpo.open_rmpo_result_action(
        "r1", "RMPO-2345", "Nhà máy A", "Open", "check_po", _quiet()
    )

    assert result["code"] == "MODULE_FAILED"
    assert result["module"] == "RMPO List"
