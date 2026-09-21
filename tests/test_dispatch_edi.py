"""EDI Production Order của luồng (GDN) Dispatch.

`wfx_panel/automation/dispatch/edi.py` ở mức 10%: toàn bộ Process Package,
chọn dòng Pending và chờ xác nhận Create Transaction chưa từng chạy. Đây là
đoạn đắt nhất của module vì CLAUDE.md nói rõ:

* "Chỉ chọn dòng package MỚI của lượt chạy hiện tại có
  `Transaction Detail=Pending`; nếu dòng đầu đang `InProgress` phải bỏ qua và
  chọn Pending mới nhất theo `Processed ON`."
* "`Create Transaction` là ranh giới không idempotent: sau khi click không tự
  retry, phải chờ WFX xác nhận thành công/lỗi."
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.dispatch import edi
from wfx_panel.automation.dispatch.constants import PACKAGE_LABEL
from wfx_panel.automation.dispatch.status import DispatchFlowError

GRID_ID = "gridEDIProductionOrder_tblGridContent"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, edi, _common)


def _quiet():
    return lambda _line: None


class _Page:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.dialog_handlers: list[tuple] = []

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)

    def locator(self, selector):
        return self.frames[0].locator(selector)

    def on(self, event, handler):
        self.dialog_handlers.append((event, handler))

    def remove_listener(self, event, handler):
        self.dialog_handlers.remove((event, handler))

    def fire_dialog(self, message):
        class Dialog:
            def __init__(self, text):
                self.message = text
                self.accepted = False

            def accept(self):
                self.accepted = True

        dialog = Dialog(message)
        for event, handler in list(self.dialog_handlers):
            if event == "dialog":
                handler(dialog)
        return dialog


def _edi_frame(clock, *, rows=(), message="", grid=True, selectors=True):
    children = []
    if selectors:
        children.append(element("select", id="ddlPackageType"))
        children.append(element("select", id="ddlPackage"))
    if grid:
        grid_rows = [
            Element(
                "tr",
                attrs={"rowid": row.get("row_id", "")},
                children=[
                    element(
                        "input",
                        id=f"sel{row.get('row_id')}",
                        attrs={"name": "rdSelector", "type": "radio"},
                    )
                ],
            )
            for row in rows
        ]
        children.append(
            Element(
                "table",
                id=GRID_ID,
                children=[Element("tbody", children=grid_rows)],
            )
        )
    if message:
        children.append(element("span", id="lblSuccessMsg", text=message))
    frame = MiniFrame(Element("body", children=children), clock=clock)
    frame.rows = list(rows)
    frame.scripts = {
        "gridEDIProductionOrder_tblGridContent": lambda _arg: [
            dict(row) for row in frame.rows
        ]
    }
    return frame


def _pending(row_id, *, detail="Pending", processed="2026-09-21 10:00", **extra):
    return {
        "row_id": row_id,
        "package_name": PACKAGE_LABEL,
        "transaction_detail": detail,
        "processed_on": processed,
        "status": "",
        "error": "",
        **extra,
    }


# --- _edi_frame / _open_edi ----------------------------------------------


def test_edi_frame_requires_both_package_selectors(clock):
    good = _edi_frame(clock)
    bad = _edi_frame(clock, selectors=False)
    page = _Page(clock, [bad, good])

    assert edi._edi_frame(page, timeout_s=1) is good


def test_edi_frame_reports_a_screen_that_never_appears(clock):
    page = _Page(clock, [_edi_frame(clock, selectors=False)])

    with pytest.raises(DispatchFlowError) as error:
        edi._edi_frame(page, timeout_s=0.5)

    assert error.value.code == "GDN_EDI_NOT_READY"


def test_open_edi_reuses_the_screen_without_clicking_the_menu(clock, monkeypatch):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    chosen: list[tuple] = []
    monkeypatch.setattr(
        edi,
        "_select_exact_option",
        lambda _page, selector, value, label, name: chosen.append((name, value)),
    )
    logs: list[str] = []

    assert edi._open_edi(page, logs.append) is frame
    assert chosen == [("PackageType", "Import"), ("Package", "2")]
    assert not any("Mở EDI Production Order" in line for line in logs)


def test_open_edi_clicks_the_menu_when_the_screen_is_not_open(clock, monkeypatch):
    ready = _edi_frame(clock)
    empty = _edi_frame(clock, selectors=False)
    page = _Page(clock, [empty])
    menu = element("a", id="edi-menu")
    empty.xpaths[edi.EDI_MENU_XPATH] = [menu]
    menu.on_click = lambda _n: page.frames.append(ready)
    monkeypatch.setattr(edi, "_select_exact_option", lambda *a, **kw: None)
    logs: list[str] = []

    assert edi._open_edi(page, logs.append) is ready
    assert menu.clicks == 1
    assert any("Mở EDI Production Order" in line for line in logs)


# --- đọc grid -------------------------------------------------------------


def test_edi_rows_normalises_every_value_to_a_string(clock):
    frame = _edi_frame(clock)
    frame.rows = [{"row_id": 7, "transaction_detail": None}]

    assert edi._edi_rows(frame) == [{"row_id": "7", "transaction_detail": ""}]


def test_edi_rows_is_empty_when_the_grid_script_fails(clock):
    frame = _edi_frame(clock)
    frame.scripts = {
        "gridEDIProductionOrder_tblGridContent": lambda _arg: (
            _ for _ in ()
        ).throw(PlaywrightError("frame rơi"))
    }

    assert edi._edi_rows(frame) == []


def test_edi_rows_ignores_a_non_list_payload(clock):
    frame = _edi_frame(clock)
    frame.scripts = {
        "gridEDIProductionOrder_tblGridContent": lambda _arg: {"row_id": "1"}
    }

    assert edi._edi_rows(frame) == []


def test_visible_message_reads_the_first_non_empty_visible_banner(clock):
    frame = _edi_frame(clock, message="  Data   Imported  ")

    assert edi._visible_message(frame) == "Data Imported"


def test_visible_message_skips_a_hidden_banner(clock):
    frame = _edi_frame(clock)
    frame.root.append(element("span", id="lblSuccessMsg", text="Ẩn", visible=False))

    assert edi._visible_message(frame) == ""


# --- Process Package ------------------------------------------------------


def _wire_upload(monkeypatch, page, frame):
    file_input = element("input", id="file", attrs={"type": "file"})
    file_input.set_input_files = lambda path: file_input.fills.append(path)
    process_link = element("a", id="process")
    monkeypatch.setattr(
        edi, "_open_import_popup", lambda _page: (frame, file_input)
    )
    monkeypatch.setattr(
        edi, "_toolbar_link", lambda _page, label, timeout_s=0: (frame, process_link)
    )
    return file_input, process_link


def test_process_package_selects_the_new_pending_row(clock, monkeypatch, tmp_path):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    file_input, process_link = _wire_upload(monkeypatch, page, frame)
    upload = tmp_path / "gdn.xlsx"
    upload.write_bytes(b"x")
    process_link.on_click = lambda _n: frame.rows.append(_pending("new-1"))
    logs: list[str] = []

    selected = edi._process_package(
        page, frame, upload, {"old-1"}, logs.append
    )

    assert selected["row_id"] == "new-1"
    assert file_input.fills == [str(upload)]
    assert page.dialog_handlers == []
    assert any("Đã gắn file XLSX" in line for line in logs)


def test_process_package_skips_an_in_progress_row_for_a_newer_pending_one(
    clock, monkeypatch, tmp_path
):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    _file_input, process_link = _wire_upload(monkeypatch, page, frame)
    upload = tmp_path / "gdn.xlsx"
    upload.write_bytes(b"x")

    def add_rows(_node):
        frame.rows.append(
            _pending("busy", detail="InProgress", processed="2026-09-21 11:00")
        )
        frame.rows.append(_pending("fresh", processed="2026-09-21 10:00"))

    process_link.on_click = add_rows

    selected = edi._process_package(page, frame, upload, set(), _quiet())

    assert selected["row_id"] == "fresh"


def test_process_package_stops_on_a_failing_dialog(clock, monkeypatch, tmp_path):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    _file_input, process_link = _wire_upload(monkeypatch, page, frame)
    upload = tmp_path / "gdn.xlsx"
    upload.write_bytes(b"x")
    process_link.on_click = lambda _n: page.fire_dialog("Package Failed to import")

    with pytest.raises(DispatchFlowError) as error:
        edi._process_package(page, frame, upload, set(), _quiet())

    assert error.value.code == "GDN_PACKAGE_PROCESS_FAILED"
    assert page.dialog_handlers == []


def test_process_package_stops_on_a_failing_banner(clock, monkeypatch, tmp_path):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    _file_input, process_link = _wire_upload(monkeypatch, page, frame)
    upload = tmp_path / "gdn.xlsx"
    upload.write_bytes(b"x")
    process_link.on_click = lambda _n: frame.root.append(
        element("span", id="lblSuccessMsg", text="Import Failed")
    )

    with pytest.raises(DispatchFlowError) as error:
        edi._process_package(page, frame, upload, set(), _quiet())

    assert error.value.code == "GDN_PACKAGE_PROCESS_FAILED"


def test_process_package_stops_when_the_new_row_itself_failed(
    clock, monkeypatch, tmp_path
):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    _file_input, process_link = _wire_upload(monkeypatch, page, frame)
    upload = tmp_path / "gdn.xlsx"
    upload.write_bytes(b"x")
    process_link.on_click = lambda _n: frame.rows.append(
        _pending("bad", detail="Failed", error="Thiếu cột Doc No.")
    )

    with pytest.raises(DispatchFlowError) as error:
        edi._process_package(page, frame, upload, set(), _quiet())

    assert error.value.code == "GDN_PACKAGE_PROCESS_FAILED"
    assert "Thiếu cột Doc No." in error.value.errors


def test_process_package_reports_when_no_pending_row_ever_appears(
    clock, monkeypatch, tmp_path
):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    _file_input, _process_link = _wire_upload(monkeypatch, page, frame)
    upload = tmp_path / "gdn.xlsx"
    upload.write_bytes(b"x")

    with pytest.raises(DispatchFlowError) as error:
        edi._process_package(page, frame, upload, set(), _quiet())

    assert error.value.code == "GDN_PENDING_NOT_FOUND"
    assert page.dialog_handlers == []


def test_process_package_ignores_a_new_row_of_another_package(
    clock, monkeypatch, tmp_path
):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    _file_input, process_link = _wire_upload(monkeypatch, page, frame)
    upload = tmp_path / "gdn.xlsx"
    upload.write_bytes(b"x")
    process_link.on_click = lambda _n: frame.rows.append(
        {
            "row_id": "other",
            "package_name": "StandardSalesOrder",
            "transaction_detail": "Failed",
            "processed_on": "2026-09-21 10:00",
            "status": "",
            "error": "",
        }
    )

    with pytest.raises(DispatchFlowError) as error:
        edi._process_package(page, frame, upload, set(), _quiet())

    # Không được coi lỗi của package khác là lỗi của lượt này.
    assert error.value.code == "GDN_PENDING_NOT_FOUND"


# --- chọn dòng ------------------------------------------------------------


def test_select_transaction_checks_exactly_that_row(clock):
    frame = _edi_frame(clock, rows=[_pending("a"), _pending("b")])

    edi._select_transaction(frame, {"row_id": "b"})

    rows = frame.locator(f"#{GRID_ID}").locator(":scope > tbody > tr")
    assert rows.nth(1).locator("#selb").node.checked is True
    assert rows.nth(0).locator("#sela").node.checked is False


def test_select_transaction_refuses_a_row_without_an_id(clock):
    frame = _edi_frame(clock, rows=[_pending("a")])

    with pytest.raises(DispatchFlowError) as error:
        edi._select_transaction(frame, {"row_id": ""})

    assert error.value.code == "GDN_PENDING_NOT_FOUND"


def test_select_transaction_refuses_a_row_that_vanished(clock):
    frame = _edi_frame(clock, rows=[_pending("a")])

    with pytest.raises(DispatchFlowError) as error:
        edi._select_transaction(frame, {"row_id": "khong-co"})

    assert error.value.code == "GDN_PENDING_NOT_FOUND"


def test_select_transaction_refuses_a_radio_wfx_never_ticks(clock):
    frame = _edi_frame(clock, rows=[_pending("a")])
    radio = frame.locator("#sela").node
    radio.check = lambda **_kwargs: None

    with pytest.raises(DispatchFlowError) as error:
        edi._select_transaction(frame, {"row_id": "a"})

    assert error.value.code == "GDN_PENDING_NOT_FOUND"


# --- nút Create Transaction ----------------------------------------------


def _create_link(text="Create Transaction", **kwargs):
    return Element(
        "a",
        css_class="clsSectionTitleBarToolCustom",
        text=text,
        **kwargs,
    )


def test_create_transaction_link_matches_by_exact_label(clock, monkeypatch):
    link = _create_link()
    frame = MiniFrame(
        Element(
            "body",
            children=[
                Element(
                    "div",
                    id="sectionEDIProductionOrder",
                    children=[_create_link("Reject"), link],
                )
            ],
        ),
        clock=clock,
    )
    monkeypatch.setattr(edi, "EDI_CREATE_SELECTOR", "a")

    assert edi._create_transaction_link(frame).node is link


def test_create_transaction_link_refuses_a_disabled_button(clock, monkeypatch):
    frame = MiniFrame(
        Element("body", children=[_create_link(enabled=False)]), clock=clock
    )
    monkeypatch.setattr(edi, "EDI_CREATE_SELECTOR", "a")

    with pytest.raises(DispatchFlowError) as error:
        edi._create_transaction_link(frame)

    assert error.value.code == "GDN_EDI_NOT_READY"


def test_create_transaction_link_refuses_two_identical_buttons(clock, monkeypatch):
    frame = MiniFrame(
        Element("body", children=[_create_link(), _create_link()]), clock=clock
    )
    monkeypatch.setattr(edi, "EDI_CREATE_SELECTOR", "a")

    with pytest.raises(DispatchFlowError):
        edi._create_transaction_link(frame)


# --- chờ xác nhận ---------------------------------------------------------


def test_transaction_result_trusts_a_completing_dialog(clock):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])

    ok, messages = edi._wait_transaction_result(
        page, frame, "a", ["Transaction created successfully"]
    )

    assert ok is True
    assert messages == ["Transaction created successfully"]


def test_transaction_result_trusts_a_failing_dialog_over_anything_else(clock):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])

    ok, messages = edi._wait_transaction_result(
        page, frame, "a", ["Failed to create", "Success"]
    )

    assert ok is False
    assert messages == ["Failed to create"]


def test_transaction_result_reads_a_failing_banner(clock):
    frame = _edi_frame(clock, message="Create Transaction Failed")
    page = _Page(clock, [frame])

    ok, messages = edi._wait_transaction_result(page, frame, "a", [])

    assert ok is False
    assert messages == ["Create Transaction Failed"]


def test_transaction_result_ignores_the_upload_success_banner(clock):
    """Banner của bước upload không được coi là xác nhận Create Transaction."""
    frame = _edi_frame(clock, message="File upload completed successfully")
    page = _Page(clock, [frame])
    frame.rows = [_pending("a", detail="Failed", error="Lỗi thật")]

    ok, messages = edi._wait_transaction_result(page, frame, "a", [])

    assert ok is False
    assert messages == ["Lỗi thật"]


def test_transaction_result_follows_the_row_transaction_detail(clock):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    frame.rows = [_pending("a", detail="Completed")]

    ok, messages = edi._wait_transaction_result(page, frame, "a", [])

    assert ok is True
    assert messages == ["Completed"]


def test_transaction_result_needs_several_stable_reads_before_trusting_removal(
    clock,
):
    """WFX refresh grid giữa chừng; một lần mất dòng chưa phải là xong."""
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    frame.rows = []

    ok, messages = edi._wait_transaction_result(page, frame, "a", [])

    assert ok is True
    assert messages == ["Package đã rời danh sách chờ xử lý."]
    # Đúng 3 lần đọc ổn định, không phải lần đầu.
    assert frame.evaluated.count(frame.evaluated[0]) >= 3


def test_transaction_result_never_trusts_removal_without_a_grid(clock):
    frame = _edi_frame(clock, grid=False)
    page = _Page(clock, [frame])
    frame.rows = []

    ok, messages = edi._wait_transaction_result(page, frame, "a", [])

    assert ok is False
    assert "chưa xác nhận hoàn tất" in messages[0]


def test_transaction_result_times_out_with_the_last_known_detail(clock):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    frame.rows = [_pending("a", detail="InProgress")]

    ok, messages = edi._wait_transaction_result(page, frame, "a", [])

    assert ok is False
    assert "InProgress" in messages[0]


# --- popup Import ---------------------------------------------------------


def test_import_popup_is_reused_when_it_is_already_open(clock, monkeypatch):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    file_input = element("input", id="file")
    monkeypatch.setattr(
        edi, "_attached_in_frames", lambda *a, **kw: (frame, file_input)
    )
    opened: list[int] = []
    monkeypatch.setattr(
        edi,
        "_toolbar_link",
        lambda *a, **kw: opened.append(1) or (frame, element("a")),
    )

    assert edi._open_import_popup(page) == (frame, file_input)
    assert opened == []


def test_import_popup_is_opened_through_the_toolbar_when_missing(
    clock, monkeypatch
):
    frame = _edi_frame(clock)
    page = _Page(clock, [frame])
    file_input = element("input", id="file")
    calls: list[float] = []

    def attached(_page, _selector, timeout_s=0):
        calls.append(timeout_s)
        if len(calls) == 1:
            raise PlaywrightTimeoutError("popup chưa mở")
        return frame, file_input

    monkeypatch.setattr(edi, "_attached_in_frames", attached)
    link = element("a", id="import")
    monkeypatch.setattr(edi, "_toolbar_link", lambda *a, **kw: (frame, link))

    assert edi._open_import_popup(page) == (frame, file_input)
    assert link.clicks == 1
    assert calls == [1, 20]
