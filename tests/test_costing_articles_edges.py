"""Costing Article: DOM đổi giữa chừng và các control WFX không như mong đợi.

CLAUDE.md: Add Article chỉ dùng `#imgAdd` và Material Search; Delete phải chọn
đúng row rồi qua popup lý do; dòng `>>` phải được tạo bằng
`#imgSplitterForUsage`. Không thao tác nào được coi là xong khi DOM đã đổi.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import FakeClock, patch_automation
from tests.test_costing_articles import (
    GRID_ID,
    _article_row,
    _Context,
    _costing_frame,
    _live_document,
    _material_frame,
    _Page,
    _section_header,
)
from wfx_panel.automation.costing import articles as costing_articles


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch):
    clock = FakeClock()
    patch_automation(monkeypatch, costing_articles, "time", clock)
    monkeypatch.setattr(costing_articles, "_sleep", clock.sleep)
    return clock


def _deletion(**overrides):
    deletion = {
        "section_key": "section-1-fabric",
        "live_item_key": "item-1",
        "article_code": "F-001",
    }
    deletion.update(overrides)
    return deletion


def _live(row_index=1):
    return {
        "fields": [
            {
                "scope": "item",
                "section_key": "section-1-fabric",
                "item_key": "item-1",
                "_live": {"row_index": row_index},
            }
        ]
    }


def _reason_popup(*, ok_visible=True):
    return Element(
        "div",
        id="sectionCostSheetDeletionReason",
        children=[
            element("input", id="txtActionRemarks"),
            element(
                "a", css_class="clsSectionTitleBarToolOk", visible=ok_visible
            ),
        ],
    )


# --- control của section --------------------------------------------------


def test_a_section_control_that_detaches_mid_probe_is_not_used():
    header = Element(
        "tr",
        css_class="cssGridRowBOMCodeMainHeaderRowType",
        children=[
            element("span", id="lblBOMCodeTranslated", text="Fabric"),
            element("img", id="imgAdd"),
        ],
    )
    frame = _costing_frame([header])
    row = frame.locator(f"#{GRID_ID}").locator(":scope > tbody > tr").nth(0).node
    add = next(child for child in row.children if child.id == "imgAdd")

    def refuse(_self=None, timeout=None):
        raise PlaywrightError("node is not attached to the DOM")

    add.is_visible = refuse

    with pytest.raises(RuntimeError, match="COSTING_SECTION_ACTION_NOT_UNIQUE"):
        costing_articles._section_action(frame, "section-1-fabric", "imgAdd")


# --- Material Search ------------------------------------------------------


def test_a_material_window_that_throws_while_being_probed_is_skipped():
    class Exploding(MiniFrame):
        def locator(self, selector):
            raise PlaywrightError("frame was detached")

    material = _material_frame([])
    context = _Context([_Page([Exploding(Element("body")), material])])

    _page, frame = costing_articles._material_search_frame(context)

    assert frame is material


def test_a_material_grid_whose_api_is_gone_falls_back_to_reading_the_rows():
    frame = _material_frame(
        [{"row_id": "1", "article_code": "F-001", "article_name": "Vải"}]
    )
    real_evaluate = frame.evaluate

    def refuse(script, arg=None):
        if "GetObjGrid" in script or "ArticleCode" in script:
            raise PlaywrightError("GetObjGrid không còn")
        return real_evaluate(script, arg)

    frame.evaluate = refuse

    rows = costing_articles._material_option_rows(frame)

    assert [row["article_code"] for row in rows] == ["F-001"]


def test_a_matched_row_whose_checkbox_is_gone_is_never_selected():
    frame = _material_frame(
        [{"row_id": "1", "article_code": "F-001", "article_name": "Vải"}]
    )
    row = frame.locator("#gridArticleList_tblGridContent").locator(
        ":scope > tbody > tr"
    ).nth(0).node
    checkbox = next(child for child in row.children if child.id == "chkSelector")
    checkbox.visible = False

    with pytest.raises(RuntimeError, match="COSTING_MATERIAL_SELECTOR_NOT_UNIQUE"):
        costing_articles._select_material_match(frame, {"row_id": "1"})


# --- Delete ---------------------------------------------------------------


def test_deleting_without_a_visible_grid_is_refused():
    frame = MiniFrame(Element("body"))

    with pytest.raises(RuntimeError, match="COSTING_GRID_NOT_FOUND"):
        costing_articles._delete_articles(
            _Page([frame]), frame, _live(), [_deletion()], lambda _line: None
        )


def test_a_delete_target_outside_the_grid_is_refused():
    frame = _costing_frame(
        [_section_header("Fabric"), _article_row("Vải chính (F-001)")],
        extra=[_reason_popup()],
    )

    with pytest.raises(RuntimeError, match="COSTING_DELETE_TARGET_DETACHED"):
        costing_articles._delete_articles(
            _Page([frame]),
            frame,
            _live(row_index=99),
            [_deletion()],
            lambda _line: None,
        )


def test_a_row_without_a_selector_checkbox_stops_the_delete():
    frame = _costing_frame(
        [
            _section_header("Fabric"),
            _article_row("Vải chính (F-001)", selector=False),
        ],
        extra=[_reason_popup()],
    )

    with pytest.raises(RuntimeError, match="COSTING_DELETE_SELECTOR_NOT_UNIQUE"):
        costing_articles._delete_articles(
            _Page([frame]), frame, _live(), [_deletion()], lambda _line: None
        )


def test_a_delete_popup_without_a_visible_ok_is_refused():
    frame = _costing_frame(
        [_section_header("Fabric"), _article_row("Vải chính (F-001)")],
        extra=[_reason_popup(ok_visible=False)],
    )

    with pytest.raises(RuntimeError, match="COSTING_DELETE_REASON_OK_NOT_FOUND"):
        costing_articles._delete_articles(
            _Page([frame]), frame, _live(), [_deletion()], lambda _line: None
        )


def test_the_native_delete_confirmation_is_accepted_for_the_user():
    popup = _reason_popup()
    frame = _costing_frame(
        [_section_header("Fabric"), _article_row("Vải chính (F-001)")],
        extra=[popup],
    )
    page = _Page([frame])
    grid_body = frame.locator(f"#{GRID_ID}").locator(":scope > tbody").node
    accepted: list[int] = []

    class Dialog:
        message = "Bạn có chắc?"

        def accept(self):
            accepted.append(1)

    delete_button = frame.locator("#imgDelete").node
    delete_button.on_click = lambda _node: [
        handler(Dialog()) for _event, handler in page.dialog_handlers
    ]
    popup.children[1].on_click = lambda _node: grid_body.children.pop()

    costing_articles._delete_articles(
        page, frame, _live(), [_deletion()], lambda _line: None
    )

    assert accepted == [1]
    assert page.dialog_handlers == []


# --- Splitter -------------------------------------------------------------


def test_a_splitter_that_playwright_cannot_click_is_clicked_natively():
    frame = _costing_frame(
        [_section_header("Fabric"), _article_row("Vải (F-001)", splitter=True)]
    )
    grid_body = frame.locator(f"#{GRID_ID}").locator(":scope > tbody").node
    splitter = frame.locator(
        '#colSplitterForUsage [id="imgSplitterForUsage"]'
    ).node

    def refuse(timeout=None):
        raise PlaywrightError("element is covered by another element")

    splitter.click = refuse
    splitter.on_click = lambda _node: grid_body.append(_article_row(">>"))

    costing_articles._split_article_row(
        frame,
        _live_document(),
        {"section_key": "section-1-fabric", "article_code": "F-001"},
    )

    assert splitter.clicks == 1


def test_splitting_without_a_visible_grid_is_refused():
    frame = MiniFrame(Element("body"))

    with pytest.raises(RuntimeError, match="COSTING_SPLIT_SOURCE_NOT_FOUND"):
        costing_articles._split_article_row(
            frame,
            _live_document(),
            {"section_key": "section-1-fabric", "article_code": "F-001"},
        )


def test_splitting_a_row_that_has_no_grid_field_is_refused():
    frame = _costing_frame(
        [_section_header("Fabric"), _article_row("Vải (F-001)", splitter=True)]
    )
    document = _live_document()
    for field in document["fields"]:
        field["_live"] = {**field["_live"], "region": "editor"}

    with pytest.raises(RuntimeError, match="COSTING_SPLIT_SOURCE_NOT_FOUND"):
        costing_articles._split_article_row(
            frame,
            document,
            {"section_key": "section-1-fabric", "article_code": "F-001"},
        )


# --- quét dropdown Article -----------------------------------------------


def test_a_material_window_that_will_not_close_does_not_fail_the_scan(
    monkeypatch
):
    frame = _costing_frame([_section_header("Fabric")])
    material = _material_frame(
        [{"row_id": "1", "article_code": "F-001", "article_name": "Vải"}]
    )
    page = _Page([frame])
    page.context = _Context([page])
    frame.page = page
    patch_automation(
        monkeypatch,
        costing_articles,
        "_material_search_frame",
        lambda _context: (page, material),
    )

    def refuse(_frame):
        raise PlaywrightError("popup đã đóng")

    patch_automation(
        monkeypatch, costing_articles, "_close_material_search", refuse
    )
    document = {
        "sections": [{"section_key": "section-1-fabric", "name": "Fabric"}]
    }

    costing_articles._scan_costing_article_dropdowns(
        frame, document, lambda _line: None
    )

    assert document["sections"][0]["article_code_options"] == ["F-001"]


# --- rollback dòng chi phí ------------------------------------------------


def test_a_cost_line_that_cannot_be_filled_is_rolled_back_without_crashing(
    monkeypatch
):
    frame = _costing_frame([_section_header("CM Costs")])

    def new_row(_frame, _addition):
        return frame.locator(f"#{GRID_ID}")

    def refuse(_row, _addition):
        raise RuntimeError("không chọn được Article")

    def refuse_action(*_args, **_kwargs):
        raise PlaywrightError("frame was detached")

    patch_automation(monkeypatch, costing_articles, "_new_special_cost_row", new_row)
    patch_automation(
        monkeypatch, costing_articles, "_select_special_cost_article", refuse
    )
    patch_automation(monkeypatch, costing_articles, "_section_action", refuse_action)

    with pytest.raises(RuntimeError, match="không chọn được Article"):
        costing_articles._add_special_cost_lines(
            frame,
            [{"section_key": "section-1-CM_Costs", "article_name": "Sewing"}],
            lambda _line: None,
        )


def test_a_row_whose_article_name_changed_stops_the_delete():
    frame = _costing_frame(
        [_section_header("Fabric"), _article_row("Khác hẳn")],
        extra=[_reason_popup()],
    )

    with pytest.raises(RuntimeError, match="COSTING_DELETE_TARGET_CHANGED"):
        costing_articles._delete_articles(
            _Page([frame]),
            frame,
            _live(),
            [_deletion(article_code="", article_name="Vải chính")],
            lambda _line: None,
        )


def test_a_delete_popup_without_its_reason_box_is_refused():
    popup = Element(
        "div",
        id="sectionCostSheetDeletionReason",
        children=[
            element("input", id="txtActionRemarks", visible=False),
            element("a", css_class="clsSectionTitleBarToolOk"),
        ],
    )
    frame = _costing_frame(
        [_section_header("Fabric"), _article_row("Vải chính (F-001)")],
        extra=[popup],
    )

    with pytest.raises(RuntimeError, match="COSTING_DELETE_REASON_NOT_FOUND"):
        costing_articles._delete_articles(
            _Page([frame]), frame, _live(), [_deletion()], lambda _line: None
        )
