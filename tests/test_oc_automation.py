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
    monkeypatch.setattr(
        oc,
        "_open_status_error_details",
        lambda *_args: (
            "Mapping Resolved",
            [],
            ["Mapping Resolved: InProgress"],
        ),
    )


def test_edi_status_kind_distinguishes_success_failure_and_pending():
    assert _status_kind("Success") == "success"
    assert _status_kind("Mapping Resolved") == "success"
    assert _status_kind("Validation Failed") == "failed"
    assert _status_kind("Unresolved") == "failed"
    assert _status_kind("Not Resolved") == "failed"
    assert _status_kind("InProgress") == "failed"
    assert _status_kind("In Progress") == "failed"
    assert _status_kind("Pending") == "pending"


def test_mapping_in_progress_returns_immediately_without_waiting(monkeypatch):
    rows = [
        {
            "imported": "Success",
            "validated": "Success",
            "mapped": "In Progress",
            "detail": "Success Success In Progress",
        }
    ]
    clock = [0.0]
    monkeypatch.setattr(oc.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(oc, "checkpoint", lambda: None)
    monkeypatch.setattr(oc, "_status_rows", lambda _page: (object(), rows))
    monkeypatch.setattr(
        oc,
        "_wait",
        lambda _page, milliseconds: clock.__setitem__(
            0, clock[0] + milliseconds / 1000
        ),
    )

    result = oc._wait_statuses(object(), log=lambda _message: None)

    assert result == rows
    assert clock[0] == 0.0


def test_upload_opens_mapping_details_without_creating_transaction(
    tmp_path, monkeypatch
):
    path = tmp_path / "edi.xlsx"
    path.write_bytes(b"placeholder")
    rows = [
        {
            "imported": "Success",
            "validated": "Success",
            "mapped": "In Progress",
            "detail": "Mapping Resolved In Progress",
        }
    ]
    _stub_edi_before_transaction(monkeypatch, rows)
    resolution_rows = [
        {
            "mapping_code": "Field Mapping not resolved",
            "doc_no": "JK-FH25-KNIT- BUY 1-FLAT",
            "mapping_details": (
                "EDI Package Field Mapping Not Resolved For Season: FH25"
            ),
            "inactive": "No",
        }
    ]
    detail = (
        "Field Mapping not resolved — EDI Package Field Mapping Not Resolved "
        "For Season: FH25 (Doc No.: JK-FH25-KNIT- BUY 1-FLAT; InActive: No)"
    )
    monkeypatch.setattr(
        oc,
        "_open_status_error_details",
        lambda *_args: ("Mapping Resolved", resolution_rows, [detail]),
    )
    create_calls = []
    monkeypatch.setattr(
        oc,
        "_click_pending_transaction",
        lambda *_args: create_calls.append("pending"),
    )

    result = oc.upload_oc_edi(path, "J.LINDEBERG", "new", log=lambda _: None)

    assert result["ok"] is False
    assert result["code"] == "OC_EDI_VALIDATION_FAILED"
    assert result["transaction_submitted"] is False
    assert result["status_rows"] == rows
    assert result["error_stage"] == "Mapping Resolved"
    assert result["resolution_rows"] == resolution_rows
    assert result["errors"] == [detail]
    assert create_calls == []


def test_failed_record_is_formatted_for_the_user():
    error = oc._format_resolution_error(
        {
            "mapping_code": "Field Mapping not resolved",
            "doc_no": "JK-FH25-KNIT- BUY 1-FLAT",
            "mapping_details": (
                "EDI Package Field Mapping Not Resolved For Season: FH25"
            ),
            "inactive": "No",
        }
    )

    assert error.startswith("Field Mapping not resolved — EDI Package")
    assert "Doc No.: JK-FH25-KNIT- BUY 1-FLAT" in error
    assert "InActive: No" in error


def test_status_reader_targets_only_the_latest_wfx_grid_row():
    assert "#gridEDIPackageImport_tblGridHeader" in oc._STATUS_JS
    assert "#gridEDIPackageImport_tblGridContent" in oc._STATUS_JS
    assert "return [record]" in oc._STATUS_JS


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
