"""Hạ tầng dùng chung của lớp automation: click, chờ frame, và marker document.

Đây là các primitive mọi flow đều đi qua, nên mỗi nhánh chịu lỗi ở đây quyết
định app báo lỗi thật hay báo nhầm: một frame vừa detach không được tính là
"chưa mở", còn một console không in được Unicode không được làm hỏng flow.
"""

from __future__ import annotations

import pytest

from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, _common)


class Node:
    def __init__(
        self,
        *,
        visible=True,
        value="",
        click_error=None,
        visible_error=None,
        options=(),
    ):
        self.visible = visible
        self.value = value
        self.click_error = click_error
        self.visible_error = visible_error
        self.options = list(options)
        self.clicks = 0
        self.js_clicks = 0
        self.events: list[str] = []
        self.selected: list[str] = []
        self.waits = 0

    def is_visible(self, **_kwargs):
        if self.visible_error is not None:
            raise self.visible_error
        return self.visible

    def wait_for(self, **_kwargs):
        self.waits += 1

    def click(self, **_kwargs):
        if self.click_error is not None:
            raise self.click_error
        self.clicks += 1

    def evaluate(self, _script, _arg=None):
        self.js_clicks += 1

    def input_value(self, **_kwargs):
        return self.value

    def dispatch_event(self, event, **_kwargs):
        self.events.append(event)

    def select_option(self, value=None, **_kwargs):
        self.selected.append(value)
        if value in self.options:
            self.value = value

    def locator(self, selector):
        wanted = selector.removeprefix('option[value="').removesuffix('"]')
        return NodeList([Node()] if wanted in self.options else [])

    def count(self):
        return 1


class NodeList:
    def __init__(self, nodes):
        self.nodes = list(nodes)

    @property
    def first(self):
        return self.nodes[0]

    def count(self):
        return len(self.nodes)

    def nth(self, index):
        return self.nodes[index]

    def wait_for(self, **_kwargs):
        if not self.nodes:
            raise PlaywrightTimeoutError("option chưa xuất hiện")


class CommonFrame:
    def __init__(self, nodes=None, *, broken=False):
        self.nodes = dict(nodes or {})
        self.broken = broken
        self.markers: dict[str, str] = {}

    def locator(self, selector):
        if self.broken:
            raise PlaywrightError("frame đã detach")
        node = self.nodes.get(selector)
        if node is None:
            return NodeList([])
        return node if isinstance(node, NodeList) else node

    def evaluate(self, script, arg=None):
        if self.broken:
            raise PlaywrightError("frame đã detach")
        name = "__wfxPanelDocumentMarker"
        if name in script:
            if "=" in script.split(name, 1)[1][:4]:
                self.markers[name] = str(arg)
                return None
            return self.markers.get(name, "")
        raise AssertionError(f"script lạ: {script[:60]}")


class CommonPage:
    def __init__(self, *frames, clock=None):
        self.frames = list(frames)
        self.clock = clock

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


# --- ghi log ------------------------------------------------------------


def test_a_console_that_cannot_print_unicode_still_gets_the_message():
    written: list[str] = []

    def fussy(message):
        if any(ord(character) > 127 for character in message):
            raise UnicodeEncodeError("ascii", message, 0, 1, "console cũ")
        written.append(message)

    _common._write_log(fussy, "Đã mở Catalog")

    assert written == ["\\u0110\\xe3 m\\u1edf Catalog"]


def test_a_plain_ascii_message_is_written_as_is():
    written: list[str] = []

    _common._write_log(written.append, "Opened Catalog")

    assert written == ["Opened Catalog"]


# --- click có fallback --------------------------------------------------


def test_a_visible_menu_is_clicked_normally():
    node = Node()

    _common._click(node)

    assert (node.clicks, node.js_clicks) == (1, 0)


def test_a_hidden_menu_falls_back_to_a_javascript_click():
    node = Node(click_error=PlaywrightTimeoutError("node bị che"))

    _common._click(node)

    assert (node.clicks, node.js_clicks) == (0, 1)


# --- node đầu tiên đang hiện --------------------------------------------


def test_the_first_visible_node_is_returned():
    wanted = Node()
    nodes = NodeList([Node(visible=False), wanted, Node()])

    assert _common._first_visible(nodes) is wanted


def test_a_node_that_throws_while_being_probed_is_skipped():
    wanted = Node()
    nodes = NodeList(
        [Node(visible_error=PlaywrightError("node đã bị thay")), wanted]
    )

    assert _common._first_visible(nodes) is wanted


def test_nothing_visible_yields_nothing():
    assert _common._first_visible(NodeList([Node(visible=False)])) is None


# --- chờ frame theo selector --------------------------------------------


def test_the_frame_holding_every_selector_is_returned(clock):
    half = CommonFrame({"#a": NodeList([Node()])})
    full = CommonFrame({"#a": NodeList([Node()]), "#b": NodeList([Node()])})
    page = CommonPage(half, full, clock=clock)

    assert _common._wait_frame_with_selectors(page, ("#a", "#b")) is full


def test_a_detached_frame_does_not_stop_the_frame_scan(clock):
    full = CommonFrame({"#a": NodeList([Node()])})
    page = CommonPage(CommonFrame(broken=True), full, clock=clock)

    assert _common._wait_frame_with_selectors(page, ("#a",)) is full


def test_a_page_without_the_selectors_names_all_of_them(clock):
    page = CommonPage(CommonFrame(), clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="#a, #b"):
        _common._wait_frame_with_selectors(page, ("#a", "#b"), timeout_s=1)


# --- đặt giá trị select --------------------------------------------------


def test_a_select_already_holding_the_value_is_left_alone(clock):
    field = Node(value="1", options=["1"])
    page = CommonPage(CommonFrame({"#ddl": field}), clock=clock)
    lines: list[str] = []

    _common._ensure_select_value(page, "#ddl", "1", "ASN Type", lines.append)

    assert field.selected == []
    assert lines == ["[MODULE NEW] ASN Type đã đúng: 1"]


def test_a_select_is_opened_with_mousedown_before_the_option_is_chosen(clock):
    field = Node(value="2", options=["1", "2"])
    page = CommonPage(CommonFrame({"#ddl": field}), clock=clock)
    lines: list[str] = []

    _common._ensure_select_value(page, "#ddl", "1", "ASN Type", lines.append)

    assert field.events == ["mousedown"]
    assert field.selected == ["1"]
    assert any("Đang chọn ASN Type" in line for line in lines)


def test_a_value_wfx_never_confirms_is_reported_with_what_it_kept(clock):
    field = Node(value="2", options=["1", "2"])

    def refuse(value=None, **_kwargs):
        field.selected.append(value)

    field.select_option = refuse
    page = CommonPage(CommonFrame({"#ddl": field}), clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="current=2"):
        _common._ensure_select_value(page, "#ddl", "1", "ASN Type", print)


def test_an_option_wfx_never_renders_stops_the_wait(clock):
    field = Node(value="2", options=[])
    page = CommonPage(CommonFrame({"#ddl": field}), clock=clock)

    with pytest.raises(PlaywrightTimeoutError):
        _common._ensure_select_value(page, "#ddl", "1", "ASN Type", print)


# --- marker document ----------------------------------------------------


def test_marking_a_frame_that_does_not_exist_still_yields_a_marker():
    frame, marker = _common._mark_document(None, "test")

    assert frame is None
    assert marker.startswith("test-")


def test_two_marks_never_collide():
    _frame, first = _common._mark_document(None, "test")
    _frame, second = _common._mark_document(None, "test")

    assert first != second


def test_a_frame_that_refuses_the_marker_does_not_break_the_snapshot():
    broken = CommonFrame(broken=True)

    frame, marker = _common._mark_document(broken, "test")

    assert frame is broken
    assert marker.startswith("test-")


def test_a_frame_still_holding_its_marker_has_not_changed():
    frame = CommonFrame()
    snapshot = _common._mark_document(frame, "test")

    assert _common._document_changed(frame, snapshot) is False


def test_a_frame_that_lost_its_marker_has_changed():
    frame = CommonFrame()
    snapshot = _common._mark_document(frame, "test")
    frame.markers.clear()

    assert _common._document_changed(frame, snapshot) is True


def test_a_different_frame_object_counts_as_changed():
    snapshot = _common._mark_document(CommonFrame(), "test")

    assert _common._document_changed(CommonFrame(), snapshot) is True


def test_a_snapshot_without_a_frame_always_counts_as_changed():
    assert _common._document_changed(CommonFrame(), (None, "test")) is True


def test_a_frame_that_detaches_before_being_read_counts_as_changed():
    frame = CommonFrame()
    snapshot = _common._mark_document(frame, "test")
    frame.broken = True

    assert _common._document_changed(frame, snapshot) is True
