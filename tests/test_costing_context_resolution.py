"""Chọn đúng tab/frame Costing và đọc định danh Style từ chính tab đó.

CLAUDE.md: khi có nhiều tab/popup Costing phải ưu tiên target đang hoạt động
gần nhất, không dùng thứ tự tạo trong `context.pages`; và các probe chỉ đọc
không được activate tab, kéo user khỏi chỗ đang làm.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation._common as common
import wfx_panel.automation.costing.context as context_module
from tests.fakes.mini_dom import Element, MiniFrame
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError

GRID = "gridCostSheetDetail_tblGridContent"
DETAIL = "sectionCostSheetDetail"
TREE = "sectionCostSheetTree"


@pytest.fixture
def clock(monkeypatch):
    # `_sleep()` đọc `time` trong namespace của `_common`, không phải của
    # context.py, nên phải gắn cùng một đồng hồ cho cả hai.
    return install_fake_clock(monkeypatch, context_module, common)


class CostingFrame(MiniFrame):
    """MiniFrame biết trả kết quả cho script quét control Style Code."""

    def __init__(self, *args, control_values=(), error=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.control_values = list(control_values)
        self.error = error

    def locator(self, selector):
        if self.error is not None:
            raise self.error
        if "," in selector and "#lblArticleCode" in selector:
            return _ValuesLocator(self.control_values)
        return super().locator(selector)


class _ValuesLocator:
    def __init__(self, values):
        self.values = list(values)

    def evaluate_all(self, _script, _arg=None):
        return list(self.values)


class CostingPage:
    def __init__(
        self,
        *frames,
        url="https://wfx.test/ArticleDetail.aspx",
        title="WFX",
        activity=None,
        opener="",
        evaluate_error=None,
    ):
        self.frames = list(frames)
        self.url = url
        self._title = title
        self.activity = activity if activity is not None else {"visible": True, "focused": True}
        self.opener = opener
        self.evaluate_error = evaluate_error
        self.activated = 0

    def title(self):
        if isinstance(self._title, Exception):
            raise self._title
        return self._title

    def bring_to_front(self):
        self.activated += 1

    def evaluate(self, script, _arg=None):
        if self.evaluate_error is not None:
            raise self.evaluate_error
        if "visibilityState" in script:
            return dict(self.activity)
        if "window.opener" in script:
            return self.opener
        raise AssertionError(f"Page giả chưa hỗ trợ script: {script[:80]}")


class Context:
    def __init__(self, *pages, sessions=None):
        self.pages = list(pages)
        self._sessions = dict(sessions or {})

    def new_cdp_session(self, page):
        return self._sessions[id(page)]


class CdpSession:
    def __init__(self, target_id, targets=None, error=None):
        self.target_id = target_id
        self.targets = targets
        self.error = error
        self.detached = 0

    def send(self, method, _params=None):
        if self.error is not None:
            raise self.error
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"targetId": self.target_id}}
        if method == "Target.getTargets":
            return {"targetInfos": self.targets or []}
        raise AssertionError(method)

    def detach(self):
        self.detached += 1


def _costing_frame(**kwargs):
    root = Element(
        "body",
        children=[
            Element("table", id=GRID),
            Element("div", id=DETAIL),
            Element("div", id=TREE),
        ],
    )
    return CostingFrame(root, **kwargs)


def _plain_frame(**kwargs):
    """Frame trống nhưng vẫn trả lời được script quét control Style Code."""
    return CostingFrame(Element("body"), control_values=[], **kwargs)


def _article_name(text):
    return Element(
        "body",
        children=[Element("span", id="lblArticleNameValue", text=text)],
    )


# --- trạng thái Costing đọc từ cây --------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Cost Sheet - Open", "Open"),
        ("Costing Approved", "Approved"),
        ("No Costing", "No Costing"),
        ("Not Open", "Not Open"),
    ],
)
def test_the_costing_status_is_read_from_the_tree_title(text, expected):
    frame = MiniFrame(
        Element("body", children=[Element("div", id=TREE, text=text)])
    )

    assert context_module._status_from_tree(frame) == expected


def test_a_tree_with_no_status_words_reads_as_no_status():
    frame = MiniFrame(
        Element("body", children=[Element("div", id=TREE, text="Cost Sheet")])
    )

    assert context_module._status_from_tree(frame) == ""


def test_a_tree_that_went_away_is_an_error_not_a_quiet_no_status():
    # Trả "" ở đây sẽ thành COSTING_NOT_OPEN, tức bảo người dùng tự tạo Costing
    # trong khi thật ra app chỉ mất frame. Lỗi phải nổi lên đúng bản chất.
    class Detached(MiniFrame):
        def locator(self, selector):
            raise PlaywrightError("frame was detached")

    with pytest.raises(PlaywrightError):
        context_module._status_from_tree(Detached(Element("body")))


# --- chọn frame Costing --------------------------------------------------


def test_the_frame_showing_the_costing_grid_wins_over_a_bare_tree(clock):
    tree_only = MiniFrame(Element("body", children=[Element("div", id=TREE)]))
    full = _costing_frame()
    page = CostingPage(tree_only, full)

    _found_page, frame = context_module._costing_frame(Context(page))

    assert frame is full


def test_a_frame_with_only_the_new_button_still_counts_as_costing(clock):
    tool = Element(
        "div",
        id=TREE,
        children=[Element("div", id="RowTool", children=[Element("img", id="imgNew")])],
    )
    frame = MiniFrame(Element("body", children=[tool]))
    page = CostingPage(frame)

    _found_page, found = context_module._costing_frame(Context(page))

    assert found is frame


def test_a_hidden_grid_does_not_make_a_frame_the_costing_frame(clock):
    hidden = MiniFrame(
        Element(
            "body",
            children=[Element("table", id=GRID, visible=False)],
        )
    )
    page = CostingPage(hidden)

    with pytest.raises(PlaywrightTimeoutError, match="COSTING_CONTEXT_NOT_FOUND"):
        context_module._costing_frame(Context(page), 1)


def test_a_frame_that_detaches_mid_scan_is_skipped(clock):
    broken = _costing_frame(error=PlaywrightError("frame was detached"))
    good = _costing_frame()
    page = CostingPage(broken, good)

    _found_page, frame = context_module._costing_frame(Context(page))

    assert frame is good


def test_a_caller_may_pin_the_scan_to_the_pages_it_already_resolved(clock):
    pinned = CostingPage(_costing_frame())
    other = CostingPage(_costing_frame())

    found_page, _frame = context_module._costing_frame(
        Context(other), pages=[pinned]
    )

    assert found_page is pinned


# --- node đang chọn trong Cost Sheet tree -------------------------------


def _tree_page(*titles):
    nodes = [
        Element("span", css_class="clsTreeSelectedNode", text=title)
        for title in titles
    ]
    root = Element(
        "body", children=[Element("div", id="treeCostSheet", children=nodes)]
    )
    return CostingPage(MiniFrame(root))


def test_the_selected_cost_sheet_node_is_read_without_clicking():
    assert context_module._selected_costing_title(
        Context(_tree_page("CS-2026-01"))
    ) == "CS-2026-01"


def test_two_different_selected_nodes_are_treated_as_no_answer():
    page = _tree_page("CS-2026-01", "CS-2026-02")

    assert context_module._selected_costing_title(Context(page)) == ""


def test_the_same_node_seen_twice_is_still_one_answer():
    page = _tree_page("CS-2026-01", "CS-2026-01")

    assert context_module._selected_costing_title(Context(page)) == "CS-2026-01"


def test_a_tree_frame_that_goes_away_is_skipped():
    class Detached(MiniFrame):
        def locator(self, selector):
            raise PlaywrightError("frame was detached")

    page = CostingPage(Detached(Element("body")))

    assert context_module._selected_costing_title(Context(page)) == ""


# --- chọn đúng tab đang hoạt động ---------------------------------------


def _costing_tab(**kwargs):
    return CostingPage(_costing_frame(), **kwargs)


def test_a_tab_the_user_cannot_see_is_never_chosen():
    hidden = _costing_tab(activity={"visible": False, "focused": False})

    with pytest.raises(PlaywrightTimeoutError, match="NOT_FOUND"):
        context_module._active_costing_page(Context(hidden))


def test_a_tab_that_is_not_costing_at_all_is_never_chosen():
    page = CostingPage(MiniFrame(Element("body")))

    with pytest.raises(PlaywrightTimeoutError, match="NOT_FOUND"):
        context_module._active_costing_page(Context(page))


def test_the_only_visible_costing_tab_is_used_without_touching_chrome():
    page = _costing_tab()

    assert context_module._active_costing_page(Context(page)) is page
    assert page.activated == 0


def test_the_focused_tab_wins_when_several_are_visible():
    focused = _costing_tab()
    background = _costing_tab(activity={"visible": True, "focused": False})

    assert context_module._active_costing_page(
        Context(background, focused)
    ) is focused


def test_a_page_that_refuses_to_report_its_state_is_treated_as_hidden():
    page = _costing_tab(evaluate_error=PlaywrightError("context destroyed"))

    with pytest.raises(PlaywrightTimeoutError, match="NOT_FOUND"):
        context_module._active_costing_page(Context(page))


def test_a_frame_that_throws_while_probing_does_not_hide_the_tab():
    page = CostingPage(
        _costing_frame(error=PlaywrightError("frame was detached")),
        _costing_frame(),
    )

    assert context_module._active_costing_page(Context(page)) is page


def test_chrome_target_order_breaks_the_tie_between_two_visible_popups():
    first = _costing_tab(activity={"visible": True, "focused": True})
    second = _costing_tab(activity={"visible": True, "focused": True})
    targets = [
        {"targetId": "B", "type": "page"},
        {"targetId": "A", "type": "page"},
        {"targetId": "W", "type": "worker"},
    ]
    context = Context(
        first,
        second,
        sessions={
            id(first): CdpSession("A", targets),
            id(second): CdpSession("B", targets),
        },
    )

    assert context_module._active_costing_page(context) is second


def test_two_popups_chrome_cannot_rank_are_refused_instead_of_guessed():
    first = _costing_tab()
    second = _costing_tab()
    context = Context(
        first,
        second,
        sessions={
            id(first): CdpSession("A", []),
            id(second): CdpSession("B", []),
        },
    )

    with pytest.raises(PlaywrightTimeoutError, match="AMBIGUOUS"):
        context_module._active_costing_page(context)


def test_a_cdp_probe_that_fails_falls_back_to_refusing_the_guess():
    first = _costing_tab()
    second = _costing_tab()
    context = Context(
        first,
        second,
        sessions={
            id(first): CdpSession("A", error=PlaywrightError("no cdp")),
            id(second): CdpSession("B"),
        },
    )

    with pytest.raises(PlaywrightTimeoutError, match="AMBIGUOUS"):
        context_module._active_costing_page(context)


def test_the_cdp_sessions_opened_for_the_probe_are_always_detached():
    first = _costing_tab()
    second = _costing_tab()
    sessions = {
        id(first): CdpSession("A", [{"targetId": "A", "type": "page"}]),
        id(second): CdpSession("B", [{"targetId": "A", "type": "page"}]),
    }

    context_module._active_costing_page(Context(first, second, sessions=sessions))

    assert all(session.detached == 1 for session in sessions.values())


# --- Style Code của đúng popup ------------------------------------------


def test_the_article_header_is_the_first_place_the_style_code_is_read():
    page = CostingPage(
        MiniFrame(_article_name("BDG-X(SWN0000001/KFSWPKN-S200 LN)")),
        url="https://wfx.test/Article.aspx?id=BCA4-D53A-0001",
    )

    assert context_module._article_code_from_page(page) == "SWN0000001"
    assert context_module._style_name_from_page(page) == "KFSWPKN-S200 LN"


def test_a_header_naming_two_codes_is_not_trusted():
    page = CostingPage(
        CostingFrame(
            _article_name("X(SWN0000001 SWN0000002/Ten)"), control_values=[]
        ),
        url="https://wfx.test/Article.aspx",
        title="WFX",
    )

    assert context_module._article_code_from_page(page) == ""


def test_the_url_and_title_are_used_when_the_header_is_missing():
    page = CostingPage(
        _plain_frame(),
        url="https://wfx.test/Article.aspx?code=SWN0000001",
        title="SWN0000001 - Costing",
    )

    assert context_module._article_code_from_page(page) == "SWN0000001"


def test_a_page_that_refuses_to_report_its_title_still_reads_the_frames():
    frame = _plain_frame(url="https://wfx.test/Costing.aspx?code=SWN0000001")
    page = CostingPage(
        frame,
        url="https://wfx.test/Article.aspx",
        title=PlaywrightError("page closed"),
    )

    assert context_module._article_code_from_page(page) == "SWN0000001"


def test_a_frame_that_cannot_report_its_url_is_skipped():
    class NoUrl(MiniFrame):
        @property
        def url(self):
            raise PlaywrightError("frame was detached")

        @url.setter
        def url(self, _value):
            return None

    page = CostingPage(
        NoUrl(Element("body")),
        url="https://wfx.test/Article.aspx?code=SWN0000001",
        title="WFX",
    )

    assert context_module._article_code_from_page(page) == "SWN0000001"


def test_the_article_left_tree_carries_the_style_code_when_nothing_else_does():
    left = MiniFrame(
        Element("body", text="Master > (SKN0000188/Ten style)"),
        url="https://wfx.test/ArticleLeft.aspx",
        name="ArticleLeft",
    )
    page = CostingPage(left, url="https://wfx.test/a.aspx", title="WFX")

    assert context_module._article_code_from_page(page) == "SKN0000188"


def test_the_article_left_tree_is_trusted_when_it_names_exactly_one_code():
    left = MiniFrame(
        Element("body", text="Master SKN0000188 Jacket"),
        url="https://wfx.test/articleleft.aspx",
    )
    page = CostingPage(left, url="https://wfx.test/a.aspx", title="WFX")

    assert context_module._article_code_from_page(page) == "SKN0000188"


def test_a_frame_that_is_not_the_article_tree_is_not_read_as_one():
    other = CostingFrame(
        Element("body", text="(SKN0000188/Ten)"),
        control_values=[],
        url="https://wfx.test/Other.aspx",
    )
    page = CostingPage(other, url="https://wfx.test/a.aspx", title="WFX")

    assert context_module._article_code_from_page(page) == ""


def test_a_style_code_control_is_the_next_source_after_the_tree():
    frame = _costing_frame(control_values=["SWN0000001", "SWN0000001"])
    page = CostingPage(frame, url="https://wfx.test/a.aspx", title="WFX")

    assert context_module._article_code_from_page(page) == "SWN0000001"


def test_controls_naming_two_different_styles_are_not_trusted():
    frame = _costing_frame(control_values=["SWN0000001", "SWN0000002"])
    page = CostingPage(
        frame, url="https://wfx.test/a.aspx", title="WFX", opener=""
    )

    assert context_module._article_code_from_page(page) == ""


def test_the_button_the_user_just_clicked_in_catalog_is_the_last_resort():
    page = CostingPage(
        _plain_frame(),
        url="https://wfx.test/a.aspx",
        title="WFX",
        opener="SWN0000001",
    )

    assert context_module._article_code_from_page(page) == "SWN0000001"


def test_a_popup_that_cannot_reach_its_opener_simply_has_no_style_code():
    page = CostingPage(
        _plain_frame(),
        url="https://wfx.test/a.aspx",
        title="WFX",
        evaluate_error=PlaywrightError("context destroyed"),
    )

    assert context_module._article_code_from_page(page) == ""


# --- tên Style ----------------------------------------------------------


def test_a_header_without_the_expected_shape_yields_no_style_name():
    page = CostingPage(MiniFrame(_article_name("BDG-X khong co ngoac")))

    assert context_module._style_name_from_page(page) == ""


def test_a_frame_that_detaches_while_reading_the_name_is_skipped():
    class Detached(MiniFrame):
        def locator(self, selector):
            raise PlaywrightError("frame was detached")

    page = CostingPage(
        Detached(Element("body")),
        MiniFrame(_article_name("X(SWN0000001/Ten style)")),
    )

    assert context_module._style_name_from_page(page) == "Ten style"


# --- node biến mất ngay giữa lúc đọc ------------------------------------


class _RaisingLocator:
    def __init__(self, error):
        self.error = error

    def count(self):
        return 1

    def nth(self, _index):
        return self

    def inner_text(self, timeout=None):
        raise self.error

    def evaluate_all(self, _script, _arg=None):
        raise self.error


def test_a_tree_node_that_vanishes_between_count_and_read_is_skipped():
    class Vanishing(MiniFrame):
        def locator(self, selector):
            return _RaisingLocator(PlaywrightError("node is not attached"))

    assert context_module._status_from_tree(Vanishing(Element("body"))) == ""


def test_an_article_tree_that_vanishes_mid_read_is_skipped():
    class Vanishing(CostingFrame):
        def locator(self, selector):
            if selector == "body":
                raise PlaywrightError("frame was detached")
            return super().locator(selector)

    left = Vanishing(
        Element("body", text="(SKN0000188/Ten)"),
        control_values=[],
        url="https://wfx.test/ArticleLeft.aspx",
    )
    page = CostingPage(left, url="https://wfx.test/a.aspx", title="WFX")

    assert context_module._article_code_from_page(page) == ""


def test_a_control_scan_that_fails_mid_frame_is_skipped():
    class Vanishing(MiniFrame):
        def locator(self, selector):
            if "#lblArticleCode" in selector:
                return _RaisingLocator(PlaywrightError("frame was detached"))
            return super().locator(selector)

    page = CostingPage(
        Vanishing(Element("body")),
        url="https://wfx.test/a.aspx",
        title="WFX",
        opener="",
    )

    assert context_module._article_code_from_page(page) == ""


def test_the_only_costing_tab_is_used_even_when_chrome_reports_no_focus():
    lonely = _costing_tab(activity={"visible": True, "focused": False})

    assert context_module._active_costing_page(Context(lonely)) is lonely
