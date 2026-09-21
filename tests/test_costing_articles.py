"""Material Search, Add/Delete Article và Splitter trong Costing.

`wfx_panel/automation/costing/articles.py` là nơi thi hành nhiều luật cứng của
CLAUDE.md: Add Article chỉ dùng `#imgAdd` + Material Search với exact Article
Code rồi fallback Article Name, 0 kết quả thì skip, nhiều kết quả thì chờ user;
Continue cho item chưa phải cuối và Finish cho item cuối; dòng `>>` phải được
tạo bằng `#imgSplitterForUsage` chứ không Add lại cùng Article; Delete phải
chọn đúng row rồi qua popup lý do.

Trước đây module này gần như không có test chạy thân hàm (7% dòng). Test ở đây
dựng một Costing grid thật bằng `tests/fakes/mini_dom` và chạy đúng hàm sản
phẩm, nên mỗi luật trên được kiểm ở chính chỗ nó được thi hành.
"""

from __future__ import annotations

import pytest

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import FakeClock, patch_automation
from wfx_panel.automation.costing import articles as costing_articles

SECTION_CLASS = "cssGridRowBOMCodeMainHeaderRowType"
DATA_CLASS = "cssGridRowDataRowType"
GRID_ID = "gridCostSheetDetail_tblGridContent"


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch):
    clock = FakeClock()
    patch_automation(monkeypatch, costing_articles, "time", clock)
    monkeypatch.setattr(costing_articles, "_sleep", clock.sleep)
    return clock


# --- dựng grid ------------------------------------------------------------


def _section_header(name: str, *, add=True, delete=True) -> Element:
    children = [element("span", id="lblBOMCodeTranslated", text=name)]
    if add:
        children.append(element("img", id="imgAdd"))
    if delete:
        children.append(element("img", id="imgDelete"))
    return Element("tr", css_class=SECTION_CLASS, children=children)


def _article_row(
    label: str,
    *,
    splitter: bool = False,
    splitter_visible: bool = True,
    selector: bool = True,
) -> Element:
    children = [element("span", id="lblArticle", text=label)]
    if selector:
        children.append(
            element("input", id="chkSelector", attrs={"type": "checkbox"})
        )
    if splitter:
        children.append(
            element(
                "span",
                id="colSplitterForUsage",
                children=[
                    element(
                        "img",
                        id="imgSplitterForUsage",
                        visible=splitter_visible,
                    )
                ],
            )
        )
    return Element("tr", css_class=DATA_CLASS, children=children)


def _costing_frame(rows, *, extra=(), clock=None) -> MiniFrame:
    body = Element("tbody", children=list(rows))
    grid = Element("table", id=GRID_ID, children=[body])
    root = Element("body", children=[grid, *extra])
    return MiniFrame(root, clock=clock)


# --- _section_row_index / _section_action ---------------------------------


def test_section_index_counts_only_section_header_rows():
    frame = _costing_frame(
        [
            _section_header("Fabric"),
            _article_row("Vải chính (F-001)"),
            _section_header("Trim"),
            _article_row("Nhãn (T-009)"),
        ]
    )
    grid = frame.locator(f"#{GRID_ID}")

    assert costing_articles._section_row_index(grid, "section-1-fabric") == 0
    assert costing_articles._section_row_index(grid, "section-2-trim") == 2


def test_section_index_rejects_a_key_that_matches_nothing():
    frame = _costing_frame([_section_header("Fabric")])
    grid = frame.locator(f"#{GRID_ID}")

    with pytest.raises(RuntimeError, match="COSTING_SECTION_NOT_FOUND"):
        costing_articles._section_row_index(grid, "section-9-khong-co")


def test_section_index_falls_back_to_col_article_when_there_is_no_bom_label():
    header = Element(
        "tr",
        css_class=SECTION_CLASS,
        children=[element("span", id="colArticle", text="CM Costs")],
    )
    frame = _costing_frame([header])
    grid = frame.locator(f"#{GRID_ID}")

    assert costing_articles._section_row_index(grid, "section-1-CM_Costs") == 0


def test_section_action_finds_the_control_of_that_section_only():
    frame = _costing_frame(
        [
            _section_header("Fabric"),
            _article_row("Vải (F-001)"),
            _section_header("Trim"),
            _article_row("Nhãn (T-009)"),
        ]
    )
    fabric_add = costing_articles._section_action(frame, "section-1-fabric", "imgAdd")
    trim_add = costing_articles._section_action(frame, "section-2-trim", "imgAdd")

    fabric_add.click()

    assert fabric_add.node.clicks == 1
    assert trim_add.node.clicks == 0


def test_section_action_stops_at_the_next_section_header():
    """Nút của section sau không được tính là của section trước."""
    frame = _costing_frame(
        [
            _section_header("Fabric", add=True),
            _section_header("Trim", add=True),
        ]
    )

    action = costing_articles._section_action(frame, "section-1-fabric", "imgAdd")

    assert action.node is frame.locator(f"#{GRID_ID}").locator(
        ":scope > tbody > tr"
    ).nth(0).locator("#imgAdd").node


def test_section_action_refuses_an_invisible_control():
    header = Element(
        "tr",
        css_class=SECTION_CLASS,
        children=[
            element("span", id="lblBOMCodeTranslated", text="Fabric"),
            element("img", id="imgAdd", visible=False),
        ],
    )
    frame = _costing_frame([header])

    with pytest.raises(RuntimeError, match="COSTING_SECTION_ACTION_NOT_UNIQUE"):
        costing_articles._section_action(frame, "section-1-fabric", "imgAdd")


def test_section_action_requires_a_visible_grid():
    root = Element("body", children=[])
    frame = MiniFrame(root)

    with pytest.raises(RuntimeError, match="COSTING_GRID_NOT_FOUND"):
        costing_articles._section_action(frame, "section-1-fabric", "imgAdd")


# --- Material Search ------------------------------------------------------


def _material_frame(rows, *, scripts=None, name="material") -> MiniFrame:
    """Frame Material Search: hai ô tìm + grid kết quả."""
    grid_rows = [
        Element(
            "tr",
            attrs={"rowid": row["row_id"]},
            children=[
                element("span", id="lblArticleCode", text=row["article_code"]),
                element("span", id="lblArticleName", text=row["article_name"]),
                element("input", id="chkSelector", attrs={"type": "checkbox"}),
            ],
        )
        for row in rows
    ]
    grid = Element(
        "table",
        id="gridArticleList_tblGridContent",
        children=[Element("tbody", children=grid_rows)],
    )
    section = Element(
        "div",
        id="sectionArticleList",
        children=[
            element("a", css_class="clsSectionTitleBarToolClose"),
            element("a", css_class="clsSectionTitleBarToolAddnContinue"),
            element("a", css_class="clsSectionTitleBarToolAddnClose"),
        ],
    )
    root = Element(
        "body",
        children=[
            element("input", id="txtSearchArticleCode"),
            element("input", id="txtSearchArticleName"),
            grid,
            section,
        ],
    )
    # Không khai báo sẵn kết quả đọc grid: mini_dom tính lại từ chính cây ở
    # trên, nên một cây dựng sai sẽ làm test đỏ thay vì xanh giả.
    return MiniFrame(root, name=name, scripts=scripts)


class _Page:
    def __init__(self, frames):
        self.frames = list(frames)
        self.dialog_handlers: list[tuple] = []

    def on(self, event, handler):
        self.dialog_handlers.append((event, handler))

    def remove_listener(self, event, handler):
        self.dialog_handlers.remove((event, handler))


class _Context:
    def __init__(self, pages):
        self.pages = list(pages)


def test_material_search_frame_returns_the_only_bound_search_window():
    material = _material_frame([])
    context = _Context([_Page([MiniFrame(Element("body")), material])])

    _page, frame = costing_articles._material_search_frame(context)

    assert frame is material


def test_material_search_frame_times_out_when_no_window_opened():
    context = _Context([_Page([MiniFrame(Element("body"))])])

    with pytest.raises(Exception, match="COSTING_MATERIAL_SEARCH_NOT_FOUND"):
        costing_articles._material_search_frame(context, timeout_seconds=0.3)


def test_material_search_frame_refuses_two_candidate_windows():
    context = _Context([_Page([_material_frame([]), _material_frame([])])])

    with pytest.raises(Exception, match="COSTING_MATERIAL_SEARCH_NOT_FOUND"):
        costing_articles._material_search_frame(context, timeout_seconds=0.3)


def test_search_material_without_a_query_never_touches_wfx():
    frame = _material_frame([])

    assert costing_articles._search_material(frame) == []
    assert frame.locator("#txtSearchArticleCode").node.fills == []


def test_search_material_prefers_the_code_field_and_confirms_exact_matches():
    rows = [
        {"row_id": "1", "article_code": "F-001", "article_name": "Vải chính"},
    ]
    frame = _material_frame(rows)

    matches = costing_articles._search_material(frame, article_code="f-001")

    assert matches == rows
    assert frame.locator("#txtSearchArticleCode").node.fills == ["", "f-001"]
    assert frame.locator("#txtSearchArticleCode").node.keys == ["Enter"]
    assert frame.locator("#txtSearchArticleName").node.fills == [""]


def test_search_material_falls_back_to_the_name_field():
    rows = [{"row_id": "7", "article_code": "T-009", "article_name": "Nhãn dệt"}]
    frame = _material_frame(rows)

    matches = costing_articles._search_material(frame, article_name="Nhãn dệt")

    assert matches == rows
    assert frame.locator("#txtSearchArticleName").node.keys == ["Enter"]


def test_search_material_drops_rows_that_only_contain_the_query():
    """WFX tìm chứa chuỗi; chỉ exact mới được coi là kết quả."""
    rows = [
        {"row_id": "1", "article_code": "F-001", "article_name": "Vải"},
        {"row_id": "2", "article_code": "F-0010", "article_name": "Vải phụ"},
    ]
    frame = _material_frame(rows)

    matches = costing_articles._search_material(frame, article_code="F-001")

    assert [row["row_id"] for row in matches] == ["1"]


def test_search_material_requires_unique_search_inputs():
    root = Element("body", children=[element("input", id="txtSearchArticleCode")])
    frame = MiniFrame(root)

    with pytest.raises(RuntimeError, match="COSTING_MATERIAL_SEARCH_INPUT_NOT_UNIQUE"):
        costing_articles._search_material(frame, article_code="F-001")


def test_material_rows_is_empty_without_the_result_grid():
    frame = MiniFrame(Element("body"))

    assert costing_articles._material_rows(frame) == []


# --- resolve từ lựa chọn của người dùng -----------------------------------


def test_resolution_from_the_user_replaces_both_code_and_name():
    addition = {
        "import_item_key": "item-1",
        "article_code": "",
        "article_name": "Vải chính",
    }

    assert costing_articles._resolved_search(addition, {"item-1": "F-001"}) == (
        "F-001",
        "",
    )


def test_without_a_resolution_the_file_values_are_used_as_is():
    addition = {
        "import_item_key": "item-1",
        "article_code": "F-001",
        "article_name": "Vải chính",
    }

    assert costing_articles._resolved_search(addition, {}) == ("F-001", "Vải chính")


# --- preflight ------------------------------------------------------------


def _preflight_world(rows):
    material = _material_frame(rows)
    grid_frame = _costing_frame(
        [_section_header("Fabric"), _article_row("Vải (F-001)")]
    )
    context = _Context([_Page([material])])
    return context, grid_frame, material


def test_preflight_reports_a_single_match_as_found():
    rows = [{"row_id": "1", "article_code": "F-001", "article_name": "Vải chính"}]
    context, grid_frame, material = _preflight_world(rows)
    logs: list[str] = []

    result = costing_articles._preflight_article_additions(
        context,
        grid_frame,
        [{"section_key": "section-1-fabric", "article_code": "F-001"}],
        {},
        logs.append,
    )

    assert [item["resolved_code"] for item in result["found"]] == ["F-001"]
    assert result["missing"] == [] and result["ambiguous"] == []
    # Luôn đóng Material Search lại, kể cả khi thành công.
    assert material.locator(".clsSectionTitleBarToolClose").node.clicks == 1


def test_preflight_skips_an_article_with_no_result_and_logs_the_count():
    context, grid_frame, _material = _preflight_world([])
    logs: list[str] = []

    result = costing_articles._preflight_article_additions(
        context,
        grid_frame,
        [{"section_key": "section-1-fabric", "article_code": "KHONG-CO"}],
        {},
        logs.append,
    )

    assert result["found"] == []
    assert [item["article_code"] for item in result["missing"]] == ["KHONG-CO"]
    assert any("Bỏ qua 1 Article" in line for line in logs)


def test_preflight_never_picks_the_first_row_when_several_match():
    """CLAUDE.md: nhiều kết quả thì chờ user resolve, không tự chọn dòng đầu."""
    rows = [
        {"row_id": "1", "article_code": "F-001", "article_name": "Vải A"},
        {"row_id": "2", "article_code": "F-001", "article_name": "Vải B"},
    ]
    context, grid_frame, _material = _preflight_world(rows)

    result = costing_articles._preflight_article_additions(
        context,
        grid_frame,
        [{"section_key": "section-1-fabric", "article_code": "F-001"}],
        {},
        lambda _line: None,
    )

    assert result["found"] == []
    assert len(result["ambiguous"]) == 1
    assert len(result["ambiguous"][0]["candidates"]) == 2


def test_preflight_closes_material_search_even_when_the_search_explodes(
    monkeypatch,
):
    context, grid_frame, material = _preflight_world([])

    def boom(*_args, **_kwargs):
        raise RuntimeError("WFX rơi frame")

    monkeypatch.setattr(costing_articles, "_search_material", boom)

    with pytest.raises(RuntimeError, match="WFX rơi frame"):
        costing_articles._preflight_article_additions(
            context,
            grid_frame,
            [{"section_key": "section-1-fabric", "article_code": "F-001"}],
            {},
            lambda _line: None,
        )

    assert material.locator(".clsSectionTitleBarToolClose").node.clicks == 1


# --- add ------------------------------------------------------------------


def test_add_uses_continue_for_every_item_but_the_last():
    rows = [
        {"row_id": "1", "article_code": "F-001", "article_name": "Vải A"},
        {"row_id": "2", "article_code": "F-002", "article_name": "Vải B"},
    ]
    material = _material_frame(rows)
    grid_frame = _costing_frame([_section_header("Fabric")])
    context = _Context([_Page([material])])
    logs: list[str] = []

    added = costing_articles._add_articles(
        context,
        grid_frame,
        {
            "found": [
                {"section_key": "section-1-fabric", "resolved_code": "F-001"},
                {"section_key": "section-1-fabric", "resolved_code": "F-002"},
            ]
        },
        logs.append,
    )

    assert len(added) == 2
    assert material.locator(".clsSectionTitleBarToolAddnContinue").node.clicks == 1
    assert material.locator(".clsSectionTitleBarToolAddnClose").node.clicks == 1
    assert any("Đã thêm 2 Article" in line for line in logs)


def test_add_ticks_exactly_the_matching_row():
    rows = [
        {"row_id": "1", "article_code": "F-001", "article_name": "Vải A"},
    ]
    material = _material_frame(rows)
    grid_frame = _costing_frame([_section_header("Fabric")])
    context = _Context([_Page([material])])

    costing_articles._add_articles(
        context,
        grid_frame,
        {"found": [{"section_key": "section-1-fabric", "resolved_code": "F-001"}]},
        lambda _line: None,
    )

    checkboxes = material.locator(
        "#gridArticleList_tblGridContent > tbody > tr #chkSelector"
    )
    assert checkboxes.nth(0).node.checked is True


def test_add_stops_when_the_row_disappeared_between_preflight_and_add():
    material = _material_frame([])
    grid_frame = _costing_frame([_section_header("Fabric")])
    context = _Context([_Page([material])])

    with pytest.raises(RuntimeError, match="COSTING_MATERIAL_RESULT_CHANGED"):
        costing_articles._add_articles(
            context,
            grid_frame,
            {
                "found": [
                    {"section_key": "section-1-fabric", "resolved_code": "F-001"}
                ]
            },
            lambda _line: None,
        )

    assert material.locator(".clsSectionTitleBarToolClose").node.clicks == 1


def test_add_with_nothing_found_touches_nothing():
    grid_frame = _costing_frame([_section_header("Fabric")])
    context = _Context([_Page([])])

    assert (
        costing_articles._add_articles(
            context, grid_frame, {"found": []}, lambda _line: None
        )
        == []
    )


def test_select_material_match_rejects_a_row_that_moved():
    frame = _material_frame(
        [{"row_id": "1", "article_code": "F-001", "article_name": "Vải"}]
    )

    with pytest.raises(RuntimeError, match="COSTING_MATERIAL_RESULT_DETACHED"):
        costing_articles._select_material_match(frame, {"row_id": "999"})


# --- splitter -------------------------------------------------------------


def _live_document(row_index: int = 1) -> dict:
    return {
        "items": [
            {
                "section_key": "section-1-fabric",
                "article_code": "F-001",
                "item_key": "item-1",
                "row_order": 1,
            }
        ],
        "fields": [
            {
                "section_key": "section-1-fabric",
                "item_key": "item-1",
                "scope": "item",
                "_live": {"row_index": row_index, "region": "grid"},
            }
        ],
    }


def test_splitter_clicks_the_source_row_and_waits_for_the_new_line():
    rows = [
        _section_header("Fabric"),
        _article_row("Vải (F-001)", splitter=True),
    ]
    frame = _costing_frame(rows)
    grid_body = frame.locator(f"#{GRID_ID}").locator(":scope > tbody").node

    def grow(_node):
        grid_body.append(_article_row(">>", splitter=False))

    splitter = frame.locator('#colSplitterForUsage [id="imgSplitterForUsage"]').node
    splitter.on_click = grow

    costing_articles._split_article_row(
        frame,
        _live_document(),
        {"section_key": "section-1-fabric", "article_code": "F-001"},
    )

    assert splitter.clicks == 1
    assert frame.locator(f"#{GRID_ID}").locator(":scope > tbody > tr").count() == 3


def test_splitter_reports_when_wfx_never_created_the_continuation_row():
    frame = _costing_frame(
        [_section_header("Fabric"), _article_row("Vải (F-001)", splitter=True)]
    )

    with pytest.raises(RuntimeError, match="COSTING_SPLIT_NOT_CONFIRMED"):
        costing_articles._split_article_row(
            frame,
            _live_document(),
            {"section_key": "section-1-fabric", "article_code": "F-001"},
        )


def test_splitter_requires_a_visible_splitter_on_that_row():
    frame = _costing_frame(
        [
            _section_header("Fabric"),
            _article_row("Vải (F-001)", splitter=True, splitter_visible=False),
        ]
    )

    with pytest.raises(RuntimeError, match="COSTING_SPLITTER_NOT_FOUND"):
        costing_articles._split_article_row(
            frame,
            _live_document(),
            {"section_key": "section-1-fabric", "article_code": "F-001"},
        )


def test_splitter_refuses_an_article_that_is_not_in_the_live_document():
    frame = _costing_frame([_section_header("Fabric"), _article_row("Vải (F-001)")])

    with pytest.raises(RuntimeError, match="COSTING_SPLIT_SOURCE_NOT_FOUND"):
        costing_articles._split_article_row(
            frame,
            _live_document(),
            {"section_key": "section-1-fabric", "article_code": "KHONG-CO"},
        )


def test_splitter_refuses_a_row_index_outside_the_grid():
    frame = _costing_frame([_section_header("Fabric"), _article_row("Vải (F-001)")])

    with pytest.raises(RuntimeError, match="COSTING_SPLIT_SOURCE_NOT_FOUND"):
        costing_articles._split_article_row(
            frame,
            _live_document(row_index=99),
            {"section_key": "section-1-fabric", "article_code": "F-001"},
        )


def test_splitter_picks_the_last_continuation_row_as_the_source():
    document = {
        "items": [
            {
                "section_key": "section-1-fabric",
                "article_code": "F-001",
                "item_key": "item-1",
                "row_order": 1,
            },
            {
                "section_key": "section-1-fabric",
                "article_code": "F-001",
                "item_key": "item-2",
                "row_order": 2,
            },
        ],
        "fields": [
            {
                "section_key": "section-1-fabric",
                "item_key": "item-2",
                "scope": "item",
                "_live": {"row_index": 2, "region": "grid"},
            }
        ],
    }
    frame = _costing_frame(
        [
            _section_header("Fabric"),
            _article_row("Vải (F-001)", splitter=True),
            _article_row(">>", splitter=True),
        ]
    )
    grid_body = frame.locator(f"#{GRID_ID}").locator(":scope > tbody").node
    rows = frame.locator(f"#{GRID_ID}").locator(":scope > tbody > tr")
    second_splitter = rows.nth(2).locator("#imgSplitterForUsage").node
    second_splitter.on_click = lambda _n: grid_body.append(_article_row(">>"))

    costing_articles._split_article_row(
        frame,
        document,
        {"section_key": "section-1-fabric", "article_code": "F-001"},
    )

    assert second_splitter.clicks == 1
    assert rows.nth(1).locator("#imgSplitterForUsage").node.clicks == 0


# --- delete ---------------------------------------------------------------


def test_delete_row_index_needs_exactly_one_matching_live_row():
    live = {
        "fields": [
            {
                "scope": "item",
                "section_key": "section-1-fabric",
                "item_key": "item-1",
                "_live": {"row_index": 3},
            }
        ]
    }

    assert (
        costing_articles._delete_row_index(
            live,
            {"section_key": "section-1-fabric", "live_item_key": "item-1"},
        )
        == 3
    )


def test_delete_row_index_refuses_an_ambiguous_target():
    live = {
        "fields": [
            {
                "scope": "item",
                "section_key": "section-1-fabric",
                "item_key": "item-1",
                "_live": {"row_index": 3},
            },
            {
                "scope": "item",
                "section_key": "section-1-fabric",
                "item_key": "item-1",
                "_live": {"row_index": 4},
            },
        ]
    }

    with pytest.raises(RuntimeError, match="COSTING_DELETE_TARGET_NOT_UNIQUE"):
        costing_articles._delete_row_index(
            live,
            {"section_key": "section-1-fabric", "live_item_key": "item-1"},
        )


def _delete_world(*, article_label="Vải chính (F-001)", with_popup=True):
    popup_children = [
        element("input", id="txtActionRemarks"),
        element("a", css_class="clsSectionTitleBarToolOk"),
    ]
    popup = Element(
        "div",
        id="sectionCostSheetDeletionReason",
        visible=with_popup,
        children=popup_children,
    )
    frame = _costing_frame(
        [_section_header("Fabric"), _article_row(article_label)],
        extra=[popup],
    )
    page = _Page([frame])
    live = {
        "fields": [
            {
                "scope": "item",
                "section_key": "section-1-fabric",
                "item_key": "item-1",
                "_live": {"row_index": 1},
            }
        ]
    }
    return page, frame, live, popup


def test_delete_ticks_the_row_fills_the_reason_and_confirms():
    page, frame, live, popup = _delete_world()
    grid_body = frame.locator(f"#{GRID_ID}").locator(":scope > tbody").node
    ok = popup.children[1]
    ok.on_click = lambda _n: grid_body.children.pop()
    logs: list[str] = []

    deleted = costing_articles._delete_articles(
        page,
        frame,
        live,
        [
            {
                "section_key": "section-1-fabric",
                "live_item_key": "item-1",
                "article_code": "F-001",
            }
        ],
        logs.append,
    )

    assert len(deleted) == 1
    assert popup.children[0].value == "Updated via Costing import"
    assert any("Đã xóa 1 Article" in line for line in logs)
    # Listener dialog phải được gỡ để lượt sau không bị handler cũ nuốt mất.
    assert page.dialog_handlers == []


def test_delete_refuses_a_row_whose_article_changed():
    page, frame, live, _popup = _delete_world(article_label="Khác hẳn (F-999)")

    with pytest.raises(RuntimeError, match="COSTING_DELETE_TARGET_CHANGED"):
        costing_articles._delete_articles(
            page,
            frame,
            live,
            [
                {
                    "section_key": "section-1-fabric",
                    "live_item_key": "item-1",
                    "article_code": "F-001",
                }
            ],
            lambda _line: None,
        )


def test_delete_matches_by_name_when_the_file_has_no_code():
    page, frame, live, popup = _delete_world(article_label="Vải chính")
    grid_body = frame.locator(f"#{GRID_ID}").locator(":scope > tbody").node
    popup.children[1].on_click = lambda _n: grid_body.children.pop()

    deleted = costing_articles._delete_articles(
        page,
        frame,
        live,
        [
            {
                "section_key": "section-1-fabric",
                "live_item_key": "item-1",
                "article_name": "Vải chính",
            }
        ],
        lambda _line: None,
    )

    assert len(deleted) == 1


def test_delete_stops_when_the_reason_popup_never_shows():
    page, frame, live, _popup = _delete_world(with_popup=False)

    with pytest.raises(RuntimeError, match="COSTING_DELETE_REASON_NOT_FOUND"):
        costing_articles._delete_articles(
            page,
            frame,
            live,
            [
                {
                    "section_key": "section-1-fabric",
                    "live_item_key": "item-1",
                    "article_code": "F-001",
                }
            ],
            lambda _line: None,
        )

    assert page.dialog_handlers == []


def test_delete_reports_when_the_row_is_still_there_afterwards():
    page, frame, live, _popup = _delete_world()

    with pytest.raises(RuntimeError, match="COSTING_DELETE_NOT_CONFIRMED"):
        costing_articles._delete_articles(
            page,
            frame,
            live,
            [
                {
                    "section_key": "section-1-fabric",
                    "live_item_key": "item-1",
                    "article_code": "F-001",
                }
            ],
            lambda _line: None,
        )


def test_delete_with_an_empty_request_never_touches_the_grid():
    page, frame, live, _popup = _delete_world()

    assert (
        costing_articles._delete_articles(page, frame, live, [], lambda _l: None)
        == []
    )


# --- quét dropdown Article cho workbook -----------------------------------


class _ContextPage(_Page):
    def __init__(self, frames):
        super().__init__(frames)
        self.context = None


def _dropdown_world(rows):
    material = _material_frame(rows)
    costing = _costing_frame(
        [_section_header("Fabric"), _section_header("CM Costs")]
    )
    page = _ContextPage([costing, material])
    context = _Context([page])
    page.context = context
    costing.page = page
    material.page = page
    return context, costing, material


def test_dropdown_scan_collects_unique_codes_and_names_per_section():
    rows = [
        {"row_id": "1", "article_code": "F-001", "article_name": "Vải chính"},
        {"row_id": "2", "article_code": "F-002", "article_name": "Vải phụ"},
        {"row_id": "3", "article_code": "F-002", "article_name": "Vải phụ"},
    ]
    _context, costing, _material = _dropdown_world(rows)
    document = {
        "sections": [
            {"section_key": "section-1-fabric", "name": "Fabric"},
        ]
    }
    logs: list[str] = []

    costing_articles._scan_costing_article_dropdowns(costing, document, logs.append)

    section = document["sections"][0]
    assert section["article_code_options"] == ["F-001", "F-002"]
    assert section["article_name_options"] == ["Vải chính", "Vải phụ"]
    assert document["article_dropdown_option_count"] == 2
    assert any("Đã quét 2 lựa chọn Article" in line for line in logs)


def test_dropdown_scan_skips_the_three_special_cost_sections():
    """CM/Production/Indirect Costs không dùng Material Search."""
    _context, costing, material = _dropdown_world(
        [{"row_id": "1", "article_code": "F-001", "article_name": "Vải"}]
    )
    document = {
        "sections": [
            {"section_key": "section-2-CM_Costs", "name": "CM Costs"},
            {"section_key": "section-3-Indirect_Costs", "name": "Indirect Costs"},
            {
                "section_key": "section-4-Production_Costs",
                "name": "Production Costs",
            },
        ]
    }

    costing_articles._scan_costing_article_dropdowns(
        costing, document, lambda _line: None
    )

    assert document["article_dropdown_option_count"] == 0
    assert all("article_code_options" not in s for s in document["sections"])
    assert material.locator("#txtSearchArticleCode").node.fills == []


def test_dropdown_scan_logs_and_continues_when_one_section_fails():
    _context, costing, _material = _dropdown_world([])
    document = {
        "sections": [
            {"section_key": "section-9-khong-co", "name": "Ma"},
        ]
    }
    logs: list[str] = []

    costing_articles._scan_costing_article_dropdowns(costing, document, logs.append)

    assert any("Không quét được dropdown Article" in line for line in logs)
    assert document["article_dropdown_option_count"] == 0


def test_scan_material_options_clears_both_fields_and_dedupes():
    rows = [
        {"row_id": "1", "article_code": "F-001", "article_name": "Vải"},
        {"row_id": "2", "article_code": "f-001", "article_name": "vải"},
        {"row_id": "3", "article_code": "", "article_name": ""},
    ]
    frame = _material_frame(rows)

    options = costing_articles._scan_material_option_rows(frame)

    assert [row["article_code"] for row in options] == ["F-001"]
    assert frame.locator("#txtSearchArticleCode").node.fills == [""]
    assert frame.locator("#txtSearchArticleName").node.fills == [""]


def test_scan_material_options_presses_enter_when_the_grid_is_empty():
    frame = _material_frame([])

    assert costing_articles._scan_material_option_rows(frame) == []
    assert frame.locator("#txtSearchArticleCode").node.keys == ["Enter"]


def test_material_option_rows_falls_back_to_the_dom_when_the_grid_api_is_absent():
    rows = [{"row_id": "1", "article_code": "F-001", "article_name": "Vải"}]
    frame = _material_frame(rows)

    assert costing_articles._material_option_rows(frame) == rows


# --- dòng chi phí đặc biệt ------------------------------------------------


@pytest.mark.parametrize(
    ("section_name", "editor"),
    [
        ("CM Costs", "#CostSheetCMCosts_ddlSupplierCompany"),
        ("Production Costs", "#CostSheetProdProcessDetails_ddlProcessName"),
        ("Indirect Costs", "#ddlTitle"),
    ],
)
def test_special_cost_config_resolves_each_of_the_three_blocks(
    section_name, editor
):
    config = costing_articles._special_cost_config(
        {"section_key": "", "section_name": section_name}
    )

    assert config["editor"] == editor


def test_special_cost_config_refuses_a_material_section():
    with pytest.raises(RuntimeError, match="COSTING_SPECIAL_SECTION_NOT_SUPPORTED"):
        costing_articles._special_cost_config(
            {"section_key": "section-1-fabric", "section_name": "Fabric"}
        )


def _special_world(options=(("Nhà máy A", "77"),), existing_value="1001"):
    """Một block Indirect Costs: header + một dòng sẵn có."""
    header = Element(
        "tr",
        css_class="cssGridRowICHeaderRowType",
        children=[
            element("span", id="lblBOMCodeTranslated", text="Indirect Costs"),
            element("img", id="imgAdd"),
            element("img", id="imgDelete"),
        ],
    )
    existing = Element(
        "tr",
        css_class="cssGridRowICDataRowType",
        children=[
            element(
                "input",
                id="chkSelector",
                attrs={"type": "checkbox", "value": existing_value},
            )
        ],
    )
    frame = _costing_frame([header, existing])
    grid_body = frame.locator("#" + GRID_ID).locator(":scope > tbody").node

    def add_new_row(_node):
        grid_body.append(
            Element(
                "tr",
                css_class="cssGridRowICDataRowType",
                children=[
                    element(
                        "input",
                        id="chkSelector",
                        attrs={"type": "checkbox", "value": "-1001"},
                    ),
                    element("span", id="lblTitle"),
                    Element(
                        "select",
                        id="ddlTitle",
                        children=[
                            element("option", text=label, attrs={"value": value})
                            for label, value in options
                        ],
                    ),
                ],
            )
        )

    frame.locator("#" + GRID_ID).locator(":scope > tbody > tr").nth(0).locator(
        "#imgAdd"
    ).node.on_click = add_new_row
    return frame


def test_new_special_cost_row_waits_for_the_row_wfx_marks_as_new():
    frame = _special_world()

    row = costing_articles._new_special_cost_row(
        frame, {"section_key": "section-1-Indirect_Costs"}
    )

    assert row.locator("#chkSelector").get_attribute("value") == "-1001"


def test_new_special_cost_row_reports_when_wfx_never_added_a_row():
    header = Element(
        "tr",
        css_class="cssGridRowICHeaderRowType",
        children=[
            element("span", id="lblBOMCodeTranslated", text="Indirect Costs"),
            element("img", id="imgAdd"),
        ],
    )
    frame = _costing_frame([header])

    with pytest.raises(RuntimeError, match="COSTING_SPECIAL_ROW_NOT_ADDED"):
        costing_articles._new_special_cost_row(
            frame, {"section_key": "section-1-Indirect_Costs"}
        )


def test_special_cost_article_selection_needs_a_name():
    frame = _special_world()
    row = costing_articles._new_special_cost_row(
        frame, {"section_key": "section-1-Indirect_Costs"}
    )

    with pytest.raises(RuntimeError, match="COSTING_SPECIAL_ARTICLE_REQUIRED"):
        costing_articles._select_special_cost_article(
            row, {"section_name": "Indirect Costs", "article_name": "  "}
        )


def test_special_cost_article_selection_applies_the_exact_option():
    frame = _special_world(options=(("Nhà máy A", "77"), ("Nhà máy B", "88")))
    row = costing_articles._new_special_cost_row(
        frame, {"section_key": "section-1-Indirect_Costs"}
    )

    costing_articles._select_special_cost_article(
        row, {"section_name": "Indirect Costs", "article_name": "nhà máy b"}
    )

    editor = row.locator("#ddlTitle")
    assert editor.node.selected == ["88"]
    assert editor.node.keys == ["Tab"]


def test_special_cost_article_selection_refuses_an_unknown_name():
    frame = _special_world()
    row = costing_articles._new_special_cost_row(
        frame, {"section_key": "section-1-Indirect_Costs"}
    )

    with pytest.raises(RuntimeError, match="COSTING_SPECIAL_ARTICLE_NOT_FOUND"):
        costing_articles._select_special_cost_article(
            row, {"section_name": "Indirect Costs", "article_name": "Không có"}
        )


def test_add_special_cost_lines_adds_and_logs():
    frame = _special_world()
    logs: list[str] = []

    added = costing_articles._add_special_cost_lines(
        frame,
        [
            {
                "section_key": "section-1-Indirect_Costs",
                "section_name": "Indirect Costs",
                "article_name": "Nhà máy A",
            }
        ],
        logs.append,
    )

    assert len(added) == 1
    assert any("Đã thêm 1 dòng chi phí" in line for line in logs)


def test_add_special_cost_lines_rolls_the_new_row_back_on_failure():
    """Không để lại một dòng chi phí rỗng trên WFX khi chọn Article hỏng."""
    frame = _special_world()

    with pytest.raises(RuntimeError, match="COSTING_SPECIAL_ARTICLE_NOT_FOUND"):
        costing_articles._add_special_cost_lines(
            frame,
            [
                {
                    "section_key": "section-1-Indirect_Costs",
                    "section_name": "Indirect Costs",
                    "article_name": "Không có",
                }
            ],
            lambda _line: None,
        )

    rows = frame.locator("#" + GRID_ID).locator(":scope > tbody > tr")
    header_delete = rows.nth(0).locator("#imgDelete").node
    new_row_checkbox = rows.nth(2).locator("#chkSelector").node
    assert new_row_checkbox.clicks == 1
    assert header_delete.clicks == 1


def test_add_special_cost_lines_with_nothing_to_add_is_silent():
    frame = _special_world()
    logs: list[str] = []

    assert costing_articles._add_special_cost_lines(frame, [], logs.append) == []
    assert logs == []
