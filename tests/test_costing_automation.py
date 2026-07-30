from pathlib import Path

from wfx_panel.automation import costing


def test_style_name_comes_from_article_name_value_after_slash():
    control = type(
        "Control",
        (),
        {
            "get_attribute": lambda self, name: (
                "BDG-KFSWPKN-S200 LN-FANCY BIRDDOGS SHORTS-UNLINED-FW25"
                "(SWN0000001/KFSWPKN-S200 LN)"
                if name == "title"
                else ""
            ),
            "inner_text": lambda self, timeout=0: "",
        },
    )()
    locator = type(
        "Locator",
        (),
        {"count": lambda self: 1, "nth": lambda self, index: control},
    )()
    frame = type("Frame", (), {"locator": lambda self, selector: locator})()
    page = type("Page", (), {"frames": [frame]})()

    assert costing._style_name_from_page(page) == "KFSWPKN-S200 LN"
    assert costing._article_code_from_page(page) == "SWN0000001"


def test_dependency_mapping_parser_supports_per_material_lines():
    rules = costing._dependency_mapping_rules(
        "BLACK(BLACK) => BLACK(BLACK) | WHITE(WHITE)\nNAVY(NAVY) => NAVY(NAVY)"
    )

    assert rules == [
        ("BLACK(BLACK)", ["BLACK(BLACK)", "WHITE(WHITE)"]),
        ("NAVY(NAVY)", ["NAVY(NAVY)"]),
    ]
    assert costing._dependency_match_tokens("BLACK (BLACK)") & (
        costing._dependency_match_tokens("BLACK(BLACK)")
    )


def test_dependency_option_indexes_match_codes_or_labels():
    options = [
        {"index": 0, "label": "Black", "code": "BLK"},
        {"index": 1, "label": "White", "code": "WHT"},
        {"index": 2, "label": "Navy", "code": "NVY"},
    ]

    assert costing._dependency_option_indexes(options, ["BLK", "White"]) == {
        0,
        1,
    }


def test_dependency_rule_matching_rejects_multiple_source_rules():
    rules = [
        ("BLACK(BLK)", ["White"]),
        ("BLK", ["Navy"]),
    ]

    try:
        costing._matching_dependency_rule("BLACK (BLK)", rules)
    except RuntimeError as error:
        assert str(error) == "COSTING_DEPENDENCY_SOURCE_AMBIGUOUS"
    else:
        raise AssertionError("Expected an ambiguous dependency source")


def test_inventory_builds_sections_items_and_stable_duplicate_field_keys():
    document = costing._inventory_to_document(
        {
            "title": "FOB Main",
            "sections": [
                {"sectionKey": "sectionFabric", "name": "Fabric", "rowOrder": 1}
            ],
            "fields": [
                {
                    "domIndex": 0,
                    "domId": "lblTitle",
                    "label": "Title",
                    "value": "FOB Main",
                    "editable": True,
                    "dataType": "text",
                    "rowOrder": 0,
                },
                {
                    "domIndex": 1,
                    "domId": "lblConsumption",
                    "label": "Consumption",
                    "value": "1.2",
                    "editable": True,
                    "dataType": "number",
                    "sectionKey": "sectionFabric",
                    "sectionName": "Fabric",
                    "itemKey": "row-1",
                    "articleCode": "FAB-001",
                    "articleName": "Jersey",
                    "rowOrder": 1,
                },
                {
                    "domIndex": 2,
                    "domId": "lblConsumption",
                    "label": "Consumption",
                    "value": "1.3",
                    "editable": True,
                    "dataType": "number",
                    "sectionKey": "sectionFabric",
                    "sectionName": "Fabric",
                    "itemKey": "row-1",
                    "articleCode": "FAB-001",
                    "articleName": "Jersey",
                    "rowOrder": 1,
                },
            ],
        },
        "SWN0000001",
        costing_status="Open",
        season="SS27",
    )

    assert document["title"] == "FOB Main"
    assert document["sections"][0]["section_key"] == "sectionFabric"
    assert document["items"][0]["article_code"] == "FAB-001"
    assert [field["field_key"] for field in document["fields"]] == [
        "lblTitle",
        "lblConsumption",
        "lblConsumption__2",
    ]
    assert document["fields"][1]["_live"]["dom_index"] == 1
    assert document["signature"]


def test_inventory_preserves_two_rows_of_the_same_article():
    document = costing._inventory_to_document(
        {
            "title": "FOB Main",
            "sections": [{"sectionKey": "fabric", "name": "Fabric", "rowOrder": 1}],
            "fields": [
                {
                    "domIndex": 1,
                    "domId": "lblMaterialColorList",
                    "dataField": "colMaterialColorList",
                    "label": "Material Color",
                    "value": "[Table]",
                    "editable": True,
                    "dataType": "text",
                    "sectionKey": "fabric",
                    "sectionName": "Fabric",
                    "itemKey": "F0000585::117001::1",
                    "articleCode": "F0000585",
                    "articleName": "Shell Fabric",
                    "rowOrder": 1,
                },
                {
                    "domIndex": 2,
                    "domId": "lblMaterialColorList",
                    "dataField": "colMaterialColorList",
                    "label": "Material Color",
                    "value": "JL NAVY(19-3922-TCX)",
                    "editable": True,
                    "dataType": "text",
                    "sectionKey": "fabric",
                    "sectionName": "Fabric",
                    "itemKey": "F0000585::117002::2",
                    "articleCode": "F0000585",
                    "articleName": "Shell Fabric",
                    "rowOrder": 2,
                },
            ],
        },
        "SKN0000188",
        costing_status="Open",
    )

    matching_items = [
        item for item in document["items"] if item["article_code"] == "F0000585"
    ]
    matching_fields = [
        field
        for field in document["fields"]
        if field["field_key"] == "colMaterialColorList"
    ]
    assert [item["item_key"] for item in matching_items] == [
        "F0000585::117001::1",
        "F0000585::117002::2",
    ]
    assert [field["item_key"] for field in matching_fields] == [
        "F0000585::117001::1",
        "F0000585::117002::2",
    ]


def test_inventory_script_carries_article_into_continuation_rows():
    source = costing._COSTING_INVENTORY_JS

    assert "articleText === '>>'" in source
    assert "if (!shown(articleElement))" in source
    assert "effectiveArticleByRow" in source
    assert "articleRowCounts" in source
    assert "itemKey = `${article.code}::${stableRow}::${ordinal}`" in source


def test_inventory_filters_every_forbidden_control():
    fields = [
        {
            "domIndex": index,
            "domId": control_id,
            "label": control_id,
            "value": "",
            "editable": True,
        }
        for index, control_id in enumerate(
            [
                "colBodyType",
                "imgDeleteSection",
                "imgEditSection",
                "imgCopySection",
            ]
        )
    ]

    document = costing._inventory_to_document(
        {"sections": [], "fields": fields},
        "SWN0000001",
        costing_status="Open",
    )

    assert document["fields"] == []
    assert set(costing.costing_forbidden_selectors()) == {
        "#colBodyType label span",
        "#imgDeleteSection",
        "#imgEditSection",
        "#imgCopySection",
    }


def test_scan_source_never_clicks_forbidden_selectors():
    source = Path(costing.__file__).read_text(encoding="utf-8")

    for selector in costing.costing_forbidden_selectors():
        assert f'locator("{selector}").click' not in source
        assert f"locator('{selector}').click" not in source


def test_apply_plan_requires_server_side_source_for_article_mutation():
    result = costing.apply_costing_plan(
        "SWN0000001",
        {
            "additions": [{"article_code": "FAB-001"}],
            "deletes": [],
        },
    )

    assert result["code"] == "COSTING_SOURCE_REQUIRED"
    assert result["additions"][0]["article_code"] == "FAB-001"


def test_save_uses_exact_required_xpath_and_cancellation_deferral():
    source = Path(costing.__file__).read_text(encoding="utf-8")

    assert 'xpath=//*[@id="titlebarCostSheet"]/tbody/tr/td[3]/span/div[1]' in source
    assert "with cancellation_deferred():" in source
    assert "def _create_new_costing" not in source
    assert "bring_to_front()" not in source
    assert "_reload_costing_after_save" not in source
    assert "missing_after_reload" not in source


def test_numeric_save_verification_accepts_wfx_decimal_format():
    assert costing._field_value_matches("1.0000", 1, "number")
    assert not costing._field_value_matches("1.2500", 1, "number")


def test_inventory_preserves_safe_click_target_for_composite_wfx_field():
    document = costing._inventory_to_document(
        {
            "sections": [{"sectionKey": "fabric", "name": "Fabric", "rowOrder": 1}],
            "fields": [
                {
                    "domIndex": 0,
                    "domId": "lblConsQty",
                    "clickDomId": "lblConsQty~",
                    "dataField": "colConsQty",
                    "label": "Cons. Qty.",
                    "value": "0.1000",
                    "editable": True,
                    "dataType": "number",
                    "sectionKey": "fabric",
                    "sectionName": "Fabric",
                    "itemKey": "FAB-001",
                    "articleCode": "FAB-001",
                    "articleName": "Jersey",
                    "rowOrder": 1,
                }
            ],
        },
        "SWN0000001",
        costing_status="Open",
    )

    field = document["fields"][0]
    assert field["field_key"] == "colConsQty"
    assert field["_live"]["dom_id"] == "lblConsQty"
    assert field["_live"]["click_dom_id"] == "lblConsQty~"


def test_supplier_is_applied_before_rate_and_delete_requires_comments():
    supplier = {"field_key": "colSupplierCompanyName", "label": "Supplier"}
    rate = {"field_key": "colRate1", "label": "Rate"}

    assert costing._field_application_priority(supplier) < (
        costing._field_application_priority(rate)
    )
    source = Path(costing.__file__).read_text(encoding="utf-8")
    assert "Updated via Costing import" in source
    assert "sectionCostSheetDeletionReason" in source


def test_production_fields_are_applied_in_required_wfx_order():
    minutes = {"field_key": "Minutes", "label": "Minutes"}
    header_minutes = {
        "field_key": "ProductionHeaderMinutes",
        "label": "Minutes",
    }
    value = {"field_key": "ProductionValue", "label": "Value"}
    rate = {"field_key": "colRate1", "label": "Rate"}

    priorities = [
        costing._field_application_priority(field)
        for field in (minutes, header_minutes, value, rate)
    ]

    assert priorities[0] == priorities[1]
    assert priorities[1] < priorities[2] < priorities[3]


def test_production_child_exposes_parent_minutes_and_value_as_virtual_fields():
    document = {
        "sections": [
            {
                "section_key": "section-8-Production_Costs",
                "name": "Production Costs",
                "row_order": 8,
            }
        ],
        "items": [
            {
                "section_key": "section-8-Production_Costs",
                "section_name": "Production Costs",
                "item_key": "parent",
                "row_order": 48,
                "action": "UPSERT",
                "item_type": "cost_line",
                "article_code": "",
                "article_name": "Production Costs",
            },
            {
                "section_key": "section-8-Production_Costs",
                "section_name": "Production Costs",
                "item_key": "child",
                "row_order": 49,
                "action": "UPSERT",
                "item_type": "cost_line",
                "article_code": "",
                "article_name": "CM (PRODUCTIONPROCESS100001)",
            },
        ],
        "fields": [
            {
                "scope": "item",
                "section_key": "section-8-Production_Costs",
                "item_key": "parent",
                "field_key": "Minutes",
                "label": "Minutes",
                "value": 1,
                "data_type": "number",
                "editable": True,
                "required": False,
                "options": [],
                "row_order": 48,
                "_live": {"row_index": 48, "dom_id": "lblMinutes"},
            },
            {
                "scope": "item",
                "section_key": "section-8-Production_Costs",
                "item_key": "parent",
                "field_key": "colValue",
                "label": "Value",
                "value": 100,
                "data_type": "number",
                "editable": True,
                "required": False,
                "options": [],
                "row_order": 48,
                "_live": {"row_index": 48, "dom_id": "lblValue"},
            },
        ],
    }

    costing._add_production_value_fields(document)

    virtual = {
        field["field_key"]: field
        for field in document["fields"]
        if field["item_key"] == "child"
    }
    assert set(virtual) == {"ProductionHeaderMinutes", "ProductionValue"}
    assert virtual["ProductionHeaderMinutes"]["_live"]["row_index"] == 48
    assert virtual["ProductionValue"]["_live"]["dom_id"] == "lblValue"


def test_hidden_select2_uses_wfx_change_event_without_select_option():
    calls = []

    class Editor:
        def get_attribute(self, name):
            assert name == "class"
            return "clsSectionSelect select2-hidden-accessible"

        def evaluate(self, script, value):
            calls.append(("evaluate", script, value))
            return True

        def select_option(self, **_kwargs):
            raise AssertionError("Không dùng select_option cho Select2 ẩn")

    costing._apply_inline_select_option(Editor(), "77952")

    assert calls[0][0] == "evaluate"
    assert "dispatchEvent(new Event('change'" in calls[0][1]
    assert calls[0][2] == "77952"


def test_regular_select_still_uses_native_select_option():
    calls = []

    class Editor:
        def get_attribute(self, name):
            assert name == "class"
            return "clsSectionSelect"

        def select_option(self, **kwargs):
            calls.append(kwargs)

    costing._apply_inline_select_option(Editor(), "USD")

    assert calls == [{"value": "USD"}]


def test_tree_not_open_text_is_not_misclassified_as_open():
    class FakeTree:
        def count(self):
            return 1

        def inner_text(self, timeout):
            assert timeout == 1_000
            return "Internal Cost Sheet Status: Not Open"

    class FakeFrame:
        def locator(self, selector):
            assert selector == costing.COSTING_TREE_SELECTOR
            return FakeTree()

    assert costing._status_from_tree(FakeFrame()) == "Not Open"


def test_active_costing_page_uses_only_visible_focused_tab():
    class Locator:
        def __init__(self, count):
            self._count = count

        def count(self):
            return self._count

    class Frame:
        url = "https://example.test/frame"

        def __init__(self, has_costing):
            self.has_costing = has_costing

        def locator(self, selector):
            return Locator(
                int(self.has_costing and selector == costing.COSTING_DETAIL_SELECTOR)
            )

    class Page:
        def __init__(self, visible, focused, has_costing):
            self.frames = [Frame(has_costing)]
            self.state = {"visible": visible, "focused": focused}

        def evaluate(self, _script):
            return self.state

    hidden_costing = Page(False, False, True)
    active_costing = Page(True, True, True)
    unrelated = Page(True, False, False)
    context = type(
        "Context",
        (),
        {"pages": [hidden_costing, unrelated, active_costing]},
    )()

    assert costing._active_costing_page(context) is active_costing


def test_active_costing_page_refuses_ambiguous_visible_windows():
    class Locator:
        def count(self):
            return 1

    class Frame:
        def locator(self, _selector):
            return Locator()

    class Page:
        frames = [Frame()]

        def evaluate(self, _script):
            return {"visible": True, "focused": False}

    context = type("Context", (), {"pages": [Page(), Page()]})()

    try:
        costing._active_costing_page(context)
    except Exception as error:
        assert str(error) == "COSTING_ACTIVE_TAB_AMBIGUOUS"
    else:
        raise AssertionError("Phải từ chối khi không xác định duy nhất tab Costing")


def test_active_costing_page_uses_current_cdp_target_order():
    class Locator:
        def count(self):
            return 1

    class Frame:
        def locator(self, _selector):
            return Locator()

    class Page:
        def __init__(self, target_id):
            self.target_id = target_id
            self.frames = [Frame()]

        def evaluate(self, _script):
            return {"visible": True, "focused": True}

    class Session:
        def __init__(self, page):
            self.page = page

        def send(self, method):
            if method == "Target.getTargetInfo":
                return {"targetInfo": {"targetId": self.page.target_id}}
            return {
                "targetInfos": [
                    {"targetId": "tab-2", "type": "page"},
                    {"targetId": "tab-1", "type": "page"},
                ]
            }

        def detach(self):
            return None

    old = Page("tab-1")
    current = Page("tab-2")

    class Context:
        pages = [old, current]

        def new_cdp_session(self, page):
            return Session(page)

    assert costing._active_costing_page(Context()) is current


def test_article_code_is_read_from_current_article_page_title():
    page = type(
        "Page",
        (),
        {
            "url": "https://example.test/wfx_ArticleDetail.aspx",
            "frames": [],
            "title": lambda self: "WFX Article - SWN0000001",
        },
    )()

    assert costing._article_code_from_page(page) == "SWN0000001"


def test_article_code_is_read_from_article_left_header():
    class Body:
        def inner_text(self, timeout):
            assert timeout == 1_500
            return "Style name (SKN0000188/REGULAR FIT POLO)"

    class Frame:
        name = "ArticleLeft"
        url = "https://example.test/WFXCostSheet.aspx"

        def locator(self, selector):
            assert selector == "body"
            return Body()

    class Page:
        url = "https://example.test/wfx_ArticleDetail.aspx?ID=123"
        frames = [Frame()]

        def title(self):
            return ""

    assert costing._article_code_from_page(Page()) == "SKN0000188"


def test_export_scan_allows_non_open_but_import_scan_still_blocks(monkeypatch):
    frame = object()
    document = {
        "sections": [{"section_key": "fabric"}],
        "items": [],
        "fields": [{"field_key": "rate"}],
    }
    monkeypatch.setattr(
        costing,
        "_costing_frame",
        lambda *_args, **_kwargs: (object(), frame),
    )
    monkeypatch.setattr(costing, "_status_from_tree", lambda _frame: "Approved")
    monkeypatch.setattr(
        costing,
        "_selected_costing_title",
        lambda *_args, **_kwargs: "Approved Costing",
    )
    monkeypatch.setattr(
        costing,
        "_inventory_costing_frame",
        lambda *_args, **_kwargs: document,
    )

    exported = costing._scan_open_costing_context(
        object(),
        "SWN0000001",
        require_open=False,
    )
    imported = costing._scan_open_costing_context(
        object(),
        "SWN0000001",
        require_open=True,
    )

    assert exported["code"] == "COSTING_SCANNED"
    assert imported["code"] == "COSTING_NOT_OPEN"


def test_active_tab_apply_rejects_a_different_style_before_touching_costing(
    monkeypatch,
):
    calls = []

    class Runtime:
        def stop(self):
            calls.append("stop")

    class Starter:
        def start(self):
            return Runtime()

    active_page = object()
    context = type("Context", (), {"pages": [active_page]})()
    browser = type("Browser", (), {"contexts": [context]})()
    session_page = object()
    monkeypatch.setattr(costing, "_chrome_is_ready", lambda: True)
    monkeypatch.setattr(costing, "sync_playwright", lambda: Starter())
    monkeypatch.setattr(
        costing,
        "_connect_to_chrome",
        lambda *_args, **_kwargs: (browser, session_page),
    )
    monkeypatch.setattr(costing, "_attach_dialog_handler", lambda *_args: None)
    monkeypatch.setattr(costing, "_session_is_active", lambda _page: True)
    monkeypatch.setattr(
        costing,
        "_active_costing_page",
        lambda _context: active_page,
    )
    monkeypatch.setattr(
        costing,
        "_article_code_from_page",
        lambda _page: "OTHER0001",
    )
    monkeypatch.setattr(
        costing,
        "_costing_frame",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Không được chạm Costing của style khác")
        ),
    )

    result = costing.apply_costing_plan(
        "SWN0000001",
        {"new_required": False, "additions": [], "deletes": []},
        active_tab_only=True,
    )

    assert result["code"] == "COSTING_STYLE_MISMATCH"
    assert result["live_style"] == "OTHER0001"
    assert calls == ["stop"]
