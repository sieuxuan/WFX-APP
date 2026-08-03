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
    SaleASNWorkbookError,
    read_sale_asn_workbook,
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


def test_sale_asn_table_value_confirmation_handles_wfx_formats():
    assert sale_asn_create._number_for_wfx("110", integer=True) == "110"
    assert sale_asn_create._number_for_wfx("498.99999999999994") == "499"
    assert sale_asn_create._table_value_matches("1085", "1,085.0000")
    assert sale_asn_create._table_value_matches("03/08/2026", "03 Aug 2026")
    assert not sale_asn_create._table_value_matches("110", "0")


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
