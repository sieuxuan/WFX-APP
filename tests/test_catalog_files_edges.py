"""Popup Article File khi một frame biến mất giữa lúc quét.

CLAUDE.md: không coi việc "đã click" là thành công — tab chỉ được coi là đã mở
khi WFX xác nhận. Một frame detach giữa chừng phải bị bỏ qua chứ không được
làm hỏng cả lượt quét, và cũng không được biến thành "đã đổi" một cách im lặng
khi thật ra app không đọc được gì.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError

from tests.fakes.mini_dom import Element, MiniFrame
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.catalog import files as catalog_files

WFX = "https://prosports.worldfashionexchange.com"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, catalog_files, _common)


class DetachedFrame(MiniFrame):
    """Frame vẫn nằm trong `page.frames` nhưng mọi lời gọi đều ném."""

    def locator(self, selector):
        raise PlaywrightError("frame was detached")

    def evaluate(self, script, arg=None):
        raise PlaywrightError("execution context was destroyed")


class Page:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.url = f"{WFX}/wfx_ArticleMain.aspx"

    def frame(self, name=None, **_kwargs):
        return next(
            (frame for frame in self.frames if getattr(frame, "name", "") == name),
            None,
        )

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)


def _frame(**kwargs):
    return MiniFrame(Element("body"), url=f"{WFX}/wfx_ArticleTop.aspx", **kwargs)


# --- tìm tab --------------------------------------------------------------


def test_a_frame_that_detaches_mid_scan_does_not_stop_the_tab_search(clock):
    tab = Element(
        "li",
        text="Documents",
        children=[Element("a", attrs={"onclick": "go()"})],
    )
    good = MiniFrame(
        Element("body", children=[Element("ul", id="0", children=[tab])]),
        url=f"{WFX}/wfx_ArticleTop.aspx",
        clock=clock,
        xpaths={'//*[@id="0"]/li[5]': [tab]},
    )
    broken = DetachedFrame(Element("body"), clock=clock)
    page = Page(clock, [broken, good])

    found = catalog_files._article_file_tab(page, broken, 5, timeout_seconds=2)

    assert found is not None
    assert found[0] is good


def test_no_tab_anywhere_times_out_quietly(clock):
    broken = DetachedFrame(Element("body"), clock=clock)
    page = Page(clock, [broken])

    assert catalog_files._article_file_tab(
        page, broken, 5, timeout_seconds=1
    ) is None


# --- marker document ------------------------------------------------------


def test_a_frame_that_cannot_be_marked_is_left_out_of_the_snapshot(clock):
    good = _frame()
    page = Page(clock, [DetachedFrame(Element("body")), good])

    snapshots = catalog_files._mark_article_documents(page)

    assert [frame for frame, _marker in snapshots] == [good]


def test_a_frame_that_went_away_counts_as_a_document_change(clock):
    good = _frame()
    page = Page(clock, [good])
    snapshots = catalog_files._mark_article_documents(page)
    page.frames = []

    assert catalog_files._article_documents_changed(page, snapshots) is True


def test_a_frame_that_cannot_be_read_back_counts_as_a_document_change(clock):
    good = _frame()
    page = Page(clock, [good])
    snapshots = catalog_files._mark_article_documents(page)

    def refuse(_script, _arg=None):
        raise PlaywrightError("execution context was destroyed")

    good.evaluate = refuse

    assert catalog_files._article_documents_changed(page, snapshots) is True


def test_an_unchanged_document_is_not_reported_as_changed(clock):
    good = _frame()
    page = Page(clock, [good])
    snapshots = catalog_files._mark_article_documents(page)

    assert catalog_files._article_documents_changed(page, snapshots) is False


# --- trạng thái tab -------------------------------------------------------


def test_a_tab_that_went_away_is_never_reported_as_selected():
    class Gone:
        def evaluate(self, _script, _arg=None):
            raise PlaywrightError("node is not attached to the DOM")

    assert catalog_files._article_tab_selected(Gone()) is False


# --- bảng file ------------------------------------------------------------


def test_a_frame_that_detaches_is_skipped_while_reading_the_file_tables(clock):
    page = Page(clock, [DetachedFrame(Element("body"))])

    assert catalog_files._visible_attachment_tables(page) == []


def test_a_table_that_detaches_between_count_and_read_is_skipped(clock):
    class HalfGone(MiniFrame):
        def locator(self, selector):
            found = super().locator(selector)
            if selector == catalog_files._ATTACHMENT_TABLE_SELECTOR:
                return _RaisingTables(found.count())
            return found

    table = Element(
        "table",
        id="gridFileUploadDownload1_tblGridContent",
        children=[Element("tbody", children=[])],
    )
    frame = HalfGone(
        Element("body", children=[table]), url=f"{WFX}/wfx_ArticleFiles.aspx"
    )

    assert catalog_files._visible_attachment_tables(Page(clock, [frame])) == []


class _RaisingTables:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count

    def nth(self, _index):
        return self

    def is_visible(self):
        raise PlaywrightError("node is not attached to the DOM")
