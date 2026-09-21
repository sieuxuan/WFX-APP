"""EDI Buyer PO: chọn Buyer/Package, Process Package và đọc trạng thái.

`wfx_panel/automation/oc/package.py` ở mức 28%. CLAUDE.md đặc tả rất chặt:

* "EDI OC phải chọn exact Buyer từ file và package value `1`/
  `StandardSalesOrder`, upload file chuẩn hoá, bấm `Process Package` rồi đọc
  cả `Data Imported`, `Data Validated`, `Mapping Resolved`. Chỉ khi tất cả đều
  Success mới chọn transaction đầu tiên."
* "Bất kỳ trạng thái `InProgress`/`In Progress` hoặc Fail nào ở
  Imported/Validated/Mapping đều được coi là lỗi ngay, không chờ timeout."
* "Automation click đúng link trạng thái, đọc popup `Failed Record` …, trả chi
  tiết cho UI, giữ popup để chụp ảnh vào Lịch sử và không click
  Create Transaction."
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.oc import package


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, package, _common)


def _quiet():
    return lambda _line: None


class _Page:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.listeners: list[tuple] = []

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)

    def on(self, event, handler):
        self.listeners.append((event, handler))

    def remove_listener(self, event, handler):
        if (event, handler) in self.listeners:
            self.listeners.remove((event, handler))

    def fire_dialog(self, message):
        class Dialog:
            def __init__(self, text):
                self.message = text
                self.accepted = False

            def accept(self):
                self.accepted = True

        dialog = Dialog(message)
        for event, handler in list(self.listeners):
            if event == "dialog":
                handler(dialog)
        return dialog


def _status_frame(clock, rows=(), *, banner="", records=None, links=()):
    children = []
    if banner:
        children.append(element("span", id="lblSuccessMsg", text=banner))
    grid_rows = [
        Element("tr", children=[element("a", id=name)]) for name in links
    ]
    children.append(
        Element(
            "table",
            id="gridEDIPackageImport_tblGridContent",
            children=grid_rows,
        )
    )
    if records is not None:
        children.append(
            Element("div", id="sectionFailedRecord", visible=True)
        )
    frame = MiniFrame(Element("body", children=children), clock=clock)
    frame.rows = list(rows)
    frame.records = records
    frame.scripts = {
        "transactiondetail": lambda _a: [dict(row) for row in frame.rows],
        "mapping_code": lambda _a: list(frame.records or []),
    }
    return frame


def _row(**overrides) -> dict:
    return {
        "imported": "Success",
        "validated": "Success",
        "mapped": "Success",
        "detail": "",
        **overrides,
    }


# --- phân loại trạng thái -------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "Failed",
        "Error",
        "Invalid",
        "Unresolved",
        "Not Resolved",
        "Rejected",
        "InProgress",
        "In Progress",
    ],
)
def test_every_failing_or_running_state_is_treated_as_a_failure(value):
    assert package._status_kind(value) == "failed"


@pytest.mark.parametrize(
    "value", ["Success", "Successful", "Resolved", "Completed"]
)
def test_every_finished_state_is_a_success(value):
    assert package._status_kind(value) == "success"


@pytest.mark.parametrize("value", ["", "   ", "Pending", None])
def test_anything_else_is_still_pending(value):
    assert package._status_kind(value) == "pending"


# --- đọc bảng trạng thái --------------------------------------------------


def test_the_status_table_is_read_from_the_first_frame_that_has_one(clock):
    empty = MiniFrame(Element("body"), clock=clock)
    empty.scripts = {"transactiondetail": lambda _a: []}
    good = _status_frame(clock, rows=[_row()])
    page = _Page(clock, [empty, good])

    frame, rows = package._status_rows(page)

    assert frame is good
    assert rows == [_row()]


def test_a_frame_that_throws_is_skipped(clock):
    class Broken:
        url = "https://wfx.test/x"

        def evaluate(self, _script, _arg=None):
            raise PlaywrightError("frame rơi")

    good = _status_frame(clock, rows=[_row()])
    page = _Page(clock, [Broken(), good])

    assert package._status_rows(page)[0] is good


def test_no_status_table_anywhere_is_reported_as_empty(clock):
    empty = MiniFrame(Element("body"), clock=clock)
    empty.scripts = {"transactiondetail": lambda _a: []}

    assert package._status_rows(_Page(clock, [empty])) == (None, [])


# --- chờ trạng thái -------------------------------------------------------


def test_all_three_stages_success_ends_the_wait(clock):
    frame = _status_frame(clock, rows=[_row()])
    page = _Page(clock, [frame])
    logs: list[str] = []

    rows = package._wait_statuses(page, logs.append)

    assert rows == [_row()]
    assert any("đạt Imported/Validated/Mapping Success" in line for line in logs)
    assert any("Trạng thái: Imported=Success" in line for line in logs)


def test_one_failing_stage_ends_the_wait_immediately(clock):
    frame = _status_frame(clock, rows=[_row(mapped="Failed")])
    page = _Page(clock, [frame])

    rows = package._wait_statuses(page, _quiet())

    assert rows[0]["mapped"] == "Failed"


def test_an_in_progress_stage_is_not_waited_out(clock):
    """CLAUDE.md: InProgress là lỗi ngay, không chờ hết timeout."""
    frame = _status_frame(clock, rows=[_row(validated="InProgress")])
    page = _Page(clock, [frame])
    started = clock.monotonic()

    package._wait_statuses(page, _quiet())

    assert clock.monotonic() - started < package.STATUS_TIMEOUT_SECONDS


def test_a_table_that_never_appears_times_out_with_a_readable_reason(clock):
    empty = MiniFrame(Element("body"), clock=clock)
    empty.scripts = {"transactiondetail": lambda _a: []}

    with pytest.raises(PlaywrightTimeoutError, match="không đọc được bảng"):
        package._wait_statuses(_Page(clock, [empty]), _quiet())


def test_a_table_stuck_on_pending_times_out_with_its_detail(clock):
    frame = _status_frame(
        clock, rows=[_row(imported="Pending", detail="Đang xếp hàng")]
    )

    with pytest.raises(PlaywrightTimeoutError, match="Đang xếp hàng"):
        package._wait_statuses(_Page(clock, [frame]), _quiet())


def test_the_status_line_is_only_logged_when_it_changes(clock):
    frame = _status_frame(clock, rows=[_row(imported="Pending")])
    page = _Page(clock, [frame])
    logs: list[str] = []

    with pytest.raises(PlaywrightTimeoutError):
        package._wait_statuses(page, logs.append)

    assert len([line for line in logs if "Trạng thái:" in line]) == 1


# --- chọn stage lỗi để mở chi tiết ---------------------------------------


def test_mapping_is_opened_before_validated_and_imported():
    rows = [_row(imported="Failed", validated="Failed", mapped="Failed")]

    assert package._failed_status(rows) == ("mapped", "Failed")


def test_validated_is_opened_when_mapping_is_fine():
    rows = [_row(validated="Failed", mapped="Success")]

    assert package._failed_status(rows) == ("validated", "Failed")


def test_nothing_is_opened_when_every_stage_succeeded():
    assert package._failed_status([_row()]) == ("", "")


def test_nothing_is_opened_without_any_row():
    assert package._failed_status([]) == ("", "")


# --- định dạng lỗi cho UI -------------------------------------------------


def test_a_failed_record_is_formatted_with_code_details_and_context():
    message = package._format_resolution_error(
        {
            "mapping_code": "BUYER",
            "mapping_details": "Không tìm thấy Buyer",
            "doc_no": "PO-1",
            "inactive": "Yes",
        }
    )

    assert message == (
        "BUYER — Không tìm thấy Buyer (Doc No.: PO-1; InActive: Yes)"
    )


def test_a_failed_record_without_a_code_still_says_something_useful():
    assert package._format_resolution_error({"doc_no": "PO-1"}) == (
        "WFX báo lỗi (Doc No.: PO-1)"
    )


def test_a_failed_record_falls_back_to_its_detail():
    assert package._format_resolution_error({"detail": "Lỗi lạ"}) == "Lỗi lạ"


def test_an_empty_failed_record_never_produces_a_blank_message():
    assert package._format_resolution_error({}) == (
        "WFX không hiển thị chi tiết lỗi."
    )


# --- mở popup Failed Record ----------------------------------------------


def test_no_failed_stage_means_nothing_is_opened(clock):
    page = _Page(clock, [_status_frame(clock)])

    assert package._open_status_error_details(page, [_row()], _quiet()) == (
        "",
        [],
        [],
    )


def test_the_failed_stage_link_is_clicked_and_the_popup_is_read(clock):
    records = [{"mapping_code": "BUYER", "mapping_details": "Thiếu Buyer"}]
    frame = _status_frame(
        clock, records=records, links=["lnkMappingResolved"]
    )
    page = _Page(clock, [frame])
    logs: list[str] = []

    stage, read, errors = package._open_status_error_details(
        page, [_row(mapped="Failed")], logs.append
    )

    assert stage == "Mapping Resolved"
    assert read == records
    assert errors == ["BUYER — Thiếu Buyer"]
    assert frame.locator("#lnkMappingResolved").node.clicks == 1
    assert any("Lỗi: BUYER" in line for line in logs)


def test_a_missing_status_link_is_reported_without_crashing(clock):
    frame = _status_frame(clock, links=[])
    page = _Page(clock, [frame])
    logs: list[str] = []

    stage, records, errors = package._open_status_error_details(
        page, [_row(validated="Failed")], logs.append
    )

    assert stage == "Data Validated"
    assert records == []
    assert "không mở được chi tiết" in errors[0]


def test_a_popup_that_never_shows_still_reports_the_stage(clock):
    frame = _status_frame(clock, records=None, links=["lnkDataImported"])
    page = _Page(clock, [frame])

    stage, records, errors = package._open_status_error_details(
        page, [_row(imported="Failed", validated="Success", mapped="Success")],
        _quiet(),
    )

    assert stage == "Data Imported"
    assert records == []
    assert "không hiển thị chi tiết lỗi" in errors[0]


def test_a_hidden_status_link_is_not_used(clock):
    frame = _status_frame(clock, links=["lnkMappingResolved"])
    frame.locator("#lnkMappingResolved").node.visible = False
    page = _Page(clock, [frame])

    _stage, _records, errors = package._open_status_error_details(
        page, [_row(mapped="Failed")], _quiet()
    )

    assert "không mở được chi tiết" in errors[0]


# --- mở form EDI ----------------------------------------------------------


def test_the_edi_form_selects_the_exact_buyer_and_the_standard_package(
    clock, monkeypatch
):
    frame = _status_frame(clock)
    page = _Page(clock, [frame])
    menu = element("a", id="edi-menu")
    monkeypatch.setattr(
        package, "_attached_in_frames", lambda *a, **kw: (frame, menu)
    )
    monkeypatch.setattr(
        package, "_visible_in_frames", lambda *a, **kw: (frame, element("select"))
    )
    chosen: list[tuple] = []
    monkeypatch.setattr(
        package,
        "_select_exact_option",
        lambda _page, selector, value, label, name: chosen.append(
            (name, value, label)
        ),
    )
    logs: list[str] = []

    assert package._open_edi_form(page, "J.LINDEBERG", logs.append) is frame
    assert menu.clicks == 1
    assert chosen == [
        ("Buyer", "", "J.LINDEBERG"),
        ("Package", package.PACKAGE_VALUE, package.PACKAGE_LABEL),
    ]
    assert any("Đã chọn Buyer: J.LINDEBERG" in line for line in logs)


# --- Process Package ------------------------------------------------------


def _wire_process(monkeypatch, page, frame, *, upload=None):
    file_input = element("input", id="file")
    file_input.set_input_files = lambda path: file_input.fills.append(path)
    import_link = element("a", id="import")
    process_link = element("a", id="process")
    monkeypatch.setattr(
        package,
        "_attached_in_frames",
        lambda *a, **kw: (frame, file_input),
    )

    def toolbar(_page, label, timeout_s=0):
        if label == "Import":
            return frame, import_link
        if label == "Process Package":
            return frame, process_link
        raise PlaywrightTimeoutError("Error Resolution chưa có")

    monkeypatch.setattr(package, "_toolbar_link", toolbar)
    return file_input, import_link, process_link


def test_process_package_uploads_then_trusts_a_success_dialog(
    clock, monkeypatch, tmp_path
):
    frame = _status_frame(clock)
    page = _Page(clock, [frame])
    upload = tmp_path / "oc.xlsx"
    upload.write_bytes(b"x")
    file_input, import_link, process_link = _wire_process(monkeypatch, page, frame)
    process_link.on_click = lambda _n: page.fire_dialog("Data uploaded successfully")
    logs: list[str] = []

    package._process_package(page, upload, logs.append)

    assert file_input.fills == [str(upload)]
    assert import_link.clicks == 1
    assert page.listeners == []
    assert any("Đã gắn file oc.xlsx" in line for line in logs)


def test_process_package_stops_on_a_failing_dialog(clock, monkeypatch, tmp_path):
    frame = _status_frame(clock)
    page = _Page(clock, [frame])
    upload = tmp_path / "oc.xlsx"
    upload.write_bytes(b"x")
    _file_input, _import_link, process_link = _wire_process(
        monkeypatch, page, frame
    )
    process_link.on_click = lambda _n: page.fire_dialog("Invalid file format")

    with pytest.raises(PlaywrightTimeoutError, match="Invalid file format"):
        package._process_package(page, upload, _quiet())

    assert page.listeners == []


def test_process_package_trusts_a_success_banner(clock, monkeypatch, tmp_path):
    frame = _status_frame(clock)
    page = _Page(clock, [frame])
    upload = tmp_path / "oc.xlsx"
    upload.write_bytes(b"x")
    _file_input, _import_link, process_link = _wire_process(
        monkeypatch, page, frame
    )
    process_link.on_click = lambda _n: frame.root.append(
        element("span", id="lblSuccessMsg", text="Package processed")
    )
    logs: list[str] = []

    package._process_package(page, upload, logs.append)

    assert any("Package processed" in line for line in logs)


def test_process_package_stops_on_a_failing_banner(clock, monkeypatch, tmp_path):
    frame = _status_frame(clock)
    page = _Page(clock, [frame])
    upload = tmp_path / "oc.xlsx"
    upload.write_bytes(b"x")
    _file_input, _import_link, process_link = _wire_process(
        monkeypatch, page, frame
    )
    process_link.on_click = lambda _n: frame.root.append(
        element("span", id="lblSuccessMsg", text="Upload failed")
    )

    with pytest.raises(PlaywrightTimeoutError, match="Upload failed"):
        package._process_package(page, upload, _quiet())


def test_process_package_accepts_the_error_resolution_toolbar_as_progress(
    clock, monkeypatch, tmp_path
):
    frame = _status_frame(clock)
    page = _Page(clock, [frame])
    upload = tmp_path / "oc.xlsx"
    upload.write_bytes(b"x")
    file_input = element("input", id="file")
    file_input.set_input_files = lambda path: file_input.fills.append(path)
    monkeypatch.setattr(
        package, "_attached_in_frames", lambda *a, **kw: (frame, file_input)
    )
    monkeypatch.setattr(
        package,
        "_toolbar_link",
        lambda _page, label, timeout_s=0: (frame, element("a", id=label)),
    )

    package._process_package(page, upload, _quiet())


def test_process_package_times_out_when_wfx_says_nothing(
    clock, monkeypatch, tmp_path
):
    frame = _status_frame(clock)
    page = _Page(clock, [frame])
    upload = tmp_path / "oc.xlsx"
    upload.write_bytes(b"x")
    _wire_process(monkeypatch, page, frame)

    with pytest.raises(PlaywrightTimeoutError, match="chưa xác nhận Process Package"):
        package._process_package(page, upload, _quiet())
