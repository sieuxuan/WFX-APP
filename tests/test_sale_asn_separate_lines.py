"""Các dòng màu cùng PO + Style phải giữ Qty, giá và đích ghi riêng."""

from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

from wfx_panel.automation.sale_asn_create import order_details, po, price_check
from wfx_panel.automation.sale_asn_create.line_mapping import (
    _remember_line_selection,
    _used_line_selections,
)


def _rows(same_qty=False):
    return [
        {
            "source_row": 2,
            "po_no": "PO133360",
            "style_no": "GMPA14590",
            "qty": "15",
            "price": "24.08",
            "carton": "6",
            "nw": "40.2",
            "gw": "49.2",
            "cbm": "0.24",
            "fob_price": "24.08",
            "cargo_ready_date": "2026-10-26",
        },
        {
            "source_row": 3,
            "po_no": "PO133360",
            "style_no": "GMPA14590",
            "qty": "15" if same_qty else "117",
            "price": "23.04",
            "fob_price": "23.04",
            "cargo_ready_date": "2026-10-27",
        },
    ]


def _candidate(row_id, quantity, oc):
    return {
        "selection_name": "optShipmentId",
        "selection_value": f"77400_{row_id}",
        "selection_order_id": f"parent-{row_id}",
        "row_index": int(row_id),
        "po_no": "PO133360",
        "style_no": "GMPA14590",
        "dispatched_qty": str(quantity),
        "cell_values": [f"{oc}/PO133360"],
    }


def _markup(same_qty=False):
    body = ""
    for row_id, qty, oc in (
        ("1002", "15" if same_qty else "117", "PSG-RR-26-5000.2"),
        ("1001", "15", "PSG-RR-26-5000.1"),
    ):
        body += (
            f'<tr class="trContent" id="{row_id}"><td id="colOrderRefNum">PO133360</td>'
            '<td id="colStyle"><span title="RR-GMPA14590-PANT">RR-GMPA14590-PANT</span></td>'
            f'<td id="colProformaInvoiceNum">{oc}</td>'
            f'<td id="colTotalShippingQty"><span title="{qty}">{qty}</span><span>{qty}</span></td>'
            + "".join(
                f'<td id="{column}"><input value="0"></td>'
                for column in (
                    "colTotalNoOfCartons",
                    "colTotalGrossWeight",
                    "colTotalNetWeight",
                    "colTotalVolume",
                    "colFFTextField1",
                    "colFFTextField2",
                )
            )
            + '<td id="colFFDate1"><input value=""></td></tr>'
        )
    return f'<table id="gridOrderDetails_tblGridContent">{body}</table>'


@pytest.mark.parametrize("same_qty", [False, True])
def test_each_source_line_keeps_its_own_wfx_row_prices_and_dates_on_retry(same_qty):
    rows = _rows(same_qty)
    bindings = {}
    _remember_line_selection(
        bindings, rows[0], [_candidate("1001", 15, "PSG-RR-26-5000.1")]
    )
    _remember_line_selection(
        bindings, rows[1], [_candidate("1002", rows[1]["qty"], "PSG-RR-26-5000.2")]
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.set_content(_markup(same_qty))
            for _attempt in range(2):
                order_details._fill_order_details(
                    page, rows, lambda _m: None, line_bindings=bindings
                )
                assert (
                    page.locator('tr[id="1001"] #colFFTextField1 input').input_value()
                    == "24.08"
                )
                assert (
                    page.locator('tr[id="1002"] #colFFTextField1 input').input_value()
                    == "23.04"
                )
                assert (
                    page.locator(
                        'tr[id="1001"] #colTotalNoOfCartons input'
                    ).input_value()
                    == "6"
                )
                assert (
                    page.locator(
                        'tr[id="1002"] #colTotalNoOfCartons input'
                    ).input_value()
                    == "0"
                )
                assert (
                    page.locator('tr[id="1001"] #colFFDate1 input').input_value()
                    == "26 Oct 2026"
                )
                assert (
                    page.locator('tr[id="1002"] #colFFDate1 input').input_value()
                    == "27 Oct 2026"
                )
                page.locator("tbody").evaluate(
                    "body => body.appendChild(body.firstElementChild)"
                )
        finally:
            browser.close()
    shipments = [
        {
            "order_no": "PSG-RR-26-5000.2/PO133360",
            "article": "GMPA14590",
            "qty": rows[1]["qty"],
            "price": "23.04",
        },
        {
            "order_no": "PSG-RR-26-5000.1/PO133360",
            "article": "GMPA14590",
            "qty": "15",
            "price": "24.08",
        },
    ]
    comparisons, totals = price_check._price_check_rows(
        rows, shipments, line_bindings=bindings
    )
    assert [item["source_rows"] for item in comparisons] == [[2], [3]]
    assert [item["file_price"] for item in comparisons] == ["24.08", "23.04"]
    assert [item["system_qty"] for item in comparisons] == [row["qty"] for row in rows]
    assert all(item["status"] == "ok" for item in comparisons)
    expected_value = sum(Decimal(row["qty"]) * Decimal(row["price"]) for row in rows)
    assert Decimal(totals["file_total_value"]) == expected_value


def test_an_existing_form_can_match_distinct_quantities_without_a_po_binding():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.set_content(_markup())
            order_details._fill_order_details(page, _rows(), lambda _m: None)
            assert (
                page.locator('tr[id="1001"] #colFFTextField1 input').input_value()
                == "24.08"
            )
            assert (
                page.locator('tr[id="1002"] #colFFTextField1 input').input_value()
                == "23.04"
            )
        finally:
            browser.close()


def test_ambiguous_color_rows_do_not_write_any_fields_without_a_binding():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.set_content(_markup(True))
            with pytest.raises(RuntimeError, match="SALE_ASN_TABLE_MAPPING_FAILED"):
                order_details._fill_order_details(page, _rows(True), lambda _m: None)
            assert page.locator("#colFFTextField1 input").evaluate_all(
                "inputs => inputs.every(input => input.value === '0')"
            )
        finally:
            browser.close()


def test_already_selected_dispatch_rows_are_not_added_again_for_another_color(
    monkeypatch,
):
    rows = _rows()
    candidates = [
        _candidate("1001", 15, "PSG-RR-26-5000.1"),
        _candidate("1002", 117, "PSG-RR-26-5000.2"),
    ]
    added = []
    monkeypatch.setattr(po, "_search_po", lambda *_a, **_k: candidates)
    monkeypatch.setattr(
        po,
        "_add_selected_po_candidates",
        lambda _f, _r, chosen, _l, **_k: added.append(chosen),
    )
    bindings = {}
    for row in rows:
        query = {
            **row,
            "_used_line_selections": _used_line_selections(bindings, row["source_row"]),
        }
        ok, chosen, _reason = po._auto_add_po(
            None, query, lambda _m: None, search_fields=("po",)
        )
        assert ok
        _remember_line_selection(bindings, row, chosen)
    assert [[item["selection_value"] for item in group] for group in added] == [
        ["77400_1001"],
        ["77400_1002"],
    ]


def test_price_check_without_bindings_keeps_two_prices_and_never_reuses_a_shipment():
    rows = _rows(True)
    shipments = [
        {"po_no": "PO133360", "article": "GMPA14590", "qty": "15", "price": "23.04"},
        {"po_no": "PO133360", "article": "GMPA14590", "qty": "15", "price": "24.08"},
    ]
    comparisons, totals = price_check._price_check_rows(rows, shipments)
    assert len(comparisons) == 2
    assert all(item["status"] == "ok" for item in comparisons)
    assert totals["file_total_qty"] == "30"


def test_stale_wfx_ticks_are_cleared_before_adding_the_next_color(monkeypatch):
    monkeypatch.setattr(po, "PO_RESULTS_TABLE_SELECTOR", "#results")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.set_content("""<table id="results"><tbody>
              <tr><td><input type="checkbox" name="optShipmentId" value="77400_1001" orderid="parent-1001" checked></td></tr>
              <tr><td><input type="checkbox" name="optShipmentId" value="77400_1002" orderid="parent-1002"></td></tr>
              </tbody></table>
              <a id="lnkAddnContinue" onclick="window.added=[...document.querySelectorAll('#results input:checked')].map(input=>input.value)">Add</a>""")
            chosen = {**_candidate("1002", 117, "PSG-RR-26-5000.2"), "row_index": 1}
            po._add_selected_po_candidates(
                page, _rows()[1], [chosen], lambda _m: None, final=False
            )
            assert page.evaluate("window.added") == ["77400_1002"]
        finally:
            browser.close()


def test_zero_qty_sizes_do_not_make_an_otherwise_unique_color_ambiguous():
    rows = _rows()
    shipments = [
        {"po_no": "PO133360", "article": "GMPA14590", "qty": "15", "price": "24.08"},
        {"po_no": "PO133360", "article": "GMPA14590", "qty": "0", "price": "24.08"},
        {"po_no": "PO133360", "article": "GMPA14590", "qty": "117", "price": "23.04"},
    ]
    comparisons, _totals = price_check._price_check_rows(rows, shipments)
    assert all(item["status"] == "ok" for item in comparisons)


def test_a_missing_second_color_is_not_hidden_by_reusing_the_first_shipment():
    rows = _rows(True)
    rows[1]["price"] = rows[0]["price"]
    shipments = [
        {"po_no": "PO133360", "article": "GMPA14590", "qty": "15", "price": "24.08"}
    ]
    comparisons, _totals = price_check._price_check_rows(rows, shipments)
    assert [item["status"] for item in comparisons] == ["ok", "shipment_not_found"]


def test_binding_reads_the_oc_for_this_po_and_ignores_slashes_in_a_style():
    state = {}
    candidate = _candidate("1001", 15, "PSG-RR-26-5000.1")
    candidate["cell_values"].insert(0, "PSG-STYLE/MODEL")
    _remember_line_selection(state, _rows()[0], [candidate])
    assert state[2]["oc_refs"] == ["psg rr 26 5000 1"]


def _combined_rows_and_bindings():
    rows = _rows()
    rows[0].update(qty="74", price="24.26", fob_price="24.26")
    rows[1].update(qty="364", price="23.46", fob_price="23.46", carton="9")
    candidate = _candidate("1001", 438, "PSG-RR-26-5000.1")
    bindings = {}
    _remember_line_selection(bindings, rows[0], [{**candidate, "_combined_member": 3}])
    return rows, bindings


@pytest.mark.parametrize("split_in_order_grid", [False, True])
def test_combined_order_details_uses_the_actual_grid_layout(monkeypatch, split_in_order_grid):
    rows, bindings = _combined_rows_and_bindings()
    quantities = ["74", "364"] if split_in_order_grid else ["438"]

    class Frame:
        def evaluate(self, *_args):
            return [
                {
                    "row_id": str(index + 1002) if split_in_order_grid else "1001",
                    "po_no": "PO133360",
                    "style_no": "GMPA14590",
                    "oc_no": "PSG-RR-26-5000.1",
                    "qty": qty,
                }
                for index, qty in enumerate(quantities)
            ]

    writes = []
    dates = []
    monkeypatch.setattr(
        order_details, "_set_order_grid_cell",
        lambda _f, _p, _s, col, value, *, row_id, **_k: writes.append((row_id, col, value)),
    )
    monkeypatch.setattr(
        order_details, "_fill_order_cargo_ready_dates",
        lambda _f, order_rows, _l, **_k: dates.extend(order_rows),
    )

    order_details._fill_order_details(Frame(), rows, lambda _m: None, line_bindings=bindings)

    if split_in_order_grid:
        assert ("1002", "colFFTextField1", "24.26") in writes
        assert ("1003", "colFFTextField1", "23.46") in writes
        assert dates == rows
    else:
        assert ("1001", "colTotalNoOfCartons", "15") in writes
        assert all(row_id == "1001" and col != "colFFTextField1" for row_id, col, _ in writes)
        assert len(dates) == 1 and dates[0]["_skip_cargo_ready_date"]
    assert [row["qty"] for row in rows] == ["74", "364"]


@pytest.mark.parametrize("wfx_split_by_price", [False, True])
def test_combined_price_check_uses_original_qty_times_price(wfx_split_by_price):
    rows, bindings = _combined_rows_and_bindings()
    shipment = {"order_no": "PSG-RR-26-5000.1/PO133360", "article": "GMPA14590"}
    if wfx_split_by_price:
        shipments = [{**shipment, "qty": row["qty"], "price": row["price"]} for row in rows]
    else:
        shipments = [{**shipment, "qty": "438", "price": "23.46"}]
    comparisons, totals = price_check._price_check_rows(rows, shipments, line_bindings=bindings)

    assert len(comparisons) == 1
    comparison = comparisons[0]
    assert comparison["source_rows"] == [2, 3]
    assert comparison["qty_ok"] is True
    assert comparison["price_ok"] is wfx_split_by_price
    assert comparison["status"] == ("ok" if wfx_split_by_price else "system_price_ambiguous")
    assert totals["file_total_qty"] == "438"
    assert totals["file_total_value"] == "10334.68"
