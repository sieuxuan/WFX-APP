from pathlib import Path

from wfx_panel.automation import grn


def _search_result(*rows):
    return {
        "ok": True,
        "code": "RMPO_RESULTS_READY",
        "rmpo_rows": list(rows),
    }


def test_partial_rmpo_number_resolves_to_the_only_full_order(monkeypatch):
    monkeypatch.setattr(
        grn,
        "search_rmpo_list",
        lambda *_args: _search_result(
            {
                "order_no": "PSW-TRM-23-2345",
                "supplier": "Acme",
                "status": "Part Received",
            }
        ),
    )

    order_no, supplier, error = grn._resolve_rmpo("xpath", "2345", print)

    assert error is None
    assert order_no == "PSW-TRM-23-2345"
    assert supplier == "Acme"


def test_partial_rmpo_number_requires_a_unique_result(monkeypatch):
    monkeypatch.setattr(
        grn,
        "search_rmpo_list",
        lambda *_args: _search_result(
            {"order_no": "PSW-23-2345", "supplier": "A", "status": "Save"},
            {"order_no": "PSW-24-2345", "supplier": "B", "status": "Save"},
        ),
    )

    order_no, supplier, error = grn._resolve_rmpo("xpath", "2345", print)

    assert order_no is None
    assert supplier is None
    assert error["code"] == "GRN_RMPO_AMBIGUOUS"


def test_received_rmpo_cannot_start_another_receipt(monkeypatch):
    monkeypatch.setattr(
        grn,
        "search_rmpo_list",
        lambda *_args: _search_result(
            {
                "order_no": "PSW-TRM-23-2345",
                "supplier": "Acme",
                "status": "Received",
            }
        ),
    )

    order_no, supplier, error = grn._resolve_rmpo("xpath", "2345", print)

    assert order_no is None
    assert supplier is None
    assert error["code"] == "GRN_ALREADY_RECEIVED"
    assert "không thể nhập thêm" in error["message"]


def test_matched_rmpo_reports_missing_supplier_separately(monkeypatch):
    monkeypatch.setattr(
        grn,
        "search_rmpo_list",
        lambda *_args: _search_result(
            {"order_no": "PSW-TRM-23-2345", "supplier": "", "status": "Save"}
        ),
    )

    _order_no, _supplier, error = grn._resolve_rmpo("xpath", "2345", print)

    assert error["code"] == "GRN_RMPO_SUPPLIER_NOT_FOUND"


def test_grn_search_never_fills_the_filter_checkbox():
    source = Path(grn.__file__).read_text(encoding="utf-8")

    assert '"#chk_8", "#txtDocNum"' in source
    assert '"#chk_9", "#txtOrderNum"' in source
    assert '"#chk_6"' in source
    assert "#row_txtFromGRNDate" in source
    assert 'field.dispatch_event("change")' in source
    assert "checkbox.check(" not in source
    assert "checkbox.uncheck(" not in source
    assert "if (element.checked) element.click()" in source
    assert "def _click_grn_search" in source
    assert "input[type='button'][value='Search' i]" in source
    assert "a[onclick*='PrintGRN(']" in source
    assert "ReOrder('GRNNum')" not in source
    assert "def _wait_grn_result_opened" in source
