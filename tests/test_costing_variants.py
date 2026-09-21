"""Bổ sung Material Color/Size còn thiếu qua Article Color/Size List.

`wfx_panel/automation/costing/variants.py` ở mức 17%. CLAUDE.md đặc tả rất chi
tiết luồng này và chưa có dòng nào được kiểm:

* "Khi Apply gặp Material Color/Size chưa có trong option của đúng Article,
  automation phải mở editor dòng Costing rồi dùng đúng
  `#imgMaterialColorAdd`/`#imgMaterialSizeAdd`."
* "giữ card hiện tại, điền Search…, click `#btnShow`, chọn exact rồi `#btnAdd`.
  Nếu card chưa có giá trị thì dùng link Search and Add…; riêng Size được
  fallback sang card `Sample` rồi tìm lại."
* "Sau Add phải click Save…, xác nhận option đã xuất hiện lại trong editor
  Costing, và không xóa/đổi Color Card, Size Card hay mapping đang có."
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import FakeClock, patch_automation
from wfx_panel.automation.costing import variants
from wfx_panel.automation.costing.constants import (
    _MATERIAL_VARIANT_CARD_XPATH,
    _MATERIAL_VARIANT_CLOSE_XPATH,
    _MATERIAL_VARIANT_SAVE_XPATH,
    _MATERIAL_VARIANT_SEARCH_AND_ADD_XPATH,
    _MATERIAL_VARIANT_SEARCH_XPATH,
)

GRID_ID = "gridCostSheetDetail_tblGridContent"


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch):
    clock = FakeClock()
    patch_automation(monkeypatch, variants, "time", clock)
    monkeypatch.setattr(variants, "_sleep", clock.sleep)
    return clock


def _quiet():
    return lambda _line: None


# --- nhận diện field và khớp option --------------------------------------


@pytest.mark.parametrize(
    ("field_key", "kind"),
    [
        ("colMaterialColorList", "Color"),
        ("colMaterialSizeList", "Size"),
    ],
)
def test_material_variant_config_recognises_both_columns(field_key, kind):
    config = variants._material_variant_config({"field_key": field_key})

    assert config is not None
    assert config["kind"] == kind


def test_material_variant_config_ignores_any_other_column():
    assert variants._material_variant_config({"field_key": "colUsage"}) is None


@pytest.mark.parametrize(
    ("wanted", "option_label", "matches"),
    [
        ("Đỏ", "Đỏ", True),
        ("  đỏ  ", "Đỏ", True),
        ("Đỏ (RED)", "RED", True),
        ("Đỏ (RED)", "Đỏ (RED)", True),
        ("Đỏ", "Xanh", False),
        ("", "Đỏ", False),
    ],
)
def test_option_matching_accepts_label_code_or_name_with_code(
    wanted, option_label, matches
):
    option = {"label": option_label, "value": ""}

    assert variants._material_variant_option_matches(option, wanted) is matches


def test_option_matching_also_looks_at_the_option_value():
    option = {"label": "Không liên quan", "value": "RED"}

    assert variants._material_variant_option_matches(option, "Đỏ (RED)") is True


def test_tokens_of_a_blank_value_are_empty():
    assert variants._material_variant_tokens("   ") == set()


# --- dòng Costing và editor ----------------------------------------------


def _costing_frame(*, rows=2, editor_options=(), editor_visible=True, add=True):
    grid_rows = []
    for index in range(rows):
        children = [element("span", id="colMaterialColorList", text="Đỏ")]
        if index == 1:
            if editor_visible:
                children.append(
                    Element(
                        "select",
                        id="ddlMaterialColorList",
                        children=[
                            element("option", text=label, attrs={"value": value})
                            for label, value in editor_options
                        ],
                    )
                )
            if add:
                children.append(element("img", id="imgMaterialColorAdd"))
        grid_rows.append(Element("tr", css_class="cssGridRowDataRowType",
                                 children=children))
    grid = Element(
        "table", id=GRID_ID, children=[Element("tbody", children=grid_rows)]
    )
    return MiniFrame(Element("body", children=[grid]))


def _field(row_index=1, region="grid"):
    return {
        "field_key": "colMaterialColorList",
        "_live": {"row_index": row_index, "region": region},
    }


def test_costing_row_is_found_by_its_live_row_index():
    frame = _costing_frame()

    row = variants._costing_row_for_field(frame, _field())

    assert row.locator("#imgMaterialColorAdd").count() == 1


@pytest.mark.parametrize("field", [_field(region="editor"), _field(row_index=99)])
def test_costing_row_refuses_a_field_that_is_not_on_the_grid(field):
    frame = _costing_frame()

    with pytest.raises(RuntimeError, match="COSTING_MATERIAL_VARIANT_ROW_NOT_FOUND"):
        variants._costing_row_for_field(frame, field)


def test_costing_row_refuses_a_missing_grid():
    frame = MiniFrame(Element("body"))

    with pytest.raises(RuntimeError, match="COSTING_MATERIAL_VARIANT_ROW_NOT_FOUND"):
        variants._costing_row_for_field(frame, _field())


def test_opening_the_editor_clicks_the_cell_and_returns_the_select(monkeypatch):
    frame = _costing_frame(editor_options=[("Đỏ", "RED")])
    control = frame.locator("#colMaterialColorList").first
    monkeypatch.setattr(variants, "_resolve_live_field", lambda _f, _field: control)

    _row, editor = variants._open_material_variant_editor(
        frame,
        _field(),
        variants._material_variant_config(_field()),
    )

    assert control.node.clicks == 1
    assert editor.get_attribute("id") == "ddlMaterialColorList"


def test_opening_the_editor_reports_when_wfx_never_shows_it(monkeypatch):
    frame = _costing_frame(editor_visible=False)
    control = frame.locator("#colMaterialColorList").first
    monkeypatch.setattr(variants, "_resolve_live_field", lambda _f, _field: control)

    with pytest.raises(
        RuntimeError, match="COSTING_MATERIAL_VARIANT_EDITOR_NOT_FOUND"
    ):
        variants._open_material_variant_editor(
            frame, _field(), variants._material_variant_config(_field())
        )


def test_availability_is_true_for_a_column_that_is_not_a_variant(monkeypatch):
    frame = _costing_frame()

    assert (
        variants._material_variant_is_available(
            frame, {"field_key": "colUsage"}, "Đỏ"
        )
        is True
    )


def test_availability_reads_the_live_option_list_and_closes_the_editor(
    monkeypatch,
):
    frame = _costing_frame(editor_options=[("Đỏ", "RED"), ("Xanh", "BLU")])
    control = frame.locator("#colMaterialColorList").first
    monkeypatch.setattr(variants, "_resolve_live_field", lambda _f, _field: control)
    editor = frame.locator("#ddlMaterialColorList").node

    assert variants._material_variant_is_available(frame, _field(), "Đỏ") is True
    assert variants._material_variant_is_available(frame, _field(), "Tím") is False
    assert editor.keys == ["Tab", "Tab"]


# --- cửa sổ Article Color/Size List --------------------------------------


class _ListPage:
    def __init__(self, frames, *, closed=False):
        self.frames = list(frames)
        self._closed = closed

    def is_closed(self):
        return self._closed

    def close(self):
        self._closed = True


class _Context:
    def __init__(self, pages):
        self.pages = list(pages)


def _variant_list_frame(
    *,
    url="https://wfx.test/wfx_articlecolorlist.aspx",
    card_options=(),
    candidates=(),
    search=True,
    show=True,
    add=True,
    save=True,
    close=True,
    search_and_add=True,
):
    children = []
    if show:
        children.append(element("input", id="btnShow", attrs={"type": "button"}))
    if add:
        children.append(element("input", id="btnAdd", attrs={"type": "button"}))
    card = None
    if card_options:
        card = Element(
            "select",
            id="ddlCard",
            children=[
                element("option", text=label, attrs={"value": value})
                for label, value in card_options
            ],
        )
        children.append(card)
    search_input = None
    if search:
        search_input = element("input", id="txtSearch", attrs={"type": "text"})
        children.append(search_input)
    candidate_select = Element(
        "select",
        id="lstCandidates",
        attrs={"multiple": "multiple"},
        children=[
            element("option", text=label, attrs={"value": value})
            for label, value in candidates
        ],
    )
    children.append(candidate_select)
    save_link = element("a", id="save") if save else None
    close_link = element("a", id="close") if close else None
    add_link = element("a", id="search-and-add") if search_and_add else None
    for extra in (save_link, close_link, add_link):
        if extra is not None:
            children.append(extra)
    xpaths = {}
    if card is not None:
        xpaths[_MATERIAL_VARIANT_CARD_XPATH] = [
            Element("tr", children=[card])
        ]
    if search_input is not None:
        xpaths[_MATERIAL_VARIANT_SEARCH_XPATH] = [
            Element("tr", children=[search_input])
        ]
    if save_link is not None:
        xpaths[_MATERIAL_VARIANT_SAVE_XPATH] = [save_link]
    if close_link is not None:
        xpaths[_MATERIAL_VARIANT_CLOSE_XPATH] = [close_link]
    if add_link is not None:
        xpaths[_MATERIAL_VARIANT_SEARCH_AND_ADD_XPATH] = [add_link]
    for key in (
        _MATERIAL_VARIANT_CARD_XPATH,
        _MATERIAL_VARIANT_SEARCH_XPATH,
        _MATERIAL_VARIANT_SAVE_XPATH,
        _MATERIAL_VARIANT_CLOSE_XPATH,
        _MATERIAL_VARIANT_SEARCH_AND_ADD_XPATH,
    ):
        xpaths.setdefault(key, [])
    frame = MiniFrame(Element("body", children=children), url=url, xpaths=xpaths)
    frame.candidate_select = candidate_select
    frame.card = card
    frame.save_link = save_link
    frame.close_link = close_link
    frame.add_link = add_link
    frame.search_input = search_input
    return frame


COLOR_CONFIG = {
    "kind": "Color",
    "editor_id": "ddlMaterialColorList",
    "add_id": "imgMaterialColorAdd",
    "list_url": "wfx_articlecolorlist",
    "fallback_card": "",
}


def test_list_frame_prefers_a_window_that_was_not_open_before():
    old = _ListPage([_variant_list_frame()])
    new_frame = _variant_list_frame()
    new = _ListPage([new_frame])
    context = _Context([old, new])

    _page, frame = variants._material_variant_list_frame(
        context, COLOR_CONFIG, {id(old)}
    )

    assert frame is new_frame


def test_list_frame_times_out_when_no_window_qualifies():
    context = _Context([_ListPage([_variant_list_frame(show=False)])])

    with pytest.raises(PlaywrightTimeoutError):
        variants._material_variant_list_frame(
            context, COLOR_CONFIG, set(), timeout_seconds=0.3
        )


def test_list_frame_refuses_two_equally_good_candidates():
    page = _ListPage([_variant_list_frame(), _variant_list_frame()])
    context = _Context([page])

    with pytest.raises(PlaywrightTimeoutError):
        variants._material_variant_list_frame(
            context, COLOR_CONFIG, set(), timeout_seconds=0.3
        )


# --- card, ô tìm và danh sách kết quả ------------------------------------


def test_card_select_is_none_when_the_row_is_missing():
    frame = _variant_list_frame()

    assert variants._material_variant_card_select(frame) is None


def test_selecting_a_card_matches_by_label_or_value():
    frame = _variant_list_frame(card_options=[("Sample", "1"), ("Bulk", "2")])

    assert variants._select_material_variant_card(frame, " sample ") is True
    assert frame.card.selected == ["1"]


def test_selecting_an_unknown_card_is_refused():
    frame = _variant_list_frame(card_options=[("Sample", "1")])

    assert variants._select_material_variant_card(frame, "Không có") is False


def test_selecting_a_card_without_a_card_select_is_refused():
    frame = _variant_list_frame()

    assert variants._select_material_variant_card(frame, "Sample") is False


def test_search_input_is_reported_when_the_row_is_missing():
    frame = _variant_list_frame(search=False)

    with pytest.raises(
        RuntimeError, match="COSTING_MATERIAL_VARIANT_SEARCH_NOT_FOUND"
    ):
        variants._material_variant_search_input(frame)


def test_candidate_select_excludes_the_card_select():
    frame = _variant_list_frame(
        card_options=[("Sample", "1")], candidates=[("Đỏ", "RED")]
    )
    frame.card.attrs["multiple"] = "multiple"

    resolved = variants._material_variant_candidate_select(frame)

    assert resolved.node is frame.candidate_select


def test_candidate_select_refuses_an_ambiguous_list():
    frame = _variant_list_frame(candidates=[("Đỏ", "RED")])
    frame.root.append(
        Element("select", id="other", attrs={"multiple": "multiple"})
    )

    with pytest.raises(RuntimeError) as error:
        variants._material_variant_candidate_select(frame)

    assert "COSTING_MATERIAL_VARIANT_RESULTS_NOT_UNIQUE" in str(error.value)


# --- tìm và thêm ----------------------------------------------------------


def test_search_fills_the_box_clicks_show_and_filters_exactly():
    frame = _variant_list_frame(
        candidates=[("Đỏ (RED)", "RED"), ("Đỏ đậm (RED2)", "RED2")]
    )

    select, matches = variants._search_material_variant(frame, " RED ")

    assert select.node is frame.candidate_select
    assert [option["value"] for option in matches] == ["RED"]
    assert frame.search_input.fills == ["RED"]
    assert frame.locator("#btnShow").node.clicks == 1


def test_search_reports_a_missing_show_button():
    frame = _variant_list_frame(show=False)

    with pytest.raises(
        RuntimeError, match="COSTING_MATERIAL_VARIANT_SHOW_NOT_FOUND"
    ):
        variants._search_material_variant(frame, "Đỏ")


def test_choose_and_add_selects_then_confirms_the_value_left_the_list():
    frame = _variant_list_frame(candidates=[("Đỏ (RED)", "RED")])
    add = frame.locator("#btnAdd").node
    add.on_click = lambda _n: frame.candidate_select.children.clear()

    assert variants._choose_and_add_material_variant(frame, "Đỏ (RED)") is True
    assert frame.candidate_select.selected == ["RED"]


def test_choose_and_add_returns_false_when_nothing_matches():
    frame = _variant_list_frame(candidates=[("Xanh", "BLU")])

    assert variants._choose_and_add_material_variant(frame, "Đỏ") is False


def test_choose_and_add_refuses_two_matching_candidates():
    frame = _variant_list_frame(
        candidates=[("Đỏ (RED)", "RED"), ("Đỏ (RED)", "RED9")]
    )

    with pytest.raises(RuntimeError, match="COSTING_MATERIAL_VARIANT_AMBIGUOUS"):
        variants._choose_and_add_material_variant(frame, "Đỏ (RED)")


def test_choose_and_add_reports_when_wfx_never_removed_the_value():
    frame = _variant_list_frame(candidates=[("Đỏ (RED)", "RED")])

    with pytest.raises(
        RuntimeError, match="COSTING_MATERIAL_VARIANT_ADD_NOT_CONFIRMED"
    ):
        variants._choose_and_add_material_variant(frame, "Đỏ (RED)")


def test_choose_and_add_reports_a_missing_add_button():
    frame = _variant_list_frame(candidates=[("Đỏ (RED)", "RED")], add=False)

    with pytest.raises(
        RuntimeError, match="COSTING_MATERIAL_VARIANT_ADD_NOT_FOUND"
    ):
        variants._choose_and_add_material_variant(frame, "Đỏ (RED)")


# --- Save và đóng ---------------------------------------------------------


def test_save_clicks_the_toolbar_link():
    frame = _variant_list_frame()

    variants._save_material_variant_list(frame)

    assert frame.save_link.clicks == 1


def test_save_reports_a_missing_link():
    frame = _variant_list_frame(save=False)

    with pytest.raises(
        RuntimeError, match="COSTING_MATERIAL_VARIANT_SAVE_NOT_FOUND"
    ):
        variants._save_material_variant_list(frame)


def test_close_prefers_the_toolbar_close_over_closing_the_tab():
    frame = _variant_list_frame()
    page = _ListPage([frame])

    variants._close_material_variant_list(page, frame)

    assert frame.close_link.clicks == 1
    assert page.is_closed() is False


def test_close_falls_back_to_closing_the_tab():
    frame = _variant_list_frame(close=False)
    page = _ListPage([frame])

    variants._close_material_variant_list(page, frame)

    assert page.is_closed() is True


def test_close_does_nothing_for_an_already_closed_tab():
    frame = _variant_list_frame(close=False)
    page = _ListPage([frame], closed=True)

    variants._close_material_variant_list(page, frame)  # không raise


# --- Search and Add sang Color/Size Range --------------------------------


def test_search_and_add_opens_a_second_window_and_saves_there():
    list_frame = _variant_list_frame()
    list_page = _ListPage([list_frame])
    range_frame = _variant_list_frame(candidates=[("Đỏ (RED)", "RED")])
    range_page = _ListPage([range_frame])
    context = _Context([list_page])
    list_frame.add_link.on_click = lambda _n: context.pages.append(range_page)
    range_frame.locator("#btnAdd").node.on_click = (
        lambda _n: range_frame.candidate_select.children.clear()
    )

    variants._add_material_variant_to_card(
        context, list_page, list_frame, COLOR_CONFIG, "Đỏ (RED)"
    )

    assert range_frame.save_link.clicks == 1
    assert range_frame.close_link.clicks == 1


def test_search_and_add_reports_a_missing_link():
    list_frame = _variant_list_frame(search_and_add=False)
    list_page = _ListPage([list_frame])
    context = _Context([list_page])

    with pytest.raises(
        RuntimeError, match="COSTING_MATERIAL_VARIANT_SEARCH_ADD_NOT_FOUND"
    ):
        variants._add_material_variant_to_card(
            context, list_page, list_frame, COLOR_CONFIG, "Đỏ"
        )


def test_search_and_add_refuses_to_reuse_the_same_window():
    list_frame = _variant_list_frame()
    list_page = _ListPage([list_frame])
    context = _Context([list_page])

    with pytest.raises(
        RuntimeError, match="COSTING_MATERIAL_VARIANT_RANGE_NOT_OPENED"
    ):
        variants._add_material_variant_to_card(
            context, list_page, list_frame, COLOR_CONFIG, "Đỏ"
        )


def test_search_and_add_closes_the_range_window_even_when_it_fails():
    list_frame = _variant_list_frame()
    list_page = _ListPage([list_frame])
    range_frame = _variant_list_frame(candidates=[("Xanh", "BLU")])
    range_page = _ListPage([range_frame])
    context = _Context([list_page])
    list_frame.add_link.on_click = lambda _n: context.pages.append(range_page)

    with pytest.raises(RuntimeError, match="COSTING_MATERIAL_VARIANT_NOT_FOUND"):
        variants._add_material_variant_to_card(
            context, list_page, list_frame, COLOR_CONFIG, "Đỏ"
        )

    assert range_frame.close_link.clicks == 1


# --- luồng đầy đủ ---------------------------------------------------------


def _full_world(monkeypatch, *, editor_options, candidates, fallback_card=""):
    frame = _costing_frame(editor_options=editor_options)
    control = frame.locator("#colMaterialColorList").first
    monkeypatch.setattr(variants, "_resolve_live_field", lambda _f, _field: control)
    list_frame = _variant_list_frame(candidates=candidates)
    list_page = _ListPage([list_frame])
    context = _Context([])
    add_icon = frame.locator("#imgMaterialColorAdd").node
    add_icon.on_click = lambda _n: context.pages.append(list_page)
    list_frame.locator("#btnAdd").node.on_click = (
        lambda _n: list_frame.candidate_select.children.clear()
    )
    return frame, context, list_frame, list_page


def test_nothing_is_added_when_the_value_is_already_an_option(monkeypatch):
    frame, context, _list_frame, _list_page = _full_world(
        monkeypatch, editor_options=[("Đỏ", "RED")], candidates=[]
    )

    assert (
        variants._add_missing_material_variant(
            context, frame, _field(), "Đỏ", _quiet()
        )
        is False
    )
    assert context.pages == []


def test_a_non_variant_column_is_left_alone(monkeypatch):
    frame = _costing_frame()

    assert (
        variants._add_missing_material_variant(
            _Context([]), frame, {"field_key": "colUsage"}, "Đỏ", _quiet()
        )
        is False
    )


def test_a_missing_value_is_added_then_confirmed_back_in_the_editor(monkeypatch):
    frame, context, list_frame, _list_page = _full_world(
        monkeypatch, editor_options=[], candidates=[("Đỏ (RED)", "RED")]
    )
    editor = frame.locator("#ddlMaterialColorList").node

    # Sau khi Save, WFX nạp lại option của Article vào editor Costing.
    list_frame.save_link.on_click = lambda _n: editor.append(
        element("option", text="Đỏ (RED)", attrs={"value": "RED"})
    )
    logs: list[str] = []

    assert (
        variants._add_missing_material_variant(
            context, frame, _field(), "Đỏ (RED)", logs.append
        )
        is True
    )
    assert any("Đã bổ sung Color" in line for line in logs)
    assert list_frame.close_link.clicks == 1


def test_the_flow_fails_loudly_when_wfx_does_not_refresh_the_editor(monkeypatch):
    frame, context, _list_frame, _list_page = _full_world(
        monkeypatch, editor_options=[], candidates=[("Đỏ (RED)", "RED")]
    )

    with pytest.raises(
        RuntimeError, match="COSTING_MATERIAL_VARIANT_REFRESH_NOT_CONFIRMED"
    ):
        variants._add_missing_material_variant(
            context, frame, _field(), "Đỏ (RED)", _quiet()
        )


def test_the_flow_reports_a_missing_add_icon(monkeypatch):
    frame = _costing_frame(editor_options=[], add=False)
    control = frame.locator("#colMaterialColorList").first
    monkeypatch.setattr(variants, "_resolve_live_field", lambda _f, _field: control)

    with pytest.raises(
        RuntimeError, match="COSTING_MATERIAL_VARIANT_BUTTON_NOT_FOUND"
    ):
        variants._add_missing_material_variant(
            _Context([]), frame, _field(), "Đỏ", _quiet()
        )


def test_size_falls_back_to_the_sample_card_before_giving_up(monkeypatch):
    """CLAUDE.md: riêng Size được fallback sang card `Sample` rồi tìm lại."""
    size_config = dict(COLOR_CONFIG, kind="Size", fallback_card="Sample")
    monkeypatch.setattr(
        variants, "_material_variant_config", lambda _field: size_config
    )
    frame = _costing_frame(editor_options=[])
    control = frame.locator("#colMaterialColorList").first
    monkeypatch.setattr(variants, "_resolve_live_field", lambda _f, _field: control)
    list_frame = _variant_list_frame(card_options=[("Sample", "1")])
    list_page = _ListPage([list_frame])
    context = _Context([])
    frame.locator("#imgMaterialColorAdd").node.on_click = (
        lambda _n: context.pages.append(list_page)
    )
    editor = frame.locator("#ddlMaterialColorList").node

    def after_card(_node, value):
        list_frame.candidate_select.append(
            element("option", text="XL", attrs={"value": "XL"})
        )

    list_frame.card.on_fill = after_card
    original_select = variants._select_material_variant_card

    def select_card(list_frame_arg, card_name):
        picked = original_select(list_frame_arg, card_name)
        if picked:
            list_frame.candidate_select.append(
                element("option", text="XL", attrs={"value": "XL"})
            )
        return picked

    monkeypatch.setattr(variants, "_select_material_variant_card", select_card)
    list_frame.locator("#btnAdd").node.on_click = (
        lambda _n: list_frame.candidate_select.children.clear()
    )
    list_frame.save_link.on_click = lambda _n: editor.append(
        element("option", text="XL", attrs={"value": "XL"})
    )

    assert (
        variants._add_missing_material_variant(
            context, frame, _field(), "XL", _quiet()
        )
        is True
    )
    assert list_frame.card.selected == ["1"]


def test_close_inline_editor_is_safe_on_a_detached_control():
    class Broken:
        def count(self):
            raise PlaywrightError("editor đã rơi")

    variants._close_inline_editor(Broken())  # không raise
