import pytest

from wfx_panel.automation.sale_asn_documents import (
    _CLICK_SALE_ASN_DOCS_JS,
    _SALE_ASN_SCROLL_STATE_JS,
    _SALE_ASN_SCROLL_TO_JS,
    _click_sale_asn_docs,
    _sale_asn_horizontal_positions,
    _select_sale_asn_row,
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
