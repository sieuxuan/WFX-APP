"""Create Transaction: ranh giới ghi dữ liệu không idempotent của OC.

`wfx_panel/automation/oc/transaction.py` ở mức 39%. CLAUDE.md:

* "`Create Transaction` là ranh giới không idempotent. Nếu đã click nhưng không
  đọc được xác nhận, trả `OC_TRANSACTION_UNCONFIRMED` và tuyệt đối không retry
  tự động."

Ngoại lệ duy nhất cho phép bấm lần hai là alert `No Record Selected` — bằng
chứng WFX chưa gửi transaction nào. Test ở đây khoá đúng ranh giới đó.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.oc import transaction


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, transaction, _common)


def _quiet():
    return lambda _line: None


class _Dialog:
    def __init__(self, message):
        self.message = message
        self.accepted = False

    def accept(self):
        self.accepted = True


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
        dialog = _Dialog(message)
        for event, handler in list(self.listeners):
            if event == "dialog":
                handler(dialog)
        return dialog


def _checkbox_row(text, *, visible=True, enabled=True, checked=False, box_id="chk"):
    return Element(
        "tr",
        text=text,
        children=[
            element(
                "input",
                id=box_id,
                attrs={"type": "checkbox"},
                visible=visible,
                enabled=enabled,
                checked=checked,
            )
        ],
    )


def _grid_frame(clock, rows=()):
    return MiniFrame(
        Element("body", children=[Element("table", children=list(rows))]),
        clock=clock,
    )


# --- chọn dòng Pending ----------------------------------------------------


def test_the_pending_link_is_clicked_wherever_it_lives(clock):
    link = element("a", id="pending", text="  Pending  ")
    frame = MiniFrame(Element("body", children=[link]), clock=clock)
    page = _Page(clock, [frame])

    transaction._click_pending_transaction(page)

    assert link.clicks == 1


def test_another_link_is_never_mistaken_for_pending(clock):
    frame = MiniFrame(
        Element("body", children=[element("a", text="Completed")]), clock=clock
    )
    page = _Page(clock, [frame])

    with pytest.raises(PlaywrightTimeoutError, match="Pending"):
        transaction._click_pending_transaction(page)


def test_a_frame_that_throws_never_stops_the_search(clock):
    class Broken:
        url = "https://wfx.test/x"

        def locator(self, _selector):
            raise PlaywrightError("frame rơi")

    link = element("a", text="Pending")
    good = MiniFrame(Element("body", children=[link]), clock=clock)
    page = _Page(clock, [Broken(), good])

    transaction._click_pending_transaction(page)

    assert link.clicks == 1


# --- lọc checkbox ---------------------------------------------------------


def test_the_select_all_row_is_never_offered_as_a_record(clock):
    frame = _grid_frame(
        clock,
        [
            _checkbox_row("Select All", box_id="all"),
            _checkbox_row("PO-1", box_id="row1"),
        ],
    )

    candidates = transaction._transaction_checkboxes(frame)

    assert len(candidates) == 1
    assert candidates[0].get_attribute("id") == "row1"


def test_an_all_records_row_is_also_skipped(clock):
    frame = _grid_frame(
        clock, [_checkbox_row("All Records", box_id="all"), _checkbox_row("PO-1")]
    )

    assert len(transaction._transaction_checkboxes(frame)) == 1


@pytest.mark.parametrize(
    ("visible", "enabled"), [(False, True), (True, False)]
)
def test_a_checkbox_the_user_could_not_click_is_skipped(clock, visible, enabled):
    frame = _grid_frame(
        clock, [_checkbox_row("PO-1", visible=visible, enabled=enabled)]
    )

    assert transaction._transaction_checkboxes(frame) == []


def test_a_frame_without_any_checkbox_yields_nothing(clock):
    assert transaction._transaction_checkboxes(_grid_frame(clock)) == []


# --- chọn dòng đầu tiên ---------------------------------------------------


def _wire_toolbar(monkeypatch, frame, link=None):
    link = link or element("a", id="create")
    monkeypatch.setattr(
        transaction,
        "_toolbar_link",
        lambda _page, _label, timeout_s=0: (frame, link),
    )
    return link


def test_the_first_record_is_ticked_and_confirmed(clock, monkeypatch):
    frame = _grid_frame(clock, [_checkbox_row("PO-1")])
    page = _Page(clock, [frame])
    _wire_toolbar(monkeypatch, frame)

    transaction._select_first_transaction(page)

    assert frame.locator("#chk").node.checked is True


def test_an_already_ticked_record_is_left_alone(clock, monkeypatch):
    frame = _grid_frame(clock, [_checkbox_row("PO-1", checked=True)])
    page = _Page(clock, [frame])
    _wire_toolbar(monkeypatch, frame)

    transaction._select_first_transaction(page)

    assert frame.locator("#chk").node.checks == 0


def test_a_forced_reselect_unticks_then_ticks_again(clock, monkeypatch):
    frame = _grid_frame(clock, [_checkbox_row("PO-1", checked=True)])
    page = _Page(clock, [frame])
    _wire_toolbar(monkeypatch, frame)

    transaction._select_first_transaction(page, force=True)

    assert frame.locator("#chk").node.checked is True
    assert frame.locator("#chk").node.checks == 1


def test_a_grid_with_no_record_is_reported(clock, monkeypatch):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    _wire_toolbar(monkeypatch, frame)

    with pytest.raises(PlaywrightTimeoutError, match="checkbox đơn hàng"):
        transaction._select_first_transaction(page)


def test_a_checkbox_wfx_refuses_to_keep_ticked_is_reported(clock, monkeypatch):
    frame = _grid_frame(clock, [_checkbox_row("PO-1")])
    page = _Page(clock, [frame])
    _wire_toolbar(monkeypatch, frame)
    node = frame.locator("#chk").node
    node.check = lambda **_kwargs: None
    node.click = lambda **_kwargs: None

    with pytest.raises(PlaywrightTimeoutError):
        transaction._select_first_transaction(page)


# --- gom alert ------------------------------------------------------------


def test_a_success_alert_is_recognised():
    dialogs = transaction._CreateTransactionDialogs()

    dialogs.accept(_Dialog("Transaction created successfully"))

    assert dialogs.reports_success is True
    assert dialogs.saw_no_record is False


def test_a_no_record_selected_alert_is_recognised():
    dialogs = transaction._CreateTransactionDialogs()

    dialog = _Dialog("No Record Selected")
    dialogs.accept(dialog)

    assert dialogs.saw_no_record is True
    assert dialogs.reports_success is False
    assert dialog.accepted is True


def test_an_unrelated_alert_means_neither():
    dialogs = transaction._CreateTransactionDialogs()

    dialogs.accept(_Dialog("Đang xử lý"))

    assert dialogs.saw_no_record is False
    assert dialogs.reports_success is False


# --- banner thành công ----------------------------------------------------


def test_a_success_banner_is_read_from_any_frame(clock):
    frame = MiniFrame(
        Element(
            "body",
            children=[
                element("span", id="lblSuccessMsg", text="  Created   OK  ")
            ],
        ),
        clock=clock,
    )

    assert transaction._success_banner_text(_Page(clock, [frame])) == "Created OK"


def test_a_banner_that_does_not_say_success_is_ignored(clock):
    frame = MiniFrame(
        Element(
            "body",
            children=[element("span", id="lblSuccessMsg", text="Đang chờ")],
        ),
        clock=clock,
    )

    assert transaction._success_banner_text(_Page(clock, [frame])) == ""


def test_a_frame_that_throws_never_breaks_the_banner_read(clock):
    class Broken:
        url = "https://wfx.test/x"

        def locator(self, _selector):
            raise PlaywrightError("frame rơi")

    assert transaction._success_banner_text(_Page(clock, [Broken()])) == ""


# --- chờ xác nhận ---------------------------------------------------------


def test_a_success_alert_confirms_the_transaction(clock):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    dialogs = transaction._CreateTransactionDialogs()
    dialogs.accept(_Dialog("Transaction created"))

    confirmed, messages = transaction._wait_transaction_confirmed(page, dialogs)

    assert confirmed is True
    assert messages == ["Transaction created"]


def test_a_no_record_alert_ends_the_wait_as_unconfirmed(clock):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    dialogs = transaction._CreateTransactionDialogs()
    dialogs.accept(_Dialog("No Record Selected"))

    confirmed, _messages = transaction._wait_transaction_confirmed(page, dialogs)

    assert confirmed is False


def test_a_banner_confirms_the_transaction_when_no_alert_arrived(clock):
    frame = MiniFrame(
        Element(
            "body",
            children=[element("span", id="lblSuccessMsg", text="Created")],
        ),
        clock=clock,
    )
    page = _Page(clock, [frame])

    confirmed, messages = transaction._wait_transaction_confirmed(
        page, transaction._CreateTransactionDialogs()
    )

    assert confirmed is True
    assert messages == ["Created"]


def test_silence_from_wfx_is_never_a_success(clock):
    page = _Page(clock, [_grid_frame(clock)])

    confirmed, messages = transaction._wait_transaction_confirmed(
        page, transaction._CreateTransactionDialogs(), timeout_s=2
    )

    assert confirmed is False
    assert messages == []


# --- toàn bộ Create Transaction ------------------------------------------


def _wire_create(monkeypatch, frame, link):
    selections: list[bool] = []
    monkeypatch.setattr(
        transaction,
        "_select_first_transaction",
        lambda _page, force=False: selections.append(force),
    )
    monkeypatch.setattr(
        transaction,
        "_toolbar_link",
        lambda _page, _label, timeout_s=0: (frame, link),
    )
    return selections


def test_a_confirmed_transaction_is_clicked_exactly_once(clock, monkeypatch):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    link = element("a", id="create")
    selections = _wire_create(monkeypatch, frame, link)
    link.on_click = lambda _n: page.fire_dialog("Transaction created successfully")
    logs: list[str] = []

    confirmed, messages = transaction._create_transaction(page, logs.append)

    assert confirmed is True
    assert link.clicks == 1
    assert selections == [False]
    assert messages
    assert page.listeners == []
    assert any("Đã gửi Create Transaction" in line for line in logs)


def test_a_lost_confirmation_never_clicks_a_second_time(clock, monkeypatch):
    """CLAUDE.md: mất xác nhận thì dừng, tuyệt đối không retry."""
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    link = element("a", id="create")
    selections = _wire_create(monkeypatch, frame, link)
    monkeypatch.setattr(
        transaction, "_wait_transaction_confirmed", lambda *a, **kw: (False, [])
    )

    confirmed, _messages = transaction._create_transaction(page, _quiet())

    assert confirmed is False
    assert link.clicks == 1
    assert selections == [False]


def test_a_no_record_selected_alert_allows_exactly_one_more_attempt(
    clock, monkeypatch
):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    link = element("a", id="create")
    selections = _wire_create(monkeypatch, frame, link)
    link.on_click = lambda _n: page.fire_dialog("No Record Selected")
    logs: list[str] = []

    confirmed, _messages = transaction._create_transaction(page, logs.append)

    assert confirmed is False
    assert link.clicks == 2
    # Lượt hai phải chọn lại dòng bằng force.
    assert selections == [False, True]
    assert any("chọn lại" in line for line in logs)


def test_the_second_attempt_can_still_succeed(clock, monkeypatch):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    link = element("a", id="create")
    _wire_create(monkeypatch, frame, link)
    attempts: list[int] = []

    def click(_node):
        attempts.append(1)
        page.fire_dialog(
            "No Record Selected" if len(attempts) == 1 else "Created successfully"
        )

    link.on_click = click

    confirmed, _messages = transaction._create_transaction(page, _quiet())

    assert confirmed is True
    assert link.clicks == 2


def test_the_dialog_listener_is_always_removed(clock, monkeypatch):
    frame = _grid_frame(clock)
    page = _Page(clock, [frame])
    link = element("a", id="create")
    _wire_create(monkeypatch, frame, link)
    monkeypatch.setattr(
        transaction,
        "_wait_transaction_confirmed",
        lambda *a, **kw: (_ for _ in ()).throw(PlaywrightError("tab rơi")),
    )

    with pytest.raises(PlaywrightError):
        transaction._create_transaction(page, _quiet())

    assert page.listeners == []
