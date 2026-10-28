"""Chốt chặn của các thao tác OC không idempotent trước trạng thái WFX lẫn lộn.

Bốn tình huống từng làm automation đọc nhầm kết quả:

* Bảng Error Resolution giữ package của các lượt trước. Đọc dòng đầu hoặc
  click link ``Pending`` đầu tiên trên trang có thể Create Transaction trên
  package CŨ. Mỗi lượt upload giờ mang tên file riêng và chỉ dòng của nó được
  đọc/click.
* Alert WFX tới SAU postback của Process Package/Confirm/Reject. Handler chỉ
  sống trong cú click thì bỏ sót, hộp thoại chặn trang tới hết timeout.
* Banner "success" còn sót từ bước trước bị đọc như xác nhận Create
  Transaction.
* Bảng EDI Buyer PO đang vẽ lại sau postback bị coi là "đã hết Style", và lỗi
  giữa chừng làm mất số Style/PO đã xử lý.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.oc import confirm, package, transaction
from wfx_panel.automation.oc.dom import _DialogCollector
from wfx_panel.automation.oc.package import PackageTarget, _own_package_rows

OURS = "OC-New-20261028-153012.xlsx"
OLD = "OC-New-20261027-090000.xlsx"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, package, transaction, confirm, _common)


def _quiet():
    return lambda _line: None


class _Dialog:
    def __init__(self, message, kind="alert"):
        self.message = message
        self.type = kind
        self.accepted = 0

    def accept(self):
        self.accepted += 1


class _Page:
    def __init__(self, clock, frames=()):
        self.clock = clock
        self.frames = list(frames)
        self.listeners: list[tuple] = []
        self.ticks: list = []

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)
        for tick in list(self.ticks):
            tick()

    def on(self, event, handler):
        self.listeners.append((event, handler))

    def remove_listener(self, event, handler):
        if (event, handler) in self.listeners:
            self.listeners.remove((event, handler))

    def fire_dialog(self, message, kind="alert"):
        dialog = _Dialog(message, kind)
        for event, handler in list(self.listeners):
            if event == "dialog":
                handler(dialog)
        return dialog


def _row(file_name="", index=0, **statuses):
    return {
        "index": index,
        "file_name": file_name,
        "imported": statuses.get("imported", "Success"),
        "validated": statuses.get("validated", "Success"),
        "mapped": statuses.get("mapped", "Success"),
        "transaction": statuses.get("transaction", "Pending"),
        "detail": f"{file_name} {index}",
    }


def _status_frame(clock, rows_source, *, links=()):
    """`rows_source` là hàm trả các dòng _STATUS_JS ở lần đọc hiện tại."""
    grid_rows = [
        Element(
            "tr",
            attrs={"data-wfx-oc-package-row": str(index)},
            children=[element("a", id=f"pending-{index}", text=text)],
        )
        for index, text in enumerate(links)
    ]
    frame = MiniFrame(
        Element(
            "body",
            children=[
                Element(
                    "table",
                    id="gridEDIPackageImport_tblGridContent",
                    children=grid_rows,
                )
            ],
        ),
        clock=clock,
    )
    frame.scripts = {"transactiondetail": lambda _a: rows_source()}
    return frame, grid_rows


# --- chọn đúng package của lượt này -------------------------------------


def test_the_row_carrying_this_runs_file_name_is_the_only_one_read():
    rows = [_row(OLD, 0), _row(OURS, 1)]

    assert _own_package_rows(rows, PackageTarget(OURS)) == [rows[1]]


def test_an_older_package_is_never_taken_while_ours_has_not_appeared():
    rows = [_row(OLD, 0, mapped="Resolved")]

    assert _own_package_rows(rows, PackageTarget(OURS)) == []


def test_without_file_names_a_row_seen_before_processing_is_stale():
    old = _row("", 0)
    target = PackageTarget(OURS, frozenset({old["detail"]}))

    assert _own_package_rows([old], target) == []
    fresh = {**_row("", 0), "detail": "new package"}
    assert _own_package_rows([fresh, old], target) == [fresh]


def test_the_status_wait_ignores_an_old_success_until_ours_shows_up(clock):
    reads: list[int] = []

    def rows():
        reads.append(1)
        if len(reads) < 4:
            return [_row(OLD, 0)]
        return [_row(OURS, 0, mapped="In Progress"), _row(OLD, 1)]

    frame, _links = _status_frame(clock, rows)
    page = _Page(clock, [frame])

    result = package._wait_statuses(page, _quiet(), PackageTarget(OURS))

    # Dòng cũ đã Success nhưng không phải của lượt này: phải chờ tới dòng của
    # mình, và In Progress của nó là lỗi ngay (không đi tiếp Create Transaction).
    assert result[0]["file_name"] == OURS
    assert package._status_kind(result[0]["mapped"]) == "failed"
    assert len(reads) == 4


def test_our_package_never_appearing_names_the_file_in_the_timeout(clock):
    frame, _links = _status_frame(clock, lambda: [_row(OLD, 0)])
    page = _Page(clock, [frame])

    with pytest.raises(PlaywrightTimeoutError, match=OURS):
        package._wait_statuses(page, _quiet(), PackageTarget(OURS))


def test_an_alert_arriving_after_process_package_stops_the_status_wait(clock):
    frame, _links = _status_frame(clock, lambda: [])
    page = _Page(clock, [frame])
    dialogs = _DialogCollector().attach(page)

    dialog = page.fire_dialog("Invalid file: Season FH25 not found")

    assert dialog.accepted == 1
    with pytest.raises(PlaywrightTimeoutError, match="Season FH25 not found"):
        package._wait_statuses(page, _quiet(), PackageTarget(OURS), dialogs)


def test_a_shared_collector_stays_attached_after_process_package(
    clock, monkeypatch, tmp_path
):
    frame, _links = _status_frame(clock, lambda: [])
    page = _Page(clock, [frame])
    upload = tmp_path / OURS
    upload.write_bytes(b"x")
    file_input = element("input", id="file")
    file_input.set_input_files = lambda path: None
    process_link = element("a", id="process")
    process_link.on_click = lambda _n: page.fire_dialog("Data uploaded successfully")
    monkeypatch.setattr(
        package, "_attached_in_frames", lambda *a, **kw: (frame, file_input)
    )
    monkeypatch.setattr(
        package,
        "_toolbar_link",
        lambda _page, label, timeout_s=0: (
            frame,
            process_link if label == "Process Package" else element("a"),
        ),
    )
    dialogs = _DialogCollector().attach(page)

    package._process_package(page, upload, _quiet(), dialogs)

    # Caller giữ collector tới khi đọc xong trạng thái; hàm không được gỡ nó.
    assert len(page.listeners) == 1
    dialogs.detach()
    assert page.listeners == []


# --- Pending đúng dòng ------------------------------------------------------


def test_pending_is_clicked_on_our_row_not_the_first_one_on_the_page(clock):
    frame, links = _status_frame(
        clock,
        lambda: [_row(OLD, 0), _row(OURS, 1)],
        links=("Pending", "Pending"),
    )
    page = _Page(clock, [frame])

    transaction._click_pending_transaction(page, PackageTarget(OURS))

    old_link, our_link = (row.children[0] for row in links)
    assert our_link.clicks == 1
    assert old_link.clicks == 0


def test_an_older_pending_is_never_used_when_ours_has_none(clock):
    frame, links = _status_frame(
        clock,
        lambda: [_row(OLD, 0), _row(OURS, 1, transaction="")],
        links=("Pending", ""),
    )
    page = _Page(clock, [frame])

    with pytest.raises(PlaywrightTimeoutError, match="package vừa upload"):
        transaction._click_pending_transaction(page, PackageTarget(OURS))

    assert links[0].children[0].clicks == 0


# --- banner thành công cũ -----------------------------------------------


def _banner_page(clock, text, *, visible=True):
    banner = element("span", id="lblSuccessMsg", text=text, visible=visible)
    frame = MiniFrame(Element("body", children=[banner]), clock=clock)
    return _Page(clock, [frame]), frame, banner


def test_a_banner_already_shown_before_the_click_is_not_a_confirmation(clock):
    page, _frame, _banner = _banner_page(clock, "Data uploaded successfully")
    before = frozenset(transaction._success_banner_texts(page))

    confirmed, _messages = transaction._wait_transaction_confirmed(
        page, transaction._CreateTransactionDialogs(), 3, before
    )

    assert before == {"Data uploaded successfully"}
    assert confirmed is False


def test_a_new_banner_after_the_click_confirms(clock):
    page, frame, _banner = _banner_page(clock, "Data uploaded successfully")
    before = frozenset(transaction._success_banner_texts(page))
    page.ticks.append(
        lambda: frame.root.append(
            element("span", id="lblMsg", css_class="success", text="Transaction created")
        )
        if len(frame.root.children) == 1
        else None
    )

    confirmed, messages = transaction._wait_transaction_confirmed(
        page, transaction._CreateTransactionDialogs(), 5, before
    )

    assert confirmed is True
    assert messages == ["Transaction created"]


def test_the_same_text_counts_once_it_has_disappeared_and_come_back(clock):
    page, _frame, banner = _banner_page(clock, "Created successfully")
    before = frozenset(transaction._success_banner_texts(page))
    # Mỗi lần chờ 300 ms chạy nhiều tick; banner ẩn đủ lâu để vòng đọc thấy.
    steps = iter([False] * 5)
    page.ticks.append(lambda: setattr(banner, "visible", next(steps, True)))

    confirmed, _messages = transaction._wait_transaction_confirmed(
        page, transaction._CreateTransactionDialogs(), 5, before
    )

    assert confirmed is True


def test_a_hidden_banner_is_never_evidence(clock):
    page, _frame, _banner = _banner_page(clock, "Created", visible=False)

    confirmed, _messages = transaction._wait_transaction_confirmed(
        page, transaction._CreateTransactionDialogs(), 3
    )

    assert confirmed is False


# --- Confirm/Reject: bảng đang vẽ lại, alert từ chối, giữ tiến độ --------


def _style(key="S1", label="Style 1"):
    return {"key": key, "label": label}


def _wire(monkeypatch, frame, reads, *, on_click=None, processed=True):
    queue = list(reads)
    monkeypatch.setattr(
        confirm,
        "_read_confirm_styles",
        lambda _frame: queue[0] if len(queue) == 1 else queue.pop(0),
    )
    monkeypatch.setattr(confirm, "_confirm_frame", lambda *a, **kw: frame)
    monkeypatch.setattr(confirm, "_focus_confirm_grid", lambda *a: None)
    monkeypatch.setattr(confirm, "_select_confirm_style", lambda *a: None)
    clicks: list[int] = []

    def click(page):
        clicks.append(1)
        if on_click is not None:
            on_click(page)

    monkeypatch.setattr(confirm, "_click_confirm_toolbar", click)
    monkeypatch.setattr(confirm, "_click_reject_toolbar", click)

    def wait(_page, _frame, _key, *, timeout_s, abort=None):
        if abort is not None and abort():
            return False
        return processed

    monkeypatch.setattr(confirm, "_wait_style_processed", wait)
    return clicks


def test_a_grid_being_redrawn_is_not_mistaken_for_an_empty_tab(clock, monkeypatch):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _Page(clock, [frame])
    clicks = _wire(monkeypatch, frame, [None, None, [_style()], None, []])

    result = confirm._confirm_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_FAST_CONFIRM_COMPLETED"
    assert result["confirmed_styles"] == 1
    assert len(clicks) == 1


def test_a_grid_that_never_comes_back_is_not_ready_rather_than_done(
    clock, monkeypatch
):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _Page(clock, [frame])
    _wire(monkeypatch, frame, [None])

    with pytest.raises(PlaywrightTimeoutError, match="không hiện lại"):
        confirm._confirm_all_pending(page, frame, "new", _quiet())


def test_styles_already_confirmed_survive_a_later_failure(clock, monkeypatch):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _Page(clock, [frame])
    clicks = _wire(monkeypatch, frame, [[_style("S1"), _style("S2")], [_style("S2")], None])

    result = confirm._confirm_all_pending(page, frame, "new", _quiet())

    assert len(clicks) == 2
    assert result["ok"] is False
    assert result["code"] == "OC_FAST_CONFIRM_NOT_READY"
    assert result["confirmed_styles"] == 2
    assert result["confirmation_submitted"] is True
    assert "Đã Confirm 2 Style" in result["message"]


def test_a_wfx_refusal_alert_stops_confirm_without_a_second_click(
    clock, monkeypatch
):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _Page(clock, [frame])
    fired: list[_Dialog] = []
    clicks = _wire(
        monkeypatch,
        frame,
        [[_style()]],
        on_click=lambda p: fired.append(p.fire_dialog("Please select WFX Sales Order")),
        processed=False,
    )

    result = confirm._confirm_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_FAST_CONFIRM_REFUSED"
    assert "Please select WFX Sales Order" in result["message"]
    assert result["stopped_style"] == "Style 1"
    assert result["confirmation_submitted"] is True
    assert len(clicks) == 1
    assert fired[0].accepted == 1
    assert page.listeners == []


def test_a_confirm_question_from_wfx_is_answered_not_treated_as_refusal(
    clock, monkeypatch
):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _Page(clock, [frame])
    fired: list[_Dialog] = []
    _wire(
        monkeypatch,
        frame,
        [[_style()], []],
        on_click=lambda p: fired.append(p.fire_dialog("Are you sure?", "confirm")),
    )

    result = confirm._confirm_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_FAST_CONFIRM_COMPLETED"
    assert fired[0].accepted == 1


def test_a_success_alert_after_confirm_is_not_a_refusal():
    dialogs = _DialogCollector()
    dialogs.handle(_Dialog("Confirmed successfully"))

    assert dialogs.refusal() == ""


def test_a_negative_sentence_wins_over_a_success_word():
    dialogs = _DialogCollector()
    dialogs.handle(_Dialog("Cannot reject: PO already confirmed"))

    assert dialogs.refusal() == "Cannot reject: PO already confirmed"


def test_a_wfx_refusal_alert_stops_reject_all(clock, monkeypatch):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _Page(clock, [frame])
    clicks = _wire(
        monkeypatch,
        frame,
        [[_style("PO1", "PO-1")]],
        on_click=lambda p: p.fire_dialog("Cannot reject: PO already confirmed"),
        processed=False,
    )

    result = confirm._reject_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_REJECT_ALL_REFUSED"
    assert result["stopped_row"] == "PO-1"
    assert result["rejection_submitted"] is True
    assert len(clicks) == 1


def test_rejected_rows_survive_a_later_failure(clock, monkeypatch):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _Page(clock, [frame])
    _wire(monkeypatch, frame, [[_style("PO1", "PO-1")], None])

    result = confirm._reject_all_pending(page, frame, "new", _quiet())

    assert result["code"] == "OC_REJECT_ALL_NOT_READY"
    assert result["rejected_rows"] == 1
    assert result["rejection_submitted"] is True


def test_a_redrawn_grid_never_counts_as_the_style_leaving(clock, monkeypatch):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _Page(clock, [frame])
    monkeypatch.setattr(confirm, "_read_confirm_styles", lambda _frame: None)
    monkeypatch.setattr(confirm, "_confirm_frame", lambda *a, **kw: frame)

    assert confirm._wait_style_processed(page, frame, "S1", timeout_s=3) is False


def test_a_refusal_ends_the_style_wait_at_once(clock, monkeypatch):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _Page(clock, [frame])
    monkeypatch.setattr(confirm, "_read_confirm_styles", lambda _frame: [_style()])
    started = clock.monotonic()

    processed = confirm._wait_style_processed(
        page, frame, "S1", timeout_s=180, abort=lambda: "WFX error"
    )

    assert processed is False
    assert clock.monotonic() - started < 1
