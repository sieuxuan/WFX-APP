from types import SimpleNamespace

from wfx_panel.automation import oc
from wfx_panel.automation.oc import _status_kind


class _Lease:
    def stop(self):
        return None


def _stub_edi_before_transaction(monkeypatch, rows):
    monkeypatch.setattr(
        oc,
        "sync_playwright",
        lambda: SimpleNamespace(start=_Lease),
    )
    monkeypatch.setattr(oc, "_active_wfx_page", lambda *_args: (object(), object()))
    monkeypatch.setattr(oc, "_open_edi_form", lambda *_args: None)
    monkeypatch.setattr(oc, "_process_package", lambda *_args: None)
    monkeypatch.setattr(
        oc,
        "_toolbar_link",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            oc.PlaywrightTimeoutError("no separate resolution link")
        ),
    )
    monkeypatch.setattr(oc, "_wait_statuses", lambda *_args: rows)


def test_edi_status_kind_distinguishes_success_failure_and_pending():
    assert _status_kind("Success") == "success"
    assert _status_kind("Mapping Resolved") == "success"
    assert _status_kind("Validation Failed") == "failed"
    assert _status_kind("Pending") == "pending"


def test_select_exact_option_waits_for_package_options(monkeypatch):
    class Option:
        def get_attribute(self, name):
            return "1" if name == "value" else "StandardSalesOrder"

        def inner_text(self):
            return "StandardSalesOrder"

    class Options:
        reads = 0

        def count(self):
            self.reads += 1
            return 0 if self.reads == 1 else 1

        def nth(self, _index):
            return Option()

    class Select:
        selected = ""
        mousedowns = 0

        def __init__(self):
            self.options = Options()

        def locator(self, selector):
            assert selector == "option"
            return self.options

        def dispatch_event(self, event, *, timeout):
            assert event == "mousedown"
            assert timeout == 2_000
            self.mousedowns += 1

        def select_option(self, *, value, timeout):
            assert timeout == 5_000
            self.selected = value

        def input_value(self, *, timeout):
            assert timeout == 1_000
            return self.selected

    select = Select()
    monkeypatch.setattr(
        oc,
        "_visible_in_frames",
        lambda *_args, **_kwargs: (object(), select),
    )
    monkeypatch.setattr(oc, "_wait", lambda *_args: None)

    selected = oc._select_exact_option(
        object(), "#ddlPackage", "1", "StandardSalesOrder", "Package", timeout_s=1
    )

    assert selected == "1"
    assert select.mousedowns >= 2


def test_upload_does_not_create_transaction_when_any_edi_status_fails(
    tmp_path, monkeypatch
):
    path = tmp_path / "edi.xlsx"
    path.write_bytes(b"placeholder")
    rows = [
        {
            "imported": "Success",
            "validated": "Validation Failed",
            "mapped": "Success",
            "detail": "Row 2 validation failed",
        }
    ]
    _stub_edi_before_transaction(monkeypatch, rows)
    create_calls = []
    monkeypatch.setattr(oc, "_click_pending_transaction", lambda *_: create_calls.append("pending"))
    monkeypatch.setattr(oc, "_create_transaction", lambda *_: create_calls.append("create"))

    result = oc.upload_oc_edi(path, "J.LINDEBERG", "new", log=lambda _: None)

    assert result["ok"] is False
    assert result["code"] == "OC_EDI_VALIDATION_FAILED"
    assert create_calls == []


def test_upload_creates_exactly_one_transaction_after_all_statuses_succeed(
    tmp_path, monkeypatch
):
    path = tmp_path / "edi.xlsx"
    path.write_bytes(b"placeholder")
    rows = [
        {
            "imported": "Success",
            "validated": "Success",
            "mapped": "Resolved",
            "detail": "all good",
        }
    ]
    _stub_edi_before_transaction(monkeypatch, rows)
    calls = []
    monkeypatch.setattr(oc, "_click_pending_transaction", lambda *_: calls.append("pending"))
    monkeypatch.setattr(oc, "_select_first_transaction", lambda *_: calls.append("select"))
    monkeypatch.setattr(
        oc,
        "_create_transaction",
        lambda *_: (calls.append("create") or (True, ["Created successfully"])),
    )

    result = oc.upload_oc_edi(path, "J.LINDEBERG", "revise", log=lambda _: None)

    assert result["ok"] is True
    assert result["code"] == "OC_TRANSACTION_CREATED"
    assert result["destination_tab"] == "Revision"
    assert result["transaction_submitted"] is True
    assert calls == ["pending", "select", "create"]


def test_upload_marks_transaction_unconfirmed_if_connection_drops_after_submit(
    tmp_path, monkeypatch
):
    path = tmp_path / "edi.xlsx"
    path.write_bytes(b"placeholder")
    rows = [
        {
            "imported": "Success",
            "validated": "Success",
            "mapped": "Resolved",
            "detail": "all good",
        }
    ]
    _stub_edi_before_transaction(monkeypatch, rows)
    monkeypatch.setattr(oc, "_click_pending_transaction", lambda *_: None)
    monkeypatch.setattr(oc, "_select_first_transaction", lambda *_: None)
    monkeypatch.setattr(
        oc,
        "_create_transaction",
        lambda *_: (_ for _ in ()).throw(oc.PlaywrightTimeoutError("CDP lost")),
    )

    result = oc.upload_oc_edi(path, "J.LINDEBERG", "new", log=lambda _: None)

    assert result["ok"] is False
    assert result["code"] == "OC_TRANSACTION_UNCONFIRMED"
    assert result["transaction_submitted"] is True
    assert "Không tự chạy lại" in result["message"]
