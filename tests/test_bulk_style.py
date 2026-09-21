from __future__ import annotations

import ast
import inspect

import pytest
from playwright.sync_api import Error as PlaywrightError

from tests.fakes.automation_boundary import wire_automation
from tests.fakes.module_reflection import module_source, module_trees, patch_automation
from tests.fakes.wfx_dom import install_fake_clock
from tests.fakes.wfx_style import StyleWorld, build_style_fields
from wfx_panel.automation import bulk_style, catalog, runtime


def test_copy_search_rule_uses_article_code_or_name_only():
    source = module_source(bulk_style)
    assert "COPY_ARTICLE_CODE_NAME_XPATH" in source
    assert "COPY_BUYER_REFERENCE_XPATH" not in source
    assert "ArticleCode/Name" in source


def test_copy_flow_selects_costsheet_then_copy_as_variant():
    source = module_source(bulk_style)
    assert "COPY_COSTSHEET_XPATH" in source
    assert "COPY_AS_VARIANT_XPATH" in source
    assert source.index("costsheet.check()") < source.index("variant.click()")


def test_style_flow_contains_mandatory_defaults():
    defaults = {
        label: value
        for label, value, _ids, _labels in bulk_style.FIXED_STYLE_FIELDS
    }
    assert defaults == {
        "Purchase UOM": "Pcs",
        "Price Per": "Article",
        "Color Definition": "Single Colors",
    }


def test_style_automation_only_saves_when_auto_save_is_enabled():
    source = inspect.getsource(bulk_style.prepare_catalog_style_row)
    assert "titlebarArticle" not in source
    assert "if saved:" in source
    assert "_save_style(context, log)" in source
    assert "requires_manual_save=not saved" in source
    assert bulk_style.SAVE_STYLE_XPATH.endswith("/span/div[1]/a")


def test_group_class_detection_accepts_actual_lowercase_wfx_class():
    catalog_source = (
        module_source(catalog)
    )
    assert "[...li.classList, ...span.classList]" in catalog_source
    assert "name.toLocaleLowerCase('en') === 'groupnode'" in catalog_source


def test_style_flow_selects_exact_new_toolbar_action():
    source = module_source(bulk_style)
    assert "def _new_style_link" in source
    assert 'candidate.inner_text().strip().casefold() == "new"' in source


def test_auto_save_click_is_wrapped_in_cancellation_deferred():
    """Stop bấm đúng lúc Save đang chạy không được trả ACTION_CANCELLED.

    ``_wait()`` gọi checkpoint(); nếu click Save nằm ngoài cancellation_deferred,
    người dùng nhận báo đã hủy trong khi WFX đã tạo Style, chạy lại dòng đó là
    sinh Style trùng.
    """
    target = _function("_save_style")
    guarded = [
        node
        for node in ast.walk(target)
        if isinstance(node, ast.With)
        and any(
            isinstance(item.context_expr, ast.Call)
            and getattr(item.context_expr.func, "id", None)
            == "cancellation_deferred"
            for item in node.items
        )
    ]
    assert guarded, "_save_style phải bọc click Save trong cancellation_deferred()"
    protected = {
        line
        for block in guarded
        for node in ast.walk(block)
        if (line := getattr(node, "lineno", None)) is not None
    }
    clicks = [
        node.lineno
        for node in ast.walk(target)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "click"
    ]
    waits = [
        node.lineno
        for node in ast.walk(target)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_wait"
    ]
    assert clicks and set(clicks) <= protected
    assert waits and set(waits) <= protected


def test_open_style_choice_does_not_block_on_a_new_page_event():
    """WFX tái dùng cửa sổ CatalogDetail nên page event không phát lại.

    Chờ blocking ở đây làm mỗi dòng Tạo Style mất trọn timeout dù popup đã sẵn
    sàng; frame scan mới là nguồn xác nhận và nhận được cả hai trường hợp.
    """
    source = inspect.getsource(bulk_style._open_style_choice)
    assert "context.expect_page(" not in source
    assert "_article_left_frame(context, timeout_s=timeout_s)" in source


# Hai test dọn popup trước đây assert chuỗi trong `inspect.getsource` đã chuyển
# sang `tests/test_bulk_style_popup_cleanup.py`: ở đó `_close_pages_opened_since`
# được chạy thật trên context giả, còn ràng buộc "dọn trong finally" và "prepare
# không tự đóng popup" được kiểm bằng AST thay vì tìm chuỗi.


class FakePage:
    def __init__(self, name: str, *, refuses_close: bool = False) -> None:
        self.name = name
        self.refuses_close = refuses_close
        self.close_calls: list[bool] = []

    def close(self, run_before_unload: bool = True) -> None:
        self.close_calls.append(run_before_unload)
        if self.refuses_close:
            raise PlaywrightError("Target closed")

    def __repr__(self) -> str:  # pragma: no cover - chỉ để đọc lỗi test
        return f"<FakePage {self.name}>"


class FakeContext:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages


def test_only_pages_opened_by_this_run_are_closed():
    user_tab = FakePage("tab người dùng")
    reused = FakePage("cửa sổ CatalogDetail có sẵn")
    opened = FakePage("popup do lượt quét mở")
    known = {user_tab, reused}
    context = FakeContext([user_tab, reused, opened])

    bulk_style._close_pages_opened_since(context, known)

    assert user_tab.close_calls == []
    assert reused.close_calls == [], (
        "WFX tái dùng cửa sổ CatalogDetail; đóng nó là đóng tab của người dùng"
    )
    assert opened.close_calls == [False], (
        "Phải bỏ qua beforeunload, nếu không form điền dở sẽ chặn bằng dialog"
    )


def test_cleanup_continues_when_one_popup_refuses_to_close():
    stubborn = FakePage("popup Chrome còn giữ target", refuses_close=True)
    other = FakePage("popup thứ hai")
    context = FakeContext([stubborn, other])

    bulk_style._close_pages_opened_since(context, set())

    assert other.close_calls == [False], (
        "Một popup lỗi không được làm mất kết quả quét đã đọc xong"
    )


def test_nothing_is_closed_when_the_run_opened_nothing():
    existing = [FakePage("a"), FakePage("b")]
    context = FakeContext(existing)

    bulk_style._close_pages_opened_since(context, set(existing))

    assert all(page.close_calls == [] for page in existing)


def _function(name: str) -> ast.FunctionDef:
    """Định nghĩa của một hàm trong package bulk_style, dù nó ở file con nào."""
    found = next(
        (
            node
            for _path, tree in module_trees(bulk_style)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == name
        ),
        None,
    )
    assert found is not None, f"Hàm đã đổi tên: {name}"
    return found


def _calls_cleanup(node: ast.AST) -> list[int]:
    return [
        child.lineno
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and (
            getattr(child.func, "id", "") or getattr(child.func, "attr", "")
        )
        == "_close_pages_opened_since"
    ]


def test_option_scan_cleans_up_inside_finally():
    """Bị Stop hoặc lỗi giữa chừng vẫn phải dọn, nên cleanup nằm trong finally."""
    scan = _function("scan_catalog_style_options")
    finallys = [
        node
        for node in ast.walk(scan)
        if isinstance(node, ast.Try) and node.finalbody
    ]
    in_finally = {
        line
        for node in finallys
        for statement in node.finalbody
        for line in _calls_cleanup(statement)
    }
    assert _calls_cleanup(scan), "Lượt quét không còn dọn popup nào"
    assert set(_calls_cleanup(scan)) == in_finally, (
        "Mọi lời gọi dọn popup phải nằm trong finally, nếu không một lần Stop "
        "sẽ để lại form New Style điền dở."
    )


def test_prepare_style_row_never_closes_its_own_popup():
    """Popup của prepare_style_row là kết quả người dùng cần xem và tự Save."""
    prepare = _function("prepare_catalog_style_row")
    assert _calls_cleanup(prepare) == [], (
        "prepare_style_row không được đóng popup vừa mở cho người dùng "
        f"(dòng {_calls_cleanup(prepare)})"
    )


VALID_NEW_ROW = {
    "type": "New",
    "material_type": "Apparel",
    "buyer": "J.LINDEBERG",
    "division": "PSHK",
    "product_group": "Jacket",
    "sub_category": "Padded",
    "color_card": "Main",
    "size_range": "XS-XXL",
    "season": "SS27",
    "buyer_style_ref": "JL-1001",
    "internal_style_ref": "INT-1001",
    "source_row": 4,
}

COPY_ROW = {
    "type": "Copy",
    "style_copy": "SWN0000001",
    "buyer": "J.LINDEBERG",
    "season": "FW26",
    "source_row": 7,
}


@pytest.fixture
def clock(monkeypatch):
    return install_fake_clock(monkeypatch, bulk_style)


@pytest.fixture
def world(clock):
    return StyleWorld(clock)


def _logs() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lines.append


def _wire(
    monkeypatch,
    world: StyleWorld,
    *,
    folder_kind: str = "group",
    **boundary,
) -> None:
    """Chỉ giả lập ranh giới ngoài module: folder + Playwright/trang WFX."""
    patch_automation(
        monkeypatch, bulk_style,
        "open_catalog_folder",
        lambda *_args, **_kwargs: {
            "ok": True,
            "code": "CATALOG_FOLDER_OPENED",
            "folder": {"kind": folder_kind, "id": "42"},
        },
    )
    wire_automation(monkeypatch, bulk_style, world, **boundary)


def _prepare(world: StyleWorld, row: dict, **kwargs) -> dict:
    _lines, log = _logs()
    return bulk_style.prepare_catalog_style_row(
        "01",
        kwargs.pop("group_id", "42"),
        row,
        log=log,
        **kwargs,
    )


# --- Toggle Tự động Save ------------------------------------------------


def test_auto_save_off_stops_before_save(monkeypatch, world):
    """Mặc định phải dừng trước Save để người dùng tự kiểm tra."""
    _wire(monkeypatch, world)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["code"] == "STYLE_FORM_READY"
    assert result["saved"] is False
    assert result["requires_manual_save"] is True
    assert world.save_clicks == 0, "Save khi user chưa bật toggle là tạo Style ngoài ý muốn"
    assert "tự bấm Save" in result["message"]


def test_auto_save_on_clicks_save_exactly_once(monkeypatch, world):
    _wire(monkeypatch, world)

    result = _prepare(world, dict(VALID_NEW_ROW), auto_save=True)

    assert result["code"] == "STYLE_FORM_READY"
    assert result["saved"] is True
    assert result["requires_manual_save"] is False
    assert world.save_clicks == 1, "Save hai lần có thể sinh Style trùng"


def test_save_is_never_interrupted_by_a_stop_request(monkeypatch, world):
    """Stop đúng lúc đang Save: WFX đã ghi nhưng user tưởng là chưa.

    `_save_style` bọc click + chờ trong `cancellation_deferred()` nên checkpoint
    không được ném ACTION_CANCELLED giữa chừng.
    """
    _wire(monkeypatch, world)
    _lines, log = _logs()
    # Mở sẵn form Article rồi mới bật cờ huỷ, đúng thời điểm nguy hiểm.
    world.open_style_form()
    runtime.RUNTIME._cancel.set()
    try:
        bulk_style._save_style(world.context, log)
    finally:
        runtime.RUNTIME._cancel.clear()

    assert world.save_clicks == 1


def test_stop_outside_the_save_window_still_cancels(monkeypatch, world):
    """Đối chứng: ngoài vùng deferred, Stop vẫn phải dừng được flow."""
    _wire(monkeypatch, world)
    runtime.RUNTIME._cancel.set()
    try:
        with pytest.raises(runtime.AutomationCancelled):
            runtime.checkpoint()
    finally:
        runtime.RUNTIME._cancel.clear()


# --- Ba field cố định ---------------------------------------------------


def test_fixed_fields_are_always_applied(monkeypatch, world):
    """Purchase UOM=Pcs, Price Per=Article, Color Definition=Single Colors."""
    _wire(monkeypatch, world)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert world.applied_value("ddlStorageUOM") == "Pcs"
    assert world.applied_value("ddlPricePer") == "Article"
    assert world.applied_value("ddlColorDefinition") == "Single Colors"
    for label in ("Purchase UOM", "Price Per", "Color Definition"):
        assert label in result["filled_fields"]


def test_row_values_reach_the_matching_wfx_controls(monkeypatch, world):
    _wire(monkeypatch, world)

    _prepare(world, dict(VALID_NEW_ROW))

    assert world.applied_value("ddlBuyer") == "J.LINDEBERG"
    assert world.applied_value("ddlSeason") == "SS27"
    assert world.applied_value("txtBuyerStyleRef") == "JL-1001"
    assert world.applied_value("txtInternalStyleRef") == "INT-1001"


def test_missing_option_names_the_field_instead_of_failing_at_save(
    monkeypatch,
    clock,
):
    world = StyleWorld(clock, fields=build_style_fields({"ddlSeason": ["FW26"]}))
    _wire(monkeypatch, world)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["ok"] is False
    assert result["code"] == "STYLE_FIELD_NOT_AVAILABLE"
    assert "Season" in result["message"]
    assert world.save_clicks == 0


# --- Dòng New thiếu dữ liệu --------------------------------------------


def test_new_row_missing_a_required_field_is_rejected(monkeypatch, world):
    _wire(monkeypatch, world)
    row = dict(VALID_NEW_ROW)
    row["division"] = ""

    result = _prepare(world, row)

    assert result["ok"] is False
    assert result["code"] == "STYLE_REQUIRED_FIELD_MISSING"
    assert "Division" in result["message"]
    assert world.save_clicks == 0


def test_copy_row_may_leave_fields_empty(monkeypatch, world):
    """Copy kế thừa từ Style nguồn nên không bắt buộc đủ field như New."""
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "SWN0000001"}
    ]

    result = _prepare(world, dict(COPY_ROW))

    assert result["code"] == "STYLE_FORM_READY"
    assert result["style_type"] == "Copy"
    assert world.applied_value("ddlBuyer") == "J.LINDEBERG"


# --- Chọn Style nguồn ---------------------------------------------------


def test_copy_searches_by_article_code_or_name_not_buyer_reference(
    monkeypatch,
    world,
):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "SWN0000001"}
    ]

    _prepare(world, dict(COPY_ROW))

    assert world.choice.copy_search_field.fills == ["SWN0000001"]
    assert world.choice.copy_search_button.clicks == 1


def test_a_single_source_style_is_selected_automatically(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 3, "article_code": "SWN0000001", "label": "SWN0000001"}
    ]

    result = _prepare(world, dict(COPY_ROW))

    assert result["code"] == "STYLE_FORM_READY"
    assert world.choice.clicked_copy_index == 3


def test_multiple_source_styles_stop_for_the_user_to_choose(monkeypatch, world):
    """Không được tự chọn dòng đầu: Copy sai Style là tạo nhầm dữ liệu."""
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"},
        {"choice_index": 1, "article_code": "SWN0000002", "label": "B"},
    ]

    result = _prepare(world, dict(COPY_ROW))

    assert result["ok"] is True
    assert result["code"] == "STYLE_COPY_MULTIPLE_RESULTS"
    assert len(result["choices"]) == 2
    assert result["source_row"] == 7
    assert world.choice.clicked_copy_index is None
    assert world.save_clicks == 0


def test_user_choice_is_honoured_and_validated(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"},
        {"choice_index": 1, "article_code": "SWN0000002", "label": "B"},
    ]

    result = _prepare(world, dict(COPY_ROW), copy_choice=1)

    assert result["code"] == "STYLE_FORM_READY"
    assert world.choice.clicked_copy_index == 1


def test_a_choice_outside_the_current_result_set_is_refused(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"},
        {"choice_index": 1, "article_code": "SWN0000002", "label": "B"},
    ]

    result = _prepare(world, dict(COPY_ROW), copy_choice=9)

    assert result["ok"] is False
    assert result["code"] == "STYLE_COPY_CHOICE_INVALID"
    assert world.choice.clicked_copy_index is None


def test_a_stale_choice_is_refused_even_when_one_result_remains(
    monkeypatch,
    world,
):
    """Tập kết quả co lại còn một Style KHÁC thì không được Copy im lặng.

    Giữa lượt `STYLE_COPY_MULTIPLE_RESULTS` và lượt xác nhận, dữ liệu WFX có
    thể đổi. Copy tạo dữ liệu thật nên phải dừng cho người dùng chọn lại.
    """
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 5, "article_code": "SWN0000009", "label": "Style khác"}
    ]

    result = _prepare(world, dict(COPY_ROW), copy_choice=1)

    assert result["ok"] is False
    assert result["code"] == "STYLE_COPY_CHOICE_INVALID"
    assert world.choice.clicked_copy_index is None
    assert world.save_clicks == 0


def test_a_choice_that_still_matches_is_honoured_when_one_result_remains(
    monkeypatch,
    world,
):
    """Đối chứng: cùng một Style thì vẫn chạy tiếp bình thường."""
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 1, "article_code": "SWN0000002", "label": "B"}
    ]

    result = _prepare(world, dict(COPY_ROW), copy_choice=1)

    assert result["code"] == "STYLE_FORM_READY"
    assert world.choice.clicked_copy_index == 1


def test_no_source_style_found_is_reported(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = []

    result = _prepare(world, dict(COPY_ROW))

    assert result["ok"] is False
    assert result["code"] == "STYLE_COPY_NOT_FOUND"


def test_source_row_detached_before_the_click_is_reported(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"}
    ]
    world.choice.copy_click_succeeds = False

    result = _prepare(world, dict(COPY_ROW))

    assert result["ok"] is False
    assert result["code"] == "STYLE_COPY_RESULT_DETACHED"


# --- CostSheet + Copy as Variant ---------------------------------------


def test_copy_always_selects_costsheet_and_copy_as_variant(monkeypatch, world):
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"}
    ]

    _prepare(world, dict(COPY_ROW))

    assert world.choice.costsheet.is_checked() is True
    assert world.choice.copy_as_variant.clicks == 1


def test_costsheet_already_ticked_is_not_toggled_off(monkeypatch, clock):
    world = StyleWorld(clock, costsheet_checked=True)
    _wire(monkeypatch, world)
    world.choice.copy_results = [
        {"choice_index": 0, "article_code": "SWN0000001", "label": "A"}
    ]

    _prepare(world, dict(COPY_ROW))

    assert world.choice.costsheet.is_checked() is True
    assert world.choice.costsheet.check_calls == 0, (
        "Tick lại checkbox đang bật sẽ bỏ chọn CostSheet"
    )


# --- Điều kiện vào flow -------------------------------------------------


def test_a_folder_that_is_not_a_group_never_touches_chrome(monkeypatch, world):
    _wire(monkeypatch, world, folder_kind="folder")

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["ok"] is False
    assert result["code"] == "STYLE_GROUP_REQUIRED"
    assert world.group.opened_popup == 0
    assert world.save_clicks == 0


def test_a_non_numeric_group_id_is_rejected_before_opening_the_folder(
    monkeypatch,
    world,
):
    opened: list[str] = []
    patch_automation(
        monkeypatch, bulk_style,
        "open_catalog_folder",
        lambda *args, **_kwargs: opened.append(str(args)) or {"ok": True},
    )

    result = _prepare(world, dict(VALID_NEW_ROW), group_id="chưa chọn")

    assert result["code"] == "STYLE_GROUP_REQUIRED"
    assert opened == []


@pytest.mark.parametrize("kind", ["", "revise", "NEW STYLE"])
def test_only_new_or_copy_are_accepted(monkeypatch, world, kind):
    _wire(monkeypatch, world)
    row = dict(VALID_NEW_ROW)
    row["type"] = kind

    result = _prepare(world, row)

    assert result["ok"] is False
    assert result["code"] == "STYLE_TYPE_INVALID"


def test_a_failing_folder_open_is_returned_unchanged(monkeypatch, world):
    patch_automation(
        monkeypatch, bulk_style,
        "open_catalog_folder",
        lambda *_args, **_kwargs: {
            "ok": False,
            "code": "CATALOG_FOLDER_STALE",
            "message": "Cây thư mục đã đổi.",
        },
    )

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["code"] == "CATALOG_FOLDER_STALE"


# --- Một lượt chỉ chuẩn bị một dòng -------------------------------------


def test_one_call_prepares_exactly_one_row_and_returns_to_the_user(
    monkeypatch,
    world,
):
    _wire(monkeypatch, world)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["source_row"] == 4
    assert world.group.opened_popup == 1, "Mỗi lượt chỉ được mở New đúng một lần"
    assert world.group_page.bring_to_front_calls == 1, (
        "Phải đưa WFX lên trước để người dùng kiểm tra dòng vừa chuẩn bị"
    )


# --- Lượt quét dropdown -------------------------------------------------


def _scan(world: StyleWorld, group_id: str = "42") -> dict:
    _lines, log = _logs()
    return bulk_style.scan_catalog_style_options("01", group_id, log=log)


def test_option_scan_never_saves_and_cleans_up_its_own_popup(monkeypatch, world):
    """Lượt quét chỉ đọc option; form New Style điền dở không được để lại."""
    _wire(monkeypatch, world)

    result = _scan(world)

    assert result["code"] == "STYLE_OPTIONS_SCANNED"
    assert world.save_clicks == 0, "Lượt quét tuyệt đối không được Save"
    assert world.popup_page.closed is True, (
        "Form New Style điền dở là rác do chính lượt quét tạo ra"
    )
    assert world.group_page.closed is False, "Không được đụng tab của người dùng"


def test_option_scan_returns_options_for_every_required_field(monkeypatch, world):
    _wire(monkeypatch, world)

    result = _scan(world)

    fields = result["fields"]
    assert [item["label"] for item in fields["buyer"]] == [
        "J.LINDEBERG",
        "TRUEWERK",
    ]
    assert [item["label"] for item in fields["season"]] == ["SS27", "FW26"]
    assert result["subcategories_by_product_group"], (
        "Sub-Category phụ thuộc Product Group nên phải quét theo từng nhóm"
    )


def test_option_scan_still_cleans_up_when_the_scan_fails(monkeypatch, clock):
    """Kể cả khi lỗi hoặc bị Stop, popup của lượt quét vẫn phải bị đóng."""
    world = StyleWorld(clock, fields=build_style_fields({"ddlSeason": []}))
    _wire(monkeypatch, world)

    result = _scan(world)

    assert result["ok"] is False
    assert result["code"] == "STYLE_OPTIONS_SCAN_FAILED"
    assert "Season" in result["message"]
    assert world.popup_page.closed is True


def test_option_scan_refuses_a_node_that_is_not_a_group(monkeypatch, world):
    _wire(monkeypatch, world, folder_kind="folder")

    result = _scan(world)

    assert result["ok"] is False
    assert result["code"] == "STYLE_GROUP_REQUIRED"
    assert world.group.opened_popup == 0


# --- Ranh giới trình duyệt / phiên đăng nhập ----------------------------


def test_playwright_driver_is_always_released(monkeypatch, world):
    _wire(monkeypatch, world)

    _prepare(world, dict(VALID_NEW_ROW))

    assert world.driver_stops == 1, "Giữ driver sau flow là rò rỉ Playwright"


@pytest.mark.parametrize(
    ("ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_prepare_reports_browser_boundary_codes_for_auto_recovery(
    monkeypatch,
    world,
    ready,
    logged_in,
    expected,
):
    """PanelAPI khớp đúng hai mã này để mở lại Chrome và đăng nhập lại.

    Gộp chúng vào STYLE_PREPARE_FAILED là mất hẳn cơ chế khôi phục, lại còn
    gửi telemetry cho một tình huống bình thường.
    """
    _wire(monkeypatch, world, chrome_ready=ready, logged_in=logged_in)

    result = _prepare(world, dict(VALID_NEW_ROW))

    assert result["ok"] is False
    assert result["code"] == expected
    assert world.driver_stops == 1


@pytest.mark.parametrize(
    ("ready", "logged_in", "expected"),
    [
        (False, True, "CHROME_CLOSED"),
        (True, False, "NOT_LOGGED_IN"),
    ],
)
def test_option_scan_reports_browser_boundary_codes(
    monkeypatch,
    world,
    ready,
    logged_in,
    expected,
):
    _wire(monkeypatch, world, chrome_ready=ready, logged_in=logged_in)

    result = _scan(world)

    assert result["code"] == expected
    assert world.driver_stops == 1
