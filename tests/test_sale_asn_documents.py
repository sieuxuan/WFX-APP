import pytest

import wfx_panel.automation.sale_asn_documents as sale_asn_documents
from wfx_panel.automation.sale_asn_documents import (
    _CLICK_SALE_ASN_DOCS_JS,
    _SALE_ASN_ROWS_JS,
    _SALE_ASN_SCROLL_STATE_JS,
    _SALE_ASN_SCROLL_TO_JS,
    DOCUMENTS_FRAME_TIMEOUT_SECONDS,
    REPORT_DOWNLOAD_START_TIMEOUT_SECONDS,
    REPORT_EXCEL_FORMAT_SELECTOR,
    REPORT_EXCEL_LABEL_SELECTOR,
    REPORT_EXPORT_MENU_TIMEOUT_SECONDS,
    REPORT_READY_TIMEOUT_SECONDS,
    _click_sale_asn_docs,
    _close_sale_asn_document_popups,
    _find_report_excel_action,
    _merge_sale_asn_row_payloads,
    _sale_asn_horizontal_positions,
    _select_sale_asn_row,
)


def test_download_report_uses_native_file_when_cdp_download_event_is_missing(
    tmp_path,
    monkeypatch,
):
    """Chrome lưu file native vẫn phải được đưa vào pipeline ghép Sale ASN."""

    source = tmp_path / "Report.xlsx"
    source.write_bytes(b"native report")
    target = tmp_path / "packing-list-source.xlsx"

    class FakeAction:
        def evaluate(self, _script):
            return None

    class FakeLocator:
        first = FakeAction()

    class FakeFrame:
        def locator(self, selector):
            assert selector == sale_asn_documents.REPORT_EXPORT_SELECTOR
            return FakeLocator()

    class FakePage:
        def on(self, event, _callback):
            assert event == "download"

        def remove_listener(self, event, _callback):
            assert event == "download"

    class FakeContext:
        pages = [FakePage()]

        def on(self, event, _callback):
            assert event == "page"

        def remove_listener(self, event, _callback):
            assert event == "page"

    clock = iter(index / 100 for index in range(100))
    monkeypatch.setattr(sale_asn_documents.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(sale_asn_documents, "_wait", lambda *_args: None)
    monkeypatch.setattr(sale_asn_documents, "snapshot_downloads", lambda: {})
    monkeypatch.setattr(
        sale_asn_documents,
        "_find_report_excel_action",
        lambda _context, frame: (frame, FakeAction()),
    )
    monkeypatch.setattr(
        sale_asn_documents,
        "native_download_candidate",
        lambda *_args, **_kwargs: (source, (source.stat().st_size, 1)),
        raising=False,
    )
    monkeypatch.setattr(
        sale_asn_documents,
        "REPORT_DOWNLOAD_START_TIMEOUT_SECONDS",
        0.5,
    )

    sale_asn_documents._download_report_excel(
        FakeContext(),
        FakeFrame(),
        target,
        "Packing List",
        lambda _message: None,
    )

    assert target.read_bytes() == b"native report"


def test_sale_asn_document_downloads_allow_slow_wfx_reports():
    assert DOCUMENTS_FRAME_TIMEOUT_SECONDS == 60
    assert REPORT_READY_TIMEOUT_SECONDS == 180
    assert REPORT_EXPORT_MENU_TIMEOUT_SECONDS == 30
    assert REPORT_DOWNLOAD_START_TIMEOUT_SECONDS == 180


def test_report_excel_selector_supports_report_viewer_markup_variants():
    assert '[onclick*="EXCELOPENXML"]' in REPORT_EXCEL_FORMAT_SELECTOR
    assert '[href*="EXCELOPENXML"]' in REPORT_EXCEL_FORMAT_SELECTOR
    assert 'a[title="Excel"]' in REPORT_EXCEL_LABEL_SELECTOR


def test_report_excel_action_accepts_hidden_explicit_openxml_link():
    class FakeAction:
        def __init__(self, name, visible=False):
            self.name = name
            self.visible = visible

        def is_visible(self):
            return self.visible

    class FakeLocator:
        def __init__(self, actions):
            self.actions = actions

        def count(self):
            return len(self.actions)

        def nth(self, index):
            return self.actions[index]

    class FakeFrame:
        def __init__(self, explicit=(), labelled=()):
            self.explicit = list(explicit)
            self.labelled = list(labelled)

        def locator(self, selector):
            if selector == REPORT_EXCEL_FORMAT_SELECTOR:
                return FakeLocator(self.explicit)
            if selector == REPORT_EXCEL_LABEL_SELECTOR:
                return FakeLocator(self.labelled)
            raise AssertionError(selector)

    hidden_excel = FakeAction("hidden-openxml")
    report_frame = FakeFrame(explicit=[hidden_excel])
    page = type("FakePage", (), {"frames": [report_frame]})()
    context = type("FakeContext", (), {"pages": [page]})()

    found_frame, found_action = _find_report_excel_action(context, report_frame)

    assert found_frame is report_frame
    assert found_action is hidden_excel


def test_report_excel_action_finds_visible_menu_in_another_frame():
    class FakeAction:
        def __init__(self, visible):
            self.visible = visible

        def is_visible(self):
            return self.visible

    class FakeLocator:
        def __init__(self, actions):
            self.actions = actions

        def count(self):
            return len(self.actions)

        def nth(self, index):
            return self.actions[index]

    class FakeFrame:
        def __init__(self, explicit=(), labelled=()):
            self.explicit = list(explicit)
            self.labelled = list(labelled)

        def locator(self, selector):
            actions = (
                self.explicit
                if selector == REPORT_EXCEL_FORMAT_SELECTOR
                else self.labelled
            )
            return FakeLocator(actions)

    report_frame = FakeFrame()
    visible_excel = FakeAction(True)
    menu_frame = FakeFrame(labelled=[visible_excel])
    page = type("FakePage", (), {"frames": [report_frame, menu_frame]})()
    context = type("FakeContext", (), {"pages": [page]})()

    found_frame, found_action = _find_report_excel_action(context, report_frame)

    assert found_frame is menu_frame
    assert found_action is visible_excel


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
