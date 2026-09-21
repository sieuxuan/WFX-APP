"""Quét Costing sống thành document: option Article, Color/Size và dependency.

`wfx_panel/automation/costing/inventory.py` ở mức 40%: phần dựng document đã có
test, phần chạm DOM thì chưa. CLAUDE.md đặt luật ngay ở phần chưa chạy:

* "Ba danh sách dùng chung của CM Costs/Production Costs/Indirect Costs chỉ
  scan một lần trong 7 ngày" — nên lượt scan phải để lại grid *y như cũ*: dòng
  tạm được xóa, các checkbox đang tick được trả lại đúng trạng thái.
* "Export phải scan Material Color/Size theo từng Article và nội dung popup
  Dependency Table."
* "Detail rỗng không được tự suy diễn là Open" — status là điều kiện bật/tắt
  Import và Apply.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError

from tests.fakes.mini_dom import Element, MiniFrame, element
from tests.fakes.wfx_dom import FakeClock, patch_automation
from wfx_panel.automation.costing import inventory

GRID_ID = "gridCostSheetDetail_tblGridContent"


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch):
    clock = FakeClock()
    patch_automation(monkeypatch, inventory, "time", clock)
    monkeypatch.setattr(inventory, "_sleep", clock.sleep)
    return clock


def _quiet():
    return lambda _line: None


# --- field mapping cho popup Dependency ----------------------------------


def _dependency_field(kind="Color", value="[Table]", scope="item"):
    return {
        "scope": scope,
        "section_key": "section-1-fabric",
        "item_key": "item-1",
        "field_key": f"col{kind}Dependency",
        "value": value,
        "row_order": 3,
        "_live": {"row_index": 1, "region": "grid"},
    }


def test_a_mapping_field_is_added_beside_every_dependency_column():
    document = {"fields": [_dependency_field("Color"), _dependency_field("Size")]}

    inventory._ensure_dependency_mapping_fields(document)

    added = [
        field
        for field in document["fields"]
        if field["field_key"].endswith("DependencyMapping")
    ]
    assert [field["label"] for field in added] == ["Color Mapping", "Size Mapping"]
    assert added[0]["_live"]["dependency_kind"] == "Color"
    assert added[0]["_live"]["dependency_mode"] == "[Table]"
    assert added[0]["row_order"] == 3


def test_a_mapping_field_is_never_added_twice():
    document = {"fields": [_dependency_field()]}

    inventory._ensure_dependency_mapping_fields(document)
    inventory._ensure_dependency_mapping_fields(document)

    assert len(document["fields"]) == 2


def test_a_section_level_dependency_never_gets_a_mapping_field():
    document = {"fields": [_dependency_field(scope="section")]}

    inventory._ensure_dependency_mapping_fields(document)

    assert len(document["fields"]) == 1


def test_a_column_that_is_not_a_dependency_is_left_alone():
    document = {"fields": [dict(_dependency_field(), field_key="colUsage")]}

    inventory._ensure_dependency_mapping_fields(document)

    assert len(document["fields"]) == 1


# --- option Material Color/Size ------------------------------------------


def _item_field(kind="Color", row_index=1):
    return {
        "scope": "item",
        "section_key": "section-1-fabric",
        "item_key": "item-1",
        "field_key": f"colMaterial{kind}List",
        "value": "",
        "options": [],
        "_live": {"row_index": row_index},
    }


def _options_frame(results):
    frame = MiniFrame(Element("body"))
    frame.requests: list[list[dict]] = []

    def read(requests):
        frame.requests.append([dict(item) for item in requests])
        if isinstance(results, Exception):
            raise results
        return results

    frame.scripts = {"GetBindDDLData": read}
    return frame


def test_item_options_are_read_in_one_call_per_document():
    frame = _options_frame(
        [
            {
                "row_index": 1,
                "kind": "Color",
                "options": ["Đỏ (RED)", " ", "Đỏ (RED)"],
                "values": ["RED", "", "RED"],
            }
        ]
    )
    document = {"fields": [_item_field()]}

    inventory._scan_costing_item_options(frame, document)

    field = document["fields"][0]
    assert field["options"] == ["Đỏ (RED)"]
    assert field["_live"]["option_values"] == ["RED", "", "RED"]
    assert frame.requests == [[{"row_index": 1, "kind": "Color"}]]


def test_a_document_without_any_color_or_size_column_never_calls_the_browser():
    frame = _options_frame([])
    document = {"fields": [dict(_item_field(), field_key="colUsage")]}

    inventory._scan_costing_item_options(frame, document)

    assert frame.requests == []


def test_a_browser_failure_leaves_the_options_untouched():
    frame = _options_frame(PlaywrightError("WFX chưa nạp GetBindDDLData"))
    document = {"fields": [_item_field()]}

    inventory._scan_costing_item_options(frame, document)

    assert document["fields"][0]["options"] == []


def test_a_row_the_browser_did_not_answer_for_keeps_its_options():
    frame = _options_frame([{"row_index": 9, "kind": "Color", "options": ["X"]}])
    document = {"fields": [_item_field(row_index=1)]}

    inventory._scan_costing_item_options(frame, document)

    assert document["fields"][0]["options"] == []


def test_both_color_and_size_columns_are_requested():
    frame = _options_frame([])
    document = {"fields": [_item_field("Color"), _item_field("Size", row_index=2)]}

    inventory._scan_costing_item_options(frame, document)

    assert frame.requests == [
        [{"row_index": 1, "kind": "Color"}, {"row_index": 2, "kind": "Size"}]
    ]


# --- option của ba block chi phí đặc biệt --------------------------------


class _Checkbox(Element):
    def __init__(self, value, checked=False):
        super().__init__(
            "input",
            id="chkSelector",
            attrs={"type": "checkbox", "value": value},
            checked=checked,
        )


def _special_world(
    *,
    existing=(("1001", False),),
    options=("Nhà máy A", "Nhà máy B"),
    add_row=True,
    header=True,
):
    """Block Indirect Costs: header + các dòng sẵn có; Add tạo dòng tạm."""
    header_children = [element("span", id="lblBOMCodeTranslated", text="Indirect")]
    if header:
        header_children.append(element("img", id="imgAdd"))
        header_children.append(element("img", id="imgDelete"))
    header_row = Element(
        "tr", css_class="cssGridRowICHeaderRowType", children=header_children
    )
    rows = [
        Element(
            "tr",
            css_class="cssGridRowICDataRowType",
            children=[_Checkbox(value, checked)],
        )
        for value, checked in existing
    ]
    body = Element("tbody", children=[header_row, *rows])
    grid = Element("table", id=GRID_ID, children=[body])
    frame = MiniFrame(Element("body", children=[grid]))

    if add_row and header:
        def add(_node):
            body.append(
                Element(
                    "tr",
                    css_class="cssGridRowICDataRowType",
                    children=[
                        _Checkbox("-1001"),
                        element("span", id="lblTitle"),
                        Element(
                            "select",
                            id="ddlTitle",
                            children=[
                                element("option", text=label)
                                for label in ("[Select]", *options)
                            ],
                        ),
                    ],
                )
            )

        frame.locator("#imgAdd").node.on_click = add
    frame.body = body
    return frame


def _section(name="Indirect Costs"):
    return {"section_key": "section-1-Indirect_Costs", "name": name}


def test_the_option_list_of_a_special_block_is_read_from_a_temporary_row():
    frame = _special_world()

    options = inventory._special_section_options(frame, _section())

    assert options == ["Nhà máy A", "Nhà máy B"]


def test_the_temporary_row_is_deleted_again_so_the_grid_is_unchanged():
    frame = _special_world()
    delete = frame.locator("#imgDelete").node
    delete.on_click = lambda _n: frame.body.children.pop()

    inventory._special_section_options(frame, _section())

    assert delete.clicks == 1
    assert len(frame.body.children) == 2


def test_rows_the_user_had_ticked_are_ticked_again_afterwards():
    """Lượt scan không được đổi selection mà người dùng đang có."""
    frame = _special_world(existing=(("1001", True), ("1002", False)))
    delete = frame.locator("#imgDelete").node
    delete.on_click = lambda _n: frame.body.children.pop()

    inventory._special_section_options(frame, _section())

    rows = frame.locator(f"#{GRID_ID}").locator(":scope > tbody > tr")
    assert rows.nth(1).locator("#chkSelector").node.checked is True
    assert rows.nth(2).locator("#chkSelector").node.checked is False


def test_a_section_that_is_not_one_of_the_three_blocks_is_skipped():
    frame = _special_world()

    assert inventory._special_section_options(
        frame, {"section_key": "section-1-fabric", "name": "Fabric"}
    ) == []


def test_a_block_without_a_visible_add_button_is_skipped():
    frame = _special_world(header=False)

    assert inventory._special_section_options(frame, _section()) == []


def test_a_block_where_wfx_never_adds_a_row_is_reported():
    frame = _special_world(add_row=False)

    with pytest.raises(RuntimeError, match="COSTING_SPECIAL_OPTION_ROW_NOT_FOUND"):
        inventory._special_section_options(frame, _section())


def test_placeholder_options_are_dropped():
    frame = _special_world(options=("[ALL]", "Nhà máy A"))

    assert inventory._special_section_options(frame, _section()) == ["Nhà máy A"]


def test_the_scan_writes_options_onto_the_sections_that_have_them(monkeypatch):
    frame = _special_world()
    document = {
        "sections": [_section(), {"section_key": "section-2-fabric", "name": "Fabric"}]
    }

    inventory._scan_special_cost_options(frame, document)

    assert document["sections"][0]["article_options"] == [
        "Nhà máy A",
        "Nhà máy B",
    ]
    assert "article_options" not in document["sections"][1]


# --- dựng document từ grid sống ------------------------------------------


def _live_frame(payload, *, grid=True):
    children = []
    if grid:
        children.append(
            Element(
                "table",
                id=GRID_ID,
                children=[Element("tbody")],
                scripts={"sections": lambda _a: dict(payload)},
            )
        )
    return MiniFrame(Element("body", children=children))


def _payload(**overrides) -> dict:
    base = {"title": "", "sections": [], "items": [], "fields": []}
    base.update(overrides)
    return base


def test_a_costing_without_a_grid_becomes_an_empty_document():
    document = inventory._inventory_costing_frame(
        _live_frame(_payload(), grid=False),
        "ABC123",
        style_name="Áo khoác",
    )

    assert document["style_code"] == "ABC123"
    assert document["style_name"] == "Áo khoác"
    assert document["sections"] == []
    assert document["fields"] == []


def test_an_empty_detail_is_never_assumed_to_be_open():
    """CLAUDE.md: detail rỗng không được tự suy diễn là Open."""
    document = inventory._inventory_costing_frame(
        _live_frame(_payload()), "ABC123"
    )

    assert document["cost_sheet_status"] == ""


def test_a_detail_with_real_data_is_treated_as_an_open_costing():
    payload = _payload(sections=[{"section_key": "s1", "name": "Fabric"}])

    document = inventory._inventory_costing_frame(
        _live_frame(payload), "ABC123"
    )

    assert document["cost_sheet_status"] == "Open"


def test_a_status_the_caller_already_knows_is_never_overwritten():
    payload = _payload(sections=[{"section_key": "s1", "name": "Fabric"}])

    document = inventory._inventory_costing_frame(
        _live_frame(payload), "ABC123", costing_status="Approved"
    )

    assert document["cost_sheet_status"] == "Approved"


def test_the_document_always_carries_a_signature():
    document = inventory._inventory_costing_frame(
        _live_frame(_payload()), "ABC123"
    )

    assert document["signature"]


def test_a_light_scan_never_touches_the_grid(monkeypatch):
    calls: list[str] = []
    for name in (
        "_scan_special_cost_options",
        "_scan_costing_item_options",
        "_scan_costing_dependency_tables",
        "_scan_costing_article_dropdowns",
    ):
        monkeypatch.setattr(
            inventory, name, lambda *a, **kw: calls.append("scan")
        )

    inventory._inventory_costing_frame(_live_frame(_payload()), "ABC123")

    assert calls == []
    assert "special_cost_options_scanned" not in inventory._inventory_costing_frame(
        _live_frame(_payload()), "ABC123"
    )


def test_a_full_scan_runs_every_scanner_and_marks_the_snapshot(monkeypatch):
    order: list[str] = []
    for name in (
        "_scan_special_cost_options",
        "_scan_costing_item_options",
        "_scan_costing_dependency_tables",
    ):
        monkeypatch.setattr(
            inventory, name, lambda *a, _name=name, **kw: order.append(_name)
        )
    monkeypatch.setattr(
        inventory, "_dependency_scan_incomplete", lambda _document: False
    )

    document = inventory._inventory_costing_frame(
        _live_frame(_payload()), "ABC123", scan_details=True
    )

    assert order == [
        "_scan_special_cost_options",
        "_scan_costing_item_options",
        "_scan_costing_dependency_tables",
    ]
    assert document["special_cost_options_scanned"] is True


def test_the_cost_option_scan_can_be_skipped_without_skipping_the_others(
    monkeypatch,
):
    """Cache 7 ngày bỏ qua scan chi phí, nhưng Color/Size vẫn phải chạy."""
    order: list[str] = []
    for name in (
        "_scan_special_cost_options",
        "_scan_costing_item_options",
        "_scan_costing_dependency_tables",
    ):
        monkeypatch.setattr(
            inventory, name, lambda *a, _name=name, **kw: order.append(_name)
        )
    monkeypatch.setattr(
        inventory, "_dependency_scan_incomplete", lambda _document: False
    )

    document = inventory._inventory_costing_frame(
        _live_frame(_payload()),
        "ABC123",
        scan_details=True,
        scan_special_cost_options=False,
    )

    assert order == ["_scan_costing_item_options", "_scan_costing_dependency_tables"]
    assert "special_cost_options_scanned" not in document


def test_an_incomplete_dependency_scan_fails_the_whole_export(monkeypatch):
    for name in (
        "_scan_special_cost_options",
        "_scan_costing_item_options",
        "_scan_costing_dependency_tables",
    ):
        monkeypatch.setattr(inventory, name, lambda *a, **kw: None)
    monkeypatch.setattr(
        inventory, "_dependency_scan_incomplete", lambda _document: True
    )

    with pytest.raises(RuntimeError, match="COSTING_DEPENDENCY_SCAN_INCOMPLETE"):
        inventory._inventory_costing_frame(
            _live_frame(_payload()), "ABC123", scan_details=True
        )


def test_the_article_dropdown_scan_is_opt_in(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        inventory,
        "_scan_costing_article_dropdowns",
        lambda *a, **kw: calls.append("dropdown"),
    )

    inventory._inventory_costing_frame(
        _live_frame(_payload()), "ABC123", scan_article_options=True
    )

    assert calls == ["dropdown"]
