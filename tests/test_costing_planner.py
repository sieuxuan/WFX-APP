import pytest

from wfx_panel.costing_planner import (
    CostingPlanError,
    build_costing_plan,
    live_signature,
)
from wfx_panel.costing_workbook import FORMAT_VERSION


def documents():
    live = {
        "format_version": FORMAT_VERSION,
        "style_code": "SWN0000001",
        "title": "Current",
        "cost_sheet_status": "Open",
        "sections": [
            {"section_key": "fabric", "name": "Fabric", "row_order": 1}
        ],
        "items": [
            {
                "section_key": "fabric",
                "section_name": "Fabric",
                "item_key": "live-1",
                "row_order": 1,
                "action": "UPSERT",
                "article_code": "FAB-001",
                "article_name": "Jersey",
            },
            {
                "section_key": "fabric",
                "section_name": "Fabric",
                "item_key": "live-9",
                "row_order": 9,
                "action": "UPSERT",
                "article_code": "FAB-DELETE",
                "article_name": "Delete Me",
            },
        ],
        "fields": [
            {
                "scope": "cost_sheet",
                "section_key": "",
                "item_key": "",
                "field_key": "title",
                "label": "Title",
                "value": "Current",
                "data_type": "text",
                "editable": True,
                "required": True,
                "row_order": 1,
            },
            {
                "scope": "item",
                "section_key": "fabric",
                "item_key": "live-1",
                "field_key": "consumption",
                "label": "Consumption",
                "value": 1.25,
                "data_type": "number",
                "editable": True,
                "required": True,
                "row_order": 1,
            },
            {
                "scope": "item",
                "section_key": "fabric",
                "item_key": "live-1",
                "field_key": "minutes",
                "label": "Minutes",
                "value": 0,
                "data_type": "number",
                "editable": True,
                "required": False,
                "row_order": 2,
            },
        ],
    }
    imported = {
        **live,
        "title": "Edited",
        "items": [
            {
                **live["items"][0],
                "item_key": "exported-1",
            },
            {
                "section_key": "fabric",
                "section_name": "Fabric",
                "item_key": "new-2",
                "row_order": 2,
                "action": "UPSERT",
                "article_code": "FAB-002",
                "article_name": "Rib",
            },
            {
                **live["items"][1],
                "action": "DELETE",
            },
        ],
        "fields": [
            {**live["fields"][0], "value": "Edited"},
            {
                **live["fields"][1],
                "item_key": "exported-1",
                "value": 2.5,
            },
            {
                **live["fields"][2],
                "item_key": "exported-1",
                "value": "",
            },
            {
                **live["fields"][1],
                "item_key": "new-2",
                "value": 0.75,
            },
        ],
    }
    return imported, live


def test_plan_classifies_updates_additions_deletes_and_minutes():
    imported, live = documents()

    plan = build_costing_plan(imported, live)

    assert plan["code"] == "COSTING_DRY_RUN_READY"
    assert plan["new_required"] is False
    assert [item["article_code"] for item in plan["additions"]] == ["FAB-002"]
    assert [item["article_code"] for item in plan["updates"]] == ["FAB-001"]
    assert [item["article_code"] for item in plan["deletes"]] == ["FAB-DELETE"]
    assert plan["article_searches"][0]["article_code"] == "FAB-002"
    changed = {
        (field["field_key"], field["item_key"]): field["value"]
        for field in plan["fields_to_set"]
    }
    assert changed[("title", "")] == "Edited"
    assert changed[("consumption", "live-1")] == 2.5
    assert changed[("minutes", "live-1")] == 1
    assert changed[("consumption", "new-2")] == 0.75


def test_plan_round_trips_structured_color_mapping_field():
    _imported, live = documents()
    live_mapping = {
        "scope": "item",
        "section_key": "fabric",
        "item_key": "live-1",
        "field_key": "colColorDependencyMapping",
        "label": "Color Mapping",
        "value": "BLACK (BLACK) => BLACK(BLACK)",
        "data_type": "text",
        "editable": True,
        "required": False,
        "row_order": 3,
    }
    live["fields"].append(live_mapping)
    imported = {
        **live,
        "items": [dict(item) for item in live["items"]],
        "fields": [dict(field) for field in live["fields"]],
    }
    imported["fields"][-1]["value"] = (
        "BLACK (BLACK) => BLACK(BLACK) | WHITE(WHITE)"
    )

    plan = build_costing_plan(imported, live)

    change = next(
        field
        for field in plan["fields_to_set"]
        if field["field_key"] == "colColorDependencyMapping"
    )
    assert "WHITE(WHITE)" in change["value"]


def test_blank_value_is_unchanged_and_clear_marker_is_explicit():
    imported, live = documents()
    imported["fields"][0]["value"] = ""
    imported["fields"][1]["value"] = "__CLEAR__"

    plan = build_costing_plan(imported, live)

    assert not any(
        field["field_key"] == "title" for field in plan["fields_to_set"]
    )
    cleared = next(
        field
        for field in plan["fields_to_set"]
        if field["field_key"] == "consumption"
        and field["item_key"] == "live-1"
    )
    assert cleared["value"] == ""


def test_style_mismatch_is_blocked():
    imported, live = documents()
    imported["style_code"] = "OTHER"
    with pytest.raises(CostingPlanError) as captured:
        build_costing_plan(imported, live)
    assert captured.value.code == "COSTING_STYLE_MISMATCH"


@pytest.mark.parametrize("status", ["", "Approved", "Closed", "Not Created"])
def test_every_non_open_status_is_blocked_until_user_creates_open_costing(
    status,
):
    imported, live = documents()
    live["cost_sheet_status"] = status
    live["sections"] = []
    live["items"] = []
    live["fields"] = []

    with pytest.raises(CostingPlanError) as captured:
        build_costing_plan(imported, live)

    assert captured.value.code == "COSTING_NOT_OPEN"


def test_boolean_comparison_only_updates_when_truth_value_differs():
    imported, live = documents()
    live["fields"].append(
        {
            "scope": "cost_sheet",
            "section_key": "",
            "item_key": "",
            "field_key": "include_wastage",
            "label": "Include Wastage",
            "value": "true",
            "data_type": "boolean",
            "editable": True,
            "required": False,
            "row_order": 3,
        }
    )
    imported["fields"].append(
        {
            **live["fields"][-1],
            "value": "yes",
        }
    )

    plan = build_costing_plan(imported, live)

    assert not any(
        field["field_key"] == "include_wastage"
        for field in plan["fields_to_set"]
    )


def test_live_signature_changes_with_costing_values():
    _imported, live = documents()
    before = live_signature(live)
    live["fields"][0]["value"] = "Changed"
    after = live_signature(live)

    assert before != after


def _multi_row_article_documents():
    imported, live = documents()
    first_key = "F0000585::117001::1"
    second_key = "F0000585::117002::2"
    live["items"] = [
        {
            "section_key": "fabric",
            "section_name": "Fabric",
            "item_key": first_key,
            "row_order": 1,
            "action": "UPSERT",
            "item_type": "article",
            "article_code": "F0000585",
            "article_name": "Shell Fabric",
        },
        {
            "section_key": "fabric",
            "section_name": "Fabric",
            "item_key": second_key,
            "row_order": 2,
            "action": "UPSERT",
            "item_type": "article",
            "article_code": "F0000585",
            "article_name": "Shell Fabric",
        },
    ]
    live["fields"] = [
        {
            "scope": "item",
            "section_key": "fabric",
            "item_key": first_key,
            "field_key": "colConsQty",
            "label": "Cons. Qty.",
            "value": 1.2,
            "data_type": "number",
            "editable": True,
            "required": False,
            "row_order": 1,
        },
        {
            "scope": "item",
            "section_key": "fabric",
            "item_key": second_key,
            "field_key": "colMaterialColorList",
            "label": "Material Color",
            "value": "OLD COLOR",
            "data_type": "text",
            "editable": True,
            "required": False,
            "row_order": 2,
        },
    ]
    imported = {
        **live,
        "items": [dict(item) for item in live["items"]],
        "fields": [dict(field) for field in live["fields"]],
    }
    return imported, live, first_key, second_key


def test_multi_row_article_uses_exact_exported_row_key():
    imported, live, first_key, _second_key = _multi_row_article_documents()
    imported["fields"][0]["value"] = 2.4

    plan = build_costing_plan(imported, live)

    changed = next(
        field
        for field in plan["fields_to_set"]
        if field["field_key"] == "colConsQty"
    )
    assert changed["item_key"] == first_key


def test_legacy_merged_article_maps_each_field_to_the_row_containing_it():
    imported, live, first_key, second_key = _multi_row_article_documents()
    imported["items"] = [
        {
            **live["items"][0],
            "item_key": "F0000585",
        }
    ]
    imported["fields"] = [
        {
            **live["fields"][0],
            "item_key": "F0000585",
            "value": 2.4,
        },
        {
            **live["fields"][1],
            "item_key": "F0000585",
            "value": "JL NAVY(19-3922-TCX)",
        },
    ]

    plan = build_costing_plan(imported, live)

    changed = {
        field["field_key"]: field["item_key"]
        for field in plan["fields_to_set"]
    }
    assert changed == {
        "colConsQty": first_key,
        "colMaterialColorList": second_key,
    }


def test_adjacent_duplicate_article_requests_one_splitter_row():
    imported, live = documents()
    imported["items"] = [
        dict(live["items"][0]),
        {
            **live["items"][0],
            "item_key": "new:fabric:FAB-001:row-3",
            "row_order": 2,
        },
    ]
    imported["fields"] = [
        {
            **live["fields"][1],
            "item_key": "live-1",
            "value": 1.5,
        },
        {
            **live["fields"][1],
            "item_key": "new:fabric:FAB-001:row-3",
            "value": 2.5,
        },
    ]

    plan = build_costing_plan(imported, live)

    assert plan["additions"] == []
    assert len(plan["splits"]) == 1
    assert plan["splits"][0]["article_code"] == "FAB-001"
    assert plan["splits"][0]["occurrence"] == 2
    assert plan["counts"]["splits"] == 1


def test_new_duplicate_article_is_added_once_then_split():
    imported, live = documents()
    imported["items"] = [
        {
            "section_key": "fabric",
            "section_name": "Fabric",
            "item_key": f"new-{index}",
            "row_order": index,
            "action": "UPSERT",
            "item_type": "article",
            "article_code": "FAB-NEW",
            "article_name": "New Fabric",
        }
        for index in (1, 2)
    ]
    imported["fields"] = []

    plan = build_costing_plan(imported, live)

    assert [item["article_code"] for item in plan["additions"]] == ["FAB-NEW"]
    assert [item["article_code"] for item in plan["splits"]] == ["FAB-NEW"]


def test_missing_cost_line_is_planned_as_special_addition():
    imported, live = documents()
    section = {
        "section_key": "production",
        "name": "Production Costs",
        "row_order": 8,
    }
    live["sections"].append(section)
    imported["items"] = [
        {
            "section_key": "production",
            "section_name": "Production Costs",
            "item_key": "new:production:CM:row-20",
            "row_order": 20,
            "action": "UPSERT",
            "item_type": "cost_line",
            "article_code": "",
            "article_name": "CM (PRODUCTIONPROCESS100001)",
        }
    ]
    imported["fields"] = [
        {
            "scope": "item",
            "section_key": "production",
            "item_key": "new:production:CM:row-20",
            "field_key": key,
            "label": label,
            "value": value,
            "data_type": "number",
            "editable": True,
            "required": False,
            "row_order": index,
        }
        for index, (key, label, value) in enumerate(
            [
                ("ProductionHeaderMinutes", "Minutes", 1),
                ("Minutes", "Minutes", 1),
                ("ProductionValue", "Value", 100),
                ("colRate1", "Rate", 2),
            ]
        )
    ]

    plan = build_costing_plan(imported, live)

    assert plan["additions"] == []
    assert len(plan["cost_line_additions"]) == 1
    assert plan["cost_line_additions"][0]["article_name"].startswith("CM (")
    assert plan["counts"]["cost_line_additions"] == 1
    assert {field["field_key"] for field in plan["fields_to_set"]} == {
        "ProductionHeaderMinutes",
        "Minutes",
        "ProductionValue",
        "colRate1",
    }


def test_missing_mandatory_purchase_officer_is_blocked_during_dry_run():
    imported, live = documents()
    live["fields"].append(
        {
            "scope": "item",
            "section_key": "fabric",
            "item_key": "live-1",
            "field_key": "colPurchaseOfficer",
            "label": "Purchase Officer",
            "value": "",
            "data_type": "text",
            "editable": True,
            "required": True,
            "row_order": 3,
        }
    )
    imported["items"] = [dict(live["items"][0])]
    imported["fields"] = []

    with pytest.raises(CostingPlanError) as captured:
        build_costing_plan(imported, live)

    assert captured.value.code == "COSTING_REQUIRED_FIELD_MISSING"
    assert captured.value.data["missing_required_fields"][0][
        "field_key"
    ] == "colPurchaseOfficer"
