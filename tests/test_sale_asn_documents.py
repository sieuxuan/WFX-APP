from io import BytesIO

import pytest
from openpyxl import Workbook

import wfx_panel.automation.sale_asn_documents as sale_asn_documents
from wfx_panel.automation.sale_asn_documents import (
    _CLICK_SALE_ASN_DOCS_JS,
    _SALE_ASN_ROWS_JS,
    _SALE_ASN_SCROLL_STATE_JS,
    _SALE_ASN_SCROLL_TO_JS,
    DOCUMENTS_FRAME_TIMEOUT_SECONDS,
    REPORT_DOWNLOAD_START_TIMEOUT_SECONDS,
    REPORT_READY_TIMEOUT_SECONDS,
    _click_sale_asn_docs,
    _close_sale_asn_document_popups,
    _download_report_excel,
    _merge_sale_asn_row_payloads,
    _report_export_url,
    _report_workbook_kind,
    _sale_asn_horizontal_positions,
    _select_sale_asn_row,
    _validate_report_kind,
)


def _report_bytes(title: str) -> bytes:
    workbook = Workbook()
    workbook.active["A1"] = title
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def test_download_report_uses_authenticated_ssrs_request_without_browser_click(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "packing-list-source.xlsx"
    payload = _report_bytes("PACKING LIST")

    class FakeFrame:
        url = "https://wfx.example/report/viewer"

    class FakeResponse:
        ok = True
        status = 200

        def body(self):
            return payload

    class FakeRequest:
        def get(self, url, **kwargs):
            assert url == "https://wfx.example/export?Format=EXCELOPENXML"
            assert kwargs["timeout"] == 180_000
            assert kwargs["fail_on_status_code"] is False
            return FakeResponse()

    class FakeContext:
        request = FakeRequest()

    monkeypatch.setattr(
        sale_asn_documents,
        "_report_export_url",
        lambda _frame: "/export?Format=",
    )

    _download_report_excel(
        FakeContext(),
        FakeFrame(),
        target,
        "Packing List",
        lambda _message: None,
    )

    assert target.read_bytes() == payload
    assert _report_workbook_kind(target) == "packing"


def test_report_kind_validation_rejects_packing_list_as_buyer_invoice(tmp_path):
    target = tmp_path / "wrong-report.xlsx"
    target.write_bytes(_report_bytes("PACKING LIST"))

    with pytest.raises(RuntimeError, match="trả nhầm Packing List"):
        _validate_report_kind(target, "Buyer Invoice")


def test_report_kind_validation_accepts_unknown_template(tmp_path):
    target = tmp_path / "custom-report.xlsx"
    target.write_bytes(_report_bytes("CUSTOM SHIPPING DOCUMENT"))

    _validate_report_kind(target, "Buyer Invoice")


def test_sale_asn_document_downloads_allow_slow_wfx_reports():
    assert DOCUMENTS_FRAME_TIMEOUT_SECONDS == 60
    assert REPORT_READY_TIMEOUT_SECONDS == 180
    assert REPORT_DOWNLOAD_START_TIMEOUT_SECONDS == 180


def test_report_export_url_is_empty_until_ssrs_export_is_initialized():
    class FakeFrame:
        def __init__(self, value):
            self.value = value

        def evaluate(self, script):
            assert "ExportUrlBase" in script
            return self.value

    assert _report_export_url(FakeFrame(None)) == ""
    assert _report_export_url(FakeFrame(" /report/export?Format= ")) == (
        "/report/export?Format="
    )


def test_select_exact_invoice_does_not_require_docs_column_to_be_rendered():
    row = {
        "row_key": "4",
        "invoice_no": "104-PRO-2026",
        "selected": False,
    }

    selected = _select_sale_asn_row(
        {"rows": [row]},
        "invoice_no",
        "104-PRO-2026",
    )

    assert selected == row


def test_rows_reader_uses_nested_grid_button_value_for_invoice_number():
    assert "element.querySelectorAll(" in _SALE_ASN_ROWS_JS
    assert "candidate?.value" in _SALE_ASN_ROWS_JS
    assert "candidate?.getAttribute?.('value')" in _SALE_ASN_ROWS_JS


def test_row_payloads_merge_invoice_from_another_horizontal_viewport():
    merged = _merge_sale_asn_row_payloads(
        [
            {
                "rows": [
                    {"row_key": "4", "invoice_no": "", "selected": True},
                ],
                "noRows": False,
            },
            {
                "rows": [
                    {
                        "row_key": "4",
                        "invoice_no": "104-PRO-2026",
                        "selected": False,
                    },
                ],
                "noRows": False,
            },
        ]
    )

    assert merged == {
        "rows": [
            {
                "row_key": "4",
                "invoice_no": "104-PRO-2026",
                "selected": True,
            }
        ],
        "noRows": False,
    }


def test_select_invoice_does_not_fall_back_to_a_different_single_row():
    with pytest.raises(RuntimeError, match="SALE_ASN_INVOICE_NOT_FOUND"):
        _select_sale_asn_row(
            {
                "rows": [
                    {
                        "row_key": "1",
                        "invoice_no": "A-DIFFERENT-INVOICE",
                        "selected": False,
                    }
                ]
            },
            "invoice_no",
            "104-PRO-2026",
        )


def test_one_selected_row_resolves_duplicate_exact_invoices():
    selected = _select_sale_asn_row(
        {
            "rows": [
                {
                    "row_key": "1",
                    "invoice_no": "104-PRO-2026",
                    "selected": False,
                },
                {
                    "row_key": "2",
                    "invoice_no": "104-PRO-2026",
                    "selected": True,
                },
            ]
        },
        "invoice_no",
        "104-PRO-2026",
    )

    assert selected["row_key"] == "2"


def test_horizontal_positions_cover_reordered_column_at_any_grid_location():
    assert _sale_asn_horizontal_positions(
        {"current": 600, "maximum": 1000, "viewport": 400}
    ) == [600, 0, 300, 900, 1000]


class _FakeFrame:
    def __init__(self):
        self.waited = 0

    def wait_for_timeout(self, milliseconds):
        self.waited += milliseconds


class _FakeRoot:
    def __init__(self):
        self.position = 0
        self.visited = []

    def evaluate(self, script, argument=None):
        if script == _SALE_ASN_SCROLL_STATE_JS:
            return {"current": 0, "maximum": 800, "viewport": 400}
        if script == _SALE_ASN_SCROLL_TO_JS:
            self.position = argument
            self.visited.append(argument)
            return True
        if script == _CLICK_SALE_ASN_DOCS_JS:
            return self.position == 600 and argument == {"rowKey": "7"}
        raise AssertionError("Unexpected script")


def test_click_docs_sweeps_horizontally_until_reordered_column_is_rendered():
    frame = _FakeFrame()
    root = _FakeRoot()

    clicked = _click_sale_asn_docs(frame, root, "7", lambda _message: None)

    assert clicked is True
    assert root.visited == [0, 300, 600]
    assert frame.waited == 450


def test_document_cleanup_closes_only_popups_opened_by_docs():
    class FakePage:
        def __init__(self):
            self.closed = False

        def is_closed(self):
            return self.closed

        def close(self, **_kwargs):
            self.closed = True

    list_page = FakePage()
    docs_page = FakePage()
    report_page = FakePage()
    context = type(
        "FakeContext",
        (),
        {"pages": [list_page, docs_page, report_page]},
    )()

    _close_sale_asn_document_popups(context, {id(list_page)}, lambda _message: None)

    assert list_page.closed is False
    assert docs_page.closed is True
    assert report_page.closed is True
