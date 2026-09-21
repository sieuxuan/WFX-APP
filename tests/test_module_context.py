"""Nhận diện frame đang phục vụ đúng module List.

CLAUDE.md: OC/Sample/Sale ASN và Buyer/Supplier dùng selector trùng nhau;
Supplier Inv List và Expense Inv List còn dùng chung cả `#titlebarAPInvoiceList`
lẫn `#gridAPInvoiceList`. Frame chỉ được nhận khi có ĐỦ bộ cột filter riêng của
đúng module — thiếu thì phải tự mở lại List, tuyệt đối không Search nhầm màn.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation.modules.context as module_context
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError
from wfx_panel.automation.modules.constants import _MODULE_LOADING_SELECTOR
from wfx_panel.automation.search_specs import (
    EXPENSE_INVOICE_SEARCH_SPEC,
    INDENT_SEARCH_SPECS,
    SUPPLIER_INVOICE_SEARCH_SPEC,
)


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, module_context)


class Node:
    def __init__(self, *, visible=True, text=""):
        self.visible = visible
        self.text = text

    def is_visible(self, **_kwargs):
        return self.visible

    def text_content(self, **_kwargs):
        return self.text


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


class ContextFrame:
    def __init__(
        self,
        nodes=None,
        *,
        url="https://wfx.test/wfx/WFX_APInvoiceList.aspx",
        marker="",
        broken=False,
        marker_error=None,
    ):
        self.nodes = dict(nodes or {})
        self.url = url
        self.marker = marker
        self.broken = broken
        self.marker_error = marker_error

    def locator(self, selector):
        if self.broken:
            raise PlaywrightError("frame đã detach")
        return NodeList(self.nodes.get(selector, ()))

    def evaluate(self, _script, _arg=None):
        if self.marker_error is not None:
            raise self.marker_error
        return self.marker


class ContextPage:
    def __init__(self, *frames, clock=None):
        self.frames = list(frames)
        self.clock = clock

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


def _fields(spec, *, missing=()):
    """Node cho mọi ô filter của spec, trừ những ô cố ý bỏ trống."""
    nodes: dict[str, list[Node]] = {}
    for name, field_spec in spec.fields.items():
        selector = ", ".join(field_spec.selectors)
        nodes[selector] = [] if name in missing else [Node()]
    return nodes


# --- marker frame -------------------------------------------------------


def test_a_frame_that_cannot_be_read_has_no_marker():
    frame = ContextFrame(marker_error=PlaywrightError("frame đã detach"))

    assert module_context._frame_context_marker(frame) == ""


def test_the_marker_is_case_folded_so_comparisons_are_stable():
    frame = ContextFrame(marker="https://WFX.test/OC  Expense Invoice")

    assert module_context._frame_context_marker(frame) == (
        "https://wfx.test/oc  expense invoice"
    )


# --- đủ bộ cột filter ---------------------------------------------------


def test_a_frame_with_every_filter_column_serves_the_module():
    spec = SUPPLIER_INVOICE_SEARCH_SPEC
    frame = ContextFrame(_fields(spec))

    assert module_context._frame_has_every_search_field(frame, spec) is True


def test_a_frame_missing_one_filter_column_does_not_serve_the_module():
    spec = SUPPLIER_INVOICE_SEARCH_SPEC
    missing = next(iter(spec.fields))
    frame = ContextFrame(_fields(spec, missing={missing}))

    assert module_context._frame_has_every_search_field(frame, spec) is False


def test_a_filter_column_that_is_present_but_hidden_does_not_count():
    spec = SUPPLIER_INVOICE_SEARCH_SPEC
    nodes = _fields(spec)
    first = next(iter(nodes))
    nodes[first] = [Node(visible=False)]
    frame = ContextFrame(nodes)

    assert module_context._frame_has_every_search_field(frame, spec) is False


def test_a_detached_frame_never_serves_a_module():
    assert (
        module_context._frame_has_every_search_field(
            ContextFrame(broken=True), SUPPLIER_INVOICE_SEARCH_SPEC
        )
        is False
    )


def test_a_frame_without_a_spec_is_always_accepted():
    assert module_context._frame_serves_search_spec(ContextFrame(), None) is True


def test_the_expense_invoice_screen_is_rejected_when_supplier_is_wanted():
    """Hai màn dùng chung id grid; marker của màn kia là bằng chứng loại trừ."""
    spec = SUPPLIER_INVOICE_SEARCH_SPEC
    assert spec.foreign_markers, "spec phải có marker để phân biệt hai màn"
    frame = ContextFrame(
        _fields(spec), marker=f"https://wfx.test/{spec.foreign_markers[0]}"
    )

    assert module_context._frame_serves_search_spec(frame, spec) is False


def test_the_right_screen_with_the_right_columns_is_accepted():
    spec = EXPENSE_INVOICE_SEARCH_SPEC
    frame = ContextFrame(_fields(spec), marker="expense invoice list")

    assert module_context._frame_serves_search_spec(frame, spec) is True


# --- phân biệt hai Indent List -----------------------------------------


@pytest.mark.parametrize(
    ("module_name", "title", "expected"),
    [
        ("Indent List", "WFX · Indent List", True),
        ("Indent List", "WFX · User Indent", False),
        ("User Indent", "WFX · User Indent", True),
        ("User Indent", "WFX · Indent List", False),
    ],
)
def test_the_two_indent_screens_are_told_apart_by_their_title(
    module_name, title, expected
):
    frame = ContextFrame({"title": [Node(text=title)]})

    assert (
        module_context._frame_matches_module_context(frame, module_name)
        is expected
    )


def test_an_indent_frame_without_a_title_is_refused():
    assert (
        module_context._frame_matches_module_context(
            ContextFrame(), "Indent List"
        )
        is False
    )


def test_an_indent_frame_that_detaches_is_refused():
    assert (
        module_context._frame_matches_module_context(
            ContextFrame(broken=True), "User Indent"
        )
        is False
    )


def test_a_module_without_a_lookalike_needs_no_extra_check():
    assert (
        module_context._frame_matches_module_context(ContextFrame(), "OC List")
        is True
    )
    assert module_context._frame_matches_module_context(ContextFrame(), None) is True


# --- Sale ASN cần AG Grid đang hiện -------------------------------------


def test_a_sale_asn_form_url_without_a_grid_is_not_the_list():
    frame = ContextFrame(url="https://wfx.test/wfx/WFXSalesASN.aspx")

    assert (
        module_context._frame_matches_module_context(frame, "Sale ASN") is False
    )


def test_a_sale_asn_list_with_a_visible_grid_is_accepted():
    frame = ContextFrame(
        {".ag-root-wrapper": [Node(visible=False), Node()]},
        url="https://wfx.test/wfx/WFXSalesASNList.aspx",
    )

    assert (
        module_context._frame_matches_module_context(frame, "Sale ASN") is True
    )


def test_another_module_url_is_never_taken_for_sale_asn():
    frame = ContextFrame(
        {".ag-root-wrapper": [Node()]},
        url="https://wfx.test/wfx/WFX_OCList.aspx",
    )

    assert (
        module_context._frame_matches_module_context(frame, "Sale ASN") is False
    )


def test_a_sale_asn_frame_that_detaches_is_refused():
    frame = ContextFrame(broken=True, url="https://wfx.test/wfx/WFXSalesASN.aspx")

    assert (
        module_context._frame_matches_module_context(frame, "Sale ASN") is False
    )


# --- chọn frame trong page ---------------------------------------------


CONTEXT = "#titlebarAPInvoiceList"


def test_the_first_frame_that_passes_every_check_is_used(clock):
    spec = SUPPLIER_INVOICE_SEARCH_SPEC
    wrong = ContextFrame({CONTEXT: [Node()]}, **{})
    right = ContextFrame({CONTEXT: [Node()], **_fields(spec)})
    page = ContextPage(wrong, right, clock=clock)

    assert (
        module_context._frame_with_visible_context(
            page, CONTEXT, search_spec=spec, timeout_s=5
        )
        is right
    )


def test_a_context_node_that_is_hidden_does_not_qualify(clock):
    spec = SUPPLIER_INVOICE_SEARCH_SPEC
    frame = ContextFrame({CONTEXT: [Node(visible=False)], **_fields(spec)})
    page = ContextPage(frame, clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match=CONTEXT):
        module_context._frame_with_visible_context(
            page, CONTEXT, search_spec=spec, timeout_s=1
        )


def test_a_detached_frame_does_not_stop_the_scan(clock):
    spec = SUPPLIER_INVOICE_SEARCH_SPEC
    right = ContextFrame({CONTEXT: [Node()], **_fields(spec)})
    page = ContextPage(ContextFrame(broken=True), right, clock=clock)

    assert (
        module_context._frame_with_visible_context(
            page, CONTEXT, search_spec=spec, timeout_s=5
        )
        is right
    )


def test_a_page_with_no_matching_frame_times_out(clock):
    page = ContextPage(ContextFrame(), clock=clock)

    with pytest.raises(PlaywrightTimeoutError):
        module_context._frame_with_visible_context(page, CONTEXT, timeout_s=1)


def test_an_indent_frame_is_checked_by_both_title_and_columns(clock):
    spec = INDENT_SEARCH_SPECS["Indent List"]
    wrong_title = ContextFrame(
        {
            CONTEXT: [Node()],
            "title": [Node(text="User Indent")],
            **_fields(spec),
        }
    )
    right = ContextFrame(
        {
            CONTEXT: [Node()],
            "title": [Node(text="Indent List")],
            **_fields(spec),
        }
    )
    page = ContextPage(wrong_title, right, clock=clock)

    assert (
        module_context._frame_with_visible_context(
            page,
            CONTEXT,
            module_name="Indent List",
            search_spec=spec,
            timeout_s=5,
        )
        is right
    )


# --- chờ kết quả search ổn định ----------------------------------------


def test_a_search_is_only_settled_after_the_overlay_stays_gone(clock):
    frame = ContextFrame({_MODULE_LOADING_SELECTOR: []})
    page = ContextPage(frame, clock=clock)
    started = clock.monotonic()

    module_context._wait_module_search_settled(page, ["Supplier"])

    assert clock.monotonic() - started >= 0.8


def test_an_overlay_that_never_clears_is_reported_with_the_labels(clock):
    frame = ContextFrame({_MODULE_LOADING_SELECTOR: [Node()]})
    page = ContextPage(frame, clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="Supplier, Invoice No."):
        module_context._wait_module_search_settled(
            page, ["Supplier", "Invoice No."]
        )


def test_an_overlay_that_reappears_restarts_the_stability_window(clock):
    overlay = Node()
    frame = ContextFrame({_MODULE_LOADING_SELECTOR: [overlay]})
    page = ContextPage(frame, clock=clock)
    ticks = {"n": 0}
    original = page.wait_for_timeout

    def tick(milliseconds):
        ticks["n"] += 1
        # WFX tắt overlay một nhịp rồi bật lại vì postback thứ hai.
        overlay.visible = ticks["n"] not in {2, 3}
        original(milliseconds)

    page.wait_for_timeout = tick

    with pytest.raises(PlaywrightTimeoutError):
        module_context._wait_module_search_settled(page, ["Supplier"])


def test_a_detached_frame_does_not_count_as_a_loading_overlay(clock):
    page = ContextPage(
        ContextFrame(broken=True),
        ContextFrame({_MODULE_LOADING_SELECTOR: []}),
        clock=clock,
    )

    module_context._wait_module_search_settled(page, ["Supplier"])
