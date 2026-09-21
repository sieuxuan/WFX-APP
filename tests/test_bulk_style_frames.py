"""Mở form New Style và tìm đúng frame editor mà không chờ `expect_page`.

WFX đặt tên cửa sổ `CatalogDetail`, nên từ dòng thứ hai trở đi `window.open`
tái dùng cửa sổ đang mở và Chromium không phát page event. Chờ blocking ở đây
làm MỖI dòng mất trọn timeout; frame scan mới là nguồn xác nhận.
"""

from __future__ import annotations

import pytest

import wfx_panel.automation.bulk_style.frames as frames
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation._common import PlaywrightError, PlaywrightTimeoutError
from wfx_panel.automation.bulk_style.constants import (
    _COPY_RESULTS_JS,
    COPY_AS_VARIANT_XPATH,
    NEW_STYLE_XPATH,
)

NEW_SELECTOR = f"xpath={NEW_STYLE_XPATH}"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, frames)


class Node:
    def __init__(self, *, visible=True, text="New", parent=None):
        self.visible = visible
        self.text = text
        self._parent = parent
        self.clicks: list[str] = []

    def is_visible(self):
        return self.visible

    def inner_text(self, **_kwargs):
        return self.text

    def locator(self, selector):
        assert selector == "xpath=.."
        return self._parent if self._parent is not None else self

    def evaluate(self, script):
        self.clicks.append(script)


class NodeList:
    def __init__(self, nodes):
        self.nodes = list(nodes)

    def count(self):
        return len(self.nodes)

    def nth(self, index):
        return self.nodes[index]


class StyleFrame:
    def __init__(
        self,
        nodes=None,
        *,
        url="https://wfx.test/CatalogDetail.aspx",
        broken=False,
        scripts=None,
        clock=None,
    ):
        self.nodes = dict(nodes or {})
        self.url = url
        self.broken = broken
        self.scripts = dict(scripts or {})
        self.clock = clock

    def locator(self, selector):
        if self.broken:
            raise PlaywrightError("frame đã detach")
        return NodeList(self.nodes.get(selector, ()))

    def evaluate(self, script, _arg=None):
        if self.broken:
            raise PlaywrightError("frame đã detach")
        for marker, value in self.scripts.items():
            if marker in script:
                return value() if callable(value) else value
        raise AssertionError(f"script lạ: {script[:60]}")


class StylePage:
    def __init__(self, *frames_, clock=None):
        self.frames = list(frames_)
        self.clock = clock
        self.closed = False
        self.close_error: BaseException | None = None
        self.goto_calls: list[str] = []

    def wait_for_timeout(self, milliseconds):
        if self.clock is not None:
            self.clock.advance(float(milliseconds) / 1_000.0)

    def close(self, run_before_unload=True):
        if self.close_error is not None:
            raise self.close_error
        self.closed = True

    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)


class Context:
    def __init__(self, *pages, new_page=None):
        self.pages = list(pages)
        self._new_page = new_page
        self.new_page_calls = 0

    def new_page(self):
        self.new_page_calls += 1
        page = self._new_page or StylePage()
        self.pages.append(page)
        return page


# --- tìm control hiện hữu ----------------------------------------------


def test_the_newest_frame_that_actually_shows_the_control_wins(clock):
    hidden = Node(visible=False)
    shown = Node()
    stale = StyleFrame({NEW_SELECTOR: [hidden]}, clock=clock)
    fresh = StyleFrame({NEW_SELECTOR: [hidden, shown]}, clock=clock)
    page = StylePage(stale, fresh, clock=clock)

    found_page, found_frame, node = frames._frame_with_visible_locator(
        Context(page), NEW_SELECTOR, 5
    )

    assert (found_page, found_frame, node) == (page, fresh, shown)


def test_a_detached_frame_never_breaks_the_scan(clock):
    good = StyleFrame({NEW_SELECTOR: [Node()]}, clock=clock)
    page = StylePage(good, StyleFrame(broken=True), clock=clock)

    _page, frame, _node = frames._frame_with_visible_locator(
        Context(page), NEW_SELECTOR, 5
    )

    assert frame is good


def test_a_control_that_never_shows_up_names_the_selector(clock):
    page = StylePage(StyleFrame(clock=clock), clock=clock)

    with pytest.raises(PlaywrightTimeoutError) as error:
        frames._frame_with_visible_locator(Context(page), NEW_SELECTOR, 1)

    assert NEW_STYLE_XPATH in str(error.value)


def test_a_context_without_any_page_still_stops_at_the_deadline():
    with pytest.raises(PlaywrightTimeoutError):
        frames._frame_with_visible_locator(Context(), NEW_SELECTOR, 0.05)


def test_the_left_frame_helper_looks_for_the_new_style_control(clock):
    target = StyleFrame({NEW_SELECTOR: [Node()]}, clock=clock)
    page = StylePage(target, clock=clock)

    assert frames._article_left_frame(Context(page)) is target


# --- nút New của Catalog Group -----------------------------------------


def test_only_the_toolbar_link_whose_text_is_new_is_accepted(clock):
    other = Node(text="Edit")
    hidden = Node(visible=False)
    wanted = Node(text="  NEW  ")
    frame = StyleFrame({"a.clsNavLinkNew": [other, hidden, wanted]}, clock=clock)
    page = StylePage(frame, clock=clock)

    _page, _frame, node = frames._new_style_link(Context(page))

    assert node is wanted


def test_a_group_without_a_new_button_is_reported(clock):
    frame = StyleFrame({"a.clsNavLinkNew": [Node(text="Edit")]}, clock=clock)
    page = StylePage(frame, clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="nút New"):
        frames._new_style_link(Context(page), timeout_s=1)


def test_a_detached_frame_does_not_stop_the_search_for_new(clock):
    wanted = Node()
    frame = StyleFrame({"a.clsNavLinkNew": [wanted]}, clock=clock)
    page = StylePage(frame, StyleFrame(broken=True), clock=clock)

    _page, _frame, node = frames._new_style_link(Context(page))

    assert node is wanted


# --- mở popup New -------------------------------------------------------


def test_opening_new_clicks_the_cell_that_carries_the_onclick(clock):
    cell = Node()
    link = Node(parent=cell)
    target = StyleFrame({NEW_SELECTOR: [Node()]}, clock=clock)
    page = StylePage(target, clock=clock)

    assert frames._open_style_choice(Context(page), link) is target
    assert cell.clicks, "phải click TD mang onclick, không click anchor con"


def test_a_window_chrome_silently_reused_is_reopened_from_the_wfx_url(clock):
    cell = Node()
    link = Node(parent=cell)
    source = StyleFrame(
        url="https://wfx.test/wfx/CatalogBottom.aspx",
        scripts={"FullScreenForChrome": "CatalogDetail.aspx?mode=new"},
        clock=clock,
    )
    popup_frame = StyleFrame({NEW_SELECTOR: [Node()]}, clock=clock)
    popup = StylePage(popup_frame, clock=clock)
    page = StylePage(source, clock=clock)
    context = Context(page, new_page=popup)

    assert frames._open_style_choice(context, link, timeout_s=1) is popup_frame
    assert context.new_page_calls == 1
    assert popup.goto_calls == [
        "https://wfx.test/wfx/CatalogDetail.aspx?mode=new"
    ]


def test_a_page_whose_new_function_cannot_be_read_is_skipped(clock):
    cell = Node()
    link = Node(parent=cell)
    blank = StyleFrame(scripts={"FullScreenForChrome": ""}, clock=clock)
    source = StyleFrame(
        url="https://wfx.test/wfx/CatalogBottom.aspx",
        scripts={"FullScreenForChrome": "CatalogDetail.aspx"},
        clock=clock,
    )
    popup_frame = StyleFrame({NEW_SELECTOR: [Node()]}, clock=clock)
    # Quét theo thứ tự ngược: frame hỏng trước, rồi frame không có hàm New,
    # cuối cùng mới tới frame đọc được URL.
    page = StylePage(source, blank, StyleFrame(broken=True), clock=clock)
    context = Context(page, new_page=StylePage(popup_frame, clock=clock))

    assert frames._open_style_choice(context, link, timeout_s=1) is popup_frame


def test_a_session_that_exposes_no_new_url_at_all_is_reported(clock):
    cell = Node()
    link = Node(parent=cell)
    page = StylePage(
        StyleFrame(scripts={"FullScreenForChrome": ""}, clock=clock), clock=clock
    )

    with pytest.raises(PlaywrightTimeoutError, match="URL New"):
        frames._open_style_choice(Context(page), link, timeout_s=1)


# --- dọn popup của lượt quét -------------------------------------------


def test_only_pages_this_run_opened_are_closed():
    kept = StylePage()
    opened = StylePage()
    context = Context(kept, opened)

    frames._close_pages_opened_since(context, {kept})

    assert kept.closed is False
    assert opened.closed is True


def test_a_popup_that_refuses_to_close_does_not_break_the_cleanup():
    stubborn = StylePage()
    stubborn.close_error = PlaywrightError("target đã đóng")
    other = StylePage()

    frames._close_pages_opened_since(Context(stubborn, other), set())

    assert other.closed is True


# --- frame editor Style -------------------------------------------------


MATERIAL = "#ddlMaterialType, #select2-ddlMaterialType-container"


def test_the_editor_frame_needs_both_the_title_and_the_material_dropdown(clock):
    half = StyleFrame({"#titlebarArticle": [Node()]}, clock=clock)
    full = StyleFrame(
        {"#titlebarArticle": [Node()], MATERIAL: [Node()]}, clock=clock
    )
    page = StylePage(half, full, clock=clock)

    assert frames._style_editor_frame(Context(page)) is full


def test_a_form_that_never_finishes_loading_is_reported(clock):
    page = StylePage(
        StyleFrame({"#titlebarArticle": [Node()]}, clock=clock), clock=clock
    )

    with pytest.raises(PlaywrightTimeoutError, match="Form Article"):
        frames._style_editor_frame(Context(page), timeout_s=1)


def test_a_detached_frame_does_not_stop_the_editor_search(clock):
    full = StyleFrame(
        {"#titlebarArticle": [Node()], MATERIAL: [Node()]}, clock=clock
    )
    page = StylePage(full, StyleFrame(broken=True), clock=clock)

    assert frames._style_editor_frame(Context(page)) is full


# --- frame kết quả Copy -------------------------------------------------


def test_a_frame_listing_copy_candidates_is_the_result_frame(clock):
    frame = StyleFrame(
        scripts={_COPY_RESULTS_JS[:40]: [{"code": "F0001"}]}, clock=clock
    )
    page = StylePage(frame, clock=clock)

    assert frames._copy_result_frame(Context(page)) is frame


def test_a_frame_showing_copy_as_variant_also_counts_even_with_no_result(clock):
    frame = StyleFrame(
        {f"xpath={COPY_AS_VARIANT_XPATH}": [Node()]},
        scripts={_COPY_RESULTS_JS[:40]: []},
        clock=clock,
    )
    page = StylePage(frame, clock=clock)

    assert frames._copy_result_frame(Context(page)) is frame


def test_a_frame_with_neither_is_not_the_result_frame(clock):
    frame = StyleFrame(scripts={_COPY_RESULTS_JS[:40]: []}, clock=clock)
    page = StylePage(frame, clock=clock)

    with pytest.raises(PlaywrightTimeoutError, match="Style nguồn"):
        frames._copy_result_frame(Context(page), timeout_s=1)


def test_a_detached_frame_does_not_stop_the_copy_result_search(clock):
    good = StyleFrame(
        scripts={_COPY_RESULTS_JS[:40]: [{"code": "F0001"}]}, clock=clock
    )
    page = StylePage(good, StyleFrame(broken=True), clock=clock)

    assert frames._copy_result_frame(Context(page)) is good
