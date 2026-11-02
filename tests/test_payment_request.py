"""ĐNTT: chọn đúng chứng từ, khóa TXNID và giữ báo cáo theo tài khoản."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wfx_panel.automation import payment_request as flow
from wfx_panel.controllers import finance

EXPENSE = "0065_0880_0030_0020"
RATE = "rptCustomReportViewer_ctl04_ctl05_txtValue"
NULL = "rptCustomReportViewer_ctl04_ctl05_cbNull"
NAME = "rptCustomReportViewer_ctl04_ctl07_txtValue"
TXN = "rptCustomReportViewer_ctl04_ctl03_txtValue"


@pytest.fixture
def state():
    return {
        "marker": "report-document-1",
        "identity": {"key": TXN, "label": "TXNID", "type": "text", "value": "7167"},
        "parameters": [
            {
                "key": RATE,
                "label": "ExchangeRate (VND>>USD)",
                "type": "text",
                "value": "",
            },
            {
                "key": NULL,
                "label": "ExchangeRate (VND>>USD)",
                "type": "checkbox",
                "value": True,
            },
            {
                "key": NAME,
                "label": "Requester (Ho va Ten)",
                "type": "text",
                "value": "",
                "required": True,
            },
        ],
    }


def test_null_rate_is_applied_before_text_and_omits_disabled_rate(state):
    result = flow._export_values(state, {RATE: "", NULL: True, NAME: "Nguyễn Văn An"})
    assert list(result) == [NULL, NAME]
    assert result[NAME] == "Nguyễn Văn An"
    assert TXN not in result


def test_non_null_rate_is_enabled_before_filling(state):
    result = flow._export_values(state, {RATE: "25000", NULL: False, NAME: "An"})
    assert list(result) == [NULL, RATE, NAME]
    assert result[RATE] == "25000"


@pytest.mark.parametrize(
    "values",
    [
        {NAME: "   "},
        {NAME: "An", TXN: "9999"},
        {NAME: "An", NULL: "false"},
        {NAME: "An", RATE: []},
        {NAME: "x" * 501},
    ],
)
def test_invalid_names_types_and_txnid_tampering_never_reach_browser(
    monkeypatch, state, values
):
    browser = Mock()
    monkeypatch.setattr(flow, "sync_playwright", browser)
    result = flow.export_payment_request(state, values)
    assert result["code"] == "REPORT_PARAMETERS_INVALID"
    browser.assert_not_called()


def test_payment_parameters_verify_transaction_and_hide_txnid(monkeypatch, state):
    reader = Mock(return_value=[state["identity"], *state["parameters"]])
    monkeypatch.setattr(flow.reports, "_read_parameters", reader)
    frame = object()
    parameters, identity = flow._parameters(frame, {"id": "7167"})
    reader.assert_called_once_with(frame, shipment_date_ids=False)
    assert identity["value"] == "7167"
    assert TXN not in {item["key"] for item in parameters}
    assert next(item for item in parameters if item["key"] == NAME)["required"]
    with pytest.raises(flow.PaymentSelectionError):
        flow._parameters(frame, {"id": "9999"})


class ListFrame:
    def __init__(self, suffix, rows, *, missing_title=False):
        self.url = f"https://wfx.test/WFX{suffix}.aspx"
        self.root = Mock()
        self.root.evaluate.return_value = rows
        self.missing_title = missing_title
        self.activity = {"visible": False, "focused": False, "interacted": 0}

    def evaluate(self, script):
        assert script == flow._ACTIVITY_JS
        return self.activity

    def locator(self, selector):
        if "tblGridContent" in selector:
            self.root.count.return_value = 1
            return self.root
        return SimpleNamespace(count=lambda: 0 if self.missing_title else 1)


def context(*frames):
    return SimpleNamespace(pages=[SimpleNamespace(frames=[frame]) for frame in frames])


def row(key="7167", invoice="INV-1", selected=True):
    return {"id": key, "invoice_no": invoice, "selected": selected}


def test_selected_invoice_ignores_other_finance_modules_and_unchecked_rows():
    target = ListFrame("ExpenseInvoiceList", [row(), row("1", selected=False)])
    supplier = ListFrame("APInvoiceList", [row("2")])
    assert flow._selected_invoice(context(supplier, target), "ExpenseInvoiceList") == (
        target,
        row(),
    )


@pytest.mark.parametrize("suffix", ["APInvoiceList", "AdvancePaymentRequestList"])
def test_wfx_lists_with_duplicate_titlebar_ids_are_supported(suffix):
    frame = ListFrame(suffix, [row()])
    original = frame.locator
    frame.locator = lambda selector: (
        SimpleNamespace(count=lambda: 2)
        if "titlebar" in selector
        else original(selector)
    )
    assert flow._selected_invoice(context(frame), suffix) == (frame, row())


@pytest.mark.parametrize("flag", ["visible", "focused"])
def test_current_list_selection_ignores_checked_rows_retained_in_old_tabs(flag):
    current = ListFrame("ExpenseInvoiceList", [row("5316")])
    current.activity[flag] = True
    stale = ListFrame("ExpenseInvoiceList", [row()])
    assert flow._selected_invoice(context(stale, current), "ExpenseInvoiceList") == (
        current,
        row("5316"),
    )


def test_minimized_browser_uses_the_row_highlighted_by_the_user():
    chosen = {**row("5316"), "highlighted": True}
    current = ListFrame("ExpenseInvoiceList", [chosen])
    stale = ListFrame("ExpenseInvoiceList", [row()])
    assert flow._selected_invoice(
        context(stale, current, stale), "ExpenseInvoiceList"
    ) == (current, chosen)


def test_latest_row_interaction_wins_over_highlights_in_old_tabs():
    old = ListFrame("ExpenseInvoiceList", [{**row(), "highlighted": True}])
    current = ListFrame("ExpenseInvoiceList", [{**row("5316"), "highlighted": True}])
    old.activity["interacted"] = 100
    current.activity["interacted"] = 200
    assert (
        flow._selected_invoice(context(current, old), "ExpenseInvoiceList")[0]
        is current
    )


@pytest.mark.parametrize("rows", [[row(selected=False)], [row(), row("2")]])
def test_current_tab_requires_one_selection_even_when_other_tabs_have_a_checked_row(
    rows,
):
    current = ListFrame("ExpenseInvoiceList", rows)
    current.activity["visible"] = True
    stale = ListFrame("ExpenseInvoiceList", [row()])
    with pytest.raises(flow.PaymentSelectionError):
        flow._selected_invoice(context(current, stale), "ExpenseInvoiceList")


def test_two_hidden_highlighted_tabs_without_recency_are_not_guessed():
    first = ListFrame("ExpenseInvoiceList", [{**row(), "highlighted": True}])
    second = ListFrame("ExpenseInvoiceList", [{**row("2"), "highlighted": True}])
    with pytest.raises(flow.PaymentSelectionError):
        flow._selected_invoice(context(first, second), "ExpenseInvoiceList")


def test_prepare_reads_the_user_tab_without_activating_main_wfx_first(monkeypatch):
    lease = Mock()
    monkeypatch.setattr(
        flow, "sync_playwright", lambda: SimpleNamespace(start=lambda: lease)
    )
    connector = Mock(return_value=(object(), SimpleNamespace(context=object())))
    monkeypatch.setattr(flow, "_active_wfx_page", connector)
    monkeypatch.setattr(
        flow,
        "_selected_invoice",
        Mock(side_effect=flow.PaymentSelectionError("Choose one row")),
    )
    assert (
        flow.prepare_payment_request(EXPENSE)["code"]
        == "PAYMENT_REQUEST_SELECTION_REQUIRED"
    )
    connector.assert_called_once_with(lease, print, bring_to_front=False)
    lease.stop.assert_called_once()


@pytest.mark.parametrize(
    "frames",
    [
        [ListFrame("ExpenseInvoiceList", [row(selected=False)])],
        [
            ListFrame("ExpenseInvoiceList", [row()]),
            ListFrame("ExpenseInvoiceList", [row("2")]),
        ],
        [ListFrame("ExpenseInvoiceList", [row()], missing_title=True)],
        [ListFrame("ExpenseInvoiceList", [row("bad-id")])],
    ],
)
def test_missing_ambiguous_or_invalid_selection_stops_before_bi_print(frames):
    with pytest.raises(flow.PaymentSelectionError):
        flow._selected_invoice(context(*frames), "ExpenseInvoiceList")


def test_typed_invoice_selects_only_the_exact_match(monkeypatch):
    frame = ListFrame("ExpenseInvoiceList", [])
    exact = row()
    frame.root.evaluate.side_effect = [[row("2", "INV-10"), exact], True, [exact]]
    monkeypatch.setattr(flow, "_search_module_fields", Mock(return_value={"ok": True}))
    monkeypatch.setattr(flow, "_open_multi_field_search_context", lambda *a: frame)
    monkeypatch.setattr(flow, "_classic_grid_result_count", lambda *a: 2)
    assert flow._find_invoice(object(), EXPENSE, "inv-1", print) == (frame, exact)


@pytest.mark.parametrize(
    "rows,total",
    [
        ([row("2", "INV-10")], 1),
        ([row(), row("2")], 2),
        ([row()], 20),
        ([row()], None),
    ],
)
def test_partial_duplicate_or_unread_pages_require_manual_choice(
    monkeypatch, rows, total
):
    frame = ListFrame("ExpenseInvoiceList", rows)
    monkeypatch.setattr(flow, "_search_module_fields", Mock(return_value={"ok": True}))
    monkeypatch.setattr(flow, "_open_multi_field_search_context", lambda *a: frame)
    monkeypatch.setattr(flow, "_classic_grid_result_count", lambda *a: total)
    with pytest.raises(flow.PaymentSelectionError):
        flow._find_invoice(object(), EXPENSE, "INV-1", print)
    assert frame.root.evaluate.call_count == 1  # no selection on an ambiguous result


class Panel:
    def __init__(self, base_dir):
        self._base_dir = base_dir
        self.user = "user-a"
        self._current_division = "woven"
        self._log = lambda line: None

    def _account(self):
        return {"user_id": self.user}

    def _run(self, name, action, request=None):
        return action()


@pytest.fixture
def controller(monkeypatch, state, tmp_path):
    monkeypatch.setattr(
        finance,
        "prepare_payment_request",
        lambda *args, **kwargs: {
            "ok": True,
            "code": "PAYMENT_REQUEST_PREPARED",
            "_report_state": state,
            "parameters": state["parameters"],
            "module_id": args[0],
        },
    )
    return finance.FinanceController(Panel(tmp_path))


def test_report_state_stays_private_and_new_prepare_invalidates_old_token(
    controller, monkeypatch
):
    first = controller.prepare_payment_request(EXPENSE)
    assert "_report_state" not in first
    second = controller.prepare_payment_request(EXPENSE)
    exporter = Mock()
    monkeypatch.setattr(finance, "export_payment_request", exporter)
    assert (
        controller.export_payment_request(first["report_token"], {NAME: "An"})["code"]
        == "PAYMENT_REQUEST_EXPIRED"
    )
    assert second["report_token"] != first["report_token"]
    exporter.assert_not_called()


@pytest.mark.parametrize("change", ["user", "division", "time"])
def test_account_division_and_age_guard_reports(controller, monkeypatch, change):
    prepared = controller.prepare_payment_request(EXPENSE)
    token = prepared["report_token"]
    if change == "user":
        controller._panel.user = "user-b"
    elif change == "division":
        controller._panel._current_division = "knit"
    else:
        controller.payment_reports[token]["created"] -= 1801
    exporter = Mock()
    monkeypatch.setattr(finance, "export_payment_request", exporter)
    assert (
        controller.export_payment_request(token, {NAME: "An"})["code"]
        == "PAYMENT_REQUEST_EXPIRED"
    )
    exporter.assert_not_called()


def test_export_uses_stored_identity_and_user_values(controller, monkeypatch, state):
    token = controller.prepare_payment_request(EXPENSE)["report_token"]
    exporter = Mock(return_value={"ok": True, "code": "REPORT_EXPORTED"})
    monkeypatch.setattr(finance, "export_payment_request", exporter)
    assert controller.export_payment_request(token, {NAME: "An"})["ok"]
    assert exporter.call_args.args[:2] == (state, {NAME: "An"})


@pytest.mark.parametrize(
    "txnid,marker", [("9999", "report-document-1"), ("7167", "other-document")]
)
def test_changed_report_never_exports(monkeypatch, state, txnid, marker):
    frame = Mock()
    frame.evaluate.return_value = marker
    frame.locator.return_value.input_value.return_value = txnid
    page = SimpleNamespace(context=context(frame))
    lease = Mock()
    monkeypatch.setattr(
        flow, "sync_playwright", lambda: SimpleNamespace(start=lambda: lease)
    )
    monkeypatch.setattr(flow, "_active_wfx_page", lambda *a: (object(), page))
    exporter = Mock()
    monkeypatch.setattr(flow.reports, "_export_excel", exporter)
    assert (
        flow.export_payment_request(state, {NAME: "An"})["code"]
        == "PAYMENT_REQUEST_EXPIRED"
    )
    exporter.assert_not_called()
    lease.stop.assert_called_once()


def test_export_runs_the_verified_report_and_native_excel_download(monkeypatch, state):
    frame = Mock()
    frame.evaluate.return_value = state["marker"]
    frame.locator.return_value.input_value.return_value = state["identity"]["value"]
    report_page = Mock(frames=[frame])
    page = SimpleNamespace(context=SimpleNamespace(pages=[report_page]))
    lease = Mock()
    monkeypatch.setattr(
        flow, "sync_playwright", lambda: SimpleNamespace(start=lambda: lease)
    )
    monkeypatch.setattr(flow, "_active_wfx_page", lambda *a: (object(), page))
    steps = Mock()
    for name in (
        "_set_parameters",
        "_click_view_report",
        "_wait_report_ready",
        "_export_excel",
    ):
        method = Mock()
        steps.attach_mock(method, name)
        monkeypatch.setattr(flow.reports, name, method)
    steps._export_excel.return_value = Path("C:/Downloads/Payment Request Form.xlsx")
    result = flow.export_payment_request(state, {NAME: "An"})
    assert result["ok"] and result["code"] == "REPORT_EXPORTED"
    assert result["file_name"] == "Payment Request Form.xlsx"
    assert [item[0] for item in steps.mock_calls] == [
        "_set_parameters",
        "_click_view_report",
        "_wait_report_ready",
        "_export_excel",
    ]
    steps._set_parameters.assert_called_once_with(frame, {NULL: True, NAME: "An"})
    steps._export_excel.assert_called_once_with(report_page, report_frame=frame)
    lease.stop.assert_called_once()


def test_only_superseded_dntt_tabs_are_closed():
    old_report, user_list, current = Mock(), Mock(), Mock()
    old_report.evaluate.return_value = True
    user_list.evaluate.return_value = False
    flow._close_previous_reports(
        SimpleNamespace(pages=[old_report, user_list, current]), current
    )
    old_report.close.assert_called_once()
    user_list.close.assert_not_called()
    current.close.assert_not_called()


def test_requester_is_shared_by_all_modules_and_survives_reopening(
    controller, monkeypatch
):
    assert controller.save_payment_request_requester("  Nguyễn Văn An  ")["ok"]
    reopened = finance.FinanceController(controller._panel)
    assert reopened.load_payment_request_requester()["requester"] == "Nguyễn Văn An"
    runner = Mock(
        return_value={"ok": False, "code": "PAYMENT_REQUEST_SELECTION_REQUIRED"}
    )
    monkeypatch.setattr(finance, "prepare_payment_request", runner)
    for module_id in flow.MODULES:
        reopened.prepare_payment_request(module_id)
        assert runner.call_args.kwargs["requester"] == "Nguyễn Văn An"


def test_requester_is_kept_across_divisions_but_separated_by_account(controller):
    controller.save_payment_request_requester("User A")
    controller._panel._current_division = "knit"
    assert controller.load_payment_request_requester()["requester"] == "User A"
    controller._panel.user = "user-b"
    assert controller.load_payment_request_requester()["requester"] == ""
    controller.save_payment_request_requester("User B")
    controller._panel.user = "USER-A"
    assert controller.load_payment_request_requester()["requester"] == "User A"


def test_late_requester_save_from_previous_account_is_rejected(controller):
    controller.save_payment_request_requester("User A")
    controller._panel.user = "user-b"
    assert not controller.save_payment_request_requester("old name", "user-a")["ok"]
    assert controller.load_payment_request_requester()["requester"] == ""


def test_prepare_persists_requester_before_opening_wfx(controller, monkeypatch):
    runner = Mock(return_value={"ok": False})
    monkeypatch.setattr(finance, "prepare_payment_request", runner)
    controller.prepare_payment_request(EXPENSE, "INV-1", "Nguyen Van An")
    assert controller.load_payment_request_requester()["requester"] == "Nguyen Van An"
    assert runner.call_args.kwargs["requester"] == "Nguyen Van An"


@pytest.mark.parametrize("value", [None, ["An"], "x" * 501])
def test_requester_rejects_invalid_values_without_erasing_saved_name(controller, value):
    controller.save_payment_request_requester("An")
    assert not controller.save_payment_request_requester(value)["ok"]
    assert controller.load_payment_request_requester()["requester"] == "An"
