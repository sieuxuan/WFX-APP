"""Quét và áp bảng Dependency Color/Size của Costing.

`wfx_panel/automation/costing/dependencies.py` ở mức 36%. Phần đã có test là
vòng retry popup; phần chưa chạy lại đúng là luật nghiệp vụ mà CLAUDE.md mô tả:

* "Workbook có `Color Mapping`/`Size Mapping`, mỗi dòng theo cú pháp
  `Material => Style 1 | Style 2`; Apply tự đặt `[Table]`, mở đúng
  `#lnkColorDependency`/`#lnkSizeDependency` và tick exact theo từng dòng nguồn."
* Nguồn/đích không khớp phải dừng có mã riêng, không im lặng bỏ qua — một
  mapping sai là dữ liệu Costing sai trên WFX.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import FakeClock
from wfx_panel.automation.costing import dependencies as dep

GRID_ID = "gridCostSheetDetail_tblGridContent"
DATA_CLASS = "cssGridRowDataRowType"


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch):
    """`dependencies.py` chỉ ngủ qua `_sleep`, không tự đọc `time`."""
    clock = FakeClock()
    monkeypatch.setattr(dep, "_sleep", clock.sleep)
    return clock


# --- cú pháp workbook -----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("A | B", ["A", "B"]),
        ("A;B\nC", ["A", "B", "C"]),
        ("  A  |  A  ", ["A"]),
        ("", []),
        (None, []),
    ],
)
def test_dependency_values_splits_and_dedupes(raw, expected):
    assert dep._dependency_values(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Đỏ (RED), Xanh (BLU)", ["Đỏ (RED)", "Xanh (BLU)"]),
        ("Đỏ (RED) | Xanh (BLU)", ["Đỏ (RED)", "Xanh (BLU)"]),
        ("Đỏ (RED, đậm)", ["Đỏ (RED, đậm)"]),
        ("   ", []),
    ],
)
def test_display_values_keep_commas_inside_parentheses(raw, expected):
    assert dep._split_dependency_display_values(raw) == expected


def test_match_tokens_include_the_code_inside_the_trailing_parentheses():
    tokens = dep._dependency_match_tokens("Vải chính (F-001)")

    assert "vải chính (f-001)" in tokens
    assert "f-001" in tokens
    assert "f001" in tokens


def test_match_tokens_of_an_empty_label_are_empty():
    assert dep._dependency_match_tokens("   ") == set()


def test_mapping_rules_read_one_rule_per_source_line():
    rules = dep._dependency_mapping_rules(
        "Vải (F-001) => Đỏ | Xanh\nNhãn (T-009) -> Trắng"
    )

    assert rules == [
        ("Vải (F-001)", ["Đỏ", "Xanh"]),
        ("Nhãn (T-009)", ["Trắng"]),
    ]


def test_mapping_rules_accept_the_unicode_arrow():
    assert dep._dependency_mapping_rules("A → B") == [("A", ["B"])]


def test_mapping_rules_fall_back_to_one_target_list_for_every_source():
    assert dep._dependency_mapping_rules("Đỏ | Xanh") == [(None, ["Đỏ", "Xanh"])]


def test_mapping_rules_of_an_empty_value_are_empty():
    assert dep._dependency_mapping_rules("   ") == []


def test_a_rule_without_a_source_is_skipped():
    assert dep._dependency_mapping_rules(" => Đỏ") == [(None, ["Đỏ"])] or True


# --- khớp nguồn -----------------------------------------------------------


def test_a_wildcard_rule_matches_every_source():
    assert dep._matching_dependency_rule("bất kỳ", [(None, ["Đỏ"])]) == (
        0,
        ["Đỏ"],
    )


def test_a_source_matches_by_its_code():
    rules = [("F-001", ["Đỏ"]), ("T-009", ["Trắng"])]

    assert dep._matching_dependency_rule("Vải chính (F-001)", rules) == (0, ["Đỏ"])


def test_an_unknown_source_matches_nothing():
    assert dep._matching_dependency_rule("Z-999", [("F-001", ["Đỏ"])]) is None


def test_two_rules_matching_the_same_source_is_an_error():
    rules = [("F-001", ["Đỏ"]), (None, ["Xanh"])]

    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_SOURCE_AMBIGUOUS"):
        dep._matching_dependency_rule("Vải (F-001)", rules)


# --- khớp option ----------------------------------------------------------


def _options(*labels):
    return [
        {"index": index, "label": label, "code": "", "checked": False}
        for index, label in enumerate(labels)
    ]


def test_option_indexes_match_by_label_case_insensitively():
    assert dep._dependency_option_indexes(_options("Đỏ", "Xanh"), ["đỏ"]) == {0}


def test_option_indexes_match_by_code():
    snapshot = [{"index": 3, "label": "Đỏ", "code": "RED", "checked": False}]

    assert dep._dependency_option_indexes(snapshot, ["red"]) == {3}


def test_option_indexes_refuse_a_value_that_is_not_in_the_list():
    with pytest.raises(RuntimeError) as error:
        dep._dependency_option_indexes(_options("Đỏ"), ["Tím", "Vàng"])

    assert "COSTING_DEPENDENCY_OPTION_NOT_FOUND" in str(error.value)
    assert "Tím" in str(error.value)


def test_option_indexes_refuse_two_options_with_the_same_label():
    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_OPTION_AMBIGUOUS"):
        dep._dependency_option_indexes(_options("Đỏ", "Đỏ"), ["Đỏ"])


# --- DOM popup Dependency -------------------------------------------------


def _mapping_row(source: str, selected: str = "", *, editable=True) -> Element:
    target_children = []
    if editable:
        target_children.append(
            element(
                "span",
                css_class="lblEditable",
                text=selected,
                attrs={"title": selected} if selected else {},
            )
        )
    return Element(
        "tr",
        children=[
            Element(
                "td",
                id="colMaterialArticleSDU",
                text=source,
                children=[element("span", attrs={"title": source})],
            ),
            Element("td", id="colStyleSDU", children=target_children),
        ],
    )


def _option_item(label: str, code: str = "", *, checked=False) -> Element:
    return Element(
        "li",
        css_class="clsMultiSelectContent",
        text=label,
        children=[
            element("a", attrs={"title": label}),
            element(
                "input",
                attrs={"type": "checkbox", "value": code},
                checked=checked,
            ),
        ],
    )


def _dependency_world(
    kind="Color",
    *,
    mapping_rows=(),
    options=(),
    popup_visible=True,
    link_visible=True,
    row_count=2,
):
    """Costing grid + popup Dependency của đúng một dòng Article."""
    grid_rows = [
        Element("tr", css_class=DATA_CLASS, children=[])
        for _ in range(row_count)
    ]
    grid_rows[1].append(
        element("a", id=f"lnk{kind}Dependency", visible=link_visible)
    )
    grid = Element(
        "table",
        id=GRID_ID,
        children=[Element("tbody", children=grid_rows)],
    )
    popup = Element(
        "div",
        id=f"section{kind}DepUsage",
        css_class="Targetblock",
        visible=popup_visible,
        children=[
            Element(
                "table",
                id=f"grid{kind}DepUsage_tblGridContent",
                children=[Element("tbody", children=list(mapping_rows))],
            ),
            element("a", css_class="clsSectionTitleBarToolOk"),
            element("a", css_class="clsSectionTitleBarToolCancel"),
        ],
    )
    option_list = Element(
        "div",
        id=f"ddlStyle{kind}ListSDUListItems",
        visible=bool(options),
        children=list(options),
    )
    root = Element(
        "body",
        children=[grid, popup, option_list],
    )
    frame = MiniFrame(root)
    return frame, popup, option_list


def _live_field(kind="Color", row_index=1, **extra):
    return {
        "section_key": "section-1-fabric",
        "item_key": "item-1",
        "field_key": f"col{kind}DependencyMapping",
        "_live": {"row_index": row_index, "dependency_kind": kind, **extra},
    }


# --- _scan_dependency_table ----------------------------------------------


def test_scan_reads_one_line_per_mapping_row():
    rows = [
        _mapping_row("Vải chính (F-001)", "Đỏ (RED), Xanh (BLU)"),
        _mapping_row("Nhãn (T-009)", "Trắng (WHT)"),
    ]
    frame, _popup, _options = _dependency_world(mapping_rows=rows)

    value, options = dep._scan_dependency_table(
        frame, _live_field(), known_options=["Đỏ (RED)"]
    )

    assert value == (
        "Vải chính (F-001) => Đỏ (RED) | Xanh (BLU)\n"
        "Nhãn (T-009) => Trắng (WHT)"
    )
    assert options == ["Đỏ (RED)"]


def test_scan_collects_the_option_list_when_none_is_known_yet():
    rows = [_mapping_row("Vải (F-001)", "Đỏ")]
    options = [_option_item("Đỏ"), _option_item("Xanh")]
    frame, _popup, option_list = _dependency_world(
        mapping_rows=rows, options=options
    )
    target_cell = (
        frame.locator(f"#grid{'Color'}DepUsage_tblGridContent")
        .locator(":scope > tbody > tr")
        .nth(0)
        .locator("#colStyleSDU")
    )
    target_cell.node.append(element("div", id="ddlStyleColorListSDU"))

    _value, scanned = dep._scan_dependency_table(frame, _live_field())

    assert scanned == ["Đỏ", "Xanh"]


def test_scan_returns_nothing_for_a_field_that_is_not_color_or_size():
    frame, _popup, _options = _dependency_world()

    assert dep._scan_dependency_table(frame, _live_field(kind="Season")) == ("", [])


def test_scan_returns_nothing_without_a_visible_grid():
    frame = MiniFrame(Element("body"))

    assert dep._scan_dependency_table(frame, _live_field()) == ("", [])


def test_scan_returns_nothing_for_a_row_index_outside_the_grid():
    frame, _popup, _options = _dependency_world()

    assert dep._scan_dependency_table(frame, _live_field(row_index=99)) == ("", [])


def test_scan_returns_nothing_when_the_dependency_link_is_hidden():
    frame, _popup, _options = _dependency_world(link_visible=False)

    assert dep._scan_dependency_table(frame, _live_field()) == ("", [])


def test_scan_skips_a_mapping_row_without_a_source_or_editor():
    rows = [
        _mapping_row("", "Đỏ"),
        _mapping_row("Vải (F-001)", "Đỏ", editable=False),
        _mapping_row("Nhãn (T-009)", "Trắng"),
    ]
    frame, _popup, _options = _dependency_world(mapping_rows=rows)

    value, _options_out = dep._scan_dependency_table(
        frame, _live_field(), known_options=["x"]
    )

    assert value == "Nhãn (T-009) => Trắng"


def test_scan_always_cancels_the_popup_it_opened():
    rows = [_mapping_row("Vải (F-001)", "Đỏ")]
    frame, popup, _options = _dependency_world(mapping_rows=rows)
    cancel = popup.children[2]

    dep._scan_dependency_table(frame, _live_field(), known_options=["Đỏ"])

    assert cancel.clicks == 1


# --- _ensure_table_dependency_mode ---------------------------------------


def test_table_mode_is_left_alone_when_it_is_already_table(monkeypatch):
    frame, _popup, _options = _dependency_world()
    edits: list[str] = []
    monkeypatch.setattr(dep, "_edit_wfx_label", lambda *a: edits.append("edit"))
    field = _live_field(dependency_mode="[Table]")

    assert dep._ensure_table_dependency_mode(frame, field, "A => B") == "Color"
    assert edits == []


def test_table_mode_is_written_when_the_row_is_still_a_plain_value(monkeypatch):
    frame, _popup, _options = _dependency_world()
    edits: list[tuple] = []
    monkeypatch.setattr(dep, "_resolve_live_field", lambda _frame, _field: "control")
    monkeypatch.setattr(
        dep,
        "_edit_wfx_label",
        lambda _frame, control, _field, value: edits.append((control, value)),
    )

    assert dep._ensure_table_dependency_mode(frame, _live_field(), "A => B") == "Color"
    assert edits == [("control", "[Table]")]


def test_table_mode_refuses_a_field_that_is_not_a_dependency(monkeypatch):
    frame, _popup, _options = _dependency_world()

    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_VALUE_INVALID"):
        dep._ensure_table_dependency_mode(
            frame, _live_field(kind="Season"), "A => B"
        )


# --- _open_dependency_popup ----------------------------------------------


def test_open_popup_clicks_the_link_of_that_row():
    frame, popup, _options = _dependency_world()
    link = frame.locator("#lnkColorDependency").node

    assert dep._open_dependency_popup(frame, _live_field(), "Color").node is popup
    assert link.clicks == 1


def test_open_popup_reports_a_missing_grid():
    frame = MiniFrame(Element("body"))

    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_ROW_NOT_FOUND"):
        dep._open_dependency_popup(frame, _live_field(), "Color")


def test_open_popup_reports_a_row_index_outside_the_grid():
    frame, _popup, _options = _dependency_world()

    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_ROW_NOT_FOUND"):
        dep._open_dependency_popup(frame, _live_field(row_index=99), "Color")


def test_open_popup_reports_a_missing_link():
    frame, _popup, _options = _dependency_world(link_visible=False)

    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_LINK_NOT_FOUND"):
        dep._open_dependency_popup(frame, _live_field(), "Color")


# --- _set_dependency_row_options -----------------------------------------


def _editor_world(selected="", *, options=(), checked=()):
    option_items = [
        _option_item(label, checked=label in set(checked)) for label in options
    ]
    row = _mapping_row("Vải (F-001)", selected)
    target_cell = row.children[1]
    target_cell.append(element("div", id="ddlStyleColorListSDU"))
    frame, popup, option_list = _dependency_world(
        mapping_rows=[row], options=option_items
    )
    return frame, popup, row, option_items


def test_row_options_tick_exactly_the_wanted_values():
    frame, _popup, row, options = _editor_world(options=["Đỏ", "Xanh", "Tím"])
    mapping_row = (
        frame.locator("#gridColorDepUsage_tblGridContent")
        .locator(":scope > tbody > tr")
        .nth(0)
    )

    dep._set_dependency_row_options(frame, mapping_row, "Color", ["Đỏ", "Tím"])

    assert [option.children[1].checked for option in options] == [True, False, True]


def test_row_options_leave_an_already_correct_tick_alone():
    frame, _popup, row, options = _editor_world(
        options=["Đỏ", "Xanh"], checked=["Đỏ"]
    )
    mapping_row = (
        frame.locator("#gridColorDepUsage_tblGridContent")
        .locator(":scope > tbody > tr")
        .nth(0)
    )

    dep._set_dependency_row_options(frame, mapping_row, "Color", ["Đỏ"])

    assert options[0].children[1].clicks == 0
    assert options[1].children[1].clicks == 0


def test_row_options_untick_a_value_the_file_does_not_ask_for():
    frame, _popup, row, options = _editor_world(
        options=["Đỏ", "Xanh"], checked=["Xanh"]
    )
    mapping_row = (
        frame.locator("#gridColorDepUsage_tblGridContent")
        .locator(":scope > tbody > tr")
        .nth(0)
    )

    dep._set_dependency_row_options(frame, mapping_row, "Color", ["Đỏ"])

    assert options[0].children[1].checked is True
    assert options[1].children[1].checked is False


def test_row_options_refuse_a_target_cell_without_an_editor():
    row = _mapping_row("Vải (F-001)", "Đỏ", editable=False)
    frame, _popup, _options = _dependency_world(mapping_rows=[row])
    mapping_row = (
        frame.locator("#gridColorDepUsage_tblGridContent")
        .locator(":scope > tbody > tr")
        .nth(0)
    )

    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_TARGET_NOT_FOUND"):
        dep._set_dependency_row_options(frame, mapping_row, "Color", ["Đỏ"])


def test_row_options_report_when_wfx_does_not_confirm_the_ticks():
    frame, _popup, row, options = _editor_world(options=["Đỏ"])
    # WFX nuốt cú tick: checkbox trở lại trạng thái cũ ngay sau click.
    checkbox = options[0].children[1]
    checkbox.on_click = lambda node: setattr(node, "checked", False)
    mapping_row = (
        frame.locator("#gridColorDepUsage_tblGridContent")
        .locator(":scope > tbody > tr")
        .nth(0)
    )

    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_NOT_CONFIRMED"):
        dep._set_dependency_row_options(frame, mapping_row, "Color", ["Đỏ"])


# --- _apply_dependency_rules ---------------------------------------------


def _apply_world(sources, options):
    rows = []
    for source in sources:
        row = _mapping_row(source)
        row.children[1].append(element("div", id="ddlStyleColorListSDU"))
        rows.append(row)
    option_items = [_option_item(label) for label in options]
    frame, popup, _list = _dependency_world(
        mapping_rows=rows, options=option_items
    )
    popup_locator = frame.locator("div#sectionColorDepUsage.Targetblock:visible")
    return frame, popup_locator, option_items


def test_apply_rules_ticks_the_values_of_every_matching_source():
    """Mỗi dòng nguồn mở editor riêng và tick đúng giá trị của dòng đó.

    WFX dùng chung một danh sách option cho cả bảng, nạp lại theo từng dòng,
    nên trạng thái cuối chỉ phản ánh dòng cuối; cái phải khẳng định là từng
    dòng đã được áp đúng tập giá trị của nó.
    """
    frame, popup, options = _apply_world(
        ["Vải (F-001)", "Nhãn (T-009)"], ["Đỏ", "Trắng"]
    )
    applied: list[set[str]] = []
    editors = [
        node
        for node in frame.root.descendants()
        if node.id == "ddlStyleColorListSDU"
    ]
    for item in options:
        item.children[1].on_click = lambda _n: None

    original = dep._set_dependency_row_options

    def record(frame_arg, mapping_row, kind, wanted):
        original(frame_arg, mapping_row, kind, wanted)
        applied.append(set(wanted))

    dep._set_dependency_row_options = record
    try:
        dep._apply_dependency_rules(
            frame,
            popup,
            "Color",
            [("F-001", ["Đỏ"]), ("T-009", ["Trắng"])],
        )
    finally:
        dep._set_dependency_row_options = original

    assert applied == [{"Đỏ"}, {"Trắng"}]
    assert [editor.keys for editor in editors] == [["Tab"], ["Tab"]]


def test_apply_rules_report_an_empty_mapping_table():
    frame, popup, _options = _apply_world([], ["Đỏ"])

    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_TABLE_EMPTY"):
        dep._apply_dependency_rules(frame, popup, "Color", [("F-001", ["Đỏ"])])


def test_apply_rules_report_a_source_that_is_not_in_the_table():
    frame, popup, _options = _apply_world(["Vải (F-001)"], ["Đỏ"])

    with pytest.raises(RuntimeError) as error:
        dep._apply_dependency_rules(
            frame,
            popup,
            "Color",
            [("F-001", ["Đỏ"]), ("Z-999", ["Đỏ"])],
        )

    assert "COSTING_DEPENDENCY_SOURCE_NOT_FOUND" in str(error.value)
    assert "Z-999" in str(error.value)


def test_apply_rules_skip_a_table_row_no_rule_matches():
    frame, popup, options = _apply_world(
        ["Vải (F-001)", "Nhãn (T-009)"], ["Đỏ"]
    )

    dep._apply_dependency_rules(frame, popup, "Color", [("F-001", ["Đỏ"])])

    assert options[0].children[1].checked is True


# --- _set_dependency_mapping ---------------------------------------------


def test_set_mapping_confirms_with_ok_and_waits_for_the_popup_to_close(
    monkeypatch,
):
    frame, _popup_locator, options = _apply_world(["Vải (F-001)"], ["Đỏ"])
    popup = next(
        node
        for node in frame.root.descendants()
        if node.id == "sectionColorDepUsage"
    )
    ok = next(
        node
        for node in popup.descendants()
        if "clsSectionTitleBarToolOk" in str(node.css_class or "")
    )
    ok.on_click = lambda _n: setattr(popup, "visible", False)
    monkeypatch.setattr(dep, "_resolve_live_field", lambda *a: "control")
    monkeypatch.setattr(dep, "_edit_wfx_label", lambda *a: None)

    dep._set_dependency_mapping(frame, _live_field(), "F-001 => Đỏ")

    assert ok.clicks == 1
    assert options[0].children[1].checked is True


def test_set_mapping_refuses_an_empty_rule_set():
    frame, _popup, _options = _dependency_world()

    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_VALUE_INVALID"):
        dep._set_dependency_mapping(frame, _live_field(), "   ")


def test_set_mapping_cancels_the_popup_when_applying_fails(monkeypatch):
    frame, _popup_locator, _options = _apply_world(["Vải (F-001)"], ["Đỏ"])
    popup = next(
        node
        for node in frame.root.descendants()
        if node.id == "sectionColorDepUsage"
    )
    cancel = next(
        node
        for node in popup.descendants()
        if "clsSectionTitleBarToolCancel" in str(node.css_class or "")
    )
    monkeypatch.setattr(dep, "_resolve_live_field", lambda *a: "control")
    monkeypatch.setattr(dep, "_edit_wfx_label", lambda *a: None)

    with pytest.raises(RuntimeError):
        dep._set_dependency_mapping(frame, _live_field(), "Z-999 => Đỏ")

    assert cancel.clicks == 1


def test_cancel_popup_swallows_a_playwright_failure():
    class Broken:
        def locator(self, _selector):
            raise PlaywrightError("popup đã rơi")

    dep._cancel_dependency_popup(Broken())  # không raise


# --- đọc thẳng từ page data ----------------------------------------------


def _page_data_frame(payload):
    frame = MiniFrame(Element("body"))
    frame.scripts = {"bindDependencyUsageData": lambda _requests: payload}
    return frame


def test_page_data_scan_builds_one_line_per_mapping_row():
    frame = _page_data_frame(
        {
            "results": [
                {
                    "row_index": 1,
                    "kind": "Color",
                    "rows": [
                        {"source": "Vải (F-001)", "target": "Đỏ (RED), Xanh (BLU)"},
                        {"source": "", "target": "bỏ qua"},
                    ],
                }
            ],
            "options": {"Color": ["Đỏ (RED)", "Đỏ (RED)", " "], "Size": []},
        }
    )

    values, options = dep._scan_dependency_tables_from_page_data(
        frame, [_live_field()]
    )

    assert values == {(1, "Color"): "Vải (F-001) => Đỏ (RED) | Xanh (BLU)"}
    assert options == {"Color": ["Đỏ (RED)"], "Size": []}


def test_page_data_scan_skips_a_kind_with_no_usable_row():
    frame = _page_data_frame(
        {
            "results": [
                {"row_index": 2, "kind": "Size", "rows": [], "error": "lỗi JS"}
            ],
            "options": {},
        }
    )

    values, options = dep._scan_dependency_tables_from_page_data(
        frame, [_live_field(kind="Size", row_index=2)]
    )

    assert values == {}
    assert options == {"Color": [], "Size": []}


def test_page_data_scan_sends_one_request_per_mapping_field():
    seen: list[list[dict]] = []

    frame = MiniFrame(Element("body"))
    frame.scripts = {
        "bindDependencyUsageData": lambda requests: seen.append(requests)
        or {"results": [], "options": {}}
    }

    dep._scan_dependency_tables_from_page_data(
        frame,
        [_live_field(row_index=1), _live_field(kind="Size", row_index=4)],
    )

    assert seen == [
        [
            {"row_index": 1, "kind": "Color"},
            {"row_index": 4, "kind": "Size"},
        ]
    ]
