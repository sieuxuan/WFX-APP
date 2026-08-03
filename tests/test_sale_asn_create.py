from datetime import date

import pytest
from openpyxl import Workbook, load_workbook

from wfx_panel import prefs
from wfx_panel.automation import sale_asn_create
from wfx_panel.automation.sale_asn_create import (
    _auto_add_po,
    _buyer_options,
    _choose_po_candidate,
    _refresh_existing_new_form,
    _set_style_hts_cell,
    _style_similarity,
)
from wfx_panel.panel_api import PanelAPI
from wfx_panel.sale_asn_workbook import (
    SALE_ASN_COLUMNS,
    SALE_ASN_ORDER_DETAILS_COLUMNS,
    SaleASNWorkbookError,
    read_sale_asn_order_details_workbook,
    read_sale_asn_workbook,
    write_sale_asn_order_details_template,
    write_sale_asn_template,
)


def _input_workbook(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(SALE_ASN_COLUMNS)
    for row in rows:
        sheet.append([row.get(column) for column in SALE_ASN_COLUMNS])
    workbook.save(path)
    workbook.close()


def _valid_rows():
    return [
        {
            "Invoice No": "INV-001",
            "Invoice Date": date(2026, 8, 1),
            "Shipping Bill No": "",
            "Shipping Bill Date": date(2026, 8, 2),
            "Style No": "STYLE A MEN",
            "PO No": "PO-001",
            "HS CODE": 62014010,
            "Qty": 10,
            "Carton": 2,
            "NW": 9.5,
            "GW": 10.5,
            "CBM": 1.25,
            "Destination": "Germany",
            "FTY": "PRO SPORTS GIAO THUY JSC",
            "Cargo Ready Date": date(2026, 8, 3),
        },
        {
            "Style No": "STYLE B WOMEN",
            "PO No": "PO-002",
            "Destination": "",
            "FTY": "",
        },
    ]


def _order_details_workbook(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ORDER DETAILS"
    sheet.append(SALE_ASN_ORDER_DETAILS_COLUMNS)
    for row in rows:
        sheet.append([row.get(column) for column in SALE_ASN_ORDER_DETAILS_COLUMNS])
    workbook.save(path)
    workbook.close()


def test_template_keeps_reference_schema_and_readable_format(tmp_path):
    target = write_sale_asn_template(tmp_path / "sale-asn.xlsx")

    workbook = load_workbook(target)
    sheet = workbook["SALE ASN"]
    assert tuple(cell.value for cell in sheet[1]) == SALE_ASN_COLUMNS
    assert sheet.freeze_panes == "A2"
    assert sheet.sheet_view.showGridLines is False
    assert sheet.tables["SaleASNInput"].ref == "A1:S21"
    assert sheet["A1"].fill.fgColor.rgb == "00FDE68A"
    assert sheet["G1"].fill.fgColor.rgb == "00DBEAFE"
    assert sheet["B2"].number_format == "dd/mm/yyyy"
    workbook.close()


def test_reader_preserves_row_order_and_applies_business_fallbacks(tmp_path):
    source = tmp_path / "input.xlsx"
    _input_workbook(source, _valid_rows())

    document = read_sale_asn_workbook(source)

    assert document["invoice_no"] == "INV-001"
    assert document["po_count"] == 2
    assert document["style_count"] == 2
    assert [row["po_no"] for row in document["rows"]] == ["PO-001", "PO-002"]
    assert document["rows"][0]["shipping_bill_no"] == "INV-001"
    assert document["rows"][1]["invoice_date"] == "2026-08-01"
    assert document["rows"][1]["shipping_bill_date"] == "2026-08-02"
    assert document["rows"][1]["cargo_ready_date"] == "2026-08-03"
    assert document["rows"][1]["destination"] == "Germany"
    assert document["rows"][0]["hs_code"] == "62014010"


def test_reader_ignores_every_row_without_po_number(tmp_path):
    rows = _valid_rows()
    rows.append(
        {
            "Style No": "TOTAL / GHI CHÚ",
            "PO No": "",
            "Qty": "không phải số",
            "Destination": "",
            "FTY": "",
        }
    )
    source = tmp_path / "ignore-no-po.xlsx"
    _input_workbook(source, rows)

    document = read_sale_asn_workbook(source)

    assert document["po_count"] == 2
    assert [row["source_row"] for row in document["rows"]] == [2, 3]


def test_reader_reports_duplicate_po_and_required_cells(tmp_path):
    rows = _valid_rows()
    rows[1]["PO No"] = "PO-001"
    rows[1]["Style No"] = ""
    source = tmp_path / "invalid.xlsx"
    _input_workbook(source, rows)

    with pytest.raises(SaleASNWorkbookError) as raised:
        read_sale_asn_workbook(source)

    assert raised.value.code == "SALE_ASN_FILE_VALIDATION_FAILED"
    assert any("PO No bị trùng" in error for error in raised.value.errors)
    assert any("Style No bắt buộc" in error for error in raised.value.errors)


def test_reader_relaxes_fields_when_continuing_only_order_details(tmp_path):
    source = tmp_path / "continue-order.xlsx"
    _input_workbook(
        source,
        [{"PO No": "PO-001", "Carton": 2, "NW": 9.5}],
    )

    document = read_sale_asn_workbook(
        source,
        required_stages=["order_details"],
    )

    assert document["po_count"] == 1
    assert document["style_count"] == 0
    assert document["rows"][0]["po_no"] == "PO-001"
    assert document["rows"][0]["carton"] == "2"
    assert document["rows"][0]["cargo_ready_date"] == ""

    with pytest.raises(SaleASNWorkbookError) as raised:
        read_sale_asn_workbook(source, required_stages=["style_details"])
    assert any("Style No bắt buộc" in error for error in raised.value.errors)


def test_full_template_can_prefill_current_order_details(tmp_path):
    target = write_sale_asn_template(
        tmp_path / "continue.xlsx",
        [
            {
                "po_no": "PO-001",
                "carton": "2",
                "nw": "9.5",
                "gw": "10.5",
                "cbm": "1.25",
                "fob_price": "12.75",
                "service_price": "0.5",
                "cargo_ready_date": "03 Aug 2026",
            }
        ],
    )

    workbook = load_workbook(target)
    sheet = workbook["SALE ASN"]
    assert sheet["F2"].value == "PO-001"
    assert sheet["K2"].value == 2
    assert sheet["L2"].value == 9.5
    assert sheet["Q2"].value == 12.75
    assert sheet["S2"].value.date() == date(2026, 8, 3)
    assert sheet.tables["SaleASNInput"].ref == "A1:S21"
    workbook.close()


def test_order_details_template_round_trip_keeps_only_editable_schema(tmp_path):
    target = write_sale_asn_order_details_template(
        tmp_path / "order-details.xlsx",
        [
            {
                "po_no": "PO-001",
                "carton": "2",
                "nw": "9.5",
                "gw": "10.5",
                "cbm": "1.25",
                "fob_price": "12.75",
                "service_price": "0.5",
                "cargo_ready_date": "03 Aug 2026",
            }
        ],
    )

    workbook = load_workbook(target)
    sheet = workbook["ORDER DETAILS"]
    assert tuple(cell.value for cell in sheet[1]) == SALE_ASN_ORDER_DETAILS_COLUMNS
    assert sheet.tables["SaleASNOrderDetailsInput"].ref == "A1:H21"
    assert sheet["A1"].fill.fgColor.rgb == "00FDE68A"
    assert sheet["B1"].fill.fgColor.rgb == "00DBEAFE"
    assert sheet["B2"].number_format == "#,##0"
    assert sheet["H2"].number_format == "dd/mm/yyyy"
    assert sheet["B2"].value == 2
    assert sheet["H2"].value.date() == date(2026, 8, 3)
    workbook.close()

    document = read_sale_asn_order_details_workbook(target)
    assert document["po_count"] == 1
    assert document["filled_count"] == 7
    assert document["rows"] == [
        {
            "source_row": 2,
            "po_no": "PO-001",
            "carton": "2",
            "nw": "9.5",
            "gw": "10.5",
            "cbm": "1.25",
            "fob_price": "12.75",
            "service_price": "0.5",
            "cargo_ready_date": "2026-08-03",
        }
    ]


def test_order_details_reader_requires_a_value_and_unique_po(tmp_path):
    source = tmp_path / "invalid-order-details.xlsx"
    _order_details_workbook(
        source,
        [
            {"PO No": "PO-001"},
            {"PO No": "PO-001", "Carton": "=1+1"},
        ],
    )

    with pytest.raises(SaleASNWorkbookError) as raised:
        read_sale_asn_order_details_workbook(source)

    assert raised.value.code == "SALE_ASN_ORDER_FILE_VALIDATION_FAILED"
    assert any("công thức" in error for error in raised.value.errors)
    assert any("PO No bị trùng" in error for error in raised.value.errors)


def test_candidate_selection_prefers_style_then_dispatched_qty():
    row = {"po_no": "PO-1", "style_no": "10758 HIBALL JACKET M", "qty": "240"}
    candidates = [
        {"po_no": "PO-1", "style_no": "10758 HIBALL JACKET M BLUE", "dispatched_qty": "100"},
        {"po_no": "PO-1", "style_no": "10758 HIBALL JACKET M RED", "dispatched_qty": "240"},
    ]

    assert _choose_po_candidate(row, candidates) == candidates[1]
    assert _style_similarity("10758 HIBALL", "10758 HIBALL JACKET M") > 0


def test_buyer_scan_waits_for_lazy_bound_select_options(monkeypatch):
    class FakeCell:
        def __init__(self):
            self.calls = 0

        def evaluate(self, _script):
            self.calls += 1
            if self.calls == 1:
                return []
            return [{"label": "  PUMA  ", "value": "77540"}]

    cell = FakeCell()
    frame = object()
    monkeypatch.setattr(sale_asn_create, "_buyer_cell", lambda _frame: cell)
    monkeypatch.setattr(sale_asn_create, "_wait", lambda _frame, _milliseconds: None)

    assert _buyer_options(frame, timeout_s=1) == [
        {"label": "PUMA", "value": "77540"}
    ]
    assert cell.calls == 2


def test_start_refreshes_existing_new_form_before_selecting_buyer(monkeypatch):
    calls = []

    class FakeFrame:
        url = "https://prosports.worldfashionexchange.com/WFXBase4.0/WFXSalesASN.aspx"

        def goto(self, url, **kwargs):
            calls.append(("goto", url, kwargs))

    frame = FakeFrame()
    page = type("FakePage", (), {"context": object()})()
    logs = []
    monkeypatch.setattr(
        sale_asn_create,
        "_frame_with_selector",
        lambda _context, _selector, timeout_s: (page, frame),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_ensure_select_value",
        lambda _page, selector, value, label, _log: calls.append(
            ("select", selector, value, label)
        ),
    )

    assert _refresh_existing_new_form(page, logs.append) is frame
    assert calls == [
        (
            "goto",
            frame.url,
            {"wait_until": "domcontentloaded", "timeout": 15_000},
        ),
        ("select", "#ddlASNType", "1", "ASN Type"),
        (
            "select",
            "#ddlASNAgainst",
            "BuyerOrderDispatch",
            "ASN Against",
        ),
    ]
    assert logs == [
        "[SALE ASN] Đã refresh form New đang mở trước khi chọn Buyer."
    ]


@pytest.mark.parametrize(
    ("final", "expected_action_selector"),
    (
        (False, sale_asn_create.PO_CONTINUE_SELECTOR),
        (True, sale_asn_create.PO_OK_SELECTOR),
    ),
)
def test_auto_add_po_selects_checkbox_by_exact_identity(
    monkeypatch,
    final,
    expected_action_selector,
):
    captured = {}

    class FakeLocator:
        @property
        def first(self):
            return self

        def evaluate(self, _script, spec=None):
            if spec is None:
                captured["continued_dom"] = True
                captured["action_script"] = _script
                return {"ok": True, "tag": "A", "id": ""}
            captured.update(spec)
            return {"ok": True, "value": spec["selection_value"]}

        def wait_for(self, **_kwargs):
            return None

        def click(self, **_kwargs):
            captured["continued"] = True

    class FakeFrame:
        def locator(self, selector):
            captured.setdefault("selectors", []).append(selector)
            return FakeLocator()

    candidate = {
        "row_index": 3,
        "selection_name": "optShipmentId",
        "selection_value": "7740025278_32043",
        "selection_order_id": "220106328",
        "po_no": "PO-1",
    }
    monkeypatch.setattr(
        sale_asn_create,
        "_search_po",
        lambda *_args, **_kwargs: [candidate],
    )
    waits = []
    monkeypatch.setattr(
        sale_asn_create,
        "_wait",
        lambda *_args: waits.append(_args),
    )

    added, _candidates, _reason = _auto_add_po(
        FakeFrame(),
        {"source_row": 2, "po_no": "PO-1"},
        lambda _message: None,
        final=final,
    )

    assert added is True
    assert captured["row_index"] == 3
    assert captured["selection_name"] == "optShipmentId"
    assert captured["selection_value"] == "7740025278_32043"
    assert captured["selection_order_id"] == "220106328"
    assert captured["continued_dom"] is True
    assert "querySelector('a, button, input, [onclick]')" in captured["action_script"]
    assert captured["selectors"] == [
        sale_asn_create.PO_RESULTS_TABLE_SELECTOR,
        expected_action_selector,
    ]
    assert len(waits) == (0 if final else 1)


def test_sale_asn_po_results_use_exact_wfx_table():
    assert sale_asn_create.PO_RESULTS_TABLE_XPATH == (
        '//*[@id="wfx_GMPOAsnSearch"]/div[3]/table'
    )
    assert sale_asn_create.PO_RESULTS_TABLE_SELECTOR == (
        'xpath=//*[@id="wfx_GMPOAsnSearch"]/div[3]/table'
    )
    assert sale_asn_create.PO_OK_SELECTOR == (
        'xpath=//*[@id="wfx_GMPOAsnSearch"]'
        "/table[1]/tbody/tr/td[3]/table/tbody/tr/td[3]"
    )


def test_sale_asn_order_grid_uses_exact_wfx_columns():
    assert sale_asn_create.ORDER_GRID_SELECTOR == "#gridOrderDetails_tblGridContent"
    assert sale_asn_create.ORDER_FIELD_COLUMNS == {
        "carton": "colTotalNoOfCartons",
        "gw": "colTotalGrossWeight",
        "nw": "colTotalNetWeight",
        "cbm": "colTotalVolume",
        "fob_price": "colFFTextField1",
        "service_price": "colFFTextField2",
        "cargo_ready_date": "colFFDate1",
    }


def test_sale_asn_style_details_targets_exact_hts_cell(monkeypatch):
    captured = {}

    class FakeFrame:
        def evaluate(self, script, spec):
            captured["script"] = script
            captured["spec"] = spec
            return {"ok": True, "style": "RVR-STYLE A", "column_id": "colHTSCode"}

    monkeypatch.setattr(
        sale_asn_create,
        "_edit_marked_table_cell",
        lambda frame, value: captured.update(frame=frame, value=value),
    )
    frame = FakeFrame()

    _set_style_hts_cell(frame, "STYLE A", "62014010")

    assert captured["spec"] == {"style": "STYLE A"}
    assert "#gridStyleDetails_tblGridContent" in captured["script"]
    assert "td#colStyle" in captured["script"]
    assert "td#colHTSCode" in captured["script"]
    assert captured["frame"] is frame
    assert captured["value"] == "62014010"


def test_sale_asn_order_grid_retries_only_rows_missing_after_final_ok(monkeypatch):
    rows = [
        {"source_row": 2, "po_no": "PO005500-DE-1"},
        {"source_row": 3, "po_no": "PO005501-DE-1"},
    ]
    main_frame = object()
    popup_frame = object()
    refreshed_frame = object()
    context = object()
    calls = {"wait": [], "retried": []}

    class FakeAdd:
        @property
        def first(self):
            return self

        def wait_for(self, **_kwargs):
            return None

        def click(self, **_kwargs):
            calls["add_clicked"] = True

    class FakeMainFrame:
        def locator(self, selector):
            assert selector == f"xpath={sale_asn_create.ADD_ORDER_XPATH}"
            return FakeAdd()

    main_frame = FakeMainFrame()

    def fake_wait(frame, waited_rows, timeout_s, *, allow_incomplete=False):
        calls["wait"].append((frame, timeout_s, allow_incomplete))
        assert list(waited_rows) == rows
        if allow_incomplete:
            return {sale_asn_create._fold("PO005500-DE-1")}
        return {sale_asn_create._fold(row["po_no"]) for row in rows}

    def fake_frame_with_selector(_context, selector, timeout_s):
        assert _context is context
        if selector == sale_asn_create.PO_POPUP_SELECTOR:
            if timeout_s < 1:
                raise sale_asn_create.PlaywrightTimeoutError("popup closed")
            return object(), popup_frame
        assert selector == "#sectionOrderDetails"
        return object(), refreshed_frame

    def fake_auto_add(frame, row, _log, *, final):
        calls["retried"].append((frame, row["po_no"], final))
        return True, [], "PO No"

    monkeypatch.setattr(sale_asn_create, "_wait_order_grid", fake_wait)
    monkeypatch.setattr(
        sale_asn_create,
        "_frame_with_selector",
        fake_frame_with_selector,
    )
    monkeypatch.setattr(sale_asn_create, "_auto_add_po", fake_auto_add)
    logs = []

    result = sale_asn_create._ensure_order_grid_rows(
        context,
        main_frame,
        rows,
        logs.append,
    )

    assert result is refreshed_frame
    assert calls["add_clicked"] is True
    assert calls["retried"] == [(popup_frame, "PO005501-DE-1", True)]
    assert calls["wait"] == [
        (main_frame, 10, True),
        (refreshed_frame, 15, False),
    ]
    assert any("còn thiếu 1 PO" in message for message in logs)
    assert logs[-1] == "[SALE ASN] Đã xác nhận đủ PO trong Order Details."


def test_sale_asn_resume_after_manual_final_ok_skips_closed_popup(monkeypatch):
    rows = [
        {"source_row": 2, "po_no": "PO-1", "invoice_no": "INV-1"},
    ]
    context = object()
    page = type("FakePage", (), {"context": context})()
    main_frame = object()
    selectors = []

    class FakePlaywright:
        def stop(self):
            return None

    class FakePlaywrightStarter:
        def start(self):
            return FakePlaywright()

    def fake_frame_with_selector(_context, selector, timeout_s):
        assert _context is context
        selectors.append((selector, timeout_s))
        assert selector == "#sectionOrderDetails"
        return page, main_frame

    monkeypatch.setattr(
        sale_asn_create,
        "sync_playwright",
        lambda: FakePlaywrightStarter(),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_active_wfx_page",
        lambda _playwright, _log: (object(), page),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_frame_with_selector",
        fake_frame_with_selector,
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_ensure_order_grid_rows",
        lambda _context, frame, _rows, _log: frame,
    )
    monkeypatch.setattr(sale_asn_create, "_fill_order_details", lambda *_args: None)
    monkeypatch.setattr(sale_asn_create, "_fill_style_details", lambda *_args: None)
    monkeypatch.setattr(sale_asn_create, "_fill_shipping", lambda *_args: None)

    result = sale_asn_create.run_sale_asn_create(
        "menu-xpath",
        "BUYER A",
        rows,
        start_index=len(rows),
        log=lambda _message: None,
    )

    assert result["code"] == "SALE_ASN_FORM_COMPLETED"
    assert selectors == [("#sectionOrderDetails", 15)]


def test_sale_asn_resume_shipping_uses_visible_shipping_tab_only(monkeypatch):
    rows = [{"source_row": 2, "po_no": "PO-1", "invoice_no": "INV-1"}]
    context = object()
    page = type("FakePage", (), {"context": context})()
    shipping_frame = object()
    selectors = []
    calls = []

    class FakePlaywright:
        def stop(self):
            return None

    class FakePlaywrightStarter:
        def start(self):
            return FakePlaywright()

    def fake_frame_with_selector(_context, selector, timeout_s):
        assert _context is context
        selectors.append((selector, timeout_s))
        return page, shipping_frame

    monkeypatch.setattr(
        sale_asn_create,
        "sync_playwright",
        lambda: FakePlaywrightStarter(),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_active_wfx_page",
        lambda _playwright, _log: (object(), page),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_frame_with_selector",
        fake_frame_with_selector,
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_fill_order_details",
        lambda *_args: calls.append("order"),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_fill_style_details",
        lambda *_args: calls.append("style"),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_fill_shipping",
        lambda *_args: ["Factory: option-not-found"],
    )

    result = sale_asn_create.run_sale_asn_create(
        "menu-xpath",
        "BUYER A",
        rows,
        start_index=len(rows),
        stage="shipping_info",
        log=lambda _message: None,
    )

    assert result["code"] == "SALE_ASN_FORM_COMPLETED"
    assert result["warning_count"] == 1
    assert result["warnings"] == ["Factory: option-not-found"]
    assert "Shipping Info đã bỏ qua 1 trường" in result["message"]
    assert selectors == [("#tabShippingInfo", 15)]
    assert calls == []


def test_sale_asn_can_skip_add_po_and_start_from_existing_order_grid(monkeypatch):
    rows = [{"source_row": 2, "po_no": "PO-1", "carton": "2"}]
    context = object()
    page = type("FakePage", (), {"context": context})()
    order_frame = object()
    calls = []

    class FakePlaywright:
        def stop(self):
            return None

    class FakePlaywrightStarter:
        def start(self):
            return FakePlaywright()

    monkeypatch.setattr(
        sale_asn_create,
        "sync_playwright",
        lambda: FakePlaywrightStarter(),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_active_wfx_page",
        lambda _playwright, _log: (object(), page),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_frame_with_selector",
        lambda selected_context, selector, timeout_s: (
            calls.append(("frame", selected_context, selector, timeout_s))
            or (page, order_frame)
        ),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_wait_order_grid",
        lambda frame, selected_rows, **kwargs: (
            calls.append(("wait", frame, list(selected_rows), kwargs))
            or {sale_asn_create._fold("PO-1")}
        ),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_ensure_order_grid_rows",
        lambda *_args: pytest.fail("Không được mở hoặc thêm lại PO"),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_fill_order_details",
        lambda frame, selected_rows, _log: calls.append(
            ("fill-order", frame, list(selected_rows))
        ),
    )

    result = sale_asn_create.run_sale_asn_create(
        "menu-xpath",
        "",
        rows,
        stage="order_details",
        skip_stages=("style_details", "shipping_info"),
        log=lambda _message: None,
    )

    assert result["code"] == "SALE_ASN_FORM_COMPLETED"
    assert result["add_po_selected"] is False
    assert ("fill-order", order_frame, rows) in calls
    assert calls[0][2] == "#sectionOrderDetails"


def test_shipping_info_skips_failed_field_and_continues(monkeypatch):
    calls = []
    logs = []

    class FakeTab:
        @property
        def first(self):
            return self

        def wait_for(self, **_kwargs):
            return None

        def click(self, **_kwargs):
            return None

    class FakeFrame:
        def locator(self, selector):
            assert selector == "#tabShippingInfo"
            return FakeTab()

    def fake_set_control(_frame, selector, value, mode, timeout_s):
        calls.append((selector, value, mode, timeout_s))
        if selector == "#ddlFactory":
            return {"ok": False, "reason": "option-not-found"}
        return {"ok": True}

    monkeypatch.setattr(sale_asn_create, "_set_control", fake_set_control)
    monkeypatch.setattr(sale_asn_create, "_wait", lambda *_args: None)

    warnings = sale_asn_create._fill_shipping(
        FakeFrame(),
        {
            "invoice_no": "INV-1",
            "invoice_date": "2026-08-01",
            "shipping_bill_no": "SB-1",
            "shipping_bill_date": "2026-08-02",
            "destination": "Germany",
            "factory": "PRO SPORTS GIAO THUY JSC",
        },
        logs.append,
    )

    assert warnings == [
        'Factory: WFX không có lựa chọn "PRO SPORTS GIAO THUY JSC"'
    ]
    assert calls[-1][0] == "#ddlNotify1"
    assert any("Shipping Info bỏ qua Factory: WFX không có lựa chọn" in item for item in logs)
    assert logs[-1] == (
        "[SALE ASN] Đã điền Shipping Info; bỏ qua 1 trường và chưa bấm Save."
    )


def test_sale_asn_table_value_confirmation_handles_wfx_formats():
    assert sale_asn_create._number_for_wfx("110", integer=True) == "110"
    assert sale_asn_create._number_for_wfx("498.99999999999994") == "499"
    assert sale_asn_create._table_value_matches("1085", "1,085.0000")
    assert sale_asn_create._table_value_matches("03/08/2026", "03 Aug 2026")
    assert not sale_asn_create._table_value_matches("110", "0")


def test_order_details_only_runner_never_enters_other_sale_asn_steps(monkeypatch):
    rows = [{"po_no": "PO-001", "carton": "2", "nw": "9.5"}]
    frame = object()
    page = type("FakePage", (), {"context": object()})()
    calls = []

    class FakePlaywright:
        def stop(self):
            calls.append("stop")

    class FakePlaywrightStarter:
        def start(self):
            return FakePlaywright()

    monkeypatch.setattr(
        sale_asn_create,
        "sync_playwright",
        lambda: FakePlaywrightStarter(),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_active_wfx_page",
        lambda _playwright, _log: (object(), page),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_frame_with_selector",
        lambda context, selector, timeout_s: (
            calls.append((context, selector, timeout_s)) or (page, frame)
        ),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_wait_order_grid",
        lambda selected_frame, selected_rows, **_kwargs: (
            calls.append(("wait", selected_frame, list(selected_rows)))
            or {sale_asn_create._fold("PO-001")}
        ),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_fill_order_details",
        lambda selected_frame, selected_rows, _log: calls.append(
            ("fill-order", selected_frame, list(selected_rows))
        ),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_fill_style_details",
        lambda *_args: pytest.fail("Không được chạy Style Details"),
    )
    monkeypatch.setattr(
        sale_asn_create,
        "_fill_shipping",
        lambda *_args: pytest.fail("Không được chạy Shipping Info"),
    )

    result = sale_asn_create.run_sale_asn_order_details(rows, lambda _message: None)

    assert result["code"] == "SALE_ASN_ORDER_DETAILS_COMPLETED"
    assert result["updated_fields"] == 2
    assert (page.context, sale_asn_create.ORDER_GRID_SELECTOR, 15) in calls
    assert any(call[0] == "fill-order" for call in calls if isinstance(call, tuple))


class _FakeSaleASNLogin:
    COMPANY_ID = "psh"
    CATALOG_XPATH = "catalog"

    def __init__(self):
        self.calls = []

    def scan_sale_asn_buyers(self, xpath, log=print):
        self.calls.append(("scan", xpath))
        return {
            "ok": True,
            "code": "SALE_ASN_BUYERS_SCANNED",
            "message": "buyers",
            "buyers": [{"label": "BUYER A", "value": "A"}],
        }

    def run_sale_asn_create(
        self,
        xpath,
        buyer,
        rows,
        start_index,
        log=print,
        *,
        stage="po",
        skip_stages=(),
        progress=None,
    ):
        self.calls.append(
            ("create", xpath, buyer, len(rows), start_index, stage, tuple(skip_stages))
        )
        if start_index == 0:
            return {
                "ok": True,
                "code": "SALE_ASN_PO_SELECTION_REQUIRED",
                "message": "manual",
                "next_index": 1,
            }
        return {
            "ok": True,
            "code": "SALE_ASN_FORM_COMPLETED",
            "message": "done",
        }


def test_panel_api_keeps_review_across_manual_po_checkpoint(tmp_path):
    source = tmp_path / "input.xlsx"
    _input_workbook(source, _valid_rows())
    login = _FakeSaleASNLogin()
    api = PanelAPI(login_module=login, prefs_module=prefs, base_dir=tmp_path / "data")

    scanned = api.scan_sale_asn_buyers()
    reviewed = api.prepare_sale_asn_create(str(source), "BUYER A")
    pending = api.start_sale_asn_create(reviewed["review_token"])
    completed = api.continue_sale_asn_create(reviewed["review_token"])
    expired = api.continue_sale_asn_create(reviewed["review_token"])

    assert scanned["buyers"] == [{"label": "BUYER A", "value": "A"}]
    assert reviewed["code"] == "SALE_ASN_CREATE_REVIEW_READY"
    assert pending["code"] == "SALE_ASN_PO_SELECTION_REQUIRED"
    assert completed["code"] == "SALE_ASN_FORM_COMPLETED"
    assert expired["code"] == "SALE_ASN_CREATE_REVIEW_EXPIRED"
    assert [call[4] for call in login.calls if call[0] == "create"] == [0, 1]


def test_panel_api_retries_or_skips_failed_sale_asn_stage(tmp_path):
    source = tmp_path / "input.xlsx"
    _input_workbook(source, _valid_rows())

    class FailingStageLogin(_FakeSaleASNLogin):
        def run_sale_asn_create(
            self,
            xpath,
            buyer,
            rows,
            start_index,
            log=print,
            *,
            stage="po",
            skip_stages=(),
            progress=None,
        ):
            self.calls.append(
                ("create", xpath, buyer, len(rows), start_index, stage, tuple(skip_stages))
            )
            if "style_details" not in skip_stages:
                return {
                    "ok": False,
                    "code": "SALE_ASN_FIELD_NOT_EDITABLE",
                    "message": "style failed",
                    "resumable": True,
                    "resume_stage": "style_details",
                    "stage_label": "Style Details",
                    "can_skip": True,
                }
            return {
                "ok": True,
                "code": "SALE_ASN_FORM_COMPLETED",
                "message": "done",
            }

    login = FailingStageLogin()
    api = PanelAPI(login_module=login, prefs_module=prefs, base_dir=tmp_path / "data")
    reviewed = api.prepare_sale_asn_create(str(source), "BUYER A")

    failed = api.start_sale_asn_create(reviewed["review_token"])
    completed = api.skip_sale_asn_create_step(reviewed["review_token"])

    assert failed["resume_stage"] == "style_details"
    assert failed["review_token"] == reviewed["review_token"]
    assert completed["code"] == "SALE_ASN_FORM_COMPLETED"
    assert login.calls[-1][5:] == ("style_details", ("style_details",))


def test_panel_api_retries_only_order_details_with_same_review(tmp_path):
    source = tmp_path / "order-details.xlsx"
    _order_details_workbook(
        source,
        [{"PO No": "PO-001", "Carton": 2, "NW": 9.5}],
    )

    class OrderDetailsLogin(_FakeSaleASNLogin):
        def run_sale_asn_order_details(self, rows, log=print):
            self.calls.append(("order-details", list(rows)))
            if len(self.calls) == 1:
                return {
                    "ok": False,
                    "code": "SALE_ASN_ORDER_ROWS_NOT_FOUND",
                    "message": "wrong Sale ASN",
                    "resumable": True,
                }
            return {
                "ok": True,
                "code": "SALE_ASN_ORDER_DETAILS_COMPLETED",
                "message": "done",
            }

    login = OrderDetailsLogin()
    api = PanelAPI(login_module=login, prefs_module=prefs, base_dir=tmp_path / "data")

    reviewed = api.prepare_sale_asn_order_details(str(source))
    pending = api.start_sale_asn_order_details(reviewed["review_token"])
    completed = api.start_sale_asn_order_details(reviewed["review_token"])
    expired = api.start_sale_asn_order_details(reviewed["review_token"])

    assert reviewed["code"] == "SALE_ASN_ORDER_DETAILS_REVIEW_READY"
    assert reviewed["po_count"] == 1
    assert reviewed["filled_count"] == 2
    assert pending["review_token"] == reviewed["review_token"]
    assert completed["code"] == "SALE_ASN_ORDER_DETAILS_COMPLETED"
    assert expired["code"] == "SALE_ASN_ORDER_REVIEW_EXPIRED"
    assert [call[0] for call in login.calls] == ["order-details", "order-details"]


def test_panel_api_starts_at_first_selected_stage_without_buyer(tmp_path):
    source = tmp_path / "continue.xlsx"
    _input_workbook(source, [{"PO No": "PO-001", "Carton": 2}])

    class ContinueLogin(_FakeSaleASNLogin):
        def run_sale_asn_create(
            self,
            xpath,
            buyer,
            rows,
            start_index,
            log=print,
            *,
            stage="po",
            skip_stages=(),
            progress=None,
        ):
            self.calls.append(
                (
                    "continue-selected",
                    xpath,
                    buyer,
                    list(rows),
                    start_index,
                    stage,
                    tuple(skip_stages),
                )
            )
            return {
                "ok": True,
                "code": "SALE_ASN_FORM_COMPLETED",
                "message": "done",
            }

    login = ContinueLogin()
    api = PanelAPI(login_module=login, prefs_module=prefs, base_dir=tmp_path / "data")

    reviewed = api.prepare_sale_asn_create(
        str(source),
        "",
        ["order_details"],
    )
    completed = api.start_sale_asn_create(reviewed["review_token"])

    assert reviewed["selected_stages"] == ["order_details"]
    assert completed["code"] == "SALE_ASN_FORM_COMPLETED"
    call = login.calls[0]
    assert call[2] == ""
    assert call[5] == "order_details"
    assert call[6] == ("po", "style_details", "shipping_info")


def test_stage_progress_numbers_follow_the_four_fixed_stages():
    seen = []

    def sink(stage, message, step, total, *, state="active"):
        seen.append((stage, message, step, total, state))

    for stage in sale_asn_create.SALE_ASN_STAGE_ORDER:
        sale_asn_create._emit_stage_progress(sink, stage, f"Đang điền {stage}")
    sale_asn_create._emit_stage_progress(sink, "style_details", "bỏ", state="skipped")

    # Bộ đếm luôn tính trên bốn bước cố định, không theo số bước user chọn.
    assert [(item[0], item[2], item[3]) for item in seen] == [
        ("po", 1, 4),
        ("order_details", 2, 4),
        ("style_details", 3, 4),
        ("shipping_info", 4, 4),
        ("style_details", 3, 4),
    ]
    assert seen[-1][4] == "skipped"


def test_stage_progress_is_optional_and_never_breaks_the_flow():
    def broken(*_args, **_kwargs):
        raise ValueError("callback hỏng")

    # Không có callback, và callback lỗi, đều không được ném ra ngoài.
    sale_asn_create._emit_stage_progress(None, "po", "x")
    sale_asn_create._emit_stage_progress(broken, "po", "x")


def test_panel_api_streams_sale_asn_progress_with_its_own_method(tmp_path):
    source = tmp_path / "input.xlsx"
    _input_workbook(source, _valid_rows())
    payloads = []

    class ProgressLogin(_FakeSaleASNLogin):
        def run_sale_asn_create(
            self,
            xpath,
            buyer,
            rows,
            start_index,
            log=print,
            *,
            stage="po",
            skip_stages=(),
            progress=None,
        ):
            progress("order_details", "Đang điền Order Details", 2, 4)
            return {
                "ok": True,
                "code": "SALE_ASN_FORM_COMPLETED",
                "message": "done",
            }

    api = PanelAPI(
        login_module=ProgressLogin(),
        prefs_module=prefs,
        base_dir=tmp_path / "data",
    )
    api.set_progress_sink(payloads.append)
    reviewed = api.prepare_sale_asn_create(str(source), "BUYER A")
    api.start_sale_asn_create(reviewed["review_token"])

    # Payload phải mang method của chính flow Sale ASN để UI không đè thẻ GDN.
    assert [item["method"] for item in payloads] == ["start_sale_asn_create"]
    assert payloads[0]["stage"] == "order_details"
    assert payloads[0]["step"] == 2
    assert payloads[0]["total"] == 4
    assert payloads[0]["state"] == "active"
