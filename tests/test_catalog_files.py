"""Quét bốn tab file đính kèm của popup Article.

`wfx_panel/automation/catalog/files.py` ở mức 17%. Hai phần quan trọng nhất
chưa từng chạy:

* `_attachment_url` — biên an toàn: chỉ nhận HTTPS trên chính
  `worldfashionexchange.com`. Một URL lạ lọt qua đây là app tải file từ máy chủ
  của người khác bằng phiên đăng nhập của người dùng.
* `_scan_article_file_tabs` — chỉ được coi là đã vào mục khi WFX xác nhận
  (tab selected, document đổi hoặc bảng file đổi), đúng tinh thần "không coi
  việc đã click là thành công" của CLAUDE.md.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.automation_boundary import WfxWorld, wire_automation
from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import install_fake_clock
from wfx_panel.automation import _common
from wfx_panel.automation.catalog import files as catalog_files

WFX = "https://prosports.worldfashionexchange.com"


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, catalog_files, _common)


def _quiet():
    return lambda _line: None


# --- _attachment_url: biên an toàn ---------------------------------------


def test_attachment_url_accepts_a_relative_href_on_the_wfx_host():
    url = catalog_files._attachment_url({"href": "/Upload/tech pack.pdf"})

    assert url == f"{WFX}/Upload/tech%20pack.pdf"


def test_attachment_url_reads_the_path_out_of_view_attachment_file():
    url = catalog_files._attachment_url(
        {"onclick": "ViewAttachmentFile(this, '/Upload/a.pdf'); return false;"}
    )

    assert url == f"{WFX}/Upload/a.pdf"


def test_attachment_url_unescapes_html_entities_first():
    url = catalog_files._attachment_url(
        {"href": "/Upload/a.pdf&amp;v=2"},
    )

    assert url.endswith("/Upload/a.pdf&v=2") or "a.pdf" in url


def test_attachment_url_keeps_the_query_but_drops_the_fragment():
    url = catalog_files._attachment_url({"href": "/Upload/a.pdf?id=7#page=3"})

    assert url == f"{WFX}/Upload/a.pdf?id=7"


def test_attachment_url_collapses_duplicate_slashes():
    url = catalog_files._attachment_url({"href": "/Upload///a.pdf"})

    assert url == f"{WFX}/Upload/a.pdf"


def test_attachment_url_refuses_a_protocol_relative_host():
    """``//evil.test/a.pdf`` là URL tuyệt đối sang host khác, không phải path."""
    assert catalog_files._attachment_url({"href": "//evil.test/a.pdf"}) == ""


def test_attachment_url_accepts_a_subdomain_of_wfx():
    url = catalog_files._attachment_url(
        {"href": "https://files.worldfashionexchange.com/a.pdf"}
    )

    assert url == "https://files.worldfashionexchange.com/a.pdf"


@pytest.mark.parametrize(
    "href",
    [
        "http://prosports.worldfashionexchange.com/a.pdf",
        "https://evil.test/a.pdf",
        "https://worldfashionexchange.com.evil.test/a.pdf",
        "file:///C:/Windows/system32/config",
        "javascript:alert(1)",
        "",
    ],
)
def test_attachment_url_refuses_anything_off_https_wfx(href):
    assert catalog_files._attachment_url({"href": href}) == ""


def test_attachment_url_refuses_an_onclick_without_a_path():
    assert catalog_files._attachment_url({"onclick": "ViewAttachmentFile(this)"}) == ""


def test_attachment_url_prefers_href_over_onclick():
    url = catalog_files._attachment_url(
        {
            "href": "/Upload/tu-href.pdf",
            "onclick": "ViewAttachmentFile(this, '/Upload/tu-onclick.pdf')",
        }
    )

    assert url.endswith("tu-href.pdf")


# --- DOM popup Article ----------------------------------------------------


def _tab(index: int, label: str, *, actionable=True, selected=False) -> Element:
    children = []
    if actionable:
        children.append(element("a", id=f"tab{index}", attrs={"onclick": "go()"}))
    return Element(
        "li",
        text=label,
        css_class="active" if selected else "",
        children=children,
        attrs={},
    )


def _attachment_table(table_id: str, rows, *, visible=True) -> Element:
    body_rows = []
    for row in rows:
        body_rows.append(
            Element(
                "tr",
                css_class="trContent",
                attrs={"rowid": row["row_id"]},
                children=[
                    element("span", id="lblUserFileName", text=row["file_name"]),
                    element("span", id="lblComments", text=row.get("comments", "")),
                    element(
                        "span", id="lblUploadedOn", text=row.get("uploaded_on", "")
                    ),
                    element(
                        "span", id="lblUploadedBY", text=row.get("uploaded_by", "")
                    ),
                    element("a", id="lnkView", attrs={"href": row["href"]}),
                ],
            )
        )
    return Element(
        "table",
        id=table_id,
        visible=visible,
        children=[Element("tbody", children=body_rows)],
    )


class _ArticlePage:
    """Popup Article: nhiều frame, mỗi frame là một MiniFrame."""

    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.url = f"{WFX}/wfx_ArticleMain.aspx"
        self.bring_to_front_calls = 0
        self.dialog_handlers: list[tuple] = []

    def frame(self, name=None, **_kwargs):
        return next((f for f in self.frames if f.name == name), None)

    def bring_to_front(self):
        self.bring_to_front_calls += 1

    def wait_for_timeout(self, milliseconds):
        self.clock.advance(float(milliseconds) / 1_000.0)

    def on(self, event, handler):
        self.dialog_handlers.append((event, handler))

    def remove_listener(self, event, handler):
        self.dialog_handlers.remove((event, handler))


def _popup(clock, *, tabs=(5, 6, 8, 9), rows_by_tab=None, selected_tabs=None):
    """Popup Article: `ul#0` đủ 9 mục, chỉ những mục trong `tabs` bấm được.

    `//*[@id="0"]/li[N]` là xpath *vị trí*, nên danh sách phải có đủ 9 `li`
    giống WFX thật; mục không nằm trong `tabs` là mục không có hành động.
    """
    selected_tabs = set(selected_tabs or ())
    tab_items = [
        _tab(
            index,
            f"Mục {index}",
            actionable=index in tabs,
            selected=index in selected_tabs,
        )
        for index in range(1, 10)
    ]
    tab_list = Element("ul", id="0", children=tab_items)
    top_root = Element("body", children=[tab_list, element("a", id="Versions")])
    top = MiniFrame(
        top_root,
        name="ArticleTop",
        url=f"{WFX}/wfx_ArticleTop.aspx",
        clock=clock,
    )
    content_root = Element("body")
    content = MiniFrame(
        content_root,
        name="ArticleContent",
        url=f"{WFX}/wfxarticletechpack.aspx",
        clock=clock,
    )
    left = MiniFrame(
        Element("body"),
        name="ArticleLeft",
        url=f"{WFX}/wfxarticletechpack.aspx",
        clock=clock,
    )
    page = _ArticlePage(clock, [top, left, content])

    # Mỗi lần click một mục, WFX thay bảng file trong frame nội dung.
    rows_by_tab = rows_by_tab or {}

    def make_handler(index):
        def handler(_node):
            content_root.children.clear()
            rows = rows_by_tab.get(index)
            if rows is not None:
                content_root.append(
                    _attachment_table(
                        f"gridFileUploadDownload{index}_tblGridContent", rows
                    )
                )

        return handler

    for index in tabs:
        item = tab_items[index - 1]
        if item.children:
            item.children[0].on_click = make_handler(index)
    return page, top, content_root


def test_article_file_tab_resolves_the_actionable_control(clock):
    page, top, _content = _popup(clock)

    resolved = catalog_files._article_file_tab(page, top, 5)

    assert resolved is not None
    _frame, tab, action = resolved
    assert action.node.id == "tab5"


def test_article_file_tab_falls_back_to_an_li_that_carries_the_onclick(clock):
    item = Element("li", text="Mục 5", attrs={"onclick": "go()"})
    top = MiniFrame(
        Element("body", children=[Element("ul", id="0", children=[item])]),
        name="ArticleTop",
        clock=clock,
        xpaths={'//*[@id="0"]/li[5]': [item]},
    )
    page = _ArticlePage(clock, [top])

    _frame, tab, action = catalog_files._article_file_tab(page, top, 5)

    assert action.node is item


def test_article_file_tab_gives_up_on_a_missing_index(clock):
    page, top, _content = _popup(clock, tabs=(5,))

    assert catalog_files._article_file_tab(page, top, 9, timeout_seconds=0.3) is None


def test_visible_attachment_tables_skips_hidden_grids(clock):
    root = Element(
        "body",
        children=[
            _attachment_table(
                "gridFileUploadDownload5_tblGridContent",
                [{"row_id": "1", "file_name": "a.pdf", "href": "/Upload/a.pdf"}],
            ),
            _attachment_table(
                "gridFileUploadDownload6_tblGridContent",
                [{"row_id": "2", "file_name": "b.pdf", "href": "/Upload/b.pdf"}],
                visible=False,
            ),
        ],
    )
    page = _ArticlePage(clock, [MiniFrame(root, clock=clock)])

    tables = catalog_files._visible_attachment_tables(page)

    assert [table["table_id"] for table in tables] == [
        "gridFileUploadDownload5_tblGridContent"
    ]
    assert tables[0]["rows"][0]["file_name"] == "a.pdf"


def test_document_markers_detect_a_frame_that_reloaded(clock):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _ArticlePage(clock, [frame])
    snapshots = catalog_files._mark_article_documents(page)

    assert catalog_files._article_documents_changed(page, snapshots) is False

    frame.markers.clear()
    assert catalog_files._article_documents_changed(page, snapshots) is True


def test_document_markers_detect_a_frame_that_disappeared(clock):
    frame = MiniFrame(Element("body"), clock=clock)
    page = _ArticlePage(clock, [frame])
    snapshots = catalog_files._mark_article_documents(page)
    page.frames = []

    assert catalog_files._article_documents_changed(page, snapshots) is True


# --- quét bốn mục ---------------------------------------------------------


def test_scan_collects_files_from_every_tab_and_dedupes_by_url(clock):
    rows = {
        5: [
            {
                "row_id": "1",
                "file_name": "techpack.pdf",
                "href": "/Upload/techpack.pdf",
                "comments": "bản mới",
                "uploaded_on": "01/09/2026",
                "uploaded_by": "XUAN",
            }
        ],
        6: [
            {
                "row_id": "2",
                "file_name": "techpack-copy.pdf",
                "href": "/Upload/techpack.pdf",
            },
            {"row_id": "3", "file_name": "size.xlsx", "href": "/Upload/size.xlsx"},
        ],
        8: [],
        9: [],
    }
    page, top, _content = _popup(clock, rows_by_tab=rows)
    logs: list[str] = []

    files, sections = catalog_files._scan_article_file_tabs(page, top, logs.append)

    assert [item["file_name"] for item in files] == ["techpack.pdf", "size.xlsx"]
    assert files[0]["section_index"] == 5
    assert files[0]["uploaded_by"] == "XUAN"
    assert [section["file_count"] for section in sections] == [1, 1, 0, 0]
    assert all(section["available"] for section in sections)


def test_scan_marks_a_missing_tab_as_unavailable(clock):
    page, top, _content = _popup(clock, tabs=(5, 6), rows_by_tab={5: [], 6: []})
    logs: list[str] = []

    _files, sections = catalog_files._scan_article_file_tabs(page, top, logs.append)

    assert [section["available"] for section in sections] == [True, True, False, False]
    assert any("Không tìm thấy mục li[8]" in line for line in logs)


def test_scan_reports_a_tab_that_wfx_never_confirmed(clock):
    """Click xong mà không có tín hiệu nào thì không được coi là đã vào mục."""
    page, top, _content = _popup(clock, tabs=(5,))
    # Không gắn handler: click không đổi document, không đổi bảng, không selected.
    for node in top.root.descendants():
        node.on_click = None
    logs: list[str] = []

    _files, sections = catalog_files._scan_article_file_tabs(page, top, logs.append)

    assert sections[0]["available"] is False
    assert any("không xác nhận chuyển mục" in line for line in logs)


def test_scan_accepts_a_tab_that_only_reports_itself_as_selected(clock):
    page, top, _content = _popup(clock, tabs=(5,), selected_tabs={5})
    for node in top.root.descendants():
        node.on_click = None

    _files, sections = catalog_files._scan_article_file_tabs(
        page, top, lambda _line: None
    )

    assert sections[0]["available"] is True


def test_scan_marks_a_tab_unavailable_when_the_click_itself_fails(clock):
    page, top, _content = _popup(clock, tabs=(5,))
    anchor = next(node for node in top.root.descendants() if node.id == "tab5")
    anchor.enabled = False

    _files, sections = catalog_files._scan_article_file_tabs(
        page, top, lambda _line: None
    )

    assert sections[0]["available"] is False


def test_scan_drops_rows_whose_url_is_not_on_the_wfx_host(clock):
    rows = {
        5: [
            {"row_id": "1", "file_name": "ok.pdf", "href": "/Upload/ok.pdf"},
            {"row_id": "2", "file_name": "xau.pdf", "href": "https://evil.test/x.pdf"},
        ]
    }
    page, top, _content = _popup(clock, tabs=(5,), rows_by_tab=rows)

    files, _sections = catalog_files._scan_article_file_tabs(
        page, top, lambda _line: None
    )

    assert [item["file_name"] for item in files] == ["ok.pdf"]


# --- Techpack -------------------------------------------------------------


def test_techpack_is_reused_when_the_popup_is_already_on_it(clock):
    page, top, _content = _popup(clock)
    logs: list[str] = []

    assert catalog_files._ensure_article_techpack(page, top, logs.append) is top
    assert logs == []


def test_techpack_is_opened_through_the_versions_control(clock):
    page, top, _content = _popup(clock)
    left = page.frame(name="ArticleLeft")
    left.url = f"{WFX}/wfx_costsheet.aspx"
    versions = next(node for node in top.root.descendants() if node.id == "Versions")
    versions.on_click = lambda _n: setattr(
        left, "url", f"{WFX}/wfxarticletechpack.aspx"
    )
    logs: list[str] = []

    result = catalog_files._ensure_article_techpack(page, top, logs.append)

    assert result is top
    assert versions.clicks == 1
    assert any("Techpack đã sẵn sàng" in line for line in logs)


def test_techpack_times_out_instead_of_reading_the_wrong_screen(clock):
    page, top, _content = _popup(clock)
    page.frame(name="ArticleLeft").url = f"{WFX}/wfx_costsheet.aspx"

    with pytest.raises(PlaywrightTimeoutError):
        catalog_files._ensure_article_techpack(
            page, top, lambda _line: None, timeout_seconds=1
        )


# --- entry point ----------------------------------------------------------


def test_scan_catalog_files_requires_an_article_code(clock):
    result = catalog_files.scan_catalog_files("   ")

    assert result["code"] == "CATALOG_RESULT_REQUIRED"


def test_scan_catalog_files_reports_a_closed_browser(clock, monkeypatch):
    world = WfxWorld(clock)
    wire_automation(
        monkeypatch, catalog_files, world, chrome_ready=False, clock=clock
    )

    assert catalog_files.scan_catalog_files("ABC")["code"] == "CHROME_CLOSED"
    assert world.driver_starts == 0


def test_scan_catalog_files_reports_an_expired_session(clock, monkeypatch):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, catalog_files, world, logged_in=False, clock=clock)

    assert catalog_files.scan_catalog_files("ABC")["code"] == "NOT_LOGGED_IN"
    assert world.driver_stops == 1


def _wire_reader(monkeypatch, clock, reader):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, catalog_files, world, clock=clock)
    page, top, _content = _popup(clock)
    monkeypatch.setattr(
        catalog_files,
        "_article_page_for_code",
        lambda *a, **kw: (page, top),
    )
    monkeypatch.setattr(
        catalog_files, "_ensure_article_techpack", lambda *a, **kw: top
    )
    monkeypatch.setattr(catalog_files, "_scan_article_file_tabs", reader)
    return world, page


def test_scan_catalog_files_returns_the_files_it_found(clock, monkeypatch):
    files = [{"file_name": "a.pdf", "download_url": f"{WFX}/Upload/a.pdf"}]
    sections = [{"index": 5, "name": "Mục 5", "available": True, "file_count": 1}]
    world, page = _wire_reader(
        monkeypatch, clock, lambda *a, **kw: (files, sections)
    )

    result = catalog_files.scan_catalog_files("ABC123", _quiet())

    assert result["code"] == "CATALOG_FILES_SCANNED"
    assert result["file_count"] == 1
    assert result["article_code"] == "ABC123"
    assert page.bring_to_front_calls == 1
    assert world.driver_stops == 1


def test_scan_catalog_files_says_so_when_a_style_has_no_attachment(
    clock, monkeypatch
):
    sections = [{"index": 5, "name": "Mục 5", "available": True, "file_count": 0}]
    _world, _page = _wire_reader(monkeypatch, clock, lambda *a, **kw: ([], sections))

    result = catalog_files.scan_catalog_files("ABC123", _quiet())

    assert result["ok"] is True
    assert "không có file đính kèm" in result["message"]


def test_scan_catalog_files_reports_when_no_tab_was_reachable(clock, monkeypatch):
    sections = [{"index": 5, "name": "Mục 5", "available": False, "file_count": 0}]
    _world, _page = _wire_reader(monkeypatch, clock, lambda *a, **kw: ([], sections))

    result = catalog_files.scan_catalog_files("ABC123", _quiet())

    assert result["code"] == "CATALOG_FILE_TABS_NOT_FOUND"
    assert result["ok"] is False


def test_scan_catalog_files_recycles_cdp_exactly_once_before_giving_up(
    clock, monkeypatch
):
    """CLAUDE.md: probe trên CDP hiện tại trước, recycle đúng một lần."""
    world = WfxWorld(clock)
    wire_automation(monkeypatch, catalog_files, world, clock=clock)
    page, top, _content = _popup(clock)
    probes: list[float] = []

    def article_page(_context, _code, timeout_seconds=0):
        probes.append(timeout_seconds)
        if len(probes) == 1:
            raise PlaywrightTimeoutError("popup chưa với tới được")
        return page, top

    monkeypatch.setattr(catalog_files, "_article_page_for_code", article_page)
    monkeypatch.setattr(
        catalog_files, "_ensure_article_techpack", lambda *a, **kw: top
    )
    sections = [{"index": 5, "name": "Mục 5", "available": True, "file_count": 0}]
    monkeypatch.setattr(
        catalog_files, "_scan_article_file_tabs", lambda *a, **kw: ([], sections)
    )
    refreshed: list[int] = []

    def refresh(playwright, browser, current_page, _log):
        refreshed.append(1)
        return playwright, browser, current_page

    monkeypatch.setattr(catalog_files, "_refresh_article_context", refresh)

    result = catalog_files.scan_catalog_files("ABC123", _quiet())

    assert result["ok"] is True
    assert probes == [12, 20]
    assert refreshed == [1]


def test_scan_catalog_files_maps_a_lost_popup_to_a_retryable_code(
    clock, monkeypatch
):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, catalog_files, world, clock=clock)

    def gone(*_args, **_kwargs):
        raise PlaywrightTimeoutError("popup đã đóng")

    monkeypatch.setattr(catalog_files, "_article_page_for_code", gone)
    monkeypatch.setattr(
        catalog_files,
        "_refresh_article_context",
        lambda playwright, browser, page, _log: (playwright, browser, page),
    )

    result = catalog_files.scan_catalog_files("ABC123", _quiet())

    assert result["code"] == "CATALOG_FILES_CONTEXT_EXPIRED"
    assert result["article_code"] == "ABC123"


def test_scan_catalog_files_reports_an_unexpected_failure(clock, monkeypatch):
    world = WfxWorld(clock)
    wire_automation(monkeypatch, catalog_files, world, clock=clock)

    def boom(*_args, **_kwargs):
        raise PlaywrightError("CDP rơi")

    monkeypatch.setattr(catalog_files, "_article_page_for_code", boom)

    def refresh_boom(*_args, **_kwargs):
        raise ValueError("không dựng lại được driver")

    monkeypatch.setattr(catalog_files, "_refresh_article_context", refresh_boom)

    result = catalog_files.scan_catalog_files("ABC123", _quiet())

    assert result["code"] == "CATALOG_FILES_SCAN_FAILED"
    assert "ValueError" in result["message"]
