"""Nhận diện frame Buyer/Supplier và điền ô Company khi WFX thay frame.

CLAUDE.md: Buyer/Supplier chỉ được resolve lại frame cùng PartyType với flow
ban đầu — hai màn dùng chung `#txtCompanyName` nên nhận nhầm là tìm trên màn
của người khác.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation._common as common
import wfx_panel.automation.directory.company_query as company_query
import wfx_panel.automation.directory.frames as frames_module
from tests.fakes.wfx_dom import FakeLocator, FakeNode, install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError

SUPPLIER_MARKER = "https://wfx.test/wfxpartygroup.aspx?partytype=2 supplier list"
BUYER_MARKER = "https://wfx.test/wfxpartygroup.aspx?partytype=1 buyer list"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(
        monkeypatch, frames_module, company_query, common
    )


class Frame:
    """Frame WFX tối giản: bảng selector + marker + hàng kết quả Company."""

    def __init__(
        self,
        nodes=None,
        *,
        url="https://wfx.test/wfxpartygroup.aspx?partytype=2",
        title="Supplier List",
        marker=SUPPLIER_MARKER,
        rows=None,
        clock=None,
        locator_error=None,
        marker_error=None,
        rows_error=None,
        busy=False,
    ):
        self.nodes = dict(nodes or {})
        self.url = url
        self.title = title
        self.marker = marker
        self.rows = rows if rows is not None else {"rows": [], "noRows": True}
        self.clock = clock
        self.locator_error = locator_error
        self.marker_error = marker_error
        self.rows_error = rows_error
        self.busy = busy
        self.evaluations = 0

    def locator(self, selector):
        if self.locator_error is not None:
            raise self.locator_error
        custom = self.nodes.get(selector)
        if isinstance(custom, (SelectLocator, FieldLocator)):
            return custom
        return FakeLocator(custom or [], selector)

    def evaluate(self, script, _arg=None):
        self.evaluations += 1
        if "(args) =>" in script:
            if self.rows_error is not None:
                raise self.rows_error
            return self.rows
        if "party.?type" in script:
            if self.marker_error is not None:
                raise self.marker_error
            return self.marker
        if "aria-busy" in script:
            return self.busy
        return self.title

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


class Page:
    def __init__(self, *frames, clock=None):
        self.frames = list(frames)
        self.clock = clock

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)


class SelectLocator:
    """Locator cho `#ddlCategory`: mousedown mới bind đủ option như WFX."""

    def __init__(self, node, *, options=("01", "05"), confirm_error=None):
        self.node = node
        self.options = tuple(options)
        self.confirm_error = confirm_error
        self.reads = 0
        self.selected: list[str] = []

    def count(self):
        return 1

    def input_value(self, timeout=None):
        self.reads += 1
        if timeout is not None and self.confirm_error is not None:
            raise self.confirm_error
        return self.node.value

    def dispatch_event(self, _event):
        return None

    def locator(self, selector):
        value = selector.split('"')[1]
        return SelectLocator(self.node) if value in self.options else _Empty()

    def wait_for(self, state=None, timeout=None):
        return None

    def select_option(self, value=None, timeout=None):
        self.selected.append(str(value))
        self.node.value = str(value)


class _Empty:
    def wait_for(self, state=None, timeout=None):
        raise PlaywrightTimeoutError("option chưa được bind")


class FieldLocator:
    """Locator cho `#txtCompanyName`: có `type()` như Playwright thật."""

    def __init__(self, node):
        self.node = node

    def count(self):
        return 1

    @property
    def first(self):
        return self

    def wait_for(self, state=None, timeout=None):
        self.node.wait_for(state, timeout)

    def fill(self, value, timeout=None):
        self.node.fill(value, timeout)

    def type(self, value, delay=0):
        self.node.type(value, delay)

    def input_value(self, timeout=None):
        return self.node.input_value(timeout)

    def press(self, key, timeout=None):
        self.node.press(key, timeout)

    def is_visible(self):
        return self.node.is_visible()

    def is_enabled(self):
        return self.node.is_enabled()


def _category(value="01", **kwargs):
    return {"#ddlCategory": SelectLocator(FakeNode(value=value), **kwargs)}


def _company(value="", **kwargs):
    return {"#txtCompanyName": [FakeNode(value=value, **kwargs)]}


def _query_field(**kwargs):
    field = QueryField(**kwargs)
    return field, {"#txtCompanyName": FieldLocator(field)}


# --- nhận diện frame Supplier -------------------------------------------


def test_the_catalog_category_dropdown_is_never_mistaken_for_supplier(clock):
    catalog = Frame(
        _category(),
        url="https://wfx.test/WFX_CatalogMain.aspx",
        title="Catalog",
    )

    assert frames_module._supplier_category_frame(Page(catalog)) is None


def test_a_frame_without_a_category_dropdown_is_skipped(clock):
    page = Page(Frame({}), Frame(_category()))

    assert frames_module._supplier_category_frame(page) is page.frames[1]


def test_the_supplier_frame_is_recognised_by_its_title_when_the_url_is_plain(
    clock,
):
    frame = Frame(
        _category(), url="https://wfx.test/list.aspx", title="Supplier List"
    )

    assert frames_module._supplier_category_frame(Page(frame)) is frame


def test_a_frame_that_detaches_mid_scan_does_not_stop_the_search(clock):
    good = Frame(_category())
    page = Page(Frame(locator_error=PlaywrightError("detached")), good)

    assert frames_module._supplier_category_frame(page) is good


def test_waiting_for_the_supplier_list_survives_a_frame_that_throws(
    clock, monkeypatch
):
    broken = Frame(_category(), locator_error=None, clock=clock)
    calls = {"n": 0}

    def flaky(_selector):
        # Lời gọi đầu là của `_supplier_category_frame`; lời gọi thứ hai mới là
        # của chính vòng chờ, và đó là chỗ frame kịp detach.
        calls["n"] += 1
        if calls["n"] == 2:
            raise PlaywrightError("frame was detached")
        return SelectLocator(FakeNode(value="01"))

    broken.locator = flaky
    monkeypatch.setattr(
        frames_module, "_document_changed", lambda _frame, _snapshot: True
    )

    assert frames_module._wait_supplier_left(
        Page(broken, clock=clock), (None, ""), 5
    ) is broken


def test_a_supplier_list_that_never_opens_times_out(clock):
    page = Page(clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="Supplier List"):
        frames_module._wait_supplier_left(page, (None, ""), 1)


# --- chọn Category -------------------------------------------------------


def test_a_category_that_is_already_selected_is_not_clicked_again(
    clock, monkeypatch
):
    frame = Frame(_category("05"), clock=clock)
    monkeypatch.setattr(
        frames_module, "_document_changed", lambda _frame, _snapshot: True
    )

    changed = frames_module._select_supplier_category(
        Page(frame, clock=clock), "Trims", "05", lambda _line: None
    )

    assert changed is False


def test_a_category_is_bound_by_mousedown_before_it_can_be_selected(
    clock, monkeypatch
):
    nodes = _category("01")
    frame = Frame(nodes, clock=clock)
    monkeypatch.setattr(
        frames_module, "_document_changed", lambda _frame, _snapshot: True
    )

    changed = frames_module._select_supplier_category(
        Page(frame, clock=clock), "Trims", "05", lambda _line: None
    )

    assert changed is True
    assert nodes["#ddlCategory"].selected == ["05"]


def test_a_category_wfx_never_confirms_is_a_timeout(clock, monkeypatch):
    nodes = _category("01", confirm_error=PlaywrightError("frame was detached"))
    frame = Frame(nodes, clock=clock)
    monkeypatch.setattr(
        frames_module, "_document_changed", lambda _frame, _snapshot: True
    )

    with pytest.raises(PlaywrightTimeoutError, match="không xác nhận Category"):
        frames_module._select_supplier_category(
            Page(frame, clock=clock), "Trims", "05", lambda _line: None
        )


def test_a_frame_that_reloads_while_the_category_is_applied_is_not_an_error(
    clock, monkeypatch
):
    class Reloading(SelectLocator):
        def select_option(self, value=None, timeout=None):
            self.node.value = str(value)
            raise PlaywrightError("frame was detached")

    node = FakeNode(value="01")
    frame = Frame({"#ddlCategory": Reloading(node)}, clock=clock)
    monkeypatch.setattr(
        frames_module, "_document_changed", lambda _frame, _snapshot: True
    )

    assert frames_module._select_supplier_category(
        Page(frame, clock=clock), "Trims", "05", lambda _line: None
    ) is True


def test_a_category_wfx_refuses_for_another_reason_is_still_an_error(
    clock, monkeypatch
):
    class Refusing(SelectLocator):
        def select_option(self, value=None, timeout=None):
            raise PlaywrightError("Element is outside of the viewport")

    frame = Frame({"#ddlCategory": Refusing(FakeNode(value="01"))}, clock=clock)
    monkeypatch.setattr(
        frames_module, "_document_changed", lambda _frame, _snapshot: True
    )

    with pytest.raises(PlaywrightError, match="viewport"):
        frames_module._select_supplier_category(
            Page(frame, clock=clock), "Trims", "05", lambda _line: None
        )


# --- node Master ---------------------------------------------------------


MASTER_SELECTOR = (
    'span[onclick], a, button, [role="button"], input[type="button"]'
)


class TreeNode(FakeNode):
    """Node cây WFX: `evaluate` chỉ trả tagName như automation hỏi."""

    def __init__(self, tag="SPAN", label="", detached_on_read=False, **kwargs):
        super().__init__(**kwargs)
        self.tag = tag
        self.text = label
        self.value = label if tag == "INPUT" else kwargs.get("value", "")
        self.detached_on_read = detached_on_read

    def evaluate(self, script, arg=None):
        if self.detached_on_read:
            raise PlaywrightError("node is detached")
        if "tagName" in script:
            return self.tag
        return super().evaluate(script, arg)


def test_a_node_that_goes_away_while_being_read_is_skipped():
    master = TreeNode(label="Master")
    frame = Frame(
        {MASTER_SELECTOR: [TreeNode(detached_on_read=True), master]}
    )

    assert frames_module._actionable_master(frame).node is master


def test_a_master_button_is_matched_by_its_value_not_its_text():
    master = TreeNode(tag="INPUT", label="Master")
    frame = Frame({MASTER_SELECTOR: [master]})

    assert frames_module._actionable_master(frame).node is master


def test_a_tree_without_a_master_node_yields_nothing():
    frame = Frame({MASTER_SELECTOR: [TreeNode(label="Group")]})

    assert frames_module._actionable_master(frame) is None


# --- marker PartyType ----------------------------------------------------


@pytest.mark.parametrize(
    ("marker", "kind", "expected"),
    [
        (SUPPLIER_MARKER, "supplier", True),
        (SUPPLIER_MARKER, "buyer", False),
        (BUYER_MARKER, "buyer", True),
        (BUYER_MARKER, "supplier", False),
        ("supplier and buyer list", "supplier", False),
        ("", "supplier", False),
        (SUPPLIER_MARKER, "khac", False),
    ],
)
def test_a_frame_is_only_accepted_for_its_own_party_type(marker, kind, expected):
    assert frames_module._company_marker_matches(marker, kind) is expected


def test_the_buyer_search_frame_never_returns_the_supplier_one(clock):
    supplier = Frame(_query_field()[1], marker=SUPPLIER_MARKER, clock=clock)
    buyer = Frame(_query_field()[1], marker=BUYER_MARKER, clock=clock)
    page = Page(supplier, buyer, clock=clock)

    assert frames_module._buyer_search_frame(page, 2) is buyer


def test_a_frame_that_throws_while_being_identified_is_skipped(clock):
    broken = Frame(_query_field()[1], marker_error=PlaywrightError("detached"), clock=clock)
    buyer = Frame(_query_field()[1], marker=BUYER_MARKER, clock=clock)

    assert frames_module._company_search_frame(
        Page(broken, buyer, clock=clock), "buyer", 2
    ) is buyer


def test_no_matching_frame_at_all_reads_as_nothing(clock):
    page = Page(Frame(_query_field()[1], marker=SUPPLIER_MARKER, clock=clock), clock=clock)

    assert frames_module._company_search_frame(page, "buyer", 1) is None


# --- Supplier đã sẵn sàng để tìm -----------------------------------------


def test_a_supplier_screen_on_the_right_category_is_ready():
    frame = Frame({**_category("05"), **_company()})

    assert frames_module._supplier_company_ready(frame, "05") is True


@pytest.mark.parametrize(
    "nodes",
    [
        {**_category("01"), **_company()},
        {**_category("05"), "#txtCompanyName": []},
        {**_category("05"), "#txtCompanyName": [FakeNode(visible=False)]},
        {**_category("05"), "#txtCompanyName": [FakeNode(enabled=False)]},
    ],
)
def test_a_supplier_screen_that_is_not_ready_is_not_searched(nodes):
    assert frames_module._supplier_company_ready(Frame(nodes), "05") is False


def test_a_screen_still_showing_its_loading_layer_is_not_ready():
    frame = Frame({**_category("05"), **_company()}, busy=True)

    assert frames_module._supplier_company_ready(frame, "05") is False


def test_a_screen_that_went_away_is_not_ready():
    frame = Frame(locator_error=PlaywrightError("frame was detached"))

    assert frames_module._supplier_company_ready(frame, "05") is False


# --- điền ô Company ------------------------------------------------------


class QueryField(FakeNode):
    def __init__(self, *, keeps="", press_error=None, **kwargs):
        super().__init__(**kwargs)
        self.keeps = keeps
        self.press_error = press_error
        self.typed: list[str] = []

    def type(self, value, delay=0):
        self._guard()
        self.typed.append(value)
        self.value = self.keeps or value

    def press(self, key, timeout=None):
        if self.press_error is not None:
            raise self.press_error
        super().press(key, timeout)


def test_a_query_is_typed_and_confirmed_before_the_search_runs(clock):
    field, nodes = _query_field()
    frame = Frame(nodes, clock=clock)
    lines: list[str] = []

    result = company_query._fill_company_query(
        Page(frame, clock=clock), frame, "NIKE", lines.append, "supplier"
    )

    assert result is frame
    assert field.typed == ["NIKE"]
    assert field.keys == ["Enter"]
    assert any("NIKE" in line for line in lines)


def test_a_field_that_swallowed_part_of_the_query_forces_a_resync(clock):
    _partial, stale_nodes = _query_field(keeps="NI")
    _fresh_field, fresh_nodes = _query_field()
    # WFX đã thay frame: frame cũ giờ thuộc PartyType khác nên không được
    # nhận lại, còn frame Supplier mới mới là nơi được điền.
    stale = Frame(stale_nodes, marker=BUYER_MARKER, clock=clock)
    fresh = Frame(fresh_nodes, clock=clock)
    page = Page(stale, fresh, clock=clock)
    lines: list[str] = []

    result = company_query._fill_company_query(
        page, stale, "NIKE", lines.append, "supplier"
    )

    assert result is fresh
    assert any("đồng bộ lại frame" in line for line in lines)


def test_a_field_that_will_not_accept_the_query_twice_is_an_error(clock):
    stale = Frame(_query_field(keeps="NI")[1], clock=clock)
    fresh = Frame(_query_field(keeps="NI")[1], clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="không xác nhận"):
        company_query._fill_company_query(
            Page(stale, fresh, clock=clock),
            stale,
            "NIKE",
            lambda _line: None,
            "supplier",
        )


def test_a_frame_that_disappears_with_no_replacement_is_an_error(clock):
    stale = Frame(_query_field(keeps="NI")[1], clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="Frame Company Name đã đổi"):
        company_query._fill_company_query(
            Page(stale, clock=clock),
            stale,
            "NIKE",
            lambda _line: None,
            "buyer",
        )


def test_an_enter_key_the_frame_refuses_does_not_fail_the_search(clock):
    field, nodes = _query_field(press_error=PlaywrightError("frame was detached"))
    frame = Frame(nodes, clock=clock)

    company_query._fill_company_query(
        Page(frame, clock=clock), frame, "NIKE", lambda _line: None, "supplier"
    )

    assert field.typed == ["NIKE"]


# --- chờ bảng kết quả ----------------------------------------------------


def _rows(*names, query="NIKE"):
    return {
        "rows": [
            {"company": name, "matches": query.casefold() in name.casefold(), "hasEdit": True}
            for name in names
        ],
        "noRows": not names,
        "loading": False,
    }


def test_a_matching_row_settles_the_search(clock):
    frame = Frame(rows=_rows("NIKE VIETNAM"), clock=clock)

    current, state = company_query._wait_company_results(
        Page(frame, clock=clock), frame, "NIKE", "supplier"
    )

    assert current is frame
    assert [row["company"] for row in state["rows"]] == ["NIKE VIETNAM"]


def test_a_frame_wfx_swapped_for_the_other_party_type_is_resolved_again(clock):
    stale = Frame(marker=BUYER_MARKER, rows=_rows("NIKE VIETNAM"), clock=clock)
    fresh = Frame(
        _query_field()[1],
        marker=SUPPLIER_MARKER,
        rows=_rows("NIKE VIETNAM"),
        clock=clock,
    )
    page = Page(stale, fresh, clock=clock)

    current, _state = company_query._wait_company_results(
        page, stale, "NIKE", "supplier"
    )

    assert current is fresh


def test_a_frame_that_is_gone_with_no_replacement_keeps_waiting_then_times_out(
    clock,
):
    stale = Frame(marker=BUYER_MARKER, rows=_rows("NIKE VIETNAM"), clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="chưa ổn định"):
        company_query._wait_company_results(
            Page(stale, clock=clock), stale, "NIKE", "supplier"
        )


def test_a_grid_that_throws_mid_read_is_re_resolved_and_read_again(clock):
    broken = Frame(rows_error=PlaywrightError("frame was detached"), clock=clock)
    fresh = Frame(_query_field()[1], rows=_rows("NIKE VIETNAM"), clock=clock)
    page = Page(broken, fresh, clock=clock)

    current, _state = company_query._wait_company_results(
        page, broken, "NIKE", "supplier"
    )

    assert current is fresh


def test_filling_and_waiting_run_as_one_step_for_the_caller(clock):
    field, nodes = _query_field()
    frame = Frame(nodes, rows=_rows("NIKE VIETNAM"), clock=clock)

    current, state = company_query._filter_company_rows(
        Page(frame, clock=clock), frame, "NIKE", lambda _line: None, "supplier"
    )

    assert current is frame
    assert field.typed == ["NIKE"]
    assert [row["company"] for row in state["rows"]] == ["NIKE VIETNAM"]
