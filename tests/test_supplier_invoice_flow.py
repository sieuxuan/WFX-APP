"""Supplier Inv List: tìm Invoice rồi bấm Delete/Cancel đúng dòng.

`wfx_panel/automation/modules/supplier_invoice.py` ở mức 34%. Đây là nhánh bấm
Delete/Cancel trên chứng từ thật, nên CLAUDE.md đặt hai rào chắn nằm đúng trong
phần chưa chạy:

* "Supplier Inv List và Expense Inv List còn dùng chung cả `#titlebarAPInvoiceList`,
  `#gridAPInvoiceList` lẫn `#txtSupplier`/`#txtInvoiceNo`, nên context chỉ được
  nhận khi frame có đủ bộ cột filter riêng của đúng module."
* Search của WFX là tìm chứa chuỗi, nên chỉ exact Invoice No. mới được tự chạy;
  mọi dòng gần đúng phải để người dùng chọn.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.modules import supplier_invoice as invoices

DELETE_XPATH = '//*[@id="titlebarAPInvoiceList"]/tbody/tr/td[2]/span/div[2]'
CANCEL_XPATH = '//*[@id="titlebarAPInvoiceList"]/tbody/tr/td[2]/span/div[4]'


@pytest.fixture
def clock(monkeypatch):
    """Module này chỉ ngủ qua `_wait` của `_common`, không tự đọc `time`."""
    return install_fake_clock(monkeypatch, _common)


def _quiet():
    return lambda _line: None


class _Page:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


def _row(**overrides) -> dict:
    return {
        "row_key": "r1",
        "invoice_no": "SI-102",
        "supplier": "Nhà máy A",
        "po_no": "PO-1",
        "asn_grn_no": "ASN-1",
        "status": "Save",
        **overrides,
    }


def _list_frame(clock, *, rows=(), grid=True, wrapper=True, buttons=True):
    children = []
    if grid:
        children.append(
            Element(
                "table",
                id=(
                    "gridAPInvoiceList_tblGridContent"
                    if wrapper
                    else "gridAPInvoiceList"
                ),
                scripts={"row_key": lambda _a: [dict(row) for row in frame.rows]},
            )
        )
    xpaths = {}
    delete_button = element("div", id="delete")
    cancel_button = element("div", id="cancel")
    if buttons:
        xpaths[DELETE_XPATH] = [delete_button]
        xpaths[CANCEL_XPATH] = [cancel_button]
    else:
        xpaths[DELETE_XPATH] = []
        xpaths[CANCEL_XPATH] = []
    frame = MiniFrame(
        Element("body", children=children), clock=clock, xpaths=xpaths
    )
    frame.rows = [dict(row) for row in rows]
    frame.clicked: list[dict] = []
    frame.click_result = True
    frame.delete_button = delete_button
    frame.cancel_button = cancel_button
    if grid:
        node = frame.locator(
            "#gridAPInvoiceList_tblGridContent" if wrapper else "#gridAPInvoiceList"
        ).node
        node.scripts = {
            "row_key": lambda spec: (
                [dict(row) for row in frame.rows]
                if not isinstance(spec, dict)
                else frame.clicked.append(dict(spec)) or frame.click_result
            )
        }
    return frame


# --- đọc grid -------------------------------------------------------------


def test_rows_are_normalised_to_the_six_columns_the_panel_shows(clock):
    frame = _list_frame(clock, rows=[{"row_key": "r1", "invoice_no": "  SI-1 "}])

    assert invoices._supplier_invoice_rows(frame) == [
        {
            "row_key": "r1",
            "invoice_no": "SI-1",
            "supplier": "",
            "po_no": "",
            "asn_grn_no": "",
            "status": "",
        }
    ]


def test_a_grid_without_the_content_wrapper_is_still_read(clock):
    frame = _list_frame(clock, rows=[_row()], wrapper=False)

    assert invoices._supplier_invoice_rows(frame)[0]["invoice_no"] == "SI-102"


def test_a_non_list_payload_reads_as_no_rows(clock):
    frame = _list_frame(clock, rows=[_row()])
    frame.locator("#gridAPInvoiceList_tblGridContent").node.scripts = {
        "row_key": lambda _a: {"row_key": "r1"}
    }

    assert invoices._supplier_invoice_rows(frame) == []


def test_a_frame_without_the_grid_is_reported(clock):
    frame = _list_frame(clock, grid=False)

    with pytest.raises(PlaywrightTimeoutError, match="Supplier Inv List"):
        invoices._supplier_invoice_rows(frame)


# --- chọn dòng ------------------------------------------------------------


def test_selecting_a_row_passes_its_identity_to_the_browser(clock):
    frame = _list_frame(clock, rows=[_row()])

    assert invoices._select_supplier_invoice_row(frame, "r1", "SI-102") is True
    assert frame.clicked == [{"row_key": "r1", "invoice_no": "SI-102"}]


def test_selecting_a_row_that_moved_is_false(clock):
    frame = _list_frame(clock, rows=[_row()])
    frame.click_result = False

    assert invoices._select_supplier_invoice_row(frame, "r1", "SI-102") is False


def test_selecting_a_row_without_a_grid_is_false(clock):
    frame = _list_frame(clock, grid=False)

    assert invoices._select_supplier_invoice_row(frame, "r1", "SI-102") is False


def test_a_browser_failure_while_selecting_is_false(clock):
    frame = _list_frame(clock, rows=[_row()])
    frame.locator("#gridAPInvoiceList_tblGridContent").node.scripts = {
        "row_key": lambda _a: (_ for _ in ()).throw(PlaywrightError("frame rơi"))
    }

    assert invoices._select_supplier_invoice_row(frame, "r1", "SI-102") is False


# --- ánh xạ Status → nút -------------------------------------------------


@pytest.mark.parametrize("status", ["Save", "saved", "  SAVE  "])
def test_a_saved_invoice_is_deleted(status):
    selector, label, code = invoices._supplier_invoice_action_for_status(status)

    assert selector == DELETE_XPATH
    assert label == "Delete"
    assert code == "SUPPLIER_INVOICE_DELETE_SUBMITTED"


@pytest.mark.parametrize("status", ["Confirm", "confirmed"])
def test_a_confirmed_invoice_is_cancelled(status):
    selector, label, code = invoices._supplier_invoice_action_for_status(status)

    assert selector == CANCEL_XPATH
    assert label == "Cancel"
    assert code == "SUPPLIER_INVOICE_CANCEL_SUBMITTED"


@pytest.mark.parametrize("status", ["", "Cancelled", "Posted", "Draft"])
def test_any_other_status_has_no_action(status):
    assert invoices._supplier_invoice_action_for_status(status) is None


# --- bấm Delete/Cancel ----------------------------------------------------


def _submit_world(clock, monkeypatch, **frame_kwargs):
    frame = _list_frame(clock, **frame_kwargs)
    page = _Page(clock, [frame])
    monkeypatch.setattr(invoices, "_attach_dialog_handler", lambda *a: None)
    return page, frame


def test_a_saved_invoice_clicks_delete(clock, monkeypatch):
    page, frame = _submit_world(clock, monkeypatch, rows=[_row()])

    result = invoices._submit_supplier_invoice_cancel(
        page, frame, _row(), _quiet()
    )

    assert result["code"] == "SUPPLIER_INVOICE_DELETE_SUBMITTED"
    assert result["action"] == "delete"
    assert frame.delete_button.clicks == 1
    assert frame.cancel_button.clicks == 0


def test_a_confirmed_invoice_clicks_cancel(clock, monkeypatch):
    page, frame = _submit_world(clock, monkeypatch, rows=[_row()])

    result = invoices._submit_supplier_invoice_cancel(
        page, frame, _row(status="Confirm"), _quiet()
    )

    assert result["code"] == "SUPPLIER_INVOICE_CANCEL_SUBMITTED"
    assert frame.cancel_button.clicks == 1
    assert frame.delete_button.clicks == 0


def test_an_invoice_whose_status_has_no_action_is_refused(clock, monkeypatch):
    page, frame = _submit_world(clock, monkeypatch, rows=[_row()])

    result = invoices._submit_supplier_invoice_cancel(
        page, frame, _row(status="Posted"), _quiet()
    )

    assert result["code"] == "SUPPLIER_INVOICE_STATUS_NOT_CANCELLABLE"
    assert frame.delete_button.clicks == 0


def test_a_row_that_moved_is_never_actioned(clock, monkeypatch):
    page, frame = _submit_world(clock, monkeypatch, rows=[_row()])
    frame.click_result = False

    result = invoices._submit_supplier_invoice_cancel(
        page, frame, _row(), _quiet()
    )

    assert result["code"] == "SUPPLIER_INVOICE_RESULT_EXPIRED"
    assert frame.delete_button.clicks == 0


def test_a_missing_toolbar_button_is_reported(clock, monkeypatch):
    page, frame = _submit_world(clock, monkeypatch, rows=[_row()], buttons=False)

    result = invoices._submit_supplier_invoice_cancel(
        page, frame, _row(), _quiet()
    )

    assert result["code"] == "SUPPLIER_INVOICE_ACTION_NOT_READY"
    assert "Delete" in result["message"]


# --- tìm và quyết định ----------------------------------------------------


def _wire_prepare(monkeypatch, clock, frame, *, chrome_ready=True):
    world = WfxWorld(clock)
    wire_automation(
        monkeypatch, invoices, world, chrome_ready=chrome_ready, clock=clock
    )
    page = _Page(clock, [frame])
    monkeypatch.setattr(
        invoices, "_active_wfx_page", lambda _p, _log: (world.browser, page)
    )
    monkeypatch.setattr(
        invoices, "_open_multi_field_search_context", lambda *a, **kw: frame
    )
    monkeypatch.setattr(
        invoices,
        "_resolve_multi_search_fields",
        lambda *a: {"invoice_no": object()},
    )
    monkeypatch.setattr(invoices, "_clear_multi_search_fields", lambda *a: None)
    monkeypatch.setattr(
        invoices, "_fill_multi_search_fields", lambda *a, **kw: ([], object())
    )
    monkeypatch.setattr(invoices, "_submit_multi_search", lambda *a: None)
    monkeypatch.setattr(invoices, "_wait_module_search_settled", lambda *a: None)
    monkeypatch.setattr(invoices, "_attach_dialog_handler", lambda *a: None)
    return world, page


def test_a_prepare_without_an_invoice_number_is_refused(clock):
    assert invoices.prepare_supplier_invoice_cancel('//*[@id="x"]/a', "  ")[
        "code"
    ] == "QUERY_REQUIRED"


def test_exactly_one_exact_match_is_actioned_straight_away(clock, monkeypatch):
    frame = _list_frame(clock, rows=[_row()])
    _wire_prepare(monkeypatch, clock, frame)

    result = invoices.prepare_supplier_invoice_cancel(
        '//*[@id="x"]/a', "SI-102", _quiet()
    )

    assert result["code"] == "SUPPLIER_INVOICE_DELETE_SUBMITTED"
    assert frame.delete_button.clicks == 1


def test_a_near_match_is_never_actioned_automatically(clock, monkeypatch):
    """`SI-102` không được tự bấm Delete lên `SI-1024`."""
    frame = _list_frame(clock, rows=[_row(invoice_no="SI-1024")])
    _wire_prepare(monkeypatch, clock, frame)

    result = invoices.prepare_supplier_invoice_cancel(
        '//*[@id="x"]/a', "SI-102", _quiet()
    )

    assert result["code"] == "SUPPLIER_INVOICE_MULTIPLE_RESULTS"
    assert result["exact_match"] is False
    assert frame.delete_button.clicks == 0
    assert "gần đúng" in result["message"]


def test_two_exact_matches_are_left_for_the_user(clock, monkeypatch):
    frame = _list_frame(
        clock, rows=[_row(row_key="r1"), _row(row_key="r2")]
    )
    _wire_prepare(monkeypatch, clock, frame)

    result = invoices.prepare_supplier_invoice_cancel(
        '//*[@id="x"]/a', "SI-102", _quiet()
    )

    assert result["code"] == "SUPPLIER_INVOICE_MULTIPLE_RESULTS"
    assert result["exact_match"] is True
    assert result["result_count"] == 2
    assert frame.delete_button.clicks == 0


def test_a_search_with_no_row_at_all_has_its_own_code(clock, monkeypatch):
    frame = _list_frame(clock, rows=[])
    _wire_prepare(monkeypatch, clock, frame)

    assert invoices.prepare_supplier_invoice_cancel(
        '//*[@id="x"]/a', "SI-102", _quiet()
    )["code"] == "SUPPLIER_INVOICE_NOT_FOUND"


def test_only_the_first_twenty_candidates_reach_the_panel(clock, monkeypatch):
    frame = _list_frame(
        clock,
        rows=[_row(row_key=f"r{index}") for index in range(25)],
    )
    _wire_prepare(monkeypatch, clock, frame)

    result = invoices.prepare_supplier_invoice_cancel(
        '//*[@id="x"]/a', "SI-102", _quiet()
    )

    assert len(result["invoices"]) == 20
    assert result["result_count"] == 25


def test_a_list_that_is_not_ready_has_its_own_code(clock, monkeypatch):
    frame = _list_frame(clock, rows=[_row()])
    _wire_prepare(monkeypatch, clock, frame)
    monkeypatch.setattr(
        invoices,
        "_open_multi_field_search_context",
        lambda *a, **kw: (_ for _ in ()).throw(PlaywrightTimeoutError("chậm")),
    )

    assert invoices.prepare_supplier_invoice_cancel(
        '//*[@id="x"]/a', "SI-102", _quiet()
    )["code"] == "SUPPLIER_INVOICE_NOT_READY"


def test_an_unexpected_failure_has_its_own_code(clock, monkeypatch):
    frame = _list_frame(clock, rows=[_row()])
    _wire_prepare(monkeypatch, clock, frame)
    monkeypatch.setattr(
        invoices,
        "_resolve_multi_search_fields",
        lambda *a: (_ for _ in ()).throw(ValueError("selector lạ")),
    )

    assert invoices.prepare_supplier_invoice_cancel(
        '//*[@id="x"]/a', "SI-102", _quiet()
    )["code"] == "SUPPLIER_INVOICE_CANCEL_FAILED"


def test_a_closed_browser_is_mapped_by_the_shared_boundary(clock, monkeypatch):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, invoices, world, chrome_ready=False, clock=clock)

    assert invoices.prepare_supplier_invoice_cancel(
        '//*[@id="x"]/a', "SI-102", _quiet()
    )["code"] == "CHROME_CLOSED"


# --- người dùng chọn dòng -------------------------------------------------


def _wire_choice(monkeypatch, clock, frame):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, invoices, world, clock=clock)
    page = _Page(clock, [frame])
    monkeypatch.setattr(
        invoices, "_active_wfx_page", lambda _p, _log: (world.browser, page)
    )
    monkeypatch.setattr(
        invoices, "_find_supplier_invoice_frame", lambda _page: frame
    )
    monkeypatch.setattr(invoices, "_attach_dialog_handler", lambda *a: None)
    return world


def test_the_chosen_row_is_actioned(clock, monkeypatch):
    frame = _list_frame(clock, rows=[_row(), _row(row_key="r2", status="Confirm")])
    _wire_choice(monkeypatch, clock, frame)

    result = invoices.cancel_supplier_invoice_choice(
        "r2", "SI-102", "Confirm", _quiet()
    )

    assert result["code"] == "SUPPLIER_INVOICE_CANCEL_SUBMITTED"
    assert frame.cancel_button.clicks == 1


def test_a_row_whose_status_changed_is_refused(clock, monkeypatch):
    frame = _list_frame(clock, rows=[_row(status="Posted")])
    _wire_choice(monkeypatch, clock, frame)

    result = invoices.cancel_supplier_invoice_choice(
        "r1", "SI-102", "Save", _quiet()
    )

    assert result["code"] == "SUPPLIER_INVOICE_RESULT_EXPIRED"
    assert frame.delete_button.clicks == 0


def test_a_row_that_disappeared_is_refused(clock, monkeypatch):
    frame = _list_frame(clock, rows=[])
    _wire_choice(monkeypatch, clock, frame)

    assert invoices.cancel_supplier_invoice_choice(
        "r1", "SI-102", "Save", _quiet()
    )["code"] == "SUPPLIER_INVOICE_RESULT_EXPIRED"


def test_a_list_that_closed_is_reported_as_expired(clock, monkeypatch):
    frame = _list_frame(clock, rows=[_row()])
    _wire_choice(monkeypatch, clock, frame)
    monkeypatch.setattr(
        invoices,
        "_find_supplier_invoice_frame",
        lambda _page: (_ for _ in ()).throw(PlaywrightTimeoutError("đóng rồi")),
    )

    assert invoices.cancel_supplier_invoice_choice(
        "r1", "SI-102", "Save", _quiet()
    )["code"] == "SUPPLIER_INVOICE_RESULT_EXPIRED"


def test_an_unexpected_failure_in_the_choice_flow_has_its_own_code(
    clock, monkeypatch
):
    frame = _list_frame(clock, rows=[_row()])
    _wire_choice(monkeypatch, clock, frame)
    monkeypatch.setattr(
        invoices,
        "_supplier_invoice_rows",
        lambda _frame: (_ for _ in ()).throw(ValueError("payload lạ")),
    )

    assert invoices.cancel_supplier_invoice_choice(
        "r1", "SI-102", "Save", _quiet()
    )["code"] == "SUPPLIER_INVOICE_CANCEL_FAILED"
